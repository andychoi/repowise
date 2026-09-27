"""Unit tests for OmlxProvider.

All tests mock the AsyncOpenAI client and httpx — no local server is required.
omlx is the keyless local OpenAI-compatible provider (OMLX backend at
http://localhost:11434).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("openai", reason="openai SDK not installed")

from repowise.core.providers.llm.base import GeneratedResponse, ProviderError
from repowise.core.providers.llm.omlx import OmlxProvider

_DEFAULT_MODEL = "Qwen3.5-9B-MTPLX-Optimized-Speed"


@pytest.fixture(autouse=True)
def _clean_omlx_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OMLX_API_KEY", raising=False)
    monkeypatch.delenv("OMLX_BASE_URL", raising=False)


def test_keyless_construction_needs_no_api_key():
    p = OmlxProvider()
    assert p.provider_name == "omlx"
    assert p._api_key == "omlx"  # dummy bearer, the ollama trick


def test_default_model():
    p = OmlxProvider()
    assert p.model_name == _DEFAULT_MODEL


def test_optional_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OMLX_API_KEY", "sk-real")
    p = OmlxProvider()
    assert p._api_key == "sk-real"


def test_explicit_api_key_wins_over_env(monkeypatch):
    monkeypatch.setenv("OMLX_API_KEY", "sk-env")
    p = OmlxProvider(api_key="sk-explicit")
    assert p._api_key == "sk-explicit"


def test_base_url_gets_v1_appended():
    p = OmlxProvider()
    assert p._base_url == "http://localhost:11434/v1"


def test_base_url_v1_not_doubled():
    p = OmlxProvider(base_url="http://localhost:11434/v1")
    assert p._base_url == "http://localhost:11434/v1"


def test_base_url_trailing_slash_normalized():
    p = OmlxProvider(base_url="http://mlbox.local:11434/")
    assert p._base_url == "http://mlbox.local:11434/v1"


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("OMLX_BASE_URL", "http://mlbox.local:11434")
    p = OmlxProvider()
    assert p._base_url == "http://mlbox.local:11434/v1"


def test_interactive_timeout_is_ollamas_local_budget():
    assert OmlxProvider.interactive_timeout_s == 120.0


def test_available_model_options_filter_embedding_ids(monkeypatch):
    """The /v1/models listing also names the embedding model; keep chat ids."""

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "data": [
                    {"id": _DEFAULT_MODEL},
                    {"id": "Qwen3-Embedding-0.6B-4bit-DWQ"},
                ]
            }

    captured: dict[str, object] = {}

    def fake_get(url, *, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)

    options = OmlxProvider().available_model_options()

    assert captured["url"] == "http://localhost:11434/v1/models"
    assert captured["headers"] == {"Authorization": "Bearer omlx"}
    assert [option.model for option in options] == [_DEFAULT_MODEL]
    assert options[0].recommended is True


def test_available_model_options_fall_back_when_listing_fails(monkeypatch):
    def fake_get(url, *, headers, timeout):
        raise ConnectionError("server down")

    monkeypatch.setattr("httpx.get", fake_get)

    options = OmlxProvider().available_model_options()

    assert len(options) == 1
    assert options[0].model == _DEFAULT_MODEL
    assert options[0].source == "fallback"


def _make_mock_chat_response(
    text: str = "# Doc\nContent.",
    *,
    finish_reason: str = "stop",
) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = 120
    usage.completion_tokens = 60
    usage.total_tokens = 180

    choice = MagicMock()
    choice.message.content = text
    choice.finish_reason = finish_reason

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


async def test_generate_returns_generated_response():
    provider = OmlxProvider()
    mock_response = _make_mock_chat_response("Hello from omlx")

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client.return_value

        result = await provider.generate(system_prompt="system", user_prompt="user")

    assert isinstance(result, GeneratedResponse)
    assert result.content == "Hello from omlx"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 120
    assert result.output_tokens == 60


async def test_generate_passes_temperature_through():
    provider = OmlxProvider()
    mock_response = _make_mock_chat_response()

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client.return_value

        await provider.generate("system", "user", temperature=0.3)

    kwargs = mock_client.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.3
    assert "extra_body" not in kwargs


async def test_generate_rejects_explicit_reasoning():
    provider = OmlxProvider()

    with patch("openai.AsyncOpenAI") as mock_client:
        provider._client = mock_client.return_value
        with pytest.raises(ProviderError, match="reasoning='off' is not supported"):
            await provider.generate("system", "user", reasoning="off")

    mock_client.return_value.chat.completions.create.assert_not_called()


async def test_cost_tracker_records_prefixed_local_model():
    """omlx is local hardware — the omlx/ prefix prices it at $0."""
    from repowise.core.generation.cost_tracker import CostTracker

    mock_tracker = MagicMock(spec=CostTracker)
    mock_tracker.record = AsyncMock(return_value=0.0)

    provider = OmlxProvider(cost_tracker=mock_tracker)
    mock_response = _make_mock_chat_response()

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client.return_value

        await provider.generate("system", "user")

    mock_tracker.record.assert_called_once()
    call_kwargs = mock_tracker.record.call_args.kwargs
    assert call_kwargs["model"] == f"omlx/{_DEFAULT_MODEL}"
    assert call_kwargs["input_tokens"] == 120
    assert call_kwargs["output_tokens"] == 60
