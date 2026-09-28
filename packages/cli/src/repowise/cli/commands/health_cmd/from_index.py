"""``repowise health --from-index``: the persisted report, read without re-analysis.

The default ``health`` path re-parses the repository and re-runs the analyzer
on every call (minutes on a large tree). The index already holds what the last
``init``/``update`` computed, and the MCP ``get_health`` tool serves from it; a
script or an agent that wants the numbers should not pay for a re-analysis.
This reads the same tables, shapes the rows like the live path's, and never
writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _finding(row: Any) -> SimpleNamespace:
    try:
        details = json.loads(row.details_json or "{}")
    except (TypeError, ValueError):
        details = {}
    return SimpleNamespace(
        biomarker_type=row.biomarker_type,
        severity=row.severity,
        file_path=row.file_path,
        function_name=row.function_name,
        health_impact=row.health_impact,
        details=details,
        reason=row.reason,
    )


def _in_scope(path: str, file_filter: str | None, module_filter: str | None) -> bool:
    if file_filter and path != file_filter:
        return False
    return not (module_filter and not path.startswith(module_filter))


async def read_health_from_index(
    repo_path: Path,
    *,
    file_filter: str | None,
    module_filter: str | None,
    history_available: bool,
) -> tuple[dict[str, Any], list[Any], list[Any]] | None:
    """``(kpis, metrics_worst_first, findings)`` from the index, or ``None``.

    ``None`` means there is nothing to read: no index, or an index with no
    health rows. The caller says so rather than printing an empty report,
    which would read as a perfectly healthy repository.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from repowise.cli.helpers import repo_index_session
    from repowise.core.analysis.health.scoring import compute_kpis, present_kpis
    from repowise.core.persistence.crud import (
        get_health_findings,
        get_health_metrics,
        get_hotspot_file_paths,
    )

    async with repo_index_session(repo_path) as opened:
        if opened is None:
            return None
        session, repo_id = opened
        try:
            metric_rows = await get_health_metrics(session, repo_id)
            # Every open finding: --min-severity is applied by bound_output, so
            # findings_total means the same population as on the live path.
            finding_rows = await get_health_findings(session, repo_id)
            hotspot_paths = await get_hotspot_file_paths(session, repo_id)
        except (SQLAlchemyError, OSError, LookupError):
            return None
    if not metric_rows:
        return None
    # KPIs describe the whole repository, as the live path's do; the file and
    # module filters narrow only the rows printed beneath them.
    kpis = present_kpis(
        compute_kpis(metric_rows, hotspot_paths),
        hotspot_paths,
        history_available=history_available,
    )
    metrics = [m for m in metric_rows if _in_scope(m.file_path, file_filter, module_filter)]
    findings = [
        _finding(f) for f in finding_rows if _in_scope(f.file_path, file_filter, module_filter)
    ]
    return kpis, metrics, findings
