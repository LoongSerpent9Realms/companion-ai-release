from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import local_image_backend


class LocalImageBackendTests(unittest.TestCase):
    def test_comfyui_config_requires_workflow_and_prompt_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "backend.json"
            workflow = root / "workflow.json"
            workflow.write_text(json.dumps({"6": {"inputs": {"text": ""}}}), encoding="utf-8")
            with patch.object(local_image_backend, "CONFIG_FILE", config_file):
                local_image_backend.save_config({"enabled": True, "backend": "comfyui", "workflow_path": str(workflow), "prompt_node_id": "6"})
                status = local_image_backend.public_status()
        self.assertTrue(status["enabled"])
        self.assertTrue(status["workflow_configured"])

    def test_invalid_backend_falls_back_to_builtin_card(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "backend.json"
            with patch.object(local_image_backend, "CONFIG_FILE", config_file):
                config = local_image_backend.save_config({"enabled": True, "backend": "unknown"})
        self.assertEqual(config["backend"], "mood_card")


if __name__ == "__main__":
    unittest.main()
