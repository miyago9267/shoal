---
name: plan-verifier
description: >
  Read-only fresh-context review of one stable Plan envelope or execution slice.
  Returns bare READY or structured REVISE and never executes, writes, or fixes.
model: inherit
prompt_mode: full
permission_mode: plan
agents_md: true
---

{{role_body}}