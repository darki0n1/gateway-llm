# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Reprise d'un batch après interruption.

Principe : le runner écrit chaque résultat en JSONL (append + flush).
Au démarrage, on lit ce fichier pour connaître les IDs déjà traités,
et on skip ces IDs dans l'entrée.
"""

from __future__ import annotations

import json
import logging
import pathlib

log = logging.getLogger(__name__)


class Checkpoint:
    def __init__(self, output_path: pathlib.Path) -> None:
        self._path = output_path
        self._done: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                task_id = obj.get("id")
                if task_id:
                    self._done.add(task_id)
        log.info("Checkpoint: %d tâches déjà traitées", len(self._done))

    def is_done(self, task_id: str) -> bool:
        return task_id in self._done

    def append(self, result: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            import os

            os.fsync(f.fileno())
        self._done.add(result["id"])

    @property
    def done_count(self) -> int:
        return len(self._done)
