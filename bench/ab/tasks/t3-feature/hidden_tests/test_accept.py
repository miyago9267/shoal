import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from invsum.cli import main

CSV = """sku,category,quantity,unit_price
A1,tools,3,10.00
A2,tools,2,2.50
B1,garden,10,1.25
C1,paint,1,19.99
"""


class AcceptTest(unittest.TestCase):
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

    def test_json_output(self):
        code, out = self.run_cli("--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertEqual([r["category"] for r in data], ["garden", "paint", "tools"])
        tools = data[2]
        self.assertEqual(set(tools), {"category", "items", "quantity", "value"})
        self.assertEqual(tools["items"], 2)
        self.assertEqual(tools["quantity"], 5)
        self.assertAlmostEqual(tools["value"], 35.0)
        self.assertIsInstance(tools["quantity"], int)
        self.assertNotIn("TOTAL", [r["category"] for r in data])

    def test_json_respects_sort_and_filter(self):
        code, out = self.run_cli("--format", "json", "--sort", "value",
                                 "--min-quantity", "2")
        data = json.loads(out)
        self.assertEqual([r["category"] for r in data], ["tools", "garden"])
        self.assertAlmostEqual(data[1]["value"], 12.5)

    def test_text_is_default_and_explicit(self):
        _, default = self.run_cli()
        _, explicit = self.run_cli("--format", "text")
        self.assertEqual(default, explicit)
        self.assertEqual(default.splitlines()[-1].split(), ["TOTAL", "4", "16", "67.49"])

    def test_rejects_unknown_format(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main([self.path, "--format", "xml"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
