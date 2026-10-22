"""Command line interface: ``python3 -m notes --db FILE <command>``."""
import argparse
import sys

from .app import build_service
from .service import DEFAULT_LIMIT, NotFound


def build_parser():
    parser = argparse.ArgumentParser(prog="notes")
    parser.add_argument("--db", default="notes.sqlite", help="SQLite file")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="create a note")
    add.add_argument("title")
    add.add_argument("--body", default="")
    add.add_argument("--tag", action="append", default=[])

    ls = sub.add_parser("list", help="list notes, newest first")
    ls.add_argument("--tag")
    ls.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ls.add_argument("--offset", type=int, default=0)

    show = sub.add_parser("show", help="print one note")
    show.add_argument("id", type=int)

    rm = sub.add_parser("rm", help="delete a note")
    rm.add_argument("id", type=int)
    return parser


def format_line(note):
    tags = f"  [{', '.join(note.tags)}]" if note.tags else ""
    return f"{note.id:>5}  {note.title}{tags}"


def main(argv=None, out=None):
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    service = build_service(args.db)
    try:
        if args.command == "add":
            note = service.create_note(args.title, args.body, args.tag)
            print(f"created {note.id}", file=out)
        elif args.command == "list":
            notes, total = service.list_notes(tag=args.tag, limit=args.limit,
                                              offset=args.offset)
            for note in notes:
                print(format_line(note), file=out)
            print(f"({len(notes)} of {total})", file=out)
        elif args.command == "show":
            note = service.get_note(args.id)
            print(format_line(note), file=out)
            print(note.body, file=out)
        elif args.command == "rm":
            service.delete_note(args.id)
            print(f"deleted {args.id}", file=out)
    except NotFound:
        print("error: no such note", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
