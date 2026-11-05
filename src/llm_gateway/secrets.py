# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Backends de secrets interchangeables (env ou PowerShell Vault)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class SecretBackend(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None:
        ...


class EnvSecretBackend(SecretBackend):
    """Lit les secrets depuis les variables d'environnement."""

    def get(self, name: str) -> str | None:
        return os.environ.get(name) or None


class PowerShellVaultBackend(SecretBackend):
    """Lit les secrets depuis Microsoft.PowerShell.SecretManagement.

    Aucun `shell=True` : liste d'arguments + échappement du nom.
    """

    def __init__(self, timeout: int = 15) -> None:
        self._cache: dict[str, str | None] = {}
        self._timeout = timeout
        ps_exe = shutil.which("pwsh") or shutil.which("powershell")
        if not ps_exe:
            raise RuntimeError("Aucun PowerShell trouvé (pwsh / powershell.exe)")
        self._ps_exe = ps_exe

    def get(self, name: str) -> str | None:
        if name in self._cache:
            return self._cache[name]

        safe_name = name.replace("'", "''")
        ps_command = (
            "Import-Module Microsoft.PowerShell.SecretManagement; "
            f"Get-Secret -Name '{safe_name}' -AsPlainText -ErrorAction Stop"
        )

        try:
            result = subprocess.run(
                [self._ps_exe, "-NoProfile", "-NonInteractive",
                 "-Command", ps_command],
                capture_output=True, text=True, timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            log.warning("Vault : timeout pour '%s'", name)
            self._cache[name] = None
            return None

        if result.returncode != 0:
            err = (result.stderr or "").strip()[:120]
            log.warning("Vault : '%s' introuvable (%s)", name, err)
            self._cache[name] = None
            return None

        value = result.stdout.strip().replace("\r", "").replace("\n", "")
        self._cache[name] = value or None
        return self._cache[name]


def get_default_backend() -> SecretBackend:
    """Détecte le backend disponible (env prioritaire, sinon Vault)."""
    if os.environ.get("LLM_GATEWAY_USE_ENV") == "1":
        return EnvSecretBackend()
    try:
        return PowerShellVaultBackend()
    except RuntimeError:
        log.info("PowerShell absent, bascule sur variables d'environnement")
        return EnvSecretBackend()