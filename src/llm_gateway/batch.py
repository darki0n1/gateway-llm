# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Orchestrateur de batch : checkpointing, reprise, dry-run, budget, rapport."""

from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
import time
from dataclasses import dataclass, field

from llm_gateway.benchmarks.aggregator import BenchmarkAggregator
from llm_gateway.budget import BudgetTracker
from llm_gateway.checkpoint import Checkpoint
from llm_gateway.classifier import ClassificationResult, TaskClassifier
from llm_gateway.config import ModelsConfig, PolicyConfig
from llm_gateway.guardrails.base import Guardrail
from llm_gateway.guardrails.noop import NoOpGuardrail
from llm_gateway.hardware import HardwareInfo
from llm_gateway.providers.base import Provider
from llm_gateway.providers.cloudflare import CloudflareProvider
from llm_gateway.providers.ollama import OllamaProvider
from llm_gateway.providers.openai_compat import OpenAICompatibleProvider
from llm_gateway.quota import QuotaManager
from llm_gateway.router import Router
from llm_gateway.secrets import SecretBackend, get_backend

log = logging.getLogger(__name__)


@dataclass
class BatchStats:
    total: int = 0
    done_before: int = 0
    processed: int = 0
    approved: int = 0
    human_review: int = 0
    failed: int = 0
    budget_exceeded_tasks: int = 0
    classified: int = 0
    total_escalations: int = 0
    per_model: dict[str, int] = field(default_factory=dict)
    per_domain: dict[str, int] = field(default_factory=dict)
    spent_eur: float = 0.0
    budget_exceeded: bool = False
    elapsed_s: float = 0.0


def _serialize_classification(c: ClassificationResult) -> dict:
    return {
        "domain": c.domain,
        "status": c.status,
        "human_priority": c.human_priority,
        "risk_level": c.risk_level,
        "flags": c.flags,
        "reason": c.reason,
    }


class BatchRunner:
    def __init__(
        self,
        config: ModelsConfig,
        input_path: pathlib.Path,
        output_path: pathlib.Path,
        policy: PolicyConfig | None = None,
        benchmarks: BenchmarkAggregator | None = None,
        hardware: HardwareInfo | None = None,
        guardrail: Guardrail | None = None,
        secrets: SecretBackend | None = None,
        classifier: TaskClassifier | None = None,
        classifier_model: str = "qwen3:4b-instruct",
        disable_classifier: bool = False,
        max_cost_eur: float | None = None,
        resume: bool = False,
        dry_run: bool = False,
        sample_size: int = 20,
    ) -> None:
        self._cfg = config
        self._in = input_path
        self._out = output_path
        self._policy = policy
        self._benchmarks = benchmarks
        self._hardware = hardware
        self._guardrail = guardrail or NoOpGuardrail()

        # Résolution explicite du backend de secrets (pas de bascule silencieuse)
        if secrets is not None:
            self._secrets = secrets
        else:
            try:
                self._secrets = get_backend()
            except RuntimeError as e:
                raise RuntimeError(
                    f"{e}\n"
                    "Lancez `llm-gateway setup-secrets` ou ouvrez l'onglet "
                    "Configuration de la GUI."
                ) from e

        self._classifier = classifier
        self._classifier_model = classifier_model
        self._disable_classifier = disable_classifier
        self._max_cost_eur = max_cost_eur
        self._resume = resume
        self._dry_run = dry_run
        self._sample_size = sample_size

    # ────────────────────────────────────────────────────────────
    # Refresh lazy des benchmarks (au démarrage d'un batch)
    # ────────────────────────────────────────────────────────────
    def _maybe_refresh_benchmarks(self) -> None:
        """Rafraîchit le cache benchmarks si plus vieux que N jours.

        Contrôlé par la variable d'environnement LLM_GATEWAY_BENCHMARK_TTL_DAYS
        (défaut: 14). Non bloquant : une erreur réseau est un simple warning.
        """
        ttl_days = int(os.environ.get("LLM_GATEWAY_BENCHMARK_TTL_DAYS", "14"))
        cache_dir = pathlib.Path("benchmarks_cache")

        if cache_dir.exists():
            latest = max(
                (p.stat().st_mtime for p in cache_dir.glob("*.json")),
                default=0.0,
            )
            age_days = (time.time() - latest) / 86400 if latest else 999.0
            if age_days < ttl_days:
                log.info("Benchmarks à jour (%.1f jours < %d)", age_days, ttl_days)
                return
            log.info(
                "Benchmarks obsolètes (%.1f jours), rafraîchissement…",
                age_days,
            )
        else:
            log.info("Premier lancement : rafraîchissement initial des benchmarks")

        try:
            from llm_gateway.benchmarks.base import TaskCategory
            from llm_gateway.benchmarks.benchlm import BenchLMAdapter
            from llm_gateway.benchmarks.f5_safety import F5SafetyAdapter
            from llm_gateway.benchmarks.rankllms import RankLLMsAdapter
            from llm_gateway.benchmarks.rws_translation import RWSTranslationAdapter

            sources = [
                BenchLMAdapter(),
                RankLLMsAdapter(),
                F5SafetyAdapter(),
                RWSTranslationAdapter(),
            ]
            agg = BenchmarkAggregator(sources, force_refresh=True)
            for cat in TaskCategory:
                agg.get_scores(cat)
            log.info("Benchmarks rafraîchis")
        except Exception as e:
            log.warning("Rafraîchissement benchmarks échoué (non bloquant) : %s", e)

    # ────────────────────────────────────────────────────────────
    # Construction des providers
    # ────────────────────────────────────────────────────────────
    def _build_providers(self) -> dict[str, Provider]:
        providers: dict[str, Provider] = {}
        for name, pcfg in self._cfg.providers.items():
            if pcfg.type == "ollama":
                providers[name] = OllamaProvider(
                    name=name, base_url=pcfg.base_url, timeout=pcfg.timeout,
                )
                continue

            api_key = self._secrets.get(pcfg.secret_name) if pcfg.secret_name else None
            if not api_key and not pcfg.local:
                log.warning("Provider '%s' sans secret, ignoré", name)
                continue

            if pcfg.type == "openai_compat":
                providers[name] = OpenAICompatibleProvider(
                    name=name, base_url=pcfg.base_url, secret=api_key or "",
                    extra_headers=pcfg.extra_headers, timeout=pcfg.timeout,
                )
            elif pcfg.type == "cloudflare":
                account_id = (
                    self._secrets.get(pcfg.account_secret_name)
                    if pcfg.account_secret_name else None
                )
                if not account_id:
                    log.warning("Cloudflare '%s' sans account_id, ignoré", name)
                    continue
                providers[name] = CloudflareProvider(
                    name=name, base_url=pcfg.base_url, api_key=api_key or "",
                    account_id=account_id, timeout=pcfg.timeout,
                )
        return providers

    # ────────────────────────────────────────────────────────────
    # Construction du classifieur
    # ────────────────────────────────────────────────────────────
    def _build_classifier(
        self, providers: dict[str, Provider],
    ) -> TaskClassifier | None:
        if self._disable_classifier:
            log.info("Classification automatique désactivée")
            return None
        if self._classifier is not None:
            return self._classifier
        ollama = providers.get("ollama")
        if ollama is None:
            log.info("Pas de provider Ollama : classification désactivée")
            return None
        log.info("Classification automatique via %s", self._classifier_model)
        return TaskClassifier(provider=ollama, model=self._classifier_model)

    # ────────────────────────────────────────────────────────────
    # Lecture JSONL
    # ────────────────────────────────────────────────────────────
    def _iter_tasks(self):
        with self._in.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    log.warning("Ligne JSON invalide ignorée : %s", e)

    # ────────────────────────────────────────────────────────────
    # Estimation tokens
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return int(len(text.split()) * 1.3) + 10

    # ────────────────────────────────────────────────────────────
    # Dry-run
    # ────────────────────────────────────────────────────────────
    def _run_dry(self) -> BatchStats:
        log.info("Dry-run : échantillon de %d tâches", self._sample_size)
        samples: list[dict] = []
        total = 0
        for task in self._iter_tasks():
            total += 1
            if len(samples) < self._sample_size:
                samples.append(task)

        if not samples:
            log.warning("Fichier d'entrée vide")
            return BatchStats()

        in_tokens = sum(
            self._estimate_tokens(
                t.get("prompt", "") + " " + t.get("task_text", "")
            )
            for t in samples
        )
        out_tokens = 400 * len(samples)
        factor = total / len(samples)
        est_in = int(in_tokens * factor)
        est_out = int(out_tokens * factor)

        print("\n=== DRY-RUN ===")
        print(f"Total tâches        : {total}")
        print(f"Échantillon         : {len(samples)}")
        print(f"Tokens entrée est.  : {est_in:,}")
        print(f"Tokens sortie est.  : {est_out:,}")
        print(f"Temps local (~15t/s): ~{est_out / 15 / 60:.1f} min")
        print(f"Temps cloud (~50t/s): ~{est_out / 50 / 60:.1f} min")
        if self._max_cost_eur is not None:
            print(f"Budget plafond      : {self._max_cost_eur:.2f} €")
        print("===============\n")
        return BatchStats(total=total)

    # ────────────────────────────────────────────────────────────
    # Run réel
    # ────────────────────────────────────────────────────────────
    def _run_real(self) -> BatchStats:
        # Refresh lazy AVANT tout appel (non bloquant si échec)
        self._maybe_refresh_benchmarks()

        providers = self._build_providers()
        if not providers:
            raise RuntimeError("Aucun provider disponible (secrets ?)")

        budget = (
            BudgetTracker(max_eur=self._max_cost_eur)
            if self._max_cost_eur is not None else None
        )
        router = Router(
            config=self._cfg,
            providers=providers,
            guardrail=self._guardrail,
            quota=QuotaManager(),
            policy=self._policy,
            benchmarks=self._benchmarks,
            hardware=self._hardware,
            budget=budget,
        )
        classifier = self._build_classifier(providers)

        checkpoint = Checkpoint(self._out)
        stats = BatchStats(done_before=checkpoint.done_count)
        start = time.monotonic()

        for task in self._iter_tasks():
            stats.total += 1
            task_id = task.get("id")
            if not task_id:
                log.warning("Tâche sans id ignorée")
                continue

            if self._resume and checkpoint.is_done(task_id):
                continue

            text = task.get("task_text") or task.get("prompt", "")
            domain = task.get("domain")
            sensitivity = task.get("sensitivity", "public")
            classification: ClassificationResult | None = None

            # 1) Classification si domaine absent
            if domain is None:
                if classifier is not None:
                    classification = classifier.classify(
                        text, task.get("description", ""),
                    )
                    domain = classification.domain
                    stats.classified += 1
                    log.info(
                        "[%s] classifié: domain=%s status=%s prio=%d",
                        task_id, classification.domain, classification.status,
                        classification.human_priority,
                    )
                else:
                    domain = "prompt_creation"
                    log.debug(
                        "[%s] pas de domaine ni classifieur, défaut: prompt_creation",
                        task_id,
                    )

            # 2) Raccourci human_review
            if classification is not None and classification.status.startswith("blocked"):
                record = {
                    "id": task_id,
                    "domain": domain,
                    "sensitivity": sensitivity,
                    "status": "human_review",
                    "reason": f"blocked by classifier: {classification.status}",
                    "classification": _serialize_classification(classification),
                }
                checkpoint.append(record)
                stats.processed += 1
                stats.human_review += 1
                stats.per_domain[domain] = stats.per_domain.get(domain, 0) + 1
                log.info("[%s] → human_review (%s)", task_id, classification.status)
                continue

            if classification is not None and classification.human_priority >= 9:
                record = {
                    "id": task_id,
                    "domain": domain,
                    "sensitivity": sensitivity,
                    "status": "human_review",
                    "reason": f"priorité critique ({classification.human_priority})",
                    "classification": _serialize_classification(classification),
                }
                checkpoint.append(record)
                stats.processed += 1
                stats.human_review += 1
                stats.per_domain[domain] = stats.per_domain.get(domain, 0) + 1
                log.info(
                    "[%s] → human_review (priorité %d)",
                    task_id, classification.human_priority,
                )
                continue

            # 3) Préparation éventuelle de l'image
            log.info(
                "[%s] route domain=%s sensitivity=%s",
                task_id, domain, sensitivity,
            )
            image_b64: str | None = None
            image_ref = task.get("image_path") or task.get("image_b64")
            if image_ref:
                if image_ref.startswith("data:"):
                    image_b64 = image_ref.split(",", 1)[1]
                else:
                    img_path = pathlib.Path(image_ref)
                    if img_path.exists():
                        image_b64 = base64.b64encode(
                            img_path.read_bytes()
                        ).decode("ascii")
                    else:
                        log.warning(
                            "[%s] image_path introuvable: %s", task_id, image_ref,
                        )

            # 4) Routage (router.route doit accepter image_b64)
            result = router.route(
                task_text=text,
                domain=domain,
                sensitivity=sensitivity,
                prompt=task.get("prompt"),
                image_b64=image_b64,
            )

            if result.success:
                status = "approved"
                stats.approved += 1
                stats.per_model[result.model_used] = (
                    stats.per_model.get(result.model_used, 0) + 1
                )
            elif result.budget_exceeded:
                status = "budget_exceeded"
                stats.budget_exceeded_tasks += 1
            elif result.response:
                status = "human_review"
                stats.human_review += 1
            else:
                status = "failed"
                stats.failed += 1

            stats.total_escalations += result.escalations
            stats.per_domain[domain] = stats.per_domain.get(domain, 0) + 1
            if budget is not None:
                stats.spent_eur = budget.snapshot().spent_eur
                if budget.exceeded():
                    stats.budget_exceeded = True

            record = {
                "id": task_id,
                "domain": domain,
                "sensitivity": sensitivity,
                "status": status,
                "response": result.response,
                "model_used": result.model_used,
                "provider": result.provider,
                "guardrail_passed": result.guardrail_passed,
                "guardrail_reason": result.guardrail_reason,
                "escalations": result.escalations,
                "cost_eur": result.cost_eur,
                "errors": result.errors,
                "had_image": image_b64 is not None,
            }
            if classification is not None:
                record["classification"] = _serialize_classification(classification)

            checkpoint.append(record)
            stats.processed += 1

        stats.elapsed_s = time.monotonic() - start
        self._print_report(stats)
        return stats

    # ────────────────────────────────────────────────────────────
    # Rapport
    # ────────────────────────────────────────────────────────────
    def _print_report(self, s: BatchStats) -> None:
        print("\n=== RAPPORT BATCH ===")
        print(f"Total tâches        : {s.total}")
        print(f"Déjà traitées       : {s.done_before}")
        print(f"Traitées ce run     : {s.processed}")
        print(f"  Approuvées        : {s.approved}")
        print(f"  → human_review    : {s.human_review}")
        print(f"  Budget dépassé    : {s.budget_exceeded_tasks}")
        print(f"  Échec technique   : {s.failed}")
        if s.classified:
            print(f"Classifiées         : {s.classified}")
        print(f"Escalades totales   : {s.total_escalations}")
        if s.spent_eur or s.budget_exceeded:
            print(f"Coût cumulé         : {s.spent_eur:.4f} €")
        if s.budget_exceeded:
            print("⚠️  Budget global dépassé pendant le run")
        print(f"Durée               : {s.elapsed_s:.1f}s")
        if s.per_model:
            print("Modèles utilisés :")
            for m, c in sorted(s.per_model.items(), key=lambda x: -x[1]):
                print(f"  {m}: {c}")
        if s.per_domain:
            print("Domaines :")
            for d, c in sorted(s.per_domain.items(), key=lambda x: -x[1]):
                print(f"  {d}: {c}")
        print("=====================\n")

    def run(self) -> BatchStats:
        if self._dry_run:
            return self._run_dry()
        return self._run_real()