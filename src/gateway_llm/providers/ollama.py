# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Provider Ollama natif (supporte le multimodal via `images`)."""

from __future__ import annotations

import logging

import requests

from .base import Provider, ProviderError, ProviderResponse, ProviderUnavailableError

log = logging.getLogger(__name__)


class OllamaProvider(Provider):
    def __init__(self, name: str, base_url: str, timeout: int = 300) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    def health(self) -> bool:
        try:
            return requests.get(f"{self.base_url}/api/tags", timeout=2).status_code == 200
        except requests.exceptions.RequestException:
            return False

    def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
        image_b64: str | None = None,
    ) -> ProviderResponse:
        message: dict = {"role": "user", "content": prompt}
        if image_b64:
            message["images"] = [image_b64]

        payload = {
            "model": model,
            "messages": [message],
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self._timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"{self.name}: {e}") from e

        data = resp.json()
        truncated = data.get("done_reason") == "length"
        if truncated:
            log.warning("Ollama: troncature (num_predict=%d)", max_tokens)

        text = data.get("message", {}).get("content", "").strip()
        if not text:
            raise ProviderUnavailableError(f"{self.name}: réponse vide")

        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            truncated=truncated,
        )
