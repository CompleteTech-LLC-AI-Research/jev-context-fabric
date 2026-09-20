# Security and operational boundaries

## Trust model

This alpha is a **single-owner local developer tool**, not a multi-user memory service. The OS account and its configured harness processes are trusted. Worktree scope prevents accidental cross-directory retrieval; it is not authentication between mutually hostile local processes. Different sessions and harnesses using the same worktree share evidence intentionally.

The OpenClaw adapter skips channel/sender/chat-identified contexts. This is a guardrail, not proof of comprehensive identity isolation on an unknown host. Do not expose this installation to untrusted gateway users. Separate OS accounts, isolated memory homes, and explicit principal-scoped storage would be needed before a multi-user deployment.

## Data handling

Canonical source text is retained locally, including sensitive information present in captured tool results or messages. Source, backup, and SQLite files are not encrypted at rest. Unix modes are restrictive when files/directories are created; existing directory permissions and Windows ACLs remain the operator's responsibility. Use a private installation directory, disk encryption where appropriate, and the harness's native secrets/permission controls.

Default retrieval and model-accessible hydration use a separately redacted view. Pattern matching is not a DLP system: it can miss a secret, redact too much, or alter source formatting. `raw_sha256` refers to canonical unredacted text, so the redacted excerpt is intentionally not byte-identical. CLI `hydrate --verbatim` is explicit and unavailable from the MCP/HTTP surfaces.

Sources are not deleted when active context is pruned. Uninstall retains the database and backups. A privacy deletion requirement is different from pruning; stop dependent processes and explicitly delete the corresponding local data/backup files under an appropriate retention procedure. No automated erasure or secure-delete guarantee is provided.

## Inference and retrieval

TypeSafe inference is off by default and cannot be enabled through an MCP/HTTP tool. Explicit CLI opt-in plus a process environment key is required. Hooks remain local even after opt-in. Explicit `enrich` and `retrieve --jev` can incur charges and send imperfectly redacted excerpts to the documented HTTPS endpoint. No redirects or arbitrary provider URLs are accepted.

Retrieved sources, typed labels, and model probabilities are not authorization. The injection signal is a routing/research feature, not a prompt-injection defense or safety certification. The system does not grant tools, approve a write, or change a native tool's arguments.

The OpenClaw recall hook requires current finalized permission for `jev_retrieve`, rechecks invocation activity after retrieval, and returns only context. If a host cannot prove that authority, no automatic enrichment is returned. Other hosts continue to apply their native hook/MCP approval controls; the package does not claim to provide a replacement enforcement layer.

## API exposure

MCP is stdio-only, uses bounded newline-delimited JSON-RPC, and exposes only a small documented tools subset. It does not implement remote MCP, OAuth, sampling, arbitrary filesystem browsing, process execution, or official full-protocol conformance certification. A connected model can deliberately capture text and pin stored evidence; it cannot approve a prune plan or enable remote inference through these tools.

The optional HTTP service binds to `127.0.0.1`, requires a generated bearer token, rejects browser Origin requests and non-loopback Host headers, and caps payloads. It is a plain JSON API, **not HTTP MCP**. It has no TLS, multi-tenant auth, production rate limiting, or Internet-facing deployment support. Do not tunnel, port-forward, or expose it publicly.

The local subprocess bridge is a trusted integration interface. Unlike MCP/HTTP, it can request a prepared native-message view for a harness adapter. It is not a secure sandbox for untrusted callers.

## Failure behavior

A failed hook or bridge operation leaves the host operation running and supplies no new memory. It is fail-open for agent availability, not for authorization. Oversized captures/snapshots are rejected instead of silently truncating the canonical source. An 8 MiB bridge input bound and 2,000,000-character individual source bound apply. A failed capture means the corresponding history was not archived.

Ordinary configuration-write failures are rolled back where the just-written hash still matches. Whole-file restore on uninstall is hash-guarded, so user edits are not silently discarded. An OS kill, power loss, concurrent hostile filesystem rewrite, or missing/corrupted backup can require manual recovery. Journals and hashes aid inspection but are not a fully crash-consistent distributed transaction or cryptographic signature.

## Prune safety limits

Pruning is heuristic, reviewable, and limited to supported active-message adapters. It preserves the original source and native history, protects known structural blocks, and requires local CLI approval. It does not prove downstream task quality, prevent stale facts from being reused, override native compaction, or ensure the host's internal token-accounting reflects the filtered view. Start with disposable sessions and measure actual model inputs before relying on savings.
