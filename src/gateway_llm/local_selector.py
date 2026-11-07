# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Sélection dynamique des modèles Ollama à installer.

Croise benchmarks + hardware + catalogue Ollama pour retourner,
par domaine, les meilleurs modèles locaux qui tiennent sur la machine.
Aucune liste de modèles en dur : le catalogue est mis à jour par
`scripts/refresh_ollama_library.py`.
"""

from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass

from gateway_llm.benchmarks.aggregator import BenchmarkAggregator
from gateway_llm.benchmarks.base import TaskCategory
from gateway_llm.benchmarks.normalizer import normalize_model_name
from gateway_llm.hardware import HardwareInfo

log = logging.getLogger(__name__)

_OLLAMA_CATALOG = pathlib.Path("benchmarks_cache/ollama_library.json")
_RUNTIME_FACTOR = 1.3


@dataclass
class OllamaModelInfo:
    name: str
    tag: str
    full_name: str
    size_gb: float
    param_count_b: float | None
    quantization: str | None
    capabilities: list[str]


def load_ollama_catalog(path: pathlib.Path | None = None) -> list[OllamaModelInfo]:
    """Charge le catalogue depuis le cache local.

    Structure attendue (produite par refresh_ollama_library.py) :
    {
      "last_updated": "2026-11-07",
      "models": [
        {"name": "qwen3.8", "capabilities": ["tools","thinking"],
         "tags": [{"tag": "27b-q4_K_M", "size_gb": 18.2,
                   "param_count_b": 27.3, "quantization": "Q4_K_M"}, ...]},
        ...
      ]
    }
    """
    p = path or _OLLAMA_CATALOG
    if not p.exists():
        log.warning(
            "Catalogue Ollama absent (%s). Lancez scripts/refresh_ollama_library.py",
            p,
        )
        return []

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Lecture catalogue Ollama échouée : %s", e)
        return []

    models: list[OllamaModelInfo] = []
    for entry in data.get("models", []):
        name = entry.get("name")
        caps = entry.get("capabilities", [])
        for tag_info in entry.get("tags", []):
            size = tag_info.get("size_gb")
            if not name or size is None:
                continue
            tag = tag_info["tag"]
            models.append(
                OllamaModelInfo(
                    name=name,
                    tag=tag,
                    full_name=f"{name}:{tag}",
                    size_gb=float(size),
                    param_count_b=tag_info.get("param_count_b"),
                    quantization=tag_info.get("quantization"),
                    capabilities=caps,
                )
            )
    log.info("Catalogue Ollama : %d variantes de modèles chargées", len(models))
    return models


def select_local_models(
    benchmarks: BenchmarkAggregator,
    hardware: HardwareInfo,
    domains: list[str],
    max_per_domain: int = 2,
) -> dict[str, list[str]]:
    """Pour chaque domaine, retourne les meilleurs modèles Ollama qui tiennent.

    Algorithme :
    1. Charger le catalogue Ollama.
    2. Pour chaque domaine, récupérer les scores de benchmark.
    3. Filtrer les modèles dont la mémoire runtime dépasse la capacité.
    4. Classer par score décroissant, garder le top N.
    """
    catalog = load_ollama_catalog()
    if not catalog:
        return {}

    capacity = hardware.effective_capacity_gb()
    if capacity <= 0:
        log.warning("Capacité mémoire nulle : impossible de sélectionner")
        return {}

    log.info(
        "Sélection locale : capacité=%.1f Go (VRAM=%.1f, RAM dispo=%.1f)",
        capacity,
        hardware.vram_gb or 0,
        hardware.ram_available_gb or 0,
    )

    result: dict[str, list[str]] = {}

    for domain in domains:
        try:
            category = TaskCategory(domain)
        except ValueError:
            log.debug("Domaine '%s' sans catégorie benchmark connue", domain)
            continue

        scores = benchmarks.get_scores(category)
        if not scores:
            log.info("Aucun score benchmark pour '%s'", domain)
            continue

        candidates: list[tuple[str, float]] = []
        for m in catalog:
            # Essaie plusieurs formes de normalisation
            normalized = normalize_model_name(m.name)
            score = (
                scores.get(normalized)
                or scores.get(m.name)
                or scores.get(m.full_name)
            )
            if score is None:
                continue

            runtime_gb = m.size_gb * _RUNTIME_FACTOR
            if runtime_gb > capacity:
                log.debug(
                    "Skip %s (%.1f Go > capacité %.1f Go)",
                    m.full_name,
                    runtime_gb,
                    capacity,
                )
                continue

            candidates.append((m.full_name, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [c[0] for c in candidates[:max_per_domain]]
        if selected:
            result[domain] = selected
            log.info("Domaine %s : %s", domain, selected)

    return result