# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Adaptateur RWS TrainAI (M-GATE) pour Translation.

M-GATE publie un leaderboard public mais pas d'API JSON documentée.
Cache local comme pour F5.
"""

from __future__ import annotations

import json
import logging
import pathlib

from .base import BenchmarkResult, BenchmarkSource, TaskCategory
from .normalizer import normalize_model_name

log = logging.getLogger(__name__)

_RWS_CACHE = pathlib.Path("benchmarks_cache/rws_translation.json")


class RWSTranslationAdapter(BenchmarkSource):
    name = "rws"

    def supports(self, category: TaskCategory) -> bool:
        return category is TaskCategory.TRANSLATION

    def fetch(self, category: TaskCategory) -> list[BenchmarkResult]:
        if category is not TaskCategory.TRANSLATION or not _RWS_CACHE.exists():
            return []
        try:
            data = json.loads(_RWS_CACHE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("RWS: lecture cache échouée: %s", e)
            return []

        results: list[BenchmarkResult] = []
        for item in data.get("models", []):
            raw_name = item.get("model", "")
            # M-GATE note sur 5 -> normalisé en /100
            score_5 = item.get("overall_score")
            if not raw_name or score_5 is None:
                continue
            results.append(
                BenchmarkResult(
                    model_key=normalize_model_name(raw_name),
                    category=category,
                    score=float(score_5) * 20.0,  # 4.5/5 -> 90/100
                    source=self.name,
                    raw_name=raw_name,
                )
            )
        return results
