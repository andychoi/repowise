"""``repowise doc-drift`` - assertions this repository's documents no longer satisfy.

Reads the findings the drift pass persisted on the last ``init`` or ``update``
rather than re-running the analyzer, and serializes them through the same
function ``get_health(include=["doc_drift"])`` uses, so the two surfaces read
the same rows the same way. They still differ where the caller asks them to:
``--kind`` and ``--min-confidence`` narrow this one and not the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from repowise.cli.helpers import console, repo_index_session, resolve_command_target, run_async
from repowise.cli.output import emit_json, emit_refusal, format_option, notice_console
from repowise.core.analysis.doc_drift.constants import (
    DETECTION_BASIS,
    bucket_confidences,
    confidence_tier,
)
from repowise.core.analysis.doc_drift.models import DriftKind

#: Sentinels. Both are distinct from "no findings": an index that cannot be
#: read, and one written before the drift table existed. Reporting either as
#: zero drift would be the detector claiming a clean bill it never checked.
_NO_INDEX = object()
_STALE_INDEX = object()


@dataclass
class _DriftRead:
    """Findings plus the coverage that makes "no findings" meaningful.

    ``referencing_documents`` is every document with a stored resolved
    reference; with the documents that carry findings it is the set the pass
    could check. ``analysis_ran`` is whether any drift row exists at all, the
    persistence layer's own "empty vs never analysed" probe. ``None`` means
    the coverage query itself failed, and is reported as unknown.
    """

    findings: list[dict[str, Any]]
    referencing_documents: set[str] | None
    analysis_ran: bool | None


def _repo_path(path: str | None, repo_alias: str | None, no_workspace: bool, fmt: str) -> Path:
    """The repository to read. One repo: a drift finding belongs to one tree."""
    target = resolve_command_target(
        path=path, no_workspace_flag=no_workspace, repo_alias=repo_alias
    )
    target.notice(notice_console(fmt), command="doc-drift")
    return target.single_repo_path().resolve()


async def _read(root: Path, *, min_confidence: float | None, kinds: tuple[str, ...]) -> Any:
    """Persisted findings for *root*, or :data:`_NO_INDEX` when there is none."""
    from sqlalchemy.exc import SQLAlchemyError

    from repowise.core.persistence.crud import (
        doc_drift_findings_stored,
        get_doc_drift_document_paths,
        get_doc_drift_findings,
        serialize_doc_drift_row,
    )

    async with repo_index_session(root) as opened:
        if opened is None:
            return _NO_INDEX
        session, repo_id = opened
        try:
            rows = await get_doc_drift_findings(session, repo_id, min_confidence=min_confidence)
        except (SQLAlchemyError, OSError, LookupError):
            # An index written before migration 0065 has no ``doc_drift_findings``
            # table, and the query raises rather than returning nothing. Measured
            # on a real checkout; ``repo_index_session`` shields the open, not the
            # read, so this is the caller's to catch, as ``overlap`` does.
            return _STALE_INDEX
        # Filtered here rather than in the query: the store has no index on
        # ``kind`` and the table is one row per drifted reference, so the scan
        # the filter would ride on is the one already being done.
        if kinds:
            rows = [r for r in rows if r.kind in kinds]
        findings = [serialize_doc_drift_row(r) for r in rows]
        try:
            referencing = await get_doc_drift_document_paths(session, repo_id)
            ran = bool(referencing) or await doc_drift_findings_stored(session, repo_id)
        except (SQLAlchemyError, OSError, LookupError):
            referencing, ran = None, None
        return _DriftRead(findings, referencing, ran)


def _payload(
    root: Path, result: _DriftRead | list[dict[str, Any]], min_confidence: float | None
) -> dict[str, Any]:
    if isinstance(result, _DriftRead):
        findings, referencing, ran = (
            result.findings,
            result.referencing_documents,
            result.analysis_ran,
        )
    else:
        findings, referencing, ran = result, None, None
    with_findings = {f["file_path"] for f in findings}
    return {
        "repo": str(root),
        "min_confidence": min_confidence,
        "total": len(findings),
        # ``documents`` always meant documents *with findings*; kept as an alias.
        "documents": len(with_findings),
        "documents_with_findings": len(with_findings),
        # The denominator: documents that name code, the only ones that can drift.
        "documents_with_references": (
            len(referencing | with_findings) if referencing is not None else None
        ),
        "analysis_status": ("unknown" if ran is None else "analyzed" if ran else "not_analyzed"),
        "confidence": bucket_confidences(f["confidence"] for f in findings),
        "findings_basis": DETECTION_BASIS,
        "findings": findings,
    }


#: Tier name to terminal colour. Keyed off :func:`confidence_tier` rather than
#: re-comparing the thresholds, so this cannot disagree with the high/medium/low
#: summary printed directly above it.
_TIER_COLOUR = {"high": "red", "medium": "yellow", "low": "dim"}


def _render(payload: dict[str, Any]) -> None:
    """Grouped by document, because the document is the file a reader edits."""
    from rich.markup import escape

    # Sorted here, not relied upon from the query: the store orders by
    # confidence first, so one document's findings are contiguous only when
    # they happen to share a confidence, and a document with both a 0.95 anchor
    # and a 0.90 path would print two headers for itself.
    findings = sorted(payload["findings"], key=lambda f: (f["file_path"], f["line_number"]))
    if not findings:
        status = payload.get("analysis_status")
        checked = payload.get("documents_with_references")
        if status == "not_analyzed":
            console.print(
                "Documentation drift has not been analysed for this index yet "
                "(no stored references or findings). Run 'repowise update'."
            )
        elif checked is not None:
            console.print(
                f"No documentation drift found across {checked} document(s) that reference code."
            )
        else:
            console.print("No documentation drift found.")
        console.print(f"[dim]{escape(DETECTION_BASIS)}[/dim]")
        return

    buckets = payload["confidence"]
    console.print(
        f"[bold]{payload['total']} finding(s) across {payload['documents']} document(s)[/bold] "
        f"[dim]({buckets['high']} high, {buckets['medium']} medium, {buckets['low']} low "
        f"confidence)[/dim]"
    )

    current = None
    for f in findings:
        if f["file_path"] != current:
            current = f["file_path"]
            console.print(f"\n[cyan]{escape(current)}[/cyan]")
        console.print(
            f"  [dim]:{f['line_number']}[/dim] "
            f"[{_TIER_COLOUR[confidence_tier(f['confidence'])]}]{f['confidence']:.2f}[/] "
            f"{escape(f['kind'])}  {escape(f['reason'])}"
        )
        for line in f["evidence"]:
            console.print(f"      [dim]{escape(line)}[/dim]")

    console.print(f"\n[dim]{escape(DETECTION_BASIS)}[/dim]")


@click.command("doc-drift")
@click.argument("path", required=False, default=None)
@click.option(
    "--min-confidence",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help=(
        "Hide findings below this confidence. Defaults to showing everything "
        "the index stored; the pass already applied the repository's own cutoff "
        "when it wrote them."
    ),
)
@click.option(
    "--kind",
    "kinds",
    multiple=True,
    type=click.Choice([k.value for k in DriftKind]),
    help="Only this reference class. Repeatable.",
)
@click.option("--repo", "repo_alias", default=None, help="In workspace mode, target one repo.")
@click.option("--no-workspace", is_flag=True, default=False, help="Force single-repo mode.")
@format_option()
def doc_drift_command(
    path: str | None,
    min_confidence: float | None,
    kinds: tuple[str, ...],
    repo_alias: str | None,
    no_workspace: bool,
    fmt: str,
) -> None:
    """Show documentation that the repository no longer matches."""
    root = _repo_path(path, repo_alias, no_workspace, fmt)
    result = run_async(_read(root, min_confidence=min_confidence, kinds=kinds))

    if result is _NO_INDEX:
        emit_refusal(
            "no_index",
            f"No readable Repowise index at {root}.",
            fmt,
            remedy="Run 'repowise init' there first.",
            repo=str(root),
        )
        return
    if result is _STALE_INDEX:
        emit_refusal(
            "index_predates_doc_drift",
            f"The index at {root} was written before drift findings were stored.",
            fmt,
            remedy="Run 'repowise update' there to populate them.",
            repo=str(root),
        )
        return

    payload = _payload(root, result, min_confidence)
    if fmt == "json":
        emit_json(payload)
        return
    _render(payload)
