# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

from llm_gateway.doctor import Doctor, DoctorReport, Severity


@patch("llm_gateway.doctor.shutil.which", return_value="/usr/bin/ollama")
@patch("llm_gateway.doctor.requests.get")
def test_all_ok(mock_get, _which):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}, {"name": "qwen3:8b"}]},
    )
    d = Doctor(required_models=["qwen3:4b", "qwen3:8b"])
    report = d.run()
    assert not report.has_errors
    assert not report.has_warnings
    assert report.missing_models == []


@patch("llm_gateway.doctor.shutil.which", return_value=None)
def test_ollama_binary_missing(_which):
    d = Doctor()
    report = d.run()
    assert not report.has_errors
    assert report.has_warnings
    names = [r.name for r in report.results]
    assert any("Ollama (binaire)" in n for n in names)


@patch("llm_gateway.doctor.shutil.which", return_value="/usr/bin/ollama")
@patch("llm_gateway.doctor.requests.get")
def test_daemon_unreachable(mock_get, _which):
    import requests
    mock_get.side_effect = requests.exceptions.ConnectionError("refused")
    d = Doctor()
    report = d.run()
    names = [r.name for r in report.results]
    assert any("Ollama (daemon)" in n for n in names)
    assert report.has_warnings


@patch("llm_gateway.doctor.shutil.which", return_value="/usr/bin/ollama")
@patch("llm_gateway.doctor.requests.get")
def test_models_missing(mock_get, _which):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}]},
    )
    d = Doctor(required_models=["qwen3:4b", "qwen3:8b", "mistral"])
    report = d.run()
    assert set(report.missing_models) == {"qwen3:8b", "mistral"}
    assert report.has_warnings


@patch("llm_gateway.doctor.importlib.import_module")
def test_python_deps_missing(mock_import):
    mock_import.side_effect = ImportError("boom")
    d = Doctor()
    report = d.run()
    assert report.has_errors


def test_report_dataclass():
    r = DoctorReport()
    assert not r.has_errors
    assert not r.has_warnings