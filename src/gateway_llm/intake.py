# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Convertisseur de données hétérogènes en JSONL de tâches."""

from __future__ import annotations

import csv
import json
import logging
import pathlib
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

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
    if not folder.exists():
        raise FileNotFoundError(f"Dossier introuvable : {folder}")
    tasks = []
    for i, p in enumerate(sorted(folder.rglob("*"))):
        if p.suffix.lower() not in _IMAGE_EXTS:
            continue
        tasks.append(
            IntakeTask(
                id=f"img-{i:04d}",
                prompt=prompt_template,
                task_text=prompt_template,
                domain=domain,
                sensitivity=sensitivity,
                image_path=str(p.resolve()),
                source=str(p.name),
            )
        )
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
        tasks.append(
            IntakeTask(
                id=f"txt-{i:04d}",
                prompt=prompt,
                task_text=prompt,
                domain=domain,
                sensitivity=sensitivity,
                source=str(p.name),
            )
        )
    return _write_jsonl(tasks, output)


# ─── CSV — toutes les colonnes ────────────────────────────────
def _format_table(rows: list[dict], fieldnames: Sequence[str]) -> str:
    """Formate un lot de lignes en pseudo-JSON compact."""
    lines = []
    for i, row in enumerate(rows, 1):
        pairs = ", ".join(
            f"{k}: {v}" for k, v in row.items() if k in fieldnames
        )
        lines.append(f"Ligne {i}: {{{pairs}}}")
    return "\n".join(lines)


def intake_from_csv(
    csv_path: pathlib.Path,
    output: pathlib.Path,
    prompt_template: str = "{table}",
    id_column: str | None = None,
    domain: str | None = None,
    sensitivity: str = "public",
    max_rows: int = 500,
    max_chars: int = 30_000,
) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV introuvable : {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        raw_fieldnames = reader.fieldnames
    fieldnames: list[str] = list(raw_fieldnames) if raw_fieldnames else []

    if not rows:
        log.warning("CSV vide : %s", csv_path)
        return 0

    tasks: list[IntakeTask] = []
    for batch_idx in range(0, len(rows), max_rows):
        batch = rows[batch_idx : batch_idx + max_rows]
        table_str = _format_table(batch, fieldnames)
        if len(table_str) > max_chars:
            table_str = table_str[:max_chars] + "\n… (tronqué)"

        prompt = prompt_template.format(table=table_str)
        task_id = (
            batch[0].get(id_column, f"csv-{batch_idx:04d}")
            if id_column and batch
            else f"csv-{batch_idx:04d}"
        )
        tasks.append(
            IntakeTask(
                id=task_id,
                prompt=prompt,
                task_text=prompt,
                domain=domain,
                sensitivity=sensitivity,
                source=f"{csv_path.name}:rows{batch_idx}-{batch_idx+len(batch)}",
            )
        )

    return _write_jsonl(tasks, output)


def intake_from_csv_multi(
    csv_paths: list[pathlib.Path],
    output: pathlib.Path,
    prompt_template: str = "{table}",
    **kwargs,
) -> int:
    all_tasks: list[dict] = []
    total = 0

    for p in csv_paths:
        tmp_out = output.with_name(f".tmp_{p.stem}.jsonl")
        n = intake_from_csv(p, tmp_out, prompt_template=prompt_template, **kwargs)
        total += n
        with tmp_out.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["id"] = f"{p.stem}-{record.get('id', '?')}"
                all_tasks.append(record)
        tmp_out.unlink(missing_ok=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for t in all_tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    log.info("Écrit %d tâches depuis %d CSV dans %s", total, len(csv_paths), output)
    return total


# ─── Multi-types (images + txt + csv en une fois) ─────────────
def intake_mixed(
    sources: list[pathlib.Path],
    output: pathlib.Path,
    prompt_template: str = "Analyse ces données et réponds à la consigne : {consigne}",
    consigne: str = "",
    domain: str | None = None,
    sensitivity: str = "public",
) -> int:
    """Fusionne images, fichiers texte et CSV en une seule tâche groupée.

    Chaque ligne de CSV devient une tâche séparée. Chaque image et chaque
    fichier texte sont fusionnés dans une tâche « contexte global » qui
    contient tout le matériel + la consigne utilisateur.
    """
    images: list[pathlib.Path] = []
    texts: list[pathlib.Path] = []
    csvs: list[pathlib.Path] = []

    for p in sources:
        ext = p.suffix.lower()
        if ext in _IMAGE_EXTS:
            images.append(p)
        elif ext in _TEXT_EXTS:
            texts.append(p)
        elif ext == ".csv":
            csvs.append(p)
        else:
            log.warning("Extension inconnue ignorée : %s", p)

    tasks: list[IntakeTask] = []

    # 1) Tâche multimodale : images + textes fusionnés
    if images or texts:
        parts: list[str] = []
        if consigne:
            parts.append(f"CONSIGNE : {consigne}")

        for i, t in enumerate(texts, 1):
            try:
                content = t.read_text(encoding="utf-8", errors="replace")[:8000]
                parts.append(f"\n--- Fichier texte {i} ({t.name}) ---\n{content}")
            except Exception as e:
                log.warning("Lecture échouée %s: %s", t, e)

        for i, img in enumerate(images, 1):
            parts.append(
                f"\n--- Image {i} : {img.name} (voir image jointe) ---"
            )

        prompt = "\n".join(parts)
        # Une seule tâche pour toutes les images (le modèle les reçoit toutes)
        # Ollama supporte plusieurs images dans `messages[].images`, mais
        # router.route ne prend qu'une image_b64. On crée donc N tâches
        # partageant le même prompt texte, une par image.
        if images:
            for j, img in enumerate(images):
                tasks.append(
                    IntakeTask(
                        id=f"mix-{j:04d}",
                        prompt=prompt,
                        task_text=prompt,
                        domain=domain or "multimodal_extraction",
                        sensitivity=sensitivity,
                        image_path=str(img.resolve()),
                        source=f"mixed:{img.name}",
                    )
                )
        else:
            tasks.append(
                IntakeTask(
                    id="mix-0000",
                    prompt=prompt,
                    task_text=prompt,
                    domain=domain,
                    sensitivity=sensitivity,
                    source="mixed:text-only",
                )
            )

    # 2) CSV : chaque CSV en tâches séparées
    if csvs:
        for csv_p in csvs:
            tmp_out = output.with_name(f".tmp_mix_{csv_p.stem}.jsonl")
            intake_from_csv(
                csv_p,
                tmp_out,
                prompt_template=consigne + "\n\n{table}" if consigne else "{table}",
                domain=domain,
                sensitivity=sensitivity,
            )
            with tmp_out.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    rec["id"] = f"mix-{csv_p.stem}-{rec.get('id', '?')}"
                    filtered = {
                        k: v
                        for k, v in rec.items()
                        if k in IntakeTask.__dataclass_fields__
                    }
                    tasks.append(IntakeTask(**filtered))
            tmp_out.unlink(missing_ok=True)

    return _write_jsonl(tasks, output)


# ─── URLs ─────────────────────────────────────────────────────
def _check_robots(url: str) -> bool:
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
        return True


def intake_from_urls(
    urls_file: pathlib.Path,
    output: pathlib.Path,
    prompt_template: str = "Résume la page suivante :\n\n{content}",
    domain: str | None = None,
    sensitivity: str = "public",
    respect_robots: bool = True,
    delay_seconds: float = 1.0,
) -> int:
    if not urls_file.exists():
        raise FileNotFoundError(f"Fichier URLs introuvable : {urls_file}")

    urls = [
        line.strip()
        for line in urls_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    tasks = []
    headers = {
        "User-Agent": "gateway-llm-intake/0.1 (+https://github.com/<vous>/gateway-llm)"
    }
    for i, url in enumerate(urls):
        if respect_robots and not _check_robots(url):
            log.warning("robots.txt interdit %s, skip", url)
            continue
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            try:
                from bs4 import BeautifulSoup

                text = BeautifulSoup(r.text, "html.parser").get_text(separator="\n")
            except ImportError:
                text = r.text
            prompt = prompt_template.format(content=text[:8000])
            tasks.append(
                IntakeTask(
                    id=f"url-{i:04d}",
                    prompt=prompt,
                    task_text=prompt,
                    domain=domain,
                    sensitivity=sensitivity,
                    source=url,
                )
            )
            time.sleep(delay_seconds)
        except Exception as e:
            log.warning("Échec fetch %s: %s", url, e)
    return _write_jsonl(tasks, output)