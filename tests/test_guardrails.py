# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests des guardrails (NoOp, Nemo)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gateway_llm.guardrails.base import Guardrail, GuardrailResult
from gateway_llm.guardrails.noop import NoOpGuardrail
from gateway_llm.guardrails.nemo import NemoGuardrail


# ─── Interface ─────────────────────────────────────────────────
def test_guardrail_is_abstract():
    with pytest.raises(TypeError):
        Guardrail()  # type: ignore[abstract]


def test_guardrail_result_defaults():
    r = GuardrailResult(is_valid=True)
    assert r.is_valid
    assert r.reason == ""
    assert r.flagged is False


# ─── NoOp ──────────────────────────────────────────────────────
def test_noop_always_valid():
    g = NoOpGuardrail()
    r = g.check("task", "n'importe quelle réponse")
    assert r.is_valid is True


def test_noop_on_empty_response():
    g = NoOpGuardrail()
    assert g.check("", "").is_valid is True


# ─── Nemo : construction ───────────────────────────────────────
def test_nemo_missing_config_raises():
    guardrail = NemoGuardrail("/chemin/inexistant")
    # _ensure_app n'est pas appelé à la construction, donc pas d'erreur ici
    assert guardrail._app is None


def test_nemo_missing_dependency_fails_open(monkeypatch):
    """Si nemoguardrails n'est pas installé, check() fail-open."""
    import sys
    # Force l'échec de l'import
    monkeypatch.setitem(sys.modules, "nemoguardrails", None)

    guardrail = NemoGuardrail("/chemin/inexistant")
    result = guardrail.check("task", "response")
    # Fail-open : considéré valide
    assert result.is_valid is True
    assert "guardrail indisponible" in result.reason


# ─── Nemo : normalisation de la réponse ────────────────────────
def _make_nemo_with_mock_app(return_value):
    """Instancie un NemoGuardrail avec _app déjà mocké."""
    guardrail = NemoGuardrail("/chemin/ignoré")
    mock_app = MagicMock()
    mock_app.generate.return_value = return_value
    guardrail._app = mock_app
    return guardrail


def test_nemo_str_valid():
    g = _make_nemo_with_mock_app("La réponse est correcte")
    assert g.check("task", "response").is_valid is True


def test_nemo_str_hallucination():
    g = _make_nemo_with_mock_app("Hallucination detected in this response")
    result = g.check("task", "response")
    assert result.is_valid is False
    assert result.flagged is True
    assert "Hallucination" in result.reason


def test_nemo_str_not_supported():
    g = _make_nemo_with_mock_app("The claim is not supported by evidence")
    assert g.check("task", "response").is_valid is False


def test_nemo_dict_response():
    g = _make_nemo_with_mock_app({
        "response": [
            {"role": "assistant", "content": "Cette réponse est correcte"},
        ],
    })
    assert g.check("task", "response").is_valid is True


def test_nemo_dict_hallucination():
    g = _make_nemo_with_mock_app({
        "response": [
            {"role": "assistant", "content": "hallucination suspectée"},
        ],
    })
    assert g.check("task", "response").is_valid is False


def test_nemo_object_response():
    """Simule un GenerationResponse avec attribut .response."""
    class FakeGenResponse:
        def __init__(self, msgs):
            self.response = msgs

    g = _make_nemo_with_mock_app(
        FakeGenResponse([{"role": "assistant", "content": "ok"}])
    )
    assert g.check("task", "response").is_valid is True


def test_nemo_exception_fails_open():
    g = NemoGuardrail("/chemin/ignoré")
    mock_app = MagicMock()
    mock_app.generate.side_effect = RuntimeError("boom")
    g._app = mock_app
    result = g.check("task", "response")
    # Fail-open : on ne bloque pas la tâche sur une erreur du guardrail
    assert result.is_valid is True
    assert "guardrail indisponible" in result.reason