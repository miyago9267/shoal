import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from invsum.cli import main

CSV = """sku,category,quantity,unit_price
A1,tools,3,10.00
A2,tools,2,2.50
B1,garden,10,1.25
C1,paint,1,19.99
"""


class CliTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as fh:
            fh.write(CSV)

    def tearDown(self):
        os.unlink(self.path)

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([self.path, *args])
        return code, buf.getvalue()

    def test_table(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Category"))
        self.assertEqual(lines[2].split(), ["garden", "1", "10", "12.50"])
        self.assertEqual(lines[-1].split(), ["TOTAL", "4", "16", "67.49"])

    def test_sort_and_filter(self):
        code, out = self.run_cli("--sort", "value", "--min-quantity", "2")
        names = [l.split()[0] for l in out.splitlines()[2:-2]]
        self.assertEqual(names, ["tools", "garden"])

    def test_missing_file(self):
        self.assertEqual(main(["/nonexistent/stock.csv"]), 1)


if __name__ == "__main__":
    unittest.main()
