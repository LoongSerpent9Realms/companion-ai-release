from __future__ import annotations

import re
import time
from pathlib import Path


from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
ACTION_FILE = DATA_DIR / "action_skills.json"


STOPWORDS = {
    "的", "了", "和", "是", "我", "你", "他", "她", "它", "们", "在", "有", "就", "也", "都", "很",
    "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on", "for", "with",
}


def ensure_action_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not ACTION_FILE.exists():
        write_sensitive_json(ACTION_FILE, {"skills": [], "evolution": []})


def load_action_store() -> dict:
    ensure_action_store()
    return read_sensitive_json(ACTION_FILE, {"skills": [], "evolution": []})


def save_action_store(store: dict) -> None:
    ensure_action_store()
    write_sensitive_json(ACTION_FILE, store)


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", lowered))
    return {word for word in words if word not in STOPWORDS}


def similarity(left: str, right: str) -> float:
    a = tokenize(left)
    b = tokenize(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _split_steps(raw: str) -> list[str]:
    steps: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        line = re.sub(r"^\s*(?:[-*]|\d+[.)、])\s*", "", line)
        if line:
            steps.append(line)
    if len(steps) <= 1:
        parts = re.split(r"\s*(?:->|=>|；|;|，然后|然后|再|最后)\s*", raw)
        steps = [part.strip(" \t\r\n.。") for part in parts if part.strip(" \t\r\n.。")]
    return steps[:40]


def learn_action_skill(title: str, body: str, source: str = "human-demo") -> dict:
    title = title.strip()
    body = body.strip()
    if not title or not body:
        return {"ok": False, "error": "格式：/learn_action 技能名 => 第一步；第二步；第三步"}

    steps = _split_steps(body)
    if not steps:
        return {"ok": False, "error": "没有识别到可学习的操作步骤。"}

    store = load_action_store()
    skills = store.setdefault("skills", [])
    skill_id = f"act-{int(time.time() * 1000)}"
    skill = {
        "id": skill_id,
        "time": int(time.time()),
        "title": title,
        "steps": steps,
        "raw_demo": body,
        "source": source,
        "uses": 0,
        "successes": 0,
        "failures": 0,
        "notes": [],
    }
    skills.append(skill)
    store.setdefault("evolution", []).append({
        "time": int(time.time()),
        "type": "learn",
        "skill_id": skill_id,
        "summary": f"学到电脑操作技能：{title}",
    })
    save_action_store(store)
    return {"ok": True, "skill": skill, "count": len(skills)}


def list_action_skills(limit: int = 12) -> list[dict]:
    store = load_action_store()
    return store.get("skills", [])[-limit:]


def best_action_skill(query: str, threshold: float = 0.16) -> tuple[dict | None, float]:
    store = load_action_store()
    best: dict | None = None
    best_score = 0.0
    for skill in store.get("skills", []):
        haystack = skill.get("title", "") + "\n" + "\n".join(skill.get("steps", []))
        score = similarity(query, haystack)
        if score > best_score:
            best = skill
            best_score = score
    if best and best_score >= threshold:
        return best, best_score
    return None, best_score


def action_plan_text(query: str) -> str:
    skill, score = best_action_skill(query)
    if not skill:
        return (
            "我还没有学过足够相似的电脑操作。你可以这样教我：\n"
            "/learn_action 打开常用项目 => 打开资源管理器；进入 H:\\Project；双击 start.cmd；确认窗口出现"
        )

    store = load_action_store()
    for item in store.get("skills", []):
        if item.get("id") == skill.get("id"):
            item["uses"] = int(item.get("uses", 0)) + 1
            break
    store.setdefault("evolution", []).append({
        "time": int(time.time()),
        "type": "plan",
        "skill_id": skill.get("id"),
        "summary": f"根据技能生成操作计划：{skill.get('title', '')}",
    })
    save_action_store(store)

    lines = [
        f"我找到了相似的人类操作示范：{skill.get('title', '')}（匹配度 {score:.2f}）",
        "",
        "我会先按下面的计划理解，不会默认控制你的鼠标键盘：",
    ]
    for i, step in enumerate(skill.get("steps", []), 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append("如果以后要进入自动执行，需要再加截图观察、权限确认、失败回退和日志审计。")
    return "\n".join(lines)


def record_action_outcome(skill_id: str, ok: bool, note: str = "") -> bool:
    store = load_action_store()
    for skill in store.get("skills", []):
        if skill.get("id") == skill_id:
            if ok:
                skill["successes"] = int(skill.get("successes", 0)) + 1
            else:
                skill["failures"] = int(skill.get("failures", 0)) + 1
            if note.strip():
                skill.setdefault("notes", []).append({"time": int(time.time()), "note": note.strip()})
            store.setdefault("evolution", []).append({
                "time": int(time.time()),
                "type": "outcome",
                "skill_id": skill_id,
                "summary": "操作成功" if ok else "操作失败，需要修正",
            })
            save_action_store(store)
            if ok:
                try:
                    from growth_loop import record_experience
                    prompt = f"执行操作技能：{item.get('title', '')}"
                    response = "；".join(str(step) for step in item.get("steps", []))
                    record_experience(prompt, response, source="action_outcome", evidence_type="user_approved", reward=1, evidence=note or "用户确认操作计划成功")
                except Exception:
                    pass
            return True
    return False


def action_status_text() -> str:
    store = load_action_store()
    skills = store.get("skills", [])
    evolution = store.get("evolution", [])
    lines = [
        "电脑操作学习状态：",
        f"技能：{len(skills)} 个",
        f"进化记录：{len(evolution)} 条",
    ]
    if not skills:
        lines.append("\n还没有示范。用 /learn_action 技能名 => 步骤1；步骤2 来教我。")
        return "\n".join(lines)

    lines.append("\n最近技能：")
    for skill in skills[-8:]:
        lines.append(
            f"- {skill.get('id')}: {skill.get('title')} "
            f"({len(skill.get('steps', []))} 步，使用 {skill.get('uses', 0)} 次，成功 {skill.get('successes', 0)} 次)"
        )
    return "\n".join(lines)


def evolution_summary() -> str:
    store = load_action_store()
    skills = store.get("skills", [])
    examples = sum(len(skill.get("steps", [])) for skill in skills)
    successes = sum(int(skill.get("successes", 0)) for skill in skills)
    failures = sum(int(skill.get("failures", 0)) for skill in skills)
    return (
        "自我进化摘要：\n"
        f"- 已学习电脑操作技能：{len(skills)} 个\n"
        f"- 累积人类示范步骤：{examples} 步\n"
        f"- 已记录成功/失败：{successes}/{failures}\n"
        "- 当前阶段：观察和计划生成\n"
        "- 下一阶段建议：接入屏幕截图观察、用户授权执行、执行后截图校验、失败时回滚到人工确认。"
    )
