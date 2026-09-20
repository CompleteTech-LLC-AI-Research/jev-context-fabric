# Implemented architecture and extension contract

## Extension contracts

Two distinct ways another program plugs in, which should not be confused:

- **stdio JSON bridge** (`run.py bridge`) — a caller drives this package's core directly,
  one `{"operation","arguments"}` object in, one result out. Documented below.
- **jev-bus stage** (`run.py bus-stage`) — this package participates in *another* package's
  message-transform chain, or carries one of its own. One `jev-bus.stage.v1` object in, one
  `{ok, messages, notes}` out. Specified in [BUS.md](BUS.md), which is byte-identical in every
  participating repository.

The bus is additive: where no chain is registered, every adapter performs its own direct
transform exactly as it did before the bus existed. `paging.prepare()` accordingly accepts an
optional pristine `original_messages` array and derives snapshot fingerprints and `msg_` keys
from it, so an upstream stage's edit cannot re-key messages or stale an open plan.
`paging.can_mutate()` reports Pi and Hermes as prunable only while this package is actually
registered on the bus for them, since it installs no native transform for either host.

## Components

`core.py` coordinates a shared SQLite-backed source store, retrieval, typed features, and normalized events. `provider.py` contains the opt-in TypeSafe client. `paging.py` owns native snapshots, review plans, and persisted active-view exclusions. `hooks.py` translates CLI hook envelopes. `mcp.py` and `http_api.py` expose distinct transports. Native JavaScript adapters call the same Python core through `bridge.mjs`.

The core is not a mandatory resident daemon. CLI/hook/native-bridge calls use short-lived processes; MCP may remain resident; HTTP is an explicitly started optional service. SQLite WAL and bounded lock waits coordinate these processes. There is no background model scheduler, host service manager, startup task, automatic paid queue, or hidden synchronizer.

## Generic bridge

Run this command with a single JSON request on stdin:

```bash
python3 run.py --home /private/memory-home --workspace /path/to/worktree bridge
```

Example request:

```json
{
  "operation": "event",
  "arguments": {
    "kind": "POST_TOOL",
    "harness": "custom-agent",
    "session": "session-42",
    "native_id": "tool-call-7",
    "origin": "test-run:7",
    "content": "118 passed, 3 failed",
    "query": "authentication regression"
  }
}
```

The workspace is a process-bound scope, not a field that untrusted source text can change. Supported dispatch operations are `status`, `capture`, `retrieve`, `page_fault`, `hydrate`, `pin`, `event`, `prepare`, `prune_plan`, `feature`, and `link`. Model-accessible transports expose a smaller subset. Error replies have a nonzero subprocess exit status; native adapters discard them and leave the existing host context intact.

For current model inputs, a custom adapter can call:

```json
{
  "operation": "prepare",
  "arguments": {
    "session": "session-42",
    "harness": "generic",
    "messages": [
      {"role":"system","content":"Original system instruction"},
      {"role":"user","content":"Current user request"}
    ],
    "query": "Current user request"
  }
}
```

The response includes `messages`, `removed`, `fingerprint`, and `native_compaction_called: false`. **The caller must actually submit the returned messages to its reasoning model**; storing a view alone does not remove active context. Before approval, the returned array is unchanged.

Normal events include `SESSION_START`, `USER_INPUT`, `PRE_MODEL`, `PRE_TOOL`, `POST_TOOL`, `TURN_END`, `SUBAGENT_END`, `SESSION_END`, and `CONTEXT_FAULT`. Native adapters support only the subset for which their verified hook envelopes supply enough information. No universal lifecycle coverage is implied. Compaction events are deliberately excluded from integration registration.

## Canonical versus derived state

Sources are identified by a hash over workspace/session/harness/origin/content-hash. Identical captures at the same origin deduplicate; changed content creates a new source. Native snapshots are canonical JSON, with per-message occurrence identity to avoid dropping identical recent messages along with an old one.

Features retain model response, question version, probabilities, usage when returned, source ID, and original source hash. The local typed router ignores mismatched source hashes/question versions. It uses the complete stored role distribution rather than inventing an independent confidence scalar. It does not implement a globally learned TaskStateVector or multi-step Bayesian belief update.

Explicit `supports`, `contradicts`, `supersedes`, `attempted_to_fix`, `resulted_in`, and `depends_on` relations are stored with caller-supplied provenance. Retrieval expands one hop; it does not treat a claimed edge as established causality. Facts are never deleted just because a classifier labels them superseded.

## Native adapter invariants

1. Do not change permissions, execute model output as code, or infer approval from memory.
2. Skip source capture when the host provides no session identity; never merge active views under an invented session.
3. Retain original sources before any eligible active-view exclusion.
4. Never conflate a `/prune` plan with completed context mutation or native compaction.
5. Return existing context on timeout or unsupported host fields. Do not invent hook compatibility.

The JavaScript bridge uses non-shell subprocess execution, bounded input/output, correct UTF-8 decoding, and a six-second deadline. It adds no NPM dependency. Each RPC can spawn a process; process overhead and lock contention have not been benchmarked at scale.

## Loopback JSON API

```bash
python3 run.py --workspace /path/to/worktree serve-http --port 8769
```

The bearer token is written to `http-token` under the selected memory home. POST JSON argument objects to `/v1/status`, `/v1/capture`, `/v1/retrieve`, `/v1/page_fault`, `/v1/hydrate`, `/v1/prune_plan`, `/v1/feature`, `/v1/pin`, or `/v1/link`. Include `Authorization: Bearer <token>` and `Content-Type: application/json`. This is not MCP-over-HTTP. Remote reranking and prune application are not HTTP capabilities.

## Extending the package

A new MCP-capable harness usually needs a path/schema installer branch plus conflict/merge/uninstall tests. Do not assume that its config uses `mcpServers`; Codex/Hermes/OpenCode illustrate incompatible schemas.

A native plugin requires an additional adapter using the bridge, exact versioned lifecycle contracts, mock envelope tests, and then a live-host smoke test. Only label `context-transform` capability after proving the host accepts a replaced message array. A hooks-only integration may inject evidence without any ability to remove previously supplied context.

Future research work includes incremental task-state compilation, embeddings, typed inverted indexes, automatically evidenced causal edges, pressure-aware consent prompts, calibrated uncertainty budgets, remote workers, task-level multi-agent sharing, and benchmark-driven optimization. None of these is represented as implemented solely because the design can accommodate it.
