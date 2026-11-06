# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Guardrail NeMo (détection d'hallucinations).

Dépendance optionnelle : `pip install llm-gateway[guardrails]`.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from .base import Guardrail, GuardrailResult

log = logging.getLogger(__name__)


class NemoGuardrail(Guardrail):
    # Déclaration au niveau classe : Pylance accepte ainsi
    # la lecture (tests) et l'affectation (mocks) sans contrainte
    # sur le type exact retourné par LLMRails.
    _app: Any = None

    def __init__(self, config_path: str | pathlib.Path) -> None:
        self._config_path = pathlib.Path(config_path)
        self._app = None  # lazy init

    def _ensure_app(self) -> Any:
        if self._app is not None:
            return self._app
        try:
            from nemoguardrails import LLMRails, RailsConfig
        except ImportError as e:
            raise RuntimeError(
                "NeMo Guardrails non installé. "
                "Lance `pip install llm-gateway[guardrails]`."
            ) from e

        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Dossier guardrails introuvable : {self._config_path}"
            )
        cfg = RailsConfig.from_path(str(self._config_path))
        self._app = LLMRails(cfg)
        log.info("NeMo Guardrails initialisé depuis %s", self._config_path)
        return self._app

    def _extract_text(self, raw: Any) -> str:
        """Normalise la sortie de LLMRails.generate()."""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            v = raw.get("response", "")
            if isinstance(v, list):
                return "\n".join(
                    m.get("content", "") for m in v
                    if isinstance(m, dict) and m.get("role") == "assistant"
                )
            return str(v)
        # GenerationResponse-like
        v = getattr(raw, "response", "")
        if isinstance(v, list):
            return "\n".join(
                m.get("content", "") for m in v
                if isinstance(m, dict) and m.get("role") == "assistant"
            )
        return str(v)

    def check(self, task_text: str, response: str) -> GuardrailResult:
        try:
            app = self._ensure_app()
            prompt = f"Tâche: {task_text}\n\nRéponse à vérifier: {response}"
            raw = app.generate(messages=[{"role": "user", "content": prompt}])
            verdict = self._extract_text(raw).lower()

            if any(kw in verdict for kw in ("hallucination", "not supported", "false")):
                return GuardrailResult(
                    is_valid=False,
                    reason="Hallucination suspectée par NeMo",
                    flagged=True,
                )
            return GuardrailResult(is_valid=True)
        except Exception as e:
            # Fail-open : en cas d'erreur, on ne bloque pas la tâche
            log.warning("NeMo Guardrail erreur (fail-open): %s", e)
            return GuardrailResult(is_valid=True, reason=f"guardrail indisponible: {e}")