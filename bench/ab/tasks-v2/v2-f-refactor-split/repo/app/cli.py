"""``python3 -m app.cli order.json`` prints an invoice."""
import json
import sys

from app.core import ShopError, order_from_dict, render_invoice


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 -m app.cli ORDER.json", file=sys.stderr)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as fh:
            order = order_from_dict(json.load(fh))
        print(render_invoice(order))
    except (OSError, ValueError, ShopError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
