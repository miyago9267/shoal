import unittest

from ops import legacy, log
from ops import (
    authn, backup, billing, cache, exporter, importer, inventory, mailer,
    notifier, reports, scheduler, syncer,
)


class Base(unittest.TestCase):
    def setUp(self):
        self.ev = []
        log.set_sink(lambda name, fields: self.ev.append((name, fields)))
        legacy.clear()

    def tearDown(self):
        log.reset_sink()
        self.assertEqual(legacy.records, [], "legacy_log still called")


class TestBilling(Base):
    def test_rejected(self):
        billing.charge({"id": "a", "balance": 0, "limit": 10}, 0)
        self.assertEqual(self.ev, [("billing.rejected", {"cents": 0, "level": "warn"})])

    def test_declined(self):
        billing.charge({"id": "a", "balance": 0, "limit": 10}, 99)
        self.assertEqual(
            self.ev,
            [("billing.declined", {"account": "a", "cents": 99, "limit": 10, "level": "error"})],
        )

    def test_charged_keeps_int_cents(self):
        billing.charge({"id": "a", "balance": 0, "limit": 5000}, 1250)
        self.assertEqual(self.ev, [("billing.charged", {"account": "a", "cents": 1250, "level": "info"})])

    def test_refunded_uses_capped_amount(self):
        a = {"id": "a", "balance": 100, "limit": 5000}
        billing.refund(a, 500)
        self.assertEqual(self.ev, [("billing.refunded", {"account": "a", "cents": 100, "level": "info"})])


class TestInventory(Base):
    def test_loop_events(self):
        stock = {"a": 1}
        inventory.restock(stock, [("a", 2), ("b", 0), ("c", 20)])
        self.assertEqual(
            self.ev,
            [
                ("inventory.restock", {"sku": "a", "qty": 2, "on_hand": 3, "level": "info"}),
                ("inventory.low", {"sku": "a", "on_hand": 3, "level": "warn"}),
                ("inventory.restock", {"sku": "c", "qty": 20, "on_hand": 20, "level": "info"}),
                ("inventory.restock_done", {"skus": 2, "level": "info"}),
            ],
        )

    def test_done_even_when_empty(self):
        inventory.restock({}, [])
        self.assertEqual(self.ev, [("inventory.restock_done", {"skus": 0, "level": "info"})])


class TestMailer(Base):
    def test_first_attempt_info(self):
        mailer.send(lambda m: None, {"to": "x"})
        self.assertEqual(self.ev, [("mailer.attempt", {"to": "x", "attempt": 1, "level": "info"})])

    def test_retry_levels_and_give_up(self):
        def dead(m):
            raise OSError("down")

        mailer.send(dead, {"to": "x"})
        self.assertEqual(
            self.ev,
            [
                ("mailer.attempt", {"to": "x", "attempt": 1, "level": "info"}),
                ("mailer.attempt", {"to": "x", "attempt": 2, "level": "warn"}),
                ("mailer.attempt", {"to": "x", "attempt": 3, "level": "warn"}),
                ("mailer.gave_up", {"to": "x", "attempts": 3, "level": "error"}),
            ],
        )


class TestScheduler(Base):
    def test_events(self):
        jobs = [
            {"name": "a", "at": 1},
            {"name": "b", "at": 1, "after": ["a"]},
            {"name": "c", "at": 1, "paused": True},
            {"name": "d", "at": 1, "after": ["c"]},
        ]
        scheduler.tick(jobs, 5, lambda j: None)
        self.assertIn(("scheduler.run", {"job": "a", "level": "info"}), self.ev)
        self.assertIn(("scheduler.skip", {"job": "c", "reason": "paused", "level": "debug"}), self.ev)
        names = [(n, f.get("job"), f.get("reason"), f.get("dep")) for n, f in self.ev]
        self.assertIn(("scheduler.run", "a", None, None), names)
        self.assertIn(("scheduler.skip", "c", "paused", None), names)
        self.assertIn(("scheduler.skip", "d", "waiting", "c"), names)
        for n, f in self.ev:
            if n == "scheduler.skip":
                self.assertEqual(f["level"], "debug")


class TestAuthn(Base):
    users = {"ann": "pw"}

    def test_ok(self):
        authn.login("ann", "pw", self.users)
        self.assertEqual(self.ev, [("authn.ok", {"user": "ann", "level": "info"})])

    def test_bad_password(self):
        authn.login("ann", "no", self.users)
        self.assertEqual(self.ev, [("authn.failed", {"user": "ann", "error": "bad password", "level": "error"})])

    def test_unknown_user_error_text(self):
        authn.login("zed", "pw", self.users)
        self.assertEqual(self.ev, [("authn.failed", {"user": "zed", "error": "'zed'", "level": "error"})])

    def test_locked(self):
        authn.login("root", "pw", self.users)
        self.assertEqual(self.ev, [("authn.locked", {"user": "root", "level": "warn"})])


class TestCache(Base):
    def test_quiet_when_not_verbose(self):
        c = cache.Cache(2)
        c.put("a", 1)
        c.get("a")
        c.get("zz")
        self.assertEqual(self.ev, [])

    def test_verbose_hit_miss(self):
        c = cache.Cache(2, verbose=True)
        c.put("a", 1)
        c.get("a")
        c.get("zz")
        self.assertEqual(
            self.ev,
            [
                ("cache.hit", {"key": "a", "level": "debug"}),
                ("cache.miss", {"key": "zz", "level": "debug"}),
            ],
        )

    def test_eviction_is_a_list_and_not_gated(self):
        c = cache.Cache(1)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        self.assertEqual(
            self.ev,
            [
                ("cache.evicted", {"keys": ["a"], "level": "info"}),
                ("cache.evicted", {"keys": ["b"], "level": "info"}),
            ],
        )

    def test_multi_eviction_list(self):
        c = cache.Cache(3)
        for k in "abc":
            c.put(k, 1)
        c.capacity = 1
        c.put("d", 1)
        self.assertEqual(self.ev, [("cache.evicted", {"keys": ["a", "b", "c"], "level": "info"})])


class TestImporter(Base):
    def test_bad_rows_and_done(self):
        importer.parse_rows(["a,1", "b,x,1", "c,2,1.5"])
        self.assertEqual(
            self.ev,
            [
                ("importer.bad_row", {"row": 1, "reason": "expected 3 fields, got 2", "level": "warn"}),
                (
                    "importer.bad_row",
                    {"row": 2, "reason": "invalid literal for int() with base 10: 'x'", "level": "warn"},
                ),
                ("importer.done", {"imported": 1, "total": 3, "level": "info"}),
            ],
        )

    def test_nothing_imported_is_error(self):
        importer.parse_rows(["bad"])
        self.assertEqual(self.ev[-1], ("importer.done", {"imported": 0, "total": 1, "level": "error"}))


class TestExporter(Base):
    def test_events_drop_prefix(self):
        exporter.export_all({"b": "", "a": "hello"}, lambda n, t: 5)
        self.assertEqual(
            self.ev,
            [
                ("exporter.wrote", {"name": "a", "size": 5, "level": "info"}),
                ("exporter.empty", {"name": "b", "level": "warn"}),
            ],
        )


class TestSyncer(Base):
    def test_no_drift_silent(self):
        syncer.reconcile(4, 4, lambda n: n)
        self.assertEqual(self.ev, [])

    def test_levels(self):
        for local, remote, level in [(10, 8, "info"), (10, 4, "warn"), (100, 20, "error"), (10, 5, "info"), (60, 10, "warn")]:
            del self.ev[:]
            syncer.reconcile(local, remote, lambda n: n)
            drift = abs(local - remote)
            self.assertEqual(
                self.ev[0],
                ("syncer.drift", {"local": local, "remote": remote, "drift": drift, "level": level}),
            )
            self.assertEqual(self.ev[1], ("syncer.pushed", {"count": drift, "level": "info"}))


class TestBackup(Base):
    def test_done_and_finally(self):
        backup.run("db", lambda n: 1.26, now=10**6)
        self.assertEqual(
            self.ev,
            [
                ("backup.attempt_finished", {"name": "db", "level": "debug"}),
                ("backup.done", {"name": "db", "secs": 1.26, "level": "info"}),
            ],
        )

    def test_failure_still_reports_finished(self):
        def boom(name):
            raise RuntimeError("disk")

        with self.assertRaises(RuntimeError):
            backup.run("db", boom, now=10**6)
        self.assertEqual(self.ev, [("backup.attempt_finished", {"name": "db", "level": "debug"})])

    def test_skipped(self):
        backup.run("db", lambda n: 1, now=43200, last_run=0)
        self.assertEqual(self.ev, [("backup.skipped", {"name": "db", "age_days": 0.5, "level": "warn"})])


class TestNotifier(Base):
    def test_mixed(self):
        def bad(u, t):
            raise RuntimeError("busy")

        notifier.notify("ann", "hi", {"sms": bad, "mail": lambda u, t: None})
        self.assertEqual(
            self.ev,
            [
                ("notifier.channel_error", {"channel": "sms", "error": "busy", "level": "error"}),
                ("notifier.sent", {"user": "ann", "channel": "mail", "level": "info"}),
            ],
        )

    def test_dropped(self):
        def bad(u, t):
            raise RuntimeError("busy")

        notifier.notify("ann", "hi", {"sms": bad})
        self.assertEqual(
            self.ev,
            [
                ("notifier.channel_error", {"channel": "sms", "error": "busy", "level": "error"}),
                ("notifier.dropped", {"user": "ann", "channel_count": 1, "level": "warn"}),
            ],
        )


class TestReports(Base):
    def test_lazy_generator(self):
        gen = reports.rows("r", [1, None, 2])
        self.assertEqual(self.ev, [])
        self.assertEqual(next(gen), 1)
        self.assertEqual(self.ev, [("reports.start", {"name": "r", "rows": 3, "level": "info"})])
        self.assertEqual(list(gen), [2])
        self.assertEqual(
            self.ev[1:],
            [
                ("reports.row_skipped", {"index": 1, "level": "debug"}),
                ("reports.end", {"name": "r", "emitted": 2, "level": "info"}),
            ],
        )

    def test_early_stop_has_no_end(self):
        reports.head("r", [1, 2, 3], 1)
        self.assertEqual([n for n, _ in self.ev], ["reports.start"])


if __name__ == "__main__":
    unittest.main()
