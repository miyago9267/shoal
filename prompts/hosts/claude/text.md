<!-- text: relay-write-rules -->
This relay writes files. The caller must dispatch you with worktree isolation, so your working directory is a linked worktree. The runner returns `blocked` anywhere else; do not work around that (no `cd` elsewhere, no `git worktree add`). The caller must follow every write relay with a fresh verifier before trusting the hand-back.

<!-- text: relay-run-step -->
Call Bash with `timeout: {{bash_timeout_ms}}` so it outlives the runner's {{timeout}}s limit.

<!-- text: relay-description-suffix -->
Runs on {{vendor}} through the shoal relay.

<!-- text: relay-write-description-suffix -->
Dispatch it with worktree isolation and follow it with a fresh verifier.

<!-- text: plugin-hooks-description -->
shoal policy bootstrap for Claude Code.

<!-- text: guard-hooks-description -->
shoal dispatch guard for Claude Code.

<!-- text: plugin-description -->
Shoal orchestration roles, skill and policy bootstrap for Claude Code.

<!-- text: guard-plugin-description -->
Optional dispatch guard for the shoal Claude Code plugin (hooks only).

<!-- text: marketplace-description -->
Marketplace for the shoal Claude Code plugins.

<!-- text: marketplace-plugin-description -->
Shoal orchestration roles, skill and policy bootstrap.

<!-- text: marketplace-guard-description -->
Optional dispatch guard hooks for the shoal plugin.
