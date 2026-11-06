# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests de sécurité : secrets, pas de shell=True, échappement, imports lazy."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from llm_gateway.secrets import (
    AWSSecretsManagerBackend,
    AzureKeyVaultBackend,
    EnvSecretBackend,
    HashiCorpVaultBackend,
    OnePasswordBackend,
    PowerShellVaultBackend,
    SecretBackend,
    get_backend,
    missing_requirements,
    save_backend_config,
)


# ─── Interface ─────────────────────────────────────────────────
def test_secret_backend_is_abstract():
    with pytest.raises(TypeError):
        SecretBackend()  # type: ignore[abstract]


def test_default_set_returns_false():
    """Le contrat ABC : set() retourne False par défaut (lecture seule)."""
    # EnvSecretBackend n'override pas set()
    assert EnvSecretBackend().set("any_key", "any_val") is False


# ─── Pas d'import cloud au niveau module ──────────────────────
def test_no_azure_import_at_module_level():
    """Régression : si azure n'est pas installé, import doit fonctionner."""
    # On simule l'absence des modules Azure en les retirant temporairement
    saved = {}
    for mod in list(sys.modules.keys()):
        if mod.startswith("azure"):
            saved[mod] = sys.modules.pop(mod)

    try:
        # Recharge le module pour s'assurer qu'aucun import module-level ne casse
        import importlib
        import llm_gateway.secrets as sec
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
        import llm_gateway.secrets as sec
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
@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_no_shell_true(mock_run, _mock_which):
    """Le backend Vault ne doit JAMAIS utiliser shell=True."""
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    PowerShellVaultBackend().get("MY_SECRET")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True
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
def test_vault_set_escapes(mock_run, _mock_which):
    """set() doit aussi échapper clé et valeur."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    PowerShellVaultBackend().set("k'ey", "v'alue")

    joined = " ".join(mock_run.call_args.args[0])
    assert "k''ey" in joined
    assert "v''alue" in joined


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_caches_result(mock_run, _mock_which):
    mock_run.return_value = MagicMock(returncode=0, stdout="v", stderr="")
    backend = PowerShellVaultBackend()
    backend.get("MY_SECRET")
    backend.get("MY_SECRET")
    backend.get("MY_SECRET")
    assert mock_run.call_count == 1


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


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
def test_vault_is_available_when_vault_registered(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=0, stdout='{"Name":"LocalVault"}', stderr="",
    )
    assert PowerShellVaultBackend().is_available() is True


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
@patch("llm_gateway.secrets.subprocess.run")
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
@patch("llm_gateway.secrets.shutil.which", return_value=None)
def test_onepassword_no_binary_raises(_mock_which):
    with pytest.raises(RuntimeError, match="1Password"):
        OnePasswordBackend()


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/op")
@patch("llm_gateway.secrets.subprocess.run")
def test_onepassword_no_shell_true(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=0, stdout="secret_value", stderr="",
    )
    OnePasswordBackend().get("MY_KEY")

    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True
    first_arg = mock_run.call_args.args[0]
    assert isinstance(first_arg, list)


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/op")
@patch("llm_gateway.secrets.subprocess.run")
def test_onepassword_get_success(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=0, stdout="mysecret\n", stderr="",
    )
    b = OnePasswordBackend("Private")
    assert b.get("GROQ_API_KEY") == "mysecret"


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/op")
@patch("llm_gateway.secrets.subprocess.run")
def test_onepassword_not_found(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="not found",
    )
    assert OnePasswordBackend().get("MISSING") is None


# ─── get_backend() / save_backend_config() ────────────────────
def test_get_backend_no_config_raises(tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    monkeypatch.setattr(sec, "_CONFIG_PATH", tmp_path / "nonexistent.yaml")
    with pytest.raises(RuntimeError, match="Aucun backend de secrets"):
        get_backend()


def test_get_backend_unknown_backend_raises(tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)
    cfg.write_text("backend: backend_qui_nexiste_pas\noptions: {}\n")
    with pytest.raises(RuntimeError, match="Backend inconnu"):
        get_backend()


def test_save_then_get_backend(tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    save_backend_config("env", {})
    backend = get_backend()
    assert isinstance(backend, EnvSecretBackend)


@patch("llm_gateway.secrets.shutil.which", return_value="/usr/bin/pwsh")
def test_get_backend_powershell_vault(_mock_which, tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    save_backend_config("powershell_vault", {})
    backend = get_backend()
    assert isinstance(backend, PowerShellVaultBackend)


def test_save_backend_config_creates_parent_dir(tmp_path, monkeypatch):
    import llm_gateway.secrets as sec
    cfg = tmp_path / "subdir" / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)
    save_backend_config("env", {})
    assert cfg.exists()
    assert cfg.parent.is_dir()


def test_save_backend_config_yaml_format(tmp_path, monkeypatch):
    """Le fichier écrit doit être du YAML valide, pas du JSON."""
    import yaml as yaml_mod
    import llm_gateway.secrets as sec
    cfg = tmp_path / "secrets.yaml"
    monkeypatch.setattr(sec, "_CONFIG_PATH", cfg)

    save_backend_config("hashicorp_vault", {"url": "http://v:8200", "token": "tk"})
    data = yaml_mod.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["backend"] == "hashicorp_vault"
    assert data["options"]["url"] == "http://v:8200"


# ─── missing_requirements() ──────────────────────────────────
def test_missing_requirements_env_returns_none():
    """'env' n'a aucune dépendance externe."""
    assert missing_requirements("env") is None


def test_missing_requirements_powershell_returns_none():
    """PowerShell utilise le binaire natif, pas de package pip."""
    assert missing_requirements("powershell_vault") is None


def test_missing_requirements_hashicorp_returns_none():
    """HashiCorp utilise requests, déjà installé."""
    assert missing_requirements("hashicorp_vault") is None


def test_missing_requirements_aws_when_installed():
    """Si boto3 est installé, retourne None ; sinon, retourne 'boto3'."""
    import importlib.util
    if importlib.util.find_spec("boto3") is not None:
        assert missing_requirements("aws_secrets_manager") is None
    else:
        assert missing_requirements("aws_secrets_manager") == "boto3"


def test_missing_requirements_azure_returns_package():
    """Retourne le nom du package pip si azure manquant, None sinon."""
    import importlib.util
    has_identity = importlib.util.find_spec("azure.identity") is not None
    has_kv = importlib.util.find_spec("azure.keyvault.secrets") is not None
    if has_identity and has_kv:
        assert missing_requirements("azure_key_vault") is None
    else:
        result = missing_requirements("azure_key_vault")
        assert result is not None
        assert "azure" in result


def test_missing_requirements_unknown_backend_returns_none():
    """Backend inconnu = pas de check de dépendance."""
    assert missing_requirements("backend_bidon") is None