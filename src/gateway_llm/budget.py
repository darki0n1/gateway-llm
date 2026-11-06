# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Suivi de budget par batch (euros ou tokens).

Permet d'arrêter proprement une cascade si le coût cumulé dépasse
un plafond. Utilisé par le Router (par appel) et le BatchRunner
(par tâche).

Thread-safe via Lock, instanciable, pas d'état global.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class BudgetSnapshot:
    spent_eur: float
    max_eur: float | None
    calls: int
    exceeded: bool

    @property
    def remaining_eur(self) -> float | None:
        if self.max_eur is None:
            return None
        return max(0.0, self.max_eur - self.spent_eur)


class BudgetTracker:
    """Compteur de coût cumulé avec plafond optionnel."""

    def __init__(self, max_eur: float | None = None) -> None:
        self._max = max_eur
        self._spent = 0.0
        self._calls = 0
        self._lock = threading.Lock()

    def record(self, cost_eur: float) -> None:
        with self._lock:
            self._spent += max(0.0, cost_eur)
            self._calls += 1
        if self._max is not None and self._spent > self._max:
            log.warning(
                "Budget dépassé : %.4f € > %.4f €", self._spent, self._max,
            )

    def can_escalate(self, estimated_next_cost: float = 0.0) -> bool:
        """Vérifie si un nouvel appel ferait dépasser le budget."""
        if self._max is None:
            return True
        with self._lock:
            return (self._spent + max(0.0, estimated_next_cost)) <= self._max

    def exceeded(self) -> bool:
        if self._max is None:
            return False
        with self._lock:
            return self._spent > self._max

    def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return BudgetSnapshot(
                spent_eur=self._spent,
                max_eur=self._max,
                calls=self._calls,
                exceeded=(
                    self._max is not None and self._spent > self._max
                ),
            )

    def reset(self) -> None:
        with self._lock:
            self._spent = 0.0
            self._calls = 0