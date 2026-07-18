from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import growth_jobs


class GrowthJobTests(unittest.TestCase):
    def test_background_job_reports_completion(self) -> None:
        with patch("growth_loop.train_candidate", return_value={"ok": True, "promoted": True}):
            result = growth_jobs.start(epochs=1)
            self.assertTrue(result["ok"])
            for _ in range(50):
                state = growth_jobs.status()
                if state["state"] in {"done", "failed", "cancelled"}:
                    break
                time.sleep(0.02)
        self.assertEqual(growth_jobs.status()["state"], "done")
        self.assertEqual(growth_jobs.status()["progress"], 100)


if __name__ == "__main__":
    unittest.main()
