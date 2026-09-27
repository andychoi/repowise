---
layout: default
title: omlx Provider
nav_order: 5.8
---

# omlx Provider
{: .no_toc }

Run Repowise fully locally with the `omlx` LLM provider — a local OMLX-served model behind an OpenAI-compatible endpoint. No API key, no data leaves the machine.
{: .fs-6 .fw-300 }

---

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Quick start

```bash
# 1. Serve a chat model locally (default endpoint :11434)
omlx serve --model Qwen3.5-9B-MTPLX-Optimized-Speed

# 2. Point repowise at it
repowise init --provider omlx --yes
```

Repowise probes the endpoint, lists the server's chat models, and writes the
choice to `.repowise/config.yaml`.

## Configuration

| Env var | Purpose |
|---|---|
| `OMLX_BASE_URL` | Server URL (default `http://localhost:11434`; `/v1` appended if missing) |
| `OMLX_API_KEY` | Optional — only for servers that enforce a key |
| `OMLX_EMBEDDING_MODEL` | Embedding model id (default `Qwen3-Embedding-0.6B-4bit-DWQ`) |
| `OMLX_EMBEDDING_DIMS` | Embedding width override (default 1024, the model's native width) |
| `OMLX_EMBEDDING_TIMEOUT` | Per-request embedding timeout in seconds (default 30) |

## Models

The default chat model is `Qwen3.5-9B-MTPLX-Optimized-Speed`. The setup picker
lists whatever the server exposes under `/v1/models` (embedding models are
filtered out); pick another with `--model`.

## Embeddings

omlx doubles as an embedder for semantic search:

```bash
repowise init --provider omlx --embedder omlx
```

Vectors are 1024-dimensional (declared explicitly — the fixed-width DWQ model
must never receive the API's `dimensions` parameter).

## Cost

$0.00 — local inference has no per-token price.

## Reasoning

Thinking controls stay at the server default; explicit reasoning modes are
rejected before an API call rather than ignored.
