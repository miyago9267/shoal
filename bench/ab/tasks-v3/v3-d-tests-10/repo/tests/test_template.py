import unittest

from utilkit import template


class TemplateSmoke(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(template.render("hi {{ name }}!", {"name": "bob"}), "hi bob!")

    def test_numbers(self):
        self.assertEqual(template.render("{{n}}{{n}}", {"n": 7}), "77")

    def test_no_tokens(self):
        self.assertEqual(template.render("plain", {}), "plain")
