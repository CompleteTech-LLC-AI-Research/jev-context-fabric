# Test report — JEV Context Fabric 0.1.0

Date: September 20, 2026.

## Executed results

| Check | Result |
|---|---|
| Python standard-library unittest suite | **109 passed; 0 failed** (69 original + 32 jev-bus contract + 8 cross-package) |
| Native JavaScript mock-host checks | **19 passed; 0 failed** |
| Python syntax validation | 18 original-code/test/example files passed |
| JavaScript syntax validation | 5 module files passed |
| Offline bootstrap with `python -S` | Passed; all eight integration targets configured without site packages |
| Repeated all-target installation | Passed; second install changed zero files |
| ZIP extraction, integrity verification, and clean-home installation | Passed: extracted checksums, no-write dry run, all-target install, zero-change reinstall, installed MCP capture/retrieve, guarded uninstall |

Runtime: Python 3.13.5, Node v22.16.0, Linux. The final Python suite was also run with `-S`, disabling site-package initialization. Vendor parsers were loaded from the package. No pip/network installation was required.

## jev-bus coordination (added after the original run)

`docs/BUS.md` specifies the contract this package shares with `jev-prune-kit`. It is covered by
`tests/test_bus.py` (32 checks) and `tests/test_bus_integration.py` (8 checks).

The unit checks cover the closed claim vocabulary and wildcard subsumption, cross-package claim
conflict as a hard failure, install-order-independent carrier assignment by rank, deferral,
forced takeover, tie-keeps-incumbent, refusal of a carrier claim for a host with no transform
API, dry-run reporting without writes, idempotent re-registration, uninstall vacating a slot
without reassigning it, priority-then-name chain order, every stage receiving the pristine
`original_messages`, and passthrough on a stage that errors, declines, returns a malformed
shape, hits a claim conflict or meets an unreadable registry. They also check that this package
claims Pi/Hermes support **only** when actually registered on the bus, never merely because it
knows the host name.

The integration checks run **both packages as real subprocesses** in one chain: the rank table
settling OpenCode, both stages running in order, a duplicate read body substituted without
changing the array length, this package's `msg_` keys surviving that upstream substitution,
evidence appended only when the carrier accepts it, `plan` mutating nothing, and a deliberately
killed dedup stage leaving the active-view stage still working. They skip unless a
`jev-prune-kit` checkout is found; set `JEV_PRUNE_KIT` to point at one.

**Environment note.** The counts above are from the reference Linux runtime below. On Windows
with Python 3.14, this suite reports one pre-existing failure (`test_symlink_output_refused`)
and the Node adapter suite does not complete; both behave identically on the unmodified 0.1.0
tree, so they are environmental, not regressions. The jev-bus checks pass on both.

## Coverage

The Python suite exercises source hashes and exact captured Unicode/newline round trips, deduplication, worktree isolation, local redaction and CLI-only raw access, evidence budgets, pins, SQLite persistence, FTS query escaping/fallback, cached typed-role routing, explicitly linked-source retrieval, no-network defaults, and disabled automatic capture.

Prune tests cover unchanged defaults, unsupported harnesses, CLI approval, stale plans, preserved user/system/recent/tool/thinking/media messages, duplicate message identity, pinning after approval, repeated plans, durable active views, reset, and no compaction fallback.

Installer tests cover all-target generation, idempotence, unrelated JSON values, TOML/YAML comments, existing disabled-hook/deny policies, server-name collisions, malformed configs, symlinks, concurrent config edits, rollback after an injected write failure, byte-exact original restoration, removal of the external OpenCode loader, guarded uninstall conflicts, repeated uninstall/reinstall, explicit MCP workspace binding, and separate V1/V2 registration.

Protocol tests include an actual subprocess MCP initialize/capture/retrieve exchange, schema errors, notifications and stdout framing. Loopback HTTP tests use a real local server and check bearer authentication, Host/Origin rejection, raw hydration restrictions, and blocked remote/prune-apply endpoints. TypeSafe tests mock the HTTP response and validate request format, redaction, ontology keys, complete probability distributions, missing key/consent, and redirect rejection.

The Node suite exercises the real JavaScript-to-Python subprocess bridge and SQLite core under mock OpenCode V1, OpenCode V2, and OpenClaw hook registries. It confirms approved OpenCode views are re-applied to subsequent model inputs, and OpenClaw enrichment is withheld without finalized memory-tool permission or for identified channel contexts.

## Explicitly not tested

**No actual OpenClaw, Hermes, OpenCode, Codex, Claude Code, Gemini CLI, Cursor, or Copilot CLI process was launched.** Native plugin loading, version-specific event schemas, host consent screens, actual reasoning-model context consumption, and custom profile behavior still require local smoke tests. A mock passing does not certify those properties.

**No live TypeSafe request was made.** Credentials, authenticated model availability, network latency, billing, accuracy, calibration, evidence recall, and task-quality/token-reduction benchmarks are unmeasured. Character counts in the synthetic demo are not model-token savings.

The PowerShell/Windows and macOS wrappers are provided but were not executed on those operating systems. No hard-crash recovery, production multi-user security audit, pressure-trigger interception, or large-scale concurrency benchmark was run.

## Reproduce

```bash
python3 -S -m unittest discover -s tests -v   # set JEV_PRUNE_KIT to include the cross-package checks
node tests/adapters.mjs
python3 -S examples/demo.py
python3 verify_release.py
```

Machine-readable results: `tests/results/summary.json`. Raw successful logs: `tests/results/python-unittest.txt` and `tests/results/node-adapter-checks.txt`. The release manifest checks file integrity, not publisher authenticity.
