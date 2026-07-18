from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import tiny_llm


class TinyLlmRuntimeTests(unittest.TestCase):
    def test_deep_reply_adds_answer_guidance_without_exposing_a_trace(self) -> None:
        inference = tiny_llm.TinyLLMInference()
        inference.loaded = True
        with patch.object(inference, "generate", return_value="结论") as generate:
            reply = inference.chat("怎么安排？", deep_reply=True)

        self.assertEqual(reply, "结论")
        prompt = generate.call_args.args[0]
        self.assertIn("回答要求", prompt)
        self.assertIn("不要展示推理过程", prompt)

    def test_frozen_training_is_forwarded_to_component_python(self) -> None:
        expected = {"ok": True, "final_loss": 0.2}
        with (
            patch.object(tiny_llm.sys, "frozen", True, create=True),
            patch.object(tiny_llm, "train_tiny_llm_in_runtime", return_value=expected) as worker,
        ):
            result = tiny_llm.train_tiny_llm(
                texts=["样本"], epochs=3, batch_size=1, max_seq_len=64,
            )

        self.assertIs(result, expected)
        self.assertEqual(worker.call_args.kwargs["texts"], ["样本"])
        self.assertEqual(worker.call_args.kwargs["epochs"], 3)
        self.assertEqual(worker.call_args.kwargs["max_seq_len"], 64)

    def test_worker_process_does_not_expose_pyinstaller_pythonpath(self) -> None:
        runtime = r"C:\runtime\python\Scripts\python.exe"

        class Completed:
            returncode = 0
            stdout = json.dumps({"ok": True})
            stderr = ""

        with (
            patch.object(tiny_llm, "_runtime_worker_path", return_value=Path("C:/bundle/_internal/tiny_llm_runtime_worker.py")),
            patch.object(tiny_llm, "runtime_python_exe", return_value=runtime),
            patch.object(tiny_llm, "runtime_subprocess_env", return_value={"PYTHONPATH": r"C:\bundle\_internal"}),
            patch.object(tiny_llm.Path, "is_file", return_value=True),
            patch.object(tiny_llm.subprocess, "run", return_value=Completed()) as run,
        ):
            result = tiny_llm._run_runtime_worker({"action": "train"})

        self.assertTrue(result["ok"])
        kwargs = run.call_args.kwargs
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertEqual(kwargs["cwd"], str(Path(runtime).parent))


if __name__ == "__main__":
    unittest.main()
