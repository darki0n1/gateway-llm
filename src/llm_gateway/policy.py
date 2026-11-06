# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Politique de résidence des données.

Formes YAML acceptées pour `residency` :
  - {"public": {"allowed_providers": ["groq"]}}
  - {"public": ["groq"]}
  - {"public": ResidencyRule(allowed_providers=["groq"])}

Les trois sont normalisées à l'accès via `_resolve_rule`.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


class ResidencyRule(BaseModel):
    """Règle de résidence : liste des providers autorisés."""

    model_config = ConfigDict(extra="forbid")
    allowed_providers: list[str] = Field(default_factory=list)


# Union explicite des formes acceptées en entrée.
ResidencyValue = ResidencyRule | dict[str, Any] | list[str]


class PolicyConfig(BaseModel):
    residency: dict[str, ResidencyValue]
    default_allow: bool = True

    def _resolve_rule(self, rule: ResidencyValue) -> list[str]:
        if isinstance(rule, ResidencyRule):
            return list(rule.allowed_providers)
        if isinstance(rule, dict):
            return list(rule.get("allowed_providers", []))
        if isinstance(rule, list):
            return list(rule)
        return []

    def is_allowed(self, provider: str, sensitivity: str) -> bool:
        rule = self.residency.get(sensitivity)
        if rule is None:
            rule = self.residency.get("default")
        if rule is None:
            return self.default_allow
        allowed = self._resolve_rule(rule)
        return any(fnmatch.fnmatchcase(provider, p) for p in allowed)

    def allowed_providers(self, sensitivity: str) -> list[str]:
        rule = self.residency.get(sensitivity)
        if rule is None:
            rule = self.residency.get("default")
        if rule is None:
            return []
        return self._resolve_rule(rule)