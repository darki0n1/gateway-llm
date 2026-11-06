# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Fusionne les sources, normalise et retourne un classement par catégorie."""

from __future__ import annotations

import logging

from .base import BenchmarkSource, TaskCategory
from .cache import BenchmarkCache

log = logging.getLogger(__name__)


class BenchmarkAggregator:
    def __init__(
        self,
        sources: list[BenchmarkSource],
        cache: BenchmarkCache | None = None,
        force_refresh: bool = False,
    ) -> None:
        self._sources = sources
        self._cache = cache or BenchmarkCache()
        self._force = force_refresh

    def get_scores(self, category: TaskCategory) -> dict[str, float]:
        """Retourne {model_key: score} pour une catégorie.

        Fusionne les sources : si plusieurs sources donnent un score,
        on prend la moyenne. Si une seule, on la garde.
        """
        accumulated: dict[str, list[float]] = {}
        for src in self._sources:
            if not src.supports(category):
                continue
            cached = None if self._force else self._cache.get(src.name, category.value)
            results = cached
            if results is None:
                results = src.fetch(category)
                if results:
                    self._cache.put(src.name, category.value, results)
            for r in results:
                accumulated.setdefault(r.model_key, []).append(r.score)

        return {model: sum(v) / len(v) for model, v in accumulated.items()}

    def rank_chain(
        self,
        chain: list[str],
        category: TaskCategory,
    ) -> list[str]:
        """Réordonne une chaîne par score décroissant.

        Les modèles sans score sont placés à la fin, dans l'ordre
        où ils apparaissaient dans la chaîne d'origine.
        """
        scores = self.get_scores(category)
        with_score: list[tuple[str, float]] = []
        without: list[str] = []
        for model_key in chain:
            s = scores.get(model_key)
            if s is None:
                without.append(model_key)
                log.warning(
                    "Aucun score benchmark pour %s (%s), gardé en fin", model_key, category.value
                )
            else:
                with_score.append((model_key, s))
        with_score.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in with_score] + without
