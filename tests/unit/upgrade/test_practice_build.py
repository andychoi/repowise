"""A practice (fork) build must never be told to upgrade from PyPI.

Client servers run ``<upstream>+aai.<n>`` builds from a practice wheelhouse.
When upstream publishes a newer release the CLI's update notice suggested
``pip install -U repowise`` / ``uv tool upgrade repowise``, which silently
replaces the fork with stock and drops every fix. Separately, ``parse_release``
documented that local suffixes are ignored but read ``0.53.0+aai.1`` as
``(0, 53, 0, 1)``.
"""

from __future__ import annotations

from repowise.cli import update_check
from repowise.core.upgrade.release import is_newer_version, is_practice_build, parse_release


def test_the_local_segment_is_not_a_release_component() -> None:
    assert parse_release("0.53.0+aai.1") == (0, 53, 0)
    assert parse_release("0.53.0+aai.12") == parse_release("0.53.0")


def test_a_practice_build_compares_as_its_upstream_release() -> None:
    assert not is_newer_version("0.53.0", "0.53.0+aai.1")
    assert is_newer_version("0.54.0", "0.53.0+aai.1")


def test_practice_builds_are_recognized_by_their_local_tag() -> None:
    assert is_practice_build("0.53.0+aai.1")
    assert not is_practice_build("0.53.0")
    assert not is_practice_build("0.53.0+local.1")


def test_a_practice_build_is_told_to_use_the_wheelhouse(monkeypatch) -> None:
    advice, hint = update_check._upgrade_advice("0.53.0+aai.1", "/usr/bin/repowise", "python3")

    assert hint == "practice_build"
    assert "wheelhouse" in advice
    assert "would replace this build" in advice


def test_a_stock_build_keeps_the_normal_advice(monkeypatch) -> None:
    monkeypatch.setattr(update_check, "_editable_checkout", lambda: None)

    advice, hint = update_check._upgrade_advice("0.53.0", "/usr/bin/repowise", "python3")

    assert hint != "practice_build"
    assert "wheelhouse" not in advice
