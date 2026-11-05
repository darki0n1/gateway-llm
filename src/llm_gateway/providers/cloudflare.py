# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Provider Cloudflare Workers AI (format spécifique)."""

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


class CloudflareProvider(Provider):
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        account_id: str,
        timeout: int = 120,
    ) -> None:
        self.name = name
        self.base_url = base_url.format(account_id=account_id).rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/{model}", headers=headers, json=payload,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"{self.name}: {e}") from e

        if resp.status_code == 429:
            raise RateLimitError(f"{self.name}: rate limit 429")

        if resp.status_code != 200:
            try:
                data = resp.json()
                errors = data.get("errors") or []
                if errors and isinstance(errors, list):
                    msg = " | ".join(
                        e.get("message", str(e)) for e in errors if isinstance(e, dict)
                    )
                else:
                    msg = str(data)[:200]
            except Exception:
                msg = resp.text[:200]
            raise ProviderUnavailableError(f"{self.name} HTTP {resp.status_code}: {msg}")

        try:
            text = resp.json()["result"]["response"].strip()
        except (KeyError, TypeError) as e:
            raise ProviderUnavailableError(f"{self.name}: réponse malformée ({e})") from e

        return ProviderResponse(text=text, model=model, provider=self.name)