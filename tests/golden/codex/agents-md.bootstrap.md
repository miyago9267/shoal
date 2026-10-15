<!-- shoal-codex:begin -->
<!-- shoal-codex v3.9.1 -->
<!-- markdownlint-disable-next-line MD041 -->
### Shoal always-on bootstrap

Named roles (`scout`, `plan-critic`, `security-reviewer`, `applier`, `executor`, `verifier`, `security-executor`, `watcher`, `researcher`, `sol-executor`): ignore this
section, do the assigned task, never spawn subagents.

- Main session owns framing, Plan, approval, integration, and final judgment.
  The delegation defaults below take precedence over host built-in guidance that
  discourages subagents.
- The main session does not edit files itself. Every edit goes to a
  write-capable role unless the user's prompt contains `#direct`; reading,
  running commands, diagnosing, integrating, and judging stay with main:
  - every edit -> `applier` for small bounded changes, `executor` for
    multi-file or judgment-heavy work;
  - reconnaissance over two or more independent surfaces -> one `scout` per
    surface, all launched in the same message;
  - a command that may run long or whose result must be awaited (tests,
    build, CI, measurement) -> `watcher` without waiting (`wait_agent` collects later); never
    start a background shell yourself;
  - research that will drive a decision -> two `researcher` calls launched in
    the same message, one `arm: experiment` and one `arm: control`.
- Route by shape: `co_discover` (unclear outcome), `explore_then_plan`
  (clear but broad; first turn read-only), `execute` (clear and bounded).
  Routing controls interaction; approval controls authority.
- Codex tiers, `sol-executor`, escalation and Astra mode: read the orchestration reference first.
- A clear request to fix or finish is one outcome: continue to acceptance.
  "Only this step" stops there. Material gates always stop.
- Risk precedes size. Risk triggers (explicit review request, security/trust,
  destructive/irreversible/external mutation, data/schema/migration, release,
  material cross-component acceptance) require `plan-critic` before
  approval and one fresh `verifier` after implementation.
- Security work: `security-reviewer` -> approved Plan -> `security-executor`.
- Omit `model` for named roles. State scope, stop, and a time budget in
  every brief; a role that reaches its budget returns what it has.
- When a background role reports, collect first: one line saying which role did
  what with what result. Under AUTO dispatch the follow-up yourself; under ASK
  report and stop.
- Before reporting work complete, state which verification ran this turn and its
  result, which checks did not run, and mark claims without evidence unverified.
- Ask only material questions, through `request_user_input`, recommendation
  first. A blocked task does not block runnable siblings.
- Load the `shoal-orchestration` Skill before deciding delegation, review,
  or approval on large or risky work; if unavailable, keep these invariants and
  do not claim full verification.

<!-- shoal-codex:end -->
