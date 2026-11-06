# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests du Router (cascade, policy, quota, hardware, budget, benchmarks)."""

from __future__ import annotations

import pytest

from gateway_llm.benchmarks.aggregator import BenchmarkAggregator
from gateway_llm.benchmarks.base import BenchmarkResult, BenchmarkSource, TaskCategory
from gateway_llm.benchmarks.cache import BenchmarkCache
from gateway_llm.budget import BudgetTracker
from gateway_llm.config import (
    DomainChain,
    ModelConfig,
    ModelsConfig,
    PolicyConfig,
    ProviderConfig,
)
from gateway_llm.guardrails.base import Guardrail, GuardrailResult
from gateway_llm.guardrails.noop import NoOpGuardrail
from gateway_llm.hardware import HardwareInfo
from gateway_llm.providers.base import (
    ProviderResponse,
    RateLimitError,
)
from gateway_llm.quota import QuotaManager
from gateway_llm.router import Router

from .helpers import FakeProvider, make_response


class AlwaysFailGuardrail(Guardrail):
    def check(self, task_text, response):
        return GuardrailResult(is_valid=False, reason="fake fail", flagged=True)


def _two_model_config() -> ModelsConfig:
    return ModelsConfig(
        providers={
            "p1": ProviderConfig(type="openai_compat", base_url="http://x", local=True),
            "p2": ProviderConfig(type="openai_compat", base_url="http://x", local=True),
        },
        models={
            "m1": ModelConfig(provider="p1"),
            "m2": ModelConfig(provider="p2"),
        },
        domains={"generation": DomainChain(chain=["m1", "m2"], max_tokens=100)},
    )


def _make_router(config, providers, **kwargs):
    kwargs.setdefault("guardrail", NoOpGuardrail())
    kwargs.setdefault("quota", QuotaManager())
    return Router(config=config, providers=providers, **kwargs)


# ─── Cas nominal ──────────────────────────────────────────────
def test_success_first_model(minimal_config):
    provider = FakeProvider("fake", [make_response("hello")])
    router = _make_router(minimal_config, {"fake": provider})
    result = router.route("task", "generation")
    assert result.success
    assert result.response == "hello"
    assert result.model_used == "m1"
    assert result.guardrail_passed
    assert result.escalations == 0


def test_unknown_domain(minimal_config):
    router = _make_router(minimal_config, {})
    result = router.route("task", "not_a_domain")
    assert not result.success
    assert "inconnu" in result.errors[0]


# ─── Escalade technique ───────────────────────────────────────
def test_escalates_on_rate_limit():
    config = _two_model_config()
    p1 = FakeProvider("p1", [RateLimitError("429")])
    p2 = FakeProvider("p2", [make_response("second")])
    router = _make_router(config, {"p1": p1, "p2": p2})
    result = router.route("task", "generation")
    assert result.success
    assert result.model_used == "m2"
    assert result.escalations == 1


def test_all_providers_fail():
    config = _two_model_config()
    p1 = FakeProvider("p1", [RateLimitError("429")])
    p2 = FakeProvider("p2", [RateLimitError("429")])
    router = _make_router(config, {"p1": p1, "p2": p2})
    result = router.route("task", "generation")
    assert not result.success
    assert result.escalations == 2
    assert len(result.errors) == 2


# ─── Guardrail : fin de chaîne, PAS escalade ──────────────────
def test_guardrail_fail_stops_chain_and_preserves_response():
    """Comportement clé : un guardrail en échec termine la chaîne,
    renvoie la réponse, et NE tente PAS le modèle suivant."""
    config = _two_model_config()
    p1 = FakeProvider("p1", [make_response("bad")])
    p2 = FakeProvider("p2", [])  # ne doit JAMAIS être appelé
    router = _make_router(
        config,
        {"p1": p1, "p2": p2},
        guardrail=AlwaysFailGuardrail(),
    )
    result = router.route("task", "generation")
    assert not result.success
    assert not result.guardrail_passed
    assert result.response == "bad"
    assert result.model_used == "m1"
    assert result.guardrail_reason == "fake fail"
    assert p1.call_count == 1
    assert p2.call_count == 0


# ─── Policy ────────────────────────────────────────────────────
def test_policy_blocks_provider():
    config = ModelsConfig(
        providers={"cloud": ProviderConfig(type="openai_compat", base_url="http://x")},
        models={"m1": ModelConfig(provider="cloud")},
        domains={"generation": DomainChain(chain=["m1"], max_tokens=100)},
    )
    policy = PolicyConfig(residency={"confidential": {"allowed_providers": []}})
    provider = FakeProvider("cloud", [])
    router = _make_router(config, {"cloud": provider}, policy=policy)
    result = router.route("task", "generation", sensitivity="confidential")
    assert not result.success
    assert provider.call_count == 0
    assert any("policy" in e for e in result.errors)


# ─── Quota ─────────────────────────────────────────────────────
def test_cooldown_skips_provider(minimal_config):
    quota = QuotaManager(cooldown_seconds=60)
    quota.record_rate_limit("fake")
    provider = FakeProvider("fake", [])
    router = _make_router(minimal_config, {"fake": provider}, quota=quota)
    result = router.route("task", "generation")
    assert not result.success
    assert provider.call_count == 0
    assert any("cooldown" in e for e in result.errors)


# ─── Budget ────────────────────────────────────────────────────
def test_budget_exceeded_before_route():
    config = _two_model_config()
    p1 = FakeProvider("p1", [])
    budget = BudgetTracker(max_eur=1.0)
    budget.record(2.0)  # déjà dépassé
    router = _make_router(config, {"p1": p1}, budget=budget)
    result = router.route("task", "generation")
    assert not result.success
    assert result.budget_exceeded is True
    assert p1.call_count == 0


def test_budget_records_cost():
    config = ModelsConfig(
        providers={"p": ProviderConfig(type="openai_compat", base_url="http://x", local=True)},
        models={
            "m1": ModelConfig(
                provider="p",
                input_price_per_1k=1.0,  # 1€ / 1000 tokens
                output_price_per_1k=2.0,
            ),
        },
        domains={"generation": DomainChain(chain=["m1"], max_tokens=100)},
    )
    # 1000 input tokens + 500 output = 1.0€ + 1.0€ = 2.0€
    provider = FakeProvider(
        "p",
        [
            ProviderResponse(
                text="ok",
                model="m1",
                provider="p",
                input_tokens=1000,
                output_tokens=500,
            ),
        ],
    )
    budget = BudgetTracker(max_eur=10.0)
    router = _make_router(config, {"p": provider}, budget=budget)
    result = router.route("task", "generation")
    assert result.success
    assert result.cost_eur == pytest.approx(2.0)
    assert budget.snapshot().spent_eur == pytest.approx(2.0)


# ─── Hardware ──────────────────────────────────────────────────
def test_hardware_no_skip_without_threshold():
    """Sans skip_threshold : on essaie le modèle même si trop gros."""
    config = ModelsConfig(
        providers={"p": ProviderConfig(type="openai_compat", base_url="http://x", local=True)},
        models={"m1": ModelConfig(provider="p", size_gb=20.0)},
        domains={"generation": DomainChain(chain=["m1"], max_tokens=100)},
    )
    hw = HardwareInfo(vram_gb=8.0, source="test", skip_threshold=None)
    provider = FakeProvider("p", [make_response("ok")])
    router = _make_router(config, {"p": provider}, hardware=hw)
    result = router.route("task", "generation")
    assert result.success
    assert provider.call_count == 1


def test_hardware_skip_with_threshold():
    """Avec skip_threshold=5 et modèle 60 Go / 8 Go VRAM = ratio 7.5 → skip."""
    config = ModelsConfig(
        providers={"p": ProviderConfig(type="openai_compat", base_url="http://x", local=True)},
        models={"m1": ModelConfig(provider="p", size_gb=60.0)},
        domains={"generation": DomainChain(chain=["m1"], max_tokens=100)},
    )
    hw = HardwareInfo(vram_gb=8.0, source="test", skip_threshold=5.0)
    provider = FakeProvider("p", [])
    router = _make_router(config, {"p": provider}, hardware=hw)
    result = router.route("task", "generation")
    assert not result.success
    assert provider.call_count == 0
    assert any("skip hardware" in e for e in result.errors)


# ─── Benchmarks ────────────────────────────────────────────────
class _FakeBenchmarkSource(BenchmarkSource):
    def __init__(self, scores: dict[str, float]):
        self.name = "fake"
        self._scores = scores

    def supports(self, category):
        return category == TaskCategory.CODE_DEBUG

    def fetch(self, category):
        return [
            BenchmarkResult(
                model_key=k,
                category=category,
                score=v,
                source="fake",
            )
            for k, v in self._scores.items()
        ]


def test_benchmarks_reorder_chain(tmp_path):
    """La chaîne est réordonnée par scores décroissants."""
    config = ModelsConfig(
        providers={
            "p1": ProviderConfig(type="openai_compat", base_url="http://x", local=True),
            "p2": ProviderConfig(type="openai_compat", base_url="http://x", local=True),
            "p3": ProviderConfig(type="openai_compat", base_url="http://x", local=True),
        },
        models={
            "m1": ModelConfig(provider="p1"),
            "m2": ModelConfig(provider="p2"),
            "m3": ModelConfig(provider="p3"),
        },
        domains={
            "code_debug": DomainChain(
                chain=["m1", "m2", "m3"],  # ordre statique
                max_tokens=100,
            ),
        },
    )
    src = _FakeBenchmarkSource({"m1": 70.0, "m2": 95.0, "m3": 80.0})
    cache = BenchmarkCache(tmp_path)
    agg = BenchmarkAggregator([src], cache=cache, force_refresh=True)

    # Le provider m2 sera appelé en premier (score 95)
    p1 = FakeProvider("p1", [])
    p2 = FakeProvider("p2", [make_response("m2 wins")])
    p3 = FakeProvider("p3", [])
    router = _make_router(
        config,
        {"p1": p1, "p2": p2, "p3": p3},
        benchmarks=agg,
    )
    result = router.route("task", "code_debug")
    assert result.success
    assert result.model_used == "m2"
    assert p2.call_count == 1
    assert p1.call_count == 0
    assert p3.call_count == 0
