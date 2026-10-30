<!-- addendum: agy-plan-mode at=after:approval-gate sep=newline -->
- If Miyago has switched agy into `/plan` mode, stay there until approval.

<!-- addendum: pending-shared-auto-approved-permissions at=after:approval-gate sep=newline -->
- Auto-approved tool permissions are not Plan approval.

<!-- addendum: agy-readiness-brief at=after:plan-gate sep=newline -->
- Brief `plan-critic` with a `## Target readiness unit` block (`- ID:`,
  `- Kind:` `program envelope` or `execution slice`), the full Plan text, and
  evidence paths.

<!-- addendum: pending-shared-security-proportionate at=before:security-sensitive-routing sep=newline -->
- Keep security basic and proportionate; the goal is to avoid tunnel vision, not
  to shrink execution capability.

<!-- addendum: pending-shared-tell-plan-critic at=after:security-reviewer-first sep=space -->
Tell `plan-critic` you did so.

<!-- addendum: pending-shared-brief-adjacent at=after:security-reviewer-first sep=space -->
Brief `security-reviewer` to look at adjacent entry points and side effects, not
  only the named boundary.

<!-- addendum: pending-shared-security-executor-failure at=after:security-executor-after-approval sep=space -->
If it fails twice, re-scope or ask Miyago; do not quietly take the slice over.

<!-- addendum: pending-shared-near-security at=after:security-no-preapproval-write sep=newline -->
- Ordinary work that merely sits near a security surface does not need this
  track; use `executor` and have `verifier` probe the obvious abuse case.

<!-- addendum: pending-shared-brief-format at=after:one-shot-spec sep=newline join=space -->
Also state the output format and verification expectation in the brief.

<!-- addendum: agy-concurrent-entries at=after:parallel-launch sep=newline -->
- `invoke_subagent` accepts several entries to run concurrently.

<!-- addendum: agy-workspace-isolation at=after:parallel-launch sep=newline -->
- Give writing workers exclusive files, or workspace mode `branch` / `share` for
  isolation; read-only workers use `inherit`.
