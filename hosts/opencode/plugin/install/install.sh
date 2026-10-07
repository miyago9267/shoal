#!/bin/sh

set -eu

usage() {
  printf '%s\n' "usage: $0 --target DIRECTORY (--enable|--disable|--rollback)" >&2
  printf '%s\n' "       $0 --global [--config-dir DIRECTORY] (--enable|--disable|--rollback)" >&2
  exit 2
}

# --global 另有一份安裝腳本（全域 config dir，docs/specs/opencode-global）；
# 下面的 --target 流程完全不動。
for arg in "$@"; do
  if [ "$arg" = "--global" ]; then
    exec sh "$(dirname -- "$0")/install_global.sh" "$@"
  fi
done

repo_root=$(CDPATH=; cd -P -- "$(dirname -- "$0")/.." && pwd)
# role md 由 render 產生，放在 hosts/opencode/dist/roles（plugin/ 的上一層）。
roles_dir="$repo_root/../dist/roles"
target_arg=
action=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      [ "$#" -ge 2 ] || usage
      target_arg=$2
      shift 2
      ;;
    --enable|--disable|--rollback)
      [ -z "$action" ] || usage
      action=${1#--}
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage
      ;;
  esac
done

[ -n "$target_arg" ] || usage
[ -n "$action" ] || usage
[ -d "$target_arg" ] || {
  printf '%s\n' "target directory does not exist: $target_arg" >&2
  exit 1
}

target=$(CDPATH=; cd -P -- "$target_arg" && pwd)
control_dir="$target/.opencode/shoal"
manifest="$control_dir/install.manifest"
plugin_target="$target/.opencode/plugins/shoal-opencode.js"

# 停用：只移除 manifest 記錄、且內容沒被改過的檔案（要照 $manifest 與 $control_dir 執行）。
disable_install() {
  if [ ! -f "$manifest" ]; then
    printf '%s\n' "shoal-opencode is disabled: no install manifest"
    return 0
  fi

  command -v shasum >/dev/null 2>&1 || {
    printf '%s\n' "shasum is required to protect modified files" >&2
    return 1
  }
  while IFS='|' read -r kind present expected_hash relative_path; do
    [ "$kind" = "entry" ] || continue
    installed_path="$target/$relative_path"
    if [ -e "$installed_path" ]; then
      actual_hash=$(shasum -a 256 "$installed_path" | awk '{ print $1 }')
      [ "$actual_hash" = "$expected_hash" ] || {
        printf '%s\n' "cannot disable: file changed after installation: $relative_path" >&2
        return 1
      }
    fi
    if [ "$present" = "0" ] && [ -e "$installed_path" ]; then
      rm -f -- "$installed_path"
    fi
  done < "$manifest"
  state_file=$(mktemp "${manifest}.XXXXXX")
  awk -F'|' 'BEGIN { OFS = "|" } $1 == "state" { $2 = "disabled" } { print }' "$manifest" > "$state_file"
  mv -- "$state_file" "$manifest"
  printf '%s\n' "shoal-opencode disabled; rollback backup kept at $control_dir/backups"
  return 0
}

# ---- LEGACY_: 2.0.0 之前的 control 目錄名（docs/specs/shoal-rebrand N5） ----
LEGACY_CONTROL_NAME=pilotfish

# 舊名安裝的 manifest 先照它自己的記錄停用，再以新名安裝或停用；舊 manifest 的檔案被改過就整批不動。
legacy_manifest="$target/.opencode/$LEGACY_CONTROL_NAME/install.manifest"
if [ -f "$legacy_manifest" ] && [ "$action" != "rollback" ]; then
  legacy_state=$(awk -F'|' '$1 == "state" { print $2; exit }' "$legacy_manifest")
  if [ "$legacy_state" = "enabled" ]; then
    printf '%s\n' "found a pre-2.0.0 install manifest; disabling it before continuing" >&2
    (manifest=$legacy_manifest; control_dir=$target/.opencode/$LEGACY_CONTROL_NAME; disable_install)
  fi
fi

if [ "$action" = "disable" ]; then
  disable_install
  exit 0
fi

if [ "$action" = "rollback" ]; then
  if [ ! -f "$manifest" ]; then
    printf '%s\n' "cannot rollback: no install manifest" >&2
    exit 1
  fi

  backup_dir=
  while IFS='|' read -r kind value _; do
    [ "$kind" = "backup" ] || continue
    backup_dir="$target/$value"
  done < "$manifest"
  [ -n "$backup_dir" ] && [ -d "$backup_dir" ] || {
    printf '%s\n' "cannot rollback: backup directory is missing" >&2
    exit 1
  }

  command -v shasum >/dev/null 2>&1 || {
    printf '%s\n' "shasum is required to protect modified files" >&2
    exit 1
  }
  while IFS='|' read -r kind present expected_hash relative_path; do
    [ "$kind" = "entry" ] || continue
    installed_path="$target/$relative_path"
    if [ -e "$installed_path" ]; then
      actual_hash=$(shasum -a 256 "$installed_path" | awk '{ print $1 }')
      [ "$actual_hash" = "$expected_hash" ] || {
        printf '%s\n' "cannot rollback: file changed after installation: $relative_path" >&2
        exit 1
      }
    fi
    if [ "$present" = "1" ]; then
      [ -f "$backup_dir/$relative_path" ] || {
        printf '%s\n' "cannot rollback: backup file is missing: $relative_path" >&2
        exit 1
      }
      mkdir -p -- "$(dirname -- "$installed_path")"
      cp -- "$backup_dir/$relative_path" "$installed_path"
    else
      if [ -e "$installed_path" ]; then
        rm -f -- "$installed_path"
      fi
    fi
  done < "$manifest"
  state_file=$(mktemp "${manifest}.XXXXXX")
  awk -F'|' 'BEGIN { OFS = "|" } $1 == "state" { $2 = "rolled_back" } { print }' "$manifest" > "$state_file"
  mv -- "$state_file" "$manifest"
  printf '%s\n' "shoal-opencode rollback restored"
  exit 0
fi

if [ -f "$manifest" ]; then
  state=$(awk -F'|' '$1 == "state" { print $2; exit }' "$manifest")
  if [ "$state" = "enabled" ]; then
    printf '%s\n' "shoal-opencode already enabled; use --disable before reinstalling"
    exit 0
  fi
fi

command -v bun >/dev/null 2>&1 || {
  printf '%s\n' "bun is required to build the OpenCode plugin" >&2
  exit 1
}

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/shoal-opencode.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM

(CDPATH=; cd -P -- "$repo_root" && bun run build >/dev/null)
(CDPATH=; cd -P -- "$repo_root" && bun build src/plugin/shoal-opencode.ts --bundle --format esm --target bun --outfile "$build_dir/shoal-opencode.js" >/dev/null)

install_files="$target/.opencode/agents/scout.md
$target/.opencode/agents/executor.md
$target/.opencode/agents/verifier.md
$target/.opencode/agents/security-reviewer.md
$target/.opencode/agents/security-executor.md
$plugin_target"

while IFS= read -r installed_path; do
  [ -n "$installed_path" ] || continue
  case "$installed_path" in
    "$plugin_target") source_path="$build_dir/shoal-opencode.js" ;;
    *) source_path="$roles_dir/$(basename -- "$installed_path")" ;;
  esac
  if [ -e "$installed_path" ] && ! cmp -s "$source_path" "$installed_path"; then
    printf '%s\n' "refusing to overwrite existing file: $installed_path" >&2
    exit 1
  fi
done <<EOF
$install_files
EOF

stamp=$(date +%Y%m%d-%H%M%S)
backup_relative=".opencode/shoal/backups/$stamp"
backup_dir="$target/$backup_relative"
mkdir -p -- "$backup_dir" "$target/.opencode/agents" "$target/.opencode/plugins"

{
  printf '%s\n' 'version|1'
  printf '%s\n' 'state|enabled'
  printf 'backup|%s|\n' "$backup_relative"
} > "$manifest"

while IFS= read -r installed_path; do
  [ -n "$installed_path" ] || continue
  case "$installed_path" in
    "$target"/*) relative_path=${installed_path#"$target/"} ;;
    *) printf '%s\n' "invalid install path" >&2; exit 1 ;;
  esac
  case "$installed_path" in
    "$plugin_target") source_path="$build_dir/shoal-opencode.js" ;;
    *) source_path="$roles_dir/$(basename -- "$installed_path")" ;;
  esac
  if [ -e "$installed_path" ]; then
    mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
    cp -- "$installed_path" "$backup_dir/$relative_path"
    expected_hash=$(shasum -a 256 "$installed_path" | awk '{ print $1 }')
    printf 'entry|1|%s|%s\n' "$expected_hash" "$relative_path" >> "$manifest"
  else
    expected_hash=$(shasum -a 256 "$source_path" | awk '{ print $1 }')
    printf 'entry|0|%s|%s\n' "$expected_hash" "$relative_path" >> "$manifest"
  fi
  cp -- "$source_path" "$installed_path"
done <<EOF
$install_files
EOF

printf '%s\n' "shoal-opencode enabled in $target"
