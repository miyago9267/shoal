"""role 條款（core/contracts）、host 外框（frames）與 host 補充（addenda）的格式、載入與組合。

純函式加上讀檔的 loader，不依賴 render.py。條款與 addendum 的 text 都是逐字文字：
條款之間的分隔由前一個條款的 sep 決定，最後一個條款之後固定補一個換行。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# sep 是「這一段之後」接什麼：paragraph = 空行，space = 同一行接續，newline = 換行（例如條列）。
SEPARATORS = {"paragraph": "\n\n", "space": " ", "newline": "\n"}
# 條款 kind 的封閉詞彙；新增 kind 要同時改這裡與 core/README.md。
KINDS = frozenset(
    {
        "identity",
        "scope",
        "boundary",
        "procedure",
        "escalation",
        "verdict",
        "severity",
        "security",
        "foreground",
        "final-message",
        "leaf",
    }
)
FRAME_PLACEHOLDER = "{{role_body}}"
_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_ANCHOR = re.compile(r"^(?:(start|end)|(after|before|replace):(.+))$")


class ContractError(Exception):
    """條款、外框或 addendum 不合法（render 轉成 exit 2）。"""


@dataclass(frozen=True)
class Clause:
    id: str
    kind: str
    text: str
    sep: str = "paragraph"


@dataclass(frozen=True)
class Addendum:
    id: str
    at: str  # start / end / after:<id> / before:<id> / replace:<id>
    text: str
    sep: str | None = None  # None：replace 沿用被取代條款的 sep，其他位置用 paragraph
    # 前一段與這個 addendum 之間的分隔；None 沿用前一段原本的 sep。
    # 用於把 host 專屬的句子接在 core 段落結尾的同一行（core 本身在那裡是換段）。
    join: str | None = None


def _load(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"無法讀取 {path}: {exc}") from exc


def _check_table(
    where: str, table: object, required: set[str], optional: set[str]
) -> dict:
    if not isinstance(table, dict):
        raise ContractError(f"{where}: 必須是 table")
    missing = sorted(required - set(table))
    if missing:
        raise ContractError(f"{where}: 缺少欄位 {', '.join(missing)}")
    unknown = sorted(set(table) - required - optional)
    if unknown:
        raise ContractError(f"{where}: 未知欄位 {', '.join(unknown)}")
    return table


def _check_id(where: str, value: object) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise ContractError(f"{where}: id 必須是小寫英數加連字號（例如 no-delegate）")
    return value


def _check_text(where: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{where}: text 必須是非空字串")
    if value != value.strip() or "\r" in value:
        raise ContractError(
            f"{where}: text 頭尾不可有空白或換行（條款之間的分隔用 sep），也不可含 CR"
        )
    return value


def _check_sep(where: str, value: object) -> str:
    if value not in SEPARATORS:
        raise ContractError(f"{where}: sep 必須是 {sorted(SEPARATORS)}")
    return value


def parse_contract(data: dict, label: str = "contract") -> list[Clause]:
    unknown = sorted(set(data) - {"clause"})
    if unknown:
        raise ContractError(f"{label}: 未知的頂層 key {', '.join(unknown)}")
    raw = data.get("clause")
    if not isinstance(raw, list) or not raw:
        raise ContractError(f"{label}: 至少要有一個 [[clause]]")
    clauses: list[Clause] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, 1):
        table = _check_table(
            f"{label} 第 {index} 個 clause", item, {"id", "kind", "text"}, {"sep"}
        )
        cid = _check_id(f"{label} 第 {index} 個 clause", table["id"])
        where = f"{label} clause {cid}"
        if cid in seen:
            raise ContractError(f"{where}: id 重複")
        seen.add(cid)
        if table["kind"] not in KINDS:
            raise ContractError(f"{where}: kind 必須是 {sorted(KINDS)}")
        clauses.append(
            Clause(
                cid,
                table["kind"],
                _check_text(where, table["text"]),
                _check_sep(where, table.get("sep", "paragraph")),
            )
        )
    return clauses


def parse_addenda(data: dict, label: str = "addenda") -> list[Addendum]:
    unknown = sorted(set(data) - {"addendum"})
    if unknown:
        raise ContractError(f"{label}: 未知的頂層 key {', '.join(unknown)}")
    raw = data.get("addendum", [])
    if not isinstance(raw, list):
        raise ContractError(f"{label}: addendum 必須是 [[addendum]]")
    out: list[Addendum] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, 1):
        table = _check_table(
            f"{label} 第 {index} 個 addendum", item, {"id", "at", "text"}, {"sep", "join"}
        )
        aid = _check_id(f"{label} 第 {index} 個 addendum", table["id"])
        where = f"{label} addendum {aid}"
        if aid in seen:
            raise ContractError(f"{where}: id 重複")
        seen.add(aid)
        if not isinstance(table["at"], str) or not _ANCHOR.match(table["at"]):
            raise ContractError(
                f"{where}: at 必須是 start、end、after:<id>、before:<id> 或 replace:<id>"
            )
        sep, join = table.get("sep"), table.get("join")
        out.append(
            Addendum(
                aid,
                table["at"],
                _check_text(where, table["text"]),
                None if sep is None else _check_sep(where, sep),
                None if join is None else _check_sep(where, join),
            )
        )
    return out


def load_contract(path: Path) -> list[Clause]:
    return parse_contract(_load(path), str(path.name))


def load_addenda(path: Path) -> list[Addendum]:
    """檔案不存在代表這個 host 對該 role 沒有補充。"""
    if not path.is_file():
        return []
    return parse_addenda(_load(path), str(path.name))


def load_frame(frames_dir: Path, role: str) -> str | None:
    """frames/<role>.md 優先，其次 frames/default.md；都沒有代表沒有外框。逐位元組讀，不轉換換行。"""
    for name in (f"{role}.md", "default.md"):
        path = frames_dir / name
        if path.is_file():
            try:
                text = path.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise ContractError(f"無法讀取 {path}: {exc}") from exc
            if text.count(FRAME_PLACEHOLDER) != 1:
                raise ContractError(f"{path.name}: 必須恰好有一個 {FRAME_PLACEHOLDER}")
            return text
    return None


def replaced_ids(addenda: list[Addendum]) -> list[str]:
    return [a.at.split(":", 1)[1] for a in addenda if a.at.startswith("replace:")]


def compose(clauses: list[Clause], addenda: list[Addendum]) -> str:
    """依序排列條款與 addenda，回傳以單一換行結尾的 role 文字。

    同一個位置有多個 addendum 時依檔案順序；after 與 before 可以掛在被 replace 的條款上。
    """
    ids = {c.id for c in clauses}
    start: list[Addendum] = []
    end: list[Addendum] = []
    before: dict[str, list[Addendum]] = {}
    after: dict[str, list[Addendum]] = {}
    replace: dict[str, Addendum] = {}
    for add in addenda:
        match = _ANCHOR.match(add.at)
        kind, target = match.group(1) or match.group(2), match.group(3)
        if kind == "start":
            start.append(add)
        elif kind == "end":
            end.append(add)
        else:
            if target not in ids:
                raise ContractError(
                    f"addendum {add.id}: {add.at} 指向不存在的條款 {target}"
                )
            if kind == "replace":
                if target in replace:
                    raise ContractError(
                        f"addendum {add.id}: 條款 {target} 被 replace 兩次"
                    )
                replace[target] = add
            else:
                (before if kind == "before" else after).setdefault(target, []).append(
                    add
                )

    pieces: list[tuple[str, str]] = []

    def put(text: str, sep: str, join: str | None = None) -> None:
        if join is not None:
            if not pieces:
                raise ContractError("join 前面沒有可接的段落（start 位置不可用 join）")
            pieces[-1] = (pieces[-1][0], join)
        pieces.append((text, sep))

    def put_addendum(add: Addendum, default_sep: str = "paragraph") -> None:
        put(add.text, add.sep or default_sep, add.join)

    for add in start:
        put_addendum(add)
    for clause in clauses:
        for add in before.get(clause.id, []):
            put_addendum(add)
        rep = replace.get(clause.id)
        if rep:
            put_addendum(rep, clause.sep)
        else:
            put(clause.text, clause.sep)
        for add in after.get(clause.id, []):
            put_addendum(add)
    for add in end:
        put_addendum(add)

    body = "".join(text + SEPARATORS[sep] for text, sep in pieces[:-1])
    return body + pieces[-1][0] + "\n"


def apply_frame(frame: str | None, body: str) -> str:
    if frame is None:
        return body
    head, tail = frame.split(FRAME_PLACEHOLDER, 1)
    return head + body + tail
