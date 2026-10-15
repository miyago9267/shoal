#!/usr/bin/env python3
"""shoal 3.8.1 compatibility shim; not registered in any hooks.json.

3.8.0 moved every guard hook out of the base plugin into `shoal-dispatch-guard`.
A Claude Code session that was already running kept the old hook config, which
still points at `${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py` of the base plugin;
without this file every tool call in that session failed ("can't open file").

The shim hands the same argv and stdin to the guard plugin's script when it can
find one, and otherwise exits 0 with no output.  It never blocks on its own.
"""
import glob
import os
import subprocess
import sys

NAME = "shoal_guard.py"


def _version_key(path):
    ver = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path))))
    return [int(p) if p.isdigit() else 0 for p in ver.split(".")]


def find_guard(here):
    plugin_root = os.path.dirname(os.path.dirname(here))
    marketplace = os.path.dirname(plugin_root)
    found = [os.path.join(marketplace, "claude-guard-plugin", "hooks", NAME)]
    cache = os.path.join(os.path.dirname(marketplace), "shoal-dispatch-guard", "*", "hooks", NAME)
    home = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache", "*", "shoal-dispatch-guard", "*", "hooks", NAME)
    for pattern in (cache, home):
        found += sorted(glob.glob(pattern), key=_version_key, reverse=True)
    for path in found:
        if os.path.isfile(path) and os.path.realpath(path) != os.path.realpath(here):
            return path
    return None


def main():
    target = find_guard(os.path.abspath(__file__))
    if target is None:
        return 0
    return subprocess.call([sys.executable, target] + sys.argv[1:])


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        code = 0
    sys.exit(code if isinstance(code, int) and code >= 0 else 0)
