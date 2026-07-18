from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_training
import conversation_audit


class AuditTrainingTests(unittest.TestCase):
    def test_auto_accepted_cloud_rewrite_is_a_positive_training_example(self) -> None:
        result = {
            "audit_id": "auto-rewrite-1",
            "user_message": "我今天很难过",
            "ai_reply": "别想太多。",
            "suggested_response": "听起来你今天真的很难受，我陪你慢慢说。",
            "needs_user_action": True,
            "ai_quality": {"overall_score": 0.3},
            "ai_correctness": {"overall_correctness": 0.4},
            "sentiment_judgment": {"correct": False},
            "suggestions": ["先回应用户的难过，再提供陪伴。"],
        }
        with tempfile.TemporaryDirectory() as directory:
            training_file = Path(directory) / "training.json"
            with patch.object(audit_training, "TRAINING_FILE", training_file):
                training = audit_training.record_audit_training(
                    result,
                    decision="auto_correct",
                    corrected_response=result["suggested_response"],
                )

        self.assertEqual(training["examples"][0]["response"], result["suggested_response"])
        self.assertEqual(training["examples"][0]["source"], "audit_auto_correct")
        self.assertEqual(training["examples"][0]["rating"], 1)
        self.assertEqual(training["feedback"][0]["wrong_response"], result["ai_reply"])
        self.assertIn(result["audit_id"], audit_training.handled_audit_ids(training))

    def test_only_cloud_audit_rewrites_are_auto_applied(self) -> None:
        config = {"api_key": "test", "auto_suggest_corrections": True, "correction_threshold": 0.65}
        cloud_result = {
            "audit_source": "api",
            "ai_quality": {"overall_score": 0.2},
            "ai_correctness": {"overall_correctness": 0.2},
            "sentiment_judgment": {"correct": False},
            "suggested_response": "更合适的回复",
        }
        local_result = dict(cloud_result, audit_source="local")

        cloud = conversation_audit._attach_review_metadata(
            cloud_result, "用户输入", "原回复", config, allow_api=True
        )
        local = conversation_audit._attach_review_metadata(
            local_result, "用户输入", "原回复", config, allow_api=True
        )

        self.assertTrue(cloud["auto_apply_suggested_correction"])
        self.assertEqual(cloud["review_status"], "auto_applied")
        self.assertNotIn("auto_apply_suggested_correction", local)

    def test_recent_audits_reads_jsonl_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results_file = Path(directory) / "audit_results.jsonl"
            results_file.write_text(
                '{"timestamp":"2026-07-15T10:00:00","user_message":"早","ai_reply":"早上好"}\n'
                '{"timestamp":"2026-07-15T11:00:00","audit_id":"newer","user_message":"晚","ai_reply":"晚上好"}\n',
                encoding="utf-8",
            )
            with patch.object(conversation_audit, "AUDIT_RESULTS_FILE", results_file):
                results = conversation_audit.get_recent_audits(2)

        self.assertEqual([item["audit_id"] for item in results], ["newer", conversation_audit._conversation_audit_id("早", "早上好")])

    def test_audit_rewrite_prompt_includes_configured_identity(self) -> None:
        result = {"ai_quality": {}, "ai_correctness": {}, "sentiment_judgment": {}, "suggestions": []}
        captured = []
        with (
            patch.object(conversation_audit, "_audit_identity_context", return_value="名字：小澜\n关系身份：女儿\n人设：温柔坦诚"),
            patch.object(conversation_audit, "call_ai_api", side_effect=lambda config, system, prompt: captured.append(prompt) or '{"suggested_response":"老爸，我是小澜。"}'),
        ):
            suggestion = conversation_audit._generate_correction_suggestion(
                "你是谁？", "我是 AI 助手。", result, {"api_key": "test"}
            )

        self.assertEqual(suggestion["suggested_response"], "老爸，我是小澜。")
        self.assertIn("AI 身份设定（改写必须遵守）", captured[0])
        self.assertIn("名字：小澜", captured[0])

    def test_audit_analysis_text_is_not_accepted_as_a_training_suggestion(self) -> None:
        raw = "用户问的是‘你知道哔哩哔哩吗’。审计结果建议：直接回答。"
        self.assertEqual(conversation_audit._trainable_suggested_response(raw), "")
        self.assertEqual(
            conversation_audit._trainable_suggested_response("我知道，哔哩哔哩是一个以视频内容和社区互动为主的平台。"),
            "我知道，哔哩哔哩是一个以视频内容和社区互动为主的平台。",
        )

    def test_positive_audit_correction_is_synced_to_live_retrieval(self) -> None:
        result = {
            "audit_id": "sync-rewrite-1",
            "user_message": "你最近有在学习新东西吗？",
            "ai_reply": "不知道。",
            "suggested_response": "我最近一直在探索一些新领域呢。",
        }
        with tempfile.TemporaryDirectory() as directory:
            training_file = Path(directory) / "training.json"
            with (
                patch.object(audit_training, "TRAINING_FILE", training_file),
                patch.object(audit_training, "_sync_positive_example") as sync,
            ):
                audit_training.record_audit_training(
                    result,
                    decision="auto_correct",
                    corrected_response=result["suggested_response"],
                )

        sync.assert_called_once_with(result["user_message"], result["suggested_response"], "audit_auto_correct")


if __name__ == "__main__":
    unittest.main()
