# Primary interface references

Reviewed on **September 20, 2026**. These are documentation/source-contract checks, not claims that a live installed host accepted this package. This file intentionally separates confirmed public entry points from package limitations.

| System | Primary reference | Contract used / qualification |
|---|---|---|
| TypeSafe | https://docs.typesafe.ai/introduction/quickstart | POST `/v1/systemone`; bearer key; `state`, `model`, typed `questions`; `answers` with Choice distributions/Noul values. Live model availability and paid responses untested. |
| TypeSafe concepts | https://docs.typesafe.ai/introduction | Typed judgments, not lossless natural-language reconstruction. |
| Codex hooks | https://learn.chatgpt.com/docs/hooks | `hooks.json`, command hooks, session/prompt/tool/stop events. Prompt hooks are not a universal active-transcript replacement API. |
| Codex MCP | https://developers.openai.com/codex/mcp | `mcp_servers` entries in `config.toml`; stdio command/arguments. |
| Claude Code hooks | https://code.claude.com/docs/en/hooks | Settings hook configuration and `hookSpecificOutput.additionalContext` envelopes. No transcript replacement claimed. |
| Claude Code MCP | https://code.claude.com/docs/en/mcp | User MCP registry in `~/.claude.json`; preserve existing project/server entries. |
| OpenCode V1 plugins | https://opencode.ai/docs/plugins/ | Global/local JS plugins and native V1 hooks. Experimental message/system transforms require live version checks. |
| OpenCode MCP | https://opencode.ai/docs/mcp-servers/ | `mcp.NAME` local server with command array. |
| OpenCode V2 plugins | https://opencode.ai/v2/docs/build/plugins/ | V2 default `id`/`setup`; plural `plugins`; `ctx.session.hook("context")`; `ctx.tool.hook("execute.after")`. Context mutations affect outgoing model call, not durable history. |
| OpenCode migration | https://opencode.ai/v2/docs/build/plugins/migrate-v1 | V1/V2 hooks are not interchangeable. The package supplies separate adapters. |
| OpenClaw plugin config | https://docs.openclaw.ai/tools/plugin | Local plugin paths, entries, enable/allow/deny policy; this package does not replace a memory slot or install policy. |
| OpenClaw hook reference | https://docs.openclaw.ai/plugins/hooks/reference | Synchronous registration, async lifecycle handlers where allowed; observer versus mutation distinctions. |
| OpenClaw prompt authority | https://docs.openclaw.ai/plugins/hooks/prompt-and-session | `before_prompt_build`, `prependContext`, `requiresToolAuthority`, `allows`, `assertActive`, optional current-user fields. Package fails closed without authority; no compatibility with older prompt APIs is claimed. |
| Hermes MCP | https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/ | YAML `mcp_servers` command/args. |
| Hermes hooks | https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks/ | Shell hooks, JSON envelopes with `extra`, returned `context`, first-use approval. `pre_llm_call` is per user turn, not every tool-loop model request. |
| Gemini CLI | https://geminicli.com/docs/tools/mcp-server/ | `mcpServers` in settings; package keeps `trust: false`. No automatic hooks installed. |
| Cursor | https://cursor.com/docs/context/mcp | User MCP server configuration; package supplies MCP only. |
| Copilot CLI | https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers | `~/.copilot/mcp-config.json`, local command/args/tools. Exposure of tools does not bypass native execution approvals. |
| MCP transport | https://modelcontextprotocol.io/specification/2025-06-18/basic/transports | Stdio newline-delimited JSON-RPC; stdout contains protocol only. Package implements a minimal tools server, not the full SDK feature set. |

Harness libraries and exact event shapes can change. Capability claims must be revalidated against the actual host version. A successful installer/config parser test proves file generation, not that a host loaded an API contract. A successful mock-host test proves the package's translation and bridge behavior against those fixtures, not end-to-end native integration.

All native host version fields remain **unverified** in the installation report. `doctor` checks availability and memory state, not compatibility certification.
