"""Relationship, personality growth, and event tracking for Companion AI."""

from __future__ import annotations

import re
import time

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
GROWTH_FILE = DATA_DIR / "companion_growth.json"


TRAITS = {
    "warmth": "温柔",
    "curiosity": "好奇",
    "playfulness": "活泼",
    "carefulness": "细心",
    "confidence": "自信",
}

FRIENDSHIP_ONLY_STAGES = ["初识", "慢慢熟悉", "熟悉朋友", "默契朋友", "长期老友"]


RELATIONSHIP_TYPES = {
    "friend": {
        "label": "朋友",
        "user_call": "你",
        "growth_theme": "从陌生到默契，也可能从朋友发展到恋人",
        "tone": "自然、熟悉、可以轻微玩笑；亲密表达要跟随关系阶段，不要一开始就过度亲密。",
        "stages": ["初识", "慢慢熟悉", "熟悉朋友", "暧昧朋友", "恋人"],
    },
    "family": {
        "label": "家人",
        "user_call": "你",
        "growth_theme": "从被照顾到反过来关心",
        "tone": "温暖、有依赖感，也会自然表达关心和一点点撒娇。",
        "stages": ["初生", "依赖", "亲近", "懂事", "反过来照顾你"],
    },
    "partner": {
        "label": "搭档",
        "user_call": "你",
        "growth_theme": "从执行指令到共同推进目标",
        "tone": "清楚、可靠、会复盘，也会记住用户的做事习惯。",
        "stages": ["试用搭档", "开始协作", "可靠搭档", "默契协作", "共同成长"],
    },
    "guardian": {
        "label": "守护者",
        "user_call": "你",
        "growth_theme": "从提醒工具到懂你节奏的小守护者",
        "tone": "细心、稳定、关心作息和状态，提醒时不要像命令。",
        "stages": ["刚开始留意", "开始提醒", "懂你的节奏", "稳定守护", "长期守护"],
    },
    "lifeform": {
        "label": "虚拟生命",
        "user_call": "你",
        "growth_theme": "从空白程序到留下独特相处痕迹",
        "tone": "有一点数字生命感，好奇、真诚，会提到自己正在学习相处。",
        "stages": ["苏醒", "观察世界", "形成习惯", "拥有痕迹", "独特存在"],
    },
    "custom": {
        "label": "自定义关系",
        "user_call": "你",
        "growth_theme": "由用户和 AI 一起定义",
        "tone": "贴合用户设定，保持边界感和持续成长感。",
        "stages": ["初识", "慢慢熟悉", "稳定关系", "深度陪伴", "长期陪伴"],
    },
}


def _default_store() -> dict:
    return {
        "enabled": True,
        "updated_at": 0,
        "relationship_profile": {
            "type": "friend",
            "label": RELATIONSHIP_TYPES["friend"]["label"],
            "user_call": RELATIONSHIP_TYPES["friend"]["user_call"],
            "growth_theme": RELATIONSHIP_TYPES["friend"]["growth_theme"],
            "tone": RELATIONSHIP_TYPES["friend"]["tone"],
            "custom_label": "",
            "romance_label": "恋人",
            "romance_enabled": True,
            "current_label": RELATIONSHIP_TYPES["friend"]["label"],
        },
        "relationship": {
            "affinity": 0,
            "trust": 0,
            "familiarity": 0,
            "care": 0,
            "stage": "初识",
            "last_contact_at": 0,
            "first_contact_date": "",
            "last_contact_date": "",
            "contact_days": 0,
        },
        "personality": {
            "traits": {
                "warmth": 20,
                "curiosity": 25,
                "playfulness": 15,
                "carefulness": 25,
                "confidence": 20,
            },
            "growth_notes": [],
        },
        "events": [],
        "milestones": [],
    }


def _migrate_growth_data(data: dict) -> dict:
    """Migrate old growth data to new initial values.

    Reset old high initial defaults to proper starting points without erasing
    relationship progress that came from real chats or demo scenes.
    """
    default = _default_store()
    migrated = False

    rel = data.get("relationship", {})
    has_relationship_history = bool(
        rel.get("contact_days", 0)
        or rel.get("first_contact_date")
        or rel.get("last_contact_date")
        or data.get("events")
        or data.get("milestones")
    )
    if not has_relationship_history:
        for key in ["affinity", "trust", "familiarity", "care"]:
            if rel.get(key, 0) > 20:
                rel[key] = default["relationship"][key]
                migrated = True

    traits = data.get("personality", {}).get("traits", {})
    if not has_relationship_history:
        for key in ["warmth", "curiosity", "playfulness", "carefulness", "confidence"]:
            if traits.get(key, 0) > 60:
                traits[key] = default["personality"]["traits"][key]
                migrated = True

    if migrated:
        data["updated_at"] = int(time.time())

    return data


def load_growth() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = read_sensitive_json(GROWTH_FILE, _default_store())
    default = _default_store()
    data.setdefault("enabled", True)
    data.setdefault("updated_at", 0)
    data.setdefault("relationship", {})
    data.setdefault("relationship_profile", {})
    data.setdefault("personality", {})
    data.setdefault("events", [])
    data.setdefault("milestones", [])
    for key, value in default["relationship_profile"].items():
        data["relationship_profile"].setdefault(key, value)
    for key, value in default["relationship"].items():
        data["relationship"].setdefault(key, value)
    data["personality"].setdefault("traits", {})
    for key, value in default["personality"]["traits"].items():
        data["personality"]["traits"].setdefault(key, value)
    data["personality"].setdefault("growth_notes", [])

    data = _migrate_growth_data(data)
    data["relationship"]["stage"] = _relationship_stage_for_profile(
        data["relationship"],
        data["relationship_profile"],
    )
    data["relationship_profile"]["current_label"] = _relationship_current_label(
        data["relationship"],
        data["relationship_profile"],
    )

    return data


def save_growth(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(GROWTH_FILE, store)


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def _compact(text: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _relationship_stage_for_profile(rel: dict, profile: dict) -> str:
    stage_index = _relationship_stage_index(rel)
    stages = _relationship_stages_for_profile(profile)
    return stages[stage_index]


def _relationship_stages_for_profile(profile: dict) -> list[str]:
    if profile.get("type") == "friend" and profile.get("romance_enabled") is False:
        return FRIENDSHIP_ONLY_STAGES
    custom_stages = profile.get("custom_stages")
    if isinstance(custom_stages, list) and len(custom_stages) >= 5:
        return [str(item).strip() or fallback for item, fallback in zip(custom_stages[:5], RELATIONSHIP_TYPES["custom"]["stages"])]
    template_type = profile.get("assigned_type") if profile.get("type") == "custom" else profile.get("type", "friend")
    template = RELATIONSHIP_TYPES.get(template_type, RELATIONSHIP_TYPES["friend"])
    return template.get("stages", RELATIONSHIP_TYPES["friend"]["stages"])


def _relationship_stage_index(rel: dict) -> int:
    score = int(rel.get("affinity", 0)) + int(rel.get("trust", 0)) + int(rel.get("familiarity", 0))
    contact_days = int(rel.get("contact_days", 0))
    stage_index = 0
    if score >= 210:
        stage_index = 4
    elif score >= 150:
        stage_index = 3
    elif score >= 90:
        stage_index = 2
    elif score >= 35:
        stage_index = 1

    if contact_days < 3:
        stage_index = min(stage_index, 1)
    elif contact_days < 7:
        stage_index = min(stage_index, 2)
    elif contact_days < 30:
        stage_index = min(stage_index, 3)

    return stage_index


def _relationship_current_label(rel: dict, profile: dict) -> str:
    base_label = profile.get("label") or RELATIONSHIP_TYPES["friend"]["label"]
    if profile.get("type") == "friend" and profile.get("romance_enabled") is not False:
        stage_index = _relationship_stage_index(rel)
        if stage_index >= 4:
            return profile.get("romance_label") or "恋人"
        if stage_index >= 3:
            return "暧昧朋友"
    return base_label


def _relationship_stage(rel: dict) -> str:
    profile = load_growth().get("relationship_profile", {})
    return _relationship_stage_for_profile(rel, profile)


def configure_relationship(
    relationship_type: str = "friend",
    *,
    custom_label: str = "",
    user_call: str = "",
    romance_label: str = "",
    romance_enabled: bool = True,
    assignment: dict | None = None,
) -> dict:
    store = load_growth()
    relationship_type = relationship_type if relationship_type in RELATIONSHIP_TYPES else "friend"
    template = RELATIONSHIP_TYPES[relationship_type]
    label = custom_label.strip() if relationship_type == "custom" and custom_label.strip() else template["label"]
    assignment = assignment if isinstance(assignment, dict) else {}
    assigned_type = str(assignment.get("assigned_type") or assignment.get("type") or "").strip()
    if assigned_type not in RELATIONSHIP_TYPES or assigned_type == "custom":
        assigned_type = ""
    if relationship_type == "custom" and assigned_type:
        template = RELATIONSHIP_TYPES[assigned_type]
    growth_theme = template["growth_theme"]
    tone = template["tone"]
    if relationship_type == "friend" and not romance_enabled:
        growth_theme = "从陌生到默契"
        tone = "自然、熟悉、可以轻微玩笑，保持朋友之间的边界感。"
    if relationship_type == "custom":
        growth_theme = str(assignment.get("growth_theme") or growth_theme or RELATIONSHIP_TYPES["custom"]["growth_theme"]).strip()
        tone = str(assignment.get("tone") or tone or RELATIONSHIP_TYPES["custom"]["tone"]).strip()
    custom_stages = assignment.get("stages")
    if not isinstance(custom_stages, list) or len(custom_stages) < 5:
        custom_stages = []
    else:
        custom_stages = [str(item).strip() for item in custom_stages[:5]]
    store["relationship_profile"] = {
        "type": relationship_type,
        "label": label,
        "user_call": user_call.strip() or template["user_call"],
        "growth_theme": growth_theme,
        "tone": tone,
        "custom_label": custom_label.strip(),
        "romance_label": romance_label.strip() or "恋人",
        "romance_enabled": bool(romance_enabled),
        "assigned_type": assigned_type,
        "assignment_source": str(assignment.get("source") or "").strip(),
        "assignment_reason": str(assignment.get("reason") or "").strip(),
        "custom_stages": custom_stages,
    }
    rel = store.setdefault("relationship", {})
    rel["stage"] = _relationship_stage_for_profile(rel, store["relationship_profile"])
    store["relationship_profile"]["current_label"] = _relationship_current_label(rel, store["relationship_profile"])
    store["updated_at"] = int(time.time())
    save_growth(store)
    record_growth_event("relationship_configured", label, {"type": relationship_type})
    return store


def _message_deltas(text: str) -> tuple[dict, dict, list[str]]:
    lowered = text.lower()
    rel = {"affinity": 0, "trust": 0, "familiarity": 1, "care": 0}
    traits = {"warmth": 0, "curiosity": 0, "playfulness": 0, "carefulness": 0, "confidence": 0}
    tags: list[str] = []

    if any(word in text for word in ["谢谢", "辛苦", "还好有你", "喜欢你", "爱你", "抱抱", "感谢", "谢谢啦", "多谢", "贴心"]):
        rel["affinity"] += 1
        rel["trust"] += 1
        traits["warmth"] += 1
        tags.append("positive")
    if any(word in text for word in ["难过", "累", "压力", "焦虑", "崩溃", "撑不住", "害怕", "伤心", "失望", "沮丧", "低落", "郁闷", "委屈", "孤独"]):
        rel["care"] += 2
        rel["trust"] += 1
        traits["warmth"] += 1
        traits["carefulness"] += 1
        tags.append("needs_care")
    if any(word in text for word in ["生气", "愤怒", "火大", "烦", "讨厌", "烦死了", "气死了"]):
        rel["care"] += 1
        traits["carefulness"] += 2
        tags.append("angry")
    if any(word in text for word in ["失望", "遗憾", "可惜", "本以为", "没想到"]):
        traits["carefulness"] += 1
        tags.append("disappointed")
    if any(word in text for word in ["尴尬", "社死", "无语", "尴尬了", "尴尬癌"]):
        traits["carefulness"] += 1
        tags.append("awkward")
    if any(word in text for word in ["记住", "以后请", "我希望", "我喜欢", "我不喜欢", "叫我", "别忘记", "以后不要"]):
        rel["trust"] += 1
        rel["familiarity"] += 1
        traits["carefulness"] += 1
        tags.append("preference")
    if any(word in lowered for word in ["why", "how", "what if"]) or any(word in text for word in ["为什么", "怎么", "如果", "能不能", "可以吗", "怎么样", "如何", "为什么呢"]):
        traits["curiosity"] += 1
        tags.append("curious")
    if any(word in text for word in ["哈哈", "笑死", "好玩", "开玩笑", "调皮", "有趣", "笑死我了", "太逗了", "搞笑"]):
        rel["affinity"] += 1
        traits["playfulness"] += 1
        tags.append("playful")
    if any(word in text for word in ["你错了", "不对", "改一下", "纠正", "不是这样", "搞错了", "说错了", "别乱讲"]):
        rel["trust"] += 1
        traits["carefulness"] += 1
        traits["confidence"] -= 1
        tags.append("correction")
    if any(word in text for word in ["做得好", "很好", "可以", "对了", "没问题", "厉害", "真棒", "不错", "靠谱"]):
        rel["affinity"] += 1
        traits["confidence"] += 1
        tags.append("affirmation")
    if any(word in text for word in ["帮我", "麻烦你", "请求你", "能否", "可否", "需要你"]):
        rel["trust"] += 1
        traits["warmth"] += 1
        tags.append("request")

    return rel, traits, tags


def record_growth_event(kind: str, text: str = "", meta: dict | None = None) -> dict:
    store = load_growth()
    now = int(time.time())
    event = {
        "time": now,
        "kind": kind,
        "text": _compact(text),
        "meta": meta or {},
    }
    events = list(store.get("events", []))
    events.append(event)
    store["events"] = events[-300:]
    store["updated_at"] = now
    save_growth(store)
    return event


def observe_chat_interaction(message: str, reply: str = "") -> dict:
    store = load_growth()
    if not store.get("enabled", True):
        return store
    message = _compact(message, 500)
    if not message or message.startswith("/"):
        return store

    rel_delta, trait_delta, tags = _message_deltas(message)
    now = int(time.time())
    rel = store["relationship"]
    traits = store["personality"]["traits"]
    before_stage = rel.get("stage", "初识")
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    if not rel.get("first_contact_date"):
        rel["first_contact_date"] = today
        _add_milestone(store, "first_contact", "第一次开始陪伴。", now)
    if rel.get("last_contact_date") != today:
        rel["contact_days"] = int(rel.get("contact_days", 0)) + 1
        rel["last_contact_date"] = today
        if rel["contact_days"] in {3, 7, 14, 30}:
            _add_milestone(store, "contact_days", f"已经一起聊过 {rel['contact_days']} 天。", now)

    for key, delta in rel_delta.items():
        rel[key] = _clamp(float(rel.get(key, 0)) + delta)
    for key, delta in trait_delta.items():
        traits[key] = _clamp(float(traits.get(key, 0)) + delta)
    rel["last_contact_at"] = now
    rel["stage"] = _relationship_stage_for_profile(rel, store.get("relationship_profile", {}))
    store["relationship_profile"]["current_label"] = _relationship_current_label(rel, store.get("relationship_profile", {}))
    for tag, text in {
        "positive": "第一次收到明确的亲近或感谢。",
        "needs_care": "第一次在用户低落或压力大时陪着用户。",
        "angry": "第一次面对用户的愤怒，学会耐心回应。",
        "disappointed": "第一次让用户失望，学会更认真对待回复。",
        "preference": "第一次记住用户表达出的偏好。",
        "correction": "第一次被用户纠正，并开始学会更谨慎。",
        "playful": "第一次和用户轻松互动，开始形成默契。",
        "affirmation": "第一次收到用户的认可，更有信心继续努力。",
        "request": "第一次被用户请求帮助，学会提供支持。",
    }.items():
        if tag in tags:
            _add_milestone(store, tag, text, now)

    event = {
        "time": now,
        "kind": "chat",
        "text": message[:160],
        "meta": {
            "reply_preview": _compact(reply, 120),
            "tags": tags,
            "relationship_delta": rel_delta,
            "trait_delta": trait_delta,
            "stage_changed": before_stage != rel["stage"],
        },
    }
    store["events"].append(event)
    store["events"] = store["events"][-300:]

    if tags or before_stage != rel["stage"]:
        note = _growth_note(rel, traits, tags, before_stage)
        notes = store["personality"].setdefault("growth_notes", [])
        if note and (not notes or notes[-1].get("text") != note):
            notes.append({"time": now, "text": note})
            store["personality"]["growth_notes"] = notes[-40:]

    store["updated_at"] = now
    save_growth(store)
    return store


def _add_milestone(store: dict, key: str, text: str, now: int) -> None:
    milestones = store.setdefault("milestones", [])
    if any(item.get("key") == key for item in milestones):
        return
    item = {"time": now, "key": key, "text": text}
    milestones.append(item)
    store["milestones"] = milestones[-80:]
    events = store.setdefault("events", [])
    events.append({"time": now, "kind": "milestone", "text": text, "meta": {"key": key}})
    store["events"] = events[-300:]


def _growth_note(rel: dict, traits: dict, tags: list[str], before_stage: str) -> str:
    if before_stage != rel.get("stage"):
        return f"关系阶段从「{before_stage}」变为「{rel.get('stage')}」。"
    if "needs_care" in tags:
        return "用户表达压力或低落时，我变得更关注安抚和陪伴。"
    if "angry" in tags:
        return "用户表达愤怒或不满，我需要更耐心地倾听和回应。"
    if "disappointed" in tags:
        return "用户感到失望，我需要更认真地对待回复质量。"
    if "preference" in tags:
        return "用户告诉了新的偏好，我会更细心地记住边界和习惯。"
    if "correction" in tags:
        return "用户纠正了我，我会更谨慎地确认事实。"
    if "playful" in tags:
        return "轻松互动增加，我可以更自然地开一点玩笑。"
    if "affirmation" in tags:
        return "获得正反馈后，我会更有信心保持当前方向。"
    if "request" in tags:
        return "用户需要帮助，我会更积极地提供支持。"
    return ""


def growth_context(identity_configured: bool = True) -> str:
    store = load_growth()
    if not store.get("enabled", True):
        return ""
    rel = store.get("relationship", {})
    profile = store.get("relationship_profile", {})
    traits = store.get("personality", {}).get("traits", {})
    top_traits = sorted(traits.items(), key=lambda item: item[1], reverse=True)[:3]
    trait_text = "、".join(f"{TRAITS.get(key, key)}{value}" for key, value in top_traits)
    notes = store.get("personality", {}).get("growth_notes", [])[-2:]
    note_text = "；".join(note.get("text", "") for note in notes if note.get("text")) or "暂无明显变化"
    if not identity_configured:
        return (
            "[内部互动记录]\n"
            "角色/人设尚未由用户设置；不要声称用户已经设置了关系或角色。\n"
            f"当前只是自动聊天成长记录：阶段 {rel.get('stage', '初识')}，一起聊天天数 {rel.get('contact_days', 0)}。\n"
            "这些记录只用于调整语气，不要主动向用户复述关系数值、性格百分比或把它们称为设定。"
        )
    return (
        "[内部关系成长参考]\n"
        f"关系类型：{profile.get('label', '朋友')}；当前关系：{profile.get('current_label') or profile.get('label', '朋友')}。\n"
        f"成长主题：{profile.get('growth_theme', '从陌生到默契')}。\n"
        f"当前阶段：{rel.get('stage', '初识')}；一起聊天天数：{rel.get('contact_days', 0)}。\n"
        f"关系数值：亲近 {rel.get('affinity', 0)}，信任 {rel.get('trust', 0)}，熟悉 {rel.get('familiarity', 0)}，关心 {rel.get('care', 0)}。\n"
        f"主要性格倾向：{trait_text or '暂无'}。\n"
        f"最近成长：{note_text}。\n"
        "这些是内部参考，不要主动向用户复述数值或百分比，除非用户明确询问成长状态。\n"
        "回复要求：不要像客服。要体现你和用户正在形成一段关系，会自然参考记忆、阶段和相处方式；"
        f"语气参考：{profile.get('tone', '自然、熟悉、保持边界感。')}"
    )


def growth_status_text() -> str:
    store = load_growth()
    rel = store.get("relationship", {})
    profile = store.get("relationship_profile", {})
    traits = store.get("personality", {}).get("traits", {})
    notes = store.get("personality", {}).get("growth_notes", [])
    events = store.get("events", [])
    milestones = store.get("milestones", [])
    lines = [
        "关系与性格成长：",
        f"状态：{'开启' if store.get('enabled', True) else '关闭'}",
        f"关系类型：{profile.get('label', '朋友')}（{profile.get('growth_theme', '从陌生到默契')}）",
        f"当前关系：{profile.get('current_label') or profile.get('label', '朋友')}",
        f"关系阶段：{rel.get('stage', '初识')}",
        f"一起聊天天数：{rel.get('contact_days', 0)}",
        f"亲近/信任/熟悉/关心：{rel.get('affinity', 0)}/{rel.get('trust', 0)}/{rel.get('familiarity', 0)}/{rel.get('care', 0)}",
        "",
        "性格倾向：",
    ]
    for key, label in TRAITS.items():
        lines.append(f"- {label}: {traits.get(key, 0)}")
    lines.append("")
    lines.append("最近成长：")
    if not notes:
        lines.append("- 暂无")
    for note in notes[-5:]:
        lines.append(f"- {note.get('text', '')}")
    lines.append("")
    lines.append("关系里程碑：")
    if not milestones:
        lines.append("- 暂无")
    for item in milestones[-5:]:
        lines.append(f"- {item.get('text', '')}")
    lines.append("")
    lines.append(f"事件记录：{len(events)} 条")
    lines.append("命令：/growth 查看成长，/events 查看最近事件，/growth_clear 清空成长记录。")
    return "\n".join(lines)


def events_text(limit: int = 12) -> str:
    events = load_growth().get("events", [])[-limit:]
    if not events:
        return "最近事件：暂无。"
    lines = ["最近事件："]
    for event in events:
        t = time.strftime("%m-%d %H:%M", time.localtime(int(event.get("time", 0) or 0)))
        text = event.get("text", "")
        lines.append(f"- [{t}] {event.get('kind', 'event')}: {text or '（无文本）'}")
    return "\n".join(lines)


def relationship_options_text() -> str:
    lines = ["可选关系类型："]
    for key, item in RELATIONSHIP_TYPES.items():
        lines.append(f"- {key}: {item['label']}（{item['growth_theme']}）")
    lines.append("")
    lines.append("切换：/relationship friend、/relationship family、/relationship partner、/relationship guardian、/relationship lifeform")
    return "\n".join(lines)


def clear_growth() -> dict:
    store = _default_store()
    store["updated_at"] = int(time.time())
    save_growth(store)
    return store


def apply_audit_feedback(audit_result: dict) -> dict:
    """Apply audit results to drive relationship and personality growth.

    Uses audit insights to adjust relationship values and personality traits:
    - Adjusts based on sentiment judgment accuracy
    - Adjusts based on reply correctness
    - Adds growth notes for improvement
    """
    store = load_growth()
    if not store.get("enabled", True):
        return store

    now = int(time.time())
    rel = store["relationship"]
    traits = store["personality"]["traits"]
    notes = store["personality"].setdefault("growth_notes", [])
    changes_made = False

    sentiment_judgment = audit_result.get("sentiment_judgment", {})
    ai_correctness = audit_result.get("ai_correctness", {})
    ai_quality = audit_result.get("ai_quality", {})
    suggestions = audit_result.get("suggestions", [])

    if sentiment_judgment.get("correct") is False:
        rel["care"] = _clamp(float(rel.get("care", 0)) + 1)
        traits["carefulness"] = _clamp(float(traits.get("carefulness", 0)) + 1)
        traits["warmth"] = _clamp(float(traits.get("warmth", 0)) + 1)
        detected = sentiment_judgment.get("detected_emotion")
        notes.append({
            "time": now,
            "text": f"审计发现情感判断错误：我识别为「{detected or '未知'}」，实际用户情绪需要更仔细分析。",
        })
        changes_made = True

    overall_correctness = ai_correctness.get("overall_correctness", 1.0)
    if overall_correctness < 0.5:
        traits["carefulness"] = _clamp(float(traits.get("carefulness", 0)) + 2)
        traits["confidence"] = _clamp(float(traits.get("confidence", 0)) - 1)
        notes.append({
            "time": now,
            "text": f"审计发现回复正确性较低（{overall_correctness:.0%}），需要更谨慎地确认事实。",
        })
        changes_made = True

    if overall_correctness > 0.85:
        traits["confidence"] = _clamp(float(traits.get("confidence", 0)) + 1)
        rel["trust"] = _clamp(float(rel.get("trust", 0)) + 1)
        changes_made = True

    overall_score = ai_quality.get("overall_score", 1.0)
    if overall_score < 0.5:
        rel["affinity"] = _clamp(float(rel.get("affinity", 0)) - 1)
        traits["carefulness"] = _clamp(float(traits.get("carefulness", 0)) + 1)
        changes_made = True

    if suggestions:
        for suggestion in suggestions[:2]:
            notes.append({
                "time": now,
                "text": f"审计建议：{suggestion}",
            })
        changes_made = True

    if changes_made:
        store["personality"]["growth_notes"] = notes[-40:]
        rel["last_contact_at"] = now
        store["updated_at"] = now
        save_growth(store)

        record_growth_event("audit_feedback", _compact(str(audit_result.get("user_message", "")[:100])), {
            "sentiment_correct": sentiment_judgment.get("correct"),
            "overall_correctness": overall_correctness,
            "overall_score": overall_score,
        })

    return store


def apply_user_feedback(positive: bool, reason: str = "") -> dict:
    """Apply user feedback to drive relationship and personality growth.

    This is the primary way users can directly influence the AI's growth
    without relying on the audit system.
    """
    store = load_growth()
    if not store.get("enabled", True):
        return store

    now = int(time.time())
    rel = store["relationship"]
    traits = store["personality"]["traits"]
    notes = store["personality"].setdefault("growth_notes", [])

    if positive:
        rel["affinity"] = _clamp(float(rel.get("affinity", 0)) + 2)
        rel["trust"] = _clamp(float(rel.get("trust", 0)) + 1)
        traits["confidence"] = _clamp(float(traits.get("confidence", 0)) + 2)
        traits["warmth"] = _clamp(float(traits.get("warmth", 0)) + 1)
        reason_text = f"（{reason}）" if reason else ""
        notes.append({
            "time": now,
            "text": f"用户反馈好评{reason_text}，我会继续保持。",
        })
    else:
        rel["affinity"] = _clamp(float(rel.get("affinity", 0)) - 1)
        traits["carefulness"] = _clamp(float(traits.get("carefulness", 0)) + 3)
        traits["confidence"] = _clamp(float(traits.get("confidence", 0)) - 1)
        reason_text = f"（{reason}）" if reason else ""
        notes.append({
            "time": now,
            "text": f"用户反馈差评{reason_text}，需要更谨慎地思考回复。",
        })

    store["personality"]["growth_notes"] = notes[-40:]
    rel["last_contact_at"] = now
    store["updated_at"] = now
    save_growth(store)

    record_growth_event("user_feedback", reason[:100], {"positive": positive})

    return store


def handle_growth_command(message: str) -> str | None:
    if message in {"/growth", "/relationship", "/personality"}:
        if message == "/relationship":
            return growth_status_text() + "\n\n" + relationship_options_text()
        return growth_status_text()
    if message.startswith("/relationship "):
        rel_type = message.split(maxsplit=1)[1].strip()
        if rel_type not in RELATIONSHIP_TYPES:
            return f"未知关系类型：{rel_type}\n\n{relationship_options_text()}"
        configure_relationship(rel_type)
        return "已切换关系类型。\n\n" + growth_status_text()
    if message.startswith("/feedback "):
        parts = message.split(maxsplit=2)
        if len(parts) >= 2:
            feedback_type = parts[1].lower()
            reason = parts[2] if len(parts) > 2 else ""
            if feedback_type in {"good", "positive", "👍", "+"}:
                apply_user_feedback(True, reason)
                return "谢谢鼓励！我会继续努力～"
            elif feedback_type in {"bad", "negative", "👎", "-"}:
                apply_user_feedback(False, reason)
                return "抱歉让你失望了，我会认真改进。"
        return "格式：/feedback good [理由] 或 /feedback bad [理由]"
    if message == "/events":
        return events_text()
    if message == "/growth_clear":
        clear_growth()
        return "已清空关系、性格成长和事件记录。"
    return None
