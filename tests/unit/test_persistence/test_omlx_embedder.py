"""Unit tests for OmlxEmbedder.

All tests mock the openai SDK client — no local server is required.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai", reason="openai SDK not installed")

from repowise.core.providers.embedding.omlx import OmlxEmbedder

_DEFAULT_MODEL = "Qwen3-Embedding-0.6B-4bit-DWQ"


@pytest.fixture(autouse=True)
def _clean_omlx_env(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "OMLX_API_KEY",
        "OMLX_BASE_URL",
        "OMLX_EMBEDDING_MODEL",
        "OMLX_EMBEDDING_DIMS",
        "OMLX_EMBEDDING_TIMEOUT",
        "REPOWISE_EMBEDDING_MODEL",
        "REPOWISE_EMBEDDING_DIMS",
        "REPOWISE_EMBEDDING_TIMEOUT",
        "REPOWISE_EMBEDDING_DECLARED_DIMS",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_registry_lists_omlx() -> None:
    from repowise.core.providers.embedding.registry import get_embedder, list_embedders

    assert "omlx" in list_embedders()
    assert isinstance(get_embedder("omlx"), OmlxEmbedder)


def test_default_model_and_dims() -> None:
    embedder = OmlxEmbedder()
    assert embedder._model == _DEFAULT_MODEL
    # The regression: "4bit" contains "4b", which OllamaEmbedder's name
    # inference would read as the 4B model's 2560. The declared width is 1024.
    assert embedder.dimensions == 1024


def test_dims_from_omlx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_EMBEDDING_DIMS", "1536")
    assert OmlxEmbedder().dimensions == 1536


def test_dims_from_repowise_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOWISE_EMBEDDING_DIMS", "512")
    assert OmlxEmbedder().dimensions == 512


def test_omlx_dims_env_beats_repowise_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_EMBEDDING_DIMS", "1536")
    monkeypatch.setenv("REPOWISE_EMBEDDING_DIMS", "512")
    assert OmlxEmbedder().dimensions == 1536


def test_base_url_gets_v1_appended() -> None:
    assert OmlxEmbedder()._base_url == "http://localhost:11434/v1"
    assert OmlxEmbedder(base_url="http://mlbox.local:11434")._base_url == (
        "http://mlbox.local:11434/v1"
    )
    assert OmlxEmbedder(base_url="http://mlbox.local:11434/v1/")._base_url == (
        "http://mlbox.local:11434/v1"
    )


def test_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_BASE_URL", "http://mlbox.local:11434")
    assert OmlxEmbedder()._base_url == "http://mlbox.local:11434/v1"


def test_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_EMBEDDING_MODEL", "bge-m3")
    assert OmlxEmbedder()._model == "bge-m3"


def test_dummy_bearer_when_keyless() -> None:
    embedder = OmlxEmbedder()
    assert embedder._api_key == "omlx"


def test_optional_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_API_KEY", "sk-real")
    assert OmlxEmbedder()._api_key == "sk-real"


def test_timeout_defaults_to_thirty_seconds() -> None:
    assert OmlxEmbedder()._timeout == 30.0


def test_timeout_from_omlx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_EMBEDDING_TIMEOUT", "120")
    assert OmlxEmbedder()._timeout == 120.0


def test_timeout_explicit_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMLX_EMBEDDING_TIMEOUT", "120")
    assert OmlxEmbedder(timeout=5.0)._timeout == 5.0


def _mock_openai_client(width: int = 1024) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    vector = [1.0] + [0.0] * (width - 1)
    client.embeddings.create.return_value.data = [MagicMock(embedding=vector)]
    return client, MagicMock(return_value=client)


async def test_embed_posts_to_v1_embeddings_with_declared_width_only() -> None:
    client, ctor = _mock_openai_client()

    with patch("openai.OpenAI", ctor):
        embedder = OmlxEmbedder()
        vectors = await embedder.embed(["hello"])

    ctor.assert_called_once()
    ctor_kwargs = ctor.call_args.kwargs
    assert ctor_kwargs["api_key"] == "omlx"
    assert ctor_kwargs["base_url"] == "http://localhost:11434/v1"
    assert ctor_kwargs["timeout"] == 30.0

    create_kwargs = client.embeddings.create.call_args.kwargs
    assert create_kwargs == {"model": _DEFAULT_MODEL, "input": ["hello"]}
    assert "dimensions" not in create_kwargs  # declared, never sent
    assert len(vectors) == 1
    assert abs(math.sqrt(sum(x * x for x in vectors[0])) - 1.0) < 1e-6


async def test_embed_uses_real_key_and_dims_override_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMLX_API_KEY", "sk-real")
    monkeypatch.setenv("OMLX_EMBEDDING_DIMS", "8")
    client, ctor = _mock_openai_client(width=8)

    with patch("openai.OpenAI", ctor):
        await OmlxEmbedder().embed(["hello"])

    assert ctor.call_args.kwargs["api_key"] == "sk-real"
    create_kwargs = client.embeddings.create.call_args.kwargs
    # An explicit dims override IS sent, for servers that accept reshaping.
    assert create_kwargs["dimensions"] == 8


async def test_embed_raises_when_server_returns_wrong_width() -> None:
    _client, ctor = _mock_openai_client(width=2560)

    with patch("openai.OpenAI", ctor):
        embedder = OmlxEmbedder()
        with pytest.raises(ValueError, match="1024"):
            await embedder.embed(["hello"])


async def test_embed_empty_returns_empty() -> None:
    assert await OmlxEmbedder().embed([]) == []
