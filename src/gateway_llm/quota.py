# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Gestion des quotas providers avec cooldown temporel.

Correction du bug de l'ancien projet : `_PROVIDER_CALLS["__429_xxx"]`
n'était jamais remis à zéro, donc un provider qui avait 2× 429 était
épuisé pour la session entière même après des heures.

Ici, un provider est "en cooldown" pendant `cooldown_seconds` après le
dernier 429, puis redevient disponible automatiquement. Pas d'état
global : l'instance est injectée dans le Router.
"""

from __future__ import annotations

import threading
import time


class QuotaManager:
    def __init__(self, cooldown_seconds: int = 60) -> None:
        self._cooldown = cooldown_seconds
        self._last_429: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_available(self, provider: str) -> bool:
        with self._lock:
            t = self._last_429.get(provider)
            if t is None:
                return True
            return (time.monotonic() - t) >= self._cooldown

    def record_rate_limit(self, provider: str) -> None:
        with self._lock:
            self._last_429[provider] = time.monotonic()

    def cooldown_remaining(self, provider: str) -> float:
        with self._lock:
            t = self._last_429.get(provider)
            if t is None:
                return 0.0
            elapsed = time.monotonic() - t
            return max(0.0, self._cooldown - elapsed)

    def reset(self) -> None:
        """Utile pour les tests."""
        with self._lock:
            self._last_429.clear()
