#!/bin/sh
# SessionStart hook of the shoal Claude plugin: inject the policy bootstrap as session context.
# Source of this file: hosts/claude/plugin-src/emit-sessionstart.sh (copied by tools/render.py).
set -eu
PATH=/usr/bin:/bin
export PATH

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
policy="$here/../policy/claude-md.bootstrap.md"

# Effective Claude config directory (CLAUDE_CONFIG_DIR when absolute, else ~/.claude).
case "${CLAUDE_CONFIG_DIR:-}" in
    /*) config_root=$CLAUDE_CONFIG_DIR ;;
    *) config_root="${HOME:-}/.claude" ;;
esac

# Data directory of the global install (tools/install_hooks.py).
case "${XDG_DATA_HOME:-}" in
    /*) data_home=$XDG_DATA_HOME ;;
    *) data_home="${HOME:-}/.local/share" ;;
esac
global_guard="$data_home/shoal/guard/shoal_guard.py"
settings="$config_root/settings.json"
claude_md="$config_root/CLAUDE.md"

# Advisory only: the guard in hooks.json makes the same decision on its own and never runs twice.
if [ -f "$global_guard" ] && [ -f "$settings" ] &&
    grep -F -q 'shoal/guard/shoal_guard.py' "$settings" 2>/dev/null; then
    printf '%s\n' "shoal plugin note: a global shoal guard from install_hooks.py is registered in settings.json; the plugin copy of the guard defers to it, so every event is judged once."
fi

if [ -f "$claude_md" ] && grep -F -q '<!-- shoal-claude v' "$claude_md" 2>/dev/null; then
    printf '%s\n' "shoal plugin note: the global CLAUDE.md already carries the shoal bootstrap; the plugin does not inject it again."
    exit 0
fi

cat -- "$policy"
