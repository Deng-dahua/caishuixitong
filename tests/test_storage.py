from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime_storage import atomic_write_json, read_json, safe_filename


class StorageTests(unittest.TestCase):
    def test_safe_filename_removes_traversal(self):
        self.assertEqual(safe_filename("../../secret.pdf"), "secret.pdf")
        self.assertNotIn("/", safe_filename("a/b/../../report.xlsx"))
        self.assertNotIn("\\", safe_filename("..\\..\\report.xlsx"))

    def test_atomic_json_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "cache.json"
            value = {"company": 7, "items": [1, 2, 3]}
            atomic_write_json(path, value)
            self.assertEqual(read_json(path, {}), value)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), value)


if __name__ == "__main__":
    unittest.main()
