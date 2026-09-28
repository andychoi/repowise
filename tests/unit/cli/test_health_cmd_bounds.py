"""``repowise health`` can be bounded, and can read the index instead of re-analyzing (E8).

On a 3,370-file repository the unbounded ``--format json`` ran 146 s and wrote
9.7 MB: every metric and every finding, recomputed from scratch. ``--top`` and
``--min-severity`` bound the rows and account for what they left out;
``--from-index`` serves the stored report read-only, the way ``get_health``
already does.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import click
import pytest

from repowise.cli.commands.health_cmd import command as health_command_module
from repowise.cli.commands.health_cmd.bounds import bound_output


def _metric(path: str, score: float) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=path,
        score=score,
        max_ccn=3,
        max_nesting=1,
        nloc=10,
        has_test_file=False,
        line_coverage_pct=None,
        branch_coverage_pct=None,
        duplication_pct=None,
    )


def _finding(path: str, severity: str, impact: float) -> SimpleNamespace:
    return SimpleNamespace(
        biomarker_type="complex_method",
        severity=severity,
        file_path=path,
        function_name="f",
        health_impact=impact,
        details={},
        reason="r",
    )


# ---------------------------------------------------------------------------
# bound_output
# ---------------------------------------------------------------------------


def test_no_bound_passes_everything_through() -> None:
    metrics = [_metric("a", 1.0), _metric("b", 2.0)]
    findings = [_finding("a", "low", 0.1)]

    m, f, account = bound_output(metrics, findings, top=None, min_severity=None)

    assert m == metrics and f == findings
    assert account["truncated"] is False
    assert account["metrics_total"] == 2 and account["findings_matching"] == 1


def test_top_keeps_the_worst_files_and_the_most_severe_findings() -> None:
    metrics = [_metric("worst", 1.0), _metric("mid", 5.0), _metric("best", 9.0)]
    findings = [
        _finding("a", "low", 0.9),
        _finding("b", "critical", 0.1),
        _finding("c", "high", 0.5),
        _finding("d", "high", 0.7),
    ]

    m, f, account = bound_output(metrics, findings, top=2, min_severity=None)

    assert [x.file_path for x in m] == ["worst", "mid"]
    assert [x.file_path for x in f] == ["b", "d"]
    assert account == {
        "top": 2,
        "min_severity": None,
        "metrics_total": 3,
        "metrics_emitted": 2,
        "findings_total": 4,
        "findings_matching": 4,
        "findings_emitted": 2,
        "truncated": True,
    }


def test_min_severity_is_a_floor() -> None:
    findings = [_finding("a", "low", 1), _finding("b", "medium", 1), _finding("c", "high", 1)]

    _, f, account = bound_output([], findings, top=None, min_severity="medium")

    assert {x.file_path for x in f} == {"b", "c"}
    assert account["findings_total"] == 3
    assert account["findings_matching"] == 2
    assert account["truncated"] is False


def test_an_enum_severity_is_read_by_its_name() -> None:
    finding = _finding("a", "Severity.HIGH", 1.0)

    _, f, _ = bound_output([], [finding], top=None, min_severity="high")

    assert f == [finding]


# ---------------------------------------------------------------------------
# --from-index
# ---------------------------------------------------------------------------


def _stub_index(monkeypatch, read) -> dict:
    seen: dict = {}

    async def _read(repo_path, **kw):
        seen.update(kw)
        return read

    monkeypatch.setattr(health_command_module, "read_health_from_index", _read)
    monkeypatch.setattr(
        health_command_module,
        "load_state",
        lambda p: {"last_sync_commit": "abc123", "git_history": "unavailable"},
    )
    return seen


def test_from_index_prints_the_stored_report_with_its_source(monkeypatch, tmp_path, capsys):
    kpis = {"average_health": 7.0, "hotspot_health": None, "hotspot_health_basis": "no_history"}
    metrics = [_metric("worst", 1.0), _metric("best", 9.0)]
    findings = [_finding("worst", "high", 0.4)]
    seen = _stub_index(monkeypatch, (kpis, metrics, findings))

    health_command_module._health_from_index(
        tmp_path,
        fmt="json",
        file_filter=None,
        module_filter="src/",
        top=1,
        min_severity="high",
        live_only=[],
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "index"
    assert payload["indexed_commit"] == "abc123"
    assert payload["kpis"]["hotspot_health_basis"] == "no_history"
    assert [m["file_path"] for m in payload["metrics"]] == ["worst"]
    assert payload["output"]["metrics_total"] == 2
    assert payload["output"]["truncated"] is True
    # The state's history flag and the filters reach the index read.
    assert seen["history_available"] is False
    assert seen["module_filter"] == "src/"
    assert "min_severity" not in seen  # applied by bound_output, not the query


def test_from_index_with_nothing_stored_says_so(monkeypatch, tmp_path):
    _stub_index(monkeypatch, None)

    with pytest.raises(click.ClickException, match="No stored health report"):
        health_command_module._health_from_index(
            tmp_path,
            fmt="json",
            file_filter=None,
            module_filter=None,
            top=None,
            min_severity=None,
            live_only=[],
        )


@pytest.mark.parametrize(
    ("fmt", "live_only", "message"),
    [
        ("table", [], "use --format json or md"),
        ("json", ["--refactoring-targets"], "a live analysis"),
    ],
)
def test_from_index_refuses_what_it_cannot_serve(tmp_path, fmt, live_only, message):
    with pytest.raises(click.UsageError, match=message):
        health_command_module._health_from_index(
            tmp_path,
            fmt=fmt,
            file_filter=None,
            module_filter=None,
            top=None,
            min_severity=None,
            live_only=live_only,
        )
