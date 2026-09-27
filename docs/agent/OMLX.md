# omlx Integration

`omlx` is the LLM provider for a local [OMLX](https://github.com/ml-explore/mlx)-served
model exposed behind an OpenAI-compatible endpoint. No API key — the server runs
on your machine, and nothing leaves it.

## Prerequisites

Start the omlx server with a chat model loaded:

```bash
omlx serve --model Qwen3.5-9B-MTPLX-Optimized-Speed   # default endpoint :11434
```

Verify it is up:

```bash
curl http://localhost:11434/v1/models
```

Repowise detects it automatically: when something is listening at
`OMLX_BASE_URL` (default `http://localhost:11434`), the interactive provider
selection shows it as "available".

## Provider

Use `omlx` when you want Repowise page generation to run on your own
hardware instead of an API key:

```bash
repowise init --provider omlx --yes
```

Or persist it:

```bash
REPOWISE_PROVIDER=omlx repowise update
```

### Default model

`Qwen3.5-9B-MTPLX-Optimized-Speed`. Override with `--model`; the provider
lists the server's chat models at setup time (embedding models are filtered
out of that listing — use the `omlx` embedder for those).

### Endpoint

The OpenAI-compatible path lives under `/v1`, which repowise appends for you:
`OMLX_BASE_URL=http://localhost:11434` and `.../v1` are equivalent. A server
on another host just needs `OMLX_BASE_URL=http://mlbox.local:11434`.

### API key

None required. If your server enforces one, set `OMLX_API_KEY`.

### Reasoning

No explicit reasoning controls are sent; thinking stays at the server
default. Requesting `--reasoning off` fails before any call rather than
silently doing nothing.

### Cost

Recorded at $0.00 — local inference has no per-token price (the
`omlx/` prefix marks it local, like `ollama/`).

## Embeddings

omlx also serves `Qwen3-Embedding-0.6B-4bit-DWQ` (1024 dimensions, declared
natively — never sent as the API's `dimensions` parameter):

```bash
repowise init --provider omlx --embedder omlx
```

Env knobs: `OMLX_EMBEDDING_MODEL`, `OMLX_EMBEDDING_DIMS`,
`OMLX_EMBEDDING_TIMEOUT` (default 30s — raise it for slow first loads), all
falling back to their `REPOWISE_EMBEDDING_*` counterparts.

## Concurrency

Local hardware serves one thing at a time. If a run shows timeouts under the
default concurrency, drop it:

```bash
repowise init --provider omlx --concurrency 1
```
