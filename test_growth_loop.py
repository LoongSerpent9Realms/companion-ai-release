from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import growth_loop


class GrowthLoopTests(unittest.TestCase):
    def _configure_paths(self, root: Path) -> None:
        growth_loop.GROWTH_DIR = root / "growth"
        growth_loop.EXPERIENCE_FILE = growth_loop.GROWTH_DIR / "experiences.json"
        growth_loop.STATE_FILE = growth_loop.GROWTH_DIR / "model_versions.json"
        growth_loop.CANDIDATE_DIR = growth_loop.GROWTH_DIR / "candidates"
        growth_loop.VERSION_DIR = growth_loop.GROWTH_DIR / "versions"
        growth_loop.TRAINING_FILE = root / "training.json"
        growth_loop.BENCHMARK_FILE = growth_loop.GROWTH_DIR / "benchmarks.json"

    def test_only_positive_verified_experience_is_trainable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE)
            try:
                self._configure_paths(Path(directory))
                growth_loop.record_experience("正确问题", "正确答案", evidence_type="test_pass", reward=1, evidence="本地测试通过")
                growth_loop.record_experience("猜测问题", "猜测答案", evidence_type="", reward=1)
                growth_loop.record_experience("差问题", "差答案", evidence_type="human", reward=-1)
                examples = growth_loop.eligible_examples()
            finally:
                (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE) = original
        self.assertEqual([(item["prompt"], item["response"]) for item in examples], [("正确问题", "正确答案")])

    def test_candidate_promotion_preserves_then_can_restore_active_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE)
            active = [root / name for name in ("active-model.pt", "active-vocab.json", "active-config.json")]
            try:
                self._configure_paths(root)
                for index in range(8):
                    growth_loop.record_experience(f"问题{index}", f"回答{index}", evidence_type="human", reward=1)
                for path, text in zip(active, ("old-model", "old-vocab", "old-config")):
                    path.write_text(text, encoding="utf-8")

                def fake_train(**kwargs):
                    staged = Path(kwargs["output_dir"])
                    staged.mkdir(parents=True, exist_ok=True)
                    for name, text in (("model.pt", "new-model"), ("vocab.json", "new-vocab"), ("config.json", "new-config")):
                        (staged / name).write_text(text, encoding="utf-8")
                    return {"ok": True, "final_loss": 1.0}

                with (
                    patch.object(growth_loop, "_active_artifacts", return_value=active),
                    patch.object(growth_loop, "_reload_active_runtime", return_value={"ok": True}),
                    patch("tiny_llm.train_tiny_llm_in_runtime", side_effect=fake_train),
                    patch("tiny_llm.evaluate_tiny_llm_in_runtime", return_value={"ok": True, "loss": 1.0}),
                    patch.object(growth_loop, "evaluate_benchmarks", return_value={"ok": True, "score": 1, "total": 1, "details": []}),
                ):
                    result = growth_loop.train_candidate(epochs=1)
                    self.assertTrue(result["promoted"])
                    self.assertEqual(active[0].read_text(encoding="utf-8"), "new-model")
                    rollback = growth_loop.rollback_active_model()
                self.assertTrue(rollback["ok"])
                self.assertEqual(active[0].read_text(encoding="utf-8"), "old-model")
            finally:
                (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE) = original

    def test_replay_keeps_core_examples_when_training_set_is_limited(self) -> None:
        examples = [
            {"id": f"core-{index}", "source": "teach:manual", "time": index}
            for index in range(3)
        ] + [
            {"id": f"other-{index}", "source": "feedback", "time": index}
            for index in range(20)
        ]
        selected, core_count = growth_loop.select_replay_examples(examples, max_samples=8)
        self.assertEqual(len(selected), 8)
        self.assertEqual(core_count, 3)
        self.assertTrue(all(item in selected for item in examples[:3]))

    def test_user_managed_benchmark_can_be_added_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE)
            try:
                self._configure_paths(Path(directory))
                added = growth_loop.add_benchmark("今天怎么样？", "开心,陪")
                self.assertTrue(added["ok"])
                self.assertEqual(len(growth_loop.list_benchmarks()), 1)
                updated = growth_loop.update_benchmark(added["benchmark"]["id"], "你是谁？", "伙伴,本地")
                self.assertTrue(updated["ok"])
                self.assertEqual(growth_loop.list_benchmarks()[0]["expected_keywords"], ["伙伴", "本地"])
                self.assertTrue(growth_loop.remove_benchmark(added["benchmark"]["id"]))
                self.assertEqual(growth_loop.list_benchmarks(), [])
            finally:
                (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE) = original

    def test_benchmark_rules_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE)
            try:
                self._configure_paths(Path(directory))
                added = growth_loop.add_benchmark("只回复 hi", "hi", rule="exact")
                self.assertTrue(added["ok"])
                updated = growth_loop.update_benchmark(added["benchmark"]["id"], "不超过五字", "5", rule="max_length")
                self.assertTrue(updated["ok"])
                self.assertEqual(growth_loop.list_benchmarks()[0]["rule"], "max_length")
            finally:
                (growth_loop.GROWTH_DIR, growth_loop.EXPERIENCE_FILE, growth_loop.STATE_FILE, growth_loop.CANDIDATE_DIR, growth_loop.VERSION_DIR, growth_loop.TRAINING_FILE, growth_loop.BENCHMARK_FILE) = original


if __name__ == "__main__":
    unittest.main()
