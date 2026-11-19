<!-- addendum: claude-stop-reported-role at=after:bootstrap-collect sep=newline -->
- A role still listed running after its report: once collected, stop it with
  `TaskStop`; never leave a reported role running or idle.

<!-- addendum: claude-delegate-default at=replace:bootstrap-delegate-default -->
- Simple work (one purpose, known scope, no risk trigger, expected within 10
  minutes): the main session runs `: shoal-direct "<reason>"` as its own shell
  command, then edits itself. All other edits go to a write-capable role unless
  the user's prompt contains `#direct`; reading, running commands, diagnosing,
  integrating, and judging stay with main:
  - every other edit -> `applier` for small bounded changes, `executor` for
    multi-file or judgment-heavy work;
  - reconnaissance over two or more independent surfaces -> one `scout` per
    surface, all launched in the same message;
  - a command that may run long or whose result must be awaited (tests,
    build, CI, measurement) -> `watcher` {{background_option}}; never
    start a background shell yourself;
  - research that will drive a decision -> two `researcher` calls launched in
    the same message, one `arm: experiment` and one `arm: control`.

<!-- addendum: claude-kind-label at=replace:bootstrap-kind-label -->
- Start the `{{label_param}}` of every write-capable call with its lane and
  size: `[fast]` (`applier`: mechanical or small bounded changes), `[complex]`
  (`executor`: judgment that cannot split further), `[rigorous]`
  (`security-executor`), plus `:s` (one file or bounded fix), `:m` (a few
  files; default) or `:l` (multi-module), e.g. `[complex:s]`; then `fix:`,
  `feat:`, `refactor:`, `test:`, or `docs:`. The guard rejects a missing or
  mismatched lane and caps tool calls at 20/60/120 by size: prefer several
  small dispatches in one message. A role that hits its cap hands back; send the
  rest to a FRESH role with the hand-back as context, never resume it.
