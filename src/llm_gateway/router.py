# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Routeur LLM avec cascade, guardrails, quotas, benchmarks, hardware, budget.

Logique :
  1. Prend le domaine et la chaîne de modèles de config/models.yaml.
  2. Réordonne la chaîne par benchmarks (si aggregator fourni).
  3. Filtre par PolicyConfig (résidence des données).
  4. Filtre par QuotaManager (providers en cooldown).
  5. Filtre par HardwareInfo (fit VRAM, non bloquant par défaut).
  6. Essaie chaque modèle dans l'ordre.
  7. Guardrail exécuté UNE FOIS sur la première réponse réussie :
     - is_valid=True  -> succès, retour immédiat
     - is_valid=False -> fin de chaîne, réponse préservée pour review
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from llm_gateway.benchmarks.aggregator import BenchmarkAggregator
from llm_gateway.benchmarks.base import TaskCategory
from llm_gateway.budget import BudgetTracker
from llm_gateway.config import ModelsConfig, PolicyConfig
from llm_gateway.guardrails.base import Guardrail, GuardrailResult
from llm_gateway.hardware import HardwareInfo
from llm_gateway.providers.base import (
    Provider,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from llm_gateway.quota import QuotaManager

log = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    success: bool
    response: str = ""
    model_used: str = ""
    provider: str = ""
    domain: str = ""
    guardrail_passed: bool = False
    guardrail_reason: str = ""
    escalations: int = 0
    errors: list[str] = field(default_factory=list)
    cost_eur: float = 0.0
    budget_exceeded: bool = False


class Router:
    def __init__(
        self,
        config: ModelsConfig,
        providers: dict[str, Provider],
        guardrail: Guardrail,
        quota: QuotaManager | None = None,
        policy: PolicyConfig | None = None,
        benchmarks: BenchmarkAggregator | None = None,
        hardware: HardwareInfo | None = None,
        budget: BudgetTracker | None = None,
    ) -> None:
        self._config = config
        self._providers = providers
        self._guardrail = guardrail
        self._quota = quota or QuotaManager()
        self._policy = policy
        self._benchmarks = benchmarks
        self._hardware = hardware
        self._budget = budget

    def route(
        self,
        task_text: str,
        domain: str,
        sensitivity: str = "public",
        prompt: str | None = None,
        temperature: float = 0.3,
        image_b64: str | None = None,
    ) -> RoutingResult:
        if domain not in self._config.domains:
            return RoutingResult(
                success=False, domain=domain,
                errors=[f"domaine inconnu : {domain}"],
            )

        # Budget global déjà dépassé : on n'essaie même pas
        if self._budget is not None and self._budget.exceeded():
            return RoutingResult(
                success=False, domain=domain, budget_exceeded=True,
                errors=["budget dépassé, cascade annulée"],
            )

        dom_cfg = self._config.domains[domain]
        prompt = prompt or task_text
        errors: list[str] = []
        escalations = 0
        chain = list(dom_cfg.chain)

        # Re-ranking dynamique par benchmarks (optionnel)
        if self._benchmarks is not None:
            try:
                category = TaskCategory(domain)
                chain = self._benchmarks.rank_chain(chain, category)
                log.info("Chaîne réordonnée par benchmarks: %s", chain)
            except ValueError:
                log.debug(
                    "Pas de catégorie benchmark pour '%s', chaîne statique",
                    domain,
                )

        for model_key in chain:
            model_cfg = self._config.models[model_key]
            provider_name = model_cfg.provider

            # 1) Politique de résidence
            if self._policy and not self._policy.is_allowed(provider_name, sensitivity):
                errors.append(f"{model_key}: interdit par policy ({sensitivity})")
                continue

            # 2) Cooldown provider (429 récent)
            if not self._quota.is_available(provider_name):
                remaining = self._quota.cooldown_remaining(provider_name)
                errors.append(f"{model_key}: cooldown ({remaining:.0f}s restantes)")
                continue

            # 3) Hardware-aware (informatif, non bloquant par défaut)
            if model_cfg.size_gb is not None and self._hardware is not None:
                fit = self._hardware.estimate_fit(model_cfg.size_gb)
                if fit.category in ("slow", "very_slow"):
                    log.warning(
                        "Modèle local %s : %s (ratio %.1fx)",
                        model_key, fit.note, fit.ratio or 0.0,
                    )
                elif fit.category == "acceptable":
                    log.info("Modèle local %s : %s", model_key, fit.note)
                if self._hardware.should_skip(model_cfg.size_gb):
                    errors.append(
                        f"{model_key}: skip hardware "
                        f"(seuil {self._hardware.skip_threshold}x)"
                    )
                    continue

            provider = self._providers.get(provider_name)
            if provider is None:
                errors.append(f"{model_key}: provider '{provider_name}' non instancié")
                continue

            # 4) Tentative
            real_model = self._config.resolve_model_name(model_key)
            log.info(
                "route domain=%s model=%s provider=%s escalation=%d",
                domain, model_key, provider_name, escalations,
            )

            try:
                resp = provider.complete(
                    model=real_model,
                    prompt=prompt,
                    max_tokens=dom_cfg.max_tokens,
                    temperature=temperature,
                    image_b64=image_b64,
                )
            except RateLimitError:
                self._quota.record_rate_limit(provider_name)
                errors.append(f"{model_key}: rate limit → cooldown")
                escalations += 1
                continue
            except ProviderUnavailableError as e:
                errors.append(f"{model_key}: {e}")
                escalations += 1
                continue
            except ProviderError as e:
                errors.append(f"{model_key}: {e}")
                escalations += 1
                continue

            # Coût estimé (0.0 par défaut si prix non renseignés)
            model_cost = model_cfg.compute_cost(
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
            )
            if self._budget is not None:
                self._budget.record(model_cost)

            # 5) Guardrail — filtre final, PAS un signal d'escalade
            gr: GuardrailResult = self._guardrail.check(task_text, resp.text)
            if gr.is_valid:
                return RoutingResult(
                    success=True,
                    response=resp.text,
                    model_used=model_key,
                    provider=provider_name,
                    domain=domain,
                    guardrail_passed=True,
                    escalations=escalations,
                    errors=errors,
                    cost_eur=model_cost,
                )

            # Guardrail fail : fin de chaîne, on renvoie la réponse
            # pour que l'appelant décide (human_review dans BatchRunner)
            log.warning(
                "guardrail reject model=%s reason=%s", model_key, gr.reason,
            )
            return RoutingResult(
                success=False,
                response=resp.text,
                model_used=model_key,
                provider=provider_name,
                domain=domain,
                guardrail_passed=False,
                guardrail_reason=gr.reason,
                escalations=escalations,
                errors=errors + [f"{model_key}: guardrail rejeté ({gr.reason})"],
                cost_eur=model_cost,
            )

        return RoutingResult(
            success=False,
            domain=domain,
            escalations=escalations,
            errors=errors,
        )