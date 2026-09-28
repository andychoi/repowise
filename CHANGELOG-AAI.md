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

### E8: `health` output can be bounded, and read from the index

- **Before:** `health --format json` re-parsed and re-analyzed the whole tree on
  every call (146 s and 9.7 MB on a 3,370-file repo) and had no way to bound its
  output.
- **Now:**
  - `--top N` keeps the N lowest-scoring files and the N most severe findings.
  - `--min-severity` sets a finding floor.
  - The JSON gains an `output` block (`metrics_total/_emitted`,
    `findings_total/_matching/_emitted`, `truncated`) and `source`.
  - `--from-index` reads the stored report through the same CRUD the MCP
    `get_health` tool uses: sub-second, read-only, KPIs identical to `status`,
    `json`/`md` only.
  - Measured on the `ams` clone: 0.53 s, 19.7 KB for `--from-index --top 25`.
- **Correction to the plan:** only the default `table` run with no
  `--file`/`--module` writes the health tables; `json`/`md` live runs never did.
- **Known, not changed:** the live analyzer and the stored index can disagree
  slightly (on `ams`: hotspot 5.24 live vs 4.74 stored). That is upstream
  behavior; pick one source per comparison.
- **Detect:** `health --format json` → `source`, `output.truncated`.

### E9: deployment-descriptor entry points (Java EE, JAAS, SAP NetWeaver, Android)

- **Before:** classes a container enters through XML had no in-source caller:
  - servlets, filters and listeners in `web.xml`;
  - EJBs in `ejb-jar.xml`;
  - JAAS login modules;
  - SAP portal components in `portalapp.xml`.

  They were never entry points and read as dead code. Spike S1 found why no
  handler could see them: the traverser skips `.xml` as an unknown language.
  That includes `AndroidManifest.xml`, so the existing Android handler never
  fired on a real repository; its tests hand it a synthetic parsed shell.
- **Now:** `framework_edges/javaee_descriptors.py` finds descriptors on disk,
  including SAP's source `dist/PORTAL-INF/`, which the traverser prunes. It
  resolves each named class through the JVM workspace index and stamps
  `is_entry_point` plus `framework_role`: `servlet`, `servlet_filter`,
  `servlet_listener`, `ejb`, `jaas_login_module`, `sap_portal_component` or
  `android_component`. Android manifests now work from disk. No edges are
  invented from descriptor files, because they are not graph nodes.
- **Measured on the legacy Java EE / SAP pilot:** entry points 34 → 77. The JAAS
  login module and 19 SAP portal components are now entry points; the
  vendored `bootstrap.js` is gone (E5).
- **Known limitation (E9b, follow-up):** the repo overview's "Execution starts
  at" sentence still comes from filename conventions, so on this estate it is
  now omitted rather than wrong. Feeding framework-declared entries into the
  overview is a separate change.

### E10: an Eclipse workspace is reported as packages, one per `.project`

- **Before:** the only JVM package manifests were `pom.xml` and `build.gradle*`,
  so a legacy Eclipse workspace (no Maven or Gradle anywhere) read as one
  package-less tree, and module rollups fell back to top-level directories.
- **Now:** `.project` is a Java package manifest. The package name is the
  directory, which for Eclipse is the project name. Cross-project imports
  already resolved through `package` declarations, so `.classpath` source-root
  parsing from the plan was not needed.
- **Measured on the legacy Java EE / SAP pilot:** 0 → 25 packages (19 Java,
  5 EAR/UI wrappers, 1 JavaScript), `is_monorepo: true`.

### E11: JSPs and WSDLs count as references to the code they name

- **Before:** JSP and WSDL files were skipped as unknown languages and fed
  nothing to the index. A class used only from a JSP (`<%@ page import %>`,
  `<jsp:useBean class>`) had no importer, so it read as dead code.
- **Now:**
  - The E9 handler also scans `.jsp`, `.jspf`, `.tag` and `.tagx`. Concrete
    classes a JSP imports or instantiates are stamped reachable
    (`framework_role: jsp_referenced`); wildcard imports are skipped.
  - `.jsp`, `.jspf`, `.tag` and `.wsdl` join the reference-bearing extensions,
    so a symbol named in them is not called deletion-ready.
- **Not done, by design:** JSP and WSDL are not graph nodes, so no JSP→Java or
  WSDL→bean edges are drawn. SOAP implementation beans were already entry
  points through `@Stateless` (Jakarta handler).
- **Measured on the legacy Java EE / SAP pilot:** no change from E11 alone;
  its JSPs import only JDK and SAP platform classes, none in the repository.
  Together, E5 + E9 + E11 took dead-code findings from 126 to 60 on that estate.
- **Limit:** the reference-bearing path list is capped at 500 files upstream; a
  very large JSP estate would exceed it.
