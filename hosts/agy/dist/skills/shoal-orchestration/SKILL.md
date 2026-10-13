---
name: shoal-orchestration
description: Shoal orchestration for agy - routing, Plan and approval gate, dispatch to named roles, fresh verification, recovery. Load before deciding delegation, review, or approval on large, ambiguous, architectural, risky, cross-surface, or plan-first work.
---

# Shoal orchestration (agy)

This skill is the detailed procedure behind the always-on shoal bootstrap.
The bootstrap stays authoritative for its invariants; this skill supplies the
complete contract.

## First move

1. Classify the interaction shape: `co_discover`, `explore_then_plan`, or
   `execute` (see the policy's routing section).
2. Set `execution_scope`, `review_intent`, and the discovery budget from the
   policy extensions.
3. Apply risk triggers before size, then the phase gate and dispatch brake
   before every invoke_subagent call.

## References

Read only the part needed for the current decision:

- [orchestration-policy.md](references/orchestration-policy.md): routing,
  lifecycle gates, dispatch and ownership, severity, recovery, AUTO/ASK,
  parallel and runtime mechanics.
- [workflow-extensions.md](references/workflow-extensions.md): outcome-level
  continuation, turn-scoped review intent, discovery budget, decision
  checkpoint through `ask_question`, task ledger and blocked-task
  isolation, continuation across user input, review-service circuit breaker,
  and verifier direction checkpoint.

If a reference is unavailable, keep the bootstrap invariants, work fail-soft,
and do not claim full shoal verification.
