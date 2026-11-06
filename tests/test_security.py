# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests de sécurité : secrets, pas de shell=True, échappement, imports lazy."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from gateway_llm.secrets import (
    AWSSecretsManagerBackend,
    AzureKeyVaultBackend,
    EnvSecretBackend,
    HashiCorpVaultBackend,
    OnePasswordBackend,
    PowerShellVaultBackend,
    SecretBackend,
    get_backend,
    save_backend_config,
)


# ─── Interface ─────────────────────────────────────────────────
def test_secret_backend_is_abstract():
    with pytest.raises(TypeError):
        SecretBackend()  # type: ignore[abstract]


def test_default_set_returns_false():
    """Le contrat ABC : set() retourne False par défaut (lecture seule)."""
    assert EnvSecretBackend().set("any_key", "any_val") is False


# ─── Pas d'import cloud au niveau module ──────────────────────
def test_no_azure_import_at_module_level():
    """Régression : si azure n'est pas installé, import doit fonctionner."""
    saved = {}
    for mod in list(sys.modules.keys()):
        if mod.startswith("azure"):
            saved[mod] = sys.modules.pop(mod)

    try:
        import importlib

        import gateway_llm.secrets as sec

        importlib.reload(sec)
        assert hasattr(sec, "AzureKeyVaultBackend")
    finally:
        sys.modules.update(saved)


def test_no_boto3_import_at_module_level():
    """Régression : si boto3 n'est pas installé, import doit fonctionner."""
    saved = {}
    for mod in list(sys.modules.keys()):
        if mod.startswith("boto3") or mod.startswith("botocore"):
            saved[mod] = sys.modules.pop(mod)

    try:
        import importlib

        import gateway_llm.secrets as sec

        importlib.reload(sec)
        assert hasattr(sec, "AWSSecretsManagerBackend")
    finally:
        sys.modules.update(saved)


# ─── Env backend ──────────────────────────────────────────────
def test_env_returns_value():
    with patch.dict(os.environ, {"MY_KEY": "secret123"}):
        assert EnvSecretBackend().get("MY_KEY") == "secret123"


def test_env_missing():
    assert EnvSecretBackend().get("NONEXISTENT_ABC123_XYZ") is None


def test_env_empty_string_is_none():
    with patch.dict(os.environ, {"MY_KEY": ""}):
        assert EnvSecretBackend().get("MY_KEY") is None


def test_env_is_available():
    assert EnvSecretBackend().is_available() is True


# ─── PowerShell Vault backend ─────────────────────────────────
@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_no_shell_true(mock_run, _mock_which):
    """Le backend Vault ne doit JAMAIS utiliser shell=True."""
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    PowerShellVaultBackend().get("MY_SECRET")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True
    first_arg = mock_run.call_args.args[0]
    assert isinstance(first_arg, list)


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_escapes_single_quotes(mock_run, _mock_which):
    """Un nom avec apostrophe doit être échappé en '' (PowerShell)."""
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    PowerShellVaultBackend().get("secret'with'quotes")

    joined = " ".join(mock_run.call_args.args[0])
    assert "secret''with''quotes" in joined


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_set_escapes(mock_run, _mock_which):
    """set() doit aussi échapper clé et valeur."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    PowerShellVaultBackend().set("k'ey", "v'alue")

    joined = " ".join(mock_run.call_args.args[0])
    assert "k''ey" in joined
    assert "v''alue" in joined


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_caches_result(mock_run, _mock_which):
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    backend = PowerShellVaultBackend()
    backend.get("MY_SECRET")
    backend.get("MY_SECRET")
    backend.get("MY_SECRET")
    assert mock_run.call_count == 1


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_nonzero_returncode(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="not found",
    )
    assert PowerShellVaultBackend().get("MISSING") is None


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_strips_line_endings(mock_run, _mock_which):
    """PowerShell 5.1 ajoute parfois des \\r\\n : ils doivent être nettoyés."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="secret_value\r\n",
        stderr="",
    )
    assert PowerShellVaultBackend().get("K") == "secret_value"


@patch("gateway_llm.secrets.shutil.which", return_value=None)
def test_vault_no_powershell_raises(_mock_which):
    with pytest.raises(RuntimeError, match="PowerShell"):
        PowerShellVaultBackend()


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_is_available_when_vault_registered(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"Name":"LocalVault"}',
        stderr="",
    )
    assert PowerShellVaultBackend().is_available() is True


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("gateway_llm.secrets.subprocess.run")
def test_vault_is_available_no_vault(mock_run, _mock_which):
    """Sortie vide ou 'null' = aucun vault enregistré."""
    mock_run.return_value = MagicMock(returncode=0, stdout="null", stderr="")
    assert PowerShellVaultBackend().is_available() is False


# ─── HashiCorp Vault ──────────────────────────────────────────
@patch("requests.get")
def test_hashicorp_get_success(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"data": {"data": {"GROQ_API_KEY": "gsk_xxx"}}},
    )
    b = HashiCorpVaultBackend("http://vault:8200", "token")
    assert b.get("GROQ_API_KEY") == "gsk_xxx"


@patch("requests.get")
def test_hashicorp_get_404(mock_get):
    mock_get.return_value = MagicMock(status_code=404)
    b = HashiCorpVaultBackend("http://vault:8200", "token")
    assert b.get("MISSING") is None


@patch("requests.get")
def test_hashicorp_network_error(mock_get):
    import requests

    mock_get.side_effect = requests.exceptions.ConnectionError("refused")
    b = HashiCorpVaultBackend("http://vault:8200", "token")
    assert b.get("K") is None


# ─── AWS Secrets Manager ──────────────────────────────────────
def test_aws_is_available_no_boto3():
    """Si boto3 n'est pas installé, is_available() retourne False."""
    with patch.dict(sys.modules, {"boto3": None}):
        b = AWSSecretsManagerBackend()
        assert b.is_available() is False


def test_aws_get_no_client_returns_none():
    """get() sans client initialisé (pas d'is_available) retourne None."""
    with patch.dict(sys.modules, {"boto3": None}):
        b = AWSSecretsManagerBackend()
        assert b.get("K") is None


# ─── Azure Key Vault ──────────────────────────────────────────
def test_azure_is_available_no_azure():
    """Si azure n'est pas installé, is_available() retourne False."""
    with patch.dict(sys.modules, {"azure.identity": None}):
        b = AzureKeyVaultBackend("https://x.vault.azure.net")
        assert b.is_available() is False


def test_azure_key_transformation():
    """Azure KV refuse les underscores : ils doivent être convertis en tirets."""
    b = AzureKeyVaultBackend("https://x.vault.azure.net")
    mock_client = MagicMock()
    mock_client.get_secret.return_value = MagicMock(value="myvalue")
    b._client = mock_client

    b.get("GROQ_API_KEY")
    mock_client.get_secret.assert_called_once_with("GROQ-API-KEY")


# ─── 1Password ────────────────────────────────────────────────
@patch("gateway_llm.secrets.shutil.which", return_value=None)
def test_onepassword_no_binary_raises(_mock_which):
    with pytest.raises(RuntimeError, match="1Password"):
        OnePasswordBackend()


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/op")
@patch("gateway_llm.secrets.subprocess.run")
def test_onepassword_no_shell_true(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="secret_value",
        stderr="",
    )
    OnePasswordBackend().get("MY_KEY")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True
    first_arg = mock_run.call_args.args[0]
    assert isinstance(first_arg, list)


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/op")
@patch("gateway_llm.secrets.subprocess.run")
def test_onepassword_get_success(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="mysecret\n",
        stderr="",
    )
    b = OnePasswordBackend("Private")
    assert b.get("GROQ_API_KEY") == "mysecret"


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/op")
@patch("gateway_llm.secrets.subprocess.run")
def test_onepassword_not_found(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="not found",
    )
    assert OnePasswordBackend().get("MISSING") is None


# ─── get_backend() / save_backend_config() ────────────────────
def test_get_backend_no_config_raises(tmp_path, monkeypatch):
    import gateway_llm.secrets as sec

    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "nonexistent.yaml")
    with pytest.raises(RuntimeError, match="Aucun backend de secrets"):
        get_backend()


def test_get_backend_unknown_backend_raises(tmp_path, monkeypatch):
    import gateway_llm.secrets as sec

    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)
    cfg.write_text("backend: backend_qui_nexiste_pas\noptions: {}\n")
    with pytest.raises(RuntimeError, match="Backend inconnu"):
        get_backend()


def test_save_then_get_backend_env(tmp_path, monkeypatch):
    """save_backend_config persiste, get_backend relit le bon backend."""
    import gateway_llm.secrets as sec

    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    save_backend_config("env", {})
    backend = get_backend()
    # On vérifie le nom du backend au lieu de la classe (plus robuste)
    assert backend.name == "env"


@patch("gateway_llm.secrets.shutil.which", return_value="/usr/bin/pwsh")
def test_save_then_get_backend_powershell(_mock_which, tmp_path, monkeypatch):
    import gateway_llm.secrets as sec

    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    save_backend_config("powershell_vault", {})
    backend = get_backend()
    # On vérifie le nom, pas la classe
    assert backend.name == "powershell_vault"


def test_save_backend_config_creates_parent_dir(tmp_path, monkeypatch):
    import gateway_llm.secrets as sec

    cfg = tmp_path / "subdir" / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)
    save_backend_config("env", {})
    assert cfg.exists()
    assert cfg.parent.is_dir()


def test_save_backend_config_yaml_format(tmp_path, monkeypatch):
    """Le fichier écrit doit être du YAML valide, pas du JSON."""
    import yaml as yaml_mod

    import gateway_llm.secrets as sec

    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    save_backend_config("hashicorp_vault", {"url": "http://v:8200", "token": "tk"})
    data = yaml_mod.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["backend"] == "hashicorp_vault"
    assert data["options"]["url"] == "http://v:8200"
