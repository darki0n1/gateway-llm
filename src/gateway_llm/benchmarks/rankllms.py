# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Adaptateur RankLLMs (https://api.rankllms.com)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .base import BenchmarkResult, BenchmarkSource, TaskCategory
from .normalizer import normalize_model_name

log = logging.getLogger(__name__)

_BASE_URL = "https://api.rankllms.com/api/v1"

# RankLLMs expose intelligence, coding, agentic, open-weight.
_RANKLLMS_CATEGORY = {
    TaskCategory.CODE_DEBUG: "coding",
    TaskCategory.THINKING: "reasoning",
    TaskCategory.PROBLEM_SOLVING: "reasoning",
}


class RankLLMsAdapter(BenchmarkSource):
    name = "rankllms"

    def supports(self, category: TaskCategory) -> bool:
        return category in _RANKLLMS_CATEGORY

    def fetch(self, category: TaskCategory) -> list[BenchmarkResult]:
        if not self.supports(category):
            return []
        dimension = _RANKLLMS_CATEGORY[category]
        log.info("RankLLMs: fetch dimension=%s", dimension)
        try:
            params: Any = {"dimension": dimension, "limit": 100}
            resp = requests.get(
                f"{_BASE_URL}/leaderboard",
                params=params,
                timeout=30,
            )  # type: ignore[arg-type]

            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("RankLLMs fetch failed: %s", e)
            return []

        results: list[BenchmarkResult] = []
        items = data.get("data") or data.get("leaderboard") or []
        for item in items:
            raw_name = item.get("model") or item.get("name") or ""
            score = item.get("score") or item.get(dimension)
            if not raw_name or score is None:
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
        log.info("RankLLMs: %d résultats pour %s", len(results), category.value)
        return results
