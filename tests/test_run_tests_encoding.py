"""tools/run_tests.py 在非 UTF-8 locale（例如 Windows cp1252）下不能崩潰。"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_tests.py"


class RunTestsEncodingTests(unittest.TestCase):
    def test_harden_stdio_survives_cp1252_stdout(self):
        code = (
            "import importlib.util as u;"
            f"s=u.spec_from_file_location('rt', r'{RUNNER}');"
            "m=u.module_from_spec(s);s.loader.exec_module(m);"
            "m.harden_stdio();print('結束於 5s')"
        )
        env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        proc = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn("結束於 5s", proc.stdout.decode("utf-8"))

    def test_run_unit_tolerates_non_utf8_worker_output(self):
        spec = importlib.util.spec_from_file_location("rt", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import tempfile
        from unittest import mock

        real = subprocess.run
        bad = "import sys;sys.stdout.buffer.write(b'x\\x90y\\xe4');sys.exit(3)"

        def fake(cmd, **kw):
            return real([sys.executable, "-c", bad], **kw)

        with tempfile.TemporaryDirectory() as d, mock.patch.object(
            mod.subprocess, "run", fake
        ):
            r = mod.run_unit(0, ["t.A.b"], Path(d))
        self.assertIn("crash", r)
        self.assertIn("x", r["crash"])


if __name__ == "__main__":
    unittest.main()
