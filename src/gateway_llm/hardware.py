# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Détection matérielle : VRAM, RAM, disque, et capacité effective."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

_RUNTIME_FACTOR = 1.3  # mémoire runtime ≈ 1.3x taille fichier (KV cache inclus)


@dataclass
class FitEstimate:
    model_size_gb: float
    vram_gb: float | None
    ratio: float | None
    category: str  # excellent | good | acceptable | slow | very_slow | unknown
    note: str


class HardwareInfo:
    def __init__(
        self,
        vram_gb: float | None = None,
        ram_total_gb: float | None = None,
        ram_available_gb: float | None = None,
        disk_free_gb: float | None = None,
        source: str = "unknown",
        warn_threshold: float = 4.0,
        skip_threshold: float | None = None,
    ) -> None:
        self.vram_gb = vram_gb
        self.ram_total_gb = ram_total_gb
        self.ram_available_gb = ram_available_gb
        self.disk_free_gb = disk_free_gb
        self.source = source
        self.warn_threshold = warn_threshold
        self.skip_threshold = skip_threshold

    # ────────────────────────────────────────────────────────────
    # Capacité mémoire effective
    # ────────────────────────────────────────────────────────────
    def effective_capacity_gb(self) -> float:
        """Mémoire utilisable par Ollama (VRAM + 70% de la RAM dispo).

        Ollama offload automatiquement sur CPU/RAM quand la VRAM
        déborde. On combine VRAM + 70% de la RAM disponible (le reste
        est laissé à l'OS et aux autres processus). Si psutil est
        absent, on retombe sur la VRAM seule.
        """
        capacity = self.vram_gb or 0.0
        if self.ram_available_gb is not None:
            capacity += self.ram_available_gb * 0.7
        return capacity

    def can_run(self, model_size_gb: float) -> bool:
        """True si le modèle (avec son runtime) tient dans la capacité."""
        required = model_size_gb * _RUNTIME_FACTOR
        return required <= self.effective_capacity_gb()

    def estimate_fit(self, model_size_gb: float) -> FitEstimate:
        """Estime le confort d'exécution (basé sur effective_capacity)."""
        capacity = self.effective_capacity_gb()
        if capacity <= 0:
            return FitEstimate(
                model_size_gb=model_size_gb,
                vram_gb=self.vram_gb,
                ratio=None,
                category="unknown",
                note="Mémoire non détectée, filtrage désactivé",
            )
        ratio = (model_size_gb * _RUNTIME_FACTOR) / capacity
        if ratio <= 0.9:
            return FitEstimate(
                model_size_gb,
                self.vram_gb,
                ratio,
                "excellent",
                f"Tient en mémoire ({model_size_gb:.0f} Go ≤ {capacity:.0f} Go)",
            )
        if ratio <= 1.5:
            return FitEstimate(
                model_size_gb,
                self.vram_gb,
                ratio,
                "good",
                "Léger débordement RAM/CPU, quasi-pleine vitesse",
            )
        if ratio <= 3.0:
            return FitEstimate(
                model_size_gb,
                self.vram_gb,
                ratio,
                "acceptable",
                "Offload RAM significatif, vitesse correcte",
            )
        if ratio <= 6.0:
            return FitEstimate(
                model_size_gb,
                self.vram_gb,
                ratio,
                "slow",
                "Offload lourd, attendre un ralentissement net",
            )
        return FitEstimate(
            model_size_gb,
            self.vram_gb,
            ratio,
            "very_slow",
            "Majoritairement CPU/RAM/SSD, très lent",
        )

    def should_skip(self, model_size_gb: float) -> bool:
        if self.skip_threshold is None:
            return False
        capacity = self.effective_capacity_gb()
        if capacity <= 0:
            return False
        return (model_size_gb * _RUNTIME_FACTOR) / capacity > self.skip_threshold


# ────────────────────────────────────────────────────────────────
# Détection
# ────────────────────────────────────────────────────────────────
def _detect_vram() -> tuple[float | None, str]:
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
            if lines:
                mb = float(lines[0])
                return mb / 1024.0, "nvidia-smi"
        except Exception as e:
            log.warning("nvidia-smi failed: %s", e)

    if shutil.which("rocm-smi"):
        try:
            out = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            m = re.search(r'"VRAM Total Memory \(B\)":\s*(\d+)', out.stdout)
            if m:
                return float(m.group(1)) / (1024**3), "rocm-smi"
        except Exception as e:
            log.warning("rocm-smi failed: %s", e)

    log.info("VRAM non détectée : filtrage hardware partiel")
    return None, "unknown"


def detect_hardware(disk_path: str = ".") -> HardwareInfo:
    """Détecte VRAM, RAM totale/dispo, et espace disque libre."""
    vram_gb, source = _detect_vram()

    ram_total = ram_available = None
    disk_free = None

    if psutil is not None:
        try:
            mem = psutil.virtual_memory()
            ram_total = mem.total / (1024**3)
            ram_available = mem.available / (1024**3)
        except Exception as e:
            log.warning("psutil.virtual_memory failed: %s", e)
    else:
        log.warning("psutil non installé : RAM non détectée")

    try:
        disk_free = shutil.disk_usage(disk_path).free / (1024**3)
    except Exception as e:
        log.warning("Impossible de lire l'espace disque (%s): %s", disk_path, e)

    log.info(
        "Hardware : VRAM=%.1f Go, RAM dispo=%.1f/%.1f Go, disque libre=%.1f Go",
        vram_gb or 0,
        ram_available or 0,
        ram_total or 0,
        disk_free or 0,
    )

    return HardwareInfo(
        vram_gb=vram_gb,
        ram_total_gb=ram_total,
        ram_available_gb=ram_available,
        disk_free_gb=disk_free,
        source=source,
    )


# Rétrocompatibilité avec l'ancien nom
detect_vram = lambda: detect_hardware()  # noqa: E731
