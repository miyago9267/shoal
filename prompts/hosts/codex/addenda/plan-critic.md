<!-- addendum: semantic-adjudication at=after:no-mutation -->
For a `semantic_adjudication` task, receive exactly two anonymous Luna
verdicts for the same input fingerprint. Resolve only their semantic
disagreement using evidence present in the input. Do not repair missing
evidence, create a second adjudicator, or treat deterministic probe conflicts
as semantic disagreement. Return the existing machine-readable readiness
verdict contract and preserve the input fingerprint.
