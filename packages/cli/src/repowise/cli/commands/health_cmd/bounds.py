"""Bounding what ``repowise health`` prints, with an account of what it left out.

On a large repository the unbounded JSON ran to ~10 MB (every file's metrics
and every finding), which no agent or script can consume whole. ``--top`` and
``--min-severity`` bound it; every bound reports its own totals so a shorter
answer is never mistaken for a smaller repository.
"""

from __future__ import annotations

from typing import Any

#: Ascending. ``--min-severity high`` keeps ``high`` and ``critical``.
SEVERITY_ORDER: tuple[str, ...] = ("low", "medium", "high", "critical")
_RANK = {name: i for i, name in enumerate(SEVERITY_ORDER)}


def _severity(finding: Any) -> str:
    return str(getattr(finding, "severity", "")).rsplit(".", 1)[-1].lower()


def bound_output(
    metrics_sorted: list[Any],
    findings: list[Any],
    *,
    top: int | None,
    min_severity: str | None,
) -> tuple[list[Any], list[Any], dict[str, Any]]:
    """Apply ``--min-severity`` then ``--top``; return the rows and the account.

    *metrics_sorted* arrives worst-first, so the top N are the N lowest scores.
    Findings are ranked by severity, then health impact, whenever a bound is
    asked for, so the first N are the most severe rather than whatever order
    the analyzer produced them in. With no bound the rows pass through
    untouched and the account says nothing was dropped.
    """
    matching = findings
    if min_severity is not None:
        floor = _RANK[min_severity]
        matching = [f for f in findings if _RANK.get(_severity(f), -1) >= floor]
    if top is not None or min_severity is not None:
        matching = sorted(
            matching,
            key=lambda f: (
                -_RANK.get(_severity(f), -1),
                -float(getattr(f, "health_impact", 0.0) or 0.0),
            ),
        )
    metrics_out = metrics_sorted if top is None else metrics_sorted[:top]
    findings_out = matching if top is None else matching[:top]
    account = {
        "top": top,
        "min_severity": min_severity,
        "metrics_total": len(metrics_sorted),
        "metrics_emitted": len(metrics_out),
        "findings_total": len(findings),
        "findings_matching": len(matching),
        "findings_emitted": len(findings_out),
        "truncated": len(metrics_out) < len(metrics_sorted) or len(findings_out) < len(matching),
    }
    return metrics_out, findings_out, account
