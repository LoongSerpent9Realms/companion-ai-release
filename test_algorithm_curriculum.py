from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import algorithm_curriculum


class AlgorithmCurriculumTests(unittest.TestCase):
    def test_seed_samples_are_executable_and_include_reasoning(self) -> None:
        with (
            patch.object(algorithm_curriculum, "_load_verification_cache", return_value={}),
            patch.object(algorithm_curriculum, "_save_verification_cache"),
            patch.object(algorithm_curriculum, "_verify_sample", return_value=True),
        ):
            samples = algorithm_curriculum.verified_samples()
            texts = algorithm_curriculum.build_training_texts()
        self.assertEqual(len(samples), 5)
        self.assertEqual(len(texts), 5)
        self.assertIn("解题计划：", texts[0])
        self.assertIn("```python", texts[0])

    def test_export_writes_only_verified_training_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dataset.jsonl"
            with patch.object(algorithm_curriculum, "DATASET_FILE", target):
                result = algorithm_curriculum.export_curriculum_dataset()

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["samples"], 3)
            self.assertEqual(len(target.read_text(encoding="utf-8").splitlines()), result["samples"])

    def test_training_uses_component_python_worker(self) -> None:
        expected = {"ok": True, "final_loss": 0.1}
        with (
            patch.object(algorithm_curriculum, "build_training_texts", return_value=["课程样本"]),
            patch.object(algorithm_curriculum, "export_curriculum_dataset"),
            patch("tiny_llm.train_tiny_llm_in_runtime", return_value=expected) as train,
        ):
            result = algorithm_curriculum.train_algorithm_tiny_llm(epochs=8)

        self.assertIs(result, expected)
        self.assertEqual(train.call_args.kwargs["texts"], ["课程样本"])
        self.assertEqual(train.call_args.kwargs["epochs"], 8)


if __name__ == "__main__":
    unittest.main()
