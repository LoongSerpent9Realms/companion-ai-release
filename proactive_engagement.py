"""Proactive Engagement Engine for Companion AI.

Makes the AI a proactive companion that:
1. Greets the user at specific times based on yesterday's state
2. Asks reverse questions every 3-5 turns to keep conversation going
3. Tracks conversation turn count and emotional state for timing

Time-triggered greeting logic:
- If user hasn't chatted in 12+ hours
- And current time is in a preferred window (e.g., 22:00)
- Look up yesterday's emotional state and conversation topics
- Generate a context-aware greeting

Reverse question logic:
- Every 3-5 rounds of dialogue, force a question
- Questions should reflect current emotional state
- Return conversational control to the user
"""

from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root

_ROOT = module_root(__file__)
DATA_DIR = data_dir(_ROOT)
ENGAGEMENT_STATE_FILE = DATA_DIR / "proactive_state.json"

# ── State management ────────────────────────────────────────────────────

def _load_state() -> dict[str, Any]:
    if ENGAGEMENT_STATE_FILE.exists():
        try:
            return json.loads(ENGAGEMENT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "enabled": True,
        "turn_count": 0,
        "last_chat_time": 0,
        "last_greeting_time": 0,
        "last_proactive_time": 0,
        "yesterday_state": {},
        "reverse_question_required": False,
    }


def _save_state(state: dict[str, Any]) -> None:
    ENGAGEMENT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Public API ─────────────────────────────────────────────────────────

def record_chat_turn() -> None:
    """Call this after each user message to increment turn counter."""
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + 1
    state["last_chat_time"] = int(time.time())
    
    # Check if reverse question is needed (every 3-5 turns)
    turn_mod = state["turn_count"] % random.randint(3, 5)
    state["reverse_question_required"] = (turn_mod == 0)
    
    _save_state(state)


def should_ask_reverse_question() -> bool:
    """Return True if it's time to ask a reverse question."""
    state = _load_state()
    return state.get("reverse_question_required", False)


def consume_reverse_question() -> None:
    """Reset the reverse question flag after asking."""
    state = _load_state()
    state["reverse_question_required"] = False
    _save_state(state)


def get_turn_count() -> int:
    """Return current conversation turn count."""
    return _load_state().get("turn_count", 0)


# ── Time-triggered greeting ────────────────────────────────────────────

def _load_yesterday_state() -> dict[str, Any]:
    """Extract yesterday's emotional state and topics from memory."""
    try:
        from app import load_history_entries, get_emotion_trend
        from memory_layer import MemoryStore
        
        # Load recent history (last 24 hours)
        entries = load_history_entries()
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_start = int(yesterday.replace(hour=0, minute=0, second=0).timestamp())
        yesterday_end = int(yesterday.replace(hour=23, minute=59, second=59).timestamp())
        
        yesterday_entries = [
            e for e in entries
            if isinstance(e, dict) and yesterday_start <= e.get("time", 0) <= yesterday_end
        ]
        
        # Extract user messages and emotions
        user_messages = []
        for e in yesterday_entries:
            if e.get("role") == "user":
                user_messages.append(str(e.get("content", "")))
        
        # Get emotion trend for yesterday
        emotion_trend = get_emotion_trend(1)
        
        # Get key facts from memory
        mem_store = MemoryStore(DATA_DIR / "memory.json")
        memory = mem_store.active_view()
        recent_facts = []
        for bucket in ["facts", "preferences"]:
            for item in memory.get(bucket, [])[-5:]:
                recent_facts.append(str(item.get("text", "")))
        
        return {
            "user_messages": user_messages,
            "emotion_trend": emotion_trend,
            "recent_facts": recent_facts,
            "message_count": len(user_messages),
        }
    except Exception:
        return {}


def should_send_proactive_greeting() -> dict[str, Any]:
    """Check if conditions are met for proactive greeting."""
    state = _load_state()
    if not state.get("enabled", True):
        return {"trigger": False, "reason": "proactive engagement disabled"}
    
    now = datetime.now()
    last_chat = state.get("last_chat_time", 0)
    hours_since_chat = (time.time() - last_chat) / 3600
    
    # Must be at least 12 hours since last chat
    if hours_since_chat < 12:
        return {"trigger": False, "reason": f"only {hours_since_chat:.1f} hours since last chat"}
    
    # Only during preferred hours
    preferred_hours = [10, 14, 22]
    if now.hour not in preferred_hours:
        return {"trigger": False, "reason": f"not in preferred hours ({preferred_hours})"}
    
    # Check if we already greeted today
    last_greeting = state.get("last_greeting_time", 0)
    last_greeting_date = datetime.fromtimestamp(last_greeting) if last_greeting else None
    if last_greeting_date and last_greeting_date.date() == now.date():
        return {"trigger": False, "reason": "already greeted today"}
    
    # Load yesterday's state for context
    yesterday_state = _load_yesterday_state()
    
    return {
        "trigger": True,
        "hour": now.hour,
        "hours_since_chat": hours_since_chat,
        "yesterday_state": yesterday_state,
    }


def generate_proactive_greeting(context: dict[str, Any]) -> str:
    """Generate a context-aware greeting based on yesterday's state."""
    yesterday = context.get("yesterday_state", {})
    emotions = yesterday.get("emotion_trend", [])
    facts = yesterday.get("recent_facts", [])
    messages = yesterday.get("user_messages", [])
    hour = context.get("hour", 22)
    
    # Extract emotion labels
    emotion_labels = []
    if emotions:
        for e in emotions:
            if isinstance(e, dict):
                emotion_labels.append(e.get("label", ""))
            elif isinstance(e, str):
                emotion_labels.append(e)
    
    # Check for key events
    has_interview = any("面试" in m for m in messages) or any("面试" in f for f in facts)
    has_exam = any("考试" in m for m in messages) or any("考试" in f for f in facts)
    has_sickness = any("生病" in m for m in messages) or any("生病" in f for f in facts)
    has_bad_mood = any(l in emotion_labels for l in ["难过", "沮丧", "焦虑", "生气"])
    
    # Time-based greeting
    time_greeting = {
        10: "上午好",
        14: "下午好",
        22: "晚上好",
    }.get(hour, "你好")
    
    # Context-aware greeting templates
    if has_interview and has_bad_mood:
        templates = [
            f"{time_greeting}，昨天你提到面试不太顺利，今天心情好一点了吗？昨晚睡得怎么样？",
            f"{time_greeting}，记得昨天你面试回来心情不太好，今天有什么想聊聊的吗？",
        ]
    elif has_exam and has_bad_mood:
        templates = [
            f"{time_greeting}，昨天考试结束了，结果怎么样？需要我帮你分析一下吗？",
            f"{time_greeting}，考试的事过去了，今天要不要做点开心的事？",
        ]
    elif has_sickness:
        templates = [
            f"{time_greeting}，昨天你说身体不舒服，现在感觉好点了吗？",
            f"{time_greeting}，记得你昨天生病休息了，今天身体怎么样？",
        ]
    elif has_bad_mood:
        templates = [
            f"{time_greeting}，昨天感觉你心情不太好，今天有什么我可以帮你的吗？",
            f"{time_greeting}，看你昨天情绪有点低落，想聊聊吗？",
        ]
    elif messages:
        # General greeting referencing yesterday's topic
        last_topic = messages[-1][:50] if messages else ""
        templates = [
            f"{time_greeting}，昨天聊到{last_topic}，今天有新进展吗？",
            f"{time_greeting}，昨天我们聊得挺开心的，今天想继续吗？",
        ]
    else:
        templates = [
            f"{time_greeting}，好久没聊天了，最近怎么样？",
            f"{time_greeting}，有什么新鲜事想分享吗？",
        ]
    
    return random.choice(templates)


def send_proactive_greeting_if_needed() -> str | None:
    """Check conditions and send greeting if appropriate."""
    result = should_send_proactive_greeting()
    if not result.get("trigger"):
        return None
    
    greeting = generate_proactive_greeting(result)
    
    # Update state
    state = _load_state()
    state["last_greeting_time"] = int(time.time())
    state["last_proactive_time"] = int(time.time())
    _save_state(state)
    
    return greeting


# ── Reverse question generation ────────────────────────────────────────

def generate_reverse_question(current_emotion: str = "") -> str:
    """Generate a reverse question based on current context."""
    # Emotion-aware question templates
    emotion_templates = {
        "开心": [
            "真为你开心！能多说说这件事吗？",
            "听起来很棒！后来怎么样了？",
            "你开心我也开心，还有什么想分享的吗？",
        ],
        "难过": [
            "我在这里陪你，想说点什么吗？",
            "听起来不容易，需要我做什么吗？",
            "难过的时候说出来会好一些，我在听。",
        ],
        "沮丧": [
            "遇到困难了吗？我们可以一起想想办法。",
            "别灰心，有什么我能帮你的吗？",
            "慢慢来，你想从哪里说起？",
        ],
        "焦虑": [
            "担心什么呢？我们一起梳理一下。",
            "紧张是正常的，你在担心什么？",
            "深呼吸，告诉我是什么让你焦虑。",
        ],
        "生气": [
            "发生什么事让你这么生气？",
            "别气坏了身体，跟我说说怎么回事。",
            "愤怒背后一定有原因，愿意聊聊吗？",
        ],
        "疲惫": [
            "累了就好好休息一下，想聊聊吗？",
            "辛苦了，需要我帮你做点什么吗？",
            "累的时候最需要有人陪伴，你想聊什么？",
        ],
        "期待": [
            "听起来很令人期待！你准备好了吗？",
            "好事将近！还有什么需要准备的吗？",
            "真替你高兴，能多说说吗？",
        ],
    }
    
    # General question templates
    general_templates = [
        "你觉得呢？",
        "你怎么看这件事？",
        "换做是你，会怎么做？",
        "你有什么想法？",
        "接下来想聊点什么？",
        "还有什么我没考虑到的吗？",
        "你希望我怎么做？",
    ]
    
    # Pick emotion-appropriate question
    if current_emotion and current_emotion in emotion_templates:
        return random.choice(emotion_templates[current_emotion])
    
    return random.choice(general_templates)


def ensure_reverse_question(reply: str, emotion: str = "") -> str:
    """Ensure the reply ends with a reverse question if required."""
    if not should_ask_reverse_question():
        return reply
    
    # Check if reply already ends with a question
    if reply.strip().endswith("？") or reply.strip().endswith("?"):
        consume_reverse_question()
        return reply
    
    # Add a natural reverse question
    question = generate_reverse_question(emotion)
    
    # Combine naturally
    if len(reply) > 50:
        reply = f"{reply} {question}"
    else:
        reply = f"{reply}。{question}"
    
    consume_reverse_question()
    return reply


# ── Proactive loop ────────────────────────────────────────────────────

_proactive_thread: threading.Thread | None = None
_proactive_running = False


def _proactive_loop() -> None:
    """Background loop checking for proactive engagement opportunities."""
    global _proactive_running
    
    while _proactive_running:
        try:
            time.sleep(60)  # Check every minute
            
            # Check for greeting
            greeting = send_proactive_greeting_if_needed()
            if greeting:
                print(f"[proactive] Sending greeting: {greeting[:50]}...")
                
                # Send to all connected clients via WebSocket if available
                try:
                    from app import send_to_all_clients
                    send_to_all_clients({
                        "type": "proactive_greeting",
                        "message": greeting,
                        "timestamp": int(time.time()),
                    })
                except Exception:
                    pass
                    
        except Exception as exc:
            print(f"[proactive] loop error: {exc}")


def start_proactive_engine() -> None:
    """Start the proactive engagement daemon."""
    global _proactive_thread, _proactive_running
    if _proactive_thread and _proactive_thread.is_alive():
        return
    _proactive_running = True
    _proactive_thread = threading.Thread(target=_proactive_loop, daemon=True, name="proactive-engine")
    _proactive_thread.start()
    print("Proactive engagement engine started")


def stop_proactive_engine() -> None:
    """Stop the proactive engagement daemon."""
    global _proactive_running
    _proactive_running = False


def get_proactive_status() -> dict[str, Any]:
    """Return current proactive engagement status."""
    state = _load_state()
    return {
        "enabled": state.get("enabled", True),
        "running": _proactive_running and (_proactive_thread is not None and _proactive_thread.is_alive()),
        "turn_count": state.get("turn_count", 0),
        "last_chat_time": state.get("last_chat_time", 0),
        "last_greeting_time": state.get("last_greeting_time", 0),
        "reverse_question_required": state.get("reverse_question_required", False),
    }


def handle_proactive_command(message: str) -> str | None:
    """Handle /proactive_* commands."""
    if message == "/proactive_status":
        s = get_proactive_status()
        lines = ["主动对话引擎状态："]
        lines.append(f"- 运行中：{'是' if s['running'] else '否'}")
        lines.append(f"- 开启：{'是' if s['enabled'] else '否'}")
        lines.append(f"- 当前轮次：{s['turn_count']}")
        lines.append(f"- 需要反问：{'是' if s['reverse_question_required'] else '否'}")
        return "\n".join(lines)
    
    if message == "/proactive_on":
        state = _load_state()
        state["enabled"] = True
        _save_state(state)
        start_proactive_engine()
        return "已开启主动对话引擎。AI 会在合适的时候主动问候你。"
    
    if message == "/proactive_off":
        state = _load_state()
        state["enabled"] = False
        _save_state(state)
        stop_proactive_engine()
        return "已关闭主动对话引擎。"
    
    if message == "/proactive_test":
        # Force a greeting for testing
        context = {
            "hour": datetime.now().hour,
            "hours_since_chat": 13,
            "yesterday_state": _load_yesterday_state(),
        }
        return f"测试问候：\n{generate_proactive_greeting(context)}"
    
    return None
