<div align="center">

# JEV Context Fabric

**A local-first, source-backed memory layer for coding agents — with an installer for eight harnesses.**

Every remembered thing keeps its bytes, its SHA-256, and its origin.
Nothing is summarized away. Nothing leaves the machine unless you say so.

[![version](https://img.shields.io/badge/version-0.1.0-1f6feb?style=flat-square)](#)
[![status](https://img.shields.io/badge/status-alpha-d29922?style=flat-square)](#what-this-is--and-is-not)
[![python](https://img.shields.io/badge/python-3.11%2B-3776ab?style=flat-square&logo=python&logoColor=white)](#quick-start)
[![dependencies](https://img.shields.io/badge/pip_dependencies-none-2da44e?style=flat-square)](#quick-start)
[![tests](https://img.shields.io/badge/tests-109_py_%2F_19_node-2da44e?style=flat-square)](TEST_REPORT.md)
[![license](https://img.shields.io/badge/license-MIT-8250df?style=flat-square)](LICENSE)

[Quick start](#quick-start) · [How it works](#how-it-works) · [Integrations](#integrations) · [CLI](#the-cli) · [`/prune`](#prune-is-not-compact) · [Coexistence](#coexisting-with-jev-prune-kit) · [Safety](#safety-and-uninstall) · [Docs](docs/)

</div>

---

## What this is — and is not

Agents forget. The usual fix is compaction: a model rewrites your history into a summary, and the original bytes are gone. This package takes the other road. It **captures canonical text, hashes it, and retrieves budgeted excerpts on demand** — so the agent can page evidence back in instead of trusting a lossy paraphrase of itself.

<table>
<tr><th align="left" width="50%">✅ What the code actually does</th><th align="left" width="50%">🚫 What it does not do</th></tr>
<tr valign="top"><td>

- Stores canonical captured text + SHA-256 in local SQLite
- Retrieves via FTS5/BM25, pins, typed-role routing, one-hop links
- Installs into **8 harnesses** with zero pip installs
- Serves 8 memory tools over MCP, a stdio bridge, or loopback HTTP
- Previews reversible pruning; requires local CLI approval
- Backs up, hashes, and cleanly uninstalls everything it writes

</td><td>

- Install the harness applications themselves
- Import your existing native transcripts
- Call `/compact`, or intercept the host's own context pressure
- Make any paid network call by default
- Provide multi-tenant access control or principal isolation
- Claim measured token savings — budgets are **characters**

</td></tr>
</table>

> [!IMPORTANT]
> **This is an alpha reference implementation.** Host APIs were checked against primary documentation, and the native adapters were exercised against **mock hosts — not running copies of the eight applications.** A passing mock certifies the adapter's shape, not the host's behavior. See [TEST_REPORT.md](TEST_REPORT.md) and [documented interfaces](docs/VERIFIED_INTERFACES.md) for exactly what was and was not verified.

---

## Quick start

**Requirements:** Python 3.11+. That is the whole list. The core is standard library only; the config parsers (`json5`, `tomlkit`, `ruamel.yaml`) are vendored with their licenses. **No pip install, no account, no network download, no model key.** JavaScript plugins run inside the host's existing Node-compatible runtime.

Unzip the package and open a terminal in `jev-context-fabric/`.

<table>
<tr><th align="left">Windows</th><th align="left">Linux / macOS</th></tr>
<tr valign="top"><td>

```powershell
py -3 install.py --all --dry-run
py -3 install.py --all
```

`install.ps1` is an equivalent wrapper. It requires no administrator rights and changes no execution policy — use the Python command directly if script execution is restricted.

</td><td>

```bash
python3 install.py --all --dry-run
python3 install.py --all
```

`./install.sh` is an equivalent wrapper.

</td></tr>
</table>

**Always dry-run first.** It prints every file it would touch and writes nothing.

```bash
python3 install.py                                    # only harnesses it detects
python3 install.py --all                              # all eight, installed or not
python3 install.py --harness codex claude-code        # an explicit subset
python3 install.py --uninstall                        # guarded, hash-checked removal
```

Restart affected sessions afterward. Host MCP permissions and hook approvals still apply — the installer never disables an approval prompt or overrides an existing deny list.

### ⚠️ Verify your workspace binding first

Native hooks read their worktree from the native event. **An MCP process is instead bound to the directory the host launches it in**, and some hosts launch MCP servers outside your repository.

Ask each host to call `jev_status` and check the `workspace` it reports **before** you rely on shared memory.

To pin every installed MCP entry to one worktree at install time:

```bash
python3 install.py --all --workspace /absolute/path/to/worktree --dry-run
```

This is a static pin, not dynamic multi-root selection; native hooks still use their own event cwd. Changing an existing binding is deliberate: uninstall, then reinstall. Server-name collisions error out rather than overwrite.

> Sources are shared across harnesses only when they resolve to the **same worktree path and the same memory home**. Branches inside one directory share a workspace; separate worktree directories do not. The package does not infer remote repository identity.

---

## How it works

```text
   native hook  ·  MCP  ·  CLI  ·  stdio bridge  ·  loopback JSON API
                              │
                              ▼
                  ┌───────────────────────┐
                  │  shared Python core   │   standard library + SQLite
                  └───────────┬───────────┘
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   canonical text       typed feature       explicit source
   + SHA-256 store      distributions       relationships
          └───────────────────┼───────────────────┘
                              ▼
        local lexical  +  cached typed  +  one-hop link retrieval
                              │
                              ▼
              optional, explicit JEV rerank  (opt-in, paid)
                              │
                              ▼
                   budgeted source excerpts
                              │
                              ▼
                    reasoning-model context
```

**Capture.** Canonical text — or canonical native-message JSON — is retained in SQLite with a content-derived identifier, a hash, and worktree/session/harness metadata, plus an independently redacted retrieval view. *This is not a claim that the package has archived every byte of an existing native transcript; it stores what was actually captured.*

**Retrieve.** Local retrieval blends SQLite FTS5/BM25 (with a lexical fallback), explicit pins, cached typed-role distributions, and one-hop caller-supplied relationships. The routing weights are heuristics. This alpha scans up to **500** cached features — it is not a production-scale typed index, and it contains no embeddings backend, learned budget policy, or autonomous causal-graph inference.

**Type (optional).** TypeSafe encoding asks `Choice`/`Noul` questions, preserves complete distributions alongside source hashes, and validates response shapes against the ontology. Source roles are `constraint`, `decision`, `failure`, `attempt`, `result`, and `background`. Relations are `supports`, `contradicts`, `supersedes`, `attempted_to_fix`, `resulted_in`, and `depends_on`. **These are retrieval features — not proof of correctness, and not calibrated risk probabilities.**

> [!NOTE]
> **A hash authenticates bytes, not truth.** `integrity_verified` means the stored content still matches its recorded SHA-256 — nothing about whether the source was right. Every retrieval is wrapped in an explicit header marking it **untrusted, possibly stale data, never authorization**. The agent must independently re-verify current files, commits, and tests.

---

## Integrations

Implemented surfaces — not a claim that every feature has been exercised in a running host.

| Target | Installed entry points | Active pruning |
|:--|:--|:--|
| **OpenClaw** | Local native plugin · authorized prompt enrichment · tool/result capture · native memory tools | — *retrieval/capture only* |
| **Hermes** | MCP · shell lifecycle hooks · per-user-turn retrieval · skill file | ✅ *only* as a [jev-bus](#coexisting-with-jev-prune-kit) stage |
| **OpenCode V1** | MCP · native message/system transforms · prompt/tool hooks · `/prune` preview · **jev-bus carrier** | ✅ persisted active-message view |
| **OpenCode V2** | MCP · `context` + `execute.after` plugin hooks · `/prune` preview · **jev-bus carrier** | ✅ persisted active-message view |
| **Codex** | MCP · `SessionStart` · `UserPromptSubmit` · tool and stop hooks · skill file | — *preview reports unsupported* |
| **Claude Code** | MCP · session/prompt/tool/stop hooks · skill · `/prune` preview | — *preview reports unsupported* |
| **Gemini CLI** | MCP · skill file | — *no lifecycle capture* |
| **Cursor** | MCP · skill file | — *no lifecycle capture* |
| **Copilot CLI** | MCP · skill file | — *no lifecycle capture* |
| **Pi** | — *no adapter of its own* | ✅ *only* as a [jev-bus](#coexisting-with-jev-prune-kit) stage |
| *Any other agent* | Generic MCP template · stdio JSON bridge · loopback API · example adapter | Bridge can return an approved view; the caller must use it |

OpenCode defaults to **V1** when no installed version is detectable. Select the separately implemented V2 API with `--opencode-api v2`. Switching families requires removing the previous integration first, so two loaders are never installed at once.

<details>
<summary><b>OpenClaw safeguards — read before enabling</b></summary>

<br>

This alpha **deliberately disables channel-, sender-, and chat-identified capture and retrieval**, because it has no multi-user principal isolation. It is built for a local owner's developer sessions, **not** a shared Discord/Telegram gateway.

Automatic enrichment additionally requires all of:

- a host implementing finalized `toolAuthority`,
- permission to call `jev_retrieve`, and
- an active hook invocation.

An older or restricted host therefore provides **no automatic recall** — that is intentional, not a bug. Existing plugin allowlists or denied prompt access can also block loading or enrichment. The installer *reports* these conflicts rather than expanding policy to work around them.

</details>

Skills are convenience guidance files. Whether they are auto-discovered depends on the host and version — the memory API never depends on a skill being loaded.

---

## The CLI

The default memory home is `~/.jev-context-fabric` (override with `JEV_CONTEXT_HOME`). The installer creates `bin/jev-context` and `bin/jev-context.cmd` but **does not modify PATH**. The absolute interpreter used at install time must remain available — don't delete a virtualenv you installed from.

The same core runs straight from the extracted package via `run.py`:

```bash
# Where am I, and what do I know?
python3 run.py --workspace /path/to/repo doctor
python3 run.py --workspace /path/to/repo status

# Remember something, with an origin you'll recognize later
python3 run.py --workspace /path/to/repo capture \
  --text "Decision: preserve canonical sources and keep native compact separate." \
  --origin "manual:architecture-decision" --session demo --harness manual

# Ask by meaning, not by filename
python3 run.py --workspace /path/to/repo retrieve "previous architecture decision"

# Read further into any returned src_... reference
python3 run.py --workspace /path/to/repo hydrate src_REPLACE_ME --offset 0 --max-chars 6000
```

`doctor` reports executables, source counts, known sessions, memory home, key presence, and workspace. It will **not** claim a native plugin loaded merely because its files exist on disk.

Hydration is redacted by default. `--verbatim` is an explicit, **CLI-only** operation — MCP and HTTP callers are structurally unable to request raw secret-bearing content.

### Memory tools

| Tool | Purpose | Read-only |
|:--|:--|:-:|
| `jev_status` | Inspect workspace and captured sessions | ✅ |
| `jev_capture` | Capture supplied source text | |
| `jev_retrieve` | Retrieve source-backed evidence within a budget | ✅ |
| `jev_page_fault` | Ask for missing evidence *by meaning*, not by filename | ✅ |
| `jev_hydrate` | Read another redacted page of a stored source | ✅ |
| `jev_pin` | Pin or unpin a captured source | |
| `jev_prune_plan` | Preview pruning — never applies it | |
| `jev_feature` | Inspect cached typed answers and distributions | ✅ |

All eight are available over MCP. The OpenClaw native plugin exposes `jev_status`, `jev_retrieve`, and `jev_hydrate`, with its hooks supplying automatic capture for eligible local runs.

---

## Opting in to TypeSafe / JEV

**Local mode is the default.** Installation, lifecycle hooks, MCP calls, and the loopback API make **no paid inference calls, ever.** Remote encoding is a separate, deliberate decision.

Put `TYPESAFE_API_KEY` in the environment of the process doing the encoding — never in a committed config file or a captured source. Then opt in explicitly:

```bash
python3 run.py config --enable-typesafe --allow-remote --model jev-1.13.0

python3 run.py --workspace /path/to/repo enrich --limit 10
python3 run.py --workspace /path/to/repo retrieve "why did authentication fail" --jev
```

`enrich` classifies unencoded sources with one bounded request each. `retrieve --jev` reranks up to eight candidates in a single request. Cached typed features then participate in ordinary local retrieval **without another paid call**.

Turn it back off at any time:

```bash
python3 run.py config --disable-typesafe
```

<details>
<summary><b>Exactly what crosses the network</b></summary>

<br>

The REST provider sends **redacted excerpts** to `https://api.typesafe.ai/v1/systemone`. It uses a four-second default timeout, caps input and output size, rejects redirects, and never logs response bodies containing credentials.

> [!CAUTION]
> **Redaction is best effort.** Enabling remote inference may disclose sensitive information the patterns do not recognize. Treat it as a real disclosure decision about a real repository.

`jev-1.13.0` is a configurable default request identifier taken from the documented response example. **Authenticated model availability was not tested in this build** — use an identifier available to your own account. No accuracy, latency, or cost-reduction result is claimed here.

</details>

---

## `/prune` is not `/compact`

This is the distinction the whole package is built around.

|  | `/prune` *(this package)* | `/compact` *(your host)* |
|:--|:--|:--|
| Mechanism | Excludes messages from an **active view** | A model **summarizes** the transcript |
| Originals | Canonical bytes stay in SQLite | Original meaning is rewritten away |
| Reversible | ✅ `prune-reset` restores the view | ❌ |
| Who approves | **You**, at the local CLI | Automatic or host-triggered |
| Owned by | This package | **Entirely your host — untouched** |

The installed `/prune` commands in Claude Code and OpenCode are **preview instructions, not permission to rewrite context**. On hosts without a message-replacement adapter, `jev_prune_plan` honestly returns `supported: false`.

```bash
# 1. Preview. This never changes anything.
python3 run.py --workspace /path/to/repo prune-plan \
  --session SESSION_ID --harness opencode-v2 \
  --goal "current task" --target-chars 12000

# 2. Approve the exact plan — local CLI only, explicit flag required.
python3 run.py --workspace /path/to/repo prune-apply PLAN_ID --enable-native

# 3. Change your mind at any time.
python3 run.py --workspace /path/to/repo prune-reset --session SESSION_ID --harness opencode-v2
```

**Only old, standalone assistant prose is ever eligible.** Every user, system, and developer message; every tool call and result; all media and thinking structures; the most recent **8** messages; all pins; and explicit guard-word constraints stay. That is a conservative heuristic, not a guarantee that no useful meaning can be omitted. Plans are invalidated the moment their source snapshot changes.

Approved exclusions persist in SQLite and are re-applied on supported model-context transforms. **The adapters never alter the native durable transcript.** A result reports `removed` only when the transform actually removed entries — a preview, a summary, or a retrieval is never reported as completed pruning.

> [!WARNING]
> **Native `/compact` stays entirely native.** This package registers no compaction hooks, invokes no summarizer, and **never falls back to compaction** from prune success, failure, no-op, or insufficient savings. It also does not intercept your host's independent context-pressure behavior, and cannot guarantee the host won't compact later — which may summarize its original stored transcript, including messages excluded only from an active view. Pressure-trigger interception and host context-engine replacement remain future work.
>
> **Budgets and savings here are measured in characters, not tokens.** No tokenizer-based reduction benchmark has been run.

---

## Coexisting with `jev-prune-kit`

[`jev-prune-kit`](https://github.com/CompleteTech-LLC-AI-Research/jev-prune-kit) prunes the
*other half* of a transcript: it substitutes **duplicate file-read result bodies**, where this
package removes **old assistant prose**. Disjoint work, and genuinely complementary — but both
wanted OpenCode's `experimental.chat.messages.transform` and both wanted `/prune`.

**jev-bus** settles that: one **carrier** per host owns the hook, every other package runs as
an ordered **stage** inside it.

```
OpenCode ── carrier: jev-context-fabric (this package: V1 + V2)
Pi       ── carrier: jev-prune-kit      (sole Pi adapter)
Hermes   ── carrier: jev-prune-kit      (real request middleware)

  the chain, in every carrier:
    100  jev-prune.dedup    claims tool-result:read
    200  jev-context.view   claims assistant-prose, message-remove, system-append
```

Each stage declares the message classes it may touch. **Two packages claiming overlapping
classes on one host is a hard install failure** — double-registration becomes impossible
rather than merely discouraged. Carrier slots go by a rank table both packages carry, so the
assignment is the same whichever you install first.

Order is load-bearing: this package keys messages as `sha256([index, message])`, so dedup
must run first — it substitutes bodies in place without changing the array length, and never
touches the prose this package owns.

**What each side gains.** This package reaches **Pi and Hermes**, where it has no adapter of
its own; `jev-prune-kit` reaches **OpenCode V2**, which it does not implement. Nothing changes
for OpenClaw, Codex, Claude Code, Gemini, Cursor or Copilot — those hosts expose no
outgoing-request transform at all, so neither package can project there, with or without the
bus. Both still install MCP, skills and capture in all of them.

Install both in either order; no flags needed. `install.py` reports what it took and what it
deferred:

```bash
python3 install.py --all --dry-run        # prints the jev_bus block before writing anything
python3 install.py --all --no-bus         # opt out; restores standalone 0.1.0 behaviour
python3 install.py --all --force-carrier  # take OpenCode from whoever currently holds it
```

> [!NOTE]
> **The bus is additive, never a prerequisite.** A stage that errors, times out or returns an
> unrecognized shape contributes nothing and the chain continues with that stage's own input;
> if the chain contributes no stage of this package at all, the adapter falls back to its own
> direct transform exactly as before jev-bus existed. It approves nothing either — `/prune`
> shows a combined, package-attributed preview, and approval stays in each package's own CLI.
> Joining a chain never starts a paid call.

The full contract, including the wire format and the vendored-file hashes, is
[`docs/BUS.md`](docs/BUS.md) — byte-identical in both repositories.

---

## Safety and uninstall

The installer previews changes, writes restrictive-permission backups where the OS supports them, writes atomically, records hashes and ownership, detects concurrent edits, and rolls back ordinary write failures. Reinstalling an unchanged configuration is idempotent and changes zero files.

JSON/JSONC/JSON5 files are rewritten as JSON: unrelated values survive, but comments and formatting are normalized — **the exact original bytes are backed up**. TOML and YAML use round-trip parsers. Conflicting MCP names, symlinked output paths, malformed files, and edited owned artifacts all raise an error instead of being silently replaced.

```bash
python3 install.py --uninstall --dry-run
python3 install.py --uninstall
```

Uninstall restores or deletes external files **only while their installed hashes still match**. Configuration you edited yourself is left untouched and reported as a conflict — meaning some integrations may stay active until you resolve them. Runtime files, original backups, settings, and the source database are retained deliberately. *Do not delete the runtime while a surviving host config still points at it.*

> [!NOTE]
> An OS or process crash mid-install can leave `.installer.lock` and a transaction journal behind. **There is no automatic hard-crash recovery.** Confirm no installer is running, inspect the receipt, backups, and journal, and reconcile partial writes before clearing a stale lock. See [docs/SECURITY.md](docs/SECURITY.md).

Alternative roots — `--home`, `--prefix`, `CODEX_HOME`, `HERMES_HOME`, `OPENCLAW_STATE_DIR`, `CLAUDE_CONFIG_DIR`, and `XDG_CONFIG_HOME` — are documented in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Bring your own agent

Not one of the eight? `generic-mcp.json` is generated in the installed home with real interpreter and runner paths. Merge its MCP entry into your client after verifying that client's schema — no universal config format is assumed beyond the eight explicit installers.

```bash
python3 -m unittest discover -s tests -v   # 109 Python tests
node tests/adapters.mjs                    # 19 mock-host adapter checks
python3 examples/demo.py                   # capture → retrieve → prune, in a temp dir
python3 verify_release.py                  # manifest integrity
```

No live TypeSafe call and no harness execution occurs in any of these. The tested runtime and precise results live in [TEST_REPORT.md](TEST_REPORT.md).

| | |
|:--|:--|
| [`examples/agent_adapter.py`](examples/agent_adapter.py) | A generic subprocess client |
| [`examples/demo.py`](examples/demo.py) | Local capture/retrieval/pruning walkthrough |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | The bridge, the loopback API, extension contract |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Trust model and operational limits |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Every switch, root, and installed file |
| [`docs/BUS.md`](docs/BUS.md) | The jev-bus contract shared with `jev-prune-kit` |
| [`docs/VERIFIED_INTERFACES.md`](docs/VERIFIED_INTERFACES.md) | Which host interfaces were checked, and how |
| [`SETUP_PROMPT.md`](SETUP_PROMPT.md) | A prompt for letting a local agent install this safely |

---

## Scope and non-goals

This is an **executable starting package, not the full proposed research platform**. It does not import old native transcripts, enumerate repositories, synchronize machines, calibrate JEV uncertainty, reconstruct natural language from numeric IDs, replace host context engines, bypass approvals, or provide multi-tenant access control. Cross-harness continuation can only use sources that were actually captured. A complete long-context benchmark and a live-host compatibility matrix remain **unmeasured**.

<div align="center">
<br>

Original code is **MIT** licensed. Vendored configuration parsers keep their original licenses under [`licenses/`](licenses/) — see [`THIRD_PARTY_NOTICES.json`](THIRD_PARTY_NOTICES.json).

*This package is not an official TypeSafe or harness-vendor release.*

**v0.1.0 · alpha reference implementation · 2026-09-20**

</div>
