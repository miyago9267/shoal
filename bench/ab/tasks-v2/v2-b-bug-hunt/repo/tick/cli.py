"""Command line interface: ``python3 -m tick [--db FILE] [--tz OFFSET] COMMAND``."""
import argparse
import os
import sys

from . import dates, export, filters, ordering, render
from .model import Task, TickError, parse_priority
from .store import Store


def build_parser():
    parser = argparse.ArgumentParser(prog="tick")
    parser.add_argument("--db", default="tick.json")
    parser.add_argument("--tz", default=os.environ.get("TICK_TZ", "+00:00"),
                        help="your UTC offset, e.g. +08:00")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("title")
    add.add_argument("--priority", default="medium")
    add.add_argument("--due", help="YYYY-MM-DD")
    add.add_argument("--tag", action="append", default=[])

    lst = sub.add_parser("list")
    lst.add_argument("--all", action="store_true", help="include finished tasks")
    lst.add_argument("--sort", choices=sorted(ordering.SORTS), default="priority")
    lst.add_argument("--tag")

    done = sub.add_parser("done")
    done.add_argument("id", type=int)

    due = sub.add_parser("due")
    due.add_argument("--days", type=int, default=0)

    exp = sub.add_parser("export")
    exp.add_argument("--out", help="write to this file instead of stdout")
    exp.add_argument("--all", action="store_true")
    return parser


def run(args, store, tz):
    if args.command == "add":
        task = Task(id=0, title=args.title, priority=parse_priority(args.priority),
                    due=dates.parse_due(args.due, tz) if args.due else None,
                    tags=args.tag)
        store.add(task)
        store.save()
        print(f"added #{task.id}")
    elif args.command == "list":
        tasks = store.tasks if args.all else filters.open_tasks(store.tasks)
        if args.tag:
            tasks = filters.with_tag(tasks, args.tag)
        print(render.listing(ordering.sort_tasks(tasks, args.sort), tz))
    elif args.command == "done":
        store.get(args.id).done = True
        store.save()
        print(f"done #{args.id}")
    elif args.command == "due":
        tasks = filters.due_within(store.tasks, args.days, tz)
        print(render.listing(ordering.sort_tasks(tasks, "due"), tz))
    elif args.command == "export":
        tasks = store.tasks if args.all else filters.open_tasks(store.tasks)
        text = export.to_csv(ordering.by_id(tasks), tz)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        tz = dates.parse_tz(args.tz)
        run(args, Store(args.db), tz)
    except (TickError, ValueError) as exc:
        print(f"tick: {exc}", file=sys.stderr)
        return 1
    return 0
