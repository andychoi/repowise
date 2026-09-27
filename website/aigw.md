---
layout: default
title: aigw Provider
nav_order: 5.9
---

# aigw Provider
{: .no_toc }

Route Repowise through your own OpenAI-compatible gateway — one key, many upstream models.
{: .fs-6 .fw-300 }

---

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Quick start

```bash
# 1. Export the gateway key
export AIGW_API_KEY="..."

# 2. Point repowise at it
repowise init --provider aigw --model glm-coding-flash
```

## Configuration

| Env var | Purpose |
|---|---|
| `AIGW_API_KEY` | Gateway API key (required) |
| `AIGW_BASE_URL` | Gateway URL override (default `http://localhost:11433/v1`, used verbatim) |

## Models

The default model is `glm-coding-flash`. If the gateway implements
`/v1/models`, the setup picker lists what it exposes; otherwise repowise falls
back to the configured model. Pick another with `--model`.

## Cost

Repowise records `aigw/*` generations at $0.00 — the gateway meters the real
upstream spend itself (virtual keys, spend logs), so double-billing it in
repowise's ledger would misstate actual cost.

## Reasoning

Thinking controls stay at the gateway default; explicit reasoning modes are
rejected before an API call rather than ignored.
