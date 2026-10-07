#!/usr/bin/env python3
"""shoal-grok 的 SubagentStop 輸出格式 gate（shoal docs/specs/grok-workflow R10、R11）。

只檢查 subagent 最後回覆的格式，不判斷內容對錯；格式不合時以
{"decision": "block", "reason": ...} 退回，讓 subagent 重送。
role 由環境變數 SHOAL_ROLE 決定（hook 設定的 env 欄位），也可用第一個參數覆寫。
stopHookActive 為 true、輸入無法解析、role 未知時一律放行（fail-open，exit 0）。
只用標準函式庫。格式規則取自 hosts/grok/dist/agents/{verifier,plan-verifier,
security-reviewer}.md，tests/test_grok_hooks.py 會確認這些 token 仍出現在 agent 文字。
"""
from __future__ import annotations

import json
import os
import re
import sys

VERIFIER_TOKENS = ("CONFIRMED", "REFUTED", "INCONCLUSIVE", "CONTINUE", "PIVOT", "ROLLBACK")
VERIFIER_RE = re.compile(r"\b(?:" + "|".join(VERIFIER_TOKENS) + r")\b")

REVISE_FIELDS = ("Blocker", "Evidence", "Minimum revision", "Acceptance check")
# 行首可有清單符號、編號、粗體或引用標記；欄位名稱不分大小寫。
_LEAD = r"^[ \t>#*_`\-]*(?:\d+[.)][ \t]*)?[*_`]*"
FIELD_RE = re.compile(_LEAD + r"(" + "|".join(REVISE_FIELDS) + r")[*_`]*[ \t]*:", re.IGNORECASE | re.MULTILINE)
REVISE_RE = re.compile(r"\bREVISE\b")

NO_FINDING_RE = re.compile(
    r"\b(?:no|zero)\s+(?:(?:confirmed|new|security|material|reportable|blocking|significant|open)\s+)*findings?\b"
    r"|\bfindings?\s*[:：-]\s*(?:none|n/a|nil)\b"
    r"|\bno\s+(?:security\s+)?issues?\s+(?:found|identified)\b"
    r"|沒有\s*finding|無\s*finding",
    re.IGNORECASE)
FINDING_HEAD_RE = re.compile(_LEAD + r"(?:finding|issue)[ \t_-]*#?[A-Za-z]{0,2}-?\d+", re.IGNORECASE)
SEVERITY_LINE_RE = re.compile(_LEAD + r"severity\b", re.IGNORECASE)
SEVERITY_RE = re.compile(
    r"severity[^\n]{0,40}?\b(?:p[0-4]|critical|high|medium|moderate|low|info|informational|advisory)\b",
    re.IGNORECASE)
FILE_LINE_RE = re.compile(r"[\w./\\@+-]+\.[A-Za-z0-9]+:\d+")
EVIDENCE_GAP_RE = re.compile(r"evidence\s+gap", re.IGNORECASE)

SHAPES = {
    "verifier": "State exactly one verdict (CONFIRMED, REFUTED or INCONCLUSIVE), or for a direction_checkpoint "
                "one of CONTINUE, PIVOT, ROLLBACK.",
    "plan-verifier": "Reply with a bare READY line, or REVISE followed by one or more blocks, each with "
                     "'Blocker:', 'Evidence:', 'Minimum revision:' and 'Acceptance check:'.",
    "security-reviewer": "For each finding give a severity and file:line evidence or an explicit evidence gap; "
                         "if there are none, say there are no findings.",
}


def check_verifier(text: str) -> list[str]:
    if VERIFIER_RE.search(text):
        return []
    return ["no verdict token found (CONFIRMED, REFUTED, INCONCLUSIVE, CONTINUE, PIVOT, ROLLBACK)"]


def _has_ready_line(text: str) -> bool:
    return any(line.strip().strip("`*_ \t") == "READY" for line in text.splitlines())


def check_plan_verifier(text: str) -> list[str]:
    if not REVISE_RE.search(text):
        if _has_ready_line(text):
            return []
        return ["neither a bare READY line nor a REVISE block found"]
    matches = list(FIELD_RE.finditer(text))
    starts = [i for i, m in enumerate(matches) if m.group(1).lower() == "blocker"]
    if not starts:
        return ["REVISE has no 'Blocker:' block"]
    problems = []
    for n, first in enumerate(starts, 1):
        last = starts[n] if n < len(starts) else len(matches)
        seen = {m.group(1).lower() for m in matches[first:last]}
        missing = [f for f in REVISE_FIELDS if f.lower() not in seen]
        if missing:
            problems.append(f"REVISE block {n} is missing: {', '.join(missing)}")
    return problems


def _split_findings(text: str) -> list[str]:
    segments: list[list[str]] = []
    for line in text.splitlines():
        if FINDING_HEAD_RE.match(line) or (
                SEVERITY_LINE_RE.match(line) and (not segments or SEVERITY_RE.search("\n".join(segments[-1])))):
            segments.append([line])
        elif segments:
            segments[-1].append(line)
    return ["\n".join(s) for s in segments]


def check_security_reviewer(text: str) -> list[str]:
    findings = _split_findings(text)
    if not findings:
        if NO_FINDING_RE.search(text):
            return []
        return ["no finding with a severity found, and no explicit statement of no findings"]
    problems = []
    for n, body in enumerate(findings, 1):
        if not SEVERITY_RE.search(body):
            problems.append(f"finding {n} has no severity")
        if not (FILE_LINE_RE.search(body) or EVIDENCE_GAP_RE.search(body)):
            problems.append(f"finding {n} has neither file:line evidence nor an explicit evidence gap")
    return problems


CHECKERS = {
    "verifier": check_verifier,
    "plan-verifier": check_plan_verifier,
    "security-reviewer": check_security_reviewer,
}


def decide(role: str, payload: object) -> dict | None:
    """回傳要輸出的 block decision；None 表示放行。"""
    if not isinstance(payload, dict) or payload.get("stopHookActive") is True:
        return None
    checker = CHECKERS.get(role)
    message = payload.get("lastAssistantMessage")
    if checker is None or not isinstance(message, str):
        return None
    problems = checker(message)
    if not problems:
        return None
    reason = (f"shoal-grok format gate ({role}): " + "; ".join(problems) + ". " + SHAPES[role]
              + " Resend your final reply in that format; do not redo the work.")
    return {"decision": "block", "reason": reason}


def main(argv: list[str]) -> int:
    try:
        role = argv[1] if len(argv) > 1 else os.environ.get("SHOAL_ROLE", "")
        result = decide(role, json.loads(sys.stdin.buffer.read()))
        if result is not None:
            sys.stdout.write(json.dumps(result))
    except Exception:  # fail-open：任何錯誤都不擋下 subagent
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
