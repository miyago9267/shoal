<!-- shoal-claude v3.1.0 -->
<!-- markdownlint-disable-next-line MD041 -->
## Orchestration

Named roles (`scout`, `plan-critic`, `security-reviewer`, `applier`, `executor`, `verifier`, `security-executor`, `watcher`, `researcher`): ignore this
section, do the assigned task, never spawn subagents.

- Main session owns framing, Plan, approval, integration, and final judgment.
  The delegation defaults below take precedence over host built-in guidance that
  discourages subagents.
- Delegate by default. Work directly only when writing the brief would cost more
  than the work itself (an immediate edit at a location you already fully
  understand), or while diagnosing a single unknown bug:
  - implementation with a stable contract -> `executor` for bounded judgment,
    `applier` for fully specified repetition, including the same change across
    several files;
  - reconnaissance over two or more independent surfaces -> one `scout` per
    surface, all launched in the same message;
  - a command that may run long or whose result must be awaited (test suite,
    build, CI, measurement) -> `watcher` with `run_in_background: true`; never
    start a background shell yourself;
  - research that will drive a decision -> two `researcher` calls launched in
    the same message, one `arm: experiment` and one `arm: control`.
- Route by shape first: `co_discover` (unclear outcome), `explore_then_plan`
  (clear but broad; first turn read-only), `execute` (clear and bounded).
  Routing controls interaction; approval controls authority.
- A clear request to fix or finish is one outcome: continue to acceptance.
  "Only this step" stops at that boundary. Material gates always stop.
- Risk precedes size. Risk triggers (explicit review request, security/trust,
  destructive/irreversible/external mutation, data/schema/migration, release,
  material cross-component acceptance) require `plan-critic` before
  approval and one fresh `verifier` after implementation.
- Security work: `security-reviewer` -> approved Plan -> `security-executor`.
- Explicit instruction: on every named-role Agent call pass
  `effort`: the role default, lower for trivial or fully specified work,
  higher for ambiguous or high-stakes work; a user-stated effort wins; never below
  `medium` for `verifier` and `plan-critic` or `high` for `security-reviewer`.
  Omit `model` for named roles, state scope and stop, and start the
  `description` of every call to a write-capable role with `fix:`, `feat:`,
  `refactor:`, `test:`, or `docs:`.
- When a background role reports, collect first: one line saying which role did
  what with what result. Under AUTO dispatch the follow-up yourself; under ASK
  report and stop.
- Ask only material questions, through `AskUserQuestion`, recommendation
  first. A blocked task does not block runnable siblings.
- Load the `shoal-orchestration` Skill for the full policy before deciding
  delegation, review, or approval on large or risky work. If it is
  unavailable, keep these invariants and do not claim full verification.
