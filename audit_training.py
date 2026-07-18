"""Store conversation audit output as local training feedback."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root
from sensitive_json import read_sensitive_json, write_sensitive_json

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
TRAINING_FILE = DATA_DIR / "training.json"


def _load_training() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return read_sensitive_json(TRAINING_FILE, {"examples": [], "feedback": []})


def _save_training(training: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(TRAINING_FILE, training)


def audit_result_id(result: dict[str, Any]) -> str:
    existing = str(result.get("audit_id") or "").strip()
    if existing:
        return existing
    payload = "|".join([
        str(result.get("timestamp") or ""),
        str(result.get("user_message") or ""),
        str(result.get("ai_reply") or ""),
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def training_response_text(response: str) -> str:
    text = str(response or "").strip()
    if not text:
        return ""

    kept: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        part = paragraph.strip()
        if not part:
            continue
        if "情感理解：" in part and "回应策略：" in part:
            continue
        if part.startswith("我先判断这是") or part.startswith("我根据已学习的情感样本判断这是"):
            continue
        kept.append(part)
    return "\n\n".join(kept).strip() or text


def _score(result: dict[str, Any], section: str, key: str) -> float | None:
    try:
        value = result.get(section, {}).get(key)
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _audit_rating(result: dict[str, Any]) -> int:
    correctness = _score(result, "ai_correctness", "overall_correctness")
    quality = _score(result, "ai_quality", "overall_score")
    sentiment_correct = result.get("sentiment_judgment", {}).get("correct")
    scores = [x for x in (correctness, quality) if x is not None]
    avg = sum(scores) / len(scores) if scores else 0.0
    if sentiment_correct is False or avg < 0.55:
        return -1
    return 1


def _audit_notes(result: dict[str, Any]) -> str:
    suggestions = result.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]
    return "；".join(str(item).strip() for item in suggestions if str(item).strip())[:1000]


def _already_recorded(training: dict, audit_id: str, source: str) -> bool:
    for bucket in ("feedback", "examples"):
        for item in training.get(bucket, []):
            if item.get("audit_id") == audit_id and item.get("source") == source:
                return True
    return False


def _sync_positive_example(prompt: str, response: str, source: str) -> None:
    """Make a just-accepted audit correction available to live retrieval."""
    if not prompt or not response:
        return
    try:
        from hybrid_chat import get_hybrid_chatbot

        chatbot = get_hybrid_chatbot()
        if not getattr(chatbot, "initialized", False):
            return
        embedding_index = getattr(chatbot, "embedding_index", None)
        if embedding_index is not None and getattr(embedding_index, "loaded", False):
            embedding_index.add_example(prompt, response, source=source)
        retrieval = getattr(chatbot, "retrieval", None)
        if retrieval is not None and getattr(retrieval, "loaded", False):
            retrieval.index.add_example(prompt, response, source=source)
    except Exception:
        pass


def handled_audit_ids(training: dict | None = None) -> set[str]:
    """Return audit IDs already resolved by a human or auto-accepted rewrite."""
    data = training if training is not None else _load_training()
    handled: set[str] = set()
    for bucket in ("feedback", "examples"):
        for item in data.get(bucket, []):
            audit_id = str(item.get("audit_id") or "").strip()
            source = str(item.get("source") or "")
            decision = str(item.get("decision") or "")
            if audit_id and (
                source.startswith("audit_human_")
                or source == "audit_auto_correct"
                or decision in {"approve", "reject", "correct", "skip", "auto_correct"}
            ):
                handled.add(audit_id)
    return handled


def record_audit_training(
    result: dict[str, Any],
    decision: str = "auto",
    corrected_response: str = "",
    note: str = "",
) -> dict:
    """Add an audit result to training feedback/examples.

    decision:
      - auto: background audit, conservative positive-example gating
      - approve: human approved the audited reply
      - reject: human rejected it without replacement
      - correct: human supplied a better response
      - skip: human intentionally leaves it as audit feedback only
    """
    audit_id = audit_result_id(result)
    source = f"audit_human_{decision}" if decision not in {"auto", "auto_correct"} else (
        "audit_auto_correct" if decision == "auto_correct" else "audit"
    )
    training = _load_training()
    if _already_recorded(training, audit_id, source):
        return training

    prompt = str(result.get("user_message") or "").strip()
    raw_reply = str(result.get("ai_reply") or "").strip()
    reply = training_response_text(corrected_response or raw_reply)
    rating = _audit_rating(result)
    if decision in {"approve", "correct", "auto_correct"}:
        rating = 1
    elif decision == "reject":
        rating = -1
    elif decision == "auto" and result.get("needs_user_action"):
        rating = -1

    row = {
        "time": int(time.time()),
        "prompt": prompt,
        "response": reply,
        "rating": rating,
        "type": "conversation_audit",
        "source": source,
        "audit_id": audit_id,
        "decision": decision,
        "audit_quality": _score(result, "ai_quality", "overall_score"),
        "audit_correctness": _score(result, "ai_correctness", "overall_correctness"),
        "audit_suggestions": _audit_notes(result),
    }
    if str(result.get("suggested_response") or "").strip():
        row["suggested_response"] = str(result.get("suggested_response") or "").strip()
    if result.get("needs_user_action") is not None:
        row["needs_user_action"] = bool(result.get("needs_user_action"))
    if note.strip():
        row["human_note"] = note.strip()
    if corrected_response.strip():
        row["corrected_response"] = corrected_response.strip()
        row["wrong_response"] = training_response_text(raw_reply)

    training.setdefault("feedback", []).append(row)

    should_add_example = bool(prompt and reply) and (
        decision in {"approve", "correct", "auto_correct"}
        or (decision == "auto" and rating > 0 and not result.get("needs_user_action"))
    )
    if should_add_example:
        example = dict(row)
        example["source"] = source
        example["rating"] = 1
        training.setdefault("examples", []).append(example)

    _save_training(training)
    if should_add_example:
        _sync_positive_example(prompt, reply, source)
        if decision in {"approve", "correct"}:
            try:
                from growth_loop import record_experience
                record_experience(prompt, reply, source=source, evidence_type="human", reward=1, evidence=note or "用户确认审计结果")
            except Exception:
                pass
    return training


def record_audit_training_by_id(
    audit_id: str,
    decision: str,
    corrected_response: str = "",
    note: str = "",
    audit_file: Path | None = None,
) -> dict:
    from conversation_audit import AUDIT_RESULTS_FILE, get_recent_audits

    audit_id = str(audit_id or "").strip()
    if not audit_id:
        raise ValueError("审计记录 ID 为空")

    target_file = audit_file or AUDIT_RESULTS_FILE
    result: dict[str, Any] | None = None
    if target_file.exists():
        for line in target_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if audit_result_id(item) == audit_id:
                result = item
    if result is None:
        for item in get_recent_audits(100):
            if audit_result_id(item) == audit_id:
                result = item
                break
    if result is None:
        raise ValueError(f"未找到审计记录：{audit_id}")
    return record_audit_training(result, decision, corrected_response, note)
