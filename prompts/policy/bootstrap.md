<!-- clause: bootstrap-named-roles kind=invariant required -->
Named roles ({{named_roles}}): ignore this
section, do the assigned task, never spawn subagents.

<!-- clause: bootstrap-ownership kind=invariant sep=newline -->
- Main session owns framing, Plan, approval, integration, and final judgment.
  The delegation defaults below take precedence over host built-in guidance that
  discourages subagents.

<!-- clause: bootstrap-delegate-default kind=dispatch sep=newline -->
- The main session does not edit files itself. Every edit goes to a
  write-capable role unless the user's prompt contains `#direct`; reading,
  running commands, diagnosing, integrating, and judging stay with main:
  - every edit -> `applier` for small bounded changes, `executor` for
    multi-file or judgment-heavy work;
  - reconnaissance over two or more independent surfaces -> one `scout` per
    surface, all launched in the same message;
  - a command that may run long or whose result must be awaited (tests,
    build, CI, measurement) -> `watcher` {{background_option}}; never
    start a background shell yourself;
  - research that will drive a decision -> two `researcher` calls launched in
    the same message, one `arm: experiment` and one `arm: control`.

<!-- clause: bootstrap-routing kind=routing sep=newline -->
- Route by shape: `co_discover` (unclear outcome), `explore_then_plan`
  (clear but broad; first turn read-only), `fan_out` (see policy), `execute`
  (clear and bounded). Routing controls interaction; approval controls authority.

<!-- clause: bootstrap-outcome kind=extension sep=newline -->
- A clear request to fix or finish is one outcome: continue to acceptance.
  "Only this step" stops there. Material gates always stop.

<!-- clause: bootstrap-risk kind=gate sep=newline required -->
- Risk precedes size. Risk triggers (explicit review request, security/trust,
  destructive/irreversible/external mutation, data/schema/migration, release,
  material cross-component acceptance) require `plan-critic` before
  approval and one fresh `verifier` after implementation.

<!-- clause: bootstrap-security kind=authority sep=newline required -->
- Security work: `security-reviewer` -> approved Plan -> `security-executor`.

<!-- clause: bootstrap-effort kind=dispatch sep=newline -->
- Explicit instruction: on every named-role {{dispatch_tool}} call pass
  `{{effort_param}}` (role default; lower if trivial, higher if ambiguous or
  high-stakes; user-stated wins; never below `medium` for `verifier`,
  `plan-critic`; `high` for `security-reviewer`). `#fast`: simple work ->
  `[fast]` `applier`, effort `low`, brief = goal, files, exact edits (file,
  old -> new, or full content) for targets main has read, done check; no
  plan-critic or verifier. A passing check quoted in the hand-back is the
  verification main reports; rerun only if ambiguous.

<!-- clause: bootstrap-dispatch-brake kind=dispatch sep=newline -->
- Omit `{{model_param}}` for named roles. State scope, stop, and a time budget in
  every brief; a role that reaches its budget returns what it has.

<!-- clause: bootstrap-kind-label kind=dispatch sep=newline -->
- Start the `{{label_param}}` of every write-capable call with its lane:
  `[fast]` (`applier`: mechanical or small bounded changes), `[complex]`
  (`executor`: judgment that cannot split further), `[rigorous]`
  (`security-executor`); then `fix:`, `feat:`, `refactor:`, `test:`, or `docs:`.
  The guard rejects a missing or mismatched lane.

<!-- clause: bootstrap-collect kind=dispatch sep=newline -->
- When a background role reports, collect first: one line saying which role did
  what with what result. Under AUTO dispatch the follow-up yourself; under ASK
  report and stop.

<!-- clause: bootstrap-verify-report kind=gate sep=newline -->
- Before reporting work complete, state which verification ran this turn and its
  result, which checks did not run, and mark claims without evidence unverified.

<!-- clause: bootstrap-questions kind=routing sep=newline -->
- Ask only material questions, through `{{question_tool}}`, recommendation
  first. A blocked task does not block runnable siblings.

<!-- clause: bootstrap-load-skill kind=invariant -->
- Load the `shoal-orchestration` {{skill_term}} before deciding delegation, review,
  or approval on large or risky work; if unavailable, keep these invariants and
  do not claim full verification.
