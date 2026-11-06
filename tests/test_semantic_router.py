# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests du routeur sémantique (embeddings)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gateway_llm.semantic_router import SemanticRouter


@patch("gateway_llm.semantic_router.requests.post")
@patch("gateway_llm.semantic_router.requests.get")
def test_ensure_model_installed_already_present(mock_get, mock_post):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "nomic-embed-text:latest"}]},
    )
    router = SemanticRouter()
    assert router._ensure_model_installed() is True


@patch("gateway_llm.semantic_router.shutil.which", return_value="/usr/bin/ollama")
@patch("gateway_llm.semantic_router.subprocess.run")
@patch("gateway_llm.semantic_router.requests.get")
def test_ensure_model_installed_downloads_if_missing(mock_get, mock_run, _which):
    # Simule un Ollama sans le modèle
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"models": [{"name": "qwen3:4b"}]},
    )
    router = SemanticRouter()
    assert router._ensure_model_installed() is True
    # Vérifie que ollama pull a bien été appelé
    mock_run.assert_called_once()
    assert "pull" in mock_run.call_args[0][0]


@patch("gateway_llm.semantic_router.requests.post")
def test_get_embedding_success(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"embedding": [0.1, 0.2, 0.3]},
    )
    router = SemanticRouter()
    assert router._get_embedding("test") == [0.1, 0.2, 0.3]


@patch("gateway_llm.semantic_router.requests.post")
def test_get_embedding_failure(mock_post):
    import requests

    mock_post.side_effect = requests.exceptions.ConnectionError()
    router = SemanticRouter()
    assert router._get_embedding("test") is None


def test_cosine_similarity():
    router = SemanticRouter()
    # Vecteurs identiques = 1.0
    assert router._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    # Vecteurs orthogonaux = 0.0
    assert router._cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    # Vecteur nul = 0.0
    assert router._cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


@patch("gateway_llm.semantic_router.SemanticRouter._get_embedding")
def test_route_above_threshold(mock_get_embedding):
    router = SemanticRouter(threshold=0.8)
    # On simule des embeddings pré-calculés
    router._is_ready = True
    router._domain_embeddings = {
        "translation": [[1.0, 0.0]],
        "code_debug": [[0.0, 1.0]],
    }
    # Le texte à router est très proche de "translation"
    mock_get_embedding.return_value = [0.9, 0.1]

    result = router.route("Traduis ceci")
    assert result is not None
    assert result.domain == "translation"
    assert result.score > 0.8


@patch("gateway_llm.semantic_router.SemanticRouter._get_embedding")
def test_route_below_threshold(mock_get_embedding):
    router = SemanticRouter(threshold=0.9)
    router._is_ready = True
    router._domain_embeddings = {
        "translation": [[1.0, 0.0]],
        "code_debug": [[0.0, 1.0]],
    }
    # Le texte est à mi-chemin, donc similaire à ~0.7 (en dessous du seuil 0.9)
    mock_get_embedding.return_value = [1.0, 1.0]

    result = router.route("Fais un truc")
    assert result is None
