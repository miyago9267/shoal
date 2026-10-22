"""Command line interface: ``python3 -m shelf --db FILE COMMAND ...``."""
import argparse
import sys

from . import formatting, storage
from .errors import ShelfError
from .model import Book


def build_parser():
    parser = argparse.ArgumentParser(prog="shelf", description=__doc__)
    parser.add_argument("--db", default="library.json", help="library file")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="add a book")
    add.add_argument("title")
    add.add_argument("--author", required=True)
    add.add_argument("--year", type=int)

    lst = sub.add_parser("list", help="list books")
    lst.add_argument("--author", help="filter by author substring")
    lst.add_argument("--year", type=int, help="only books from this year")

    show = sub.add_parser("show", help="show one book")
    show.add_argument("id", type=int)

    rm = sub.add_parser("remove", help="remove a book")
    rm.add_argument("id", type=int)

    find = sub.add_parser("search", help="search titles and authors")
    find.add_argument("text")
    return parser


def cmd_add(lib, args):
    book = lib.add(Book(id=0, title=args.title, author=args.author, year=args.year))
    print(f"added #{book.id}: {book.title}")
    return True


def cmd_list(lib, args):
    books = lib.by_author(args.author) if args.author else lib.all()
    if args.year is not None:
        books = [book for book in books if book.year == args.year]
    print(formatting.table(books))
    return False


def cmd_show(lib, args):
    print(formatting.detail(lib.get(args.id)))
    return False


def cmd_remove(lib, args):
    book = lib.remove(args.id)
    print(f"removed #{book.id}: {book.title}")
    return True


def cmd_search(lib, args):
    print(formatting.table(lib.search(args.text)))
    return False


COMMANDS = {"add": cmd_add, "list": cmd_list, "show": cmd_show,
            "remove": cmd_remove, "search": cmd_search}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        lib = storage.load(args.db)
        changed = COMMANDS[args.command](lib, args)
        if changed:
            storage.save(lib, args.db)
    except ShelfError as exc:
        print(f"shelf: {exc}", file=sys.stderr)
        return 1
    return 0
