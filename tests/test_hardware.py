# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests du module hardware (VRAM, RAM, disque, capacité effective, fit)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gateway_llm.hardware import (
    _RUNTIME_FACTOR,
    HardwareInfo,
    _detect_vram,
    detect_hardware,
    detect_vram,
)


# ─── Constante de runtime ──────────────────────────────────────
def test_runtime_factor_constant():
    """La constante 1.3 (overhead runtime KV cache) ne doit pas bouger."""
    assert _RUNTIME_FACTOR == 1.3


# ─── effective_capacity_gb ─────────────────────────────────────
def test_capacity_vram_only():
    hw = HardwareInfo(vram_gb=8.0, source="test")
    assert hw.effective_capacity_gb() == pytest.approx(8.0)


def test_capacity_vram_plus_ram():
    hw = HardwareInfo(vram_gb=8.0, ram_available_gb=16.0, source="test")
    # 8 + 16 * 0.7 = 19.2
    assert hw.effective_capacity_gb() == pytest.approx(19.2)


def test_capacity_ram_only():
    hw = HardwareInfo(ram_available_gb=10.0, source="test")
    # 0 + 10 * 0.7 = 7.0
    assert hw.effective_capacity_gb() == pytest.approx(7.0)


def test_capacity_nothing():
    hw = HardwareInfo(source="test")
    assert hw.effective_capacity_gb() == 0.0


# ─── can_run (facteur 1.3) ─────────────────────────────────────
def test_can_run_uses_runtime_factor():
    hw = HardwareInfo(vram_gb=10.0, source="test")
    # 6 * 1.3 = 7.8 <= 10
    assert hw.can_run(6.0) is True
    # 8 * 1.3 = 10.4 > 10
    assert hw.can_run(8.0) is False


def test_can_run_exactly_at_limit():
    hw = HardwareInfo(vram_gb=13.0, source="test")
    # 10 * 1.3 = 13.0 <= 13.0 (cas limite)
    assert hw.can_run(10.0) is True


# ─── estimate_fit : toutes les catégories ──────────────────────
def test_fit_excellent():
    hw = HardwareInfo(vram_gb=10.0, source="test")
    fit = hw.estimate_fit(5.0)  # ratio = 5*1.3/10 = 0.65
    assert fit.category == "excellent"
    assert fit.ratio == pytest.approx(0.65)
    assert fit.model_size_gb == 5.0


def test_fit_good():
    hw = HardwareInfo(vram_gb=10.0, source="test")
    fit = hw.estimate_fit(8.0)  # ratio = 1.04
    assert fit.category == "good"


def test_fit_acceptable():
    hw = HardwareInfo(vram_gb=10.0, source="test")
    fit = hw.estimate_fit(15.0)  # ratio = 1.95
    assert fit.category == "acceptable"


def test_fit_slow():
    hw = HardwareInfo(vram_gb=10.0, source="test")
    fit = hw.estimate_fit(30.0)  # ratio = 3.9
    assert fit.category == "slow"


def test_fit_very_slow():
    hw = HardwareInfo(vram_gb=10.0, source="test")
    fit = hw.estimate_fit(100.0)  # ratio = 13.0
    assert fit.category == "very_slow"


def test_fit_unknown_when_capacity_zero():
    hw = HardwareInfo(source="test")
    fit = hw.estimate_fit(10.0)
    assert fit.category == "unknown"
    assert fit.ratio is None


# ─── should_skip ───────────────────────────────────────────────
def test_should_skip_no_threshold():
    hw = HardwareInfo(vram_gb=8.0, source="test", skip_threshold=None)
    assert hw.should_skip(100.0) is False


def test_should_skip_below_threshold():
    hw = HardwareInfo(vram_gb=10.0, source="test", skip_threshold=5.0)
    # 20*1.3/10 = 2.6 < 5 → pas de skip
    assert hw.should_skip(20.0) is False


def test_should_skip_above_threshold():
    hw = HardwareInfo(vram_gb=10.0, source="test", skip_threshold=5.0)
    # 100*1.3/10 = 13 > 5 → skip
    assert hw.should_skip(100.0) is True


def test_should_skip_zero_capacity_is_safe():
    """Capacité inconnue → on ne skip pas (fail-open)."""
    hw = HardwareInfo(source="test", skip_threshold=5.0)
    assert hw.should_skip(100.0) is False


# ─── _detect_vram (mocké) ──────────────────────────────────────
@patch("gateway_llm.hardware.subprocess.run")
@patch("gateway_llm.hardware.shutil.which")
def test_detect_vram_nvidia(mock_which, mock_run):
    mock_which.side_effect = lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None
    mock_run.return_value = MagicMock(stdout="8192\n", returncode=0)
    vram_gb, source = _detect_vram()
    assert vram_gb == pytest.approx(8.0)
    assert source == "nvidia-smi"


@patch("gateway_llm.hardware.subprocess.run")
@patch("gateway_llm.hardware.shutil.which")
def test_detect_vram_rocm(mock_which, mock_run):
    mock_which.side_effect = lambda name: "/opt/rocm/bin/rocm-smi" if name == "rocm-smi" else None
    # 8 Go en bytes
    mock_run.return_value = MagicMock(
        stdout='{"card0": {"VRAM Total Memory (B)": "8589934592"}}',
        returncode=0,
    )
    vram_gb, source = _detect_vram()
    assert vram_gb == pytest.approx(8.0)
    assert source == "rocm-smi"


@patch("gateway_llm.hardware.shutil.which", return_value=None)
def test_detect_vram_no_gpu(_mock_which):
    vram_gb, source = _detect_vram()
    assert vram_gb is None
    assert source == "unknown"


# ─── detect_hardware() : orchestration ─────────────────────────
@patch("gateway_llm.hardware.shutil.disk_usage")
@patch("gateway_llm.hardware.psutil")
@patch("gateway_llm.hardware.shutil.which", return_value=None)
def test_detect_hardware_full(mock_which, mock_psutil, mock_disk_usage):
    mock_psutil.virtual_memory.return_value = MagicMock(
        total=32 * 1024**3,
        available=16 * 1024**3,
    )
    mock_disk_usage.return_value = MagicMock(free=500 * 1024**3)
    hw = detect_hardware()
    assert hw.vram_gb is None
    assert hw.ram_total_gb == pytest.approx(32.0)
    assert hw.ram_available_gb == pytest.approx(16.0)
    assert hw.disk_free_gb == pytest.approx(500.0)
    assert hw.source == "unknown"


# ─── Alias rétrocompatibilité ──────────────────────────────────
def test_detect_vram_alias(monkeypatch):
    """detect_vram() est un alias de detect_hardware()."""
    fake = HardwareInfo(vram_gb=4.0, source="test")
    monkeypatch.setattr("gateway_llm.hardware.detect_hardware", lambda: fake)
    assert detect_vram() is fake
