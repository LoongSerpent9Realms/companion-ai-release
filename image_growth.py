"""Local preference learning for generated image recipes.

This stores generation parameters and explicit user adoption signals.  It does
not train an image model or inspect private images; it only reuses metadata
that the local generator already used.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from _paths import data_dir, module_root
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
STORE_FILE = DATA_DIR / "image_growth.json"


def _load() -> dict[str, Any]:
    return read_sensitive_json(STORE_FILE, {"recipes": []})


def _save(data: dict[str, Any]) -> None:
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(STORE_FILE, data)


def record_generation(path: str, *, kind: str, mood: str = "", seed: str = "", parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(path).strip()
    if not path:
        return {"ok": False, "error": "缺少生成图片路径"}
    data = _load()
    recipe_id = hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
    for recipe in data["recipes"]:
        if recipe.get("id") == recipe_id:
            return {"ok": True, "created": False, "recipe": recipe}
    recipe = {
        "id": recipe_id, "path": path, "kind": str(kind), "mood": str(mood), "seed": str(seed),
        "parameters": dict(parameters or {}), "created_at": int(time.time()), "feedback": "pending",
    }
    data["recipes"].append(recipe)
    _save(data)
    return {"ok": True, "created": True, "recipe": recipe}


IMAGE_FEEDBACK_LABELS = {"accepted", "rejected", "too_bright", "too_dark", "simpler"}


def record_feedback(path: str, feedback: bool | str) -> bool:
    data = _load()
    for recipe in reversed(data["recipes"]):
        if recipe.get("path") == str(path):
            label = ("accepted" if feedback else "rejected") if isinstance(feedback, bool) else str(feedback).strip().lower()
            if label not in IMAGE_FEEDBACK_LABELS:
                return False
            recipe["feedback"] = label
            recipe["feedback_at"] = int(time.time())
            _save(data)
            return True
    return False


def recommend_recipe(mood: str = "") -> dict[str, Any]:
    """Return the latest accepted recipe for this mood, or neutral defaults."""
    recipes = _load().get("recipes", [])
    accepted = [item for item in recipes if item.get("feedback") == "accepted" and (not mood or item.get("mood") == mood)]
    if not accepted:
        return {"seed": "", "parameters": {}, "learned": False}
    best = max(accepted, key=lambda item: int(item.get("feedback_at") or item.get("created_at") or 0))
    return {"seed": str(best.get("seed") or ""), "parameters": dict(best.get("parameters") or {}), "learned": True, "recipe_id": best.get("id")}


def list_recipes(limit: int = 100) -> list[dict[str, Any]]:
    rows = list(_load().get("recipes", []))
    rows.sort(key=lambda item: int(item.get("feedback_at") or item.get("created_at") or 0), reverse=True)
    return rows[:max(1, min(int(limit), 500))]


def status() -> dict[str, int]:
    recipes = _load().get("recipes", [])
    return {
        "generated": len(recipes),
        "accepted": sum(1 for item in recipes if item.get("feedback") == "accepted"),
        "rejected": sum(1 for item in recipes if item.get("feedback") == "rejected"),
        "too_bright": sum(1 for item in recipes if item.get("feedback") == "too_bright"),
        "too_dark": sum(1 for item in recipes if item.get("feedback") == "too_dark"),
        "simpler": sum(1 for item in recipes if item.get("feedback") == "simpler"),
    }
