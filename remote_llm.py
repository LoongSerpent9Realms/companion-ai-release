"""
remote_llm.py - optional OpenAI-compatible large-model gateway.

This module only replaces the reply generator when enabled. Local memory,
profile, skills, history, and training flows remain owned by the existing app.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from _paths import module_root, data_dir

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
REMOTE_LLM_CONFIG_FILE = DATA_DIR / "remote_llm_config.json"

REMOTE_LLM_SYSTEM_PROMPT = (
    "你是用户本机 Companion AI 的对话大模型后端。"
    "你只会收到当前用户消息、用户主动提供的网页或文件摘要、用户显式设置的角色风格摘要，以及用户画像的精简个性化摘要。"
    "完整本地记忆、完整用户画像、关系成长、训练数据和审计记录不会外发给你。"
    "请自然回答用户；不要声称自己已经修改、删除或保存了本地记忆。"
)

DEFAULT_REMOTE_LLM_CONFIG = {
    "enabled": False,
    "enabled_for_hybrid": True,
    "api_base": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 1024,
    "timeout": 45,
    "reasoning_enabled": False,
    "reasoning_effort": "medium",
    "system_prompt": REMOTE_LLM_SYSTEM_PROMPT,
    "user_prompt": "",
}


_SECTION_HEADER_RE = re.compile(r"(?m)^\[([^\]\n]+)\]\n")
_API_ALLOWED_SECTION_PREFIXES = ("外部API可见风格", "外部API可见个性化", "用户消息", "已读取网页", "已读取文件")


def sanitize_message_for_api(message: str) -> str:
    """Keep only user-intended content before sending text to a remote LLM API."""
    text = str(message or "")
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return text[:12000]

    allowed: list[str] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if title.startswith(_API_ALLOWED_SECTION_PREFIXES) and body:
            if title == "用户消息":
                allowed.append(body)
            else:
                allowed.append(f"[{title}]\n{body}")

    if allowed:
        return "\n\n".join(allowed)[:12000]
    return text[:12000]


def _coerce_config(data: dict | None = None) -> dict:
    raw = dict(DEFAULT_REMOTE_LLM_CONFIG)
    incoming = data if isinstance(data, dict) else {}
    if isinstance(data, dict):
        raw.update(data)
    if not raw.get("api_key"):
        raw["api_key"] = os.environ.get("COMPANION_LLM_API_KEY", "")
    raw["api_base"] = str(raw.get("api_base") or DEFAULT_REMOTE_LLM_CONFIG["api_base"]).rstrip("/")
    raw["model"] = str(raw.get("model") or DEFAULT_REMOTE_LLM_CONFIG["model"]).strip()
    raw["enabled"] = bool(raw.get("enabled"))
    raw["enabled_for_hybrid"] = bool(raw.get("enabled_for_hybrid", True))
    try:
        raw["temperature"] = max(0.0, min(2.0, float(raw.get("temperature", 0.7))))
    except Exception:
        raw["temperature"] = 0.7
    try:
        raw["max_tokens"] = max(64, min(8192, int(raw.get("max_tokens", 1024))))
    except Exception:
        raw["max_tokens"] = 1024
    try:
        raw["timeout"] = max(5, min(180, int(raw.get("timeout", 45))))
    except Exception:
        raw["timeout"] = 45
    raw["user_prompt"] = str(raw.get("user_prompt") or "").strip()
    raw["reasoning_enabled"] = bool(raw.get("reasoning_enabled"))
    effort = str(raw.get("reasoning_effort") or "medium").lower().strip()
    raw["reasoning_effort"] = effort if effort in {"low", "medium", "high"} else "medium"
    raw["system_prompt"] = str(raw.get("system_prompt") or DEFAULT_REMOTE_LLM_CONFIG["system_prompt"]).strip()
    if (
        "现实上下文、用户画像、记忆" in raw["system_prompt"]
        or "你只会收到当前用户消息，以及用户主动提供" in raw["system_prompt"]
        or "用户显式设置的角色风格摘要" in raw["system_prompt"]
    ):
        raw["system_prompt"] = DEFAULT_REMOTE_LLM_CONFIG["system_prompt"]
    if not raw["user_prompt"] and "user_prompt" not in incoming:
        old_prompt = str(incoming.get("system_prompt") or "").strip()
        if old_prompt and old_prompt != DEFAULT_REMOTE_LLM_CONFIG["system_prompt"]:
            raw["user_prompt"] = old_prompt
            raw["system_prompt"] = DEFAULT_REMOTE_LLM_CONFIG["system_prompt"]
    return raw


def effective_remote_llm_system_prompt(config: dict) -> str:
    """Build the system prompt sent to the remote model."""
    base = str(config.get("system_prompt") or DEFAULT_REMOTE_LLM_CONFIG["system_prompt"]).strip()
    user_prompt = str(config.get("user_prompt") or "").strip()
    if user_prompt:
        return f"{base}\n\n[用户设置的提示词]\n{user_prompt}"
    return base


def load_remote_llm_config() -> dict:
    if REMOTE_LLM_CONFIG_FILE.exists():
        try:
            return _coerce_config(json.loads(REMOTE_LLM_CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return _coerce_config()


def save_remote_llm_config(updates: dict) -> dict:
    config = load_remote_llm_config()
    for key in DEFAULT_REMOTE_LLM_CONFIG:
        if key in updates:
            config[key] = updates[key]
    config = _coerce_config(config)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REMOTE_LLM_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def public_remote_llm_config(config: dict | None = None) -> dict:
    data = dict(config or load_remote_llm_config())
    key = str(data.get("api_key") or "")
    data["configured"] = bool(key)
    if key:
        data["api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    data.pop("system_prompt", None)
    return data


def is_remote_llm_ready(config: dict | None = None) -> bool:
    data = config or load_remote_llm_config()
    return bool(data.get("enabled") and data.get("api_key") and data.get("api_base") and data.get("model"))


def list_available_models(api_base: str, api_key: str, timeout: int = 15) -> dict:
    """List models from an OpenAI-compatible API without persisting the key."""
    base = str(api_base or "").strip().rstrip("/")
    key = str(api_key or "").strip()
    if not base or not key:
        return {"ok": False, "models": [], "error": "缺少 API Base 或 API Key"}
    if not re.match(r"^https?://", base, re.IGNORECASE):
        return {"ok": False, "models": [], "error": "API Base 必须以 http:// 或 https:// 开头"}

    if base.endswith("/chat/completions"):
        base = base.removesuffix("/chat/completions")
    url = base if base.endswith("/models") else f"{base}/models"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            # Some API gateways reject urllib's default user agent before the
            # request reaches their OpenAI-compatible endpoint.
            "User-Agent": "CompanionAI/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5, min(int(timeout), 60))) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = _api_error_detail(exc.read().decode("utf-8", errors="ignore"))
        finally:
            exc.close()
        if exc.code == 403 and detail == "服务器返回了网页防护页":
            detail = (
                "服务器拒绝了模型列表请求（网页防护页）。请确认 API Base 是服务商提供的 API 地址"
                "（通常以 /v1 结尾），并检查该服务是否限制当前 IP；也可手动填写模型名后测试连接。"
            )
        return {"ok": False, "models": [], "error": f"获取模型失败：HTTP {exc.code} {detail}".strip()}
    except Exception as exc:
        return {"ok": False, "models": [], "error": f"获取模型失败：{exc}"}

    entries = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return {"ok": False, "models": [], "error": "模型接口返回格式无效"}
    models: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            model_id = entry.strip()
        elif isinstance(entry, dict):
            model_id = str(entry.get("id") or entry.get("name") or entry.get("model") or "").strip()
        else:
            model_id = ""
        if model_id and model_id not in models:
            models.append(model_id)
    if not models:
        return {"ok": False, "models": [], "error": "接口没有返回可用模型"}
    return {"ok": True, "models": models}


def _api_error_detail(body: str) -> str:
    """Extract a concise, safe error summary from an API error response."""
    text = str(body or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if "<html" in text.lower() or "<!doctype html" in text.lower():
            return "服务器返回了网页防护页"
        return re.sub(r"\s+", " ", text)[:200]

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or error.get("code")
        else:
            message = error or payload.get("message") or payload.get("detail")
        if message:
            return re.sub(r"\s+", " ", str(message)).strip()[:200]
    return "接口返回错误"


def call_remote_llm(
    message: str,
    history: list[tuple[str, str]] | None = None,
    config: dict | None = None,
) -> str:
    data = config or load_remote_llm_config()
    if not is_remote_llm_ready(data):
        return "[大模型接口未启用或未配置]"

    messages = [{"role": "system", "content": effective_remote_llm_system_prompt(data)}]
    if history:
        for user_msg, assistant_msg in history[-6:]:
            if user_msg:
                messages.append({"role": "user", "content": str(user_msg)[:4000]})
            if assistant_msg:
                messages.append({"role": "assistant", "content": str(assistant_msg)[:4000]})
    api_message = sanitize_message_for_api(message)
    messages.append({"role": "user", "content": api_message})

    payload_data = {
        "model": data["model"],
        "messages": messages,
        "temperature": data["temperature"],
        "max_tokens": data["max_tokens"],
    }
    # The field is omitted unless explicitly enabled, preserving compatibility
    # with providers that only implement the baseline chat-completions schema.
    if data.get("reasoning_enabled"):
        payload_data["reasoning"] = {"effort": data["reasoning_effort"]}
    payload = json.dumps(payload_data).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {data['api_key']}",
    }
    req = urllib.request.Request(
        f"{data['api_base']}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=data["timeout"]) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
        finally:
            exc.close()
        return f"[大模型接口请求失败: HTTP {exc.code} {detail}]"
    except Exception as exc:
        return f"[大模型接口请求失败: {exc}]"

    choices = body.get("choices") or []
    if not choices:
        return "[大模型接口没有返回回复]"
    reply = choices[0].get("message", {}).get("content", "")
    return str(reply).strip() or "[大模型接口返回了空回复]"


def test_remote_llm_connection(config: dict | None = None) -> dict:
    """Send a minimal request to verify the OpenAI-compatible backend."""
    data = _coerce_config(config or load_remote_llm_config())
    if not is_remote_llm_ready(data):
        return {"ok": False, "error": "大模型接口未启用或缺少 API Base / API Key / 模型"}

    started = time.perf_counter()
    reply = call_remote_llm(
        "请只回复：连接测试成功",
        history=[],
        config={**data, "max_tokens": min(int(data.get("max_tokens", 1024)), 64)},
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not reply or reply.startswith("["):
        return {"ok": False, "error": reply or "没有返回内容", "latency_ms": latency_ms}
    return {"ok": True, "reply": reply, "latency_ms": latency_ms}


def remote_llm_status_text() -> str:
    config = load_remote_llm_config()
    public = public_remote_llm_config(config)
    lines = [
        "大模型接口状态：",
        f"  状态: {'已启用' if config.get('enabled') else '未启用'}",
        f"  混合模式参与: {'是' if config.get('enabled_for_hybrid') else '否'}",
        f"  API Base: {config.get('api_base')}",
        f"  模型: {config.get('model')}",
        f"  API Key: {'已配置 ' + public.get('api_key', '') if public.get('configured') else '未配置'}",
        "",
        "命令：",
        "  /api_llm_on 或 /api_llm_off",
        "  /chat_mode api_llm",
        "  /api_llm_config <api_base> <model> <api_key>",
    ]
    return "\n".join(lines)


def handle_remote_llm_command(message: str) -> str | None:
    text = message.strip()
    if text in {"/api_llm", "/api_llm_status", "/remote_llm", "/remote_llm_status"}:
        return remote_llm_status_text()
    if text in {"/api_llm_test", "/remote_llm_test"}:
        result = test_remote_llm_connection()
        if result.get("ok"):
            return f"大模型接口连接测试成功（{result.get('latency_ms')} ms）：\n{result.get('reply', '')}"
        return f"大模型接口连接测试失败：\n{result.get('error', '未知错误')}"
    if text == "/api_llm_on":
        config = save_remote_llm_config({"enabled": True})
        if not config.get("api_key"):
            return remote_llm_status_text() + "\n\n已开启开关，但还没有 API Key。请先在设置里保存，或使用 /api_llm_config。"
        return remote_llm_status_text()
    if text == "/api_llm_off":
        save_remote_llm_config({"enabled": False})
        return "已关闭大模型接口；本地记忆、训练和规则回复仍可继续使用。"
    if text.startswith("/api_llm_hybrid "):
        value = text.split(maxsplit=1)[1].strip().lower()
        enabled = value in {"1", "true", "yes", "on", "开", "开启", "启用"}
        save_remote_llm_config({"enabled_for_hybrid": enabled})
        return f"已{'允许' if enabled else '禁止'}大模型接口参与混合模式。"
    if text.startswith("/api_llm_config "):
        body = text.removeprefix("/api_llm_config ").strip()
        parts = body.split(maxsplit=2)
        if len(parts) != 3:
            return "格式：/api_llm_config <api_base> <model> <api_key>"
        config = save_remote_llm_config({
            "api_base": parts[0],
            "model": parts[1],
            "api_key": parts[2],
            "enabled": True,
        })
        return "大模型接口已保存并启用。\n\n" + remote_llm_status_text()
    return None
