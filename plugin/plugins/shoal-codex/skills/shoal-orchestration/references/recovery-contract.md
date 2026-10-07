# Recovery contract

- Preserve the last verified good checkpoint.
- Retry a blocked verification only after material evidence, candidate, contract,
  prerequisite, or environment change.
- Never overwrite an independently changed user policy or external artifact.
- After repeated failed recovery passes, mark the affected slice
  `PAUSED_VERIFICATION` and continue only unrelated approved work.
- Report confirmed, fixed, deferred, regraded/rejected, paused, inconclusive, and
  unrun checks separately.
