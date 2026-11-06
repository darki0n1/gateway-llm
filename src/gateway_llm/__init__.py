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

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # doctor / installer
    "Doctor",
    "DoctorReport",
    "CheckResult",
    "Severity",
    "Installer",
    # config
    "load_config",
    "load_policy",
    "ModelsConfig",
    "ModelConfig",
    "ProviderConfig",
    "DomainChain",
    "PolicyConfig",
    # router
    "Router",
    "RoutingResult",
    # quota
    "QuotaManager",
    # budget
    "BudgetTracker",
    "BudgetSnapshot",
    "PolicyConfig",
    # providers
    "Provider",
    "ProviderResponse",
    "ProviderError",
    "ProviderUnavailableError",
    "RateLimitError",
    "OpenAICompatibleProvider",
    "OllamaProvider",
    "CloudflareProvider",
    # guardrails
    "Guardrail",
    "GuardrailResult",
    "NoOpGuardrail",
    # secrets
    "SecretBackend",
    "EnvSecretBackend",
    "PowerShellVaultBackend",
    # logging
    "configure_logging",
    "intake_from_folder",
    "intake_from_text",
    "intake_from_csv",
    "intake_from_urls",
]
