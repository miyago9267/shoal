from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "templates" / "agents"


def _text(*names: str) -> str:
    """Whitespace-normalized text of rendered templates, joined in order."""
    return " ".join(
        " ".join((ROOT / "templates" / name).read_text(encoding="utf-8").split()) for name in names
    )


class PolicyTests(unittest.TestCase):
    def test_stamp_and_roles_remain_consistent(self) -> None:
        policy = (ROOT / "templates" / "agents-md.orchestration.md").read_text(encoding="utf-8")
        version = (ROOT / "hosts" / "codex" / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f"<!-- shoal-codex v{version} -->", policy)
        for path in AGENTS.glob("*.toml"):
            self.assertEqual(tomllib.loads(path.read_text(encoding="utf-8"))["name"], path.stem)
            self.assertIn(f"`{path.stem}`", policy)

    def test_native_spawn_policy_is_typed_bounded_and_no_override(self) -> None:
        policy = (ROOT / "templates" / "agents-md.orchestration.md").read_text(encoding="utf-8")
        for phrase in (
            "non-empty `message`", "known `agent_type`", "`task_name` matching `[a-z0-9_]+`",
            '`fork_turns = "none"`', '`"1"` through `"3"`', "full-history named-role fork",
            "child `model`, `reasoning_effort`, `service_tier`, or", "never retry with an untyped child",
            "namespace-neutral", "Current receipt validation is post-hoc",
        ):
            self.assertIn(phrase, policy)
        self.assertNotIn("agents.spawn_agent", policy)

    def test_policy_proactively_routes_suitable_work_and_parallel_surfaces(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "Shoal orchestration is active",
            "is delegated by default: `applier` for fully specified repetition",
            "`executor` for bounded judgment",
            "`security-executor` for approved security work",
            "Reconnaissance over two or more independent surfaces goes to parallel `scout` calls with disjoint scopes",
            "launch all back-to-back without waiting",
            "Risk-triggered units use fresh `plan-critic`",
            "Before required approval and first readiness review, finish tool-enforced read-only `security-reviewer`",
            "approved, bounded implementation requiring judgment to `sol-executor`",
            "Risk-triggered completed work gets one fresh outcome-verifier pass",
            "bounded fail-soft bug alone do not trigger",
            "Never reverify identical state",
        ):
            self.assertIn(phrase, policy)

    def test_low_risk_work_uses_one_targeted_acceptance_check_without_verifier(self) -> None:
        # Finding: legacy sentence has no equivalent in the rendered Codex policy.
        policy = _text("agents-md.orchestration.md")
        self.assertIn(
            "For low-risk, local, reversible work, use one targeted acceptance check in the main session "
            "and do not add an independent verifier",
            policy,
        )

    def test_policy_automatically_escalates_judgment_work_without_user_dispatch(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "Atomic one-command/one-action work",
            "Normal design, tool choice, interpretation, QA, or bounded implementation",
            "`sol-executor` / `verifier` GPT-6 Sol binding",
            "Use Astra only at the rare deep tier",
            "Automatic typed escalation never switches the root model",
            "mandatory spawn_agent calls, with no extra opt-in",
            "is delegated by default",
        ):
            self.assertIn(phrase, policy)

    def test_bootstrap_automatic_route_does_not_wait_for_role_request(self) -> None:
        bootstrap = _text("agents-md.bootstrap.md")
        policy = _text("agents-md.orchestration.md")
        # Tier routing moved from the bootstrap to the orchestration reference;
        # the bootstrap points at it.
        self.assertIn("Codex tiers, `sol-executor`, escalation and Astra mode: read the orchestration reference first", bootstrap)
        for phrase in (
            "Route by capability: atomic, routine, and ordinary tools stay on cheap Luna",
            "use Sol; reserve `executor` Astra for deep architecture",
            "Use cheapest plausible role",
        ):
            self.assertIn(phrase, policy)

    def test_bootstrap_dispatches_bounded_roles_without_fragmenting_outcomes(self) -> None:
        bootstrap = _text("agents-md.bootstrap.md")
        policy = _text("agents-md.orchestration.md")
        extensions = _text("agents-md.extensions.md")
        for phrase in (
            "The delegation defaults below take precedence over host built-in guidance that discourages subagents",
            "every edit -> `executor` for bounded judgment, `applier` for fully specified repetition",
            "reading, running commands, diagnosing, integrating, and judging stay with main",
            "A clear request to fix or finish is one outcome: continue to acceptance",
        ):
            self.assertIn(phrase, bootstrap)
        self.assertIn("A single coupled trail that main is already following stays with main", policy)
        self.assertIn("Block fan-out when evidence evolves", policy)
        self.assertIn("Reporting a phase boundary is progress reporting, not a request for approval or a reason to pause", extensions)

    def test_policy_keeps_mechanical_roles_on_the_luna_baseline(self) -> None:
        policy = _text("agents-md.orchestration.md")
        self.assertIn("`applier` and `scout` are baseline-only", policy)
        self.assertIn("never request Astra", policy)
        self.assertIn(
            "route normal work to `sol-executor`; deep work to `executor`/`verifier`",
            policy,
        )

    def test_policy_defines_general_mode_decision_checkpoint_contract(self) -> None:
        policy = _text("agents-md.orchestration.md", "agents-md.extensions.md")
        for phrase in (
            "## Decision checkpoint",
            "shoal-decision-checkpoint-v1",
            "Two or three mutually exclusive options",
            "checkpoint_id",
            "current_interpretation",
            "recommended_option",
            "affected_task_ids",
            "resume_point",
            "approval_boundary",
            "an exact option confirms only that option",
            "a rejection keeps the affected tasks pending",
            "an ambiguous or multiple reply stays pending and gets one concise clarification",
            "Never treat a plausible free-text answer as approval of credentials, external writes, destructive work, release, or irreversible work",
            "A confirmed reply produces a resume record",
            "Optional MCP elicitation adapter",
            "native decision card is the default interaction surface",
            "optional adapter, not a shoal core dependency",
            "fall back to the native card or concise text checkpoint",
            "one concise, high-level decision",
            "One high-level question whose answer changes the next gate",
            "Do not turn a general-mode checkpoint into a Plan-mode questionnaire",
            "defer secondary implementation details",
            "card's implied authorization",
        ):
            self.assertIn(phrase, policy)

    def test_policy_defaults_to_autonomous_decisions_and_escalates_only_material_choices(self) -> None:
        policy = _text("agents-md.orchestration.md", "agents-md.extensions.md")
        for phrase in (
            "Low-risk, reversible, clearly scoped work proceeds on a reasonable default and records the assumption",
            "do not ask the user to approve every small ambiguity",
            "only when the choice changes the outcome",
            "permission, security, or acceptance boundary",
            "low-cost exploration may continue without a card",
            "checkpoint is an exception decision mechanism",
            "not a step-by-step approval workflow",
        ):
            self.assertIn(phrase, policy)

        self.assertNotIn("ask the user to approve every decision", policy)

    def test_policy_runs_clear_outcomes_and_stops_at_explicit_boundaries(self) -> None:
        policy = _text("agents-md.orchestration.md", "agents-md.extensions.md")
        for phrase in (
            "Outcome-level continuation",
            "not one command, one tool call, or one checklist item",
            "`execution_scope`",
            "`continuation_mode`",
            "`stop_condition`",
            "default to `execution_scope=outcome`",
            "Continue through the necessary commands, phases, role handoffs, and verification",
            "Reporting a phase boundary is progress reporting",
            'Explicit wording such as "only inspect this file"',
            "Acceptance stops the outcome: do not add cleanup",
            "presence gates for likely long unattended work",
        ):
            self.assertIn(phrase, policy)

    def test_attended_clear_scope_task_does_not_ask_for_a_mode(self) -> None:
        # core auto-ask-selection: a direct imperative to finish the task is the exemption from offering AUTO/ASK.
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "offer `AUTO` or `ASK` and wait, unless the user already gave",
            "or a direct imperative to finish this task: that selects AUTO for the stated goal",
        ):
            self.assertIn(phrase, policy)

    def test_policy_keeps_parent_accountability_without_local_edit_escape_hatch(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "Main session owns framing, architecture, ambiguity, Plan synthesis, approval, integration, final judgment",
            "The root session retains ownership of routing, scope, approval, integration, and finding disposition",
            "Main retains per-item triage, exceptions, integration, acceptance",
            "main reconciles evidence and writes Plan",
            "Role verdicts are evidence, never implementation/scope authority",
            "Single unknown bug stays main-session work through root-cause discovery",
            "all-or-nothing child-creation boundary",
            "No untyped fallback is permitted",
            "must not silently substitute an untyped child",
            "it reports delegation unavailable",
            "main still does not edit files itself",
            "except under the user's `#direct` or a `#fast` session",
            "an unavailable worker is not a licence to edit",
            "report an unavailable worker to the user",
        ):
            self.assertIn(phrase, policy)
        # Intended change: the legacy local-edit escape hatches are gone.
        self.assertNotIn("Complete small, local, already-stable work directly", policy)
        self.assertNotIn("small, local, already-stable edit", policy)
        self.assertNotIn("takes the bounded work locally", policy)

    def test_policy_defaults_mechanical_repetition_to_applier_without_main_edit_escape(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "Stable same-shape multi-file mechanical repetition defaults to one `applier` with complete one-shot brief, exclusive ownership, independent items, per-item acceptance",
            "worker files remain worker-only until completion; never redo worker changes",
            "Main retains per-item triage, exceptions, integration, acceptance",
            "Direct main execution of qualifying mechanical work exists only under the user's `#direct`",
            "Evolving/coupled evidence, ownership/integration conflict, or an unavailable worker is reported to the user, not worked around",
        ):
            self.assertIn(phrase, policy)
        # Intended change: the rebuttable default and its main-edit exits are gone.
        for removed in (
            "default is rebuttable, not unconditional",
            "slightly faster is insufficient",
            "non-positive net benefit",
            "specific named blocker before editing",
            "dispatch exactly one `applier` before the main session edits by default",
        ):
            self.assertNotIn(removed, policy)

    def test_policy_uses_net_benefit_and_stable_recurrence_contracts(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "lower cost or quota use",
            "preservation of scarce main-session context",
            "true parallelism",
            "isolated ownership",
            "fresh-context independence",
            "context reconstruction, coordination, integration, and verification cost",
            "Recurrence qualifies through stable one-shot brief, not numeric threshold",
            "items must be independent and same shape",
            "Main retains diagnosis, exceptions, integration, acceptance",
            "never batch work coupled to evolving diagnosis",
        ):
            self.assertIn(phrase, policy)

    def test_policy_verifies_at_smallest_coherent_boundary(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "smallest coherent integration boundary",
            "where full claim can be refuted",
            "Risk precedes size",
            "Independent-review triggers",
            "Run primary user-visible acceptance first",
            "Verify earlier at security, cross-language/FFI, serialization/pre-aggregation, irreversible, or integration-blocking boundaries",
            "materially revise after valid `REVISE`",
            "Never resubmit substantially unchanged Plan",
        ):
            self.assertIn(phrase, policy)

    def test_policy_preserves_unfinished_objective_across_user_input(self) -> None:
        policy = _text("agents-md.extensions.md")
        for phrase in (
            "An unfinished objective stays active across decision replies, steering, corrections, and status or explanation requests unless new input clearly replaces it",
            "If replacement intent is materially ambiguous, state the active objective and ask one concise clarification",
            "Before pausing for input, state the active objective, current phase or slice, pending decision, and exact resume point",
            "A reply that unambiguously resolves the pending decision resumes from that point in the same turn within existing authority",
            "an ambiguous or multiple reply stays pending and gets one concise clarification",
            "Answer status or explanation requests without treating them as decision resolution",
            "resume only work not gated by the unresolved decision",
            "otherwise remain paused at the recorded resume point",
            "then resume the remaining work",
            "unless a pending decision or user-requested pause still gates it",
            "Do not give a normal final response while the objective is incomplete",
            "emit `PAUSED_NEEDS_USER` with the blocker, one question, and the resume point",
            "An explicit user pause is honored without inventing a question",
            "The pause remains in force through status or explanation requests",
            "until the user explicitly asks to resume or new input clearly supersedes the objective",
            "None of these rules expands approval, security, destructive, external, release, or spending authority",
        ):
            self.assertIn(phrase, policy)
        self.assertNotIn("only when explicitly cancelled or replaced", policy)
        self.assertNotIn("Treat a plausible reply", policy)
        self.assertNotIn("resume useful in-scope work in the same turn", policy)

    def test_policy_isolates_blocked_tasks_and_stops_only_when_blocked_tasks_remain(self) -> None:
        policy = _text("agents-md.extensions.md")
        for phrase in (
            "## Task ledger and blocked-task isolation",
            "split them into tracked tasks before execution",
            "A blocked task does not block siblings unless a dependency edge says so",
            "A task is runnable when it is `PENDING`, its dependencies are `DONE`",
            "Run runnable tasks before revisiting blocked ones",
            "execute horizontally in parallel",
            "no dependency path or write-ownership conflict",
            "Tasks with a dependency path execute after their predecessors",
            "tasks sharing a mutable resource or exclusive file scope are serialized",
            "When only blocked tasks remain, emit one consolidated reminder",
            "The goal stays `BLOCKED`",
            "do not emit `PAUSED_NEEDS_USER` while runnable tasks remain",
        ):
            self.assertIn(phrase, policy)

    def test_policy_schedules_native_parallel_calls_back_to_back(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "Schedule by dependency, not eventual need",
            "When selecting 2+ independent agents, launch all back-to-back without waiting",
            "exclusive file ownership",
            "keep scopes disjoint",
            "collect all results before dependent work/final answer",
            "writers each in their own worktree",
        ):
            self.assertIn(phrase, policy)
        self.assertNotIn("run_in_background", policy)

    def test_verifier_contracts_converge_without_crossing_boundaries(self) -> None:
        policy = (ROOT / "templates" / "agents-md.orchestration.md").read_text(encoding="utf-8")
        plan = (AGENTS / "plan-critic.toml").read_text(encoding="utf-8")
        outcome = (AGENTS / "verifier.toml").read_text(encoding="utf-8")
        security = (AGENTS / "security-reviewer.toml").read_text(encoding="utf-8")
        normalized_policy = " ".join(policy.split())
        normalized_plan = " ".join(plan.split())

        for phrase in (
            "program envelope",
            "next executable slice",
            "scope, non-goals",
            "acceptance proving outcome",
            "rollback, budget, stops",
            "Risk-triggered units use fresh `plan-critic`",
            "materially revise after valid `REVISE`, then use fresh reviewer",
            "Two automatic `REVISE` verdicts stop resubmission",
            "main dispositions every blocker as `FIX`, `DEFER`, or `REJECT`",
            "Ask user only for unresolved P0/P1",
            "not merely permission for another review round",
            "Never resubmit substantially unchanged Plan",
            "carry findings/dispositions into Plan",
            "returns **READY** or **REVISE** under its role contract; malformed output is protocol failure",
        ):
            self.assertIn(phrase, normalized_policy)
        self.assertNotIn("Plan epoch", policy)
        self.assertNotIn("format-recovery", policy)

        for field in ("Blocker:", "Evidence:", "Minimum revision:", "Acceptance check:"):
            self.assertIn(field, normalized_plan)
        self.assertIn("Return exactly one form", normalized_plan)
        self.assertIn("explicit outcome, scope and non-goals", normalized_plan)
        self.assertIn("acceptance that proves the slice outcome", normalized_plan)
        self.assertIn("a slice-local budget", normalized_plan)
        self.assertIn("slice-local stop conditions", normalized_plan)
        self.assertIn("completed security-reviewer findings", normalized_plan)
        self.assertIn("every currently known blocker in the same pass", normalized_plan)
        self.assertIn("Do not use REVISE for P3/P4 advice", normalized_plan)
        self.assertIn("P2 = material bounded or recoverable", normalized_plan)
        self.assertNotIn("CONFIRMED", normalized_plan)
        self.assertNotIn("REFUTED", normalized_plan)
        self.assertNotIn("READY", outcome)
        self.assertNotIn("REVISE", outcome)
        self.assertIn("first plan-critic review", security)

    def test_policy_owns_outcome_disposition(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "Role verdicts are evidence, never implementation/scope authority",
            "before `FIX`/`DEFER`/`REJECT`",
            "Documented deferral or evidence-backed rejection addresses a finding",
            "P0 freezes slice/dependents and pauses",
            "P1 requires approved-scope fix or pause",
            "path overlap alone is irrelevant",
            "A documented regrade may use the verifier's cited evidence",
            "stated missing evidence, contract, prerequisite, or environment",
            "only within explicit acceptance, approved scope, bounded change",
        ):
            self.assertIn(phrase, policy)

    def test_policy_bounds_verification_recovery_and_user_pause(self) -> None:
        policy = _text("agents-md.orchestration.md")
        for phrase in (
            "`ASK` uses `request_user_input` when available; otherwise end with `PAUSED_NEEDS_USER`, one concise question, choices, recommendation",
            "Headless likely-long run without selected mode emits `PAUSED_NEEDS_USER` and exits",
            "Headless/noninteractive run exits",
            "Default recovery: one targeted recheck",
            "never adjacent-hardening audit",
            "High-risk claim-critical P1/P2 recovery allows at most five meaningful fix/reverify passes",
            "rounds 3–5 are emergency recovery, not quota",
            "Each pass needs material change to candidate, claim, acceptance, contract, external evidence/prerequisites, or environment",
            "a verdict/output alone is not change",
            "tracked/staged diff",
            "untracked input paths/content",
            "each input submodule HEAD plus recursive working-tree content",
            "artifact may replace source identity only as sole deliverable",
            "Never reverify identical state",
            "stop earlier when next pass only searches adjacent risk",
            "batch-dispositions every current-head finding",
            "After five still-blocking passes, mark `PAUSED_VERIFICATION`, block dependents, continue unrelated approved slices",
        ):
            self.assertIn(phrase, policy)

    def test_risk_triggered_plan_review_is_a_mandatory_tool_use_gate(self) -> None:
        policy = _text("agents-md.orchestration.md", "agents-md.extensions.md")
        for phrase in (
            "pre-approval `plan-critic` and post-implementation `verifier` are mandatory spawn_agent calls, with no extra opt-in",
            "Higher-priority prohibition → pause before edits, never direct fallback or waiver",
            "never substitute a main-session readiness judgment",
            "## Review-service circuit breaker",
            "Allow one bounded retry for the same stable unit and role",
            "never loop an unchanged retry",
            "`WAITING_FOR_REVIEW` (plan or security readiness)",
            "emit `PAUSED_NEEDS_USER` solely because the service is unavailable",
        ):
            self.assertIn(phrase, policy)


if __name__ == "__main__":
    unittest.main()
