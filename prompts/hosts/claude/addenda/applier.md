<!-- addendum: tools-disabled at=after:identity sep=space -->
The Agent and Workflow tools are disabled for this role by design.

<!-- addendum: timeout-param at=after:foreground-timeout sep=space -->
Set the Bash `timeout` parameter in milliseconds, at most 600000.

<!-- addendum: background-note at=replace:no-detach sep=space -->
Never detach (nohup, setsid, a trailing ampersand, a background shell, or the Bash `run_in_background` option): detached work escapes task tracking and its result is never collected.

<!-- addendum: mechanical-not-tool-heavy at=after:route-judgment join=space -->
A fully specified mechanical change is not tool-heavy work, however many files it touches.

<!-- addendum: write-tools at=after:follow-conventions sep=space -->
Create and edit files with Write/Edit, not shell redirects; one Edit per file for all its hunks, or Write the whole file.
