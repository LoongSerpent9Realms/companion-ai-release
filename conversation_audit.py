"""Conversation Audit Module for Companion AI.

Uses external AI API to audit conversations between user and the app's AI:
- Analyze user sentiment/emotion
- Analyze AI reply sentiment/emotion
- Evaluate AI reply correctness/quality
- Store audit results for AI self-improvement

Supports multiple AI API providers (OpenAI-compatible).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json

_ROOT = module_root(__file__)
DATA_DIR = data_dir(_ROOT)
AUDIT_CONFIG_FILE = DATA_DIR / "audit_config.json"
AUDIT_RESULTS_FILE = DATA_DIR / "audit_results.jsonl"
AUDIT_SUMMARY_FILE = DATA_DIR / "audit_summary.json"
IDENTITY_FILE = DATA_DIR / "identity.json"

# Thread lock for file writes
_write_lock = threading.Lock()

# Audit queue for batch processing
_audit_queue: list[dict] = []
_queue_lock = threading.Lock()
_audit_thread: threading.Thread | None = None
_running = False
_current_audit_id: str | None = None
_current_audit_status: str | None = None
_status_lock = threading.Lock()

# Pending corrections that haven't been pushed to the chat UI yet
_pending_corrections: list[dict] = []
_corrections_lock = threading.Lock()


# ── Configuration ─────────────────────────────────────────────────────

def load_audit_config() -> dict:
    """Load audit configuration from file."""
    default = {
        "enabled": True,
        "use_cloud_audit": False,
        "api_provider": "openai_compatible",
        "api_base": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "batch_size": 5,
        "audit_interval": 10,
        "max_context_turns": 6,
        "language": "zh",
        "local_fallback": True,
        "auto_suggest_corrections": False,
        "correction_threshold": 0.65,
    }
    if AUDIT_CONFIG_FILE.exists():
        try:
            data = json.loads(AUDIT_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = dict(default)
                merged.update(data)
                return merged
        except Exception:
            pass
    return default


def save_audit_config(config: dict) -> None:
    """Save audit configuration to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_audit_enabled() -> bool:
    """Check if audit is enabled and configured."""
    config = load_audit_config()
    return bool(config.get("enabled")) and (bool(config.get("local_fallback", True)) or (bool(config.get("use_cloud_audit")) and bool(config.get("api_key"))))


# ── AI API Call ───────────────────────────────────────────────────────

def _message_text(message: Any) -> str:
    """Extract assistant text from OpenAI-compatible message payloads.

    Local reasoning models (e.g. Qwen3) often put the usable answer in
    ``reasoning_content`` while leaving ``content`` empty. Some providers
    also return content as a list of text parts.
    """
    if message is None:
        return ""
    if isinstance(message, str):
        return message.strip()
    if not isinstance(message, dict):
        return str(message).strip()

    parts: list[str] = []
    for key in ("content", "reasoning_content", "reasoning", "text", "output_text"):
        value = message.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text)
            continue
        if isinstance(value, list):
            chunks: list[str] = []
            for item in value:
                if isinstance(item, str):
                    chunk = item.strip()
                elif isinstance(item, dict):
                    chunk = str(
                        item.get("text")
                        or item.get("content")
                        or item.get("value")
                        or ""
                    ).strip()
                else:
                    chunk = str(item or "").strip()
                if chunk:
                    chunks.append(chunk)
            joined = "\n".join(chunks).strip()
            if joined:
                parts.append(joined)
    if not parts:
        return ""
    return parts[0]


def call_ai_api(config: dict, system_prompt: str, user_prompt: str) -> str | None:
    """Call an OpenAI-compatible API."""
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        return None

    api_base = config.get("api_base", "https://api.openai.com/v1").rstrip("/")
    api_key = config.get("api_key", "")
    model = config.get("model", "gpt-4o-mini")

    url = f"{api_base}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        # Reasoning models burn tokens in hidden thinking; keep headroom for JSON.
        "max_tokens": int(config.get("max_tokens") or config.get("audit_max_tokens") or 2048),
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    timeout = float(config.get("timeout") or config.get("audit_timeout") or 120)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                choice = choices[0] if isinstance(choices[0], dict) else {}
                message = choice.get("message") if isinstance(choice, dict) else None
                text = _message_text(message)
                if not text and isinstance(choice, dict):
                    text = _message_text(choice)
                if text:
                    return text
                print("[audit] API returned empty assistant content/reasoning_content")
                return None
    except Exception as e:
        print(f"[audit] API call failed: {e}")
        return None

    return None


# ── Audit Logic ───────────────────────────────────────────────────────

AUDIT_SYSTEM_PROMPT = """你是一个对话质量审计与改进专家。你的任务是：
1) 分析用户与AI助手之间的对话，给出准确的情感判定
2) 评估AI回复的正确性和质量
3) **当AI回复存在问题时，必须给出可直接训练的正确回复**

你需要分析以下内容并以JSON格式返回：

1. **用户情感分析** (user_sentiment):
   - emotion: 用户的真实情绪 (如：平静、开心、难过、焦虑、愤怒、困惑、期待、好奇等)
   - polarity: 正面/中性/负面
   - intensity: 1-5 (情绪强度)

2. **AI情感判断准确性** (sentiment_judgment):
   - detected_emotion: AI回复中体现出的对用户情绪的判断（如果AI没有明确表达情绪判断则为null）
   - correct: AI的情感判断是否与你分析的一致 (true/false/null)
   - explanation: 情感判断正确或错误的原因说明

3. **AI回复情感分析** (ai_sentiment):
   - emotion: AI回复传达的情绪
   - polarity: 正面/中性/负面
   - empathy: 是否有共情 (true/false)
   - appropriate: 情感是否适合当前场景 (true/false)

4. **AI回复正确性评估** (ai_correctness):
   - factual_correctness: 0.0-1.0 (回复事实内容的正确性)
   - answer_completeness: 0.0-1.0 (回答的完整性)
   - reasoning_correctness: 0.0-1.0 (推理逻辑的正确性)
   - overall_correctness: 0.0-1.0 (正确性综合评分)

5. **AI回复质量评估** (ai_quality):
   - relevance: 0.0-1.0 (回复与问题的相关性)
   - helpfulness: 0.0-1.0 (回复的有用程度)
   - clarity: 0.0-1.0 (回复的清晰度)
   - overall_score: 0.0-1.0 (综合评分)

6. **改进建议** (suggestions):
   - 数组，每条是一个具体的改进建议，包括：
     * 正确的情感判定应该是什么
     * 如果回复内容错误，正确的回答方向是什么
     * 如何改进回复质量

7. **建议改写** (suggested_response):
   - **这是最重要的部分！** 如果AI回复存在任何问题（情感判断错误、回答不完整、语气不当、暴露内部思考等），必须给出一条可直接训练的理想回复
   - 理想回复必须：正确识别用户情绪、自然回应、不暴露内部思考过程、遵守用户原始要求（例如字数、语气、只输出一句等）
   - 如果当前回复已经完全合格（overall_correctness >= 0.8 且 overall_score >= 0.8），则返回空字符串
   - 否则**必须**提供具体的改进回复

8. 如果上下文提供了“AI 身份设定”，suggested_response 必须自然保留其中的名字、关系身份和人设语气，不能退化成通用客服式 AI 自我介绍。

请严格以JSON格式返回，不要包含其他内容。
最终答案必须是完整 JSON 对象本身；不要只把 JSON 写在思考过程里。"""


def _audit_identity_context() -> str:
    """Return the local companion identity relevant to a rewrite, if configured."""
    try:
        identity = read_sensitive_json(IDENTITY_FILE, {})
    except Exception:
        identity = {}
    if not isinstance(identity, dict):
        return ""
    name = str(identity.get("name") or "").strip()
    if not name:
        return ""
    relation = str(identity.get("relationship_label") or "").strip()
    if not relation:
        relation = {
            "friend": "朋友", "family": "家人", "partner": "搭档",
            "guardian": "守护者", "lifeform": "数字生命",
        }.get(str(identity.get("relationship_type") or ""), "陪伴伙伴")
    subtype = str(identity.get("relationship_subtype") or "").strip()
    persona = str(identity.get("persona") or "").strip()
    worldview = str(identity.get("worldview") or "").strip()
    lines = [f"名字：{name}", f"关系身份：{subtype or relation}"]
    if persona:
        lines.append(f"人设：{persona[:500]}")
    if worldview:
        lines.append(f"背景：{worldview[:500]}")
    return "\n".join(lines)


def _local_audit(user_message: str, ai_reply: str) -> dict:
    """Local fallback audit without external API."""
    user_lower = user_message.lower()
    reply_lower = ai_reply.lower()

    positive_keywords = ["谢谢", "感谢", "太棒了", "好的", "不错", "厉害", "满意", "喜欢", "开心", "高兴"]
    negative_keywords = ["生气", "愤怒", "失望", "伤心", "难过", "讨厌", "烦", "郁闷", "委屈", "无语"]
    question_keywords = ["什么", "怎么", "为什么", "如何", "吗", "呢", "是不是"]
    request_keywords = ["帮我", "麻烦", "需要", "请求", "请"]

    user_sentiment = {"emotion": "neutral", "polarity": 0.0, "intensity": 0.5}
    ai_sentiment = {"emotion": "neutral", "polarity": 0.0, "intensity": 0.5}
    sentiment_correct = True

    if any(k in user_lower for k in positive_keywords):
        user_sentiment = {"emotion": "positive", "polarity": 0.7, "intensity": 0.7}
    elif any(k in user_lower for k in negative_keywords):
        user_sentiment = {"emotion": "negative", "polarity": -0.7, "intensity": 0.7}
    elif any(k in user_lower for k in question_keywords):
        user_sentiment = {"emotion": "curious", "polarity": 0.0, "intensity": 0.6}
    elif any(k in user_lower for k in request_keywords):
        user_sentiment = {"emotion": "need_help", "polarity": 0.0, "intensity": 0.6}

    if any(k in reply_lower for k in positive_keywords):
        ai_sentiment = {"emotion": "positive", "polarity": 0.7, "intensity": 0.7}
    elif any(k in reply_lower for k in negative_keywords):
        ai_sentiment = {"emotion": "negative", "polarity": -0.5, "intensity": 0.6}

    if user_sentiment["emotion"] == "negative" and ai_sentiment["emotion"] == "positive":
        sentiment_correct = True
    elif user_sentiment["emotion"] == "positive" and ai_sentiment["emotion"] == "negative":
        sentiment_correct = False

    suggestions: list[str] = []
    answer_correctness = 0.7
    if len(ai_reply) < 10:
        answer_correctness = 0.3

    is_question = any(k in user_lower for k in question_keywords)
    answer_complete = 0.6 if is_question and len(ai_reply) > 50 else 0.7
    reasoning_correctness = 0.6
    relevance = 0.7
    helpfulness = 0.6
    clarity = 0.7

    non_answer_markers = [
        "需要学习",
        "/teach",
        "不知道",
        "不确定",
        "无法回答",
        "不会回答",
        "还没学会",
        "没学会",
        "我不会",
        "i don't know",
        "cannot answer",
    ]
    is_non_answer = any(marker in reply_lower for marker in non_answer_markers)
    if is_non_answer:
        answer_correctness = min(answer_correctness, 0.25)
        answer_complete = min(answer_complete, 0.2)
        reasoning_correctness = min(reasoning_correctness, 0.3)
        relevance = min(relevance, 0.25)
        helpfulness = min(helpfulness, 0.25)
        clarity = min(clarity, 0.5)
        suggestions.append("这条回复没有完成用户要求，建议点击“改正并训练”，写入一条符合原指令的理想回复。")

    wants_one_sentence = any(token in user_message for token in ("只输出一句", "只回复一句", "一句话", "只说一句", "一句"))
    reply_paragraphs = [p for p in re.split(r"\n\s*\n", ai_reply.strip()) if p.strip()]
    has_meta_prefix = any(marker in ai_reply for marker in ("情感理解：", "回应策略：", "我先判断这是"))
    if wants_one_sentence and (len(reply_paragraphs) > 1 or "\n" in ai_reply.strip() or has_meta_prefix):
        answer_complete = min(answer_complete, 0.35)
        clarity = min(clarity, 0.35)
        helpfulness = min(helpfulness, 0.45)
        suggestions.append("用户要求只输出一句话，回复应避免多段、元说明或额外铺垫。")
    elif has_meta_prefix and len(reply_paragraphs) > 1:
        answer_complete = min(answer_complete, 0.5)
        clarity = min(clarity, 0.5)
        suggestions.append("回复包含情感元说明和多段铺垫，建议改成直接可训练的最终答案。")

    max_len_match = re.search(r"不(?:要|超过|多于|超過)\s*(\d+)\s*个?字", user_message)
    if max_len_match:
        try:
            max_len = int(max_len_match.group(1))
            reply_len = len(re.sub(r"\s+", "", ai_reply))
            if reply_len > max_len:
                answer_complete = min(answer_complete, 0.45)
                clarity = min(clarity, 0.45)
                suggestions.append(f"用户要求不超过 {max_len} 个字，当前回复约 {reply_len} 个字。")
        except Exception:
            pass

    overall_correctness = (answer_correctness + answer_complete + reasoning_correctness) / 3
    overall_quality = (relevance + helpfulness + clarity) / 3

    return {
        "user_sentiment": user_sentiment,
        "sentiment_judgment": {
            "detected_emotion": ai_sentiment["emotion"],
            "correct": sentiment_correct,
            "explanation": "本地规则审计：基于关键词和格式约束粗略判断，不等同于外部 AI 审计。",
        },
        "ai_sentiment": ai_sentiment,
        "ai_correctness": {
            "factual_correctness": answer_correctness,
            "answer_completeness": answer_complete,
            "reasoning_correctness": reasoning_correctness,
            "overall_correctness": overall_correctness,
        },
        "ai_quality": {
            "relevance": relevance,
            "helpfulness": helpfulness,
            "clarity": clarity,
            "overall_score": overall_quality,
        },
        "suggestions": suggestions,
        "suggested_response": "",
        "audit_source": "local",
    }


def _extract_json_object(text: str) -> dict | None:
    """Extract the first balanced JSON object from model output."""
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    # Reasoning models sometimes wrap the JSON after a long chain-of-thought.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S | re.I)
    if fence:
        raw = fence.group(1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Scan every object start; prefer the last successfully parsed dict.
    candidates: list[dict] = []
    for start in [idx for idx, ch in enumerate(raw) if ch == "{"]:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:index + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            candidates.append(parsed)
                    except json.JSONDecodeError:
                        pass
                    break
    if not candidates:
        return None
    # Prefer objects that look like audit/correction payloads.
    preferred_keys = {
        "ai_quality", "ai_correctness", "user_sentiment", "suggested_response",
        "suggestions", "sentiment_judgment",
    }
    scored = sorted(
        candidates,
        key=lambda item: sum(1 for key in preferred_keys if key in item),
        reverse=True,
    )
    return scored[0]


AUDIT_CORRECTION_SYSTEM_PROMPT = """你是一个对话改写专家。你的任务：根据用户原始输入、AI原回复和审计结果，写出一条可直接作为正确训练答案的 suggested_response。

**核心要求：**
1. 回复必须自然、拟人化，像真人对话一样，**绝对不能**暴露任何内部思考过程（如情感分析、置信度、策略说明等）。
2. 必须正确识别并回应用户的真实情绪，保持适当的共情。
3. 必须遵守用户原始输入中的格式、语气、字数、角色和输出限制。
4. 如果用户要求一句话，就只给一句话。
5. 如果原回复已经合格（overall_correctness >= 0.8 且 overall_score >= 0.8），返回空字符串。
6. 否则**必须**提供具体的改进回复。
7. 如果输入包含 AI 身份设定，回复必须使用该名字、关系身份和人设语气；绝不能改写成泛化的客服/通用 AI 自我介绍。

请严格返回 JSON：
{
  "suggested_response": "可直接训练的理想回复",
  "reason": "一句话说明为什么这样改"
}"""


def _trainable_suggested_response(value: object) -> str:
    """Accept only a direct end-user reply, never an audit analysis as training data."""
    text = str(value or "").strip()
    if not text or len(text) > 1200:
        return ""
    forbidden = (
        "用户问的是", "用户原始输入", "ai原回复", "ai 原回复", "审计结果",
        "改写建议", "改写原因", "内部思考", "情感理解", "回应策略", "评分：",
        "建议：", "suggested_response", "```",
    )
    lowered = text.lower()
    if any(marker in lowered for marker in forbidden):
        return ""
    return text


def _score_value(result: dict, section: str, key: str) -> float | None:
    try:
        value = result.get(section, {}).get(key)
        return None if value is None else float(value)
    except Exception:
        return None


def _needs_user_action(result: dict, threshold: float = 0.65) -> bool:
    correctness = _score_value(result, "ai_correctness", "overall_correctness")
    quality = _score_value(result, "ai_quality", "overall_score")
    sentiment_correct = result.get("sentiment_judgment", {}).get("correct")
    if sentiment_correct is False:
        return True
    if correctness is not None and correctness < threshold:
        return True
    if quality is not None and quality < threshold:
        return True
    if str(result.get("suggested_response") or "").strip():
        return True
    return bool(result.get("suggestions"))


def _generate_correction_suggestion(
    user_message: str,
    ai_reply: str,
    audit_result: dict,
    config: dict,
) -> dict | None:
    if not config.get("api_key"):
        return None
    audit_brief = {
        "ai_correctness": audit_result.get("ai_correctness", {}),
        "ai_quality": audit_result.get("ai_quality", {}),
        "sentiment_judgment": audit_result.get("sentiment_judgment", {}),
        "suggestions": audit_result.get("suggestions", []),
    }
    identity_context = _audit_identity_context()
    prompt = (
        "请根据以下审计结果生成一条可直接训练的改写回复。\n\n"
        f"用户原始输入：\n{user_message}\n\n"
        f"AI原回复：\n{ai_reply}\n\n"
        f"审计结果：\n{json.dumps(audit_brief, ensure_ascii=False)}"
    )
    if identity_context:
        prompt += f"\n\nAI 身份设定（改写必须遵守）：\n{identity_context}"
    response = call_ai_api(config, AUDIT_CORRECTION_SYSTEM_PROMPT, prompt)
    if not response:
        return None
    parsed = _extract_json_object(response)
    suggestion = _trainable_suggested_response(
        parsed.get("suggested_response") if parsed else response
    )
    if not suggestion:
        retry_prompt = (
            prompt
            + "\n\n上一条输出不合格。现在只返回一条直接对用户说的话，不要解释审计、问题、评分、建议或改写过程；"
              "仍严格返回 {\"suggested_response\":\"...\",\"reason\":\"...\"}。"
        )
        retry_response = call_ai_api(config, AUDIT_CORRECTION_SYSTEM_PROMPT, retry_prompt)
        parsed = _extract_json_object(retry_response or "") if retry_response else None
        suggestion = _trainable_suggested_response(
            parsed.get("suggested_response") if parsed else retry_response
        )
    if not suggestion:
        return None
    return {
        "suggested_response": suggestion,
        "reason": str(parsed.get("reason") or "").strip(),
    }


def _attach_review_metadata(
    result: dict,
    user_message: str,
    ai_reply: str,
    config: dict,
    *,
    allow_api: bool = True,
) -> dict:
    threshold = float(config.get("correction_threshold", 0.65) or 0.65)
    result["needs_user_action"] = _needs_user_action(result, threshold)
    result["correction_threshold"] = threshold
    has_api = bool(str(config.get("api_key") or "").strip())
    existing_suggestion = str(result.get("suggested_response") or "").strip()
    if existing_suggestion and not _trainable_suggested_response(existing_suggestion):
        result["suggested_response"] = ""
        result["correction_error"] = "审计 AI 返回了分析文本，不会作为训练建议保存"
    if (
        allow_api and has_api
        and result["needs_user_action"]
        and config.get("auto_suggest_corrections")
        and not str(result.get("suggested_response") or "").strip()
    ):
        correction = _generate_correction_suggestion(user_message, ai_reply, result, config)
        if correction:
            result["suggested_response"] = correction["suggested_response"]
            if correction.get("reason"):
                result["correction_reason"] = correction["reason"]
            result["correction_source"] = "audit_ai"
        else:
            result["correction_error"] = "审计 AI 改写建议请求失败或返回为空"
    elif (
        result["needs_user_action"]
        and config.get("auto_suggest_corrections")
        and not str(result.get("suggested_response") or "").strip()
        and not has_api
    ):
        result["correction_error"] = "未配置审计 API Key，无法请求改写建议"

    # Automatic learning is intentionally limited to an external audit that
    # supplied an answer ready for training. Local fallback findings and audit
    # results without a replacement remain in the human review workflow.
    suggested = str(result.get("suggested_response") or "").strip()
    if (
        allow_api
        and config.get("auto_suggest_corrections")
        and result.get("audit_source") == "api"
        and suggested
    ):
        result["auto_apply_suggested_correction"] = True
        result["review_status"] = "auto_applied"
    return result



def _normalize_history(history: list | None, max_turns: int = 6) -> list[tuple[str, str]]:
    """Accept tuple history or chat history dicts and return (user, ai) pairs."""
    if not history:
        return []
    pairs: list[tuple[str, str]] = []
    for item in history:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            user_msg = str(item[0] or "").strip()
            ai_msg = str(item[1] or "").strip()
            if user_msg or ai_msg:
                pairs.append((user_msg, ai_msg))
            continue
        if isinstance(item, dict):
            user_msg = str(
                item.get("user")
                or item.get("user_message")
                or item.get("message")
                or item.get("prompt")
                or ""
            ).strip()
            ai_msg = str(
                item.get("assistant")
                or item.get("ai")
                or item.get("ai_reply")
                or item.get("reply")
                or item.get("response")
                or ""
            ).strip()
            if user_msg or ai_msg:
                pairs.append((user_msg, ai_msg))
    return pairs[-max(1, int(max_turns or 1)):]


def audit_conversation(
    user_message: str,
    ai_reply: str,
    history: list[tuple[str, str]] | None = None,
    config: dict | None = None,
) -> dict | None:
    """Audit a single conversation turn.

    Returns audit result dict or None if failed.
    """
    if config is None:
        config = load_audit_config()

    api_key = config.get("api_key", "")
    local_fallback = config.get("local_fallback", True)
    allow_api = bool(config.get("use_cloud_audit", False)) and bool(str(api_key or "").strip())

    if not allow_api and local_fallback:
        result = _local_audit(user_message, ai_reply)
        result["timestamp"] = datetime.now().isoformat()
        result["user_message"] = user_message[:500]
        result["ai_reply"] = ai_reply[:500]
        result["audit_error"] = "本地规则审计模式（云端审计未启用）"
        return _attach_review_metadata(result, user_message, ai_reply, config, allow_api=allow_api)
    if not allow_api:
        return None

    # Build context
    context_parts = []
    identity_context = _audit_identity_context()
    if identity_context:
        context_parts.append(f"[AI 身份设定]\n{identity_context}")
    max_turns = int(config.get("max_context_turns", 3) or 3)
    for user_msg, ai_msg in _normalize_history(history, max_turns):
        if user_msg:
            context_parts.append(f"用户: {user_msg}")
        if ai_msg:
            context_parts.append(f"AI: {ai_msg}")

    context_parts.append(f"用户: {user_message}")
    context_parts.append(f"AI: {ai_reply}")

    user_prompt = f"请审计以下对话：\n\n" + "\n".join(context_parts)

    response = call_ai_api(config, AUDIT_SYSTEM_PROMPT, user_prompt)
    if not response:
        if local_fallback:
            result = _local_audit(user_message, ai_reply)
            result["timestamp"] = datetime.now().isoformat()
            result["user_message"] = user_message[:500]
            result["ai_reply"] = ai_reply[:500]
            result["audit_error"] = "审计 AI 调用失败或返回空内容，已回退本地规则审计"
            # Still allow a second-chance rewrite request when auto-suggest is on.
            return _attach_review_metadata(result, user_message, ai_reply, config, allow_api=allow_api)
        return None

    result = _extract_json_object(response)
    if result is not None:
        result["timestamp"] = datetime.now().isoformat()
        result["user_message"] = user_message[:500]  # Truncate for storage
        result["ai_reply"] = ai_reply[:500]
        result["audit_source"] = "api"
        return _attach_review_metadata(result, user_message, ai_reply, config, allow_api=allow_api)

    print(f"[audit] Failed to parse audit result: {response[:200]}")
    if local_fallback:
        result = _local_audit(user_message, ai_reply)
        result["timestamp"] = datetime.now().isoformat()
        result["user_message"] = user_message[:500]
        result["ai_reply"] = ai_reply[:500]
        result["audit_parse_error"] = response[:500]
        result["audit_error"] = "审计 AI 返回无法解析为 JSON，已回退本地规则审计"
        return _attach_review_metadata(result, user_message, ai_reply, config, allow_api=allow_api)
    return None


# ── Background Processing ─────────────────────────────────────────────

def _audit_worker():
    """Background thread that processes audit queue."""
    global _running, _current_audit_id, _current_audit_status

    while _running:
        config = load_audit_config()
        batch_size = config.get("batch_size", 5)
        items = []
        with _queue_lock:
            while _audit_queue and len(items) < batch_size:
                items.append(_audit_queue.pop(0))

        if not items:
            time.sleep(1)
            continue

        for item in items:
            try:
                audit_id = item.get("audit_id")
                with _status_lock:
                    _current_audit_id = audit_id
                    _current_audit_status = "processing"
                
                result = audit_conversation(
                    item["user_message"],
                    item["ai_reply"],
                    item.get("history"),
                    config,
                )
                
                with _status_lock:
                    if _current_audit_id == audit_id:
                        _current_audit_status = "completed" if result else "failed"
                
                if result:
                    if item.get("audit_id"):
                        result["audit_id"] = item["audit_id"]
                    _save_audit_result(result)
                    print(
                        f"[audit] saved source={result.get('audit_source')} "
                        f"needs={result.get('needs_user_action')} "
                        f"id={result.get('audit_id')}"
                    )
            except Exception as e:
                with _status_lock:
                    _current_audit_status = "failed"
                print(f"[audit] Worker error: {e}")
                traceback.print_exc()

        # Rate limiting only when queue is idle after this batch.
        with _queue_lock:
            pending = len(_audit_queue)
        if pending == 0:
            with _status_lock:
                _current_audit_id = None
                _current_audit_status = None
            time.sleep(config.get("audit_interval", 10))
        else:
            time.sleep(0.2)


def _save_audit_result(result: dict) -> None:
    """Save a single audit result to JSONL file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not result.get("audit_id"):
        seed = "|".join([
            str(result.get("timestamp") or ""),
            str(result.get("user_message") or ""),
            str(result.get("ai_reply") or ""),
        ])
        result["audit_id"] = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    audit_id = str(result.get("audit_id") or "").strip()
    with _write_lock:
        if audit_id and AUDIT_RESULTS_FILE.exists():
            try:
                for line in AUDIT_RESULTS_FILE.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if str(item.get("audit_id") or "").strip() == audit_id:
                        return
            except Exception:
                pass
        with open(AUDIT_RESULTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    _update_summary(result)
    _apply_to_growth(result)
    _apply_to_training(result)

    # Push correction to pending buffer if there's a suggested_response
    suggested = str(result.get("suggested_response") or "").strip()
    if (
        suggested
        and result.get("needs_user_action")
        and not result.get("auto_apply_suggested_correction")
    ):
        with _corrections_lock:
            _pending_corrections.append({
                "audit_id": result.get("audit_id", ""),
                "user_message": result.get("user_message", ""),
                "original_reply": result.get("ai_reply", ""),
                "suggested_response": suggested,
                "reason": result.get("correction_reason", ""),
                "overall_correctness": _score_value(result, "ai_correctness", "overall_correctness"),
                "overall_score": _score_value(result, "ai_quality", "overall_score"),
            })


def _conversation_audit_id(user_message: str, ai_reply: str) -> str:
    payload = "|".join([str(user_message or ""), str(ai_reply or "")])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _audit_result_exists(audit_id: str) -> bool:
    audit_id = str(audit_id or "").strip()
    if not audit_id or not AUDIT_RESULTS_FILE.exists():
        return False
    with _write_lock:
        try:
            for line in AUDIT_RESULTS_FILE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if str(item.get("audit_id") or "").strip() == audit_id:
                    return True
        except Exception:
            return False
    return False


def _apply_to_growth(result: dict) -> None:
    """Apply audit result to companion growth system."""
    try:
        from companion_growth import apply_audit_feedback
        apply_audit_feedback(result)
    except ImportError:
        print("[audit] companion_growth module not found")
    except Exception as e:
        print(f"[audit] Failed to apply audit feedback to growth: {e}")


def _apply_to_training(result: dict) -> None:
    """Persist an automatically accepted cloud rewrite as a training example."""
    if not result.get("auto_apply_suggested_correction"):
        return
    try:
        from audit_training import record_audit_training
        record_audit_training(
            result,
            decision="auto_correct",
            corrected_response=str(result.get("suggested_response") or ""),
        )
    except ImportError:
        print("[audit] audit_training module not found")
    except Exception as e:
        print(f"[audit] Failed to apply audit result to training: {e}")


def _update_summary(result: dict) -> None:
    """Update running summary of audit results."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _write_lock:
        summary = {}
        if AUDIT_SUMMARY_FILE.exists():
            try:
                summary = json.loads(AUDIT_SUMMARY_FILE.read_text(encoding="utf-8"))
            except Exception:
                summary = {}

        # Update counters
        summary.setdefault("total_audits", 0)
        summary["total_audits"] += 1

        # Update quality averages
        quality = result.get("ai_quality", {})
        for key in ["relevance", "helpfulness", "clarity", "overall_score"]:
            val = quality.get(key)
            if val is not None:
                summary.setdefault(f"avg_{key}", {"sum": 0.0, "count": 0})
                summary[f"avg_{key}"]["sum"] += val
                summary[f"avg_{key}"]["count"] += 1
                summary[f"avg_{key}"]["value"] = (
                    summary[f"avg_{key}"]["sum"] / summary[f"avg_{key}"]["count"]
                )

        # Update correctness averages
        correctness = result.get("ai_correctness", {})
        for key in ["factual_correctness", "answer_completeness", "reasoning_correctness", "overall_correctness"]:
            val = correctness.get(key)
            if val is not None:
                summary.setdefault(f"avg_{key}", {"sum": 0.0, "count": 0})
                summary[f"avg_{key}"]["sum"] += val
                summary[f"avg_{key}"]["count"] += 1
                summary[f"avg_{key}"]["value"] = (
                    summary[f"avg_{key}"]["sum"] / summary[f"avg_{key}"]["count"]
                )

        # Track sentiment distribution
        summary.setdefault("user_sentiments", {})
        user_pol = result.get("user_sentiment", {}).get("polarity", "unknown")
        summary["user_sentiments"][user_pol] = summary["user_sentiments"].get(user_pol, 0) + 1

        summary.setdefault("ai_sentiments", {})
        ai_pol = result.get("ai_sentiment", {}).get("polarity", "unknown")
        summary["ai_sentiments"][ai_pol] = summary["ai_sentiments"].get(ai_pol, 0) + 1

        # Track sentiment judgment accuracy
        sentiment_judgment = result.get("sentiment_judgment", {})
        judgment_correct = sentiment_judgment.get("correct")
        if judgment_correct is not None:
            summary.setdefault("sentiment_judgment", {"correct": 0, "incorrect": 0, "total": 0})
            summary["sentiment_judgment"]["total"] += 1
            if judgment_correct:
                summary["sentiment_judgment"]["correct"] += 1
            else:
                summary["sentiment_judgment"]["incorrect"] += 1

        # Track suggestions
        suggestions = result.get("suggestions", [])
        if suggestions:
            summary.setdefault("recent_suggestions", [])
            summary["recent_suggestions"].extend(suggestions[:2])
            summary["recent_suggestions"] = summary["recent_suggestions"][-20:]

        summary["last_audit_time"] = result.get("timestamp")

        AUDIT_SUMMARY_FILE.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# ── Public Interface ──────────────────────────────────────────────────

def start_audit_worker():
    """Start the background audit worker thread."""
    global _audit_thread, _running
    if _audit_thread and _audit_thread.is_alive():
        return
    _running = True
    _audit_thread = threading.Thread(target=_audit_worker, daemon=True, name="audit-worker")
    _audit_thread.start()


def stop_audit_worker():
    """Stop the background audit worker thread."""
    global _running
    _running = False
    if _audit_thread:
        _audit_thread.join(timeout=5)


def submit_audit(
    user_message: str,
    ai_reply: str,
    history: list[tuple[str, str]] | None = None,
) -> None:
    """Submit a conversation for async audit.

    This is the main entry point called from handle_chat.
    Non-blocking: adds to queue for background processing.
    """
    if not is_audit_enabled():
        return

    audit_id = _conversation_audit_id(user_message, ai_reply)
    if _audit_result_exists(audit_id):
        return

    if not _audit_thread or not _audit_thread.is_alive():
        start_audit_worker()

    with _queue_lock:
        if any(item.get("audit_id") == audit_id for item in _audit_queue):
            return
        config = load_audit_config()
        _audit_queue.append({
            "user_message": user_message,
            "ai_reply": ai_reply,
            "history": _normalize_history(history, int(config.get("max_context_turns", 6) or 6)),
            "audit_id": audit_id,
        })


def get_audit_summary() -> dict:
    """Get the current audit summary."""
    if AUDIT_SUMMARY_FILE.exists():
        try:
            return json.loads(AUDIT_SUMMARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"total_audits": 0}


def get_recent_audits(limit: int = 10) -> list[dict]:
    """Get recent audit results."""
    if not AUDIT_RESULTS_FILE.exists():
        return []
    results: list[dict] = []
    with _write_lock:
        try:
            lines = AUDIT_RESULTS_FILE.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        if not item.get("audit_id"):
            item["audit_id"] = _conversation_audit_id(
                str(item.get("user_message") or ""),
                str(item.get("ai_reply") or ""),
            )
        existing_suggestion = str(item.get("suggested_response") or "").strip()
        if existing_suggestion and not _trainable_suggested_response(existing_suggestion):
            item["suggested_response"] = ""
            item["correction_error"] = "审计 AI 返回了分析文本，不会作为训练建议保存"
        results.append(item)
    return sorted(results, key=lambda item: str(item.get("timestamp") or ""), reverse=True)[:limit]


def get_audit_status() -> dict:
    """Get current audit status for UI display."""
    global _current_audit_id, _current_audit_status
    status = {
        "enabled": is_audit_enabled(),
        "worker_running": False,
        "queue_size": 0,
        "current_audit_id": None,
        "current_status": None,
    }
    if _audit_thread and _audit_thread.is_alive():
        status["worker_running"] = True
    with _queue_lock:
        status["queue_size"] = len(_audit_queue)
    with _status_lock:
        status["current_audit_id"] = _current_audit_id
        status["current_status"] = _current_audit_status
    return status


def get_audit_context_for_chat() -> str:
    """Generate context string to include in chat prompt.

    This feeds audit insights back to the AI so it can improve.
    """
    summary = get_audit_summary()
    if summary.get("total_audits", 0) < 3:
        return ""

    parts = ["[对话审计反馈]"]

    # Correctness scores
    correctness_lines = []
    for key, label in [
        ("avg_factual_correctness", "事实正确性"),
        ("avg_answer_completeness", "回答完整性"),
        ("avg_reasoning_correctness", "推理正确性"),
        ("avg_overall_correctness", "正确性"),
    ]:
        if key in summary:
            val = summary[key].get("value", 0)
            correctness_lines.append(f"{label}:{val:.0%}")

    if correctness_lines:
        parts.append(f"正确性 - {' | '.join(correctness_lines)}")

    # Quality scores
    quality_lines = []
    for key, label in [
        ("avg_relevance", "相关性"),
        ("avg_helpfulness", "有用性"),
        ("avg_clarity", "清晰度"),
        ("avg_overall_score", "综合"),
    ]:
        if key in summary:
            val = summary[key].get("value", 0)
            quality_lines.append(f"{label}:{val:.0%}")

    if quality_lines:
        parts.append(f"质量评分 - {' | '.join(quality_lines)}")

    # Sentiment judgment accuracy
    sentiment_judgment = summary.get("sentiment_judgment", {})
    judgment_total = sentiment_judgment.get("total", 0)
    judgment_correct = sentiment_judgment.get("correct", 0)
    if judgment_total > 0:
        accuracy = judgment_correct / judgment_total
        parts.append(f"情感判断正确率: {accuracy:.0%}")
        if accuracy < 0.7:
            parts.append("警告：情感判断准确率较低，请仔细分析用户情绪。")

    # Sentiment balance
    user_sentiments = summary.get("user_sentiments", {})
    negative_count = user_sentiments.get("负面", 0)
    total_user = sum(user_sentiments.values())
    if total_user > 0 and negative_count / total_user > 0.3:
        parts.append("注意：近期用户负面情绪较多，请多关注和共情。")

    # Recent suggestions
    suggestions = summary.get("recent_suggestions", [])
    if suggestions:
        unique_suggestions = list(dict.fromkeys(suggestions))[-3:]
        parts.append("改进建议：" + "；".join(unique_suggestions))

    return "\n".join(parts) if len(parts) > 1 else ""


# ── Audit Commands ────────────────────────────────────────────────────

def handle_audit_command(message: str) -> dict | None:
    """Handle audit-related commands. Returns reply dict or None."""

    if message == "/audit_status":
        config = load_audit_config()
        summary = get_audit_summary()
        enabled = is_audit_enabled()

        lines = [
            "对话审计状态：",
            f"  启用：{'是' if enabled else '否'}",
            f"  模式：{'云端辅助' if config.get('use_cloud_audit') else '本地规则（默认）'}",
            f"  API: {config.get('api_base', '未设置')}",
            f"  模型：{config.get('model', '未设置')}",
            f"  已审计：{summary.get('total_audits', 0)} 条",
        ]

        if summary.get("total_audits", 0) > 0:
            lines.append("\n正确性评分：")
            for key, label in [
                ("avg_factual_correctness", "事实正确性"),
                ("avg_answer_completeness", "回答完整性"),
                ("avg_reasoning_correctness", "推理正确性"),
                ("avg_overall_correctness", "正确性"),
            ]:
                if key in summary:
                    val = summary[key].get("value", 0)
                    lines.append(f"  {label}: {val:.0%}")

            lines.append("\n质量评分：")
            for key, label in [
                ("avg_relevance", "相关性"),
                ("avg_helpfulness", "有用性"),
                ("avg_clarity", "清晰度"),
                ("avg_overall_score", "综合"),
            ]:
                if key in summary:
                    val = summary[key].get("value", 0)
                    lines.append(f"  {label}: {val:.0%}")

            # Sentiment judgment accuracy
            sentiment_judgment = summary.get("sentiment_judgment", {})
            judgment_total = sentiment_judgment.get("total", 0)
            judgment_correct = sentiment_judgment.get("correct", 0)
            if judgment_total > 0:
                accuracy = judgment_correct / judgment_total
                lines.append(f"\n情感判断准确率：{accuracy:.0%} ({judgment_correct}/{judgment_total})")

            lines.append("\n用户情感分布：")
            for pol, count in summary.get("user_sentiments", {}).items():
                lines.append(f"  {pol}: {count}")

        return {"reply": "\n".join(lines)}

    if message == "/audit_enable":
        config = load_audit_config()
        config["enabled"] = not config.get("enabled", False)
        save_audit_config(config)
        return {"reply": f"审计已{'启用' if config['enabled'] else '禁用'}。"}

    if message in {"/audit_cloud_on", "/audit_cloud_off"}:
        config = load_audit_config()
        enabled = message == "/audit_cloud_on"
        if enabled and not config.get("api_key"):
            return {"reply": "未配置审计 API Key，无法启用云端审计。"}
        config["use_cloud_audit"] = enabled
        save_audit_config(config)
        return {"reply": "已启用云端审计辅助。" if enabled else "已切回本地规则审计。"}

    if message == "/audit_config":
        config = load_audit_config()
        # Mask API key
        masked = dict(config)
        if masked.get("api_key"):
            key = masked["api_key"]
            masked["api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
        lines = ["当前审计配置："]
        for k, v in masked.items():
            lines.append(f"  {k}: {v}")
        lines.append("\n编辑 data/audit_config.json 修改配置。")
        return {"reply": "\n".join(lines)}

    if message == "/audit_recent":
        results = get_recent_audits(5)
        if not results:
            return {"reply": "暂无审计记录。"}
        lines = [f"最近 {len(results)} 条审计："]
        for r in results:
            ts = r.get("timestamp", "?")[:16]
            user_em = r.get("user_sentiment", {}).get("emotion", "?")
            ai_score = r.get("ai_quality", {}).get("overall_score", 0)
            lines.append(f"  [{ts}] 用户:{user_em} | AI评分:{ai_score:.0%}")
        return {"reply": "\n".join(lines)}

    return None


def get_pending_corrections() -> list[dict]:
    """Return and clear pending audit corrections for the chat UI.

    Each call drains the buffer so corrections are shown only once.
    """
    with _corrections_lock:
        corrections = list(_pending_corrections)
        _pending_corrections.clear()
    return corrections
