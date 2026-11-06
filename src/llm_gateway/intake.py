# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Convertisseur de données hétérogènes en JSONL de tâches.

Transforme un dossier d'images, de fichiers texte, un CSV, ou une liste
d'URLs en fichier JSONL prêt à traiter par `BatchRunner`.

Aucune donnée n'est modifiée, seulement convertie.
"""

from __future__ import annotations

import csv
import json
import logging
import pathlib
import time
from dataclasses import asdict, dataclass, field
from typing import Iterable

import requests

log = logging.getLogger(__name__)


@dataclass
class IntakeTask:
    id: str
    prompt: str = ""
    task_text: str = ""
    domain: str | None = None
    sensitivity: str = "public"
    description: str = ""
    image_path: str | None = None
    source: str = ""

    def to_record(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


def _write_jsonl(tasks: Iterable[IntakeTask], output: pathlib.Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t.to_record(), ensure_ascii=False) + "\n")
            count += 1
    log.info("Écrit %d tâches dans %s", count, output)
    return count


# ─── Images ───────────────────────────────────────────────────
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def intake_from_folder(
    folder: pathlib.Path,
    output: pathlib.Path,
    prompt_template: str = "Analyse cette image et décris ce que tu vois.",
    domain: str = "multimodal_extraction",
    sensitivity: str = "public",
) -> int:
    """Une tâche par image dans `folder` (récursif)."""
    if not folder.exists():
        raise FileNotFoundError(f"Dossier introuvable : {folder}")
    tasks = []
    for i, p in enumerate(sorted(folder.rglob("*"))):
        if p.suffix.lower() not in _IMAGE_EXTS:
            continue
        tasks.append(IntakeTask(
            id=f"img-{i:04d}",
            prompt=prompt_template,
            task_text=prompt_template,
            domain=domain,
            sensitivity=sensitivity,
            image_path=str(p.resolve()),
            source=str(p.name),
        ))
    return _write_jsonl(tasks, output)


# ─── Fichiers texte ───────────────────────────────────────────
_TEXT_EXTS = {".txt", ".md", ".html", ".htm", ".eml"}


def intake_from_text(
    folder: pathlib.Path,
    output: pathlib.Path,
    prompt_template: str = "Traite le contenu suivant :\n\n{content}",
    domain: str | None = None,
    sensitivity: str = "public",
) -> int:
    """Une tâche par fichier texte dans `folder` (récursif)."""
    if not folder.exists():
        raise FileNotFoundError(f"Dossier introuvable : {folder}")
    tasks = []
    for i, p in enumerate(sorted(folder.rglob("*"))):
        if p.suffix.lower() not in _TEXT_EXTS:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            log.warning("Lecture échouée pour %s: %s", p, e)
            continue
        prompt = prompt_template.format(content=content[:8000])
        tasks.append(IntakeTask(
            id=f"txt-{i:04d}",
            prompt=prompt,
            task_text=prompt,
            domain=domain,
            sensitivity=sensitivity,
            source=str(p.name),
        ))
    return _write_jsonl(tasks, output)


# ─── CSV ──────────────────────────────────────────────────────
def intake_from_csv(
    csv_path: pathlib.Path,
    output: pathlib.Path,
    column: str,
    id_column: str | None = None,
    prompt_template: str = "{content}",
    domain: str | None = None,
    sensitivity: str = "public",
) -> int:
    """Une tâche par ligne du CSV, utilisant `column` comme contenu."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV introuvable : {csv_path}")
    tasks = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            raise ValueError(
                f"Colonne '{column}' absente. Disponibles : {reader.fieldnames}"
            )
        for i, row in enumerate(reader):
            content = (row.get(column) or "").strip()
            if not content:
                continue
            task_id = row.get(id_column, f"csv-{i:04d}") if id_column else f"csv-{i:04d}"
            prompt = prompt_template.format(content=content)
            tasks.append(IntakeTask(
                id=task_id,
                prompt=prompt,
                task_text=prompt,
                domain=domain,
                sensitivity=sensitivity,
                source=f"{csv_path.name}:{i}",
            ))
    return _write_jsonl(tasks, output)


# ─── URLs (avec garde-fous éthiques) ──────────────────────────
def _check_robots(url: str) -> bool:
    """Vérifie si le path est autorisé par robots.txt. Fail-open si indisponible."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        r = requests.get(robots_url, timeout=5)
        if r.status_code != 200:
            return True
        for line in r.text.splitlines():
            if line.strip().lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path and path in parsed.path:
                    return False
        return True
    except Exception:
        return True   # fail-open : on laisse l'utilisateur décider


def intake_from_urls(
    urls_file: pathlib.Path,
    output: pathlib.Path,
    prompt_template: str = "Résume la page suivante :\n\n{content}",
    domain: str | None = None,
    sensitivity: str = "public",
    respect_robots: bool = True,
    delay_seconds: float = 1.0,
) -> int:
    """Une tâche par URL, en téléchargeant le contenu.

    ATTENTION : ne pas utiliser pour scraper massivement des sites tiers.
    Respecter robots.txt (activé par défaut) et les conditions d'utilisation.
    """
    if not urls_file.exists():
        raise FileNotFoundError(f"Fichier URLs introuvable : {urls_file}")

    urls = [
        line.strip() for line in urls_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    tasks = []
    headers = {"User-Agent": "llm-gateway-intake/0.1 (+https://github.com/<vous>/llm-gateway)"}
    for i, url in enumerate(urls):
        if respect_robots and not _check_robots(url):
            log.warning("robots.txt interdit %s, skip", url)
            continue
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            # Extraction basique du texte
            try:
                from bs4 import BeautifulSoup
                text = BeautifulSoup(r.text, "html.parser").get_text(separator="\n")
            except ImportError:
                text = r.text
            prompt = prompt_template.format(content=text[:8000])
            tasks.append(IntakeTask(
                id=f"url-{i:04d}",
                prompt=prompt,
                task_text=prompt,
                domain=domain,
                sensitivity=sensitivity,
                source=url,
            ))
            time.sleep(delay_seconds)
        except Exception as e:
            log.warning("Échec fetch %s: %s", url, e)
    return _write_jsonl(tasks, output)