# Copyright 2026 <VOTRE NOM / ORGANISATION>
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

"""Interface commune à tous les guardrails.

Un guardrail prend une (tâche, réponse) et retourne un GuardrailResult
qui indique si la réponse est fiable ou doit être escaladée vers la
review humaine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardrailResult:
    """Résultat d'une vérification de guardrail.

    Attributes:
        is_valid: True si la réponse est jugée fiable.
        reason: Explication courte (utile pour le rapport et la review).
        flagged: True si le guardrail a explicitement détecté un problème
                 (distinct de is_valid=False par "erreur de vérification").
    """

    is_valid: bool
    reason: str = ""
    flagged: bool = False


class Guardrail(ABC):
    """Vérifie la fiabilité d'une réponse LLM."""

    @abstractmethod
    def check(self, task_text: str, response: str) -> GuardrailResult:
        """Retourne un GuardrailResult. Ne doit jamais lever d'exception
        sur une entrée valide — en cas de doute, retourner is_valid=True
        (fail-open) et logger un warning."""