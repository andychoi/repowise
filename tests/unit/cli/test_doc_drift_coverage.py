"""``repowise doc-drift`` states how many documents it checked (E7).

``documents`` in the JSON counted documents *with findings*, so a clean run
printed ``documents: 0`` and a reader (and one consumer's evidence projector)
took that as "no documents were checked". The persisted store already knows
the denominator: every document with a resolved code reference, plus the ones
with findings, are the documents that can drift. These tests pin that the
payload reports it, keeps ``documents`` as an alias, and tells "clean" apart
from "never analysed".
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from repowise.cli.commands import doc_drift_cmd
from repowise.cli.commands.doc_drift_cmd import _DriftRead


def _finding(file_path: str = "docs/a.md") -> dict:
    return {
        "file_path": file_path,
        "line_number": 3,
        "kind": "path",
        "target": "src/gone.py",
        "confidence": 0.9,
        "reason": "gone",
        "evidence": ["docs/a.md:3 states `src/gone.py`"],
    }


def _invoke(monkeypatch, tmp_path, result, args=("--format", "json")):
    monkeypatch.setattr(doc_drift_cmd, "_repo_path", lambda *a, **k: tmp_path)

    def _run(coro):
        coro.close()
        return result

    monkeypatch.setattr(doc_drift_cmd, "run_async", _run)
    return CliRunner().invoke(doc_drift_cmd.doc_drift_command, list(args))


def test_a_clean_run_reports_how_many_documents_it_checked(monkeypatch, tmp_path):
    read = _DriftRead(
        findings=[], referencing_documents={"README.md", "docs/a.md"}, analysis_ran=True
    )

    payload = json.loads(_invoke(monkeypatch, tmp_path, read).output)

    assert payload["documents"] == 0
    assert payload["documents_with_findings"] == 0
    assert payload["documents_with_references"] == 2
    assert payload["analysis_status"] == "analyzed"


def test_documents_with_findings_count_toward_the_denominator(monkeypatch, tmp_path):
    """A drifted reference resolves to nothing, so it never appears in the
    reference store; its document must still count as checked."""
    read = _DriftRead(
        findings=[_finding("docs/b.md")],
        referencing_documents={"docs/a.md"},
        analysis_ran=True,
    )

    payload = json.loads(_invoke(monkeypatch, tmp_path, read).output)

    assert payload["documents"] == 1
    assert payload["documents_with_findings"] == 1
    assert payload["documents_with_references"] == 2


def test_never_analysed_is_not_reported_as_clean(monkeypatch, tmp_path):
    read = _DriftRead(findings=[], referencing_documents=set(), analysis_ran=False)

    json_payload = json.loads(_invoke(monkeypatch, tmp_path, read).output)
    table = _invoke(monkeypatch, tmp_path, read, args=()).output

    assert json_payload["analysis_status"] == "not_analyzed"
    assert "has not been analysed" in table
    assert "No documentation drift found" not in table


def test_the_table_states_the_denominator_on_a_clean_run(monkeypatch, tmp_path):
    read = _DriftRead(
        findings=[], referencing_documents={"a.md", "b.md", "c.md"}, analysis_ran=True
    )

    out = _invoke(monkeypatch, tmp_path, read, args=()).output

    assert "across 3 document(s) that reference code" in out


def test_an_unreadable_coverage_query_reports_unknown_not_zero(monkeypatch, tmp_path):
    read = _DriftRead(findings=[], referencing_documents=None, analysis_ran=None)

    payload = json.loads(_invoke(monkeypatch, tmp_path, read).output)

    assert payload["documents_with_references"] is None
    assert payload["analysis_status"] == "unknown"
