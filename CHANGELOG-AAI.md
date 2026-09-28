# a-ai.solutions fork changes

This fork (`andychoi/repowise`) is upstream Repowise plus the fixes below. Client
releases are versioned `<upstream>+aai.<n>` and built from a public tag. Each entry
names the edge case (E#) from the hardening plan, the upstream behavior it changes,
and how to detect it from a consumer.

Licensed under AGPL-3.0, as upstream. Source for any deployed release is the
matching tag at https://github.com/andychoi/repowise.

## Unreleased (branch `aai/tier1`, based on upstream `v0.53.0`)

### E1: `risk --target` no longer shortens its answer silently

- **Before:** `get_risk` fits a 24,000-character budget by shedding whole target
  cards from the tail of the request, and records what it shed. The CLI's JSON
  projection was an allowlist that dropped every accounting field, so a 30-target
  request returned 7 cards and nothing saying 23 were missing.
- **Now:**
  - The projection keeps `truncated`, `targets_total` / `_emitted` / `_omitted` /
    `_truncated` / `_reduced_reason`, and `_meta.omitted` (as `omitted`).
  - `risk --target` pages by default, re-requesting only the missing cards until
    every target has one. The JSON gains `pages`. `--no-paginate` restores one
    budgeted page. PR mode (`--changed-file`) and `--full` are never paged.
  - `get_risk` orders cards riskiest first (counted bug fixes, then hotspot score),
    with unresolved cards kept up front. Budget shedding now drops the least risky
    card instead of whichever was named last. This affects MCP callers too.
- **Detect:** a paged response carries `pages`; any remaining shortfall carries
  `truncated: true` and `targets_omitted`.

### E2: a code base with no Git history says so

- **Before:** `GitIndexer.index_repo` returned the same zero `GitIndexSummary` for
  a plain directory, a skipped partial clone and a repository with nothing
  tracked. The receipt then reported the *configured* tier (`git_tier: "full"`)
  and an empty `analysis.unavailable`, so a source export read as a repository
  with quiet, clean history.
- **Now:**
  - `GitIndexSummary.history_status` is one of `indexed` / `no_repository` /
    `partial_clone_skipped` / `no_tracked_files`.
  - Init records `git_history: "unavailable"` and `git_history_reason` in
    `state.json`. `git_tier` is kept, because it is the resume policy
    `repowise update` parses.
  - `index_scope` reports `git_tier: "none"` and lists `git_history` under
    `analysis.unavailable`.
- **Detect:** `status --format json` → `index_scope.git_tier == "none"`.

### E3: `health` reports unmeasured hotspot health as null, not 10.0

- **Before:** `compute_kpis` floors `hotspot_health` to 10.0 for the non-nullable
  snapshot column, and `repowise health` printed that floor: a "perfect" hotspot
  score for a repo with no hotspots or no history at all. `history_average: 0.0`
  likewise read as clean history.
- **Now:**
  - `present_kpis()` (in the owner module `health/scoring.py`) shapes the KPIs
    for output: `hotspot_health: null` plus `hotspot_health_basis` of
    `no_history`, `no_hotspots` or `hotspot_files`.
  - With no history, the history averages are null too.
  - The persisted snapshot and trend alerts are unchanged.
- **Detect:** `health --format json` → `kpis.hotspot_health_basis`.

### E5 (and E4): vendored JavaScript libraries are not indexed as application code

- **Before:** library builds checked into a web root (`WebContent/js/libs/…`,
  `iam/js/bootstrap.js`) sat outside every blocked directory, and only minified
  builds matched `*.min.js`. They were health-scored and offered as dead code.
  Because `bootstrap` is a generic entry stem, a vendored Twitter Bootstrap was
  named a Java EE application's execution entry point (E4).
- **Now:**
  - A JavaScript file whose opening `/*!` banner carries a version and a licence,
    copyright or URL is skipped as a vendored library and counted in
    `TraversalStats.skipped_vendored`.
  - `bower_components`, `jspm_packages`, `third_party` and `third-party` join
    the blocked directories.
  - Hand-written code, a project's own unversioned `/*!` note, and ordinary `/*`
    template headers stay indexed.
  - E4 needs no separate entry-point rule: a skipped file never reaches entry
    candidacy. A hand-written `bootstrap.js` is still a legitimate entry.
- **Detect:** `skipped_vendored` in traversal stats; vendored paths are absent
  from `health` and the overview entry points.

### E6: every flag the CLI reference documents is one the command accepts

- **Before:** the reference told readers to pass `--no-agents-md` to `init`; the
  option was `--agents/--no-agents`, so the documented isolation invocation
  failed with "No such option". Nothing checked the reference against the
  commands. The new check found four more stale rows:
  - `--workspace` on `search`, `dead-code` and `costs` (only `--no-workspace`
    exists; workspace mode is auto-detected);
  - `--primary` on `workspace add` (the command is `workspace set-default`).
- **Now:**
  - `--agents-md/--no-agents-md` is an accepted alias.
  - The five rows are corrected, and `--save-key` is documented for
    `workspace add`.
  - `tests/unit/cli/test_cli_reference_flags.py` asserts every first-column flag
    in every command's option table is declared by the live Click command
    (subcommand flags count for group sections).

### E7: `doc-drift` states how many documents it checked

- **Before:** the JSON `documents` field counted documents *with findings*, so a
  clean run read `documents: 0`, which is indistinguishable from "nothing was
  checked". One consumer's evidence projector wrote exactly that wrong claim.
  An index where the pass never ran also printed "No documentation drift found."
- **Now:** the payload adds:
  - `documents_with_findings` (`documents` kept as an alias);
  - `documents_with_references`: the documents that name code, from the stored
    reference index plus the documents with findings (a drifted reference
    resolves to nothing, so its document isn't in the index);
  - `analysis_status`: `analyzed` / `not_analyzed` / `unknown`.

  The table says "No documentation drift found across N document(s) that
  reference code", or that the pass has not run. There is no state plumbing: the
  count comes from the store, so partial `update` passes stay correct.
- **Detect:** `doc-drift --format json` → `documents_with_references`,
  `analysis_status`.
