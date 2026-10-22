import unittest

from hq import router
from hq.errors import UnknownHandler, ValidationError


class RouterTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(len(router.names()), 10)

    def test_unknown(self):
        with self.assertRaises(UnknownHandler):
            router.dispatch("nope", {})

    def test_error_has_field(self):
        with self.assertRaises(ValidationError) as ctx:
            router.dispatch("rating", {"item_id": 1, "stars": 9})
        self.assertEqual(ctx.exception.field, "stars")

    def test_payload_not_mutated(self):
        payload = {"name": " Ann ", "tags": ["Go"]}
        router.dispatch("profile", payload)
        self.assertEqual(payload, {"name": " Ann ", "tags": ["Go"]})
