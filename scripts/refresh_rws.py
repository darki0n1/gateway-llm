#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Scrape le leaderboard RWS TrainAI (M-GATE) et écrit benchmarks_cache/rws_translation.json.

⚠️ Destiné à tourner dans GitHub Actions (planifié) ou en local par un
technicien. Non appelé au runtime du package.

Les sélecteurs HTML sont à ajuster si RWS change la structure de sa page.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

OUT = pathlib.Path("benchmarks_cache/rws_translation.json")
URL = "https://m-gate.ai/leaderboard/"
HEADERS = {"User-Agent": "llm-gateway-benchmark-bot/0.1"}


def parse_mgate(html: str) -> dict[str, float]:
    """Extrait {model: score_sur_5} depuis m-gate.ai.

    TODO: ajuster les sélecteurs selon la structure réelle.
    Le leaderboard est rendu en JS, donc il peut falloir
    chercher les données dans un <script> JSON ou appeler une API sous-jacente.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: dict[str, float] = {}

    # Tentative 1 : chercher un tableau HTML
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        model_idx = next((i for i, h in enumerate(headers)
                         if "model" in h), None)
        score_idx = next((i for i, h in enumerate(headers)
                         if "score" in h or "overall" in h), None)
        if model_idx is None or score_idx is None:
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) <= max(model_idx, score_idx):
                continue
            model = cells[model_idx].get_text(strip=True)
            raw = cells[score_idx].get_text(strip=True).split()[0]
            try:
                results[model] = float(raw)
            except ValueError:
                continue

    # Tentative 2 : chercher du JSON embarqué dans un <script>
    if not results:
        for script in soup.find_all("script"):
            text = script.string or ""
            if "leaderboard" in text.lower() and "model" in text.lower():
                import re
                m = re.search(r'\[\s*\{[^\]]*"model"[^\]]*\}\s*\]', text)
                if m:
                    try:
                        data = json.loads(m.group(0))
                        for item in data:
                            if "model" in item and "score" in item:
                                results[item["model"]] = float(item["score"])
                    except json.JSONDecodeError:
                        pass

    return results


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    try:
        r = requests.get(URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        scores = parse_mgate(r.text)
    except Exception as e:
        print(f"❌ Échec fetch: {e}", file=sys.stderr)
        return 1

    if not scores:
        print("❌ Aucun score parsé. Vérifier les sélecteurs HTML.", file=sys.stderr)
        return 1

    payload = {
        "last_updated": date.today().isoformat(),
        "source": "RWS TrainAI M-GATE leaderboard (scraped)",
        "notes": "Auto-généré par scripts/refresh_rws.py. Scores sur 5.",
        "models": [
            {"model": m, "overall_score": s} for m, s in sorted(scores.items())
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {len(scores)} modèles écrits dans {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())