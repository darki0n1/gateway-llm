# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Tests du Doctor : deps, Ollama, secrets, modèles."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from llm_gateway.doctor import Doctor, DoctorReport, Severity


# ─── Cas nominal ───────────────────────────────────────────────
@patch("llm_gateway.doctor.shutil.which", return_value="/usr/bin/ollama")
@patch("llm_gateway.doctor.requests.get")
def test_all_ok(mock_get, _which, tmp_path, monkeypatch):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}, {"name": "qwen3:8b"}]},
    )
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    cfg.write_text("backend: env\noptions: {}\n")
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    d = Doctor(required_models=["qwen3:4b", "qwen3:8b"])
    report = d.run()
    assert not report.has_errors
    assert report.missing_models == []


# ─── Ollama ────────────────────────────────────────────────────
@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_ollama_binary_missing(_which, tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "none.yaml")
    d = Doctor()
    report = d.run()
    names = [r.name for r in report.results]
    assert any("Ollama (binaire)" in n for n in names)


@patch("llm_gateway.doctor.shutil.which", return_value="/usr/bin/ollama")
@patch("llm_gateway.doctor.requests.get")
def test_daemon_unreachable(mock_get, _which, tmp_path, monkeypatch):
    import requests
    mock_get.side_effect = requests.exceptions.ConnectionError("refused")
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "none.yaml")
    d = Doctor()
    report = d.run()
    names = [r.name for r in report.results]
    assert any("Ollama (daemon)" in n for n in names)


@patch("llm_gateway.doctor.shutil.which", return_value="/usr/bin/ollama")
@patch("llm_gateway.doctor.requests.get")
def test_models_missing(mock_get, _which, tmp_path, monkeypatch):
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"models": [{"name": "qwen3:4b"}]},
    )
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "none.yaml")
    d = Doctor(required_models=["qwen3:4b", "qwen3:8b", "mistral"])
    report = d.run()
    assert set(report.missing_models) == {"qwen3:8b", "mistral"}


# ─── Stockage des secrets ─────────────────────────────────────
@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_secret_storage_no_config(_which, tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "none.yaml")
    # Pas de .env, pas d'env vars
    for var in ["GROQ_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY",
                "GOOGLE_API_KEY", "NVIDIA_API_KEY", "CLOUDFLARE_API_KEY"]:
        monkeypatch.delenv(var, raising=False)

    report = Doctor().run()
    secret_results = [r for r in report.results if "Stockage" in r.name]
    assert len(secret_results) == 1
    assert "Aucun backend" in secret_results[0].message


@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_secret_storage_env_vars_detected(_which, tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "none.yaml")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_xxx")

    report = Doctor().run()
    secret_results = [r for r in report.results if "Stockage" in r.name]
    assert len(secret_results) == 1
    assert "Variables d'env" in secret_results[0].message


@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_secret_storage_dotenv_detected(_which, tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "none.yaml")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_xxx\n")

    report = Doctor().run()
    secret_results = [r for r in report.results if "Stockage" in r.name]
    assert len(secret_results) == 1
    assert ".env" in secret_results[0].message


@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_secret_storage_backend_ok(_which, tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    cfg.write_text("backend: env\noptions: {}\n")
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    report = Doctor().run()
    secret_results = [r for r in report.results if "Stockage" in r.name]
    assert len(secret_results) == 1
    assert secret_results[0].severity == Severity.OK
    assert "opérationnel" in secret_results[0].message


@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_secret_storage_backend_unavailable(_which, tmp_path, monkeypatch):
    """Backend configuré mais is_available() retourne False."""
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    cfg.write_text("backend: powershell_vault\noptions: {}\n")
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    # PowerShell absent sur cette machine de test
    with patch("llm_gateway.secrets.shutil.which", return_value=None):
        report = Doctor().run()
    secret_results = [r for r in report.results if "Stockage" in r.name]
    assert len(secret_results) == 1
    assert secret_results[0].severity == Severity.WARNING


# ─── Structure du rapport ─────────────────────────────────────
def test_report_dataclass():
    r = DoctorReport()
    assert not r.has_errors
    assert not r.has_warnings