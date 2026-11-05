# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Diagnostic de l'environnement : deps Python, Ollama, modèles locaux.

Utilisé par `llm-gateway doctor` (rapport seul) et par le pre-flight
de `batch run` (auto-installation optionnelle).
"""

from __future__ import annotations

import importlib
import logging
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
        symbols = {
            Severity.OK: "✓",
            Severity.WARNING: "⚠",
            Severity.ERROR: "✗",
        }
        for r in self.results:
            print(f"  {symbols[r.severity]} {r.name}: {r.message}")
            if r.hint:
                print(f"      → {r.hint}")


# Dépendances vérifiées par le doctor.
_REQUIRED_PY = ["requests", "pydantic", "yaml"]
_OPTIONAL_PY = {
    "bs4": "pip install beautifulsoup4  (nécessaire pour intake from-urls)",
    "nemoguardrails": "pip install -e \".[guardrails]\"  (pour NemoGuardrail)",
}


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
        has_binary = self._check_ollama_binary(report)
        has_daemon = self._check_ollama_daemon(report) if has_binary else False
        if has_binary and has_daemon and self._required_models:
            self._check_models(report)
        return report

    def _check_python(self, report: DoctorReport) -> None:
        missing_required = []
        for mod in _REQUIRED_PY:
            try:
                importlib.import_module(mod)
            except ImportError:
                missing_required.append(mod)

        if missing_required:
            report.add(CheckResult(
                name="Python (requis)",
                severity=Severity.ERROR,
                message=f"Manquants : {', '.join(missing_required)}",
                hint="pip install -e .",
            ))
        else:
            report.add(CheckResult(
                name="Python (requis)",
                severity=Severity.OK,
                message="requests, pydantic, yaml importables",
            ))

        missing_optional = []
        for mod in _OPTIONAL_PY:
            try:
                importlib.import_module(mod)
            except ImportError:
                missing_optional.append(mod)
        if missing_optional:
            for mod in missing_optional:
                report.add(CheckResult(
                    name=f"Python (optionnel) : {mod}",
                    severity=Severity.WARNING,
                    message="Absent",
                    hint=_OPTIONAL_PY[mod],
                ))

    def _check_ollama_binary(self, report: DoctorReport) -> bool:
        path = shutil.which("ollama")
        if not path:
            report.add(CheckResult(
                name="Ollama (binaire)",
                severity=Severity.WARNING,
                message="Introuvable dans le PATH",
                hint="Installer depuis https://ollama.com/download puis relancer",
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
                hint="Lancer : llm-gateway setup  (ou ollama pull <modèle>)",
            ))
        else:
            report.add(CheckResult(
                name="Modèles Ollama",
                severity=Severity.OK,
                message=f"{len(self._required_models)} modèle(s) installé(s)",
            ))