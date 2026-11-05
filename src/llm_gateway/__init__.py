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

"""llm-gateway — Quality-Gated Batch Router."""

from llm_gateway.doctor import CheckResult, Doctor, DoctorReport, Severity
from llm_gateway.installer import Installer
from llm_gateway.config import (
    DomainChain,
    ModelConfig,
    ModelsConfig,
    PolicyConfig,
    ProviderConfig,
    load_config,
    load_policy,
)
from llm_gateway.guardrails.base import Guardrail, GuardrailResult
from llm_gateway.guardrails.noop import NoOpGuardrail
from llm_gateway.logging import configure as configure_logging
from llm_gateway.providers.base import (
    Provider,
    ProviderError,
    ProviderResponse,
    ProviderUnavailableError,
    RateLimitError,
)
from llm_gateway.providers.cloudflare import CloudflareProvider
from llm_gateway.providers.ollama import OllamaProvider
from llm_gateway.providers.openai_compat import OpenAICompatibleProvider
from llm_gateway.budget import BudgetSnapshot, BudgetTracker
from llm_gateway.policy import PolicyConfig
from llm_gateway.quota import QuotaManager
from llm_gateway.router import Router, RoutingResult
from llm_gateway.secrets import (
    EnvSecretBackend,
    PowerShellVaultBackend,
    SecretBackend,
)
from llm_gateway.intake import (
    intake_from_csv, intake_from_folder, intake_from_text, intake_from_urls,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # doctor / installer
    "Doctor", "DoctorReport", "CheckResult", "Severity", "Installer",
    # config
    "load_config", "load_policy",
    "ModelsConfig", "ModelConfig", "ProviderConfig", "DomainChain", "PolicyConfig",
    # router
    "Router", "RoutingResult",
    # quota
    "QuotaManager",
    # budget
    "BudgetTracker", "BudgetSnapshot", "PolicyConfig",
    # providers
    "Provider", "ProviderResponse",
    "ProviderError", "ProviderUnavailableError", "RateLimitError",
    "OpenAICompatibleProvider", "OllamaProvider", "CloudflareProvider",
    # guardrails
    "Guardrail", "GuardrailResult", "NoOpGuardrail",
    # secrets
    "SecretBackend", "EnvSecretBackend", "PowerShellVaultBackend",
    # logging
    "configure_logging",
    "intake_from_folder", "intake_from_text", "intake_from_csv", "intake_from_urls",    
]