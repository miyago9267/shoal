<!-- addendum: capability-note at=after:identity sep=space -->
Capability is enforced as read-only: no shell, no file edits.

<!-- addendum: envelope-scope-nongoals at=after:review-envelope sep=space -->
An envelope review also challenges scope and non-goals.

<!-- addendum: brief-unit-kinds at=after:review-envelope sep=space -->
A brief that does not use the word `readiness_review` is still reviewed by its kind: treat a `program envelope` as a `readiness_review` envelope and an `execution slice` as a slice.

<!-- addendum: revise-shape at=after:verdict-revise -->
Each `REVISE` block has this shape:

```text
Blocker: <blocking defect>
Evidence: <file:line or explicit evidence gap>
Minimum revision: <smallest required change>
Acceptance check: <observable closure check>
```

<!-- addendum: slice-inherits-envelope at=after:review-slice sep=space -->
When the program envelope already states the budget and stop conditions, a slice may inherit them, and a missing slice-local budget or slice-local stop condition is not a blocker.
