# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Backends de secrets interchangeables.

Aucune bascule silencieuse : le backend est choisi EXPLICITEMENT par
l'utilisateur (CLI setup-secrets ou GUI Configuration) et mémorisé
dans un fichier de config local (~/.llm-gateway/secrets.yaml).

Les dépendances cloud (azure, boto3) sont OPTIONNELLES et importées
à la demande, à l'intérieur des méthodes. Aucun import au niveau module
pour éviter de casser `import llm_gateway.secrets` si elles sont absentes.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import subprocess
from abc import ABC, abstractmethod

import yaml

log = logging.getLogger(__name__)

_CONFIG_PATH = pathlib.Path.home() / ".llm-gateway" / "secrets.yaml"


class SecretBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def get(self, key: str) -> str | None:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    def set(self, key: str, value: str) -> bool:
        """Optionnel : écriture d'un secret. Retourne False par défaut."""
        return False


# ─── PowerShell Vault ─────────────────────────────────────────
class PowerShellVaultBackend(SecretBackend):
    name = "powershell_vault"

    def __init__(self) -> None:
        self._cache: dict[str, str | None] = {}
        ps_exe = shutil.which("pwsh") or shutil.which("powershell")
        if not ps_exe:
            raise RuntimeError("PowerShell introuvable")
        self._ps_exe = ps_exe

    def is_available(self) -> bool:
        try:
            r = subprocess.run(
                [self._ps_exe, "-NoProfile", "-NonInteractive", "-Command",
                 "Import-Module Microsoft.PowerShell.SecretManagement; "
                 "Get-SecretVault | Select-Object -First 1 | ConvertTo-Json"],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0 and r.stdout.strip() not in ("", "null")
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        safe = key.replace("'", "''")
        cmd = (
            "Import-Module Microsoft.PowerShell.SecretManagement; "
            f"Get-Secret -Name '{safe}' -AsPlainText -ErrorAction Stop"
        )
        try:
            r = subprocess.run(
                [self._ps_exe, "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                log.warning("Vault '%s' introuvable : %s", key,
                            (r.stderr or "").strip()[:120])
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
        safe_k = key.replace("'", "''")
        safe_v = value.replace("'", "''")
        cmd = (
            "Import-Module Microsoft.PowerShell.SecretManagement; "
            f"Set-Secret -Name '{safe_k}' -Secret '{safe_v}'"
        )
        try:
            r = subprocess.run(
                [self._ps_exe, "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True, text=True, timeout=15,
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
                f"{self._url}/v1/{self._mount}/data/llm-gateway",
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

    def __init__(self, region: str = "us-east-1", prefix: str = "llm-gateway/") -> None:
        self._region = region
        self._prefix = prefix
        self._client = None
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
        self._client = None
        self._cache: dict[str, str | None] = {}

    def _get_client(self):
        if self._client is not None:
            return self._client
        from azure.identity import DefaultAzureCredential  # type: ignore[import-not-found]
        from azure.keyvault.secrets import SecretClient  # type: ignore[import-not-found]
        self._client = SecretClient(
            vault_url=self._vault_url, credential=DefaultAzureCredential(),
        )
        return self._client

    def is_available(self) -> bool:
        try:
            client = self._get_client()
            # Vraie requête réseau : list_properties_of_secrets() lève
            # si le vault est injoignable ou si les credentials sont invalides.
            next(client.list_properties_of_secrets(), None)
            return True
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        try:
            client = self._get_client()
            # Azure KV n'accepte pas "_" dans les noms
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
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        try:
            r = subprocess.run(
                ["op", "read", f"op://{self._vault}/llm-gateway/{key}"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                self._cache[key] = None
                return None
            self._cache[key] = r.stdout.strip()
            return self._cache[key]
        except Exception:
            self._cache[key] = None
            return None


# ─── Fallback : variables d'environnement (opt-in explicite) ──
class EnvSecretBackend(SecretBackend):
    name = "env"

    def is_available(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        return os.environ.get(key) or None


# ─── Résolution explicite du backend ──────────────────────────
_BACKEND_FACTORIES = {
    "powershell_vault": lambda c: PowerShellVaultBackend(),
    "hashicorp_vault": lambda c: HashiCorpVaultBackend(
        c["url"], c["token"], c.get("mount", "secret"),
    ),
    "aws_secrets_manager": lambda c: AWSSecretsManagerBackend(
        c.get("region", "us-east-1"), c.get("prefix", "llm-gateway/"),
    ),
    "azure_key_vault": lambda c: AzureKeyVaultBackend(c["vault_url"]),
    "1password": lambda c: OnePasswordBackend(c.get("vault", "Private")),
    "env": lambda c: EnvSecretBackend(),
}

# Mapping backend → nom du package pip à installer si manquant.
_BACKEND_REQUIREMENTS = {
    "hashicorp_vault": None,   # utilise requests (déjà installé)
    "aws_secrets_manager": "boto3",
    "azure_key_vault": "azure-identity azure-keyvault-secrets",
    "1password": None,         # utilise le binaire `op` (à installer séparément)
    "powershell_vault": None,  # utilise PowerShell natif
    "env": None,
}


def _load_config() -> dict | None:
    if not _CONFIG_PATH.exists():
        return None
    try:
        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_backend() -> SecretBackend:
    """Charge le backend EXPLICITEMENT configuré par setup-secrets."""
    cfg = _load_config()
    if cfg is None or "backend" not in cfg:
        raise RuntimeError(
            "Aucun backend de secrets configuré.\n"
            "Lancez : llm-gateway setup-secrets\n"
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


def missing_requirements(backend_name: str) -> str | None:
    """Retourne le nom du package pip manquant, ou None si tout est installé.

    Utilisé par `setup-secrets` pour avertir l'utilisateur avant qu'il
    choisisse un backend dont les dépendances ne sont pas installées.
    """
    req = _BACKEND_REQUIREMENTS.get(backend_name)
    if req is None:
        return None
    pkg = req.split()[0]
    try:
        __import__(pkg.replace("-", "_"))
        return None
    except ImportError:
        return req