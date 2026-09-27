"""omlx provider for repowise.

Access local models served by the OMLX runtime via its OpenAI-compatible
endpoint (http://localhost:11434). The API is fully OpenAI-compatible — this
provider uses the openai Python SDK with a custom base_url, following the same
pattern as KimiProvider and DeepSeekProvider.

No API key required for local deployments; an optional OMLX_API_KEY is honored
when the server enforces one. The /v1 suffix is appended to the base URL
automatically if missing.

Models:
    - Qwen3.5-9B-MTPLX-Optimized-Speed      — speed-optimized local chat model [default]

omlx also serves an embedding model (Qwen3-Embedding-0.6B-4bit-DWQ); embedding
ids are filtered out of the chat model listing — use the ``omlx`` embedder for
those (see repowise.core.providers.embedding.omlx).
"""

from __future__ import annotations

import os
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

_DEFAULT_BASE_URL = "http://localhost:11434"
_DUMMY_API_KEY = "omlx"


def _normalize_base_url(url: str) -> str:
    """Ensure base_url ends with /v1 for OpenAI SDK compatibility."""
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _is_chat_model(model_id: str) -> bool:
    """The /v1/models listing also names the embedding model; keep chat ids only."""
    return "embedding" not in model_id.lower()


def _omlx_notes(model_id: str, reasoning_modes: tuple[ReasoningMode, ...]) -> str:
    return ""


def _omlx_model_options(
    api_key: str,
    base_url: str,
    fallback_model: str,
) -> tuple[ProviderModelOption, ...]:
    return listed_model_options(
        api_key,
        base_url,
        fallback_model,
        reasoning_modes_for=lambda model: (),
        notes_for=_omlx_notes,
        model_filter=_is_chat_model,
    )


class OmlxProvider(OpenAICompatibleProvider):
    """omlx provider — local models via the OMLX OpenAI-compatible API.

    Args:
        model:        Model identifier. Defaults to Qwen3.5-9B-MTPLX-Optimized-Speed.
        api_key:      Optional API key for servers that enforce one. Falls back
                      to the OMLX_API_KEY env var, then to a dummy bearer.
        base_url:     omlx server URL. Defaults to http://localhost:11434.
                      The /v1 suffix is appended automatically if missing.
        rate_limiter: Optional RateLimiter instance.
        cost_tracker: Optional CostTracker instance for usage recording.
    """

    provider_id = "omlx"
    api_key_env = "OMLX_API_KEY"
    base_url_env = "OMLX_BASE_URL"
    default_base_url = _DEFAULT_BASE_URL
    reasoning_detail = (
        "omlx /v1/models lists IDs only; Qwen3.5 thinking controls are left "
        "at the server default."
    )
    # Generation speed is the user's own hardware and a cold model pays a load
    # from disk — the same budget ollama gets (see OllamaProvider).
    interactive_timeout_s = 120.0
    cost_model_prefix = "omlx/"

    def __init__(
        self,
        model: str = "Qwen3.5-9B-MTPLX-Optimized-Speed",
        api_key: str | None = None,
        base_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        # Keyless by design: the base __init__ raises ProviderError without a
        # key, so supply the dummy the SDK requires — the same trick ollama
        # uses (api_key="ollama"). The dummy also short-circuits the base
        # class's env read, so the optional OMLX_API_KEY is resolved here.
        super().__init__(
            api_key or os.environ.get(self.api_key_env) or _DUMMY_API_KEY,
            model,
            base_url,
            rate_limiter,
            cost_tracker,
        )

    def _clean_base_url(self, base_url: str) -> str:
        return _normalize_base_url(base_url)

    def available_model_options(self) -> tuple[ProviderModelOption, ...]:
        return _omlx_model_options(self._api_key, self._base_url, self._model)

    def _explicit_reasoning_modes(self, model: str) -> tuple[ReasoningMode, ...]:
        return ()

    def _reasoning_kwargs(self, reasoning: ReasoningMode) -> dict[str, Any]:
        return {}
