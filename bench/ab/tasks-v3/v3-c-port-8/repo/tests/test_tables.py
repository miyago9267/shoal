import unittest

from fmtkit import tables
from fmtkit.errors import ParseError


def row(ident, flag, name, reserved=b"\x00\x00"):
    return ident.to_bytes(2, "big") + bytes([flag, len(name)]) + name + reserved


class TablesTest(unittest.TestCase):
    def test_parse(self):
        data = (2).to_bytes(4, "big") + row(1, 0, b"ab") + row(2, 1, b"c")
        rows = tables.parse(data)
        self.assertEqual([r["name"] for r in rows], ["ab", "c"])
        self.assertEqual(tables.flagged(rows), [2])
        self.assertEqual(tables.by_id(rows)[1]["flag"], 0)

    def test_missing_rows(self):
        data = (3).to_bytes(4, "big") + row(1, 0, b"ab")
        with self.assertRaises(ParseError):
            tables.parse(data)
