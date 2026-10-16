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


LEGACY_BETA_MAX = (3, 11, 1)  # same rule as install/shoal_version.py; this file must stay self-contained


def _version_key(path):
    """Key of the `<version>` directory in `.../<version>/hooks/<NAME>`, or None.

    Channel first (beta < stable), then the numbers: `X.Y.Z-beta` and bare legacy
    versions up to LEGACY_BETA_MAX are beta, any other bare version is stable.
    """
    ver = os.path.basename(os.path.dirname(os.path.dirname(path)))
    base, sep, suffix = ver.partition("-")
    parts = base.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or (sep and suffix != "beta"):
        return None
    nums = tuple(int(p) for p in parts)
    stable = not sep and nums > LEGACY_BETA_MAX
    return (1 if stable else 0,) + nums


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
    # 3.11.0 moved the plugins to plugins/claude{,-guard}; keep the pre-3.11 sibling name for one release.
    found = [os.path.join(marketplace, d, "hooks", NAME) for d in ("claude-guard", "claude-guard-plugin")]
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
