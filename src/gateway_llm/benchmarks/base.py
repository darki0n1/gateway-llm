# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Classes de base pour les sources de benchmarks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class TaskCategory(StrEnum):
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
    model_key: str
    category: TaskCategory
    score: float
    source: str
    raw_name: str = ""
    # ── Champs enrichis pour la sélection locale ──
    size_gb: float | None = None
    runtime_memory_gb: float | None = None
    quantization: str | None = None
    param_count_b: float | None = None


class BenchmarkSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, category: TaskCategory) -> list[BenchmarkResult]: ...

    @abstractmethod
    def supports(self, category: TaskCategory) -> bool: ...
