"""User-taught behavior rules for Companion AI."""

from __future__ import annotations

import re
import time

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
RULES_FILE = DATA_DIR / "procedural_rules.json"

WEB_ACTION_MARKERS = {
    "联网",
    "搜索",
    "核实",
    "最新",
    "查资料",
    "查一下",
    "联网确认",
    "公开资料",
    "官网",
    "新闻",
    "网上",
    "网页",
    "web",
    "search",
}

SHORT_ACK_MESSAGES = {
    "哦",
    "噢",
    "喔",
    "嗯",
    "恩",
    "啊",
    "呀",
    "好",
    "好的",
    "行",
    "可以",
    "对",
    "是",
    "不是",
    "没事",
    "收到",
    "明白",
    "懂了",
    "ok",
    "okay",
}


def _default_store() -> dict:
    return {"rules": []}


def load_procedural_rules() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = read_sensitive_json(RULES_FILE, _default_store())
    data.setdefault("rules", [])
    for rule in data.get("rules", []):
        instruction = str(rule.get("instruction", ""))
        if instruction:
            rule["action"] = infer_action(instruction)
    return data


def save_procedural_rules(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(RULES_FILE, store)


def _rule_id(title: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", title.strip()).strip("-").lower()
    return (safe[:28] or "rule") + "-" + str(int(time.time()))[-6:]


def _split_triggers(text: str) -> list[str]:
    parts = re.split(r"[,，;；、|]", text)
    triggers = []
    for part in parts:
        item = re.sub(r"\s+", " ", part).strip()
        if item and item not in triggers:
            triggers.append(item[:40])
    return triggers[:24]


def infer_action(action_text: str) -> str:
    lowered = action_text.strip().lower()
    if any(marker in lowered for marker in WEB_ACTION_MARKERS):
        return "web_search"
    return "instruction"


def add_procedural_rule(title: str, triggers_text: str, action_text: str) -> dict:
    title = re.sub(r"\s+", " ", title).strip()[:80]
    triggers = _split_triggers(triggers_text)
    action_text = action_text.strip()[:2000]
    if not title or not triggers or not action_text:
        return {
            "ok": False,
            "error": "格式：/teach_rule 规则名 => 触发词1,触发词2 => 动作说明",
        }

    store = load_procedural_rules()
    rule = {
        "id": _rule_id(title),
        "title": title,
        "triggers": triggers,
        "action": infer_action(action_text),
        "instruction": action_text,
        "created_at": int(time.time()),
        "usage_count": 0,
    }
    store["rules"].append(rule)
    save_procedural_rules(store)
    return {"ok": True, "rule": rule}


def delete_procedural_rule(rule_id: str) -> bool:
    store = load_procedural_rules()
    before = len(store.get("rules", []))
    store["rules"] = [rule for rule in store.get("rules", []) if rule.get("id") != rule_id]
    if len(store["rules"]) == before:
        return False
    save_procedural_rules(store)
    return True


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", value.lower()))


def _token_overlap(trigger: str, message: str) -> float:
    left = _tokens(trigger)
    right = _tokens(message)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def _normalize_short_message(value: str) -> str:
    return re.sub(r"[\s，。！？、,.!?;；:：~～…]+", "", value.strip().lower())


def match_procedural_rule(message: str) -> dict | None:
    text = message.strip().lower()
    if not text or text.startswith("/"):
        return None
    if _normalize_short_message(text) in SHORT_ACK_MESSAGES:
        return None

    store = load_procedural_rules()
    best: dict | None = None
    best_score = 0.0
    for rule in store.get("rules", []):
        for trigger in rule.get("triggers", []):
            trig = str(trigger).strip().lower()
            if not trig:
                continue
            score = 0.0
            if trig in text:
                score = len(trig) + 10
            elif len(trig) >= 4:
                overlap = _token_overlap(trig, text)
                if overlap >= 0.6:
                    score = len(trig) * overlap
            if score > best_score:
                best = rule
                best_score = score

    if not best:
        return None

    best["usage_count"] = int(best.get("usage_count", 0)) + 1
    save_procedural_rules(store)
    return dict(best)


def list_procedural_rules_text(limit: int = 30) -> str:
    rules = load_procedural_rules().get("rules", [])
    if not rules:
        return (
            "行为规则：暂无。\n\n"
            "添加格式：/teach_rule 规则名 => 触发词1,触发词2 => 动作说明\n"
            "例：/teach_rule 时效联网 => 最新,最近,现在,今年,目前,新进展 => 先联网搜索并给出来源。"
        )
    lines = [f"行为规则：共 {len(rules)} 条"]
    for rule in rules[-limit:]:
        lines.append(
            f"- {rule.get('title')} [{rule.get('id')}]\n"
            f"  触发：{', '.join(rule.get('triggers', []))}\n"
            f"  动作：{rule.get('action', 'instruction')}\n"
            f"  使用：{rule.get('usage_count', 0)} 次"
        )
    lines.append("")
    lines.append("删除：/delete_rule 规则ID")
    return "\n".join(lines)


def handle_procedural_rule_command(message: str) -> str | None:
    if message in {"/rules", "/procedural_rules", "/teach_rules"}:
        return list_procedural_rules_text()
    if message.startswith("/teach_rule ") or message.startswith("/learn_rule "):
        body = message.split(maxsplit=1)[1].strip() if len(message.split(maxsplit=1)) > 1 else ""
        parts = [part.strip() for part in body.split("=>", 2)]
        if len(parts) != 3:
            return "格式：/teach_rule 规则名 => 触发词1,触发词2 => 动作说明"
        result = add_procedural_rule(parts[0], parts[1], parts[2])
        if not result.get("ok"):
            return result.get("error", "添加失败")
        rule = result["rule"]
        return (
            f"已添加行为规则「{rule['title']}」。\n"
            f"ID：{rule['id']}\n"
            f"触发词：{', '.join(rule['triggers'])}\n"
            f"动作：{rule['action']}"
        )
    if message.startswith("/delete_rule ") or message.startswith("/delete_procedural_rule "):
        rule_id = message.split(maxsplit=1)[1].strip() if len(message.split(maxsplit=1)) > 1 else ""
        if not rule_id:
            return "格式：/delete_rule 规则ID"
        return "已删除行为规则。" if delete_procedural_rule(rule_id) else f"没有找到行为规则：{rule_id}"
    return None
