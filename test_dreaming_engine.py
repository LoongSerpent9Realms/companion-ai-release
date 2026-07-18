from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dreaming_engine


PYTHON_DRILL = {
    "id": "python-drill",
    "lang": "python",
    "title": "Python drill",
    "description": "Return the value.",
    "template": "class Solution:\n    def solve(self, value):\n        pass",
    "test_cases": [],
}


class DreamPracticeTests(unittest.TestCase):
    def test_runtime_settings_persist_idle_and_quiet_hours(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "dream_config.json"
            with patch.object(dreaming_engine, "DREAM_CONFIG_FILE", config_file):
                config = dreaming_engine.load_dream_config()
                config.update({"system_idle_threshold_seconds": 180, "chat_idle_threshold_seconds": 75, "quiet_hours": [2, 3]})
                dreaming_engine.save_dream_config(config)
                loaded = dreaming_engine.load_dream_config()
        self.assertEqual(loaded["system_idle_threshold_seconds"], 180)
        self.assertEqual(loaded["chat_idle_threshold_seconds"], 75)
        self.assertEqual(loaded["quiet_hours"], [2, 3])

    def test_practice_selects_only_python_drills(self) -> None:
        drills = [
            {"id": "cpp-drill", "lang": "cpp", "title": "C++ drill"},
            PYTHON_DRILL,
        ]
        with (
            patch.object(dreaming_engine, "_load_drills", return_value=drills),
            patch.object(dreaming_engine, "_load_skills", return_value={"mastered": []}),
        ):
            selected = dreaming_engine._pick_next_drill({"python"})

        self.assertEqual(selected["id"], "python-drill")

    def test_natural_language_model_output_is_not_executed_as_python(self) -> None:
        runner_calls = []
        with (
            patch.object(dreaming_engine, "_code_practice_environment", return_value={"languages": {"python"}, "labels": ["Python"]}),
            patch.object(dreaming_engine, "_pick_next_drill", return_value=PYTHON_DRILL),
            patch.object(dreaming_engine, "_learn_programming_language_structure", return_value={"ok": True, "summary": "Python class syntax", "context": "class Solution"}),
            patch.object(dreaming_engine, "_ask_llm_for_code", return_value="我不太确定怎么回答，你可以换个方式问吗？"),
            patch.object(dreaming_engine, "_run_drill_code", side_effect=lambda *args: runner_calls.append(args)),
            patch.object(dreaming_engine, "_save_state"),
        ):
            result = dreaming_engine._do_code_practice({}, {})

        self.assertFalse(result["ok"])
        self.assertIn("没有返回有效 Python 代码", result["last_error"])
        self.assertEqual(runner_calls, [])

    def test_code_extractor_discards_unfenced_chinese_preface(self) -> None:
        reply = "下面是实现，包含示例测试：\nclass Solution:\n    def solve(self, value):\n        return value"
        with patch("hybrid_chat.hybrid_chat_simple", return_value=reply):
            code = dreaming_engine._ask_llm_for_code("write code")

        self.assertEqual(
            code,
            "class Solution:\n    def solve(self, value):\n        return value",
        )
        self.assertEqual(dreaming_engine._validate_solution(code, "python"), "")

    def test_language_learning_reference_is_given_to_code_generator(self) -> None:
        prompts = []
        valid_code = "class Solution:\n    def solve(self, value):\n        return value"
        learning = {
            "ok": True,
            "summary": "Python 语言结构已学习",
            "context": "Python class definitions and dictionaries",
            "sources": ["docs.python.org"],
        }
        with (
            patch.object(dreaming_engine, "_code_practice_environment", return_value={"languages": {"python"}, "labels": ["Python"]}),
            patch.object(dreaming_engine, "_pick_next_drill", return_value=PYTHON_DRILL),
            patch.object(dreaming_engine, "_learn_programming_language_structure", return_value=learning),
            patch.object(dreaming_engine, "_ask_llm_for_code", side_effect=lambda prompt, error="": prompts.append(prompt) or valid_code),
            patch.object(dreaming_engine, "_run_drill_code", return_value={"ok": True, "stderr": ""}),
            patch.object(dreaming_engine, "_record_skill"),
            patch.object(dreaming_engine, "_queue_showoff"),
            patch.object(dreaming_engine, "_save_state"),
        ):
            result = dreaming_engine._do_code_practice({}, {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["language_learning"], learning)
        self.assertIn("Python class definitions", prompts[0])

    def test_csharp_solution_requires_a_main_test_entrypoint(self) -> None:
        incomplete = "public class Solution { public int Add(int a, int b) => a + b; }"
        complete = incomplete + " class Program { static void Main() { } }"

        self.assertIn("Main", dreaming_engine._validate_solution(incomplete, "csharp"))
        self.assertEqual(dreaming_engine._validate_solution(complete, "csharp"), "")

    def test_environment_status_exposes_available_runtimes(self) -> None:
        with patch("code_lab._compiler_status", return_value={
            "python": "python.exe", "g++": "", "clang++": "", "cl": "", "dotnet": "dotnet.exe", "csc": "",
        }):
            environment = dreaming_engine._code_practice_environment()

        self.assertEqual(environment["languages"], {"python", "csharp"})
        self.assertEqual(environment["labels"], ["Python", "C#"])


if __name__ == "__main__":
    unittest.main()
