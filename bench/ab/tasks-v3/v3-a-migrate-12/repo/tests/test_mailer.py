import unittest

from ops import mailer


class MailerTest(unittest.TestCase):
    def test_first_try(self):
        sent = []
        self.assertTrue(mailer.send(sent.append, {"to": "x@y"}))
        self.assertEqual(len(sent), 1)

    def test_retries_then_ok(self):
        calls = []

        def flaky(m):
            calls.append(m)
            if len(calls) < 3:
                raise OSError("down")

        self.assertTrue(mailer.send(flaky, {"to": "x@y"}))
        self.assertEqual(len(calls), 3)

    def test_gives_up(self):
        def dead(m):
            raise OSError("down")

        self.assertFalse(mailer.send(dead, {"to": "x@y"}))

    def test_render(self):
        self.assertEqual(mailer.render("hi {n}", n=3), "hi 3")
