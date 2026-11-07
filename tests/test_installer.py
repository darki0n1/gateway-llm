# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gateway_llm.installer import Installer


@patch("gateway_llm.installer.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.installer.subprocess.Popen")
@patch("gateway_llm.installer.requests.get")
def test_pull_success(mock_get, mock_popen, _which):
    mock_stdout = iter(["pulling...\n", "done\n"])
    mock_proc = MagicMock(
        stdout=mock_stdout,
        returncode=0,
        wait=MagicMock(),
    )
    mock_popen.return_value = mock_proc
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}]},
    )
    inst = Installer(assume_yes=True)
    assert inst.pull_model("qwen3:4b")


@patch("gateway_llm.installer.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.installer.subprocess.Popen")
@patch("gateway_llm.installer.requests.get")
def test_pull_failure(mock_get, mock_popen, _which):
    mock_proc = MagicMock(
        stdout=iter([]),
        returncode=1,
        wait=MagicMock(),
    )
    mock_popen.return_value = mock_proc
    inst = Installer(assume_yes=True)
    assert not inst.pull_model("qwen3:4b")


@patch("gateway_llm.installer.shutil.which", return_value=None)
def test_pull_no_binary(_which):
    inst = Installer(assume_yes=True)
    assert not inst.pull_model("qwen3:4b")


def test_ask_returns_false_when_not_interactive():
    inst = Installer(interactive=False)
    assert not inst._ask("Continue ?")


def test_ask_auto_yes():
    inst = Installer(assume_yes=True)
    assert inst._ask("Continue ?")


# ─── ensure_models : on mocke ensure_ollama_daemon pour éviter
#     les sleeps de 20s et les appels réseau ─────────────────────
@patch("gateway_llm.installer.ensure_ollama_daemon", return_value=True)
@patch("gateway_llm.installer.requests.get")
def test_ensure_models_no_missing(mock_get, _mock_daemon):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}, {"name": "qwen3:8b"}]},
    )
    inst = Installer(assume_yes=True)
    assert inst.ensure_models(["qwen3:4b", "qwen3:8b"]) == 0


@patch("gateway_llm.installer.ensure_ollama_daemon", return_value=True)
@patch("gateway_llm.installer.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.installer.subprocess.Popen")
@patch("gateway_llm.installer.requests.get")
def test_ensure_models_pulls_missing(mock_get, mock_popen, _which, _mock_daemon):
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: {"models": [{"name": "qwen3:4b"}]}),
        MagicMock(status_code=200, json=lambda: {"models": [{"name": "qwen3:8b"}]}),
    ]
    mock_proc = MagicMock(stdout=iter([]), returncode=0, wait=MagicMock())
    mock_popen.return_value = mock_proc

    inst = Installer(assume_yes=True)
    n = inst.ensure_models(["qwen3:4b", "qwen3:8b"])
    assert n == 1


@patch("gateway_llm.installer.ensure_ollama_daemon", return_value=False)
@patch("gateway_llm.installer.requests.get")
def test_ensure_models_daemon_unavailable(mock_get, _mock_daemon):
    """Si le daemon n'est pas dispo, ensure_models retourne 0 sans pull."""
    inst = Installer(assume_yes=True)
    assert inst.ensure_models(["qwen3:4b"]) == 0
    mock_get.assert_not_called()  # On n'a même pas essayé de lister