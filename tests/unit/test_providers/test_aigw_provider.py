"""Unit tests for AigwProvider.

All tests mock the AsyncOpenAI client and httpx — no gateway is required.
aigw is the keyed OpenAI-compatible gateway provider (AIGW_API_KEY,
http://localhost:11433/v1).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("openai", reason="openai SDK not installed")

from repowise.core.providers.llm.aigw import AigwProvider
from repowise.core.providers.llm.base import GeneratedResponse, ProviderError

_DEFAULT_MODEL = "glm-coding-flash"


@pytest.fixture(autouse=True)
def _clean_aigw_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AIGW_API_KEY", raising=False)
    monkeypatch.delenv("AIGW_BASE_URL", raising=False)


def test_missing_api_key_raises():
    with pytest.raises(ProviderError):
        AigwProvider()


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("AIGW_API_KEY", "sk-gw")
    p = AigwProvider()
    assert p.provider_name == "aigw"
    assert p._api_key == "sk-gw"


def test_explicit_api_key_wins_over_env(monkeypatch):
    monkeypatch.setenv("AIGW_API_KEY", "sk-env")
    p = AigwProvider(api_key="sk-explicit")
    assert p._api_key == "sk-explicit"


def test_default_model():
    p = AigwProvider(api_key="sk-gw")
    assert p.model_name == _DEFAULT_MODEL


def test_default_base_url_includes_v1():
    p = AigwProvider(api_key="sk-gw")
    assert p._base_url == "http://localhost:11433/v1"


def test_base_url_env_override_is_used_verbatim(monkeypatch):
    """aigw does no /v1 rewriting — the operator's URL is taken as given."""
    monkeypatch.setenv("AIGW_BASE_URL", "http://gw.internal:9000/openai")
    p = AigwProvider(api_key="sk-gw")
    assert p._base_url == "http://gw.internal:9000/openai"


def test_interactive_timeout_is_the_remote_default():
    """aigw fronts remote models — the 60s class budget, not omlx's 120s."""
    p = AigwProvider(api_key="sk-gw")
    assert p.interactive_timeout_s == 60.0


def test_available_model_options_uses_models_endpoint(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"data": [{"id": "glm-coding-flash"}, {"id": "glm-coding-air"}]}

    captured: dict[str, object] = {}

    def fake_get(url, *, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("httpx.get", fake_get)

    options = AigwProvider(api_key="sk-gw").available_model_options()

    assert captured["url"] == "http://localhost:11433/v1/models"
    assert captured["headers"] == {"Authorization": "Bearer sk-gw"}
    assert [option.model for option in options] == ["glm-coding-flash", "glm-coding-air"]


def test_available_model_options_fall_back_when_listing_fails(monkeypatch):
    """The gateway 404s /v1/models in practice — the configured model stands in."""

    def fake_get(url, *, headers, timeout):
        raise ConnectionError("gateway down")

    monkeypatch.setattr("httpx.get", fake_get)

    options = AigwProvider(api_key="sk-gw").available_model_options()

    assert len(options) == 1
    assert options[0].model == _DEFAULT_MODEL
    assert options[0].source == "fallback"


def _make_mock_chat_response(text: str = "pong") -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15

    choice = MagicMock()
    choice.message.content = text
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


async def test_generate_returns_generated_response():
    provider = AigwProvider(api_key="sk-gw")

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(
            return_value=_make_mock_chat_response("Hello from aigw")
        )
        provider._client = mock_client.return_value

        result = await provider.generate(system_prompt="system", user_prompt="user")

    assert isinstance(result, GeneratedResponse)
    assert result.content == "Hello from aigw"
    assert result.input_tokens == 10
    assert result.output_tokens == 5


async def test_generate_passes_temperature_through():
    provider = AigwProvider(api_key="sk-gw")

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(
            return_value=_make_mock_chat_response()
        )
        provider._client = mock_client.return_value

        await provider.generate("system", "user", temperature=0.3)

    kwargs = mock_client.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.3


async def test_generate_rejects_explicit_reasoning():
    provider = AigwProvider(api_key="sk-gw")

    with patch("openai.AsyncOpenAI") as mock_client:
        provider._client = mock_client.return_value
        with pytest.raises(ProviderError, match="reasoning='off' is not supported"):
            await provider.generate("system", "user", reasoning="off")

    mock_client.return_value.chat.completions.create.assert_not_called()


async def test_cost_tracker_records_prefixed_model():
    """The gateway meters upstream spend itself — aigw/* is recorded at $0."""
    from repowise.core.generation.cost_tracker import CostTracker

    mock_tracker = MagicMock(spec=CostTracker)
    mock_tracker.record = AsyncMock(return_value=0.0)

    provider = AigwProvider(api_key="sk-gw", cost_tracker=mock_tracker)

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(
            return_value=_make_mock_chat_response()
        )
        provider._client = mock_client.return_value

        await provider.generate("system", "user")

    mock_tracker.record.assert_called_once()
    call_kwargs = mock_tracker.record.call_args.kwargs
    assert call_kwargs["model"] == f"aigw/{_DEFAULT_MODEL}"
    assert call_kwargs["input_tokens"] == 10
    assert call_kwargs["output_tokens"] == 5
