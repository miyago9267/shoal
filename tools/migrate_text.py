#!/usr/bin/env python3
"""一次性：把 TOML 內的 prompt 文字搬成 prompts/*.md，並逐條斷言新 loader 讀回的結果與舊 TOML 相同。

用法：python3 tools/migrate_text.py [--root DIR]
讀 core/contracts、core/policy 的文件 TOML、hosts/*/addenda、policy-addenda、relay/policy-addenda 與
hosts/<host>/binding.toml 的 description，寫入 prompts/ 對應位置，再用 tools/contracts.py 的 Markdown loader 讀回，
比對 (id, kind, sep, required, at, join, text) 與 description 全部相等。binding.toml 的 description 欄位同時被移除，
並斷言移除後的 TOML 與原來只差 description。不刪舊 TOML 檔（git rm 另做）。同一個 PR 的最後一個 commit 移除本檔。
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts  # noqa: E402

NEWLINE = "\n"


def clause_md(clause: contracts.Clause) -> str:
    attrs = [f"kind={clause.kind}"]
    if clause.sep != "paragraph":
        attrs.append(f"sep={clause.sep}")
    if clause.required:
        attrs.append("required")
    return f"<!-- clause: {clause.id} {' '.join(attrs)} -->\n{clause.text}\n"


def addendum_md(add: contracts.Addendum) -> str:
    attrs = [f"at={add.at}"]
    if add.sep is not None:
        attrs.append(f"sep={add.sep}")
    if add.join is not None:
        attrs.append(f"join={add.join}")
    return f"<!-- addendum: {add.id} {' '.join(attrs)} -->\n{add.text}\n"


def block_md(tag: str, key: str, text: str) -> str:
    return f"<!-- {tag}: {key} -->\n{text}\n"


def write(path: Path, blocks: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(NEWLINE.join(blocks).encode("utf-8"))


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def convert_clauses(src: Path, dest: Path, *, policy: bool) -> int:
    kinds = contracts.POLICY_KINDS if policy else contracts.KINDS
    old = contracts.parse_contract(
        load_toml(src), src.name, kinds=kinds, allow_required=policy
    )
    write(dest, [clause_md(c) for c in old])
    new = contracts.parse_markdown_contract(
        dest.read_bytes().decode("utf-8"), dest.name, kinds=kinds, allow_required=policy
    )
    assert new == old, f"{src} -> {dest}: 讀回的條款與舊 TOML 不同"
    return len(old)


def convert_addenda(src: Path, dest: Path) -> int:
    old = contracts.parse_addenda(load_toml(src), src.name)
    write(dest, [addendum_md(a) for a in old])
    new = contracts.parse_markdown_addenda(dest.read_bytes().decode("utf-8"), dest.name)
    assert new == old, f"{src} -> {dest}: 讀回的 addendum 與舊 TOML 不同"
    return len(old)


_DESCRIPTION = re.compile(r"^description = ")


def strip_descriptions(text: str) -> str:
    """刪掉 binding.toml 內每個 `description = ...`（單行或 `'''` 多行）；其餘位元組不動。"""
    out: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if _DESCRIPTION.match(line):
            value = line[len("description = ") :]
            if value.startswith("'''") and not (
                len(value) > 3 and value.endswith("'''")
            ):
                i += 1
                while not lines[i].endswith("'''"):
                    i += 1
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def convert_descriptions(binding_path: Path, dest: Path) -> int:
    text = binding_path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    old: dict[str, str] = {}
    for table in ("roles", "extra_roles"):
        for name, spec in data.get(table, {}).items():
            if "description" in spec:
                old[name] = spec["description"]
    if not old:
        return 0
    expected = {k: v.rstrip("\n") if "\n" in v else v for k, v in old.items()}
    write(dest, [block_md("description", k, v) for k, v in expected.items()])
    new = contracts.parse_markdown_blocks(
        dest.read_bytes().decode("utf-8"), dest.name, "description"
    )
    assert new == expected, (
        f"{binding_path} -> {dest}: 讀回的 description 與舊 TOML 不同"
    )
    stripped = strip_descriptions(text)
    after = tomllib.loads(stripped)
    for table in ("roles", "extra_roles"):
        for spec in data.get(table, {}).values():
            spec.pop("description", None)
    assert after == data, f"{binding_path}: 移除 description 後與原 TOML 不同"
    binding_path.write_bytes(stripped.encode("utf-8"))
    return len(old)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    root = parser.parse_args().root
    prompts = root / "prompts"
    total = {"clause": 0, "addendum": 0, "description": 0}
    files = 0

    for path in sorted((root / "core" / "contracts").glob("*.toml")):
        total["clause"] += convert_clauses(
            path, prompts / "roles" / f"{path.stem}.md", policy=False
        )
        files += 1
    for path in sorted((root / "core" / "policy").glob("*.toml")):
        if path.name == "placeholders.toml":
            continue
        total["clause"] += convert_clauses(
            path, prompts / "policy" / f"{path.stem}.md", policy=True
        )
        files += 1
    for host_dir in sorted((root / "hosts").iterdir()):
        dest = prompts / "hosts" / host_dir.name
        for folder, target in (
            ("addenda", "addenda"),
            ("policy-addenda", "policy-addenda"),
            ("relay/policy-addenda", "relay/policy-addenda"),
        ):
            for path in sorted((host_dir / folder).glob("*.toml")):
                total["addendum"] += convert_addenda(
                    path, dest / target / f"{path.stem}.md"
                )
                files += 1
        binding = host_dir / "binding.toml"
        if binding.is_file():
            count = convert_descriptions(binding, dest / "descriptions.md")
            total["description"] += count
            files += 1 if count else 0
    print(
        f"migrate_text: OK {files} files, {total['clause']} clauses, {total['addendum']} addenda, "
        f"{total['description']} descriptions; (id, kind, sep, required, at, join, text) all equal"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
