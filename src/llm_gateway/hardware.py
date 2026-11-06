# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Estimation du confort d'exécution d'un modèle local.

Philosophie : Ollama offload intelligemment sur RAM/CPU/SSD, et sur un
laptop récent c'est souvent très utilisable au-delà du seul fit VRAM.
On NE SKIPPE PAS par défaut : on classe en catégories et on log.
Le seuil de skip reste optionnel pour les cas extrêmes.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class FitEstimate:
    model_size_gb: float
    vram_gb: float | None
    ratio: float | None
    category: str          # excellent | good | acceptable | slow | very_slow | unknown
    note: str


class HardwareInfo:
    def __init__(
        self,
        vram_gb: float | None,
        source: str,
        warn_threshold: float = 4.0,
        skip_threshold: float | None = None,
    ) -> None:
        self.vram_gb = vram_gb
        self.source = source
        self.warn_threshold = warn_threshold
        self.skip_threshold = skip_threshold

    def estimate_fit(self, model_size_gb: float) -> FitEstimate:
        if self.vram_gb is None or self.vram_gb <= 0:
            return FitEstimate(
                model_size_gb=model_size_gb, vram_gb=None, ratio=None,
                category="unknown", note="VRAM non détectée, filtrage désactivé",
            )
        ratio = model_size_gb / self.vram_gb
        if ratio <= 0.9:
            return FitEstimate(
                model_size_gb, self.vram_gb, ratio, "excellent",
                f"Tient en VRAM ({model_size_gb:.0f} Go ≤ {self.vram_gb:.0f} Go)",
            )
        if ratio <= 1.5:
            return FitEstimate(
                model_size_gb, self.vram_gb, ratio, "good",
                "Léger débordement RAM/CPU, quasi-pleine vitesse",
            )
        if ratio <= 3.0:
            return FitEstimate(
                model_size_gb, self.vram_gb, ratio, "acceptable",
                "Offload RAM significatif, vitesse correcte",
            )
        if ratio <= 6.0:
            return FitEstimate(
                model_size_gb, self.vram_gb, ratio, "slow",
                "Offload lourd, attendre un ralentissement net",
            )
        return FitEstimate(
            model_size_gb, self.vram_gb, ratio, "very_slow",
            "Majoritairement CPU/RAM/SSD, très lent",
        )

    def should_skip(self, model_size_gb: float) -> bool:
        """Skip uniquement si l'utilisateur a explicitement fixé un seuil."""
        if self.skip_threshold is None or self.vram_gb is None:
            return False
        return (model_size_gb / self.vram_gb) > self.skip_threshold


def detect_vram() -> HardwareInfo:
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in out.stdout.splitlines() if l.strip()]
            if lines:
                mb = float(lines[0])
                return HardwareInfo(vram_gb=mb / 1024.0, source="nvidia-smi")
        except Exception as e:
            log.warning("nvidia-smi failed: %s", e)

    if shutil.which("rocm-smi"):
        try:
            out = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(r'"VRAM Total Memory \(B\)":\s*(\d+)', out.stdout)
            if m:
                return HardwareInfo(
                    vram_gb=float(m.group(1)) / (1024**3), source="rocm-smi",
                )
        except Exception as e:
            log.warning("rocm-smi failed: %s", e)

    log.info("VRAM non détectée : filtrage hardware désactivé")
    return HardwareInfo(vram_gb=None, source="unknown")