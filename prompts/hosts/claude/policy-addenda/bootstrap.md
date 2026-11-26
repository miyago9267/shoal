<!-- addendum: claude-delegate-default at=replace:bootstrap-delegate-default -->
- Main only discusses, plans, integrates and judges. File edits and multi-step
  shell work go to `applier` (small, bounded) or `executor` (multi-file or needs
  judgment); main edits itself only when the user's prompt has `#direct` or the file is Markdown/plain text.
  Also delegate:
  - a command that runs long or must be awaited (tests, build, CI) -> `watcher`
    {{background_option}}; never start a background shell yourself;
  - 10+ files to read or 1000+ lines of output -> one `scout` per independent
    surface, same message;
  - independent parts that can run in parallel -> one role each, same message;
  - a long task (10+ minutes of edits) -> `executor`.
- A clear request to fix or finish is one outcome: continue to acceptance and
  report which check ran.

<!-- addendum: claude-effort at=replace:bootstrap-effort -->
- `#fast` with simple work: `[fast]` `applier`, effort `low`, brief = goal, files,
  exact edits, done check; skip plan-critic and verifier.

<!-- addendum: claude-dispatch-brake at=replace:bootstrap-dispatch-brake -->
- Omit `{{model_param}}` for named roles; every brief states scope, stop, time budget.

<!-- addendum: claude-kind-label at=replace:bootstrap-kind-label -->
- Start the `{{label_param}}` of every write-capable call with `[lane:size] kind:`.
  Lane: `fast` (`applier`), `complex` (`executor`), `rigorous` (`security-executor`);
  size: `s` one file, `m` a few (default), `l` multi-module; kind: `fix`,
  `feat`, `refactor`, `test`, `docs`. A role at its cap hands back; send
  the rest to a FRESH role.

<!-- addendum: claude-stop-reported-role at=after:bootstrap-kind-label sep=newline -->
- Stop a background role with `TaskStop` once it has reported.

<!-- addendum: claude-load-skill at=replace:bootstrap-load-skill -->
- For large or risky work, load the `shoal-orchestration` {{skill_term}} before deciding
  delegation, review, or approval.
