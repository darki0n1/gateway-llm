# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Tests du BudgetTracker."""

from __future__ import annotations

from llm_gateway.budget import BudgetSnapshot, BudgetTracker


# ─── Sans plafond ──────────────────────────────────────────────
def test_no_max_never_exceeded():
    b = BudgetTracker(max_eur=None)
    assert not b.exceeded()
    for _ in range(10):
        b.record(100.0)
    assert not b.exceeded()
    assert b.snapshot().max_eur is None


def test_no_max_can_always_escalate():
    b = BudgetTracker(max_eur=None)
    b.record(1_000_000.0)
    assert b.can_escalate(999.0)


# ─── Avec plafond ──────────────────────────────────────────────
def test_record_cumulates():
    b = BudgetTracker(max_eur=10.0)
    b.record(2.5)
    b.record(3.0)
    snap = b.snapshot()
    assert snap.spent_eur == 5.5
    assert snap.calls == 2
    assert not snap.exceeded


def test_exceeded_after_plafond():
    b = BudgetTracker(max_eur=1.0)
    b.record(1.5)
    assert b.exceeded()
    assert b.snapshot().exceeded


def test_exactly_at_plafond_not_exceeded():
    b = BudgetTracker(max_eur=1.0)
    b.record(1.0)
    # Le code fait `> max`, donc égal n'est pas "exceeded"
    assert not b.exceeded()


def test_remaining_eur():
    b = BudgetTracker(max_eur=10.0)
    b.record(3.0)
    assert b.snapshot().remaining_eur == 7.0
    b.record(8.0)
    assert b.snapshot().remaining_eur == 0.0   # jamais négatif


def test_can_escalate_within_budget():
    b = BudgetTracker(max_eur=10.0)
    b.record(5.0)
    assert b.can_escalate(2.0)      # 5+2=7 <= 10
    assert b.can_escalate(5.0)      # 5+5=10 <= 10
    assert not b.can_escalate(5.1)  # 5+5.1=10.1 > 10


def test_negative_cost_ignored():
    b = BudgetTracker(max_eur=10.0)
    b.record(-5.0)   # ignoré (max(0, ...))
    assert b.snapshot().spent_eur == 0.0


def test_reset():
    b = BudgetTracker(max_eur=10.0)
    b.record(5.0)
    b.reset()
    snap = b.snapshot()
    assert snap.spent_eur == 0.0
    assert snap.calls == 0
    assert not snap.exceeded


# ─── BudgetSnapshot ────────────────────────────────────────────
def test_snapshot_dataclass():
    snap = BudgetSnapshot(spent_eur=3.0, max_eur=10.0, calls=2, exceeded=False)
    assert snap.remaining_eur == 7.0
    snap_none = BudgetSnapshot(spent_eur=3.0, max_eur=None, calls=2, exceeded=False)
    assert snap_none.remaining_eur is None


# ─── Thread safety (basique) ───────────────────────────────────
def test_thread_safety_concurrent_records():
    import threading
    b = BudgetTracker(max_eur=None)
    def worker():
        for _ in range(1000):
            b.record(0.001)
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = b.snapshot()
    assert snap.calls == 4000
    assert abs(snap.spent_eur - 4.0) < 1e-6