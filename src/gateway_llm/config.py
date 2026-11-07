# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Chargement et validation des YAML de configuration."""

from __future__ import annotations

import pathlib
from enum import StrEnum
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from gateway_llm.policy import PolicyConfig

__all__ = [
    "DomainChain",
    "LocalMode",
    "ModelConfig",
    "ModelsConfig",
    "PolicyConfig",
    "ProviderConfig",
    "load_config",
    "load_local_mode",
    "load_policy",
    "save_local_mode",
]

class LocalMode(StrEnum):
    """Mode d'exécution choisi par l'utilisateur au premier lancement."""
    CLOUD_ONLY = "cloud_only"   # uniquement les API cloud
    LOCAL_ONLY = "local_only"   # uniquement Ollama
    HYBRID = "hybrid"           # local existant + cloud complémentaire
    DEFAULT = "default"         # les modèles bootstrap (qwen légers)


_CONFIG_DIR = pathlib.Path.home() / ".gateway-llm"
_MODE_FILE = _CONFIG_DIR / "config.yaml"


def load_local_mode() -> LocalMode:
    """Lit le mode depuis ~/.gateway-llm/config.yaml (défaut: DEFAULT)."""
    if not _MODE_FILE.exists():
        return LocalMode.DEFAULT
    try:
        data = yaml.safe_load(_MODE_FILE.read_text(encoding="utf-8"))
        return LocalMode(data.get("local_mode", LocalMode.DEFAULT.value))
    except Exception:
        return LocalMode.DEFAULT


def save_local_mode(mode: LocalMode) -> None:
    """Persiste le mode dans ~/.gateway-llm/config.yaml."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _MODE_FILE.write_text(
        yaml.safe_dump({"local_mode": mode.value}),
        encoding="utf-8",
    )

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


# ────────────────────────────────────────────────────────────────
# Configuration par défaut (bootstrap).
#
# Utilisée quand `load_config(None)` est appelé (GUI, CLI sans --config,
# fallback utilisateur). Elle reproduit fidèlement config/models.yaml, plus
# `qwen3:4b-instruct` déclaré sous ollama pour que le classifieur
# (BatchRunner.classifier_model) soit téléchargé automatiquement.
#
# L'utilisateur avancé fournit son propre YAML via `--config`.
# ────────────────────────────────────────────────────────────────
_DEFAULT_CONFIG: dict = {
    "providers": {
        "groq": {
            "type": "openai_compat",
            "base_url": "https://api.groq.com/openai/v1",
            "secret_name": "GROQ_API_KEY",
        },
        "openrouter": {
            "type": "openai_compat",
            "base_url": "https://openrouter.ai/api/v1",
            "secret_name": "OPENROUTER_API_KEY",
            "extra_headers": {
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "gateway-llm",
            },
        },
        "mistral": {
            "type": "openai_compat",
            "base_url": "https://api.mistral.ai/v1",
            "secret_name": "MISTRAL_API_KEY",
        },
        "google_ai": {
            "type": "openai_compat",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "secret_name": "GOOGLE_API_KEY",
        },
        "ollama": {
            "type": "ollama",
            "base_url": "http://localhost:11434",
            "local": True,
            "timeout": 300,
        },
        "flexrouter": {
            "type": "openai_compat",
            "base_url": "http://localhost:4891/v1",
            "secret_name": None,  # pas de clé API
            "local": True,
        },
    },
    "models": {
        # ── Providers cloud ─────────────────────────────────────
        "qwen/qwen3.8-27b": {"provider": "groq"},
        "thinkingmachines/inkling:free": {"provider": "openrouter"},
        "mistral-large-3": {"provider": "mistral"},
        "gemma-4-31b-it": {"provider": "google_ai"},
        # ── Ollama local ────────────────────────────────────────
        "qwen3.6:27b-q4_K_M": {
            "provider": "ollama",
            "model_name": "qwen3.6:27b-q4_K_M",
            "size_gb": 16.0,
        },
        "qwen3.6:35b-a3b-mtp-q4_K_M": {
            "provider": "ollama",
            "model_name": "qwen3.6:35b-a3b-mtp-q4_K_M",
            "size_gb": 20.0,
        },
        "qwen2.5vl:7b-q4_K_M": {
            "provider": "ollama",
            "model_name": "qwen2.5vl:7b-q4_K_M",
            "size_gb": 6.0,
        },
        "nomic-embed-text": {
            "provider": "ollama",
            "model_name": "nomic-embed-text",
            "size_gb": 0.3,
        },
        # ── Classifieur (décisions de routage sémantique) ───────
        "qwen3:4b-instruct": {
            "provider": "ollama",
            "model_name": "qwen3:4b-instruct",
            "size_gb": 2.7,
        },
        # ── Classifieur (décisions de routage sémantique) ───────
        "flexrouter-low": {
            "provider": "flexrouter",
            "model_name": "low",
        },
    },
    "domains": {
        "code_debug": {
            "chain": [
                "thinkingmachines/inkling:free",
                "qwen3.6:27b-q4_K_M",
                "qwen3.6:35b-a3b-mtp-q4_K_M",
            ],
            "max_tokens": 4096,
        },
        "thinking": {
            "chain": [
                "qwen/qwen3.8-27b",
                "qwen3.6:27b-q4_K_M",
                "thinkingmachines/inkling:free",
                "qwen3.6:35b-a3b-mtp-q4_K_M",
            ],
            "max_tokens": 3072,
        },
        "problem_solving": {
            "chain": ["qwen/qwen3.8-27b", "qwen3.6:27b-q4_K_M", "qwen3.6:35b-a3b-mtp-q4_K_M"],
            "max_tokens": 3072,
        },
        "translation": {
            "chain": ["mistral-large-3", "gemma-4-31b-it", "qwen3.6:27b-q4_K_M"],
            "max_tokens": 1024,
        },
        "fact_checking": {
            "chain": ["qwen/qwen3.8-27b", "gemma-4-31b-it", "qwen3.6:27b-q4_K_M"],
            "max_tokens": 2048,
        },
        "safety": {
            "chain": ["qwen3.6:27b-q4_K_M", "qwen/qwen3.8-27b"],
            "max_tokens": 1024,
        },
        "red_teaming": {
            "chain": ["qwen3.6:27b-q4_K_M", "qwen/qwen3.8-27b"],
            "max_tokens": 1024,
        },
        "prompt_creation": {
            "chain": ["gemma-4-31b-it", "qwen3.6:27b-q4_K_M"],
            "max_tokens": 2048,
        },
        "multimodal_extraction": {
            "chain": ["gemma-4-31b-it", "qwen2.5vl:7b-q4_K_M"],
            "max_tokens": 2048,
        },
    },
}


# Politique de résidence par défaut (identique à config/policy.example.yaml).
_DEFAULT_POLICY: dict = {
    "residency": {
        "public": {
            "allowed_providers": [
                "groq",
                "openrouter",
                "mistral",
                "nvidia",
                "google_ai",
                "cloudflare",
                "ollama",
            ],
        },
        "internal": {"allowed_providers": ["mistral", "ollama"]},
        "confidential": {"allowed_providers": ["ollama"]},
    },
}


def _load_yaml(path) -> dict:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config introuvable: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{p} ne contient pas un mapping YAML")
    return data


def load_config(path: str | pathlib.Path | None = None) -> ModelsConfig:
    """Charge une configuration.

    Si `path` est None, retourne la configuration bootstrap embarquée
    (aucun fichier requis). L'utilisateur avancé fournit son propre YAML.
    """
    if path is None:
        return ModelsConfig.model_validate(_DEFAULT_CONFIG)
    return ModelsConfig.model_validate(_load_yaml(path))


def load_policy(path: str | pathlib.Path | None = None) -> PolicyConfig:
    """Charge une politique de résidence.

    Si `path` est None, retourne la politique bootstrap embarquée
    (public → cloud autorisé, internal/confidential → local).
    """
    if path is None:
        return PolicyConfig.model_validate(_DEFAULT_POLICY)
    return PolicyConfig.model_validate(_load_yaml(path))