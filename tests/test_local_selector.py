# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests du sélecteur local (catalogue Ollama × benchmarks × hardware)."""

from __future__ import annotations

import json
import pathlib

import pytest

from gateway_llm.benchmarks.aggregator import BenchmarkAggregator
from gateway_llm.benchmarks.base import (
    BenchmarkResult,
    BenchmarkSource,
    TaskCategory,
)
from gateway_llm.benchmarks.cache import BenchmarkCache
from gateway_llm.hardware import HardwareInfo
from gateway_llm.local_selector import (
    OllamaModelInfo,
    load_ollama_catalog,
    select_local_models,
)


# ─── Helpers ───────────────────────────────────────────────────
def _write_catalog(path: pathlib.Path, models: list[dict]) -> pathlib.Path:
    path.write_text(
        json.dumps({"last_updated": "2026-01-01", "models": models}),
        encoding="utf-8",
    )
    return path


class _FakeBenchmarkSource(BenchmarkSource):
    """Source de benchmark minimale, pilotée par un dict."""

    def __init__(self, scores: dict[str, float], category: TaskCategory):
        self.name = "fake"
        self._scores = scores
        self._category = category

    def supports(self, category):
        return category is self._category

    def fetch(self, category):
        return [
            BenchmarkResult(
                model_key=k,
                category=category,
                score=v,
                source="fake",
            )
            for k, v in self._scores.items()
        ]


# ─── load_ollama_catalog ───────────────────────────────────────
def test_load_catalog_valid(tmp_path):
    path = _write_catalog(
        tmp_path / "cat.json",
        [
            {
                "name": "qwen3.8",
                "capabilities": ["tools", "thinking"],
                "tags": [
                    {
                        "tag": "27b-q4_K_M",
                        "size_gb": 16.0,
                        "param_count_b": 27.3,
                        "quantization": "Q4_K_M",
                    },
                    {
                        "tag": "7b-q4_K_M",
                        "size_gb": 4.5,
                        "param_count_b": 7.0,
                        "quantization": "Q4_K_M",
                    },
                ],
            }
        ],
    )
    models = load_ollama_catalog(path)
    assert len(models) == 2
    assert all(isinstance(m, OllamaModelInfo) for m in models)
    assert models[0].name == "qwen3.8"
    assert models[0].full_name == "qwen3.8:27b-q4_K_M"
    assert models[0].size_gb == pytest.approx(16.0)
    assert "tools" in models[0].capabilities


def test_load_catalog_missing_file(tmp_path):
    assert load_ollama_catalog(tmp_path / "absent.json") == []


def test_load_catalog_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not valid json", encoding="utf-8")
    assert load_ollama_catalog(path) == []


def test_load_catalog_skips_entries_without_size(tmp_path):
    path = _write_catalog(
        tmp_path / "cat.json",
        [
            {
                "name": "broken",
                "capabilities": [],
                "tags": [
                    {"tag": "x", "size_gb": None},  # sans size → skip
                    {"tag": "y", "size_gb": 4.0},  # OK
                ],
            },
            {
                "name": "no_tags",
                "capabilities": [],
                "tags": [],
            },
        ],
    )
    models = load_ollama_catalog(path)
    assert len(models) == 1
    assert models[0].full_name == "broken:y"


def test_load_catalog_default_path_missing(tmp_path, monkeypatch):
    """Sans argument, utilise _OLLAMA_CATALOG (absent → [])."""
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", tmp_path / "absent.json")
    assert load_ollama_catalog() == []


# ─── select_local_models : cas de garde ────────────────────────
def test_select_no_catalog_returns_empty(tmp_path, monkeypatch):
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", tmp_path / "absent.json")
    hw = HardwareInfo(vram_gb=24.0, source="test")
    src = _FakeBenchmarkSource({}, TaskCategory.CODE_DEBUG)
    agg = BenchmarkAggregator([src], cache=BenchmarkCache(tmp_path))
    assert select_local_models(agg, hw, domains=["code_debug"]) == {}


def test_select_zero_capacity_returns_empty(tmp_path, monkeypatch):
    catalog = _write_catalog(
        tmp_path / "cat.json",
        [{"name": "m", "capabilities": [], "tags": [{"tag": "t", "size_gb": 4.0}]}],
    )
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", catalog)
    hw = HardwareInfo(source="test")  # capacité 0
    src = _FakeBenchmarkSource({"m": 90.0}, TaskCategory.CODE_DEBUG)
    agg = BenchmarkAggregator([src], cache=BenchmarkCache(tmp_path))
    assert select_local_models(agg, hw, domains=["code_debug"]) == {}


def test_select_unknown_domain_skipped(tmp_path, monkeypatch):
    catalog = _write_catalog(
        tmp_path / "cat.json",
        [{"name": "m", "capabilities": [], "tags": [{"tag": "t", "size_gb": 4.0}]}],
    )
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", catalog)
    hw = HardwareInfo(vram_gb=24.0, source="test")
    agg = BenchmarkAggregator([], cache=BenchmarkCache(tmp_path))
    result = select_local_models(agg, hw, domains=["pas_un_domaine"])
    assert result == {}


def test_select_no_scores_for_domain(tmp_path, monkeypatch):
    """Si aucun score benchmark pour la catégorie, rien n'est retenu."""
    catalog = _write_catalog(
        tmp_path / "cat.json",
        [{"name": "m", "capabilities": [], "tags": [{"tag": "t", "size_gb": 3.0}]}],
    )
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", catalog)
    hw = HardwareInfo(vram_gb=24.0, source="test")
    # Source qui ne supporte QUE thinking, pas code_debug
    src = _FakeBenchmarkSource({"m": 90.0}, TaskCategory.THINKING)
    agg = BenchmarkAggregator([src], cache=BenchmarkCache(tmp_path))
    assert select_local_models(agg, hw, domains=["code_debug"]) == {}


# ─── select_local_models : filtrage & tri ─────────────────────
def test_select_filters_by_capacity(tmp_path, monkeypatch):
    """Un modèle trop gros pour la machine est exclu, même mieux noté."""
    catalog = _write_catalog(
        tmp_path / "cat.json",
        [
            # runtime = 3.9, tient dans 10 Go
            {"name": "small", "capabilities": [], "tags": [{"tag": "4b", "size_gb": 3.0}]},
            # runtime = 52.0, ne tient pas
            {"name": "big", "capabilities": [], "tags": [{"tag": "70b", "size_gb": 40.0}]},
        ],
    )
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", catalog)
    hw = HardwareInfo(vram_gb=10.0, source="test")
    src = _FakeBenchmarkSource(
        {"small": 80.0, "big": 99.0},
        TaskCategory.CODE_DEBUG,
    )
    agg = BenchmarkAggregator([src], cache=BenchmarkCache(tmp_path))
    result = select_local_models(agg, hw, domains=["code_debug"])
    assert result == {"code_debug": ["small:4b"]}


def test_select_sorts_by_score_and_keeps_top_n(tmp_path, monkeypatch):
    """Tri décroissant par score, top N par domaine."""
    catalog = _write_catalog(
        tmp_path / "cat.json",
        [
            {"name": "a", "capabilities": [], "tags": [{"tag": "t", "size_gb": 3.0}]},
            {"name": "b", "capabilities": [], "tags": [{"tag": "t", "size_gb": 3.0}]},
            {"name": "c", "capabilities": [], "tags": [{"tag": "t", "size_gb": 3.0}]},
        ],
    )
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", catalog)
    hw = HardwareInfo(vram_gb=24.0, source="test")
    src = _FakeBenchmarkSource(
        {"a": 70.0, "b": 95.0, "c": 85.0},
        TaskCategory.CODE_DEBUG,
    )
    agg = BenchmarkAggregator([src], cache=BenchmarkCache(tmp_path))
    result = select_local_models(agg, hw, domains=["code_debug"], max_per_domain=2)
    assert result["code_debug"] == ["b:t", "c:t"]


def test_select_multiple_domains(tmp_path, monkeypatch):
    """Chaque domaine est traité indépendamment."""
    catalog = _write_catalog(
        tmp_path / "cat.json",
        [
            {"name": "coder", "capabilities": [], "tags": [{"tag": "t", "size_gb": 3.0}]},
            {"name": "thinker", "capabilities": [], "tags": [{"tag": "t", "size_gb": 3.0}]},
        ],
    )
    import gateway_llm.local_selector as ls

    monkeypatch.setattr(ls, "_OLLAMA_CATALOG", catalog)
    hw = HardwareInfo(vram_gb=24.0, source="test")

    class _MultiSource(BenchmarkSource):
        name = "multi"

        def supports(self, category):
            return category in (TaskCategory.CODE_DEBUG, TaskCategory.THINKING)

        def fetch(self, category):
            if category is TaskCategory.CODE_DEBUG:
                return [BenchmarkResult("coder", category, 90.0, "fake")]
            if category is TaskCategory.THINKING:
                return [BenchmarkResult("thinker", category, 88.0, "fake")]
            return []

    agg = BenchmarkAggregator([_MultiSource()], cache=BenchmarkCache(tmp_path))
    result = select_local_models(agg, hw, domains=["code_debug", "thinking"])
    assert result["code_debug"] == ["coder:t"]
    assert result["thinking"] == ["thinker:t"]
