"""Command line entry point: ``python3 -m invsum stock.csv``."""
import argparse
import sys

from .loader import load_rows
from .report import format_table, summarize


def build_parser():
    parser = argparse.ArgumentParser(
        prog="invsum", description="Summarize an inventory CSV by category.")
    parser.add_argument("path", help="CSV file with sku,category,quantity,unit_price")
    parser.add_argument("--sort", choices=["category", "quantity", "value"],
                        default="category", help="column to sort rows by")
    parser.add_argument("--min-quantity", type=int, default=0,
                        help="skip categories with fewer units than this")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        rows = load_rows(args.path)
    except (OSError, ValueError) as exc:
        print(f"invsum: {exc}", file=sys.stderr)
        return 1
    summary = summarize(rows, sort_by=args.sort, min_quantity=args.min_quantity)
    print(format_table(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
