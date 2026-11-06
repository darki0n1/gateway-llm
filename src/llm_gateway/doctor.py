# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Diagnostic de l'environnement : deps Python, Ollama, secrets, modèles."""

from __future__ import annotations

import importlib
import logging
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum

import requests

log = logging.getLogger(__name__)


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    severity: Severity
    message: str
    hint: str = ""


@dataclass
class DoctorReport:
    results: list[CheckResult] = field(default_factory=list)
    missing_models: list[str] = field(default_factory=list)

    def add(self, r: CheckResult) -> None:
        self.results.append(r)

    @property
    def has_errors(self) -> bool:
        return any(r.severity == Severity.ERROR for r in self.results)

    @property
    def has_warnings(self) -> bool:
        return any(r.severity == Severity.WARNING for r in self.results)

    def print_report(self) -> None:
        symbols = {Severity.OK: "✓", Severity.WARNING: "⚠", Severity.ERROR: "✗"}
        for r in self.results:
            print(f"  {symbols[r.severity]} {r.name}: {r.message}")
            if r.hint:
                print(f"      → {r.hint}")


_REQUIRED_PY = ["requests", "pydantic", "yaml"]
_OPTIONAL_PY = {
    "bs4": "pip install beautifulsoup4  (intake from-urls)",
    "nemoguardrails": "pip install -e \".[guardrails]\"  (NemoGuardrail)",
    "boto3": "pip install -e \".[aws]\"  (AWS Secrets Manager)",
    "azure.identity": "pip install -e \".[azure]\"  (Azure Key Vault)",
}

_CLOUD_API_ENV_VARS = [
    "GROQ_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY", "NVIDIA_API_KEY",
    "CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID",
]


class Doctor:
    def __init__(
        self,
        required_models: list[str] | None = None,
        ollama_url: str = "http://localhost:11434",
    ) -> None:
        self._required_models = required_models or []
        self._ollama_url = ollama_url.rstrip("/")

    def run(self) -> DoctorReport:
        report = DoctorReport()
        self._check_python(report)
        self._check_secret_storage(report)
        has_binary = self._check_ollama_binary(report)
        has_daemon = self._check_ollama_daemon(report) if has_binary else False
        if has_binary and has_daemon and self._required_models:
            self._check_models(report)
        return report

    def _check_python(self, report: DoctorReport) -> None:
        missing = [m for m in _REQUIRED_PY if not self._import_ok(m)]
        if missing:
            report.add(CheckResult(
                name="Python (requis)",
                severity=Severity.ERROR,
                message=f"Manquants : {', '.join(missing)}",
                hint="pip install -e .",
            ))
        else:
            report.add(CheckResult(
                name="Python (requis)",
                severity=Severity.OK,
                message="requests, pydantic, yaml importables",
            ))

        for mod, hint in _OPTIONAL_PY.items():
            if not self._import_ok(mod):
                report.add(CheckResult(
                    name=f"Python (optionnel) : {mod}",
                    severity=Severity.WARNING,
                    message="Absent",
                    hint=hint,
                ))

    @staticmethod
    def _import_ok(mod: str) -> bool:
        try:
            importlib.import_module(mod)
            return True
        except ImportError:
            return False

    def _check_secret_storage(self, report: DoctorReport) -> None:
        """Vérifie que les secrets sont dans un coffre-fort, pas en .env."""
        try:
            from llm_gateway.secrets import _load_config, get_backend
        except Exception as e:
            report.add(CheckResult(
                name="Stockage des secrets",
                severity=Severity.WARNING,
                message=f"Impossible de vérifier : {e}",
            ))
            return

        cfg = _load_config()
        if cfg is None or "backend" not in cfg:
            # Pas de config : détecte .env ou env vars
            env_file = __import__("pathlib").Path(".env")
            if env_file.exists():
                report.add(CheckResult(
                    name="Stockage des secrets",
                    severity=Severity.WARNING,
                    message="Fichier .env détecté (non chiffré)",
                    hint=(
                        "Un .env est lisible par tout processus. "
                        "Lancez : llm-gateway setup-secrets"
                    ),
                ))
                return

            risky = [v for v in _CLOUD_API_ENV_VARS if os.environ.get(v)]
            if risky:
                report.add(CheckResult(
                    name="Stockage des secrets",
                    severity=Severity.WARNING,
                    message=f"Variables d'env détectées : {', '.join(risky)}",
                    hint="Préférez un coffre-fort : llm-gateway setup-secrets",
                ))
                return

            report.add(CheckResult(
                name="Stockage des secrets",
                severity=Severity.WARNING,
                message="Aucun backend configuré",
                hint="Lancez : llm-gateway setup-secrets",
            ))
            return

        backend_name = cfg.get("backend", "?")
        try:
            backend = get_backend()
            if backend.is_available():
                report.add(CheckResult(
                    name="Stockage des secrets",
                    severity=Severity.OK,
                    message=f"Backend '{backend_name}' opérationnel",
                ))
            else:
                report.add(CheckResult(
                    name="Stockage des secrets",
                    severity=Severity.WARNING,
                    message=f"Backend '{backend_name}' configuré mais indisponible",
                    hint="Vérifiez la connexion au vault et vos credentials",
                ))
        except Exception as e:
            report.add(CheckResult(
                name="Stockage des secrets",
                severity=Severity.WARNING,
                message=f"Backend '{backend_name}' en erreur",
                hint=str(e)[:120],
            ))

    def _check_ollama_binary(self, report: DoctorReport) -> bool:
        path = shutil.which("ollama")
        if not path:
            report.add(CheckResult(
                name="Ollama (binaire)",
                severity=Severity.WARNING,
                message="Introuvable dans le PATH",
                hint="Installer depuis https://ollama.com/download",
            ))
            return False
        report.add(CheckResult(
            name="Ollama (binaire)",
            severity=Severity.OK,
            message=f"Trouvé ({path})",
        ))
        return True

    def _check_ollama_daemon(self, report: DoctorReport) -> bool:
        try:
            r = requests.get(f"{self._ollama_url}/api/tags", timeout=2)
            if r.status_code == 200:
                report.add(CheckResult(
                    name="Ollama (daemon)",
                    severity=Severity.OK,
                    message=f"Répond sur {self._ollama_url}",
                ))
                return True
            report.add(CheckResult(
                name="Ollama (daemon)",
                severity=Severity.WARNING,
                message=f"Répond HTTP {r.status_code}",
                hint="Vérifier avec : ollama serve",
            ))
            return False
        except requests.exceptions.RequestException:
            report.add(CheckResult(
                name="Ollama (daemon)",
                severity=Severity.WARNING,
                message=f"Injoignable sur {self._ollama_url}",
                hint="Lancer : ollama serve",
            ))
            return False

    def _list_local_models(self) -> set[str]:
        try:
            r = requests.get(f"{self._ollama_url}/api/tags", timeout=5)
            r.raise_for_status()
            return {m["name"] for m in r.json().get("models", [])}
        except Exception:
            return set()

    def _check_models(self, report: DoctorReport) -> None:
        installed = self._list_local_models()
        missing = [m for m in self._required_models if m not in installed]
        report.missing_models = missing
        if missing:
            report.add(CheckResult(
                name="Modèles Ollama",
                severity=Severity.WARNING,
                message=f"{len(missing)} manquant(s) : {', '.join(missing)}",
                hint="Lancer : llm-gateway setup",
            ))
        else:
            report.add(CheckResult(
                name="Modèles Ollama",
                severity=Severity.OK,
                message=f"{len(self._required_models)} modèle(s) installé(s)",
            ))