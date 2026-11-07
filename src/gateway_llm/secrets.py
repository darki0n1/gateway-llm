# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Backends de secrets interchangeables.

Aucune bascule silencieuse : le backend est choisi EXPLICITEMENT par
l'utilisateur (CLI setup-secrets ou GUI Configuration) et mémorisé
dans un fichier de config local (~/.gateway-llm/secrets.yaml).

Backends supportés : PowerShell Vault, 1Password, HashiCorp Vault,
AWS Secrets Manager, Azure Key Vault, Variables d'environnement.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Any

import yaml

log = logging.getLogger(__name__)

_CONFIG_PATH = pathlib.Path.home() / ".gateway-llm" / "secrets.yaml"


class SecretBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    def set(self, key: str, value: str) -> bool:
        """Optionnel : écriture d'un secret. Retourne False par défaut."""
        return False


# ─── PowerShell Vault ─────────────────────────────────────────
class PowerShellVaultBackend(SecretBackend):
    name = "powershell_vault"

    def __init__(self) -> None:
        self._cache: dict[str, str | None] = {}
        self._error: str | None = None
        # On collecte les candidats dans l'ordre de préférence.
        # powershell.exe (PS5.1) est souvent celui qui a le module
        # quand pwsh (PS7 Store) ne l'a pas.
        self._candidates: list[str] = [
            p
            for p in (shutil.which("powershell"), shutil.which("pwsh"))
            if p is not None
        ]
        self._ps_exe: str | None = None

    def _probe(self, exe: str) -> bool:
        """Teste si cet exécutable peut charger SecretManagement."""
        try:
            r = subprocess.run(
                [
                    exe,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Import-Module Microsoft.PowerShell.SecretManagement "
                    "-ErrorAction Stop; "
                    "Get-Command Get-Secret -ErrorAction Stop | Out-Null",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0

    def _resolve_exe(self) -> str | None:
        """Retourne le premier exécutable qui charge le module, sinon None."""
        if self._ps_exe is not None:
            return self._ps_exe
        for exe in self._candidates:
            if self._probe(exe):
                self._ps_exe = exe
                return exe
        # Aucun candidat n'a le module : on garde le premier pour les logs
        if self._candidates:
            self._ps_exe = self._candidates[0]
            self._error = (
                "Aucun PowerShell ne charge SecretManagement. "
                "Installez le module :\n"
                "  Install-Module Microsoft.PowerShell.SecretManagement "
                "-Scope CurrentUser\n"
                "  Install-Module Microsoft.PowerShell.SecretStore "
                "-Scope CurrentUser"
            )
        else:
            self._error = "PowerShell (pwsh/powershell) introuvable dans le PATH"
        return None

    def is_available(self) -> bool:
        # _resolve_exe a déjà validé le module via _probe.
        return self._resolve_exe() is not None

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        exe = self._resolve_exe()
        if exe is None:
            self._cache[key] = None
            return None
        safe = key.replace("'", "''")
        cmd = (
            "Import-Module Microsoft.PowerShell.SecretManagement "
            "-ErrorAction SilentlyContinue; "
            f"Get-Secret -Name '{safe}' -AsPlainText -ErrorAction Stop"
        )
        try:
            r = subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode != 0:
                log.warning(
                    "Vault '%s' introuvable : %s",
                    key,
                    (r.stderr or "").strip()[:120],
                )
                self._cache[key] = None
                return None
            value = r.stdout.strip().replace("\r", "").replace("\n", "")
            self._cache[key] = value or None
            return self._cache[key]
        except Exception as e:
            log.warning("Vault erreur '%s' : %s", key, str(e)[:80])
            self._cache[key] = None
            return None

    def set(self, key: str, value: str) -> bool:
        exe = self._resolve_exe()
        if exe is None:
            return False
        safe_k = key.replace("'", "''")
        safe_v = value.replace("'", "''")
        cmd = (
            "Import-Module Microsoft.PowerShell.SecretManagement -ErrorAction Stop; "
            f"Set-Secret -Name '{safe_k}' -Secret '{safe_v}'"
        )
        try:
            r = subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return r.returncode == 0
        except Exception:
            return False

# ─── HashiCorp Vault ──────────────────────────────────────────
class HashiCorpVaultBackend(SecretBackend):
    name = "hashicorp_vault"

    def __init__(self, url: str, token: str, mount: str = "secret") -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._mount = mount
        self._cache: dict[str, str | None] = {}

    def is_available(self) -> bool:
        try:
            import requests

            r = requests.get(
                f"{self._url}/v1/sys/health",
                headers={"X-Vault-Token": self._token},
                timeout=5,
            )
            return r.status_code in (200, 429, 472, 473, 501, 503)
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        try:
            import requests

            r = requests.get(
                f"{self._url}/v1/{self._mount}/data/gateway-llm",
                headers={"X-Vault-Token": self._token},
                timeout=10,
            )
            if r.status_code != 200:
                self._cache[key] = None
                return None
            data = r.json().get("data", {}).get("data", {})
            self._cache[key] = data.get(key)
            return self._cache[key]
        except Exception as e:
            log.warning("HashiCorp Vault erreur '%s' : %s", key, e)
            self._cache[key] = None
            return None


# ─── AWS Secrets Manager ──────────────────────────────────────
class AWSSecretsManagerBackend(SecretBackend):
    name = "aws_secrets_manager"

    def __init__(self, region: str = "us-east-1", prefix: str = "gateway-llm/") -> None:
        self._region = region
        self._prefix = prefix
        self._client: Any = None
        self._cache: dict[str, str | None] = {}

    def is_available(self) -> bool:
        try:
            import boto3  # type: ignore[import-not-found]

            self._client = boto3.client("secretsmanager", region_name=self._region)
            self._client.list_secrets(MaxResults=1)
            return True
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        try:
            if self._client is None:
                import boto3  # type: ignore[import-not-found]

                self._client = boto3.client("secretsmanager", region_name=self._region)
            r = self._client.get_secret_value(SecretId=f"{self._prefix}{key}")
            self._cache[key] = r.get("SecretString")
            return self._cache[key]
        except Exception as e:
            log.warning("AWS SM erreur '%s' : %s", key, str(e)[:80])
            self._cache[key] = None
            return None


# ─── Azure Key Vault ──────────────────────────────────────────
class AzureKeyVaultBackend(SecretBackend):
    name = "azure_key_vault"

    def __init__(self, vault_url: str) -> None:
        self._vault_url = vault_url.rstrip("/")
        self._client: Any = None
        self._cache: dict[str, str | None] = {}

    def _get_client(self):
        if self._client is not None:
            return self._client
        from azure.identity import DefaultAzureCredential  # type: ignore[import-not-found]
        from azure.keyvault.secrets import SecretClient  # type: ignore[import-not-found]

        self._client = SecretClient(
            vault_url=self._vault_url,
            credential=DefaultAzureCredential(),
        )
        return self._client

    def is_available(self) -> bool:
        try:
            client = self._get_client()
            next(client.list_properties_of_secrets(), None)
            return True
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        try:
            client = self._get_client()
            azure_key = key.replace("_", "-")
            secret = client.get_secret(azure_key)
            self._cache[key] = secret.value
            return self._cache[key]
        except Exception as e:
            log.warning("Azure KV erreur '%s' : %s", key, str(e)[:80])
            self._cache[key] = None
            return None


# ─── 1Password CLI ────────────────────────────────────────────
class OnePasswordBackend(SecretBackend):
    name = "1password"

    def __init__(self, vault: str = "Private") -> None:
        self._vault = vault
        if not shutil.which("op"):
            raise RuntimeError("1Password CLI 'op' introuvable")
        self._cache: dict[str, str | None] = {}

    def is_available(self) -> bool:
        try:
            r = subprocess.run(
                ["op", "vault", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return r.returncode == 0
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        try:
            r = subprocess.run(
                ["op", "read", f"op://{self._vault}/gateway-llm/{key}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode != 0:
                self._cache[key] = None
                return None
            self._cache[key] = r.stdout.strip()
            return self._cache[key]
        except Exception:
            self._cache[key] = None
            return None


# ─── Variables d'environnement (opt-in explicite, déconseillé) ─
class EnvSecretBackend(SecretBackend):
    """Lit les secrets depuis les variables d'environnement du processus.

    Déconseillé en usage quotidien (les variables d'env sont visibles par
    les autres processus du même utilisateur et peuvent fuiter via les
    logs). Utile en CI/CD où les variables sont injectées par la plateforme.
    """

    name = "env"

    def is_available(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        return os.environ.get(key) or None


# ─── Résolution explicite du backend ──────────────────────────
_BACKEND_FACTORIES = {
    "powershell_vault": lambda c: PowerShellVaultBackend(),
    "hashicorp_vault": lambda c: HashiCorpVaultBackend(
        c["url"],
        c["token"],
        c.get("mount", "secret"),
    ),
    "aws_secrets_manager": lambda c: AWSSecretsManagerBackend(
        c.get("region", "us-east-1"),
        c.get("prefix", "gateway-llm/"),
    ),
    "azure_key_vault": lambda c: AzureKeyVaultBackend(c["vault_url"]),
    "1password": lambda c: OnePasswordBackend(c.get("vault", "Private")),
    "env": lambda c: EnvSecretBackend(),
}


def _load_config() -> dict | None:
    if not _CONFIG_PATH.exists():
        return None
    try:
        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except Exception:
        return None


def get_backend() -> SecretBackend:
    """Charge le backend EXPLICITEMENT configuré par setup-secrets."""
    cfg = _load_config()
    if cfg is None or "backend" not in cfg:
        raise RuntimeError(
            "Aucun backend de secrets configuré.\n"
            "Lancez : gateway-llm setup-secrets\n"
            "Ou ouvrez l'onglet Configuration de la GUI."
        )
    backend_name = cfg["backend"]
    factory = _BACKEND_FACTORIES.get(backend_name)
    if not factory:
        raise RuntimeError(f"Backend inconnu : {backend_name}")
    return factory(cfg.get("options", {}))


def save_backend_config(backend_name: str, options: dict) -> None:
    """Persiste le choix du backend (appelé par setup-secrets et GUI)."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        yaml.safe_dump(
            {"backend": backend_name, "options": options},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    log.info("Backend '%s' enregistré dans %s", backend_name, _CONFIG_PATH)
