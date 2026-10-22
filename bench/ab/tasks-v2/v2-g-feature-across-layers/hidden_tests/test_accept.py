import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from notes.app import build_service
from notes.cli import main
from notes.http import handle

T0 = datetime(2024, 5, 1, 9, 0, tzinfo=timezone.utc)


class ManualClock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def seeded():
    """23 notes; timestamps collide in groups and some ids are backdated."""
    clock = ManualClock()
    svc = build_service(clock=clock)
    for i in range(1, 19):
        clock.now = T0 + timedelta(minutes=10 + i // 4)  # groups of equal timestamps
        svc.create_note(f"n{i}", tags=["even"] if i % 2 == 0 else [])
    for i in range(19, 24):  # imported later, but older than everything above
        svc.create_note(f"n{i}", tags=["even"] if i % 2 == 0 else [],
                        created_at=T0 + timedelta(minutes=i % 3))
    clock.now = T0 + timedelta(hours=2)
    return svc, clock


def expected_order(svc, tag=None):
    notes, nxt = svc.list_notes(tag=tag, limit=100)
    assert nxt is None
    return [n.id for n in notes]


def walk_service(svc, limit, tag=None, between=None):
    seen, cursor, pages = [], None, 0
    while True:
        notes, cursor = svc.list_notes(tag=tag, limit=limit, cursor=cursor)
        seen.extend(n.id for n in notes)
        pages += 1
        if cursor is None:
            return seen
        if between:
            between(pages, notes)
        assert pages < 100, "pagination does not terminate"


class ServiceCursorTest(unittest.TestCase):
    def test_full_walk_matches_unpaged_order(self):
        svc, _ = seeded()
        order = expected_order(svc)
        self.assertEqual(len(order), 23)
        for limit in (1, 4, 5, 7, 22, 23, 50):
            self.assertEqual(walk_service(svc, limit), order, f"limit={limit}")

    def test_next_cursor_none_exactly_at_end(self):
        svc, _ = seeded()
        notes, nxt = svc.list_notes(limit=23)
        self.assertEqual(len(notes), 23)
        self.assertIsNone(nxt)
        notes, nxt = svc.list_notes(limit=22)
        self.assertIsInstance(nxt, str)
        self.assertFalse(nxt.isdigit(), "cursor should be opaque, not a raw id")
        rest, last = svc.list_notes(limit=22, cursor=nxt)
        self.assertEqual(len(rest), 1)
        self.assertIsNone(last)

    def test_stable_when_new_notes_arrive_mid_walk(self):
        svc, clock = seeded()
        order = expected_order(svc)

        def insert(page, notes):
            for k in range(3):
                clock.now += timedelta(seconds=1)
                svc.create_note(f"new{page}.{k}")
            svc.create_note(f"same-ts{page}", created_at=notes[-1].created_at)

        seen = walk_service(svc, 5, between=insert)
        self.assertEqual(len(seen), len(set(seen)), "a note was returned twice")
        self.assertEqual([i for i in seen if i in set(order)], order)

    def test_stable_when_last_seen_note_is_deleted(self):
        svc, _ = seeded()
        order = expected_order(svc)
        deleted = []

        def delete_last(page, notes):
            svc.delete_note(notes[-1].id)
            deleted.append(notes[-1].id)

        seen = walk_service(svc, 4, between=delete_last)
        self.assertEqual(seen, order)
        self.assertTrue(deleted)

    def test_tag_filter_with_cursor(self):
        svc, clock = seeded()
        order = expected_order(svc, tag="even")

        def insert(page, notes):
            clock.now += timedelta(seconds=1)
            svc.create_note(f"tagged{page}", tags=["even"])

        seen = walk_service(svc, 3, tag="even", between=insert)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual([i for i in seen if i in set(order)], order)
        self.assertTrue(all("even" in svc.get_note(i).tags for i in seen))

    def test_invalid_cursor_and_limit(self):
        svc, _ = seeded()
        for bad in ("not a cursor", "!!!!", "eyJ"):
            with self.assertRaises(ValueError, msg=bad):
                svc.list_notes(limit=5, cursor=bad)
        with self.assertRaises(ValueError):
            svc.list_notes(limit=0)
        with self.assertRaises(ValueError):
            svc.list_notes(limit=101)


class HttpCursorTest(unittest.TestCase):
    def test_walk_over_http_with_inserts(self):
        svc, clock = seeded()
        order = expected_order(svc)
        seen, cursor = [], None
        for _ in range(50):
            query = {"limit": "6"}
            if cursor:
                query["cursor"] = cursor
            status, body = handle(svc, "GET", "/notes", query)
            self.assertEqual(status, 200)
            self.assertIn("next_cursor", body)
            seen.extend(item["id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
            clock.now += timedelta(seconds=1)
            handle(svc, "POST", "/notes", body={"title": "live"})
        self.assertIsNone(cursor)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual([i for i in seen if i in set(order)], order)

    def test_bad_cursor_is_400(self):
        svc, _ = seeded()
        status, body = handle(svc, "GET", "/notes", {"limit": "5", "cursor": "garbage!"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_last_page_has_null_cursor(self):
        svc, _ = seeded()
        status, body = handle(svc, "GET", "/notes", {"limit": "30", "tag": "even"})
        self.assertEqual(status, 200)
        self.assertIsNone(body["next_cursor"])
        self.assertEqual(len(body["items"]), 11)


class CliCursorTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.db)

    def run_cli(self, *args):
        out = io.StringIO()
        code = main(["--db", self.db, *args], out=out)
        return code, out.getvalue().splitlines()

    def test_cli_pages_with_cursor(self):
        for i in range(7):
            self.run_cli("add", f"title{i}")
        titles, cursor = [], None
        for _ in range(10):
            args = ["list", "--limit", "3"] + (["--cursor", cursor] if cursor else [])
            code, lines = self.run_cli(*args)
            self.assertEqual(code, 0)
            cursor = None
            for line in lines:
                if line.startswith("next cursor: "):
                    cursor = line[len("next cursor: "):].strip()
                elif "title" in line:
                    titles.append(line.split()[-1])
            if cursor is None:
                break
            self.run_cli("add", "fresh")
        self.assertEqual(titles, [f"title{i}" for i in reversed(range(7))])

    def test_cli_bad_cursor(self):
        self.run_cli("add", "x")
        code, _ = self.run_cli("list", "--cursor", "garbage!")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
