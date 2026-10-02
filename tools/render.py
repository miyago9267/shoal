#!/usr/bin/env python3
"""從 core/（roles、models、tiers）、hosts/<host>/binding.toml 與 hosts/<host>/src/ 產生 host 輸出。

用法：python3 tools/render.py --host claude|codex|agy|grok|opencode (--check|--write|--explain) [--root DIR]

--explain 只印出每個 role 的選模過程，不讀也不改 dist。
exit code：0 成功；1 --check 發現 dist 與 render 結果不同；2 來源驗證失敗或沒有模型滿足規則。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolve  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

ACCESS = {"read-only", "write", "verify"}
TIERS = ("fast", "standard", "strong", "frontier")
READ_ONLY_FORBIDDEN_TOOLS = {"Write", "Edit", "Bash", "NotebookEdit"}
# frontmatter 之後緊接一行空白，再接 body。
FRONTMATTER_KEYS = ("name", "description", "model", "effort")
# codex agent toml 中，name / description / model / effort 之後依序輸出的選填欄位。
CODEX_OPTIONAL_KEYS = ("sandbox_mode", "web_search")


class RenderError(Exception):
    """來源不合法（exit 2）。"""


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RenderError(f"無法讀取 {path}: {exc}") from exc


def _tools_of(name: str, spec: dict) -> tuple[str, list[str]]:
    keys = [k for k in ("tools", "disallowedTools") if k in spec]
    if len(keys) != 1:
        raise RenderError(f"{name}: binding 必須恰好有 tools 或 disallowedTools 其中之一")
    return keys[0], list(spec[keys[0]])


def load_core(root: Path) -> dict:
    """合併 core/roles.toml、models.toml、tiers.toml；頂層 key 分別是 roles、models、tiers。"""
    core: dict = {}
    for name in ("roles", "models", "tiers"):
        core.update(load_toml(root / "core" / f"{name}.toml"))
    return core


def resolve_resolution(name: str, core: dict, binding: dict) -> resolve.Resolution:
    """覆寫順序：[roles.<name>].model > binding 的 [tiers] > 規則。"""
    role = core["roles"][name]
    pin = binding.get("roles", {}).get(name, {}).get("model")
    return resolve.resolve(core, binding, tier=role["tier"], security=bool(role.get("security")),
                           pin=None if pin is None else (pin, f"[roles.{name}].model"))


def resolve_model(name: str, core: dict, binding: dict) -> object:
    try:
        return resolve_resolution(name, core, binding).model
    except resolve.ResolveError as exc:
        raise RenderError(f"role {name}: {exc}") from exc


def validate_catalog(core: dict, binding: dict) -> None:
    """host 共通規則：catalog 合法、catalog 的每個 role 在 binding 有對應或列入 omitted_roles、選模規則可解。"""
    try:
        resolve.validate_core(core)
        resolve.validate_binding(core, binding)
    except resolve.ResolveError as exc:
        raise RenderError(str(exc)) from exc
    catalog = core.get("roles", {})
    bound = binding.get("roles", {})

    for name, role in catalog.items():
        if role.get("access") not in ACCESS:
            raise RenderError(f"{name}: access 必須是 {sorted(ACCESS)}")
        if role.get("tier") not in TIERS:
            raise RenderError(f"{name}: tier 必須是 {list(TIERS)}")
    omitted = binding.get("omitted_roles", [])
    for name in omitted:
        if name not in catalog:
            raise RenderError(f"{name}: omitted_roles 列了此 role，但 roles.toml 沒有")
        if name in bound:
            raise RenderError(f"{name}: 同時出現在 omitted_roles 與 binding [roles]")
    for name in catalog:
        if name not in bound and name not in omitted:
            raise RenderError(f"{name}: roles.toml 有此 role，但 binding 沒有對應，也沒列在 omitted_roles")
    for name in bound:
        if name not in catalog:
            raise RenderError(f"{name}: binding 有此 role，但 roles.toml 沒有")
    for name in catalog:
        if name not in omitted:
            resolve_model(name, core, binding)  # 沒有模型滿足規則時在這裡 exit 2


def validate_claude(core: dict, binding: dict) -> None:
    validate_catalog(core, binding)
    catalog, bound = core["roles"], binding["roles"]
    specs = [(n, catalog[n]["access"], bound[n]) for n in catalog]
    specs += [(n, s.get("access"), s) for n, s in binding.get("extra_roles", {}).items()]
    for name, access, spec in specs:
        kind, tools = _tools_of(name, spec)
        if access == "read-only":
            if kind != "tools":
                raise RenderError(f"{name}: read-only role 必須用 tools allowlist，不可用 {kind}")
            bad = sorted(READ_ONLY_FORBIDDEN_TOOLS & set(tools))
            if bad:
                raise RenderError(f"{name}: read-only role 的 tools 不可包含 {', '.join(bad)}")


def _frontmatter(name: str, spec: dict, model: str) -> str:
    kind, tools = _tools_of(name, spec)
    fields = {"name": name, "description": spec["description"], "model": model, "effort": spec["effort"]}
    lines = [f"{k}: {fields[k]}" for k in FRONTMATTER_KEYS]
    lines.append(f"{kind}: {', '.join(tools)}")
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def render_claude(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """回傳 {相對於 dist 的路徑: bytes}，結構等於舊 pilotfish-claude 的 templates/。"""
    validate_claude(core, binding)
    out: dict[str, bytes] = {}

    def agent(name: str, spec: dict, model: str) -> None:
        body = (src / "agents" / f"{name}.md").read_bytes()
        out[f"agents/{name}.md"] = _frontmatter(name, spec, model).encode("utf-8") + body

    for name in core["roles"]:
        agent(name, binding["roles"][name], resolve_model(name, core, binding))
    for name, spec in binding.get("extra_roles", {}).items():
        agent(name, spec, spec["model"])

    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_file() and rel.parts[0] != "agents":
            out[rel.as_posix()] = path.read_bytes()
    return out



def resolve_root_model(core: dict, binding: dict) -> object:
    """codex [root]：有 model 就是手動指定，否則依 [root].tier 解析。"""
    root = binding["root"]
    pin = root.get("model")
    try:
        return resolve.resolve(core, binding, tier=root["tier"],
                               pin=None if pin is None else (pin, "[root].model")).model
    except resolve.ResolveError as exc:
        raise RenderError(f"[root]: {exc}") from exc


def validate_codex(core: dict, binding: dict) -> None:
    validate_catalog(core, binding)
    catalog = core["roles"]
    specs = [(n, catalog[n]["access"], binding["roles"][n]) for n in catalog]
    specs += [(n, s.get("access"), s) for n, s in binding.get("extra_roles", {}).items()]
    for name, access, spec in specs:
        if access not in ACCESS:
            raise RenderError(f"{name}: access 必須是 {sorted(ACCESS)}")
        sandbox = spec.get("sandbox_mode")
        if access == "read-only" and sandbox != "read-only":
            raise RenderError(f"{name}: read-only role 必須設 sandbox_mode = \"read-only\"")
        if access != "read-only" and sandbox == "read-only":
            raise RenderError(f"{name}: {access} role 不可設 sandbox_mode = \"read-only\"")
    if binding.get("root", {}).get("tier") not in TIERS:
        raise RenderError(f"binding 的 [root].tier 必須是 {list(TIERS)}")
    resolve_root_model(core, binding)


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _codex_agent(name: str, spec: dict, model: str, body: bytes) -> bytes:
    text = body.decode("utf-8")
    if '"""' in text or "\\" in text:
        raise RenderError(f"{name}: developer_instructions 不可含 三個雙引號 或反斜線")
    fields = {"name": name, "description": spec["description"], "model": model,
              "model_reasoning_effort": spec["effort"]}
    for key in CODEX_OPTIONAL_KEYS:
        if key in spec:
            fields[key] = spec[key]
    head = "".join(f"{k} = {_toml_str(v)}\n" for k, v in fields.items())
    data = f'{head}\ndeveloper_instructions = """\n{text}"""\n'
    parsed = tomllib.loads(data)
    if parsed["developer_instructions"] != text or parsed["name"] != name:
        raise RenderError(f"{name}: 產生的 toml 與來源不一致")
    return data.encode("utf-8")


def render_codex(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """回傳 {相對於 templates/ 的路徑: bytes}；templates/ 就是 codex 的 dist。"""
    validate_codex(core, binding)
    out: dict[str, bytes] = {}

    def agent(name: str, spec: dict, model: str) -> None:
        body = (src / "agents" / f"{name}.md").read_bytes()
        out[f"agents/{name}.toml"] = _codex_agent(name, spec, model, body)

    for name in core["roles"]:
        agent(name, binding["roles"][name], resolve_model(name, core, binding))
    for name, spec in binding.get("extra_roles", {}).items():
        agent(name, spec, spec["model"])

    root = binding["root"]
    values = {"model": resolve_root_model(core, binding),
              "model_reasoning_effort": root["model_reasoning_effort"],
              "plan_mode_reasoning_effort": root["plan_mode_reasoning_effort"]}
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if not path.is_file() or rel.parts[0] == "agents":
            continue
        data = path.read_bytes()
        if rel.as_posix() == "config.snippet.toml":
            text = data.decode("utf-8")
            for key, value in values.items():
                text = text.replace("{{" + key + "}}", value)
            if "{{" in text:
                raise RenderError("config.snippet.toml 有未替換的 placeholder")
            data = text.encode("utf-8")
        out[rel.as_posix()] = data
    return out


def _passthrough(src: Path, out: dict[str, bytes], skip_top: set[str]) -> None:
    """src/ 內不經 render 的檔案原樣進 dist（頂層目錄在 skip_top 內的除外）。"""
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_file() and rel.parts[0] not in skip_top:
            out[rel.as_posix()] = path.read_bytes()


def _bound_roles(core: dict, binding: dict) -> list[str]:
    """catalog 順序中、此 host 實際提供的 role（排除 omitted_roles）。"""
    return [n for n in core["roles"] if n in binding["roles"]]


# ---- agy（Gemini / Antigravity）----
AGY_MODELS = {"flash", "pro", "inherit"}
AGY_READ_ONLY_FORBIDDEN_TOOLS = {"run_command"}


def validate_agy(core: dict, binding: dict) -> None:
    validate_catalog(core, binding)
    if binding.get("supports_effort") is not False:
        raise RenderError("agy binding 必須設 supports_effort = false（frontmatter 沒有 effort 欄位）")
    for name in _bound_roles(core, binding):
        spec = binding["roles"][name]
        if "effort" in spec:
            raise RenderError(f"{name}: 此 host 不支援 effort，binding 不可設定")
        model = resolve_model(name, core, binding)
        if model not in AGY_MODELS:
            raise RenderError(f"{name}: agy model 只接受 {sorted(AGY_MODELS)}，收到 {model}")
        if core["roles"][name]["access"] == "read-only":
            if "tools" not in spec:
                raise RenderError(f"{name}: read-only role 必須用 tools allowlist")
            bad = sorted(AGY_READ_ONLY_FORBIDDEN_TOOLS & set(spec["tools"]))
            if bad:
                raise RenderError(f"{name}: read-only role 的 tools 不可包含 {', '.join(bad)}")


def _agy_frontmatter(name: str, spec: dict, model: str) -> str:
    desc = "".join(f"  {line}\n" for line in spec["description"].rstrip("\n").split("\n"))
    text = f"---\nname: {name}\ndescription: >\n{desc}model: {model}\n"
    if "tools" in spec:
        text += "tools:\n" + "".join(f"    - {tool}\n" for tool in spec["tools"])
    return text + "---\n\n"


def render_agy(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """回傳 {相對於 dist 的路徑: bytes}，結構等於 dotfile plugins/pilotfish-agy/templates/。"""
    validate_agy(core, binding)
    out: dict[str, bytes] = {}
    for name in _bound_roles(core, binding):
        body = (src / "agents" / f"{name}.md").read_bytes()
        model = resolve_model(name, core, binding)
        out[f"agents/{name}/agent.md"] = _agy_frontmatter(name, binding["roles"][name], model).encode("utf-8") + body
    _passthrough(src, out, {"agents"})
    return out


# ---- grok ----
GROK_CAPABILITY_MODES = {"read-only", "execute", "all"}


def validate_grok(core: dict, binding: dict) -> None:
    validate_catalog(core, binding)
    for name in _bound_roles(core, binding):
        spec = binding["roles"][name]
        if spec.get("capability_mode") not in GROK_CAPABILITY_MODES:
            raise RenderError(f"{name}: capability_mode 必須是 {sorted(GROK_CAPABILITY_MODES)}")
        read_only = core["roles"][name]["access"] == "read-only"
        if read_only != (spec["capability_mode"] == "read-only"):
            raise RenderError(f"{name}: capability_mode 必須在（且僅在）read-only role 設為 read-only")


def _grok_role_toml(name: str, spec: dict) -> bytes:
    head = f"# {spec['comment']}\n" if "comment" in spec else ""
    data = (f"{head}description = {_toml_str(spec['description'])}\n"
            f"default_capability_mode = {_toml_str(spec['capability_mode'])}\n"
            f"reasoning_effort = {_toml_str(spec['effort'])}\n")
    parsed = tomllib.loads(data)
    if parsed["description"] != spec["description"] or parsed["reasoning_effort"] != spec["effort"]:
        raise RenderError(f"{name}: 產生的 toml 與 binding 不一致")
    return data.encode("utf-8")


def render_grok(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """agents/*.md 與 config.snippet.toml 逐字取自 vendored src；roles/*.toml 由 binding 產生。"""
    validate_grok(core, binding)
    out: dict[str, bytes] = {}
    for name in _bound_roles(core, binding):
        body = (src / "agents" / f"{name}.md").read_bytes()
        match = re.search(rb"^model: (.+)$", body.split(b"\n---\n", 1)[0], re.MULTILINE)
        expected = resolve_model(name, core, binding)
        if not match or match.group(1).decode("utf-8") != expected:
            raise RenderError(f"{name}: src/agents/{name}.md 的 model 必須等於 binding 解析出的 {expected}")
        out[f"agents/{name}.md"] = body
        out[f"roles/{name}.toml"] = _grok_role_toml(name, binding["roles"][name])
    _passthrough(src, out, {"agents"})
    return out


# ---- opencode ----
OPENCODE_FALLBACKS = {"none", "ordered_candidates", "same_capability"}


def validate_opencode(core: dict, binding: dict) -> None:
    validate_catalog(core, binding)
    providers = binding.get("providers", {})
    for name in _bound_roles(core, binding):
        spec = binding["roles"][name]
        if spec.get("fallback") not in OPENCODE_FALLBACKS:
            raise RenderError(f"{name}: fallback 必須是 {sorted(OPENCODE_FALLBACKS)}")
        if spec["fallback"] == "none" and spec.get("fallback_candidates"):
            raise RenderError(f"{name}: fallback = \"none\" 不可有 fallback_candidates")
        candidates = [resolve_model(name, core, binding), *spec.get("fallback_candidates", [])]
        for cand in candidates:
            try:
                supported = providers[cand["provider"]]["models"][cand["model"]]["supported"]
            except KeyError as exc:
                raise RenderError(f"{name}: candidate {cand} 不在 binding 的 [providers] 內") from exc
            missing = sorted(set(spec["required_capabilities"]) - set(supported))
            if missing:
                raise RenderError(f"{name}: {cand['provider']}/{cand['model']} 不支援 {', '.join(missing)}")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def render_opencode(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """roles/*.md 逐字取自 src；catalog.json、routing.json 由 binding 產生。TS plugin 不經 render。"""
    validate_opencode(core, binding)
    names = _bound_roles(core, binding)
    stray = sorted(p.name for p in (src / "roles").glob("*.md") if p.stem not in names)
    if stray:
        raise RenderError(f"src/roles 有 binding 沒有的 role: {', '.join(stray)}")
    out = {f"roles/{name}.md": (src / "roles" / f"{name}.md").read_bytes() for name in names}

    agents, routes = {}, {}
    for name in names:
        spec = binding["roles"][name]
        primary = resolve_model(name, core, binding)
        agents[name] = {"mode": "subagent", "available": True, "model": dict(primary)}
        routes[name] = {"agent": name,
                        "candidates": [dict(primary), *map(dict, spec["fallback_candidates"])],
                        "fallback": spec["fallback"],
                        "requiredCapabilities": list(spec["required_capabilities"])}
    providers = {
        pname: {"authenticated": p["authenticated"], "identity": p["identity"],
                "models": {m: {"capabilities": {"supported": list(v["supported"]), "source": v["source"]}}
                           for m, v in p["models"].items()}}
        for pname, p in binding["providers"].items()
    }
    out["catalog.json"] = _json_bytes({"agents": agents, "providers": providers})
    out["routing.json"] = _json_bytes({"version": binding["routing"]["version"], "roles": routes})
    return out


# 多 host 擴充點：每個 host 一個 renderer，簽名 (root) -> {相對路徑: bytes}。
def _claude(root: Path) -> dict[str, bytes]:
    host = root / "hosts" / "claude"
    return render_claude(load_core(root), load_toml(host / "binding.toml"), host / "src")


def _codex(root: Path) -> dict[str, bytes]:
    host = root / "hosts" / "codex"
    return render_codex(load_core(root), load_toml(host / "binding.toml"), host / "src")


def _host_renderer(host: str, render: Callable[[dict, dict, Path], dict[str, bytes]]) -> Callable[[Path], dict[str, bytes]]:
    def run(root: Path) -> dict[str, bytes]:
        dirpath = root / "hosts" / host
        return render(load_core(root), load_toml(dirpath / "binding.toml"), dirpath / "src")
    return run


RENDERERS: dict[str, Callable[[Path], dict[str, bytes]]] = {
    "claude": _claude,
    "codex": _codex,
    "agy": _host_renderer("agy", render_agy),
    "grok": _host_renderer("grok", render_grok),
    "opencode": _host_renderer("opencode", render_opencode),
}
# dist 目錄（相對 repo 根）。codex 的 dist 沿用既有的 templates/，因為 installer、
# 測試與遠端 --ref raw URL 都寫死這個路徑。
DIST_DIRS = {"claude": "hosts/claude/dist", "codex": "templates", "agy": "hosts/agy/dist",
             "grok": "hosts/grok/dist", "opencode": "hosts/opencode/dist"}
# dist 之外、內容必須與 dist 某檔逐位元組相同的副本：{host: {dist 內路徑: repo 相對路徑}}。
MIRRORS = {
    "codex": {
        "agents-md.orchestration.md":
            "plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/references/orchestration-policy.md",
    },
}


def write_dist(dist: Path, files: dict[str, bytes]) -> None:
    for path in sorted(dist.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(dist).as_posix() not in files:
            path.unlink()
    for rel, data in files.items():
        target = dist / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def diff_dist(dist: Path, files: dict[str, bytes]) -> list[str]:
    existing = {p.relative_to(dist).as_posix(): p for p in dist.rglob("*") if p.is_file()} if dist.is_dir() else {}
    problems = [f"缺少: {rel}" for rel in files if rel not in existing]
    problems += [f"多出: {rel}" for rel in existing if rel not in files]
    problems += [f"內容不同: {rel}" for rel, data in files.items() if rel in existing and existing[rel].read_bytes() != data]
    return sorted(problems)


def write_mirrors(root: Path, host: str, files: dict[str, bytes]) -> None:
    for rel, target in MIRRORS.get(host, {}).items():
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        (root / target).write_bytes(files[rel])


def diff_mirrors(root: Path, host: str, files: dict[str, bytes]) -> list[str]:
    problems = []
    for rel, target in MIRRORS.get(host, {}).items():
        path = root / target
        if not path.is_file():
            problems.append(f"缺少: {target}")
        elif path.read_bytes() != files[rel]:
            problems.append(f"內容不同: {target}")
    return problems


def _name(value: object) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)


def _explain_one(label: str, tier: str, security: bool, core: dict, binding: dict,
                 pin: tuple[object, str] | None) -> list[str]:
    lines = [f"{label}  tier={tier}  security={str(security).lower()}"]
    try:
        res = resolve.resolve(core, binding, tier=tier, security=security, pin=pin)
    except resolve.ResolveError as exc:
        raise RenderError(f"{label}: {exc}") from exc
    width = max((len(c.key) for c in res.candidates), default=0)
    for cand in res.candidates:
        mark = "*" if cand.key == res.detail and res.source == "rule" else " "
        note = f"  排除：{cand.excluded}" if cand.excluded else ""
        lines.append(f"  {mark} {cand.key.ljust(width)}  capability={cand.capability} cost={cand.cost}{note}")
    origin = {"pin": f"手動指定 {res.detail}", "inherit": f"不介入 {res.detail}",
              "rule": f"resolver 選出 {res.detail}"}[res.source]
    lines.append(f"  結果：{_name(res.model)}（{origin}）")
    return lines


def explain(root: Path, host: str) -> str:
    """印出每個 role 的 tier、候選模型（含被排除的原因）、最後結果，以及它是 resolver 選的還是手動 pin 的。"""
    core, binding = load_core(root), load_toml(root / "hosts" / host / "binding.toml")
    validate_catalog(core, binding)
    mode = 'selection = "inherit"' if binding.get("selection") == "inherit" else "規則（catalog + tiers）"
    out = [f"host: {host}", f"選模方式: {mode}", ""]
    for name in _bound_roles(core, binding):
        role = core["roles"][name]
        pin = binding["roles"][name].get("model")
        out += _explain_one(name, role["tier"], bool(role.get("security")), core, binding,
                            None if pin is None else (pin, f"[roles.{name}].model")) + [""]
    for name, spec in binding.get("extra_roles", {}).items():
        out += [f"{name}（host 專屬 role）", f"  結果：{_name(spec['model'])}（手動指定 [extra_roles.{name}].model）", ""]
    if "root" in binding:
        rt = binding["root"]
        pin = rt.get("model")
        out += _explain_one("[root]", rt["tier"], False, core, binding,
                            None if pin is None else (pin, "[root].model")) + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    # Windows 預設 cp1252，輸出中文會拋 UnicodeEncodeError，強制 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, choices=sorted(RENDERERS))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--explain", action="store_true", help="印出每個 role 的選模過程")
    parser.add_argument("--root", type=Path, default=REPO, help="repo 根目錄（測試用）")
    args = parser.parse_args(argv)

    if args.explain:
        try:
            print(explain(args.root, args.host), end="")
        except (RenderError, resolve.ResolveError, OSError, KeyError) as exc:
            print(f"render 失敗: host {args.host}: {exc}", file=sys.stderr)
            return 2
        return 0

    try:
        files = RENDERERS[args.host](args.root)
    except (RenderError, OSError, KeyError) as exc:
        print(f"render 失敗: host {args.host}: {exc}", file=sys.stderr)
        return 2

    dist = args.root / DIST_DIRS[args.host]
    if args.write:
        write_dist(dist, files)
        write_mirrors(args.root, args.host, files)
        print(f"已寫入 {len(files)} 個檔案到 {dist}")
        return 0
    problems = diff_dist(dist, files) + diff_mirrors(args.root, args.host, files)
    if problems:
        print(f"{dist} 與 render 結果不同：", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} 個檔案一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
