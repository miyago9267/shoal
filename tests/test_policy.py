"""Prompt 政策的結構與協定斷言（text-first P3a）。

prompt 的字句由 prompts/ 單一來源、`render --check` 與 prompt lock（預算與 required_fragments）保證，這裡不再逐句
比對。留下三類：

- 結構：marker 等於 VERSION、每個安裝的 role 都列在政策裡。
- 協定符號：hooks、guard、bench 或別的 host 會解析的 token（狀態名、欄位名、標籤）必須留在輸出裡。
- 行為契約：lock 沒涵蓋、但改掉會改變派工或核准行為的句子，每個契約一句。
"""

from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "templates" / "agents"
CLAUDE_REFS = (
    ROOT / "plugins" / "claude" / "skills" / "shoal-orchestration" / "references"
)


CLAUDE_BOOTSTRAP = ROOT / "plugins" / "claude" / "policy" / "claude-md.bootstrap.md"


def flat(*paths: Path) -> str:
    """多個檔案去掉換行與縮排差異後串接。"""
    return " ".join(" ".join(p.read_text(encoding="utf-8").split()) for p in paths)


def codex(*names: str) -> str:
    return flat(*(ROOT / "templates" / name for name in names))


def claude(*names: str) -> str:
    return flat(*(CLAUDE_REFS / name for name in names))


class StructureTests(unittest.TestCase):
    def test_stamp_and_roles_remain_consistent(self) -> None:
        policy = (ROOT / "templates" / "agents-md.orchestration.md").read_text(
            encoding="utf-8"
        )
        version = (
            (ROOT / "hosts" / "codex" / "VERSION").read_text(encoding="utf-8").strip()
        )
        self.assertIn(f"<!-- shoal-codex v{version} -->", policy)
        for path in AGENTS.glob("*.toml"):
            self.assertEqual(
                tomllib.loads(path.read_text(encoding="utf-8"))["name"], path.stem
            )
            self.assertIn(f"`{path.stem}`", policy)


class ProtocolTokenTests(unittest.TestCase):
    """token 的消費者在文字之外：autoroute gate、guard、bench 的解析器，或別的 host。"""

    CODEX_TOKENS = (
        # autoroute gate 與 stop hook 解析的狀態
        "PAUSED_NEEDS_USER",
        "WAITING_FOR_REVIEW",
        "PAUSED_VERIFICATION",
        # typed spawn 的呼叫形狀
        "spawn_agent",
        "`agent_type`",
        "`task_name`",
        "`[a-z0-9_]+`",
        '`fork_turns = "none"`',
        # intent 分類與 discovery
        "`execute`",
        "`explore_then_plan`",
        "`co_discover`",
        "`change_impact`",
        "`discovery_budget`",
        "`budget_exhausted`",
        "`evidence_sufficient`",
        # 結果層級的續跑與方向檢查
        "`execution_scope`",
        "`continuation_mode`",
        "`stop_condition`",
        "`direction_checkpoint`",
        "`CONTINUE`",
        "`PIVOT`",
        "`ROLLBACK`",
        # decision checkpoint 的 schema
        "shoal-decision-checkpoint-v1",
        "checkpoint_id",
        "current_interpretation",
        "recommended_option",
        "affected_task_ids",
        "resume_point",
        "approval_boundary",
        # finding 處置
        "`FIX`",
        "`DEFER`",
        "`REJECT`",
    )
    CLAUDE_TOKENS = (
        # guard 以標籤判斷 lane（hooks/shoal_guard.py）
        "`[fast]`",
        "`[complex]`",
        "`[rigorous]`",
        # watcher 與 researcher 的呼叫形狀
        "`run_in_background: true`",
        "`arm: experiment`",
        "`arm: control`",
        "`mode: gaps`",
        "`status: failed`",
        "`status: insufficient`",
    )

    def test_codex_policy_keeps_its_protocol_tokens(self) -> None:
        policy = codex(
            "agents-md.bootstrap.md",
            "agents-md.orchestration.md",
            "agents-md.extensions.md",
        )
        for token in self.CODEX_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, policy)

    def test_claude_policy_keeps_its_protocol_tokens(self) -> None:
        policy = claude("orchestration-policy.md", "workflow-extensions.md")
        for token in self.CLAUDE_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, policy)

    def test_codex_policy_uses_native_transport_vocabulary(self) -> None:
        policy = codex(
            "agents-md.bootstrap.md",
            "agents-md.orchestration.md",
            "agents-md.extensions.md",
        )
        for legacy in ("agents.spawn_agent", "run_in_background"):
            with self.subTest(token=legacy):
                self.assertNotIn(legacy, policy)


class BehaviourContractTests(unittest.TestCase):
    """每個契約一句：lock 的 required_fragments 沒涵蓋，但改掉就改變派工或核准行為。"""

    CODEX = (
        "never retry with an untyped child",
        "No untyped fallback is permitted",
        "it reports delegation unavailable",
        "main still does not edit files itself",
        "Direct main execution of mechanical work needs `#direct`",
        "Never treat a plausible free-text answer as approval of credentials, external writes, destructive work, release, or irreversible work",
        "Two automatic `REVISE` verdicts stop resubmission",
        "Never reverify identical state",
        "never substitute a main-session readiness judgment",
        "pre-approval `plan-critic` and post-implementation `verifier` are mandatory spawn_agent calls",
        "A blocked task does not block siblings unless a dependency edge says so",
        "For low-risk, local, reversible work, use one targeted acceptance check in the main session and do not add an independent verifier",
    )
    CLAUDE = (
        "main still does not edit files itself",
        "Direct main execution of mechanical work needs `#direct`",
        "Once root cause and remedy are known, the fix is Execution work and is delegated.",
    )

    def test_codex_contracts(self) -> None:
        policy = codex("agents-md.orchestration.md", "agents-md.extensions.md")
        for sentence in self.CODEX:
            with self.subTest(contract=sentence[:50]):
                self.assertIn(sentence, policy)

    def test_claude_contracts(self) -> None:
        policy = claude("orchestration-policy.md", "workflow-extensions.md")
        for sentence in self.CLAUDE:
            with self.subTest(contract=sentence[:50]):
                self.assertIn(sentence, policy)

    def test_claude_bootstrap_lets_main_edit_simple_work_after_declaring(self) -> None:
        text = flat(CLAUDE_BOOTSTRAP)
        self.assertIn(
            'Simple work (one purpose, known scope, no risk trigger, expected within 10 minutes): '
            'the main session runs `: shoal-direct "<reason>"` as its own shell command, then edits itself.',
            text,
        )
        self.assertIn("All other edits go to a write-capable role unless the user's prompt contains `#direct`", text)
        self.assertNotIn("The main session does not edit files itself", text)

    def test_codex_bootstrap_keeps_the_no_direct_edit_sentence(self) -> None:
        text = codex("agents-md.bootstrap.md")
        self.assertIn("The main session does not edit files itself", text)
        self.assertNotIn("shoal-direct", text)


class RoleBoundaryTests(unittest.TestCase):
    """plan-critic 與 verifier 的 verdict 詞彙互不渗透；兩者的輸出格式各自固定。"""

    @staticmethod
    def role(name: str) -> dict:
        return tomllib.loads((AGENTS / f"{name}.toml").read_text(encoding="utf-8"))

    def test_plan_critic_reports_blocker_fields_and_never_outcome_verdicts(
        self,
    ) -> None:
        plan = " ".join(self.role("plan-critic")["developer_instructions"].split())
        for field in (
            "Blocker:",
            "Evidence:",
            "Minimum revision:",
            "Acceptance check:",
        ):
            self.assertIn(field, plan)
        for verdict in ("CONFIRMED", "REFUTED"):
            self.assertNotIn(verdict, plan)

    def test_verifier_reports_outcome_verdicts_and_never_plan_verdicts(self) -> None:
        verifier = self.role("verifier")
        outcome = " ".join(verifier["developer_instructions"].split())
        for verdict in ("CONFIRMED", "REFUTED", "INCONCLUSIVE"):
            self.assertIn(verdict, verifier["description"])
        for verdict in ("READY", "REVISE"):
            self.assertNotIn(verdict, outcome)

    def test_verifier_supports_the_direction_checkpoint_tokens(self) -> None:
        verifier = self.role("verifier")
        text = f"{verifier['description']} {' '.join(verifier['developer_instructions'].split())}"
        for token in (
            "direction-checkpoint",
            "`direction_checkpoint`",
            "`CONTINUE`",
            "`PIVOT`",
            "`ROLLBACK`",
            "`INCONCLUSIVE`",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_security_reviewer_hands_the_plan_to_plan_critic(self) -> None:
        self.assertIn(
            "plan-critic", self.role("security-reviewer")["developer_instructions"]
        )


if __name__ == "__main__":
    unittest.main()
