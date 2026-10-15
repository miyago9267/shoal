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
    """Numeric key of the `<version>` directory in `.../<version>/hooks/<NAME>`, or None."""
    ver = os.path.basename(os.path.dirname(os.path.dirname(path)))
    parts = ver.split(".")
    if all(p.isdigit() for p in parts):
        return [int(p) for p in parts]
    return None


def _config_dir():
    """Where Claude Code keeps its plugin cache: CLAUDE_CONFIG_DIR, else ~/.claude."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    if configured and os.path.isabs(configured):
        return configured
    return os.path.join(os.path.expanduser("~"), ".claude")


def _newest(pattern):
    keyed = [(_version_key(p), p) for p in glob.glob(pattern)]
    return [p for k, p in sorted((i for i in keyed if i[0] is not None), reverse=True)]


def find_guard(here):
    plugin_root = os.path.dirname(os.path.dirname(here))
    marketplace = os.path.dirname(plugin_root)
    found = [os.path.join(marketplace, "claude-guard-plugin", "hooks", NAME)]
    cache = os.path.join(os.path.dirname(marketplace), "shoal-dispatch-guard", "*", "hooks", NAME)
    home = os.path.join(_config_dir(), "plugins", "cache", "*", "shoal-dispatch-guard", "*", "hooks", NAME)
    for pattern in (cache, home):
        found += _newest(pattern)
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
