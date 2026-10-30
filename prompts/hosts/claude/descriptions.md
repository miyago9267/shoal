<!-- description: scout -->
Read-only reconnaissance. Use for any search, lookup, or "where/how is X" question that requires no judgment - locating files, symbols, usages, config values, or summarizing how something works across a codebase. Returns concise findings with file:line references. Cheapest way to gather facts; prefer it over reading files yourself when more than a couple of files are involved.

<!-- description: applier -->
Fast executor for small, bounded changes - one file or one tightly scoped purpose, such as a test fix, a doc fix, a config tweak, a rename, or a repetitive edit from an explicit spec. Makes minor local judgment calls but no design decisions; runs only the checks for what it touched; time-boxed to about 10 minutes. Stops and reports when scope grows, a design decision is needed, or the change spans modules, so the orchestrator can route to executor. Give it the goal, exact scope, and done-criteria.

<!-- description: executor -->
Implementation requiring judgment - feature work, bug fixes, refactors with design decisions, integration work. The default executor for real development tasks that are more than mechanical but don't need the frontier model. Give it the goal, constraints, and done-criteria; it makes reasonable local design decisions itself.

<!-- description: plan-critic -->
Read-only fresh-context review of one stable Plan envelope or execution slice before approval. Returns bare READY or structured REVISE and never executes, writes, or fixes.

<!-- description: verifier -->
Fresh-context calibrated outcome verification after implementation. Give it the claimed acceptance and relevant diff or paths; it independently runs tests, drives the affected flow, probes claim-relevant edge cases, and returns CONFIRMED, REFUTED, or INCONCLUSIVE. Read-and-run only; it never plans, edits, fixes, or delegates.

<!-- description: security-reviewer -->
Read-only security analysis before approval - authentication/authorization, secrets, crypto, validation, hardening, dependency vulnerability evidence, and threat review. Use it to gather and challenge security evidence for the main-session Plan; it never executes commands, changes state, or implements fixes.

<!-- description: security-executor -->
Security-sensitive implementation after approval - authentication/authorization, secrets handling, crypto usage, input validation, hardening, and dependency remediation. Give it only an approved, stable execution contract; pre-approval analysis belongs to security-reviewer.

<!-- description: watcher -->
Background watcher for long-running commands - test suites, builds, CI runs, measurements. It runs the assigned command or follows the CI run until it reaches a terminal state, never edits files, and returns the exact command, exit status, and the output lines that decide success or failure, ending with status and suggested_next. Dispatch it with run_in_background so the main session never starts a background shell itself.

<!-- description: researcher -->
Read-only external research - papers, upstream projects, vendor documentation, and prior art. It treats fetched content as data, separates what a source states from inference and from what is unverified, and attaches a source to every claim. The brief assigns one arm, experiment (direct analysis) or control (counter-evidence and methodological flaws); use two independent calls when the conclusion will drive a design or decision. Ends with status and suggested_next.

<!-- description: Explore -->
Read-only search agent for broad fan-out searches - when answering means sweeping many files, directories, or naming conventions and you only need the conclusion, not the file dumps. It reads excerpts rather than whole files, so it locates code; it doesn't review or audit it. Specify search breadth - "medium" for moderate exploration, "very thorough" for multiple locations and naming conventions.
