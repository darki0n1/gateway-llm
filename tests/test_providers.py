# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests des providers (HTTP mocké, pas de réseau)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gateway_llm.providers.base import (
    ProviderUnavailableError,
    RateLimitError,
)
from gateway_llm.providers.cloudflare import CloudflareProvider
from gateway_llm.providers.ollama import OllamaProvider
from gateway_llm.providers.openai_compat import OpenAICompatibleProvider


# ─── OpenAI-compatible (Groq / Mistral / OpenRouter / Google AI / NVIDIA) ──
@patch("gateway_llm.providers.openai_compat.requests.post")
def test_openai_compat_success(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )
    p = OpenAICompatibleProvider("test", "http://api", "key")
    r = p.complete("m1", "prompt", max_tokens=100)
    assert r.text == "hello"
    assert r.model == "m1"
    assert r.provider == "test"
    assert r.input_tokens == 10
    assert r.output_tokens == 5
    assert r.truncated is False


@patch("gateway_llm.providers.openai_compat.requests.post")
def test_openai_compat_429(mock_post):
    mock_post.return_value = MagicMock(status_code=429)
    p = OpenAICompatibleProvider("test", "http://api", "key")
    with pytest.raises(RateLimitError):
        p.complete("m1", "prompt", max_tokens=100)


@patch("gateway_llm.providers.openai_compat.requests.post")
def test_openai_compat_404(mock_post):
    mock_post.return_value = MagicMock(
        status_code=404,
        json=lambda: {"error": {"message": "model not found"}},
    )
    p = OpenAICompatibleProvider("test", "http://api", "key")
    with pytest.raises(ProviderUnavailableError, match="introuvable"):
        p.complete("nonexistent", "prompt", max_tokens=100)


@patch("gateway_llm.providers.openai_compat.requests.post")
def test_openai_compat_500(mock_post):
    mock_post.return_value = MagicMock(
        status_code=500,
        json=lambda: {"error": "internal"},
    )
    p = OpenAICompatibleProvider("test", "http://api", "key")
    with pytest.raises(ProviderUnavailableError, match="HTTP 500"):
        p.complete("m1", "prompt", max_tokens=100)


@patch("gateway_llm.providers.openai_compat.requests.post")
def test_openai_compat_malformed(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"unexpected": "shape"},
    )
    p = OpenAICompatibleProvider("test", "http://api", "key")
    with pytest.raises(ProviderUnavailableError, match="malformée"):
        p.complete("m1", "prompt", max_tokens=100)


@patch("gateway_llm.providers.openai_compat.requests.post")
def test_openai_compat_extra_headers(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        },
    )
    p = OpenAICompatibleProvider(
        "openrouter", "http://api", "key",
        extra_headers={"HTTP-Referer": "http://localhost"},
    )
    p.complete("m1", "prompt", max_tokens=100)
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["HTTP-Referer"] == "http://localhost"


# ─── Ollama ────────────────────────────────────────────────────
@patch("gateway_llm.providers.ollama.requests.post")
def test_ollama_success(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "message": {"content": "response"},
            "done_reason": "stop",
            "prompt_eval_count": 15,
            "eval_count": 8,
        },
    )
    p = OllamaProvider("ollama", "http://localhost:11434")
    r = p.complete("qwen", "prompt", max_tokens=100)
    assert r.text == "response"
    assert r.input_tokens == 15
    assert r.output_tokens == 8
    assert r.truncated is False


@patch("gateway_llm.providers.ollama.requests.post")
def test_ollama_truncation_detected(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "message": {"content": "cut..."},
            "done_reason": "length",
            "prompt_eval_count": 10,
            "eval_count": 100,
        },
    )
    p = OllamaProvider("ollama", "http://localhost:11434")
    r = p.complete("qwen", "prompt", max_tokens=100)
    assert r.truncated is True


@patch("gateway_llm.providers.ollama.requests.post")
def test_ollama_empty_response(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"message": {"content": ""}, "done_reason": "stop"},
    )
    p = OllamaProvider("ollama", "http://localhost:11434")
    with pytest.raises(ProviderUnavailableError, match="vide"):
        p.complete("qwen", "prompt", max_tokens=100)


@patch("gateway_llm.providers.ollama.requests.get")
def test_ollama_health_ok(mock_get):
    mock_get.return_value = MagicMock(status_code=200)
    p = OllamaProvider("ollama", "http://localhost:11434")
    assert p.health() is True


@patch("gateway_llm.providers.ollama.requests.get")
def test_ollama_health_down(mock_get):
    import requests as req
    mock_get.side_effect = req.exceptions.ConnectionError("refused")
    p = OllamaProvider("ollama", "http://localhost:11434")
    assert p.health() is False


# ─── Cloudflare ────────────────────────────────────────────────
@patch("gateway_llm.providers.cloudflare.requests.post")
def test_cloudflare_success(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"result": {"response": "cloudflare reply"}},
    )
    p = CloudflareProvider(
        "cf", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run",
        api_key="key", account_id="acc123",
    )
    r = p.complete("@cf/meta/llama", "prompt", max_tokens=100)
    assert r.text == "cloudflare reply"
    assert r.provider == "cf"


@patch("gateway_llm.providers.cloudflare.requests.post")
def test_cloudflare_429(mock_post):
    mock_post.return_value = MagicMock(status_code=429)
    p = CloudflareProvider(
        "cf", "https://x/{account_id}/ai/run", api_key="k", account_id="a",
    )
    with pytest.raises(RateLimitError):
        p.complete("@cf/m", "prompt", max_tokens=100)


@patch("gateway_llm.providers.cloudflare.requests.post")
def test_cloudflare_malformed(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200, json=lambda: {"unexpected": "shape"},
    )
    p = CloudflareProvider(
        "cf", "https://x/{account_id}/ai/run", api_key="k", account_id="a",
    )
    with pytest.raises(ProviderUnavailableError, match="malformée"):
        p.complete("@cf/m", "prompt", max_tokens=100)