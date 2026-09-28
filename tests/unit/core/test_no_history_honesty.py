"""A repository with no version-control history must say so (E2, E3).

Indexing a plain directory (a source export, a legacy code drop) skips git
indexing with a warning and carries on. The receipt then claimed the tier it
was *configured* for (``git_tier: "full"``) and ``repowise health`` reported a
perfect ``hotspot_health`` of 10.0 over files that had never been measured.
Both read as good news when the truth is "no data". These tests pin the honest
answers: history is recorded as unavailable, the scope says so, and the
history-derived KPIs are null with a basis a caller can branch on.
"""

from __future__ import annotations

from types import SimpleNamespace

from repowise.cli.commands.init_cmd.persistence import apply_git_history_coverage_state
from repowise.core.analysis.health.scoring import present_kpis
from repowise.core.index_scope import resolve_index_scope

# ---------------------------------------------------------------------------
# E2: the receipt records history that was never read as unavailable
# ---------------------------------------------------------------------------


def test_a_skipped_git_stage_is_recorded_as_unavailable() -> None:
    state = {"git_tier": "full", "git_history_coverage": {"stale": True}}

    apply_git_history_coverage_state(state, SimpleNamespace(git_summary=None))

    assert state["git_history"] == "unavailable"
    assert "git_history_coverage" not in state
    # The tier stays: it is the resume policy `repowise update` parses.
    assert state["git_tier"] == "full"


def test_the_indexer_says_why_it_read_no_history(tmp_path) -> None:
    """A plain directory returns the same zero summary as a quiet repo, so the
    summary itself has to carry the difference."""
    import asyncio

    from repowise.core.ingestion.git_indexer import GitIndexer

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    summary, rows = asyncio.run(GitIndexer(tmp_path).index_repo(""))

    assert rows == []
    assert summary.history_status == "no_repository"


def test_an_empty_summary_from_a_plain_directory_is_unavailable() -> None:
    summary = SimpleNamespace(history_status="no_repository", history_coverage=None)
    state = {"git_tier": "full"}

    apply_git_history_coverage_state(state, SimpleNamespace(git_summary=summary))

    assert state["git_history"] == "unavailable"
    assert state["git_history_reason"] == "no_repository"


def test_a_later_run_with_history_clears_the_flag() -> None:
    coverage = SimpleNamespace(to_dict=lambda: {"files_with_history": 3})
    state = {"git_history": "unavailable"}

    apply_git_history_coverage_state(
        state, SimpleNamespace(git_summary=SimpleNamespace(history_coverage=coverage))
    )

    assert "git_history" not in state
    assert state["git_history_coverage"] == {"files_with_history": 3}


def test_the_scope_reports_no_git_tier_and_names_the_missing_analysis() -> None:
    scope = resolve_index_scope({"git_tier": "full", "git_history": "unavailable"})

    assert scope["git_tier"] == "none"
    assert "git_history" in scope["analysis"]["unavailable"]


def test_a_repository_with_history_keeps_its_tier() -> None:
    scope = resolve_index_scope({"git_tier": "full"})

    assert scope["git_tier"] == "full"
    assert "git_history" not in scope["analysis"]["unavailable"]


# ---------------------------------------------------------------------------
# E3: history-derived KPIs are null, with a basis, when nothing was measured
# ---------------------------------------------------------------------------


def _floored_kpis() -> dict:
    # What compute_kpis returns for the snapshot column: hotspot floored to 10.0.
    return {
        "hotspot_health": 10.0,
        "average_health": 6.9,
        "history_average": 0.0,
        "history_hotspot": None,
    }


def test_no_history_nulls_the_history_derived_kpis() -> None:
    out = present_kpis(_floored_kpis(), set(), history_available=False)

    assert out["hotspot_health"] is None
    assert out["hotspot_health_basis"] == "no_history"
    assert out["history_average"] is None
    assert out["history_hotspot"] is None
    # Structural figures are real measurements and stay.
    assert out["average_health"] == 6.9


def test_history_without_hotspots_says_so_rather_than_ten() -> None:
    out = present_kpis(_floored_kpis(), set(), history_available=True)

    assert out["hotspot_health"] is None
    assert out["hotspot_health_basis"] == "no_hotspots"
    assert out["history_average"] == 0.0


def test_a_real_hotspot_score_is_left_alone() -> None:
    kpis = {**_floored_kpis(), "hotspot_health": 5.24}

    out = present_kpis(kpis, {"a.py"}, history_available=True)

    assert out["hotspot_health"] == 5.24
    assert out["hotspot_health_basis"] == "hotspot_files"


def test_presenting_does_not_mutate_the_persisted_dict() -> None:
    kpis = _floored_kpis()

    present_kpis(kpis, set(), history_available=False)

    assert kpis["hotspot_health"] == 10.0
