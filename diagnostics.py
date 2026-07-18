"""Safe local diagnostic report export for Companion AI."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
DIAGNOSTIC_DIR = DATA_DIR / "diagnostics"


def build_report(health: dict[str, Any], runtime: dict[str, Any], growth: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": int(time.time()),
        "health": health,
        "runtime": runtime,
        "growth": growth,
        "training_job": job,
        "privacy": "No chat content, API key, memory, image or audit text is included.",
    }


def export_report(report: dict[str, Any]) -> str:
    DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
    path = DIAGNOSTIC_DIR / f"companion-diagnostic-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
