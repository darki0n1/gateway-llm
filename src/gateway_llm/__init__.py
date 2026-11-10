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

"""gateway-llm — Quality-Gated Batch Router."""

from gateway_llm.budget import BudgetSnapshot, BudgetTracker
from gateway_llm.config import (
    DomainChain,
    ModelConfig,
    ModelsConfig,
    PolicyConfig,
    ProviderConfig,
    load_config,
    load_policy,
)
from gateway_llm.doctor import CheckResult, Doctor, DoctorReport, Severity
from gateway_llm.guardrails.base import Guardrail, GuardrailResult
from gateway_llm.guardrails.noop import NoOpGuardrail
from gateway_llm.installer import Installer
from gateway_llm.intake import (
    intake_from_csv,
    intake_from_folder,
    intake_from_text,
    intake_from_urls,
)
from gateway_llm.logging import configure as configure_logging
from gateway_llm.providers.base import (
    Provider,
    ProviderError,
    ProviderResponse,
    ProviderUnavailableError,
    RateLimitError,
)
from gateway_llm.providers.cloudflare import CloudflareProvider
from gateway_llm.providers.ollama import OllamaProvider
from gateway_llm.providers.openai_compat import OpenAICompatibleProvider
from gateway_llm.quota import QuotaManager
from gateway_llm.router import Router, RoutingResult
from gateway_llm.secrets import (
    EnvSecretBackend,
    PowerShellVaultBackend,
    SecretBackend,
)

__version__ = "0.2.0"

__all__ = [
    "BudgetSnapshot",
    # budget
    "BudgetTracker",
    "CheckResult",
    "CloudflareProvider",
    # doctor / installer
    "Doctor",
    "DoctorReport",
    "DomainChain",
    "EnvSecretBackend",
    # guardrails
    "Guardrail",
    "GuardrailResult",
    "Installer",
    "ModelConfig",
    "ModelsConfig",
    "NoOpGuardrail",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "PolicyConfig",
    "PowerShellVaultBackend",
    # providers
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "ProviderResponse",
    "ProviderUnavailableError",
    # quota
    "QuotaManager",
    "RateLimitError",
    # router
    "Router",
    "RoutingResult",
    # secrets
    "SecretBackend",
    "Severity",
    "__version__",
    # logging
    "configure_logging",
    "intake_from_csv",
    "intake_from_folder",
    "intake_from_text",
    "intake_from_urls",
    # config
    "load_config",
    "load_policy",
]
