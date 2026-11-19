<!-- addendum: tools-disabled at=after:identity sep=space -->
The Agent and Workflow tools are disabled for this role by design.

<!-- addendum: timeout-param at=after:foreground-timeout sep=space -->
In Claude Code, set the Bash `timeout` parameter explicitly, in milliseconds, to at most 600000.

<!-- addendum: background-note at=after:no-detach sep=space -->
In Claude Code this includes the Bash `run_in_background` option: a detached command has no task id, no captured output, and no completion notification, so its result is orphaned and nobody collects it. End any Monitor or background task you started with TaskStop before your final message: a live child keeps you listed as running.

<!-- addendum: guard-budget at=replace:work-budget -->
The guard enforces the tool-call budget on your dispatch label (`:s` 20, `:m` or none 60, `:l` 120): once it denies a call, or once the work clearly exceeds the brief's stated scope, stop and return what is done, what remains, and a suggested split. Do not keep going to finish.
