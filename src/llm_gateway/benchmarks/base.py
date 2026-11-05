# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Classes de base pour les sources de benchmarks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class TaskCategory(str, Enum):
    """Catégories de tâches que le routeur sait gérer."""
    CODE_DEBUG = "code_debug"
    THINKING = "thinking"
    PROBLEM_SOLVING = "problem_solving"
    TRANSLATION = "translation"
    FACT_CHECKING = "fact_checking"
    SAFETY = "safety"
    RED_TEAMING = "red_teaming"
    PROMPT_CREATION = "prompt_creation"
    MULTIMODAL_EXTRACTION = "multimodal_extraction"


@dataclass
class BenchmarkResult:
    """Score d'un modèle dans une catégorie donnée."""
    model_key: str            # nom normalisé
    category: TaskCategory
    score: float              # 0-100 (ou 0-5 pour RWS, normalisé)
    source: str               # "benchlm", "rankllms", "f5", "rws"
    raw_name: str = ""        # nom original dans la source


class BenchmarkSource(ABC):
    """Une source de benchmarks interrogeable."""

    name: str

    @abstractmethod
    def fetch(self, category: TaskCategory) -> list[BenchmarkResult]:
        """Retourne les scores pour une catégorie donnée."""
        ...

    @abstractmethod
    def supports(self, category: TaskCategory) -> bool:
        """Indique si cette source couvre la catégorie."""
        ...