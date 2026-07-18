from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import conversation_audit
import image_growth


class ImageGrowthTests(unittest.TestCase):
    def test_accepted_recipe_is_recommended_for_same_mood(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "image_growth.json"
            with patch.object(image_growth, "STORE_FILE", store):
                image_growth.record_generation("C:/images/a.png", kind="mood_card", mood="温暖", seed="seed-a", parameters={"ratio": "4:5"})
                self.assertTrue(image_growth.record_feedback("C:/images/a.png", True))
                recipe = image_growth.recommend_recipe("温暖")
        self.assertTrue(recipe["learned"])
        self.assertEqual(recipe["seed"], "seed-a")
        self.assertEqual(recipe["parameters"]["ratio"], "4:5")

    def test_cloud_audit_is_opt_in_even_when_a_key_exists(self) -> None:
        config = {"enabled": True, "local_fallback": True, "api_key": "configured", "use_cloud_audit": False}
        with patch.object(conversation_audit, "call_ai_api") as call:
            result = conversation_audit.audit_conversation("我很难过", "我在这里陪你。", config=config)
        self.assertEqual(result["audit_source"], "local")
        call.assert_not_called()

    def test_recipe_can_store_specific_visual_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "image_growth.json"
            with patch.object(image_growth, "STORE_FILE", store):
                image_growth.record_generation("C:/images/b.png", kind="mood_card", mood="平静")
                self.assertTrue(image_growth.record_feedback("C:/images/b.png", "too_bright"))
                self.assertEqual(image_growth.status()["too_bright"], 1)


if __name__ == "__main__":
    unittest.main()
