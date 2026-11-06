# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from gateway_llm.classifier import DOMAINS, ClassificationResult, TaskClassifier
from gateway_llm.providers.base import ProviderUnavailableError

from .helpers import FakeProvider, make_response


def _mock_llm(payload: dict) -> FakeProvider:
    return FakeProvider("fake", [make_response(json.dumps(payload))])


# ─── Mode LLM ───────────────────────────────────────────────────
def test_llm_success():
    provider = _mock_llm({
        "domain": "code_debug",
        "status": "pending",
        "human_priority": 3,
        "risk_level": "low",
        "flags": [],
        "reason": "code python",
    })
    c = TaskClassifier(provider=provider)
    r = c.classify("Corriger ce code", "Python")
    assert r.domain == "code_debug"
    assert r.status == "pending"
    assert r.human_priority == 3


def test_llm_unknown_domain_falls_back_to_prompt_creation():
    provider = _mock_llm({
        "domain": "domaine_inconnu",
        "status": "pending",
        "human_priority": 0,
        "flags": [],
    })
    c = TaskClassifier(provider=provider)
    r = c.classify("Test", "")
    assert r.domain == "prompt_creation"


def test_llm_bad_json_uses_fallback():
    provider = FakeProvider("fake", [make_response("pas de json ici")])
    c = TaskClassifier(provider=provider)
    r = c.classify("Corriger ce code Python", "")
    assert r.domain == "code_debug"   # fallback regex


def test_llm_http_error_uses_fallback():
    provider = FakeProvider("fake", [ProviderUnavailableError("500")])
    c = TaskClassifier(provider=provider)
    r = c.classify("Corriger ce code Python", "")
    assert r.domain == "code_debug"
    assert r.reason == "Fallback regex"


def test_priority_clamped():
    provider = _mock_llm({
        "domain": "safety",
        "status": "blocked_subjective",
        "human_priority": 99,
        "flags": ["HIGH_RISK"],
    })
    c = TaskClassifier(provider=provider)
    r = c.classify("audit", "")
    assert r.human_priority == 10


def test_flags_string_converted_to_list():
    provider = _mock_llm({
        "domain": "safety",
        "status": "pending",
        "human_priority": 5,
        "flags": "HIGH_RISK",
    })
    c = TaskClassifier(provider=provider)
    r = c.classify("test", "")
    assert isinstance(r.flags, list)
    assert "HIGH_RISK" in r.flags


def test_think_tags_stripped():
    payload = json.dumps({"domain": "thinking", "status": "pending", "human_priority": 0, "flags": []})
    raw = f"<think>réflexion interne</think>\n```json\n{payload}\n```"
    provider = FakeProvider("fake", [make_response(raw)])
    c = TaskClassifier(provider=provider)
    r = c.classify("Analyse ce problème", "")
    assert r.domain == "thinking"


# ─── Fallback (pas de provider) ─────────────────────────────────
def test_no_provider_uses_fallback():
    c = TaskClassifier(provider=None)
    r = c.classify("Corriger ce code Python", "")
    assert r.domain == "code_debug"
    assert r.reason == "Fallback regex"


def test_fallback_multimodal():
    c = TaskClassifier(provider=None)
    r = c.classify("Analyse ce screenshot", "Décrire l'image")
    assert "MULTIMODAL_BLOCKED" in r.flags
    assert r.human_priority == 10
    assert r.status == "blocked_multimodal"


def test_fallback_post_2024():
    c = TaskClassifier(provider=None)
    r = c.classify("Quoi de neuf en 2025 ?", "Actualités récentes")
    assert "POST_2024_FACT_CHECK" in r.flags
    assert r.human_priority >= 8
    assert r.status == "blocked_post2024"


def test_fallback_subjective():
    c = TaskClassifier(provider=None)
    r = c.classify("Quelle formulation est plus professionnelle ?", "")
    assert "SUBJECTIVE_NORMAL" in r.flags
    assert r.human_priority >= 7


def test_fallback_high_risk():
    c = TaskClassifier(provider=None)
    r = c.classify("Vérifier injection SQL", "Audit sécurité")
    assert "HIGH_RISK" in r.flags
    assert r.human_priority >= 9


@pytest.mark.parametrize("text,expected", [
    ("Corriger ce code Python", "code_debug"),
    ("Traduire en anglais", "translation"),
    ("Audit de sécurité", "safety"),
    ("Résoudre ce problème", "problem_solving"),
    ("Analyse logique", "thinking"),
    ("Vérifier cette affirmation", "fact_checking"),
    ("Pentest ce serveur", "red_teaming"),
    ("Rédiger un prompt", "prompt_creation"),
])
def test_fallback_domain_detection(text, expected):
    c = TaskClassifier(provider=None)
    r = c.classify(text, "")
    assert r.domain == expected, f"{text} -> {r.domain} (attendu {expected})"


def test_fallback_edge_empty():
    c = TaskClassifier(provider=None)
    r = c.classify("", "")
    assert r.status == "pending"
    assert r.domain == "prompt_creation"


def test_all_domains_valid():
    """Tous les domaines produits doivent être dans la liste DOMAINS."""
    c = TaskClassifier(provider=None)
    for text in ["code", "traduire", "sécurité", "résoudre", "logique", "fact", "pentest", "prompt"]:
        r = c.classify(text, "")
        assert r.domain in DOMAINS