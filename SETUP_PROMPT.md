# Local coding-agent setup prompt

Inspect this package and its README, SECURITY, TEST_REPORT, and installer dry run before applying changes. Do not send captured data to a remote model or enable TypeSafe inference without separate explicit consent.

Determine the user's intended worktree and which harnesses are present. Run `python install.py --all --dry-run` when they requested all targets; otherwise use detection or an explicit selection. Explain any config collisions, edited files, exclusive plugin allowlists, unsupported profile paths, or MCP workspace ambiguity. Do not bypass an existing deny policy or rewrite unrelated configuration to make installation pass.

After the user-authorized installation, verify the real host loads the integration, check `jev_status` workspace, perform a nonsensitive capture/retrieve/hydrate test, and report which native lifecycle events actually fired. Do not label a host verified merely because its binary or config exists.

Keep `/prune` separate from `/compact`. Preview candidates and require explicit local CLI approval. Do not invoke compact after a prune no-op, error, or insufficient savings. Do not promise to override the host's independent automatic context-pressure behavior; this package does not implement that control.

Run the included Python tests and Node mock-adapter checks. Report actual test results and any untested live integrations. Preserve canonical sources and backups. Never include API keys, private source data, or a user's home directory contents in a bug report.
