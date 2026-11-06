# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Cache local des scores de benchmarks (JSON, TTL 24h)."""

from __future__ import annotations

import json
import logging
import pathlib
import time
from dataclasses import asdict, dataclass

from .base import BenchmarkResult

log = logging.getLogger(__name__)

_CACHE_DIR = pathlib.Path("benchmarks_cache")
_TTL_SECONDS = 24 * 3600


@dataclass
class _Entry:
    fetched_at: float
    results: list[dict]


class BenchmarkCache:
    def __init__(self, cache_dir: pathlib.Path | None = None) -> None:
        self._dir = cache_dir or _CACHE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, source: str, category: str) -> pathlib.Path:
        return self._dir / f"{source}_{category}.json"

    def get(self, source: str, category: str) -> list[BenchmarkResult] | None:
        p = self._path(source, category)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            entry = _Entry(**data)
        except Exception:
            return None
        if time.time() - entry.fetched_at > _TTL_SECONDS:
            return None
        return [BenchmarkResult(**r) for r in entry.results]

    def put(self, source: str, category: str, results: list[BenchmarkResult]) -> None:
        entry = _Entry(
            fetched_at=time.time(),
            results=[asdict(r) for r in results],
        )
        self._path(source, category).write_text(
            json.dumps(asdict(entry), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("Cache écrit: %s/%s (%d résultats)", source, category, len(results))
