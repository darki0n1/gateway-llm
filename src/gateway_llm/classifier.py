# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Classification des tâches par domaine + flags de risque.

Architecture en cascade :
1. Règles regex rapides (détection des flags critiques).
2. Routeur sémantique (embeddings locaux via Ollama).
3. LLM (si les deux premiers niveaux n'ont pas suffi).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from gateway_llm.providers.base import Provider
from gateway_llm.semantic_router import SemanticRouter

log = logging.getLogger(__name__)

DOMAINS: tuple[str, ...] = (
    "code_debug",
    "thinking",
    "problem_solving",
    "translation",
    "fact_checking",
    "safety",
    "red_teaming",
    "prompt_creation",
    "multimodal_extraction",
)

_STATUSES = (
    "pending",
    "blocked_post2024",
    "blocked_subjective",
)


@dataclass
class ClassificationResult:
    domain: str
    status: str = "pending"
    human_priority: int = 0
    risk_level: str = "low"
    flags: list[str] = field(default_factory=list)
    reason: str = ""


class TaskClassifier:
    def __init__(
        self,
        provider: Provider | None = None,
        model: str = "qwen3:4b-instruct",
        max_tokens: int = 200,
        semantic_router: SemanticRouter | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._semantic_router = semantic_router or SemanticRouter()

    def classify(self, task_text: str, task_desc: str = "") -> ClassificationResult:
        # 1. Regex rapide : détecte les blocages critiques (sécurité, dates...)
        regex_result = self._fallback(task_text, task_desc)

        # Si la regex a trouvé un flag bloquant, on s'arrête immédiatement
        if regex_result.status != "pending":
            return regex_result

        # 2. Routeur sémantique (embeddings)
        semantic_result = self._semantic_router.route(task_text)
        if semantic_result:
            return ClassificationResult(
                domain=semantic_result.domain,
                status="pending",
                human_priority=regex_result.human_priority,
                risk_level=regex_result.risk_level,
                flags=regex_result.flags,
                reason=f"Routage sémantique (score={semantic_result.score:.2f})",
            )

        # 3. LLM (si dispo et si les deux premiers ont échoué)
        if self._provider is not None:
            try:
                return self._classify_llm(task_text, task_desc)
            except Exception as e:
                log.warning("Classifieur LLM échoué, fallback regex : %s", e)

        # 4. Fallback ultime (regex non critique)
        return regex_result

    def _classify_llm(self, task_text: str, task_desc: str) -> ClassificationResult:
        provider = self._provider
        if provider is None:
            return self._fallback(task_text, task_desc)

        domains_str = ", ".join(DOMAINS)
        prompt = f"""\
Tu es un classifieur de tâches. Tu identifies le DOMAINE et le NIVEAU DE RISQUE.

Domaines possibles : {domains_str}

--- RÈGLES ---

1. MULTIMODAL_EXTRACTION
   La tâche demande de lire, analyser ou extraire des données d'une image,
   d'un screenshot, d'un graphique ou d'un tableau visuel.
   => domain: "multimodal_extraction", status: "pending", priority: 0

2. POST_2024_FACT_CHECK
   Tâche portant sur un fait vérifiable postérieur à 2024.
   => domain selon contexte, status: "blocked_post2024", priority: 8

3. HIGH_RISK
   Intention offensive explicite (exploit, exfiltration, nuisance).
   => status: "blocked_subjective", priority: 10

4. SUBJECTIVE_NORMAL
   Jugement de valeur, notation, préférence personnelle.
   => status: "blocked_subjective", priority: 7

--- FORMAT ---
Retourne UNIQUEMENT un JSON valide :
{{"domain": "...", "status": "pending|blocked_post2024|blocked_subjective",
  "human_priority": 0-10, "risk_level": "low|medium|high",
  "flags": [], "reason": "..."}}

Tâche: {task_text}
Contexte: {task_desc}
Réponse:"""

        response = provider.complete(
            model=self._model,
            prompt=prompt,
            max_tokens=self._max_tokens,
            temperature=0.1,
        )

        raw = response.text
        raw = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", raw, flags=re.S)
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError("aucun JSON dans la réponse du classifieur")

        parsed = json.loads(m.group(0))

        domain = parsed.get("domain", "prompt_creation")
        if domain not in DOMAINS:
            domain = "prompt_creation"

        status = parsed.get("status", "pending")
        if status not in _STATUSES:
            status = "pending"

        flags = parsed.get("flags", [])
        if not isinstance(flags, list):
            flags = [str(flags)] if flags else []

        try:
            priority = int(parsed.get("human_priority", 0))
        except (TypeError, ValueError):
            priority = 0
        priority = max(0, min(10, priority))

        return ClassificationResult(
            domain=domain,
            status=status,
            human_priority=priority,
            risk_level=parsed.get("risk_level", "low"),
            flags=flags,
            reason=parsed.get("reason", "Classifieur LLM"),
        )

    def _fallback(self, task_text: str, task_desc: str) -> ClassificationResult:
        text_lower = task_text.lower()
        flags: list[str] = []
        priority = 0

        # 1) Multimodal (détection rapide par mots-clés)
        is_image = any(
            re.search(p, text_lower)
            for p in [
                r"\bimage\b",
                r"\bscreenshot\b",
                r"\bphoto\b",
                r"\bgraphique\b",
                r"\btableau\b",
                r"\bcapture\b",
            ]
        )
        wants_extract = any(
            re.search(p, text_lower)
            for p in [
                r"\bextrait",
                r"\blis\b",
                r"\banalyse",
                r"\bkpi\b",
                r"\bchiffre",
                r"\bdonnée",
                r"\brésume",
            ]
        )
        if is_image and wants_extract:
            return ClassificationResult(
                domain="multimodal_extraction",
                status="pending",
                human_priority=0,
                risk_level="low",
                flags=[],
                reason="Détection image + extraction",
            )

        # 2) Post-2024
        if any(
            re.search(p, text_lower)
            for p in [
                r"\b202[5-9]\b",
                r"\bactuellement\b",
                r"\baujourd'hui\b",
            ]
        ):
            flags.append("POST_2024_FACT_CHECK")
            priority = max(priority, 8)

        # 3) High risk
        if any(
            re.search(p, text_lower)
            for p in [
                r"\bsécurité\b",
                r"\bdanger\b",
                r"\brisqu(e|es)\b",
                r"\binjection\b",
                r"\bsecret\b",
                r"\bmot de passe\b",
                r"\bclé api\b",
                r"\bpirater\b",
                r"\bvulnérabilité\b",
            ]
        ):
            flags.append("HIGH_RISK")
            priority = max(priority, 10)

        # 4) Subjectif
        if any(
            re.search(p, text_lower)
            for p in [
                r"\bquelle formulation\b",
                r"\bplus professionnel",
                r"\bnot(er|ez|ion)\b",
                r"\béval(u|ue)er\b",
            ]
        ):
            flags.append("SUBJECTIVE_NORMAL")
            priority = max(priority, 7)

        status = "pending"
        if "POST_2024_FACT_CHECK" in flags:
            status = "blocked_post2024"
        elif "HIGH_RISK" in flags or "SUBJECTIVE_NORMAL" in flags:
            status = "blocked_subjective"

        # Domaine par défaut (au cas où le sémantique et le LLM échouent)
        domain = "prompt_creation"
        if any(w in text_lower for w in ["code", "python", "sql", "debug", "bug", "erreur"]):
            domain = "code_debug"
        elif any(w in text_lower for w in ["red team", "redteam", "pentest", "attaque"]):
            domain = "red_teaming"
        elif any(w in text_lower for w in ["sécurit", "safety"]):
            domain = "safety"
        elif any(w in text_lower for w in ["vérifi", "fact", "affirmation", "véracité"]):
            domain = "fact_checking"
        elif any(w in text_lower for w in ["tradui", "traduc", "français", "francais"]):
            domain = "translation"
        elif any(w in text_lower for w in ["résoudre", "resoudre", "problème", "probleme"]):
            domain = "problem_solving"
        elif any(w in text_lower for w in ["raisonn", "logique", "analy", "thinking"]):
            domain = "thinking"

        return ClassificationResult(
            domain=domain,
            status=status,
            human_priority=priority,
            risk_level=("high" if priority >= 7 else "medium" if priority >= 4 else "low"),
            flags=flags,
            reason="Fallback regex",
        )
