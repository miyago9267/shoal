#!/usr/bin/env python3
"""產生 generic-md host 的骨架：hosts/<name>/binding.toml、frames/default.md、addenda/。

用法：python3 tools/new_host.py <name> [--root DIR]

已存在的 host 不會被覆寫（exit 2）。骨架的 [models] 還是註解，填好之前
`python3 tools/render.py --host <name> --check` 會 exit 2；後續步驟見 docs/new-host.md。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402

TEMPLATE = '''\
# {name} host binding：由 tools/new_host.py 產生，步驟見 docs/new-host.md。
# 填好 [models]、工具對應表與每個 role 的 description 後：
#   python3 tools/render.py --host {name} --write

renderer = "generic-md"
role_text = "core"

# 這個 host 可用的模型與它們在 {name} 的名稱；key 必須在 core/models.toml。
# resolver 只在這裡選模（規則見 core/tiers.toml）。沒填之前 render 會 exit 2。
# [models]
# "anthropic/haiku" = "haiku"
# "anthropic/sonnet" = "sonnet"
# "anthropic/opus" = "opus"

# 輸出格式：每個 role 一個 Markdown 檔加 YAML frontmatter，dist 在 hosts/{name}/dist/。
# encoding 可選 scalar、comma-list、block-list、folded、nested-map。
# 權限欄位（這裡是 tools）要先用 [output.permissions.<欄位>] 宣告型別
# （list、scalar、map），frontmatter 才能用它當 source。
[output]
path = "agents/{{role}}.md"

[[output.frontmatter]]
key = "name"
source = "name"
encoding = "scalar"

[[output.frontmatter]]
key = "description"
source = "description"
encoding = "scalar"

[[output.frontmatter]]
key = "model"
source = "model"
encoding = "scalar"

[[output.frontmatter]]
key = "tools"
source = "tools"
encoding = "comma-list"

[output.permissions.tools]
type = "list"

# 存取等級 -> 權限欄位。下面是範例工具名稱，換成 {name} 的實際名稱。
# write 沒有欄位要輸出時留空表（代表不限制）。
[access.read-only]
tools = ["read", "grep", "glob"]

[access.write]

[access.verify]
tools = ["read", "grep", "glob", "bash"]

# role 宣告了 web capability（目前是 security-reviewer）時套用；
# list 欄位會附加到 access 表同名的 list。這個 host 沒有對應的開關就留空。
[capabilities.web]
{roles}'''

ROLE = '''
[roles.{role}]
description = "TODO 填寫 {role} 的一句話說明，什麼時候該派它"
'''


def scaffold(root: Path, name: str) -> list[Path]:
    if not render.HOST_NAME.match(name):
        raise render.RenderError(f"host 名稱必須是小寫英數加連字號，收到 {name!r}")
    host = root / "hosts" / name
    if name in render.RENDERERS or host.exists():
        raise render.RenderError(f"hosts/{name} 已存在，不覆寫")
    roles = render.load_toml(root / "core" / "roles.toml")["roles"]
    files = {
        host / "binding.toml": TEMPLATE.format(name=name, roles="".join(ROLE.format(role=r) for r in roles)),
        host / "frames" / "default.md": render.contracts.FRAME_PLACEHOLDER,
        host / "addenda" / ".gitkeep": "",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return list(files)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="新 host 的名稱（小寫英數加連字號）")
    parser.add_argument("--root", type=Path, default=render.REPO, help="repo 根目錄（測試用）")
    args = parser.parse_args(argv)
    try:
        created = scaffold(args.root, args.name)
    except (render.RenderError, OSError, KeyError) as exc:
        print(f"new_host 失敗: {exc}", file=sys.stderr)
        return 2
    for path in created:
        print(f"已建立 {path.relative_to(args.root).as_posix()}")
    print(f"下一步：填 hosts/{args.name}/binding.toml 的 [models]，再執行 docs/new-host.md 的步驟。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
