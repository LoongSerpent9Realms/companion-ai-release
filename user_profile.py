"""User profile memory for Companion AI.

This module keeps a small local profile inferred from ordinary chat. It is
separate from action skills and training examples so the user can inspect,
pause, or clear it without disturbing learned replies.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
PROFILE_FILE = DATA_DIR / "user_profile.json"


BUCKETS = {
    "identity": "身份/称呼",
    "preferences": "偏好",
    "communication": "沟通风格",
    "projects": "项目/目标",
    "routines": "习惯/日程",
}

SENSITIVE_HINTS = [
    "密码",
    "验证码",
    "密钥",
    "token",
    "api key",
    "apikey",
    "secret",
    "身份证",
    "银行卡",
    "手机号",
    "电话",
]


def _default_store() -> dict:
    return {
        "enabled": True,
        "updated_at": 0,
        "buckets": {key: [] for key in BUCKETS},
    }


def load_user_profile() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = read_sensitive_json(PROFILE_FILE, _default_store())
    data.setdefault("enabled", True)
    data.setdefault("updated_at", 0)
    buckets = data.setdefault("buckets", {})
    for key in BUCKETS:
        buckets.setdefault(key, [])
    return data


def save_user_profile(profile: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(PROFILE_FILE, profile)


def set_profile_enabled(enabled: bool) -> dict:
    profile = load_user_profile()
    profile["enabled"] = enabled
    profile["updated_at"] = int(time.time())
    save_user_profile(profile)
    return profile


def clear_user_profile() -> dict:
    profile = load_user_profile()
    enabled = bool(profile.get("enabled", True))
    cleared = _default_store()
    cleared["enabled"] = enabled
    cleared["updated_at"] = int(time.time())
    save_user_profile(cleared)
    return cleared


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in SENSITIVE_HINTS)


def _compact(text: str, limit: int = 140) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _candidate_items(message: str) -> list[tuple[str, str, str]]:
    msg = _compact(message, 300)
    lowered = msg.lower()
    items: list[tuple[str, str, str]] = []

    if any(key in msg for key in ["我叫", "叫我", "我是", "我的名字"]):
        items.append(("identity", msg, "self_disclosure"))
    if any(key in msg for key in ["我喜欢", "我偏好", "我更喜欢", "我不喜欢", "我希望", "以后请", "回答时", "用中文", "别太"]):
        bucket = "communication" if any(key in msg for key in ["回答", "语气", "中文", "简短", "详细", "先给结论", "别太"]) else "preferences"
        items.append((bucket, msg, "preference"))
    if any(key in msg for key in ["我的项目", "我在做", "我正在做", "目标是", "我要做", "计划做"]):
        items.append(("projects", msg, "project"))
    if any(key in msg for key in ["每天", "每周", "通常", "经常", "下班", "上课", "工作时间"]) or "routine" in lowered:
        items.append(("routines", msg, "routine"))
    if any(key in lowered for key in ["prefer", "i like", "i want you to", "call me"]):
        items.append(("preferences", msg, "preference"))

    return items[:4]


def observe_user_message(message: str) -> list[dict]:
    """Extract lightweight profile facts from one user message."""
    profile = load_user_profile()
    if not profile.get("enabled", True):
        return []
    message = _compact(message, 500)
    if len(message) < 4 or message.startswith("/"):
        return []
    if _is_sensitive(message):
        return []

    added: list[dict] = []
    now = int(time.time())
    buckets = profile.setdefault("buckets", {})
    for bucket, text, source in _candidate_items(message):
        entries = buckets.setdefault(bucket, [])
        if any(item.get("text") == text for item in entries):
            continue
        item = {"time": now, "text": text, "source": source, "confidence": 0.65}
        entries.append(item)
        del entries[:-30]
        added.append({"bucket": bucket, **item})

    if added:
        profile["updated_at"] = now
        save_user_profile(profile)
    return added


def profile_summary(limit_per_bucket: int = 5) -> str:
    profile = load_user_profile()
    lines = [f"用户画像：{'开启' if profile.get('enabled', True) else '已暂停'}"]
    for bucket, label in BUCKETS.items():
        lines.append(f"{label}：")
        items = profile.get("buckets", {}).get(bucket, [])[-limit_per_bucket:]
        if not items:
            lines.append("- 暂无")
        for item in items:
            lines.append(f"- {item.get('text', '')}")
    lines.append("")
    lines.append("命令：/profile_on 开启画像，/profile_off 暂停画像，/profile_clear 清空画像。")
    return "\n".join(lines)


def profile_context(limit_per_bucket: int = 3) -> str:
    profile = load_user_profile()
    if not profile.get("enabled", True):
        return ""
    parts: list[str] = []
    for bucket, label in BUCKETS.items():
        items = [item.get("text", "") for item in profile.get("buckets", {}).get(bucket, [])[-limit_per_bucket:] if item.get("text")]
        if items:
            parts.append(f"{label}: " + "；".join(items))
    if not parts:
        return ""
    return "已知用户画像（仅来自本地聊天推断，可用 /profile 管理）：\n" + "\n".join(parts)


def set_user_address(name: str) -> str:
    """Directly set the user's preferred address in the identity bucket."""
    profile = load_user_profile()
    buckets = profile.setdefault("buckets", {})
    entries = buckets.setdefault("identity", [])
    now = int(time.time())
    # Remove any existing address entries that look like names
    entries[:] = [
        e for e in entries
        if not any(kw in e.get("text", "") for kw in ["我叫", "叫我", "我的名字是", "我是"])
    ]
    entries.append({"time": now, "text": f"叫我{name}", "source": "user_command", "confidence": 1.0})
    profile["updated_at"] = now
    save_user_profile(profile)
    return name


def handle_profile_command(message: str) -> str | None:
    if message == "/profile":
        return profile_summary()
    if message == "/profile_on":
        set_profile_enabled(True)
        return "已开启用户画像：我会从普通聊天里提炼称呼、偏好、项目目标和沟通风格。敏感信息不会写入画像。"
    if message == "/profile_off":
        set_profile_enabled(False)
        return "已暂停用户画像：之后普通聊天不会再写入画像，已有画像仍可用 /profile 查看或 /profile_clear 清空。"
    if message == "/profile_clear":
        clear_user_profile()
        return "已清空用户画像。"
    if message.startswith("/name "):
        name = message[6:].strip()
        if not name or len(name) > 20:
            return "请提供一个有效的称呼（1-20个字符）。例如：/name 主人"
        set_user_address(name)
        return f"已设置称呼为「{name}」，之后我会用这个称呼来叫你。"
    return None


def get_user_preferred_address() -> str | None:
    """Extract how the user prefers to be called from identity bucket.

    Returns the most recent identity text (e.g., "叫我小明", "我叫李华"),
    stripped to just the name part, or None if not set.
    """
    profile = load_user_profile()
    if not profile.get("enabled", True):
        return None
    identity_items = profile.get("buckets", {}).get("identity", [])
    if not identity_items:
        return None
    # Take the most recent identity item
    latest = identity_items[-1] if identity_items else None
    if not latest:
        return None
    text = latest.get("text", "")
    # Extract name from patterns like "我叫X", "叫我X", "我的名字是X"
    patterns = [
        r"(?:我叫|叫我|我的名字是|我是)\s*([^\s，。；,.\!！？?]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            if name and len(name) <= 20:
                return name
    return None


def get_ai_address_to_user() -> str:
    """Return the address prefix AI should use for the user.

    Examples: "小明", "李华", or empty string if not set.
    """
    name = get_user_preferred_address()
    return name or ""
