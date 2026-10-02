"""依 tier 規則在 host 的可用模型內選模；純函式，不讀檔，可單獨測試。

輸入是 core（roles / models / tiers 三份 TOML 合併成的 dict）與某個 host 的 binding。
覆寫順序：role 或 root 的 model pin > binding 的 [tiers].<tier> > selection = "inherit" > 規則。
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIER_NAMES = ("fast", "standard", "strong", "frontier")
PICKS = ("cheapest", "most_capable")
# security = true 的 role 不可選到帶此旗標的模型。
SECURITY_EXCLUDE_FLAG = "refuses_defensive_security"


class ResolveError(Exception):
    """目錄、規則或 binding 不合法，或沒有模型滿足規則（exit 2）。"""


@dataclass(frozen=True)
class Candidate:
    key: str
    capability: int
    cost: int
    host_name: object
    excluded: str | None = None  # 被排除的原因；None 表示符合條件


@dataclass(frozen=True)
class Resolution:
    model: object  # host 內的名稱（字串，或 OpenCode 的 {provider, model}）
    source: str  # "pin" / "inherit" / "rule"
    detail: str  # 例如 "[roles.scout].model"、"[tiers].fast"、"anthropic/sonnet"
    candidates: tuple[Candidate, ...] = field(default=())


def validate_core(core: dict) -> None:
    for key, spec in core.get("models", {}).items():
        vendor = spec.get("vendor")
        if (
            not isinstance(vendor, str)
            or key.split("/", 1)[0] != vendor
            or "/" not in key
        ):
            raise ResolveError(
                f"models.toml: {key} 的 key 必須是 vendor/name，且 vendor 欄位要一致"
            )
        for axis in ("capability", "cost"):
            value = spec.get(axis)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 5
            ):
                raise ResolveError(f"models.toml: {key} 的 {axis} 必須是 1-5 的整數")
        flags = spec.get("flags", [])
        if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
            raise ResolveError(f"models.toml: {key} 的 flags 必須是字串 list")
    rules = core.get("tiers", {})
    for tier in TIER_NAMES:
        if tier not in rules:
            raise ResolveError(f"tiers.toml: 缺少 tier {tier}")
        rule = rules[tier]
        if rule.get("pick") not in PICKS:
            raise ResolveError(f"tiers.toml: {tier} 的 pick 必須是 {list(PICKS)}")
        if rule["pick"] == "cheapest":
            floor = rule.get("min_capability")
            if (
                isinstance(floor, bool)
                or not isinstance(floor, int)
                or not 1 <= floor <= 5
            ):
                raise ResolveError(
                    f"tiers.toml: {tier} 的 min_capability 必須是 1-5 的整數"
                )
    for tier in rules:
        if tier not in TIER_NAMES:
            raise ResolveError(f"tiers.toml: 未知的 tier {tier}")


def validate_binding(core: dict, binding: dict) -> None:
    selection, models = binding.get("selection"), binding.get("models")
    if selection not in (None, "inherit"):
        raise ResolveError('binding 的 selection 只接受 "inherit"')
    if selection == "inherit" and models is not None:
        raise ResolveError('binding 的 selection = "inherit" 不可同時有 [models]')
    if selection is None and not models:
        raise ResolveError('binding 必須有 [models]，或設 selection = "inherit"')
    for key in models or {}:
        if key not in core.get("models", {}):
            raise ResolveError(
                f"binding 的 [models] 有 {key}，但 core/models.toml 沒有"
            )
    for tier in binding.get("tiers", {}):
        if tier not in TIER_NAMES:
            raise ResolveError(f"binding 的 [tiers] 有未知的 tier {tier}")


def candidates_for(
    core: dict, binding: dict, tier: str, security: bool
) -> list[Candidate]:
    """這個 host 可用的每個模型，附上在該 tier 是否被排除與原因。依 key 排序。"""
    catalog, rule = core["models"], core["tiers"][tier]
    out = []
    for key, host_name in sorted(binding.get("models", {}).items()):
        spec = catalog[key]
        reason = None
        if security and SECURITY_EXCLUDE_FLAG in spec.get("flags", []):
            reason = f"帶有 {SECURITY_EXCLUDE_FLAG} 旗標（security role 不可用）"
        elif rule["pick"] == "cheapest" and spec["capability"] < rule["min_capability"]:
            reason = f"capability {spec['capability']} 低於 {tier} 門檻 {rule['min_capability']}"
        out.append(Candidate(key, spec["capability"], spec["cost"], host_name, reason))
    return out


def _pick(core: dict, tier: str, eligible: list[Candidate]) -> Candidate:
    if core["tiers"][tier]["pick"] == "cheapest":
        return min(eligible, key=lambda c: (c.cost, c.capability, c.key))
    return min(eligible, key=lambda c: (-c.capability, c.cost, c.key))


def _reject_flagged_pin(core: dict, binding: dict, pin: tuple[object, str]) -> None:
    """手動 pin 優先於選模規則，但不能繞過 security 排除：pin 到帶旗標的模型直接失敗。"""
    for key, host_name in binding.get("models", {}).items():
        if host_name == pin[0] and SECURITY_EXCLUDE_FLAG in core["models"][key].get(
            "flags", []
        ):
            raise ResolveError(
                f"security role 被 {pin[1]} 指定到 {key}，"
                f"但它帶有 {SECURITY_EXCLUDE_FLAG} 旗標"
            )


def resolve(
    core: dict,
    binding: dict,
    *,
    tier: str,
    security: bool = False,
    pin: tuple[object, str] | None = None,
) -> Resolution:
    """pin 是 (host 內名稱, 來源標籤)，例如 ("haiku", "[roles.scout].model")。"""
    tier_pins = binding.get("tiers", {})
    if pin is None and tier in tier_pins:
        pin = (tier_pins[tier], f"[tiers].{tier}")
    if pin is not None:
        if security:
            _reject_flagged_pin(core, binding, pin)
        return Resolution(pin[0], "pin", pin[1])
    if binding.get("selection") == "inherit":
        return Resolution("inherit", "inherit", 'selection = "inherit"')
    cands = candidates_for(core, binding, tier, security)
    eligible = [c for c in cands if c.excluded is None]
    if not eligible:
        raise ResolveError(
            f"tier {tier}{'（security）' if security else ''} 沒有任何可用模型滿足規則"
        )
    chosen = _pick(core, tier, eligible)
    return Resolution(chosen.host_name, "rule", chosen.key, tuple(cands))
