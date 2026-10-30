<!-- clause: skill-intro kind=invariant sep=newline -->
This {{skill_term}} is the detailed procedure behind the always-on shoal bootstrap.

<!-- clause: skill-bootstrap-authority kind=invariant -->
The bootstrap stays authoritative for its invariants; this {{skill_term}} supplies the
complete contract.

<!-- clause: first-move-heading kind=heading -->
## First move

<!-- clause: first-move-steps kind=routing -->
1. Classify the interaction shape: `co_discover`, `explore_then_plan`, `fan_out`, or
   `execute` (see the policy's routing section).
2. Set `execution_scope`, `review_intent`, and the discovery budget from the
   policy extensions.
3. Apply risk triggers before size, then the phase gate and dispatch brake
   before every {{dispatch_tool}} call.

<!-- clause: executor-brief-bound kind=dispatch sep=newline -->
An `executor` brief names its file/module bound; work larger than that is split into several executors or routed to `applier`.

<!-- clause: references-heading kind=heading -->
## References

<!-- clause: references-intro kind=invariant -->
Read only the part needed for the current decision:

<!-- clause: reference-policy kind=routing sep=newline -->
- [{{policy_doc}}]({{references_dir}}{{policy_doc}}): routing,
  lifecycle gates, dispatch and ownership, severity, recovery, AUTO/ASK,
  parallel and runtime mechanics.

<!-- clause: reference-extensions kind=routing -->
- [{{extensions_doc}}]({{references_dir}}{{extensions_doc}}): outcome-level
  continuation, turn-scoped review intent, discovery budget, decision
  checkpoint through `{{question_tool}}`, task ledger and blocked-task
  isolation, continuation across user input, review-service circuit breaker,
  and verifier direction checkpoint.

<!-- clause: reference-fail-soft kind=invariant -->
If a reference is unavailable, keep the bootstrap invariants, work fail-soft,
and do not claim full shoal verification.
