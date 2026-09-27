"""omlx embedding support for repowise semantic search.

Uses omlx's OpenAI-compatible ``/v1/embeddings`` endpoint for the local
Qwen3-Embedding model. Complements the ``omlx`` chat provider — one local
server, two registries.

The DWQ quantized model's width is fixed (1024, the Qwen3-Embedding-0.6B
native width), and the width is *declared* rather than sent as the API's
``dimensions`` parameter — a fixed-width model that rejects the parameter
must never receive it (see ``OpenAIEmbedder.declared_dimensions``).

Env vars:
    OMLX_EMBEDDING_MODEL    model id (default Qwen3-Embedding-0.6B-4bit-DWQ)
    OMLX_EMBEDDING_DIMS     width override, also sent as the API's
                            ``dimensions`` parameter (REPOWISE_EMBEDDING_DIMS
                            works too, with lower precedence)
    OMLX_EMBEDDING_TIMEOUT  per-request seconds (default 30)
    OMLX_BASE_URL           server URL; /v1 appended if missing
    OMLX_API_KEY            optional; only for servers that enforce one
"""

from __future__ import annotations

import os

from repowise.core.providers.embedding.base import resolve_embedding_timeout
from repowise.core.providers.embedding.openai import OpenAIEmbedder, _parse_dimensions_env

_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_MODEL = "Qwen3-Embedding-0.6B-4bit-DWQ"
# Qwen3-Embedding-0.6B's native width (measured against this server). Declared
# explicitly — the model name contains "4bit", and OllamaEmbedder's "4b"
# substring inference would misread that as the 4B model's 2560.
_DEFAULT_DIMS = 1024
_DEFAULT_TIMEOUT = 30.0
_DUMMY_API_KEY = "omlx"


def _normalize_base_url(url: str) -> str:
    """Ensure base_url ends with /v1 for the OpenAI SDK's embeddings path."""
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


class OmlxEmbedder(OpenAIEmbedder):
    """omlx embedding adapter implementing the repowise Embedder protocol.

    Keyless by design: a dummy bearer is used unless OMLX_API_KEY is set.

    Args:
        model: Embedding model id. Falls back to OMLX_EMBEDDING_MODEL /
            REPOWISE_EMBEDDING_MODEL, then Qwen3-Embedding-0.6B-4bit-DWQ.
        base_url: omlx server URL. Falls back to OMLX_BASE_URL, then
            http://localhost:11434/v1. The /v1 suffix is appended if missing.
        dimensions: Width override; also sent to the API as ``dimensions``.
            Falls back to OMLX_EMBEDDING_DIMS / REPOWISE_EMBEDDING_DIMS.
        declared_dimensions: Width declared *without* sending the parameter.
            Defaults to 1024; ignored when ``dimensions`` is set.
        timeout: Per-request seconds. Falls back to OMLX_EMBEDDING_TIMEOUT /
            REPOWISE_EMBEDDING_TIMEOUT, then 30.0 — local GPU work needs more
            than the hosted default.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        declared_dimensions: int | None = None,
        timeout: float | None = None,
    ) -> None:
        resolved_model = (
            model
            or os.environ.get("OMLX_EMBEDDING_MODEL")
            or os.environ.get("REPOWISE_EMBEDDING_MODEL")
            or _DEFAULT_MODEL
        )
        if dimensions is None:
            env = os.environ.get("OMLX_EMBEDDING_DIMS")
            if env:
                dimensions = _parse_dimensions_env(env)
        # The width is fixed, so declare it without ever sending the API's
        # 'dimensions' parameter; an explicit dimensions override still wins
        # (base precedence), for servers that do accept reshaping.
        resolved_timeout = resolve_embedding_timeout(
            timeout, _DEFAULT_TIMEOUT, provider_env="OMLX_EMBEDDING_TIMEOUT"
        )
        super().__init__(
            api_key=os.environ.get("OMLX_API_KEY") or _DUMMY_API_KEY,
            model=resolved_model,
            base_url=_normalize_base_url(
                base_url or os.environ.get("OMLX_BASE_URL") or _DEFAULT_BASE_URL
            ),
            timeout=resolved_timeout,
            dimensions=dimensions,
            declared_dimensions=declared_dimensions if declared_dimensions is not None else _DEFAULT_DIMS,
        )
