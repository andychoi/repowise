"""`repowise risk --target` must never shorten its answer silently.

``get_risk`` fits a response budget by shedding whole target cards, and it
records what it shed (``truncated``, ``targets_total`` / ``_emitted`` /
``_omitted`` and ``_meta.omitted``). The CLI projection used to be an allowlist
that dropped every one of those fields, so a 30-target request came back as a
7-target map with nothing saying 23 were missing. These tests pin the three
repairs: the accounting survives the projection, the CLI pages for the shed
targets (a terminal has no context budget to protect), and the server sheds
the least risky cards first so the answers a caller most needs survive.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from repowise.cli.commands import risk_cmd
from repowise.cli.commands.risk_cmd import project_risk, risk_command
from repowise.server.mcp_server.tool_risk.get_risk import order_cards_for_shedding

# ---------------------------------------------------------------------------
# (a) The projection keeps the truncation accounting
# ---------------------------------------------------------------------------


def _truncated_payload() -> dict:
    return {
        "targets": {f"f{i}.py": {"risk_summary": "s"} for i in range(7)},
        "truncated": True,
        "targets_total": 30,
        "targets_emitted": 7,
        "targets_omitted": 23,
        "targets_truncated": True,
        "targets_reduced_reason": "response_budget",
        "omission_marker": "[repowise#abc: 23 targets omitted]",
        "_meta": {"omitted": [{"ref": "repowise#abc", "label": "targets"}], "timing_ms": 12},
    }


def test_the_projection_keeps_the_truncation_accounting() -> None:
    projected = project_risk(_truncated_payload())

    assert projected["truncated"] is True
    assert projected["targets_total"] == 30
    assert projected["targets_emitted"] == 7
    assert projected["targets_omitted"] == 23
    assert projected["targets_truncated"] is True
    assert projected["targets_reduced_reason"] == "response_budget"
    assert projected["omitted"] == [{"ref": "repowise#abc", "label": "targets"}]


def test_an_untruncated_projection_adds_no_accounting_keys() -> None:
    projected = project_risk({"targets": {"a.py": {"risk_summary": "s"}}})

    for key in ("truncated", "targets_total", "targets_omitted", "omitted"):
        assert key not in projected


# ---------------------------------------------------------------------------
# (b) The CLI pages for targets the server shed
# ---------------------------------------------------------------------------


def _fake_server(page_size: int):
    """A ``get_risk`` stand-in that keeps the first *page_size* targets per call."""
    calls: list[list[str]] = []

    def fetch(repo, targets, changed_files):
        calls.append(list(targets))
        kept = list(targets)[:page_size]
        payload: dict = {"targets": {t: {"risk_summary": f"card {t}"} for t in kept}}
        if len(kept) < len(targets):
            payload.update(
                truncated=True,
                targets_total=len(targets),
                targets_emitted=len(kept),
                targets_omitted=len(targets) - len(kept),
                targets_truncated=True,
                targets_reduced_reason="response_budget",
            )
        return payload

    return fetch, calls


def _invoke(monkeypatch, fetch, *extra: str):
    monkeypatch.setattr(risk_cmd, "_resolve_target_repo", lambda path, fmt: object())
    monkeypatch.setattr(risk_cmd, "_fetch_target_payload", fetch)
    targets = [arg for i in range(5) for arg in ("--target", f"f{i}.py")]
    return CliRunner().invoke(risk_command, [*targets, "--format", "json", *extra])


def test_the_cli_pages_until_every_target_has_a_card(monkeypatch) -> None:
    fetch, calls = _fake_server(page_size=2)

    result = _invoke(monkeypatch, fetch)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload["targets"]) == {f"f{i}.py" for i in range(5)}
    assert "truncated" not in payload
    assert payload["pages"] == 3
    # Each page asks only for what is still missing.
    assert calls == [
        [f"f{i}.py" for i in range(5)],
        ["f2.py", "f3.py", "f4.py"],
        ["f4.py"],
    ]


def test_no_paginate_reports_the_shortfall_instead(monkeypatch) -> None:
    fetch, calls = _fake_server(page_size=2)

    result = _invoke(monkeypatch, fetch, "--no-paginate")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(calls) == 1
    assert set(payload["targets"]) == {"f0.py", "f1.py"}
    assert payload["truncated"] is True
    assert payload["targets_omitted"] == 3


def test_paging_stops_when_a_page_makes_no_progress(monkeypatch) -> None:
    """A server that returns nothing for the remainder must not loop forever."""

    def stuck(repo, targets, changed_files):
        if len(targets) == 5:
            return {"targets": {"f0.py": {}}, "truncated": True, "targets_total": 5}
        return {"targets": {}}

    result = _invoke(monkeypatch, stuck)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload["targets"]) == {"f0.py"}
    assert payload["truncated"] is True
    assert payload["targets_total"] == 5
    assert payload["targets_omitted"] == 4


# ---------------------------------------------------------------------------
# (c) The server sheds the least risky cards first
# ---------------------------------------------------------------------------


def test_cards_are_ordered_riskiest_first_with_unresolved_cards_kept_up_front() -> None:
    results = [
        {"target": "calm.py", "hotspot_score": 0.1},
        {"target": "missing.py", "resolved": False},
        {"target": "fixed_often.py", "hotspot_score": 0.2, "defect_profile": {"fix_count": 4}},
        {"target": "hot.py", "hotspot_score": 0.9},
        {"target": "fixed_once.py", "hotspot_score": 0.95, "defect_profile": {"fix_count": 1}},
    ]

    ordered = [r["target"] for r in order_cards_for_shedding(results)]

    # Budget shedding pops from the tail, so the tail must be the least risky.
    assert ordered == ["missing.py", "fixed_often.py", "fixed_once.py", "hot.py", "calm.py"]


def test_ordering_is_stable_for_equal_risk() -> None:
    results = [{"target": f"t{i}.py", "hotspot_score": 0.5} for i in range(4)]

    assert [r["target"] for r in order_cards_for_shedding(results)] == [
        "t0.py",
        "t1.py",
        "t2.py",
        "t3.py",
    ]
