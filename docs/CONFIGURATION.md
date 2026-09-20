# Configuration and installed files

## Installer switches

| Switch | Effect |
|---|---|
| no selection switch | Detect installed binaries or known config roots; install those integrations |
| `--all` | Configure all eight supported application targets |
| `--harness NAME ...` | Configure only the selected targets |
| `--dry-run` | Show paths/actions without writing configuration, backups, runtime, or a receipt |
| `--home PATH` | Use a test/alternative user home; ignore harness environment-root overrides |
| `--prefix PATH` | Place the shared installed runtime/data in a different directory |
| `--workspace PATH` | Pin generated MCP server processes to one existing worktree |
| `--opencode-api auto\|v1\|v2` | Choose the matching separately implemented plugin API |
| `--uninstall` | Guardedly restore external integration files using the receipt |
| `--no-bus` | Do not participate in jev-bus; claim every hook this package supports, as in 0.1.0 |
| `--force-carrier` | Take the OpenCode transform hook even if another jev-bus package currently carries it |

Detection executes only `opencode --version` when available to select its plugin API, with a timeout. It does not download applications. `--all` is explicit configuration of absent targets, not evidence that they are installed.

## jev-bus registry

Coordination with another context-transforming package (see [BUS.md](BUS.md)) is recorded in
`~/.jev/bus/v1/registry.json`, overridable with the **`JEV_BUS_HOME`** environment variable.
The installer negotiates before it plans, so `--dry-run` prints the resulting `jev_bus` block
without writing anything.

The registry is additive metadata, **never a file-ownership claim**: `install-receipt.json`
remains the sole record of which files this package owns. Uninstalling removes only this
package's entries, and a vacated carrier slot is left empty rather than reassigned.

## Default external files

| Target | Paths touched |
|---|---|
| Claude Code | `~/.claude.json`; `~/.claude/settings.json`; `~/.claude/skills/jev-context/SKILL.md`; `~/.claude/commands/prune.md` |
| Codex | `~/.codex/config.toml`; `~/.codex/hooks.json`; `~/.agents/skills/jev-context/SKILL.md` |
| Hermes | `~/.hermes/config.yaml`; `~/.hermes/skills/jev-context/SKILL.md` |
| OpenCode | one of `~/.config/opencode/opencode.json` or `opencode.jsonc`; V1 `plugins/jev-context.js`; `skills/jev-context/SKILL.md`; `commands/prune.md` **only when this package carries OpenCode on the bus** |
| OpenClaw | `~/.openclaw/openclaw.json`; `~/.openclaw/skills/jev-context/SKILL.md` |
| Gemini CLI | `~/.gemini/settings.json`; `~/.gemini/skills/jev-context/SKILL.md` |
| Cursor | `~/.cursor/mcp.json`; `~/.cursor/skills/jev-context/SKILL.md` |
| Copilot CLI | `~/.copilot/mcp-config.json`; `~/.copilot/skills/jev-context/SKILL.md` |

Existing `/prune` commands not owned by this package are retained and reported, not overwritten. A conflicting skill file is also not overwritten. V1 and V2 OpenCode registrations must not coexist; uninstall before changing API families.

The following environment overrides are read unless `--home` is supplied: `CODEX_HOME`, `HERMES_HOME`, `OPENCLAW_STATE_DIR`, `CLAUDE_CONFIG_DIR`, `XDG_CONFIG_HOME` (OpenCode). **Claude's global MCP registry remains `~/.claude.json` in this implementation**, even with `CLAUDE_CONFIG_DIR`; verify custom/profile setups in the dry run. `OPENCLAW_CONFIG_PATH`, arbitrary named profiles, portable installs, remote containers, and per-project policy layers are not auto-discovered. Do not infer that a global entry takes precedence over an organization policy.

## Installed prefix

```text
~/.jev-context-fabric/
  runner.py
  runtime/jev_context/
  adapters/
    adapter-config.json
    bridge.mjs
    openclaw/
    opencode-v1/
    opencode-v2/
  bin/jev-context
  bin/jev-context.cmd
  config.json
  generic-mcp.json
  install-receipt.json
  backups/<transaction>/
  memory.sqlite3                 # created when the core first runs
  http-token                     # created only for the optional HTTP server
```

Normal runtime imports no third-party package. The extracted installer retains vendored parsers and is used for uninstall/reinstall; keep the ZIP or extracted package. The installed runtime does not depend on the extracted directory remaining at its original path.

The default CLI memory home can be overridden with `JEV_CONTEXT_HOME` or global `--home`. Generated hooks/MCP entries contain an explicit installed home, so moving it requires reinstalling/updating those entries. Use identical memory homes for cross-harness sharing.

## Core flags

`config.json` defaults to local inference, automatic capture/injection enabled, native prune views disabled, 6,000 evidence characters, 16,000 maximum remote-state characters, a four-second network timeout, and eight protected recent messages.

```bash
python3 run.py config --disable-capture
python3 run.py config --disable-injection
python3 run.py config --enable-capture --enable-injection
```

Disabling capture stops automatic hook capture and native-message snapshots; supported context transforms then skip pruning. Explicit local `capture` and model-requested `jev_capture` are still deliberate capture operations. Disabling injection suppresses automatically injected evidence, not explicit retrieval. An approved prune view is independent; reset it explicitly to restore the original view.

Each CLI global option (`--home`, `--workspace`) must appear **before** the subcommand. Installed launchers already supply `--home`, but callers may pass a later global `--home` before the subcommand to override it deliberately.

## Validation after installation

Open an actual repository in each target, call `jev_status`, and check `workspace`. Submit a nonsensitive unique test phrase and use a normal tool in a hook-enabled host. Call status again and confirm its native session/harness appears in captured sources. Retrieve the phrase and hydrate its source. On MCP-only targets, explicitly call `jev_capture`; automatic capture is not installed there.

For OpenCode, run the explicit plan/approval workflow in a disposable test session, inspect the next model-context transform, and verify protected user/tool/recent messages remain. `doctor` and file existence cannot establish that the host accepted a hook, consumed returned context, or omitted messages.

For OpenClaw, verify the local plugin is enabled and the native `jev_retrieve` tool is allowed. Automatic recall fails closed without finalized tool authority. For Hermes, review the first-use shell-hook approval prompt. Rejected approvals are preserved.
