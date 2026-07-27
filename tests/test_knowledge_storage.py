import json
import tempfile
import unittest
from pathlib import Path

from engine import knowledge_base


class KnowledgeStorageTests(unittest.TestCase):
    def test_legacy_static_knowledge_is_migrated_to_private_data(self):
        previous_path = knowledge_base._KB_PATH
        previous_legacy = knowledge_base._LEGACY_KB_PATH
        try:
            with tempfile.TemporaryDirectory() as temp_name:
                root = Path(temp_name)
                private_path = root / "data" / "tax_agi_knowledge.json"
                legacy_path = root / "static" / "tax_agi_knowledge.json"
                legacy_path.parent.mkdir(parents=True)
                legacy_path.write_text(
                    json.dumps({"policies": {"custom": {"name": "test"}}}),
                    encoding="utf-8",
                )
                knowledge_base._KB_PATH = str(private_path)
                knowledge_base._LEGACY_KB_PATH = legacy_path

                loaded = knowledge_base.KnowledgeBase()

                self.assertEqual(loaded.get_policy("custom")["name"], "test")
                self.assertTrue(private_path.is_file())
                migrated = json.loads(private_path.read_text(encoding="utf-8"))
                self.assertIn("semantic_dict", migrated)
        finally:
            knowledge_base._KB_PATH = previous_path
            knowledge_base._LEGACY_KB_PATH = previous_legacy


if __name__ == "__main__":
    unittest.main()
