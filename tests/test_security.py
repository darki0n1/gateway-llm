# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Tests de sécurité : secrets, pas de shell=True, échappement."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from llm_gateway.secrets import (
    EnvSecretBackend,
    PowerShellVaultBackend,
    SecretBackend,
    get_default_backend,
)


# ─── Interface ─────────────────────────────────────────────────
def test_secret_backend_is_abstract():
    with pytest.raises(TypeError):
        SecretBackend()  # type: ignore[abstract]


# ─── Env backend ──────────────────────────────────────────────
def test_env_returns_value():
    with patch.dict(os.environ, {"MY_KEY": "secret123"}):
        assert EnvSecretBackend().get("MY_KEY") == "secret123"


def test_env_missing():
    assert EnvSecretBackend().get("NONEXISTENT_ABC123_XYZ") is None


def test_env_empty_string_is_none():
    with patch.dict(os.environ, {"MY_KEY": ""}):
        assert EnvSecretBackend().get("MY_KEY") is None


# ─── Vault backend ────────────────────────────────────────────
@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_no_shell_true(mock_run, _mock_which):
    """Le backend Vault ne doit JAMAIS utiliser shell=True."""
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    PowerShellVaultBackend().get("MY_SECRET")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True
    # Le premier argument doit être une liste (pas une string)
    first_arg = mock_run.call_args.args[0]
    assert isinstance(first_arg, list)


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_escapes_single_quotes(mock_run, _mock_which):
    """Un nom avec apostrophe doit être échappé en '' (PowerShell)."""
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    PowerShellVaultBackend().get("secret'with'quotes")

    joined = " ".join(mock_run.call_args.args[0])
    assert "secret''with''quotes" in joined


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_caches_result(mock_run, _mock_which):
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    backend = PowerShellVaultBackend()
    backend.get("MY_SECRET")
    backend.get("MY_SECRET")
    backend.get("MY_SECRET")
    assert mock_run.call_count == 1  # un seul subprocess pour 3 get


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_nonzero_returncode(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="not found",
    )
    assert PowerShellVaultBackend().get("MISSING") is None


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_strips_line_endings(mock_run, _mock_which):
    """PowerShell 5.1 ajoute parfois des \\r\\n : ils doivent être nettoyés."""
    mock_run.return_value = MagicMock(
        returncode=0, stdout="secret_value\r\n", stderr="",
    )
    assert PowerShellVaultBackend().get("K") == "secret_value"


@patch("llm_gateway.secrets.shutil.which", return_value=None)
def test_vault_no_powershell_raises(_mock_which):
    with pytest.raises(RuntimeError, match="PowerShell"):
        PowerShellVaultBackend()


# ─── get_default_backend() ────────────────────────────────────
def test_default_backend_env_forced():
    with patch.dict(os.environ, {"LLM_GATEWAY_USE_ENV": "1"}):
        backend = get_default_backend()
    assert isinstance(backend, EnvSecretBackend)


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
def test_default_backend_picks_vault(_mock_which):
    backend = get_default_backend()
    assert isinstance(backend, PowerShellVaultBackend)


@patch("llm_gateway.secrets.shutil.which", return_value=None)
def test_default_backend_falls_back_to_env(_mock_which):
    backend = get_default_backend()
    assert isinstance(backend, EnvSecretBackend)