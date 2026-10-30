# Verification contract

1. State the exact completed-work claim and acceptance conditions.
2. Run the primary flow and the cheapest relevant targeted checks.
3. For risk-triggered work, use a fresh-context verifier at the smallest coherent
   integration boundary.
4. Return one disposition: `CONFIRMED`, `REFUTED`, or `INCONCLUSIVE`.
5. For every finding, record priority, confidence, evidence, expected, actual, and
   recheck. Do not call a finding fixed without contrary evidence or a successful
   recheck of the original failure.

P0 freezes the affected slice. Introduced P1 and P2 regressions block the claim;
P3 and P4 remain advisories unless explicitly in scope.
