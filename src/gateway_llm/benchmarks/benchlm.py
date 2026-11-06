# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Adaptateur BenchLM (https://benchlm.ai/api/data/leaderboard)."""

from __future__ import annotations

import logging

import requests

from .base import BenchmarkResult, BenchmarkSource, TaskCategory
from .normalizer import normalize_model_name

log = logging.getLogger(__name__)

_BASE_URL = "https://benchlm.ai/api/data/leaderboard"

# Correspondance catégorie interne -> catégorie BenchLM
_BENCHLM_CATEGORY = {
    TaskCategory.CODE_DEBUG: "coding",
    TaskCategory.THINKING: "reasoning",
    TaskCategory.PROBLEM_SOLVING: "reasoning",
    TaskCategory.FACT_CHECKING: "knowledge",
    TaskCategory.PROMPT_CREATION: "instructionFollowing",
    TaskCategory.MULTIMODAL_EXTRACTION: "multimodalGrounded",
}


class BenchLMAdapter(BenchmarkSource):
    name = "benchlm"

    def supports(self, category: TaskCategory) -> bool:
        return category in _BENCHLM_CATEGORY

    def fetch(self, category: TaskCategory) -> list[BenchmarkResult]:
        if not self.supports(category):
            return []
        benchlm_cat = _BENCHLM_CATEGORY[category]
        log.info("BenchLM: fetch category=%s", benchlm_cat)
        try:
            resp = requests.get(
                _BASE_URL,
                params={"category": benchlm_cat, "limit": 200, "format": "json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("BenchLM fetch failed: %s", e)
            return []

        results: list[BenchmarkResult] = []
        for item in data.get("models", []):
            raw_name = item.get("model", "")
            if not raw_name:
                continue
            scores = item.get("categoryScores", {}) or {}
            score = scores.get(benchlm_cat)
            if score is None:
                score = item.get("overallScore")
            if score is None:
                continue
            results.append(
                BenchmarkResult(
                    model_key=normalize_model_name(raw_name),
                    category=category,
                    score=float(score),
                    source=self.name,
                    raw_name=raw_name,
                )
            )
        log.info("BenchLM: %d résultats pour %s", len(results), category.value)
        return results
