# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Adaptateur F5 Labs (CASI / ARS) pour Safety et Red Teaming.

F5 ne publie pas d'API JSON documentée. On utilise le cache local,
mis à jour manuellement ou via un script séparé, et on ne fait
AUCUN scraping en runtime.
"""

from __future__ import annotations

import json
import logging
import pathlib

from .base import BenchmarkResult, BenchmarkSource, TaskCategory
from .normalizer import normalize_model_name

log = logging.getLogger(__name__)

# Fichier rempli manuellement depuis les leaderboards F5 (mensuels).
_F5_CACHE = pathlib.Path("benchmarks_cache/f5_safety.json")

# CASI = sécurité générale ; ARS = résistance aux attaques agentiques.
_F5_CATEGORY = {
    TaskCategory.SAFETY: "casi",
    TaskCategory.RED_TEAMING: "ars",
}


class F5SafetyAdapter(BenchmarkSource):
    name = "f5"

    def supports(self, category: TaskCategory) -> bool:
        return category in _F5_CATEGORY

    def fetch(self, category: TaskCategory) -> list[BenchmarkResult]:
        if not self.supports(category) or not _F5_CACHE.exists():
            if not _F5_CACHE.exists():
                log.warning("F5: cache absent (%s). Skipped.", _F5_CACHE)
            return []
        metric = _F5_CATEGORY[category]
        try:
            data = json.loads(_F5_CACHE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("F5: lecture cache échouée: %s", e)
            return []

        results: list[BenchmarkResult] = []
        for item in data.get("models", []):
            raw_name = item.get("model", "")
            score = item.get(metric)
            if not raw_name or score is None:
                continue
            results.append(
                BenchmarkResult(
                    model_key=normalize_model_name(raw_name),
                    category=category,
                    score=float(score),  # 0-100, plus haut = mieux
                    source=self.name,
                    raw_name=raw_name,
                )
            )
        return results
