# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Tests de BatchRunner (progress callback, annulation, checkpoint)."""

from __future__ import annotations

import json
import pathlib
import threading
from unittest.mock import patch

from gateway_llm.batch import BatchRunner
from gateway_llm.config import LocalMode
from gateway_llm.secrets import EnvSecretBackend

from .helpers import FakeProvider, make_response


def _make_input(tmp_path: pathlib.Path, tasks: list[dict]) -> pathlib.Path:
    input_file = tmp_path / "input.jsonl"
    with input_file.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return input_file


def _make_runner(
    tmp_path: pathlib.Path,
    input_file: pathlib.Path,
    minimal_config,
    provider: FakeProvider,
    progress_callback=None,
) -> tuple[BatchRunner, pathlib.Path]:
    output_file = tmp_path / "output.jsonl"
    runner = BatchRunner(
        config=minimal_config,
        input_path=input_file,
        output_path=output_file,
        secrets=EnvSecretBackend(),
        progress_callback=progress_callback,
    )
    # On mocke les étapes externes (réseau, hardware, ollama)
    runner._build_providers = lambda: {"fake": provider}  # type: ignore[method-assign]
    runner._maybe_refresh_benchmarks = lambda: None  # type: ignore[method-assign]
    runner._apply_local_mode = lambda b, m: None  # type: ignore[method-assign]
    return runner, output_file


# ─── progress_callback ─────────────────────────────────────────
def test_progress_callback_called_per_task(tmp_path, minimal_config):
    """Le callback est appelé une fois par tâche avec (current, total, speed)."""
    tasks = [
        {"id": f"t{i}", "domain": "generation", "task_text": "hello"}
        for i in range(3)
    ]
    input_file = _make_input(tmp_path, tasks)
    provider = FakeProvider("fake", [make_response("ok") for _ in range(3)])

    calls: list[tuple[int, int, float]] = []

    def cb(current: int, total: int, speed: float) -> None:
        calls.append((current, total, speed))

    runner, _ = _make_runner(
        tmp_path, input_file, minimal_config, provider, progress_callback=cb
    )

    with patch("gateway_llm.batch.load_local_mode", return_value=LocalMode.DEFAULT):
        runner._run_real()

    assert len(calls) == 3
    for current, total, speed in calls:
        assert total == 3
        assert 1 <= current <= 3
        assert speed >= 0.0
    assert calls[-1][0] == 3


def test_no_progress_callback_does_not_crash(tmp_path, minimal_config):
    """Sans progress_callback, le batch tourne normalement."""
    tasks = [{"id": "t0", "domain": "generation", "task_text": "hello"}]
    input_file = _make_input(tmp_path, tasks)
    provider = FakeProvider("fake", [make_response("ok")])

    runner, output_file = _make_runner(
        tmp_path, input_file, minimal_config, provider, progress_callback=None
    )

    with patch("gateway_llm.batch.load_local_mode", return_value=LocalMode.DEFAULT):
        stats = runner._run_real()

    assert stats.processed == 1
    assert output_file.exists()


# ─── Annulation ────────────────────────────────────────────────
def test_cancel_event_stops_loop(tmp_path, minimal_config):
    """Si _cancel_event est set, la boucle s'arrête au premier tour."""
    tasks = [
        {"id": f"t{i}", "domain": "generation", "task_text": "hello"}
        for i in range(5)
    ]
    input_file = _make_input(tmp_path, tasks)
    provider = FakeProvider("fake", [make_response("ok") for _ in range(5)])

    runner, _ = _make_runner(
        tmp_path, input_file, minimal_config, provider, progress_callback=None
    )

    runner._cancel_event = threading.Event()
    runner._cancel_event.set()

    with patch("gateway_llm.batch.load_local_mode", return_value=LocalMode.DEFAULT):
        stats = runner._run_real()

    assert stats.processed == 0
    assert provider.call_count == 0


def test_cancel_event_partial_processing(tmp_path, minimal_config):
    """Si l'event est set après 2 tâches, seules 2 sont traitées."""
    tasks = [
        {"id": f"t{i}", "domain": "generation", "task_text": "hello"}
        for i in range(5)
    ]
    input_file = _make_input(tmp_path, tasks)
    provider = FakeProvider("fake", [make_response("ok") for _ in range(5)])

    cancel_event = threading.Event()
    call_count = {"n": 0}

    def cb(current: int, total: int, speed: float) -> None:
        call_count["n"] += 1
        if call_count["n"] >= 2:
            cancel_event.set()

    runner, _ = _make_runner(
        tmp_path, input_file, minimal_config, provider, progress_callback=cb
    )
    runner._cancel_event = cancel_event

    with patch("gateway_llm.batch.load_local_mode", return_value=LocalMode.DEFAULT):
        stats = runner._run_real()

    assert stats.processed == 2
    assert provider.call_count == 2


# ─── Resume / checkpoint ───────────────────────────────────────
def test_resume_skips_already_done(tmp_path, minimal_config):
    """Avec resume=True, les IDs déjà présents dans l'output sont sautés."""
    tasks = [
        {"id": "t0", "domain": "generation", "task_text": "hello"},
        {"id": "t1", "domain": "generation", "task_text": "hello"},
    ]
    input_file = _make_input(tmp_path, tasks)

    output_file = tmp_path / "output.jsonl"
    output_file.write_text(
        json.dumps({"id": "t0", "status": "approved", "response": "ok"}) + "\n",
        encoding="utf-8",
    )

    provider = FakeProvider("fake", [make_response("ok")])
    runner = BatchRunner(
        config=minimal_config,
        input_path=input_file,
        output_path=output_file,
        secrets=EnvSecretBackend(),
        resume=True,
    )
    runner._build_providers = lambda: {"fake": provider}  # type: ignore[method-assign]
    runner._maybe_refresh_benchmarks = lambda: None  # type: ignore[method-assign]
    runner._apply_local_mode = lambda b, m: None  # type: ignore[method-assign]

    with patch("gateway_llm.batch.load_local_mode", return_value=LocalMode.DEFAULT):
        stats = runner._run_real()

    assert stats.processed == 1
    assert provider.call_count == 1


# ─── Dry-run ───────────────────────────────────────────────────
def test_dry_run_does_not_call_providers(tmp_path, minimal_config):
    """En dry-run, aucun provider n'est appelé."""
    tasks = [
        {"id": f"t{i}", "domain": "generation", "task_text": "hello"}
        for i in range(3)
    ]
    input_file = _make_input(tmp_path, tasks)
    provider = FakeProvider("fake", [])

    output_file = tmp_path / "output.jsonl"
    runner = BatchRunner(
        config=minimal_config,
        input_path=input_file,
        output_path=output_file,
        secrets=EnvSecretBackend(),
        dry_run=True,
    )

    stats = runner.run()

    assert stats.total == 3
    assert provider.call_count == 0
    assert not output_file.exists()