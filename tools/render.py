#!/usr/bin/env python3
"""從 core/（roles、models、tiers）、hosts/<host>/binding.toml 與 hosts/<host>/src/ 產生 host 輸出。

用法：python3 tools/render.py --host <host> (--check|--write|--explain) [--root DIR]
<host> 是 claude、codex、agy、grok、opencode，或 hosts/<name>/binding.toml 宣告
renderer = "generic-md" 的 host（輸出格式由 binding 的 [output] 宣告，不需寫程式碼）。
另有 claude-plugin：由 claude 的 render 結果、hooks/shoal_guard.py 與根目錄 VERSION 產生
Claude plugin（claude-plugin/ 與 .claude-plugin/marketplace.json），不屬於五個 host。

--explain 只印出每個 role 的選模與權限推導過程，不讀也不改 dist。
exit code：0 成功；1 --check 發現 dist 與 render 結果不同；2 來源驗證失敗或沒有模型滿足規則。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts  # noqa: E402
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
# role 文字來源：core = core/contracts 的條款加 host 的 frames/addenda；legacy = host src 內的原文。
ROLE_TEXT_MODES = ("core", "legacy")
READ_ONLY_FORBIDDEN_TOOLS = {"Write", "Edit", "Bash", "NotebookEdit"}
# frontmatter 之後緊接一行空白，再接 body。
FRONTMATTER_KEYS = ("name", "description", "model", "effort")
# codex agent toml 中，name / description / model / effort 之後依序輸出的選填欄位。
CODEX_OPTIONAL_KEYS = ("sandbox_mode", "web_search")


# generic-md host：輸出格式由 binding 的 [output] 宣告（見 docs/new-host.md）。
GENERIC_RENDERER = "generic-md"
ENCODINGS = ("scalar", "comma-list", "block-list", "folded", "nested-map")
PERMISSION_TYPES = ("list", "scalar", "map")
# frontmatter 欄位的內建來源；其餘來源必須是 [output.permissions] 宣告過的權限欄位。
BUILTIN_SOURCES = ("name", "description", "model")
_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")
HOST_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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


@dataclass(frozen=True)
class PermSchema:
    """host 接受的權限欄位：欄位名 -> list / scalar / map，以及互斥的欄位組。"""
    types: dict[str, str]
    exclusive: tuple[str, ...] = ()


def permission_schema(host: str, binding: dict) -> PermSchema:
    """既有五個 host 用程式內的表；generic-md host 取自 binding 的 [output.permissions.<field>]。"""
    if host in PERMISSION_KEYS:
        return PermSchema({k: "list" if k in LIST_KEYS else "scalar" for k in PERMISSION_KEYS[host]},
                          EXCLUSIVE_KEYS.get(host, ()))
    declared = binding.get("output", {}).get("permissions", {})
    if not isinstance(declared, dict):
        raise RenderError("[output.permissions] 必須是 table")
    types: dict[str, str] = {}
    for key, table in declared.items():
        where = f"[output.permissions.{key}]"
        if not _KEY.match(key) or key in BUILTIN_SOURCES:
            raise RenderError(f"{where}: 欄位名只能是英數、底線、連字號，且不可是 {', '.join(BUILTIN_SOURCES)}")
        if not isinstance(table, dict) or set(table) != {"type"}:
            raise RenderError(f"{where}: 只接受 type 一個欄位")
        if table["type"] not in PERMISSION_TYPES:
            raise RenderError(f"{where}: type 必須是 {list(PERMISSION_TYPES)}")
        types[key] = table["type"]
    return PermSchema(types)


def _check_field(where: str, key: str, value: object, kind: str) -> None:
    if kind == "list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise RenderError(f"{where}: {key} 必須是字串陣列")
    elif kind == "map":
        if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
            raise RenderError(f"{where}: {key} 必須是字串對字串的 table")
    elif not isinstance(value, str):
        raise RenderError(f"{where}: {key} 必須是字串")


def validate_access_tables(host: str, binding: dict) -> None:
    """binding 的 [access.<level>]、[capabilities.<name>]：名稱在詞彙內、欄位屬於這個 host、型別正確。"""
    types = permission_schema(host, binding).types
    keys = tuple(types)
    for kind, vocabulary in (("access", ACCESS), ("capabilities", CAPABILITIES)):
        for level, table in binding.get(kind, {}).items():
            if level not in vocabulary:
                raise RenderError(f"[{kind}.{level}]: 名稱必須是 {sorted(vocabulary)}")
            unknown = sorted(set(table) - set(keys))
            if unknown:
                only = ", ".join(keys) or "無，先在 [output.permissions.<欄位>] 宣告"
                raise RenderError(f"[{kind}.{level}]: {host} 不接受欄位 {', '.join(unknown)}（只有 {only}）")
            for key, value in table.items():
                _check_field(f"[{kind}.{level}]", key, value, types[key])


def derive_permission(host: str, name: str, access: str, capabilities: list[str],
                      binding: dict, spec: dict) -> Permission:
    """對應表 [access.<level>] 疊加 [capabilities.<name>]，最後套用 role 層級的選用覆寫。

    capability 的 list 欄位附加到 access 表同名的 list（access 表沒有該 list，代表這個等級本來
    不受限，不輸出）；scalar 欄位直接設定，與 access 表衝突時失敗。覆寫以欄位為單位整個取代。
    """
    if access not in ACCESS:
        raise RenderError(f"{name}: access 必須是 {sorted(ACCESS)}")
    schema = permission_schema(host, binding)
    table = binding.get("access", {}).get(access)
    if table is None:
        raise RenderError(f"{name}: access = \"{access}\"，但 binding 沒有 [access.{access}]")
    fields = {k: list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v
              for k, v in table.items()}
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
            elif isinstance(value, dict):
                merged = fields.setdefault(key, {})
                for mkey, mvalue in value.items():
                    if merged.get(mkey, mvalue) != mvalue:
                        raise RenderError(f"{name}: [capabilities.{cap}].{key}.{mkey} 與 [access.{access}].{key}.{mkey} 衝突")
                    merged[mkey] = mvalue
            elif key in fields and fields[key] != value:
                raise RenderError(f"{name}: [capabilities.{cap}].{key} 與 [access.{access}].{key} 衝突")
            else:
                fields[key] = value
    overridden = [k for k in schema.types if k in spec]
    for key in overridden:
        _check_field(f"{name}", key, spec[key], schema.types[key])
        fields[key] = spec[key]
    exclusive = schema.exclusive
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
    core["contracts"] = load_contracts(root, core["roles"])
    return core


def load_contracts(root: Path, roles: dict) -> dict[str, list[contracts.Clause]]:
    """core/contracts/<role>.toml；檔名必須是 roles.toml 的 role。沒有檔案的 role 不在結果內。"""
    out: dict[str, list[contracts.Clause]] = {}
    for path in sorted((root / "core" / "contracts").glob("*.toml")):
        if path.stem not in roles:
            raise RenderError(f"core/contracts/{path.name}: roles.toml 沒有 role {path.stem}")
        try:
            out[path.stem] = contracts.load_contract(path)
        except contracts.ContractError as exc:
            raise RenderError(f"core/contracts/{path.name}: {exc}") from exc
    return out


def role_text_mode(name: str, binding: dict) -> str:
    """[roles.<name>].role_text 覆寫 binding 頂層的 role_text。"""
    return binding["roles"][name].get("role_text", binding["role_text"])


def role_body(name: str, core: dict, binding: dict, src: Path,
              legacy: Callable[[], bytes]) -> bytes:
    """role 的正文 bytes：legacy 時是 src 原文，core 時是 frame + 依序排列的條款與 addenda。

    frames/ 與 addenda/ 在 hosts/<host>/ 底下、src/ 之外，不會被 passthrough 帶進 dist。
    """
    if role_text_mode(name, binding) == "legacy":
        return legacy()
    clauses = core["contracts"].get(name)
    if clauses is None:
        raise RenderError(f'{name}: role_text = "core"，但 core/contracts/{name}.toml 不存在')
    host_dir = src.parent
    try:
        addenda = contracts.load_addenda(host_dir / "addenda" / f"{name}.toml")
        frame = contracts.load_frame(host_dir / "frames", name)
        text = contracts.apply_frame(frame, contracts.compose(clauses, addenda))
    except contracts.ContractError as exc:
        raise RenderError(f"{name}: {exc}") from exc
    return text.encode("utf-8")


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


def _legacy_body(src: Path, folder: str, name: str) -> bytes:
    return (src / folder / f"{name}.md").read_bytes()


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
    if binding.get("role_text") not in ROLE_TEXT_MODES:
        raise RenderError(f"binding 的 role_text 必須是 {list(ROLE_TEXT_MODES)}")
    for name, spec in bound.items():
        if spec.get("role_text", "legacy") not in ROLE_TEXT_MODES:
            raise RenderError(f"{name}: role_text 必須是 {list(ROLE_TEXT_MODES)}")
    for name, spec in binding.get("extra_roles", {}).items():
        if "role_text" in spec:
            raise RenderError(f"{name}: host 專屬 role 沒有 core 條款，不可設 role_text")
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

    def agent(name: str, spec: dict, model: str, body: bytes) -> None:
        out[f"agents/{name}.md"] = _frontmatter(name, spec, perms[name], model).encode("utf-8") + body

    for name in core["roles"]:
        agent(name, binding["roles"][name], resolve_model(name, core, binding),
              role_body(name, core, binding, src, lambda n=name: _legacy_body(src, "agents", n)))
    for name, spec in binding.get("extra_roles", {}).items():
        agent(name, spec, spec["model"], _legacy_body(src, "agents", name))

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

    def agent(name: str, spec: dict, model: str, body: bytes) -> None:
        out[f"agents/{name}.toml"] = _codex_agent(name, spec, perms[name], model, body)

    for name in core["roles"]:
        agent(name, binding["roles"][name], resolve_model(name, core, binding),
              role_body(name, core, binding, src, lambda n=name: _legacy_body(src, "agents", n)))
    for name, spec in binding.get("extra_roles", {}).items():
        agent(name, spec, spec["model"], _legacy_body(src, "agents", name))

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
        body = role_body(name, core, binding, src, lambda n=name: _legacy_body(src, "agents", n))
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


GROK_RULES_PATH = "rules/pilotfish-grok.md"
GROK_GUARD_PATH = "hooks/pilotfish-grok/shoal_guard.py"
GROK_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")
GROK_MARKER = re.compile(rb"^<!-- pilotfish-grok v\S+ -->$", re.MULTILINE)


def grok_version(host_dir: Path) -> str:
    """hosts/grok/VERSION 的內容（R2）；格式是 semver，可帶 -shoal.N 之類的後綴。"""
    path = host_dir / "VERSION"
    try:
        version = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RenderError(f"無法讀取 {path}: {exc}") from exc
    if not GROK_VERSION.match(version):
        raise RenderError(f"{path}: 版本格式不合法: {version!r}")
    return version


def _grok_rules(src: Path) -> bytes:
    """rules 取自 src/rules/pilotfish-grok.md（上游 v1.0.6 逐字）；只有 version marker 由 hosts/grok/VERSION 產生（R1、R2）。"""
    path = src / GROK_RULES_PATH
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RenderError(f"無法讀取 {path}: {exc}") from exc
    if len(GROK_MARKER.findall(data)) != 1:
        raise RenderError(f"{path} 必須恰有一行 '<!-- pilotfish-grok v<版本> -->' marker")
    marker = f"<!-- pilotfish-grok v{grok_version(src.parent)} -->".encode("utf-8")
    return GROK_MARKER.sub(lambda _m: marker, data, count=1)


def _guard_script(root: Path) -> bytes:
    """dispatch guard 只有一份來源（hooks/shoal_guard.py）；host dist 內的副本由 render 產生，--check 擋住手改。"""
    path = root / "hooks" / "shoal_guard.py"
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RenderError(f"無法讀取 {path}: {exc}") from exc


def render_grok(core: dict, binding: dict, src: Path) -> dict[str, bytes]:
    """config.snippet.toml 等 agents/ 以外的檔案逐字取自 vendored src；agents/*.md 依 role_text 產生（core 時 frame 內含 frontmatter）；roles/*.toml 由 binding 產生。"""
    perms = validate_grok(core, binding)
    out: dict[str, bytes] = {}
    for name in _bound_roles(core, binding):
        body = role_body(name, core, binding, src, lambda n=name: _legacy_body(src, "agents", n))
        match = re.search(rb"^model: (.+)$", body.split(b"\n---\n", 1)[0], re.MULTILINE)
        expected = resolve_model(name, core, binding)
        if not match or match.group(1).decode("utf-8") != expected:
            raise RenderError(f"{name}: src/agents/{name}.md 的 model 必須等於 binding 解析出的 {expected}")
        out[f"agents/{name}.md"] = body
        out[f"roles/{name}.toml"] = _grok_role_toml(name, binding["roles"][name], perms[name])
    _passthrough(src, out, {"agents", "rules"})
    out[GROK_RULES_PATH] = _grok_rules(src)
    out[GROK_GUARD_PATH] = _guard_script(src.parents[2])
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
    out = {f"roles/{name}.md": role_body(name, core, binding, src,
                                         lambda n=name: _legacy_body(src, "roles", n))
           for name in names}

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


# ---- generic-md：輸出格式由 binding 的 [output] 宣告，不需要專屬 renderer ----
# 每個 role 一個 Markdown 檔：YAML frontmatter（依宣告順序）加 role 文字（core 條款加 frames 與 addenda）。
ENCODING_KIND = {"scalar": "scalar", "folded": "scalar", "comma-list": "list",
                 "block-list": "list", "nested-map": "map"}
# 各編碼接受的選項；indent 預設 2，width 只給 folded（含縮排的行寬，省略則沿用來源的換行）。
ENCODING_OPTIONS = {"scalar": (), "comma-list": (), "block-list": ("indent",),
                    "folded": ("indent", "width"), "nested-map": ("indent",)}
GENERIC_ROLE_KEYS = ("description", "model", "role_text")


def _value_kind(value: object) -> str | None:
    if isinstance(value, str):
        return "scalar"
    if isinstance(value, list):
        return "list"
    return "map" if isinstance(value, dict) else None


def _role_fields(binding: dict, schema: PermSchema) -> list[str]:
    """[output].role_fields：除了 description、model、role_text 與權限欄位之外，[roles.<r>] 還允許的 key。"""
    fields = binding["output"].get("role_fields", [])
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        raise RenderError("[output] 的 role_fields 必須是字串陣列")
    for field in fields:
        if not _KEY.match(field) or field in GENERIC_ROLE_KEYS or field in schema.types:
            raise RenderError(f"[output] 的 role_fields 不可含 {field}（key 格式不合，或已是內建的 role key 或權限欄位）")
    if len(set(fields)) != len(fields):
        raise RenderError("[output] 的 role_fields 有重複")
    return fields


def _generic_entries(where: str, binding: dict, schema: PermSchema) -> list[dict]:
    """驗證 [output].frontmatter 的每個欄位宣告；where 是錯誤訊息的前綴（含 role）。"""
    role_fields = _role_fields(binding, schema)
    entries = binding["output"]["frontmatter"]
    if not isinstance(entries, list) or not entries or not all(isinstance(e, dict) for e in entries):
        raise RenderError(f"{where}: [output] 的 frontmatter 必須是至少一個 [[output.frontmatter]]")
    seen: set[str] = set()
    for entry in entries:
        key = entry.get("key")
        label = f"{where} 欄位 {key}"
        unknown = sorted(set(entry) - {"key", "source", "value", "encoding", "indent", "width", "optional"})
        if unknown:
            raise RenderError(f"{label}: 未知的設定 {', '.join(unknown)}")
        if not isinstance(key, str) or not _KEY.match(key):
            raise RenderError(f"{label}: key 必須是英數、底線、連字號組成的字串")
        if key in seen:
            raise RenderError(f"{label}: key 重複")
        seen.add(key)
        encoding = entry.get("encoding")
        if encoding not in ENCODINGS:
            raise RenderError(f"{label}: 不支援的編碼 {encoding}（只有 {', '.join(ENCODINGS)}）")
        if ("source" in entry) == ("value" in entry):
            raise RenderError(f"{label}: source 與 value 必須恰好有一個")
        if "source" in entry:
            source = entry["source"]
            if source in BUILTIN_SOURCES:
                kind = "scalar"
            elif isinstance(source, str) and source.startswith("role."):
                kind = None  # 型別由每個 role 的值決定，render 時再對編碼檢查
                if source[len("role."):] not in role_fields:
                    raise RenderError(f"{label}: 來源 {source} 沒有在 [output] 的 role_fields 宣告")
            elif source in schema.types:
                kind = schema.types[source]
            else:
                allowed = [*BUILTIN_SOURCES, *schema.types, *(f"role.{f}" for f in role_fields)]
                raise RenderError(f"{label}: 來源 {source} 不存在（只有 {', '.join(allowed)}；"
                                  "權限欄位要先在 [output.permissions.<欄位>] 宣告，role 欄位要先列入 role_fields）")
        else:
            kind = _value_kind(entry["value"])
            if kind is None:
                raise RenderError(f"{label}: value 必須是字串、字串陣列或字串對字串的 table")
            _check_field(label, "value", entry["value"], kind)
        if "optional" in entry:
            if not str(entry.get("source", "")).startswith("role.") or not isinstance(entry["optional"], bool):
                raise RenderError(f"{label}: optional 只能用在 role.<key> 來源，值必須是 true 或 false")
        if kind is not None and ENCODING_KIND[encoding] != kind:
            raise RenderError(f"{label}: 編碼 {encoding} 需要 {ENCODING_KIND[encoding]} 型別的來源，收到 {kind}")
        for option in ("indent", "width"):
            if option in entry:
                value = entry[option]
                if option not in ENCODING_OPTIONS[encoding]:
                    raise RenderError(f"{label}: 編碼 {encoding} 不接受 {option}")
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise RenderError(f"{label}: {option} 必須是正整數")
    return entries


def _check_output_path(pattern: object) -> str:
    if not isinstance(pattern, str) or pattern.count("{role}") != 1 or "{" in pattern.replace("{role}", ""):
        raise RenderError('[output] 的 path 必須恰好有一個 {role}，且沒有其他大括號（例如 "agents/{role}.md"）')
    parts = pattern.split("/")
    if "\\" in pattern or pattern.startswith("/") or ".." in parts or "" in parts or not pattern.endswith(".md"):
        raise RenderError("[output] 的 path 必須是 dist 內的相對路徑（用 /，不含 ..），且以 .md 結尾")
    return pattern


def validate_generic(host: str, core: dict, binding: dict) -> dict[str, Permission]:
    """generic-md 的驗證：renderer、[models]、R4（不可有 extra_roles）、role_text 必須 core、[output] 宣告。"""
    if binding.get("renderer") != GENERIC_RENDERER:
        raise RenderError(f'binding 的 renderer 必須是 "{GENERIC_RENDERER}"')
    if not binding.get("models") and binding.get("selection") != "inherit":
        raise RenderError(f"尚未填 [models]：請在 hosts/{host}/binding.toml 填入這個 host 可用的模型"
                          "（key 必須在 core/models.toml），或設 selection = \"inherit\"")
    for name in binding.get("extra_roles", {}):
        raise RenderError(f"{name}: generic-md host 不支援 host 專屬 role（[extra_roles.{name}]）；"
                          "需要時請改寫專屬 renderer")
    if binding.get("role_text") != "core":
        raise RenderError('generic-md host 的 role_text 必須是 "core"')
    output = binding.get("output")
    if not isinstance(output, dict):
        raise RenderError("binding 必須有 [output]（path 與 [[output.frontmatter]]）")
    unknown = sorted(set(output) - {"path", "frontmatter", "permissions", "role_fields"})
    if unknown:
        raise RenderError(f"[output]: 未知的設定 {', '.join(unknown)}")
    _check_output_path(output.get("path"))
    schema = permission_schema(host, binding)
    validate_catalog(core, binding)
    perms = derive_permissions(host, core, binding)
    for name in _bound_roles(core, binding):
        spec = binding["roles"][name]
        if spec.get("role_text", "core") != "core":
            raise RenderError(f'{name}: generic-md host 的 role_text 必須是 "core"')
        allowed = [*GENERIC_ROLE_KEYS, *schema.types, *_role_fields(binding, schema)]
        unknown = sorted(set(spec) - set(allowed))
        if unknown:
            raise RenderError(f"{name}: [roles.{name}] 不接受 {', '.join(unknown)}"
                              f"（只有 {', '.join(allowed)}；其他 key 要先列入 [output] 的 role_fields）")
        _generic_entries(f"{name}: frontmatter", binding, schema)
    return perms


def _no_legacy() -> bytes:
    raise RenderError("generic-md host 只用 core 條款，沒有 legacy 原文")


def _fold(text: str, indent: str, width: int | None) -> list[str]:
    if width is None:
        return [indent + line if line else "" for line in text.strip("\n").split("\n")]
    lines: list[str] = []
    for index, paragraph in enumerate(re.split(r"\n[ \t]*\n", text.strip())):
        if index:
            lines.append("")
        lines += [indent + line for line in textwrap.wrap(" ".join(paragraph.split()), width=max(width - len(indent), 1),
                                                          break_long_words=False, break_on_hyphens=False)]
    return lines


def _unsafe_plain(text: str) -> bool:
    """YAML plain scalar 不能原樣表達的文字；scalar 類編碼不加引號，遇到就拒絕。"""
    return (": " in text or " #" in text or text.endswith(":") or text[0] in "[]{}&*!|>'\"%@`#,?:"
            or text.startswith("- "))


def _encode_field(label: str, entry: dict, value: object) -> str:
    """把一個欄位依編碼寫成 YAML；label 是錯誤訊息的前綴（含 role 與欄位）。"""
    key, encoding = entry["key"], entry["encoding"]
    indent = " " * entry.get("indent", 2)
    kind = ENCODING_KIND[encoding]
    if encoding == "folded":
        if not value.strip() or "\r" in value:
            raise RenderError(f"{label}: 值不可為空，也不可含 CR")
    else:
        items = [*value, *value.values()] if kind == "map" else value if kind == "list" else [value]
        if kind != "scalar" and not value:
            raise RenderError(f"{label}: 不可是空的（不輸出請移除該欄位或對應表的設定）")
        if any(not item.strip() or "\n" in item or "\r" in item for item in items):
            raise RenderError(f"{label}: 值不可為空，也不可含換行")
        if encoding == "comma-list" and any("," in item for item in items):
            raise RenderError(f"{label}: 項目不可含逗號（逗號串接會混淆）")
        if any(_unsafe_plain(item) for item in items):
            raise RenderError(f"{label}: 值不能原樣寫成 YAML（含 \": \"、\" #\" 或以特殊字元開頭）；"
                              "scalar 不加引號，請改寫文字或改用 folded")
    if encoding == "scalar":
        return f"{key}: {value}\n"
    if encoding == "comma-list":
        return f"{key}: {', '.join(value)}\n"
    if encoding == "block-list":
        return f"{key}:\n" + "".join(f"{indent}- {item}\n" for item in value)
    if encoding == "nested-map":
        return f"{key}:\n" + "".join(f"{indent}{k}: {v}\n" for k, v in value.items())
    return f"{key}: >\n" + "".join(line + "\n" for line in _fold(value, indent, entry.get("width")))


def _generic_frontmatter(host: str, name: str, core: dict, binding: dict, perm: Permission) -> str:
    where = f"{name}: frontmatter"
    schema = permission_schema(host, binding)
    sources = {"name": name, "description": binding["roles"][name].get("description"),
               "model": resolve_model(name, core, binding)}
    text = "---\n"
    for entry in _generic_entries(where, binding, schema):
        if "value" in entry:
            value = entry["value"]
        elif entry["source"] in BUILTIN_SOURCES:
            value = sources[entry["source"]]
            if not isinstance(value, str):
                raise RenderError(f"{where} 欄位 {entry['key']}: 來源 {entry['source']} 必須是字串，"
                                  f"收到 {_name(value) if value is not None else '未設定'}")
        elif entry["source"].startswith("role."):
            field = entry["source"][len("role."):]
            label = f"{where} 欄位 {entry['key']}"
            if field not in binding["roles"][name]:
                if entry.get("optional"):
                    continue
                raise RenderError(f"{label}: [roles.{name}] 沒有 {field}（來源 {entry['source']}；"
                                  "不是每個 role 都有的欄位請設 optional = true）")
            value = binding["roles"][name][field]
            kind = _value_kind(value)
            if kind is None:
                raise RenderError(f"{label}: [roles.{name}].{field} 必須是字串、字串陣列或字串對字串的 table")
            _check_field(label, field, value, kind)
            if ENCODING_KIND[entry["encoding"]] != kind:
                raise RenderError(f"{label}: 編碼 {entry['encoding']} 需要 {ENCODING_KIND[entry['encoding']]} "
                                  f"型別的來源，[roles.{name}].{field} 是 {kind}")
        else:
            if entry["source"] not in perm.fields:
                continue  # 這個等級不限制此欄位（例如 write 沒有 tools allowlist），不輸出
            value = perm.fields[entry["source"]]
        text += _encode_field(f"{where} 欄位 {entry['key']}", entry, value)
    return text + "---\n\n"


def render_generic(host: str, core: dict, binding: dict, host_dir: Path) -> dict[str, bytes]:
    """回傳 {相對於 dist 的路徑: bytes}；role 文字沿用 role_body 的 frame / addenda 機制（frames/default.md）。"""
    perms = validate_generic(host, core, binding)
    pattern = binding["output"]["path"]
    out: dict[str, bytes] = {}
    for name in _bound_roles(core, binding):
        body = role_body(name, core, binding, host_dir / "src", _no_legacy)
        head = _generic_frontmatter(host, name, core, binding, perms[name])
        out[pattern.replace("{role}", name)] = head.encode("utf-8") + body
    return out


def discover_generic_hosts(root: Path) -> list[str]:
    """掃描 hosts/*/binding.toml 裡 renderer = "generic-md" 的 host；既有五個 host 的名稱保留給 RENDERERS。"""
    found = []
    for path in sorted((root / "hosts").glob("*/binding.toml")):
        name = path.parent.name
        if name in RENDERERS:
            continue
        if load_toml(path).get("renderer") == GENERIC_RENDERER:
            if not HOST_NAME.match(name):
                raise RenderError(f"hosts/{name}: host 名稱必須是小寫英數加連字號")
            found.append(name)
    return found


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


def render_host(root: Path, host: str) -> dict[str, bytes]:
    """既有五個 host 用各自的 renderer；其他 host 一律是 generic-md。"""
    if host in RENDERERS:
        return RENDERERS[host](root)
    host_dir = root / "hosts" / host
    return render_generic(host, load_core(root), load_toml(host_dir / "binding.toml"), host_dir)


def dist_dir(host: str) -> str:
    """generic-md host 的 dist 固定在 hosts/<name>/dist。"""
    return DIST_DIRS.get(host) or f"hosts/{host}/dist"


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


# ---- claude-plugin：Claude Code plugin 與 marketplace（generic-shoal K1、K2、K5）----
# 不是第六個 host：沒有自己的 binding，內容全部取自 claude 的 render 結果、guard 與根目錄 VERSION。
CLAUDE_PLUGIN = "claude-plugin"
CLAUDE_PLUGIN_HOST = "claude-plugin"  # --host 的名稱
CLAUDE_MARKETPLACE = ".claude-plugin/marketplace.json"
CLAUDE_PLUGIN_SRC = "hosts/claude/plugin-src"
# render 擁有的路徑（相對 repo 根）；其下多出的檔案由 --check 回報、--write 刪除。
CLAUDE_PLUGIN_OWNED = (CLAUDE_PLUGIN, CLAUDE_MARKETPLACE)
CLAUDE_PLUGIN_AUTHOR = {"name": "Miyago", "url": "https://github.com/miyago9267"}
CLAUDE_PLUGIN_REPO = "https://github.com/miyago9267/shoal"
# 與 tools/install_hooks.py 的 CLAUDE_MATCHER 相同；全域安裝與 plugin 的 guard 要看到同一批工具。
CLAUDE_PLUGIN_MATCHER = "Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow"
CLAUDE_PLUGIN_GUARD = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py" --host claude --plugin'
CLAUDE_PLUGIN_SESSIONSTART = '/bin/sh "${CLAUDE_PLUGIN_ROOT}/hooks/emit-sessionstart.sh"'
CLAUDE_PLUGIN_TIMEOUT = 10
PRODUCT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def product_version(root: Path) -> str:
    """根目錄 VERSION（產品版本）；plugin 與 marketplace 的版本都等於它。"""
    path = root / "VERSION"
    try:
        version = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RenderError(f"無法讀取 {path}: {exc}") from exc
    if not PRODUCT_VERSION.match(version):
        raise RenderError(f"{path}: 版本格式不合法: {version!r}")
    return version


def _plugin_hooks() -> dict:
    guard = {"type": "command", "command": CLAUDE_PLUGIN_GUARD, "timeout": CLAUDE_PLUGIN_TIMEOUT}
    return {
        "description": "shoal dispatch guard and policy bootstrap for Claude Code.",
        "hooks": {
            "SessionStart": [{
                "matcher": "startup|resume|clear|compact",
                "hooks": [{"type": "command", "command": CLAUDE_PLUGIN_SESSIONSTART}],
            }],
            "UserPromptSubmit": [{"hooks": [dict(guard)]}],
            "PreToolUse": [{"matcher": CLAUDE_PLUGIN_MATCHER, "hooks": [dict(guard)]}],
        },
    }


def render_claude_plugin(root: Path) -> dict[str, bytes]:
    """{相對 repo 根的路徑: bytes}。agents 與 skills 取自 claude 的 render 結果，guard 是 hooks/shoal_guard.py 的逐位元組副本。"""
    version = product_version(root)
    claude = RENDERERS["claude"](root)
    out: dict[str, bytes] = {}
    for rel, data in claude.items():
        if rel.startswith("agents/") or rel.startswith("skills/"):
            out[f"{CLAUDE_PLUGIN}/{rel}"] = data
    out[f"{CLAUDE_PLUGIN}/policy/claude-md.bootstrap.md"] = claude["claude-md.bootstrap.md"]
    src = root / CLAUDE_PLUGIN_SRC / "emit-sessionstart.sh"
    try:
        out[f"{CLAUDE_PLUGIN}/hooks/emit-sessionstart.sh"] = src.read_bytes()
    except OSError as exc:
        raise RenderError(f"無法讀取 {src}: {exc}") from exc
    out[f"{CLAUDE_PLUGIN}/hooks/shoal_guard.py"] = _guard_script(root)
    out[f"{CLAUDE_PLUGIN}/hooks/hooks.json"] = _json_bytes(_plugin_hooks())
    out[f"{CLAUDE_PLUGIN}/.claude-plugin/plugin.json"] = _json_bytes({
        "name": "shoal",
        "version": version,
        "description": "Pilotfish orchestration roles, skill, dispatch guard and policy bootstrap for Claude Code.",
        "author": CLAUDE_PLUGIN_AUTHOR,
        "repository": CLAUDE_PLUGIN_REPO,
        "license": "MIT",
        "keywords": ["orchestration", "subagents", "delegation", "dispatch-guard"],
    })
    out[CLAUDE_MARKETPLACE] = _json_bytes({
        "name": "shoal",
        "owner": CLAUDE_PLUGIN_AUTHOR,
        "description": "Marketplace for the shoal Claude Code plugin.",
        "plugins": [{
            "name": "shoal",
            "source": f"./{CLAUDE_PLUGIN}",
            "version": version,
            "description": "Pilotfish orchestration roles, skill, dispatch guard and policy bootstrap.",
            "category": "productivity",
            "tags": ["orchestration", "subagents", "delegation"],
        }],
    })
    return out


def _owned_files(root: Path, owned: tuple[str, ...]) -> set[str]:
    found: set[str] = set()
    for item in owned:
        path = root / item
        if path.is_file():
            found.add(item)
        elif path.is_dir():
            found |= {p.relative_to(root).as_posix() for p in path.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts}
    return found


def write_owned(root: Path, files: dict[str, bytes], owned: tuple[str, ...]) -> None:
    for rel in sorted(_owned_files(root, owned) - set(files)):
        (root / rel).unlink()
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)


def diff_owned(root: Path, files: dict[str, bytes], owned: tuple[str, ...]) -> list[str]:
    existing = _owned_files(root, owned)
    problems = [f"缺少: {rel}" for rel in files if rel not in existing]
    problems += [f"多出: {rel}" for rel in existing if rel not in files]
    problems += [f"內容不同: {rel}" for rel, data in files.items() if rel in existing and (root / rel).read_bytes() != data]
    return sorted(problems)


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
    if host in RENDERERS:
        validate_catalog(core, binding)
        perms = derive_permissions(host, core, binding)
    else:
        perms = validate_generic(host, core, binding)
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


def plugin_main(args: argparse.Namespace) -> int:
    """--host claude-plugin 的 --check / --write；輸出散在 repo 根下，所以用擁有的路徑清單比對，不是單一 dist 目錄。"""
    if args.explain:
        print("render 失敗: claude-plugin 沒有選模過程可 --explain（用 --host claude --explain）", file=sys.stderr)
        return 2
    try:
        files = render_claude_plugin(args.root)
    except (RenderError, OSError, KeyError) as exc:
        print(f"render 失敗: host {args.host}: {exc}", file=sys.stderr)
        return 2
    if args.write:
        write_owned(args.root, files, CLAUDE_PLUGIN_OWNED)
        print(f"已寫入 {len(files)} 個檔案到 {args.root / CLAUDE_PLUGIN} 與 {args.root / CLAUDE_MARKETPLACE}")
        return 0
    problems = diff_owned(args.root, files, CLAUDE_PLUGIN_OWNED)
    if problems:
        print(f"{CLAUDE_PLUGIN}/ 與 render 結果不同：", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} 個檔案一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows 預設 cp1252，輸出中文會拋 UnicodeEncodeError，強制 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    # --host 的選項要從 --root 底下探索 generic-md host，所以先單獨解析 --root。
    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre.add_argument("--root", type=Path, default=REPO)
    try:
        generic = discover_generic_hosts(pre.parse_known_args(argv)[0].root)
    except RenderError as exc:
        print(f"render 失敗: {exc}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, choices=[*sorted(RENDERERS), *generic, CLAUDE_PLUGIN_HOST])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--explain", action="store_true", help="印出每個 role 的選模過程")
    parser.add_argument("--root", type=Path, default=REPO, help="repo 根目錄（測試用）")
    args = parser.parse_args(argv)

    if args.host == CLAUDE_PLUGIN_HOST:
        return plugin_main(args)

    if args.explain:
        try:
            print(explain(args.root, args.host), end="")
        except (RenderError, resolve.ResolveError, OSError, KeyError) as exc:
            print(f"render 失敗: host {args.host}: {exc}", file=sys.stderr)
            return 2
        return 0

    try:
        files = render_host(args.root, args.host)
    except (RenderError, OSError, KeyError) as exc:
        print(f"render 失敗: host {args.host}: {exc}", file=sys.stderr)
        return 2

    dist = args.root / dist_dir(args.host)
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
