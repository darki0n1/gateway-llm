# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Chargement et validation des YAML de configuration."""

from __future__ import annotations

import pathlib
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

# PolicyConfig vit désormais dans policy.py ; on le ré-exporte pour
# ne pas casser les imports existants (`from gateway_llm.config import PolicyConfig`).
from gateway_llm.policy import PolicyConfig

__all__ = [
    "DomainChain",
    "ModelConfig",
    "ModelsConfig",
    "PolicyConfig",
    "ProviderConfig",
    "load_config",
    "load_policy",
]


class ProviderConfig(BaseModel):
    type: Literal["openai_compat", "ollama", "cloudflare"]
    base_url: str
    secret_name: str | None = None
    account_secret_name: str | None = None
    local: bool = False
    extra_headers: dict[str, str] = Field(default_factory=dict)
    timeout: int = 120


class ModelConfig(BaseModel):
    provider: str
    model_name: str | None = None
    size_gb: float | None = None
    max_tokens: int = 2048
    # Prix optionnels pour le budget (par 1000 tokens).
    # 0.0 = gratuit (free tier, local). À ajuster pour les APIs payantes.
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0

    def compute_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens / 1000.0) * self.input_price_per_1k + (
            output_tokens / 1000.0
        ) * self.output_price_per_1k


class DomainChain(BaseModel):
    chain: list[str]
    max_tokens: int = 2048


class ModelsConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelConfig]
    domains: dict[str, DomainChain]

    @model_validator(mode="after")
    def _check_refs(self) -> ModelsConfig:
        for dname, d in self.domains.items():
            for mk in d.chain:
                if mk not in self.models:
                    raise ValueError(f"domaine '{dname}' -> modèle inconnu: {mk}")
        for mk, mc in self.models.items():
            if mc.provider not in self.providers:
                raise ValueError(f"modèle '{mk}' -> provider inconnu: {mc.provider}")
        return self

    def resolve_model_name(self, model_key: str) -> str:
        mc = self.models[model_key]
        return mc.model_name or model_key


def _load_yaml(path) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config introuvable: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{p} ne contient pas un mapping YAML")
    return data


def load_config(path) -> ModelsConfig:
    return ModelsConfig.model_validate(_load_yaml(path))


def load_policy(path) -> PolicyConfig:
    return PolicyConfig.model_validate(_load_yaml(path))
