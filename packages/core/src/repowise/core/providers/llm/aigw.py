"""aigw provider for repowise.

Access models behind the aigw gateway via its OpenAI-compatible endpoint
(default http://localhost:11433/v1). The API is fully OpenAI-compatible — this
provider uses the openai Python SDK with a custom base_url, following the same
pattern as KimiProvider.

The gateway requires a key (AIGW_API_KEY) and meters the real upstream spend
itself, so repowise records aigw/* generations at $0.00 — the claude_cli
subscription precedent, not ollama-style local inference.

Models:
    - glm-coding-flash — coding model routed by the gateway [default]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from repowise.core.providers.llm.base import ProviderModelOption
from repowise.core.providers.llm.openai_compat import (
    OpenAICompatibleProvider,
    listed_model_options,
)
from repowise.core.rate_limiter import RateLimiter
from repowise.core.reasoning import ReasoningMode

if TYPE_CHECKING:
    from repowise.core.generation.cost_tracker import CostTracker

_DEFAULT_BASE_URL = "http://localhost:11433/v1"
_DEFAULT_MODEL = "glm-coding-flash"


class AigwProvider(OpenAICompatibleProvider):
    """aigw provider — gateway models via an OpenAI-compatible API.

    Args:
        api_key:      Gateway API key. Falls back to the AIGW_API_KEY env var.
        model:        Model identifier. Defaults to glm-coding-flash.
        base_url:     Gateway URL. Defaults to http://localhost:11433/v1; an
                      AIGW_BASE_URL override is used verbatim (include /v1).
        rate_limiter: Optional RateLimiter instance.
        cost_tracker: Optional CostTracker instance for usage recording.
    """

    provider_id = "aigw"
    api_key_env = "AIGW_API_KEY"
    base_url_env = "AIGW_BASE_URL"
    default_base_url = _DEFAULT_BASE_URL
    reasoning_detail = (
        "aigw /v1/models may not list IDs; thinking controls stay at the "
        "gateway's server default."
    )
    cost_model_prefix = "aigw/"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        base_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url, rate_limiter, cost_tracker)

    def available_model_options(self) -> tuple[ProviderModelOption, ...]:
        # The gateway may not expose /v1/models at all; listed_model_options
        # falls back to the configured model on any listing failure.
        return listed_model_options(
            self._api_key,
            self._base_url,
            self._model,
            reasoning_modes_for=lambda model: (),
            notes_for=lambda model_id, modes: "",
        )

    def _explicit_reasoning_modes(self, model: str) -> tuple[ReasoningMode, ...]:
        return ()

    def _reasoning_kwargs(self, reasoning: ReasoningMode) -> dict[str, Any]:
        return {}
