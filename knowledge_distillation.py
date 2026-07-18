"""Knowledge Distillation System for Companion AI.

Implements a teacher-student learning loop where:
1. Local AI encounters hard problems it can't solve
2. Problems are queued for later consultation with remote LLM (teacher)
3. When network is available, teacher provides detailed solutions
4. High-quality solutions are distilled into local training data
5. AI improves autonomously without user interaction

Key components:
- Question queue with priority levels
- Remote LLM consultation with structured prompts
- Solution formatting and quality filtering
- Integration with local training system
- Background thread for batch processing
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root

_ROOT = module_root(__file__)
DATA_DIR = data_dir(_ROOT)
DISTILLATION_STATE_FILE = DATA_DIR / "distillation_state.json"
DISTILLATION_CONFIG_FILE = DATA_DIR / "distillation_config.json"

DISTILLATION_SYSTEM_PROMPT = """你是 Companion AI 的"老师"，负责指导本地小模型学习新知识。

任务：详细解答用户的问题，并给出清晰的解题思路和步骤。

要求：
1. 解答要详细但清晰，适合作为教学范例
2. 包含解题思路、关键步骤、代码示例（如适用）
3. 用中文回答
4. 输出格式：
   【问题】用户的原始问题
   【分析】问题分析和解题思路
   【解答】详细解答过程
   【总结】核心要点总结

注意：你的回答将被用作本地AI的训练样本，请确保质量。"""


def _default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "max_queue_size": 50,
        "max_concurrent_queries": 2,
        "consult_interval_minutes": 15,
        "min_confidence_threshold": 0.3,
        "max_retries": 3,
        "quality_score_threshold": 0.6,
        "auto_train_after_distillation": True,
        "preferred_hours": [0, 1, 2, 3, 12, 13, 22, 23],
    }


def load_distillation_config() -> dict[str, Any]:
    if DISTILLATION_CONFIG_FILE.exists():
        try:
            return {**_default_config(), **json.loads(DISTILLATION_CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return _default_config()


def save_distillation_config(config: dict[str, Any]) -> None:
    DISTILLATION_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_state() -> dict[str, Any]:
    if DISTILLATION_STATE_FILE.exists():
        try:
            return json.loads(DISTILLATION_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "pending_questions": [],
        "completed_questions": [],
        "failed_questions": [],
        "consult_count": 0,
        "distilled_count": 0,
        "last_consult_time": 0,
        "last_distillation_time": 0,
    }


def _save_state(state: dict[str, Any]) -> None:
    DISTILLATION_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def queue_question(message: str, context: dict | None = None, priority: int = 1) -> dict[str, Any]:
    """Queue a hard question for later consultation with teacher LLM."""
    config = load_distillation_config()
    if not config.get("enabled", True):
        return {"ok": False, "reason": "distillation disabled"}

    state = _load_state()
    pending = state.setdefault("pending_questions", [])

    if len(pending) >= config.get("max_queue_size", 50):
        return {"ok": False, "reason": "queue full"}

    question_id = f"q_{int(time.time())}_{hash(message) % 10000}"
    question = {
        "id": question_id,
        "message": message[:2000],
        "context": context or {},
        "priority": max(1, min(5, priority)),
        "created_at": int(time.time()),
        "retries": 0,
        "status": "pending",
    }

    pending.append(question)
    pending.sort(key=lambda x: (-x["priority"], x["created_at"]))
    state["pending_questions"] = pending[:config.get("max_queue_size", 50)]
    _save_state(state)

    return {"ok": True, "question_id": question_id, "position": len(pending)}


def dequeue_question() -> dict[str, Any] | None:
    """Get the highest priority pending question."""
    state = _load_state()
    pending = state.get("pending_questions", [])
    if not pending:
        return None

    question = pending[0]
    state["pending_questions"] = pending[1:]
    _save_state(state)
    return question


def _consult_teacher(question: dict[str, Any]) -> dict[str, Any]:
    """Consult the remote LLM (teacher) for a detailed solution."""
    try:
        from remote_llm import call_remote_llm, is_remote_llm_ready, load_remote_llm_config

        config = load_remote_llm_config()
        if not is_remote_llm_ready(config):
            return {"ok": False, "error": "remote LLM not configured"}

        prompt = f"{DISTILLATION_SYSTEM_PROMPT}\n\n【用户问题】\n{question['message']}"
        reply = call_remote_llm(prompt, history=[], config=config)

        if reply.startswith("["):
            return {"ok": False, "error": reply}

        return {"ok": True, "reply": reply, "question_id": question["id"]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _score_solution_quality(reply: str) -> float:
    """Score the quality of a teacher's solution."""
    score = 0.0

    if len(reply) >= 100:
        score += 0.2
    if len(reply) >= 300:
        score += 0.15
    if len(reply) >= 500:
        score += 0.15

    if "【分析】" in reply:
        score += 0.15
    if "【解答】" in reply:
        score += 0.15
    if "【总结】" in reply:
        score += 0.1

    code_blocks = re.findall(r"```[\s\S]*?```", reply)
    if code_blocks:
        score += 0.1

    return min(1.0, score)


def _format_for_training(question: dict[str, Any], reply: str) -> dict[str, Any]:
    """Format the teacher's solution for local training."""
    return {
        "prompt": question["message"],
        "response": reply,
        "source": "distillation",
        "quality_score": _score_solution_quality(reply),
        "priority": question["priority"],
        "created_at": int(time.time()),
        "question_id": question["id"],
    }


def _save_to_training(sample: dict[str, Any]) -> None:
    """Save a distilled solution to local training data."""
    try:
        from app import load_training, save_training

        training = load_training()
        examples = training.setdefault("examples", [])

        exists = any(e.get("prompt") == sample["prompt"] for e in examples)
        if not exists:
            examples.append(sample)
            save_training(training)
    except Exception:
        pass


def _distill_question(question: dict[str, Any]) -> dict[str, Any]:
    """Complete the distillation process for a single question."""
    consult_result = _consult_teacher(question)
    if not consult_result.get("ok"):
        return {
            "ok": False,
            "question_id": question["id"],
            "error": consult_result.get("error", "consultation failed"),
        }

    reply = consult_result["reply"]
    quality_score = _score_solution_quality(reply)
    config = load_distillation_config()

    if quality_score >= config.get("quality_score_threshold", 0.6):
        sample = _format_for_training(question, reply)
        _save_to_training(sample)

        state = _load_state()
        completed = state.setdefault("completed_questions", [])
        completed.append({
            "id": question["id"],
            "message": question["message"],
            "reply_preview": reply[:200],
            "quality_score": quality_score,
            "distilled_at": int(time.time()),
        })
        completed = completed[-100:]
        state["completed_questions"] = completed
        state["distilled_count"] = state.get("distilled_count", 0) + 1
        _save_state(state)

        return {
            "ok": True,
            "question_id": question["id"],
            "quality_score": quality_score,
            "distilled": True,
        }
    else:
        state = _load_state()
        failed = state.setdefault("failed_questions", [])
        failed.append({
            "id": question["id"],
            "message": question["message"],
            "quality_score": quality_score,
            "failed_at": int(time.time()),
        })
        failed = failed[-50:]
        state["failed_questions"] = failed
        _save_state(state)

        return {
            "ok": True,
            "question_id": question["id"],
            "quality_score": quality_score,
            "distilled": False,
            "reason": "quality score below threshold",
        }


def process_pending_questions(batch_size: int = 2) -> dict[str, Any]:
    """Process a batch of pending questions."""
    config = load_distillation_config()
    if not config.get("enabled", True):
        return {"ok": False, "reason": "distillation disabled"}

    try:
        from remote_llm import is_remote_llm_ready, load_remote_llm_config
        if not is_remote_llm_ready(load_remote_llm_config()):
            return {"ok": False, "reason": "remote LLM not ready"}
    except Exception:
        return {"ok": False, "reason": "remote LLM check failed"}

    results = []
    processed = 0
    distilled = 0

    for _ in range(batch_size):
        question = dequeue_question()
        if not question:
            break

        result = _distill_question(question)
        results.append(result)
        processed += 1
        if result.get("distilled"):
            distilled += 1

    state = _load_state()
    state["consult_count"] = state.get("consult_count", 0) + processed
    state["last_consult_time"] = int(time.time())
    _save_state(state)

    return {
        "ok": True,
        "processed": processed,
        "distilled": distilled,
        "results": results,
    }


_distillation_thread: threading.Thread | None = None
_distillation_running = False


def _distillation_loop() -> None:
    """Background loop for processing pending questions."""
    global _distillation_running
    config = load_distillation_config()

    while _distillation_running:
        try:
            time.sleep(config.get("consult_interval_minutes", 15) * 60)

            config = load_distillation_config()
            if not config.get("enabled", True):
                continue

            now = datetime.now()
            preferred_hours = config.get("preferred_hours", [0, 1, 2, 3, 12, 13, 22, 23])
            if now.hour not in preferred_hours:
                continue

            result = process_pending_questions(config.get("max_concurrent_queries", 2))
            if result.get("ok"):
                print(f"[distill] processed {result['processed']}, distilled {result['distilled']}")
            else:
                print(f"[distill] skipped: {result.get('reason')}")

        except Exception as exc:
            print(f"[distill] loop error: {exc}")


def start_distillation_engine() -> None:
    """Start the background distillation daemon."""
    global _distillation_thread, _distillation_running
    if _distillation_thread and _distillation_thread.is_alive():
        return
    _distillation_running = True
    _distillation_thread = threading.Thread(target=_distillation_loop, daemon=True, name="distillation-engine")
    _distillation_thread.start()
    print("Knowledge distillation engine started")


def stop_distillation_engine() -> None:
    """Stop the distillation daemon."""
    global _distillation_running
    _distillation_running = False


def get_distillation_status() -> dict[str, Any]:
    """Return current distillation engine status."""
    state = _load_state()
    config = load_distillation_config()
    return {
        "enabled": config.get("enabled", True),
        "running": _distillation_running and (_distillation_thread is not None and _distillation_thread.is_alive()),
        "pending_count": len(state.get("pending_questions", [])),
        "completed_count": len(state.get("completed_questions", [])),
        "failed_count": len(state.get("failed_questions", [])),
        "consult_count": state.get("consult_count", 0),
        "distilled_count": state.get("distilled_count", 0),
        "last_consult_time": state.get("last_consult_time", 0),
        "last_distillation_time": state.get("last_distillation_time", 0),
    }


def handle_distillation_command(message: str) -> str | None:
    """Handle /distill_* commands."""
    if message == "/distill_status":
        s = get_distillation_status()
        lines = ["知识蒸馏系统状态："]
        lines.append(f"- 运行中：{'是' if s['running'] else '否'}")
        lines.append(f"- 开启：{'是' if s['enabled'] else '否'}")
        lines.append(f"- 待请教：{s['pending_count']} 个问题")
        lines.append(f"- 已完成：{s['completed_count']} 个")
        lines.append(f"- 失败：{s['failed_count']} 个")
        lines.append(f"- 请教次数：{s['consult_count']}")
        lines.append(f"- 蒸馏成功：{s['distilled_count']}")
        return "\n".join(lines)

    if message == "/distill_on":
        cfg = load_distillation_config()
        cfg["enabled"] = True
        save_distillation_config(cfg)
        start_distillation_engine()
        return "已开启知识蒸馏系统。AI 将在后台向大模型请教难题。"

    if message == "/distill_off":
        cfg = load_distillation_config()
        cfg["enabled"] = False
        save_distillation_config(cfg)
        stop_distillation_engine()
        return "已关闭知识蒸馏系统。"

    if message == "/distill_now":
        result = process_pending_questions(2)
        if result.get("ok"):
            return f"蒸馏完成：处理了 {result['processed']} 个问题，成功蒸馏 {result['distilled']} 个。"
        return f"蒸馏失败：{result.get('reason', '未知错误')}"

    if message.startswith("/distill_queue "):
        question = message[15:].strip()
        if not question:
            return "格式：/distill_queue 你的问题\n\n将问题放入蒸馏队列，AI 会在后台向大模型请教。"
        result = queue_question(question)
        if result.get("ok"):
            return f"问题已加入蒸馏队列，位置：第 {result['position']} 位。AI 会在后台向大模型请教。"
        return f"加入队列失败：{result.get('reason', '未知错误')}"

    return None


def get_pending_questions_summary(limit: int = 5) -> list[dict[str, Any]]:
    """Return a summary of pending questions for display."""
    state = _load_state()
    pending = state.get("pending_questions", [])[:limit]
    return [
        {
            "id": q["id"],
            "message": q["message"][:100],
            "priority": q["priority"],
            "created_at": q["created_at"],
        }
        for q in pending
    ]