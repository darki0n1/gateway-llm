# Copyright 2026 <VOTRE NOM / ORGANISATION>
# SPDX-License-Identifier: Apache-2.0

"""Fixtures partagées pour les tests."""

from __future__ import annotations

import pytest

from llm_gateway.config import (
    DomainChain,
    ModelConfig,
    ModelsConfig,
    ProviderConfig,
)

# Réexport pour les tests qui importent depuis conftest (fallback).
# La source de vérité est tests/helpers.py.
from .helpers import FakeProvider, make_response  # noqa: F401


@pytest.fixture
def minimal_config() -> ModelsConfig:
    return ModelsConfig(
        providers={
            "fake": ProviderConfig(
                type="openai_compat", base_url="http://fake", local=True,
            ),
        },
        models={"m1": ModelConfig(provider="fake")},
        domains={"generation": DomainChain(chain=["m1"], max_tokens=100)},
    )