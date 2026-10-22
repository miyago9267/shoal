import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from app.cli import main
from app.core import Customer, Order, Product, order_from_dict, order_to_dict, render_invoice


class ReportTest(unittest.TestCase):
    def make(self):
        o = Order("O7", Customer("Ann@Ex.org", "Ann"))
        o.add(Product("PEN-001", "Pen", 250), 3)
        return o

    def test_roundtrip(self):
        data = order_to_dict(self.make())
        self.assertEqual(data["customer"]["email"], "ann@ex.org")
        self.assertEqual(order_to_dict(order_from_dict(data)), data)

    def test_invoice(self):
        text = render_invoice(self.make())
        self.assertIn("Invoice O7 for ann@ex.org", text)
        self.assertTrue(text.splitlines()[-1].strip().endswith("€9.00"))

    def test_cli(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(order_to_dict(self.make()), fh)
        try:
            buf = StringIO()
            with redirect_stdout(buf):
                self.assertEqual(main([path]), 0)
            self.assertIn("TOTAL", buf.getvalue())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
