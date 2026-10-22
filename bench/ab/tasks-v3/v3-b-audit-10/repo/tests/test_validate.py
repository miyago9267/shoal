import unittest

from hq import validate
from hq.errors import ValidationError


class StrFieldTest(unittest.TestCase):
    def test_strips(self):
        self.assertEqual(validate.str_field({"a": " x "}, "a"), "x")

    def test_required(self):
        with self.assertRaises(ValidationError) as ctx:
            validate.str_field({}, "a")
        self.assertEqual(ctx.exception.field, "a")

    def test_optional(self):
        self.assertIsNone(validate.str_field({}, "a", required=False))

    def test_limits(self):
        with self.assertRaises(ValidationError):
            validate.str_field({"a": "  "}, "a")
        with self.assertRaises(ValidationError):
            validate.str_field({"a": "abcd"}, "a", max_len=3)

    def test_type(self):
        with self.assertRaises(ValidationError):
            validate.str_field({"a": 3}, "a")


class IntFieldTest(unittest.TestCase):
    def test_range(self):
        self.assertEqual(validate.int_field({"n": 3}, "n", 1, 5), 3)
        with self.assertRaises(ValidationError):
            validate.int_field({"n": 6}, "n", 1, 5)
        with self.assertRaises(ValidationError):
            validate.int_field({"n": 0}, "n", 1, 5)

    def test_bool_and_float(self):
        for bad in (True, False, 1.0, "1"):
            with self.assertRaises(ValidationError):
                validate.int_field({"n": bad}, "n")

    def test_default(self):
        self.assertEqual(validate.int_field({}, "n", default=7), 7)


class ChoiceListTest(unittest.TestCase):
    def test_choice(self):
        self.assertEqual(validate.choice_field({"c": "a"}, "c", {"a", "b"}), "a")
        self.assertEqual(validate.choice_field({}, "c", {"a"}, default="a"), "a")
        with self.assertRaises(ValidationError):
            validate.choice_field({"c": "z"}, "c", {"a", "b"})

    def test_list(self):
        self.assertEqual(validate.list_field({"l": [1]}, "l", min_items=1), [1])
        with self.assertRaises(ValidationError):
            validate.list_field({"l": []}, "l", min_items=1)
        with self.assertRaises(ValidationError):
            validate.list_field({"l": (1,)}, "l")
        self.assertIsNone(validate.list_field({}, "l", required=False))


class EmailTest(unittest.TestCase):
    def test_valid(self):
        for e in ("a@b.co", "a.b+c@mail.example.com", "x@y-z.io"):
            self.assertTrue(validate.is_email(e), e)

    def test_invalid(self):
        for e in ("a", "a@b", "@b.co", "a@@b.co", "a@b..co", "a@-b.co", "a b@c.co", 5):
            self.assertFalse(validate.is_email(e), e)

    def test_email_field_lowercases(self):
        self.assertEqual(validate.email_field({"e": " A@B.co "}, "e"), "a@b.co")
