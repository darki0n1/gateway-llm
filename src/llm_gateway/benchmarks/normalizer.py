# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Normalisation des noms de modèles et appariement flou.

Aucun fichier d'alias à maintenir : les règles sont génériques.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


_STRIP_PREFIXES = ("openai/", "anthropic/", "google/", "meta/", "mistralai/")
_STRIP_SUFFIXES = (
    "-latest", "-instruct", "-chat", "-preview", "-thinking",
    "-q4_k_m", "-q4_k_s", "-q5_k_m", "-q8_0", "-fp16",
)
_TAG_PATTERN = re.compile(r":\d+[bm]", re.IGNORECASE)


def normalize_model_name(raw: str) -> str:
    """Normalise un nom de modèle brut en forme canonique.

    Exemples :
        "qwen/qwen3.8-27b"           -> "qwen3.8-27b"
        "qwen3.6:27b-q4_K_M"         -> "qwen3.6-27b"
        "mistral-large-latest"       -> "mistral-large"
        "Claude Mythos 5"            -> "claude-mythos-5"
    """
    name = raw.strip().lower()
    for prefix in _STRIP_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = _TAG_PATTERN.sub("", name)          # retire ":27b"
    for suffix in _STRIP_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    name = re.sub(r"[_\s]+", "-", name)        # espaces/underscores -> tirets
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name


def fuzzy_match(query: str, candidates: list[str], threshold: float = 0.80) -> str | None:
    """Retourne le candidat le plus proche si la similarité dépasse le seuil."""
    if not candidates:
        return None
    scored = [
        (c, SequenceMatcher(None, query, c).ratio())
        for c in candidates
    ]
    best, score = max(scored, key=lambda x: x[1])
    return best if score >= threshold else None