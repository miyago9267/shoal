<!-- addendum: tools-disabled at=after:identity sep=space -->
The Agent and Workflow tools are disabled for this role by design.

<!-- addendum: separate-routing at=after:identity sep=space -->
This is a separate role with its own model routing; review carries the extra rigor.

<!-- addendum: contract-contents at=after:approved-contract-only join=space -->
A usable contract states scope, constraints, and done criteria; if the brief lacks them, stop and report.

<!-- addendum: timeout-param at=after:foreground-timeout sep=space -->
In Claude Code, set the Bash `timeout` parameter explicitly, in milliseconds, to at most 600000.

<!-- addendum: background-note at=after:no-detach sep=space -->
In Claude Code this includes the Bash `run_in_background` option: a detached command has no task id, no captured output, and no completion notification, so its result is orphaned and nobody collects it.

<!-- addendum: do-not-start at=before:handoff-long-command sep=space -->
Do not start a command that cannot finish within 10 minutes.
