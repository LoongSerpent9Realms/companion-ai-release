"""Export and import Companion AI memory bundles."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from _paths import module_root, data_dir
import dialogue_skills
import user_profile
from sensitive_json import read_sensitive_json, write_sensitive_json
from memory_layer import MemoryStore


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
MEMORY_FILE = DATA_DIR / "memory.json"
MEMORY_STORE = MemoryStore(MEMORY_FILE)
TRAINING_FILE = DATA_DIR / "training.json"
EXPORT_DIR = DATA_DIR / "exports"


def _read_json(path: Path, default: dict) -> dict:
    return read_sensitive_json(path, default)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_sensitive_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(path, data)


def _default_memory() -> dict:
    return {"schema_version": 2, "profile": [], "facts": [], "preferences": []}


def _default_training() -> dict:
    return {"examples": [], "feedback": []}


def _bundle() -> dict:
    return {
        "format": "companion-ai-memory-bundle",
        "version": 1,
        "created_at": int(time.time()),
        "memory": _read_json(MEMORY_FILE, _default_memory()),
        "training": _read_json(TRAINING_FILE, _default_training()),
        "user_profile": user_profile.load_user_profile(),
        "dialogue_skills": dialogue_skills.load_dialogue_skills(),
    }


def export_memory_bundle(target: str = "") -> str:
    bundle = _bundle()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if target.strip():
        path = Path(target.strip().strip('"')).expanduser()
        if path.suffix.lower() != ".json":
            path.mkdir(parents=True, exist_ok=True)
            path = path / _default_export_name()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path = EXPORT_DIR / _default_export_name()
    _write_json(path, bundle)
    stats = _bundle_stats(bundle)
    return (
        "记忆已导出：\n"
        f"{path}\n\n"
        f"长期记忆：{stats['memory']} 条\n"
        f"训练样本：{stats['examples']} 条\n"
        f"用户画像：{stats['profile']} 条\n"
        f"对话技能：{stats['skills']} 个"
    )


def _default_export_name() -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"companion_memory_{stamp}.json"


def _bundle_stats(bundle: dict) -> dict:
    memory = bundle.get("memory", {})
    profile = bundle.get("user_profile", {}).get("buckets", {})
    return {
        "memory": sum(len(memory.get(bucket, [])) for bucket in ("profile", "preferences", "facts")),
        "examples": len(bundle.get("training", {}).get("examples", [])),
        "profile": sum(len(items) for items in profile.values() if isinstance(items, list)),
        "skills": len(bundle.get("dialogue_skills", {}).get("skills", [])),
    }


def import_memory_bundle(path_text: str, replace: bool = False) -> str:
    path = Path(path_text.strip().strip('"')).expanduser()
    if not path.exists():
        return f"导入失败：文件不存在：{path}"
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"导入失败：无法读取 JSON：{exc}"
    if bundle.get("format") != "companion-ai-memory-bundle":
        return "导入失败：这不是 Companion AI 记忆导出包。"

    if replace:
        MEMORY_STORE.save(_normalize_memory(bundle.get("memory", {})))
        _write_sensitive_json(TRAINING_FILE, _normalize_training(bundle.get("training", {})))
        user_profile.save_user_profile(_normalize_user_profile(bundle.get("user_profile", {})))
        dialogue_skills.save_dialogue_skills(_normalize_dialogue_skills(bundle.get("dialogue_skills", {})))
        stats = _bundle_stats(bundle)
        return (
            "记忆已替换导入。\n"
            f"长期记忆：{stats['memory']} 条；训练样本：{stats['examples']} 条；"
            f"用户画像：{stats['profile']} 条；对话技能：{stats['skills']} 个"
        )

    before = _bundle_stats(_bundle())
    MEMORY_STORE.save(_merge_memory(MEMORY_STORE.load(), bundle.get("memory", {})))
    _write_sensitive_json(TRAINING_FILE, _merge_training(_read_json(TRAINING_FILE, _default_training()), bundle.get("training", {})))
    user_profile.save_user_profile(_merge_user_profile(user_profile.load_user_profile(), bundle.get("user_profile", {})))
    dialogue_skills.save_dialogue_skills(_merge_dialogue_skills(dialogue_skills.load_dialogue_skills(), bundle.get("dialogue_skills", {})))
    after = _bundle_stats(_bundle())
    return (
        "记忆已合并导入。\n"
        f"长期记忆：{before['memory']} -> {after['memory']} 条\n"
        f"训练样本：{before['examples']} -> {after['examples']} 条\n"
        f"用户画像：{before['profile']} -> {after['profile']} 条\n"
        f"对话技能：{before['skills']} -> {after['skills']} 个"
    )


def _normalize_memory(data: dict) -> dict:
    result = _default_memory()
    if isinstance(data, dict):
        for bucket in ("profile", "preferences", "facts"):
            result[bucket] = [item for item in data.get(bucket, []) if isinstance(item, dict)]
    return result


def _normalize_training(data: dict) -> dict:
    result = _default_training()
    if isinstance(data, dict):
        result["examples"] = [item for item in data.get("examples", []) if isinstance(item, dict)]
        result["feedback"] = [item for item in data.get("feedback", []) if isinstance(item, dict)]
    return result


def _normalize_user_profile(data: dict) -> dict:
    result = {
        "enabled": True,
        "updated_at": 0,
        "buckets": {key: [] for key in user_profile.BUCKETS},
    }
    if isinstance(data, dict):
        result.update({key: value for key, value in data.items() if key != "buckets"})
        buckets = result.setdefault("buckets", {})
        for bucket in user_profile.BUCKETS:
            source_items = data.get("buckets", {}).get(bucket, []) if isinstance(data.get("buckets", {}), dict) else []
            buckets[bucket] = [item for item in source_items if isinstance(item, dict)]
    return result


def _normalize_dialogue_skills(data: dict) -> dict:
    if not isinstance(data, dict):
        return {"skills": []}
    return {"skills": [item for item in data.get("skills", []) if isinstance(item, dict)]}


def _merge_memory(current: dict, incoming: dict) -> dict:
    current = _normalize_memory(current)
    incoming = _normalize_memory(incoming)
    for bucket in ("profile", "preferences", "facts"):
        _merge_list(current[bucket], incoming[bucket], ["text"])
    return current


def _merge_training(current: dict, incoming: dict) -> dict:
    current = _normalize_training(current)
    incoming = _normalize_training(incoming)
    _merge_list(current["examples"], incoming["examples"], ["prompt", "response", "source"])
    _merge_list(current["feedback"], incoming["feedback"], ["prompt", "response", "type", "rating"])
    return current


def _merge_user_profile(current: dict, incoming: dict) -> dict:
    current = _normalize_user_profile(current)
    incoming = _normalize_user_profile(incoming)
    current["enabled"] = bool(current.get("enabled", True))
    for bucket in user_profile.BUCKETS:
        _merge_list(current.setdefault("buckets", {}).setdefault(bucket, []), incoming.get("buckets", {}).get(bucket, []), ["text", "source"])
    return current


def _merge_dialogue_skills(current: dict, incoming: dict) -> dict:
    current = _normalize_dialogue_skills(current)
    incoming = _normalize_dialogue_skills(incoming)
    _merge_list(current["skills"], incoming["skills"], ["title", "response"])
    return current


def _merge_list(target: list[dict], incoming: list[dict], keys: list[str]) -> None:
    seen = {_signature(item, keys) for item in target}
    for item in incoming:
        sig = _signature(item, keys)
        if sig and sig not in seen:
            target.append(item)
            seen.add(sig)


def _signature(item: dict, keys: list[str]) -> str:
    parts = []
    for key in keys:
        value = item.get(key, "")
        parts.append(re.sub(r"\s+", " ", str(value)).strip())
    return "|".join(parts)


def handle_memory_transfer_command(message: str) -> str | None:
    if message == "/memory_export":
        return export_memory_bundle()
    if message.startswith("/memory_export_path "):
        return export_memory_bundle(message.removeprefix("/memory_export_path ").strip())
    if message.startswith("/memory_import_path "):
        return import_memory_bundle(message.removeprefix("/memory_import_path ").strip(), replace=False)
    if message.startswith("/memory_import_replace_path "):
        return import_memory_bundle(message.removeprefix("/memory_import_replace_path ").strip(), replace=True)
    return None
