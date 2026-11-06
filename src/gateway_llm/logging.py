# SPDX-FileCopyrightText: 2026 Amandine Dennieau
# SPDX-License-Identifier: Apache-2.0

"""Configuration du logging pour gateway_llm.

Comportement par défaut : bibliothèque silencieuse (NullHandler sur le
logger racine du package). L'application hôte (ou le CLI) appelle
`configure()` pour brancher les handlers et le niveau.
"""

from __future__ import annotations

import logging
from logging.config import dictConfig

PACKAGE_LOGGER_NAME = "gateway_llm"

# ─── NullHandler : la bibliothèque ne crie pas toute seule ─────────────────
_pkg_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
if not any(isinstance(h, logging.NullHandler) for h in _pkg_logger.handlers):
    _pkg_logger.addHandler(logging.NullHandler())


def configure(
    level: str = "INFO",
    fmt: str = "text",
    stream: str = "stderr",
) -> None:
    """Configure le logging pour le CLI (ou un script hôte).

    Args:
        level: DEBUG / INFO / WARNING / ERROR
        fmt: "text" (lisible) ou "json" (structuré, pour CI/logs)
        stream: "stdout" ou "stderr"
    """
    handlers_cfg = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": f"ext://sys.{stream}",
            "formatter": "json" if fmt == "json" else "text",
        },
    }
    formatters_cfg = {
        "text": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%H:%M:%S",
        },
        "json": {
            "format": '{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}',
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    }
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters_cfg,
            "handlers": handlers_cfg,
            "loggers": {
                PACKAGE_LOGGER_NAME: {
                    "level": level,
                    "handlers": ["console"],
                    "propagate": False,
                },
            },
        }
    )
