# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Téléchargement des modèles Ollama manquants + gestion du daemon.

Appelé par `gateway-llm setup` et par le pre-flight de `batch run`.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

import requests

log = logging.getLogger(__name__)


def ensure_ollama_daemon(ollama_url: str = "http://localhost:11434") -> bool:
    """Vérifie que le daemon Ollama répond. Le lance sinon.

    Retourne True si le daemon est joignable après l'opération.
    Si `ollama` n'est pas installé, log un message clair et retourne False.
    """
    # 1) Test direct
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=2)
        if r.status_code == 200:
            log.info("Daemon Ollama opérationnel")
            return True
    except requests.exceptions.RequestException:
        pass

    # 2) Binaire présent ?
    if not shutil.which("ollama"):
        log.error(
            "Ollama introuvable dans le PATH. Téléchargez-le depuis "
            "https://ollama.com/download puis relancez."
        )
        return False

    # 3) Lancement en arrière-plan (jamais de shell=True)
    log.info("Daemon Ollama injoignable, tentative de démarrage…")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        log.error("Impossible de lancer 'ollama serve' : %s", e)
        return False

    # 4) Attente : 20 tentatives de 1s
    for attempt in range(20):
        time.sleep(1)
        try:
            r = requests.get(f"{ollama_url}/api/tags", timeout=2)
            if r.status_code == 200:
                log.info("Daemon Ollama démarré (après %ds)", attempt + 1)
                return True
        except requests.exceptions.RequestException:
            continue

    log.error("Le daemon Ollama n'a pas démarré après 20s")
    return False


class Installer:
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        interactive: bool = True,
        assume_yes: bool = False,
    ) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._interactive = interactive
        self._assume_yes = assume_yes

    def _ask(self, question: str) -> bool:
        if self._assume_yes:
            return True
        if not self._interactive:
            return False
        try:
            return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def pull_model(self, name: str) -> bool:
        if not shutil.which("ollama"):
            log.error("Ollama introuvable. Installer depuis https://ollama.com/download")
            return False

        if not self._ask(f"Télécharger le modèle '{name}' ?"):
            log.info("Skip : %s", name)
            return False

        log.info("Téléchargement de %s…", name)
        try:
            proc = subprocess.Popen(
                ["ollama", "pull", name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if proc.stdout:
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        print(f"  {line}")
            proc.wait(timeout=3600)
            if proc.returncode != 0:
                log.error("Échec ollama pull %s (code %d)", name, proc.returncode)
                return False
        except Exception as e:
            log.error("Erreur pull %s: %s", name, e)
            return False

        # Confirme que le modèle est listé
        try:
            r = requests.get(f"{self._ollama_url}/api/tags", timeout=5)
            if r.status_code == 200:
                names = {m["name"] for m in r.json().get("models", [])}
                if name in names:
                    log.info("✓ %s installé", name)
                    return True
        except Exception:
            pass
        log.warning("Modèle %s non confirmé après pull", name)
        return False

    def ensure_models(self, required: list[str]) -> int:
        # Daemon d'abord : sinon /api/tags échoue systématiquement
        if not ensure_ollama_daemon(self._ollama_url):
            log.error("Daemon Ollama indisponible, impossible d'installer les modèles")
            return 0

        try:
            r = requests.get(f"{self._ollama_url}/api/tags", timeout=5)
            r.raise_for_status()
            installed = {m["name"] for m in r.json().get("models", [])}
        except Exception as e:
            log.error("Impossible de lister les modèles Ollama : %s", e)
            return 0

        missing = [m for m in required if m not in installed]
        if not missing:
            log.info("Tous les modèles requis sont déjà installés")
            return 0

        log.info("%d modèle(s) manquant(s) : %s", len(missing), ", ".join(missing))
        count = 0
        for name in missing:
            if self.pull_model(name):
                count += 1
        return count