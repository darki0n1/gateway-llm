# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Orchestrateur de batch : checkpointing, reprise, dry-run, budget, rapport."""

from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from gateway_llm.benchmarks.aggregator import BenchmarkAggregator
from gateway_llm.budget import BudgetTracker
from gateway_llm.checkpoint import Checkpoint
from gateway_llm.classifier import ClassificationResult, TaskClassifier
from gateway_llm.config import LocalMode, ModelsConfig, PolicyConfig, load_local_mode
from gateway_llm.guardrails.base import Guardrail
from gateway_llm.guardrails.noop import NoOpGuardrail
from gateway_llm.hardware import HardwareInfo
from gateway_llm.providers.base import Provider
from gateway_llm.providers.cloudflare import CloudflareProvider
from gateway_llm.providers.ollama import OllamaProvider
from gateway_llm.providers.openai_compat import OpenAICompatibleProvider
from gateway_llm.quota import QuotaManager
from gateway_llm.router import Router
from gateway_llm.secrets import SecretBackend, get_backend

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
        progress_callback: Callable[[int, int, float], None] | None = None,
        ensure_markdown: bool = True,
    ) -> None:
        self._cfg = config
        self._in = input_path
        self._out = output_path
        self._policy = policy
        self._benchmarks = benchmarks
        self._hardware = hardware
        self._guardrail = guardrail or NoOpGuardrail()

        if secrets is not None:
            self._secrets = secrets
        else:
            try:
                self._secrets = get_backend()
            except RuntimeError as e:
                raise RuntimeError(
                    f"{e}\n"
                    "Lancez `gateway-llm setup-secrets` ou ouvrez l'onglet "
                    "Configuration de la GUI."
                ) from e

        self._classifier = classifier
        self._classifier_model = classifier_model
        self._disable_classifier = disable_classifier
        self._max_cost_eur = max_cost_eur
        self._resume = resume
        self._dry_run = dry_run
        self._sample_size = sample_size
        self._progress_callback = progress_callback
        self._ensure_markdown = ensure_markdown
        self._cancel_event: threading.Event | None = None

    # ────────────────────────────────────────────────────────────
    # Sélection locale par benchmarks + hardware
    # ────────────────────────────────────────────────────────────
    def _build_default_benchmarks(self) -> BenchmarkAggregator:
        from gateway_llm.benchmarks.benchlm import BenchLMAdapter
        from gateway_llm.benchmarks.f5_safety import F5SafetyAdapter
        from gateway_llm.benchmarks.rankllms import RankLLMsAdapter
        from gateway_llm.benchmarks.rws_translation import RWSTranslationAdapter

        return BenchmarkAggregator(
            [
                BenchLMAdapter(),
                RankLLMsAdapter(),
                F5SafetyAdapter(),
                RWSTranslationAdapter(),
            ],
            force_refresh=False,
        )

    def _ensure_ollama_models(self) -> None:
        """Bootstrap : install les modèles Ollama déclarés dans les chaînes."""
        from gateway_llm.installer import Installer

        ollama_provider = self._cfg.providers.get("ollama")
        if ollama_provider is None or ollama_provider.type != "ollama":
            return

        required: set[str] = set()
        for domain_cfg in self._cfg.domains.values():
            for model_key in domain_cfg.chain:
                mc = self._cfg.models.get(model_key)
                if mc is None:
                    continue
                provider = self._cfg.providers.get(mc.provider)
                if provider is not None and provider.type == "ollama":
                    required.add(mc.model_name or model_key)

        if "nomic-embed-text" in self._cfg.models:
            required.add("nomic-embed-text")

        if not self._disable_classifier:
            required.add(self._classifier_model)

        if not required:
            return

        log.info("Bootstrap Ollama : %s", ", ".join(sorted(required)))
        try:
            installer = Installer(interactive=False, assume_yes=True)
            n = installer.ensure_models(sorted(required))
            if n:
                log.info("%d modèle(s) Ollama installé(s) (bootstrap)", n)
        except Exception as e:
            log.warning("Bootstrap Ollama échoué (non bloquant) : %s", e)

    def _apply_local_mode(
        self,
        benchmarks: BenchmarkAggregator,
        local_mode: LocalMode,
    ) -> list[str] | None:
        """Retourne les modèles à installer selon le mode (ou None)."""
        if local_mode == LocalMode.CLOUD_ONLY:
            log.info("Mode cloud-only : aucun modèle local")
            return None

        if local_mode in (LocalMode.LOCAL_ONLY, LocalMode.HYBRID):
            from gateway_llm.hardware import detect_hardware
            from gateway_llm.local_selector import select_local_models

            hw = self._hardware or detect_hardware()
            selected = select_local_models(
                benchmarks, hw, domains=list(self._cfg.domains.keys())
            )
            to_install = sorted({m for models in selected.values() for m in models})
            if to_install:
                log.info(
                    "Mode %s : %d modèle(s) local(aux) : %s",
                    local_mode.value,
                    len(to_install),
                    ", ".join(to_install),
                )
            else:
                log.warning(
                    "Aucun modèle local sélectionnable (benchmarks ou hardware)"
                )
            return to_install

        # DEFAULT
        self._ensure_ollama_models()
        return None

    # ────────────────────────────────────────────────────────────
    # Refresh lazy des benchmarks
    # ────────────────────────────────────────────────────────────
    def _maybe_refresh_benchmarks(self) -> None:
        ttl_days = int(os.environ.get("GATEWAY_LLM_BENCHMARK_TTL_DAYS", "14"))
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
            log.info("Benchmarks obsolètes (%.1f jours), rafraîchissement…", age_days)
        else:
            log.info("Premier lancement : rafraîchissement initial des benchmarks")

        try:
            from gateway_llm.benchmarks.base import TaskCategory

            agg = self._build_default_benchmarks()
            for cat in TaskCategory:
                agg.get_scores(cat)
            log.info("Benchmarks rafraîchis")
        except Exception as e:
            log.warning("Rafraîchissement benchmarks échoué (non bloquant) : %s", e)

    # ────────────────────────────────────────────────────────────
    # Providers
    # ────────────────────────────────────────────────────────────
    def _build_providers(self) -> dict[str, Provider]:
        providers: dict[str, Provider] = {}
        for name, pcfg in self._cfg.providers.items():
            if pcfg.type == "ollama":
                providers[name] = OllamaProvider(
                    name=name,
                    base_url=pcfg.base_url,
                    timeout=pcfg.timeout,
                )
                continue

            api_key = self._secrets.get(pcfg.secret_name) if pcfg.secret_name else None
            if not api_key and not pcfg.local:
                log.warning("Provider '%s' sans secret, ignoré", name)
                continue

            if pcfg.type == "openai_compat":
                providers[name] = OpenAICompatibleProvider(
                    name=name,
                    base_url=pcfg.base_url,
                    secret=api_key or "",
                    extra_headers=pcfg.extra_headers,
                    timeout=pcfg.timeout,
                )
            elif pcfg.type == "cloudflare":
                account_id = (
                    self._secrets.get(pcfg.account_secret_name)
                    if pcfg.account_secret_name
                    else None
                )
                if not account_id:
                    log.warning("Cloudflare '%s' sans account_id, ignoré", name)
                    continue
                providers[name] = CloudflareProvider(
                    name=name,
                    base_url=pcfg.base_url,
                    api_key=api_key or "",
                    account_id=account_id,
                    timeout=pcfg.timeout,
                )
        return providers

    # ────────────────────────────────────────────────────────────
    # Classifieur
    # ────────────────────────────────────────────────────────────
    def _build_classifier(
        self,
        providers: dict[str, Provider],
    ) -> TaskClassifier | None:
        if self._disable_classifier:
            log.info("Classification automatique désactivée")
            return None
        if self._classifier is not None:
            return self._classifier

        mode = load_local_mode()

        if mode == LocalMode.CLOUD_ONLY:
            flex = providers.get("flexrouter")
            if flex is not None:
                log.info("Classifieur cloud-only via flexrouter (bucket 'low')")
                return TaskClassifier(provider=flex, model="low")
            log.warning(
                "Mode cloud-only mais flexrouter absent : classification désactivée"
            )
            return None

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
            self._estimate_tokens(t.get("prompt", "") + " " + t.get("task_text", ""))
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
        self._maybe_refresh_benchmarks()

        benchmarks = self._benchmarks or self._build_default_benchmarks()
        local_mode = load_local_mode()
        log.info("Mode d'exécution : %s", local_mode.value)

        to_install = self._apply_local_mode(benchmarks, local_mode)
        if to_install:
            from gateway_llm.installer import Installer
            Installer(interactive=False, assume_yes=True).ensure_models(to_install)

        providers = self._build_providers()

        if local_mode == LocalMode.CLOUD_ONLY:
            providers = {k: v for k, v in providers.items() if k != "ollama"}
            log.info("Providers cloud-only : %s", list(providers.keys()))

        if not providers:
            raise RuntimeError(
                "Aucun provider disponible. Vérifiez vos secrets ou votre mode."
            )

        budget = (
            BudgetTracker(max_eur=self._max_cost_eur)
            if self._max_cost_eur is not None
            else None
        )
        router = Router(
            config=self._cfg,
            providers=providers,
            guardrail=self._guardrail,
            quota=QuotaManager(),
            policy=self._policy,
            benchmarks=benchmarks,
            hardware=self._hardware,
            budget=budget,
        )
        classifier = self._build_classifier(providers)

        # --- Comptage préalable pour la barre de progression ---
        total_tasks = sum(1 for _ in self._iter_tasks())
        processed_since_start = 0
        # -------------------------------------------------------

        checkpoint = Checkpoint(self._out)
        stats = BatchStats(done_before=checkpoint.done_count)
        start = time.monotonic()

        for task in self._iter_tasks():
            if self._cancel_event is not None and self._cancel_event.is_set():
                log.info("Annulation demandée, arrêt du batch")
                break

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
                        text, task.get("description", "")
                    )
                    domain = classification.domain
                    stats.classified += 1
                    log.info(
                        "[%s] classifié: domain=%s status=%s prio=%d",
                        task_id,
                        classification.domain,
                        classification.status,
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
                checkpoint.append(
                    {
                        "id": task_id,
                        "domain": domain,
                        "sensitivity": sensitivity,
                        "status": "human_review",
                        "reason": f"blocked by classifier: {classification.status}",
                        "classification": _serialize_classification(classification),
                    }
                )
                stats.processed += 1
                stats.human_review += 1
                stats.per_domain[domain] = stats.per_domain.get(domain, 0) + 1
                log.info("[%s] → human_review (%s)", task_id, classification.status)

                processed_since_start += 1
                if self._progress_callback is not None:
                    elapsed = time.monotonic() - start
                    current_total = stats.done_before + processed_since_start
                    speed = processed_since_start / elapsed if elapsed > 0 else 0
                    self._progress_callback(current_total, total_tasks, speed)
                continue

            if classification is not None and classification.human_priority >= 9:
                checkpoint.append(
                    {
                        "id": task_id,
                        "domain": domain,
                        "sensitivity": sensitivity,
                        "status": "human_review",
                        "reason": f"priorité critique ({classification.human_priority})",
                        "classification": _serialize_classification(classification),
                    }
                )
                stats.processed += 1
                stats.human_review += 1
                stats.per_domain[domain] = stats.per_domain.get(domain, 0) + 1
                log.info(
                    "[%s] → human_review (priorité %d)",
                    task_id,
                    classification.human_priority,
                )

                processed_since_start += 1
                if self._progress_callback is not None:
                    elapsed = time.monotonic() - start
                    current_total = stats.done_before + processed_since_start
                    speed = processed_since_start / elapsed if elapsed > 0 else 0
                    self._progress_callback(current_total, total_tasks, speed)
                continue

            # 3) Préparation image
            log.info("[%s] route domain=%s sensitivity=%s", task_id, domain, sensitivity)
            image_b64: str | None = None
            image_ref = task.get("image_path") or task.get("image_b64")
            if image_ref:
                if image_ref.startswith("data:"):
                    image_b64 = image_ref.split(",", 1)[1]
                else:
                    img_path = pathlib.Path(image_ref)
                    if img_path.exists():
                        image_b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
                    else:
                        log.warning("[%s] image_path introuvable: %s", task_id, image_ref)

            # 4) Routage
            result = router.route(
                task_text=text,
                domain=domain,
                sensitivity=sensitivity,
                prompt=task.get("prompt"),
                image_b64=image_b64,
                ensure_markdown=self._ensure_markdown,
            )

            if result.success:
                status = "approved"
                stats.approved += 1
                stats.per_model[result.model_used] = stats.per_model.get(result.model_used, 0) + 1
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

            processed_since_start += 1
            if self._progress_callback is not None:
                elapsed = time.monotonic() - start
                current_total = stats.done_before + processed_since_start
                speed = processed_since_start / elapsed if elapsed > 0 else 1.0
                self._progress_callback(current_total, total_tasks, speed)

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