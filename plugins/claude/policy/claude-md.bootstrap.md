<!-- shoal-claude v3.14.9-beta -->
<!-- markdownlint-disable-next-line MD041 -->
## Orchestration

Named roles (`scout`, `plan-critic`, `security-reviewer`, `applier`, `executor`, `verifier`, `security-executor`, `watcher`, `researcher`): ignore this
section, do the assigned task, never spawn subagents.

- Main edits itself when the target is known and the change is small; under
  `SHOAL_GUARD_R1=declare` it first runs `: shoal-direct "<reason>"` as its own
  shell command (`#direct` also allows it). Delegate only when one of these
  fits, `applier` for small bounded edits and `executor` for multi-file work:
  - 10+ files to read or 1000+ lines of output for a small change -> one
    `scout` per independent surface, same message;
  - independent parts that can run in parallel -> one role each, same message;
  - a long task (10+ minutes of edits) -> `executor`;
  - a command that runs long or must be awaited (tests, build, CI) -> `watcher`
    with `run_in_background: true`; never start a background shell yourself.
- A clear request to fix or finish is one outcome: continue to acceptance and
  report which check ran.
- Risk precedes size. Risk triggers (explicit review request, security/trust,
  destructive/irreversible/external mutation, data/schema/migration, release,
  material cross-component acceptance) require `plan-critic` before
  approval and one fresh `verifier` after implementation.
- Security work: `security-reviewer` -> approved Plan -> `security-executor`.
- `#fast` with simple work: `[fast]` `applier`, effort `low`, brief = goal, files,
  exact edits, done check; skip plan-critic and verifier.
- Omit `model` for named roles; every brief states scope, stop, time budget.
- Start the `description` of every write-capable call with `[lane:size] kind:`.
  Lane: `fast` (`applier`), `complex` (`executor`), `rigorous` (`security-executor`);
  size: `s` one file, `m` a few (default), `l` multi-module; kind: `fix`,
  `feat`, `refactor`, `test`, `docs`. A role at its cap hands back; send
  the rest to a FRESH role.
- Stop a background role with `TaskStop` once it has reported.
- For large or risky work, load the `shoal-orchestration` Skill before deciding
  delegation, review, or approval.
