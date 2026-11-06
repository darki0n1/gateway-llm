# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests de la PolicyConfig (résidence des données)."""

from __future__ import annotations

import pytest

from gateway_llm.policy import PolicyConfig


# ─── Règle simple, liste explicite ─────────────────────────────
def test_provider_allowed():
    p = PolicyConfig(
        residency={
            "public": {"allowed_providers": ["groq", "mistral"]},
        }
    )
    assert p.is_allowed("groq", "public")
    assert p.is_allowed("mistral", "public")


def test_provider_denied():
    p = PolicyConfig(
        residency={
            "confidential": {"allowed_providers": ["ollama"]},
        }
    )
    assert not p.is_allowed("groq", "confidential")
    assert p.is_allowed("ollama", "confidential")


# ─── Sensibilité inconnue → default_allow ──────────────────────
def test_unknown_sensitivity_default_allow_true():
    p = PolicyConfig(
        residency={
            "confidential": {"allowed_providers": ["ollama"]},
        }
    )
    assert p.is_allowed("groq", "sensibilité_inconnue")


def test_unknown_sensitivity_default_allow_false():
    p = PolicyConfig(
        residency={"confidential": {"allowed_providers": ["ollama"]}},
        default_allow=False,
    )
    assert not p.is_allowed("groq", "sensibilité_inconnue")
    assert not p.is_allowed("ollama", "sensibilité_inconnue")


# ─── Règle "default" fallback ──────────────────────────────────
def test_default_rule_used_for_unknown_sensitivity():
    p = PolicyConfig(
        residency={
            "confidential": {"allowed_providers": ["ollama"]},
            "default": {"allowed_providers": ["ollama", "mistral"]},
        }
    )
    assert p.is_allowed("mistral", "sensibilité_inconnue")
    assert not p.is_allowed("groq", "sensibilité_inconnue")
    assert not p.is_allowed("mistral", "confidential")


# ─── Wildcards ─────────────────────────────────────────────────
def test_wildcard_prefix():
    p = PolicyConfig(
        residency={
            "public": {"allowed_providers": ["groq-*", "mistral"]},
        }
    )
    assert p.is_allowed("groq-eu", "public")
    assert p.is_allowed("groq-us", "public")
    assert not p.is_allowed("groq", "public")
    assert p.is_allowed("mistral", "public")


def test_wildcard_all():
    p = PolicyConfig(
        residency={
            "public": {"allowed_providers": ["*"]},
        }
    )
    assert p.is_allowed("n-importe-quoi", "public")


def test_wildcard_suffix():
    p = PolicyConfig(
        residency={
            "internal": {"allowed_providers": ["*-eu", "ollama"]},
        }
    )
    assert p.is_allowed("mistral-eu", "internal")
    assert p.is_allowed("groq-eu", "internal")
    assert not p.is_allowed("groq-us", "internal")
    assert p.is_allowed("ollama", "internal")


# ─── Formes acceptées (dict ou liste) ──────────────────────────
def test_list_form_normalized():
    p = PolicyConfig(residency={"confidential": ["ollama"]})
    assert p.is_allowed("ollama", "confidential")
    assert not p.is_allowed("groq", "confidential")


def test_dict_form_accepted():
    p = PolicyConfig(
        residency={
            "confidential": {"allowed_providers": ["ollama"]},
        }
    )
    assert p.is_allowed("ollama", "confidential")


# ─── allowed_providers() helper ────────────────────────────────
def test_allowed_providers_returns_list():
    p = PolicyConfig(
        residency={
            "public": {"allowed_providers": ["a", "b", "c"]},
        }
    )
    assert p.allowed_providers("public") == ["a", "b", "c"]


def test_allowed_providers_unknown_returns_empty():
    p = PolicyConfig(
        residency={
            "public": {"allowed_providers": ["a"]},
        }
    )
    assert p.allowed_providers("sensibilité_inconnue") == []


def test_allowed_providers_default_rule():
    p = PolicyConfig(
        residency={
            "default": {"allowed_providers": ["x", "y"]},
        }
    )
    assert p.allowed_providers("sensibilité_inconnue") == ["x", "y"]


# ─── Validation YAML shape (tests d'erreur volontaires) ────────
def test_residency_must_be_dict():
    with pytest.raises(Exception):
        # Erreur attendue : Pylance est averti via le commentaire
        PolicyConfig(residency="not a dict")  # type: ignore[arg-type]


def test_rule_must_be_dict_or_list():
    with pytest.raises(Exception):
        # 42 n'est ni dict, ni list, ni ResidencyRule → rejet pydantic
        PolicyConfig(residency={"public": 42})  # type: ignore[dict-item]
