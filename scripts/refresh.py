#!/usr/bin/env python3
# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Scrape le leaderboard F5 Labs CASI/ARS et écrit benchmarks_cache/f5_safety.json.

⚠️ Ce script est destiné à tourner dans GitHub Actions (planifié) ou
en local par un technicien. Il n'est PAS appelé au runtime du package.

Les sélecteurs HTML sont à ajuster si F5 change la structure de sa page.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

OUT = pathlib.Path("benchmarks_cache/f5_safety.json")
HEADERS = {"User-Agent": "llm-gateway-benchmark-bot/0.1"}

# URL publiques des deux classements
URLS = {
    "casi": "https://www.f5.com/labs/casi",
    "ars": "https://www.f5.com/labs/ars",
}


def parse_leaderboard(html: str, metric: str) -> dict[str, float]:
    """Extrait {model_name: score} depuis la page F5.

    TODO: ajuster les sélecteurs selon la structure réelle de la page.
    Le tableau F5 est en HTML classique (table > tr > td).
    """
    soup = BeautifulSoup(html, "html.parser")
    results: dict[str, float] = {}

    # Cherche un tableau principal
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        # Trouve les colonnes "model" et "score" (ou nommées différemment)
        model_idx = next((i for i, h in enumerate(headers)
                         if "model" in h or "name" in h), None)
        score_idx = next((i for i, h in enumerate(headers)
                         if "score" in h or metric in h or "%" in h), None)
        if model_idx is None or score_idx is None:
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) <= max(model_idx, score_idx):
                continue
            model = cells[model_idx].get_text(strip=True)
            raw = cells[score_idx].get_text(strip=True).replace("%", "").strip()
            try:
                results[model] = float(raw)
            except ValueError:
                continue

    return results


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict] = {}

    for metric, url in URLS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            scores = parse_leaderboard(r.text, metric)
            print(f"{url}: {len(scores)} entrées parsées")
            for model, score in scores.items():
                merged.setdefault(model, {})[metric] = score
        except Exception as e:
            print(f"⚠️ Échec {url}: {e}", file=sys.stderr)

    if not merged:
        print("❌ Aucun résultat parsé. Vérifier les sélecteurs HTML.", file=sys.stderr)
        return 1

    payload = {
        "last_updated": date.today().isoformat(),
        "source": "F5 Labs CASI / ARS leaderboards (scraped)",
        "notes": "Auto-généré par scripts/refresh_f5.py",
        "models": [
            {"model": m, **scores} for m, scores in sorted(merged.items())
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {len(merged)} modèles écrits dans {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())