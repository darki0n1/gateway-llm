# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests du QuotaManager (cooldown temporel)."""

from __future__ import annotations

from unittest.mock import patch

from gateway_llm.quota import QuotaManager


def test_fresh_provider_available():
    q = QuotaManager(cooldown_seconds=60)
    assert q.is_available("groq")
    assert q.cooldown_remaining("groq") == 0.0


def test_after_rate_limit_unavailable():
    q = QuotaManager(cooldown_seconds=60)
    q.record_rate_limit("groq")
    assert not q.is_available("groq")
    assert 0 < q.cooldown_remaining("groq") <= 60


def test_cooldown_expires():
    with patch("gateway_llm.quota.time.monotonic") as mock_time:
        mock_time.return_value = 100.0
        q = QuotaManager(cooldown_seconds=60)
        q.record_rate_limit("groq")
        assert not q.is_available("groq")

        mock_time.return_value = 150.0  # 50s plus tard, encore en cooldown
        assert not q.is_available("groq")

        mock_time.return_value = 200.0  # 100s plus tard, expiré
        assert q.is_available("groq")
        assert q.cooldown_remaining("groq") == 0.0


def test_providers_independent():
    q = QuotaManager(cooldown_seconds=60)
    q.record_rate_limit("groq")
    assert not q.is_available("groq")
    assert q.is_available("mistral")


def test_429_consecutive_does_not_permanently_ban():
    """Le bug original : 2× 429 = ban permanent. Corrigé par le cooldown."""
    with patch("gateway_llm.quota.time.monotonic") as mock_time:
        mock_time.return_value = 100.0
        q = QuotaManager(cooldown_seconds=60)
        q.record_rate_limit("groq")
        q.record_rate_limit("groq")  # 2e 429 ne change rien

        mock_time.return_value = 200.0
        assert q.is_available("groq")  # expiré → redevient dispo


def test_reset_clears_cooldowns():
    q = QuotaManager(cooldown_seconds=60)
    q.record_rate_limit("groq")
    q.record_rate_limit("mistral")
    q.reset()
    assert q.is_available("groq")
    assert q.is_available("mistral")


def test_thread_safety():
    import threading

    q = QuotaManager(cooldown_seconds=60)

    def worker():
        for _ in range(100):
            q.record_rate_limit("groq")
            q.is_available("groq")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Pas de crash, l'état est cohérent
    assert not q.is_available("groq")
