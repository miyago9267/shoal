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
