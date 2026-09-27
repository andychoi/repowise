"""The omlx embedder must be selectable on every surface the CLI exposes.

The chat-provider surfaces are pinned by registry drift guards; these are the
embedder-side surfaces no guard covered when omlx shipped — `reindex
--embedder omlx`, the advanced-mode and index-only interactive choices, and
the advanced prompt's env-based default.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

pytest.importorskip("openai", reason="openai SDK not installed")

from repowise.cli.main import cli
from repowise.cli.ui import mode_selection


def test_reindex_accepts_omlx_embedder():
    """`reindex --embedder omlx` must pass flag validation — the docs promise it."""
    result = CliRunner().invoke(cli, ["reindex", "--embedder", "omlx", "/definitely/not/a/repo"])
    assert "Invalid value for '--embedder'" not in result.output


def test_advanced_mode_embedder_choices_include_omlx():
    assert "omlx" in mode_selection.ADVANCED_EMBEDDER_CHOICES


def test_index_only_embedder_choices_include_omlx():
    assert "omlx" in mode_selection.INDEX_ONLY_EMBEDDER_CHOICES


def test_advanced_embedder_env_detection_sees_omlx(monkeypatch):
    """The advanced prompt's default must match the shared resolver: omlx."""
    for var in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "OLLAMA_EMBEDDING_MODEL",
        "EDENAI_API_KEY",
        "OMLX_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("repowise.cli.providers.keys.global_config_embedder", lambda: None)
    monkeypatch.setenv("OMLX_EMBEDDING_MODEL", "Qwen3-Embedding-0.6B-4bit-DWQ")
    assert mode_selection._resolve_embedder_from_env() == "omlx"
