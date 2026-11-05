# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Guardrail neutre : accepte toujours. C'est le défaut."""

from __future__ import annotations

from llm_gateway.guardrails.base import Guardrail, GuardrailResult


class NoOpGuardrail(Guardrail):
    """Retourne systématiquement is_valid=True.

    Utile pour :
    - le développement et la CI (pas de dépendance NeMo) ;
    - les comparaisons de modèles sans couche qualité ;
    - un utilisateur qui veut juste le routage sans guardrail.
    """

    def check(self, task_text: str, response: str) -> GuardrailResult:
        return GuardrailResult(is_valid=True, reason="noop", flagged=False)