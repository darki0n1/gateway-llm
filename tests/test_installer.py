# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gateway_llm.installer import Installer


@patch("gateway_llm.installer.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.installer.subprocess.Popen")
@patch("gateway_llm.installer.requests.get")
def test_pull_success(mock_get, mock_popen, _which):
    # Simule la sortie de `ollama pull`
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


@patch("gateway_llm.installer.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.installer.requests.get")
def test_ensure_models_no_missing(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}, {"name": "qwen3:8b"}]},
    )
    inst = Installer(assume_yes=True)
    assert inst.ensure_models(["qwen3:4b", "qwen3:8b"]) == 0


@patch("gateway_llm.installer.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.installer.subprocess.Popen")
@patch("gateway_llm.installer.requests.get")
def test_ensure_models_pulls_missing(mock_get, mock_popen, _which):
    # Premier GET (list) : un modèle présent
    # Deuxième GET (après pull) : deux modèles présents
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: {"models": [{"name": "qwen3:4b"}]}),
        MagicMock(status_code=200, json=lambda: {"models": [{"name": "qwen3:8b"}]}),
    ]
    mock_proc = MagicMock(stdout=iter([]), returncode=0, wait=MagicMock())
    mock_popen.return_value = mock_proc

    inst = Installer(assume_yes=True)
    n = inst.ensure_models(["qwen3:4b", "qwen3:8b"])
    assert n == 1
