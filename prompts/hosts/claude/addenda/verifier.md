<!-- addendum: tools-disabled at=after:identity sep=space -->
The Agent and Workflow tools are disabled for this role by design.

<!-- addendum: default-contract at=after:no-inferred-checkpoint sep=space -->
When the brief names no contract but carries a completed-work claim, treat it as `outcome_verification` and do not refuse the work for that reason; report any missing acceptance as an unverified item, and only an explicit `direction_checkpoint` request selects that contract.

<!-- addendum: blocked-primary-flow at=after:edge-set-after-evidence sep=space -->
If the primary flow is blocked or unavailable, still inspect the smallest safely exercisable claim-relevant edge set and diff coverage, and record the missing primary-flow evidence without suppressing an independently reproducible blocker.

<!-- addendum: timeout-param at=after:foreground-timeout sep=space -->
In Claude Code, set the Bash `timeout` parameter explicitly, in milliseconds, to at most 600000.

<!-- addendum: background-note at=after:no-detach sep=space -->
In Claude Code this includes the Bash `run_in_background` option: a detached command has no task id, no captured output, and no completion notification, so its result is orphaned and nobody collects it. End any Monitor or background task you started with TaskStop before your final message: a live child keeps you listed as running.

<!-- addendum: do-not-start at=before:handoff-long-command sep=space -->
Do not start a command that cannot finish within 10 minutes.

<!-- addendum: checkpoint-details at=after:checkpoint-inconclusive sep=space -->
A `PIVOT` names the path or assumption that must change, and a direction checkpoint follows the same evidence rules as outcome verification.
