#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Scrape ollama.com/library pour produire benchmarks_cache/ollama_library.json.

Utilise Playwright pour rendre la page (les tailles de tags sont chargées
dynamiquement), puis BeautifulSoup pour parser le HTML.
Fallback sur l'API akazwz/ollama-models si le parsing échoue.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import async_playwright

OUT = pathlib.Path("benchmarks_cache/ollama_library.json")
LIBRARY_URL = "https://ollama.com/library?sort=popular"
FALLBACK_API = "https://ollama-models.zwz.workers.dev"
HEADERS = {"User-Agent": "gateway-llm-benchmark-bot/0.1"}
MIN_PLAUSIBLE = 20


# ────────────────────────────────────────────────────────────────
# Helpers typés pour les attributs BS4
# ────────────────────────────────────────────────────────────────
def _attr_str(tag: Tag, attr: str) -> str:
    """Retourne un attribut HTML sous forme de str (gère AttributeValueList)."""
    value = tag.get(attr)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        items = list(value)  # type: ignore[arg-type]
        return str(items[0]) if items else ""
    except TypeError:
        return str(value)


def _attr_classes(tag: Tag) -> str:
    """Retourne les classes CSS comme une chaîne espace-séparée."""
    value = tag.get("class")
    if not value:
        return ""
    if isinstance(value, str):
        return value
    try:
        return " ".join(str(c) for c in value)  # type: ignore[union-attr]
    except TypeError:
        return str(value)


# ────────────────────────────────────────────────────────────────
# Playwright + BeautifulSoup
# ────────────────────────────────────────────────────────────────
async def fetch_library_html() -> str:
    """Rend la page de la bibliothèque avec Playwright et retourne le HTML."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await page.goto(LIBRARY_URL, wait_until="domcontentloaded", timeout=30_000)
        with contextlib.suppress(Exception):
            await page.wait_for_selector('a[href^="/library/"]', timeout=15_000)
        html = await page.content()
        await browser.close()
        return html


def parse_model_cards(html: str) -> list[dict]:
    """Parse les cartes de modèles depuis le HTML rendu."""
    soup = BeautifulSoup(html, "html.parser")
    models: list[dict] = []
    seen_names: set[str] = set()

    for li in soup.find_all("li"):
        link = li.find("a", href=re.compile(r"^/library/[a-z0-9._-]+$"))
        if not isinstance(link, Tag):
            continue

        href = _attr_str(link, "href")
        if not href:
            continue
        name = href.rsplit("/", 1)[-1]
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        capabilities: list[str] = []
        base_sizes: list[str] = []
        for span in li.find_all("span"):
            if not isinstance(span, Tag):
                continue
            cls = _attr_classes(span)
            txt = span.get_text(strip=True)
            txt_lower = txt.lower()

            if not txt or len(txt) > 20:
                continue
            if "bg-indigo-50" in cls or "bg-blue-50" in cls:
                if txt_lower in (
                    "tools",
                    "thinking",
                    "vision",
                    "embedding",
                    "audio",
                    "cloud",
                ):
                    capabilities.append(txt_lower)
            elif (
                ("bg-[#ddf4ff]" in cls or "bg-blue-100" in cls)
                and re.fullmatch(r"[\d.]+[bm]", txt_lower)
            ):
                base_sizes.append(txt_lower)

        models.append(
            {
                "name": name,
                "capabilities": capabilities,
                "base_sizes": base_sizes,
                "tags": [],
            }
        )

    return models


async def scrape_model_tags(model_name: str) -> list[dict]:
    """Scrape /library/<name> pour les tags (quantifications, tailles exactes)."""
    url = f"https://ollama.com/library/{model_name}"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            with contextlib.suppress(Exception):
                await page.wait_for_selector('a[href*=":"]', timeout=8_000)
            html = await page.content()
            await browser.close()
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tags: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a"):
        if not isinstance(a, Tag):
            continue
        href = _attr_str(a, "href")
        if not href or f"/library/{model_name}:" not in href:
            continue
        tag = href.split(":")[-1]
        if not tag or tag in seen:
            continue
        seen.add(tag)

        text = a.get_text(" ", strip=True)
        size_match = re.search(r"([\d.]+)\s*GB", text, re.IGNORECASE)
        size_gb = float(size_match.group(1)) if size_match else None

        tags.append(
            {
                "tag": tag,
                "size_gb": size_gb,
                "param_count_b": _infer_param_count(tag),
                "quantization": _infer_quantization(tag),
            }
        )

    return tags


def _infer_param_count(tag: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)b", tag.lower())
    return float(m.group(1)) if m else None


def _infer_quantization(tag: str) -> str | None:
    m = re.search(r"(q\d+_k_[ms]|q\d+_0|q\d+_\d+|bf16|fp16)", tag.lower())
    return m.group(1).upper() if m else None


# ────────────────────────────────────────────────────────────────
# Fallback API
# ────────────────────────────────────────────────────────────────
def fetch_from_api() -> list[dict]:
    """Fallback : API akazwz/ollama-models (JSON déjà structuré)."""
    try:
        r = requests.get(FALLBACK_API, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"⚠️ Fallback API échoué : {e}", file=sys.stderr)
        return []

    models: list[dict] = []
    for item in data:
        name = item.get("name")
        tags_raw = item.get("tags", [])
        if not name:
            continue
        tags = []
        for t in tags_raw:
            param_b = _infer_param_count(t)
            size_gb = round(param_b * 0.6, 1) if param_b else None
            tags.append(
                {
                    "tag": t,
                    "size_gb": size_gb,
                    "param_count_b": param_b,
                    "quantization": _infer_quantization(t),
                }
            )
        models.append(
            {
                "name": name,
                "capabilities": [],
                "base_sizes": [],
                "tags": tags,
            }
        )
    return models


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────
async def scrape_all() -> list[dict]:
    print("🌐 Rendu de ollama.com/library avec Playwright…")
    html = await fetch_library_html()
    cards = parse_model_cards(html)
    print(f"   {len(cards)} modèles détectés")

    enriched: list[dict] = []
    for i, card in enumerate(cards, 1):
        name = card["name"]
        print(f"   [{i}/{len(cards)}] {name}…", end="", flush=True)
        tags = await scrape_model_tags(name)
        if tags:
            card["tags"] = tags
            enriched.append(card)
            print(f" {len(tags)} tags")
        else:
            print(" aucun tag, ignoré")

    return enriched


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    try:
        models = asyncio.run(scrape_all())
    except Exception as e:
        print(f"⚠️ Playwright échoué : {e}", file=sys.stderr)
        models = []

    if len(models) < MIN_PLAUSIBLE:
        print(
            f"⚠️ Seulement {len(models)} modèles parsés (< {MIN_PLAUSIBLE}). "
            "Fallback sur l'API akazwz…",
            file=sys.stderr,
        )
        api_models = fetch_from_api()
        if len(api_models) > len(models):
            models = api_models

    if not models:
        print("❌ Aucun modèle récupéré (ni scraping ni API)", file=sys.stderr)
        return 1

    payload = {
        "last_updated": date.today().isoformat(),
        "source": "ollama.com/library (Playwright + BeautifulSoup) + fallback API",
        "models": models,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(models)} modèles écrits dans {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())