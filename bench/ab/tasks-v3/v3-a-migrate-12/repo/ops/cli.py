"""Tiny command line front end: python3 -m ops.cli <command> ..."""
import sys

from . import billing, config, importer, inventory, util


def cmd_money(args):
    return billing.format_money(int(args[0]))


def cmd_low(args):
    stock = {}
    for pair in args:
        sku, qty = pair.split("=")
        stock[sku] = int(qty)
    return ",".join(inventory.low_items(stock))


def cmd_import(args):
    rows = importer.parse_rows(importer.split_lines(sys.stdin.read()))
    return "%.2f" % importer.total_value(rows)


def cmd_duration(args):
    return util.human_duration(int(args[0]))


def cmd_config(args):
    return str(config.get(args[0], args[1]))


COMMANDS = {
    "money": cmd_money,
    "low": cmd_low,
    "import": cmd_import,
    "duration": cmd_duration,
    "config": cmd_config,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print("usage: ops.cli {%s} ..." % "|".join(sorted(COMMANDS)), file=sys.stderr)
        return 2
    print(COMMANDS[argv[0]](argv[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
