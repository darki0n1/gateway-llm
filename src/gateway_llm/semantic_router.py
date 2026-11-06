# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Routeur sémantique par embeddings locaux (via Ollama).

Remplace/complète les regex en comparant la similarité entre le prompt
et des phrases d'exemple (utterances) propres à chaque domaine.
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

# Phrases d'exemple pour définir chaque domaine.
# L'idée est de couvrir les différentes façons de formuler la même intention.
DOMAIN_UTTERANCES = {
    "translation": [
        "Traduis ce texte en anglais",
        "Comment dit-on bonjour en espagnol",
        "Passe cette phrase en français",
        "Donne-moi la traduction de ce paragraphe",
        "Translate this to French",
    ],
    "code_debug": [
        "Corrige ce bug dans mon code Python",
        "Pourquoi j'ai une erreur d'indentation",
        "Réparer cette fonction qui plante",
        "Trouve l'erreur dans ce script",
        "Fix this code snippet",
    ],
    "fact_checking": [
        "Vérifie si cette affirmation est vraie",
        "Est-ce que ce chiffre est correct",
        "Fact-check ce paragraphe",
        "Cette information est-elle fiable",
    ],
    "thinking": [
        "Analyse cette situation en profondeur",
        "Quelles sont les causes de ce phénomène",
        "Explique-moi le raisonnement derrière cette théorie",
        "Réfléchis à ce problème",
    ],
    "problem_solving": [
        "Comment résoudre ce problème mathématique",
        "Propose une solution pour optimiser ce processus",
        "Comment puis-je améliorer cette architecture",
        "Aide-moi à trouver une solution",
    ],
    "safety": [
        "Est-ce que ce site est sécurisé",
        "Audit de sécurité de ce serveur",
        "Vérifie les failles dans ce code",
        "Comment sécuriser cette API",
    ],
    "red_teaming": [
        "Fais un test d'intrusion sur ce système",
        "Comment contourner cette authentification",
        "Trouve une faille dans cette application",
        "Simule une attaque",
    ],
    "prompt_creation": [
        "Rédige un prompt pour une IA",
        "Écris un article sur ce sujet",
        "Crée un email de prospection",
        "Génère un texte créatif",
    ],
    "multimodal_extraction": [
        "Extrais les données de cette image",
        "Lis les chiffres sur ce graphique",
        "Analyse ce screenshot",
        "Que vois-tu sur cette photo",
    ],
}


@dataclass
class SemanticResult:
    domain: str
    score: float


class SemanticRouter:
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        threshold: float = 0.75,
    ) -> None:
        self._url = ollama_url.rstrip("/")
        self._model = model
        self._threshold = threshold
        self._domain_embeddings: dict[str, list[list[float]]] = {}
        self._is_ready = False

    def _ensure_model_installed(self) -> bool:
        """Vérifie si le modèle d'embedding est installé, sinon le télécharge."""
        try:
            # On demande à Ollama la liste des modèles
            resp = requests.get(f"{self._url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                # On vérifie si nomic-embed-text (ou sa version taguée) est là
                if any(self._model in m for m in models):
                    return True

            log.info("Téléchargement du modèle d'embedding manquant : %s...", self._model)

            # Si le binaire ollama est présent, on lance le pull
            if shutil.which("ollama"):
                subprocess.run(
                    ["ollama", "pull", self._model], check=True, capture_output=True, text=True
                )
                return True
            else:
                log.warning("Ollama n'est pas dans le PATH, impossible de télécharger le modèle.")
                return False

        except Exception as e:
            log.warning("Échec de l'installation automatique du modèle : %s", e)
            return False

    def _get_embedding(self, text: str) -> list[float] | None:
        """Récupère l'embedding via l'API Ollama."""
        try:
            resp = requests.post(
                f"{self._url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as e:
            log.debug("Erreur embedding pour '%s': %s", text[:20], e)
            return None

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Calcule la similarité cosinus entre deux vecteurs."""
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _ensure_ready(self) -> bool:
        """Pré-calcule les embeddings des phrases d'exemple (une seule fois)."""
        if self._is_ready:
            return True

        log.info("Initialisation du SemanticRouter (calcul des embeddings)...")
        for domain, utterances in DOMAIN_UTTERANCES.items():
            embeddings = []
            for utt in utterances:
                emb = self._get_embedding(utt)
                if emb:
                    embeddings.append(emb)

            if embeddings:
                self._domain_embeddings[domain] = embeddings
            else:
                log.warning("Impossible de charger les embeddings pour %s", domain)

        self._is_ready = bool(self._domain_embeddings)
        return self._is_ready

    def route(self, text: str) -> SemanticResult | None:
        """Détermine le domaine d'un texte par similarité sémantique.

        Retourne None si le score est inférieur au seuil de confiance.
        """
        if not self._ensure_ready():
            return None

        query_emb = self._get_embedding(text)
        if not query_emb:
            return None

        best_domain = None
        best_score = 0.0

        for domain, embs in self._domain_embeddings.items():
            # On compare avec toutes les phrases du domaine, on garde la meilleure
            score = max(self._cosine_similarity(query_emb, e) for e in embs)
            if score > best_score:
                best_score = score
                best_domain = domain

        if best_score >= self._threshold and best_domain:
            return SemanticResult(domain=best_domain, score=best_score)

        return None
