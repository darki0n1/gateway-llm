# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Utilitaires partagés pour les tests (providers factices, réponses)."""

from __future__ import annotations

from gateway_llm.providers.base import Provider, ProviderResponse


class FakeProvider(Provider):
    """Provider scriptable : chaque appel consomme le prochain outcome."""

    def __init__(self, name: str, outcomes: list) -> None:
        self.name = name
        self._outcomes = list(outcomes)
        self.call_count = 0
        self.last_prompt: str | None = None

    def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
        image_b64: str | None = None,
    ):
        self.last_prompt = prompt
        if self.call_count >= len(self._outcomes):
            raise RuntimeError(f"{self.name}: plus d'outcomes scriptés")
        outcome = self._outcomes[self.call_count]
        self.call_count += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_response(text: str = "ok", model: str = "m1", provider: str = "fake"):
    return ProviderResponse(text=text, model=model, provider=provider)
