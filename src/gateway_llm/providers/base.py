# SPDX-FileCopyrightText: 2026 Amandine Dennieau
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Classes de base pour les providers LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Erreur générique d'un provider."""


class RateLimitError(ProviderError):
    """Le provider a renvoyé 429 (quota / rate limit)."""


class ProviderUnavailableError(ProviderError):
    """Secret manquant, modèle introuvable, réponse malformée, etc."""


@dataclass
class ProviderResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    truncated: bool = False


class Provider(ABC):
    """Un provider encapsule l'appel HTTP vers un backend donné."""

    name: str

    @abstractmethod
    def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
        image_b64: str | None = None
    ) -> ProviderResponse:
        """Envoie un prompt et retourne la réponse normalisée.

        Doit lever :
        - RateLimitError si le provider renvoie 429
        - ProviderUnavailableError pour tout autre échec
        """