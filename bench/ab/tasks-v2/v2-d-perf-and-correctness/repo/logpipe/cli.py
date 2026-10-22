"""``python3 -m logpipe LOG USERS [--json]``."""
import argparse
import sys

from . import report
from .pipeline import run_files


def main(argv=None):
    parser = argparse.ArgumentParser(prog="logpipe")
    parser.add_argument("log")
    parser.add_argument("users")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_files(args.log, args.users)
    except (OSError, ValueError) as exc:
        print(f"logpipe: {exc}", file=sys.stderr)
        return 1
    print(report.to_json(result) if args.json else report.to_text(result))
    return 0
