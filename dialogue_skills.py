"""User-defined dialogue skills for Companion AI."""

from __future__ import annotations

import re
import time
from pathlib import Path

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
SKILLS_FILE = DATA_DIR / "dialogue_skills.json"


def _default_store() -> dict:
    return {"skills": []}


def load_dialogue_skills() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = read_sensitive_json(SKILLS_FILE, _default_store())
    data.setdefault("skills", [])
    return data


def save_dialogue_skills(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(SKILLS_FILE, store)


def _skill_id(title: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", title.strip()).strip("-").lower()
    return (safe[:28] or "skill") + "-" + str(int(time.time()))[-6:]


def _split_triggers(text: str) -> list[str]:
    parts = re.split(r"[,，;；、|]", text)
    triggers = []
    for part in parts:
        item = re.sub(r"\s+", " ", part).strip()
        if item and item not in triggers:
            triggers.append(item[:40])
    return triggers[:12]


def add_dialogue_skill(title: str, triggers_text: str, response: str) -> dict:
    title = re.sub(r"\s+", " ", title).strip()[:60]
    triggers = _split_triggers(triggers_text)
    response = response.strip()[:2000]
    if not title or not triggers or not response:
        return {"ok": False, "error": "格式：/learn_skill 技能名 => 触发词1,触发词2 => 回复内容"}

    store = load_dialogue_skills()
    skill = {
        "id": _skill_id(title),
        "title": title,
        "triggers": triggers,
        "response": response,
        "created_at": int(time.time()),
        "usage_count": 0,
    }
    store["skills"].append(skill)
    save_dialogue_skills(store)
    return {"ok": True, "skill": skill}


def delete_dialogue_skill(skill_id: str) -> bool:
    store = load_dialogue_skills()
    before = len(store.get("skills", []))
    store["skills"] = [skill for skill in store.get("skills", []) if skill.get("id") != skill_id]
    if len(store["skills"]) == before:
        return False
    save_dialogue_skills(store)
    return True


def list_dialogue_skills_text(limit: int = 30) -> str:
    skills = load_dialogue_skills().get("skills", [])
    if not skills:
        return (
            "对话技能：暂无。\n\n"
            "添加格式：/learn_skill 技能名 => 触发词1,触发词2 => 回复内容\n"
            "例：/learn_skill 睡前复盘 => 睡前复盘,复盘一下 => 我们按今天完成了什么、卡在哪里、明天最小一步来整理。"
        )
    lines = [f"对话技能：共 {len(skills)} 个"]
    for skill in skills[-limit:]:
        lines.append(
            f"- {skill.get('title')} [{skill.get('id')}]\n"
            f"  触发：{', '.join(skill.get('triggers', []))}\n"
            f"  使用：{skill.get('usage_count', 0)} 次"
        )
    lines.append("")
    lines.append("删除：/delete_skill 技能ID")
    return "\n".join(lines)


def match_dialogue_skill(message: str) -> dict | None:
    text = message.strip().lower()
    if not text or text.startswith("/"):
        return None
    store = load_dialogue_skills()
    best: dict | None = None
    best_score = 0
    for skill in store.get("skills", []):
        for trigger in skill.get("triggers", []):
            trig = str(trigger).strip().lower()
            if not trig:
                continue
            score = 0
            if trig in text:
                score = len(trig) + 10
            elif len(trig) >= 4 and _token_overlap(trig, text) >= 0.6:
                score = len(trig)
            if score > best_score:
                best = skill
                best_score = score
    if not best:
        return None
    best["usage_count"] = int(best.get("usage_count", 0)) + 1
    save_dialogue_skills(store)
    return best


def _token_overlap(trigger: str, message: str) -> float:
    def tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", value.lower()))

    left = tokens(trigger)
    right = tokens(message)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def skill_reply(skill: dict, profile_context: str = "") -> str:
    response = str(skill.get("response", "")).strip()
    if "{profile}" in response:
        response = response.replace("{profile}", profile_context or "暂无用户画像")
    return f"我调用了对话技能「{skill.get('title', '')}」：\n{response}"


def handle_dialogue_skill_command(message: str) -> str | None:
    if message in {"/skills", "/dialogue_skills"}:
        return list_dialogue_skills_text()
    if message.startswith("/learn_skill ") or message.startswith("/learn_dialog_skill "):
        body = message.split(maxsplit=1)[1].strip() if len(message.split(maxsplit=1)) > 1 else ""
        parts = [part.strip() for part in body.split("=>", 2)]
        if len(parts) != 3:
            return "格式：/learn_skill 技能名 => 触发词1,触发词2 => 回复内容"
        result = add_dialogue_skill(parts[0], parts[1], parts[2])
        if not result.get("ok"):
            return result.get("error", "添加失败")
        skill = result["skill"]
        return f"已添加对话技能「{skill['title']}」。\nID：{skill['id']}\n触发词：{', '.join(skill['triggers'])}"
    if message.startswith("/delete_skill ") or message.startswith("/delete_dialog_skill "):
        skill_id = message.split(maxsplit=1)[1].strip() if len(message.split(maxsplit=1)) > 1 else ""
        if not skill_id:
            return "格式：/delete_skill 技能ID"
        return "已删除对话技能。" if delete_dialogue_skill(skill_id) else f"没有找到对话技能：{skill_id}"
    return None
