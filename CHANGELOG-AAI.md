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
