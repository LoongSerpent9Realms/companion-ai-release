from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_layer import MemoryStore
from sensitive_json import write_sensitive_json


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "memory.json"
        self.store = MemoryStore(self.path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_legacy_records_gain_structured_metadata(self) -> None:
        write_sensitive_json(self.path, {"profile": [{"time": 123, "text": "我叫小明"}], "preferences": [], "facts": []})
        record = self.store.load()["profile"][0]
        self.assertEqual(record["text"], "我叫小明")
        self.assertEqual(record["source"], "legacy")
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["field_key"], "identity.name")

    def test_new_single_value_fact_supersedes_old_one(self) -> None:
        first = self.store.add("我住在上海", "profile", source="explicit")
        second = self.store.add("我住在香港", "profile", source="explicit")
        records = self.store.load()["profile"]
        self.assertTrue(first["created"])
        self.assertEqual(second["superseded"], 1)
        self.assertEqual(records[0]["status"], "superseded")
        self.assertEqual(records[0]["superseded_by"], records[1]["id"])
        self.assertEqual(records[1]["status"], "active")
        self.assertEqual([item["text"] for item in self.store.active_view()["profile"]], ["我住在香港"])

    def test_recall_is_relevant_and_excludes_sensitive_memories(self) -> None:
        self.store.add("我的项目是 Companion AI 记忆层改造", "profile", source="explicit")
        self.store.add("密码是 example-secret", "facts", source="explicit")
        recalled = self.store.recall("Companion 项目进度")
        self.assertEqual(len(recalled), 1)
        self.assertIn("Companion AI", recalled[0]["text"])
        self.assertNotIn("example-secret", self.store.context_for("密码"))


if __name__ == "__main__":
    unittest.main()
