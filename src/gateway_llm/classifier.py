# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Classification des tâches par domaine + flags de risque.

Architecture en cascade à 3 niveaux (standard 2026 pour l'intent
classification en production) :

1. Règles déterministes (regex) — rapides, fiables sur les cas
   structurés (dates, sécurité, subjectif). Couvre ~60% du trafic.
2. Embeddings (cosine similarity via SemanticRouter) — sémantique.
   Couvre ~30%. Seuil haut = acceptation directe, zone grise = LLM.
3. LLM — fallback pour les cas ambigus ou hors distribution.
   Couvre ~10%.

Avantage mesuré (littérature 2026) : coût ~10× inférieur au LLM pur,
précision supérieure, latence maîtrisée.
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

# ─── Seuils calibrés (littérature 2026) ───────────────────────
HIGH_CONFIDENCE = 0.82  # au-dessus : on accepte sans LLM
LOW_CONFIDENCE = 0.60  # en-dessous : LLM obligatoire
AMBIGUITY_GAP = 0.10  # top-2 trop proche du top-1 = ambigu


@dataclass
class ClassificationResult:
    domain: str
    status: str = "pending"
    human_priority: int = 0
    risk_level: str = "low"
    flags: list[str] = field(default_factory=list)
    reason: str = ""
    # Nouveaux champs pour l'audit / debug
    confidence: float | None = None
    decision_layer: str = ""  # "regex" | "embedding" | "llm" | "fallback"


class TaskClassifier:
    def __init__(
        self,
        provider: Provider | None = None,
        model: str = "qwen3:4b-instruct",
        max_tokens: int = 200,
        semantic_router: SemanticRouter | None = None,
        *,
        high_confidence: float = HIGH_CONFIDENCE,
        low_confidence: float = LOW_CONFIDENCE,
        ambiguity_gap: float = AMBIGUITY_GAP,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._semantic_router = semantic_router or SemanticRouter()
        self._high = high_confidence
        self._low = low_confidence
        self._gap = ambiguity_gap

    # ────────────────────────────────────────────────────────
    # Point d'entrée
    # ────────────────────────────────────────────────────────
    def classify(self, task_text: str, task_desc: str = "") -> ClassificationResult:
        # Étage 1 : règles déterministes
        regex_result = self._fallback(task_text, task_desc)

        # Si la regex détecte un blocage critique, on s'arrête là.
        # Les règles déterministes priment sur le sémantique parce que
        # les embeddings sont aveugles à la négation et aux inversions
        # de sens (cf. audit arXiv 2608.10216).
        if regex_result.status != "pending":
            regex_result.decision_layer = "regex"
            return regex_result

        # Étage 2 : embeddings (cosine)
        semantic_result = self._semantic_router.route(task_text)

        if semantic_result is not None:
            score = semantic_result.score
            domain = semantic_result.domain

            # Confiance haute : acceptation directe
            if score >= self._high:
                return ClassificationResult(
                    domain=domain,
                    status="pending",
                    human_priority=regex_result.human_priority,
                    risk_level=regex_result.risk_level,
                    flags=regex_result.flags,
                    reason=f"Embeddings (score={score:.2f})",
                    confidence=score,
                    decision_layer="embedding",
                )

            # Zone grise haute (0.60 ≤ score < 0.82) : LLM tiebreaker
            if score >= self._low:
                # On vérifie l'ambiguïté : si un autre domaine est proche,
                # le sémantique n'est pas fiable → LLM.
                second = self._second_best(task_text)
                is_ambiguous = second is not None and (score - second[1]) < self._gap
                if not is_ambiguous and self._provider is not None:
                    # Pas ambigu et LLM dispo : on tente le LLM pour
                    # confirmer, mais on garde le sémantique comme filet.
                    try:
                        llm_result = self._classify_llm(task_text, task_desc)
                        llm_result.confidence = score
                        llm_result.decision_layer = "llm"
                        return llm_result
                    except Exception as e:
                        log.warning("LLM tiebreaker échoué, on garde le sémantique : %s", e)

                # LLM indisponible ou ambigu : on garde le sémantique avec
                # une priorité humaine plus élevée pour review.
                return ClassificationResult(
                    domain=domain,
                    status="pending",
                    human_priority=max(regex_result.human_priority, 4),
                    risk_level=regex_result.risk_level,
                    flags=regex_result.flags,
                    reason=f"Embeddings zone grise (score={score:.2f})",
                    confidence=score,
                    decision_layer="embedding",
                )

        # Étage 3 : LLM (score bas ou pas de résultat sémantique)
        if self._provider is not None:
            try:
                llm_result = self._classify_llm(task_text, task_desc)
                llm_result.decision_layer = "llm"
                return llm_result
            except Exception as e:
                log.warning("Classifieur LLM échoué, fallback regex : %s", e)

        # Fallback ultime : regex
        regex_result.decision_layer = "fallback"
        return regex_result

    # ────────────────────────────────────────────────────────
    # Second best (pour l'ambiguïté)
    # ────────────────────────────────────────────────────────
    def _second_best(self, text: str) -> tuple[str, float] | None:
        """Retourne le second meilleur domaine et son score, si dispo."""
        # On accède aux embeddings déjà calculés par le SemanticRouter
        # pour éviter un deuxième appel API.
        router = self._semantic_router
        if not getattr(router, "_is_ready", False):
            return None
        emb = router._get_embedding(text)
        if not emb:
            return None
        scores: list[tuple[str, float]] = []
        for domain, embs in router._domain_embeddings.items():
            best = max(router._cosine_similarity(emb, e) for e in embs) if embs else 0.0
            scores.append((domain, best))
        scores.sort(key=lambda x: x[1], reverse=True)
        if len(scores) < 2:
            return None
        return scores[1]

    # ────────────────────────────────────────────────────────
    # Étage 3 : LLM
    # ────────────────────────────────────────────────────────
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

    # ────────────────────────────────────────────────────────
    # Étage 1 : règles déterministes
    # ────────────────────────────────────────────────────────
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
            for p in [r"\b202[5-9]\b", r"\bactuellement\b", r"\baujourd'hui\b"]
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
