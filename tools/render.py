#!/usr/bin/env python3
"""從 core/（roles、models、tiers）、hosts/<host>/binding.toml 與 hosts/<host>/src/ 產生 host 輸出。

用法：python3 tools/render.py --host claude|codex|agy|grok|opencode (--check|--write|--explain) [--root DIR]

--explain 只印出每個 role 的選模與權限推導過程，不讀也不改 dist。
exit code：0 成功；1 --check 發現 dist 與 render 結果不同；2 來源驗證失敗或沒有模型滿足規則。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolve  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

ACCESS = {"read-only", "write", "verify"}
# core 的 host 中立能力詞彙；各 host 在 binding 的 [capabilities.<name>] 宣告對應（可以是空表）。
CAPABILITIES = {"web"}
# 各 host 的權限欄位：[access.*]、[capabilities.*] 與 role 層級覆寫只能用這些 key。
PERMISSION_KEYS = {
    "claude": ("tools", "disallowedTools"),
    "codex": ("sandbox_mode", "web_search"),
    "agy": ("tools",),
    "grok": ("capability_mode",),
    "opencode": ("required_capabilities",),
}
LIST_KEYS = {"tools", "disallowedTools", "required_capabilities"}
# 同一組 key 互斥（Claude 的 allowlist 與 denylist）；覆寫其中一個時，推導出的其他個會被丟掉。
EXCLUSIVE_KEYS = {"claude": ("tools", "disallowedTools")}
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


@dataclass
class Permission:
    """一個 role 在某個 host 推導出的權限欄位，以及推導過程（給 --explain 與驗證用）。"""
    access: str
    capabilities: list[str]
    fields: dict[str, object]
    tables: list[str]
    overridden: list[str]


def _check_field(where: str, key: str, value: object) -> None:
    if key in LIST_KEYS:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise RenderError(f"{where}: {key} 必須是字串陣列")
    elif not isinstance(value, str):
        raise RenderError(f"{where}: {key} 必須是字串")


def validate_access_tables(host: str, binding: dict) -> None:
    """binding 的 [access.<level>]、[capabilities.<name>]：名稱在詞彙內、欄位屬於這個 host、型別正確。"""
    keys = PERMISSION_KEYS[host]
    for kind, vocabulary in (("access", ACCESS), ("capabilities", CAPABILITIES)):
        for level, table in binding.get(kind, {}).items():
            if level not in vocabulary:
                raise RenderError(f"[{kind}.{level}]: 名稱必須是 {sorted(vocabulary)}")
            unknown = sorted(set(table) - set(keys))
            if unknown:
                raise RenderError(f"[{kind}.{level}]: {host} 不接受欄位 {', '.join(unknown)}（只有 {', '.join(keys)}）")
            for key, value in table.items():
                _check_field(f"[{kind}.{level}]", key, value)


def derive_permission(host: str, name: str, access: str, capabilities: list[str],
                      binding: dict, spec: dict) -> Permission:
    """對應表 [access.<level>] 疊加 [capabilities.<name>]，最後套用 role 層級的選用覆寫。

    capability 的 list 欄位附加到 access 表同名的 list（access 表沒有該 list，代表這個等級本來
    不受限，不輸出）；scalar 欄位直接設定，與 access 表衝突時失敗。覆寫以欄位為單位整個取代。
    """
    if access not in ACCESS:
        raise RenderError(f"{name}: access 必須是 {sorted(ACCESS)}")
    table = binding.get("access", {}).get(access)
    if table is None:
        raise RenderError(f"{name}: access = \"{access}\"，但 binding 沒有 [access.{access}]")
    fields = {k: list(v) if isinstance(v, list) else v for k, v in table.items()}
    tables = [f"access.{access}"]
    for cap in capabilities:
        ctable = binding.get("capabilities", {}).get(cap)
        if ctable is None:
            raise RenderError(f"{name}: capability \"{cap}\"，但 binding 沒有 [capabilities.{cap}]")
        tables.append(f"capabilities.{cap}")
        for key, value in ctable.items():
            if isinstance(value, list):
                if key in fields:
                    fields[key] += [v for v in value if v not in fields[key]]
            elif key in fields and fields[key] != value:
                raise RenderError(f"{name}: [capabilities.{cap}].{key} 與 [access.{access}].{key} 衝突")
            else:
                fields[key] = value
    overridden = [k for k in PERMISSION_KEYS[host] if k in spec]
    for key in overridden:
        _check_field(f"{name}", key, spec[key])
        fields[key] = spec[key]
    exclusive = EXCLUSIVE_KEYS.get(host, ())
    if any(k in spec for k in exclusive):
        for key in exclusive:
            if key not in spec:
                fields.pop(key, None)
    return Permission(access, list(capabilities), fields, tables, overridden)


def derive_permissions(host: str, core: dict, binding: dict) -> dict[str, Permission]:
    """此 host 每個實際提供的 role（含 extra_roles）的權限；順序與輸出順序一致。"""
    validate_access_tables(host, binding)
    out: dict[str, Permission] = {}
    for name in _bound_roles(core, binding):
        role = core["roles"][name]
        out[name] = derive_permission(host, name, role["access"], role.get("capabilities", []),
                                      binding, binding["roles"][name])
    for name, spec in binding.get("extra_roles", {}).items():
        out[name] = derive_permission(host, name, spec.get("access"), spec.get("capabilities", []),
                                      binding, spec)
    return out


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
        caps = role.get("capabilities", [])
        if not isinstance(caps, list) or not set(caps) <= CAPABILITIES:
            raise RenderError(f"{name}: capabilities 必須是 {sorted(CAPABILITIES)} 的子集")
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


def _claude_tools(name: str, perm: Permission) -> tuple[str, list[str]]:
    keys = [k for k in ("tools", "disallowedTools") if k in perm.fields]
    if len(keys) != 1:
        raise RenderError(f"{name}: 推導結果必須恰好有 tools 或 disallowedTools 其中之一")
    return keys[0], list(perm.fields[keys[0]])


def validate_claude(core: dict, binding: dict) -> dict[str, Permission]:
    validate_catalog(core, binding)
    perms = derive_permissions("claude", core, binding)
    for name, perm in perms.items():
        kind, tools = _claude_tools(name, perm)
        if perm.access == "read-only":
            if kind != "tools":
                raise RenderError(f"{name}: read-only role 必須用 tools allowlist，不可用 {kind}")
            bad = sorted(READ_ONLY_FORBIDDEN_TOOLS & set(tools))
            if bad:
                raise RenderError(f"{name}: read-only role 的 tools 不可包含 {', '.join(bad)}")
    return perms


def _frontmatter(name: str, spec: dict, perm: Permission, model: str) -> str:
    kind, tools = _claude_tools(name, perm)
    fields = {"name": name, "description": spec["description"], "model": model, "effort": spec["effort"]}
    lines = [f"{k}: {fields[k]}" for k in FRONTMATTER_KEYS]
    lines.append(f"{kind}: {', '.join(tools)}")
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def render_claude(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """回傳 {相對於 dist 的路徑: bytes}，結構等於舊 pilotfish-claude 的 templates/。"""
    perms = validate_claude(core, binding)
    out: dict[str, bytes] = {}

    def agent(name: str, spec: dict, model: str) -> None:
        body = (src / "agents" / f"{name}.md").read_bytes()
        out[f"agents/{name}.md"] = _frontmatter(name, spec, perms[name], model).encode("utf-8") + body

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


def validate_codex(core: dict, binding: dict) -> dict[str, Permission]:
    validate_catalog(core, binding)
    perms = derive_permissions("codex", core, binding)
    for name, perm in perms.items():
        sandbox = perm.fields.get("sandbox_mode")
        if perm.access == "read-only" and sandbox != "read-only":
            raise RenderError(f"{name}: read-only role 必須設 sandbox_mode = \"read-only\"")
        if perm.access != "read-only" and sandbox == "read-only":
            raise RenderError(f"{name}: {perm.access} role 不可設 sandbox_mode = \"read-only\"")
    if binding.get("root", {}).get("tier") not in TIERS:
        raise RenderError(f"binding 的 [root].tier 必須是 {list(TIERS)}")
    resolve_root_model(core, binding)
    return perms


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _codex_agent(name: str, spec: dict, perm: Permission, model: str, body: bytes) -> bytes:
    text = body.decode("utf-8")
    if '"""' in text or "\\" in text:
        raise RenderError(f"{name}: developer_instructions 不可含 三個雙引號 或反斜線")
    fields = {"name": name, "description": spec["description"], "model": model,
              "model_reasoning_effort": spec["effort"]}
    for key in CODEX_OPTIONAL_KEYS:
        if key in perm.fields:
            fields[key] = perm.fields[key]
    head = "".join(f"{k} = {_toml_str(v)}\n" for k, v in fields.items())
    data = f'{head}\ndeveloper_instructions = """\n{text}"""\n'
    parsed = tomllib.loads(data)
    if parsed["developer_instructions"] != text or parsed["name"] != name:
        raise RenderError(f"{name}: 產生的 toml 與來源不一致")
    return data.encode("utf-8")


def render_codex(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """回傳 {相對於 templates/ 的路徑: bytes}；templates/ 就是 codex 的 dist。"""
    perms = validate_codex(core, binding)
    out: dict[str, bytes] = {}

    def agent(name: str, spec: dict, model: str) -> None:
        body = (src / "agents" / f"{name}.md").read_bytes()
        out[f"agents/{name}.toml"] = _codex_agent(name, spec, perms[name], model, body)

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


def validate_agy(core: dict, binding: dict) -> dict[str, Permission]:
    validate_catalog(core, binding)
    if binding.get("supports_effort") is not False:
        raise RenderError("agy binding 必須設 supports_effort = false（frontmatter 沒有 effort 欄位）")
    perms = derive_permissions("agy", core, binding)
    for name in _bound_roles(core, binding):
        spec = binding["roles"][name]
        if "effort" in spec:
            raise RenderError(f"{name}: 此 host 不支援 effort，binding 不可設定")
        model = resolve_model(name, core, binding)
        if model not in AGY_MODELS:
            raise RenderError(f"{name}: agy model 只接受 {sorted(AGY_MODELS)}，收到 {model}")
        if perms[name].access == "read-only":
            if "tools" not in perms[name].fields:
                raise RenderError(f"{name}: read-only role 必須用 tools allowlist")
            bad = sorted(AGY_READ_ONLY_FORBIDDEN_TOOLS & set(perms[name].fields["tools"]))
            if bad:
                raise RenderError(f"{name}: read-only role 的 tools 不可包含 {', '.join(bad)}")
    return perms


def _agy_frontmatter(name: str, spec: dict, perm: Permission, model: str) -> str:
    desc = "".join(f"  {line}\n" for line in spec["description"].rstrip("\n").split("\n"))
    text = f"---\nname: {name}\ndescription: >\n{desc}model: {model}\n"
    if "tools" in perm.fields:
        text += "tools:\n" + "".join(f"    - {tool}\n" for tool in perm.fields["tools"])
    return text + "---\n\n"


def render_agy(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """回傳 {相對於 dist 的路徑: bytes}，結構等於 dotfile plugins/pilotfish-agy/templates/。"""
    perms = validate_agy(core, binding)
    out: dict[str, bytes] = {}
    for name in _bound_roles(core, binding):
        body = (src / "agents" / f"{name}.md").read_bytes()
        model = resolve_model(name, core, binding)
        out[f"agents/{name}/agent.md"] = _agy_frontmatter(name, binding["roles"][name], perms[name], model).encode("utf-8") + body
    _passthrough(src, out, {"agents"})
    return out


# ---- grok ----
GROK_CAPABILITY_MODES = {"read-only", "execute", "all"}


def validate_grok(core: dict, binding: dict) -> dict[str, Permission]:
    validate_catalog(core, binding)
    perms = derive_permissions("grok", core, binding)
    for name in _bound_roles(core, binding):
        mode = perms[name].fields.get("capability_mode")
        if mode not in GROK_CAPABILITY_MODES:
            raise RenderError(f"{name}: capability_mode 必須是 {sorted(GROK_CAPABILITY_MODES)}")
        if (perms[name].access == "read-only") != (mode == "read-only"):
            raise RenderError(f"{name}: capability_mode 必須在（且僅在）read-only role 設為 read-only")
    return perms


def _grok_role_toml(name: str, spec: dict, perm: Permission) -> bytes:
    head = f"# {spec['comment']}\n" if "comment" in spec else ""
    data = (f"{head}description = {_toml_str(spec['description'])}\n"
            f"default_capability_mode = {_toml_str(perm.fields['capability_mode'])}\n"
            f"reasoning_effort = {_toml_str(spec['effort'])}\n")
    parsed = tomllib.loads(data)
    if parsed["description"] != spec["description"] or parsed["reasoning_effort"] != spec["effort"]:
        raise RenderError(f"{name}: 產生的 toml 與 binding 不一致")
    return data.encode("utf-8")


def render_grok(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """agents/*.md 與 config.snippet.toml 逐字取自 vendored src；roles/*.toml 由 binding 產生。"""
    perms = validate_grok(core, binding)
    out: dict[str, bytes] = {}
    for name in _bound_roles(core, binding):
        body = (src / "agents" / f"{name}.md").read_bytes()
        match = re.search(rb"^model: (.+)$", body.split(b"\n---\n", 1)[0], re.MULTILINE)
        expected = resolve_model(name, core, binding)
        if not match or match.group(1).decode("utf-8") != expected:
            raise RenderError(f"{name}: src/agents/{name}.md 的 model 必須等於 binding 解析出的 {expected}")
        out[f"agents/{name}.md"] = body
        out[f"roles/{name}.toml"] = _grok_role_toml(name, binding["roles"][name], perms[name])
    _passthrough(src, out, {"agents"})
    return out


# ---- opencode ----
OPENCODE_FALLBACKS = {"none", "ordered_candidates", "same_capability"}


def validate_opencode(core: dict, binding: dict) -> dict[str, Permission]:
    validate_catalog(core, binding)
    perms = derive_permissions("opencode", core, binding)
    providers = binding.get("providers", {})
    for name in _bound_roles(core, binding):
        spec = binding["roles"][name]
        if spec.get("fallback") not in OPENCODE_FALLBACKS:
            raise RenderError(f"{name}: fallback 必須是 {sorted(OPENCODE_FALLBACKS)}")
        if spec["fallback"] == "none" and spec.get("fallback_candidates"):
            raise RenderError(f"{name}: fallback = \"none\" 不可有 fallback_candidates")
        if "required_capabilities" not in perms[name].fields:
            raise RenderError(f"{name}: 推導結果必須有 required_capabilities")
        candidates = [resolve_model(name, core, binding), *spec.get("fallback_candidates", [])]
        for cand in candidates:
            try:
                supported = providers[cand["provider"]]["models"][cand["model"]]["supported"]
            except KeyError as exc:
                raise RenderError(f"{name}: candidate {cand} 不在 binding 的 [providers] 內") from exc
            missing = sorted(set(perms[name].fields.get("required_capabilities", [])) - set(supported))
            if missing:
                raise RenderError(f"{name}: {cand['provider']}/{cand['model']} 不支援 {', '.join(missing)}")
    return perms


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def render_opencode(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """roles/*.md 逐字取自 src；catalog.json、routing.json 由 binding 產生。TS plugin 不經 render。"""
    perms = validate_opencode(core, binding)
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
                        "requiredCapabilities": list(perms[name].fields["required_capabilities"])}
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


def _explain_permission(name: str, perm: Permission, section: str) -> list[str]:
    """權限推導：access、capabilities、套用的對應表、覆寫，以及推導出的欄位。"""
    tables = "、".join(f"[{t}]" for t in perm.tables)
    over = f"{'、'.join(perm.overridden)}（{section}）" if perm.overridden else "無"
    lines = [f"  權限：access={perm.access}  capabilities={','.join(perm.capabilities) or '無'}"
             f"  對應表={tables}  覆寫={over}"]
    lines += [f"    {k} = {json.dumps(v, ensure_ascii=False)}" for k, v in perm.fields.items()]
    if not perm.fields:
        lines.append("    （此等級沒有權限欄位輸出）")
    return lines


def explain(root: Path, host: str) -> str:
    """印出每個 role 的 tier、候選模型（含被排除的原因）、結果（resolver 選的或手動 pin 的）與權限推導。"""
    core, binding = load_core(root), load_toml(root / "hosts" / host / "binding.toml")
    validate_catalog(core, binding)
    perms = derive_permissions(host, core, binding)
    mode = 'selection = "inherit"' if binding.get("selection") == "inherit" else "規則（catalog + tiers）"
    out = [f"host: {host}", f"選模方式: {mode}", ""]
    for name in _bound_roles(core, binding):
        role = core["roles"][name]
        pin = binding["roles"][name].get("model")
        out += _explain_one(name, role["tier"], bool(role.get("security")), core, binding,
                            None if pin is None else (pin, f"[roles.{name}].model"))
        out += _explain_permission(name, perms[name], f"[roles.{name}]") + [""]
    for name, spec in binding.get("extra_roles", {}).items():
        out += [f"{name}（host 專屬 role）", f"  結果：{_name(spec['model'])}（手動指定 [extra_roles.{name}].model）"]
        out += _explain_permission(name, perms[name], f"[extra_roles.{name}]") + [""]
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
