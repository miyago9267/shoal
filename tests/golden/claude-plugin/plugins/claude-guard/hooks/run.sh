#!/bin/sh
# Hook launcher: run.sh <guard.py> [args...].  Uses the interpreter shoal_update recorded (skips a slow pyenv
# shim), else python3; imports the guard so its bytecode is cached (-I: no cwd on sys.path).
py= f="${XDG_DATA_HOME:-$HOME/.local/share}/shoal/python"
[ -r "$f" ] && read -r py < "$f"
[ -n "$py" ] && [ -x "$py" ] || py=python3
exec "$py" -I -c 'import os, sys
c = os.environ.get("XDG_CACHE_HOME", "")
sys.pycache_prefix = os.path.join(c if os.path.isabs(c) else os.path.expanduser("~/.cache"), "shoal", "pycache")
d, n = os.path.split(sys.argv[1])
sys.path.insert(0, d)
raise SystemExit(__import__(n[:-3]).main(sys.argv[2:]))' "$@"
