# Role contract

Shoal roles are native Codex roles installed under `<CODEX_HOME>/agents/`.
The root session retains ownership of routing, scope, approval, integration, and
finding disposition.

| Role | Boundary | Must not do |
| --- | --- | --- |
| `scout` | Read-only, bounded reconnaissance | Write files or delegate further |
| `plan-critic` | Pre-approval Plan challenge | Approve user work or edit the Plan |
| `executor` | Bounded implementation with judgment | Expand scope without a gate |
| `applier` | Fully specified mechanical repetition | Resolve product ambiguity |
| `security-reviewer` | Read-only security evidence | Implement the security change |
| `security-executor` | Approved security-sensitive implementation | Self-approve or broaden access |
| `verifier` | Fresh-context falsification | Fix its own findings or replace acceptance |
| `watcher` | Run a long command or follow a CI run to its end and report | Edit files or fix what it observes |
| `researcher` | Read-only external research with a source for every claim | Fill a gap from memory or edit files |

Use exclusive file ownership for writing roles. A user-owned extra role is
preserved; a customized same-name shoal role requires explicit per-role
replacement approval.
