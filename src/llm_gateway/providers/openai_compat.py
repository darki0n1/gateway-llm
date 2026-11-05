# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Provider compatible OpenAI (supporte le multimodal via content array)."""

from __future__ import annotations

import logging

import requests

from .base import (
    Provider,
    ProviderError,
    ProviderResponse,
    ProviderUnavailableError,
    RateLimitError,
)

log = logging.getLogger(__name__)


class OpenAICompatibleProvider(Provider):
    def __init__(
        self,
        name: str,
        base_url: str,
        secret: str,
        extra_headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._secret = secret
        self._extra_headers = extra_headers or {}
        self._timeout = timeout

    def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
        image_b64: str | None = None,
    ) -> ProviderResponse:
        headers = {
            "Authorization": f"Bearer {self._secret}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        if image_b64:
            user_content: str | list = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
            ]
        else:
            user_content = prompt

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        log.debug(
            "POST %s/chat/completions model=%s image=%s",
            self.base_url, model, bool(image_b64),
        )

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers, json=payload, timeout=self._timeout,
            )
        except requests.exceptions.Timeout as e:
            raise ProviderError(f"{self.name}: timeout") from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"{self.name}: {e}") from e

        if resp.status_code == 429:
            raise RateLimitError(f"{self.name}: rate limit 429")

        if resp.status_code != 200:
            try:
                data = resp.json()
                err = data.get("error", data)
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            except Exception:
                msg = resp.text[:200]
            if resp.status_code == 404:
                msg = f"modèle '{model}' introuvable. Détail: {msg}"
            raise ProviderUnavailableError(f"{self.name} HTTP {resp.status_code}: {msg}")

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {}) or {}
            return ProviderResponse(
                text=text,
                model=model,
                provider=self.name,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderUnavailableError(f"{self.name}: réponse malformée ({e})") from e