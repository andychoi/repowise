# aigw Integration

`aigw` is the LLM provider for a local [AI gateway](https://github.com/andychoi/ai-gateway)
exposed behind an OpenAI-compatible endpoint. The gateway fronts remote models
and meters the real upstream spend itself, so repowise needs only the gateway
key — not a key per upstream vendor.

## Prerequisites

The gateway runs at `http://localhost:11433/v1` and reads its key from
`AIGW_API_KEY`:

```bash
export AIGW_API_KEY="..."
curl -s -H "Authorization: Bearer $AIGW_API_KEY" http://localhost:11433/v1/models
```

A 404 from `/v1/models` is fine — repowise falls back to the configured model.

## Provider

```bash
repowise init --provider aigw --model glm-coding-flash
```

Or persist it:

```bash
REPOWISE_PROVIDER=aigw repowise update
```

### Default model

`glm-coding-flash`. Override with `--model`; the setup picker lists whatever
the gateway exposes under `/v1/models` when it implements the endpoint.

### Endpoint

The default base URL is `http://localhost:11433/v1`. Set `AIGW_BASE_URL` for a
gateway on another host or port — the value is used verbatim, so include the
`/v1` suffix yourself.

### Reasoning

No explicit reasoning controls are sent; thinking stays at the gateway
default. Requesting `--reasoning off` fails before any call rather than
silently doing nothing.

### Cost

Recorded at $0.00. The gateway meters the real upstream spend (virtual keys,
spend logs) — the same rationale as the `claude_cli` subscription passthrough,
not local inference.

## Concurrency

The gateway fronts remote models, so repowise applies its standard remote
rate limits and the 60s interactive synthesis budget.
