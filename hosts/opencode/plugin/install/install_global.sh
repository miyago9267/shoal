#!/bin/sh
# 把 shoal 的 OpenCode role、plugin 與控制檔安裝到全域 config dir。
# 由 install.sh --global 呼叫（docs/specs/opencode-global，R2-R5）。
#
# 寫入 <config-dir>：agents/*.md、plugins/pilotfish-opencode.js、pilotfish/{catalog,routing}.json
# manifest 與備份放在 <state-dir>（不進 config dir，避免落入 dotfile 追蹤目錄）：
#   ${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global

set -eu

usage() {
  printf '%s\n' "usage: install.sh --global [--config-dir DIRECTORY] (--enable|--disable|--rollback)" >&2
  exit 2
}

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

warn() {
  printf '%s\n' "warning: $*" >&2
}

script_dir=$(CDPATH=; cd -P -- "$(dirname -- "$0")" && pwd)
config_arg=
action=
global_seen=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --global)
      global_seen=1
      shift
      ;;
    --config-dir)
      [ "$#" -ge 2 ] || usage
      config_arg=$2
      shift 2
      ;;
    --enable|--disable|--rollback)
      [ -z "$action" ] || usage
      action=${1#--}
      shift
      ;;
    *)
      usage
      ;;
  esac
done

[ "$global_seen" = "1" ] || usage
[ -n "$action" ] || usage

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global"
manifest="$state_dir/install.manifest"

# 與 plugin 的全域層一致：--config-dir，其次 OPENCODE_CONFIG_DIR，最後 ~/.config/opencode。
if [ -n "$config_arg" ]; then
  config_input=$config_arg
elif [ -n "${OPENCODE_CONFIG_DIR:-}" ]; then
  config_input=$OPENCODE_CONFIG_DIR
else
  config_input="$HOME/.config/opencode"
fi

hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{ print $1 }'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    die "shasum or sha256sum is required to protect modified files"
  fi
}

# manifest 內的相對路徑只允許 config dir 底下的普通相對路徑。
check_relative() {
  case "$1" in
    ""|/*|..|../*|*/..|*/../*) die "invalid path in manifest: $1" ;;
  esac
}

manifest_value() {
  awk -F'|' -v key="$1" '$1 == key { print $2; exit }' "$manifest"
}

# 停用與還原：沿用 --target 的語意，並先驗證所有檔案再動手，任何一個被改過就整批不動。
verify_manifest_files() {
  verb=$1
  while IFS='|' read -r kind present expected_hash relative_path; do
    [ "$kind" = "entry" ] || continue
    check_relative "$relative_path"
    installed_path="$config_dir/$relative_path"
    if [ -e "$installed_path" ]; then
      actual_hash=$(hash_file "$installed_path")
      [ "$actual_hash" = "$expected_hash" ] || \
        die "cannot $verb: file changed after installation: $relative_path"
    fi
    if [ "$verb" = "rollback" ] && [ "$present" = "1" ] && [ ! -f "$backup_dir/$relative_path" ]; then
      die "cannot rollback: backup file is missing: $relative_path"
    fi
  done < "$manifest"
}

# 只移除安裝時由 installer 建立、且現在已空的目錄。
remove_created_dirs() {
  while IFS='|' read -r kind relative_path _; do
    [ "$kind" = "mkdir" ] || continue
    check_relative "$relative_path"
    rmdir -- "$config_dir/$relative_path" 2>/dev/null || true
  done < "$manifest"
}

set_state() {
  state_file=$(mktemp "${manifest}.XXXXXX")
  awk -F'|' -v new_state="$1" 'BEGIN { OFS = "|" } $1 == "state" { $2 = new_state } { print }' "$manifest" > "$state_file"
  mv -- "$state_file" "$manifest"
}

# disable 與 rollback 以 manifest 記錄的 config dir 為準；明確指定且不同就拒絕。
resolve_recorded_config() {
  recorded=$(manifest_value config)
  [ -n "$recorded" ] || die "invalid install manifest: config directory is missing"
  if [ -n "$config_arg" ]; then
    [ -d "$config_arg" ] || die "config directory does not exist: $config_arg"
    requested=$(CDPATH=; cd -P -- "$config_arg" && pwd)
    [ "$requested" = "$recorded" ] || \
      die "manifest was installed into $recorded, not $requested"
  fi
  config_dir=$recorded
}

if [ "$action" = "disable" ]; then
  if [ ! -f "$manifest" ]; then
    printf '%s\n' "pilotfish-opencode is disabled: no install manifest"
    exit 0
  fi
  resolve_recorded_config
  verify_manifest_files disable
  while IFS='|' read -r kind present _ relative_path; do
    [ "$kind" = "entry" ] || continue
    if [ "$present" = "0" ] && [ -e "$config_dir/$relative_path" ]; then
      rm -f -- "$config_dir/$relative_path"
    fi
  done < "$manifest"
  remove_created_dirs
  set_state disabled
  printf '%s\n' "pilotfish-opencode disabled; rollback backup kept at $state_dir/$(manifest_value backup)"
  exit 0
fi

if [ "$action" = "rollback" ]; then
  [ -f "$manifest" ] || die "cannot rollback: no install manifest"
  resolve_recorded_config
  backup_relative=$(manifest_value backup)
  check_relative "$backup_relative"
  backup_dir="$state_dir/$backup_relative"
  [ -d "$backup_dir" ] || die "cannot rollback: backup directory is missing"
  verify_manifest_files rollback
  while IFS='|' read -r kind present _ relative_path; do
    [ "$kind" = "entry" ] || continue
    installed_path="$config_dir/$relative_path"
    if [ "$present" = "1" ]; then
      mkdir -p -- "$(dirname -- "$installed_path")"
      cp -- "$backup_dir/$relative_path" "$installed_path"
    elif [ -e "$installed_path" ]; then
      rm -f -- "$installed_path"
    fi
  done < "$manifest"
  remove_created_dirs
  set_state rolled_back
  printf '%s\n' "pilotfish-opencode rollback restored"
  exit 0
fi

# ---- enable ----

[ -d "$config_input" ] || die "config directory does not exist: $config_input"
config_dir=$(CDPATH=; cd -P -- "$config_input" && pwd)

if [ -f "$manifest" ]; then
  state=$(manifest_value state)
  if [ "$state" = "enabled" ]; then
    printf '%s\n' "pilotfish-opencode already enabled; use --disable before reinstalling"
    exit 0
  fi
fi

command -v bun >/dev/null 2>&1 || die "bun is required to build the OpenCode plugin"
command -v git >/dev/null 2>&1 || die "git is required to read the committed dist"

repo_top=$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null) || \
  die "shoal repository not found (install.sh --global must run from a shoal checkout)"

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/pilotfish-opencode-global.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT HUP INT TERM

# R4：只取 committed HEAD 的 hosts/opencode，不吃未 commit 的 WIP，也不在 repo 內留下 node_modules / dist。
git -C "$repo_top" archive HEAD hosts/opencode | tar -x -C "$work_dir" || \
  die "cannot read hosts/opencode at HEAD of $repo_top"
src_root="$work_dir/hosts/opencode"
[ -d "$src_root/dist/roles" ] || die "hosts/opencode/dist/roles is missing at HEAD"

# plugin 打成單一 bundle（與 --target 相同的 bun build 參數），讓 plugins/ 底下的 js 可獨立載入。
(
  CDPATH=
  cd -P -- "$src_root/plugin"
  bun install --frozen-lockfile >/dev/null
  bun build src/plugin/pilotfish-opencode.ts --bundle --format esm --target bun \
    --outfile "$work_dir/pilotfish-opencode.js" >/dev/null
) || die "failed to build the OpenCode plugin from HEAD"
[ -s "$work_dir/pilotfish-opencode.js" ] || die "plugin build produced no output"

# 安裝計畫：每行 "<相對 config dir 的路徑>|<來源檔>"。
plan="$work_dir/plan"
: > "$plan"
for role_file in "$src_root"/dist/roles/*.md; do
  [ -f "$role_file" ] || continue
  printf 'agents/%s|%s\n' "$(basename -- "$role_file")" "$role_file" >> "$plan"
done
printf '%s\n' "plugins/pilotfish-opencode.js|$work_dir/pilotfish-opencode.js" >> "$plan"
printf '%s\n' "pilotfish/catalog.json|$src_root/dist/catalog.json" >> "$plan"
printf '%s\n' "pilotfish/routing.json|$src_root/dist/routing.json" >> "$plan"
[ -f "$src_root/dist/catalog.json" ] && [ -f "$src_root/dist/routing.json" ] || \
  die "hosts/opencode/dist/catalog.json or routing.json is missing at HEAD"

# R3：先找出所有衝突再決定要不要寫；有任何衝突就中止，且完全不寫入。
# 已存在的檔案只有兩種可以覆蓋：內容與來源相同，或 manifest 記錄過且 hash 仍相符（先前由本 installer 安裝）。
manifest_hash_for() {
  [ -f "$manifest" ] || return 0
  awk -F'|' -v path="$1" '$1 == "entry" && $4 == path { print $3; exit }' "$manifest"
}

conflicts="$work_dir/conflicts"
: > "$conflicts"
while IFS='|' read -r relative_path source_path; do
  installed_path="$config_dir/$relative_path"
  { [ -e "$installed_path" ] || [ -L "$installed_path" ]; } || continue
  if [ -f "$installed_path" ] && cmp -s "$source_path" "$installed_path"; then
    continue
  fi
  if [ -f "$installed_path" ]; then
    recorded_hash=$(manifest_hash_for "$relative_path")
    if [ -n "$recorded_hash" ] && [ "$recorded_hash" = "$(hash_file "$installed_path")" ]; then
      continue
    fi
  fi
  printf '  %s\n' "$installed_path" >> "$conflicts"
done < "$plan"

if [ -s "$conflicts" ]; then
  {
    printf '%s\n' "refusing to overwrite files that were not installed by shoal; nothing was written:"
    cat "$conflicts"
    printf '%s\n' "move or remove them (or merge by hand), then run --enable again"
  } >&2
  exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)
backup_relative="backups/$stamp"
backup_dir="$state_dir/$backup_relative"
# 同一秒內重跑不能共用備份目錄。
suffix=1
while [ -e "$backup_dir" ]; do
  backup_relative="backups/$stamp-$suffix"
  backup_dir="$state_dir/$backup_relative"
  suffix=$((suffix + 1))
done
mkdir -p -- "$backup_dir"

{
  printf '%s\n' 'version|1'
  printf '%s\n' 'state|enabled'
  printf 'config|%s\n' "$config_dir"
  printf 'backup|%s|\n' "$backup_relative"
} > "$manifest"

for created in agents plugins pilotfish; do
  if [ ! -d "$config_dir/$created" ]; then
    mkdir -p -- "$config_dir/$created"
    printf 'mkdir|%s\n' "$created" >> "$manifest"
  fi
done

while IFS='|' read -r relative_path source_path; do
  installed_path="$config_dir/$relative_path"
  if [ -e "$installed_path" ]; then
    mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
    cp -- "$installed_path" "$backup_dir/$relative_path"
    printf 'entry|1|%s|%s\n' "$(hash_file "$installed_path")" "$relative_path" >> "$manifest"
  else
    printf 'entry|0|%s|%s\n' "$(hash_file "$source_path")" "$relative_path" >> "$manifest"
  fi
  cp -- "$source_path" "$installed_path.shoal-tmp"
  mv -- "$installed_path.shoal-tmp" "$installed_path"
done < "$plan"

printf '%s\n' "pilotfish-opencode enabled globally in $config_dir (state: $state_dir)"

# R5：routing.json 的候選 provider 必須在 opencode.json 宣告（只比 key 名稱，不讀也不印任何值）。
check_providers() {
  opencode_json="$config_dir/opencode.json"
  if [ ! -f "$opencode_json" ]; then
    warn "$opencode_json not found; provider check skipped"
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found; provider check skipped"
    return 0
  fi
  python3 - "$opencode_json" "$config_dir/pilotfish/routing.json" <<'PY' >&2 || true
import json
import sys

config_path, routing_path = sys.argv[1], sys.argv[2]
try:
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
except (OSError, ValueError):
    print("warning: cannot parse opencode.json as JSON (JSONC?); provider check skipped")
    raise SystemExit(0)
with open(routing_path, encoding="utf-8") as handle:
    routing = json.load(handle)

declared = set()
providers = config.get("provider") if isinstance(config, dict) else None
if isinstance(providers, dict):
    declared.update(providers.keys())
enabled = config.get("enabled_providers") if isinstance(config, dict) else None
if isinstance(enabled, list):
    declared.update(item for item in enabled if isinstance(item, str))

missing = {}
for role, route in (routing.get("roles") or {}).items():
    for candidate in route.get("candidates") or []:
        provider = candidate.get("provider")
        if provider and provider not in declared:
            missing.setdefault(provider, []).append(role)
for provider, roles in sorted(missing.items()):
    print(
        "warning: routing.json candidate provider '%s' (roles: %s) is not in opencode.json "
        "provider keys or enabled_providers; auth or env based providers cannot be verified here"
        % (provider, ", ".join(sorted(set(roles))))
    )
PY
}

# R2a：專案已有 plugin 時，全域與專案兩份會同時載入；去重靠新版 plugin 的旗標，舊版專案 plugin 不保證。
check_project_plugins() {
  cwd_plugin="$PWD/.opencode/plugins/pilotfish-opencode.js"
  [ -f "$cwd_plugin" ] && \
    warn "project plugin found at $cwd_plugin; it loads alongside the global plugin. Rebuild it from this version (dedup flag) or run: install.sh --target $PWD --disable"
  top=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [ -n "$top" ] && [ "$top" != "$PWD" ] && [ -f "$top/.opencode/plugins/pilotfish-opencode.js" ]; then
    warn "project plugin found at $top/.opencode/plugins/pilotfish-opencode.js; it loads alongside the global plugin. Rebuild it from this version (dedup flag) or run: install.sh --target $top --disable"
  fi
  return 0
}

check_providers
check_project_plugins
