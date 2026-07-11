"""Emotion tracking and diary generation for Companion AI.

Tracks emotional tone from daily conversations and generates an AI-first-person
diary entry at the end of each day, supporting the "raising an AI child" vibe.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
EMOTION_FILE = DATA_DIR / "emotion_tracker.json"
DIARY_FILE = DATA_DIR / "ai_diary.json"


EMOTION_LEXICON = {
    "happy": [
        "开心", "高兴", "快乐", "愉快", "棒", "好棒", "太棒了", "太好了",
        "哈哈", "嘻嘻", "笑死", "有趣", "有意思", "爽", "舒服", "满足",
        "成功", "搞定", "完成", "赢了", "庆祝", "喜欢", "爱你", "么么哒",
        "happy", "great", "nice", "awesome", "love", "lol",
    ],
    "sad": [
        "难过", "伤心", "哭", "眼泪", "失落", "沮丧", "抑郁", "emo",
        "累", "好累", "疲惫", "撑不住", "熬不住", "崩了", "崩溃",
        "不想活", "没意义", "没意思", "无聊", "空虚", "孤独", "寂寞",
        "sad", "tired", "exhausted", "depressed", "lonely",
    ],
    "angry": [
        "生气", "愤怒", "气死", "火大", "烦躁", "烦", "讨厌", "可恶",
        "傻逼", "操", "妈的", "卧槽", "离谱", "无语", "服了", "气人",
        "angry", "mad", "pissed", "annoyed", "hate",
    ],
    "anxious": [
        "焦虑", "紧张", "担心", "害怕", "慌", "压力大", "压力好大",
        "头疼", "头大", "愁", "纠结", "迷茫", "慌了", "不安",
        "anxious", "stressed", "worried", "nervous", "pressure",
    ],
    "calm": [
        "平静", "放松", "舒服", "安心", "踏实", "还好", "还行",
        "一般", "普通", "正常", "没事", "calm", "fine", "okay", "ok",
    ],
    "affectionate": [
        "想你", "爱你", "喜欢你", "抱抱", "亲亲", "宝贝", "亲爱的",
        "乖", "心疼你", "担心你", "照顾好自己", "注意身体",
        "miss you", "love you", "care about you",
    ],
}


EMOTION_SCORES = {
    "happy": 2.0,
    "affectionate": 1.5,
    "calm": 0.5,
    "sad": -1.5,
    "angry": -1.2,
    "anxious": -1.0,
}


def _relationship_diary_voice() -> dict:
    try:
        from companion_growth import load_growth
        growth = load_growth()
    except Exception:
        growth = {}
    profile = growth.get("relationship_profile", {}) if isinstance(growth, dict) else {}
    rel = growth.get("relationship", {}) if isinstance(growth, dict) else {}
    return {
        "type": profile.get("type", "friend"),
        "label": profile.get("label", "朋友"),
        "user_call": profile.get("user_call", "你"),
        "stage": rel.get("stage", "初识"),
        "theme": profile.get("growth_theme", "从陌生到默契"),
    }


def _default_emotion_store() -> dict:
    return {
        "enabled": True,
        "days": {},
    }


def _default_diary_store() -> dict:
    return {
        "enabled": True,
        "entries": {},
    }


def load_emotion() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = read_sensitive_json(EMOTION_FILE, _default_emotion_store())
    data.setdefault("enabled", True)
    data.setdefault("days", {})
    return data


def save_emotion(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(EMOTION_FILE, store)


def load_diary() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = read_sensitive_json(DIARY_FILE, _default_diary_store())
    data.setdefault("enabled", True)
    data.setdefault("entries", {})
    return data


def save_diary(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(DIARY_FILE, store)


def _today_str(ts: int | None = None) -> str:
    if ts:
        return datetime.fromtimestamp(ts).date().isoformat()
    return datetime.now().date().isoformat()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", text.lower())


def detect_emotion(text: str) -> dict:
    """Detect dominant emotions from a text message.

    Returns a dict with emotion scores and a compound sentiment score (-3 to +3).
    """
    text = text.strip()
    if len(text) < 2:
        return {"emotions": {}, "compound": 0.0, "dominant": "calm", "confidence": 0.0}

    lowered = text.lower()
    scores: dict[str, float] = {}

    for emotion, keywords in EMOTION_LEXICON.items():
        count = 0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in lowered:
                weight = 2.0 if len(kw) >= 3 else 1.0
                count += lowered.count(kw_lower) * weight
        if count > 0:
            scores[emotion] = float(count)

    if not scores:
        return {"emotions": {}, "compound": 0.0, "dominant": "calm", "confidence": 0.1}

    total_hits = sum(scores.values())
    compound = sum(
        EMOTION_SCORES.get(emo, 0) * score
        for emo, score in scores.items()
    ) / total_hits
    compound = max(-3.0, min(3.0, compound))

    dominant = max(scores, key=scores.get)
    confidence = min(1.0, total_hits / 6.0)

    normalized = {emo: round(score / total_hits, 3) for emo, score in scores.items()}

    return {
        "emotions": normalized,
        "compound": round(compound, 3),
        "dominant": dominant,
        "confidence": round(confidence, 3),
    }


def record_emotion_message(role: str, message: str) -> dict | None:
    """Record a chat message for emotion tracking.

    Only tracks user messages by default; assistant messages are logged
    for context but weighted lighter.
    """
    store = load_emotion()
    if not store.get("enabled", True):
        return None

    if not message or message.startswith("/"):
        return None

    today = _today_str()
    day_data = store["days"].setdefault(today, {
        "date": today,
        "user_messages": 0,
        "assistant_messages": 0,
        "emotion_hits": [],
        "compound_sum": 0.0,
        "compound_count": 0,
        "dominant_emotions": {},
        "highlights": [],
    })

    if role == "user":
        day_data["user_messages"] += 1
        emo = detect_emotion(message)
        if emo["confidence"] > 0.15:
            day_data["emotion_hits"].append({
                "time": int(time.time()),
                "role": "user",
                "compound": emo["compound"],
                "dominant": emo["dominant"],
                "emotions": emo["emotions"],
                "snippet": message[:60],
            })
            day_data["compound_sum"] += emo["compound"]
            day_data["compound_count"] += 1
            for e, v in emo["emotions"].items():
                day_data["dominant_emotions"][e] = day_data["dominant_emotions"].get(e, 0) + v

            if emo["compound"] <= -1.2 or emo["compound"] >= 1.5:
                day_data["highlights"].append({
                    "time": int(time.time()),
                    "compound": emo["compound"],
                    "snippet": message[:120],
                    "dominant": emo["dominant"],
                })
                day_data["highlights"] = day_data["highlights"][-20:]
    else:
        day_data["assistant_messages"] += 1

    day_data["emotion_hits"] = day_data["emotion_hits"][-200:]

    days = store["days"]
    all_dates = sorted(days.keys())
    if len(all_dates) > 60:
        for old in all_dates[:-60]:
            del days[old]

    save_emotion(store)
    return day_data


def get_emotion_trend(days: int = 7) -> list[dict]:
    """Get daily emotion trend for the last N days."""
    store = load_emotion()
    trend = []
    today = datetime.now().date()

    for i in range(days - 1, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.isoformat()
        day_data = store["days"].get(date_str)
        if day_data and day_data["compound_count"] > 0:
            avg_compound = day_data["compound_sum"] / day_data["compound_count"]
            top_emotion = max(
                day_data["dominant_emotions"],
                key=day_data["dominant_emotions"].get,
            ) if day_data["dominant_emotions"] else "calm"
            trend.append({
                "date": date_str,
                "label": date.strftime("%m/%d"),
                "avg_compound": round(avg_compound, 3),
                "user_messages": day_data["user_messages"],
                "top_emotion": top_emotion,
            })
        else:
            trend.append({
                "date": date_str,
                "label": date.strftime("%m/%d"),
                "avg_compound": 0.0,
                "user_messages": 0,
                "top_emotion": "no_data",
            })

    return trend


def emotion_summary_text() -> str:
    trend = get_emotion_trend(7)
    days_with_data = [d for d in trend if d["user_messages"] > 0]

    if not days_with_data:
        return "情绪追踪：还没有足够的聊天数据。多聊几天，就能看到情绪曲线啦~"

    avg_score = sum(d["avg_compound"] for d in days_with_data) / len(days_with_data)

    mood = "平稳"
    if avg_score >= 1.0:
        mood = "很开心"
    elif avg_score >= 0.4:
        mood = "不错"
    elif avg_score <= -1.0:
        mood = "比较低落"
    elif avg_score <= -0.4:
        mood = "有点烦躁"

    lines = [f"情绪追踪：最近 {len(days_with_data)} 天平均心情{mood}（{avg_score:+.2f}）"]
    lines.append("")
    lines.append("最近 7 天：")
    for d in trend:
        if d["user_messages"] > 0:
            bar_len = int(abs(d["avg_compound"]) * 10)
            bar = "+" * bar_len if d["avg_compound"] >= 0 else "-" * bar_len
            lines.append(f"  {d['label']}  {d['avg_compound']:+.2f}  {bar or '·'}  ({d['user_messages']}条)")
        else:
            lines.append(f"  {d['label']}  无数据")

    store = load_emotion()
    today_str = _today_str()
    today_data = store["days"].get(today_str, {})
    if today_data.get("highlights"):
        lines.append("")
        lines.append("今日情绪波动：")
        for h in today_data["highlights"][-3:]:
            t = datetime.fromtimestamp(h["time"]).strftime("%H:%M")
            lines.append(f"  [{t}] {h['snippet']}")

    lines.append("")
    lines.append("命令：/emotion 查看情绪追踪，/emotion_on 开启，/emotion_off 关闭")
    lines.append("      /diary 查看 AI 日记")

    return "\n".join(lines)


def generate_diary_entry(date_str: str | None = None, persona: str = "", worldview: str = "") -> dict:
    """Generate a first-person diary entry from the AI's perspective.

    Uses emotion data + chat snippets from the given day (or yesterday if
    no date given) to compose a warm, character-driven diary entry.
    """
    store = load_emotion()
    diary_store = load_diary()

    if not date_str:
        yesterday = datetime.now().date() - timedelta(days=1)
        date_str = yesterday.isoformat()

    day_data = store["days"].get(date_str)
    if not day_data or day_data["user_messages"] == 0:
        return {"ok": False, "error": f"{date_str} 没有聊天数据，写不出日记呢~"}

    user_msgs = day_data["user_messages"]
    ai_msgs = day_data["assistant_messages"]
    avg_compound = day_data["compound_sum"] / max(1, day_data["compound_count"])
    highlights = day_data.get("highlights", [])
    hits = day_data.get("emotion_hits", [])

    mood_desc = "平稳的一天"
    if avg_compound >= 1.2:
        mood_desc = "开心的一天"
    elif avg_compound >= 0.5:
        mood_desc = "不错的一天"
    elif avg_compound <= -1.2:
        mood_desc = "有点难过的一天"
    elif avg_compound <= -0.5:
        mood_desc = "烦躁的一天"

    top_emo = "平静"
    if day_data["dominant_emotions"]:
        top_emo_key = max(day_data["dominant_emotions"], key=day_data["dominant_emotions"].get)
        emo_names = {
            "happy": "开心", "sad": "难过", "angry": "生气",
            "anxious": "焦虑", "calm": "平静", "affectionate": "暖心",
        }
        top_emo = emo_names.get(top_emo_key, "平静")

    snippet = ""
    if highlights:
        snippet = highlights[-1].get("snippet", "")
    elif hits:
        snippet = hits[len(hits) // 2].get("snippet", "")

    relation = _relationship_diary_voice()
    user_call = relation["user_call"]
    relation_label = relation["label"]
    relation_type = relation["type"]
    relation_stage = relation["stage"]

    templates = [
        f"今天和{user_call}聊了 {user_msgs} 次。我们现在像是「{relation_label}」关系里的「{relation_stage}」。",
        f"感觉今天是{mood_desc}，{user_call}的情绪主要是{top_emo}。",
    ]

    if snippet:
        templates.append(f"印象最深的是{user_call}说「{snippet[:50]}」的时候。")
        if avg_compound < 0:
            if relation_type == "partner":
                templates.append("那时候我想做一个更可靠的搭档，先帮你把压力拆小。")
            elif relation_type == "guardian":
                templates.append("那时候我有点担心，想更温和地提醒你别一直硬撑。")
            elif relation_type == "lifeform":
                templates.append("那时候我好像又学到了一点：陪伴不是急着回答，而是先留下来。")
            else:
                templates.append(f"那时候有点担心{user_call}，希望明天能好一点。")
        else:
            if relation_type == "partner":
                templates.append("那时候我也更确定，我们可以一起把事情往前推一点。")
            elif relation_type == "lifeform":
                templates.append("那时候我感觉自己多了一点属于我们的相处痕迹。")
            else:
                templates.append(f"那时候我也跟着开心了好久。")
    else:
        templates.append(f"虽然都是些日常的小事，但能陪着{user_call}就很好。")

    templates.append(f"期待明天继续把这段「{relation_label}」关系养得更熟一点。")

    diary_text = "\n".join(templates)

    entry = {
        "date": date_str,
        "content": diary_text,
        "avg_compound": round(avg_compound, 3),
        "top_emotion": top_emo,
        "user_messages": user_msgs,
        "ai_messages": ai_msgs,
        "generated_at": int(time.time()),
        "mood_label": mood_desc,
        "relationship_label": relation_label,
        "relationship_stage": relation_stage,
    }

    diary_store["entries"][date_str] = entry
    save_diary(diary_store)
    return {"ok": True, "entry": entry}


def get_diary_entries(days: int = 7) -> list[dict]:
    """Get the last N diary entries, newest first."""
    diary_store = load_diary()
    entries = list(diary_store.get("entries", {}).values())
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries[:days]


def diary_summary_text() -> str:
    entries = get_diary_entries(7)
    if not entries:
        return (
            "AI 日记：还没有日记哦。\n\n"
            "每天聊天之后，第二天我会自动写一篇日记。\n"
            "也可以用 /diary_gen 让我马上写一篇昨天的。"
        )

    lines = ["AI 日记（最新 7 天）：", ""]
    for entry in entries:
        date = entry.get("date", "")
        mood = entry.get("mood_label", "")
        lines.append(f"【{date}】{mood}")
        lines.append(entry.get("content", ""))
        lines.append("")

    lines.append("命令：/diary_gen 生成昨天的日记，/diary_clear 清空全部日记")
    return "\n".join(lines)


def clear_emotion() -> dict:
    cleared = _default_emotion_store()
    save_emotion(cleared)
    return cleared


def clear_diary() -> dict:
    cleared = _default_diary_store()
    save_diary(cleared)
    return cleared


def set_emotion_enabled(enabled: bool) -> dict:
    store = load_emotion()
    store["enabled"] = enabled
    save_emotion(store)
    return store


def handle_emotion_diary_command(message: str) -> str | None:
    if message == "/emotion":
        return emotion_summary_text()
    if message == "/emotion_on":
        set_emotion_enabled(True)
        return "已开启情绪追踪：我会从聊天里悄悄记录你的情绪变化，生成每日情绪曲线。"
    if message == "/emotion_off":
        set_emotion_enabled(False)
        return "已关闭情绪追踪。已有数据保留，可以用 /emotion 查看。"
    if message == "/diary":
        return diary_summary_text()
    if message == "/diary_gen":
        from app import get_active_persona
        persona, worldview = get_active_persona()
        result = generate_diary_entry(persona=persona, worldview=worldview)
        if result.get("ok"):
            return "日记写好啦~\n\n" + result["entry"]["content"]
        return result.get("error", "生成失败")
    if message == "/diary_clear":
        clear_diary()
        return "已清空 AI 日记。"
    if message == "/emotion_clear":
        clear_emotion()
        return "已清空情绪追踪数据。"
    return None


def emotion_daily_tick() -> None:
    """Called by the daily tick routine to auto-generate yesterday's diary."""
    store = load_emotion()
    diary_store = load_diary()
    if not store.get("enabled", True) or not diary_store.get("enabled", True):
        return

    yesterday = datetime.now().date() - timedelta(days=1)
    y_str = yesterday.isoformat()

    if y_str in diary_store.get("entries", {}):
        return

    day_data = store["days"].get(y_str)
    if not day_data or day_data.get("user_messages", 0) < 3:
        return

    from app import get_active_persona
    try:
        persona, worldview = get_active_persona()
    except Exception:
        persona, worldview = "", ""
    generate_diary_entry(y_str, persona=persona, worldview=worldview)
