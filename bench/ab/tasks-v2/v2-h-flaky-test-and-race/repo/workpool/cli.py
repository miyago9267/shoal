"""Demo: ``python3 -m workpool.cli 1000 --workers 8`` squares numbers."""
import argparse
import sys

from .batch import map_unordered


def main(argv=None):
    parser = argparse.ArgumentParser(prog="workpool")
    parser.add_argument("count", type=int)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    results, errors = map_unordered(lambda n: n * n, range(args.count), args.workers)
    print(f"{len(results)} results, {len(errors)} errors, sum={sum(results.values())}")
    return 0 if len(results) == args.count and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
