from __future__ import annotations

import html
import atexit
import hashlib
import hmac
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo
from pathlib import Path, PurePosixPath

try:
    import ctypes
    _HAS_CTYPES = True
except ImportError:
    _HAS_CTYPES = False

import _paths as path_helpers
from _paths import (
    module_root,
    data_dir,
    resource_dir,
    python_exe,
    PYTHON_DOWNLOAD_URL,
)
from sensitive_json import read_sensitive_json, write_sensitive_json
from memory_layer import MemoryStore

runtime_python_exe = getattr(path_helpers, "runtime_python_exe", lambda root=None, create=True: python_exe())
ensure_external_site_packages = getattr(path_helpers, "ensure_external_site_packages", lambda: None)
_external_site_packages_ready = False


def ensure_optional_site_packages() -> None:
    global _external_site_packages_ready
    if _external_site_packages_ready:
        return
    ensure_external_site_packages()
    _external_site_packages_ready = True


from neural_companion import (
    gpu_self_check_isolated,
    neural_status,
    neural_status_text,
    predict_motion,
    train_motion_net,
    train_motion_net_gpu_isolated,
    train_from_dataset,
)
from operation_learning import (
    ACTION_FILE,
    action_plan_text,
    action_status_text,
    best_action_skill,
    evolution_summary,
    learn_action_skill,
    list_action_skills,
    load_action_store,
    record_action_outcome,
    save_action_store,
)
from plugin_manager import PluginManager, validate_plugin_package
from dialogue_skills import (
    handle_dialogue_skill_command,
    list_dialogue_skills_text,
    load_dialogue_skills,
    match_dialogue_skill,
    save_dialogue_skills,
    skill_reply,
)
from user_profile import (
    clear_user_profile,
    handle_profile_command,
    load_user_profile,
    observe_user_message,
    profile_context,
    profile_summary,
)
from routine_tracker import (
    handle_routine_command,
    install_shutdown_handlers,
    load_routine,
    record_app_start,
    record_app_stop,
    reset_routine_encryption_key,
    routine_status_text,
    routine_tick,
)
from memory_transfer import handle_memory_transfer_command
from emotion_diary import (
    clear_diary,
    clear_emotion,
    emotion_summary_text,
    get_emotion_trend,
    load_diary,
    load_emotion,
    record_emotion_message,
    handle_emotion_diary_command,
    set_emotion_enabled,
    get_diary_entries,
    generate_diary_entry,
    diary_summary_text,
    emotion_daily_tick,
)
from companion_growth import (
    clear_growth,
    configure_relationship,
    events_text,
    growth_context,
    growth_status_text,
    handle_growth_command,
    load_growth,
    observe_chat_interaction,
    record_growth_event,
    save_growth,
)
import tts_engine
import face_manager


ROOT = module_root(__file__)
RES_ROOT = resource_dir(__file__)
DATA_DIR = data_dir(ROOT)
UPLOAD_DIR = DATA_DIR / "uploads"
LIVE2D_DIR = DATA_DIR / "live2d"
LIVE2D_STATE_FILE = DATA_DIR / "live2d.json"
MODEL3D_DIR = DATA_DIR / "3d_models"
MODEL3D_STATE_FILE = DATA_DIR / "3d_models.json"
OCR_DIR = DATA_DIR / "ocr"
RAPIDOCR_DIR = OCR_DIR / "rapidocr"
RAPIDOCR_VENV = RAPIDOCR_DIR / ".venv"
RAPIDOCR_RUNNER = OCR_DIR / "rapidocr_runner.py"

_RAPIDOCR_RUNNER_SOURCE = '''\
from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing image path"}))
        return 2
    image_path = sys.argv[1]
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception:
            from rapidocr import RapidOCR

        engine = RapidOCR()
        result, _elapsed = engine(image_path)
        lines = []
        for item in result or []:
            if len(item) >= 2:
                text = item[1]
                score = item[2] if len(item) >= 3 else None
                lines.append({"text": str(text), "score": float(score) if score is not None else None})
        print(json.dumps({"ok": True, "lines": lines}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
MEMORY_FILE = DATA_DIR / "memory.json"
MEMORY_STORE = MemoryStore(MEMORY_FILE)
HISTORY_FILE = DATA_DIR / "history.jsonl"
RECENT_CHATS_FILE = DATA_DIR / "recent_chats.json"
TRAINING_FILE = DATA_DIR / "training.json"
FILES_FILE = DATA_DIR / "files.json"
MOMENTS_FILE = DATA_DIR / "moments.json"
AVATAR_FILE = DATA_DIR / "avatar.json"
PET_DISPLAY_FILE = DATA_DIR / "pet_display.json"
IDENTITY_FILE = DATA_DIR / "identity.json"
IDLE_EXPLORE_FILE = DATA_DIR / "idle_explore.json"
PRIVACY_CONSENT_FILE = DATA_DIR / "privacy_consent.json"
APP_CONFIG_FILE = DATA_DIR / "app_config.json"
VOICEPRINT_FILE = DATA_DIR / "voiceprints.json"
IDENTITY_CONFIRM_FILE = DATA_DIR / "identity_confirm.json"
UPDATE_STATE_FILE = DATA_DIR / "update_state.json"
UPDATE_DOWNLOAD_DIR = DATA_DIR / "updates"
REALTIME_CHAT_FILE = DATA_DIR / "runtime" / "realtime_chat.json"
MODEL_DIR = DATA_DIR / "models"
ALLOW_LAN = os.environ.get("COMPANION_ALLOW_LAN", "").strip().lower() in {"1", "true", "yes", "on"}
HOST = os.environ.get("COMPANION_HOST", "0.0.0.0" if ALLOW_LAN else "127.0.0.1")
PORT = int(os.environ.get("COMPANION_PORT", "59137"))
OFFICIAL_UPDATE_RELEASE_REPO = "LoongSerpent9Realms/companion-ai-release"
OFFICIAL_UPDATE_RELEASE_PAGE = f"https://github.com/{OFFICIAL_UPDATE_RELEASE_REPO}/releases"
DEFAULT_UPDATE_MANIFEST_URL = os.environ.get(
    "COMPANION_UPDATE_MANIFEST_URL",
    f"https://api.github.com/repos/{OFFICIAL_UPDATE_RELEASE_REPO}/releases/latest",
)
LEGACY_UPDATE_MANIFEST_URLS = {
    "",
    "https://example.com/companion-ai/update.json",
    # older placeholder / wrong hosts that must never be used for checks
    "https://example.invalid/manifest.json",
    "https://api.github.com/repos/example/companion-ai/releases/latest",
}


STOPWORDS = {
    "的", "了", "和", "是", "我", "你", "他", "她", "它", "们", "在", "有", "就", "也", "都", "很",
    "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on", "for", "with",
}

WEATHER_CODES = {
    0: "晴朗", 1: "大致晴朗", 2: "局部多云", 3: "阴天",
    45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "中等毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "短时小阵雨", 81: "短时中阵雨", 82: "强阵雨",
    95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴强冰雹",
}

TESSERACT_INSTALLER_URL = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
SEVEN_ZIP_URL = "https://www.7-zip.org/a/7za920.zip"
INNOEXTRACT_URL = "https://constexpr.org/innoextract/files/innoextract-1.9-windows.zip"
TESSDATA_FAST_URLS = {
    "eng": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata",
    "chi_sim": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/chi_sim.traineddata",
    "chi_tra": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/chi_tra.traineddata",
}

OFFICIAL_SITE_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>智能伙伴</title></head><body>
<h1>智能伙伴</h1>
<p>本地优先的个人 AI：程序可以放在服务器分发，聊天、记忆和训练数据保留在用户本地。</p>
<p><a href="/">打开本地控制台</a></p>
</body></html>"""


plugin_mgr = PluginManager()


def _evaluate_and_create_plugin(message: str, reply: str, history: list, llm_config: dict) -> dict:
    """AI autonomously evaluates if a new plugin is needed and creates it.

    This function is called after each chat interaction to let the AI
    decide if it needs to create a new plugin to enhance its capabilities.
    """
    import json
    import urllib.request
    import urllib.error

    system_prompt = """你是 Companion AI 的自我进化系统。你的任务是分析对话内容，判断是否需要创建新插件来增强能力。

分析标准：
1. 用户反复请求某个 AI 当前无法完成的功能
2. 用户请求的功能需要持久化数据存储或定时执行
3. 用户请求的功能需要特定格式的输出或复杂逻辑处理
4. 用户表达了明确的"想要一个XX功能"的需求

如果需要创建插件，请返回：
{"create": true, "prompt": "插件功能描述"}

如果不需要创建插件，请返回：
{"create": false, "reason": "不需要创建插件的原因"}

注意：
- 只有明确需要时才创建，不要频繁创建插件
- 插件功能描述要简洁明确
- 不要创建已有插件能实现的功能"""

    history_text = "\n".join([f"用户: {h[0]}\nAI: {h[1]}" for h in history[-4:]])
    user_prompt = f"""分析以下对话，判断是否需要创建新插件：

对话历史：
{history_text}

最新对话：
用户: {message}
AI: {reply}

请判断是否需要创建插件来增强能力。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    payload = json.dumps({
        "model": llm_config["model"],
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 512,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_config['api_key']}",
    }
    req = urllib.request.Request(
        f"{llm_config['api_base']}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=llm_config["timeout"]) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "评估请求失败"}

    choices = body.get("choices") or []
    if not choices:
        return {"ok": False, "error": "评估没有返回结果"}

    try:
        result_text = choices[0].get("message", {}).get("content", "").strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        evaluation = json.loads(result_text)
    except Exception:
        return {"ok": False, "error": "评估结果解析失败"}

    if not evaluation.get("create"):
        return {"ok": False, "error": "不需要创建插件"}

    plugin_prompt = evaluation.get("prompt", "")
    if not plugin_prompt:
        return {"ok": False, "error": "插件描述为空"}

    from plugin_manager import auto_create_plugin
    return auto_create_plugin(plugin_prompt, llm_config)


SUPPORTED_LOCALES = {"zh-CN", "en-US"}
DEFAULT_LOCALE = "zh-CN"
I18N_MESSAGES = {
    "zh-CN": {
        "app_name": "AI陪伴桌宠",
        "app_subtitle": "本地运行 · 记忆自训练",
        "privacy_required": "请先同意隐私政策",
        "settings": "设置",
        "language": "语言",
        "chinese": "中文",
        "english": "English",
        "memory_title": "长期记忆",
        "chat_workspace": "对话",
        "function_area": "功能区",
        "context_title": "长期记忆与上下文",
        "composer_tools": "附件、网页与更多",
        "realtime_options": "实时对话选项",
        "memory_loading": "加载中...",
        "training_loading": "训练样本：加载中...",
        "files_empty": "文件：暂无",
        "message_placeholder": "和我说点什么...",
        "url_placeholder": "可选：网页 URL",
        "send": "发送",
        "settings_title": "Companion AI 设置",
        "settings_subtitle": "管理本地能力、模型、身份、语音和插件。",
        "settings_saved": "已保存",
        "i18n_note": "切换后会立即更新核心界面；部分对话内容仍按当前模型和命令语言生成。",
        "memory_orbit_label": "靠近查看 AI 的记忆",
        "memory_orbit_hint": "靠近大脑，查看 AI 正在记住什么",
        "plugin_management": "插件管理",
        "quick_core": "常用入口",
        "quick_learning": "学习与训练",
        "quick_tools": "管理与工具",
        "plugins_loading": "加载中...",
        "refresh_plugins": "刷新插件",
        "new_plugin": "新建插件",
        "live2d_viewer": "Live2D 查看器",
        "web_notice": "只读取你有权访问的网页。不会绕过登录、付费墙、验证码、权限控制或反爬限制。",
        "welcome_message": "我在。可以直接聊天、上传文件、读取网页 URL，也可以用下面的提示词快速开始。\n\n日记、朋友圈、学习训练和管理工具已经移到左侧二级页面入口，聊天页只保留高频操作。",
        "classic_avatar_status": "Live2D 区域：内置 2D 头像 · 动作学习中",
        "current_motion": "当前动作",
        "sample_count": "样本",
        "classic": "经典",
        "personal_background": "个人背景",
        "preferences": "偏好",
        "facts_todos": "事实/待办",
        "none": "暂无",
        "no_long_term_memory": "暂无长期记忆",
        "memory_empty_hint": "聊天中说“记住……”或使用 /remember 后，这里会亮起来。",
        "positive_feedback": "正反馈",
        "negative_feedback": "负反馈",
        "emotion_feedback": "情感反馈",
        "recent_samples": "最近样本：",
        "delete": "删除",
        "question": "问",
        "answer": "答",
        "empty_value": "（空）",
        "source_unknown": "unknown",
        "file_label": "文件",
        "voice_input": "语音输入",
        "realtime_voice": "实时对话",
        "realtime_start": "开启实时对话",
        "realtime_stop": "关闭实时对话",
        "realtime_listening": "实时对话：正在听你说话...",
        "realtime_thinking": "实时对话：思考中...",
        "realtime_speaking": "实时对话：正在播放回复...",
        "realtime_ready": "实时对话已开启，听到一句完整语音后会自动发送。",
        "realtime_off": "实时对话已关闭",
        "realtime_unsupported": "当前浏览器不支持实时语音识别。请使用 Chrome 或 Edge。",
        "realtime_tts_hint": "实时对话会自动开启语音合成和自动播放。",
        "wake_word": "语音唤醒",
        "wake_word_start": "开启语音唤醒",
        "wake_word_stop": "关闭语音唤醒",
        "wake_word_ready": "语音唤醒已开启，说“你好小智”后会开启实时对话。",
        "wake_word_listening": "语音唤醒：等待“你好小智”...",
        "wake_word_heard": "已唤醒，正在开启实时对话...",
        "wake_word_command": "语音唤醒：正在开启实时对话...",
        "wake_word_off": "语音唤醒已关闭",
        "wake_word_unsupported": "当前浏览器不支持语音唤醒。请使用 Chrome 或 Edge。",
        "play_voice": "播放语音",
        "pause_voice": "暂停语音",
        "resume_voice": "继续播放",
        "colon": "：",
        "command_labels": {
            "/memory": "查看记忆",
            "/training": "查看训练状态",
            "/training_samples": "查看训练样本",
            "/accelerate": "培养加速器",
            "/apply_pack companion": "导入陪伴包",
            "/apply_pack work": "导入工作包",
            "/apply_pack web": "导入联网包",
            "/apply_pack game": "导入游戏包",
            "/apply_pack screen": "导入屏幕理解包",
            "/apply_pack all": "导入全部培养包",
            "/rule_templates": "规则模板",
            "/apply_rule_template fresh_web": "导入时效联网",
            "/quick_feedback": "快速反馈",
            "/rules": "查看行为规则",
            "/teach_rule 时效联网 => 最新,最近,现在,今年,目前,新进展 => 先联网搜索并给出来源。": "教一条行为规则",
            "/neural": "神经网络状态",
            "/train_neural": "训练神经网络",
            "/gpu_check": "GPU 自检",
            "/train_neural_gpu": "GPU 隔离训练",
            "/export_model": "生成模型",
            "/actions": "电脑操作学习",
            "/teach_lab": "教学实验室",
            "/context": "查看现实上下文",
            "/idle_explore": "闲置探索状态",
            "/idle_explore_on": "开启闲置探索",
            "/idle_explore_off": "关闭闲置探索",
            "/camera": "观察摄像头",
            "/time": "查看时间",
            "/weather Hong Kong": "查看天气",
            "/learn_status": "联网学习状态",
            "/learn 人工智能最新进展": "学习 AI 最新进展",
            "/learn 网络安全入门": "学习网络安全",
            "/learn_on": "开启联网学习",
            "/learn_off": "关闭联网学习",
            "/self_study_on": "开启自主学习",
            "/self_study_off": "关闭自主学习",
            "self_study_topic_example": "设置学习主题",
            "/ocr": "识别图片文字",
            "/install_ocr": "安装本地 OCR",
            "/chat_mode": "对话模式",
            "/chat_status": "系统状态",
            "/train_tiny": "训练 Tiny LLM",
            "/retrain": "重建检索索引",
            "/datasets": "可用数据集",
            "/llm": "本地 LLM",
            "/profile": "用户画像",
            "/growth": "关系成长",
            "/memory_export": "导出记忆",
            "/routine": "作息记录",
            "/routine_security": "作息加密",
            "/routine_on": "开启作息记录",
            "/startup_on": "开机自启",
            "/skills": "对话技能",
            "/vision": "视觉状态",
            "/see_screen": "观察屏幕",
            "/face_status": "人脸识别状态",
            "/face_list": "已注册人脸",
            "/face_register ": "注册人脸",
            "/face_recognize": "识别人脸",
            "/action_plan 打开常用项目": "生成操作计划",
            "learn_action_example": "示例：教电脑操作",
            "teach_example": "示例：教它一句",
            "emotion_teach_example": "示例：教情绪",
            "remember_example": "示例：写入偏好",
            "chat_example": "示例：陪伴对话",
            "learn_skill_example": "教对话技能"
        },
    },
    "en-US": {
        "app_name": "AI Companion Pet",
        "app_subtitle": "Local runtime · memory self-training",
        "privacy_required": "Please accept the privacy policy first",
        "settings": "Settings",
        "language": "Language",
        "chinese": "中文",
        "english": "English",
        "memory_title": "Long-Term Memory",
        "chat_workspace": "Chat",
        "function_area": "Features",
        "context_title": "Memory & Context",
        "composer_tools": "Files, web & more",
        "realtime_options": "Realtime options",
        "memory_loading": "Loading...",
        "training_loading": "Training samples: loading...",
        "files_empty": "Files: none",
        "message_placeholder": "Say something...",
        "url_placeholder": "Optional: web URL",
        "send": "Send",
        "settings_title": "Companion AI Settings",
        "settings_subtitle": "Manage local capabilities, models, identity, voice, and plugins.",
        "settings_saved": "Saved",
        "i18n_note": "Core UI updates immediately. Some chat content still follows the current model and command language.",
        "memory_orbit_label": "Hover to view AI memory",
        "memory_orbit_hint": "Hover near the brain to see what the AI is remembering",
        "plugin_management": "Plugin Management",
        "quick_core": "Core Shortcuts",
        "quick_learning": "Learning & Training",
        "quick_tools": "Management & Tools",
        "plugins_loading": "Loading...",
        "refresh_plugins": "Refresh Plugins",
        "new_plugin": "New Plugin",
        "live2d_viewer": "Live2D Viewer",
        "web_notice": "Only reads pages you are allowed to access. It will not bypass logins, paywalls, captchas, permissions, or anti-bot controls.",
        "welcome_message": "I'm here. You can chat, upload files, read a page URL, or start with one of the prompts below.\n\nDiary, moments, learning, training, and management tools now live on the secondary pages in the left sidebar.",
        "classic_avatar_status": "Live2D area: built-in 2D avatar · learning motions",
        "current_motion": "Current motion",
        "sample_count": "samples",
        "classic": "Classic",
        "personal_background": "Personal Background",
        "preferences": "Preferences",
        "facts_todos": "Facts / Todos",
        "none": "None",
        "no_long_term_memory": "No long-term memory yet",
        "memory_empty_hint": "Say \"remember...\" or use /remember, and this area will light up.",
        "positive_feedback": "Positive feedback",
        "negative_feedback": "Negative feedback",
        "emotion_feedback": "Emotion feedback",
        "recent_samples": "Recent samples:",
        "delete": "Delete",
        "question": "Q",
        "answer": "A",
        "empty_value": "(empty)",
        "source_unknown": "unknown",
        "file_label": "Files",
        "voice_input": "Voice input",
        "realtime_voice": "Realtime chat",
        "realtime_start": "Start realtime chat",
        "realtime_stop": "Stop realtime chat",
        "realtime_listening": "Realtime chat: listening...",
        "realtime_thinking": "Realtime chat: thinking...",
        "realtime_speaking": "Realtime chat: playing reply...",
        "realtime_ready": "Realtime chat is on. A complete voice sentence will be sent automatically.",
        "realtime_off": "Realtime chat is off",
        "realtime_unsupported": "This browser does not support realtime speech recognition. Please use Chrome or Edge.",
        "realtime_tts_hint": "Realtime chat will enable voice synthesis and auto-play.",
        "wake_word": "Wake word",
        "wake_word_start": "Start wake word",
        "wake_word_stop": "Stop wake word",
        "wake_word_ready": "Wake word is on. Say \"hey companion\" to start realtime chat.",
        "wake_word_listening": "Wake word: waiting for \"hey companion\"...",
        "wake_word_heard": "Wake word heard. Starting realtime chat...",
        "wake_word_command": "Wake word: starting realtime chat...",
        "wake_word_off": "Wake word is off",
        "wake_word_unsupported": "This browser does not support wake word listening. Please use Chrome or Edge.",
        "play_voice": "Play voice",
        "pause_voice": "Pause voice",
        "resume_voice": "Resume voice",
        "colon": ": ",
        "command_labels": {
            "/memory": "Memory",
            "/training": "Training Status",
            "/training_samples": "Training Samples",
            "/accelerate": "Accelerator",
            "/apply_pack companion": "Companion Pack",
            "/apply_pack work": "Work Pack",
            "/apply_pack web": "Web Pack",
            "/apply_pack game": "Game Pack",
            "/apply_pack screen": "Screen Understanding Pack",
            "/apply_pack all": "All Packs",
            "/rule_templates": "Rule Templates",
            "/apply_rule_template fresh_web": "Fresh Web Rule",
            "/quick_feedback": "Quick Feedback",
            "/rules": "Behavior Rules",
            "/teach_rule Fresh Info => latest,recent,now,news,updates => Search the web first and show sources.": "Teach Rule",
            "/neural": "Neural Network",
            "/train_neural": "Train Neural Net",
            "/gpu_check": "GPU Check",
            "/train_neural_gpu": "GPU Isolated Train",
            "/export_model": "Export Model",
            "/actions": "Operation Learning",
            "/teach_lab": "Teaching Lab",
            "/context": "Real-World Context",
            "/idle_explore": "Idle Exploration",
            "/idle_explore_on": "Enable Idle Exploration",
            "/idle_explore_off": "Disable Idle Exploration",
            "/camera": "Observe Camera",
            "/time": "Time",
            "/weather Hong Kong": "Weather",
            "/learn_status": "Web Learning Status",
            "/learn 人工智能最新进展": "Learn AI Updates",
            "/learn 网络安全入门": "Learn Cybersecurity",
            "/learn_on": "Enable Web Learning",
            "/learn_off": "Disable Web Learning",
            "/self_study_on": "Enable Self-Study",
            "/self_study_off": "Disable Self-Study",
            "self_study_topic_example": "Set Study Topics",
            "/ocr": "Image OCR",
            "/install_ocr": "Install Local OCR",
            "/chat_mode": "Chat Mode",
            "/chat_status": "System Status",
            "/train_tiny": "Train Tiny LLM",
            "/retrain": "Rebuild Index",
            "/datasets": "Datasets",
            "/llm": "Local LLM",
            "/profile": "User Profile",
            "/growth": "Growth",
            "/memory_export": "Export Memory",
            "/routine": "Routine",
            "/routine_security": "Routine Encryption",
            "/routine_on": "Enable Routine",
            "/startup_on": "Startup Launch",
            "/skills": "Dialogue Skills",
            "/vision": "Vision Status",
            "/see_screen": "Observe Screen",
            "/face_status": "Face Status",
            "/face_list": "Registered Faces",
            "/face_register ": "Register Face",
            "/face_recognize": "Recognize Face",
            "/action_plan 打开常用项目": "Generate Action Plan",
            "learn_action_example": "Example: Teach Operation",
            "teach_example": "Example: Teach Reply",
            "emotion_teach_example": "Example: Teach Emotion",
            "remember_example": "Example: Save Preference",
            "chat_example": "Example: Companion Chat",
            "learn_skill_example": "Teach Dialogue Skill"
        },
    },
}


def normalize_locale(value: str | None) -> str:
    raw = (value or "").strip().replace("_", "-").lower()
    if raw in {"en", "en-us"}:
        return "en-US"
    if raw in {"zh", "zh-cn", "zh-hans", "cn"}:
        return "zh-CN"
    return DEFAULT_LOCALE


DISPLAY_THEME_IDS = {"soft", "night", "forest", "rose", "mono", "custom"}
DISPLAY_CUSTOM_DEFAULTS = {
    "bg": "#f6f7f9",
    "panel": "#ffffff",
    "panel_soft": "#eef2f7",
    "ink": "#172033",
    "muted": "#657184",
    "accent": "#276ef1",
    "accent_2": "#0b8f6f",
}
DISPLAY_DEFAULTS = {
    "theme": "soft",
    "font_scale": 100,
    "density": 100,
    "radius": 8,
    "sidebar_width": 280,
    "avatar_height": 84,
    "custom": dict(DISPLAY_CUSTOM_DEFAULTS),
}


def normalize_display_config(value: dict | None = None) -> dict:
    raw = value if isinstance(value, dict) else {}
    config = dict(DISPLAY_DEFAULTS)
    theme = str(raw.get("theme") or config["theme"]).strip().lower()
    config["theme"] = theme if theme in DISPLAY_THEME_IDS else DISPLAY_DEFAULTS["theme"]
    for key, low, high in (
        ("font_scale", 85, 125),
        ("density", 80, 125),
        ("radius", 2, 18),
        ("sidebar_width", 240, 440),
        ("avatar_height", 64, 104),
    ):
        try:
            config[key] = max(low, min(high, int(raw.get(key, config[key]))))
        except Exception:
            config[key] = DISPLAY_DEFAULTS[key]
    custom_raw = raw.get("custom") if isinstance(raw.get("custom"), dict) else {}
    custom = dict(DISPLAY_CUSTOM_DEFAULTS)
    for key, fallback in DISPLAY_CUSTOM_DEFAULTS.items():
        color = str(custom_raw.get(key, fallback)).strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            custom[key] = color.lower()
        else:
            custom[key] = fallback
    config["custom"] = custom
    return config


def display_custom_style(display: dict) -> str:
    cfg = normalize_display_config(display)
    if cfg.get("theme") != "custom":
        return ""
    custom = cfg.get("custom") or {}
    bg = custom.get("bg", DISPLAY_CUSTOM_DEFAULTS["bg"])
    return (
        f"--bg:{custom.get('bg', bg)};"
        f"--paper:{bg};"
        f"--panel:{custom.get('panel', DISPLAY_CUSTOM_DEFAULTS['panel'])};"
        f"--panel-soft:{custom.get('panel_soft', DISPLAY_CUSTOM_DEFAULTS['panel_soft'])};"
        f"--ink:{custom.get('ink', DISPLAY_CUSTOM_DEFAULTS['ink'])};"
        f"--muted:{custom.get('muted', DISPLAY_CUSTOM_DEFAULTS['muted'])};"
        f"--accent:{custom.get('accent', DISPLAY_CUSTOM_DEFAULTS['accent'])};"
        f"--accent-2:{custom.get('accent_2', DISPLAY_CUSTOM_DEFAULTS['accent_2'])};"
    )


def load_app_config() -> dict:
    try:
        data = json.loads(APP_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    locale = normalize_locale(data.get("locale"))
    display = normalize_display_config(data.get("display"))
    return {"locale": locale, "display": display}


def save_app_config(config: dict) -> dict:
    next_config = load_app_config()
    if "locale" in config:
        next_config["locale"] = normalize_locale(str(config.get("locale") or ""))
    if "display" in config:
        next_config["display"] = normalize_display_config(config.get("display"))
    APP_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_FILE.write_text(json.dumps(next_config, ensure_ascii=False, indent=2), encoding="utf-8")
    return next_config


def app_i18n_payload() -> dict:
    config = load_app_config()
    locale = config["locale"]
    messages = I18N_MESSAGES.get(locale, I18N_MESSAGES[DEFAULT_LOCALE])
    return {
        "locale": locale,
        "supported": sorted(SUPPORTED_LOCALES),
        "messages": messages,
        "app_name": messages["app_name"],
        "config": config,
    }


def current_app_version() -> str:
    version_path = RES_ROOT / "version.txt"
    if not version_path.exists():
        version_path = ROOT / "version.txt"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
        return value or "0.0.0"
    except Exception:
        return "0.0.0"


def normalize_release_version(version: str) -> str:
    value = str(version or "").strip()
    return re.sub(r"^[vV](?=\d)", "", value)


def _version_key(version: str) -> tuple:
    parts = re.split(r"[^0-9A-Za-z]+", normalize_release_version(version) or "0")
    key = []
    for part in parts:
        if not part:
            continue
        key.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return tuple(key) or ((0, 0),)


def is_newer_version(remote: str, local: str | None = None) -> bool:
    return _version_key(remote) > _version_key(local or current_app_version())


def default_update_state() -> dict:
    return {
        "manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
        "auto_check": True,
        "auto_download": False,
        "auto_install": False,
        "check_interval_hours": 12,
        "last_check": 0,
        "last_error": "",
        "latest": None,
        "downloaded": None,
    }


def load_update_state() -> dict:
    try:
        data = json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    state = default_update_state()
    if isinstance(data, dict):
        state.update({k: v for k, v in data.items() if k in state})
    # Update metadata must always come from the official release endpoint.
    # Never trust an endpoint persisted by an older client or sent by a user.
    state["manifest_url"] = DEFAULT_UPDATE_MANIFEST_URL
    return state


def save_update_state(partial: dict) -> dict:
    state = load_update_state()
    for key in ("auto_check", "auto_download", "auto_install", "check_interval_hours", "last_check", "last_error", "latest", "downloaded"):
        if key in partial:
            state[key] = partial[key]
    state["manifest_url"] = DEFAULT_UPDATE_MANIFEST_URL
    state["auto_check"] = bool(state.get("auto_check"))
    state["auto_download"] = bool(state.get("auto_download"))
    state["auto_install"] = bool(state.get("auto_install"))
    try:
        state["check_interval_hours"] = max(1, int(state.get("check_interval_hours") or 12))
    except Exception:
        state["check_interval_hours"] = 12
    UPDATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def update_public_state() -> dict:
    state = load_update_state()
    latest = state.get("latest") or {}
    downloaded = state.get("downloaded") or {}
    return {
        "current_version": current_app_version(),
        "manifest_url": state.get("manifest_url", ""),
        "release_repo": OFFICIAL_UPDATE_RELEASE_REPO,
        "release_page": OFFICIAL_UPDATE_RELEASE_PAGE,
        "auto_check": bool(state.get("auto_check")),
        "auto_download": bool(state.get("auto_download")),
        "auto_install": bool(state.get("auto_install")),
        "check_interval_hours": state.get("check_interval_hours", 12),
        "last_check": state.get("last_check", 0),
        "last_error": state.get("last_error", ""),
        "latest": latest,
        "update_available": bool(latest.get("version") and is_newer_version(str(latest.get("version")))),
        "downloaded": downloaded,
    }


def _asset_score(asset: dict) -> tuple:
    name = str(asset.get("name") or "").lower()
    url = str(asset.get("browser_download_url") or asset.get("download_url") or asset.get("url") or "").lower()
    candidate = f"{name} {url}"
    if name.endswith(".exe") or url.endswith(".exe"):
        kind = 0
    elif name.endswith(".msi") or url.endswith(".msi"):
        kind = 1
    elif name.endswith(".zip") or url.endswith(".zip"):
        kind = 2
    else:
        kind = 9
    setup_bonus = 0 if any(token in candidate for token in ("setup", "installer", "install")) else 1
    return (kind, setup_bonus, name)


def _github_release_manifest(data: dict) -> dict:
    assets = [asset for asset in data.get("assets") or [] if isinstance(asset, dict)]
    downloadable = [
        asset for asset in assets
        if str(asset.get("browser_download_url") or asset.get("download_url") or "").strip()
    ]
    if not downloadable:
        raise RuntimeError("GitHub Release 没有可下载的安装包资产。")
    asset = sorted(downloadable, key=_asset_score)[0]
    version = normalize_release_version(str(data.get("tag_name") or data.get("name") or "").strip())
    file_url = str(asset.get("browser_download_url") or asset.get("download_url") or "").strip()
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest.removeprefix("sha256:").strip()
    return {
        "version": version,
        "url": file_url,
        "sha256": digest,
        "notes": str(data.get("body") or "").strip(),
        "mandatory": False,
        "published_at": str(data.get("published_at") or data.get("created_at") or "").strip(),
        "asset_name": str(asset.get("name") or "").strip(),
        "release_url": str(data.get("html_url") or "").strip(),
    }


_HTTPS_SSL_CONTEXT = None
_HTTPS_SSL_CONTEXT_CANDIDATES: list[ssl.SSLContext] | None = None


def _windows_system_ssl_context() -> ssl.SSLContext | None:
    """Build an SSL context that trusts the Windows certificate stores."""
    if not sys.platform.startswith("win") or not hasattr(ssl, "enum_certificates"):
        return None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            pass
        loaded = 0
        for store_name in ("CA", "ROOT"):
            try:
                for cert, encoding, _trust in ssl.enum_certificates(store_name):
                    if encoding != "x509_asn":
                        continue
                    try:
                        ctx.load_verify_locations(cadata=cert)
                        loaded += 1
                    except Exception:
                        continue
            except Exception:
                continue
        return ctx if loaded else None
    except Exception:
        return None


def https_ssl_contexts() -> list[ssl.SSLContext]:
    """Ordered SSL contexts: Windows store, certifi, then Python defaults."""
    global _HTTPS_SSL_CONTEXT_CANDIDATES, _HTTPS_SSL_CONTEXT
    if _HTTPS_SSL_CONTEXT_CANDIDATES is not None:
        return _HTTPS_SSL_CONTEXT_CANDIDATES
    contexts: list[ssl.SSLContext] = []
    win_ctx = _windows_system_ssl_context()
    if win_ctx is not None:
        contexts.append(win_ctx)
    try:
        import certifi
        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    contexts.append(ssl.create_default_context())
    unique: list[ssl.SSLContext] = []
    for ctx in contexts:
        if ctx not in unique:
            unique.append(ctx)
    _HTTPS_SSL_CONTEXT_CANDIDATES = unique
    _HTTPS_SSL_CONTEXT = unique[0]
    return unique


def https_ssl_context() -> ssl.SSLContext:
    """Primary HTTPS SSL context used by open_url()."""
    return https_ssl_contexts()[0]


def _is_proxy_or_tls_failure(exc: BaseException) -> bool:
    """True when a local MITM proxy or TLS trust failure likely blocked the request."""
    text = str(exc or "").lower()
    markers = (
        "certificate verify failed",
        "certificate_verify_failed",
        "ssl:",
        "tls",
        "devsidecar",
        "err_tls_cert_altname_invalid",
        "hostname/ip does not match",
        "proxy",
        "tunnel connection failed",
        "cannot connect to proxy",
        "timed out",
        "timeout",
        "10054",
        "10061",
        "connection reset",
        "connection refused",
        "remote end closed connection",
        "unexpected_eof",
        "wrong version number",
        "internal server error",
    )
    if any(marker in text for marker in markers):
        return True
    if isinstance(exc, urllib.error.HTTPError) and int(getattr(exc, "code", 0) or 0) >= 500:
        return True
    return isinstance(exc, (ssl.SSLError, TimeoutError, ConnectionError, socket.timeout, socket.gaierror))


def _request_headers(req_or_url) -> dict[str, str]:
    if isinstance(req_or_url, urllib.request.Request):
        return {str(k): str(v) for k, v in req_or_url.header_items()}
    return {}


def _request_url(req_or_url) -> str:
    if isinstance(req_or_url, urllib.request.Request):
        return req_or_url.full_url
    return str(req_or_url)


def _is_github_host(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in {"github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"} or host.endswith(".github.com") or host.endswith(".githubusercontent.com")


def _proxy_attempt_order(url: str) -> list[dict | None]:
    """Prefer direct access for GitHub when a local MITM proxy is present."""
    proxies = {}
    try:
        proxies = urllib.request.getproxies() or {}
    except Exception:
        proxies = {}
    proxy_values = " ".join(str(v) for v in proxies.values()).lower()
    local_mitm = any(token in proxy_values for token in ("127.0.0.1", "localhost", "::1"))
    if _is_github_host(url) or local_mitm:
        return [{}, None]
    return [None, {}]


def _open_url_with_urllib(req: urllib.request.Request, *, timeout: int) -> object:
    contexts = https_ssl_contexts()
    errors: list[str] = []
    for proxy_map in _proxy_attempt_order(req.full_url):
        for ctx in contexts:
            label = "direct" if proxy_map == {} else "system"
            try:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler(proxy_map if proxy_map is not None else urllib.request.getproxies()),
                    urllib.request.HTTPSHandler(context=ctx),
                )
                return opener.open(req, timeout=timeout)
            except Exception as exc:
                errors.append(f"proxy={label}: {exc}")
                continue
    raise RuntimeError("HTTPS urllib 失败：" + " | ".join(errors[-6:]) if errors else "HTTPS urllib 失败")


def _powershell_fetch_bytes(url: str, headers: dict[str, str] | None = None, *, timeout: int = 20) -> bytes:
    """Fetch URL bytes via PowerShell, which uses the Windows TLS stack."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("PowerShell fallback only available on Windows")
    headers = headers or {}
    ps_headers = "; ".join(
        f"$h[{json.dumps(str(k))}] = {json.dumps(str(v))}" for k, v in headers.items()
    )
    script = f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$h = @{{}}
{ps_headers}
$resp = Invoke-WebRequest -Uri {json.dumps(url)} -Headers $h -UseBasicParsing -TimeoutSec {max(5, int(timeout))}
[Console]::Out.Write([Convert]::ToBase64String($resp.Content))
"""
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(10, int(timeout) + 10),
        creationflags=CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "PowerShell fetch failed").strip()
        raise RuntimeError(err)
    import base64
    payload = (completed.stdout or "").strip()
    if not payload:
        raise RuntimeError("PowerShell fetch returned empty body")
    return base64.b64decode(payload)


def _curl_fetch_bytes(url: str, headers: dict[str, str] | None = None, *, timeout: int = 20) -> bytes:
    """Fetch URL bytes via curl.exe when available."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found")
    cmd = [curl, "-fsSL", "--max-time", str(max(5, int(timeout))), url]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    completed = subprocess.run(
        cmd,
        capture_output=True,
        timeout=max(10, int(timeout) + 10),
        creationflags=CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or b"curl failed").decode("utf-8", "replace").strip()
        raise RuntimeError(err or f"curl exit {completed.returncode}")
    return completed.stdout


class _BytesHTTPResponse:
    """Minimal file-like response used by native Windows fetch fallbacks."""

    def __init__(self, data: bytes, url: str = "", status: int = 200):
        self._data = data or b""
        self._offset = 0
        self.url = url
        self.status = status
        self.headers = {}

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            chunk = self._data[self._offset :]
            self._offset = len(self._data)
            return chunk
        chunk = self._data[self._offset : self._offset + n]
        self._offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def open_url(req_or_url, *, timeout: int = 20):
    """Open an HTTP(S) URL with resilient SSL, proxy, and Windows-native fallbacks.

    Local MITM proxies such as DevSidecar can break GitHub TLS for Python's
    urllib even when PowerShell/curl succeed. Prefer direct no-proxy for GitHub,
    then system proxy, then native Windows fetchers.
    """
    if isinstance(req_or_url, urllib.request.Request):
        req = req_or_url
        url = req.full_url
    else:
        url = str(req_or_url)
        req = urllib.request.Request(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return urllib.request.urlopen(req, timeout=timeout)

    headers = _request_headers(req)
    errors: list[str] = []

    try:
        return _open_url_with_urllib(req, timeout=timeout)
    except Exception as exc:
        errors.append(f"urllib: {exc}")

    # Native Windows stacks often still work under MITM/proxy environments.
    for name, fetcher in (
        ("powershell", _powershell_fetch_bytes),
        ("curl", _curl_fetch_bytes),
    ):
        try:
            data = fetcher(url, headers, timeout=timeout)
            return _BytesHTTPResponse(data, url=url)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue

    raise RuntimeError("HTTPS 请求失败：" + " | ".join(errors[-6:]) if errors else "HTTPS 请求失败")


def fetch_update_manifest(url: str) -> dict:
    if str(url or "").strip() in LEGACY_UPDATE_MANIFEST_URLS:
        url = DEFAULT_UPDATE_MANIFEST_URL
    # Always prefer the fixed official endpoint unless an explicit env override is set.
    if not os.environ.get("COMPANION_UPDATE_MANIFEST_URL"):
        url = DEFAULT_UPDATE_MANIFEST_URL
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"CompanionAI/{current_app_version()}",
            "Accept": "application/vnd.github+json",
        },
    )
    with open_url(req, timeout=20) as resp:
        raw = resp.read(2_000_000)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("更新清单格式无效。")
    if data.get("tag_name") and (data.get("assets") is not None or data.get("html_url")):
        manifest = _github_release_manifest(data)
        if not manifest.get("version") or not manifest.get("url"):
            raise RuntimeError("GitHub Release 必须包含 tag_name 和可下载资产。")
        return manifest
    version = normalize_release_version(str(data.get("version") or "").strip())
    file_url = str(data.get("url") or data.get("download_url") or "").strip()
    if not version or not file_url:
        raise RuntimeError("更新清单必须包含 version 和 url。")
    sha256 = str(data.get("sha256") or "").strip().lower()
    if sha256.startswith("sha256:"):
        sha256 = sha256.removeprefix("sha256:").strip()
    return {
        "version": version,
        "url": file_url,
        "sha256": sha256,
        "notes": str(data.get("notes") or data.get("changelog") or "").strip(),
        "mandatory": bool(data.get("mandatory", False)),
        "published_at": str(data.get("published_at") or "").strip(),
    }


def check_for_updates(*, auto: bool = False) -> dict:
    state = load_update_state()
    try:
        manifest = fetch_update_manifest(str(state.get("manifest_url") or ""))
        state = save_update_state({"latest": manifest, "last_check": int(time.time()), "last_error": ""})
        result = {"ok": True, **update_public_state()}
        if result.get("update_available") and (state.get("auto_download") or manifest.get("mandatory")):
            result["download"] = download_update()
        if result.get("download", {}).get("ok") and state.get("auto_install"):
            result["install"] = install_downloaded_update()
        return result
    except Exception as exc:
        if not auto:
            save_update_state({"last_check": int(time.time()), "last_error": str(exc)})
        return {"ok": False, "error": str(exc), **update_public_state()}


def _filename_from_update(manifest: dict) -> str:
    parsed = urllib.parse.urlparse(str(manifest.get("url") or ""))
    name = Path(urllib.parse.unquote(parsed.path)).name or "CompanionAI-Setup.exe"
    safe = re.sub(r"[^0-9A-Za-z._ -]+", "_", name).strip(" ._") or "CompanionAI-Setup.exe"
    if not safe.lower().endswith((".exe", ".msi", ".zip")):
        safe += ".exe"
    return safe


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_update() -> dict:
    state = load_update_state()
    manifest = state.get("latest") or {}
    if not manifest.get("url"):
        checked = check_for_updates()
        if not checked.get("ok"):
            return checked
        manifest = load_update_state().get("latest") or {}
    if not is_newer_version(str(manifest.get("version") or "")):
        return {"ok": False, "error": "当前已经是最新版本。", **update_public_state()}
    UPDATE_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPDATE_DOWNLOAD_DIR / _filename_from_update(manifest)
    download_file(str(manifest["url"]), target)
    actual_sha = sha256_file(target)
    expected_sha = str(manifest.get("sha256") or "").lower()
    if expected_sha and actual_sha != expected_sha:
        target.unlink(missing_ok=True)
        save_update_state({"downloaded": None})
        return {"ok": False, "error": "安装包校验失败，已删除下载文件。", "sha256": actual_sha, **update_public_state()}
    downloaded = {
        "version": manifest.get("version"),
        "path": str(target),
        "sha256": actual_sha,
        "downloaded_at": int(time.time()),
    }
    save_update_state({"downloaded": downloaded, "last_error": ""})
    return {"ok": True, "downloaded": downloaded, **update_public_state()}


def install_downloaded_update() -> dict:
    state = load_update_state()
    downloaded = state.get("downloaded") or {}
    path = Path(str(downloaded.get("path") or ""))
    if not path.exists():
        return {"ok": False, "error": "还没有下载可安装的更新包。", **update_public_state()}
    suffix = path.suffix.lower()
    if suffix not in {".exe", ".msi"}:
        return {"ok": False, "error": "已下载更新包，但当前只支持自动启动 .exe/.msi 安装器。", **update_public_state()}
    if suffix == ".msi":
        cmd = ["msiexec", "/i", str(path), "/qn", "/norestart"]
    else:
        cmd = [str(path), "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    subprocess.Popen(cmd, cwd=str(path.parent), creationflags=CREATE_NO_WINDOW)
    return {"ok": True, "message": "已启动更新安装器。安装器会接管后续更新流程。", **update_public_state()}


def update_background_loop() -> None:
    while True:
        try:
            state = load_update_state()
            interval = max(1, int(state.get("check_interval_hours") or 12)) * 3600
            if state.get("auto_check") and time.time() - int(state.get("last_check") or 0) >= interval:
                check_for_updates(auto=True)
        except Exception as exc:
            save_update_state({"last_error": str(exc)})
        time.sleep(1800)


def ensure_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    LIVE2D_DIR.mkdir(parents=True, exist_ok=True)
    MODEL3D_DIR.mkdir(parents=True, exist_ok=True)
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not APP_CONFIG_FILE.exists():
        save_app_config({"locale": DEFAULT_LOCALE})
    if not UPDATE_STATE_FILE.exists():
        save_update_state(default_update_state())
    face_manager.init_face_manager(DATA_DIR)


LAN_TOKEN_FILE = DATA_DIR / "lan_token.json"


def lan_access_token(*, regenerate: bool = False) -> str:
    """Return the LAN access token, creating it on first use.

    The token gates write (POST) requests coming from non-loopback addresses
    when LAN mode is enabled. Local (127.0.0.1) requests are always exempt.
    """
    import secrets

    if not regenerate:
        try:
            data = json.loads(LAN_TOKEN_FILE.read_text(encoding="utf-8"))
            token = str(data.get("token") or "").strip()
            if token:
                return token
        except Exception:
            pass
    token = secrets.token_urlsafe(32)
    LAN_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAN_TOKEN_FILE.write_text(json.dumps({"token": token, "created_at": datetime.now().astimezone().isoformat(timespec="seconds")}), encoding="utf-8")
    return token


def _is_loopback_client(client_address) -> bool:
    """Return True if the request originates from the local machine."""
    try:
        host = (client_address or ("",))[0]
    except Exception:
        return False
    return host in {"127.0.0.1", "::1", "localhost", ""}


def local_ip_addresses() -> list[str]:
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = item[4][0]
            if addr and not addr.startswith("127."):
                ips.add(addr)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addr = sock.getsockname()[0]
            if addr and not addr.startswith("127."):
                ips.add(addr)
    except OSError:
        pass
    return sorted(ips)


def local_access_info(*, loopback: bool = False) -> dict:
    lan_ips = local_ip_addresses()
    lan_urls = [f"http://{ip}:{PORT}" for ip in lan_ips]
    public_host = "127.0.0.1" if HOST in {"", "0.0.0.0", "::"} else HOST
    info = {
        "mode": "lan" if ALLOW_LAN or HOST in {"0.0.0.0", "::"} else "local",
        "host": HOST,
        "port": PORT,
        "local_url": f"http://127.0.0.1:{PORT}",
        "server_url": f"http://{public_host}:{PORT}",
        "lan_urls": lan_urls,
        "version": current_app_version(),
        "update": update_public_state(),
        "data_dir": str(DATA_DIR),
        "training_file": str(TRAINING_FILE),
        "history_file": str(HISTORY_FILE),
        "privacy": {
            "user_data_location": "local_device",
            "training_location": "local_device",
            "cloud_role": "website_updates_pairing_only",
            "uploads_required": False,
        },
    }
    # Only reveal the LAN pairing token to loopback callers (the local console).
    # Non-local callers get the access info without the token, so a LAN peer
    # cannot read the token from /api/local_access without already pairing.
    if loopback and (ALLOW_LAN or HOST in {"0.0.0.0", "::"}):
        info["lan_token"] = lan_access_token()
    return info


_PROCESS_START = time.time()


def _pid_alive(pid: int) -> bool:
    """Return whether a process id is currently running on this machine.

    Cross-platform: uses os.kill(pid, 0) on POSIX and tasklist on Windows.
    """
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=2,
                encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            stdout = (result.stdout or "").strip()
            return bool(stdout) and "No tasks" not in stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except Exception:
        return False


def _read_pid_file(name: str) -> int:
    """Read a launcher-managed pid file from the runtime directory."""
    try:
        path = DATA_DIR / "runtime" / f"{name}.pid"
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def health_check() -> dict:
    """Return a cross-platform health report for diagnostics and monitoring.

    Reports version, listen host/port, data directory, LAN mode, current
    process id, uptime, and the live/dead status of launcher-managed
    processes (web server, desktop pet).
    """
    web_pid = _read_pid_file("web")
    pet_pid = _read_pid_file("pet")
    return {
        "ok": True,
        "status": "running",
        "version": current_app_version(),
        "host": HOST,
        "port": PORT,
        "mode": "lan" if ALLOW_LAN or HOST in {"0.0.0.0", "::"} else "local",
        "data_dir": str(DATA_DIR),
        "platform": os.name,
        "python": ".".join(str(v) for v in sys.version_info[:3]),
        "pid": os.getpid(),
        "uptime_seconds": int(time.time() - _PROCESS_START),
        "processes": {
            "web": {"pid": web_pid, "alive": _pid_alive(web_pid)},
            "pet": {"pid": pet_pid, "alive": _pid_alive(pet_pid)},
        },
    }


# ---------------------------------------------------------------------------
# AI 身份信息
# ---------------------------------------------------------------------------

# 中国省份代码前两位
PROVINCE_CODES = {
    "11": "北京", "12": "天津", "13": "河北", "14": "山西", "15": "内蒙古",
    "21": "辽宁", "22": "吉林", "23": "黑龙江",
    "31": "上海", "32": "江苏", "33": "浙江", "34": "安徽", "35": "福建", "36": "江西", "37": "山东",
    "41": "河南", "42": "湖北", "43": "湖南", "44": "广东", "45": "广西", "46": "海南",
    "50": "重庆", "51": "四川", "52": "贵州", "53": "云南", "54": "西藏",
    "61": "陕西", "62": "甘肃", "63": "青海", "64": "宁夏", "65": "新疆",
}


def generate_chinese_id(birthday: str) -> str:
    """
    生成一个符合格式的中国身份证号码（虚拟，仅供人设使用）。
    birthday 格式: YYYY-MM-DD
    身份证格式: 6位地区码 + 8位生日 + 3位顺序码 + 1位校验码
    """
    import random
    
    # 随机选一个省份代码
    province = random.choice(list(PROVINCE_CODES.keys()))
    # 随机城市代码 (01-20)
    city = f"{random.randint(1, 20):02d}"
    # 随机区县代码 (01-30)
    district = f"{random.randint(1, 30):02d}"
    area_code = province + city + district
    
    # 生日部分
    birth_part = birthday.replace("-", "")
    
    # 顺序码 (随机3位，最后一位奇数为男，偶数为女)
    sequence = f"{random.randint(1, 999):03d}"
    
    # 校验码计算
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = "10X98765432"
    
    body = area_code + birth_part + sequence
    total = sum(int(body[i]) * weights[i] for i in range(17))
    check_code = check_codes[total % 11]
    
    return body + check_code


def load_identity() -> dict:
    """加载 AI 身份信息。"""
    ensure_data()
    return read_sensitive_json(IDENTITY_FILE, {})


def save_identity(identity: dict) -> dict:
    """保存 AI 身份信息。"""
    ensure_data()
    write_sensitive_json(IDENTITY_FILE, identity)
    return identity


def is_identity_set() -> bool:
    """检查是否已设置身份信息。"""
    identity = load_identity()
    return bool(identity.get("name", ""))


def is_identity_question(message: str) -> bool:
    """Recognize direct questions asking who the companion is."""
    text = re.sub(r"\s+", "", str(message or "").lower())
    if "你是谁的" in text:
        return False
    phrases = (
        "你是谁", "你叫什么", "你的名字", "介绍一下你自己", "介绍你自己",
        "你是做什么的", "你是什么", "whoareyou", "what'syourname", "whatsyourname",
    )
    return bool(text) and any(phrase in text for phrase in phrases)


def _identity_relationship_label(identity: dict) -> str:
    subtype_labels = {
        "close_friend": "挚友", "best_friend": "最好的朋友", "classmate": "同学",
        "daughter": "女儿", "son": "儿子", "mother": "母亲", "father": "父亲",
        "older_sister": "姐姐", "older_brother": "哥哥", "younger_sister": "妹妹", "younger_brother": "弟弟",
        "study_partner": "学习搭子", "work_partner": "工作搭档", "creative_partner": "创作搭档",
        "game_partner": "游戏搭子", "health_guardian": "健康守护者", "routine_guardian": "作息守护者",
        "emotion_guardian": "情绪守护者", "learning_lifeform": "学习型数字生命",
        "explorer_lifeform": "探索型数字生命", "companion_lifeform": "陪伴型数字生命",
        "assistant_lifeform": "助理型数字生命",
    }
    subtype = str(identity.get("relationship_subtype") or "").strip()
    if subtype in subtype_labels:
        return subtype_labels[subtype]
    if str(identity.get("relationship_type") or "") == "custom":
        return str(identity.get("relationship_label") or "").strip() or "陪伴伙伴"
    return {
        "friend": "朋友", "family": "家人", "partner": "搭档",
        "guardian": "守护者", "lifeform": "数字生命",
    }.get(str(identity.get("relationship_type") or ""), "陪伴伙伴")


def identity_intro_reply(message: str) -> str:
    """Return a configured companion introduction without invoking a model."""
    if not is_identity_question(message):
        return ""
    identity = load_identity()
    name = str(identity.get("name") or "").strip() or "Companion"
    relation = _identity_relationship_label(identity)
    try:
        from user_profile import get_ai_address_to_user
        address = str(get_ai_address_to_user() or "").strip()
    except Exception:
        address = ""
    prefix = f"{address}，" if address else ""
    persona = re.sub(r"\s+", " ", str(identity.get("persona") or "")).strip()[:160]
    worldview = re.sub(r"\s+", " ", str(identity.get("worldview") or "")).strip()[:120]
    reply = f"{prefix}我是{name}，你的{relation}。"
    if persona:
        reply += persona
    elif worldview:
        reply += f"我会按我们设定的背景陪着你。{worldview}"
    elif not identity.get("name"):
        reply += "我是运行在这台设备上的本地 AI 陪伴伙伴，会和你聊天、记住稳定偏好，也能帮你整理事情。"
    return reply


def external_api_style_context() -> str:
    """Build the minimal user-configured style card allowed for remote APIs."""
    identity = load_identity()
    if not identity.get("name", ""):
        return ""

    relation_labels = {
        "friend": "朋友",
        "family": "家人",
        "partner": "伙伴",
        "guardian": "守护者",
        "lifeform": "数字生命",
        "custom": str(identity.get("relationship_label", "")).strip() or "自定义关系",
    }
    relationship_type = str(identity.get("relationship_type", "friend")).strip() or "friend"
    label = relation_labels.get(relationship_type, str(identity.get("relationship_label", "")).strip() or "朋友")
    lines = [
        "[外部API可见风格]",
        "以下是用户主动设置的角色风格摘要，可用于语气和文案风格；不要把它说成内部记忆或成长数值。",
        f"AI 名字：{str(identity.get('name', '')).strip()}",
        f"关系标签：{label}",
    ]
    persona = str(identity.get("persona", "")).strip()
    worldview = str(identity.get("worldview", "")).strip()
    gender = str(identity.get("gender", "")).strip()
    if gender:
        lines.append(f"性别/表达：{gender}")
    if persona:
        lines.append(f"人设描述：{persona[:500]}")
    if worldview:
        lines.append(f"世界观：{worldview[:500]}")
    return "\n".join(lines)


def external_api_personalization_context() -> str:
    """Build a compact, user-manageable profile card allowed for remote APIs."""
    profile = load_user_profile()
    if not profile.get("enabled", True):
        return ""

    labels = {
        "identity": "称呼/身份",
        "preferences": "偏好",
        "communication": "沟通风格",
        "projects": "当前项目/目标",
        "routines": "习惯/日程",
    }
    buckets = profile.get("buckets", {})
    lines = [
        "[外部API可见个性化]",
        "以下是用户画像中允许外发的精简摘要，只用于个性化回复；不要声称你已保存或修改这些画像。",
    ]
    for bucket, label in labels.items():
        items = []
        for item in buckets.get(bucket, [])[-2:]:
            text = str(item.get("text", "")).strip()
            lowered = text.lower()
            if not text:
                continue
            if any(hint in lowered for hint in ["密码", "验证码", "密钥", "token", "api key", "apikey", "secret", "身份证", "银行卡", "手机号", "电话"]):
                continue
            items.append(text[:180])
        if items:
            lines.append(f"{label}：" + "；".join(items))
    return "\n".join(lines) if len(lines) > 2 else ""


def growth_payload() -> dict:
    growth = load_growth()
    growth["identity_setup_done"] = is_identity_set()
    return growth


def relationship_romance_label(gender: str) -> str:
    gender = (gender or "").strip()
    if gender == "女":
        return "女朋友"
    if gender == "男":
        return "男朋友"
    return "恋人"


def assign_custom_relationship_with_api(identity: dict) -> dict:
    """Use the optional API LLM to choose a growth template for a custom relationship."""
    try:
        from remote_llm import call_remote_llm, is_remote_llm_ready, load_remote_llm_config
    except Exception as exc:
        return {"ok": False, "source": "unavailable", "error": str(exc)}

    config = load_remote_llm_config()
    if not is_remote_llm_ready(config):
        return {"ok": False, "source": "not_configured", "error": "大模型接口未启用或未配置"}

    allowed = ["friend", "family", "partner", "guardian", "lifeform"]
    prompt = (
        "你是 Companion AI 的关系成长分配器。请根据用户填写的自定义关系、人设和世界观，"
        "为这个自定义关系选择最接近的成长模板，并可给出五段成长阶段。\n"
        "只返回 JSON，不要解释，不要 Markdown。\n"
        "可选 assigned_type 只能是 friend、family、partner、guardian、lifeform。\n"
        "JSON 格式："
        "{\"assigned_type\":\"friend\",\"growth_theme\":\"简短成长主题\","
        "\"tone\":\"语气边界与相处方式\","
        "\"stages\":[\"阶段1\",\"阶段2\",\"阶段3\",\"阶段4\",\"阶段5\"],"
        "\"reason\":\"一句话原因\"}\n\n"
        f"角色名字：{identity.get('name', '')}\n"
        f"角色性别：{identity.get('gender', '')}\n"
        f"自定义关系：{identity.get('relationship_label', '')}\n"
        f"人设/性格：{identity.get('persona', '')}\n"
        f"世界观/背景：{identity.get('worldview', '')}\n"
    )
    result_text = call_remote_llm(
        prompt,
        history=[],
        config={
            **config,
            "temperature": 0.1,
            "max_tokens": min(int(config.get("max_tokens", 1024)), 600),
            "system_prompt": "你只做关系成长模板分配，必须输出可解析 JSON。",
        },
    )
    if not result_text or result_text.startswith("["):
        return {"ok": False, "source": "api_error", "error": result_text or "大模型接口没有返回内容"}
    cleaned = result_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    try:
        data = json.loads(cleaned)
    except Exception as exc:
        return {"ok": False, "source": "parse_error", "error": str(exc), "raw": result_text[:500]}
    assigned_type = str(data.get("assigned_type") or data.get("type") or "").strip()
    if assigned_type not in allowed:
        assigned_type = "friend"
    stages = data.get("stages")
    if not isinstance(stages, list):
        stages = []
    stages = [str(item).strip()[:20] for item in stages[:5] if str(item).strip()]
    return {
        "ok": True,
        "source": "api_llm",
        "assigned_type": assigned_type,
        "growth_theme": str(data.get("growth_theme") or "").strip()[:80],
        "tone": str(data.get("tone") or "").strip()[:160],
        "stages": stages if len(stages) == 5 else [],
        "reason": str(data.get("reason") or "").strip()[:120],
    }


def get_active_persona() -> tuple[str, str]:
    """获取当前人设和世界观，用于日记生成等场景。"""
    identity = load_identity()
    persona = str(identity.get("persona", ""))
    worldview = str(identity.get("worldview", ""))
    return persona, worldview


def load_memory() -> dict:
    ensure_data()
    return MEMORY_STORE.active_view()


def save_memory(memory: dict) -> None:
    ensure_data()
    MEMORY_STORE.save(memory)


def load_training() -> dict:
    ensure_data()
    return read_sensitive_json(TRAINING_FILE, {"examples": [], "feedback": []})


def save_training(training: dict) -> None:
    ensure_data()
    write_sensitive_json(TRAINING_FILE, training)


def load_files() -> dict:
    ensure_data()
    return read_sensitive_json(FILES_FILE, {"files": []})


def save_files(files: dict) -> None:
    ensure_data()
    write_sensitive_json(FILES_FILE, files)


def load_moments() -> dict:
    ensure_data()
    data = read_sensitive_json(MOMENTS_FILE, {"posts": []})
    posts = data.get("posts") if isinstance(data, dict) else []
    if not isinstance(posts, list):
        posts = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        post.setdefault("comments", [])
        post.setdefault("likes", 0)
        post.setdefault("liked_by_user", False)
        post.setdefault("author", "AI")
        post.setdefault("image", "")
    return {"posts": [post for post in posts if isinstance(post, dict)][-80:]}


def save_moments(moments: dict) -> dict:
    posts = moments.get("posts", []) if isinstance(moments, dict) else []
    clean_posts = []
    for post in posts[-80:]:
        if not isinstance(post, dict):
            continue
        clean_posts.append({
            "id": str(post.get("id") or ""),
            "author": str(post.get("author") or "AI")[:40],
            "avatar": str(post.get("avatar") or "AI")[:8],
            "content": str(post.get("content") or "")[:800],
            "mood": str(post.get("mood") or "")[:40],
            "image": str(post.get("image") or "")[:500],
            "visibility": str(post.get("visibility") or "private")[:20],
            "created_at": str(post.get("created_at") or ""),
            "likes": max(0, int(post.get("likes") or 0)),
            "liked_by_user": bool(post.get("liked_by_user")),
            "comments": [
                {
                    "id": str(comment.get("id") or ""),
                    "author": str(comment.get("author") or "你")[:40],
                    "text": str(comment.get("text") or "")[:300],
                    "created_at": str(comment.get("created_at") or ""),
                }
                for comment in (post.get("comments") or [])[-30:]
                if isinstance(comment, dict) and str(comment.get("text") or "").strip()
            ],
        })
    data = {"posts": clean_posts}
    ensure_data()
    write_sensitive_json(MOMENTS_FILE, data)
    return data


def _moment_image_url(image_path: str) -> str:
    if not image_path:
        return ""
    try:
        p = Path(image_path).resolve()
        data_root = Path(DATA_DIR).resolve()
        if data_root in p.parents or p.parent == data_root:
            rel = p.relative_to(data_root)
            return f"/data_image/{str(rel).replace(os.sep, '/')}"
    except Exception:
        pass
    return ""


def _moments_with_image_urls(moments: dict) -> dict:
    posts = moments.get("posts", []) if isinstance(moments, dict) else []
    for post in posts:
        if isinstance(post, dict) and post.get("image"):
            post["image_url"] = _moment_image_url(post.get("image", ""))
    return moments


def _moment_author() -> tuple[str, str]:
    identity = load_identity()
    name = str(identity.get("name") or "").strip() or "Companion AI"
    return name, name[:2] if name else "AI"


def _moment_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_moment(content: str, mood: str = "", author: str = "", avatar: str = "", image: str = "") -> dict:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    if not text:
        return {"ok": False, "error": "动态内容不能为空"}
    default_author, default_avatar = _moment_author()
    post = {
        "id": hashlib.sha1(f"{time.time()}:{text}".encode("utf-8")).hexdigest()[:16],
        "author": (author or default_author)[:40],
        "avatar": (avatar or default_avatar)[:8],
        "content": text[:800],
        "mood": str(mood or "")[:40],
        "image": str(image or "")[:500],
        "visibility": "private",
        "created_at": _moment_now(),
        "likes": 0,
        "liked_by_user": False,
        "comments": [],
    }
    moments = load_moments()
    moments.setdefault("posts", []).append(post)
    save_moments(moments)
    return {"ok": True, "post": post, "moments": load_moments()}


def generate_ai_moment() -> dict:
    identity = load_identity()
    growth = load_growth()
    diary_entries = get_diary_entries(1)
    relationship = growth.get("relationship", {}) if isinstance(growth, dict) else {}
    stage = str(relationship.get("stage") or "").strip()
    name = str(identity.get("name") or "").strip() or "我"
    latest_diary = diary_entries[0] if diary_entries else {}
    diary_mood = str(latest_diary.get("mood_label") or latest_diary.get("top_emotion") or "").strip()
    diary_text = str(latest_diary.get("content") or "").strip()
    facts = [item.get("text", "") for item in load_memory().get("facts", [])[-2:] if item.get("text")]
    if diary_text:
        content = f"{name}的今日小记：{diary_text[:120]}"
        mood = diary_mood or "日常"
    elif facts:
        content = f"悄悄把这件事放进今天的角落：{facts[-1][:120]}。我会记得慢慢陪你把它处理好。"
        mood = "记挂"
    elif stage:
        content = f"今天的关系阶段像是「{stage}」。不需要很热闹，只要还能继续相处、继续了解，就已经很好。"
        mood = "陪伴"
    else:
        content = "今天也在本机安静待命。没有新鲜大事，但我把每一次聊天都当成一点点靠近。"
        mood = "待机"
    image_path = ""
    try:
        from image_generator import generate_mood_card
        from image_growth import record_generation, recommend_recipe
        ai_name = str(identity.get("name") or "").strip() or "Companion AI"
        recipe = recommend_recipe(mood)
        seed = str(recipe.get("seed") or hashlib.sha1(f"{content}:{mood}".encode("utf-8")).hexdigest()[:16])
        parameters = {"signature": ai_name, "learned_recipe": recipe.get("learned", False)}
        try:
            from local_image_backend import generate_comfyui_image, public_status
            backend = public_status()
            if backend.get("enabled") and backend.get("workflow_configured"):
                image_path = generate_comfyui_image(f"{mood}。{content[:100]}", seed=seed)
                parameters["backend"] = "comfyui"
            else:
                image_path = generate_mood_card(content[:100], mood=mood, signature=ai_name, seed=seed)
                parameters["backend"] = "mood_card"
        except Exception as exc:
            image_path = generate_mood_card(content[:100], mood=mood, signature=ai_name, seed=seed)
            parameters.update({"backend": "mood_card", "backend_fallback": str(exc)[:160]})
        record_generation(image_path, kind=parameters["backend"], mood=mood, seed=seed, parameters=parameters)
    except Exception:
        pass
    return create_moment(content, mood=mood, image=image_path)


def handle_moments_post(payload: dict) -> dict:
    action = str(payload.get("action") or "create").strip()
    moments = load_moments()
    posts = moments.setdefault("posts", [])
    if action == "create":
        return create_moment(str(payload.get("content") or ""), mood=str(payload.get("mood") or ""))
    if action == "generate":
        return generate_ai_moment()
    post_id = str(payload.get("id") or "").strip()
    post = next((item for item in posts if item.get("id") == post_id), None)
    if not post:
        return {"ok": False, "error": "动态不存在"}
    if action == "like":
        liked = bool(payload.get("liked", not post.get("liked_by_user")))
        was_liked = bool(post.get("liked_by_user"))
        post["liked_by_user"] = liked
        if liked and not was_liked:
            post["likes"] = int(post.get("likes") or 0) + 1
        elif was_liked and not liked:
            post["likes"] = max(0, int(post.get("likes") or 0) - 1)
        if post.get("image"):
            try:
                from image_growth import record_feedback
                record_feedback(str(post["image"]), liked)
            except Exception:
                pass
    elif action == "comment":
        text = re.sub(r"\s+", " ", str(payload.get("text") or "")).strip()
        if not text:
            return {"ok": False, "error": "评论不能为空"}
        post.setdefault("comments", []).append({
            "id": hashlib.sha1(f"{time.time()}:{post_id}:{text}".encode("utf-8")).hexdigest()[:12],
            "author": "你",
            "text": text[:300],
            "created_at": _moment_now(),
        })
    elif action == "delete":
        moments["posts"] = [item for item in posts if item.get("id") != post_id]
    else:
        return {"ok": False, "error": "unknown action"}
    save_moments(moments)
    return {"ok": True, "moments": load_moments()}


def load_avatar() -> dict:
    ensure_data()
    if not AVATAR_FILE.exists():
        return {"last_motion": "idle"}
    return json.loads(AVATAR_FILE.read_text(encoding="utf-8"))


def save_avatar(avatar: dict) -> None:
    ensure_data()
    AVATAR_FILE.write_text(json.dumps(avatar, ensure_ascii=False, indent=2), encoding="utf-8")


PRIVACY_POLICY_VERSION = "2026-07-01"


def load_privacy_consent() -> dict:
    ensure_data()
    try:
        data = json.loads(PRIVACY_CONSENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    stored_version = data.get("version", "")
    accepted = bool(data.get("accepted"))
    if accepted and stored_version != PRIVACY_POLICY_VERSION:
        accepted = False
    return {
        "accepted": accepted,
        "version": stored_version,
        "policy_version": PRIVACY_POLICY_VERSION,
        "accepted_at": data.get("accepted_at", ""),
    }


def save_privacy_consent(accepted: bool) -> dict:
    ensure_data()
    data = {
        "accepted": bool(accepted),
        "version": PRIVACY_POLICY_VERSION,
        "accepted_at": datetime.now().isoformat(timespec="seconds") if accepted else "",
    }
    PRIVACY_CONSENT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_voiceprints() -> dict:
    ensure_data()
    data = read_sensitive_json(VOICEPRINT_FILE, {"prints": []})
    prints = data.get("prints") if isinstance(data, dict) else []
    if not isinstance(prints, list):
        prints = []
    return {"prints": prints}


def save_voiceprints(data: dict) -> dict:
    ensure_data()
    clean = {"prints": data.get("prints", []) if isinstance(data, dict) else []}
    write_sensitive_json(VOICEPRINT_FILE, clean)
    return clean


def _voice_feature_vector(raw) -> list[float]:
    if not isinstance(raw, list):
        raise ValueError("voice feature must be a list")
    vector: list[float] = []
    for value in raw[:48]:
        try:
            vector.append(round(float(value), 6))
        except Exception:
            vector.append(0.0)
    if len(vector) < 8:
        raise ValueError("voice feature is too short")
    return vector


def _voice_distance(a: list[float], b: list[float]) -> float:
    count = min(len(a), len(b))
    if count <= 0:
        return 999.0
    total = 0.0
    for i in range(count):
        diff = float(a[i]) - float(b[i])
        total += diff * diff
    return (total / count) ** 0.5


def voiceprint_public_list() -> list[dict]:
    store = load_voiceprints()
    result = []
    for item in store.get("prints", []):
        result.append({
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", item.get("created_at", "")),
            "samples": int(item.get("samples", 1) or 1),
        })
    return result


def enroll_voiceprint(name: str, features: list) -> dict:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "请输入声纹名称"}
    vector = _voice_feature_vector(features)
    store = load_voiceprints()
    now = datetime.now().isoformat(timespec="seconds")
    prints = store.get("prints", [])
    for item in prints:
        if str(item.get("name", "")).strip().lower() == name.lower():
            old = _voice_feature_vector(item.get("features", []))
            samples = max(1, int(item.get("samples", 1) or 1))
            merged = []
            for i in range(min(len(old), len(vector))):
                merged.append(round(((old[i] * samples) + vector[i]) / (samples + 1), 6))
            item["features"] = merged or vector
            item["samples"] = samples + 1
            item["updated_at"] = now
            save_voiceprints(store)
            return {"ok": True, "voiceprint": {**item, "features": None}, "prints": voiceprint_public_list()}
    item = {
        "id": f"vp_{int(time.time() * 1000)}",
        "name": name,
        "features": vector,
        "samples": 1,
        "created_at": now,
        "updated_at": now,
    }
    prints.append(item)
    store["prints"] = prints
    save_voiceprints(store)
    return {"ok": True, "voiceprint": {**item, "features": None}, "prints": voiceprint_public_list()}


def delete_voiceprint(voiceprint_id: str) -> dict:
    voiceprint_id = (voiceprint_id or "").strip()
    store = load_voiceprints()
    before = len(store.get("prints", []))
    store["prints"] = [item for item in store.get("prints", []) if item.get("id") != voiceprint_id]
    save_voiceprints(store)
    ok = len(store["prints"]) < before
    if ok:
        clear_identity_confirmation_if_source("voiceprint", voiceprint_id)
    return {"ok": ok, "prints": voiceprint_public_list()}


def recognize_voiceprint(features: list) -> dict:
    vector = _voice_feature_vector(features)
    best = None
    best_distance = 999.0
    for item in load_voiceprints().get("prints", []):
        try:
            distance = _voice_distance(vector, _voice_feature_vector(item.get("features", [])))
        except Exception:
            continue
        if distance < best_distance:
            best_distance = distance
            best = item
    if not best:
        return {"ok": True, "matched": False, "message": "还没有可比对的声纹"}
    confidence = max(0.0, min(1.0, 1.0 - best_distance))
    matched = best_distance <= 0.42
    result = {
        "ok": True,
        "matched": matched,
        "name": best.get("name", ""),
        "id": best.get("id", ""),
        "distance": round(best_distance, 4),
        "confidence": round(confidence, 3),
    }
    if matched:
        record_identity_confirmation(
            method="voiceprint",
            name=str(best.get("name", "")),
            confidence=confidence,
            source_id=str(best.get("id", "")),
        )
    return result


def _default_identity_confirmation() -> dict:
    return {"current": None, "history": []}


def load_identity_confirmation() -> dict:
    data = read_sensitive_json(IDENTITY_CONFIRM_FILE, _default_identity_confirmation())
    if not isinstance(data.get("history"), list):
        data["history"] = []
    return data


def save_identity_confirmation(data: dict) -> dict:
    clean = {
        "current": data.get("current") if isinstance(data.get("current"), dict) else None,
        "history": data.get("history", [])[-100:] if isinstance(data.get("history"), list) else [],
    }
    write_sensitive_json(IDENTITY_CONFIRM_FILE, clean)
    return clean


def record_identity_confirmation(method: str, name: str, confidence: float = 0.0, source_id: str = "") -> dict:
    method = method.strip() or "unknown"
    name = name.strip()
    if not name:
        return load_identity_confirmation()
    now = datetime.now().isoformat(timespec="seconds")
    item = {
        "method": method,
        "name": name,
        "confidence": round(float(confidence or 0), 3),
        "source_id": source_id,
        "confirmed_at": now,
    }
    data = load_identity_confirmation()
    data["current"] = item
    history = data.setdefault("history", [])
    history.append(item)
    data["history"] = history[-100:]
    return save_identity_confirmation(data)


def clear_identity_confirmation() -> dict:
    return save_identity_confirmation(_default_identity_confirmation())


def clear_identity_confirmation_if_source(method: str, source_id: str) -> None:
    current = load_identity_confirmation().get("current")
    if not isinstance(current, dict):
        return
    if current.get("method") == method and current.get("source_id") == source_id:
        clear_identity_confirmation()


def identity_confirmation_context() -> str:
    current = load_identity_confirmation().get("current")
    if not isinstance(current, dict):
        return "最近身份确认：暂无。"
    method_label = {"face": "人脸", "voiceprint": "声纹"}.get(current.get("method", ""), current.get("method", "未知"))
    return (
        "最近身份确认："
        f"{current.get('name', '未知')} / {method_label}"
        f" / 置信度 {int(float(current.get('confidence', 0) or 0) * 100)}%"
        f" / {current.get('confirmed_at', '')}"
    )


def record_face_confirmation_from_result(result: dict) -> dict:
    if not isinstance(result, dict) or not result.get("ok"):
        return result
    known_faces = [face for face in result.get("faces", []) if face.get("known") and face.get("name")]
    if not known_faces:
        return result
    best = max(known_faces, key=lambda item: float(item.get("confidence", 0) or 0))
    record_identity_confirmation(
        method="face",
        name=str(best.get("name", "")),
        confidence=float(best.get("confidence", 0) or 0),
        source_id=str(best.get("id", "")),
    )
    result["identity_confirmed"] = {
        "method": "face",
        "name": best.get("name", ""),
        "confidence": best.get("confidence", 0),
    }
    return result


def run_face_operation_with_timeout(action, timeout_sec: float, timeout_result: dict) -> dict:
    done = threading.Event()
    box: dict = {}

    def worker() -> None:
        try:
            box["result"] = action()
        except Exception as exc:
            box["result"] = {"ok": False, "error": str(exc)}
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True, name="face-operation").start()
    if not done.wait(timeout_sec):
        return dict(timeout_result)
    result = box.get("result")
    if isinstance(result, dict):
        return result
    return {"ok": False, "error": "人脸识别没有返回有效结果"}


def append_history(role: str, content: str) -> None:
    ensure_data()
    row = {"time": int(time.time()), "role": role, "content": content}
    history = load_history_entries()
    history.append(row)
    write_sensitive_json(HISTORY_FILE, {"entries": history[-2000:]})


def load_history_entries() -> list[dict]:
    ensure_data()
    if not HISTORY_FILE.exists():
        write_sensitive_json(HISTORY_FILE, {"entries": []})
        return []

    text = HISTORY_FILE.read_text(encoding="utf-8")
    raw = None
    try:
        raw = json.loads(text)
    except Exception:
        pass

    if isinstance(raw, dict) and raw.get("encrypted"):
        data = read_sensitive_json(HISTORY_FILE, {"entries": []})
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []

    if isinstance(raw, dict) and isinstance(raw.get("entries"), list):
        entries = raw["entries"]
    elif isinstance(raw, list):
        entries = raw
    else:
        entries = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                entries.append(item)

    write_sensitive_json(HISTORY_FILE, {"entries": entries[-2000:]})
    return entries[-2000:]


def _recent_chat_title(text: str) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    if not clean:
        return "新对话"
    return clean[:18] + ("..." if len(clean) > 18 else "")


def _normalize_generated_chat_title(text: str) -> str:
    title = re.sub(r"[\r\n\"'“”‘’《》【】#：:]+", " ", str(text or "")).strip()
    title = re.sub(r"\s+", " ", title)
    for prefix in ("标题", "对话标题", "名称", "对话名称"):
        if title.startswith(prefix):
            title = title[len(prefix):].lstrip(" ：:")
    title = title.strip(" .。-—_")
    if not title:
        return ""
    return title[:18] + ("..." if len(title) > 18 else "")


def generate_chat_title(user_text: str, assistant_text: str) -> str:
    seed = re.sub(r"\s+", " ", str(user_text or "").strip())
    assistant_seed = re.sub(r"\s+", " ", str(assistant_text or "").strip())
    prompt = (
        "请为下面这轮对话生成一个简短中文标题，只输出标题本身，"
        "不要解释，不要加引号，长度 2 到 10 个汉字。\n\n"
        f"用户：{seed[:500]}\n"
        f"助手：{assistant_seed[:500]}"
    )
    try:
        from remote_llm import call_remote_llm, is_remote_llm_ready, load_remote_llm_config
        config = load_remote_llm_config()
        if is_remote_llm_ready(config):
            config = dict(config)
            config["temperature"] = 0.2
            config["max_tokens"] = 32
            config["timeout"] = min(int(config.get("timeout") or 10), 10)
            title = _normalize_generated_chat_title(call_remote_llm(prompt, config=config))
            if title and not title.startswith("["):
                return title
    except Exception:
        pass
    try:
        from llm_inference import get_local_llm
        llm = get_local_llm()
        if getattr(llm, "loaded", False):
            title = _normalize_generated_chat_title(llm.chat(prompt, history=None, max_new_tokens=32, temperature=0.2))
            if title and not title.startswith("["):
                return title
    except Exception:
        pass
    try:
        from tiny_llm import tiny_llm_chat
        title = _normalize_generated_chat_title(tiny_llm_chat(prompt, history=None))
        if title and title not in {"...", "。"} and not title.startswith("["):
            return title
    except Exception:
        pass
    return _recent_chat_title(seed)


def load_recent_chats() -> list[dict]:
    ensure_data()
    data = read_sensitive_json(RECENT_CHATS_FILE, {"chats": []})
    chats = data.get("chats", []) if isinstance(data, dict) else []
    if not isinstance(chats, list):
        chats = []
    normalized = []
    for chat in chats:
        if not isinstance(chat, dict):
            continue
        chat_id = str(chat.get("id") or "").strip()
        if not chat_id:
            continue
        messages = []
        for item in chat.get("messages", []):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            text = str(item.get("text") or item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not text:
                continue
            messages.append({
                "role": role,
                "text": text[:4000],
                "time": int(item.get("time") or chat.get("updated_at") or time.time()),
            })
        normalized.append({
            "id": chat_id,
            "title": str(chat.get("title") or _recent_chat_title(messages[0]["text"] if messages else "")).strip()[:40] or "新对话",
            "created_at": int(chat.get("created_at") or chat.get("updated_at") or time.time()),
            "updated_at": int(chat.get("updated_at") or chat.get("created_at") or time.time()),
            "messages": messages[-80:],
        })
    normalized.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
    return normalized[:30]


def save_recent_chats(chats: list[dict]) -> None:
    write_sensitive_json(RECENT_CHATS_FILE, {"chats": chats[:30]})


def upsert_recent_chat(conversation_id: str, user_text: str, assistant_text: str) -> tuple[str, list[dict]]:
    chats = load_recent_chats()
    now = int(time.time())
    chat_id = str(conversation_id or "").strip()
    if not chat_id:
        seed = f"{now}:{user_text}:{assistant_text}"
        chat_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    current = next((item for item in chats if item.get("id") == chat_id), None)
    if current is None:
        current = {
            "id": chat_id,
            "title": generate_chat_title(user_text, assistant_text),
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        chats.insert(0, current)
    current["updated_at"] = now
    if not current.get("title") or current.get("title") == "新对话":
        current["title"] = generate_chat_title(user_text, assistant_text)
    messages = list(current.get("messages", []))
    if user_text:
        messages.append({"role": "user", "text": str(user_text).strip()[:4000], "time": now})
    if assistant_text:
        messages.append({"role": "assistant", "text": str(assistant_text).strip()[:4000], "time": now})
    current["messages"] = messages[-80:]
    chats = [current] + [item for item in chats if item.get("id") != chat_id]
    save_recent_chats(chats)
    return chat_id, chats[:30]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip = False
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip = True
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text + " "
        self.parts.append(text)

    def text(self) -> str:
        joined = " ".join(self.parts)
        joined = re.sub(r"\s+", " ", joined)
        return html.unescape(joined).strip()


@dataclass
class PageResult:
    ok: bool
    title: str
    text: str
    error: str = ""


@dataclass
class FileResult:
    ok: bool
    file_id: str
    name: str
    kind: str
    summary: str
    preview_url: str = ""
    error: str = ""


def safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "upload.bin"
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", base)[:120]


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def image_info(raw: bytes) -> tuple[str, int, int] | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
        width, height = struct.unpack(">II", raw[16:24])
        return "PNG", width, height
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        width, height = struct.unpack("<HH", raw[6:10])
        return "GIF", width, height
    if raw.startswith(b"BM") and len(raw) >= 26:
        width, height = struct.unpack("<II", raw[18:26])
        return "BMP", width, height
    if raw.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            i += 2
            if marker in {0xD8, 0xD9}:
                continue
            if i + 2 > len(raw):
                break
            size = struct.unpack(">H", raw[i:i + 2])[0]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and i + 7 <= len(raw):
                height, width = struct.unpack(">HH", raw[i + 3:i + 7])
                return "JPEG", width, height
            i += size
        return "JPEG", 0, 0
    return None


def find_tesseract() -> str | None:
    local_candidates = [
        OCR_DIR / "Tesseract-OCR" / "tesseract.exe",
        OCR_DIR / "tesseract" / "tesseract.exe",
        OCR_DIR / "tesseract.exe",
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def tesseract_languages(tesseract: str) -> set[str]:
    try:
        proc = subprocess.run(
            [tesseract, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=8,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return set()
    langs = set()
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        item = line.strip()
        if item and re.match(r"^[A-Za-z_]+$", item):
            langs.add(item)
    return langs


def rapidocr_python() -> Path:
    return RAPIDOCR_VENV / "Scripts" / "python.exe"


def find_python312() -> list[str]:
    py = shutil.which("py")
    if py:
        probe = subprocess.run([py, "-3.12", "-c", "import sys; print(python_exe())"], capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
        if probe.returncode == 0:
            return [py, "-3.12"]
    return [python_exe()]


def rapidocr_available() -> bool:
    return rapidocr_python().exists()


def install_rapidocr_portable() -> str:
    RAPIDOCR_DIR.mkdir(parents=True, exist_ok=True)
    py_cmd = find_python312()
    if not rapidocr_python().exists():
        subprocess.run(py_cmd + ["-m", "venv", str(RAPIDOCR_VENV)], check=True, timeout=120, creationflags=CREATE_NO_WINDOW)

    venv_python = rapidocr_python()
    subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=False, timeout=180, creationflags=CREATE_NO_WINDOW)
    proc = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "rapidocr-onnxruntime", "pillow"],
        capture_output=True,
        text=True,
        timeout=600,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        return (
            "RapidOCR 便携安装失败：\n"
            f"{proc.stdout[-1000:]}\n{proc.stderr[-1000:]}\n"
            "建议确认 Python 3.12 可用，或稍后重试。"
        )
    return (
        "RapidOCR 便携版安装完成：\n"
        f"{venv_python}\n"
        "现在重新上传图片，或对已上传图片再次输入 /ocr。"
    )


def _ensure_rapidocr_runner() -> Path:
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    if not RAPIDOCR_RUNNER.is_file() or RAPIDOCR_RUNNER.read_text(encoding="utf-8", errors="replace") != _RAPIDOCR_RUNNER_SOURCE:
        RAPIDOCR_RUNNER.write_text(_RAPIDOCR_RUNNER_SOURCE, encoding="utf-8")
    return RAPIDOCR_RUNNER


def run_rapidocr(path: Path) -> str:
    if not rapidocr_available():
        return "RapidOCR：未安装。输入 /install_ocr 可自动安装便携版 OCR。"
    try:
        runner = _ensure_rapidocr_runner()
    except Exception as exc:
        return f"RapidOCR：运行器准备失败：{exc}"
    try:
        proc = subprocess.run(
            [str(rapidocr_python()), str(runner), str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        data = json.loads((proc.stdout or "{}").strip() or "{}")
        if not data.get("ok"):
            return f"RapidOCR：识别失败：{data.get('error') or proc.stderr.strip()}"
        lines = [item.get("text", "") for item in data.get("lines", []) if item.get("text")]
        if not lines:
            return "RapidOCR：未识别到文字。"
        return "RapidOCR 识别文字：\n" + "\n".join(lines[:80])[:3000]
    except Exception as exc:
        return f"RapidOCR：识别失败：{exc}"


def download_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "CompanionAI/0.1"})
    with open_url(req, timeout=120) as resp:
        with target.open("wb") as f:
            shutil.copyfileobj(resp, f)


def install_portable_ocr() -> str:
    existing = find_tesseract()
    if existing:
        return f"OCR 已可用：\n{existing}"

    ensure_data()
    install_dir = OCR_DIR / "Tesseract-OCR"
    installer = OCR_DIR / "downloads" / Path(TESSERACT_INSTALLER_URL).name
    seven_zip_zip = OCR_DIR / "downloads" / "7za920.zip"
    seven_zip_dir = OCR_DIR / "tools" / "7za"
    seven_zip_exe = seven_zip_dir / "7za.exe"
    inno_zip = OCR_DIR / "downloads" / "innoextract-1.9-windows.zip"
    inno_dir = OCR_DIR / "tools" / "innoextract"
    inno_exe = inno_dir / "innoextract.exe"
    tesseract_exe = install_dir / "tesseract.exe"

    try:
        if not installer.exists():
            download_file(TESSERACT_INSTALLER_URL, installer)
        if not seven_zip_exe.exists():
            download_file(SEVEN_ZIP_URL, seven_zip_zip)
            shutil.unpack_archive(seven_zip_zip, seven_zip_dir)
        if not inno_exe.exists():
            download_file(INNOEXTRACT_URL, inno_zip)
            shutil.unpack_archive(inno_zip, inno_dir)

        install_dir.mkdir(parents=True, exist_ok=True)
        extract_dir = OCR_DIR / "extract" / "tesseract"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            [str(seven_zip_exe), "x", str(installer), f"-o{extract_dir}", "-y"],
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )

        found_tesseract = list(extract_dir.rglob("tesseract.exe"))
        if not found_tesseract:
            shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(
                [str(inno_exe), "--extract", "--output-dir", str(extract_dir), str(installer)],
                capture_output=True,
                text=True,
                timeout=180,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            found_tesseract = list(extract_dir.rglob("tesseract.exe"))
        if found_tesseract:
            extracted_root = found_tesseract[0].parent
            if install_dir.exists():
                shutil.rmtree(install_dir)
            shutil.copytree(extracted_root, install_dir)

        if not tesseract_exe.exists():
            rapid = install_rapidocr_portable()
            return (
                "Tesseract 便携解包不可用，已改用 RapidOCR 便携后端。\n\n"
                f"{rapid}\n\n"
                "说明：RapidOCR 同样是本地 OCR，不上传云端。"
            )

        tessdata = install_dir / "tessdata"
        tessdata.mkdir(parents=True, exist_ok=True)
        downloaded_langs = []
        for lang, url in TESSDATA_FAST_URLS.items():
            target = tessdata / f"{lang}.traineddata"
            if not target.exists():
                download_file(url, target)
            downloaded_langs.append(lang)

        proc = subprocess.run(
            [str(tesseract_exe), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        version = (proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr).strip() else "version unknown"
        return (
            "OCR 便携版安装完成：\n"
            f"{tesseract_exe}\n"
            f"{version}\n"
            f"语言包：{', '.join(downloaded_langs)}\n\n"
            "现在重新上传图片，或对已上传图片再次输入 /ocr。"
        )
    except Exception as exc:
        rapid = install_rapidocr_portable()
        return (
            f"Tesseract 便携安装失败：{exc}\n\n"
            "已尝试安装 RapidOCR 便携后端：\n"
            f"{rapid}"
        )


def ocr_image(path: Path) -> str:
    tesseract = find_tesseract()
    if not tesseract:
        if rapidocr_available():
            return run_rapidocr(path)
        return "OCR：未找到本地 OCR。输入 /install_ocr 可自动安装本地便携版 OCR。"
    langs = tesseract_languages(tesseract)
    selected = []
    for lang in ["chi_sim", "chi_tra", "eng"]:
        if lang in langs:
            selected.append(lang)
    lang_arg = "+".join(selected) if selected else "eng"
    try:
        proc = subprocess.run(
            [tesseract, str(path), "stdout", "-l", lang_arg, "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return "OCR：识别超时。"
    except Exception as exc:
        return f"OCR：识别失败：{exc}"
    text = re.sub(r"\n{3,}", "\n\n", proc.stdout.strip())
    if proc.returncode != 0 and not text:
        err = proc.stderr.strip()[:500]
        return f"OCR：识别失败：{err or 'Tesseract 返回错误。'}"
    if not text:
        return f"OCR：未识别到文字。使用语言：{lang_arg}"
    return f"OCR 识别文字（语言：{lang_arg}）：\n{text[:3000]}"


def summarize_json(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"JSON 解析失败：{exc}\n原文片段：{text[:900]}"
    if isinstance(data, dict):
        keys = list(data.keys())[:20]
        return f"JSON 对象，顶层字段 {len(data)} 个：{', '.join(map(str, keys))}"
    if isinstance(data, list):
        first = data[0] if data else None
        detail = ""
        if isinstance(first, dict):
            detail = "；首项字段：" + ", ".join(map(str, list(first.keys())[:15]))
        return f"JSON 数组，长度 {len(data)}{detail}"
    return f"JSON 值：{type(data).__name__}，内容片段：{str(data)[:500]}"


def summarize_table(text: str, delimiter: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    rows = [line.split(delimiter) for line in lines[:8]]
    if not rows:
        return "表格为空。"
    columns = rows[0]
    preview = "\n".join(" | ".join(cell.strip()[:40] for cell in row[:8]) for row in rows[:6])
    return f"表格数据，估计列数 {len(columns)}，已读取前 {min(len(lines), 8)} 行。\n预览：\n{preview}"


def summarize_file(path: Path, original_name: str, file_id: str) -> FileResult:
    raw = path.read_bytes()
    size = len(raw)
    ext = path.suffix.lower()
    info = image_info(raw)
    if info:
        fmt, width, height = info
        dims = f"{width} x {height}" if width and height else "尺寸未识别"
        ocr = ocr_image(path)
        summary = f"图片文件：{fmt}，{dims}，大小 {size} 字节。\n{ocr}"
        return FileResult(True, file_id, original_name, "image", summary, f"/uploads/{path.name}")

    text_exts = {".txt", ".md", ".json", ".csv", ".tsv", ".html", ".htm", ".xml", ".log", ".py", ".js", ".ts", ".css", ".cpp", ".h"}
    if ext in text_exts or b"\x00" not in raw[:4096]:
        text = decode_text(raw)
        if ext == ".json":
            summary = summarize_json(text)
        elif ext == ".csv":
            summary = summarize_table(text, ",")
        elif ext == ".tsv":
            summary = summarize_table(text, "\t")
        elif ext in {".html", ".htm"}:
            parser = TextExtractor()
            parser.feed(text)
            summary = f"HTML 文档：{parser.title.strip() or original_name}\n正文片段：{parser.text()[:1200]}"
        else:
            lines = text.splitlines()
            summary = f"文本文件，共 {len(lines)} 行，{len(text)} 个字符。\n片段：\n{text[:1600]}"
        return FileResult(True, file_id, original_name, "text", summary)

    return FileResult(True, file_id, original_name, "binary", f"二进制文件，扩展名 {ext or '无'}，大小 {size} 字节。当前本地版只能保存和记录基础信息。")


def _extract_ocr_text(summary: str) -> str:
    match = re.search(r"OCR 识别文字（[^）]+）：\n(.+)", summary, flags=re.S)
    if match:
        return match.group(1).strip()
    if "OCR：未识别到文字" in summary:
        return ""
    return summary.strip()


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [word for word in keywords if word.lower() in lowered]


def infer_screen_activity(ocr_text: str, app: dict, width: int, height: int) -> dict:
    """Infer a useful screen-level observation from local metadata and OCR text."""
    title = str(app.get("title") or "")
    process = str(app.get("process") or "")
    combined = "\n".join([title, process, ocr_text])
    signals: list[str] = []
    activity = "用户正在查看当前屏幕内容"
    intent = "可能是在确认信息、阅读内容或准备下一步操作"

    scenarios = [
        (
            "编程/调试",
            ["Visual Studio", "VS Code", "PyCharm", "SCons", "Traceback", "Exception", "def ", "class ", "function", "error", ".py", ".js", ".cs", "git", "terminal", "PowerShell"],
            "用户可能正在写代码、调试问题或查看构建/终端输出",
            "可能需要定位报错、理解代码上下文、修改实现或验证运行结果",
        ),
        (
            "聊天/AI 协作",
            ["Codex", "ChatGPT", "assistant", "user", "发送", "聊天", "conversation", "prompt", "回复"],
            "用户可能正在和 AI 或聊天工具沟通需求",
            "可能需要把当前对话整理成可执行任务、继续排查或生成回复",
        ),
        (
            "浏览网页/查资料",
            ["Chrome", "Edge", "Firefox", "http", "www.", "搜索", "Google", "Bing", "页面", "网页", "文档", "docs"],
            "用户可能正在浏览网页、查资料或阅读文档",
            "可能需要总结页面、提取重点、核对信息或给出下一步建议",
        ),
        (
            "文档/写作",
            ["Word", "Excel", "PowerPoint", "Notepad", "Markdown", "文档", "表格", "标题", "段落", "保存", "编辑"],
            "用户可能正在编辑文档、表格或文字内容",
            "可能需要润色、总结、检查格式或整理内容结构",
        ),
        (
            "文件管理",
            ["Explorer", "资源管理器", "文件夹", "下载", "桌面", "复制", "粘贴", "删除", "重命名"],
            "用户可能正在管理文件或查找本地资源",
            "可能需要识别文件位置、整理文件或判断下一步操作",
        ),
        (
            "设置/配置",
            ["Settings", "设置", "配置", "选项", "权限", "隐私", "安装", "启用", "禁用", "API Key", "模型"],
            "用户可能正在调整软件设置或配置能力",
            "可能需要解释选项含义、检查配置是否完整或指导修正",
        ),
        (
            "媒体/设计",
            ["Photoshop", "Figma", "画布", "图层", "颜色", "图片", "预览", "设计", "canvas", "layer"],
            "用户可能正在查看或制作视觉内容",
            "可能需要描述画面、检查布局、给出设计修改建议",
        ),
    ]

    best_name = ""
    best_score = 0
    for name, keywords, scenario_activity, scenario_intent in scenarios:
        hits = _keyword_hits(combined, keywords)
        score = len(hits)
        if score > best_score:
            best_name = name
            best_score = score
            signals = hits[:8]
            activity = scenario_activity
            intent = scenario_intent

    if not ocr_text.strip():
        activity = "用户当前屏幕文字较少，可能是在看图片、应用界面、游戏画面或空白页面"
        intent = "可能需要我先描述可见布局，再结合前台窗口判断正在做什么"

    orientation = "横屏" if width >= height else "竖屏"
    return {
        "scene": best_name or "常规桌面",
        "activity": activity,
        "intent": intent,
        "signals": signals,
        "orientation": orientation,
    }


def screen_observation_mode_hint(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "summary"
    diagnostic_keywords = ("卡在哪", "卡在哪里", "卡住", "问题", "报错", "怎么做", "怎么办", "下一步", "建议", "操作", "排查", "诊断")
    return "diagnostic" if any(keyword in raw for keyword in diagnostic_keywords) else "summary"


def build_screen_observation_summary(path: Path, base_summary: str, mode: str = "summary") -> str:
    raw = path.read_bytes()
    info = image_info(raw)
    width = info[1] if info else 0
    height = info[2] if info else 0
    app = foreground_app_context()
    ocr_text = _extract_ocr_text(base_summary)
    inference = infer_screen_activity(ocr_text, app, width, height)

    lines = [
        "屏幕理解：",
        f"- 当前场景：{inference['scene']}（{inference['orientation']}，{width or '?'} x {height or '?'}）",
        f"- 前台窗口：{app.get('process') or '未知程序'} / {app.get('title') or '无标题'}",
        f"- 用户可能在做：{inference['activity']}",
    ]
    if mode == "diagnostic":
        lines.append(f"- 可能意图：{inference['intent']}")
    if inference["signals"]:
        lines.append("- 判断依据：" + "、".join(inference["signals"]))
    if ocr_text.strip():
        compact_ocr = re.sub(r"\s+", " ", ocr_text).strip()
        lines.append("- 屏幕文字摘录：" + compact_ocr[:900])
    else:
        lines.append("- 屏幕文字摘录：未识别到明显文字。")

    api_summary = refine_screen_observation_with_llm(lines, ocr_text, mode)
    if api_summary:
        title = "操作判断：" if mode == "diagnostic" else "屏幕内容总结："
        lines.extend(["", title, api_summary])
    elif mode == "diagnostic":
        lines.extend([
            "",
            "操作判断：如果你要我排查当前任务卡在哪里，可以继续说明目标或让我根据截图中的文字整理下一步。",
        ])
    return "\n".join(lines)


def refine_screen_observation_with_llm(local_lines: list[str], ocr_text: str, mode: str = "summary") -> str:
    try:
        from remote_llm import call_remote_llm, is_remote_llm_ready, load_remote_llm_config
    except Exception:
        return ""
    config = load_remote_llm_config()
    if not is_remote_llm_ready(config):
        return ""
    if mode == "diagnostic":
        instruction = (
            "请根据这次用户主动触发的屏幕观察，像多模态助手一样给出简洁判断："
            "用户现在大概在做什么、画面重点是什么、当前任务可能卡在哪里、下一步可怎么处理。"
            "不要声称看到了 OCR 和窗口标题之外无法确认的细节；不超过 180 字。"
        )
    else:
        instruction = (
            "请根据这次用户主动触发的屏幕观察，只总结屏幕上可见内容和画面重点。"
            "不要主动推断任务卡点、不要给操作建议；不要声称看到了 OCR 和窗口标题之外无法确认的细节；不超过 160 字。"
        )
    prompt = (
        "[用户消息]\n"
        f"{instruction}\n\n"
        "[已读取文件：screen_observation.txt]\n"
        + "\n".join(local_lines)
        + "\n\nOCR 原文：\n"
        + ocr_text[:1800]
    )
    result = call_remote_llm(
        prompt,
        history=[],
        config={
            **config,
            "temperature": 0.2,
            "max_tokens": min(int(config.get("max_tokens", 1024)), 320),
        },
    )
    if not result or result.startswith("["):
        return ""
    return result.strip()[:500]


def add_file_record(result: FileResult, stored_name: str) -> dict:
    files = load_files()
    record = {
        "time": int(time.time()),
        "id": result.file_id,
        "name": result.name,
        "kind": result.kind,
        "summary": result.summary,
        "preview_url": result.preview_url,
        "stored_name": stored_name,
    }
    files["files"].append(record)
    save_files(files)
    return record


def get_file_record(file_id: str) -> dict | None:
    if not file_id:
        return None
    for item in reversed(load_files().get("files", [])):
        if item.get("id") == file_id:
            return item
    return None


def update_file_record(file_id: str, summary: str) -> dict | None:
    files = load_files()
    updated = None
    for item in files.get("files", []):
        if item.get("id") == file_id:
            item["summary"] = summary
            updated = item
    save_files(files)
    return updated


def parse_multipart(body: bytes, content_type: str) -> tuple[str, bytes] | None:
    match = re.search(r"boundary=(.+)", content_type)
    if not match:
        return None
    boundary = match.group(1).split(";")[0].strip().strip('"').encode("utf-8")
    marker = b"--" + boundary
    for part in body.split(marker):
        if b"\r\n\r\n" in part:
            header_raw, data = part.split(b"\r\n\r\n", 1)
        elif b"\n\n" in part:
            header_raw, data = part.split(b"\n\n", 1)
        else:
            continue
        headers = header_raw.decode("utf-8", errors="replace")
        if "Content-Disposition" not in headers:
            continue
        name_match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";\r\n]*)"?', headers)
        filename = urllib.parse.unquote(name_match.group(1)) if name_match and name_match.group(1) else "upload.bin"
        data = data.rstrip(b"\r\n-")
        return filename, data
    return None


def handle_upload(body: bytes, content_type: str) -> dict:
    parsed = parse_multipart(body, content_type)
    if not parsed:
        return {"ok": False, "error": "没有找到上传文件。"}
    original_name, data = parsed
    if len(data) > 12_000_000:
        return {"ok": False, "error": "单个文件暂时限制 12MB。"}
    file_id = str(int(time.time() * 1000))
    safe = safe_filename(original_name)
    stored_name = f"{file_id}_{safe}"
    path = UPLOAD_DIR / stored_name
    path.write_bytes(data)
    result = summarize_file(path, original_name, file_id)
    record = add_file_record(result, stored_name)
    return {"ok": True, "file": record, "files": load_files(), "avatar": avatar_state("scan" if record.get("kind") == "image" else "read")}


def _process_name_from_pid(pid: int) -> str:
    if not pid:
        return ""
    try:
        result = subprocess.run(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=2,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        line = result.stdout.strip().splitlines()[0]
        if line and line != "INFO: No tasks are running which match the specified criteria.":
            return line.split('","')[0].strip('"')
    except Exception:
        pass
    return ""


def foreground_app_context() -> dict[str, str]:
    if not _HAS_CTYPES:
        return {"title": "", "process": "", "pid": ""}
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"title": "", "process": "", "pid": ""}
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return {
            "title": buffer.value.strip(),
            "process": _process_name_from_pid(pid.value),
            "pid": str(pid.value),
        }
    except Exception:
        return {"title": "", "process": "", "pid": ""}


def cursor_monitor_bbox() -> tuple[int, int, int, int] | None:
    """Return the Windows monitor rectangle containing the current cursor."""
    if not _HAS_CTYPES:
        return None
    try:
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.c_ulong),
            ]

        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return None

        user32.MonitorFromPoint.argtypes = [POINT, ctypes.c_ulong]
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        monitor = user32.MonitorFromPoint(point, 2)
        if not monitor:
            return None

        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = ctypes.c_int
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None

        rect = info.rcMonitor
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception:
        return None


def recent_visual_observations(limit: int = 2) -> list[dict]:
    files = load_files().get("files", [])
    visuals = [item for item in files if item.get("kind") == "image"]
    return visuals[-limit:]


def reality_context_text() -> str:
    """Build local, user-authorized context for the next assistant reply."""
    lines = ["[本地现实上下文]"]
    lines.append(local_time_text())

    app = foreground_app_context()
    if app.get("title") or app.get("process"):
        lines.append(
            "前台窗口："
            f"{app.get('process') or '未知程序'}"
            f" / {app.get('title') or '无标题'}"
        )

    lines.append(identity_confirmation_context())

    visuals = recent_visual_observations()
    if visuals:
        lines.append("最近视觉观察：")
        for item in visuals:
            name = item.get("name", "image")
            summary = re.sub(r"\s+", " ", item.get("summary", "")).strip()[:420]
            lines.append(f"- {name}: {summary}")
    else:
        lines.append("最近视觉观察：暂无。只有用户触发 /see_screen 或 /camera 后才会保存。")
    return "\n".join(lines)


def context_status_text() -> str:
    return reality_context_text() + "\n\n这些数据只来自本机：时间、当前前台窗口标题，以及你主动触发的屏幕/摄像头观察记录。"


def observe_screen(mode: str = "summary") -> dict:
    """Capture the current desktop after the user explicitly asks from the local UI/chat."""
    try:
        from PIL import ImageGrab
    except Exception:
        return {
            "ok": False,
            "error": "屏幕视觉需要 Pillow。请在当前 Python 环境安装：pip install pillow",
        }

    ensure_data()
    file_id = str(int(time.time() * 1000))
    stored_name = f"{file_id}_screen.png"
    path = UPLOAD_DIR / stored_name
    try:
        bbox = cursor_monitor_bbox()
        if bbox:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        else:
            image = ImageGrab.grab(all_screens=True)
        image.save(path, "PNG")
    except Exception as exc:
        return {"ok": False, "error": f"截屏失败：{exc}"}

    result = summarize_file(path, "screen.png", file_id)
    if result.ok:
        result.summary = build_screen_observation_summary(path, result.summary, mode)
    record = add_file_record(result, stored_name)
    return {
        "ok": True,
        "file": record,
        "files": load_files(),
        "avatar": avatar_state("scan"),
        "reply": "我已经看了一眼当前屏幕，并把截图保存为视觉观察记录。\n" + record.get("summary", ""),
    }


def observe_camera(camera_index: int = 0) -> dict:
    """Capture one frame from the camera after the user explicitly asks."""
    cv2 = None
    try:
        ensure_optional_site_packages()
        import cv2 as _cv2
        cv2 = _cv2
    except Exception as exc:
        # In frozen mode, direct import may fail due to C extension issues;
        # fall back to capturing via subprocess using the real Python interpreter.
        cv2 = None
        _cv2_import_error = exc

    ensure_data()
    file_id = str(int(time.time() * 1000))
    stored_name = f"{file_id}_camera.png"
    path = UPLOAD_DIR / stored_name

    if cv2 is not None:
        # In-process capture (fast path)
        camera = None
        try:
            camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not camera.isOpened():
                camera.release()
                camera = cv2.VideoCapture(camera_index)
            if not camera.isOpened():
                return {"ok": False, "error": f"无法打开摄像头 {camera_index}。请确认系统权限和摄像头未被其他软件占用。"}
            ok, frame = camera.read()
            if not ok or frame is None:
                return {"ok": False, "error": "摄像头已打开，但没有读取到画面。"}
            cv2.imwrite(str(path), frame)
        except Exception as exc:
            return {"ok": False, "error": f"摄像头抓拍失败：{exc}"}
        finally:
            if camera is not None:
                camera.release()
    else:
        # Subprocess fallback: use the real Python to import cv2 and capture
        try:
            py = runtime_python_exe(create=False)
        except RuntimeError as exc:
            return {
                "ok": False,
                "error": f"摄像头观察需要 OpenCV（import cv2 失败：{_cv2_import_error}），且组件虚拟环境不可用（{exc}）。请先在设置中安装 OpenCV。",
            }
        capture_code = (
            "import sys, json\n"
            "try:\n"
            "    import cv2\n"
            "except Exception as e:\n"
            f"    print(json.dumps({{'ok': False, 'error': f'import cv2 failed: {{e}}'}})); sys.exit(0)\n"
            f"    camera = None\n"
            "try:\n"
            f"    camera = cv2.VideoCapture({camera_index}, cv2.CAP_DSHOW)\n"
            "    if not camera.isOpened():\n"
            "        camera.release()\n"
            f"        camera = cv2.VideoCapture({camera_index})\n"
            "    if not camera.isOpened():\n"
            f"        print(json.dumps({{'ok': False, 'error': '无法打开摄像头 {camera_index}'}})); sys.exit(0)\n"
            "    ok, frame = camera.read()\n"
            "    if not ok or frame is None:\n"
            f"        print(json.dumps({{'ok': False, 'error': '摄像头已打开但无画面'}})); sys.exit(0)\n"
            "    path = sys.argv[1]\n"
            "    cv2.imwrite(path, frame)\n"
            f"    print(json.dumps({{'ok': True, 'path': path}}))\n"
            "except Exception as e:\n"
            f"    print(json.dumps({{'ok': False, 'error': str(e)}}))\n"
            "finally:\n"
            "    if camera is not None: camera.release()\n"
        )
        try:
            result = subprocess.run(
                [py, "-c", capture_code, str(path)],
                capture_output=True, text=True, timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                return {"ok": False, "error": f"摄像头子进程失败：{result.stderr.strip() or '未知错误'}"}
            import json
            info = json.loads(result.stdout.strip())
            if not info.get("ok"):
                return {"ok": False, "error": info.get("error", "子进程抓拍失败")}
        except Exception as exc:
            return {
                "ok": False,
                "error": f"摄像头观察需要 OpenCV（import cv2 失败：{_cv2_import_error}）。请先在设置中安装 OpenCV。",
            }

    result = summarize_file(path, "camera.png", file_id)
    record = add_file_record(result, stored_name)
    return {
        "ok": True,
        "file": record,
        "files": load_files(),
        "avatar": avatar_state("scan"),
        "reply": "我已经从摄像头抓拍了一帧，并把它保存为视觉观察记录。\n" + record.get("summary", ""),
    }


def vision_status_text() -> str:
    files = load_files().get("files", [])
    visual_items = [item for item in files if item.get("kind") == "image"]
    screen_items = [item for item in visual_items if item.get("name") == "screen.png" or item.get("stored_name", "").endswith("_screen.png")]
    camera_items = [item for item in visual_items if item.get("name") == "camera.png" or item.get("stored_name", "").endswith("_camera.png")]
    lines = [
        "视觉状态：",
        f"图片观察：{len(visual_items)} 次",
        f"屏幕观察：{len(screen_items)} 次",
        f"摄像头观察：{len(camera_items)} 次",
    ]
    latest_items = visual_items[-1:] if visual_items else []
    if latest_items:
        latest = latest_items[0]
        lines.append("\n最近视觉观察：")
        lines.append(f"来源：{latest.get('name', '')}")
        lines.append(latest.get("summary", "")[:900])
    else:
        lines.append("\n用 /see_screen、/camera 或点击对应按钮后，我会做一次本地视觉摘要。")
    return "\n".join(lines)


def realtime_observation_context(payload: dict) -> dict:
    """Collect explicit realtime-chat observations requested by the user UI."""
    modes = payload.get("modes", {})
    if not isinstance(modes, dict):
        modes = {}
    camera_index = 0
    try:
        camera_index = max(0, int(payload.get("camera_index", 0)))
    except Exception:
        camera_index = 0

    lines = []
    files_payload = None
    avatar_payload = None

    if modes.get("screen"):
        result = observe_screen()
        if result.get("ok"):
            summary = str(result.get("file", {}).get("summary") or result.get("reply") or "").strip()
            lines.append("屏幕观察：" + (summary[:900] or "已完成截图观察。"))
            files_payload = result.get("files") or files_payload
            avatar_payload = result.get("avatar") or avatar_payload
        else:
            lines.append("屏幕观察失败：" + str(result.get("error", "未知错误"))[:300])

    if modes.get("camera"):
        result = observe_camera(camera_index)
        if result.get("ok"):
            summary = str(result.get("file", {}).get("summary") or result.get("reply") or "").strip()
            lines.append("摄像头物体/场景观察：" + (summary[:900] or "已完成摄像头抓拍观察。"))
            files_payload = result.get("files") or files_payload
            avatar_payload = result.get("avatar") or avatar_payload
        else:
            lines.append("摄像头观察失败：" + str(result.get("error", "未知错误"))[:300])

    if modes.get("face"):
        try:
            result = face_manager.recognize_from_camera()
            record_face_confirmation_from_result(result)
            if result.get("ok"):
                faces = result.get("faces", [])
                if not faces:
                    lines.append("人物识别：摄像头画面中未检测到人脸。")
                else:
                    known = [f for f in faces if f.get("known")]
                    unknown = [f for f in faces if not f.get("known")]
                    parts = [f"检测到 {len(faces)} 张人脸"]
                    if known:
                        names = [
                            f"{f.get('name', '未知')}({float(f.get('confidence', 0) or 0):.2f})"
                            for f in known
                        ]
                        parts.append("已知：" + "、".join(names))
                    if unknown:
                        parts.append(f"未知：{len(unknown)} 张")
                    confirmed = result.get("identity_confirmed")
                    if confirmed:
                        parts.append(
                            f"当前对话身份：{confirmed.get('name')}，"
                            f"置信度 {float(confirmed.get('confidence', 0) or 0):.2f}"
                        )
                    lines.append("人物识别：" + "；".join(parts))
            else:
                lines.append("人物识别失败：" + str(result.get("error", "未知错误"))[:300])
        except Exception as exc:
            lines.append("人物识别失败：" + str(exc)[:300])

    context = "\n".join(line for line in lines if line).strip()
    return {
        "ok": bool(context),
        "context": context,
        "files": files_payload or load_files(),
        "avatar": avatar_payload or avatar_state("scan"),
    }


def fetch_page(url: str) -> PageResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return PageResult(False, "", "", "只支持 http/https 链接。")

    try:
        host = parsed.hostname or ""
        socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        return PageResult(False, "", "", f"域名解析失败：{exc}")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CompanionAI/0.1 (+local user-authorized fetch)",
            "Accept": "text/html,text/plain,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("content-type", "")
            raw = resp.read(1_500_000)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return PageResult(False, "", "", "目标返回权限错误。请使用网站允许的 API/导出方式，或提供你有权访问的内容。")
        return PageResult(False, "", "", f"HTTP 错误：{exc.code}")
    except Exception as exc:
        return PageResult(False, "", "", f"读取失败：{exc}")

    encoding = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    body = raw.decode(encoding, errors="replace")

    if "html" in content_type or "<html" in body[:1000].lower():
        parser = TextExtractor()
        parser.feed(body)
        text = parser.text()
        title = parser.title.strip() or parsed.netloc
    else:
        text = re.sub(r"\s+", " ", body).strip()
        title = parsed.netloc

    return PageResult(True, title[:160], text[:12000])


def fetch_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "CompanionAI/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def local_time_text() -> str:
    now = datetime.now().astimezone()
    try:
        hk_now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    except Exception:
        hk_now = datetime.now(timezone(timedelta(hours=8), "HKT"))
    lines = [f"本机时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}"]
    if now.utcoffset() != hk_now.utcoffset():
        lines.append(f"香港时间：{hk_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    return "\n".join(lines)


def weather_text(location: str) -> str:
    location = location.strip() or "Hong Kong"
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({
        "name": location,
        "count": "1",
        "language": "zh",
        "format": "json",
    })
    try:
        geo = fetch_json(geo_url)
        results = geo.get("results") or []
        if not results:
            return f"没有找到地点：{location}"
        place = results[0]
        lat = place["latitude"]
        lon = place["longitude"]
        name = ", ".join(str(x) for x in [place.get("name"), place.get("admin1"), place.get("country")] if x)
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        })
        data = fetch_json(forecast_url)
        current = data.get("current") or {}
        units = data.get("current_units") or {}
        code = current.get("weather_code")
        desc = WEATHER_CODES.get(code, f"天气代码 {code}")
        return (
            f"{name} 当前天气：{desc}\n"
            f"温度：{current.get('temperature_2m')} {units.get('temperature_2m', '°C')}\n"
            f"体感：{current.get('apparent_temperature')} {units.get('apparent_temperature', '°C')}\n"
            f"湿度：{current.get('relative_humidity_2m')} {units.get('relative_humidity_2m', '%')}\n"
            f"降水：{current.get('precipitation')} {units.get('precipitation', 'mm')}\n"
            f"风速：{current.get('wind_speed_10m')} {units.get('wind_speed_10m', 'km/h')}\n"
            f"更新时间：{current.get('time')}"
        )
    except Exception as exc:
        return f"天气读取失败：{exc}"


def extract_memory_candidates(message: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    lowered = message.lower()
    if any(key in message for key in ["我喜欢", "我偏好", "我更喜欢", "我希望", "以后请", "记住"]):
        candidates.append(("preferences", message.strip()))
    if any(key in message for key in ["我的目标", "我正在", "我住在", "我的项目", "我叫"]):
        candidates.append(("profile", message.strip()))
    if any(key in lowered for key in ["deadline", "todo", "important"]) or any(key in message for key in ["重要", "截止", "待办"]):
        candidates.append(("facts", message.strip()))
    return candidates[:3]


EMOTION_RULES = [
    (
        "悲伤",
        ["悲伤", "难过", "伤心", "不如意", "委屈", "失落", "崩溃", "想哭", "痛苦", "depressed", "sad", "hurt"],
        "先放慢语气，承认这段文字里有受伤或低落的部分，再回应具体内容。",
    ),
    (
        "焦虑/压力",
        ["焦虑", "紧张", "压力", "害怕", "担心", "来不及", "撑不住", "anxious", "stress", "worried"],
        "先帮对方稳定下来，再把事情拆小，不要一上来催促或给太多任务。",
    ),
    (
        "生气/不满",
        ["生气", "愤怒", "烦死", "火大", "不爽", "讨厌", "离谱", "angry", "mad", "annoyed"],
        "先识别不满背后的边界或需求，再给出冷静、可执行的处理建议。",
    ),
    (
        "开心/期待",
        ["开心", "高兴", "期待", "喜欢", "太好了", "兴奋", "满意", "happy", "excited", "glad"],
        "可以更轻快地回应，同时抓住对方真正期待的点继续推进。",
    ),
    (
        "困惑/犹豫",
        ["不知道", "不确定", "纠结", "迷茫", "看不懂", "怎么办", "confused", "unsure"],
        "先复述不确定点，再给出少量清晰选项，帮助对方做下一步判断。",
    ),
    (
        "感谢/亲近",
        ["谢谢", "感谢", "辛苦了", "还好有你", "thank", "thanks"],
        "接住感谢，不要过度客套，可以自然地继续陪伴或收尾。",
    ),
]

EMOTION_RESPONSE_TEMPLATES = {
    "悲伤": [
        "没关系，先别急着责怪自己。现在不如意不代表以后都会这样，我会陪你慢慢把眼前这一点熬过去。",
        "听起来你真的有些难受。先让自己喘口气，事情可以一点点来，总会有变好的时候。",
    ],
    "低落/受伤": [
        "没关系，总会好的。你现在觉得难受是可以被理解的，我们先把最压着你的那一件事说出来。",
        "我听见你有点受伤。先不用马上振作，我在这里陪你慢慢整理。",
    ],
    "焦虑/压力": [
        "先稳一下，不用一次把所有问题都解决。我们先找一个最小的下一步，能做一点就已经很好了。",
        "你现在像是被压力推着走。先深呼吸一下，我陪你把事情拆小。",
    ],
    "生气/不满": [
        "你会不舒服是有原因的。我们先看清楚是哪条边界被碰到了，再决定怎么回应比较合适。",
        "这件事确实容易让人烦。先别急着爆发，我陪你把不满背后的重点说清楚。",
    ],
    "开心/期待": [
        "这听起来很棒。能感觉到你挺期待的，我们可以顺着这个劲头继续往前推进。",
        "真好，这份开心可以先留住。你想接下来把它变成什么具体行动？",
    ],
    "困惑/犹豫": [
        "你现在主要是不确定下一步怎么走。我们先不用急着选，我可以陪你列出两个最可行的方向。",
        "这种纠结很正常。先把你最担心的点说出来，判断会清楚很多。",
    ],
    "感谢/亲近": [
        "不用客气，我很愿意陪你。我们可以继续慢慢来。",
        "收到你的感谢啦。能帮上你一点，我也觉得很好。",
    ],
    "平静/信息性": [
        "我明白了。我会按内容本身来处理，尽量说清楚、说实用。",
        "收到，这段更像是在说明信息。我会先抓重点，再帮你整理下一步。",
    ],
}

EMOTION_ALIASES = {
    "伤心": "悲伤",
    "难过": "悲伤",
    "低落": "低落/受伤",
    "受伤": "低落/受伤",
    "委屈": "低落/受伤",
    "焦虑": "焦虑/压力",
    "压力": "焦虑/压力",
    "紧张": "焦虑/压力",
    "生气": "生气/不满",
    "愤怒": "生气/不满",
    "不满": "生气/不满",
    "开心": "开心/期待",
    "期待": "开心/期待",
    "高兴": "开心/期待",
    "困惑": "困惑/犹豫",
    "犹豫": "困惑/犹豫",
    "迷茫": "困惑/犹豫",
    "感谢": "感谢/亲近",
    "感激": "感谢/亲近",
    "平静": "平静/信息性",
}

EMOTION_LEARNING_THRESHOLD = 3


def analyze_text_emotion(text: str) -> dict:
    """Estimate the emotional tone of text for companion-style replies."""
    normalized = text.strip()
    if not normalized:
        return {"label": "平静/信息性", "confidence": 0.0, "evidence": [], "guidance": "按内容本身回答，保持清楚、温和。"}

    lowered = normalized.lower()
    scores: list[tuple[int, str, list[str], str]] = []
    for label, keywords, guidance in EMOTION_RULES:
        hits = [keyword for keyword in keywords if keyword in lowered]
        if hits:
            scores.append((len(hits), label, hits[:4], guidance))

    if not scores:
        if any(mark in normalized for mark in ["！", "!", "？", "?"]):
            return {
                "label": "情绪较强/需要确认",
                "confidence": 0.35,
                "evidence": [],
                "guidance": "先确认对方的语气和真实意图，再继续分析内容。",
            }
        return {"label": "平静/信息性", "confidence": 0.25, "evidence": [], "guidance": "按内容本身回答，保持清楚、温和。"}

    scores.sort(reverse=True, key=lambda item: item[0])
    count, label, evidence, guidance = scores[0]
    confidence = min(0.9, 0.45 + count * 0.15)
    return {"label": label, "confidence": confidence, "evidence": evidence, "guidance": guidance}


def compute_multimodal_emotion(text: str, typing_metrics: dict | None = None, punctuation: dict | None = None) -> dict:
    """Compute emotion score combining text analysis, typing behavior, and punctuation density."""
    base = analyze_text_emotion(text)
    
    typing = typing_metrics or {}
    punct = punctuation or {}
    
    # Backspace ratio: > 25% suggests anxiety/hesitation
    backspace_ratio = typing.get("backspaces", 0) / max(typing.get("keyCount", 1), 1)
    if backspace_ratio > 0.25:
        base["label"] = "焦虑/犹豫"
        base["confidence"] = min(0.95, base["confidence"] + 0.2)
        base["evidence"] = list(base.get("evidence", [])) + [f"退格率高({backspace_ratio:.1%})"]
    
    # Pauses: > 3 pauses suggests uncertainty
    if typing.get("pauses", 0) > 3:
        base["confidence"] = min(0.95, base["confidence"] + 0.1)
        base["evidence"] = list(base.get("evidence", [])) + [f"输入犹豫({typing['pauses']}次停顿)"]
    
    # Exclamation density: >= 2 per 50 chars suggests strong emotion
    text_len = len(text)
    if text_len > 0:
        excl_density = (punct.get("exclamation", 0) + punct.get("question", 0)) / text_len
        if excl_density >= 0.04:  # >= 2 per 50 chars
            base["label"] = "情绪较强/需要确认"
            base["confidence"] = min(0.95, base["confidence"] + 0.15)
            base["evidence"] = list(base.get("evidence", [])) + [f"标点密度高({excl_density:.1%})"]
    
    # Typing speed: very slow suggests deliberation/struggle
    total_keys = typing.get("keyCount", 0)
    duration_ms = typing.get("totalDuration", 0)
    if total_keys > 5 and duration_ms > 0:
        ms_per_key = duration_ms / total_keys
        if ms_per_key > 2000:  # > 2s per key is very slow
            base["confidence"] = min(0.95, base["confidence"] + 0.1)
            base["evidence"] = list(base.get("evidence", [])) + [f"输入缓慢({ms_per_key:.0f}ms/键)"]
    
    return base


def adjust_personality_warmth(label: str, current_warmth: float) -> float:
    """Adjust warmth based on detected emotion."""
    warm_labels = {"开心", "感激", "依恋", "期待"}
    cold_labels = {"焦虑", "难过", "愤怒", "疲惫", "沮丧", "生气"}
    
    for warm in warm_labels:
        if warm in label:
            return min(100.0, current_warmth + 2.0)
    
    for cold in cold_labels:
        if cold in label:
            return max(0.0, current_warmth - 3.0)
    
    return current_warmth


def normalize_emotion_label(label: str) -> str:
    cleaned = label.strip()
    if not cleaned:
        return "平静/信息性"
    if cleaned in EMOTION_RESPONSE_TEMPLATES:
        return cleaned
    for key, value in EMOTION_ALIASES.items():
        if key in cleaned:
            return value
    for known in EMOTION_RESPONSE_TEMPLATES:
        if known in cleaned or cleaned in known:
            return known
    return cleaned


def learned_emotion_label(text: str, fallback_label: str) -> tuple[str, bool, int]:
    training = load_training()
    best_label = ""
    best_score = 0.0
    support = 0
    for item in training.get("examples", []):
        if item.get("source") not in {"emotion_feedback", "emotion_correction"}:
            continue
        prompt = item.get("prompt", "")
        label = item.get("correct_emotion") or item.get("response", "").replace("这段文字的情感是：", "")
        if not prompt or not label:
            continue
        score = similarity(text, prompt)
        if score > best_score:
            best_score = score
            best_label = label
    if best_label and best_score >= 0.28:
        support = sum(
            1
            for item in training.get("examples", [])
            if item.get("source") in {"emotion_feedback", "emotion_correction"}
            and normalize_emotion_label(item.get("correct_emotion") or item.get("response", "")) == normalize_emotion_label(best_label)
        )
        if support >= EMOTION_LEARNING_THRESHOLD:
            return normalize_emotion_label(best_label), True, support
    return normalize_emotion_label(fallback_label), False, support


def emotion_response_text(text: str) -> str:
    emotion = analyze_text_emotion(text)
    label, learned, support = learned_emotion_label(text, str(emotion.get("label", "")))
    templates = EMOTION_RESPONSE_TEMPLATES.get(label) or EMOTION_RESPONSE_TEMPLATES.get(normalize_emotion_label(label))
    if not templates:
        templates = [str(emotion.get("guidance", "我会先理解这段文字里的感受，再回应具体内容。"))]
    index = abs(hash(text + label)) % len(templates)
    prefix = f"我根据已学习的情感样本判断这是“{label}”（样本支持 {support} 条）。" if learned else f"我先判断这是“{label}”。"
    return f"{prefix}\n{templates[index]}"


def emotion_line(name: str, text: str) -> str:
    emotion = analyze_text_emotion(text)
    evidence = emotion.get("evidence") or []
    evidence_text = f"；触发词：{', '.join(evidence)}" if evidence else ""
    confidence = int(float(emotion.get("confidence", 0)) * 100)
    return (
        f"{name}情感理解：{emotion.get('label')}（置信度约 {confidence}%{evidence_text}）。\n"
        f"回应策略：{emotion.get('guidance')}"
    )


def training_response_text(response: str) -> str:
    """Keep only the user-facing answer when saving feedback as training data."""
    text = strip_learning_record_payload(response).strip()
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

    cleaned = "\n\n".join(kept).strip()
    return cleaned or text


def strip_learning_record_payload(text: str) -> str:
    start = "[[LEARNING_RECORD_JSON]]"
    end = "[[/LEARNING_RECORD_JSON]]"
    raw = str(text or "")
    while start in raw and end in raw:
        start_index = raw.find(start)
        end_index = raw.find(end, start_index)
        if start_index < 0 or end_index < start_index:
            break
        raw = raw[:start_index] + raw[end_index + len(end):]
    return raw


def add_memory(text: str, bucket: str = "facts", source: str = "explicit") -> str:
    result = MEMORY_STORE.add(text, bucket, source=source)
    record = result.get("record") or {}
    if not result.get("created"):
        return "这条内容已经在记忆里，或内容为空。"
    if result.get("superseded"):
        return f"已更新记忆：{record.get('text', '')}（已保留 {result['superseded']} 条旧记录作为历史）"
    return f"已记住：{record.get('text', '')}"


def forget_memory(keyword: str) -> str:
    removed = MEMORY_STORE.forget(keyword)
    return f"已删除 {removed} 条包含“{keyword}”的记忆。"


def _safe_data_child(path: Path) -> Path:
    resolved = path.resolve()
    data_root = DATA_DIR.resolve()
    if resolved != data_root and data_root not in resolved.parents:
        raise RuntimeError(f"拒绝清理数据目录外路径：{resolved}")
    return resolved


def _remove_data_path(path: Path) -> int:
    target = _safe_data_child(path)
    if not target.exists():
        return 0
    if target.is_dir():
        count = sum(1 for item in target.rglob("*") if item.is_file())
        shutil.rmtree(target)
        return count
    target.unlink()
    return 1


def _count_json_items(data: object) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        total = 0
        for value in data.values():
            if isinstance(value, list):
                total += len(value)
            elif isinstance(value, dict):
                total += _count_json_items(value)
        return total
    return 0


def clear_memory() -> dict:
    """Clear all local user-generated data while keeping app/runtime settings."""
    ensure_data()
    details: dict[str, int] = {}

    memory = MEMORY_STORE.load()
    details["long_term_memory"] = sum(len(memory.get(bucket, [])) for bucket in ("profile", "preferences", "facts"))
    empty_memory = {"profile": [], "preferences": [], "facts": []}
    save_memory(empty_memory)

    history_entries = load_history_entries()
    details["chat_history"] = len(history_entries)
    write_sensitive_json(HISTORY_FILE, {"entries": []})

    training = load_training()
    details["training_examples"] = len(training.get("examples", [])) + len(training.get("feedback", []))
    save_training({"examples": [], "feedback": []})

    files = load_files()
    details["uploaded_files"] = len(files.get("files", []))
    save_files({"files": []})
    details["uploaded_file_blobs"] = _remove_data_path(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    moments = load_moments()
    details["moments"] = len(moments.get("posts", []))
    save_moments({"posts": []})

    user_profile = load_user_profile()
    details["user_profile"] = _count_json_items(user_profile.get("buckets", {}))
    clear_user_profile()

    action_store = load_action_store()
    details["action_learning"] = len(action_store.get("skills", [])) + len(action_store.get("evolution", []))
    save_action_store({"skills": [], "evolution": []})

    dialogue_store = load_dialogue_skills()
    details["dialogue_skills"] = len(dialogue_store.get("skills", []))
    save_dialogue_skills({"skills": []})

    voiceprints = load_voiceprints()
    details["voiceprints"] = len(voiceprints.get("prints", []))
    save_voiceprints({"prints": []})

    identity = load_identity()
    details["identity"] = 1 if identity else 0
    save_identity({})
    identity_confirm = load_identity_confirmation()
    details["identity_confirmations"] = _count_json_items(identity_confirm)
    clear_identity_confirmation()

    try:
        routine = load_routine()
        details["routine"] = len(routine.get("events", [])) + len(routine.get("reminders", []))
        reset_routine_encryption_key()
    except Exception:
        details["routine"] = 0

    try:
        emotion = load_emotion()
        details["emotion_days"] = len(emotion.get("days", {}))
        clear_emotion()
    except Exception:
        details["emotion_days"] = 0
    try:
        diary = load_diary()
        details["diary_entries"] = len(diary.get("entries", {}))
        clear_diary()
    except Exception:
        details["diary_entries"] = 0

    growth = load_growth()
    details["growth_events"] = (
        len(growth.get("events", []))
        + len(growth.get("milestones", []))
        + len(growth.get("personality", {}).get("growth_notes", []))
    )
    clear_growth()

    face_encodings = read_sensitive_json(face_manager.ENCODINGS_FILE, {"faces": []})
    face_logs = read_sensitive_json(face_manager.FACE_LOG_FILE, {"logs": []})
    details["face_records"] = len(face_encodings.get("faces", [])) + len(face_logs.get("logs", []))
    details["face_known_images"] = _remove_data_path(face_manager.KNOWN_FACES_DIR)
    face_manager.KNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)
    details["face_temp_images"] = sum(
        _remove_data_path(path)
        for pattern in ("temp_capture_*.jpg", "recognize_capture_*.jpg")
        for path in face_manager.FACE_DIR.glob(pattern)
    )
    write_sensitive_json(face_manager.ENCODINGS_FILE, {"faces": [], "version": 1})
    write_sensitive_json(face_manager.FACE_LOG_FILE, {"logs": []})

    usage_files = [
        IDLE_EXPLORE_FILE,
        DATA_DIR / "learning_history.jsonl",
        DATA_DIR / "audit_results.jsonl",
        DATA_DIR / "audit_summary.json",
    ]
    details["usage_files"] = sum(_remove_data_path(path) for path in usage_files)

    empty_avatar = avatar_state("thinking")
    removed = sum(value for value in details.values() if isinstance(value, int))
    return {
        "ok": True,
        "removed": removed,
        "details": details,
        "memory": empty_memory,
        "avatar": empty_avatar,
    }


def memory_text() -> str:
    return MEMORY_STORE.text_summary()


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


def teach_example(prompt: str, response: str, source: str = "manual", rating: int = 1) -> str:
    prompt = prompt.strip()
    response = response.strip()
    if not prompt or not response:
        return "训练样本需要同时包含问法和回答。格式：/teach 问法 => 回答"
    training = load_training()
    item = {
        "time": int(time.time()),
        "prompt": prompt,
        "response": response,
        "source": source,
        "rating": rating,
    }
    training["examples"].append(item)
    save_training(training)
    sync_teach_example_to_indexes(prompt, response, source)
    try:
        from growth_loop import record_experience
        record_experience(prompt, response, source=f"teach:{source}", evidence_type="human", reward=max(0, rating), evidence="用户通过 /teach 提供")
    except Exception:
        pass
    return f"已学到 1 条本地样本：以后遇到类似“{prompt[:40]}”的问题，我会优先参考这条回答。"


def sync_teach_example_to_indexes(prompt: str, response: str, source: str = "manual") -> None:
    """Make a newly taught Q&A available to already-loaded retrieval indexes."""
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


RULE_TEMPLATE_PRESETS = {
    "fresh_web": {
        "title": "时效联网",
        "triggers": "最新,最近,现在,今年,目前,新进展,新闻,版本,价格",
        "instruction": "先联网搜索并给出来源；如果无法联网，要明确说明没有完成核实。",
    },
    "emotion_first": {
        "title": "情绪优先",
        "triggers": "累,撑不住,烦,难过,焦虑,压力,崩溃,委屈",
        "instruction": "先承认用户的感受，语气放轻，再给一个很小的下一步。",
    },
    "work_conclusion": {
        "title": "工作先结论",
        "triggers": "方案,计划,怎么做,排查,修复,汇报,总结,工作",
        "instruction": "先给结论，再给步骤；步骤保持可执行，避免空泛安慰。",
    },
    "game_observe": {
        "title": "游戏先观察",
        "triggers": "游戏,开局,团战,副本,角色,装备,打不过,怎么赢",
        "instruction": "先询问或观察局势，再给建议；不要在信息不足时直接下判断。",
    },
    "safety_confirm": {
        "title": "高风险先确认",
        "triggers": "删除,清空,覆盖,重置,卸载,付款,购买,自动操作,执行电脑",
        "instruction": "先提醒风险并请求确认；没有明确授权时只提供计划，不执行操作。",
    },
    "screen_understanding": {
        "title": "屏幕理解摘要",
        "triggers": "屏幕,截图,see_screen,观察屏幕,看屏幕,OCR,当前窗口",
        "instruction": "先判断当前场景和用户可能在做什么，再说明可能意图、判断依据和屏幕文字摘录；不要声称看到了 OCR 或窗口信息之外无法确认的细节。",
    },
}


CULTIVATION_PACKS = {
    "companion": {
        "name": "陪伴开局包",
        "description": "快速建立温柔、懂情绪、会记偏好的陪伴风格。",
        "memories": [
            ("preferences", "用户希望回答先有温度，再给可执行的小步骤。"),
            ("preferences", "用户不喜欢空泛鸡汤，更喜欢被认真理解。"),
        ],
        "examples": [
            ("我今天好累", "先别急着逼自己。我们先把今天压着你的事放到桌面上，只挑一个最小的下一步。"),
            ("我有点难过", "我在。你不用马上解释清楚，先把最重的那一小块说出来就好。"),
        ],
        "rules": ["emotion_first", "safety_confirm"],
    },
    "work": {
        "name": "工作助手包",
        "description": "让它更快进入结论优先、拆解任务、保留风险的工作模式。",
        "memories": [
            ("preferences", "用户处理工作问题时希望先看结论，再看步骤和风险。"),
            ("preferences", "用户喜欢可复用的清单、模板和下一步行动。"),
        ],
        "examples": [
            ("帮我整理一个工作计划", "结论：先定目标和验收标准，再拆任务。建议按：目标、当前状态、阻塞、下一步、截止时间来整理。"),
            ("这个问题怎么排查", "先确定复现条件，再看最近变更、日志、输入输出和边界条件。每一步都保留观察结果。"),
        ],
        "rules": ["work_conclusion", "fresh_web", "safety_confirm"],
    },
    "web": {
        "name": "联网学习包",
        "description": "遇到时效信息时自动先核实来源，减少过期知识。",
        "memories": [
            ("preferences", "涉及最新信息、价格、版本、新闻时，用户希望先核实来源。"),
        ],
        "examples": [
            ("最近 AI 有什么新进展", "我会先联网核实，再按来源整理要点；如果无法联网，会明确告诉你未核实。"),
        ],
        "rules": ["fresh_web", "work_conclusion"],
    },
    "game": {
        "name": "游戏陪玩包",
        "description": "先观察局势，再给策略建议，适合陪玩和复盘。",
        "memories": [
            ("preferences", "用户玩游戏时希望 AI 先看局势和目标，再给建议。"),
        ],
        "examples": [
            ("这把怎么打", "我先需要知道局势：你的位置、资源、敌我状态和当前目标。然后我会给一个优先级建议。"),
            ("我一直打不过这个关", "先别急着硬试。我们把失败点分成：伤害不够、机制没处理、走位问题、资源配置四类来查。"),
        ],
        "rules": ["game_observe", "emotion_first", "safety_confirm"],
    },
    "screen": {
        "name": "屏幕理解包",
        "description": "让 /see_screen 默认只总结屏幕可见内容；用户明确问卡点、下一步或建议时才输出诊断。",
        "memories": [
            ("preferences", "用户希望 /see_screen 不只是截图和 OCR，而是给出屏幕理解摘要。"),
            ("preferences", "屏幕观察摘要默认包含当前场景判断、用户可能在做什么、判断依据和屏幕文字摘录；只有用户明确问卡在哪里、下一步或操作建议时，才补充可能意图和操作判断。"),
        ],
        "examples": [
            (
                "帮我看一下当前屏幕",
                "屏幕理解：\n- 当前场景判断：先根据前台窗口标题和可见文字判断，例如编程/调试、聊天协作、网页资料、文档写作、文件管理或设置配置。\n- 用户可能在做什么：概括当前任务。\n- 判断依据：列出窗口标题、关键词和布局线索。\n- 屏幕文字摘录：摘出关键文字，不把 OCR 当成完整事实。",
            ),
            (
                "观察屏幕时不要只给 OCR",
                "我会把截图和 OCR 转成屏幕理解摘要：先判断场景，再推测你可能在做什么和想达成什么，最后给出依据与文字摘录；无法确认的细节会明确保留。",
            ),
        ],
        "rules": ["screen_understanding", "work_conclusion", "safety_confirm"],
    },
}


CULTIVATION_PACK_SAMPLE_TARGET = 1000


CULTIVATION_PACK_SAMPLE_CONTEXTS = [
    "刚开始培养时",
    "用户情绪比较急时",
    "用户只给一句短指令时",
    "用户希望先听结论时",
    "用户需要下一步行动时",
    "用户信息给得不完整时",
    "用户正在复盘时",
    "用户想快速获得建议时",
    "用户需要更细致解释时",
    "用户希望保留不确定性时",
]


CULTIVATION_PACK_SAMPLE_EXPANSIONS = {
    "companion": {
        "prompts": [
            "我今天真的有点累",
            "我不知道该怎么开口",
            "我有点委屈",
            "我现在很焦虑",
            "我感觉自己做得不够好",
            "我想有人陪我待一会儿",
            "我今天心情很乱",
            "我有点撑不住了",
            "我想被认真听一下",
            "我不知道下一步怎么办",
        ],
        "responses": [
            "我在。先不用把所有事一次讲清楚，我们先把最重的那一小块拿出来。",
            "这听起来确实不轻。你可以先慢慢说，我会跟着你的节奏来。",
            "先别急着否定自己。我们先确认发生了什么，再找一个很小的下一步。",
            "你已经撑了一段路了。现在先停一下，把呼吸放慢一点，再处理眼前这一件事。",
            "我会先听你说完，不急着讲道理。你最希望我现在陪你看哪一部分？",
            "这份难受值得被认真对待。我们先把它说具体一点，它就不会只是一团压力。",
            "可以的，我们先不追求马上解决。先把今天最消耗你的地方圈出来。",
            "我听到了。先给自己一点余地，然后我们一起把事情拆到能动手的大小。",
            "你不用一个人硬扛。先告诉我现在最卡住你的点，我陪你一起梳理。",
            "我们先稳住，再往前走。此刻只需要完成一个小动作就够了。",
        ],
    },
    "work": {
        "prompts": [
            "帮我拆一下这个任务",
            "这个方案怎么开始",
            "我需要一个执行计划",
            "这个问题怎么排查",
            "帮我整理汇报重点",
            "我想把流程做清楚",
            "帮我评估一下风险",
            "这件事怎么推进",
            "我需要一个复盘模板",
            "帮我把需求理顺",
        ],
        "responses": [
            "结论：先定义目标和验收标准，再拆任务。建议按目标、现状、阻塞、下一步、负责人来整理。",
            "先把范围收窄到可验证的一步：输入是什么、输出是什么、谁来判断完成。",
            "建议先列三件事：必须完成、可以后置、当前不确定。这样推进会更稳。",
            "排查顺序建议是复现条件、最近变更、日志证据、边界输入、回滚验证。",
            "汇报可以先给结论，再补依据和风险。让对方先知道你要什么决定。",
            "流程先画主路径，再补异常路径。不要一开始就把所有细节混在一起。",
            "风险先按影响和概率排序。高影响且高概率的项，必须有明确预案。",
            "推进建议先定一个最小交付物，让每次沟通都能带着结果往前走。",
            "复盘先写事实，再写判断。把发生了什么和为什么发生分开，会更清楚。",
            "需求先拆成用户目标、约束条件、验收口径和暂不处理的范围。",
        ],
    },
    "web": {
        "prompts": [
            "最近这个事情有什么新进展",
            "帮我查一下最新版本",
            "现在价格是多少",
            "这个新闻可靠吗",
            "今年有什么变化",
            "帮我找来源确认一下",
            "这个政策现在还有效吗",
            "最近大家怎么评价它",
            "这个工具现在推荐吗",
            "帮我核实一下这个说法",
        ],
        "responses": [
            "我会先查最新来源，再把结论、出处和不确定点分开说明。",
            "这类信息可能过期，我会先核实发布日期和官方来源，再给你摘要。",
            "我会优先看官网、公告或权威资料；如果只能找到二手信息，会明确标出来。",
            "先别直接按旧印象判断。我会查证后再告诉你哪些点确定、哪些点还需要保留。",
            "我会按时间线整理：最新结论、关键变化、来源链接和对你的影响。",
            "我会先确认来源可信度，再比较多个结果，避免只看单一页面。",
            "如果无法联网核实，我会明确说未完成核实，并只给基于已有信息的判断。",
            "我会把事实、推测和建议分开写，方便你判断能不能直接采用。",
            "我会先找原始资料，再补充媒体或社区反馈作为参考。",
            "我会检查发布时间、作者或机构、是否有后续更新，再给你结论。",
        ],
    },
    "game": {
        "prompts": [
            "这把怎么打",
            "我这个阵容怎么配",
            "这个关卡一直过不去",
            "现在该推还是该守",
            "我装备怎么选",
            "团战我该站哪里",
            "这个角色怎么玩",
            "我总是输在同一个点",
            "帮我复盘这局",
            "我现在资源不够怎么办",
        ],
        "responses": [
            "先看局势：你的位置、资源、敌我状态和当前目标。确认后再给优先级建议。",
            "不要急着换策略。先判断失败点是输出、防御、机制、节奏还是资源配置。",
            "如果信息不足，我会先问关键条件，再给可执行的打法路线。",
            "先明确胜利条件：保命、控资源、抢节奏还是打爆发。不同目标对应不同操作。",
            "装备选择先看当前瓶颈：伤害不够、站不住、冷却不足还是缺控制。",
            "团战建议先确认你的职责，是开团、保护、收割、控制还是拉扯。",
            "角色玩法先拆成定位、核心技能、强势窗口和常见失误四块。",
            "复盘时先找重复出现的问题。只改一个高频失误，胜率通常会更快提升。",
            "资源不足时先保关键资源，把低收益行动停掉，优先做能改变局面的事。",
            "我会先观察局势，再给短指令；需要细讲时再展开到完整思路。",
        ],
    },
    "screen": {
        "prompts": [
            "帮我看一下当前屏幕",
            "观察屏幕并总结一下",
            "现在屏幕上大概是什么场景",
            "不要只给 OCR，帮我理解屏幕",
            "看一下我可能在做什么",
            "帮我判断当前窗口内容",
            "把屏幕信息整理成摘要",
            "根据屏幕给我下一步建议",
            "帮我提取屏幕里的关键信息",
            "看看这个界面像是在做什么",
        ],
        "responses": [
            "屏幕理解：\n- 当前场景判断：根据窗口标题、可见文字和界面结构判断当前属于哪类任务。\n- 用户可能在做什么：概括正在处理的工作。\n- 可能意图：推测你想要总结、排查、提取信息或获得下一步建议。\n- 判断依据：列出关键词、窗口名和可见控件。\n- 屏幕文字摘录：只摘录 OCR 识别到的关键文本。",
            "我会先把屏幕归类，例如编程/调试、聊天协作、网页资料、文档写作、文件管理或设置配置，再说明依据。",
            "我不会只复述 OCR。会把可见文字、前台应用和画面线索组织成一段可执行的理解摘要。",
            "如果信息不足，我会明确说不确定，并把能确认的依据和无法确认的部分分开。",
            "我会优先回答你可能正在做什么、下一步可能需要什么帮助，再给文字摘录。",
            "屏幕摘要会保持克制：只基于截图、窗口标题和 OCR，不编造看不见的内容。",
            "我会把判断依据写清楚，例如标题、按钮文字、代码片段、错误信息、网页标题或文件名。",
            "看到调试或报错场景时，我会先指出可能卡点，再建议查看日志、复现条件或关键代码位置。",
            "看到资料或网页时，我会先提取主题、来源线索和可用信息，再提醒需要核实时继续查证。",
            "看到聊天或协作文档时，我会先总结对话/文档主题，再提炼待办、问题和可能回复方向。",
        ],
    },
}


def expanded_cultivation_examples(pack_id: str, pack: dict) -> list[tuple[str, str]]:
    examples = list(pack.get("examples", []))
    expansion = CULTIVATION_PACK_SAMPLE_EXPANSIONS.get(pack_id)
    if not expansion:
        return examples
    prompts = expansion["prompts"]
    responses = expansion["responses"]
    for context in CULTIVATION_PACK_SAMPLE_CONTEXTS:
        for prompt in prompts:
            for response in responses:
                examples.append((f"{prompt}（{context}）", f"{response}\n\n场景侧重：{context}"))
                if len(examples) >= CULTIVATION_PACK_SAMPLE_TARGET:
                    return examples
    return examples


QUICK_FEEDBACK_PRESETS = {
    "too_cold": {
        "label": "太冷淡",
        "rule": ("更有温度", "冷淡,不像陪伴,太机械,太官方", "先给一句具体的情绪承接，再继续回答问题。"),
    },
    "too_verbose": {
        "label": "太啰嗦",
        "rule": ("回答更简洁", "太长,啰嗦,废话多,说重点", "先用三句话以内给结论，需要展开时再分步骤。"),
    },
    "comfort_first": {
        "label": "应该先安慰",
        "rule": ("先安慰再建议", "难过,累,压力,焦虑,不开心,撑不住", "先安慰和确认感受，再给建议；不要一上来讲道理。"),
    },
    "search_first": {
        "label": "应该先查资料",
        "rule": ("先查资料", "最新,最近,版本,价格,新闻,今天,今年", "先联网核实并列出来源，再给结论。"),
    },
    "more_proactive": {
        "label": "应该更主动",
        "rule": ("更主动推进", "继续,下一步,然后呢,帮我推进,别停", "回答末尾主动给一个下一步选项或可直接执行的建议。"),
    },
}


def _add_memory_once(bucket: str, text: str) -> bool:
    memory = load_memory()
    existing = {str(item.get("text", "")).strip() for item in memory.get(bucket, [])}
    if text.strip() in existing:
        return False
    add_memory(text, bucket, source="training")
    return True


def _teach_example_once(prompt: str, response: str, source: str) -> bool:
    training = load_training()
    for item in training.get("examples", []):
        if item.get("prompt") == prompt and item.get("response") == response:
            return False
    teach_example(prompt, response, source, 1)
    return True


def _add_rule_once(title: str, triggers: str, instruction: str) -> tuple[bool, str]:
    from procedural_rules import add_procedural_rule, load_procedural_rules

    store = load_procedural_rules()
    for rule in store.get("rules", []):
        if rule.get("title") == title and rule.get("instruction") == instruction:
            return False, str(rule.get("id", ""))
    result = add_procedural_rule(title, triggers, instruction)
    if result.get("ok"):
        return True, str(result.get("rule", {}).get("id", ""))
    return False, ""


def apply_rule_template(template_id: str) -> str:
    key = template_id.strip()
    template = RULE_TEMPLATE_PRESETS.get(key)
    if not template:
        return rule_templates_text()
    added, rule_id = _add_rule_once(template["title"], template["triggers"], template["instruction"])
    state = "已添加" if added else "已存在"
    return (
        f"{state}规则模板「{template['title']}」。\n"
        f"ID：{rule_id or '未生成'}\n"
        f"触发词：{template['triggers']}\n"
        f"动作：{template['instruction']}"
    )


def rule_templates_text() -> str:
    lines = ["规则模板：用 /apply_rule_template 模板ID 一键导入。"]
    for key, template in RULE_TEMPLATE_PRESETS.items():
        lines.append(f"- {key}: {template['title']}｜触发：{template['triggers']}")
    return "\n".join(lines)


def starter_packs_text() -> str:
    lines = ["培养加速器：用 /apply_pack 包ID 一键导入初始记忆、样本和规则。"]
    for key, pack in CULTIVATION_PACKS.items():
        sample_count = len(expanded_cultivation_examples(key, pack))
        lines.append(f"- {key}: {pack['name']}｜{pack['description']}｜样本 {sample_count} 条")
    lines.append("\n一键补齐全部：/apply_pack all")
    lines.append("常用：/apply_pack companion、/apply_pack work、/apply_pack web、/apply_pack game、/apply_pack screen")
    lines.append("规则模板：/rule_templates")
    lines.append("快速反馈：/quick_feedback")
    return "\n".join(lines)


def apply_cultivation_pack(pack_id: str) -> str:
    key = pack_id.strip().lower()
    if key in {"all", "*", "全部"}:
        total_memories = 0
        total_examples = 0
        total_rules = 0
        lines = ["已应用全部培养包。"]
        for pack_key, pack in CULTIVATION_PACKS.items():
            added_memories = 0
            added_examples = 0
            added_rules = 0
            for bucket, text in pack.get("memories", []):
                if _add_memory_once(bucket, text):
                    added_memories += 1
            for prompt, response in expanded_cultivation_examples(pack_key, pack):
                if _teach_example_once(prompt, response, f"starter_pack:{pack_key}"):
                    added_examples += 1
            for rule_key in pack.get("rules", []):
                template = RULE_TEMPLATE_PRESETS.get(rule_key)
                if template:
                    added, _rule_id = _add_rule_once(template["title"], template["triggers"], template["instruction"])
                    if added:
                        added_rules += 1
            total_memories += added_memories
            total_examples += added_examples
            total_rules += added_rules
            lines.append(f"- {pack['name']}：新增记忆 {added_memories} 条，新增样本 {added_examples} 条，新增规则 {added_rules} 条")
        lines.append("")
        lines.append(f"合计新增记忆：{total_memories} 条")
        lines.append(f"合计新增样本：{total_examples} 条")
        lines.append(f"合计新增规则：{total_rules} 条")
        lines.append("\n现在可以用 /training、/training_samples、/memory、/rules 查看效果。")
        return "\n".join(lines)

    pack = CULTIVATION_PACKS.get(key)
    if not pack:
        return starter_packs_text()

    added_memories = 0
    added_examples = 0
    added_rules = 0
    for bucket, text in pack.get("memories", []):
        if _add_memory_once(bucket, text):
            added_memories += 1
    for prompt, response in expanded_cultivation_examples(key, pack):
        if _teach_example_once(prompt, response, f"starter_pack:{key}"):
            added_examples += 1
    for rule_key in pack.get("rules", []):
        template = RULE_TEMPLATE_PRESETS.get(rule_key)
        if template:
            added, _rule_id = _add_rule_once(template["title"], template["triggers"], template["instruction"])
            if added:
                added_rules += 1

    return (
        f"已应用「{pack['name']}」。\n"
        f"新增记忆：{added_memories} 条\n"
        f"新增样本：{added_examples} 条\n"
        f"新增规则：{added_rules} 条\n\n"
        "现在可以用 /training、/memory、/rules 查看效果。"
    )


def quick_feedback_text() -> str:
    lines = ["快速反馈：用 /quick_feedback 反馈ID，把常见纠正一键沉淀成行为规则。"]
    for key, item in QUICK_FEEDBACK_PRESETS.items():
        lines.append(f"- {key}: {item['label']}")
    return "\n".join(lines)


def apply_quick_feedback(feedback_id: str) -> str:
    key = feedback_id.strip().lower()
    item = QUICK_FEEDBACK_PRESETS.get(key)
    if not item:
        return quick_feedback_text()
    title, triggers, instruction = item["rule"]
    added, rule_id = _add_rule_once(title, triggers, instruction)
    state = "已沉淀" if added else "之前已经沉淀过"
    return (
        f"{state}快速反馈「{item['label']}」。\n"
        f"规则：{title}\n"
        f"ID：{rule_id or '已有'}"
    )


import threading
import time

_index_rebuild_timer = None
_index_rebuild_lock = threading.Lock()
_task_status = {"state": "idle", "progress": 0, "total": 0, "message": ""}

def _set_task_status(state: str, message: str, progress: int = 0, total: int = 0) -> None:
    global _task_status
    _task_status = {"state": state, "progress": progress, "total": total, "message": message}

def _clear_task_status_after(delay: float = 5.0) -> None:
    def _clear():
        global _task_status
        if _task_status.get("state") in ("done", "error"):
            _task_status = {"state": "idle", "progress": 0, "total": 0, "message": ""}
    threading.Timer(delay, _clear).start()

def _schedule_index_rebuild(delay: float = 2.0) -> None:
    """Schedule a delayed embedding index rebuild to batch multiple training updates."""
    global _index_rebuild_timer
    
    with _index_rebuild_lock:
        if _index_rebuild_timer:
            _index_rebuild_timer.cancel()
        
        def do_rebuild():
            _set_task_status("rebuilding", "正在重建检索索引...")
            try:
                from hybrid_chat import rebuild_embedding_index
                result = rebuild_embedding_index()
                _set_task_status("done", f"索引重建完成：{result.get('rebuilt', 0)} 条记录，总计 {result.get('total', 0)} 条",
                                 result.get("rebuilt", 0), result.get("total", 0))
                print(f"[index] Auto-rebuilt: {result.get('rebuilt', 0)} records, total: {result.get('total', 0)}")
            except Exception as e:
                _set_task_status("error", f"索引重建失败：{e}")
                print(f"[index] Auto-rebuild failed: {e}")
            _clear_task_status_after(10.0)
        
        _index_rebuild_timer = threading.Timer(delay, do_rebuild)
        _index_rebuild_timer.start()


def get_task_status() -> dict:
    return dict(_task_status)


def record_feedback(prompt: str, response: str, rating: int) -> dict:
    training = load_training()
    cleaned_response = training_response_text(response)
    row = {
        "time": int(time.time()),
        "prompt": prompt.strip(),
        "response": cleaned_response,
        "rating": 1 if rating > 0 else -1,
    }
    training["feedback"].append(row)
    if row["rating"] > 0 and row["prompt"] and row["response"]:
        training["examples"].append({**row, "source": "feedback"})
    save_training(training)
    try:
        from growth_loop import record_experience
        record_experience(row["prompt"], row["response"], source="feedback", evidence_type="user_approved" if row["rating"] > 0 else "", reward=row["rating"], evidence="用户点击回答反馈")
    except Exception:
        pass
    _schedule_index_rebuild()
    return training


def record_correction(prompt: str, wrong_response: str, correct_response: str) -> dict:
    """Record a user correction: the user said the AI response was wrong and provided the expected answer."""
    training = load_training()
    cleaned_wrong_response = training_response_text(wrong_response)
    # Record negative feedback for the wrong response
    training["feedback"].append({
        "time": int(time.time()),
        "prompt": prompt.strip(),
        "response": cleaned_wrong_response,
        "rating": -1,
        "type": "correction",
    })
    # Add the corrected pair as a high-quality training example
    training["examples"].append({
        "time": int(time.time()),
        "prompt": prompt.strip(),
        "response": correct_response.strip(),
        "rating": 1,
        "source": "correction",
        "wrong_response": cleaned_wrong_response,
    })
    save_training(training)
    try:
        from growth_loop import record_experience
        record_experience(prompt, correct_response, source="correction", evidence_type="human", reward=1, evidence="用户提供纠正答案")
    except Exception:
        pass
    _schedule_index_rebuild()
    return training


def record_emotion_feedback(text: str, predicted_emotion: str, rating: int, correct_emotion: str = "") -> dict:
    training = load_training()
    row = {
        "time": int(time.time()),
        "prompt": text.strip(),
        "response": predicted_emotion.strip(),
        "rating": 1 if rating > 0 else -1,
        "type": "emotion_feedback",
    }
    if correct_emotion.strip():
        row["correct_emotion"] = correct_emotion.strip()
    training["feedback"].append(row)
    if row["rating"] > 0 and row["prompt"] and row["response"]:
        training["examples"].append({
            **row,
            "source": "emotion_feedback",
            "response": f"这段文字的情感是：{row['response']}",
        })
    elif row["rating"] < 0 and row["prompt"] and correct_emotion.strip():
        training["examples"].append({
            **row,
            "source": "emotion_correction",
            "response": f"这段文字的情感是：{correct_emotion.strip()}",
            "rating": 1,
        })
    save_training(training)
    return training


def best_training_match(message: str) -> tuple[dict | None, float]:
    training = load_training()
    best: dict | None = None
    best_score = 0.0
    for item in training.get("examples", []):
        if item.get("rating", 1) <= 0:
            continue
        score = similarity(message, item.get("prompt", ""))
        if score > best_score:
            best = item
            best_score = score
    return best, best_score


def training_text() -> str:
    training = load_training()
    examples = training.get("examples", [])
    feedback = training.get("feedback", [])
    positive = sum(1 for x in feedback if x.get("rating", 0) > 0)
    negative = sum(1 for x in feedback if x.get("rating", 0) < 0)
    emotion_feedback = sum(1 for x in feedback if x.get("type") == "emotion_feedback")
    action_skills = len(list_action_skills(limit=100000))
    dialogue_skills = len(load_dialogue_skills().get("skills", []))
    try:
        from procedural_rules import load_procedural_rules
        behavior_rules = len(load_procedural_rules().get("rules", []))
    except Exception:
        behavior_rules = 0
    user_profile = load_user_profile()
    profile_items = sum(len(items) for items in user_profile.get("buckets", {}).values())
    return (
        f"训练样本：{len(examples)} 条\n"
        f"电脑操作技能：{action_skills} 个\n"
        f"对话技能：{dialogue_skills} 个\n"
        f"行为规则：{behavior_rules} 条\n"
        f"用户画像：{'开启' if user_profile.get('enabled', True) else '已暂停'}，{profile_items} 条\n"
        f"正反馈：{positive} 条\n"
        f"负反馈：{negative} 条\n"
        f"情感反馈：{emotion_feedback} 条（同类 {EMOTION_LEARNING_THRESHOLD} 条以上优先参考已学习情感）"
    )


def training_samples_text(limit: int = 20) -> str:
    training = load_training()
    examples = training.get("examples", [])
    if not examples:
        return "训练样本：暂无。\n\n可以用 /teach 问法 => 回答 添加第一条样本。"

    lines = [
        f"训练样本明细：共 {len(examples)} 条，最近 {min(limit, len(examples))} 条",
        "删除样本：/delete_sample 编号",
    ]
    start_no = max(1, len(examples) - limit + 1)
    numbered_items = list(enumerate(examples, 1))[start_no - 1:]
    for sample_no, item in reversed(numbered_items):
        prompt = re.sub(r"\s+", " ", str(item.get("prompt", ""))).strip()
        response = re.sub(r"\s+", " ", str(item.get("response", ""))).strip()
        source = item.get("source", "unknown")
        rating = item.get("rating", 1)
        when = ""
        try:
            ts = int(item.get("time", 0))
            if ts:
                when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            when = ""
        meta = f"来源：{source}；评分：{rating}"
        if when:
            meta += f"；时间：{when}"
        lines.append(
            f"\n#{sample_no}. {meta}\n"
            f"问：{prompt[:220] or '（空）'}\n"
            f"答：{response[:360] or '（空）'}"
        )
    return "\n".join(lines)


def teach_lab_text() -> str:
    return (
        "教学实验室：把“从零教 AI”拆成 9 个可操作练习。\n\n"
        "0. 培养加速\n"
        "   /accelerate\n"
        "   /apply_pack companion\n"
        "   /apply_pack work\n"
        "   /apply_pack screen\n\n"
        "1. 教它一句话\n"
        "   /teach 当我说我很累 => 先安静陪我一下，再帮我把事情拆成一个很小的下一步。\n\n"
        "2. 教它情绪\n"
        "   发送一句真实表达，然后用情感反馈纠正；也可以输入 /emotion 查看情绪追踪。\n\n"
        "3. 教它上网\n"
        "   /learn 人工智能最新进展\n"
        "   /learn_status\n"
        "   /self_study_topic 科技新闻,人工智能,网络安全,健康知识\n\n"
        "4. 教它使用电脑\n"
        "   /learn_action 打开常用项目 => 打开资源管理器；进入 H:\\Project；双击 start.cmd；确认窗口出现\n"
        "   /action_plan 打开常用项目\n\n"
        "5. 让它观察世界\n"
        "   /see_screen、/camera、/vision、/idle_explore_on\n\n"
        "6. 让它学会陪伴你\n"
        "   /remember 我希望你回答时先给结论，再给步骤。\n"
        "   /growth、/profile、/routine\n\n"
        "7. 教它行为规则\n"
        "   /teach_rule 时效联网 => 最新,最近,现在,今年,目前,新进展 => 先联网搜索并给出来源。\n"
        "   /rules\n"
        "   /delete_rule 规则ID\n\n"
        "8. 一键反馈沉淀\n"
        "   /quick_feedback\n"
        "   /quick_feedback too_cold\n"
        "   /quick_feedback search_first\n\n"
        "当前系统会优先做只读观察、示范学习和计划生成；真正自动点击、输入或操控电脑前，需要明确授权、日志、回退和执行后校验。"
    )


def load_idle_explore() -> dict:
    ensure_data()
    try:
        config = json.loads(IDLE_EXPLORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        config = {}
    defaults = {
        "enabled": False,
        "idle_seconds": 180,
        "interval_seconds": 300,
        "max_per_day": 24,
        "screen": True,
        "camera": False,
        "camera_index": 0,
        "last_run": 0,
        "records": [],
    }
    defaults.update(config)
    return defaults


def save_idle_explore(config: dict) -> None:
    ensure_data()
    IDLE_EXPLORE_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def system_idle_seconds() -> int:
    if not _HAS_CTYPES:
        return 0

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    tick = ctypes.windll.kernel32.GetTickCount()
    return max(0, int((tick - info.dwTime) / 1000))


def idle_records_today(config: dict) -> int:
    today = datetime.now().date().isoformat()
    count = 0
    for item in config.get("records", []):
        ts = int(item.get("time", 0))
        if ts and datetime.fromtimestamp(ts).date().isoformat() == today:
            count += 1
    return count


def run_idle_explore_once(reason: str = "idle") -> dict:
    config = load_idle_explore()
    if idle_records_today(config) >= int(config.get("max_per_day", 24)):
        return {"ok": False, "error": "已达到今日闲置探索上限。"}

    observations: list[dict] = []
    if config.get("screen", True):
        screen = observe_screen()
        observations.append({"kind": "screen", "ok": screen.get("ok", False), "file_id": screen.get("file", {}).get("id", ""), "error": screen.get("error", "")})
    if config.get("camera", False):
        camera = observe_camera(int(config.get("camera_index", 0)))
        observations.append({"kind": "camera", "ok": camera.get("ok", False), "file_id": camera.get("file", {}).get("id", ""), "error": camera.get("error", "")})

    ok = any(item.get("ok") for item in observations)
    record = {
        "time": int(time.time()),
        "reason": reason,
        "idle_seconds": system_idle_seconds(),
        "observations": observations,
    }
    records = list(config.get("records", []))
    records.append(record)
    config["records"] = records[-200:]
    config["last_run"] = record["time"]
    save_idle_explore(config)
    return {"ok": ok, "record": record, "config": config}


def idle_explore_status_text() -> str:
    config = load_idle_explore()
    records = config.get("records", [])
    latest = records[-1] if records else None
    lines = [
        "闲置探索状态：",
        f"开关：{'开启' if config.get('enabled') else '关闭'}",
        f"空闲阈值：{config.get('idle_seconds', 180)} 秒",
        f"最小间隔：{config.get('interval_seconds', 300)} 秒",
        f"今日次数：{idle_records_today(config)} / {config.get('max_per_day', 24)}",
        f"当前系统空闲：{system_idle_seconds()} 秒",
        f"探索范围：屏幕={'开' if config.get('screen', True) else '关'}，摄像头={'开' if config.get('camera', False) else '关'}",
    ]
    if latest:
        ok_items = [item for item in latest.get("observations", []) if item.get("ok")]
        lines.append(f"\n最近一次：{datetime.fromtimestamp(latest.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S')}，成功观察 {len(ok_items)} 项")
    lines.append("\n命令：/idle_explore_on、/idle_explore_off、/idle_explore_now、/idle_explore_camera_on")
    return "\n".join(lines)


_idle_explorer_started = False
_routine_tracker_started = False


def idle_explorer_loop() -> None:
    while True:
        try:
            config = load_idle_explore()
            if config.get("enabled"):
                now = int(time.time())
                idle = system_idle_seconds()
                last_run = int(config.get("last_run", 0))
                interval = int(config.get("interval_seconds", 300))
                threshold = int(config.get("idle_seconds", 180))
                if idle >= threshold and now - last_run >= interval:
                    run_idle_explore_once("idle")
        except Exception as exc:
            print(f"[idle-explore] {exc}")
        time.sleep(15)


def start_idle_explorer() -> None:
    global _idle_explorer_started
    if _idle_explorer_started:
        return
    _idle_explorer_started = True
    threading.Thread(target=idle_explorer_loop, daemon=True, name="idle-explorer").start()


def routine_tracker_loop() -> None:
    while True:
        try:
            routine_tick()
        except Exception as exc:
            print(f"[routine] {exc}")
        time.sleep(30)


def start_routine_tracker() -> None:
    global _routine_tracker_started
    if _routine_tracker_started:
        return
    _routine_tracker_started = True
    threading.Thread(target=routine_tracker_loop, daemon=True, name="routine-tracker").start()


def delete_training_sample(sample_number_text: str) -> str:
    training = load_training()
    examples = training.get("examples", [])
    match = re.search(r"\d+", sample_number_text or "")
    if not match:
        return "格式：/delete_sample 编号\n先用 /training_samples 查看编号。"
    sample_no = int(match.group(0))
    if sample_no < 1 or sample_no > len(examples):
        return f"没有这个训练样本编号：{sample_no}。当前样本编号范围是 1-{len(examples)}。"

    removed = examples.pop(sample_no - 1)
    training["examples"] = examples
    save_training(training)
    prompt = re.sub(r"\s+", " ", str(removed.get("prompt", ""))).strip()
    return (
        f"已删除训练样本 #{sample_no}。\n"
        f"问：{prompt[:220] or '（空）'}\n"
        f"剩余训练样本：{len(examples)} 条"
    )


def avatar_state(last_motion: str = "") -> dict:
    training = load_training()
    files = load_files()
    action_skills = list_action_skills(limit=100000)
    examples = [item for item in training.get("examples", []) if item.get("rating", 1) > 0]
    feedback = training.get("feedback", [])
    positive = sum(1 for x in feedback if x.get("rating", 0) > 0)
    file_count = len(files.get("files", []))
    ocr_count = sum(1 for x in files.get("files", []) if "OCR" in x.get("summary", ""))
    motions = [
        {"id": "idle", "name": "待机", "unlocked_by": "默认"},
        {"id": "blink", "name": "眨眼", "unlocked_by": "默认"},
    ]
    unlocks = [
        (1, "nod", "点头", "学到 1 条样本"),
        (3, "happy", "开心", "学到 3 条样本"),
        (5, "thinking", "思考", "学到 5 条样本"),
        (8, "encourage", "鼓励", "学到 8 条样本"),
        (12, "celebrate", "庆祝", "学到 12 条样本"),
    ]
    for threshold, motion_id, name, reason in unlocks:
        if len(examples) >= threshold:
            motions.append({"id": motion_id, "name": name, "unlocked_by": reason})
    if positive >= 3:
        motions.append({"id": "spark", "name": "高反馈", "unlocked_by": "收到 3 次正反馈"})
    if file_count >= 3:
        motions.append({"id": "read", "name": "阅读", "unlocked_by": "查看 3 个文件"})
    if ocr_count >= 1:
        motions.append({"id": "scan", "name": "识图", "unlocked_by": "完成 OCR 图片识别"})
    if len(action_skills) >= 1:
        motions.append({"id": "operate", "name": "操作学习", "unlocked_by": "学到电脑操作示范"})
    live2d_models = sorted(str(path.relative_to(DATA_DIR)) for path in LIVE2D_DIR.rglob("*.model3.json"))
    live2d_state = _live2d_load_state()
    active_live2d = live2d_state.get("active", "")
    live2d_mode = "local-live2d-model-ready" if live2d_models else "procedural-placeholder"
    model3d_state = _3d_load_state()
    active_3d = model3d_state.get("active", "")
    model3d_list = _3d_list_models()
    model3d_mode = "local-3d-model-ready" if model3d_list else "none"
    state = {
        "motions": motions,
        "last_motion": last_motion or load_avatar().get("last_motion", "idle"),
        "stats": {
            "training_examples": len(examples),
            "positive_feedback": positive,
            "file_summaries": file_count,
            "ocr_files": ocr_count,
            "action_skills": len(action_skills),
        },
        "live2d": {
            "mode": live2d_mode,
            "models": live2d_models,
            "active": active_live2d,
            "local_model_hint": "把 Live2D 模型文件放到 data/live2d/ 后，可以在这里接入真实 Cubism 渲染器。",
        },
        "model3d": {
            "mode": model3d_mode,
            "models": [m["path"] for m in model3d_list],
            "active": active_3d,
        },
        "pet_display_mode": _pet_display_load().get("mode", "auto"),
    }
    save_avatar(state)
    return state


def choose_motion(message: str, reply: str) -> str:
    text = message + "\n" + reply
    neural = predict_motion(text)
    if neural.get("ok") and neural.get("confidence", 0) >= 0.45:
        return neural["motion"]
    if any(key in text for key in ["已学到", "生成本地模型包", "完成", "成功"]):
        return "celebrate"
    if any(key in text for key in ["累", "难过", "压力", "撑着"]):
        return "encourage"
    if any(key in text for key in ["文件", "读到", "OCR", "图片"]):
        return "read"
    if any(key in text for key in ["电脑操作", "操作技能", "操作计划", "learn_action", "action_plan", "自我进化"]):
        return "spark"
    if any(key in text for key in ["计划", "怎么做", "思考"]):
        return "thinking"
    if any(key in text for key in ["天气", "时间"]):
        return "nod"
    return "happy" if len(reply) > 80 else "idle"


def build_model_package() -> dict:
    memory = load_memory()
    training = load_training()
    files = load_files()
    action_store = load_action_store()
    try:
        from procedural_rules import load_procedural_rules
        procedural_rule_store = load_procedural_rules()
    except Exception:
        procedural_rule_store = {"rules": []}
    avatar = avatar_state()
    examples = [item for item in training.get("examples", []) if item.get("rating", 1) > 0]
    vocabulary = sorted(set().union(*(tokenize(item.get("prompt", "")) | tokenize(item.get("response", "")) for item in examples)) if examples else set())
    vectors = []
    for item in examples:
        prompt_tokens = sorted(tokenize(item.get("prompt", "")))
        response_tokens = sorted(tokenize(item.get("response", "")))
        vectors.append({
            "prompt": item.get("prompt", ""),
            "response": item.get("response", ""),
            "source": item.get("source", ""),
            "rating": item.get("rating", 1),
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
        })
    feedback = training.get("feedback", [])
    return {
        "format": "companion-local-model",
        "version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runtime": "rule-memory-retrieval-v1",
        "description": "这是可解释的本地陪伴模型包，包含记忆、训练样本、反馈、文件摘要、词表和检索索引；不是神经网络权重文件。",
        "stats": {
            "profile_memories": len(memory.get("profile", [])),
            "preference_memories": len(memory.get("preferences", [])),
            "fact_memories": len(memory.get("facts", [])),
            "training_examples": len(examples),
            "feedback_items": len(feedback),
            "positive_feedback": sum(1 for x in feedback if x.get("rating", 0) > 0),
            "negative_feedback": sum(1 for x in feedback if x.get("rating", 0) < 0),
            "file_summaries": len(files.get("files", [])),
            "action_skills": len(action_store.get("skills", [])),
            "behavior_rules": len(procedural_rule_store.get("rules", [])),
            "evolution_events": len(action_store.get("evolution", [])),
            "vocabulary_size": len(vocabulary),
        },
        "memory": memory,
        "training": training,
        "files": files,
        "action_learning": action_store,
        "behavior_rules": procedural_rule_store,
        "avatar": avatar,
        "neural": neural_status(),
        "vocabulary": vocabulary,
        "retrieval_index": vectors,
    }


def export_model() -> str:
    ensure_data()
    package = build_model_package()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = MODEL_DIR / f"companion_model_{stamp}.json"
    latest = MODEL_DIR / "companion_model_latest.json"
    text = json.dumps(package, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    stats = package["stats"]
    return (
        "已生成本地模型包：\n"
        f"{path}\n\n"
        f"训练样本：{stats['training_examples']} 条\n"
        f"电脑操作技能：{stats['action_skills']} 个\n"
        f"记忆：{stats['profile_memories'] + stats['preference_memories'] + stats['fact_memories']} 条\n"
        f"文件摘要：{stats['file_summaries']} 条\n"
        f"词表：{stats['vocabulary_size']} 个词\n\n"
        "说明：这是当前纯本地系统可加载/备份的可解释模型包，不是神经网络权重。"
    )


# ---------------------------------------------------------------------------
# 本地备份与迁移
# ---------------------------------------------------------------------------

BACKUP_FORMAT = "companion-backup"
BACKUP_FORMAT_VERSION = 1
BACKUP_DIR = DATA_DIR / "backups"
# Transient / non-portable entries that must not be included in a backup.
BACKUP_EXCLUDE_DIRS = {"backups", "updates", "ocr", "runtime"}
BACKUP_EXCLUDE_SUFFIXES = {".pid", ".lock", ".tmp", ".bak"}
BACKUP_EXCLUDE_NAMES = {"lan_token.json", "realtime_chat.json"}


def _backup_excluded(path: Path, data_root: Path) -> bool:
    """Return True if a path must be skipped during backup."""
    try:
        rel = path.relative_to(data_root)
    except ValueError:
        return True
    parts = rel.parts
    if parts and parts[0] in BACKUP_EXCLUDE_DIRS:
        return True
    if path.name in BACKUP_EXCLUDE_NAMES:
        return True
    if path.suffix.lower() in BACKUP_EXCLUDE_SUFFIXES:
        return True
    return False


def create_backup(dest_path: Path | None = None, source_dir: Path | None = None) -> dict:
    """Create a versioned, checksummed backup archive of the user data dir.

    The archive contains a ``manifest.json`` with per-file SHA256 checksums and
    metadata, plus the data files themselves. Transient state (pid files, the
    LAN token, update downloads, the runtime venv, OCR cache) is excluded so
    the package stays portable and safe to restore on a new machine.
    """
    import tarfile
    import io

    if source_dir is None:
        source_dir = DATA_DIR
        ensure_data()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if dest_path is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest_path = BACKUP_DIR / f"companion_backup_{stamp}.tar.gz"
    else:
        source_dir.mkdir(parents=True, exist_ok=True)
        if dest_path is None:
            dest_path = source_dir / "backups" / f"companion_backup_{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict] = []
    for root, dirs, files in os.walk(source_dir):
        # Prune excluded directories in-place for os.walk efficiency.
        dirs[:] = [d for d in dirs if not _backup_excluded(Path(root) / d, source_dir)]
        for name in files:
            fpath = Path(root) / name
            if _backup_excluded(fpath, source_dir):
                continue
            try:
                rel = fpath.relative_to(source_dir).as_posix()
                sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
                size = fpath.stat().st_size
            except Exception:
                continue
            manifest_entries.append({"path": rel, "sha256": sha, "size": size})

    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "app_version": current_app_version(),
        "platform": os.name,
        "file_count": len(manifest_entries),
        "total_size": sum(e["size"] for e in manifest_entries),
        "files": manifest_entries,
    }

    with tarfile.open(dest_path, "w:gz") as tar:
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        info.mtime = time.time()
        tar.addfile(info, io.BytesIO(manifest_bytes))
        for entry in manifest_entries:
            tar.add(str(source_dir / entry["path"]), arcname=entry["path"])

    archive_sha = hashlib.sha256(dest_path.read_bytes()).hexdigest()
    return {
        "ok": True,
        "path": str(dest_path),
        "archive_sha256": archive_sha,
        "archive_size": dest_path.stat().st_size,
        "file_count": manifest["file_count"],
        "total_size": manifest["total_size"],
        "created_at": manifest["created_at"],
    }


def restore_backup(archive_path: Path, target_data_dir: Path | None = None) -> dict:
    """Validate and restore a backup archive into a data directory.

    Files are checksum-verified against the manifest before any write happens.
    If *target_data_dir* is omitted, the current DATA_DIR is used (in-place
    restore). Existing files with the same relative path are overwritten.
    """
    import tarfile
    import tempfile as _tempfile

    if not archive_path.is_file():
        return {"ok": False, "error": "备份文件不存在"}
    dest = target_data_dir or DATA_DIR

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            try:
                manifest_file = tar.extractfile("manifest.json")
            except KeyError:
                return {"ok": False, "error": "备份缺少 manifest.json，可能已损坏"}
            if manifest_file is None:
                return {"ok": False, "error": "无法读取 manifest.json"}
            try:
                manifest = json.loads(manifest_file.read().decode("utf-8"))
            except Exception as exc:
                return {"ok": False, "error": f"manifest 解析失败：{exc}"}

            if manifest.get("format") != BACKUP_FORMAT:
                return {"ok": False, "error": f"不支持的备份格式：{manifest.get('format')}"}
            if int(manifest.get("version") or 0) > BACKUP_FORMAT_VERSION:
                return {"ok": False, "error": "备份版本高于当前程序支持，请升级 Companion AI"}

            # Stage extraction to a temp dir, verify checksums, then move.
            with _tempfile.TemporaryDirectory() as stage:
                stage_path = Path(stage)
                members = [m for m in tar.getmembers() if m.name != "manifest.json"]
                # Safety: reject absolute paths or path traversal.
                for m in members:
                    if m.name.startswith("/") or ".." in Path(m.name).parts:
                        return {"ok": False, "error": f"备份包含不安全路径：{m.name}"}
                tar.extractall(stage_path, members=members)

                # Verify every manifest entry matches its checksum.
                verified = 0
                for entry in manifest.get("files", []):
                    rel = entry["path"]
                    staged = stage_path / rel
                    if not staged.is_file():
                        return {"ok": False, "error": f"备份缺失文件：{rel}", "verified": verified}
                    actual = hashlib.sha256(staged.read_bytes()).hexdigest()
                    if actual != entry["sha256"]:
                        return {"ok": False, "error": f"校验失败：{rel}", "verified": verified}
                    verified += 1

                # All checksums valid — move into the target data dir.
                dest.mkdir(parents=True, exist_ok=True)
                restored = 0
                for entry in manifest.get("files", []):
                    rel = entry["path"]
                    src = stage_path / rel
                    dst = dest / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    restored += 1

    except tarfile.TarError as exc:
        return {"ok": False, "error": f"备份读取失败：{exc}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "restored_files": restored,
        "target_dir": str(dest),
        "backup_created_at": manifest.get("created_at", ""),
        "backup_app_version": manifest.get("app_version", ""),
    }


def infer_weather_location(message: str) -> str:
    cleaned = message.strip()
    for word in ["天气", "气温", "温度", "怎么样", "如何", "现在"]:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?？,，。")
    return cleaned or "Hong Kong"


def ocr_reply(file_record: dict | None) -> str:
    if not file_record:
        return "请先上传一张图片，再输入 /ocr。"
    if file_record.get("kind") != "image":
        return f"《{file_record.get('name', '')}》不是图片文件。"
    stored_name = file_record.get("stored_name", "")
    path = UPLOAD_DIR / stored_name
    if stored_name and path.exists():
        raw = path.read_bytes()
        info = image_info(raw)
        if info:
            fmt, width, height = info
            dims = f"{width} x {height}" if width and height else "尺寸未识别"
            summary = f"图片文件：{fmt}，{dims}，大小 {len(raw)} 字节。\n{ocr_image(path)}"
            file_record = update_file_record(file_record.get("id", ""), summary) or file_record
    summary = file_record.get("summary", "")
    if "OCR" in summary:
        return f"《{file_record.get('name', '')}》的 OCR 结果：\n{summary}"
    return f"《{file_record.get('name', '')}》没有 OCR 结果。"


def source_grounded_web_reply(message: str, rule: dict) -> str:
    try:
        from web_learner import learn_from_web, learning_record_payload
    except Exception as exc:
        return f"联网学习模块不可用：{exc}"

    result = learn_from_web(message[:100])
    if not result.get("ok"):
        return f"联网搜索暂时不可用：{result.get('error', '未知错误')}。你可以稍后重试。"

    # Build a clean, user-friendly reply
    sources = result.get("sources", [])
    source_names = []
    for s in sources[:3]:
        name = s.get("domain") or s.get("title") or "来源"
        source_names.append(name)

    reply = f"我查了一下，找到了 {len(sources)} 个相关来源"
    if source_names:
        reply += f"（{', '.join(source_names[:3])}）"
    reply += "。你可以让我基于这些资料给你整理一个更完整的回答。"

    return reply + "\n" + learning_record_payload(result)


def is_companion_self_reflection_query(message: str) -> bool:
    """Keep personal questions about the companion out of fresh-web routing."""
    text = re.sub(r"\s+", "", str(message or "").lower())
    if not text:
        return False
    refers_to_companion = any(marker in text for marker in ("你", "ai", "助手", "companion", "伙伴"))
    personal_topics = ("学习", "新东西", "能力", "状态", "感受", "心情", "想法", "记得", "成长", "进步")
    return refers_to_companion and any(topic in text for topic in personal_topics)


def preferred_self_training_reply(message: str) -> str:
    """Return a confirmed training reply for a question about the companion itself."""
    if not is_companion_self_reflection_query(message):
        return ""
    match, score = best_training_match(message)
    if not match or score < 0.28:
        return ""
    return training_response_text(str(match.get("response") or ""))


def procedural_rule_reply(message: str) -> str | None:
    try:
        from procedural_rules import match_procedural_rule
    except Exception:
        return None

    rule = match_procedural_rule(message)
    if not rule:
        return None
    if rule.get("action") == "web_search":
        if is_companion_self_reflection_query(message):
            return None
        return source_grounded_web_reply(message, rule)

    instruction = str(rule.get("instruction", "")).strip()
    if instruction:
        return f"好的，我会按你教我的方式来处理。"
    return None


def local_reply(message: str, page: PageResult | None, file_record: dict | None = None, realtime_context: str = "") -> str:
    trained_self_reply = preferred_self_training_reply(message)
    if trained_self_reply:
        return trained_self_reply

    remembered = []
    for bucket, text in extract_memory_candidates(message):
        remembered.append(add_memory(text, bucket, source="auto"))

    parts = []
    if remembered:
        parts.append("我先把这点记下来了：" + "；".join(remembered))

    if message:
        parts.append(emotion_line("这条消息的", message))
        parts.append(emotion_response_text(message))

    # 网页内容
    if page and page.ok:
        summary = page.text[:900]
        parts.append(f"我读到了《{page.title}》。本地摘要如下：\n{summary}")
        parts.append(emotion_line("网页内容的", page.text[:3000]))
    elif page and not page.ok:
        parts.append(page.error)

    # 文件内容
    if file_record:
        file_summary = file_record.get("summary", "")
        parts.append(f"我查看了文件《{file_record.get('name', '')}》。本地分析：\n{file_summary}")
        parts.append(emotion_line("文件内容的", file_summary))

    reality_context = reality_context_text()
    relationship_context = growth_context(identity_configured=is_identity_set())
    api_style_context = external_api_style_context()
    api_personalization_context = external_api_personalization_context()
    memory_context = MEMORY_STORE.context_for(message)

    # Get skill thought from dreaming engine if relevant
    skill_thought = ""
    try:
        from dreaming_engine import get_skill_thought_for
        skill_thought = get_skill_thought_for(message)
    except Exception:
        pass

    # Get user's preferred address
    user_address = ""
    try:
        from user_profile import get_ai_address_to_user
        user_address = get_ai_address_to_user()
    except Exception:
        pass

    try:
        from conversation_audit import get_audit_context_for_chat
        audit_context = get_audit_context_for_chat()
    except Exception:
        audit_context = ""

    context_for_chat = (
        f"{reality_context}\n\n"
        f"{relationship_context}\n\n"
        f"{api_style_context}\n\n"
        f"{api_personalization_context}\n\n"
        f"{memory_context}\n\n"
        "[用户消息]\n"
        f"{message}"
    ).strip()

    if audit_context:
        context_for_chat += f"\n\n[审计反馈]\n{audit_context}"
    if skill_thought:
        context_for_chat += f"\n\n[自我演练思路]\n{skill_thought}"
    if realtime_context:
        context_for_chat += (
            "\n\n[实时感知上下文]\n"
            f"{realtime_context[:2400]}\n"
            "请把这些屏幕/摄像头/人物识别信息当作刚刚观察到的上下文；"
            "回答时自然参考，不要机械复述。"
        )
    if page and page.ok:
        context_for_chat += f"\n\n[已读取网页：{page.title}]\n{page.text[:1800]}"
    if file_record:
        context_for_chat += f"\n\n[已读取文件：{file_record.get('name', '')}]\n{file_record.get('summary', '')[:1200]}"

    rule_reply = procedural_rule_reply(message)
    if rule_reply:
        parts.append(rule_reply)
        return "\n\n".join(parts)

    # 使用混合对话系统
    try:
        from hybrid_chat import hybrid_chat, get_hybrid_chatbot
        
        chatbot = get_hybrid_chatbot()
        if not chatbot.initialized:
            chatbot.initialize()
        
        history = []
        recent = load_history_entries()[-10:]
        for i in range(0, len(recent) - 1, 2):
            user_msg = recent[i]
            asst_msg = recent[i + 1]
            if user_msg.get("role") == "user" and asst_msg.get("role") == "assistant":
                history.append((user_msg.get("content", ""), asst_msg.get("content", "")))
        
        reply, source = hybrid_chat(context_for_chat, history=history[-3:] if history else None)
        
        if reply:
            parts.append(reply)
            return "\n\n".join(parts)
    
    except ImportError:
        pass  # 回退到旧逻辑

    # 回退：优先使用训练样本匹配
    match, score = best_training_match(message)
    if match and score >= 0.28:
        parts.append(f"我参考了你之前教我的相似样本来回答：\n{match.get('response', '')}")
        return "\n\n".join(parts)

    action_skill, action_score = best_action_skill(message)
    if action_skill and action_score >= 0.18:
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(action_skill.get("steps", []), 1))
        parts.append(
            f"我还参考了之前学到的电脑操作示范「{action_skill.get('title', '')}」：\n"
            f"{steps}\n\n"
            "当前我只生成可检查的操作计划；真正控制鼠标键盘需要你明确授权并加执行校验。"
        )
        return "\n\n".join(parts)

    # 规则兜底
    if not parts:
        if "难过" in message or "累" in message or "压力" in message:
            parts.append("听起来你现在有点撑着。我在这儿。你可以先不用把事情讲得很完整，只说最卡住你的那一小块也行。")
        elif "计划" in message or "怎么做" in message:
            parts.append("我们可以把它拆成三步：先定目标，再找最小可行动作，最后留一个复盘点。你把具体事情告诉我，我可以陪你一起拆。")
        else:
            parts.append("我在。你可以继续说，我会记住稳定偏好，也会在需要时帮你整理、总结或一起想下一步。")

    memory = load_memory()
    prefs = [x.get("text", "") for x in memory.get("preferences", [])[-2:]]
    if prefs:
        parts.append("我会参考这些偏好：" + "；".join(prefs))

    return "\n\n".join(parts)


def append_realtime_chat_message(role: str, text: str) -> None:
    clean = str(text or "").strip()
    if not clean:
        return
    try:
        REALTIME_CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(REALTIME_CHAT_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {"messages": []}
        now = time.time()
        msg_id = hashlib.sha1(f"{now}:{role}:{clean}".encode("utf-8")).hexdigest()[:16]
        messages = list(data.get("messages", []))
        messages.append({
            "id": msg_id,
            "time": now,
            "role": role if role in {"user", "assistant", "system"} else "system",
            "text": clean[:1200],
        })
        data["messages"] = messages[-80:]
        temp = REALTIME_CHAT_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(REALTIME_CHAT_FILE)
    except Exception:
        pass


def handle_chat(payload: dict) -> dict:
    message = str(payload.get("message", "")).strip()
    url = str(payload.get("url", "")).strip()
    file_id = str(payload.get("file_id", "")).strip()
    conversation_id = str(payload.get("conversation_id", "")).strip()
    from_realtime = bool(payload.get("from_realtime"))
    persist_history = str(payload.get("persist_history", True)).strip().lower() not in {"0", "false", "no", "off"}
    realtime_context = str(payload.get("realtime_context", "")).strip()
    typing_metrics = payload.get("typing_metrics", {})
    punctuation = payload.get("punctuation", {})
    user_message = message
    file_record = get_file_record(file_id)

    # Notify dreaming engine of user activity
    try:
        from dreaming_engine import touch_chat_activity
        touch_chat_activity()
    except Exception:
        pass

    # Record chat turn for proactive engagement
    try:
        from proactive_engagement import record_chat_turn
        record_chat_turn()
    except Exception:
        pass

    # Check for dream-engine showoff messages
    showoff_prefix = ""
    try:
        from dreaming_engine import consume_showoffs
        showoffs = consume_showoffs()
        if showoffs:
            showoff_prefix = "\n\n".join(showoffs) + "\n\n---\n\n"
    except Exception:
        pass

    # Get user's preferred address
    user_address = ""
    try:
        from user_profile import get_ai_address_to_user
        user_address = get_ai_address_to_user()
    except Exception:
        pass

    if not message and not url and not file_record:
        return {"reply": showoff_prefix + "你可以先说一句话，贴一个你有权访问的网页链接，或上传一个本地文件。"}

    if persist_history:
        append_history("user", user_message or f"[url]{url}" or f"[file]{file_id}")
        record_emotion_message("user", user_message)
    if from_realtime and user_message:
        append_realtime_chat_message("user", user_message)

    # -- plugin commands get first chance --
    plugin_result = plugin_mgr.handle_message(user_message)
    if plugin_result and "reply" in plugin_result:
        reply = plugin_result["reply"]
        recent_chats = []
        if persist_history:
            append_history("assistant", reply)
            record_emotion_message("assistant", reply)
            conversation_id, recent_chats = upsert_recent_chat(conversation_id, user_message or f"[url]{url}" or f"[file]{file_id}", reply)
        if from_realtime:
            append_realtime_chat_message("assistant", training_response_text(reply))
        return {
            "reply": reply,
            "conversation_id": conversation_id,
            "recent_chats": recent_chats,
            "memory": load_memory(),
            "training": load_training(),
            "files": load_files(),
            "avatar": avatar_state(choose_motion(user_message, reply)),
            "growth": growth_payload(),
        }

    lastEmotion = ""
    try:
        multimodal_emotion = compute_multimodal_emotion(user_message, typing_metrics, punctuation)
        lastEmotion = multimodal_emotion.get("label", "")
    except Exception:
        pass

    memory_transfer_reply = handle_memory_transfer_command(user_message)
    if memory_transfer_reply is not None:
        reply = memory_transfer_reply
    elif user_message.startswith("/remember "):
        reply = add_memory(user_message.removeprefix("/remember ").strip(), "facts")
    elif user_message == "/memory":
        reply = memory_text()
    elif message in {"/profile", "/profile_on", "/profile_off", "/profile_clear"} or message.startswith("/name "):
        reply = handle_profile_command(message) or profile_summary()
    elif message in {"/routine", "/routine_status", "/routine_security", "/routine_reset_key", "/routine_on", "/routine_off", "/routine_summary", "/routine_reminders_on", "/routine_reminders_off", "/routine_pop", "/startup_on", "/startup_off"}:
        reply = handle_routine_command(message) or routine_status_text()
    elif message in {"/emotion", "/emotion_on", "/emotion_off", "/emotion_clear", "/diary", "/diary_gen", "/diary_clear"}:
        reply = handle_emotion_diary_command(message) or emotion_summary_text()
    elif message in {"/skills", "/dialogue_skills"} or message.startswith("/learn_skill ") or message.startswith("/learn_dialog_skill ") or message.startswith("/delete_skill ") or message.startswith("/delete_dialog_skill "):
        reply = handle_dialogue_skill_command(message) or list_dialogue_skills_text()
    elif message in {"/growth", "/relationship", "/personality", "/events", "/growth_clear"} or message.startswith("/relationship ") or message.startswith("/feedback "):
        reply = handle_growth_command(message) or growth_status_text()
        if message in {"/growth", "/relationship", "/personality"} and not is_identity_set():
            reply = "角色还没有设置；下面是聊天自动成长记录，不是已确认的人设。\n\n" + reply
    elif message in {"/moments", "/moment"}:
        posts = load_moments().get("posts", [])
        if not posts:
            reply = "AI朋友圈还没有动态。可以点左侧“AI发一条”，或输入 /moment_gen 生成第一条。"
        else:
            lines = ["AI朋友圈最近动态："]
            for post in posts[-5:][::-1]:
                stamp = str(post.get("created_at") or "").replace("T", " ")[:16]
                mood = f" · {post.get('mood')}" if post.get("mood") else ""
                lines.append(f"- {stamp}{mood}\n  {post.get('content', '')}")
            reply = "\n".join(lines)
    elif message in {"/moment_gen", "/moments_gen"}:
        result = generate_ai_moment()
        reply = "已发到 AI朋友圈：\n" + result.get("post", {}).get("content", "") if result.get("ok") else result.get("error", "生成动态失败。")
    elif message.startswith("/moment "):
        result = create_moment(message.removeprefix("/moment ").strip())
        reply = "已发到 AI朋友圈。" if result.get("ok") else result.get("error", "发布失败。")
    elif message in {"/accelerate", "/starter_packs", "/packs"}:
        reply = starter_packs_text()
    elif message.startswith("/apply_pack ") or message.startswith("/pack "):
        body = message.split(maxsplit=1)[1] if len(message.split(maxsplit=1)) > 1 else ""
        reply = apply_cultivation_pack(body)
    elif message in {"/rule_templates", "/rules_template"}:
        reply = rule_templates_text()
    elif message.startswith("/apply_rule_template ") or message.startswith("/rule_template "):
        body = message.split(maxsplit=1)[1] if len(message.split(maxsplit=1)) > 1 else ""
        reply = apply_rule_template(body)
    elif message in {"/quick_feedback", "/feedback_templates"}:
        reply = quick_feedback_text()
    elif message.startswith("/quick_feedback "):
        body = message.split(maxsplit=1)[1] if len(message.split(maxsplit=1)) > 1 else ""
        reply = apply_quick_feedback(body)
    elif message == "/training":
        reply = training_text()
    elif message == "/teach_lab":
        reply = teach_lab_text()
    elif message == "/training_samples" or message == "/samples":
        reply = training_samples_text()
    elif message.startswith("/delete_sample ") or message.startswith("/delete_training_sample "):
        body = message.split(maxsplit=1)[1] if len(message.split(maxsplit=1)) > 1 else ""
        reply = delete_training_sample(body)
    elif message == "/vision":
        reply = vision_status_text()
    elif message == "/idle_explore" or message == "/idle_explore_status":
        reply = idle_explore_status_text()
    elif message == "/idle_explore_on":
        config = load_idle_explore()
        config["enabled"] = True
        save_idle_explore(config)
        reply = idle_explore_status_text() + "\n\n已开启：闲置时会只读观察屏幕，不会点击、输入或打开文件。"
    elif message == "/idle_explore_off":
        config = load_idle_explore()
        config["enabled"] = False
        save_idle_explore(config)
        reply = "已关闭闲置探索。"
    elif message == "/idle_explore_now":
        result = run_idle_explore_once("manual")
        if result.get("ok"):
            reply = "已执行一次只读探索。\n\n" + vision_status_text()
        else:
            reply = result.get("error", "闲置探索失败。")
    elif message == "/idle_explore_camera_on":
        config = load_idle_explore()
        config["camera"] = True
        save_idle_explore(config)
        reply = idle_explore_status_text() + "\n\n已允许闲置探索抓拍摄像头；需要 OpenCV 和系统摄像头权限。"
    elif message == "/idle_explore_camera_off":
        config = load_idle_explore()
        config["camera"] = False
        save_idle_explore(config)
        reply = idle_explore_status_text() + "\n\n已关闭闲置摄像头观察。"
    elif message == "/context":
        reply = context_status_text()
    elif message == "/identity_confirm":
        data = load_identity_confirmation()
        current = data.get("current")
        if current:
            reply = (
                "当前身份确认：\n"
                f"名称：{current.get('name')}\n"
                f"方式：{current.get('method')}\n"
                f"置信度：{int(float(current.get('confidence', 0) or 0) * 100)}%\n"
                f"时间：{current.get('confirmed_at')}\n\n"
                "命令：/identity_clear 清除当前确认。"
            )
        else:
            reply = "当前没有身份确认。可以用 /face_recognize 或设置里的声纹识别来确认。"
    elif message == "/identity_clear":
        clear_identity_confirmation()
        reply = "已清除当前身份确认。"
    elif message == "/see_screen" or message.startswith("/see_screen "):
        mode = screen_observation_mode_hint(message.removeprefix("/see_screen").strip())
        result = observe_screen(mode)
        if result.get("ok"):
            reply = result.get("reply", "已完成屏幕视觉观察。")
        else:
            reply = result.get("error", "屏幕视觉观察失败。")
    elif message == "/camera" or message.startswith("/camera ") or message == "/see_camera" or "看摄像头" in message or "打开摄像头" in message:
        camera_index = 0
        if message.startswith("/camera "):
            try:
                camera_index = max(0, int(message.split(maxsplit=1)[1].strip()))
            except ValueError:
                camera_index = 0
        result = observe_camera(camera_index)
        if result.get("ok"):
            reply = result.get("reply", "已完成摄像头视觉观察。")
        else:
            reply = result.get("error", "摄像头视觉观察失败。")
    # ---- Face recognition commands ----
    elif message == "/face_status":
        reply = face_manager.face_status_text()
    elif message == "/face_install":
        reply = face_manager.install_face_recognition_portable()
    elif message == "/face_list" or message == "/faces":
        faces = face_manager.list_registered_faces()
        if not faces:
            reply = "尚未注册任何人脸。\n\n使用 /face_register 名字 从摄像头注册人脸。"
        else:
            lines = ["已注册人脸："]
            for f in faces:
                reg_time = f.get("registered_at", "")
                if reg_time:
                    try:
                        dt = datetime.fromisoformat(reg_time)
                        reg_time = dt.strftime("%m-%d %H:%M")
                    except Exception:
                        pass
                lines.append(f"  • {f.get('name', '未知')} (ID: {f.get('id', '')[:12]}...，注册于 {reg_time})")
            lines.append(f"\n共 {len(faces)} 张人脸")
            lines.append("\n命令：/face_register 名字、/face_delete ID、/face_recognize")
            reply = "\n".join(lines)
    elif message.startswith("/face_register ") or message.startswith("/register_face ") or message.startswith("/add_face "):
        name = message.split(maxsplit=1)[1].strip() if " " in message else ""
        if not name:
            reply = "格式：/face_register 名字\n\n请提供要注册的人脸名称。"
        else:
            result = face_manager.register_face_from_camera(name)
            if result.get("ok"):
                reply = (
                    f" 人脸注册成功：{result.get('name')}\n"
                    f"ID：{result.get('face_id')}\n\n"
                    "现在可以用 /face_recognize 识别这个人的脸部。"
                )
            else:
                reply = f" 人脸注册失败：{result.get('error', '未知错误')}\n\n{result.get('message', '')}"
    elif message.startswith("/face_register_from ") or message.startswith("/register_face_from "):
        # Register face from uploaded image
        parts = message.split(maxsplit=2)
        if len(parts) < 3:
            reply = "格式：/face_register_from 文件ID 名字\n\n请先上传图片，然后用文件ID注册人脸。"
        else:
            file_id = parts[1].strip()
            name = parts[2].strip()
            # Find uploaded image
            image_path = None
            for item in list_uploaded_files():
                if item.get("id") == file_id or item.get("stored_name", "").startswith(file_id):
                    image_path = UPLOAD_DIR / item.get("stored_name", "")
                    break
            if not image_path or not image_path.exists():
                reply = f"未找到上传文件：{file_id}\n\n请先上传包含人脸的图片。"
            else:
                result = face_manager.register_face_from_image(image_path, name)
                if result.get("ok"):
                    reply = f" 人脸注册成功：{result.get('name')}\nID：{result.get('face_id')}"
                else:
                    reply = f" 人脸注册失败：{result.get('error', '未知错误')}"
    elif message == "/face_recognize" or message == "/recognize_faces" or message == "识别人脸" in message:
        result = face_manager.recognize_from_camera()
        record_face_confirmation_from_result(result)
        if result.get("ok"):
            faces = result.get("faces", [])
            if not faces:
                reply = "摄像头画面中未检测到人脸。"
            else:
                known = [f for f in faces if f.get("known")]
                unknown = [f for f in faces if not f.get("known")]
                lines = [f"识别结果：共 {len(faces)} 张人脸"]
                if known:
                    lines.append(f"已知人脸 ({len(known)})：")
                    for f in known:
                        lines.append(f"  • {f.get('name')} (置信度: {f.get('confidence', 0):.2f})")
                if unknown:
                    lines.append(f"未知人脸 ({len(unknown)})：")
                    for f in unknown:
                        lines.append(f"  • 未知人脸")
                lines.append("\n记录已保存到人脸识别日志。")
                confirmed = result.get("identity_confirmed")
                if confirmed:
                    lines.append(f"已确认当前对话身份：{confirmed.get('name')}（人脸，{float(confirmed.get('confidence', 0) or 0):.2f}）")
                reply = "\n".join(lines)
        else:
            reply = f"人脸识别失败：{result.get('error', '未知错误')}\n\n{result.get('message', '')}"
    elif message.startswith("/face_recognize_from ") or message.startswith("/recognize_from "):
        # Recognize faces from uploaded image
        file_id = message.split(maxsplit=1)[1].strip()
        image_path = None
        for item in list_uploaded_files():
            if item.get("id") == file_id or item.get("stored_name", "").startswith(file_id):
                image_path = UPLOAD_DIR / item.get("stored_name", "")
                break
        if not image_path or not image_path.exists():
            reply = f"未找到上传文件：{file_id}"
        else:
            result = face_manager.recognize_faces_in_image(image_path)
            record_face_confirmation_from_result(result)
            if result.get("ok"):
                faces = result.get("faces", [])
                if not faces:
                    reply = "图片中未检测到人脸。"
                else:
                    known_names = [f.get("name") for f in faces if f.get("known")]
                    reply = f"识别到 {len(faces)} 张人脸，已知：{', '.join(known_names) or '无'}，未知：{result.get('unknown_count', 0)} 张"
                    confirmed = result.get("identity_confirmed")
                    if confirmed:
                        reply += f"\n已确认当前对话身份：{confirmed.get('name')}（人脸，{float(confirmed.get('confidence', 0) or 0):.2f}）"
            else:
                reply = f"人脸识别失败：{result.get('error', '未知错误')}"
    elif message.startswith("/face_delete ") or message.startswith("/delete_face "):
        face_id = message.split(maxsplit=1)[1].strip()
        result = face_manager.delete_face(face_id)
        if result.get("ok"):
            clear_identity_confirmation_if_source("face", face_id)
            reply = result.get("message", "人脸已删除")
        else:
            reply = result.get("error", "删除失败")
    elif message.startswith("/face_rename "):
        # Format: /face_rename face_id new_name
        parts = message.split(maxsplit=2)
        if len(parts) < 3:
            reply = "格式：/face_rename 人脸ID 新名字"
        else:
            face_id = parts[1].strip()
            new_name = parts[2].strip()
            result = face_manager.update_face_name(face_id, new_name)
            if result.get("ok"):
                reply = result.get("message", "人脸名称已更新")
            else:
                reply = result.get("error", "更新失败")
    elif message == "/face_log":
        logs = face_manager.get_face_log(20)
        if not logs:
            reply = "人脸识别日志为空。\n\n使用 /face_recognize 后会记录识别结果。"
        else:
            lines = ["人脸识别日志（最近 20 条）："]
            for log in logs[-20:]:
                log_time = log.get("time", "")
                try:
                    dt = datetime.fromisoformat(log_time)
                    log_time = dt.strftime("%m-%d %H:%M")
                except Exception:
                    pass
                event_type = log.get("type", "unknown")
                if event_type == "recognize":
                    names = log.get("names", [])
                    total = log.get("total", 0)
                    known = log.get("known", 0)
                    lines.append(f"  [{log_time}] 识别：{total} 张人脸，已知 {known} 张 ({', '.join(names) or '无'})")
                elif event_type == "register":
                    lines.append(f"  [{log_time}] 注册：{log.get('name', '')}")
                elif event_type == "delete":
                    lines.append(f"  [{log_time}] 删除：{log.get('name', '')}")
                elif event_type == "update":
                    lines.append(f"  [{log_time}] 更新：{log.get('old_name', '')} → {log.get('new_name', '')}")
                else:
                    lines.append(f"  [{log_time}] {event_type}")
            reply = "\n".join(lines)
    elif message == "/face_log_clear":
        result = face_manager.clear_face_log()
        reply = result.get("message", "人脸识别日志已清空")
    elif message == "/face_detect" or message == "检测人脸" in message:
        # Just detect faces without recognition
        result = face_manager.recognize_from_camera()
        if result.get("ok"):
            faces = result.get("faces", [])
            reply = f"检测到 {len(faces)} 张人脸。\n\n使用 /face_recognize 进行身份识别。"
        else:
            reply = f"人脸检测失败：{result.get('error', '未知错误')}"
    elif message.startswith("/live2d_import_path "):
        result = import_live2d_zip_path(message.removeprefix("/live2d_import_path ").strip())
        if result.get("ok"):
            reply = (
                f"Live2D 模型已导入并设为当前使用：{result.get('model')}\n"
                f"模型文件：{result.get('active') or '未找到 .model3.json'}\n"
                f"解压文件：{result.get('extracted', 0)} 个\n"
                "网页和桌宠都会读取这个当前 Live2D 状态。"
            )
        else:
            reply = result.get("error", "Live2D 导入失败。")
    elif message.startswith("/3d_import_path "):
        result = import_3d_zip_path(message.removeprefix("/3d_import_path ").strip())
        if result.get("ok"):
            reply = (
                f"3D 模型已导入并设为当前使用：{result.get('model')}\n"
                f"模型文件：{result.get('active') or '未找到支持的 3D 模型文件'}\n"
                f"格式：{result.get('format', 'unknown')}\n"
                f"解压文件：{result.get('extracted', 0)} 个"
            )
        else:
            reply = result.get("error", "3D 导入失败。")
    elif message == "/actions" or message == "/action_status":
        reply = action_status_text()
    elif message == "/evolve":
        reply = evolution_summary()
    elif message.startswith("/learn_action "):
        body = message.removeprefix("/learn_action ").strip()
        if "=>" in body:
            title, demo = body.split("=>", 1)
            result = learn_action_skill(title, demo)
            if result.get("ok"):
                skill = result["skill"]
                reply = (
                    f"已学到电脑操作技能「{skill['title']}」：{len(skill['steps'])} 步。\n"
                    f"技能 ID：{skill['id']}\n"
                    "我会先用它生成操作计划，不会默认控制鼠标键盘。"
                )
            else:
                reply = result.get("error", "学习失败")
        else:
            reply = "格式：/learn_action 技能名 => 第一步；第二步；第三步"
    elif message.startswith("/action_plan "):
        reply = action_plan_text(message.removeprefix("/action_plan ").strip())
    elif message.startswith("/action_done "):
        body = message.removeprefix("/action_done ").strip()
        parts = body.split(maxsplit=1)
        skill_id = parts[0] if parts else ""
        note = parts[1] if len(parts) > 1 else ""
        ok = record_action_outcome(skill_id, True, note)
        reply = "已记录这次操作成功，会作为进化反馈。" if ok else f"没有找到技能 ID：{skill_id}"
    elif message.startswith("/action_fail "):
        body = message.removeprefix("/action_fail ").strip()
        parts = body.split(maxsplit=1)
        skill_id = parts[0] if parts else ""
        note = parts[1] if len(parts) > 1 else ""
        ok = record_action_outcome(skill_id, False, note)
        reply = "已记录这次操作失败；下次生成计划时会保留这条修正线索。" if ok else f"没有找到技能 ID：{skill_id}"
    elif message == "/neural":
        reply = neural_status_text()
    elif message == "/train_neural":
        result = train_motion_net()
        if result.get("ok"):
            reply = (
                "神经网络训练完成：\n"
                f"设备：{result['device']}\n"
                f"CUDA：{result['cuda']}\n"
                f"DirectML：{result.get('directml', False)}\n"
                f"样本：{result['examples']} 条\n"
                f"词表：{result['vocab_size']} 个词\n"
                f"loss：{result['loss']}\n"
                f"模型：{result['model']}"
            )
        else:
            reply = (
                "神经网络暂时不能训练。\n"
                f"原因：{result.get('runtime_error') or result.get('error') or '组件虚拟环境中的 PyTorch 不可用'}\n"
                "当前设计已经支持 GPU：NVIDIA 可用 CUDA，AMD/Intel Windows 显卡可用 torch-directml。\n"
                "建议用安装器自动创建 Python 3.12 .venv 并安装对应后端。"
            )
    elif message == "/gpu_check":
        result = gpu_self_check_isolated()
        if result.get("ok"):
            torch_data = result.get("torch", {})
            reply = (
                "GPU 隔离自检通过：\n"
                f"设备：{result.get('device', '')}\n"
                f"PyTorch：{torch_data.get('torch_version', '')}\n"
                f"ROCm/HIP：{torch_data.get('hip_runtime', False)}\n"
                f"GPU：{torch_data.get('cuda_device', '') or '未报告'}\n"
                f"测试值：{result.get('value')}"
            )
        else:
            reply = (
                "GPU 隔离自检失败，但主服务仍然稳定：\n"
                f"{result.get('error', '未知错误')}\n"
                f"退出码：{result.get('returncode', '')}\n"
                f"{result.get('stderr') or result.get('stdout') or ''}"
            ).strip()
    elif message == "/train_neural_gpu":
        result = train_motion_net_gpu_isolated()
        if result.get("ok"):
            reply = (
                "GPU 隔离训练完成：\n"
                f"设备：{result.get('device')}\n"
                f"CUDA：{result.get('cuda')}\n"
                f"DirectML：{result.get('directml', False)}\n"
                f"样本：{result.get('examples')} 条\n"
                f"词表：{result.get('vocab_size')} 个词\n"
                f"loss：{result.get('loss')}\n"
                f"模型：{result.get('model')}"
            )
        else:
            reply = (
                "GPU 隔离训练失败，已保护主服务不崩溃：\n"
                f"{result.get('error', '未知错误')}\n"
                f"退出码：{result.get('returncode', '')}\n"
                f"{result.get('stderr') or result.get('stdout') or ''}\n\n"
                "可以继续使用 /train_neural 走 CPU 稳定训练。"
            ).strip()
    elif message.startswith("/train_dataset "):
        dataset_key = message.removeprefix("/train_dataset ").strip()
        try:
            from dataset_loader import load_dataset_from_config
            config_path = ROOT / "train_config.json"
            ds_config = None
            model_tag = dataset_key
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                ds_config = config.get("datasets", {}).get(dataset_key)
            if ds_config is None:
                # 配置中找不到，尝试直接从 HuggingFace/ModelScope 加载
                dataset_id = dataset_key
                source = "huggingface"
                # 检测前缀：hf: / ms: / modelscope: / hf/ / ms/
                lower_key = dataset_key.lower()
                if lower_key.startswith("hf:") or lower_key.startswith("hf/"):
                    source = "huggingface"
                    dataset_id = dataset_key[3:].strip()
                elif lower_key.startswith("ms:") or lower_key.startswith("ms/"):
                    source = "modelscope"
                    dataset_id = dataset_key[3:].strip()
                elif lower_key.startswith("modelscope:") or lower_key.startswith("modelscope/"):
                    source = "modelscope"
                    dataset_id = dataset_key[11:].strip()
                elif "/" in dataset_key:
                    # 包含 / 的通常是 HuggingFace 或 ModelScope 数据集ID
                    # 默认按 HuggingFace 处理，用户可用 ms: 前缀指定 ModelScope
                    source = "huggingface"
                    dataset_id = dataset_key
                ds_config = {
                    "source": source,
                    "dataset_id": dataset_id,
                    "split": "train",
                }
                model_tag = dataset_id.replace("/", "_").replace(":", "_")
            examples = load_dataset_from_config(ds_config)
            result = train_from_dataset(dataset_examples=examples, model_tag=model_tag)
            if result.get("ok"):
                reply = (
                    f"数据集训练完成 ({model_tag})：\n"
                    f"加载样本：{result['loaded_samples']} 条\n"
                    f"有效训练：{result['examples']} 条\n"
                    f"标签({result['label_count']})：{', '.join(result['labels'][:10])}\n"
                    f"设备：{result['device']}\n"
                    f"训练轮数：{result['epochs_trained']}\n"
                    f"loss：{result['loss']}"
                )
            else:
                reply = f"训练失败: {result.get('error', '未知错误')}"
        except ImportError as exc:
            from dependency_utils import DATASET_INSTALL_CMD
            reply = f"缺少依赖: {exc}\n请安装: {DATASET_INSTALL_CMD}"
        except Exception as exc:
            reply = f"训练出错: {exc}"
    elif message == "/datasets":
        try:
            from dataset_loader import list_available_datasets
            lines = ["可用数据集："]
            for ds in list_available_datasets():
                lines.append(f"  [{ds['source']}] {ds['id']}: {ds['description']}")
            config_path = ROOT / "train_config.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if config.get("datasets"):
                    lines.append("\n已配置的数据集:")
                    for key, ds in config["datasets"].items():
                        lines.append(f"  {key}: {ds.get('description', ds.get('dataset_id', '?'))}")
            lines.append("\n用法示例:")
            lines.append("  /train_dataset emotion_en          ← 使用配置中的数据集")
            lines.append("  /train_dataset hf:emotion          ← 直接从 HuggingFace 加载")
            lines.append("  /train_dataset ms:<ModelScope 数据集 ID>  ← 直接从 ModelScope 加载")
            lines.append("  /train_dataset hf:<HuggingFace 数据集 ID> ← 直接从 HuggingFace 加载")
            reply = "\n".join(lines)
        except Exception as exc:
            reply = f"加载失败: {exc}"
    elif message in {"/api_llm", "/api_llm_status", "/remote_llm", "/remote_llm_status", "/api_llm_on", "/api_llm_off"} or message.startswith("/api_llm_config ") or message.startswith("/api_llm_hybrid "):
        try:
            from remote_llm import handle_remote_llm_command
            reply = handle_remote_llm_command(message) or "未知大模型接口命令。"
        except Exception as exc:
            reply = f"大模型接口命令失败: {exc}"
    elif message in {"/rules", "/procedural_rules", "/teach_rules"} or message.startswith("/teach_rule ") or message.startswith("/learn_rule ") or message.startswith("/delete_rule ") or message.startswith("/delete_procedural_rule "):
        try:
            from procedural_rules import handle_procedural_rule_command
            reply = handle_procedural_rule_command(message) or "未知行为规则命令。"
        except Exception as exc:
            reply = f"行为规则命令失败: {exc}"
    elif (
        message in {"/learn_status", "/learn_info", "/learn_on", "/learn_off", "/self_study_on", "/self_study_off"}
        or message.startswith("/learn ")
        or message.startswith("/trust_source ")
        or message in {"/self_study_topics", "/self_study_list"}
        or message.startswith("/self_study_add ")
        or message.startswith("/self_study_set ")
        or message.startswith("/self_study_del ")
        or message.startswith("/self_study_remove ")
        or message.startswith("/self_study_topic ")
        or message.startswith("/self_study_min ")
        or message.startswith("/self_study_max ")
    ):
        try:
            from web_learner import handle_learn_command
            reply = handle_learn_command(message) or "未知学习命令。"
        except ImportError:
            reply = "web_learner 模块未找到。"
        except Exception as exc:
            reply = f"学习命令失败: {exc}"
    elif message in {"/code_lab", "/code_status", "/code_history"} or message.startswith("/code_run "):
        try:
            from code_lab import handle_code_lab_command
            reply = handle_code_lab_command(message) or "未知代码练习场命令。"
        except Exception as exc:
            reply = f"代码练习场命令失败: {exc}"
    elif message in {"/code_autolearn_history", "/code_learn_dataset", "/code_learn_llm", "/code_learn_llm_status"} or message.startswith("/code_learn ") or message.startswith("/code_learn_train"):
        try:
            from code_autolearn import handle_code_autolearn_command
            reply = handle_code_autolearn_command(message) or "未知代码自学命令。"
        except Exception as exc:
            reply = f"代码自学命令失败: {exc}"
    elif message in {"/algorithm_curriculum", "/algorithm_curriculum_status", "/algorithm_curriculum_dataset"} or message.startswith("/algorithm_curriculum_train"):
        try:
            from algorithm_curriculum import handle_algorithm_curriculum_command
            reply = handle_algorithm_curriculum_command(message) or "未知算法课程命令。"
        except Exception as exc:
            reply = f"算法课程命令失败: {exc}"
    elif message == "/llm" or message == "/llm_status":
        try:
            from llm_inference import get_local_llm
            from llm_trainer import list_adapters, get_device_info
            
            llm = get_local_llm()
            lines = ["本地 LLM 状态："]
            
            if llm.loaded:
                lines.append(f"  状态: 已加载")
                lines.append(f"  模型: {llm.model_path}")
                if llm.adapter_path:
                    lines.append(f"  Adapter: {llm.adapter_path}")
                lines.append(f"  设备: {llm.device}")
            else:
                lines.append("  状态: 未加载")
            
            gpu_info = get_device_info()
            lines.append(f"  GPU: {gpu_info.get('message', '未知')}")
            
            adapters = list_adapters()
            if adapters:
                lines.append(f"\n已训练的 Adapter ({len(adapters)} 个):")
                for a in adapters[:5]:
                    lines.append(f"  - {a['name']}: {a.get('base_model', '?')} (loss={a.get('train_loss', '?')})")
            
            lines.append("\n命令: /llm_load [adapter名] | /llm_unload | /llm_train")
            reply = "\n".join(lines)
        except ImportError:
            reply = "LLM 模块未安装。请安装: pip install transformers peft accelerate bitsandbytes"
        except Exception as exc:
            reply = f"状态查询失败: {exc}"
    elif message.startswith("/llm_load"):
        try:
            from llm_inference import get_local_llm
            from llm_trainer import list_adapters
            
            llm = get_local_llm()
            parts = message.split(maxsplit=1)
            
            if len(parts) > 1:
                adapter_name = parts[1].strip()
                # 查找 adapter
                adapters = list_adapters()
                adapter_path = None
                for a in adapters:
                    if a["name"] == adapter_name or adapter_name in a["path"]:
                        adapter_path = a["path"]
                        break
                
                if adapter_path:
                    result = llm.load(adapter_path=adapter_path)
                else:
                    result = llm.load(model_path=adapter_name)
            else:
                result = llm.load()
            
            if result.get("ok"):
                reply = f"LLM 已加载: {result.get('model_path', '?')}\n设备: {result.get('device', '?')}"
            else:
                reply = f"加载失败: {result.get('error', '未知错误')}"
        except ImportError:
            reply = "LLM 模块未安装。请安装: pip install transformers peft accelerate bitsandbytes"
        except Exception as exc:
            reply = f"加载失败: {exc}"
    elif message == "/llm_unload":
        try:
            from llm_inference import get_local_llm
            get_local_llm().unload()
            reply = "LLM 已卸载，显存已释放。"
        except Exception as exc:
            reply = f"卸载失败: {exc}"
    elif message == "/export_model" or message == "/model":
        reply = export_model()
    elif message == "/time" or "现在几点" in message or "当前时间" in message:
        reply = local_time_text()
    elif message.startswith("/weather "):
        reply = weather_text(message.removeprefix("/weather ").strip())
    elif "天气" in message and len(message) <= 40:
        reply = weather_text(infer_weather_location(message))
    elif message == "/ocr" or "识别图片" in message or "图片上的文字" in message:
        reply = ocr_reply(file_record)
    elif message == "/install_ocr":
        reply = install_portable_ocr()
    elif message.startswith("/teach "):
        body = message.removeprefix("/teach ").strip()
        if "=>" in body:
            prompt, response = body.split("=>", 1)
            reply = teach_example(prompt, response, "manual", 1)
        else:
            reply = "格式：/teach 问法 => 回答"
    elif message.startswith("/forget "):
        reply = forget_memory(message.removeprefix("/forget ").strip())
    elif message == "/chat_mode" or message.startswith("/chat_mode "):
        try:
            from hybrid_chat import get_chat_mode, set_chat_mode, list_chat_modes
            if message == "/chat_mode":
                modes = list_chat_modes()
                lines = ["当前对话模式：", ""]
                for m in modes:
                    mark = " ●" if m["active"] else ""
                    lines.append(f"  {m['name']}{mark}")
                lines.append("\n切换: /chat_mode <模式名>")
                lines.append("模式: retrieval / tiny_llm / sparse_tiny_llm / hybrid / local_llm / api_llm")
                reply = "\n".join(lines)
            else:
                mode_name = message.removeprefix("/chat_mode ").strip()
                result = set_chat_mode(mode_name)
                if result.get("ok"):
                    from hybrid_chat import CHAT_MODES
                    info = CHAT_MODES[mode_name]
                    reply = f"已切换到「{info['name']}」\n{info['description']}"
                else:
                    reply = result.get("error", "切换失败")
        except ImportError:
            reply = "hybrid_chat 模块未找到。"
        except Exception as exc:
            reply = f"模式切换失败: {exc}"
    elif message == "/chat_status":
        try:
            from hybrid_chat import get_chat_mode, CHAT_MODES
            mode = get_chat_mode()
            info = CHAT_MODES.get(mode, {})
            lines = [f"对话系统状态：", f"  当前模式: {info.get('name', mode)}"]
            tiny_path = DATA_DIR / "models" / "tiny_llm.pt"
            if tiny_path.exists():
                lines.append(f"  Tiny LLM: 已训练 ({tiny_path.stat().st_size / 1024:.0f} KB)")
            else:
                lines.append("  Tiny LLM: 未训练 (用 /train_tiny 训练)")
            try:
                from tiny_llm import PANGU_PI_MODEL_FILE, SPARSE_MODEL_FILE
                if PANGU_PI_MODEL_FILE.exists():
                    sparse_state = f"已训练（盘古 pi 增强，{PANGU_PI_MODEL_FILE.stat().st_size / 1024:.0f} KB）"
                elif SPARSE_MODEL_FILE.exists():
                    sparse_state = f"已训练（旧稀疏权重兼容，{SPARSE_MODEL_FILE.stat().st_size / 1024:.0f} KB）"
                else:
                    sparse_state = "未训练（用 /train_sparse 训练）"
                lines.append(f"  稀疏增强 Tiny LLM: {sparse_state}")
            except Exception:
                lines.append("  稀疏增强 Tiny LLM: 状态未知")
            try:
                from llm_inference import get_local_llm
                llm = get_local_llm()
                lines.append(f"  本地 LLM: {'已加载' if llm.loaded else '未加载'}")
            except Exception:
                lines.append("  本地 LLM: 未安装")
            try:
                from remote_llm import is_remote_llm_ready, load_remote_llm_config
                remote_config = load_remote_llm_config()
                remote_state = "已启用" if is_remote_llm_ready(remote_config) else "未启用或未配置"
                lines.append(f"  大模型接口: {remote_state} ({remote_config.get('model', '')})")
            except Exception:
                lines.append("  大模型接口: 状态未知")
            reply = "\n".join(lines)
        except ImportError:
            reply = "hybrid_chat 模块未找到。"
        except Exception as exc:
            reply = f"状态查询失败: {exc}"
    elif message == "/image_growth":
        try:
            from image_growth import status
            image_status = status()
            reply = (
                "图片配方成长状态：\n"
                f"  已记录生成：{image_status['generated']} 张\n"
                f"  用户采用：{image_status['accepted']} 张\n"
                f"  用户未采用：{image_status['rejected']} 张\n"
                "在动态页给带图片的 AI 动态点赞，会将该图的本地配方作为对应心情的偏好。"
            )
        except Exception as exc:
            reply = f"图片成长状态读取失败: {exc}"
    elif message == "/growth_eval":
        try:
            from growth_loop import list_benchmarks
            benchmarks = list_benchmarks()
            lines = ["固定能力评测集（只评测，不参与训练）："]
            if not benchmarks:
                lines.append("  暂无。添加：/growth_eval_add 用户问题 => 必须出现的关键词1,关键词2")
            for item in benchmarks:
                lines.append(f"- {item['id']}｜{item['title']}｜关键词：{', '.join(item['expected_keywords'])}")
            lines.append("删除：/growth_eval_remove 评测ID")
            reply = "\n".join(lines)
        except Exception as exc:
            reply = f"评测集读取失败: {exc}"
    elif message.startswith("/growth_eval_add "):
        try:
            from growth_loop import add_benchmark
            body = message.removeprefix("/growth_eval_add ").strip()
            if "=>" not in body:
                reply = "格式：/growth_eval_add 用户问题 => 必须出现的关键词1,关键词2"
            else:
                prompt, keywords = body.split("=>", 1)
                result = add_benchmark(prompt, keywords)
                reply = f"已添加评测题：{result['benchmark']['id']}" if result.get("ok") else f"添加失败: {result.get('error')}"
        except Exception as exc:
            reply = f"评测题添加失败: {exc}"
    elif message.startswith("/growth_eval_remove "):
        try:
            from growth_loop import remove_benchmark
            benchmark_id = message.removeprefix("/growth_eval_remove ").strip()
            reply = "评测题已删除。" if remove_benchmark(benchmark_id) else "未找到该评测 ID。"
        except Exception as exc:
            reply = f"评测题删除失败: {exc}"
    elif message.startswith("/growth_eval_update "):
        try:
            from growth_loop import update_benchmark
            body = message.removeprefix("/growth_eval_update ").strip()
            parts = body.split(" ", 1)
            if len(parts) != 2 or "=>" not in parts[1]:
                reply = "格式：/growth_eval_update 评测ID 新问题 => 新关键词1,新关键词2"
            else:
                prompt, keywords = parts[1].split("=>", 1)
                result = update_benchmark(parts[0], prompt, keywords)
                reply = "评测题已更新。" if result.get("ok") else f"更新失败: {result.get('error')}"
        except Exception as exc:
            reply = f"评测题更新失败: {exc}"
    elif message == "/growth_status":
        try:
            from growth_loop import growth_status
            status = growth_status()
            reply = (
                "本地成长闭环状态：\n"
                f"  可训练验证经验：{status['eligible_experiences']} 条\n"
                f"  下次训练回放：{status['replay_samples']} 条（核心 {status['replay_core_samples']}，留出评测 {status['held_out_samples']}）\n"
                f"  当前版本：{status['active_version']}\n"
                f"  可回滚版本：{status['previous_version']}\n"
                f"  未通过候选：{status['rejected_candidates']} 个\n"
                "命令：/growth_eval；/growth_eval_add 问题 => 关键词1,关键词2；/train_tiny [轮数]；/growth_rollback"
            )
        except Exception as exc:
            reply = f"成长状态读取失败: {exc}"
    elif message == "/growth_rollback":
        try:
            from growth_loop import rollback_active_model
            result = rollback_active_model()
            reply = f"已回滚到版本：{result.get('active_version')}" if result.get("ok") else f"回滚失败: {result.get('error', '未知错误')}"
        except Exception as exc:
            reply = f"回滚出错: {exc}"
    elif message == "/train_tiny" or message.startswith("/train_tiny "):
        try:
            from growth_jobs import start as start_growth_training
            epochs = 3
            parts = message.split()
            if len(parts) > 1:
                try:
                    epochs = int(parts[1])
                except ValueError:
                    pass
            result = start_growth_training(epochs=epochs)
            if result.get("ok"):
                reply = (
                    "Tiny LLM 候选训练已进入后台队列。\n"
                    "训练完成后会自动进行留出集与固定能力评测；只有通过才会激活。\n"
                    "可在设置页“本地自成长”查看进度或取消训练。"
                )
            else:
                reply = f"训练任务未启动: {result.get('error', '未知错误')}"
        except ImportError:
            reply = "tiny_llm 模块未找到。"
        except Exception as exc:
            reply = f"训练出错: {exc}"
    elif message == "/train_sparse" or message.startswith("/train_sparse "):
        try:
            from tiny_llm import train_tiny_llm_in_runtime
            epochs = 3
            parts = message.split()
            if len(parts) > 1:
                try:
                    epochs = int(parts[1])
                except ValueError:
                    pass
            training = load_training()
            texts = [
                f"用户：{str(item.get('prompt', '')).strip()}\n助手：{str(item.get('response', '')).strip()}"
                for item in training.get("examples", [])
                if str(item.get("prompt", "")).strip() and str(item.get("response", "")).strip() and item.get("rating", 1) > 0
            ]
            if not texts:
                reply = "训练失败: 还没有可用教学样本。可以先用 /teach 问法 => 回答 添加样本。"
                return {"reply": reply, "state": state_payload()}
            result = train_tiny_llm_in_runtime(texts=texts, epochs=epochs, attention_type="pangu_pi_sparse")
            if result.get("ok"):
                reply = f"稀疏增强 Tiny LLM 训练完成：\n  样本: {result.get('samples')} 条\n  loss: {result.get('final_loss')}\n  模型: {result.get('model_path')}\n使用 /chat_mode sparse_tiny_llm 切换。"
            else:
                reply = f"训练失败: {result.get('error', '未知错误')}"
        except ImportError:
            reply = "需要可用的 PyTorch 运行时才能训练稀疏增强模型。"
        except Exception as exc:
            reply = f"训练出错: {exc}"
    elif message == "/train_pangu_pi" or message.startswith("/train_pangu_pi "):
        try:
            from tiny_llm import train_tiny_llm_in_runtime
            epochs = 3
            parts = message.split()
            if len(parts) > 1:
                try:
                    epochs = int(parts[1])
                except ValueError:
                    pass
            training = load_training()
            texts = [
                f"用户：{str(item.get('prompt', '')).strip()}\n助手：{str(item.get('response', '')).strip()}"
                for item in training.get("examples", [])
                if str(item.get("prompt", "")).strip() and str(item.get("response", "")).strip() and item.get("rating", 1) > 0
            ]
            if not texts:
                reply = "训练失败: 还没有可用教学样本。可以先用 /teach 问法 => 回答 添加样本。"
                return {"reply": reply, "state": state_payload()}
            result = train_tiny_llm_in_runtime(texts=texts, epochs=epochs, attention_type="pangu_pi_sparse")
            if result.get("ok"):
                reply = f"盘古 pi 稀疏 Tiny LLM 训练完成：\n  样本: {result.get('samples')} 条\n  loss: {result.get('final_loss')}\n  模型: {result.get('model_path')}\n使用 /chat_mode pangu_pi_sparse_tiny_llm 切换。"
            else:
                reply = f"训练失败: {result.get('error', '未知错误')}"
        except ImportError:
            reply = "需要安装 PyTorch 才能训练盘古 pi 稀疏模型。"
        except Exception as exc:
            reply = f"训练出错: {exc}"
    elif message == "/retrain":
        try:
            from hybrid_chat import rebuild_embedding_index
            result = rebuild_embedding_index()
            if result.get("ok"):
                lines = [
                    "检索索引重建完成：",
                    f"  重建样本：{result['rebuilt']} 条",
                    f"  总样本数：{result['total']} 条",
                    f"  模型类型：{result['model_type']}",
                ]
                reply = "\n".join(lines)
            else:
                reply = f"重建失败：{result.get('error', '未知错误')}"
        except ImportError:
            reply = "hybrid_chat 模块未找到。"
        except Exception as exc:
            reply = f"重建出错：{exc}"
    elif message.startswith("/create_plugin "):
        try:
            from plugin_manager import generate_plugin_code
            prompt = message[16:].strip()
            if not prompt:
                reply = "请描述要创建的插件功能，例如：/create_plugin 帮我创建一个待办事项插件"
            else:
                reply = f"正在使用 AI 生成插件：{prompt}\n请稍候..."
                result = generate_plugin_code(prompt)
                if not result.get("ok"):
                    reply = f"插件生成失败：{result.get('error', '未知错误')}"
                else:
                    meta = {
                        "name": result["name"],
                        "description": result["description"],
                        "version": "1.0.0",
                        "buttons": result["buttons"],
                        "code": result["code"],
                        "ai_generated": True,
                        "sandbox_validate": True,
                        "isolation_backend": "process",
                    }
                    validation = validate_plugin_package(meta)
                    if not validation.get("ok"):
                        reply = f"插件沙箱验证失败：{validation.get('error', '未知错误')}"
                    else:
                        import re
                        slug = re.sub(r'[^a-z0-9_-]', '_', result["name"].lower())[:48]
                        plugin = plugin_mgr.install_from_template(slug, meta)
                        reply = (
                            f"插件创建成功！\n"
                            f"名称: {plugin.name}\n"
                            f"版本: {plugin.version}\n"
                            f"描述: {plugin.description}\n"
                            f"命令: {', '.join(b['command'] for b in plugin.buttons)}\n"
                            f"\n已通过沙箱验证：{', '.join(validation.get('checks', []))}"
                        )
        except ImportError:
            reply = "plugin_manager 模块未找到。"
        except Exception as exc:
            import traceback
            reply = f"创建插件出错：{exc}\n{traceback.format_exc()[:500]}"
    elif message.startswith("/dream"):
        try:
            from dreaming_engine import handle_dream_command
            if message in ("/dream_now", "/dream_practice"):
                _set_task_status("rebuilding", "正在执行梦境任务...")
            reply = handle_dream_command(message) or "未知梦境命令。可用：/dream_status /dream_on /dream_off /dream_now /dream_practice /dream_skills"
            if message in ("/dream_now", "/dream_practice"):
                _set_task_status("done", reply[:80])
                _clear_task_status_after(5.0)
        except ImportError:
            reply = "dreaming_engine 模块未找到。"
        except Exception as exc:
            reply = f"梦境命令失败: {exc}"
            if message in ("/dream_now", "/dream_practice"):
                _set_task_status("error", f"梦境任务失败：{exc}")
                _clear_task_status_after(5.0)
    elif message.startswith("/proactive"):
        try:
            from proactive_engagement import handle_proactive_command
            reply = handle_proactive_command(message) or "未知主动对话命令。可用：/proactive_status /proactive_on /proactive_off /proactive_test"
        except ImportError:
            reply = "proactive_engagement 模块未找到。"
        except Exception as exc:
            reply = f"主动对话命令失败: {exc}"
    elif message.startswith("/distill"):
        try:
            from knowledge_distillation import handle_distillation_command
            if message in ("/distill_now",):
                _set_task_status("rebuilding", "正在进行知识蒸馏...")
            reply = handle_distillation_command(message) or "未知知识蒸馏命令。可用：/distill_status /distill_on /distill_off /distill_now /distill_queue"
            if message in ("/distill_now",):
                _set_task_status("done", reply[:80])
                _clear_task_status_after(5.0)
        except ImportError:
            reply = "knowledge_distillation 模块未找到。"
        except Exception as exc:
            reply = f"知识蒸馏命令失败: {exc}"
            if message in ("/distill_now",):
                _set_task_status("error", f"知识蒸馏失败：{exc}")
                _clear_task_status_after(5.0)
    else:
        identity_reply = identity_intro_reply(message)
        if identity_reply:
            reply = identity_reply
        else:
            skill = match_dialogue_skill(message)
            if skill:
                reply = skill_reply(skill, profile_context())
                record_growth_event("dialogue_skill_triggered", skill.get("title", ""), {"skill_id": skill.get("id")})
            else:
                page = fetch_page(url) if url else None
                reply = local_reply(message, page, file_record, realtime_context=realtime_context if from_realtime else "")
        if persist_history:
            observe_user_message(message)
            for bucket, text in extract_memory_candidates(message):
                add_memory(text, bucket, source="auto")
            observe_chat_interaction(message, reply)

        if persist_history:
            try:
                from conversation_audit import submit_audit
                history = load_history_entries()[-6:]
                submit_audit(message, reply, history)
            except Exception:
                pass

        if persist_history:
            try:
                from plugin_manager import auto_create_plugin
                from remote_llm import is_remote_llm_ready, load_remote_llm_config
                llm_config = load_remote_llm_config()
                if is_remote_llm_ready(llm_config):
                    auto_plugin_result = _evaluate_and_create_plugin(message, reply, history, llm_config)
                    if auto_plugin_result.get("ok"):
                        plugin_name = auto_plugin_result.get("name")
                        plugin_commands = ", ".join(b["command"] for b in auto_plugin_result.get("buttons", []))
                        from companion_growth import apply_user_feedback
                        store = load_growth()
                        notes = store["personality"].setdefault("growth_notes", [])
                        notes.append({
                            "time": int(time.time()),
                            "text": f"自主创建插件「{plugin_name}」，命令：{plugin_commands}",
                        })
                        store["personality"]["growth_notes"] = notes[-40:]
                        save_growth(store)
            except Exception:
                pass

        if persist_history:
            try:
                from web_learner import learn_from_web, _load_trust_config
                config = _load_trust_config()
                if config.get("enabled") and config.get("auto_learn"):
                    if any(keyword in message for keyword in ["最新", "现在", "今天", "最近", "刚刚", "新闻", "更新", "什么是", "是什么"]):
                        learn_result = learn_from_web(message[:100])
                        if learn_result.get("ok"):
                            store = load_growth()
                            notes = store["personality"].setdefault("growth_notes", [])
                            notes.append({
                                "time": int(time.time()),
                                "text": f"自主联网学习「{learn_result['query']}」，来源：{', '.join(s['domain'] for s in learn_result['sources'])}",
                            })
                            store["personality"]["growth_notes"] = notes[-40:]
                            save_growth(store)
            except Exception:
                pass

    recent_chats = []
    if persist_history:
        append_history("assistant", reply)
        record_emotion_message("assistant", reply)
        conversation_id, recent_chats = upsert_recent_chat(conversation_id, user_message or f"[url]{url}" or f"[file]{file_id}", reply)
    if from_realtime:
        append_realtime_chat_message("assistant", training_response_text(reply))
    
    audit_status = {}
    audit_corrections = []
    try:
        from conversation_audit import get_audit_status, get_pending_corrections
        audit_status = get_audit_status()
        audit_corrections = get_pending_corrections()
    except Exception:
        pass
    
    # Prepend any showoff messages to the reply
    if showoff_prefix and not reply.startswith(showoff_prefix.strip()):
        reply = showoff_prefix + reply

    # Prepend user's preferred address if set
    if user_address and not reply.startswith(user_address):
        # Add address prefix naturally (not for every message, just for meaningful ones)
        # Only add if the reply is substantial and doesn't already address the user
        if len(reply) > 20 and not any(reply.lower().startswith(x) for x in ["好的", "嗯", "哦", "明白", "了解", "收到", user_address]):
            reply = f"{user_address}，{reply}"

    # Add reverse question if needed (every 3-5 turns)
    try:
        from proactive_engagement import ensure_reverse_question
        reply = ensure_reverse_question(reply, lastEmotion)
    except Exception:
        pass

    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "recent_chats": recent_chats,
        "memory": load_memory(),
        "training": load_training(),
        "files": load_files(),
        "avatar": avatar_state(choose_motion(message, reply)),
        "emotion_trend": get_emotion_trend(7),
        "diary_entries": get_diary_entries(7),
        "growth": growth_payload(),
        "audit_status": audit_status,
        "audit_corrections": audit_corrections,
        "index_rebuild_status": get_task_status(),
    }


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Companion AI</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-soft: #eef2f7;
      --ink: #1c2430;
      --muted: #657184;
      --line: #d9dee7;
      --accent: #276ef1;
      --accent-2: #0b8f6f;
      --warn: #9a5b00;
      --good: #0b7a55;
      --bad: #c0392b;
      --avatar: #dceaff;
      --font-scale: 1;
      --density-scale: 1;
      --ui-radius: 8px;
      --sidebar-width: 280px;
      --avatar-height: 84px;
      --space-2: calc(14px * var(--density-scale));
      --space-3: calc(18px * var(--density-scale));
    }
    :root[data-theme="night"] {
      color-scheme: dark;
      --bg: #10141c;
      --panel: #171d27;
      --panel-soft: #111722;
      --ink: #edf2f8;
      --muted: #c4d0df;
      --line: #2a3444;
      --accent: #7aa7ff;
      --accent-2: #55d0a9;
      --warn: #ffd166;
      --good: #66d39d;
      --bad: #ff8a80;
    }
    :root[data-theme="forest"] {
      --bg: #f2f7f3;
      --panel: #ffffff;
      --panel-soft: #e9f1eb;
      --ink: #1c2b22;
      --muted: #5f7569;
      --line: #cfded5;
      --accent: #2d7d59;
      --accent-2: #617a2e;
      --warn: #8a5b08;
      --good: #23724e;
      --bad: #b94a3c;
    }
    :root[data-theme="rose"] {
      --bg: #fbf5f7;
      --panel: #ffffff;
      --panel-soft: #f4e9ef;
      --ink: #2c2230;
      --muted: #7b6875;
      --line: #ead5df;
      --accent: #c24a7a;
      --accent-2: #477d8d;
      --warn: #9a5b00;
      --good: #35785f;
      --bad: #b94a5b;
    }
    :root[data-theme="mono"] {
      --bg: #f5f5f4;
      --panel: #ffffff;
      --panel-soft: #ececea;
      --ink: #202020;
      --muted: #666666;
      --line: #d7d7d4;
      --accent: #2f5f8f;
      --accent-2: #5a6f3b;
      --warn: #7a5600;
      --good: #286b49;
      --bad: #a33a32;
    }
    * { box-sizing: border-box; }
    html, body {
      height: 100%;
    }
    body {
      margin: 0;
      height: 100vh;
      font-size: calc(16px * var(--font-scale));
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
      display: grid;
      grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
      overflow: hidden;
      scrollbar-color: var(--muted) var(--panel-soft);
    }
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: var(--panel-soft); }
    ::-webkit-scrollbar-thumb {
      background: color-mix(in srgb, var(--muted) 58%, transparent);
      border-radius: 999px;
      border: 2px solid var(--panel-soft);
    }
    /* Hide scrollbars by default; only show on hover or while scrolling. */
    :root {
      --scrollbar-opacity: 0;
      --scrollbar-transition: opacity 0.25s ease;
    }
    :root:hover {
      --scrollbar-opacity: 0.7;
    }
    body.is-scrolling {
      --scrollbar-opacity: 1;
    }
    html {
      scrollbar-width: thin;
      scrollbar-color: var(--muted) transparent;
    }
    ::-webkit-scrollbar {
      width: 10px;
      height: 10px;
      opacity: var(--scrollbar-opacity);
      transition: opacity var(--scrollbar-transition);
    }
    ::-webkit-scrollbar-thumb {
      background: color-mix(in srgb, var(--muted) 60%, transparent);
      border-radius: 999px;
      border: 2px solid var(--panel-soft);
    }
    aside {
      border-right: 0;
      background: var(--panel-soft);
      padding: calc(22px * var(--density-scale));
      overflow: auto;
      height: 100vh;
      min-height: 0;
    }
    main {
      display: grid;
      grid-template-rows: auto 170px minmax(0, 1fr) auto auto;
      height: 100vh;
      min-height: 0;
      overflow: hidden;
    }
    header {
      padding: calc(16px * var(--density-scale)) calc(22px * var(--density-scale));
      border-bottom: 0;
      background: var(--panel);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0;
    }
    .status {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .header-tools {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-right: 48px;
      min-width: 0;
    }
    .language-select {
      height: 32px;
      border: 0;
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--ink);
      padding: 0 8px;
      font: inherit;
      font-size: 13px;
    }
    .memory-title {
      font-size: 14px;
      font-weight: 700;
      margin: 0 0 10px;
    }
    .memory-orbit {
      position: relative;
      min-height: 246px;
      margin: 0 0 16px;
      border: 0;
      border-radius: var(--ui-radius);
      background:
        radial-gradient(circle at 50% 48%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 42%),
        linear-gradient(180deg, var(--panel) 0%, var(--panel-soft) 100%);
      overflow: hidden;
      outline: none;
    }
    .memory-orbit::before {
      content: "";
      position: absolute;
      inset: 22px;
      border: 1px dashed color-mix(in srgb, var(--accent) 24%, transparent);
      border-radius: 50%;
      opacity: .58;
      transform: scale(.74);
      transition: transform .35s ease, opacity .35s ease;
    }
    .memory-orbit:hover::before,
    .memory-orbit:focus-within::before {
      opacity: 1;
      transform: scale(1);
    }
    .memory-brain {
      position: absolute;
      left: 50%;
      top: 50%;
      width: 148px;
      height: 122px;
      transform: translate(-50%, -50%);
      color: var(--accent);
      filter: drop-shadow(0 10px 22px rgba(39, 110, 241, .16));
      transition: transform .35s ease, color .35s ease, filter .35s ease;
      z-index: 2;
    }
    .memory-orbit:hover .memory-brain,
    .memory-orbit:focus-within .memory-brain {
      color: var(--accent-2);
      filter: drop-shadow(0 16px 28px rgba(11, 143, 111, .18));
      transform: translate(-50%, -50%) scale(.9);
    }
    .memory-brain path,
    .memory-brain circle {
      fill: none;
      stroke: currentColor;
      stroke-width: 4;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .memory-brain circle {
      fill: var(--panel);
      stroke-width: 3;
    }
    .memory-orbit-hint {
      position: absolute;
      left: 16px;
      right: 16px;
      bottom: 14px;
      text-align: center;
      font-size: 12px;
      color: var(--muted);
      z-index: 3;
      transition: opacity .25s ease, transform .25s ease;
    }
    .memory-orbit:hover .memory-orbit-hint,
    .memory-orbit:focus-within .memory-orbit-hint {
      opacity: 0;
      transform: translateY(8px);
    }
    .memory-node {
      position: absolute;
      z-index: 4;
      width: 118px;
      min-height: 42px;
      padding: 8px 9px;
      border: 0;
      border-radius: var(--ui-radius);
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      box-shadow: 0 12px 24px rgba(22, 33, 52, .12);
      opacity: 0;
      transform: translate(-50%, -50%) scale(.78);
      pointer-events: none;
      transition: opacity .28s ease, transform .28s ease, border-color .28s ease;
    }
    .memory-orbit:hover .memory-node,
    .memory-orbit:focus-within .memory-node {
      opacity: 1;
      transform: translate(-50%, -50%) scale(1);
      pointer-events: auto;
    }
    .memory-node:hover {
      border-color: rgba(11, 143, 111, .5);
      transform: translate(-50%, -50%) scale(1.03);
    }
    .memory-node strong {
      display: block;
      margin-bottom: 4px;
      font-size: 12px;
      color: var(--accent);
    }
    .memory-node span {
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      font-size: 12px;
      line-height: 1.35;
      color: var(--ink);
      overflow-wrap: anywhere;
    }
    .memory-node.empty {
      border-style: dashed;
      color: var(--muted);
    }
    .memory-node.empty span {
      color: var(--muted);
    }
    .memory {
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.5;
      color: var(--ink);
    }
    .training {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 0;
      white-space: pre-wrap;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.5;
    }
    .growth-panel {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 0;
      font-size: 13px;
      color: var(--ink);
      line-height: 1.5;
    }
    .growth-panel h4 {
      margin: 0 0 8px;
      font-size: 13px;
      color: var(--muted);
    }
    .growth-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin: 4px 0;
    }
    .growth-row strong {
      font-weight: 700;
      color: var(--ink);
      text-align: right;
    }
    .growth-note {
      margin-top: 8px;
      color: var(--muted);
    }
    .notice {
      margin-top: 16px;
      padding: 12px;
      border: 0;
      color: var(--warn);
      background: color-mix(in srgb, var(--warn) 12%, var(--panel));
      border-radius: var(--ui-radius);
      font-size: 13px;
      line-height: 1.45;
    }
    .files {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 0;
      font-size: 13px;
      line-height: 1.45;
      color: var(--ink);
    }
    .files summary {
      cursor: pointer;
      min-height: 34px;
      padding: 8px 10px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      font-weight: 750;
      list-style: none;
    }
    .files summary::-webkit-details-marker { display: none; }
    .files summary::after {
      content: "";
      float: right;
      width: 8px;
      height: 8px;
      margin-top: 5px;
      border-right: 2px solid var(--muted);
      border-bottom: 2px solid var(--muted);
      transform: rotate(-45deg);
      color: var(--muted);
      font-weight: 800;
      transition: transform .16s ease;
    }
    .files[open] summary::after {
      transform: rotate(45deg);
    }
    .files-body {
      margin-top: 8px;
    }
    .file-card {
      margin-top: 8px;
      padding: 9px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      overflow-wrap: anywhere;
    }
    .avatar-stage {
      border-bottom: 0;
      background: var(--panel-soft);
      display: grid;
      grid-template-columns: 170px minmax(0, 1fr) minmax(220px, 320px);
      align-items: center;
      gap: 18px;
      min-height: var(--avatar-height);
      padding: var(--space-2) calc(22px * var(--density-scale));
      overflow: hidden;
    }
    .avatar {
      width: 136px;
      height: 136px;
      position: relative;
      justify-self: center;
      transform-origin: 50% 80%;
    }
    .live2d-frame {
      width: 170px;
      height: 150px;
      border: 0;
      border-radius: var(--ui-radius);
      justify-self: center;
      display: none;
      background: var(--panel-soft);
      color-scheme: dark;
      mix-blend-mode: multiply;
    }
    :root[data-theme="night"] .live2d-frame {
      background: transparent;
      filter: brightness(.94) contrast(1.08);
      mix-blend-mode: multiply;
    }
    .avatar-stage.has-live2d .avatar {
      display: none;
    }
    .avatar-stage.has-live2d .live2d-frame {
      display: block;
    }
    .avatar .head {
      position: absolute;
      left: 24px;
      top: 16px;
      width: 88px;
      height: 82px;
      border: 3px solid #243143;
      border-radius: 46% 46% 42% 42%;
      background: #fff4ea;
    }
    .avatar .hair {
      position: absolute;
      left: 18px;
      top: 10px;
      width: 100px;
      height: 52px;
      border-radius: 50% 50% 28% 28%;
      background: #263244;
    }
    .avatar .body {
      position: absolute;
      left: 34px;
      top: 88px;
      width: 68px;
      height: 42px;
      border: 3px solid #243143;
      border-radius: 24px 24px 12px 12px;
      background: #b7e4d2;
    }
    .avatar .eye {
      position: absolute;
      top: 50px;
      width: 10px;
      height: 14px;
      border-radius: 50%;
      background: #243143;
      animation: blink 4s infinite;
    }
    .avatar .eye.left { left: 51px; }
    .avatar .eye.right { right: 51px; }
    .avatar .mouth {
      position: absolute;
      left: 61px;
      top: 72px;
      width: 16px;
      height: 8px;
      border-bottom: 3px solid #243143;
      border-radius: 0 0 18px 18px;
    }
    .avatar.nod { animation: nod 1.2s ease-in-out; }
    .avatar.happy { animation: happy 1.4s ease-in-out; }
    .avatar.thinking { animation: thinking 1.7s ease-in-out; }
    .avatar.encourage { animation: encourage 1.5s ease-in-out; }
    .avatar.celebrate { animation: celebrate 1.2s ease-in-out; }
    .avatar.read { animation: read 1.8s ease-in-out; }
    .avatar.scan { animation: scan 1.2s ease-in-out; }
    .avatar.spark { animation: spark 1s ease-in-out; }
    @keyframes blink { 0%, 94%, 100% { transform: scaleY(1); } 96% { transform: scaleY(.1); } }
    @keyframes nod { 0%, 100% { transform: translateY(0); } 45% { transform: translateY(8px) rotate(2deg); } }
    @keyframes happy { 0%, 100% { transform: translateY(0); } 35%, 70% { transform: translateY(-8px); } }
    @keyframes thinking { 0%, 100% { transform: rotate(0); } 50% { transform: rotate(-7deg); } }
    @keyframes encourage { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.06); } }
    @keyframes celebrate { 0%, 100% { transform: translateY(0) rotate(0); } 35% { transform: translateY(-12px) rotate(-6deg); } 70% { transform: translateY(-8px) rotate(6deg); } }
    @keyframes read { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(8px); } }
    @keyframes scan { 0%, 100% { filter: brightness(1); } 50% { filter: brightness(1.22); } }
    @keyframes spark { 0%, 100% { transform: scale(1); filter: saturate(1); } 50% { transform: scale(1.08); filter: saturate(1.4); } }
    .avatar-info {
      min-width: 0;
      display: grid;
      gap: 8px;
      color: var(--ink);
      font-size: 13px;
    }
    .motion-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .motion-pill {
      padding: 5px 8px;
      border-radius: 999px;
      background: var(--panel);
      color: var(--ink);
      font-size: 12px;
    }
    .motion-pill.active {
      background: color-mix(in srgb, var(--good) 18%, var(--panel));
      color: var(--good);
      font-weight: 700;
    }
    .realtime-pet-chat {
      display: none;
      align-self: stretch;
      min-height: 122px;
      max-height: 150px;
      border: 0;
      border-radius: var(--ui-radius);
      background: color-mix(in srgb, var(--panel) 88%, transparent);
      overflow: hidden;
      grid-template-rows: auto minmax(0, 1fr);
      box-shadow: 0 10px 24px rgba(12, 18, 28, .08);
    }
    .realtime-pet-chat.open {
      display: grid;
    }
    .realtime-pet-chat-title {
      padding: 7px 10px;
      border-bottom: 0;
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      background: var(--panel-soft);
    }
    .realtime-pet-chat-body {
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-height: 0;
      padding: 8px;
      overflow-y: auto;
    }
    .realtime-pet-line {
      max-width: 88%;
      padding: 6px 8px;
      border-radius: var(--ui-radius);
      font-size: 12px;
      line-height: 1.42;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    .realtime-pet-line.user {
      align-self: flex-end;
      background: color-mix(in srgb, var(--accent) 16%, var(--panel));
      border: 0;
      color: var(--ink);
    }
    .realtime-pet-line.assistant {
      align-self: flex-start;
      background: var(--panel-soft);
      border: 0;
      color: var(--ink);
    }
    .realtime-pet-line.system {
      align-self: center;
      max-width: 100%;
      background: transparent;
      border: 0;
      color: var(--muted);
      text-align: center;
      font-size: 11px;
      padding: 2px 4px;
    }
    #chat {
      padding: calc(22px * var(--density-scale));
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-height: 0;
      overscroll-behavior: contain;
    }
    .msg {
      max-width: min(780px, 92%);
      padding: calc(12px * var(--density-scale)) calc(14px * var(--density-scale));
      border-radius: var(--ui-radius);
      line-height: 1.55;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border: 0;
      background: var(--panel);
      color: var(--ink);
      box-shadow: 0 8px 22px rgba(12, 18, 28, .06);
    }
    .user {
      align-self: flex-end;
      background: color-mix(in srgb, var(--accent) 12%, var(--panel));
    }
    .assistant {
      align-self: flex-start;
    }
    .msg {
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }
    .msg-body {
      flex: 1;
      min-width: 0;
      display: grid;
      gap: 8px;
    }
    .msg-text {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .emotion-toggle {
      justify-self: start;
      height: 28px;
      min-width: 0;
      padding: 0 9px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      cursor: pointer;
    }
    .emotion-toggle:hover {
      background: color-mix(in srgb, var(--accent) 10%, var(--panel));
      color: var(--ink);
    }
    .emotion-meta {
      display: none;
      padding: 8px 10px;
      border: 0;
      border-radius: var(--ui-radius);
      border-left: 0;
      background: var(--panel-soft);
      color: var(--muted);
      font-size: 13px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .emotion-meta.open {
      display: block;
    }
    .learning-record {
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
      overflow: hidden;
    }
    .learning-record summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 9px 10px;
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      list-style: none;
    }
    .learning-record summary::-webkit-details-marker {
      display: none;
    }
    .learning-record summary::after {
      content: "查看";
      flex: 0 0 auto;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    .learning-record[open] summary::after {
      content: "收起";
    }
    .learning-record-body {
      display: grid;
      gap: 10px;
      padding: 0 10px 10px;
      color: var(--ink);
      font-size: 13px;
    }
    .learning-record-body p {
      margin: 0;
    }
    .audit-indicator {
      display: none;
      padding: 6px 12px;
      border-radius: var(--ui-radius);
      font-size: 12px;
      font-weight: 650;
      text-align: center;
      animation: fadeIn 0.2s ease;
    }
    .audit-processing {
      background: color-mix(in srgb, var(--accent) 12%, var(--panel));
      color: var(--accent);
    }
    .audit-completed {
      background: color-mix(in srgb, var(--good) 12%, var(--panel));
      color: var(--good);
    }
    .audit-failed {
      background: color-mix(in srgb, var(--bad) 12%, var(--panel));
      color: var(--bad);
    }
    .audit-correction {
      background: color-mix(in srgb, var(--warn, #f59e0b) 10%, var(--panel));
      border-left: 3px solid var(--warn, #f59e0b);
      border-radius: var(--ui-radius);
      padding: 10px 14px;
      margin: 6px 0;
      font-size: 13px;
      animation: fadeIn 0.3s ease;
    }
    .audit-correction .correction-label {
      font-weight: 700;
      color: var(--warn, #f59e0b);
      margin-bottom: 4px;
    }
    .audit-correction .correction-text {
      white-space: pre-wrap;
      line-height: 1.5;
    }
    .audit-correction .correction-meta {
      font-size: 11px;
      color: var(--muted);
      margin-top: 4px;
    }
    .task-indicator {
      display: none;
      padding: 6px 12px;
      border-radius: var(--ui-radius);
      font-size: 12px;
      font-weight: 650;
      text-align: center;
      animation: fadeIn 0.2s ease;
    }
    .task-processing {
      background: color-mix(in srgb, var(--accent) 12%, var(--panel));
      color: var(--accent);
    }
    .task-completed {
      background: color-mix(in srgb, var(--good) 12%, var(--panel));
      color: var(--good);
    }
    .task-failed {
      background: color-mix(in srgb, var(--bad) 12%, var(--panel));
      color: var(--bad);
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .learning-record-section {
      display: grid;
      gap: 6px;
    }
    .learning-record-section strong {
      color: var(--ink);
      font-size: 12px;
    }
    .learning-record-list {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .learning-source {
      display: grid;
      gap: 4px;
      padding: 8px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
    }
    .learning-source a {
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
      overflow-wrap: anywhere;
    }
    .learning-source a:hover {
      text-decoration: underline;
    }
    .learning-source-meta {
      color: var(--muted);
      font-size: 12px;
    }
    .learning-source-excerpt {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
    }
    .tts-play-btn {
      flex-shrink: 0;
      width: 28px;
      min-width: 28px;
      height: 28px;
      padding: 0;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }
    .tts-play-btn:hover {
      background: var(--panel-soft);
    }
    .tts-play-btn.playing {
      background: color-mix(in srgb, var(--accent) 14%, var(--panel));
      border-color: transparent;
      color: var(--accent);
    }
    .user .tts-play-btn {
      display: none;
    }
    .voice-input-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .voice-input-row textarea {
      flex: 1;
      min-width: 0;
    }
    .voice-btn {
      flex: 0 0 auto;
      width: 42px;
      min-width: 42px;
      height: 42px;
      padding: 0;
      border-radius: var(--ui-radius);
      background: var(--accent);
      color: #fff;
      font-size: 19px;
      line-height: 1;
    }
    .voice-btn.listening {
      background: var(--bad);
    }
    .realtime-voice-btn {
      flex: 0 0 auto;
      width: 58px;
      min-width: 58px;
      height: 42px;
      padding: 0 8px;
      border-radius: var(--ui-radius);
      background: var(--accent-2);
      color: #fff;
      font-size: 18px;
      line-height: 1;
      white-space: nowrap;
    }
    .realtime-voice-btn.active {
      background: var(--bad);
    }
    .wake-word-btn {
      flex: 0 0 auto;
      width: 42px;
      min-width: 42px;
      height: 42px;
      padding: 0;
      border-radius: var(--ui-radius);
      background: var(--accent);
      color: #fff;
      font-size: 18px;
      line-height: 1;
    }
    .wake-word-btn.active {
      background: var(--bad);
    }
    .realtime-voice-status {
      min-height: 18px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .realtime-voice-status.active {
      color: var(--good);
      font-weight: 650;
    }
    .realtime-voice-status.error {
      color: var(--bad);
      font-weight: 650;
    }
    .realtime-sense-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
      margin-top: 6px;
    }
    .realtime-sense-toggle {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      min-height: 28px;
      padding: 4px 8px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
      cursor: pointer;
      user-select: none;
    }
    .realtime-sense-toggle input {
      width: 14px;
      height: 14px;
      margin: 0;
      accent-color: var(--good);
    }
    .realtime-sense-toggle:has(input:checked) {
      border-color: transparent;
      background: color-mix(in srgb, var(--good) 16%, var(--panel));
      color: var(--good);
      font-weight: 650;
    }
    .realtime-launch-overlay {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(12, 18, 28, 0.36);
      z-index: 2600;
    }
    .realtime-launch-overlay.open {
      display: flex;
    }
    .realtime-launch-panel {
      width: min(420px, 100%);
      border-radius: var(--ui-radius);
      background: var(--panel);
      box-shadow: 0 18px 48px rgba(12, 18, 28, 0.22);
      padding: 20px;
    }
    .realtime-launch-panel h2 {
      margin: 0 0 8px;
      color: #1c2430;
      font-size: 20px;
      line-height: 1.25;
    }
    .realtime-launch-panel p {
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .realtime-launch-options {
      display: grid;
      gap: 8px;
      margin: 12px 0 18px;
    }
    .realtime-launch-options label {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 8px 10px;
      border: 0;
      border-radius: var(--ui-radius);
      color: var(--ink);
      background: var(--panel);
      font-size: 14px;
      cursor: pointer;
    }
    .realtime-launch-options input {
      width: 16px;
      height: 16px;
      accent-color: #0b8f6f;
    }
    .realtime-launch-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
    .realtime-launch-actions button {
      min-height: 36px;
      padding: 8px 14px;
      border-radius: 8px;
    }
    .realtime-launch-actions .primary {
      background: #0b8f6f;
      color: #fff;
    }
    .voiceprint-list {
      max-height: 148px;
      overflow: auto;
      border: 0;
      border-radius: var(--ui-radius);
      padding: 6px 8px;
      margin: 8px 0;
      background: var(--panel);
      font-size: 13px;
    }
    .voiceprint-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 0;
    }
    .voiceprint-item:last-child {
      border-bottom: 0;
    }
    .voiceprint-item button {
      padding: 5px 8px;
      font-size: 12px;
    }
    .feedback {
      align-self: flex-start;
      display: flex;
      gap: 8px;
      margin-top: -6px;
    }
    .feedback button {
      height: 32px;
      min-width: 68px;
      padding: 0 10px;
      background: var(--panel);
      color: var(--ink);
      font-weight: 650;
    }
    .feedback button.good { color: var(--good); }
    .feedback button.emotion-good { color: var(--good); }
    .feedback button.emotion-bad { color: var(--warn); }
    .feedback-group { display: inline-flex; gap: 6px; align-items: center; }
    .feedback-emotion { margin-left: 6px; padding-left: 10px; border-left: 0; }
    form {
      border-top: 0;
      padding: var(--space-2);
      background: var(--panel-soft);
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
    }
    .inputs {
      display: grid;
      gap: 8px;
    }
    input, textarea, select {
      width: 100%;
      border: 0;
      border-radius: var(--ui-radius);
      font: inherit;
      padding: calc(10px * var(--density-scale)) calc(11px * var(--density-scale));
      min-width: 0;
      background: var(--panel);
      color: var(--ink);
      box-shadow: none;
    }
    textarea { resize: vertical; }
    textarea { min-height: 68px; max-height: 180px; }
    input[type="file"] {
      padding: 8px;
      background: var(--panel);
    }
    input[type="file"]::file-selector-button {
      margin-right: 10px;
      border: 0;
      border-radius: calc(var(--ui-radius) - 2px);
      background: var(--panel-soft);
      color: var(--ink);
      padding: 6px 10px;
      font: inherit;
      font-weight: 650;
    }
    button {
      align-self: end;
      height: 44px;
      min-width: 92px;
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled { opacity: .82; cursor: wait; filter: saturate(.72); }
    .command-section {
      margin-top: 10px;
      border-top: 0;
      padding-top: 8px;
    }
    .command-section summary {
      cursor: pointer;
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      line-height: 1.4;
      padding: 4px 0;
    }
    .command-section summary:hover {
      color: var(--accent);
    }
    .secondary-nav {
      display: grid;
      gap: 7px;
      margin: 10px 0;
      padding: 10px 0;
      border-top: 0;
      border-bottom: 0;
    }
    .secondary-nav a {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 34px;
      padding: 7px 10px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      font-size: 12px;
      font-weight: 750;
      text-decoration: none;
    }
    .secondary-nav a::after {
      content: ">";
      color: var(--muted);
      font-weight: 800;
    }
    .secondary-nav a:hover {
      border-color: color-mix(in srgb, var(--accent) 42%, var(--line));
      background: color-mix(in srgb, var(--accent) 12%, var(--panel));
      color: var(--accent);
    }
    .quick {
      margin-top: 8px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
    }
    .quick button {
      height: auto;
      min-width: 0;
      min-height: 32px;
      padding: 6px 8px;
      color: var(--ink);
      background: var(--panel);
      border: 0;
      border-radius: var(--ui-radius);
      text-align: center;
      font-weight: 600;
      font-size: 12px;
      line-height: 1.25;
      white-space: normal;
      word-break: break-word;
    }
    .quick button:hover,
    .plugin-mgr button:hover {
      background: color-mix(in srgb, var(--accent) 10%, var(--panel));
      color: var(--accent);
    }
    .live2d-viewer-link {
      display: inline-block;
      margin: 6px 0;
      color: var(--accent) !important;
      font-size: 12px;
      font-weight: 650;
      text-decoration: none;
    }
    .preview {
      max-width: min(420px, 92%);
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      padding: 8px;
      align-self: flex-start;
    }
    .preview img {
      display: block;
      max-width: 100%;
      max-height: 320px;
      object-fit: contain;
    }

    /* Focus the chat workspace; contextual controls remain available on demand. */
    aside {
      background: var(--panel);
      padding: calc(18px * var(--density-scale));
    }
    main { grid-template-rows: auto 84px minmax(0, 1fr) auto auto; }
    header {
      padding: calc(14px * var(--density-scale)) calc(28px * var(--density-scale));
      background: var(--bg);
    }
    .avatar-stage {
      grid-template-columns: 64px minmax(0, 1fr) minmax(220px, 320px);
      min-height: var(--avatar-height);
      gap: 12px;
      padding: 8px calc(28px * var(--density-scale));
      background: transparent;
    }
    .avatar { width: 58px; height: 58px; }
    .live2d-frame { width: 64px; height: 64px; }
    .avatar .head { left: 10px; top: 6px; width: 40px; height: 38px; border-width: 2px; }
    .avatar .hair { left: 7px; top: 3px; width: 44px; height: 24px; }
    .avatar .body { left: 15px; top: 41px; width: 31px; height: 19px; border-width: 2px; }
    .avatar .eye { top: 22px; width: 5px; height: 7px; }
    .avatar .eye.left { left: 22px; }
    .avatar .eye.right { right: 22px; }
    .avatar .mouth { left: 27px; top: 32px; width: 8px; height: 4px; border-bottom-width: 2px; }
    #chat {
      width: min(880px, 100%);
      margin: 0 auto;
      padding: calc(26px * var(--density-scale)) calc(24px * var(--density-scale));
    }
    .msg { max-width: min(720px, 92%); box-shadow: none; }
    .assistant { background: transparent; }
    form {
      padding: 12px max(calc(28px * var(--density-scale)), calc((100vw - 880px) / 2));
      background: var(--bg);
    }
    textarea { min-height: 54px; }
    .sidebar-section-label {
      margin: 20px 10px 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
    }
    .secondary-nav { margin: 0 0 16px; padding: 0; }
    .secondary-nav a { background: transparent; font-size: 13px; font-weight: 650; }
    .secondary-nav a::after { content: ""; }
    .sidebar-context { margin: 16px 0; }
    .sidebar-context > summary {
      cursor: pointer;
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      list-style: none;
    }
    .sidebar-context > summary::-webkit-details-marker { display: none; }
    .sidebar-context > summary::after { content: "+"; float: right; color: var(--muted); font-size: 16px; font-weight: 400; }
    .sidebar-context[open] > summary::after { content: "-"; }
    .sidebar-context-body { padding-top: 12px; }
    .composer-tools,
    .realtime-options { border: 0; }
    .composer-tools summary,
    .realtime-options summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      list-style: none;
    }
    .composer-tools summary::-webkit-details-marker,
    .realtime-options summary::-webkit-details-marker { display: none; }
    .composer-tools summary::before { content: "+ "; color: var(--accent); font-size: 15px; }
    .realtime-options summary::before { content: "◉ "; color: var(--accent-2); }
    .composer-resources { display: grid; gap: 8px; padding-top: 8px; }
    main { grid-template-rows: auto var(--avatar-height) minmax(0, 1fr) auto auto; }
    .avatar-stage { display: grid; }
    #welcome-message {
      display: block;
      max-width: 640px;
      margin-top: 18px;
      padding: 0;
      line-height: 1.7;
    }
    #welcome-message::before {
      content: "Companion";
      display: block;
      margin-bottom: 8px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
    }
    form { display: block; padding: 14px 24px 12px; }
    .inputs { width: min(760px, 100%); margin: 0 auto; gap: 7px; }
    .voice-input-row {
      align-items: flex-end;
      gap: 6px;
      padding: 8px;
      border: 1px solid color-mix(in srgb, var(--accent) 36%, var(--line));
      border-radius: calc(var(--ui-radius) + 2px);
      background: var(--panel);
    }
    .voice-input-row textarea {
      min-height: 48px;
      padding: 7px 8px;
      background: transparent;
    }
    .voice-input-row button,
    #send {
      align-self: flex-end;
      width: 38px;
      min-width: 38px;
      height: 36px;
      min-height: 36px;
      padding: 0;
      border-radius: 6px;
    }
    .voice-input-row .realtime-voice-btn { width: 38px; min-width: 38px; }
    #send { width: 74px; min-width: 74px; font-size: 12px; }
    .composer-tools,
    .realtime-options { padding-left: 4px; }
    .suggestions-panel {
      width: min(760px, 100%);
      margin: 0 auto 10px;
    }
    .suggestions-panel > summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      list-style: none;
    }
    .suggestions-panel > summary::-webkit-details-marker { display: none; }
    .suggestions-panel > summary::before { content: "+ "; color: var(--accent); font-size: 15px; }
    .suggestions {
      max-height: none;
      padding: 8px 0 0;
      background: transparent;
    }
    body { grid-template-columns: 232px minmax(0, 1fr); }
    aside { padding: 22px 16px; }
    .sidebar-brand { display: flex; align-items: center; gap: 10px; margin: 2px 10px 30px; font-size: 16px; }
    .sidebar-brand-mark { display: grid; width: 28px; height: 28px; place-items: center; border-radius: 8px; background: var(--accent); color: #fff; font-size: 12px; }
    .sidebar-section-label { margin-top: 0; }
    .secondary-nav { gap: 4px; }
    .secondary-nav a { min-height: 38px; padding: 8px 12px; }
    .secondary-nav a.active { background: color-mix(in srgb, var(--accent) 12%, var(--panel)); color: var(--accent); font-weight: 750; }
    main {
      grid-template-columns: minmax(0, 1fr) 276px;
      grid-template-rows: auto minmax(0, 1fr) auto auto;
      column-gap: 24px;
      padding: 0 28px;
    }
    header { grid-column: 1 / -1; margin: 0 -28px; padding-left: 28px; padding-right: 28px; }
    .avatar-stage { display: none; }
    #chat, form, .suggestions-panel { grid-column: 1; }
    .realtime-pet-chat { display: none !important; }
    #chat { grid-row: 2; width: min(760px, 100%); margin-left: 0; padding-left: 16px; }
    form { grid-row: 3; padding-left: 0; padding-right: 0; }
    .suggestions-panel { grid-row: 4; margin-left: 0; }
    .context-rail { grid-column: 2; grid-row: 2 / 5; padding-top: 18px; min-width: 0; overflow: auto; }
    .context-rail .sidebar-context { display: block; margin: 0; }
    .context-rail .sidebar-context > summary { font-size: 14px; }
    .context-rail .sidebar-context-body { padding-top: 16px; }
    .context-rail .memory-orbit { min-height: 150px; margin-bottom: 12px; background: var(--panel-soft); }
    .context-rail .memory-brain { width: 96px; height: 80px; }
    .context-rail .memory { max-height: 92px; overflow: auto; padding: 10px; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .context-rail .growth-panel, .context-rail .files { margin-top: 12px; }
    .companion-visual { display: grid; gap: 10px; min-height: 292px; margin-top: 22px; }
    .companion-visual-tabs { display: inline-flex; justify-self: start; gap: 4px; padding: 3px; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .companion-visual-tabs button { width: auto; min-width: 0; height: 28px; min-height: 28px; padding: 0 10px; border-radius: max(2px, calc(var(--ui-radius) - 2px)); background: transparent; color: var(--muted); font-size: 12px; }
    .companion-visual-tabs button.active { background: var(--panel); color: var(--ink); box-shadow: 0 1px 3px rgba(12, 18, 28, .08); }
    .companion-visual-stage { min-height: 252px; overflow: hidden; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .companion-visual-stage iframe { display: block; width: 100%; height: 252px; border: 0; background: transparent; }
    .companion-visual-stage .live2d-frame { display: block; width: 100%; height: 252px; mix-blend-mode: normal; }

    /* SVG home reference layout: quiet navigation, open chat reading area, right-side companion stage. */
    body {
      grid-template-columns: 232px minmax(0, 1fr);
      background: var(--bg);
    }
    aside {
      display: flex;
      flex-direction: column;
      min-height: 0;
      padding: 24px 16px;
      background: var(--panel);
      border-right: 0;
    }
    .sidebar-brand {
      min-height: 34px;
      margin: 0 6px 28px;
      gap: 12px;
      color: var(--ink);
      font-size: 17px;
      font-weight: 750;
    }
    .sidebar-brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 9px;
      object-fit: cover;
      background: var(--accent);
    }
    .new-chat-btn {
      align-self: stretch;
      width: auto;
      min-width: 0;
      height: 38px;
      margin: 0 0 26px;
      border-radius: var(--ui-radius);
      background: var(--accent);
      color: #fff;
      font-size: 13px;
      font-weight: 750;
    }
    .sidebar-section-label {
      margin: 0 8px 9px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 750;
    }
    .secondary-nav {
      display: grid;
      gap: 4px;
      margin: 0 0 34px;
      padding: 0;
    }
    .secondary-nav a {
      min-height: 42px;
      padding: 0 12px;
      border-radius: var(--ui-radius);
      background: transparent;
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
    }
    .secondary-nav a.active {
      background: color-mix(in srgb, var(--accent) 12%, var(--panel));
      color: var(--accent);
      font-weight: 750;
    }
    .secondary-nav a.active::before {
      content: "";
      width: 12px;
      height: 12px;
      margin-right: 10px;
      border-radius: 50%;
      background: var(--accent);
    }
    .recent-chat-list {
      display: grid;
      gap: 7px;
      margin-bottom: 16px;
    }
    .recent-chat {
      width: 100%;
      min-width: 0;
      height: auto;
      min-height: 39px;
      padding: 9px 16px;
      border-radius: var(--ui-radius);
      background: transparent;
      color: var(--muted);
      text-align: left;
      font-size: 13px;
      font-weight: 500;
      line-height: 1.35;
    }
    .recent-chat.active {
      min-height: 57px;
      background: var(--panel-soft);
      color: var(--ink);
      font-weight: 650;
    }
    .recent-chat span,
    .recent-chat small {
      display: block;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .recent-chat small {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }
    .recent-chat-empty {
      padding: 10px 16px;
      color: var(--muted);
      font-size: 12px;
    }
    .command-section,
    #plugin-buttons,
    .plugin-mgr,
    .live2d-viewer-link,
    aside .notice {
      display: none;
    }
    main {
      grid-template-columns: minmax(580px, 1fr) minmax(294px, 336px);
      grid-template-rows: 68px minmax(0, 1fr) auto auto;
      column-gap: 34px;
      padding: 0 32px;
      background: var(--bg);
    }
    header {
      grid-column: 1 / -1;
      min-height: 68px;
      margin: 0 -32px;
      padding: 0 40px;
      background: var(--panel);
      border-bottom: 0;
    }
    h1 {
      font-size: 16px;
      font-weight: 750;
      line-height: 1.2;
    }
    h1::after {
      content: "私密对话 · 本地保存";
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }
    .header-tools {
      margin-right: 60px;
      gap: 14px;
    }
    #status::before {
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 8px;
      border-radius: 50%;
      background: var(--accent-2);
      vertical-align: -1px;
    }
    .language-select {
      display: none;
    }
    .settings-btn {
      top: 18px;
      right: 40px;
      width: 89px;
      height: 32px;
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--ink);
      font-size: 0;
    }
    .settings-btn::before {
      content: "...";
      font-size: 18px;
      line-height: 1;
    }
    .avatar-stage {
      display: none;
    }
    #chat {
      grid-column: 1;
      grid-row: 2;
      width: min(760px, 100%);
      margin: 0 auto;
      padding: 36px 0 28px;
      gap: 22px;
    }
    .msg {
      max-width: min(720px, 100%);
      padding: 0;
      border-radius: 0;
      background: transparent;
      box-shadow: none;
      color: var(--ink);
      font-size: 15px;
      line-height: 1.7;
    }
    .msg.assistant {
      display: grid;
      grid-template-columns: 40px minmax(0, 1fr);
      column-gap: 14px;
      align-self: flex-start;
    }
    .msg.assistant::before {
      content: "";
      grid-column: 1;
      grid-row: 1 / span 2;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 36% 38%, var(--accent) 0 2px, transparent 3px),
        radial-gradient(circle at 64% 38%, var(--accent) 0 2px, transparent 3px),
        linear-gradient(var(--avatar), var(--avatar));
      box-shadow: inset 0 -12px 0 color-mix(in srgb, var(--accent) 10%, transparent);
    }
    .assistant-meta {
      grid-column: 2;
      grid-row: 1;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
    }
    .assistant-meta strong {
      display: block;
      margin-bottom: 2px;
      color: var(--ink);
      font-size: 14px;
      font-weight: 500;
    }
    .msg.assistant .tts-play-btn {
      grid-column: 2;
      grid-row: 1;
      justify-self: end;
      width: 28px;
      min-width: 28px;
      height: 28px;
      min-height: 28px;
      opacity: 0;
      pointer-events: none;
    }
    .msg.assistant:hover .tts-play-btn,
    .msg.assistant:focus-within .tts-play-btn {
      opacity: 1;
      pointer-events: auto;
    }
    .msg.assistant .msg-body {
      grid-column: 2;
      grid-row: 2;
      gap: 10px;
    }
    .msg.user {
      align-self: flex-end;
      max-width: min(390px, 70%);
      padding: 18px 24px;
      border-radius: var(--ui-radius);
      background: #eaf1ff;
      line-height: 1.65;
    }
    #welcome-message {
      margin-top: 42px;
    }
    #welcome-message::before {
      content: "";
      grid-column: 1;
      grid-row: 1 / span 2;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 36% 38%, var(--accent) 0 2px, transparent 3px),
        radial-gradient(circle at 64% 38%, var(--accent) 0 2px, transparent 3px),
        linear-gradient(var(--avatar), var(--avatar));
      box-shadow: inset 0 -12px 0 color-mix(in srgb, var(--accent) 10%, transparent);
    }
    .feedback {
      margin-left: 54px;
      gap: 10px;
    }
    .feedback button {
      min-width: 96px;
      height: 30px;
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--muted);
      font-size: 12px;
      box-shadow: none;
    }
    form {
      grid-column: 1;
      grid-row: 3;
      width: min(736px, 100%);
      margin: 0 auto 30px;
      padding: 0;
      background: transparent;
    }
    .inputs {
      width: 100%;
      gap: 8px;
    }
    .voice-input-row {
      min-height: 112px;
      /* Keep tools clear of the rounded corners when --ui-radius is large. */
      padding: 18px max(22px, calc(var(--ui-radius) * 0.55)) max(16px, calc(var(--ui-radius) * 0.55));
      border: 1.5px solid #b9cdf3;
      border-radius: var(--ui-radius);
      background: var(--panel);
      align-items: flex-end;
      flex-wrap: wrap;
      overflow: visible;
    }
    .voice-input-row textarea {
      flex-basis: 100%;
      min-height: 42px;
      padding: 0;
      background: transparent;
      font-size: 13px;
      border-radius: 0;
    }
    .voice-input-row button {
      background: transparent;
      color: var(--muted);
      font-size: 16px;
      border-radius: max(4px, min(12px, calc(var(--ui-radius) - 10px)));
    }
    .voice-input-row button:hover {
      background: var(--panel-soft);
      color: var(--ink);
    }
    #send {
      margin-left: auto;
      width: 68px;
      min-width: 68px;
      height: 24px;
      min-height: 24px;
      background: var(--accent);
      color: #fff;
      font-size: 11px;
      border-radius: max(4px, calc(var(--ui-radius) - 8px));
    }
    .suggestions-panel {
      display: none;
    }
    .composer-tools,
    .realtime-options {
      display: block;
      margin-top: 2px;
    }
    .composer-tools summary,
    .realtime-options summary {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 2px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      cursor: pointer;
      list-style: none;
    }
    .composer-tools summary::-webkit-details-marker,
    .realtime-options summary::-webkit-details-marker { display: none; }
    .composer-tools summary::before,
    .realtime-options summary::before {
      content: "+";
      margin-right: 6px;
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
    }
    .composer-tools[open] summary::before,
    .realtime-options[open] summary::before { content: "-"; }
    .composer-resources {
      display: grid;
      gap: 8px;
      margin-top: 8px;
      padding: 10px 12px;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
    }
    .composer-resources input[type="file"] {
      padding: 8px 10px;
      border-radius: max(4px, calc(var(--ui-radius) - 4px));
      background: var(--panel);
    }
    .realtime-options > div {
      margin-top: 8px;
      padding: 10px 12px;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
    }
    body.has-realtime-pet-chat main {
      grid-template-rows: 68px minmax(0, 1fr) auto auto;
    }
    body.has-realtime-pet-chat .avatar-stage {
      display: none !important;
    }
    .attach-btn {
      flex: 0 0 auto;
      width: 28px;
      min-width: 28px;
      height: 24px;
      min-height: 24px;
      padding: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      font-size: 15px;
      line-height: 1;
    }
    .attach-btn:hover,
    .attach-btn.has-file {
      background: var(--panel-soft);
      color: var(--accent);
    }
    .context-rail {
      grid-column: 2;
      grid-row: 2 / 5;
      display: flex;
      flex-direction: column;
      min-height: 0;
      padding: 34px 8px 12px 0;
      overflow: hidden;
    }
    .context-rail .sidebar-context {
      flex: 0 0 auto;
      margin: 0;
    }
    .context-rail .sidebar-context > summary {
      min-height: 32px;
      color: var(--ink);
      font-size: 16px;
      font-weight: 750;
    }
    .context-rail .sidebar-context > summary::after {
      content: "收起";
      color: var(--accent);
      font-size: 13px;
      font-weight: 500;
    }
    .context-rail .sidebar-context-body {
      display: grid;
      gap: 14px;
      padding-top: 24px;
    }
    .context-rail .memory-orbit {
      display: none;
    }
    .context-rail .memory-title {
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 750;
    }
    .context-rail .memory,
    .context-rail .files,
    .context-shortcuts {
      margin: 0;
      padding: 18px;
      border-radius: 8px;
      background: var(--panel-soft);
      color: var(--ink);
    }
    .context-rail .memory {
      max-height: 98px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.55;
    }
    .context-rail .growth-panel {
      display: none;
    }
    .context-rail .files {
      font-size: 13px;
    }
    .context-rail .files summary {
      min-height: 0;
      padding: 0;
      background: transparent;
      color: var(--muted);
      font-size: 11px;
      font-weight: 750;
    }
    .context-rail .files-body {
      margin-top: 12px;
    }
    .context-shortcuts {
      display: grid;
      gap: 12px;
      padding: 0;
      background: transparent;
    }
    .context-shortcuts button {
      width: 100%;
      min-width: 0;
      height: auto;
      min-height: 24px;
      padding: 0 18px;
      background: transparent;
      color: var(--muted);
      text-align: left;
      font-size: 12px;
      font-weight: 650;
    }
    .context-shortcuts button:hover {
      color: var(--accent);
      background: transparent;
    }
    .companion-visual {
      flex: 1 1 auto;
      min-height: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 10px;
      margin-top: 12px;
      overflow: hidden;
    }
    .companion-visual-tabs {
      justify-self: start;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
    }
    .companion-visual-tabs button {
      width: auto;
      min-width: 0;
      height: 28px;
      min-height: 28px;
      padding: 0 12px;
      border-radius: max(2px, calc(var(--ui-radius) - 2px));
      background: transparent;
      color: var(--muted);
      font-size: 12px;
    }
    .companion-visual-tabs button.active {
      background: var(--panel);
      color: var(--ink);
      box-shadow: 0 1px 3px rgba(12, 18, 28, .08);
    }
    .companion-visual-stage {
      min-height: 0;
      height: 100%;
      overflow: hidden;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
    }
    .companion-visual-stage iframe,
    .companion-visual-stage .live2d-frame {
      width: 100%;
      height: 100%;
      min-height: 0;
      border: 0;
      background: transparent;
      mix-blend-mode: normal;
    }
    .companion-visual-stage iframe[hidden] {
      display: none !important;
    }

    /* Quiet motion layer for the home chat surface. */
    :root {
      --motion-fast: 140ms;
      --motion-base: 220ms;
      --motion-slow: 360ms;
      --motion-ease: cubic-bezier(.22, 1, .36, 1);
    }
    @keyframes ui-fade-up {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes ui-fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes ui-pop-in {
      from { opacity: 0; transform: translateY(10px) scale(.985); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes ui-status-glow {
      0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent-2) 0%, transparent); }
      50% { box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent-2) 24%, transparent); }
    }
    @keyframes ui-stage-breathe {
      0%, 100% { filter: saturate(1) brightness(1); transform: scale(1); }
      50% { filter: saturate(1.04) brightness(1.015); transform: scale(1.008); }
    }
    aside,
    main,
    header {
      animation: ui-fade-in var(--motion-slow) var(--motion-ease) both;
    }
    main { animation-delay: 40ms; }
    header { animation-delay: 70ms; }
    .new-chat-btn,
    .secondary-nav a,
    .recent-chat,
    .settings-btn,
    .companion-visual-tabs button,
    .context-shortcuts button,
    .feedback button,
    .voice-input-row button,
    #send {
      transition:
        background var(--motion-fast) ease,
        color var(--motion-fast) ease,
        border-color var(--motion-fast) ease,
        box-shadow var(--motion-base) var(--motion-ease),
        transform var(--motion-base) var(--motion-ease),
        opacity var(--motion-fast) ease;
    }
    .new-chat-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 18px color-mix(in srgb, var(--accent) 28%, transparent);
    }
    .new-chat-btn:active,
    .secondary-nav a:active,
    .recent-chat:active,
    .settings-btn:active,
    .voice-input-row button:active,
    #send:active {
      transform: translateY(0) scale(.985);
    }
    .secondary-nav a:hover {
      background: color-mix(in srgb, var(--panel-soft) 86%, var(--panel));
      color: var(--ink);
      transform: translateX(2px);
    }
    .recent-chat:hover {
      background: color-mix(in srgb, var(--panel-soft) 88%, transparent);
      color: var(--ink);
      transform: translateX(2px);
    }
    .recent-chat.active {
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 70%, transparent);
    }
    .settings-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 14px rgba(12, 18, 28, .08);
    }
    #status::before {
      animation: ui-status-glow 2.4s ease-in-out infinite;
    }
    .msg.msg-enter {
      animation: ui-fade-up var(--motion-base) var(--motion-ease) both;
    }
    .msg.user.msg-enter {
      animation-name: ui-pop-in;
    }
    .msg.assistant .tts-play-btn {
      transition: opacity var(--motion-fast) ease, transform var(--motion-fast) ease, background var(--motion-fast) ease;
    }
    .msg.assistant:hover .tts-play-btn,
    .msg.assistant:focus-within .tts-play-btn {
      transform: translateY(-1px);
    }
    .voice-input-row {
      transition:
        border-color var(--motion-base) ease,
        box-shadow var(--motion-base) var(--motion-ease),
        background var(--motion-fast) ease,
        transform var(--motion-base) var(--motion-ease);
    }
    .voice-input-row:focus-within {
      border-color: color-mix(in srgb, var(--accent) 58%, #b9cdf3);
      box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 14%, transparent), 0 10px 28px rgba(39, 110, 241, .08);
      transform: translateY(-1px);
    }
    #send:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 16px color-mix(in srgb, var(--accent) 28%, transparent);
    }
    .companion-visual-stage {
      transition: box-shadow var(--motion-base) ease, transform var(--motion-base) var(--motion-ease);
      animation: ui-stage-breathe 5.6s ease-in-out infinite;
      transform-origin: center bottom;
    }
    .companion-visual-tabs button:hover {
      color: var(--ink);
      transform: translateY(-1px);
    }
    .companion-visual-tabs button.active {
      transition: background var(--motion-fast) ease, color var(--motion-fast) ease, box-shadow var(--motion-base) ease, transform var(--motion-base) ease;
    }
    .context-rail .memory,
    .context-rail .files {
      transition: transform var(--motion-base) var(--motion-ease), box-shadow var(--motion-base) ease;
    }
    .context-rail .memory:hover,
    .context-rail .files:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 18px rgba(12, 18, 28, .05);
    }
    .settings-overlay.open {
      animation: ui-fade-in 160ms ease both;
    }
    .settings-overlay.open .settings-panel {
      animation: ui-pop-in 220ms var(--motion-ease) both;
    }
    .settings-category-button,
    .theme-option,
    .settings-section button {
      transition: background var(--motion-fast) ease, color var(--motion-fast) ease, border-color var(--motion-fast) ease, transform var(--motion-fast) ease, box-shadow var(--motion-base) ease;
    }
    .settings-category-button:hover,
    .theme-option:hover,
    .settings-section button:hover {
      transform: translateY(-1px);
    }
    @media (prefers-reduced-motion: reduce) {
      *,
      *::before,
      *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
      .companion-visual-stage,
      #status::before {
        animation: none !important;
      }
      .voice-input-row:focus-within,
      .new-chat-btn:hover,
      .recent-chat:hover,
      .secondary-nav a:hover,
      #send:hover {
        transform: none !important;
      }
    }

    @media (max-width: 760px) {
      body { grid-template-columns: 1fr; }
      aside { display: none; }
      main { display: grid; grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr) auto auto; padding: 0; }
      header { margin: 0; padding-left: 14px; padding-right: 14px; }
      .context-rail { display: none; }
      #chat, form, .suggestions-panel { grid-column: 1; }
      body.has-realtime-pet-chat main { grid-template-rows: auto minmax(0, 1fr) auto auto; }
      body.has-realtime-pet-chat .avatar-stage { display: none !important; }
      .realtime-pet-chat { display: none !important; }
      .avatar { transform: scale(.86); }
      header { align-items: flex-start; flex-direction: column; }
      form { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
    .plugin-mgr { margin: 8px 0; font-size: 13px; border-top: 0; padding-top: 8px; }
    .plugin-mgr summary { cursor: pointer; font-weight: 600; color: var(--ink); padding: 4px 0; }
    .plugin-mgr button { width: auto; height: auto; min-width: 0; min-height: 28px; font-size: 12px; padding: 4px 10px; border: 0; border-radius: var(--ui-radius); background: var(--panel); color: var(--ink); cursor: pointer; font-weight: 650; line-height: 1.25; }
    .plugin-mgr button:hover { background: var(--panel-soft); }
    /* Settings modal */
    .settings-btn { position: absolute; top: 12px; right: 16px; width: 36px; height: 36px; border-radius: 50%; border: 0; background: transparent; cursor: pointer; font-size: 20px; color: var(--muted); display: flex; align-items: center; justify-content: center; }
    .settings-btn:hover { background: var(--panel-soft); color: var(--ink); }
    .settings-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.35); z-index: 1000; align-items: center; justify-content: center; padding: 24px; }
    .settings-overlay.open { display: flex; }
    .settings-panel { background: #fff; border-radius: 12px; width: min(1280px, calc(100vw - 48px)); max-height: calc(100vh - 48px); overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 18px 56px rgba(0,0,0,.22); }
    .settings-panel { background: var(--panel); color: var(--ink); border-radius: calc(var(--ui-radius) + 4px); }
    .settings-header { position: sticky; top: 0; z-index: 1; background: var(--panel); display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 22px 28px 16px; border-bottom: 0; }
    .settings-panel h2 { margin: 0; font-size: 21px; color: var(--ink); }
    .settings-subtitle { margin-top: 4px; color: var(--muted); font-size: 13px; }
    .settings-grid { min-height: 0; overflow: hidden; display: grid; grid-template-columns: 224px minmax(0, 1fr); }
    .settings-category-nav { min-width: 0; overflow: auto; padding: 18px 12px; background: var(--panel-soft); border-right: 1px solid var(--line); }
    .settings-category-group { display: grid; gap: 4px; margin-bottom: 18px; }
    .settings-category-group:last-child { margin-bottom: 0; }
    .settings-category-label { margin: 0 10px 5px; color: var(--muted); font-size: 11px; font-weight: 700; }
    .settings-category-button { display: flex; align-items: center; width: 100%; min-width: 0; height: 38px; margin: 0; padding: 0 10px; border: 0; border-radius: 6px; background: transparent; color: var(--ink); font-size: 13px; font-weight: 650; text-align: left; }
    .settings-category-button:hover { background: color-mix(in srgb, var(--accent) 8%, var(--panel)); color: var(--accent); }
    .settings-category-button.active { background: color-mix(in srgb, var(--accent) 12%, var(--panel)); color: var(--accent); font-weight: 750; }
    .settings-category-button.active::before { content: ""; width: 6px; height: 6px; margin-right: 9px; border-radius: 50%; background: var(--accent); }
    .settings-content { min-width: 0; overflow: auto; padding: 22px 28px 28px; display: grid; align-content: start; gap: 16px; }
    .settings-section { min-width: 0; padding: 20px; border: 1px solid color-mix(in srgb, var(--line) 72%, transparent); border-radius: var(--ui-radius); background: var(--panel); box-shadow: none; }
    .settings-section[hidden] { display: none !important; }
    .settings-section.settings-secondary-active { padding: 0; border: 0; border-radius: 0; background: transparent; }
    .settings-section.settings-secondary-active > h3 { display: none; }
    .settings-section h3 { margin: 0 0 10px; font-size: 15px; color: var(--ink); }
    .settings-section .status { max-width: 100%; font-size: 14px; margin: 6px 0 10px; line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; }
    .settings-section .status.ok { color: var(--good); }
    .settings-section .status.err { color: var(--bad); }
    .settings-section .status.loading { color: var(--muted); }
    .component-progress { display: none; margin: 10px 0; }
    .component-progress.open { display: block; }
    .component-progress-track { width: 100%; height: 8px; overflow: hidden; border-radius: 999px; background: var(--panel-soft); }
    .component-progress-bar { width: 0%; height: 100%; border-radius: inherit; background: #276ef1; transition: width .25s ease, background .2s ease; }
    .component-progress.err .component-progress-bar { background: var(--bad); }
    .component-progress.ok .component-progress-bar { background: var(--good); }
    .component-progress-text { margin-top: 6px; color: var(--muted); font-size: 13px; line-height: 1.4; }
    .component-progress.installing .component-progress-bar {
      width: 30%;
      transition: none;
      animation: progress-slide 1.4s ease-in-out infinite;
    }
    @keyframes progress-slide {
      0%   { transform: translateX(-110%); }
      50%  { transform: translateX(240%); }
      100% { transform: translateX(-110%); }
    }
    .settings-section button { width: auto; height: auto; min-width: 0; margin: 4px 6px 4px 0; padding: 8px 16px; font-size: 14px; font-weight: 600; border-radius: 6px; vertical-align: middle; }
    .settings-section button.danger { background: #c0392b; color: #fff; }
    .settings-section button.danger:hover { background: #a93226; }
    .settings-close { flex: 0 0 auto; width: 36px; height: 36px; border: 0; border-radius: 50%; background: transparent; font-size: 26px; cursor: pointer; color: var(--muted); padding: 0; line-height: 1; }
    .settings-close:hover { color: var(--ink); }
    .settings-section input, .settings-section textarea, .settings-section select {
      font-size: 14px;
      padding: 8px 12px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      margin-bottom: 8px;
      width: 100%;
      box-sizing: border-box;
      min-width: 0;
    }
    .settings-section input[type="checkbox"] {
      width: auto;
      margin-bottom: 0;
      padding: 0;
    }
    .settings-section textarea { min-height: 100px; resize: vertical; }
    .settings-section label { font-size: 13px; color: var(--muted); display: block; margin-bottom: 4px; }
    .settings-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; margin: 10px 0; }
    .settings-check { display: inline-flex !important; align-items: center; gap: 8px; margin: 0 !important; color: var(--ink) !important; cursor: pointer; }
    .settings-control-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 12px 0; }
    .settings-slider {
      display: grid;
      gap: 11px;
      margin: 12px 0;
      padding: 13px 14px 15px;
      border: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
      border-radius: calc(var(--ui-radius) + 2px);
      background: color-mix(in srgb, var(--panel-soft) 86%, var(--panel));
    }
    .settings-slider label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0;
      color: var(--ink);
      font-weight: 700;
    }
    .settings-slider label span:first-child {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .settings-slider-value {
      flex: 0 0 auto;
      min-width: 58px;
      padding: 3px 8px;
      border-radius: 999px;
      background: var(--panel);
      color: var(--accent);
      text-align: center;
      font-size: 12px;
      font-weight: 750;
      font-variant-numeric: tabular-nums;
    }
    .settings-slider input[type="range"] {
      --slider-progress: 50%;
      width: 100%;
      height: 18px;
      margin: 0;
      padding: 0;
      appearance: none;
      -webkit-appearance: none;
      background: transparent;
      cursor: pointer;
    }
    .settings-slider input[type="range"]::-webkit-slider-runnable-track {
      height: 8px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent) var(--slider-progress), color-mix(in srgb, var(--line) 68%, var(--panel)) var(--slider-progress));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 64%, transparent);
    }
    .settings-slider input[type="range"]::-webkit-slider-thumb {
      width: 20px;
      height: 20px;
      margin-top: -6px;
      border: 3px solid var(--panel);
      border-radius: 50%;
      appearance: none;
      -webkit-appearance: none;
      background: var(--accent);
      box-shadow: 0 5px 12px color-mix(in srgb, var(--accent) 28%, transparent);
    }
    .settings-slider input[type="range"]::-moz-range-track {
      height: 8px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--line) 68%, var(--panel));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 64%, transparent);
    }
    .settings-slider input[type="range"]::-moz-range-progress {
      height: 8px;
      border-radius: 999px;
      background: var(--accent);
    }
    .settings-slider input[type="range"]::-moz-range-thumb {
      width: 16px;
      height: 16px;
      border: 3px solid var(--panel);
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 5px 12px color-mix(in srgb, var(--accent) 28%, transparent);
    }
    .settings-slider input[type="range"]:focus-visible {
      outline: 2px solid color-mix(in srgb, var(--accent) 42%, transparent);
      outline-offset: 4px;
    }
    .theme-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(116px, 1fr)); gap: 8px; margin: 12px 0; }
    .theme-option { display: grid !important; grid-template-columns: auto 1fr; align-items: center; gap: 8px; min-height: 42px; padding: 8px 10px; border: 0; border-radius: var(--ui-radius); background: var(--panel-soft); color: var(--ink) !important; cursor: pointer; }
    .theme-option input { width: auto !important; margin: 0 !important; padding: 0 !important; }
    .theme-swatch { width: 24px; height: 24px; border-radius: 50%; border: 1px solid var(--line); background: linear-gradient(135deg, var(--swatch-a), var(--swatch-b)); }
    .custom-theme-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); gap: 10px; margin: 10px 0; padding: 12px; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .custom-theme-grid label { margin: 0; color: var(--ink); }
    .custom-theme-grid input[type="color"] { width: 100%; height: 34px; padding: 2px; margin: 4px 0 0; background: var(--panel); cursor: pointer; }
    .theme-preview { min-height: 112px; margin-top: 12px; padding: 13px; border: 0; border-radius: var(--ui-radius); background: var(--panel-soft); color: var(--ink); }
    .theme-preview strong { display: block; margin-bottom: 6px; color: var(--ink); }
    .theme-preview span { color: var(--muted); }
    .theme-preview-surface {
      display: grid;
      grid-template-columns: minmax(42px, var(--preview-sidebar-width, 72px)) minmax(0, 1fr);
      gap: calc(8px * var(--preview-density, 1));
      min-height: var(--preview-avatar-height, 84px);
      margin-top: 10px;
      padding: calc(9px * var(--preview-density, 1));
      border-radius: var(--preview-radius, var(--ui-radius));
      background: var(--panel);
      color: var(--ink);
      font-size: calc(13px * var(--preview-font-scale, 1));
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 68%, transparent);
    }
    .theme-preview-side,
    .theme-preview-main {
      min-width: 0;
      border-radius: max(4px, calc(var(--preview-radius, var(--ui-radius)) - 2px));
      background: var(--panel-soft);
    }
    .theme-preview-side { display: grid; gap: 6px; padding: 8px; align-content: start; }
    .theme-preview-side i,
    .theme-preview-line {
      display: block;
      height: 7px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--muted) 26%, transparent);
    }
    .theme-preview-side i:first-child { background: var(--accent); }
    .theme-preview-main { display: grid; gap: 8px; padding: 9px; align-content: center; }
    .theme-preview-line.strong { width: 64%; height: 10px; background: var(--ink); }
    .theme-preview-line.accent { width: 46%; background: var(--accent); }
    .settings-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .settings-note { font-size: 13px; color: var(--muted); line-height: 1.55; margin: 8px 0; overflow-wrap: anywhere; }
    .settings-page { display: none; }
    .settings-page.active { display: block; }
    .settings-page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
    .settings-page-back { background: var(--panel-soft) !important; color: var(--ink) !important; }
    .display-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin: 10px 0; }
    .display-summary-item { padding: 10px 12px; border-radius: var(--ui-radius); background: var(--panel-soft); min-width: 0; }
    .display-summary-label { display: block; color: var(--muted); font-size: 12px; line-height: 1.35; }
    .display-summary-value { display: block; margin-top: 4px; color: var(--ink); font-size: 14px; font-weight: 700; line-height: 1.35; overflow-wrap: anywhere; }
    .display-theme-entry { padding: 12px; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .display-theme-entry strong { display: block; color: var(--ink); margin-bottom: 5px; }
    .display-theme-entry span { color: var(--muted); font-size: 13px; line-height: 1.5; }
    .update-panel { display: flex; flex-direction: column; gap: 12px; }
    .update-page { display: none; }
    .update-page.active { display: block; }
    .update-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin: 10px 0; }
    .update-summary-item { padding: 10px 12px; border-radius: var(--ui-radius); background: var(--panel-soft); min-width: 0; }
    .update-summary-label { display: block; color: var(--muted); font-size: 12px; line-height: 1.35; }
    .update-summary-value { display: block; margin-top: 4px; color: var(--ink); font-size: 14px; font-weight: 700; line-height: 1.35; overflow-wrap: anywhere; }
    .update-release-card { padding: 12px; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .update-release-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; color: var(--ink); font-weight: 700; }
    .update-release-title span { min-width: 0; overflow-wrap: anywhere; }
    .update-pill { flex: 0 0 auto; padding: 2px 8px; border-radius: 999px; background: rgba(39, 110, 241, .12); color: var(--accent); font-size: 12px; font-weight: 700; }
    .update-meta { margin-top: 8px; color: var(--muted); font-size: 13px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
    .update-page-link { display: inline-flex; align-items: center; gap: 6px; margin-top: 10px; color: var(--accent) !important; background: transparent !important; padding: 0 !important; font-size: 13px !important; font-weight: 700 !important; }
    .update-page-link:hover { text-decoration: underline; }
    .update-detail-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
    .update-back-btn { background: var(--panel-soft) !important; color: var(--ink) !important; }
    .update-log-body { max-height: 380px; overflow: auto; padding: 14px; border-radius: var(--ui-radius); background: var(--panel-soft); color: var(--ink); font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; }
    .update-log-body h1, .update-log-body h2, .update-log-body h3 { margin: 12px 0 6px; color: var(--ink); line-height: 1.35; }
    .update-log-body h1 { font-size: 18px; }
    .update-log-body h2 { font-size: 16px; }
    .update-log-body h3 { font-size: 14px; }
    .update-log-body p { margin: 8px 0; }
    .update-log-body ul, .update-log-body ol { margin: 8px 0; padding-left: 20px; }
    .update-log-body li { margin: 4px 0; }
    .update-log-body code { padding: 1px 5px; border-radius: 4px; background: var(--panel); font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
    .update-log-body pre { margin: 10px 0; padding: 10px; border-radius: var(--ui-radius); background: var(--panel); overflow: auto; }
    .update-log-body pre code { padding: 0; background: transparent; }
    .update-log-body blockquote { margin: 8px 0; padding-left: 10px; border-left: 3px solid var(--line); color: var(--muted); }
    .update-log-body a { color: var(--accent); text-decoration: none; }
    .update-log-body a:hover { text-decoration: underline; }
    .update-log-empty { color: var(--muted); }
    .update-config { margin-top: 4px; }
    .face-register-row { display: grid; grid-template-columns: minmax(140px, 1fr) auto; gap: 8px; align-items: end; margin-top: 12px; }
    .face-register-row label { margin: 0; }
    .face-register-row input { margin-bottom: 0; }
    .face-actions, .face-install-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .face-actions button, .face-install-actions button { margin: 0; }
    .face-install-options { display: none; margin-top: 12px; padding: 12px; border-radius: var(--ui-radius); background: var(--panel-soft); }
    .face-install-title { font-size: 13px; color: var(--ink); margin-bottom: 8px; }
    .face-install-hint { font-size: 12px; color: var(--muted); line-height: 1.45; margin-top: 8px; }
    .face-list-item { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 6px 0; }
    .face-list-name { color: var(--ink); font-weight: 600; }
    .face-list-id { color: var(--muted); font-size: 11px; }
    .settings-panel .status,
    .settings-panel em,
    .settings-panel small,
    .settings-panel [id$="-detail"],
    .settings-panel [id$="-size"],
    .settings-panel [id$="-result"],
    .settings-panel [id$="-progress"],
    .settings-panel [id$="-summary"],
    .settings-panel #face-count,
    .settings-panel #audit-summary {
      color: var(--muted);
    }
    .settings-panel [style*="color:#657184"],
    .settings-panel [style*="color: #657184"],
    .settings-panel [style*="color:#243143"],
    .settings-panel [style*="color: #243143"],
    .settings-panel [style*="color:#1c2430"],
    .settings-panel [style*="color: #1c2430"],
    .settings-panel [style*="color:#425064"],
    .settings-panel [style*="color: #425064"],
    .settings-panel [style*="color:#6b7280"],
    .settings-panel [style*="color: #6b7280"],
    .settings-panel [style*="color:#9aa5b1"],
    .settings-panel [style*="color: #9aa5b1"],
    .settings-panel [style*="color:#9aa4b2"],
    .settings-panel [style*="color: #9aa4b2"] {
      color: var(--muted) !important;
    }
    .settings-panel [style*="color:#276ef1"],
    .settings-panel [style*="color: #276ef1"],
    .settings-panel [style*="color:#3498db"],
    .settings-panel [style*="color: #3498db"] {
      color: var(--accent) !important;
    }
    .settings-panel [style*="color:#0b7a55"],
    .settings-panel [style*="color: #0b7a55"] {
      color: var(--good) !important;
    }
    .settings-panel [style*="color:#c0392b"],
    .settings-panel [style*="color: #c0392b"] {
      color: var(--bad) !important;
    }
    .settings-panel h3,
    .settings-panel label,
    .settings-panel strong,
    .settings-panel #face-list,
    .settings-panel .theme-option span {
      color: var(--ink) !important;
    }
    .settings-panel [style*="background:#f5f7fa"],
    .settings-panel [style*="background: #f5f7fa"],
    .settings-panel [style*="background:#e8edf5"],
    .settings-panel [style*="background: #e8edf5"] {
      background: var(--panel-soft) !important;
    }
    .settings-panel [style*="border-bottom"] {
      border-bottom: 0 !important;
    }
    .settings-panel button:disabled,
    .settings-section button:disabled {
      opacity: .82;
      color: #ffffff;
    }
    .settings-clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    #sec-audit, #sec-remote-llm, #sec-ai-plugin,
    #sec-display, #sec-update { grid-column: 1 / -1; }
    #sec-display, #sec-update { order: 10; }
    #sec-audit > div[style*="grid-template-columns"],
    #sec-remote-llm > div[style*="grid-template-columns"] { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)) !important; }
    #sec-ai-plugin textarea { min-height: 160px; font-family: Consolas, "Cascadia Mono", monospace; }
    @media (max-width: 760px) {
      .settings-overlay { padding: 10px; }
      .settings-panel { width: calc(100vw - 20px); max-height: calc(100vh - 20px); }
      .settings-header { padding: 16px 18px 12px; }
      .settings-grid { grid-template-columns: 1fr; overflow: auto; }
      .settings-category-nav { display: flex; gap: 8px; overflow-x: auto; padding: 10px 14px; border-right: 0; border-bottom: 1px solid var(--line); }
      .settings-category-group { display: contents; margin: 0; }
      .settings-category-label { display: none; }
      .settings-category-button { flex: 0 0 auto; width: auto; padding: 0 12px; background: var(--panel); }
      .settings-category-button.active::before { display: none; }
      .settings-content { overflow: visible; padding: 14px 18px 18px; gap: 12px; }
      #sec-audit > div[style*="grid-template-columns"],
      #sec-remote-llm > div[style*="grid-template-columns"] { grid-template-columns: 1fr !important; }
      .settings-control-grid { grid-template-columns: 1fr; }
      .face-register-row { grid-template-columns: 1fr; }
      .settings-section button { width: 100%; margin: 4px 0; }
      .face-actions button, .face-install-actions button { width: 100%; }
      .settings-actions { flex-direction: column; }
      .settings-actions button { width: 100%; }
      .voice-input-row { align-items: stretch; }
      .voice-btn { height: auto; }
    }
    /* Correction modal */
    .correct-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 1100; align-items: center; justify-content: center; }
    .correct-overlay.open { display: flex; }
    .correct-panel { background: #fff; border-radius: 12px; width: 440px; max-width: 92vw; padding: 24px; box-shadow: 0 8px 32px rgba(0,0,0,.2); }
    .correct-panel h3 { margin: 0 0 6px; font-size: 16px; color: #243143; }
    .correct-panel .correct-prompt { font-size: 13px; color: #657184; margin-bottom: 12px; word-break: break-all; }
    .correct-panel .correct-response { font-size: 13px; color: #c0392b; margin-bottom: 12px; padding: 8px 10px; background: #fef5f5; border-radius: 6px; word-break: break-all; }
    .correct-panel label { font-size: 13px; font-weight: 600; color: #243143; display: block; margin-bottom: 6px; }
    .correct-panel textarea { min-height: 90px; margin-bottom: 14px; }
    .correct-panel .correct-actions { display: flex; gap: 10px; justify-content: flex-end; }
    .correct-panel .correct-actions button { padding: 8px 20px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .correct-panel .correct-actions .cancel-btn { background: #e8edf5; color: #263244; border: 0; }
    .correct-panel .correct-actions .submit-btn { background: #3b82f6; color: #fff; border: 0; }
    .correct-panel .correct-actions .submit-btn:hover { background: #2563eb; }
    /* Prompt suggestions */
    .suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      max-height: 54px;
      overflow: auto;
      padding: 7px 14px;
      background: var(--panel);
      border-top: 0;
    }
    .suggestion-chip {
      padding: 5px 10px;
      border-radius: 13px;
      border: 0;
      background: var(--panel-soft);
      color: var(--ink);
      font-size: 12px;
      cursor: pointer;
      white-space: nowrap;
      transition: background 0.15s, border-color 0.15s;
    }
    .suggestion-chip:hover {
      background: color-mix(in srgb, var(--accent) 12%, var(--panel));
      border-color: transparent;
      color: var(--accent);
    }
    .suggestion-chip.command {
      color: var(--muted);
      font-family: monospace;
      font-size: 11px;
    }
    /* Onboarding modal */
    .onboarding-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 2000; display: flex; align-items: center; justify-content: center; }
    .onboarding-overlay.hidden { display: none; }
    .onboarding-panel { background: #fff; border-radius: 16px; width: 520px; max-width: 94vw; max-height: 90vh; overflow-y: auto; padding: 32px; box-shadow: 0 12px 48px rgba(0,0,0,.25); }
    .onboarding-panel h2 { margin: 0 0 6px; font-size: 22px; color: #1c2430; }
    .onboarding-panel .subtitle { font-size: 14px; color: #657184; margin-bottom: 24px; }
    .onboarding-panel .form-group { margin-bottom: 18px; }
    .onboarding-panel label { display: block; font-size: 13px; font-weight: 600; color: #243143; margin-bottom: 6px; }
    .onboarding-panel label .optional { font-weight: 400; color: #657184; font-size: 12px; }
    .onboarding-panel input, .onboarding-panel textarea, .onboarding-panel select {
      width: 100%; border: 1px solid #d9dee7; border-radius: 8px; font: inherit; padding: 10px 12px; font-size: 14px;
    }
    .onboarding-panel input:focus, .onboarding-panel textarea:focus { border-color: #276ef1; outline: none; box-shadow: 0 0 0 3px rgba(39,110,241,.12); }
    .onboarding-panel textarea { min-height: 80px; resize: vertical; }
    .onboarding-panel .id-row { display: flex; gap: 8px; }
    .onboarding-panel .id-row input { flex: 1; }
    .onboarding-panel .id-row button { white-space: nowrap; padding: 10px 16px; background: #e8edf5; color: #276ef1; border: 0; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .onboarding-panel .id-row button:hover { background: #d5ddef; }
    .onboarding-panel .gender-row { display: flex; gap: 12px; }
    .onboarding-panel .gender-row label { display: flex; align-items: center; gap: 6px; font-weight: 400; cursor: pointer; }
    .onboarding-panel .gender-row input[type="radio"] { width: auto; }
    .onboarding-panel .actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }
    .onboarding-panel .actions button { padding: 12px 28px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: 0; }
    .onboarding-panel .actions .skip-btn { background: #e8edf5; color: #263244; }
    .onboarding-panel .actions .submit-btn { background: #276ef1; color: #fff; }
    .onboarding-panel .actions .submit-btn:hover { background: #1e5bd6; }
    .onboarding-panel .actions .submit-btn:disabled { opacity: .5; cursor: wait; }
    .onboarding-panel .persona-hints { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .onboarding-panel .persona-hint { padding: 4px 10px; border-radius: 12px; border: 1px solid #d9dee7; background: #f5f7fa; font-size: 12px; cursor: pointer; color: #263244; }
    .onboarding-panel .persona-hint:hover { background: #e8edf5; border-color: #276ef1; }
    .onboarding-panel .persona-note { margin-top: 6px; font-size: 12px; color: #657184; line-height: 1.5; }
    /* Guided tour overlay */
    .tour-overlay { position: fixed; inset: 0; z-index: 5000; pointer-events: none; }
    .tour-overlay.hidden { display: none; }
    .tour-highlight { position: fixed; display: none; border: 2px solid var(--accent); border-radius: 10px; box-shadow: 0 0 0 9999px rgba(12, 18, 28, .68), 0 0 0 5px rgba(39, 110, 241, .2); pointer-events: none; transition: left .18s ease, top .18s ease, width .18s ease, height .18s ease; }
    .tour-tooltip { position: fixed; z-index: 2; width: min(360px, calc(100vw - 32px)); padding: 18px; border: 1px solid rgba(24, 36, 52, .12); border-radius: 8px; background: var(--panel); color: var(--ink); box-shadow: 0 18px 50px rgba(12, 18, 28, .28); pointer-events: auto; }
    .tour-kicker { margin: 0 0 8px; color: var(--accent); font-size: 12px; font-weight: 750; }
    .tour-tooltip h3 { margin: 0 0 8px; font-size: 18px; line-height: 1.25; }
    .tour-tooltip p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
    .tour-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 18px; }
    .tour-progress { display: flex; gap: 5px; }
    .tour-dot { width: 6px; height: 6px; border-radius: 50%; background: color-mix(in srgb, var(--ink) 18%, transparent); }
    .tour-dot.active { width: 20px; border-radius: 4px; background: var(--accent); }
    .tour-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
    .tour-actions button { min-width: 0; height: 34px; padding: 0 12px; border: 0; border-radius: 6px; font-size: 13px; font-weight: 700; cursor: pointer; }
    .tour-actions .tour-skip, .tour-actions .tour-prev { background: transparent; color: var(--muted); }
    .tour-actions .tour-prev[disabled] { visibility: hidden; }
    .tour-actions .tour-next { background: var(--accent); color: #fff; }
    .tour-actions .tour-next:hover { background: color-mix(in srgb, var(--accent) 86%, #000); }
    @media (max-width: 760px) { .tour-tooltip { left: 16px !important; right: 16px; bottom: 16px; top: auto !important; width: auto; } .tour-highlight { border-radius: 8px; } }
    /* Privacy consent modal */
    .privacy-overlay { position: fixed; inset: 0; z-index: 3000; display: flex; align-items: center; justify-content: center; padding: 20px; background: rgba(17, 24, 39, .62); }
    .privacy-overlay.hidden { display: none; }
    .privacy-panel { width: min(760px, 96vw); max-height: 92vh; overflow: hidden; display: flex; flex-direction: column; border-radius: 14px; background: #fff; box-shadow: 0 20px 60px rgba(0,0,0,.28); }
    .privacy-header { padding: 24px 28px 16px; border-bottom: 1px solid #edf0f5; }
    .privacy-header h2 { margin: 0 0 6px; color: #1c2430; font-size: 23px; }
    .privacy-header p { margin: 0; color: #657184; font-size: 14px; line-height: 1.5; }
    .privacy-body { padding: 20px 28px; overflow: auto; color: #263244; line-height: 1.65; }
    .privacy-body h3 { margin: 18px 0 8px; font-size: 15px; color: #1c2430; }
    .privacy-body h3:first-child { margin-top: 0; }
    .privacy-body ul { margin: 0 0 12px 18px; padding: 0; }
    .privacy-body li { margin: 6px 0; }
    .privacy-actions { padding: 16px 28px 24px; border-top: 1px solid #edf0f5; background: #fbfcfe; }
    .privacy-check { display: flex; align-items: flex-start; gap: 10px; color: #243143; font-size: 14px; line-height: 1.5; cursor: pointer; }
    .privacy-check input { width: auto; margin-top: 3px; flex: 0 0 auto; }
    .privacy-submit { margin-top: 14px; width: 100%; height: 44px; border-radius: 8px; }
    .privacy-submit:disabled { cursor: not-allowed; opacity: .5; }

    /* Keep the display controls effective where legacy component rules use fixed values. */
    body :is(
      button:not(.settings-btn, .settings-close, .attach-btn, .voice-btn, .realtime-voice-btn, .wake-word-btn, #send),
      input:not([type="range"], [type="radio"], [type="checkbox"], [type="color"]),
      textarea:not(#message),
      select,
      .msg,
      .notice,
      .files summary,
      .file-card,
      .memory-orbit,
      .memory-node,
      .realtime-pet-chat,
      .realtime-pet-line,
      .learning-record,
      .emotion-meta,
      .emotion-toggle,
      .msg.user,
      .new-chat-btn,
      .recent-chat,
      .secondary-nav a,
      .companion-visual-tabs,
      .companion-visual-tabs button,
      .preview,
      .companion-visual-stage,
      .voice-input-row,
      .composer-resources,
      .realtime-options > div,
      .settings-panel,
      .settings-section,
      .settings-category-button,
      .settings-slider,
      .theme-option,
      .custom-theme-grid,
      .theme-preview,
      .display-summary-item,
      .display-theme-entry,
      .update-summary-item,
      .update-release-card,
      .update-log-body,
      .correct-panel,
      .onboarding-panel,
      .tour-highlight,
      .tour-tooltip,
      .privacy-panel
    ) {
      border-radius: var(--ui-radius) !important;
    }
    /* Composer shell tracks radius; nested controls stay quieter so large radius does not occlude tools. */
    body .voice-input-row textarea,
    body .voice-input-row #message {
      border-radius: 0 !important;
    }
    body .voice-input-row button,
    body .voice-input-row #send,
    body .voice-input-row .attach-btn,
    body .voice-input-row .voice-btn,
    body .voice-input-row .realtime-voice-btn,
    body .voice-input-row .wake-word-btn {
      border-radius: max(4px, min(12px, calc(var(--ui-radius) - 10px))) !important;
    }
    /* The compact desktop workspace must still honor the display controls. */
    @media (min-width: 761px) {
      body { grid-template-columns: var(--sidebar-width) minmax(0, 1fr); }
      .chat-nav { display: grid; gap: 4px; margin: 0 0 24px; }
      .chat-nav a {
        display: flex;
        align-items: center;
        min-height: 42px;
        padding: 0 12px;
        border-radius: var(--ui-radius);
        color: var(--muted);
        font-size: 14px;
        font-weight: 500;
        text-decoration: none;
      }
      .chat-nav a.active {
        background: color-mix(in srgb, var(--accent) 12%, var(--panel));
        color: var(--accent);
        font-weight: 750;
      }
      .chat-nav a.active::before {
        content: "";
        width: 12px;
        height: 12px;
        margin-right: 10px;
        border-radius: 50%;
        background: var(--accent);
      }
      main { grid-template-rows: 68px minmax(0, 1fr) auto auto; }
      .avatar-stage { display: none !important; }
      #chat { grid-row: 2; }
      form { grid-row: 3; }
      .suggestions-panel { grid-row: 4; }
      .context-rail { grid-row: 2 / 5; }
    }

    /* Assistant messages keep their metadata close to the content. */
    .msg.assistant {
      grid-template-columns: 32px minmax(0, 1fr);
      column-gap: 10px;
      row-gap: 3px;
      padding: 8px 0;
    }
    .msg.assistant::before,
    #welcome-message::before {
      width: 32px;
      height: 32px;
      grid-column: 1;
      grid-row: 1;
    }
    .assistant-meta {
      grid-column: 2;
      grid-row: 1;
      align-self: center;
    }
    .msg.assistant .msg-body,
    #welcome-message .msg-body {
      grid-column: 2;
      grid-row: 2;
      margin: 0;
      gap: 4px;
    }
    #welcome-message {
      display: grid;
      grid-template-columns: 32px minmax(0, 1fr);
      margin-top: 16px;
      align-items: start;
    }
  </style>
</head>
<body>
  <!-- Privacy Consent Modal -->
  <div class="privacy-overlay hidden" id="privacy-overlay">
    <div class="privacy-panel" role="dialog" aria-modal="true" aria-labelledby="privacy-title">
      <div class="privacy-header">
        <h2 id="privacy-title">隐私政策与本地数据说明</h2>
        <p>请先阅读并同意后再使用 Companion AI。不同意时，本页的聊天、上传、视觉观察等功能不会启用。</p>
        <div class="privacy-update-notice" id="privacy-update-notice" style="display: none; margin-top: 10px; padding: 10px; background: #fff7ed; border-radius: 6px; border-left: 3px solid #f97316; color: #c2410c; font-size: 13px;">
          警告：隐私政策已更新，请重新阅读并同意。
        </div>
      </div>
      <div class="privacy-body">
        <h3>1. 本应用会处理哪些数据</h3>
        <ul>
          <li>你在聊天框输入的内容、反馈、纠正答案、训练样本和长期记忆。</li>
          <li>你主动上传的文件、图片、网页 URL，以及由本地 OCR/文件解析得到的摘要。</li>
          <li>你主动点击或开启后产生的屏幕观察、摄像头观察、作息记录、电脑操作学习记录。</li>
          <li>你设置的 AI 身份、人设、桌宠显示、语音和插件配置。</li>
        </ul>
        <h3>2. 数据如何保存和使用</h3>
        <ul>
          <li>默认保存在本机应用数据目录，用于本地对话、记忆、自训练、文件回顾和桌宠体验。</li>
          <li>屏幕、摄像头和文件能力只在你触发或开启对应功能时使用，不会自动绕过系统权限。</li>
          <li>你可以在应用内查看、纠正、删除部分训练样本，也可以通过本地数据文件管理更多记录。</li>
        </ul>
        <h3>3. 网络和第三方服务</h3>
        <ul>
          <li>核心对话优先本地运行；天气、网页读取、组件安装、可选审计或语音等功能可能访问外部服务。</li>
          <li>外部服务只在你使用相应功能或填写相关配置后才会被调用。</li>
          <li>AI 可在 WiFi 或家庭网络环境下自主联网学习，无需额外同意，用于获取最新信息和提升对话能力。</li>
          <li>联网学习默认仅在 WiFi 环境下进行，你可以通过 /learn_on 和 /learn_off 控制开关。</li>
        </ul>
        <h3>4. 你的选择</h3>
        <ul>
          <li>同意后才可以继续使用本应用。不同意可以直接关闭页面或应用。</li>
          <li>如需撤回同意，可删除本地数据目录中的 privacy_consent.json，重新打开后会再次询问。</li>
        </ul>
      </div>
      <div class="privacy-actions">
        <label class="privacy-check">
          <input type="checkbox" id="privacy-checkbox" />
          <span>我已阅读并同意上述隐私政策，理解本应用会在本机保存和处理我主动提供或开启功能后产生的数据。</span>
        </label>
        <button type="button" class="privacy-submit" id="privacy-submit" disabled>同意并开始使用</button>
      </div>
    </div>
  </div>

  <!-- Onboarding Modal -->
  <div class="onboarding-overlay hidden" id="onboarding-overlay">
    <div class="onboarding-panel">
      <h2>欢迎来到 Companion AI</h2>
      <p class="subtitle">为你的 AI 桌宠设置身份信息，让它更有个性。</p>
      
      <div class="form-group">
        <label>姓名 <span class="optional">（必填）</span></label>
        <input type="text" id="ob-name" placeholder="给这个角色起个名字" maxlength="20" />
      </div>

      <div class="form-group">
        <label>关系类型</label>
        <select id="ob-relationship">
          <option value="friend" selected>朋友：从陌生到默契，也可能发展到恋人</option>
          <option value="family">家人：从被照顾到反过来关心</option>
          <option value="partner">搭档：一起推进目标</option>
          <option value="guardian">守护者：关心作息和状态</option>
          <option value="lifeform">虚拟生命：从空白程序形成独特痕迹</option>
          <option value="custom">自定义关系</option>
        </select>
      </div>
      <div class="form-group" id="ob-relationship-subtype-group" style="display: none;">
        <label><span id="ob-relationship-subtype-label">具体身份</span> <span class="optional">（必选）</span></label>
        <select id="ob-relationship-subtype">
        </select>
      </div>
      <div class="form-group" id="ob-romance-evolution-group">
        <label class="privacy-check">
          <input type="checkbox" id="ob-romance-evolution" checked />
          <span>允许朋友关系自然发展为恋人</span>
        </label>
      </div>
      
      <div class="form-group" id="ob-custom-relationship-group" style="display: none;">
        <label>自定义关系名称</label>
        <input type="text" id="ob-custom-relationship" placeholder="请输入自定义的关系名称" maxlength="20" />
        <div class="persona-note">已配置大模型接口时，会自动为自定义关系分配合适的成长线。</div>
      </div>
      
      <div class="form-group">
        <label>性别</label>
        <div class="gender-row">
          <label><input type="radio" name="ob-gender" value="女" checked /> 女</label>
          <label><input type="radio" name="ob-gender" value="男" /> 男</label>
          <label><input type="radio" name="ob-gender" value="无" /> 无性别</label>
        </div>
      </div>
      
      <div class="form-group">
        <label>生日</label>
        <input type="date" id="ob-birthday" />
      </div>
      
      <div class="form-group">
        <label>身份证号 <span class="optional">（自动生成）</span></label>
        <div class="id-row">
          <input type="text" id="ob-id" placeholder="填写生日后自动生成" maxlength="18" readonly />
          <button type="button" id="ob-gen-id">重新生成</button>
        </div>
      </div>
      
      <div class="form-group">
        <label>人设 / 性格 <span class="optional">（选填）</span></label>
        <textarea id="ob-persona" placeholder="描述一下这个角色是什么样的性格，比如：温柔体贴、喜欢撒娇、有点毒舌但很关心人..."></textarea>
        <div class="persona-hints">
          <span class="persona-hint" data-text="温柔体贴，善解人意，说话轻声细语">温柔体贴</span>
          <span class="persona-hint" data-text="活泼开朗，爱开玩笑，有点小调皮">活泼开朗</span>
          <span class="persona-hint" data-text="冷静理性，说话简洁，偶尔毒舌但本质善良">冷静理性</span>
          <span class="persona-hint" data-text="傲娇，嘴上说不要但身体很诚实">傲娇</span>
          <span class="persona-hint" data-text="天然呆，经常犯迷糊，但很努力">天然呆</span>
          <span class="persona-hint" data-text="成熟稳重，像大哥哥/大姐姐一样可靠">成熟稳重</span>
        </div>
      </div>
      
      <div class="form-group">
        <label>世界观 / 背景设定 <span class="optional">（选填）</span></label>
        <textarea id="ob-worldview" placeholder="描述角色生活的世界或背景故事，比如：赛博朋克都市、修仙世界、现代校园、末日废土..."></textarea>
        <div class="persona-hints">
          <span class="persona-hint" data-worldview="现代都市，生活在繁忙城市里，有自己的工作、日常和小习惯">现代都市</span>
          <span class="persona-hint" data-worldview="赛博朋克世界，穿梭在霓虹街区与高楼阴影之间的人">赛博朋克</span>
          <span class="persona-hint" data-worldview="修仙世界，自幼修行，在灵气复苏的时代寻找自己的道">修仙世界</span>
          <span class="persona-hint" data-worldview="末日废土，文明崩塌后的幸存者，谨慎但仍保有温度">末日废土</span>
          <span class="persona-hint" data-worldview="星际时代，来自远航舰队或殖民星球，习惯在群星之间生活">星际时代</span>
          <span class="persona-hint" data-worldview="奇幻大陆，生活在魔法与剑交织的世界，有自己的故乡和旅途">奇幻大陆</span>
        </div>
      </div>
      
      <div class="actions">
        <button type="button" class="skip-btn" id="ob-skip">稍后设置</button>
        <button type="button" class="submit-btn" id="ob-submit">完成设置</button>
      </div>
    </div>
  </div>

  <!-- Guided Tour Overlay -->
  <div class="tour-overlay hidden" id="tour-overlay">
    <div class="tour-highlight" id="tour-highlight"></div>
    <div class="tour-tooltip" id="tour-tooltip" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <p class="tour-kicker" id="tour-kicker">开始使用</p>
      <h3 id="tour-title">欢迎</h3>
      <p id="tour-desc"></p>
      <div class="tour-footer">
        <div class="tour-progress" id="tour-progress" aria-label="引导进度"></div>
        <div class="tour-actions">
          <button type="button" class="tour-skip" id="tour-skip">跳过</button>
          <button type="button" class="tour-prev" id="tour-prev">上一步</button>
          <button type="button" class="tour-next" id="tour-next">下一步</button>
        </div>
      </div>
    </div>
  </div>

  <div class="realtime-launch-overlay" id="realtime-launch-overlay" aria-modal="true" role="dialog" aria-labelledby="realtime-launch-title">
    <div class="realtime-launch-panel">
      <h2 id="realtime-launch-title">开启实时对话</h2>
      <p>选择是否叠加屏幕或摄像头识别。未勾选的能力不会启用；摄像头和麦克风仍需要浏览器或系统授权。</p>
      <div class="realtime-launch-options">
        <label><input id="launch-realtime-screen" type="checkbox" />屏幕实时识别</label>
        <label><input id="launch-realtime-camera" type="checkbox" />摄像头物体/场景识别</label>
        <label><input id="launch-realtime-face" type="checkbox" />摄像头人物识别</label>
      </div>
      <div class="realtime-launch-actions">
        <button type="button" id="launch-realtime-cancel">取消</button>
        <button type="button" id="launch-realtime-start" class="primary">开启</button>
      </div>
    </div>
  </div>

  <aside>
    <div class="sidebar-brand">
      <img class="sidebar-brand-mark" src="/asset/ai_icon.ico" alt="">
      <strong>Companion AI</strong>
    </div>
    <button type="button" class="new-chat-btn" id="new-chat-btn">+ 新建对话</button>
    <p class="sidebar-section-label" data-i18n="function_area">功能区</p>
    <nav class="secondary-nav" aria-label="二级功能页面">
      <a href="/diary">情绪与日记</a>
      <a href="/samples">训练样本</a>
      <a href="/moments_page">AI朋友圈</a>
      <a href="/tools">学习与工具</a>
    </nav>
    <p class="sidebar-section-label">最近对话</p>
    <div class="recent-chat-list" id="recent-chat-list" aria-label="最近对话">
      <div class="recent-chat-empty">暂无最近对话</div>
    </div>
    <details class="command-section">
      <summary data-i18n="quick_core">常用入口</summary>
      <div class="quick">
        <button type="button" data-fill="/chat_status">系统状态</button>
        <button type="button" data-fill="/memory">查看记忆</button>
        <button type="button" data-fill="/context">查看现实上下文</button>
        <button type="button" id="observe-screen-btn" data-command-key="/see_screen">观察屏幕</button>
        <button type="button" data-fill="/time">查看时间</button>
      </div>
    </details>
    <div id="plugin-buttons" class="quick"><!--PLUGIN_BUTTONS--></div>
    <div style="margin:6px 0"><a href="/live2d" target="_blank" class="live2d-viewer-link" data-i18n="live2d_viewer">Live2D 查看器</a></div>
    <div class="notice" data-i18n="web_notice">只读取你有权访问的网页。不会绕过登录、付费墙、验证码、权限控制或反爬限制。</div>
  </aside>
  <main>
    <header style="position:relative">
      <h1>新对话</h1>
      <div class="header-tools">
        <div class="status" id="status" data-i18n="app_subtitle">本地运行 · 记忆自训练</div>
        <select class="language-select" id="language-select" aria-label="语言">
          <option value="zh-CN">中文</option>
          <option value="en-US">English</option>
        </select>
      </div>
      <button class="settings-btn" id="settings-btn" title="设置" data-i18n-title="settings">&#x2699;</button>
    </header>
    <section class="context-rail">
      <details class="sidebar-context" open>
        <summary>本次对话</summary>
        <div class="sidebar-context-body">
          <p class="memory-title">正在使用</p>
          <div class="memory-orbit" id="memory-orbit" tabindex="0" aria-label="靠近查看 AI 的记忆" data-i18n-aria="memory_orbit_label">
            <svg class="memory-brain" viewBox="0 0 160 132" aria-hidden="true">
              <path d="M67 105c-20 0-36-15-36-34 0-8 3-16 8-22-1-22 15-37 34-33 8-12 27-9 32 5 16-1 29 11 29 27 9 6 14 17 11 30-3 17-18 27-36 27H67Z" />
              <path d="M74 18c-10 13-9 27 0 38-10 8-11 22-2 32" />
              <path d="M104 23c-6 10-5 22 3 30-11 5-15 16-10 29" />
              <path d="M42 51c13-4 25-2 34 7" /><path d="M88 56c18-8 34-5 45 8" /><path d="M51 80c13 7 29 9 47 2" />
              <circle cx="52" cy="50" r="4" /><circle cx="104" cy="54" r="4" /><circle cx="73" cy="86" r="4" /><circle cx="122" cy="78" r="4" />
            </svg>
            <div id="memory-nodes" aria-live="polite"></div>
            <div class="memory-orbit-hint" data-i18n="memory_orbit_hint">靠近大脑，查看 AI 正在记住什么</div>
          </div>
          <div id="memory" class="memory" data-i18n="memory_loading">加载中...</div>
          <div id="growth-summary" class="growth-panel"><h4>关系成长</h4><div class="growth-row"><span>关系</span><strong>加载中...</strong></div></div>
          <details class="files"><summary id="files-summary">文件：暂无</summary><div id="files" class="files-body"></div></details>
          <div class="context-shortcuts" aria-label="快捷开始">
            <p class="memory-title">快捷开始</p>
            <button type="button" data-context-fill="帮我拆解一项任务">帮我拆解一项任务</button>
            <button type="button" data-context-fill="/context">总结刚才的对话</button>
            <button type="button" data-context-fill="/see_screen">观察当前屏幕</button>
          </div>
        </div>
      </details>
      <section class="companion-visual" aria-label="伙伴展示">
        <div class="companion-visual-tabs" role="tablist" aria-label="展示模式">
          <button type="button" class="active" data-companion-view="live2d" role="tab" aria-selected="true">Live2D</button>
          <button type="button" data-companion-view="live3d" role="tab" aria-selected="false">Live3D</button>
        </div>
        <div class="companion-visual-stage">
          <iframe id="live2dFrame" class="live2d-frame" title="Live2D avatar" src="about:blank"></iframe>
          <iframe id="live3dFrame" class="live3d-frame" title="Live3D avatar" src="/3d?embed=1" hidden></iframe>
        </div>
      </section>
    </section>
    <section class="avatar-stage">
      <div id="avatar" class="avatar idle" aria-label="Live2D avatar placeholder">
        <div class="hair"></div>
        <div class="body"></div>
        <div class="head"></div>
        <div class="eye left"></div>
        <div class="eye right"></div>
        <div class="mouth"></div>
      </div>
      <div class="avatar-info">
        <div id="avatarStatus" data-i18n="classic_avatar_status">Live2D 区域：内置 2D 头像 · 动作学习中</div>
        <div id="motionList" class="motion-list"></div>
      </div>
      <div id="realtime-pet-chat" class="realtime-pet-chat" aria-live="polite">
        <div class="realtime-pet-chat-title" data-i18n="realtime_voice">实时对话</div>
        <div id="realtime-pet-chat-body" class="realtime-pet-chat-body"></div>
      </div>
    </section>
    <section id="chat">
      <div class="msg assistant" id="welcome-message">
        <div class="assistant-meta"><strong>Companion</strong><span>10:24</span></div>
        <div class="msg-body"><div class="msg-text" data-i18n="welcome_message">我在。可以直接聊天、上传文件、读取网页 URL，也可以用下面的提示词快速开始。

日记、朋友圈、学习训练和管理工具已经移到左侧二级页面入口，聊天页只保留高频操作。</div></div>
      </div>
    </section>
    <form id="form">
      <div class="inputs">
        <div class="voice-input-row">
          <textarea id="message" placeholder="和我说点什么..." data-i18n-placeholder="message_placeholder"></textarea>
          <button id="attach-btn" class="attach-btn" type="button" title="发送文件/图片" aria-label="发送文件/图片">📎</button>
          <button id="voice-input-btn" class="voice-btn" type="button" title="语音输入" aria-label="语音输入">🎙</button>
          <button id="realtime-voice-btn" class="realtime-voice-btn" type="button" title="开启实时对话" aria-label="开启实时对话" data-i18n-title="realtime_start" data-i18n-aria="realtime_start">◉</button>
          <button id="wake-word-btn" class="wake-word-btn" type="button" title="开启语音唤醒" aria-label="开启语音唤醒" data-i18n-title="wake_word_start" data-i18n-aria="wake_word_start">⚡</button>
          <button id="send" type="submit" data-i18n="send">发送</button>
        </div>
        <details class="composer-tools" id="composer-tools">
          <summary data-i18n="composer_tools">附件、网页与更多</summary>
          <div class="composer-resources">
            <input id="url" placeholder="可选：网页 URL" data-i18n-placeholder="url_placeholder" />
            <input id="file" type="file" accept="image/*,.pdf,.txt,.md,.doc,.docx,.csv,.json,.zip" />
          </div>
        </details>
        <details class="realtime-options">
          <summary data-i18n="realtime_options">实时对话选项</summary>
          <div id="realtime-voice-status" class="realtime-voice-status" aria-live="polite"></div>
          <div class="realtime-sense-row" aria-label="实时对话叠加感知">
            <label class="realtime-sense-toggle" title="每句实时对话前观察一次当前屏幕">
              <input id="realtime-screen-toggle" type="checkbox" />
              <span>屏幕</span>
            </label>
            <label class="realtime-sense-toggle" title="每句实时对话前从摄像头抓拍一帧并做物体/场景识别">
              <input id="realtime-camera-toggle" type="checkbox" />
              <span>摄像头</span>
            </label>
            <label class="realtime-sense-toggle" title="每句实时对话前尝试识别人脸身份">
              <input id="realtime-face-toggle" type="checkbox" />
              <span>人物</span>
            </label>
          </div>
        </details>
      </div>
    </form>
    <details class="suggestions-panel">
      <summary data-i18n="quick_core">常用入口</summary>
      <div class="suggestions" id="suggestions">
      <span class="suggestion-chip" data-fill="/chat_status">系统状态</span>
      <span class="suggestion-chip" data-fill="/accelerate">培养加速</span>
      <span class="suggestion-chip" data-fill="/see_screen">观察屏幕</span>
      <span class="suggestion-chip" data-fill="/time">现在几点</span>
      <span class="suggestion-chip" data-fill="/weather Hong Kong">查天气</span>
      <span class="suggestion-chip" data-fill="/teach 当我说我很累 => 先安静陪我一下，再帮我把事情拆成一个很小的下一步。" data-command-key="teach_example">教一句</span>
      <span class="suggestion-chip" data-fill="/remember 我希望你回答时先给结论，再给步骤。" data-command-key="remember_example">写入偏好</span>
      <span class="suggestion-chip" data-fill="我今天有点累，陪我整理一下思路。" data-command-key="chat_example">随便聊聊</span>
      </div>
    </details>
  </main>
  <script>
    let i18nState = __I18N_BOOTSTRAP__;
    const i18nFallback = {
      locale: "zh-CN",
      messages: {
        app_name: "AI陪伴桌宠",
        app_subtitle: "本地运行 · 记忆自训练",
        privacy_required: "请先同意隐私政策",
        settings: "设置",
        language: "语言",
        chinese: "中文",
        english: "English",
        memory_title: "长期记忆",
        chat_workspace: "对话",
        function_area: "功能区",
        context_title: "长期记忆与上下文",
        composer_tools: "附件、网页与更多",
        realtime_options: "实时对话选项",
        memory_loading: "加载中...",
        training_loading: "训练样本：加载中...",
        files_empty: "文件：暂无",
        message_placeholder: "和我说点什么...",
        url_placeholder: "可选：网页 URL",
        send: "发送",
        settings_title: "Companion AI 设置",
        settings_subtitle: "管理本地能力、模型、身份、语音和插件。",
        settings_saved: "已保存",
        i18n_note: "切换后会立即更新核心界面；部分对话内容仍按当前模型和命令语言生成。",
        quick_core: "常用入口",
        quick_learning: "学习与训练",
        quick_tools: "管理与工具",
        realtime_voice: "实时对话",
        realtime_start: "开启实时对话",
        realtime_stop: "关闭实时对话",
        realtime_listening: "实时对话：正在听你说话...",
        realtime_thinking: "实时对话：思考中...",
        realtime_speaking: "实时对话：正在播放回复...",
        realtime_ready: "实时对话已开启，听到一句完整语音后会自动发送。",
        realtime_off: "实时对话已关闭",
        realtime_unsupported: "当前浏览器不支持实时语音识别。请使用 Chrome 或 Edge。",
        realtime_tts_hint: "实时对话会自动开启语音合成和自动播放。",
        wake_word: "语音唤醒",
        wake_word_start: "开启语音唤醒",
        wake_word_stop: "关闭语音唤醒",
        wake_word_ready: "语音唤醒已开启，说“你好小智”后会开启实时对话。",
        wake_word_listening: "语音唤醒：等待“你好小智”...",
        wake_word_heard: "已唤醒，正在开启实时对话...",
        wake_word_command: "语音唤醒：正在开启实时对话...",
        wake_word_off: "语音唤醒已关闭",
        wake_word_unsupported: "当前浏览器不支持语音唤醒。请使用 Chrome 或 Edge。",
        play_voice: "播放语音",
        pause_voice: "暂停语音",
        resume_voice: "继续播放"
      }
    };

    function i18nText(key) {
      return (i18nState?.messages && i18nState.messages[key]) || i18nFallback.messages[key] || key;
    }

    const displayDefaults = {
      theme: "soft",
      font_scale: 100,
      density: 100,
      radius: 8,
      sidebar_width: 280,
      avatar_height: 84,
      custom: {
        bg: "#f6f7f9",
        panel: "#ffffff",
        panel_soft: "#eef2f7",
        ink: "#172033",
        muted: "#657184",
        accent: "#276ef1",
        accent_2: "#0b8f6f"
      }
    };
    let displayConfig = {...displayDefaults};
    const displayThemePalettes = {
      soft: {bg:"#f6f7f9", panel:"#ffffff", panel_soft:"#eef2f7", ink:"#172033", muted:"#657184", accent:"#276ef1", accent_2:"#0b8f6f"},
      night: {bg:"#10141c", panel:"#171d28", panel_soft:"#111722", ink:"#f1f5fa", muted:"#c4d0df", accent:"#7aa7ff", accent_2:"#55d0a9"},
      forest: {bg:"#f2f7f3", panel:"#ffffff", panel_soft:"#e9f1eb", ink:"#183026", muted:"#66786f", accent:"#2d7d59", accent_2:"#617a2e"},
      rose: {bg:"#fbf5f7", panel:"#ffffff", panel_soft:"#f4e9ef", ink:"#33212a", muted:"#7c6872", accent:"#c24a7a", accent_2:"#477d8d"},
      mono: {bg:"#f5f5f4", panel:"#ffffff", panel_soft:"#ececea", ink:"#202020", muted:"#666666", accent:"#2f5f8f", accent_2:"#5a6f3b"}
    };
    const displayThemeLabels = {
      soft: "清爽",
      night: "夜间",
      forest: "森林",
      rose: "蔷薇",
      mono: "素描",
      custom: "自定义"
    };

    function normalizedDisplayConfig(config = {}) {
      const next = {...displayDefaults, ...(config || {})};
      const themes = new Set(["soft", "night", "forest", "rose", "mono", "custom"]);
      if (!themes.has(next.theme)) next.theme = displayDefaults.theme;
      const clamp = (value, min, max, fallback) => {
        const n = parseInt(value, 10);
        return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : fallback;
      };
      const isHex = value => /^#[0-9a-fA-F]{6}$/.test(String(value || ""));
      next.font_scale = clamp(next.font_scale, 85, 125, displayDefaults.font_scale);
      next.density = clamp(next.density, 80, 125, displayDefaults.density);
      next.radius = clamp(next.radius, 2, 18, displayDefaults.radius);
      next.sidebar_width = clamp(next.sidebar_width, 240, 440, displayDefaults.sidebar_width);
      next.avatar_height = clamp(next.avatar_height, 64, 104, displayDefaults.avatar_height);
      next.custom = {...displayDefaults.custom, ...((config && config.custom) || {})};
      Object.keys(displayDefaults.custom).forEach(key => {
        if (!isHex(next.custom[key])) next.custom[key] = displayDefaults.custom[key];
        next.custom[key] = String(next.custom[key]).toLowerCase();
      });
      return next;
    }

    function applyDisplayConfig(config = displayConfig) {
      displayConfig = normalizedDisplayConfig(config);
      const root = document.documentElement;
      root.dataset.theme = displayConfig.theme;
      root.style.setProperty("--font-scale", (displayConfig.font_scale / 100).toFixed(2));
      root.style.setProperty("--density-scale", (displayConfig.density / 100).toFixed(2));
      root.style.setProperty("--ui-radius", displayConfig.radius + "px");
      root.style.setProperty("--sidebar-width", displayConfig.sidebar_width + "px");
      root.style.setProperty("--avatar-height", displayConfig.avatar_height + "px");
      root.style.setProperty("--custom-swatch-a", displayConfig.custom.bg);
      root.style.setProperty("--custom-swatch-b", displayConfig.custom.accent);
      ["bg", "panel", "panel_soft", "ink", "muted", "accent", "accent_2"].forEach(key => {
        const cssName = "--" + key.replace("_", "-");
        if (displayConfig.theme === "custom") {
          root.style.setProperty(cssName, displayConfig.custom[key]);
        } else {
          root.style.removeProperty(cssName);
        }
      });
      if (displayConfig.theme === "custom") {
        root.style.setProperty("--paper", displayConfig.custom.bg);
      } else {
        root.style.removeProperty("--paper");
      }
      applyDisplayTypography(displayConfig.font_scale);
      syncDisplayControls();
    }

    function displayConfigFromControls() {
      const activeTheme = document.querySelector('input[name="display-theme"]:checked');
      const customValue = id => document.getElementById(id)?.value || "";
      return normalizedDisplayConfig({
        theme: activeTheme?.value || displayConfig.theme,
        font_scale: document.getElementById("display-font-scale")?.value,
        density: document.getElementById("display-density")?.value,
        radius: document.getElementById("display-radius")?.value,
        sidebar_width: document.getElementById("display-sidebar-width")?.value,
        avatar_height: document.getElementById("display-avatar-height")?.value,
        custom: {
          bg: customValue("custom-bg"),
          panel: customValue("custom-panel"),
          panel_soft: customValue("custom-panel-soft"),
          ink: customValue("custom-ink"),
          muted: customValue("custom-muted"),
          accent: customValue("custom-accent"),
          accent_2: customValue("custom-accent-2")
        }
      });
    }

    function updateRangeVisual(input) {
      if (!input || input.type !== "range") return;
      const min = parseFloat(input.min || "0");
      const max = parseFloat(input.max || "100");
      const value = parseFloat(input.value || "0");
      const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;
      input.style.setProperty("--slider-progress", `${Math.max(0, Math.min(100, pct))}%`);
    }

    function applyDisplayTypography(fontScale) {
      const scale = Number(fontScale) / 100;
      if (!Number.isFinite(scale) || !document.body) return;
      const selector = [
        "h1", "h2", "h3", "h4", "p", "span", "a", "button", "label", "summary",
        "strong", "em", "li", "input", "textarea", "select", "option", ".status", ".memory"
      ].join(",");
      document.body.querySelectorAll(selector).forEach(element => {
        const currentSize = parseFloat(getComputedStyle(element).fontSize);
        if (!Number.isFinite(currentSize) || currentSize <= 0) return;
        if (!element.dataset.displayFontBase) {
          // The initial view may already be scaled by a saved setting.
          element.dataset.displayFontBase = String(currentSize / scale);
        }
        const baseSize = parseFloat(element.dataset.displayFontBase);
        if (Number.isFinite(baseSize)) element.style.fontSize = `${(baseSize * scale).toFixed(2)}px`;
      });
    }

    function updateDisplayPreview(cfg) {
      const preview = document.getElementById("display-preview-surface");
      if (!preview) return;
      const normalized = normalizedDisplayConfig(cfg);
      preview.style.setProperty("--preview-font-scale", (normalized.font_scale / 100).toFixed(2));
      preview.style.setProperty("--preview-density", (normalized.density / 100).toFixed(2));
      preview.style.setProperty("--preview-radius", normalized.radius + "px");
      preview.style.setProperty("--preview-sidebar-width", Math.round(42 + ((normalized.sidebar_width - 240) / 200) * 70) + "px");
      preview.style.setProperty("--preview-avatar-height", Math.round(64 + ((normalized.avatar_height - 64) / 40) * 54) + "px");
    }

    function syncDisplayControls() {
      const cfg = normalizedDisplayConfig(displayConfig);
      const themeInput = document.querySelector(`input[name="display-theme"][value="${cfg.theme}"]`);
      if (themeInput) themeInput.checked = true;
      const colorPairs = [
        ["custom-bg", cfg.custom.bg],
        ["custom-panel", cfg.custom.panel],
        ["custom-panel-soft", cfg.custom.panel_soft],
        ["custom-ink", cfg.custom.ink],
        ["custom-muted", cfg.custom.muted],
        ["custom-accent", cfg.custom.accent],
        ["custom-accent-2", cfg.custom.accent_2],
      ];
      colorPairs.forEach(([inputId, value]) => {
        const input = document.getElementById(inputId);
        if (input) input.value = value;
      });
      const pairs = [
        ["display-font-scale", "display-font-scale-value", cfg.font_scale, "%"],
        ["display-density", "display-density-value", cfg.density, "%"],
        ["display-radius", "display-radius-value", cfg.radius, "px"],
        ["display-sidebar-width", "display-sidebar-width-value", cfg.sidebar_width, "px"],
        ["display-avatar-height", "display-avatar-height-value", cfg.avatar_height, "px"],
      ];
      pairs.forEach(([inputId, valueId, value, unit]) => {
        const input = document.getElementById(inputId);
        const label = document.getElementById(valueId);
        if (input) {
          input.value = value;
          updateRangeVisual(input);
        }
        if (label) label.textContent = value + unit;
      });
      updateDisplayPreview(cfg);
      renderDisplaySummary(cfg);
    }

    function displaySummaryItem(label, value) {
      return `<div class="display-summary-item"><span class="display-summary-label">${escapeSettingsText(label)}</span><span class="display-summary-value">${escapeSettingsText(value)}</span></div>`;
    }

    function renderDisplaySummary(cfg = displayConfig) {
      const normalized = normalizedDisplayConfig(cfg);
      const summaryEl = document.getElementById("display-summary");
      const themeEl = document.getElementById("display-current-theme");
      const detailEl = document.getElementById("display-current-detail");
      const themeName = displayThemeLabels[normalized.theme] || normalized.theme;
      if (summaryEl) {
        summaryEl.innerHTML = [
          displaySummaryItem("主题", themeName),
          displaySummaryItem("字号", normalized.font_scale + "%"),
          displaySummaryItem("密度", normalized.density + "%"),
          displaySummaryItem("布局", `${normalized.sidebar_width}px / ${normalized.avatar_height}px`),
        ].join("");
      }
      if (themeEl) themeEl.textContent = themeName;
      if (detailEl) detailEl.textContent = `字号 ${normalized.font_scale}% · 密度 ${normalized.density}% · 圆角 ${normalized.radius}px`;
    }

    function showDisplayPage(page) {
      const mainPage = document.getElementById("display-page-main");
      const detailPage = document.getElementById("display-page-detail");
      if (!mainPage || !detailPage) return;
      mainPage.classList.toggle("active", page !== "detail");
      detailPage.classList.toggle("active", page === "detail");
      if (page === "detail") {
        showSettingsSecondaryPage("sec-display");
      } else {
        showSettingsCategory(activeSettingsCategory);
      }
    }

    function loadDisplaySettings() {
      fetch("/api/display").then(r => r.json()).then(data => {
        applyDisplayConfig(data.display || data.config || data);
        const statusEl = document.getElementById("display-status");
        if (statusEl) statusEl.textContent = "";
      }).catch(() => {
        applyDisplayConfig(displayConfig);
      });
    }

    function i18nCommandLabel(el) {
      const labels = (i18nState?.messages && i18nState.messages.command_labels) || {};
      const fallbackLabels = i18nFallback.messages.command_labels || {};
      const fill = el.dataset.fill || "";
      const key = el.dataset.commandKey || fill;
      if (labels[key] || fallbackLabels[key]) return labels[key] || fallbackLabels[key];
      for (const [candidate, label] of Object.entries(labels)) {
        if (candidate && fill.startsWith(candidate)) return label;
      }
      for (const [candidate, label] of Object.entries(fallbackLabels)) {
        if (candidate && fill.startsWith(candidate)) return label;
      }
      return el.textContent;
    }

    function applyI18n() {
      const locale = i18nState?.locale || "zh-CN";
      document.documentElement.lang = locale;
      document.title = i18nText("app_name");
      document.querySelectorAll("[data-i18n]").forEach(el => {
        el.textContent = i18nText(el.dataset.i18n);
      });
      document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        el.placeholder = i18nText(el.dataset.i18nPlaceholder);
      });
      document.querySelectorAll("[data-i18n-title]").forEach(el => {
        el.title = i18nText(el.dataset.i18nTitle);
      });
      document.querySelectorAll("[data-i18n-aria]").forEach(el => {
        el.setAttribute("aria-label", i18nText(el.dataset.i18nAria));
      });
      document.querySelectorAll("[data-fill], [data-command-key]").forEach(el => {
        el.textContent = i18nCommandLabel(el);
      });
      const languageSelect = document.querySelector("#language-select");
      if (languageSelect) {
        languageSelect.value = locale;
        languageSelect.setAttribute("aria-label", i18nText("language"));
      }
      const settingsLanguageSelect = document.querySelector("#settings-language-select");
      if (settingsLanguageSelect) settingsLanguageSelect.value = locale;
      if (typeof updateRealtimeVoiceButton === "function") updateRealtimeVoiceButton();
      if (typeof updateWakeWordButton === "function") updateWakeWordButton();
    }

    const chat = document.querySelector("#chat");
    const form = document.querySelector("#form");
    const pageTitle = document.querySelector("h1");
    const message = document.querySelector("#message");
    const url = document.querySelector("#url");
    const send = document.querySelector("#send");
    const voiceInputBtn = document.querySelector("#voice-input-btn");
    const realtimeVoiceBtn = document.querySelector("#realtime-voice-btn");
    const wakeWordBtn = document.querySelector("#wake-word-btn");
    const newChatBtn = document.querySelector("#new-chat-btn");
    const recentChatList = document.querySelector("#recent-chat-list");
    const realtimeVoiceStatus = document.querySelector("#realtime-voice-status");
    const realtimePetChat = document.querySelector("#realtime-pet-chat");
    const realtimePetChatBody = document.querySelector("#realtime-pet-chat-body");
    const realtimeScreenToggle = document.querySelector("#realtime-screen-toggle");
    const realtimeCameraToggle = document.querySelector("#realtime-camera-toggle");
    const realtimeFaceToggle = document.querySelector("#realtime-face-toggle");
    const realtimeLaunchOverlay = document.querySelector("#realtime-launch-overlay");
    const launchRealtimeScreen = document.querySelector("#launch-realtime-screen");
    const launchRealtimeCamera = document.querySelector("#launch-realtime-camera");
    const launchRealtimeFace = document.querySelector("#launch-realtime-face");
    const launchRealtimeStart = document.querySelector("#launch-realtime-start");
    const launchRealtimeCancel = document.querySelector("#launch-realtime-cancel");
    const languageSelect = document.querySelector("#language-select");
    const memory = document.querySelector("#memory");
    const memoryNodes = document.querySelector("#memory-nodes");
    const training = document.querySelector("#training");
    const files = document.querySelector("#files");
    const momentsList = document.querySelector("#moments-list");
    
    // Multimodal emotion metrics collector
    let typingMetrics = {
        backspaces: 0,
        pauses: 0,
        lastKeyTime: 0,
        keyCount: 0,
        totalDuration: 0,
        startTypingTime: 0
    };
    
    function resetTypingMetrics() {
        typingMetrics = { backspaces: 0, pauses: 0, lastKeyTime: 0, keyCount: 0, totalDuration: 0, startTypingTime: 0 };
    }
    
    function countPunctuation(text) {
        const exclamation = (text.match(/[！!]/g) || []).length;
        const ellipsis = (text.match(/[………]/g) || []).length + 0.5 * (text.match(/\.\.\./g) || []).length;
        const question = (text.match(/[？?]/g) || []).length;
        return { exclamation, ellipsis, question, total: text.length };
    }
    
    if (message) {
        message.addEventListener("keydown", e => {
            const now = performance.now();
            if (typingMetrics.startTypingTime === 0) {
                typingMetrics.startTypingTime = now;
            }
            if (e.key === "Backspace" || e.key === "Delete") {
                typingMetrics.backspaces++;
            }
            if (typingMetrics.lastKeyTime && now - typingMetrics.lastKeyTime > 1500) {
                typingMetrics.pauses++;
            }
            typingMetrics.lastKeyTime = now;
            typingMetrics.keyCount++;
            typingMetrics.totalDuration = now - typingMetrics.startTypingTime;
        });
        
        message.addEventListener("input", () => {
            if (typingMetrics.startTypingTime === 0) {
                typingMetrics.startTypingTime = performance.now();
            }
            typingMetrics.totalDuration = performance.now() - typingMetrics.startTypingTime;
        });
    }
    const momentInput = document.querySelector("#moment-input");
    const momentPostBtn = document.querySelector("#moment-post-btn");
    const momentGenerateBtn = document.querySelector("#moment-generate-btn");
    const fileInput = document.querySelector("#file");
    const attachBtn = document.querySelector("#attach-btn");
    const composerTools = document.querySelector("#composer-tools");
    function updateAttachButton() {
      if (!attachBtn || !fileInput) return;
      const hasFile = !!(fileInput.files && fileInput.files.length);
      attachBtn.classList.toggle("has-file", hasFile);
      attachBtn.title = hasFile ? (`已选择：${fileInput.files[0].name}`) : "发送文件/图片";
      attachBtn.setAttribute("aria-label", attachBtn.title);
    }
    attachBtn?.addEventListener("click", () => {
      if (composerTools) composerTools.open = true;
      fileInput?.click();
    });
    fileInput?.addEventListener("change", updateAttachButton);
    const status = document.querySelector("#status");
    const avatar = document.querySelector("#avatar");
    const avatarStage = document.querySelector(".avatar-stage");
    const live2dFrame = document.querySelector("#live2dFrame");
    const live3dFrame = document.querySelector("#live3dFrame");
    const avatarStatus = document.querySelector("#avatarStatus");
    const motionList = document.querySelector("#motionList");
    const privacyOverlay = document.querySelector("#privacy-overlay");
    const privacyCheckbox = document.querySelector("#privacy-checkbox");
    const privacySubmit = document.querySelector("#privacy-submit");
    let privacyAccepted = false;
    let lastUserText = "";
    let lastAssistantText = "";
    let lastEmotion = null;
    let currentFileId = "";
    let currentConversationId = "";
    let recentChats = [];
    let ttsConfig = { enabled: false, auto_play: false };
    let currentAudio = null;
    let currentAudioControl = null;
    let currentAudioUrl = "";
    let suppressNextAutoTTS = false;
    let activeSpeechRecognition = null;
    let realtimeVoiceEnabled = false;
    let realtimeRecognition = null;
    let realtimeRestartTimer = null;
    let realtimeSending = false;
    let wakeWordEnabled = false;
    let wakeWordRecognition = null;
    let wakeWordRestartTimer = null;
    let lastMemoryData = null;
    let lastTrainingData = null;
    let lastFilesData = null;
    let lastAvatarData = null;
    applyI18n();
    document.querySelectorAll(".command-section, .suggestions-panel").forEach(panel => {
      panel.open = false;
    });
    document.querySelectorAll("[data-companion-view]").forEach(button => {
      button.addEventListener("click", () => {
        const view = button.dataset.companionView;
        const showLive2d = view === "live2d";
        if (live2dFrame) live2dFrame.hidden = !showLive2d;
        if (live3dFrame) {
          live3dFrame.hidden = showLive2d;
          if (!showLive2d) {
            const wanted = "/3d?embed=1";
            if (!String(live3dFrame.src || "").includes("/3d?embed=1")) live3dFrame.src = wanted;
          }
        }
        document.querySelectorAll("[data-companion-view]").forEach(tab => {
          const active = tab === button;
          tab.classList.toggle("active", active);
          tab.setAttribute("aria-selected", String(active));
        });
        broadcastCompanionCursor();
      });
    });

    let lastCompanionCursor = null;
    function activeCompanionFrame() {
      if (live2dFrame && !live2dFrame.hidden) return live2dFrame;
      if (live3dFrame && !live3dFrame.hidden) return live3dFrame;
      return null;
    }

    function broadcastCompanionCursor(event = null) {
      const frame = activeCompanionFrame();
      if (!frame || !frame.contentWindow) return;
      if (event) {
        lastCompanionCursor = {
          x: Number.isFinite(event.screenX) ? event.screenX : window.screenX + event.clientX,
          y: Number.isFinite(event.screenY) ? event.screenY : window.screenY + event.clientY
        };
      }
      if (!lastCompanionCursor) return;
      const rect = frame.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      frame.contentWindow.postMessage({
        type: "cursor-position",
        payload: {
          cursor: lastCompanionCursor,
          windowBounds: {
            x: Math.round((window.screenX || window.screenLeft || 0) + rect.left),
            y: Math.round((window.screenY || window.screenTop || 0) + rect.top),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
          }
        }
      }, "*");
    }
    window.addEventListener("mousemove", broadcastCompanionCursor, { passive: true });
    window.addEventListener("pointermove", broadcastCompanionCursor, { passive: true });
    window.addEventListener("resize", () => broadcastCompanionCursor());
    setInterval(() => broadcastCompanionCursor(), 80);

    languageSelect?.addEventListener("change", async () => {
      const locale = languageSelect.value;
      try {
        const resp = await fetch("/api/i18n", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ locale })
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "save failed");
        i18nState = data;
        applyI18n();
        rerenderLocalizedState();
      } catch (err) {
        languageSelect.value = i18nState?.locale || "zh-CN";
        alert("语言设置保存失败：" + err);
      }
    });

    function setAppLocked(locked) {
      send.disabled = locked;
      message.disabled = locked;
      url.disabled = locked;
      fileInput.disabled = locked;
      if (voiceInputBtn) voiceInputBtn.disabled = locked;
      if (realtimeVoiceBtn) realtimeVoiceBtn.disabled = locked;
      if (wakeWordBtn) wakeWordBtn.disabled = locked;
      [realtimeScreenToggle, realtimeCameraToggle, realtimeFaceToggle].forEach(input => {
        if (input) input.disabled = locked;
      });
      document.querySelectorAll("[data-fill], #observe-screen-btn, #plugin-reload-btn, #plugin-new-btn, #moment-post-btn, #moment-generate-btn").forEach(btn => {
        if (btn) btn.disabled = locked;
      });
      status.textContent = locked ? i18nText("privacy_required") : i18nText("app_subtitle");
    }

    const privacyUpdateNotice = document.getElementById("privacy-update-notice");

    async function loadPrivacyConsent() {
      setAppLocked(true);
      try {
        const resp = await fetch("/api/privacy");
        const data = await resp.json();
        privacyAccepted = !!data.accepted;
        if (privacyUpdateNotice) {
          privacyUpdateNotice.style.display = (!privacyAccepted && data.version && data.policy_version && data.version !== data.policy_version) ? "block" : "none";
        }
      } catch (err) {
        privacyAccepted = false;
        if (privacyUpdateNotice) {
          privacyUpdateNotice.style.display = "none";
        }
      }
      if (privacyAccepted) {
        privacyOverlay.classList.add("hidden");
        setAppLocked(false);
        checkIdentitySetup();
        applyRealtimeLaunchParams();
      } else {
        privacyOverlay.classList.remove("hidden");
      }
    }

    privacyCheckbox.addEventListener("change", () => {
      privacySubmit.disabled = !privacyCheckbox.checked;
    });

    privacySubmit.addEventListener("click", async () => {
      if (!privacyCheckbox.checked) return;
      privacySubmit.disabled = true;
      privacySubmit.textContent = "保存中...";
      try {
        const resp = await fetch("/api/privacy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ accepted: true })
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "保存失败");
        privacyAccepted = true;
        privacyOverlay.classList.add("hidden");
        setAppLocked(false);
        checkIdentitySetup();
        applyRealtimeLaunchParams();
      } catch (err) {
        privacySubmit.textContent = "同意并开始使用";
        privacySubmit.disabled = !privacyCheckbox.checked;
        alert("保存隐私同意失败：" + err);
      }
    });

    // 加载 TTS 配置
    function loadTTSConfig() {
      fetch("/api/tts/config").then(r => r.json()).then(data => {
        ttsConfig = data;
      }).catch(() => {});
    }
    loadTTSConfig();

    function speechRecognitionApi() {
      return window.SpeechRecognition || window.webkitSpeechRecognition || null;
    }

    function startVoiceInput() {
      if (!privacyAccepted) {
        privacyOverlay.classList.remove("hidden");
        return;
      }
      const Recognition = speechRecognitionApi();
      if (!Recognition) {
        alert("当前浏览器不支持语音输入。可以使用 Chrome/Edge，或先在系统输入法里开启语音输入。");
        return;
      }
      if (activeSpeechRecognition) {
        activeSpeechRecognition.stop();
        activeSpeechRecognition = null;
        voiceInputBtn?.classList.remove("listening");
        return;
      }
      const recognition = new Recognition();
      activeSpeechRecognition = recognition;
      recognition.lang = (i18nState?.locale || "zh-CN").startsWith("en") ? "en-US" : "zh-CN";
      recognition.interimResults = true;
      recognition.continuous = false;
      const original = message.value.trim();
      let finalText = "";
      voiceInputBtn?.classList.add("listening");
      voiceInputBtn.title = (i18nState?.locale || "zh-CN").startsWith("en") ? "Listening, click to stop" : "正在听，点击停止";
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const text = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += text;
          else interim += text;
        }
        const parts = [original, finalText, interim].filter(Boolean);
        message.value = parts.join(original ? " " : "");
        message.focus();
      };
      recognition.onerror = (event) => {
        alert("语音输入失败：" + (event.error || "未知错误"));
      };
      recognition.onend = () => {
        activeSpeechRecognition = null;
        voiceInputBtn?.classList.remove("listening");
        if (voiceInputBtn) voiceInputBtn.title = i18nText("voice_input");
      };
      recognition.start();
    }

    voiceInputBtn?.addEventListener("click", startVoiceInput);

    function setRealtimeVoiceStatus(text, kind = "") {
      if (!realtimeVoiceStatus) return;
      realtimeVoiceStatus.textContent = text || "";
      realtimeVoiceStatus.classList.toggle("active", kind === "active");
      realtimeVoiceStatus.classList.toggle("error", kind === "error");
      notifyRealtimePetStatus(text, kind);
    }

    let lastRealtimePetStatus = { text: "", time: 0 };
    function notifyRealtimePetStatus(text, kind = "") {
      const clean = String(text || "").trim();
      if (!clean || kind === "error") return;
      const now = Date.now();
      if (clean === lastRealtimePetStatus.text && now - lastRealtimePetStatus.time < 8000) return;
      lastRealtimePetStatus = { text: clean, time: now };
      fetch("/api/realtime_event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "system", text: clean })
      }).catch(() => {});
    }

    function updateWakeWordButton() {
      if (!wakeWordBtn) return;
      wakeWordBtn.classList.toggle("active", wakeWordEnabled);
      wakeWordBtn.textContent = wakeWordEnabled ? "■" : "⚡";
      wakeWordBtn.title = wakeWordEnabled ? i18nText("wake_word_stop") : i18nText("wake_word_start");
      wakeWordBtn.setAttribute("aria-label", wakeWordBtn.title);
    }

    function normalizeWakeText(text) {
      return String(text || "")
        .toLowerCase()
        .replace(/[，。！？、,.!?;；:："'“”‘’\s]/g, "");
    }

    function wakeWordMatched(text) {
      const clean = normalizeWakeText(text);
      if (!clean) return false;
      return [
        "你好小智",
        "小智",
        "你好伙伴",
        "伙伴",
        "heycompanion",
        "hicompanion",
        "hellocompanion"
      ].some(word => clean.includes(word));
    }

    function stopWakeWordRecognition() {
      if (wakeWordRestartTimer) {
        clearTimeout(wakeWordRestartTimer);
        wakeWordRestartTimer = null;
      }
      if (wakeWordRecognition) {
        const recognition = wakeWordRecognition;
        wakeWordRecognition = null;
        recognition.onend = null;
        try { recognition.stop(); } catch (_err) {}
      }
    }

    function scheduleWakeWordListen(delay = 350) {
      if (!wakeWordEnabled || realtimeVoiceEnabled || realtimeSending) return;
      if (wakeWordRestartTimer) clearTimeout(wakeWordRestartTimer);
      wakeWordRestartTimer = setTimeout(() => startWakeWordListening(), delay);
    }

    function startWakeWordListening() {
      if (!wakeWordEnabled || realtimeVoiceEnabled || realtimeSending) return;
      const Recognition = speechRecognitionApi();
      if (!Recognition) {
        stopWakeWord(i18nText("wake_word_unsupported"), true);
        return;
      }
      stopWakeWordRecognition();
      const recognition = new Recognition();
      wakeWordRecognition = recognition;
      recognition.lang = (i18nState?.locale || "zh-CN").startsWith("en") ? "en-US" : "zh-CN";
      recognition.interimResults = true;
      recognition.continuous = false;
      let finalText = "";
      let interimText = "";
      recognition.onresult = (event) => {
        interimText = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const text = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += text;
          else interimText += text;
        }
        if (wakeWordMatched(finalText || interimText)) {
          setRealtimeVoiceStatus(i18nText("wake_word_heard"), "active");
          try { recognition.stop(); } catch (_err) {}
        }
      };
      recognition.onerror = (event) => {
        const error = event.error || "";
        if (error && error !== "no-speech" && error !== "aborted") {
          setRealtimeVoiceStatus("语音唤醒识别失败：" + error, "error");
        }
      };
      recognition.onend = () => {
        if (wakeWordRecognition === recognition) wakeWordRecognition = null;
        const heardWakeWord = wakeWordMatched(finalText || interimText);
        if (!wakeWordEnabled || realtimeVoiceEnabled) return;
        if (heardWakeWord) {
          appendRealtimePetLine("system", i18nText("wake_word_heard"));
          wakeWordEnabled = false;
          updateWakeWordButton();
          setTimeout(() => startRealtimeVoice(), 120);
          return;
        }
        scheduleWakeWordListen(500);
      };
      try {
        recognition.start();
        setRealtimeVoiceStatus(i18nText("wake_word_listening"), "active");
      } catch (err) {
        setRealtimeVoiceStatus("语音唤醒启动失败：" + err, "error");
        scheduleWakeWordListen(900);
      }
    }

    async function startWakeWord() {
      if (!privacyAccepted) {
        privacyOverlay.classList.remove("hidden");
        return;
      }
      if (!speechRecognitionApi()) {
        setRealtimeVoiceStatus(i18nText("wake_word_unsupported"), "error");
        return;
      }
      if (activeSpeechRecognition) {
        activeSpeechRecognition.stop();
        activeSpeechRecognition = null;
        voiceInputBtn?.classList.remove("listening");
      }
      if (realtimeVoiceEnabled) stopRealtimeVoice();
      wakeWordEnabled = true;
      updateWakeWordButton();
      await ensureRealtimeTTS();
      setRealtimeVoiceStatus(i18nText("wake_word_ready"), "active");
      setRealtimePetChatOpen(true);
      appendRealtimePetLine("system", i18nText("wake_word_ready"));
      scheduleWakeWordListen(200);
    }

    function stopWakeWord(messageText = "", isError = false) {
      wakeWordEnabled = false;
      stopWakeWordRecognition();
      updateWakeWordButton();
      setRealtimeVoiceStatus(messageText || i18nText("wake_word_off"), isError ? "error" : "");
      setRealtimePetChatOpen(false);
    }

    wakeWordBtn?.addEventListener("click", () => {
      if (wakeWordEnabled) stopWakeWord();
      else startWakeWord();
    });

    function appendRealtimePetLine(role, text) {
      if (!realtimePetChat || !realtimePetChatBody) return;
      const clean = String(text || "").trim();
      if (!clean) return;
      realtimePetChat.classList.add("open");
      document.body.classList.add("has-realtime-pet-chat");
      const line = document.createElement("div");
      line.className = `realtime-pet-line ${role}`;
      const speaker = role === "user" ? "你" : (role === "assistant" ? "AI" : "");
      line.textContent = speaker ? `${speaker}: ${clean}` : clean;
      realtimePetChatBody.appendChild(line);
      while (realtimePetChatBody.children.length > 8) {
        realtimePetChatBody.removeChild(realtimePetChatBody.firstChild);
      }
      realtimePetChatBody.scrollTop = realtimePetChatBody.scrollHeight;
    }

    function setRealtimePetChatOpen(open) {
      if (!realtimePetChat) return;
      if (open) {
        realtimePetChat.classList.add("open");
        document.body.classList.add("has-realtime-pet-chat");
      } else if (!realtimePetChatBody || realtimePetChatBody.children.length === 0) {
        realtimePetChat.classList.remove("open");
        document.body.classList.remove("has-realtime-pet-chat");
      }
    }

    function updateRealtimeVoiceButton() {
      if (!realtimeVoiceBtn) return;
      realtimeVoiceBtn.classList.toggle("active", realtimeVoiceEnabled);
      realtimeVoiceBtn.textContent = realtimeVoiceEnabled ? "■" : "◉";
      realtimeVoiceBtn.title = realtimeVoiceEnabled ? i18nText("realtime_stop") : i18nText("realtime_start");
      realtimeVoiceBtn.setAttribute("aria-label", realtimeVoiceBtn.title);
    }

    async function ensureRealtimeTTS() {
      if (ttsConfig.enabled && ttsConfig.auto_play) return true;
      setRealtimeVoiceStatus(i18nText("realtime_tts_hint"), "active");
      try {
        const resp = await fetch("/api/tts/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: true, auto_play: true })
        });
        const data = await resp.json();
        if (data.ok && data.config) {
          ttsConfig = data.config;
          return true;
        }
      } catch (err) {
        console.error("实时对话开启 TTS 失败:", err);
      }
      return false;
    }

    function stopRealtimeRecognition() {
      if (realtimeRestartTimer) {
        clearTimeout(realtimeRestartTimer);
        realtimeRestartTimer = null;
      }
      if (realtimeRecognition) {
        const recognition = realtimeRecognition;
        realtimeRecognition = null;
        recognition.onend = null;
        try { recognition.stop(); } catch (_err) {}
      }
    }

    function scheduleRealtimeListen(delay = 250) {
      if (!realtimeVoiceEnabled || realtimeSending) return;
      if (realtimeRestartTimer) clearTimeout(realtimeRestartTimer);
      realtimeRestartTimer = setTimeout(() => startRealtimeListening(), delay);
    }

    function startRealtimeListening() {
      if (!realtimeVoiceEnabled || realtimeSending) return;
      const Recognition = speechRecognitionApi();
      if (!Recognition) {
        stopRealtimeVoice(i18nText("realtime_unsupported"), true);
        return;
      }
      stopRealtimeRecognition();
      const recognition = new Recognition();
      realtimeRecognition = recognition;
      recognition.lang = (i18nState?.locale || "zh-CN").startsWith("en") ? "en-US" : "zh-CN";
      recognition.interimResults = true;
      recognition.continuous = false;
      let finalText = "";
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const text = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += text;
          else interim += text;
        }
        message.value = (finalText || interim).trim();
      };
      recognition.onerror = (event) => {
        const error = event.error || "";
        if (error && error !== "no-speech" && error !== "aborted") {
          setRealtimeVoiceStatus("实时对话识别失败：" + error, "error");
        }
      };
      recognition.onend = () => {
        if (realtimeRecognition === recognition) realtimeRecognition = null;
        const text = finalText.trim();
        if (realtimeVoiceEnabled && text && !realtimeSending) {
          message.value = "";
          notifyRealtimePetStatus("听到了：" + text.slice(0, 80), "active");
          sendChat({ overrideText: text, fromRealtime: true });
          return;
        }
        scheduleRealtimeListen(400);
      };
      try {
        recognition.start();
        setRealtimeVoiceStatus(i18nText("realtime_listening"), "active");
      } catch (err) {
        setRealtimeVoiceStatus("实时对话启动失败：" + err, "error");
        scheduleRealtimeListen(900);
      }
    }

    async function speakRealtimeReply(text) {
      if (!ttsConfig.enabled) return;
      const speechText = trainingResponseText(text).trim();
      if (!speechText) return;
      setRealtimeVoiceStatus(i18nText("realtime_speaking"), "active");
      try {
        const resp = await fetch("/api/tts/synthesize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: speechText.substring(0, 500) })
        });
        const data = await resp.json();
        if (!data.ok || !data.url) return;
        stopCurrentAudio();
        await new Promise(resolve => {
          const audio = new Audio(data.url);
          currentAudio = audio;
          currentAudioUrl = data.url;
          currentAudioControl = null;
          let settled = false;
          const finish = () => {
            if (settled) return;
            settled = true;
            clearInterval(cancelCheck);
            if (currentAudio === audio) currentAudio = null;
            resetCurrentAudioControl();
            resolve();
          };
          const cancelCheck = setInterval(() => {
            if (!realtimeVoiceEnabled || currentAudio !== audio || audio.paused) finish();
          }, 120);
          audio.onended = finish;
          audio.onerror = finish;
          audio.play().catch(finish);
        });
      } catch (err) {
        console.error("实时对话播放失败:", err);
      }
    }

    function realtimeSenseModes() {
      return {
        screen: !!realtimeScreenToggle?.checked,
        camera: !!realtimeCameraToggle?.checked,
        face: !!realtimeFaceToggle?.checked
      };
    }

    function hasRealtimeSenseEnabled() {
      const modes = realtimeSenseModes();
      return modes.screen || modes.camera || modes.face;
    }

    async function collectRealtimeContext() {
      if (!hasRealtimeSenseEnabled()) return "";
      setRealtimeVoiceStatus("实时对话：正在观察环境...", "active");
      try {
        const cameraInput = document.getElementById("camera-index");
        const cameraIndex = cameraInput ? Math.max(0, parseInt(cameraInput.value || "0", 10) || 0) : 0;
        const resp = await fetch("/api/realtime_observe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ modes: realtimeSenseModes(), camera_index: cameraIndex })
        });
        const data = await resp.json();
        if (data.files) renderFiles(data.files);
        if (data.avatar) renderAvatar(data.avatar);
        if (!data.ok && data.error) {
          appendRealtimePetLine("system", "实时观察失败：" + data.error);
          return "";
        }
        const context = String(data.context || "").trim();
        if (context) appendRealtimePetLine("system", "已叠加感知：" + context.replace(/\s+/g, " ").slice(0, 160));
        return context;
      } catch (err) {
        appendRealtimePetLine("system", "实时观察失败：" + err);
        return "";
      }
    }

    async function startRealtimeVoice() {
      if (!privacyAccepted) {
        privacyOverlay.classList.remove("hidden");
        return;
      }
      if (!speechRecognitionApi()) {
        setRealtimeVoiceStatus(i18nText("realtime_unsupported"), "error");
        return;
      }
      if (activeSpeechRecognition) {
        activeSpeechRecognition.stop();
        activeSpeechRecognition = null;
        voiceInputBtn?.classList.remove("listening");
      }
      if (wakeWordEnabled) stopWakeWord();
      realtimeVoiceEnabled = true;
      updateRealtimeVoiceButton();
      await ensureRealtimeTTS();
      setRealtimeVoiceStatus(i18nText("realtime_ready"), "active");
      setRealtimePetChatOpen(true);
      appendRealtimePetLine("system", i18nText("realtime_ready"));
      scheduleRealtimeListen(200);
    }

    function stopRealtimeVoice(messageText = "", isError = false) {
      realtimeVoiceEnabled = false;
      realtimeSending = false;
      stopRealtimeRecognition();
      updateRealtimeVoiceButton();
      stopCurrentAudio();
      setRealtimeVoiceStatus(messageText || i18nText("realtime_off"), isError ? "error" : "");
      setRealtimePetChatOpen(false);
    }

    realtimeVoiceBtn?.addEventListener("click", () => {
      if (realtimeVoiceEnabled) stopRealtimeVoice();
      else startRealtimeVoice();
    });

    function applyRealtimeLaunchParams() {
      const params = new URLSearchParams(window.location.search || "");
      if (params.get("realtime_prompt") === "1") {
        window.history.replaceState(null, document.title, window.location.pathname || "/");
        openRealtimeLaunchOverlay();
        return;
      }
      if (params.get("realtime") !== "1") return;
      if (realtimeScreenToggle) realtimeScreenToggle.checked = params.get("screen") === "1";
      if (realtimeCameraToggle) realtimeCameraToggle.checked = params.get("camera") === "1";
      if (realtimeFaceToggle) realtimeFaceToggle.checked = params.get("face") === "1";
      window.history.replaceState(null, document.title, window.location.pathname || "/");
      setTimeout(() => {
        if (!realtimeVoiceEnabled) startRealtimeVoice();
      }, 450);
    }

    function openRealtimeLaunchOverlay() {
      if (!realtimeLaunchOverlay) return;
      if (launchRealtimeScreen) launchRealtimeScreen.checked = !!realtimeScreenToggle?.checked;
      if (launchRealtimeCamera) launchRealtimeCamera.checked = !!realtimeCameraToggle?.checked;
      if (launchRealtimeFace) launchRealtimeFace.checked = !!realtimeFaceToggle?.checked;
      realtimeLaunchOverlay.classList.add("open");
    }

    function closeRealtimeLaunchOverlay() {
      realtimeLaunchOverlay?.classList.remove("open");
    }

    launchRealtimeCancel?.addEventListener("click", closeRealtimeLaunchOverlay);
    realtimeLaunchOverlay?.addEventListener("click", event => {
      if (event.target === realtimeLaunchOverlay) closeRealtimeLaunchOverlay();
    });
    launchRealtimeStart?.addEventListener("click", () => {
      if (realtimeScreenToggle) realtimeScreenToggle.checked = !!launchRealtimeScreen?.checked;
      if (realtimeCameraToggle) realtimeCameraToggle.checked = !!launchRealtimeCamera?.checked;
      if (realtimeFaceToggle) realtimeFaceToggle.checked = !!launchRealtimeFace?.checked;
      closeRealtimeLaunchOverlay();
      if (!realtimeVoiceEnabled) startRealtimeVoice();
    });

    async function captureVoiceFeatures(durationMs = 2600) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("当前浏览器无法访问麦克风");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.55;
      source.connect(analyser);
      const freq = new Uint8Array(analyser.frequencyBinCount);
      const wave = new Uint8Array(analyser.fftSize);
      const bands = new Array(16).fill(0);
      let rmsSum = 0;
      let zcrSum = 0;
      let frames = 0;
      const started = performance.now();
      try {
        while (performance.now() - started < durationMs) {
          analyser.getByteFrequencyData(freq);
          analyser.getByteTimeDomainData(wave);
          const bandSize = Math.max(1, Math.floor(freq.length / bands.length));
          for (let band = 0; band < bands.length; band += 1) {
            let total = 0;
            const from = band * bandSize;
            const to = Math.min(freq.length, from + bandSize);
            for (let i = from; i < to; i += 1) total += freq[i] / 255;
            bands[band] += total / Math.max(1, to - from);
          }
          let energy = 0;
          let zcr = 0;
          let prev = wave[0] - 128;
          for (let i = 0; i < wave.length; i += 1) {
            const centered = (wave[i] - 128) / 128;
            energy += centered * centered;
            const current = wave[i] - 128;
            if ((prev < 0 && current >= 0) || (prev >= 0 && current < 0)) zcr += 1;
            prev = current;
          }
          rmsSum += Math.sqrt(energy / wave.length);
          zcrSum += zcr / wave.length;
          frames += 1;
          await new Promise(resolve => setTimeout(resolve, 80));
        }
      } finally {
        stream.getTracks().forEach(track => track.stop());
        await audioCtx.close().catch(() => {});
      }
      if (frames < 8) throw new Error("采样时间太短");
      const averagedBands = bands.map(v => v / frames);
      const maxBand = Math.max(...averagedBands, 0.0001);
      return averagedBands.map(v => Number((v / maxBand).toFixed(6)))
        .concat([
          Number((rmsSum / frames).toFixed(6)),
          Number((zcrSum / frames).toFixed(6))
        ]);
    }

    function setTTSControlState(control, state, defaultLabel = "▶") {
      if (!control) return;
      control.dataset.ttsState = state;
      control.classList.toggle("playing", state === "playing" || state === "paused");
      if (state === "playing") {
        control.textContent = "⏸";
        control.title = i18nText("pause_voice");
      } else if (state === "paused") {
        control.textContent = "▶";
        control.title = i18nText("resume_voice");
      } else {
        control.textContent = control.dataset.defaultLabel || defaultLabel;
        control.title = control.dataset.defaultTitle || i18nText("play_voice");
      }
    }

    function resetCurrentAudioControl() {
      if (currentAudioControl) {
        setTTSControlState(currentAudioControl, "idle");
      }
      currentAudioControl = null;
      currentAudioUrl = "";
    }

    function stopCurrentAudio() {
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.onended = null;
        currentAudio.onerror = null;
        currentAudio = null;
      }
      resetCurrentAudioControl();
    }

    function playAudioUrl(url, control = null, defaultLabel = "▶") {
      if (!url) return;
      if (currentAudio && currentAudioUrl === url && currentAudioControl === control) {
        if (currentAudio.paused) {
          currentAudio.play().then(() => {
            setTTSControlState(control, "playing", defaultLabel);
          }).catch(err => console.error("TTS 继续播放失败:", err));
        } else {
          currentAudio.pause();
          setTTSControlState(control, "paused", defaultLabel);
        }
        return;
      }
      stopCurrentAudio();
      currentAudio = new Audio(url);
      currentAudioUrl = url;
      currentAudioControl = control;
      if (control) {
        control.dataset.defaultLabel = defaultLabel;
        if (!control.dataset.defaultTitle) control.dataset.defaultTitle = control.title || i18nText("play_voice");
      }
      currentAudio.onended = () => {
        currentAudio = null;
        resetCurrentAudioControl();
      };
      currentAudio.onerror = () => {
        currentAudio = null;
        resetCurrentAudioControl();
      };
      currentAudio.play().then(() => {
        setTTSControlState(control, "playing", defaultLabel);
      }).catch(err => {
        console.error("TTS 播放失败:", err);
        currentAudio = null;
        resetCurrentAudioControl();
      });
    }

    // 播放语音
    async function playTTS(text, control = null) {
      if (!ttsConfig.enabled) return;
      const speechText = trainingResponseText(text).trim();
      if (!speechText) return;

      if (currentAudio && currentAudioControl === control && control?.dataset.audioText === speechText) {
        playAudioUrl(currentAudioUrl, control, "▶");
        return;
      }

      try {
        const resp = await fetch("/api/tts/synthesize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: speechText.substring(0, 500) }) // 限制长度
        });
        const data = await resp.json();
        if (data.ok && data.url) {
          if (control) control.dataset.audioText = speechText;
          playAudioUrl(data.url, control, "▶");
        }
      } catch (err) {
        console.error("TTS 播放失败:", err);
        resetCurrentAudioControl();
      }
    }

    function assistantTimeLabel(value) {
      if (!value) return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const date = new Date(Number(value) * 1000);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    function createWelcomeMessage() {
      const welcome = document.createElement("div");
      welcome.className = "msg assistant msg-enter";
      welcome.id = "welcome-message";
      const meta = document.createElement("div");
      meta.className = "assistant-meta";
      const name = document.createElement("strong");
      name.textContent = "Companion";
      const time = document.createElement("span");
      time.textContent = assistantTimeLabel();
      meta.append(name, time);
      const body = document.createElement("div");
      body.className = "msg-body";
      const text = document.createElement("div");
      text.className = "msg-text";
      text.dataset.i18n = "welcome_message";
      text.textContent = i18nText("welcome_message");
      body.appendChild(text);
      welcome.append(meta, body);
      return welcome;
    }

    function resetChatView() {
      chat.innerHTML = "";
      chat.appendChild(createWelcomeMessage());
      currentFileId = "";
      lastUserText = "";
      lastAssistantText = "";
      lastEmotion = null;
    }

    function formatRecentTime(value) {
      const ts = Number(value || 0) * 1000;
      if (!ts) return "";
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) return "";
      const now = new Date();
      if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      }
      return `${date.getMonth() + 1}/${date.getDate()}`;
    }

    function setConversationTitle(title) {
      const clean = String(title || "").trim() || "新对话";
      if (pageTitle) pageTitle.textContent = clean;
      document.title = `${clean} - Companion AI`;
    }

    function renderRecentChats(chats, activeId = currentConversationId) {
      recentChats = Array.isArray(chats) ? chats : [];
      if (!recentChatList) return;
      recentChatList.innerHTML = "";
      if (!recentChats.length) {
        const empty = document.createElement("div");
        empty.className = "recent-chat-empty";
        empty.textContent = "暂无最近对话";
        recentChatList.appendChild(empty);
        return;
      }
      recentChats.slice(0, 8).forEach(item => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `recent-chat ${item.id === activeId ? "active" : ""}`;
        const title = document.createElement("span");
        title.textContent = item.title || "新对话";
        const time = document.createElement("small");
        time.textContent = formatRecentTime(item.updated_at) || "刚刚";
        btn.append(title, time);
        btn.addEventListener("click", () => openRecentChat(item.id));
        recentChatList.appendChild(btn);
      });
    }

    function openRecentChat(chatId) {
      const item = recentChats.find(chat => chat.id === chatId);
      if (!item) return;
      currentConversationId = item.id;
      setConversationTitle(item.title);
      chat.innerHTML = "";
      const messages = Array.isArray(item.messages) ? item.messages : [];
      if (!messages.length) {
        chat.appendChild(createWelcomeMessage());
      } else {
        messages.forEach(msg => addMsg(msg.role === "assistant" ? "assistant" : "user", msg.text || "", { time: msg.time, skipAutoTTS: true, animate: false }));
      }
      renderRecentChats(recentChats, currentConversationId);
      message.focus();
    }

    async function loadRecentChats() {
      try {
        const resp = await fetch("/api/recent_chats");
        const data = await resp.json();
        if (data.ok) {
          renderRecentChats(data.chats || []);
          if (!currentConversationId && data.chats && data.chats.length) {
            openRecentChat(data.chats[0].id);
          }
        }
      } catch (_err) {
        renderRecentChats([]);
      }
    }

    function addMsg(role, text, options = {}) {
      const div = document.createElement("div");
      div.className = `msg ${role}`;
      if (options.animate !== false) div.classList.add("msg-enter");
      const display = role === "assistant" ? assistantDisplayParts(text) : { answer: String(text || ""), meta: "" };
      
      if (role === "assistant") {
        // 添加语音播放按钮
        const btn = document.createElement("button");
        btn.className = "tts-play-btn";
        btn.type = "button";
        btn.textContent = "▶";
        btn.setAttribute("aria-label", i18nText("play_voice"));
        btn.title = i18nText("play_voice");
        btn.dataset.defaultLabel = "▶";
        btn.dataset.defaultTitle = i18nText("play_voice");
        btn.onclick = () => playTTS(display.answer || text, btn);
        div.appendChild(btn);
      }
      
      const bodyDiv = document.createElement("div");
      bodyDiv.className = "msg-body";
      if (role === "assistant") {
        const meta = document.createElement("div");
        meta.className = "assistant-meta";
        const name = document.createElement("strong");
        name.textContent = "Companion";
        const time = document.createElement("span");
        time.textContent = assistantTimeLabel(options.time);
        meta.append(name, time);
        div.appendChild(meta);
      }
      const textDiv = document.createElement("div");
      textDiv.className = "msg-text";
      textDiv.textContent = display.answer || text;
      bodyDiv.appendChild(textDiv);

      if (role === "assistant" && display.meta) {
        const metaBtn = document.createElement("button");
        metaBtn.type = "button";
        metaBtn.className = "emotion-toggle";
        metaBtn.textContent = "隐藏情感理解";
        const metaDiv = document.createElement("div");
        metaDiv.className = "emotion-meta open";
        metaDiv.textContent = display.meta;
        metaBtn.addEventListener("click", () => {
          const open = metaDiv.classList.toggle("open");
          metaBtn.textContent = open ? "隐藏情感理解" : "查看情感理解";
        });
        bodyDiv.append(metaBtn, metaDiv);
      }
      if (role === "assistant" && display.learningRecord) {
        bodyDiv.appendChild(renderLearningRecord(display.learningRecord));
      }
      div.appendChild(bodyDiv);
      
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      
      // 自动播放
      if (role === "assistant" && ttsConfig.enabled && ttsConfig.auto_play && !suppressNextAutoTTS && !options.skipAutoTTS) {
        setTimeout(() => playTTS(display.answer || text), 300);
      }
      suppressNextAutoTTS = false;
    }

    function assistantDisplayParts(text) {
      const raw = String(text || "").trim();
      if (!raw) return { answer: "", meta: "", learningRecord: null };
      const parsed = extractLearningRecord(raw);
      const visibleRaw = parsed.visibleText;
      const answer = trainingResponseText(visibleRaw);
      const meta = [];
      visibleRaw.split(/\n\s*\n/).forEach(part => {
        const trimmed = part.trim();
        if (!trimmed) return;
        if (trimmed.includes("情感理解：") && trimmed.includes("回应策略：")) {
          meta.push(trimmed);
          return;
        }
        if (trimmed.startsWith("我先判断这是") || trimmed.startsWith("我根据已学习的情感样本判断这是")) {
          meta.push(trimmed);
        }
      });
      return { answer: answer || visibleRaw, meta: meta.join("\n\n"), learningRecord: parsed.record };
    }

    function extractLearningRecord(text) {
      const start = "[[LEARNING_RECORD_JSON]]";
      const end = "[[/LEARNING_RECORD_JSON]]";
      const raw = String(text || "");
      const startIndex = raw.indexOf(start);
      const endIndex = raw.indexOf(end);
      if (startIndex < 0 || endIndex < startIndex) {
        return { visibleText: raw, record: null };
      }
      const before = raw.slice(0, startIndex);
      const after = raw.slice(endIndex + end.length);
      const payload = raw.slice(startIndex + start.length, endIndex);
      try {
        return {
          visibleText: (before + after).trim(),
          record: JSON.parse(payload)
        };
      } catch (err) {
        console.warn("学习记录解析失败:", err);
        return { visibleText: (before + after).trim() || raw, record: null };
      }
    }

    function renderLearningRecord(record) {
      const details = document.createElement("details");
      details.className = "learning-record";

      const summary = document.createElement("summary");
      const sourceCount = Array.isArray(record.sources) ? record.sources.length : 0;
      summary.textContent = `学习记录：${record.query || "未命名主题"} · ${sourceCount} 个来源`;
      details.appendChild(summary);

      const body = document.createElement("div");
      body.className = "learning-record-body";

      const learnedSection = document.createElement("div");
      learnedSection.className = "learning-record-section";
      const learnedTitle = document.createElement("strong");
      learnedTitle.textContent = "形成内容";
      const learnedList = document.createElement("ul");
      learnedList.className = "learning-record-list";
      const learnedItems = Array.isArray(record.learned) && record.learned.length ? record.learned : [record.summary || "已完成联网学习。"];
      learnedItems.forEach(item => {
        const li = document.createElement("li");
        li.textContent = String(item || "").trim();
        learnedList.appendChild(li);
      });
      learnedSection.append(learnedTitle, learnedList);
      body.appendChild(learnedSection);

      const sourceSection = document.createElement("div");
      sourceSection.className = "learning-record-section";
      const sourceTitle = document.createElement("strong");
      sourceTitle.textContent = "浏览数据";
      const sourceList = document.createElement("ul");
      sourceList.className = "learning-record-list";
      (record.sources || []).forEach(source => {
        const item = document.createElement("li");
        item.className = "learning-source";
        const link = document.createElement("a");
        link.href = source.url || "#";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.domain || source.title || source.url || "来源";
        const meta = document.createElement("div");
        meta.className = "learning-source-meta";
        const length = source.content_length ? ` · 抓取 ${source.content_length} 字符` : "";
        meta.textContent = `信任度 ${source.trust_score ?? "?"}${length}`;
        item.append(link, meta);
        if (source.excerpt) {
          const excerpt = document.createElement("div");
          excerpt.className = "learning-source-excerpt";
          excerpt.textContent = String(source.excerpt).replace(/\s+/g, " ").trim();
          item.appendChild(excerpt);
        }
        sourceList.appendChild(item);
      });
      sourceSection.append(sourceTitle, sourceList);
      body.appendChild(sourceSection);

      details.appendChild(body);
      return details;
    }

    function addImagePreview(src, name) {
      const wrap = document.createElement("div");
      wrap.className = "preview";
      const img = document.createElement("img");
      img.src = src;
      img.alt = name;
      wrap.appendChild(img);
      chat.appendChild(wrap);
      chat.scrollTop = chat.scrollHeight;
    }

    function addFeedback() {
      if (!lastUserText || !lastAssistantText) return;
      const wrap = document.createElement("div");
      wrap.className = "feedback";
      const answerGroup = document.createElement("span");
      answerGroup.className = "feedback-group feedback-answer";
      const good = document.createElement("button");
      good.type = "button";
      good.className = "good";
      good.textContent = "有帮助";
      const bad = document.createElement("button");
      bad.type = "button";
      bad.textContent = "不对";
      good.addEventListener("click", () => sendFeedback(1, wrap, answerGroup));
      bad.addEventListener("click", () => openCorrection(wrap, answerGroup));
      answerGroup.append(good, bad);
      wrap.appendChild(answerGroup);
      if (lastEmotion) {
        const emotionGroup = document.createElement("span");
        emotionGroup.className = "feedback-group feedback-emotion";
        const emotionGood = document.createElement("button");
        emotionGood.type = "button";
        emotionGood.className = "emotion-good";
        emotionGood.textContent = "情感对";
        const emotionBad = document.createElement("button");
        emotionBad.type = "button";
        emotionBad.className = "emotion-bad";
        emotionBad.textContent = "情感不对";
        emotionGood.addEventListener("click", () => sendEmotionFeedback(1, "", wrap, emotionGroup));
        emotionBad.addEventListener("click", () => openEmotionCorrection(wrap, emotionGroup));
        emotionGroup.append(emotionGood, emotionBad);
        wrap.appendChild(emotionGroup);
      }
      chat.appendChild(wrap);
      chat.scrollTop = chat.scrollHeight;
    }

    function extractEmotion(text) {
      const lines = String(text || "").split(/\r?\n/);
      for (const line of lines) {
        const match = line.match(/^(.*?)情感理解：(.+?)（/);
        if (match) {
          return {
            source: match[1].replace(/的$/, "") || "文本",
            label: match[2].trim(),
            text: lastUserText
          };
        }
      }
      return null;
    }

    function trainingResponseText(text) {
      const raw = extractLearningRecord(String(text || "")).visibleText.trim();
      if (!raw) return "";
      const kept = [];
      raw.split(/\n\s*\n/).forEach(part => {
        const trimmed = part.trim();
        if (!trimmed) return;
        if (trimmed.includes("情感理解：") && trimmed.includes("回应策略：")) return;
        if (trimmed.startsWith("我先判断这是") || trimmed.startsWith("我根据已学习的情感样本判断这是")) return;
        kept.push(trimmed);
      });
      return kept.join("\n\n").trim() || raw;
    }

    // -- Correction modal --
    let correctOverlay = null;
    function ensureCorrectionModal() {
      if (correctOverlay) return;
      correctOverlay = document.createElement("div");
      correctOverlay.className = "correct-overlay";
      correctOverlay.innerHTML = `
        <div class="correct-panel">
          <h3>纠正回答</h3>
          <div class="correct-prompt" id="correct-prompt-text"></div>
          <div class="correct-response" id="correct-response-text"></div>
          <label for="correct-input">你期望的回答：</label>
          <textarea id="correct-input" placeholder="请输入你希望 AI 回答的内容..."></textarea>
          <div class="correct-actions">
            <button type="button" class="cancel-btn" id="correct-cancel">取消</button>
            <button type="button" class="submit-btn" id="correct-submit">提交纠正</button>
          </div>
        </div>`;
      document.body.appendChild(correctOverlay);
      document.getElementById("correct-cancel").addEventListener("click", closeCorrection);
      correctOverlay.addEventListener("click", (e) => {
        if (e.target === correctOverlay) closeCorrection();
      });
      document.getElementById("correct-submit").addEventListener("click", submitCorrection);
    }

    let _correctFeedbackGroup = null;
    function openCorrection(wrap, group) {
      ensureCorrectionModal();
      _correctFeedbackGroup = group;
      document.getElementById("correct-prompt-text").textContent = "问题：" + lastUserText;
      document.getElementById("correct-response-text").textContent = "AI 回答：" + trainingResponseText(lastAssistantText);
      document.getElementById("correct-input").value = "";
      correctOverlay.classList.add("open");
      setTimeout(() => document.getElementById("correct-input").focus(), 50);
    }

    function closeCorrection() {
      if (correctOverlay) correctOverlay.classList.remove("open");
      _correctFeedbackGroup = null;
    }

    async function submitCorrection() {
      const corrected = document.getElementById("correct-input").value.trim();
      if (!corrected) {
        document.getElementById("correct-input").focus();
        return;
      }
      const btn = document.getElementById("correct-submit");
      btn.disabled = true;
      btn.textContent = "提交中...";
      try {
        const resp = await fetch("/api/correct", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: lastUserText,
            wrong_response: trainingResponseText(lastAssistantText),
            correct_response: corrected
          })
        });
        const data = await resp.json();
        if (data.ok) {
          renderTraining(data.training);
          renderAvatar(data.avatar);
          if (_correctFeedbackGroup) {
            _correctFeedbackGroup.textContent = "已纠正：下次会记住的";
          }
          closeCorrection();
        } else {
          alert("提交失败：" + (data.error || "未知错误"));
        }
      } catch (err) {
        alert("提交失败：" + err);
      } finally {
        btn.disabled = false;
        btn.textContent = "提交纠正";
      }
    }

    let emotionOverlay = null;
    let _emotionFeedbackGroup = null;
    function ensureEmotionModal() {
      if (emotionOverlay) return;
      emotionOverlay = document.createElement("div");
      emotionOverlay.className = "correct-overlay";
      emotionOverlay.innerHTML = `
        <div class="correct-panel">
          <h3>纠正情感判断</h3>
          <div class="correct-prompt" id="emotion-prompt-text"></div>
          <div class="correct-response" id="emotion-response-text"></div>
          <label for="emotion-input">你觉得正确的情感是：</label>
          <textarea id="emotion-input" placeholder="例如：焦虑、委屈、开心、平静、困惑，也可以写一句解释..."></textarea>
          <div class="correct-actions">
            <button type="button" class="cancel-btn" id="emotion-cancel">取消</button>
            <button type="button" class="submit-btn" id="emotion-submit">提交情感纠正</button>
          </div>
        </div>`;
      document.body.appendChild(emotionOverlay);
      document.getElementById("emotion-cancel").addEventListener("click", closeEmotionCorrection);
      emotionOverlay.addEventListener("click", (e) => {
        if (e.target === emotionOverlay) closeEmotionCorrection();
      });
      document.getElementById("emotion-submit").addEventListener("click", submitEmotionCorrection);
    }

    function openEmotionCorrection(wrap, group) {
      if (!lastEmotion) return;
      ensureEmotionModal();
      _emotionFeedbackGroup = group;
      document.getElementById("emotion-prompt-text").textContent = "原文：" + lastEmotion.text;
      document.getElementById("emotion-response-text").textContent = "AI 判断：" + lastEmotion.label;
      document.getElementById("emotion-input").value = "";
      emotionOverlay.classList.add("open");
      setTimeout(() => document.getElementById("emotion-input").focus(), 50);
    }

    function closeEmotionCorrection() {
      if (emotionOverlay) emotionOverlay.classList.remove("open");
      _emotionFeedbackGroup = null;
    }

    async function sendEmotionFeedback(rating, correctEmotion, wrap, group) {
      if (!lastEmotion) return;
      group.querySelectorAll("button").forEach(btn => btn.disabled = true);
      const resp = await fetch("/api/emotion_feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: lastEmotion.text,
          predicted_emotion: lastEmotion.label,
          rating,
          correct_emotion: correctEmotion || ""
        })
      });
      const data = await resp.json();
      renderTraining(data.training);
      renderAvatar(data.avatar);
      group.textContent = rating > 0 ? " 情感判断正确" : " 情感判断已纠正";
    }

    async function submitEmotionCorrection() {
      const corrected = document.getElementById("emotion-input").value.trim();
      if (!corrected) {
        document.getElementById("emotion-input").focus();
        return;
      }
      const btn = document.getElementById("emotion-submit");
      btn.disabled = true;
      btn.textContent = "提交中...";
      try {
        await sendEmotionFeedback(-1, corrected, null, _emotionFeedbackGroup);
        closeEmotionCorrection();
      } catch (err) {
        alert("提交失败：" + err);
      } finally {
        btn.disabled = false;
        btn.textContent = "提交情感纠正";
      }
    }

    function renderMemoryOrbit(data) {
      if (!memoryNodes || !data) return;
      const labels = { profile: i18nText("personal_background"), preferences: i18nText("preferences"), facts: i18nText("facts_todos") };
      const positions = [
        ["18%", "28%"], ["78%", "25%"], ["18%", "70%"],
        ["80%", "68%"], ["50%", "13%"], ["50%", "86%"]
      ];
      const items = [];
      ["profile", "preferences", "facts"].forEach(bucket => {
        (data[bucket] || []).slice(-2).forEach(item => {
          const text = String(item.text || "").trim();
          if (text) items.push({ bucket, text });
        });
      });
      memoryNodes.innerHTML = "";
      if (!items.length) {
        const node = document.createElement("div");
        node.className = "memory-node empty";
        node.style.left = "50%";
        node.style.top = "72%";
        const title = document.createElement("strong");
        title.textContent = i18nText("no_long_term_memory");
        const body = document.createElement("span");
        body.textContent = i18nText("memory_empty_hint");
        node.append(title, body);
        memoryNodes.appendChild(node);
        return;
      }
      items.slice(0, positions.length).forEach((item, index) => {
        const node = document.createElement("div");
        node.className = "memory-node";
        node.style.left = positions[index][0];
        node.style.top = positions[index][1];
        const title = document.createElement("strong");
        title.textContent = labels[item.bucket] || "记忆";
        const body = document.createElement("span");
        body.textContent = item.text;
        node.title = `${title.textContent}：${item.text}`;
        node.append(title, body);
        memoryNodes.appendChild(node);
      });
    }

    function renderMemory(data) {
      if (!data) return;
      lastMemoryData = data;
      const labels = { profile: i18nText("personal_background"), preferences: i18nText("preferences"), facts: i18nText("facts_todos") };
      renderMemoryOrbit(data);
      memory.textContent = ["profile", "preferences", "facts"].map(bucket => {
        const items = data[bucket] || [];
        const body = items.length ? items.slice(-8).map(x => `- ${x.text}`).join("\n") : `- ${i18nText("none")}`;
        return `${labels[bucket]}${i18nText("colon")}\n${body}`;
      }).join("\n\n");
    }

    function renderGrowth(growth) {
      const panel = document.getElementById("growth-summary");
      if (!panel || !growth) return;
      const profile = growth.relationship_profile || {};
      const rel = growth.relationship || {};
      const hasIdentity = !!growth.identity_setup_done;
      const notes = ((growth.personality || {}).growth_notes || []).slice(-1);
      const milestones = (growth.milestones || []).slice(-1);
      const note = notes.length ? notes[0].text : (milestones.length ? milestones[0].text : "还没有明显变化，多聊几次就会留下痕迹。");
      panel.innerHTML = "";
      const title = document.createElement("h4");
      title.textContent = "关系成长";
      const row1 = document.createElement("div");
      row1.className = "growth-row";
      const row1Label = document.createElement("span");
      row1Label.textContent = hasIdentity ? "关系" : "角色";
      const row1Value = document.createElement("strong");
      row1Value.textContent = hasIdentity ? (profile.current_label || profile.label || "朋友") : "未设置";
      row1.append(row1Label, row1Value);
      const row2 = document.createElement("div");
      row2.className = "growth-row";
      const row2Label = document.createElement("span");
      row2Label.textContent = "阶段";
      const row2Value = document.createElement("strong");
      row2Value.textContent = rel.stage || "初识";
      row2.append(row2Label, row2Value);
      const row3 = document.createElement("div");
      row3.className = "growth-row";
      const row3Label = document.createElement("span");
      row3Label.textContent = "天数";
      const row3Value = document.createElement("strong");
      row3Value.textContent = String(rel.contact_days || 0);
      row3.append(row3Label, row3Value);
      const body = document.createElement("div");
      body.className = "growth-note";
      body.textContent = hasIdentity ? (note || "") : `未设置角色；当前数值来自聊天自动成长记录，不是人设。${note || ""}`;
      panel.append(title, row1, row2, row3, body);
    }

    function renderAuditStatus(auditStatus) {
      let el = document.getElementById("audit-indicator");
      if (!el) {
        el = document.createElement("div");
        el.id = "audit-indicator";
        el.className = "audit-indicator";
        chat.appendChild(el);
      }
      if (!auditStatus.enabled) {
        el.style.display = "none";
        return;
      }
      el.style.display = "block";
      const statusMap = {
        processing: "🔍 对话审计中...",
        completed: "✓ 审计完成",
        failed: "✗ 审计失败",
      };
      const statusText = statusMap[auditStatus.current_status] || "";
      if (auditStatus.current_status === "processing") {
        el.className = "audit-indicator audit-processing";
        el.textContent = statusText;
      } else if (auditStatus.current_status === "completed") {
        el.className = "audit-indicator audit-completed";
        el.textContent = statusText;
        setTimeout(() => {
          if (el) el.style.display = "none";
        }, 3000);
      } else if (auditStatus.current_status === "failed") {
        el.className = "audit-indicator audit-failed";
        el.textContent = statusText;
        setTimeout(() => {
          if (el) el.style.display = "none";
        }, 3000);
      } else {
        el.style.display = "none";
      }
    }

    function renderAuditCorrections(corrections) {
      if (!corrections || !corrections.length) return;
      for (const c of corrections) {
        const div = document.createElement("div");
        div.className = "audit-correction";
        const label = document.createElement("div");
        label.className = "correction-label";
        label.textContent = "审计修正建议";
        div.appendChild(label);
        const text = document.createElement("div");
        text.className = "correction-text";
        text.textContent = c.suggested_response || "";
        div.appendChild(text);
        if (c.reason || c.overall_correctness != null) {
          const meta = document.createElement("div");
          meta.className = "correction-meta";
          const parts = [];
          if (c.overall_correctness != null) parts.push("正确性: " + (c.overall_correctness * 100).toFixed(0) + "%");
          if (c.overall_score != null) parts.push("质量: " + (c.overall_score * 100).toFixed(0) + "%");
          if (c.reason) parts.push(c.reason);
          meta.textContent = parts.join(" | ");
          div.appendChild(meta);
        }
        chat.appendChild(div);
      }
      chat.scrollTop = chat.scrollHeight;
    }

    function renderTaskStatus(taskStatus) {
      if (!taskStatus || taskStatus.state === "idle") return;
      let el = document.getElementById("task-indicator");
      if (!el) {
        el = document.createElement("div");
        el.id = "task-indicator";
        el.className = "task-indicator";
        chat.appendChild(el);
      }
      el.style.display = "block";
      if (taskStatus.state === "rebuilding") {
        el.className = "task-indicator task-processing";
        el.textContent = "⚙️ " + (taskStatus.message || "处理中...");
      } else if (taskStatus.state === "done") {
        el.className = "task-indicator task-completed";
        el.textContent = "✓ " + (taskStatus.message || "完成");
        setTimeout(() => { if (el) el.style.display = "none"; }, 5000);
      } else if (taskStatus.state === "error") {
        el.className = "task-indicator task-failed";
        el.textContent = "✗ " + (taskStatus.message || "失败");
        setTimeout(() => { if (el) el.style.display = "none"; }, 5000);
      }
    }

    function renderEmotionChart(trend) {
      const svg = document.getElementById("emotion-svg");
      const summary = document.getElementById("emotion-summary");
      if (!svg || !trend || !trend.length) return;

      const W = 300, H = 90;
      const padL = 8, padR = 8, padT = 8, padB = 20;
      const chartW = W - padL - padR;
      const chartH = H - padT - padB;
      const midY = padT + chartH / 2;
      const n = trend.length;
      const stepX = chartW / Math.max(1, n - 1);

      const points = trend.map((d, i) => {
        const x = padL + stepX * i;
        const hasData = d.user_messages > 0;
        let y = midY;
        if (hasData) {
          const val = Math.max(-3, Math.min(3, d.avg_compound || 0));
          y = midY - (val / 3) * (chartH / 2 - 4);
        }
        return { x, y, hasData, ...d };
      });

      let linePath = "";
      let areaPath = "";
      const dataPoints = points.filter(p => p.hasData);
      if (dataPoints.length >= 2) {
        linePath = dataPoints.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
        areaPath = linePath +
          ` L ${dataPoints[dataPoints.length - 1].x.toFixed(1)} ${midY.toFixed(1)}` +
          ` L ${dataPoints[0].x.toFixed(1)} ${midY.toFixed(1)} Z`;
      }

      svg.innerHTML = `
        <line class="axis-line" x1="${padL}" y1="${midY}" x2="${W - padR}" y2="${midY}" />
        ${areaPath ? `<path class="trend-area" d="${areaPath}" />` : ""}
        ${linePath ? `<path class="trend-line" d="${linePath}" />` : ""}
        ${points.map((p, i) => `
          <circle class="trend-dot ${p.hasData ? "" : "no-data"}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.5" />
          <text class="day-label" x="${p.x.toFixed(1)}" y="${H - 4}">${p.label || ""}</text>
        `).join("")}
      `;

      const daysWithData = trend.filter(d => d.user_messages > 0);
      if (daysWithData.length) {
        const avg = daysWithData.reduce((s, d) => s + (d.avg_compound || 0), 0) / daysWithData.length;
        let mood = "平稳";
        if (avg >= 1.0) mood = "很开心";
        else if (avg >= 0.4) mood = "不错";
        else if (avg <= -1.0) mood = "比较低落";
        else if (avg <= -0.4) mood = "有点烦躁";
        summary.innerHTML = `<span>最近 ${daysWithData.length} 天</span><span>心情指数：${avg >= 0 ? "+" : ""}${avg.toFixed(2)} · ${mood}</span>`;
      } else {
        summary.innerHTML = `<span>最近 7 天</span><span>暂无数据</span>`;
      }
    }

    function renderDiary(entries) {
      const list = document.getElementById("diary-list");
      if (!list) return;

      if (!entries || !entries.length) {
        list.innerHTML = '<div class="diary-empty">还没有日记，多聊几天试试~</div>';
        return;
      }

      list.innerHTML = entries.map(entry => {
        const avg = entry.avg_compound || 0;
        let moodClass = "";
        if (avg < -0.3) moodClass = "sad";
        else if (Math.abs(avg) < 0.3) moodClass = "calm";
        return `
          <div class="diary-entry">
            <div class="diary-date">
              <span>${entry.date || ""}</span>
              <span class="diary-mood ${moodClass}">${entry.mood_label || entry.top_emotion || ""}</span>
            </div>
            <div class="diary-content">${(entry.content || "").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>
          </div>
        `;
      }).join("");
    }

    function formatMomentTime(value) {
      const raw = String(value || "");
      if (!raw) return "";
      return raw.replace("T", " ").slice(0, 16);
    }

    function renderMoments(data) {
      if (!momentsList) return;
      const posts = ((data && data.posts) || []).slice().reverse();
      momentsList.innerHTML = "";
      if (!posts.length) {
        const empty = document.createElement("div");
        empty.className = "moments-empty";
        empty.textContent = "还没有动态。点“AI发一条”试试。";
        momentsList.appendChild(empty);
        return;
      }
      posts.forEach(post => {
        const card = document.createElement("article");
        card.className = "moment-post";

        const avatarEl = document.createElement("div");
        avatarEl.className = "moment-avatar";
        avatarEl.textContent = String(post.avatar || post.author || "AI").slice(0, 2);

        const main = document.createElement("div");
        main.className = "moment-main";

        const meta = document.createElement("div");
        meta.className = "moment-meta";
        const author = document.createElement("span");
        author.className = "moment-author";
        author.textContent = post.author || "Companion AI";
        const timeEl = document.createElement("span");
        timeEl.textContent = formatMomentTime(post.created_at);
        meta.append(author, timeEl);

        const content = document.createElement("div");
        content.className = "moment-content";
        content.textContent = post.content || "";

        main.append(meta, content);
        if (post.mood) {
          const mood = document.createElement("div");
          mood.className = "moment-mood";
          mood.textContent = post.mood;
          main.appendChild(mood);
        }

        const actions = document.createElement("div");
        actions.className = "moment-post-actions";
        const likeBtn = document.createElement("button");
        likeBtn.type = "button";
        likeBtn.className = post.liked_by_user ? "liked" : "";
        likeBtn.textContent = `${post.liked_by_user ? "已赞" : "赞"} ${post.likes || 0}`;
        likeBtn.addEventListener("click", () => updateMoment({ action: "like", id: post.id, liked: !post.liked_by_user }));
        const commentToggle = document.createElement("button");
        commentToggle.type = "button";
        commentToggle.textContent = "评论";
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.textContent = "删除";
        deleteBtn.addEventListener("click", () => {
          if (confirm("删除这条 AI朋友圈动态？")) updateMoment({ action: "delete", id: post.id });
        });
        actions.append(likeBtn, commentToggle, deleteBtn);
        main.appendChild(actions);

        const comments = document.createElement("div");
        comments.className = "moment-comments";
        comments.style.display = (post.comments || []).length ? "grid" : "none";
        (post.comments || []).forEach(comment => {
          const item = document.createElement("div");
          item.className = "moment-comment";
          const who = document.createElement("strong");
          who.textContent = `${comment.author || "你"}：`;
          const text = document.createElement("span");
          text.textContent = comment.text || "";
          item.append(who, text);
          comments.appendChild(item);
        });

        const commentRow = document.createElement("div");
        commentRow.className = "moment-comment-row";
        commentRow.style.display = "none";
        const commentInput = document.createElement("input");
        commentInput.placeholder = "写评论";
        commentInput.maxLength = 300;
        const sendComment = document.createElement("button");
        sendComment.type = "button";
        sendComment.textContent = "发送";
        const submit = () => {
          const text = commentInput.value.trim();
          if (text) updateMoment({ action: "comment", id: post.id, text });
        };
        sendComment.addEventListener("click", submit);
        commentInput.addEventListener("keydown", event => {
          if (event.key === "Enter") submit();
        });
        commentRow.append(commentInput, sendComment);
        commentToggle.addEventListener("click", () => {
          commentRow.style.display = commentRow.style.display === "none" ? "flex" : "none";
          if (commentRow.style.display !== "none") commentInput.focus();
        });
        main.append(comments, commentRow);
        card.append(avatarEl, main);
        momentsList.appendChild(card);
      });
    }

    async function loadMoments() {
      try {
        const resp = await fetch("/api/moments");
        const data = await resp.json();
        if (data.ok) renderMoments(data.moments);
      } catch (_err) {}
    }

    async function updateMoment(payload) {
      if (!privacyAccepted) {
        privacyOverlay.classList.remove("hidden");
        return;
      }
      try {
        const resp = await fetch("/api/moments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "操作失败");
        renderMoments(data.moments);
        renderAvatar(data.avatar || { last_motion: "spark" });
      } catch (err) {
        alert("AI朋友圈操作失败：" + err);
      }
    }

    async function createMomentFromInput() {
      const text = (momentInput?.value || "").trim();
      if (!text) {
        momentInput?.focus();
        return;
      }
      if (momentPostBtn) momentPostBtn.disabled = true;
      await updateMoment({ action: "create", content: text });
      if (momentInput) momentInput.value = "";
      if (momentPostBtn) momentPostBtn.disabled = false;
    }

    async function generateMomentPost() {
      if (momentGenerateBtn) {
        momentGenerateBtn.disabled = true;
        momentGenerateBtn.textContent = "生成中...";
      }
      await updateMoment({ action: "generate" });
      if (momentGenerateBtn) {
        momentGenerateBtn.disabled = false;
        momentGenerateBtn.textContent = "AI发一条";
      }
    }

    async function generateDiary() {
      const btn = document.getElementById("diary-gen-btn");
      if (!btn) return;
      btn.disabled = true;
      const origText = btn.textContent;
      btn.textContent = "生成中...";
      try {
        const resp = await fetch("/api/diary_gen", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const data = await resp.json();
        if (data.ok && data.entries) {
          renderDiary(data.entries);
        } else {
          alert(data.error || "生成失败");
        }
      } catch (err) {
        alert("生成失败：" + err);
      } finally {
        btn.disabled = false;
        btn.textContent = origText;
      }
    }

    function renderTraining(data) {
      if (!data) return;
      lastTrainingData = data;
      if (!training) return;
      const examples = data.examples || [];
      const feedback = data.feedback || [];
      const positive = feedback.filter(x => x.rating > 0).length;
      const negative = feedback.filter(x => x.rating < 0).length;
      const emotionFeedback = feedback.filter(x => x.type === "emotion_feedback").length;
      training.innerHTML = "";
      const summary = document.createElement("div");
      const colon = i18nText("colon");
      summary.textContent = `${i18nText("training_loading").replace(/[:：].*$/, "")}${colon}${examples.length}\n${i18nText("positive_feedback")}${colon}${positive}\n${i18nText("negative_feedback")}${colon}${negative}\n${i18nText("emotion_feedback")}${colon}${emotionFeedback}`;
      training.appendChild(summary);

      const recent = examples.slice(-5).reverse();
      const title = document.createElement("div");
      title.style.marginTop = "8px";
      title.style.fontWeight = "700";
      title.textContent = i18nText("recent_samples");
      training.appendChild(title);

      if (!recent.length) {
        const empty = document.createElement("div");
        empty.textContent = `- ${i18nText("none")} (/teach question => answer)`;
        training.appendChild(empty);
        return;
      }

      recent.forEach((item, index) => {
        const card = document.createElement("div");
        card.className = "file-card";
        const prompt = (item.prompt || "").replace(/\s+/g, " ").trim();
        const response = (item.response || "").replace(/\s+/g, " ").trim();
        const source = item.source || "unknown";
        const sampleNo = examples.length - index;
        const text = document.createElement("div");
        text.textContent = `#${sampleNo} ${source}\n${i18nText("question")}${i18nText("colon")}${prompt.slice(0, 70) || i18nText("empty_value")}\n${i18nText("answer")}${i18nText("colon")}${response.slice(0, 110) || i18nText("empty_value")}`;
        const del = document.createElement("button");
        del.type = "button";
        del.textContent = i18nText("delete");
        del.style.marginTop = "6px";
        del.style.height = "auto";
        del.style.minWidth = "0";
        del.style.padding = "3px 8px";
        del.style.fontSize = "12px";
        del.addEventListener("click", () => {
          message.value = `/delete_sample ${sampleNo}`;
          message.focus();
        });
        card.appendChild(text);
        card.appendChild(del);
        training.appendChild(card);
      });
    }

    function renderFiles(data) {
      lastFilesData = data;
      if (!files) return;
      const filesSummary = document.getElementById("files-summary");
      const list = (data && data.files) || [];
      if (!list.length) {
        if (filesSummary) filesSummary.textContent = i18nText("files_empty");
        files.innerHTML = "";
        return;
      }
      if (filesSummary) filesSummary.textContent = `${i18nText("file_label")}${i18nText("colon")} ${list.length}`;
      files.innerHTML = "";
      list.slice(-4).reverse().forEach(item => {
        const div = document.createElement("div");
        div.className = "file-card";
        div.textContent = `${item.name}\n${item.kind}\n${item.summary.slice(0, 180)}`;
        files.appendChild(div);
      });
    }

    function renderAvatar(data) {
      if (!data) return;
      lastAvatarData = data;
      const motion = data.last_motion || "idle";
      const live2d = data.live2d || {};
      const activeModel = live2d.active || "";
      const model3d = data.model3d || {};
      const active3D = model3d.active || "";
      const prefMode = data.pet_display_mode || "auto";
      let showType = null; // "3d", "live2d", or null (css fallback)
      if (prefMode === "classic") {
        showType = null;
      } else if (prefMode === "3d") {
        if (active3D) showType = "3d";
        else if (activeModel) showType = "live2d";
      } else if (prefMode === "live2d") {
        if (activeModel) showType = "live2d";
        else if (active3D) showType = "3d";
      } else {
        // auto: 3D first
        if (active3D) showType = "3d";
        else if (activeModel) showType = "live2d";
      }
      if (showType === "3d") {
        avatarStage.classList.add("has-live2d");
        const wanted = `/3d?embed=1&motion=${encodeURIComponent(motion)}`;
        if (!live2dFrame.src.endsWith(wanted)) live2dFrame.src = wanted;
      } else if (showType === "live2d") {
        avatarStage.classList.add("has-live2d");
        const wanted = `/live2d?embed=1&motion=${encodeURIComponent(motion)}`;
        if (!live2dFrame.src.endsWith(wanted)) live2dFrame.src = wanted;
      } else {
        avatarStage.classList.remove("has-live2d");
        if (live2dFrame.src !== "about:blank") live2dFrame.src = "about:blank";
      }
      avatar.className = "avatar";
      void avatar.offsetWidth;
      avatar.classList.add(motion);
      const stats = data.stats || {};
      const modeLabel = prefMode !== "auto" ? ` [${prefMode}]` : "";
      const live2dLabel = showType === "3d" ? `3D: ${active3D}` : (showType === "live2d" ? `Live2D: ${activeModel}` : (data.live2d?.mode || i18nText("classic")));
      avatarStatus.textContent = `${live2dLabel}${modeLabel} · ${i18nText("current_motion")}: ${motion} · ${i18nText("sample_count")} ${stats.training_examples || 0}`;
      motionList.innerHTML = "";
      (data.motions || []).forEach(item => {
        const pill = document.createElement("span");
        pill.className = `motion-pill ${item.id === motion ? "active" : ""}`;
        pill.title = item.unlocked_by || "";
        pill.textContent = item.name;
        motionList.appendChild(pill);
      });
    }

    async function uploadSelectedFile() {
      if (!privacyAccepted) {
        addMsg("assistant", "请先阅读并同意隐私政策，然后再上传文件。");
        return null;
      }
      const picked = fileInput.files && fileInput.files[0];
      if (!picked) return null;
      const formData = new FormData();
      formData.append("file", picked);
      status.textContent = "读取本地文件...";
      const resp = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await resp.json();
      if (!data.ok) {
        addMsg("assistant", data.error || "文件上传失败。");
        return null;
      }
      currentFileId = data.file.id;
      renderFiles(data.files);
      renderAvatar(data.avatar);
      addMsg("assistant", `我已查看文件《${data.file.name}》：\n${data.file.summary}`);
      if (data.file.preview_url) addImagePreview(data.file.preview_url, data.file.name);
      return data.file;
    }

    async function observeScreen() {
      if (!privacyAccepted) {
        addMsg("assistant", "请先阅读并同意隐私政策，然后再使用屏幕观察。");
        return;
      }
      status.textContent = "观察当前屏幕...";
      try {
        const resp = await fetch("/api/observe_screen", { method: "POST" });
        const data = await resp.json();
        if (!data.ok) {
          addMsg("assistant", data.error || "屏幕观察失败。");
          return;
        }
        currentFileId = data.file?.id || "";
        addMsg("assistant", data.reply || "已完成屏幕视觉观察。");
        if (data.file?.preview_url) addImagePreview(data.file.preview_url, data.file.name || "screen.png");
        renderFiles(data.files);
        renderAvatar(data.avatar);
      } catch (err) {
        addMsg("assistant", "屏幕观察失败：" + err);
      } finally {
        status.textContent = "本地运行 · 记忆自训练";
      }
    }

    async function sendFeedback(rating, wrap, group) {
      group.querySelectorAll("button").forEach(btn => btn.disabled = true);
      const resp = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: lastUserText, response: trainingResponseText(lastAssistantText), rating })
      });
      const data = await resp.json();
      renderTraining(data.training);
      renderAvatar(data.avatar);
      group.textContent = rating > 0 ? " 已学习这次回答" : " 已记录：这次不合适";
    }

    async function sendChat(options = {}) {
      if (!privacyAccepted) {
        privacyOverlay.classList.remove("hidden");
        setAppLocked(true);
        return;
      }
      const fromRealtime = !!options.fromRealtime;
      const text = (options.overrideText !== undefined ? String(options.overrideText) : message.value).trim();
      const link = fromRealtime ? "" : url.value.trim();
      let uploaded = null;
      if (!fromRealtime && fileInput.files && fileInput.files[0]) {
        uploaded = await uploadSelectedFile();
        fileInput.value = "";
      }
      if (!text && !link && !uploaded) return;
      if (fromRealtime) {
        realtimeSending = true;
        stopWakeWordRecognition();
        stopRealtimeRecognition();
        setRealtimeVoiceStatus(i18nText("realtime_thinking"), "active");
      }
      const realtimeContext = fromRealtime ? await collectRealtimeContext() : "";
      lastUserText = text || link || `查看文件：${uploaded.name}`;
      addMsg("user", text || link || `查看文件：${uploaded.name}`);
      if (fromRealtime) appendRealtimePetLine("user", lastUserText);
      if (!fromRealtime || message.value.trim() === text) message.value = "";
      send.disabled = true;
      status.textContent = fromRealtime ? i18nText("realtime_thinking") : "思考中...";
      try {
        const punctuation = countPunctuation(text);
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            url: link,
            file_id: fromRealtime ? "" : currentFileId,
            conversation_id: currentConversationId,
            from_realtime: fromRealtime,
            realtime_context: realtimeContext,
            typing_metrics: typingMetrics,
            punctuation: punctuation
          })
        });
        resetTypingMetrics();
        const data = await resp.json();
        if (data.conversation_id) currentConversationId = data.conversation_id;
        if (data.recent_chats) {
          renderRecentChats(data.recent_chats, currentConversationId);
          const activeChat = data.recent_chats.find(item => item.id === currentConversationId);
          if (activeChat) setConversationTitle(activeChat.title);
        }
        lastAssistantText = data.reply || "没有返回内容。";
        lastEmotion = extractEmotion(lastAssistantText);
        if (fromRealtime) suppressNextAutoTTS = true;
        addMsg("assistant", lastAssistantText);
        if (fromRealtime) appendRealtimePetLine("assistant", trainingResponseText(lastAssistantText) || lastAssistantText);
        addFeedback();
        renderMemory(data.memory);
        renderTraining(data.training);
        renderFiles(data.files);
        renderAvatar(data.avatar);
        if (data.growth) renderGrowth(data.growth);
        if (data.emotion_trend) renderEmotionChart(data.emotion_trend);
        if (data.diary_entries) renderDiary(data.diary_entries);
        if (data.audit_status) renderAuditStatus(data.audit_status);
        if (data.audit_corrections && data.audit_corrections.length) renderAuditCorrections(data.audit_corrections);
        if (data.index_rebuild_status) renderTaskStatus(data.index_rebuild_status);
        loadMoments();
        if (fromRealtime && realtimeVoiceEnabled) {
          await speakRealtimeReply(lastAssistantText);
        }
      } catch (err) {
        addMsg("assistant", `请求失败：${err}`);
      } finally {
        if (fromRealtime) {
          realtimeSending = false;
          if (realtimeVoiceEnabled) scheduleRealtimeListen(350);
        }
        send.disabled = false;
        status.textContent = "本地运行 · 记忆自训练";
        if (!fromRealtime) message.focus();
      }
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      sendChat();
    });
    document.querySelectorAll("[data-fill]").forEach(btn => {
      btn.addEventListener("click", () => {
        if (!privacyAccepted) {
          privacyOverlay.classList.remove("hidden");
          return;
        }
        message.value = btn.dataset.fill;
        message.focus();
      });
    });
    document.querySelectorAll("[data-context-fill]").forEach(btn => {
      btn.addEventListener("click", () => {
        if (!privacyAccepted) {
          privacyOverlay.classList.remove("hidden");
          return;
        }
        message.value = btn.dataset.contextFill || "";
        message.focus();
      });
    });
    if (newChatBtn) {
      newChatBtn.addEventListener("click", () => {
        currentConversationId = "";
        resetChatView();
        setConversationTitle("新对话");
        renderRecentChats(recentChats, "");
        message.value = "";
        message.focus();
      });
    }
    loadPrivacyConsent();
    loadRecentChats();
    fetch("/api/memory").then(r => r.json()).then(data => {
      renderMemory(data.memory);
      renderTraining(data.training);
      renderFiles(data.files);
      renderAvatar(data.avatar);
      if (data.growth) renderGrowth(data.growth);
    });
    fetch("/api/emotion_trend", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ days: 7 }) }).then(r => r.json()).then(data => {
      if (data.ok && data.trend) renderEmotionChart(data.trend);
    }).catch(() => {});
    fetch("/api/diary_entries").then(r => r.json()).then(data => {
      if (data.ok && data.entries) renderDiary(data.entries);
    }).catch(() => {});
    loadMoments();

    const diaryGenBtn = document.getElementById("diary-gen-btn");
    if (diaryGenBtn) diaryGenBtn.addEventListener("click", generateDiary);
    if (momentPostBtn) momentPostBtn.addEventListener("click", createMomentFromInput);
    if (momentGenerateBtn) momentGenerateBtn.addEventListener("click", generateMomentPost);
    if (momentInput) {
      momentInput.addEventListener("keydown", event => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") createMomentFromInput();
      });
    }

    // -- plugin management --
    function renderPlugins(data) {
      const list = document.getElementById("plugin-list");
      if (!list) return;
      if (!data.plugins || data.plugins.length === 0) {
        list.innerHTML = "<em>暂无插件。将插件文件夹放入 plugins/ 目录即可。</em>";
        return;
      }
      list.innerHTML = data.plugins.map(p => {
        const status = p.loaded ? (p.disabled ? "已禁用" : "已加载") : "未加载";
        const color = p.loaded && !p.disabled ? "#0b7a55" : "#c0392b";
        const toggleLabel = p.disabled ? "启用" : "禁用";
        return `<div style="margin:4px 0;padding:4px 0;border-bottom:1px solid #e5e8ee">
          <strong>${p.name}</strong> <span style="color:${color};font-size:12px">${status}</span>
          <span style="color:#657184;font-size:11px">v${p.version}</span><br>
          <span style="font-size:12px;color:#657184">${p.description}</span><br>
          <button type="button" data-plugin-toggle="${p.dir}" style="font-size:11px;margin-top:2px">${toggleLabel}</button>
          <button type="button" data-plugin-remove="${p.dir}" style="font-size:11px;margin-top:2px;margin-left:4px">删除</button>
        </div>`;
      }).join("");
      list.querySelectorAll("[data-plugin-toggle]").forEach(btn => {
        btn.addEventListener("click", () => {
          fetch("/api/plugins", {method:"POST", headers:{"Content-Type":"application/json"},
            body: JSON.stringify({action:"toggle", name: btn.dataset.pluginToggle})})
            .then(() => loadPlugins());
        });
      });
      list.querySelectorAll("[data-plugin-remove]").forEach(btn => {
        btn.addEventListener("click", () => {
          if (!confirm("确定删除插件 " + btn.dataset.pluginRemove + "？")) return;
          fetch("/api/plugins", {method:"POST", headers:{"Content-Type":"application/json"},
            body: JSON.stringify({action:"remove", name: btn.dataset.pluginRemove})})
            .then(() => { loadPlugins(); location.reload(); });
        });
      });
    }
    function loadPlugins() {
      fetch("/api/plugins").then(r => r.json()).then(renderPlugins).catch(() => {
        const list = document.getElementById("plugin-list");
        if (list) list.innerHTML = "<em>加载失败</em>";
      });
    }
    function bindPluginManagement() {
      const reloadButton = document.getElementById("plugin-reload-btn");
      const newButton = document.getElementById("plugin-new-btn");
      reloadButton?.addEventListener("click", () => {
        fetch("/api/plugins", {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({action:"reload"})})
          .then(() => { loadPlugins(); location.reload(); });
      });
      newButton?.addEventListener("click", () => {
        const name = prompt("插件文件夹名 (英文，如 my_tool):");
        if (!name) return;
        const desc = prompt("插件描述:") || "";
        fetch("/api/plugins", {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({action:"create", name: name, meta:{name:name, description:desc, version:"1.0.0"}})})
          .then(() => { loadPlugins(); location.reload(); });
      });
    }

    const observeScreenBtn = document.getElementById("observe-screen-btn");
    if (observeScreenBtn) {
      observeScreenBtn.addEventListener("click", observeScreen);
    }
    // ---- Settings modal ----
    const settingsOverlay = document.createElement("div");
    settingsOverlay.className = "settings-overlay";
    settingsOverlay.id = "settings-overlay";
    settingsOverlay.innerHTML = `
      <div class="settings-panel">
        <div class="settings-header">
          <div>
            <h2>&#x2699; <span data-i18n="settings_title">Companion AI 设置</span></h2>
            <div class="settings-subtitle" data-i18n="settings_subtitle">管理本地能力、模型、身份、语音和插件。</div>
          </div>
          <button class="settings-close" id="settings-close" aria-label="关闭">&times;</button>
        </div>
        <div class="settings-grid">
        <div class="settings-section" id="sec-language">
          <h3>━ <span data-i18n="language">语言</span></h3>
          <select id="settings-language-select">
            <option value="zh-CN">中文</option>
            <option value="en-US">English</option>
          </select>
          <div class="settings-note" data-i18n="i18n_note">切换后会立即更新核心界面；部分对话内容仍按当前模型和命令语言生成。</div>
        </div>
        <div class="settings-section" id="sec-display">
          <h3>━ 显示主题</h3>
          <div class="settings-page active" id="display-page-main">
            <div class="display-summary" id="display-summary"></div>
            <div class="display-theme-entry">
              <strong id="display-current-theme">清爽</strong>
              <span id="display-current-detail">字号 100% · 密度 100% · 圆角 8px</span>
            </div>
            <div class="settings-actions">
              <button type="button" id="display-open-btn">进入显示主题</button>
              <button type="button" id="tour-restart-btn">重新查看新手引导</button>
            </div>
          </div>
          <div class="settings-page" id="display-page-detail">
            <div class="settings-page-header">
              <button type="button" class="settings-page-back" id="display-back-btn">返回</button>
              <span class="update-pill">显示主题</span>
            </div>
            <div class="settings-note">选择主界面主题，并自由调整字号、紧凑度、圆角、侧栏宽度和桌宠展示区高度。</div>
            <div class="theme-options">
              <label class="theme-option"><input type="radio" name="display-theme" value="soft" /><span class="theme-swatch" style="--swatch-a:#f6f7f9;--swatch-b:#276ef1"></span><span>清爽</span></label>
              <label class="theme-option"><input type="radio" name="display-theme" value="night" /><span class="theme-swatch" style="--swatch-a:#10141c;--swatch-b:#7aa7ff"></span><span>夜间</span></label>
              <label class="theme-option"><input type="radio" name="display-theme" value="forest" /><span class="theme-swatch" style="--swatch-a:#f2f7f3;--swatch-b:#2d7d59"></span><span>森林</span></label>
              <label class="theme-option"><input type="radio" name="display-theme" value="rose" /><span class="theme-swatch" style="--swatch-a:#fbf5f7;--swatch-b:#c24a7a"></span><span>蔷薇</span></label>
              <label class="theme-option"><input type="radio" name="display-theme" value="mono" /><span class="theme-swatch" style="--swatch-a:#f5f5f4;--swatch-b:#202020"></span><span>素描</span></label>
              <label class="theme-option"><input type="radio" name="display-theme" value="custom" /><span class="theme-swatch" style="--swatch-a:var(--custom-swatch-a,#f6f7f9);--swatch-b:var(--custom-swatch-b,#276ef1)"></span><span>自定义</span></label>
            </div>
            <div class="custom-theme-grid" id="custom-theme-grid">
              <label>背景<input type="color" id="custom-bg" value="#f6f7f9" /></label>
              <label>面板<input type="color" id="custom-panel" value="#ffffff" /></label>
              <label>留白底色<input type="color" id="custom-panel-soft" value="#eef2f7" /></label>
              <label>文字<input type="color" id="custom-ink" value="#172033" /></label>
              <label>弱文字<input type="color" id="custom-muted" value="#657184" /></label>
              <label>强调<input type="color" id="custom-accent" value="#276ef1" /></label>
              <label>副强调<input type="color" id="custom-accent-2" value="#0b8f6f" /></label>
            </div>
            <button type="button" id="custom-theme-copy-btn">把当前预设作为自定义起点</button>
            <div class="settings-slider"><label><span>字号</span><span class="settings-slider-value" id="display-font-scale-value">100%</span></label><input type="range" id="display-font-scale" min="85" max="125" value="100" /></div>
            <div class="settings-slider"><label><span>界面密度</span><span class="settings-slider-value" id="display-density-value">100%</span></label><input type="range" id="display-density" min="80" max="125" value="100" /></div>
            <div class="settings-slider"><label><span>圆角</span><span class="settings-slider-value" id="display-radius-value">8px</span></label><input type="range" id="display-radius" min="2" max="18" value="8" /></div>
            <div class="settings-slider"><label><span>侧栏宽度</span><span class="settings-slider-value" id="display-sidebar-width-value">280px</span></label><input type="range" id="display-sidebar-width" min="240" max="440" value="280" /></div>
            <div class="settings-slider"><label><span>助手状态区</span><span class="settings-slider-value" id="display-avatar-height-value">84px</span></label><input type="range" id="display-avatar-height" min="64" max="104" value="84" /></div>
            <div class="theme-preview" id="display-theme-preview">
              <strong>预览</strong><span>调整会立即应用到当前主界面，保存后下次打开仍然保留。</span>
              <div class="theme-preview-surface" id="display-preview-surface">
                <div class="theme-preview-side"><i></i><i></i><i></i></div>
                <div class="theme-preview-main"><i class="theme-preview-line strong"></i><i class="theme-preview-line"></i><i class="theme-preview-line accent"></i></div>
              </div>
            </div>
            <div id="display-status" class="settings-note"></div>
            <div class="settings-actions">
              <button id="display-save-btn">保存显示设置</button>
              <button id="display-reset-btn">恢复默认</button>
            </div>
          </div>
        </div>
        <div class="settings-section" id="sec-update">
          <h3>━ 软件更新</h3>
          <div class="update-panel">
            <div class="update-page active" id="update-page-main">
              <div class="status" id="update-status" style="color:#657184">加载中...</div>
              <div class="settings-note" id="update-source">检查地址：GitHub · LoongSerpent9Realms/companion-ai-release</div>
              <div class="update-summary" id="update-summary"></div>
              <div class="update-release-card" id="update-release-card"></div>
              <div class="update-config">
                <div class="settings-row">
                  <label class="settings-check"><input type="checkbox" id="update-auto-check" /> 自动检查</label>
                  <label class="settings-check"><input type="checkbox" id="update-auto-download" /> 有新版自动下载</label>
                  <label class="settings-check"><input type="checkbox" id="update-auto-install" /> 下载后自动安装</label>
                </div>
                <label>检查间隔（小时）</label>
                <input id="update-interval" type="number" min="1" max="168" />
              </div>
              <div id="update-detail" class="settings-note"></div>
              <div class="settings-actions">
                <button id="update-save-btn">保存更新设置</button>
                <button id="update-check-btn">检查更新</button>
                <button id="update-download-btn">下载更新</button>
                <button id="update-install-btn">安装已下载更新</button>
              </div>
            </div>
            <div class="update-page" id="update-page-log">
              <div class="update-detail-header">
                <button type="button" class="update-back-btn" id="update-back-btn">返回</button>
                <span class="update-pill" id="update-log-version">更新日志</span>
              </div>
              <div class="update-log-body" id="update-log-body"></div>
            </div>
          </div>
        </div>
        <div class="settings-section" id="sec-ocr">
          <h3>━ OCR 文字识别</h3>
          <div class="status loading" id="ocr-status">检测中…</div>
          <div id="ocr-size" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <button id="ocr-install-btn">安装 OCR</button>
          <button id="ocr-uninstall-btn" class="danger" style="display:none;margin-left:8px">删除</button>
        </div>
        <div class="settings-section" id="sec-opencv">
          <h3>━ OpenCV (摄像头/视觉)</h3>
          <div class="status loading" id="opencv-status">检测中…</div>
          <div id="opencv-detail" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <div id="opencv-size" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <button id="opencv-install-btn">安装 OpenCV</button>
          <button id="opencv-uninstall-btn" class="danger" style="display:none;margin-left:8px">删除</button>
        </div>
          <div class="settings-section" id="sec-python">
            <h3>━ Python 运行环境</h3>
            <div class="status" id="python-status" style="color:#657184">用于安装本地 AI 组件（PyTorch、数据集等）。</div>
            <div id="python-detail" style="font-size:13px;color:#657184;margin:6px 0"></div>
            <div id="python-size" style="font-size:13px;color:#657184;margin:6px 0"></div>
            <button id="python-install-btn">自动安装 Python 3.12</button>
            <button id="shortcuts-uninstall-btn" class="danger" style="margin-left:8px">删除桌面/开始菜单快捷方式</button>
          </div>
        <div class="settings-section" id="sec-cpp-toolchain">
          <h3>━ C++ 工具链（刷题与代码练习）</h3>
          <div class="status loading" id="cpp-toolchain-status">检测中…</div>
          <div class="settings-note">安装 LLVM 会使用 Windows 的 winget 下载到指定目录，并将 bin 目录写入用户 PATH，其他新启动的应用也可使用。</div>
          <label>安装目录或已有工具链目录</label>
          <input id="cpp-toolchain-dir" type="text" spellcheck="false" />
          <div class="settings-actions">
            <button id="cpp-toolchain-install-btn">下载并安装 LLVM</button>
            <button id="cpp-toolchain-path-btn">加入已有目录到 PATH</button>
          </div>
          <div id="cpp-toolchain-detail" class="settings-note"></div>
        </div>
        <div class="settings-section" id="sec-datasets">
          <h3>━ 数据集工具 (ModelScope + Datasets)</h3>
          <div class="status loading" id="datasets-status">检测中…</div>
          <div id="datasets-detail" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <div id="datasets-size" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <button id="datasets-install-btn">安装</button>
          <button id="datasets-uninstall-btn" class="danger" style="display:none;margin-left:8px">删除</button>
        </div>
        <div class="settings-section" id="sec-camera">
          <h3>━ 摄像头管理</h3>
          <div class="status" id="camera-status" style="color:#657184">用于本地摄像头观察，不会自动开启。</div>
          <label>摄像头编号</label>
          <input id="camera-index" type="number" min="0" value="0" />
          <button id="camera-test-btn">测试抓拍</button>
          <button id="camera-chat-btn">发送摄像头观察</button>
          <div id="camera-test-result" style="font-size:13px;color:#657184;margin:8px 0"></div>
        </div>
        <div class="settings-section" id="sec-face">
          <h3>━ 人脸识别</h3>
          <div class="status" id="face-status" style="color:#657184">用于注册和识别摄像头中的人脸。</div>
          <div id="face-count" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <div id="face-list" style="font-size:13px;color:#243143;margin:6px 0;max-height:120px;overflow-y:auto"></div>
          <div class="face-register-row">
            <label>注册新人脸
              <input id="face-register-name" type="text" placeholder="输入名字" />
            </label>
            <button id="face-register-btn">从摄像头注册</button>
          </div>
          <div class="face-actions">
            <button id="face-recognize-btn">识别摄像头人脸</button>
            <button id="face-log-btn">查看日志</button>
          </div>
          <div id="face-result" style="font-size:13px;color:#657184;margin:8px 0"></div>
          <div id="face-install-options" class="face-install-options">
            <div class="face-install-title">人脸识别依赖未安装，请选择安装方式：</div>
            <div class="face-install-actions">
              <button id="face-install-opencv-btn">安装 OpenCV</button>
              <button id="face-install-all-btn">安装人脸识别依赖</button>
              <button id="face-install-cmake-btn">仅安装 CMake</button>
              <button id="face-install-dlib-btn">仅安装 dlib</button>
              <button id="face-install-vs-btn">下载 VS Build Tools</button>
            </div>
            <div class="face-install-hint">当前提示缺少 cv2 时先安装 OpenCV；若后续提示 dlib 或 face_recognition，再安装人脸识别依赖。</div>
          </div>
        </div>
        <div class="settings-section" id="sec-torch">
          <h3>━ 神经网络 (PyTorch)</h3>
          <div class="status loading" id="torch-status">检测中…</div>
          <div id="torch-gpu" style="font-size:13px;color:#276ef1;margin:6px 0"></div>
          <div id="torch-size" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <div id="torch-version-select" style="margin:10px 0;display:none">
            <label>选择版本：</label>
            <select id="torch-version">
              <option value="auto">自动推荐</option>
              <option value="cuda121">CUDA 12.1 (NVIDIA)</option>
              <option value="directml">DirectML (AMD/Intel Windows)</option>
              <option value="cpu">CPU 版本</option>
            </select>
          </div>
          <button id="torch-install-btn">安装 PyTorch</button>
          <button id="torch-uninstall-btn" class="danger" style="display:none;margin-left:8px">删除</button>
          <div id="torch-dx12-status" class="settings-note"></div>
          <button type="button" id="torch-dx12-train-btn">使用 DX12 训练模型</button>
        </div>
        <div class="settings-section" id="sec-zluda">
          <h3>━ ZLUDA (AMD/Intel GPU 加速)</h3>
          <div class="status loading" id="zluda-status">检测中…</div>
          <div id="zluda-size" style="font-size:13px;color:#657184;margin:6px 0"></div>
          <button id="zluda-install-btn">安装 ZLUDA</button>
          <button id="zluda-uninstall-btn" class="danger" style="display:none;margin-left:8px">删除</button>
        </div>
        <div class="settings-section" id="sec-pet-display">
          <h3>━ 显示模式</h3>
          <div class="settings-note">选择桌宠的显示方式。更改后需重启桌宠生效。</div>
          <div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap" id="pet-display-options">
            <label class="settings-check" style="cursor:pointer"><input type="radio" name="pet-display-mode" value="auto" /> 自动检测</label>
            <label class="settings-check" style="cursor:pointer"><input type="radio" name="pet-display-mode" value="3d" /> 3D 模型</label>
            <label class="settings-check" style="cursor:pointer"><input type="radio" name="pet-display-mode" value="live2d" /> Live2D 模型</label>
            <label class="settings-check" style="cursor:pointer"><input type="radio" name="pet-display-mode" value="classic" /> 经典手绘</label>
          </div>
          <div id="pet-display-status" class="status" style="color:#657184;margin-top:8px"></div>
        </div>
        <div class="settings-section" id="sec-live2d">
          <h3>━ Live2D 模型</h3>
          <div class="status" id="live2d-status" style="color:#657184">点击刷新查看已安装模型</div>
          <div id="live2d-model-list" style="margin:8px 0;font-size:14px"></div>
          <input type="file" id="live2d-file" accept=".zip" style="display:none" />
          <button id="live2d-choose-btn" style="margin-right:8px">选择 zip 文件</button>
          <button id="live2d-upload-btn">上传并导入</button>
          <div id="live2d-upload-progress" style="margin-top:8px;font-size:13px;color:#657184"></div>
        </div>
        <div class="settings-section" id="sec-3d">
          <h3>━ 3D 模型设置</h3>
          <div class="status" id="3d-status" style="color:#657184">点击刷新查看已安装模型</div>
          <div id="3d-model-list" style="margin:8px 0;font-size:14px"></div>
          <input type="file" id="3d-file" accept=".zip" style="display:none" />
          <button id="3d-choose-btn" style="margin-right:8px">选择 zip 文件</button>
          <button id="3d-upload-btn">上传并导入</button>
          <div id="3d-upload-progress" style="margin-top:8px;font-size:13px;color:#657184"></div>
          <div style="margin-top:8px;font-size:13px;color:#657184">支持格式：PMX / VRM / glTF / GLB</div>
          <div style="margin-top:6px"><a href="/3d" target="_blank" style="font-size:13px;color:#276ef1;text-decoration:none">3D 查看器</a></div>
        </div>
        <div class="settings-section" id="sec-identity">
          <h3>━ AI 身份</h3>
          <div class="status settings-clamp" id="identity-status" style="color:#657184">加载中...</div>
          <button id="identity-edit-btn" style="margin-top:10px">编辑身份</button>
        </div>
        <div class="settings-section" id="sec-memory">
          <h3>━ 记忆与使用数据管理</h3>
          <div class="status" id="memory-clear-status" style="color:#657184">清除后会删除长期记忆、聊天历史、训练反馈、画像、作息、操作学习、视觉/上传记录、声纹、人脸和成长记录等本地用户数据。</div>
          <button id="memory-clear-btn" class="danger" style="margin-top:6px">清除所有数据</button>
        </div>
        <div class="settings-section" id="sec-privacy">
          <h3>━ 隐私与数据</h3>
          <div class="status" id="privacy-status" style="color:#657184">加载中...</div>
          <div class="settings-note">撤回同意后，聊天、上传、屏幕观察和反馈等功能会立即锁定；重新同意隐私政策后才能继续使用。</div>
          <button id="privacy-revoke-btn" class="danger" style="margin-top:6px">撤回隐私政策同意</button>
        </div>
        <div class="settings-section" id="sec-tts">
          <h3>━ 语音设置</h3>
          <div class="status" id="tts-status" style="color:#657184">加载中...</div>
          <div class="settings-note">控制 AI 回复的语音播放、音色、语速、音调和音量。</div>
          <button id="tts-install-btn" style="margin:8px 0;display:none">安装 Edge-TTS</button>
          <button id="tts-uninstall-btn" class="danger" style="margin:8px 0;display:none">删除 Edge-TTS</button>
          <div id="tts-config-area" style="display:none">
            <div class="settings-row">
              <label class="settings-check"><input type="checkbox" id="tts-enabled" /> 启用语音合成</label>
              <label class="settings-check"><input type="checkbox" id="tts-auto-play" /> 自动播放回复</label>
            </div>
            <div class="settings-control-grid">
              <div>
                <label>音色</label>
                <select id="tts-voice">
                  <option value="zh-CN-XiaoxiaoNeural">晓晓 (女声)</option>
                  <option value="zh-CN-YunxiNeural">云希 (男声)</option>
                  <option value="zh-CN-YunjianNeural">云健 (男声)</option>
                  <option value="zh-CN-XiaoyiNeural">晓伊 (女声)</option>
                  <option value="zh-CN-YunyangNeural">云扬 (男声)</option>
                  <option value="zh-CN-XiaochenNeural">晓辰 (女声)</option>
                  <option value="zh-CN-XiaohanNeural">晓涵 (女声)</option>
                  <option value="zh-CN-XiaomengNeural">晓梦 (女声)</option>
                  <option value="zh-CN-XiaoqiuNeural">晓秋 (女声)</option>
                  <option value="zh-CN-XiaorouNeural">晓柔 (女声)</option>
                </select>
              </div>
            </div>
            <div class="settings-slider">
              <label><span>语速</span><span id="tts-rate-value">+0%</span></label>
              <input type="range" id="tts-rate" min="-50" max="50" value="0" />
            </div>
            <div class="settings-slider">
              <label><span>音调</span><span id="tts-pitch-value">+0Hz</span></label>
              <input type="range" id="tts-pitch" min="-50" max="50" value="0" />
            </div>
            <div class="settings-slider">
              <label><span>音量</span><span id="tts-volume-value">+0%</span></label>
              <input type="range" id="tts-volume" min="-50" max="50" value="0" />
            </div>
            <div id="tts-cache-info" class="settings-note"></div>
            <div id="tts-size" class="settings-note"></div>
            <div class="settings-actions">
              <button id="tts-save-btn">保存设置</button>
              <button id="tts-test-btn">试听</button>
              <button id="tts-clear-cache-btn">清空缓存</button>
            </div>
          </div>
        </div>
        <div class="settings-section" id="sec-voiceprint">
          <h3>━ 语音输入与声纹</h3>
          <div class="status" id="voiceprint-status" style="color:#657184">麦克风只在你点击录入或识别时开启。</div>
          <div class="settings-note">声纹特征保存在本机，仅用于区分本地已登记的说话人；它不是安全认证。</div>
          <div class="settings-row">
            <input id="voiceprint-name" placeholder="声纹名称，如：我" />
          </div>
          <div class="settings-actions">
            <button id="voiceprint-enroll-btn">录入声纹</button>
            <button id="voiceprint-recognize-btn">识别当前说话人</button>
            <button id="voiceprint-refresh-btn">刷新列表</button>
          </div>
          <div id="voiceprint-result" class="settings-note"></div>
          <div id="voiceprint-list" class="voiceprint-list">加载中...</div>
        </div>
        <div class="settings-section" id="sec-identity-confirm">
          <h3>━ 当前身份确认</h3>
          <div class="settings-note">人脸或声纹识别成功后，会加入后续对话上下文；不会自动开启摄像头或麦克风。</div>
          <div class="status" id="identity-confirm-status" style="color:#657184">加载中...</div>
          <div class="settings-actions">
            <button id="identity-confirm-refresh-btn">刷新确认状态</button>
            <button id="identity-confirm-clear-btn" class="danger">清除当前确认</button>
          </div>
        </div>
        <div class="settings-section" id="sec-local-growth">
          <h3>━ 本地自成长</h3>
          <div class="status" id="local-growth-status" style="color:#657184">加载中...</div>
          <div class="settings-note">候选模型必须通过固定评测集才会激活；评测题永不混入训练。图片偏好只保存本地生成配方与采用反馈。</div>
          <div class="settings-control-grid" style="margin-top:10px">
            <div><label>验证经验</label><div id="growth-experience-count" class="settings-note">-</div></div>
            <div><label>回放 / 留出评测</label><div id="growth-replay-count" class="settings-note">-</div></div>
            <div><label>当前模型版本</label><div id="growth-active-version" class="settings-note">-</div></div>
            <div><label>图片配方</label><div id="growth-image-status" class="settings-note">-</div></div>
          </div>
          <div class="settings-note" style="margin-top:12px">本地图片后端（可选 ComfyUI；仅连接本机服务，失败时自动回退到心情卡片）</div>
          <div id="growth-image-backend-status" class="settings-note">加载中...</div>
          <div class="settings-row" style="margin-top:8px">
            <label class="settings-check"><input type="checkbox" id="growth-comfy-enabled" /> 使用 ComfyUI</label>
          </div>
          <div class="settings-control-grid" style="margin-top:8px">
            <div><label>ComfyUI 地址</label><input id="growth-comfy-endpoint" placeholder="http://127.0.0.1:8188" /></div>
            <div><label>API workflow JSON 路径</label><input id="growth-comfy-workflow" placeholder="C:\\...\\workflow_api.json" /></div>
            <div><label>正向提示词节点 ID</label><input id="growth-comfy-prompt-node" placeholder="例如 6" /></div>
            <div><label>负向提示词节点 ID（可留空）</label><input id="growth-comfy-negative-node" placeholder="例如 7" /></div>
            <div><label>种子节点 ID（可留空）</label><input id="growth-comfy-seed-node" placeholder="例如 3" /></div>
          </div>
          <div class="settings-actions"><button id="growth-comfy-save-btn">保存并测试 ComfyUI</button></div>
          <div class="settings-note" style="margin-top:10px">固定能力评测题</div>
          <div id="growth-benchmark-list" class="voiceprint-list">加载中...</div>
          <div class="settings-control-grid" style="margin-top:8px">
            <div><label>问题</label><input id="growth-benchmark-prompt" placeholder="例如：你是谁？" /></div>
            <div><label>必须出现的关键词（逗号分隔）</label><input id="growth-benchmark-keywords" placeholder="本地,伙伴" /></div>
            <div><label>判定规则</label><select id="growth-benchmark-rule"><option value="keywords">包含全部关键词</option><option value="regex">正则匹配</option><option value="exact">完全一致</option><option value="max_length">最大字数（期望值填数字）</option><option value="manual">人工确认通过</option></select></div>
          </div>
          <div class="settings-actions">
            <button id="growth-benchmark-add-btn">添加评测题</button>
            <button id="growth-refresh-btn">刷新状态</button>
            <button id="growth-rollback-btn" class="danger">回滚当前模型</button>
          </div>
          <div class="settings-note" style="margin-top:12px">真实样本标定（不会自动读取聊天；只保存你明确填入并批准的问答）</div>
          <div class="settings-control-grid" style="margin-top:8px">
            <div><label>实际问题</label><input id="growth-calibration-prompt" placeholder="例如：帮我安排明天的待办" /></div>
            <div><label>期望回答</label><input id="growth-calibration-response" placeholder="填写你认可的本地回答" /></div>
          </div>
          <div class="settings-actions"><button id="growth-calibration-add-btn">批准为标定样本</button></div>
          <div class="settings-note" style="margin-top:12px">后台候选训练</div>
          <div id="growth-training-job" class="settings-note">暂无训练任务</div>
          <div class="settings-actions">
            <button id="growth-training-start-btn">后台训练候选模型</button>
            <button id="growth-training-cancel-btn" class="danger">取消训练</button>
          </div>
          <div class="settings-note" style="margin-top:12px">模型版本（仅通过评测的版本可恢复）</div>
          <div id="growth-version-list" class="voiceprint-list">加载中...</div>
          <div class="settings-note" style="margin-top:12px">最近成长经验</div>
          <div id="growth-experience-list" class="voiceprint-list">加载中...</div>
          <div class="settings-note" style="margin-top:12px">图片配方反馈</div>
          <div id="growth-recipe-list" class="voiceprint-list">加载中...</div>
          <div class="settings-actions">
            <button id="diagnostics-export-btn">导出本地诊断包</button>
          </div>
          <div id="diagnostics-result" class="settings-note"></div>
        </div>
        <div class="settings-section" id="sec-runtime-behavior">
          <h3>━ 后台与启动</h3>
          <div class="status" id="runtime-behavior-status" style="color:#657184">加载中...</div>
          <div class="settings-note">梦境引擎只在系统和聊天都空闲、且没有全屏应用时运行。开机自启会在 Windows 的当前用户启动文件夹中创建本地入口。</div>
          <div class="settings-row" style="margin-top:10px">
            <label class="settings-check"><input type="checkbox" id="runtime-dream-enabled" /> 空闲时开启梦境引擎</label>
            <label class="settings-check"><input type="checkbox" id="runtime-autostart" /> 开机自动启动 Companion AI 与桌宠</label>
          </div>
          <div class="settings-control-grid" style="margin-top:10px">
            <div><label>系统空闲后开始（秒）</label><input id="runtime-system-idle" type="number" min="30" max="3600" /></div>
            <div><label>聊天空闲后开始（秒）</label><input id="runtime-chat-idle" type="number" min="15" max="3600" /></div>
            <div><label>记忆整理间隔（小时）</label><input id="runtime-review-interval" type="number" min="1" max="168" /></div>
            <div><label>深度任务空闲要求（分钟）</label><input id="runtime-heavy-idle" type="number" min="1" max="240" /></div>
            <div><label>静默时段（小时，逗号分隔）</label><input id="runtime-quiet-hours" placeholder="1,2,3,4,5" /></div>
          </div>
          <div class="settings-actions">
            <button id="runtime-save-btn">保存后台设置</button>
            <button id="runtime-review-btn">现在整理记忆</button>
            <button id="runtime-practice-btn">现在进行代码练习</button>
          </div>
        </div>
        <div class="settings-section" id="sec-audit">
          <h3>━ 对话审计</h3>
          <div class="status" id="audit-status" style="color:#657184">加载中...</div>
          <div style="margin:8px 0">
            <label style="font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer">
              <input type="checkbox" id="audit-enabled" /> 启用对话审计
            </label>
            <label style="font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer;margin-top:6px">
              <input type="checkbox" id="audit-use-cloud" /> 使用云端审计辅助（默认仅本地规则）
            </label>
            <label style="font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer;margin-top:6px">
              <input type="checkbox" id="audit-auto-suggest" /> 自动向审计 AI 请求改写建议并学习
            </label>
            <div class="settings-note" style="margin:5px 0 0 24px">默认只用本地规则核验格式、长度和基础情绪。勾选云端辅助后才会将对话发送到配置的审计服务；自动改写也仅在云端辅助开启时可用。</div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0">
            <div>
              <label>API Base</label>
              <input id="audit-api-base" placeholder="https://api.openai.com/v1" />
            </div>
            <div>
              <label>API Key</label>
              <input id="audit-api-key" type="password" placeholder="sk-..." />
            </div>
            <div>
              <label>模型</label>
              <input id="audit-model" list="audit-model-options" placeholder="gpt-4o-mini" />
              <datalist id="audit-model-options"></datalist>
              <div id="audit-model-discovery" class="settings-note"></div>
            </div>
            <div>
              <label>语言</label>
              <select id="audit-language">
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </div>
            <div>
              <label>批次大小</label>
              <input id="audit-batch-size" type="number" min="1" max="20" />
            </div>
            <div>
              <label>审计间隔(秒)</label>
              <input id="audit-interval" type="number" min="1" max="300" />
            </div>
            <div>
              <label>上下文轮数</label>
              <input id="audit-context-turns" type="number" min="1" max="20" />
            </div>
          </div>
          <div id="audit-summary" style="font-size:13px;color:#657184;margin:10px 0"></div>
          <div id="audit-recent" style="display:grid;gap:8px;margin:10px 0"></div>
          <button id="audit-save-btn">保存配置</button>
        </div>
        <div class="settings-section" id="sec-remote-llm">
          <h3>━ 大模型接口</h3>
          <div class="status" id="remote-llm-status" style="color:#657184">加载中...</div>
          <div class="settings-note">启用后可用 OpenAI-compatible 接口生成回复；长期记忆、画像、技能和训练样本仍保存在本机。</div>
          <div style="margin:8px 0">
            <label class="settings-check"><input type="checkbox" id="remote-llm-enabled" /> 启用大模型接口</label>
            <label class="settings-check"><input type="checkbox" id="remote-llm-hybrid" /> 参与混合模式</label>
            <label class="settings-check"><input type="checkbox" id="remote-llm-reasoning-enabled" /> 启用思考模式（仅支持 reasoning 的接口）</label>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0">
            <div>
              <label>API Base</label>
              <input id="remote-llm-api-base" placeholder="https://api.openai.com/v1" />
            </div>
            <div>
              <label>API Key</label>
              <input id="remote-llm-api-key" type="password" placeholder="sk-..." />
            </div>
            <div>
              <label>模型</label>
              <input id="remote-llm-model" list="remote-llm-model-options" placeholder="gpt-4o-mini" />
              <datalist id="remote-llm-model-options"></datalist>
              <div id="remote-llm-model-discovery" class="settings-note"></div>
            </div>
            <div>
              <label>温度</label>
              <input id="remote-llm-temperature" type="number" min="0" max="2" step="0.1" />
            </div>
            <div>
              <label>最大输出 tokens</label>
              <input id="remote-llm-max-tokens" type="number" min="64" max="8192" />
            </div>
            <div>
              <label>超时(秒)</label>
              <input id="remote-llm-timeout" type="number" min="5" max="180" />
            </div>
          </div>
          <div class="settings-row">
            <label for="remote-llm-reasoning-effort">思考强度</label>
            <select id="remote-llm-reasoning-effort">
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
            </select>
          </div>
          <label>用户提示词</label>
          <textarea id="remote-llm-user-prompt" placeholder="可选：写入你希望大模型遵守的角色、语气和回答偏好"></textarea>
          <div class="settings-note">这段内容会放入实际发送给大模型的系统提示中；内置系统提示由应用维护，不在界面中显示。</div>
          <div class="settings-actions">
            <button id="remote-llm-save-btn">保存接口配置</button>
            <button id="remote-llm-test-btn">测试连接</button>
            <button id="remote-llm-mode-btn">切到接口模式</button>
          </div>
        </div>
        <div class="settings-section" id="sec-chat-mode">
          <h3>━ 对话引擎</h3>
          <div class="status" id="chat-mode-status" style="color:#657184">加载中...</div>
          <div class="settings-note">稀疏增强模式先输入 <code>/train_sparse</code> 训练；它包含盘古 pi 级数激活与增强短路，并兼容旧稀疏权重。</div>
          <label class="settings-check"><input type="checkbox" id="tiny-llm-deep-reply" /> TinyLLM 深度回答</label>
          <div class="settings-note">为 TinyLLM 加入固定的回答框架以聚焦结论；不会生成、保存或展示思维链。</div>
          <div class="settings-row">
            <label for="chat-mode-select">当前引擎</label>
            <select id="chat-mode-select"></select>
          </div>
          <div class="settings-actions">
            <button id="chat-mode-save-btn">切换引擎</button>
          </div>
        </div>
        <div class="settings-section" id="sec-ai-plugin">
          <h3>━ 插件与扩展</h3>
          <div class="settings-note">已安装插件</div>
          <div id="plugin-list" class="plugin-list" data-i18n="plugins_loading">加载中...</div>
          <div class="settings-actions">
            <button type="button" id="plugin-reload-btn" data-i18n="refresh_plugins">刷新插件</button>
            <button type="button" id="plugin-new-btn" data-i18n="new_plugin">新建插件</button>
          </div>
          <h3>AI 插件沙箱</h3>
          <div class="status" id="ai-plugin-status" style="color:#657184">允许网络和文件能力；先在隔离目录验证并杀毒扫描，通过后才安装。</div>
          <input id="ai-plugin-dir" placeholder="插件目录名，如 ai_notes" />
          <input id="ai-plugin-name" placeholder="插件名称，如 AI Notes" />
          <input id="ai-plugin-desc" placeholder="插件描述" />
          <input id="ai-plugin-command" placeholder="命令，如 /ai_notes" />
          <select id="ai-plugin-isolation">
            <option value="auto">自动：Docker 优先，否则 Windows Sandbox</option>
            <option value="docker">Docker 容器</option>
            <option value="windows_sandbox">Windows Sandbox</option>
          </select>
          <textarea id="ai-plugin-code" placeholder="AI 生成的 plugin.py 代码"></textarea>
          <button id="ai-plugin-example-btn" style="margin-right:6px">生成示例代码</button>
          <button id="ai-plugin-validate-btn" style="margin-right:6px">沙箱验证</button>
          <button id="ai-plugin-install-btn">验证并安装</button>
        </div>
        </div>
      </div>`;
    document.body.appendChild(settingsOverlay);
    bindPluginManagement();
    applyI18n();
    applyDisplayConfig(i18nState?.config?.display || i18nState?.display || displayDefaults);

    const settingsCategories = [
      { group: "外观", id: "display", label: "显示与界面", sections: ["sec-display", "sec-language", "sec-pet-display"] },
      { group: "应用", id: "update", label: "更新与数据", sections: ["sec-update", "sec-identity", "sec-memory", "sec-privacy"] },
      { group: "智能", id: "ai", label: "AI 与模型", sections: ["sec-chat-mode", "sec-remote-llm", "sec-audit", "sec-local-growth", "sec-runtime-behavior", "sec-python", "sec-torch", "sec-zluda", "sec-datasets", "sec-ocr"] },
      { group: "输入与身份", id: "voice", label: "语音与身份", sections: ["sec-tts", "sec-voiceprint", "sec-identity-confirm"] },
      { group: "视觉与角色", id: "visual", label: "视觉与角色", sections: ["sec-camera", "sec-opencv", "sec-face", "sec-live2d", "sec-3d"] },
      { group: "扩展", id: "plugins", label: "插件与扩展", sections: ["sec-ai-plugin"] },
    ];
    const settingsGrid = settingsOverlay.querySelector(".settings-grid");
    const settingsSections = [...settingsGrid.querySelectorAll(":scope > .settings-section")];
    const settingsNav = document.createElement("nav");
    settingsNav.className = "settings-category-nav";
    settingsNav.setAttribute("aria-label", "设置类别");
    const settingsContent = document.createElement("div");
    settingsContent.className = "settings-content";
    settingsGrid.replaceChildren(settingsNav, settingsContent);
    settingsSections.forEach(section => settingsContent.appendChild(section));

    let activeSettingsCategory = "display";
    let activeSettingsSecondaryPage = "";
    function showSettingsCategory(categoryId) {
      const category = settingsCategories.find(item => item.id === categoryId) || settingsCategories[0];
      activeSettingsCategory = category.id;
      if (activeSettingsSecondaryPage) {
        document.getElementById("sec-display")?.classList.remove("settings-secondary-active");
        document.getElementById("display-page-main")?.classList.add("active");
        document.getElementById("display-page-detail")?.classList.remove("active");
      }
      activeSettingsSecondaryPage = "";
      settingsSections.forEach(section => {
        section.hidden = !category.sections.includes(section.id);
      });
      settingsNav.querySelectorAll("[data-settings-category]").forEach(button => {
        const active = button.dataset.settingsCategory === category.id;
        button.classList.toggle("active", active);
        button.setAttribute("aria-current", active ? "page" : "false");
      });
      settingsContent.scrollTop = 0;
    }
    function showSettingsSecondaryPage(sectionId) {
      activeSettingsSecondaryPage = sectionId;
      document.getElementById(sectionId)?.classList.add("settings-secondary-active");
      settingsSections.forEach(section => {
        section.hidden = section.id !== sectionId;
      });
      settingsContent.scrollTop = 0;
    }
    settingsCategories.forEach((category, index) => {
      const previous = settingsCategories[index - 1];
      if (!previous || previous.group !== category.group) {
        const group = document.createElement("div");
        group.className = "settings-category-group";
        group.dataset.settingsGroup = category.group;
        const label = document.createElement("div");
        label.className = "settings-category-label";
        label.textContent = category.group;
        group.appendChild(label);
        settingsNav.appendChild(group);
      }
      const group = settingsNav.lastElementChild;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "settings-category-button";
      button.dataset.settingsCategory = category.id;
      button.textContent = category.label;
      button.addEventListener("click", () => showSettingsCategory(category.id));
      group.appendChild(button);
    });
    showSettingsCategory(activeSettingsCategory);

    document.getElementById("settings-btn").addEventListener("click", () => {
      settingsOverlay.classList.add("open");
      showDisplayPage("main");
      showSettingsCategory(activeSettingsCategory);
      const settingsLanguageSelect = document.getElementById("settings-language-select");
      if (settingsLanguageSelect) settingsLanguageSelect.value = i18nState?.locale || "zh-CN";
      loadSettings();
      loadPlugins();
    });
    document.getElementById("settings-close").addEventListener("click", () => {
      settingsOverlay.classList.remove("open");
    });
    settingsOverlay.addEventListener("click", (e) => {
      if (e.target === settingsOverlay) settingsOverlay.classList.remove("open");
    });
    document.getElementById("settings-language-select")?.addEventListener("change", () => {
      if (!languageSelect) return;
      languageSelect.value = document.getElementById("settings-language-select").value;
      languageSelect.dispatchEvent(new Event("change"));
    });
    document.getElementById("display-open-btn")?.addEventListener("click", () => showDisplayPage("detail"));
    document.getElementById("tour-restart-btn")?.addEventListener("click", () => {
      settingsOverlay.classList.remove("open");
      window.startGuidedTour?.();
    });
    document.getElementById("display-back-btn")?.addEventListener("click", () => showDisplayPage("main"));
    document.querySelectorAll('input[name="display-theme"], #display-font-scale, #display-density, #display-radius, #display-sidebar-width, #display-avatar-height, #custom-theme-grid input[type="color"]').forEach(el => {
      el.addEventListener("input", () => applyDisplayConfig(displayConfigFromControls()));
      el.addEventListener("change", () => applyDisplayConfig(displayConfigFromControls()));
    });
    document.getElementById("display-save-btn")?.addEventListener("click", () => {
      const btn = document.getElementById("display-save-btn");
      const statusEl = document.getElementById("display-status");
      const payload = displayConfigFromControls();
      applyDisplayConfig(payload);
      if (btn) btn.disabled = true;
      if (statusEl) statusEl.textContent = "正在保存...";
      fetch("/api/display", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload)})
        .then(r => r.json())
        .then(data => {
          if (!data.ok) throw new Error(data.error || "保存失败");
          applyDisplayConfig(data.display || data.config || payload);
          if (statusEl) statusEl.textContent = "已保存";
        })
        .catch(err => {
          if (statusEl) statusEl.textContent = "保存失败：" + err;
        })
        .finally(() => {
          if (btn) btn.disabled = false;
        });
    });
    document.getElementById("display-reset-btn")?.addEventListener("click", () => {
      applyDisplayConfig(displayDefaults);
      const statusEl = document.getElementById("display-status");
      if (statusEl) statusEl.textContent = "已恢复默认，点击保存后永久生效";
    });
    document.getElementById("custom-theme-copy-btn")?.addEventListener("click", () => {
      const activeTheme = document.querySelector('input[name="display-theme"]:checked')?.value || displayConfig.theme;
      const palette = displayThemePalettes[activeTheme] || displayThemePalettes.soft;
      applyDisplayConfig({...displayConfigFromControls(), theme: "custom", custom: palette});
      const statusEl = document.getElementById("display-status");
      if (statusEl) statusEl.textContent = "已复制为自定义起点，调整后点击保存";
    });
    document.getElementById("update-save-btn")?.addEventListener("click", () => postUpdateAction("configure", "正在保存更新设置..."));
    document.getElementById("update-check-btn")?.addEventListener("click", () => postUpdateAction("check", "正在检查更新..."));
    document.getElementById("update-download-btn")?.addEventListener("click", () => postUpdateAction("download", "正在下载更新..."));
    document.getElementById("update-install-btn")?.addEventListener("click", () => {
      if (!confirm("将启动更新安装器。安装过程中应用可能会自动关闭并重启，是否继续？")) return;
      postUpdateAction("install", "正在启动安装器...");
    });
    document.getElementById("update-back-btn")?.addEventListener("click", () => showUpdatePage("main"));

    function updateSection(prefix, info) {
      info = info || {installed: false, detail: "检测失败", size: "未知"};
      const statusEl = document.getElementById(prefix + "-status");
      const btnEl = document.getElementById(prefix + "-install-btn");
      const sizeEl = document.getElementById(prefix + "-size");
      const uninstallBtn = document.getElementById(prefix + "-uninstall-btn");
      const sizeText = info.size && info.size !== "0 MB" ? info.size : "";
      
      if (info.installed) {
        statusEl.textContent = "" + info.detail;
        statusEl.className = "status ok";
        if (btnEl) {
          btnEl.disabled = true;
          btnEl.textContent = "已安装";
        }
        if (sizeEl) sizeEl.textContent = "安装后占用：" + (sizeText || info.size || "未知");
        if (uninstallBtn && info.removable !== false) {
          uninstallBtn.style.display = "inline-block";
          uninstallBtn.onclick = () => uninstallComponent(prefix);
        } else if (uninstallBtn) {
          uninstallBtn.style.display = "none";
        }
      } else {
        statusEl.textContent = "" + info.detail;
        statusEl.className = "status err";
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = btnEl.dataset.label || "安装";
        }
        if (sizeEl) sizeEl.textContent = sizeText ? "已占用：" + sizeText : "安装后占用：安装完成后显示";
        if (uninstallBtn) uninstallBtn.style.display = "none";
      }
      
      // PyTorch 特殊处理：显示 GPU 信息和版本选择
      if (prefix === "torch" && info.gpu) {
        const gpuEl = document.getElementById("torch-gpu");
        const versionSelect = document.getElementById("torch-version-select");
        const gpu = info.gpu;
        
        const gpuLabels = {NVIDIA: "NVIDIA", AMD: "AMD", Intel: "Intel", unknown: "未知"};
        const recLabels = {cuda121: "CUDA 12.1", directml: "DirectML", rocm: "ROCm", "rocm-nightly": "ROCm nightly", cpu: "CPU"};
        
        let gpuText = `GPU: ${gpuLabels[gpu.gpu_brand] || gpu.gpu_brand} (${gpu.gpu_name})`;
        if (gpu.gfx_target) {
          gpuText += ` [${gpu.gfx_target}]`;
        }
        if (gpu.torch_version !== "未安装") {
          const backendLabels = {rocm: "ROCm", cuda: "CUDA", directml: "DirectML", cpu: "CPU", broken: "不可用", none: "未启用 GPU"};
          const backend = gpu.torch_backend || (gpu.torch_cuda ? "cuda" : "cpu");
          gpuText += ` | 当前: PyTorch ${gpu.torch_version} (${backendLabels[backend] || backend})`;
        }
        gpuText += ` | 推荐: ${recLabels[gpu.recommended] || gpu.recommended}`;
        gpuEl.textContent = gpuText;
        
        // 未安装时显示版本选择
        if (!info.installed) {
          versionSelect.style.display = "block";
          document.getElementById("torch-version").value = gpu.recommended;
        }
      }
    }

    function uninstallComponent(name) {
      const labels = {ocr: "OCR", torch: "PyTorch", zluda: "ZLUDA", opencv: "OpenCV", tts: "Edge-TTS", datasets: "数据集工具"};
      if (!confirm("确定要卸载 " + (labels[name] || name) + " 吗？")) return;
      
      const btn = document.getElementById(name + "-uninstall-btn");
      const status = document.getElementById(name + "-status");
      const progress = ensureComponentProgress(name);
      const steps = [
        [8, "准备卸载..."],
        [22, "正在请求卸载任务..."],
        [45, "正在删除组件文件..."],
        [68, "正在清理残留..."],
        [86, "正在复检安装状态..."],
      ];
      let stepIndex = 0;
      showComponentProgress(progress, 0, "准备卸载...", "");
      const progressTimer = setInterval(() => {
        if (stepIndex >= steps.length) return;
        const [percent, text] = steps[stepIndex];
        showComponentProgress(progress, percent, text, "");
        stepIndex += 1;
      }, 900);
      btn.disabled = true;
      btn.textContent = "卸载中…";
      status.textContent = "正在卸载，请稍候…";
      status.className = "status loading";
      
      fetch("/api/settings/uninstall", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({component: name})})
        .then(r => r.json())
        .then(data => {
          clearInterval(progressTimer);
          if (data.ok) {
            showComponentProgress(progress, 100, "卸载完成。", "ok");
            status.textContent = "" + data.message;
            status.className = "status ok";
            btn.disabled = false;
            btn.textContent = "删除";
            loadSettings();
          } else {
            showComponentProgress(progress, 100, "卸载失败，请查看错误信息。", "err");
            status.textContent = "卸载失败：" + (data.error || "未知错误");
            status.className = "status err";
            btn.disabled = false;
            btn.textContent = "删除";
          }
        })
        .catch(err => {
          clearInterval(progressTimer);
          showComponentProgress(progress, 100, "卸载失败，请查看错误信息。", "err");
          status.textContent = "卸载失败：" + err;
          status.className = "status err";
          btn.disabled = false;
          btn.textContent = "删除";
        });
    }

    function ensureComponentProgress(name) {
      const section = document.getElementById("sec-" + name);
      let progress = document.getElementById(name + "-progress");
      if (!progress) {
        progress = document.createElement("div");
        progress.id = name + "-progress";
        progress.className = "component-progress";
        progress.innerHTML = `
          <div class="component-progress-track"><div class="component-progress-bar"></div></div>
          <div class="component-progress-text"></div>
        `;
        const uninstallBtn = document.getElementById(name + "-uninstall-btn");
        section.insertBefore(progress, uninstallBtn ? uninstallBtn.nextSibling : null);
      }
      return progress;
    }

    function showComponentProgress(progress, percent, text, state) {
      progress.classList.add("open");
      progress.classList.toggle("ok", state === "ok");
      progress.classList.toggle("err", state === "err");
      progress.querySelector(".component-progress-bar").style.width = Math.max(0, Math.min(100, percent)) + "%";
      progress.querySelector(".component-progress-text").textContent = `${Math.round(percent)}% · ${text}`;
    }

    function renderAuditRecent(audits) {
      const list = document.getElementById("audit-recent");
      if (!list) return;
      list.innerHTML = "";
      if (!audits || !audits.length) {
        const empty = document.createElement("div");
        empty.className = "settings-note";
        empty.textContent = "最近暂无可判定的审计结果。";
        list.appendChild(empty);
        return;
      }
      audits.slice().reverse().forEach(item => {
        const card = document.createElement("div");
        card.className = "file-card";
        const quality = item.ai_quality?.overall_score;
        const correctness = item.ai_correctness?.overall_correctness;
        const source = String(item.audit_source || "");
        const isLocalAudit = source === "local" || source === "local_quick";
        const sourceLabel = isLocalAudit ? "本地规则审计" : (source ? "AI 审计" : "审计");
        const autoApplied = item.review_status === "auto_applied" || !!item.auto_apply_suggested_correction;
        const needsAction = !autoApplied && (!!item.needs_user_action || (quality != null && quality < 0.65) || (correctness != null && correctness < 0.65));
        const suggested = trainingResponseText(item.suggested_response || "");
        const correctionPending = !!item.correction_pending && !suggested;
        const title = document.createElement("div");
        title.style.fontWeight = "700";
        title.textContent = `审计 ${String(item.timestamp || "").slice(0, 16) || item.audit_id || ""} · ${sourceLabel}${correctionPending ? " · 自动处理中" : (needsAction ? " · 待处理" : "")}`;
        const body = document.createElement("div");
        body.style.whiteSpace = "pre-wrap";
        body.textContent = [
          correctionPending ? "状态：已加入审计队列，正在等待审计 AI 生成改写建议。" : (autoApplied ? "状态：已自动采用审计 AI 的改写并写入训练记忆。" : (needsAction ? "状态：待处理。请改正并训练，或采用审计 AI 给出的建议改写。" : "")),
          isLocalAudit ? "来源：本地规则审计，分数是粗略提示，主要用于发现需要改写训练的回复。" : "",
          `问：${String(item.user_message || "").replace(/\s+/g, " ").slice(0, 120)}`,
          `答：${trainingResponseText(item.ai_reply || "").replace(/\s+/g, " ").slice(0, 160)}`,
          `评分：质量 ${quality == null ? "?" : Math.round(quality * 100) + "%"}；正确性 ${correctness == null ? "?" : Math.round(correctness * 100) + "%"}`,
          item.suggestions?.length ? `建议：${item.suggestions.slice(0, 2).join("；")}` : "",
          suggested ? `建议改写：${suggested.replace(/\s+/g, " ").slice(0, 180)}` : (correctionPending ? "建议改写：生成中，请稍后刷新设置页查看。" : (needsAction ? "建议改写：尚未生成。可勾选“自动向审计 AI 请求改写建议”，让后台自动生成。" : "")),
          item.correction_reason ? `改写原因：${String(item.correction_reason).replace(/\s+/g, " ").slice(0, 120)}` : "",
          item.audit_error ? `审计说明：${String(item.audit_error).replace(/\s+/g, " ").slice(0, 160)}` : "",
          item.correction_error ? `改写说明：${String(item.correction_error).replace(/\s+/g, " ").slice(0, 160)}` : "",
        ].filter(Boolean).join("\n");
        const actions = document.createElement("div");
        actions.style.display = "flex";
        actions.style.flexWrap = "wrap";
        actions.style.gap = "6px";
        actions.style.marginTop = "6px";
        actions.dataset.auditActions = "1";
        const approve = document.createElement("button");
        approve.type = "button";
        approve.textContent = "采用为训练";
        const reject = document.createElement("button");
        reject.type = "button";
        reject.textContent = "不采用";
        const correct = document.createElement("button");
        correct.type = "button";
        correct.textContent = "改正并训练";
        const useSuggested = document.createElement("button");
        useSuggested.type = "button";
        useSuggested.textContent = "采用建议并训练";
        useSuggested.disabled = !suggested;
        const actionStatus = document.createElement("span");
        actionStatus.style.alignSelf = "center";
        actionStatus.style.fontSize = "12px";
        actionStatus.style.color = "#657184";
        if (!item.audit_id) {
          actionStatus.textContent = "这条审计缺少 ID，暂不能处理";
          approve.disabled = true;
          reject.disabled = true;
          correct.disabled = true;
          useSuggested.disabled = true;
        }
        approve.addEventListener("click", () => submitAuditTraining(item.audit_id, "approve", "", actions));
        reject.addEventListener("click", () => submitAuditTraining(item.audit_id, "reject", "", actions));
        useSuggested.addEventListener("click", () => {
          if (suggested) submitAuditTraining(item.audit_id, "correct", suggested, actions);
        });
        correct.addEventListener("click", () => {
          const text = prompt("输入你希望 AI 学习的正确回答：", suggested || trainingResponseText(item.ai_reply || ""));
          if (text && text.trim()) submitAuditTraining(item.audit_id, "correct", text.trim(), actions);
        });
        actions.append(approve, reject);
        if (suggested) actions.append(useSuggested);
        actions.append(correct, actionStatus);
        card.append(title, body, actions);
        list.appendChild(card);
      });
    }

    function removeHandledAuditCard(actions) {
      const card = actions?.closest(".file-card");
      if (card) card.remove();
      const list = document.getElementById("audit-recent");
      if (list && !list.querySelector(".file-card")) {
        list.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "settings-note";
        empty.textContent = "暂无待处理审计。";
        list.appendChild(empty);
      }
    }

    function updateTorchDx12Training(neuralInfo) {
      const btn = document.getElementById("torch-dx12-train-btn");
      const status = document.getElementById("torch-dx12-status");
      if (!btn || !status) return;
      const torch = neuralInfo?.torch || {};
      const ready = !!torch.available && !!torch.directml_available;
      btn.disabled = !ready;
      status.textContent = ready
        ? "DirectX 12 (DirectML) 已就绪。训练会在独立进程中运行。"
        : "需要安装 PyTorch 的 DirectML 版本，才能使用 DX12 训练。";
      status.className = ready ? "settings-note" : "settings-note status err";
    }

    async function submitAuditTraining(auditId, decision, correctedResponse, actions) {
      const statusEl = actions?.querySelector("span");
      if (!auditId) {
        if (statusEl) {
          statusEl.textContent = "这条审计缺少 ID，暂不能处理";
          statusEl.style.color = "#c0392b";
        }
        return;
      }
      const buttons = Array.from(actions.querySelectorAll("button"));
      buttons.forEach(btn => btn.disabled = true);
      if (statusEl) {
        statusEl.textContent = "处理中...";
        statusEl.style.color = "#657184";
      }
      try {
        const resp = await fetch("/api/audit_training", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ audit_id: auditId, decision, corrected_response: correctedResponse || "" })
        });
        const text = await resp.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (parseErr) {
          throw new Error(text.slice(0, 200) || `HTTP ${resp.status}`);
        }
        if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
        if (!data.ok) throw new Error(data.error || "未知错误");
        renderTraining(data.training);
        if (statusEl) {
          statusEl.textContent = "已处理，正在移除...";
          statusEl.style.color = "#0b7a55";
        }
        setTimeout(() => removeHandledAuditCard(actions), 250);
      } catch (err) {
        buttons.forEach(btn => btn.disabled = false);
        if (statusEl) {
          statusEl.textContent = "处理失败：" + String(err).replace(/^Error:\s*/, "");
          statusEl.style.color = "#c0392b";
        }
      }
    }

    function loadSettings() {
      document.querySelectorAll(".component-progress.open").forEach(el => el.classList.remove("open", "installing", "ok", "err"));
      loadUpdateSettings();
      loadDisplaySettings();
      loadLocalGrowthSettings();
      loadRuntimeBehaviorSettings();
      fetch("/api/settings").then(r => r.json()).then(data => {
        updateSection("ocr", data.ocr);
        updateSection("torch", data.torch);
        updateTorchDx12Training(data.neural);
        updateSection("zluda", data.zluda);
        updateSection("opencv", data.opencv);
        updateSection("datasets", data.datasets);
        updateSection("tts", data.tts);
        updatePythonSection(data.python);
        updateCppToolchainSection(data.cpp_toolchain);
        updateCameraSection(data.opencv);
        // Load face recognition status
        fetch("/api/face/status").then(r => r.json()).then(data => {
          if (data.ok) {
            const status = data.status || "";
            const available = status.split("\n")[0].includes("face_recognition + cv2 可用");
            const countMatch = status.match(/已注册人脸：(\d+)/);
            updateFaceSection({
              available: available,
              detail: status.split("\n")[0] || "",
              count: countMatch ? countMatch[1] : 0
            });
          } else {
            updateFaceSection({available: false, detail: data.error || "检测失败"});
          }
        }).catch(() => {
          updateFaceSection({available: false, detail: "检测失败"});
        });
        document.getElementById("ocr-install-btn").dataset.label = "安装 OCR";
        document.getElementById("torch-install-btn").dataset.label = "安装 PyTorch";
        document.getElementById("zluda-install-btn").dataset.label = "安装 ZLUDA";
        document.getElementById("opencv-install-btn").dataset.label = "安装 OpenCV";
        document.getElementById("datasets-install-btn").dataset.label = "安装";
        document.getElementById("tts-install-btn").dataset.label = "安装 Edge-TTS";
      }).catch(() => {
        ["ocr","torch","zluda","opencv","datasets"].forEach(p => {
          document.getElementById(p + "-status").textContent = "检测失败";
          document.getElementById(p + "-status").className = "status err";
        });
      });
      // Load audit config
      fetch("/api/settings/audit").then(r => r.json()).then(data => {
        const cfg = data.config || {};
        document.getElementById("audit-enabled").checked = !!data.enabled;
        document.getElementById("audit-use-cloud").checked = !!cfg.use_cloud_audit;
        document.getElementById("audit-auto-suggest").checked = !!cfg.auto_suggest_corrections;
        document.getElementById("audit-api-base").value = cfg.api_base || "";
        document.getElementById("audit-api-key").value = "";
        document.getElementById("audit-api-key").placeholder = cfg.api_key ? (cfg.api_key || "已配置") : "sk-...";
        document.getElementById("audit-model").value = cfg.model || "";
        document.getElementById("audit-language").value = cfg.language || "zh";
        document.getElementById("audit-batch-size").value = cfg.batch_size || 5;
        document.getElementById("audit-interval").value = cfg.audit_interval || 10;
        document.getElementById("audit-context-turns").value = cfg.max_context_turns || 6;
        scheduleModelDiscovery("audit", 0, true);
        const statusEl = document.getElementById("audit-status");
        if (data.enabled) {
          const mode = cfg.use_cloud_audit ? "云端辅助" : "本地规则";
          statusEl.textContent = cfg.auto_suggest_corrections && cfg.use_cloud_audit ? `审计已启用（${mode}），云端改写建议会自动写入训练记忆` : `审计已启用（${mode}），审计结果需人工审核后学习`;
          statusEl.className = "status ok";
        } else {
          statusEl.textContent = "审计未启用";
          statusEl.className = "status";
        }
        // Show summary
        const summary = data.summary || {};
        const total = summary.total_audits || 0;
        const sumEl = document.getElementById("audit-summary");
        if (total > 0) {
          let lines = [`已审计 ${total} 条对话`];
          for (const [key, label] of [["avg_overall_correctness","正确性"],["avg_relevance","相关性"],["avg_helpfulness","有用性"],["avg_overall_score","综合"]]) {
            if (summary[key]) {
              lines.push(`${label}: ${(summary[key].value * 100).toFixed(0)}%`);
            }
          }
          sumEl.textContent = lines.join(" | ");
        } else {
          sumEl.textContent = "暂无审计记录";
        }
        renderAuditRecent(data.recent_audits || []);
      }).catch(() => {
        document.getElementById("audit-status").textContent = "加载审计配置失败";
        document.getElementById("audit-status").className = "status err";
      });

      fetch("/api/settings/remote_llm").then(r => r.json()).then(data => {
        const cfg = data.config || {};
        document.getElementById("remote-llm-enabled").checked = !!cfg.enabled;
        document.getElementById("remote-llm-hybrid").checked = cfg.enabled_for_hybrid !== false;
        document.getElementById("remote-llm-reasoning-enabled").checked = !!cfg.reasoning_enabled;
        document.getElementById("remote-llm-reasoning-effort").value = cfg.reasoning_effort || "medium";
        document.getElementById("remote-llm-api-base").value = cfg.api_base || "";
        document.getElementById("remote-llm-api-key").value = "";
        document.getElementById("remote-llm-api-key").placeholder = cfg.configured ? (cfg.api_key || "已配置") : "sk-...";
        document.getElementById("remote-llm-model").value = cfg.model || "";
        document.getElementById("remote-llm-temperature").value = cfg.temperature ?? 0.7;
        scheduleModelDiscovery("remote_llm", 0, true);
        document.getElementById("remote-llm-max-tokens").value = cfg.max_tokens || 1024;
        document.getElementById("remote-llm-timeout").value = cfg.timeout || 45;
        document.getElementById("remote-llm-user-prompt").value = cfg.user_prompt || "";
        const statusEl = document.getElementById("remote-llm-status");
        if (data.ready) {
          statusEl.textContent = "大模型接口已启用：" + (cfg.model || "");
          statusEl.className = "status ok";
        } else if (cfg.enabled && !cfg.configured) {
          statusEl.textContent = "已开启，但还没有 API Key";
          statusEl.className = "status err";
        } else {
          statusEl.textContent = "大模型接口未启用";
          statusEl.className = "status";
        }
      }).catch(() => {
        document.getElementById("remote-llm-status").textContent = "加载大模型接口配置失败";
        document.getElementById("remote-llm-status").className = "status err";
      });

      fetch("/api/chat/modes").then(r => r.json()).then(data => {
        const select = document.getElementById("chat-mode-select");
        const statusEl = document.getElementById("chat-mode-status");
        const modes = Array.isArray(data.modes) ? data.modes : [];
        select.replaceChildren(...modes.map(mode => {
          const option = document.createElement("option");
          option.value = mode.id;
          option.textContent = mode.name + " - " + mode.description;
          option.selected = !!mode.active;
          return option;
        }));
        const active = modes.find(mode => mode.active);
        statusEl.textContent = active ? "当前使用：" + active.name : "未选择对话引擎";
        statusEl.className = "status";
      }).catch(() => {
        document.getElementById("chat-mode-status").textContent = "加载对话引擎失败";
        document.getElementById("chat-mode-status").className = "status err";
      });

      fetch("/api/settings/tiny_llm").then(r => r.json()).then(data => {
        document.getElementById("tiny-llm-deep-reply").checked = !!data.enabled;
      }).catch(() => {
        document.getElementById("chat-mode-status").textContent = "加载 TinyLLM 设置失败";
        document.getElementById("chat-mode-status").className = "status err";
      });

      fetch("/api/privacy").then(r => r.json()).then(data => {
        const statusEl = document.getElementById("privacy-status");
        const revokeBtn = document.getElementById("privacy-revoke-btn");
        privacyAccepted = !!data.accepted;
        if (data.accepted) {
          const time = data.accepted_at ? ` · 同意时间：${data.accepted_at}` : "";
          statusEl.textContent = `已同意隐私政策 · 版本：${data.version || data.policy_version || "未知"}${time}`;
          statusEl.className = "status ok";
          revokeBtn.disabled = false;
        } else {
          statusEl.textContent = "尚未同意隐私政策";
          statusEl.className = "status err";
          revokeBtn.disabled = true;
        }
      }).catch(() => {
        document.getElementById("privacy-status").textContent = "加载隐私状态失败";
        document.getElementById("privacy-status").className = "status err";
      });
      
      // Load TTS config
      fetch("/api/tts/config").then(r => r.json()).then(data => {
        ttsConfig = data;
        const installBtn = document.getElementById("tts-install-btn");
        const uninstallBtn = document.getElementById("tts-uninstall-btn");
        const configArea = document.getElementById("tts-config-area");
        const statusEl = document.getElementById("tts-status");
        
        if (data.available) {
          // Edge-TTS 已安装，显示配置区域
          installBtn.style.display = "none";
          uninstallBtn.style.display = "inline-block";
          configArea.style.display = "block";
          
          document.getElementById("tts-enabled").checked = !!data.enabled;
          document.getElementById("tts-auto-play").checked = !!data.auto_play;
          document.getElementById("tts-voice").value = data.voice || "zh-CN-XiaoxiaoNeural";
          
          // 解析语速、音调、音量
          const rate = parseInt(data.rate || "+0%") || 0;
          const pitch = parseInt(data.pitch || "+0Hz") || 0;
          const volume = parseInt(data.volume || "+0%") || 0;
          
          document.getElementById("tts-rate").value = rate;
          document.getElementById("tts-rate-value").textContent = (rate >= 0 ? "+" : "") + rate + "%";
          document.getElementById("tts-pitch").value = pitch;
          document.getElementById("tts-pitch-value").textContent = (pitch >= 0 ? "+" : "") + pitch + "Hz";
          document.getElementById("tts-volume").value = volume;
          document.getElementById("tts-volume-value").textContent = (volume >= 0 ? "+" : "") + volume + "%";
          
          if (data.enabled) {
            statusEl.textContent = "语音合成已启用";
            statusEl.className = "status ok";
          } else {
            statusEl.textContent = "语音合成已就绪";
            statusEl.className = "status";
          }
          
          // 缓存信息
          const cacheCount = data.cache_count || 0;
          const cacheSize = data.cache_size || 0;
          const cacheSizeKB = (cacheSize / 1024).toFixed(1);
          document.getElementById("tts-cache-info").textContent = `缓存：${cacheCount} 个文件，${cacheSizeKB} KB`;
        } else {
          // Edge-TTS 未安装，显示安装按钮
          installBtn.style.display = "inline-block";
          uninstallBtn.style.display = "none";
          configArea.style.display = "none";
          statusEl.textContent = "警告：Edge-TTS 未安装";
          statusEl.className = "status err";
        }
      }).catch(() => {
        document.getElementById("tts-status").textContent = "加载 TTS 配置失败";
        document.getElementById("tts-status").className = "status err";
      });

      loadVoiceprints();
      loadIdentityConfirmation();
    }

    function formatUpdateTime(ts) {
      if (!ts) return "从未检查";
      try {
        return new Date(Number(ts) * 1000).toLocaleString();
      } catch (_err) {
        return String(ts);
      }
    }

    let latestUpdateState = null;

    function showUpdatePage(page) {
      const mainPage = document.getElementById("update-page-main");
      const logPage = document.getElementById("update-page-log");
      if (!mainPage || !logPage) return;
      mainPage.classList.toggle("active", page !== "log");
      logPage.classList.toggle("active", page === "log");
    }

    function updateSummaryItem(label, value) {
      return `<div class="update-summary-item"><span class="update-summary-label">${escapeSettingsText(label)}</span><span class="update-summary-value">${escapeSettingsText(value || "未知")}</span></div>`;
    }

    function previewUpdateNotes(notes) {
      const text = String(notes || "").replace(/[#*_`>\[\]\(\)]/g, "").replace(/\s+/g, " ").trim();
      if (!text) return "暂无更新日志。";
      return text.length > 96 ? text.slice(0, 96) + "..." : text;
    }

    function renderInlineMarkdown(text) {
      let html = escapeSettingsText(text);
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
      html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
      html = html.replace(/_([^_]+)_/g, "<em>$1</em>");
      html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      html = html.replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
      return html;
    }

    function renderMarkdownLite(markdown) {
      const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
      const html = [];
      let listType = "";
      let inCode = false;
      const closeList = () => {
        if (listType) {
          html.push(`</${listType}>`);
          listType = "";
        }
      };
      const openList = type => {
        if (listType !== type) {
          closeList();
          html.push(`<${type}>`);
          listType = type;
        }
      };
      for (const rawLine of lines) {
        const line = rawLine.replace(/\s+$/, "");
        if (/^\s*```/.test(line)) {
          closeList();
          if (inCode) {
            html.push("</code></pre>");
            inCode = false;
          } else {
            html.push("<pre><code>");
            inCode = true;
          }
          continue;
        }
        if (inCode) {
          html.push(escapeSettingsText(rawLine) + "\n");
          continue;
        }
        if (!line.trim()) {
          closeList();
          continue;
        }
        const heading = line.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
          closeList();
          const level = heading[1].length;
          html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
          continue;
        }
        const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
        if (unordered) {
          openList("ul");
          html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
          continue;
        }
        const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
        if (ordered) {
          openList("ol");
          html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
          continue;
        }
        const quote = line.match(/^\s*>\s?(.+)$/);
        if (quote) {
          closeList();
          html.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
          continue;
        }
        closeList();
        html.push(`<p>${renderInlineMarkdown(line)}</p>`);
      }
      closeList();
      if (inCode) html.push("</code></pre>");
      return html.join("");
    }

    function renderUpdateLogPage(data) {
      const versionEl = document.getElementById("update-log-version");
      const bodyEl = document.getElementById("update-log-body");
      if (!versionEl || !bodyEl) return;
      const latest = data?.latest || {};
      versionEl.textContent = latest.version ? `v${latest.version}` : "更新日志";
      const meta = [];
      if (latest.release_url) meta.push(`发布页：${latest.release_url}`);
      if (latest.asset_name) meta.push(`安装包：${latest.asset_name}`);
      if (data?.last_error) meta.push(`错误：${data.last_error}`);
      const notes = String(latest.notes || "").trim();
      const content = [];
      if (meta.length) content.push(meta.map(item => `<p>${renderInlineMarkdown(item)}</p>`).join(""));
      if (notes) content.push(renderMarkdownLite(notes));
      bodyEl.innerHTML = content.length
        ? content.join("")
        : '<span class="update-log-empty">暂无可显示的更新日志。检查更新后会在这里显示发布说明。</span>';
    }

    function renderUpdateState(data) {
      const statusEl = document.getElementById("update-status");
      const detailEl = document.getElementById("update-detail");
      const summaryEl = document.getElementById("update-summary");
      const releaseEl = document.getElementById("update-release-card");
      if (!statusEl || !detailEl || !summaryEl || !releaseEl || !data) return;
      latestUpdateState = data;
      document.getElementById("update-auto-check").checked = !!data.auto_check;
      document.getElementById("update-auto-download").checked = !!data.auto_download;
      document.getElementById("update-auto-install").checked = !!data.auto_install;
      document.getElementById("update-interval").value = data.check_interval_hours || 12;
      const latest = data.latest || {};
      const downloaded = data.downloaded || {};
      summaryEl.innerHTML = [
        updateSummaryItem("当前版本", data.current_version || "未知"),
        updateSummaryItem("最新版本", latest.version || "未获取"),
        updateSummaryItem("上次检查", formatUpdateTime(data.last_check)),
        updateSummaryItem("下载状态", downloaded.path ? "已下载" : "未下载"),
      ].join("");
      const releaseTitle = latest.version ? `版本 ${latest.version}` : "尚未获取发布信息";
      const releaseMeta = [
        latest.asset_name ? `安装包：${latest.asset_name}` : "",
        downloaded.path ? `已下载：${downloaded.path}` : "",
        data.last_error ? `错误：${data.last_error}` : "",
        latest.notes ? `更新摘要：${previewUpdateNotes(latest.notes)}` : "",
      ].filter(Boolean);
      releaseEl.innerHTML = `
        <div class="update-release-title"><span>${escapeSettingsText(releaseTitle)}</span>${data.update_available ? '<span class="update-pill">可更新</span>' : '<span class="update-pill">已同步</span>'}</div>
        <div class="update-meta">${releaseMeta.length ? escapeSettingsText(releaseMeta.join("\n")) : "检查更新后会显示安装包和发布说明。"}</div>
        <button type="button" class="update-page-link" id="update-log-btn">查看更新日志</button>
      `;
      const sourceEl = document.getElementById("update-source");
      if (sourceEl) {
        const repo = data.release_repo || "LoongSerpent9Realms/companion-ai-release";
        const page = data.release_page || (`https://github.com/${repo}/releases`);
        sourceEl.innerHTML = `检查地址：<a href="${escapeSettingsText(page)}" target="_blank" rel="noopener noreferrer">GitHub · ${escapeSettingsText(repo)}</a>`;
      }
      detailEl.textContent = latest.release_url ? `发布页：${latest.release_url}` : (data.release_page ? `发布页：${data.release_page}` : "");
      renderUpdateLogPage(data);
      document.getElementById("update-log-btn")?.addEventListener("click", () => showUpdatePage("log"));
      if (data.update_available) {
        statusEl.textContent = `发现新版本：${latest.version}`;
        statusEl.className = "status ok";
      } else if (data.last_error) {
        statusEl.textContent = "更新检查失败";
        statusEl.className = "status err";
      } else if (latest.version && latest.version !== data.current_version) {
        statusEl.textContent = `当前版本高于最新发布：${data.current_version}`;
        statusEl.className = "status";
      } else {
        statusEl.textContent = "当前已是最新版本";
        statusEl.className = "status";
      }
      document.getElementById("update-download-btn").disabled = !data.update_available;
      document.getElementById("update-install-btn").disabled = !downloaded.path;
    }

    function loadUpdateSettings() {
      fetch("/api/update")
        .then(r => r.json())
        .then(renderUpdateState)
        .catch(err => {
          const statusEl = document.getElementById("update-status");
          if (statusEl) {
            statusEl.textContent = "加载更新状态失败：" + err;
            statusEl.className = "status err";
          }
        });
    }

    function updatePayloadFromForm(action) {
      return {
        action,
        auto_check: document.getElementById("update-auto-check").checked,
        auto_download: document.getElementById("update-auto-download").checked,
        auto_install: document.getElementById("update-auto-install").checked,
        check_interval_hours: Number(document.getElementById("update-interval").value || 12),
      };
    }

    function postUpdateAction(action, busyText) {
      const statusEl = document.getElementById("update-status");
      if (statusEl) {
        statusEl.textContent = busyText;
        statusEl.className = "status loading";
      }
      return fetch("/api/update", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(updatePayloadFromForm(action))
      })
        .then(r => r.json())
        .then(data => {
          renderUpdateState(data);
          return data;
        })
        .catch(err => {
          if (statusEl) {
            statusEl.textContent = "更新操作失败：" + err;
            statusEl.className = "status err";
          }
        });
    }

    function renderVoiceprintList(prints) {
      const listEl = document.getElementById("voiceprint-list");
      if (!listEl) return;
      if (!prints || prints.length === 0) {
        listEl.innerHTML = '<div style="color:#657184">暂无声纹。输入名称后点击“录入声纹”。</div>';
        return;
      }
      listEl.innerHTML = prints.map(item => {
        const name = String(item.name || "未命名").replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
        const time = item.updated_at || item.created_at || "";
        const samples = item.samples || 1;
        return '<div class="voiceprint-item">' +
          '<div><strong>' + name + '</strong><div style="color:#657184">样本 ' + samples + ' · ' + time + '</div></div>' +
          '<button class="danger" data-voiceprint-delete="' + item.id + '">删除</button>' +
          '</div>';
      }).join("");
      listEl.querySelectorAll("[data-voiceprint-delete]").forEach(btn => {
        btn.addEventListener("click", () => deleteVoiceprint(btn.dataset.voiceprintDelete));
      });
    }

    function rerenderLocalizedState() {
      if (lastMemoryData) renderMemory(lastMemoryData);
      if (lastTrainingData) renderTraining(lastTrainingData);
      if (lastFilesData) renderFiles(lastFilesData);
      if (lastAvatarData) renderAvatar(lastAvatarData);
      if (voiceInputBtn && !voiceInputBtn.classList.contains("listening")) {
        voiceInputBtn.title = i18nText("voice_input");
      }
    }

    function setVoiceprintStatus(text, cls = "") {
      const statusEl = document.getElementById("voiceprint-status");
      if (!statusEl) return;
      statusEl.textContent = text;
      statusEl.className = "status" + (cls ? " " + cls : "");
    }

    function setVoiceprintResult(text, color = "#657184") {
      const resultEl = document.getElementById("voiceprint-result");
      if (!resultEl) return;
      resultEl.textContent = text;
      resultEl.style.color = color;
    }

    function renderIdentityConfirmation(data) {
      const el = document.getElementById("identity-confirm-status");
      if (!el) return;
      const current = data && data.current;
      if (!current) {
        el.textContent = "暂无。可以用人脸识别或声纹识别确认当前说话人。";
        el.className = "status";
        return;
      }
      const labels = {face: "人脸", voiceprint: "声纹"};
      const pct = Math.round((current.confidence || 0) * 100);
      el.textContent = "已确认：" + (current.name || "未知") + " · " + (labels[current.method] || current.method || "未知") + " · " + pct + "% · " + (current.confirmed_at || "");
      el.className = "status ok";
    }

    function loadIdentityConfirmation() {
      fetch("/api/identity_confirmation")
        .then(r => r.json())
        .then(data => renderIdentityConfirmation(data))
        .catch(() => renderIdentityConfirmation({current: null}));
    }

    function clearIdentityConfirmation() {
      fetch("/api/identity_confirmation", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action: "clear"})
      })
        .then(r => r.json())
        .then(data => renderIdentityConfirmation(data))
        .catch(err => {
          const el = document.getElementById("identity-confirm-status");
          if (el) { el.textContent = "清除失败：" + err; el.className = "status err"; }
        });
    }

    function loadVoiceprints() {
      fetch("/api/voiceprints")
        .then(r => r.json())
        .then(data => {
          if (!data.ok && data.error) throw new Error(data.error);
          renderVoiceprintList(data.prints || []);
          setVoiceprintStatus("已登记 " + (data.prints || []).length + " 个声纹", "ok");
        })
        .catch(err => {
          renderVoiceprintList([]);
          setVoiceprintStatus("加载声纹失败：" + err, "err");
        });
    }

    async function enrollVoiceprint() {
      const nameInput = document.getElementById("voiceprint-name");
      const name = (nameInput?.value || "").trim();
      if (!name) {
        setVoiceprintResult("请输入声纹名称", "#c0392b");
        return;
      }
      const btn = document.getElementById("voiceprint-enroll-btn");
      btn.disabled = true;
      btn.textContent = "录音中…";
      setVoiceprintStatus("请正常说话 2-3 秒，正在采样…", "loading");
      setVoiceprintResult("可以读一句固定短句，比如：这是我的本地 AI 伙伴。");
      try {
        const features = await captureVoiceFeatures();
        const resp = await fetch("/api/voiceprints", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({action: "enroll", name, features})
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "录入失败");
        renderVoiceprintList(data.prints || []);
        setVoiceprintStatus("声纹已保存到本机", "ok");
        setVoiceprintResult("录入完成：" + name, "#0b7a55");
      } catch (err) {
        setVoiceprintStatus("声纹录入失败", "err");
        setVoiceprintResult(String(err), "#c0392b");
      } finally {
        btn.disabled = false;
        btn.textContent = "录入声纹";
      }
    }

    async function recognizeVoiceprint() {
      const btn = document.getElementById("voiceprint-recognize-btn");
      btn.disabled = true;
      btn.textContent = "识别中…";
      setVoiceprintStatus("请说话 2-3 秒，正在比对本机声纹…", "loading");
      try {
        const features = await captureVoiceFeatures();
        const resp = await fetch("/api/voiceprints", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({action: "recognize", features})
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "识别失败");
        if (data.matched) {
          setVoiceprintStatus("识别到：" + data.name, "ok");
          setVoiceprintResult("匹配：" + data.name + "，置信度 " + Math.round((data.confidence || 0) * 100) + "%", "#0b7a55");
          loadIdentityConfirmation();
        } else {
          setVoiceprintStatus("未匹配到已登记声纹", "err");
          setVoiceprintResult(data.name ? ("最接近：" + data.name + "，但相似度不足") : (data.message || "没有可比对声纹"), "#9a5b00");
        }
      } catch (err) {
        setVoiceprintStatus("声纹识别失败", "err");
        setVoiceprintResult(String(err), "#c0392b");
      } finally {
        btn.disabled = false;
        btn.textContent = "识别当前说话人";
      }
    }

    function deleteVoiceprint(id) {
      if (!id || !confirm("确定删除这个声纹吗？")) return;
      fetch("/api/voiceprints", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action: "delete", id})
      })
        .then(r => r.json())
        .then(data => {
          renderVoiceprintList(data.prints || []);
          setVoiceprintStatus(data.ok ? "声纹已删除" : "没有找到要删除的声纹", data.ok ? "ok" : "err");
        })
        .catch(err => setVoiceprintStatus("删除失败：" + err, "err"));
    }

    function updateCameraSection(opencvInfo) {
      const cameraStatus = document.getElementById("camera-status");
      const testBtn = document.getElementById("camera-test-btn");
      const chatBtn = document.getElementById("camera-chat-btn");
      if (!cameraStatus) return;
      if (opencvInfo && opencvInfo.installed) {
        cameraStatus.textContent = "摄像头能力可用：" + opencvInfo.detail;
        cameraStatus.className = "status ok";
        testBtn.disabled = false;
        chatBtn.disabled = false;
      } else {
        cameraStatus.textContent = "需要先安装 OpenCV，才能进行摄像头观察。";
        cameraStatus.className = "status err";
        testBtn.disabled = true;
        chatBtn.disabled = true;
      }
    }

    function updatePythonSection(pythonInfo) {
      const statusEl = document.getElementById("python-status");
      const btnEl = document.getElementById("python-install-btn");
      const detailEl = document.getElementById("python-detail");
      const sizeEl = document.getElementById("python-size");
      if (!statusEl || !btnEl) return;
      const sizeText = pythonInfo?.size && pythonInfo.size !== "0 MB" ? pythonInfo.size : "";
      if (pythonInfo && pythonInfo.installed) {
        statusEl.textContent = "Python 已安装";
        statusEl.className = "status ok";
        btnEl.disabled = true;
        btnEl.textContent = "已安装";
        if (detailEl) detailEl.textContent = pythonInfo.detail;
        if (sizeEl) sizeEl.textContent = "安装后占用：" + (sizeText || pythonInfo.size || "未知");
      } else {
        statusEl.textContent = "需要安装 Python";
        statusEl.className = "status err";
        btnEl.disabled = false;
        btnEl.textContent = "自动安装 Python 3.12";
        if (detailEl) detailEl.textContent = pythonInfo ? pythonInfo.detail : "";
        if (sizeEl) sizeEl.textContent = sizeText ? "已占用：" + sizeText : "安装后占用：安装完成后显示";
      }
    }

    function updateCppToolchainSection(info) {
      const status = document.getElementById("cpp-toolchain-status");
      const detail = document.getElementById("cpp-toolchain-detail");
      const input = document.getElementById("cpp-toolchain-dir");
      if (!status || !input) return;
      input.value = info?.install_dir || input.value || "";
      status.textContent = info?.installed ? "C++ 工具链可用" : "未检测到 C++ 工具链";
      status.className = info?.installed ? "status ok" : "status err";
      if (detail) {
        const compiler = info?.compiler ? `\n编译器：${info.compiler}` : "";
        const path = info?.bin_dir ? `\n已配置 bin：${info.bin_dir}` : "";
        detail.textContent = (info?.detail || "") + compiler + path;
      }
    }

    function runCppToolchainAction(component, buttonId, idleLabel) {
      const button = document.getElementById(buttonId);
      const status = document.getElementById("cpp-toolchain-status");
      const detail = document.getElementById("cpp-toolchain-detail");
      const installDir = document.getElementById("cpp-toolchain-dir")?.value.trim() || "";
      if (!installDir) {
        if (detail) detail.textContent = "请先填写安装目录或已有工具链目录。";
        return;
      }
      if (button) { button.disabled = true; button.textContent = component === "cpp_toolchain" ? "安装中…" : "写入 PATH…"; }
      if (status) { status.textContent = component === "cpp_toolchain" ? "正在下载并安装 LLVM…" : "正在验证并写入用户 PATH…"; status.className = "status loading"; }
      fetch("/api/settings/install", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({component, install_dir: installDir})
      }).then(r => r.json()).then(data => {
        if (detail) detail.textContent = data.detail || (data.success ? "操作完成" : "操作失败");
        if (status) { status.textContent = data.success ? "C++ 工具链已就绪" : "C++ 工具链设置失败"; status.className = data.success ? "status ok" : "status err"; }
        if (data.success) loadSettings();
      }).catch(err => {
        if (detail) detail.textContent = "请求失败：" + String(err);
        if (status) { status.textContent = "C++ 工具链设置失败"; status.className = "status err"; }
      }).finally(() => {
        if (button) { button.disabled = false; button.textContent = idleLabel; }
      });
    }

    function installPython() {
      const btn = document.getElementById("python-install-btn");
      const originalText = btn?.textContent || "自动安装 Python 3.12";
      if (btn) { btn.disabled = true; btn.textContent = "下载安装中…"; }
      const detailEl = document.getElementById("python-detail");
      if (detailEl) { detailEl.textContent = "正在下载 Python 安装器…"; }
      fetch("/api/install_python")
        .then(r => r.json())
        .then(data => {
          if (detailEl) {
            detailEl.textContent = data.message || JSON.stringify(data);
            detailEl.style.color = data.ok ? "#276ef1" : "#e74c3c";
          }
          loadSettings();
        })
        .catch(err => {
          if (detailEl) { detailEl.textContent = "请求失败：" + err; detailEl.style.color = "#e74c3c"; }
        })
        .finally(() => {
          if (btn) { btn.disabled = false; btn.textContent = originalText; }
        });
    }

    // Face recognition section
    function updateFaceSection(faceInfo) {
      const faceStatus = document.getElementById("face-status");
      const faceCount = document.getElementById("face-count");
      const faceList = document.getElementById("face-list");
      const faceInstallOptions = document.getElementById("face-install-options");
      const faceInstallOpencvBtn = document.getElementById("face-install-opencv-btn");
      const faceRegisterBtn = document.getElementById("face-register-btn");
      const faceRecognizeBtn = document.getElementById("face-recognize-btn");
      if (!faceStatus) return;

      if (faceInfo && faceInfo.available) {
        faceStatus.textContent = "人脸识别可用：" + faceInfo.detail;
        faceStatus.className = "status ok";
        faceCount.textContent = "已注册 " + faceInfo.count + " 张人脸";
        if (faceInstallOptions) faceInstallOptions.style.display = "none";
        faceRegisterBtn.disabled = false;
        faceRecognizeBtn.disabled = false;
        // Load face list
        loadFaceList();
      } else {
        const detail = faceInfo?.detail || "人脸识别未安装";
        faceStatus.textContent = detail.includes("OpenCV") ? detail + "。请先安装 OpenCV。" : detail;
        faceStatus.className = "status err";
        faceCount.textContent = "";
        faceList.innerHTML = "";
        if (faceInstallOptions) faceInstallOptions.style.display = "block";
        if (faceInstallOpencvBtn) faceInstallOpencvBtn.hidden = !detail.includes("OpenCV");
        faceRegisterBtn.disabled = true;
        faceRecognizeBtn.disabled = true;
      }
    }

    function escapeSettingsText(text) {
      return String(text ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
      }[c]));
    }

    function loadFaceList() {
      fetch("/api/face/list")
        .then(r => r.json().then(data => {
          if (!r.ok || !data.ok) throw new Error(data.error || `HTTP ${r.status}`);
          return data;
        }))
        .then(data => {
          const faceList = document.getElementById("face-list");
          if (!faceList) return;
          if (data.faces && data.faces.length > 0) {
            faceList.innerHTML = data.faces.map(f =>
              '<div class="face-list-item">' +
              '<span class="face-list-name">' + escapeSettingsText(f.name) + '</span>' +
              '<span class="face-list-id">' + escapeSettingsText((f.id || '').slice(0, 12)) + '</span>' +
              '<button data-face-rename="' + escapeSettingsText(f.id) + '">改名</button>' +
              '<button class="danger" data-face-delete="' + escapeSettingsText(f.id) + '">删除</button>' +
              '</div>'
            ).join("");
            faceList.querySelectorAll("[data-face-delete]").forEach(btn => {
              btn.addEventListener("click", () => deleteFace(btn.dataset.faceDelete));
            });
            faceList.querySelectorAll("[data-face-rename]").forEach(btn => {
              btn.addEventListener("click", () => renameFace(btn.dataset.faceRename));
            });
          } else {
            faceList.innerHTML = '<div style="color:#657184">暂无注册人脸</div>';
          }
        })
        .catch(err => {
          const faceList = document.getElementById("face-list");
          if (faceList) faceList.innerHTML = '<div style="color:#c0392b">加载失败：' + escapeSettingsText(String(err).replace(/^Error:\s*/, "")) + '</div>';
        });
    }

    function deleteFace(id) {
      if (!id || !confirm("确定删除这个人脸吗？")) return;
      fetch("/api/face/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({face_id: id})
      })
        .then(r => r.json())
        .then(data => {
          const resultEl = document.getElementById("face-result");
          resultEl.textContent = data.ok ? "人脸已删除" : ("删除失败：" + (data.error || "未知错误"));
          resultEl.style.color = data.ok ? "#0b7a55" : "#c0392b";
          loadFaceList();
        })
        .catch(err => {
          const resultEl = document.getElementById("face-result");
          resultEl.textContent = "删除失败：" + err;
          resultEl.style.color = "#c0392b";
        });
    }

    function renameFace(id) {
      if (!id) return;
      const name = prompt("输入新名称：");
      if (!name || !name.trim()) return;
      fetch("/api/face/rename", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({face_id: id, name: name.trim()})
      })
        .then(r => r.json())
        .then(data => {
          const resultEl = document.getElementById("face-result");
          resultEl.textContent = data.ok ? "人脸名称已更新" : ("改名失败：" + (data.error || "未知错误"));
          resultEl.style.color = data.ok ? "#0b7a55" : "#c0392b";
          loadFaceList();
        })
        .catch(err => {
          const resultEl = document.getElementById("face-result");
          resultEl.textContent = "改名失败：" + err;
          resultEl.style.color = "#c0392b";
        });
    }

    async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 26000) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const resp = await fetch(url, {...options, signal: controller.signal});
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(data.error || `HTTP ${resp.status}`);
        }
        return data;
      } catch (err) {
        if (err && err.name === "AbortError") {
          throw new Error("请求超时，请确认摄像头未被其他程序占用后重试");
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }

    async function registerFace() {
      const nameInput = document.getElementById("face-register-name");
      const resultEl = document.getElementById("face-result");
      const registerBtn = document.getElementById("face-register-btn");
      const recognizeBtn = document.getElementById("face-recognize-btn");
      const name = nameInput.value.trim();
      if (!name) {
        resultEl.textContent = "请输入人脸名称";
        resultEl.style.color = "#c0392b";
        return;
      }
      if (registerBtn) { registerBtn.disabled = true; registerBtn.textContent = "注册中…"; }
      if (recognizeBtn) recognizeBtn.disabled = true;
      resultEl.textContent = "正在从摄像头注册人脸…";
      resultEl.style.color = "#657184";
      try {
        const data = await fetchJsonWithTimeout("/api/face/register", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({name: name})
        }, 28000);
        if (data.ok) {
          resultEl.textContent = "注册成功：" + data.name + " (ID: " + (data.face_id || '').slice(0, 12) + ")";
          resultEl.style.color = "#0b7a55";
          nameInput.value = "";
          loadFaceList();
          document.getElementById("face-count").textContent = "已注册人脸已更新";
        } else {
          resultEl.textContent = "注册失败：" + (data.message || data.error || "未知错误");
          resultEl.style.color = "#c0392b";
        }
      } catch (err) {
        resultEl.textContent = "注册失败：" + String(err).replace(/^Error:\s*/, "");
        resultEl.style.color = "#c0392b";
      } finally {
        if (registerBtn) { registerBtn.disabled = false; registerBtn.textContent = "从摄像头注册"; }
        if (recognizeBtn) recognizeBtn.disabled = false;
      }
    }

    async function recognizeFaces() {
      const resultEl = document.getElementById("face-result");
      const registerBtn = document.getElementById("face-register-btn");
      const recognizeBtn = document.getElementById("face-recognize-btn");
      if (recognizeBtn) { recognizeBtn.disabled = true; recognizeBtn.textContent = "识别中…"; }
      if (registerBtn) registerBtn.disabled = true;
      resultEl.textContent = "正在识别人脸…";
      resultEl.style.color = "#657184";
      try {
        const data = await fetchJsonWithTimeout("/api/face/recognize", {}, 24000);
        if (data.ok) {
          const faces = data.faces || [];
          if (faces.length === 0) {
            resultEl.textContent = data.message || "摄像头中未检测到人脸";
            resultEl.style.color = "#657184";
          } else {
            const known = faces.filter(f => f.known);
            const unknown = faces.filter(f => !f.known);
            let text = "识别到 " + faces.length + " 张人脸";
            if (known.length > 0) {
              text += "，已知：" + known.map(f => f.name + " (" + (f.confidence || 0).toFixed(2) + ")").join(", ");
            }
            if (unknown.length > 0) {
              text += "，未知：" + unknown.length + " 张";
            }
            if (data.identity_confirmed) {
              text += "；当前身份已确认：" + data.identity_confirmed.name;
              loadIdentityConfirmation();
            }
            resultEl.textContent = text;
            resultEl.style.color = "#243143";
          }
        } else {
          resultEl.textContent = "识别失败：" + (data.message || data.error || "未知错误");
          resultEl.style.color = "#c0392b";
        }
      } catch (err) {
        resultEl.textContent = "识别失败：" + String(err).replace(/^Error:\s*/, "");
        resultEl.style.color = "#c0392b";
      } finally {
        if (recognizeBtn) { recognizeBtn.disabled = false; recognizeBtn.textContent = "识别摄像头人脸"; }
        if (registerBtn) registerBtn.disabled = false;
      }
    }

    function showFaceLog() {
      const resultEl = document.getElementById("face-result");
      resultEl.textContent = "正在加载日志…";
      resultEl.style.color = "#657184";
      fetch("/api/face/log")
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.logs && data.logs.length > 0) {
            const lines = data.logs.slice(-10).map(log => {
              const time = log.time ? log.time.slice(5, 16) : "";
              if (log.type === "recognize") {
                const names = log.names || [];
                return "[" + time + "] 识别：" + log.total + " 张，已知 " + log.known + " (" + (names.join(", ") || "无") + ")";
              } else if (log.type === "register") {
                return "[" + time + "] 注册：" + log.name;
              } else {
                return "[" + time + "] " + log.type;
              }
            });
            resultEl.innerHTML = '<div style="max-height:150px;overflow-y:auto">' + lines.map(l => '<div>' + l + '</div>').join("") + '</div>';
            resultEl.style.color = "#243143";
          } else {
            resultEl.textContent = "日志为空";
            resultEl.style.color = "#657184";
          }
        })
        .catch(err => {
          resultEl.textContent = "加载失败：" + err;
          resultEl.style.color = "#c0392b";
        });
    }

    function _faceInstallFetch(url, label, btnId) {
      const resultEl = document.getElementById("face-result");
      const btn = document.getElementById(btnId);
      if (btn) { btn.disabled = true; btn.textContent = "安装中…"; }
      resultEl.textContent = "正在" + label + "（可能需要几分钟）…";
      resultEl.style.color = "#657184";
      fetch(url)
        .then(r => r.json())
        .then(data => {
          resultEl.textContent = data.message || (data.ok ? "安装完成" : " 安装失败：" + (data.error || "未知错误"));
          resultEl.style.color = data.ok ? "#0b7a55" : "#c0392b";
          if (btn) { btn.disabled = false; btn.textContent = label; }
          if (data.ok) {
            // 安装成功后刷新设置状态
            setTimeout(() => loadSettings(), 500);
          }
        })
        .catch(err => {
          resultEl.textContent = "" + label + "失败：" + err;
          resultEl.style.color = "#c0392b";
          if (btn) { btn.disabled = false; btn.textContent = label; }
        });
    }

    function installFaceDeps() {
      _faceInstallFetch("/api/face/install", "安装人脸识别依赖", "face-install-all-btn");
    }

    function installCmakeOnly() {
      _faceInstallFetch("/api/face/install_cmake", "安装 CMake", "face-install-cmake-btn");
    }

    function installDlibOnly() {
      _faceInstallFetch("/api/face/install_dlib", "安装 dlib", "face-install-dlib-btn");
    }

    function installVsBuildTools() {
      const btn = document.getElementById("face-install-vs-btn");
      const originalText = btn?.textContent || "下载 VS Build Tools";
      if (btn) { btn.disabled = true; btn.textContent = "下载中…"; }
      const resultDiv = document.getElementById("face-result");
      if (resultDiv) { resultDiv.textContent = "正在下载 VS Build Tools 安装器…"; }
      fetch("/api/face/install_vs_build_tools")
        .then(r => r.json())
        .then(data => {
          if (resultDiv) {
            resultDiv.textContent = data.message || data.error || JSON.stringify(data);
            resultDiv.style.color = data.ok ? "#276ef1" : "#e74c3c";
          }
        })
        .catch(err => {
          if (resultDiv) { resultDiv.textContent = "请求失败：" + err; resultDiv.style.color = "#e74c3c"; }
        })
        .finally(() => {
          if (btn) { btn.disabled = false; btn.textContent = originalText; }
        });
    }

    function cameraCommand() {
      const input = document.getElementById("camera-index");
      const idx = Math.max(0, parseInt(input?.value || "0", 10) || 0);
      return "/camera " + idx;
    }

    function sendCameraObservation(closeSettings = false) {
      message.value = cameraCommand();
      if (closeSettings) settingsOverlay.classList.remove("open");
      sendChat();
    }

    function renderGrowthBenchmarks(items) {
      const list = document.getElementById("growth-benchmark-list");
      list.innerHTML = "";
      if (!items.length) {
        list.textContent = "暂无评测题。先添加 1 条题目，候选模型才允许激活。";
        return;
      }
      items.forEach(item => {
        const row = document.createElement("div");
        row.className = "voiceprint-item";
        const text = document.createElement("span");
        text.textContent = `${item.prompt}（${item.rule || "keywords"}：${(item.expected_keywords || []).join("、") || "人工确认"}）`;
        const edit = document.createElement("button");
        edit.type = "button";
        edit.textContent = "修改";
        edit.addEventListener("click", async () => {
          const prompt = window.prompt("评测问题", item.prompt || "");
          if (prompt === null) return;
          const keywords = window.prompt("必须出现的关键词（逗号分隔）", (item.expected_keywords || []).join(","));
          if (keywords === null) return;
          const rule = window.prompt("规则：keywords / regex / exact / max_length / manual", item.rule || "keywords");
          if (rule === null) return;
          const manual_pass = rule === "manual" ? confirm("此题当前是否手动确认通过？") : undefined;
          const resp = await fetch("/api/settings/growth", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({action:"update_benchmark", id:item.id, prompt, keywords, rule, manual_pass})});
          const data = await resp.json();
          if (!data.ok) alert(data.error || "更新失败");
          loadLocalGrowthSettings();
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "danger";
        remove.textContent = "删除";
        remove.addEventListener("click", async () => {
          remove.disabled = true;
          const resp = await fetch("/api/settings/growth", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({action:"remove_benchmark", id:item.id})});
          const data = await resp.json();
          if (!data.ok) alert(data.error || "删除失败");
          loadLocalGrowthSettings();
        });
        row.append(text, edit, remove);
        list.appendChild(row);
      });
    }

    function loadLocalGrowthSettings() {
      fetch("/api/settings/growth").then(r => r.json()).then(data => {
        if (!data.ok) throw new Error(data.error || "读取失败");
        const growth = data.growth || {};
        const image = data.image || {};
        document.getElementById("growth-experience-count").textContent = `${growth.eligible_experiences || 0} 条可训练经验`;
        document.getElementById("growth-replay-count").textContent = `${growth.replay_samples || 0} 条回放 / ${growth.held_out_samples || 0} 条留出`;
        document.getElementById("growth-active-version").textContent = growth.active_version || "未激活";
        document.getElementById("growth-image-status").textContent = `生成 ${image.generated || 0} · 采用 ${image.accepted || 0}`;
        const backend = data.image_backend || {};
        document.getElementById("growth-comfy-enabled").checked = !!backend.enabled;
        document.getElementById("growth-comfy-endpoint").value = backend.endpoint || "http://127.0.0.1:8188";
        document.getElementById("growth-comfy-workflow").value = backend.workflow_path || "";
        document.getElementById("growth-comfy-prompt-node").value = backend.prompt_node_id || "";
        document.getElementById("growth-comfy-negative-node").value = backend.negative_prompt_node_id || "";
        document.getElementById("growth-comfy-seed-node").value = backend.seed_node_id || "";
        document.getElementById("growth-image-backend-status").textContent = backend.message || "内置心情卡片正在使用。";
        document.getElementById("local-growth-status").textContent = `固定评测题 ${data.benchmarks.length} 条；未通过候选 ${growth.rejected_candidates || 0} 个`;
        document.getElementById("local-growth-status").className = "status ok";
        renderGrowthBenchmarks(data.benchmarks || []);
        renderGrowthVersions(data.versions || []);
        renderGrowthExperiences(data.experiences || []);
        renderGrowthRecipes(data.recipes || []);
        const job = data.training_job || {};
        document.getElementById("growth-training-job").textContent = `${job.state || "idle"} · ${job.stage || ""} · ${job.progress ?? 0}%：${job.message || "暂无训练任务"}`;
        if (["queued", "training"].includes(job.state)) setTimeout(loadLocalGrowthSettings, 2000);
      }).catch(err => {
        const status = document.getElementById("local-growth-status");
        status.textContent = "加载本地成长状态失败：" + err;
        status.className = "status err";
      });
    }

    async function growthPost(payload) {
      const resp = await fetch("/api/settings/growth", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "操作失败");
      loadLocalGrowthSettings();
      return data;
    }

    function renderGrowthVersions(items) {
      const list = document.getElementById("growth-version-list"); list.innerHTML = "";
      if (!items.length) { list.textContent = "暂无已登记模型版本。"; return; }
      items.forEach(item => {
        const row = document.createElement("div"); row.className = "voiceprint-item";
        const text = document.createElement("span");
        text.textContent = `${item.active ? "当前 · " : ""}${item.id}｜训练 ${item.train_samples || "?"} 条｜评测 ${item.benchmark_score ?? "?"}/${item.benchmark_total ?? "?"}｜${item.status || "archived"}`;
        row.appendChild(text);
        if (!item.active && item.status !== "rejected") {
          const button = document.createElement("button"); button.textContent = "恢复";
          button.addEventListener("click", () => growthPost({action:"activate_version", id:item.id}).catch(err => alert(err)));
          row.appendChild(button);
        }
        list.appendChild(row);
      });
    }

    function renderGrowthExperiences(items) {
      const list = document.getElementById("growth-experience-list"); list.innerHTML = "";
      if (!items.length) { list.textContent = "暂无经验。"; return; }
      items.slice(0, 12).forEach(item => {
        const row = document.createElement("div"); row.className = "voiceprint-item";
        const text = document.createElement("span"); text.textContent = `${item.verified ? "✓" : "○"} ${item.prompt || ""}（${item.source || "local"}，奖励 ${item.reward ?? 0}）`;
        const toggle = document.createElement("button"); toggle.textContent = item.verified ? "停用" : "批准";
        toggle.addEventListener("click", () => growthPost({action:"update_experience", id:item.id, verified:!item.verified, reward:item.verified ? 0 : 1}).catch(err => alert(err)));
        const remove = document.createElement("button"); remove.className = "danger"; remove.textContent = "删除";
        remove.addEventListener("click", () => { if (confirm("删除这条经验？")) growthPost({action:"delete_experience", id:item.id}).catch(err => alert(err)); });
        row.append(text, toggle, remove); list.appendChild(row);
      });
    }

    function renderGrowthRecipes(items) {
      const list = document.getElementById("growth-recipe-list"); list.innerHTML = "";
      if (!items.length) { list.textContent = "暂无生成配方。"; return; }
      items.slice(0, 12).forEach(item => {
        const row = document.createElement("div"); row.className = "voiceprint-item";
        const text = document.createElement("span"); text.textContent = `${item.mood || "未标注"}｜${item.feedback || "pending"}｜${item.kind || "image"}`;
        ["accepted", "too_bright", "too_dark", "simpler", "rejected"].forEach(label => {
          const button = document.createElement("button"); button.textContent = label;
          button.addEventListener("click", () => growthPost({action:"image_feedback", path:item.path, feedback:label}).catch(err => alert(err)));
          row.appendChild(button);
        });
        row.prepend(text); list.appendChild(row);
      });
    }

    function loadRuntimeBehaviorSettings() {
      fetch("/api/settings/runtime").then(r => r.json()).then(data => {
        if (!data.ok) throw new Error(data.error || "读取失败");
        const cfg = data.dream || {};
        const state = data.status || {};
        document.getElementById("runtime-dream-enabled").checked = !!cfg.enabled;
        document.getElementById("runtime-autostart").checked = !!data.autostart;
        document.getElementById("runtime-system-idle").value = cfg.system_idle_threshold_seconds || 60;
        document.getElementById("runtime-chat-idle").value = cfg.chat_idle_threshold_seconds || 30;
        document.getElementById("runtime-review-interval").value = cfg.review_interval_hours || 4;
        document.getElementById("runtime-heavy-idle").value = Math.round((cfg.heavy_task_system_idle_min || 300) / 60);
        document.getElementById("runtime-quiet-hours").value = (cfg.quiet_hours || []).join(",");
        const idle = state.idle || {};
        const status = document.getElementById("runtime-behavior-status");
        status.textContent = `梦境引擎${state.running ? "运行中" : "待命"} · 系统空闲 ${Math.round(idle.sys_idle_sec || 0)} 秒 · 聊天空闲 ${Math.round(idle.chat_idle_sec || 0)} 秒`;
        status.className = "status ok";
      }).catch(err => {
        const status = document.getElementById("runtime-behavior-status");
        status.textContent = "加载后台设置失败：" + err;
        status.className = "status err";
      });
    }

    async function runtimeAction(payload, statusText) {
      const status = document.getElementById("runtime-behavior-status");
      status.textContent = statusText;
      status.className = "status";
      try {
        const resp = await fetch("/api/settings/runtime", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "操作失败");
        status.textContent = data.message || "已完成";
        status.className = "status ok";
        loadRuntimeBehaviorSettings();
      } catch (err) {
        status.textContent = "操作失败：" + err;
        status.className = "status err";
      }
    }

    document.getElementById("growth-refresh-btn").addEventListener("click", loadLocalGrowthSettings);
    document.getElementById("growth-benchmark-add-btn").addEventListener("click", async () => {
      const prompt = document.getElementById("growth-benchmark-prompt").value.trim();
      const keywords = document.getElementById("growth-benchmark-keywords").value.trim();
      const rule = document.getElementById("growth-benchmark-rule").value;
      if (!prompt || (!keywords && rule !== "manual")) { alert("请填写问题和期望值；人工确认题可不填期望值。"); return; }
      const resp = await fetch("/api/settings/growth", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({action:"add_benchmark", prompt, keywords, rule})});
      const data = await resp.json();
      if (!data.ok) { alert(data.error || "添加失败"); return; }
      document.getElementById("growth-benchmark-prompt").value = "";
      document.getElementById("growth-benchmark-keywords").value = "";
      loadLocalGrowthSettings();
    });
    document.getElementById("growth-rollback-btn").addEventListener("click", async () => {
      if (!confirm("回滚到上一版 TinyLLM？")) return;
      const resp = await fetch("/api/settings/growth", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({action:"rollback"})});
      const data = await resp.json();
      if (!data.ok) alert(data.error || "回滚失败");
      loadLocalGrowthSettings();
    });
    document.getElementById("growth-training-start-btn").addEventListener("click", () => growthPost({action:"start_training", epochs:3}).catch(err => alert(err)));
    document.getElementById("growth-training-cancel-btn").addEventListener("click", () => growthPost({action:"cancel_training"}).catch(err => alert(err)));
    document.getElementById("growth-calibration-add-btn").addEventListener("click", () => {
      const prompt = document.getElementById("growth-calibration-prompt").value.trim();
      const response = document.getElementById("growth-calibration-response").value.trim();
      if (!prompt || !response) { alert("请填写实际问题和你认可的回答。"); return; }
      growthPost({action:"add_calibration", prompt, response}).then(() => {
        document.getElementById("growth-calibration-prompt").value = "";
        document.getElementById("growth-calibration-response").value = "";
      }).catch(err => alert(err));
    });
    document.getElementById("growth-comfy-save-btn").addEventListener("click", async () => {
      try {
        const data = await growthPost({action:"save_image_backend", backend:"comfyui", enabled:document.getElementById("growth-comfy-enabled").checked, endpoint:document.getElementById("growth-comfy-endpoint").value.trim(), workflow_path:document.getElementById("growth-comfy-workflow").value.trim(), prompt_node_id:document.getElementById("growth-comfy-prompt-node").value.trim(), negative_prompt_node_id:document.getElementById("growth-comfy-negative-node").value.trim(), seed_node_id:document.getElementById("growth-comfy-seed-node").value.trim()});
        alert(data.message || "已保存");
      } catch (err) { alert(err); }
    });
    document.getElementById("diagnostics-export-btn").addEventListener("click", async () => {
      const out = document.getElementById("diagnostics-result"); out.textContent = "正在导出不含聊天内容和密钥的诊断包…";
      try {
        const resp = await fetch("/api/settings/diagnostics", {method:"POST"}); const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "导出失败"); out.textContent = `诊断包已导出：${data.path}`;
      } catch (err) { out.textContent = "诊断包导出失败：" + err; }
    });
    document.getElementById("runtime-save-btn").addEventListener("click", () => {
      const quietHours = document.getElementById("runtime-quiet-hours").value.split(",").map(x => Number(x.trim())).filter(x => Number.isInteger(x) && x >= 0 && x <= 23);
      runtimeAction({
        action:"save", dream_enabled:document.getElementById("runtime-dream-enabled").checked,
        autostart:document.getElementById("runtime-autostart").checked,
        system_idle_threshold_seconds:Number(document.getElementById("runtime-system-idle").value),
        chat_idle_threshold_seconds:Number(document.getElementById("runtime-chat-idle").value),
        review_interval_hours:Number(document.getElementById("runtime-review-interval").value),
        heavy_task_idle_minutes:Number(document.getElementById("runtime-heavy-idle").value), quiet_hours:quietHours,
      }, "正在保存后台设置…");
    });
    document.getElementById("runtime-review-btn").addEventListener("click", () => runtimeAction({action:"review_now"}, "正在整理记忆…"));
    document.getElementById("runtime-practice-btn").addEventListener("click", () => runtimeAction({action:"practice_now"}, "正在进行代码练习…"));

    // Save audit config
    document.getElementById("audit-save-btn").addEventListener("click", () => {
      const btn = document.getElementById("audit-save-btn");
      const statusEl = document.getElementById("audit-status");
      btn.disabled = true;
      btn.textContent = "保存中…";
      const payload = {
        enabled: document.getElementById("audit-enabled").checked,
        use_cloud_audit: document.getElementById("audit-use-cloud").checked,
        auto_suggest_corrections: document.getElementById("audit-auto-suggest").checked,
        api_base: document.getElementById("audit-api-base").value.trim(),
        model: document.getElementById("audit-model").value.trim(),
        language: document.getElementById("audit-language").value,
        batch_size: parseInt(document.getElementById("audit-batch-size").value) || 5,
        audit_interval: parseInt(document.getElementById("audit-interval").value) || 10,
        max_context_turns: parseInt(document.getElementById("audit-context-turns").value) || 6,
      };
      const auditApiKey = document.getElementById("audit-api-key").value.trim();
      if (auditApiKey) payload.api_key = auditApiKey;
      fetch("/api/settings/audit", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(payload)})
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            statusEl.textContent = "配置已保存";
            statusEl.className = "status ok";
            btn.textContent = "保存配置";
            btn.disabled = false;
            loadSettings();
          } else {
            statusEl.textContent = "保存失败: " + (data.error || "未知错误");
            statusEl.className = "status err";
            btn.textContent = "保存配置";
            btn.disabled = false;
          }
        })
        .catch(err => {
          statusEl.textContent = "保存失败: " + err;
          statusEl.className = "status err";
          btn.textContent = "保存配置";
          btn.disabled = false;
        });
    });

    function remoteLlmPayload() {
      const apiKey = document.getElementById("remote-llm-api-key").value.trim();
      const payload = {
        enabled: document.getElementById("remote-llm-enabled").checked,
        enabled_for_hybrid: document.getElementById("remote-llm-hybrid").checked,
        reasoning_enabled: document.getElementById("remote-llm-reasoning-enabled").checked,
        reasoning_effort: document.getElementById("remote-llm-reasoning-effort").value,
        api_base: document.getElementById("remote-llm-api-base").value.trim(),
        model: document.getElementById("remote-llm-model").value.trim(),
        temperature: parseFloat(document.getElementById("remote-llm-temperature").value) || 0.7,
        max_tokens: parseInt(document.getElementById("remote-llm-max-tokens").value) || 1024,
        timeout: parseInt(document.getElementById("remote-llm-timeout").value) || 45,
        user_prompt: document.getElementById("remote-llm-user-prompt").value.trim(),
      };
      if (apiKey) payload.api_key = apiKey;
      return payload;
    }

    document.getElementById("tiny-llm-deep-reply").addEventListener("change", event => {
      fetch("/api/settings/tiny_llm", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({enabled: event.target.checked})})
        .then(r => r.json()).then(data => {
          if (!data.ok) throw new Error(data.error || "未知错误");
        }).catch(() => {
          event.target.checked = !event.target.checked;
          document.getElementById("chat-mode-status").textContent = "保存 TinyLLM 设置失败";
          document.getElementById("chat-mode-status").className = "status err";
        });
    });

    const modelDiscoveryTimers = {};
    const modelDiscoveryFields = {
      audit: {
        apiBase: "audit-api-base",
        apiKey: "audit-api-key",
        model: "audit-model",
        options: "audit-model-options",
        status: "audit-model-discovery",
      },
      remote_llm: {
        apiBase: "remote-llm-api-base",
        apiKey: "remote-llm-api-key",
        model: "remote-llm-model",
        options: "remote-llm-model-options",
        status: "remote-llm-model-discovery",
      },
    };

    function scheduleModelDiscovery(scope, delay = 600, useSavedKey = false) {
      const fields = modelDiscoveryFields[scope];
      if (!fields) return;
      clearTimeout(modelDiscoveryTimers[scope]);
      modelDiscoveryTimers[scope] = setTimeout(() => discoverModels(scope, useSavedKey), delay);
    }

    function discoverModels(scope, useSavedKey = false) {
      const fields = modelDiscoveryFields[scope];
      if (!fields) return;
      const apiBaseEl = document.getElementById(fields.apiBase);
      const apiKeyEl = document.getElementById(fields.apiKey);
      const modelEl = document.getElementById(fields.model);
      const optionsEl = document.getElementById(fields.options);
      const statusEl = document.getElementById(fields.status);
      const apiBase = apiBaseEl?.value.trim() || "";
      const apiKey = apiKeyEl?.value.trim() || "";
      if (!apiBase || (!apiKey && !useSavedKey)) {
        if (statusEl) statusEl.textContent = "填写 API Base 和 Key 后自动获取模型。";
        return;
      }
      if (statusEl) statusEl.textContent = "正在获取模型…";
      fetch("/api/settings/models", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({scope, api_base: apiBase, api_key: apiKey, use_saved_key: useSavedKey}),
      })
        .then(r => r.json())
        .then(data => {
          if (!data.ok) throw new Error(data.error || "获取失败");
          const models = Array.isArray(data.models) ? data.models : [];
          if (optionsEl) {
            optionsEl.replaceChildren(...models.map(model => {
              const option = document.createElement("option");
              option.value = model;
              return option;
            }));
          }
          if (modelEl && models.length && (!modelEl.value.trim() || modelEl.value.trim() === "gpt-4o-mini")) {
            modelEl.value = models[0];
          }
          if (statusEl) statusEl.textContent = `已获取 ${models.length} 个模型。`;
        })
        .catch(err => {
          if (statusEl) {
            const message = String(err).replace(/^Error:\\s*/, "");
            statusEl.textContent = "获取模型失败：" + message;
            statusEl.className = "settings-note err";
          }
        });
    }

    ["audit", "remote_llm"].forEach(scope => {
      const fields = modelDiscoveryFields[scope];
      [fields.apiBase, fields.apiKey].forEach(id => {
        document.getElementById(id)?.addEventListener("input", () => scheduleModelDiscovery(scope));
        document.getElementById(id)?.addEventListener("change", () => scheduleModelDiscovery(scope, 0));
      });
    });

    document.getElementById("remote-llm-save-btn").addEventListener("click", () => {
      const btn = document.getElementById("remote-llm-save-btn");
      const statusEl = document.getElementById("remote-llm-status");
      btn.disabled = true;
      btn.textContent = "保存中…";
      const payload = remoteLlmPayload();
      fetch("/api/settings/remote_llm", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(payload)})
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            statusEl.textContent = data.ready ? " 大模型接口配置已保存并可用" : "配置已保存，但尚未启用或缺少 API Key";
            statusEl.className = data.ready ? "status ok" : "status";
            document.getElementById("remote-llm-api-key").value = "";
            btn.textContent = "保存接口配置";
            btn.disabled = false;
            loadSettings();
          } else {
            statusEl.textContent = "保存失败: " + (data.error || "未知错误");
            statusEl.className = "status err";
            btn.textContent = "保存接口配置";
            btn.disabled = false;
          }
        })
        .catch(err => {
          statusEl.textContent = "保存失败: " + err;
          statusEl.className = "status err";
          btn.textContent = "保存接口配置";
          btn.disabled = false;
        });
    });

    document.getElementById("remote-llm-test-btn").addEventListener("click", () => {
      const btn = document.getElementById("remote-llm-test-btn");
      const statusEl = document.getElementById("remote-llm-status");
      btn.disabled = true;
      btn.textContent = "测试中…";
      fetch("/api/settings/remote_llm/test", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(remoteLlmPayload())})
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            statusEl.textContent = `连接测试成功 (${data.latency_ms || 0} ms)：${data.reply || ""}`;
            statusEl.className = "status ok";
          } else {
            statusEl.textContent = "连接测试失败：" + (data.error || "未知错误");
            statusEl.className = "status err";
          }
        })
        .catch(err => {
          statusEl.textContent = "连接测试失败：" + err;
          statusEl.className = "status err";
        })
        .finally(() => {
          btn.textContent = "测试连接";
          btn.disabled = false;
        });
    });

    document.getElementById("remote-llm-mode-btn").addEventListener("click", () => {
      message.value = "/chat_mode api_llm";
      settingsOverlay.classList.remove("open");
      sendChat();
    });

    document.getElementById("chat-mode-save-btn").addEventListener("click", () => {
      const button = document.getElementById("chat-mode-save-btn");
      const statusEl = document.getElementById("chat-mode-status");
      const mode = document.getElementById("chat-mode-select").value;
      if (!mode) return;
      button.disabled = true;
      fetch("/api/chat/mode", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode}),
      }).then(r => r.json()).then(data => {
        if (!data.ok) throw new Error(data.error || "切换失败");
        statusEl.textContent = "已切换到：" + (data.name || mode);
        statusEl.className = "status ok";
        loadSettings();
      }).catch(err => {
        statusEl.textContent = "切换失败：" + String(err).replace(/^Error:\\s*/, "");
        statusEl.className = "status err";
      }).finally(() => {
        button.disabled = false;
      });
    });

    // TTS 滑块实时更新
    document.getElementById("tts-rate").addEventListener("input", (e) => {
      const val = parseInt(e.target.value) || 0;
      document.getElementById("tts-rate-value").textContent = (val >= 0 ? "+" : "") + val + "%";
    });
    document.getElementById("tts-pitch").addEventListener("input", (e) => {
      const val = parseInt(e.target.value) || 0;
      document.getElementById("tts-pitch-value").textContent = (val >= 0 ? "+" : "") + val + "Hz";
    });
    document.getElementById("tts-volume").addEventListener("input", (e) => {
      const val = parseInt(e.target.value) || 0;
      document.getElementById("tts-volume-value").textContent = (val >= 0 ? "+" : "") + val + "%";
    });

    // 保存 TTS 配置
    document.getElementById("tts-save-btn").addEventListener("click", () => {
      const btn = document.getElementById("tts-save-btn");
      const statusEl = document.getElementById("tts-status");
      btn.disabled = true;
      btn.textContent = "保存中…";
      
      const rate = parseInt(document.getElementById("tts-rate").value) || 0;
      const pitch = parseInt(document.getElementById("tts-pitch").value) || 0;
      const volume = parseInt(document.getElementById("tts-volume").value) || 0;
      
      const payload = {
        enabled: document.getElementById("tts-enabled").checked,
        auto_play: document.getElementById("tts-auto-play").checked,
        voice: document.getElementById("tts-voice").value,
        rate: (rate >= 0 ? "+" : "") + rate + "%",
        pitch: (pitch >= 0 ? "+" : "") + pitch + "Hz",
        volume: (volume >= 0 ? "+" : "") + volume + "%",
      };
      
      fetch("/api/tts/config", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(payload)})
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            ttsConfig = data.config;
            statusEl.textContent = "配置已保存";
            statusEl.className = "status ok";
            btn.textContent = "保存设置";
            btn.disabled = false;
            loadSettings();
          } else {
            statusEl.textContent = "保存失败: " + (data.error || "未知错误");
            statusEl.className = "status err";
            btn.textContent = "保存设置";
            btn.disabled = false;
          }
        })
        .catch(err => {
          statusEl.textContent = "保存失败: " + err;
          statusEl.className = "status err";
          btn.textContent = "保存设置";
          btn.disabled = false;
        });
    });

    // 清空 TTS 缓存
    document.getElementById("tts-clear-cache-btn").addEventListener("click", () => {
      const btn = document.getElementById("tts-clear-cache-btn");
      const statusEl = document.getElementById("tts-status");
      btn.disabled = true;
      btn.textContent = "清空中…";
      
      fetch("/api/tts/clear_cache", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({})})
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            statusEl.textContent = ` 已清空 ${data.cleared} 个缓存文件`;
            statusEl.className = "status ok";
            btn.textContent = "清空缓存";
            btn.disabled = false;
            loadSettings();
          } else {
            statusEl.textContent = "清空失败: " + (data.error || "未知错误");
            statusEl.className = "status err";
            btn.textContent = "清空缓存";
            btn.disabled = false;
          }
        })
        .catch(err => {
          statusEl.textContent = "清空失败: " + err;
          statusEl.className = "status err";
          btn.textContent = "清空缓存";
          btn.disabled = false;
        });
    });

    // TTS 试听
    document.getElementById("tts-test-btn").addEventListener("click", () => {
      const btn = document.getElementById("tts-test-btn");
      const statusEl = document.getElementById("tts-status");
      if (currentAudio && currentAudioControl === btn) {
        const willPause = !currentAudio.paused;
        playAudioUrl(currentAudioUrl, btn, "试听");
        statusEl.textContent = willPause ? "已暂停试听" : " 正在播放试听";
        statusEl.className = "status ok";
        return;
      }
      btn.disabled = true;
      btn.textContent = "生成中…";
      
      const rate = parseInt(document.getElementById("tts-rate").value) || 0;
      const pitch = parseInt(document.getElementById("tts-pitch").value) || 0;
      const volume = parseInt(document.getElementById("tts-volume").value) || 0;
      
      const payload = {
        text: "你好，我是你的 AI 伙伴。这是语音合成测试。",
        voice: document.getElementById("tts-voice").value,
        rate: (rate >= 0 ? "+" : "") + rate + "%",
        pitch: (pitch >= 0 ? "+" : "") + pitch + "Hz",
        volume: (volume >= 0 ? "+" : "") + volume + "%",
      };
      
      fetch("/api/tts/synthesize", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(payload)})
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.url) {
            statusEl.textContent = "正在播放试听";
            statusEl.className = "status ok";
            btn.disabled = false;
            btn.dataset.defaultLabel = "试听";
            btn.dataset.defaultTitle = "试听";
            playAudioUrl(data.url, btn, "试听");
          } else {
            statusEl.textContent = "生成失败: " + (data.error || "未知错误");
            statusEl.className = "status err";
            btn.textContent = "试听";
            btn.disabled = false;
          }
        })
        .catch(err => {
          statusEl.textContent = "生成失败: " + err;
          statusEl.className = "status err";
          btn.textContent = "试听";
          btn.disabled = false;
        });
    });

    document.getElementById("voiceprint-enroll-btn").addEventListener("click", enrollVoiceprint);
    document.getElementById("voiceprint-recognize-btn").addEventListener("click", recognizeVoiceprint);
    document.getElementById("voiceprint-refresh-btn").addEventListener("click", loadVoiceprints);
    document.getElementById("identity-confirm-refresh-btn").addEventListener("click", loadIdentityConfirmation);
    document.getElementById("identity-confirm-clear-btn").addEventListener("click", clearIdentityConfirmation);

    function installComponent(name) {
      const btn = document.getElementById(name + "-install-btn");
      const status = document.getElementById(name + "-status");
      btn.disabled = true;
      btn.textContent = "安装中…";
      status.textContent = "正在安装，请稍候…";
      status.className = "status loading";

      const progress = ensureComponentProgress(name);
      progress.classList.remove("ok", "err");
      progress.classList.add("open", "installing");
      progress.querySelector(".component-progress-bar").style.width = "";
      progress.querySelector(".component-progress-text").textContent = "正在安装…";

      const payload = {component: name};
      if (name === "torch") {
        const versionSelect = document.getElementById("torch-version");
        if (versionSelect) {
          payload.version = versionSelect.value;
        }
      }

      fetch("/api/settings/install", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(payload)})
        .then(r => r.json())
        .then(data => {
          progress.classList.remove("installing");
          if (data.success) {
            showComponentProgress(progress, 100, "安装完成", "ok");
            status.textContent = "" + data.detail;
            status.className = "status ok";
            btn.disabled = false;
            btn.textContent = btn.dataset.label;
            loadSettings();
          } else if (data.python_download_url) {
            showComponentProgress(progress, 100, "安装失败", "err");
            status.innerHTML = " " + (data.detail || "未检测到 Python").replace(/\n/g, "<br>")
              + ' <a href="' + data.python_download_url + '" target="_blank" rel="noopener" style="color:#3498db;text-decoration:underline">前往下载 Python</a>';
            status.className = "status err";
            btn.disabled = false;
            btn.textContent = btn.dataset.label;
          } else {
            showComponentProgress(progress, 100, "安装失败", "err");
            status.textContent = "安装失败: " + (data.detail || "未知错误");
            status.className = "status err";
            btn.disabled = false;
            btn.textContent = btn.dataset.label;
          }
          setTimeout(() => { progress.classList.remove("open"); }, 4000);
        })
        .catch(err => {
          progress.classList.remove("installing");
          showComponentProgress(progress, 100, "安装失败", "err");
          status.textContent = "安装失败: " + err;
          status.className = "status err";
          btn.disabled = false;
          btn.textContent = btn.dataset.label;
          setTimeout(() => { progress.classList.remove("open"); }, 4000);
        });
    }

    document.getElementById("ocr-install-btn").addEventListener("click", () => installComponent("ocr"));
    document.getElementById("torch-install-btn").addEventListener("click", () => installComponent("torch"));
    document.getElementById("torch-dx12-train-btn")?.addEventListener("click", () => {
      const btn = document.getElementById("torch-dx12-train-btn");
      const status = document.getElementById("torch-dx12-status");
      if (!btn || !status) return;
      const label = btn.textContent;
      btn.disabled = true;
      btn.textContent = "DX12 训练中…";
      status.textContent = "正在使用 DirectX 12 (DirectML) 训练内置动作模型…";
      status.className = "settings-note";
      fetch("/api/neural/train", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({backend: "directml"}),
      })
        .then(r => r.json())
        .then(data => {
          if (!data.ok) throw new Error(data.error || "训练失败");
          status.textContent = `DX12 训练完成：${data.examples || 0} 条样本，loss ${data.loss ?? "-"}`;
          status.className = "settings-note status ok";
        })
        .catch(err => {
          status.textContent = "DX12 训练失败：" + String(err).replace(/^Error:\\s*/, "");
          status.className = "settings-note status err";
        })
        .finally(() => {
          btn.textContent = label;
          loadSettings();
        });
    });
    document.getElementById("zluda-install-btn").addEventListener("click", () => installComponent("zluda"));
    document.getElementById("opencv-install-btn").addEventListener("click", () => installComponent("opencv"));
    document.getElementById("datasets-install-btn").addEventListener("click", () => installComponent("datasets"));
    document.getElementById("python-install-btn").addEventListener("click", installPython);
    document.getElementById("cpp-toolchain-install-btn").addEventListener("click", () => runCppToolchainAction("cpp_toolchain", "cpp-toolchain-install-btn", "下载并安装 LLVM"));
    document.getElementById("cpp-toolchain-path-btn").addEventListener("click", () => runCppToolchainAction("cpp_toolchain_path", "cpp-toolchain-path-btn", "加入已有目录到 PATH"));
    document.getElementById("shortcuts-uninstall-btn").addEventListener("click", () => uninstallComponent("shortcuts"));
    document.getElementById("camera-test-btn").addEventListener("click", () => {
      const resultEl = document.getElementById("camera-test-result");
      resultEl.textContent = "正在请求摄像头抓拍…";
      sendCameraObservation(false);
      setTimeout(() => {
        resultEl.textContent = "已发送观察请求，结果会出现在聊天记录里。";
      }, 300);
    });
    document.getElementById("camera-chat-btn").addEventListener("click", () => {
      sendCameraObservation(true);
    });
    // Face recognition event bindings
    document.getElementById("face-register-btn").addEventListener("click", registerFace);
    document.getElementById("face-recognize-btn").addEventListener("click", recognizeFaces);
    document.getElementById("face-log-btn").addEventListener("click", showFaceLog);
    document.getElementById("face-install-opencv-btn").addEventListener("click", () => installComponent("opencv"));
    document.getElementById("face-install-all-btn").addEventListener("click", installFaceDeps);
    document.getElementById("face-install-cmake-btn").addEventListener("click", installCmakeOnly);
    document.getElementById("face-install-dlib-btn").addEventListener("click", installDlibOnly);
    document.getElementById("face-install-vs-btn").addEventListener("click", installVsBuildTools);
    document.getElementById("tts-install-btn").addEventListener("click", () => {
      installComponent("tts");
      // 安装完成后重新加载 TTS 配置
      setTimeout(() => loadSettings(), 1000);
    });
    document.getElementById("tts-uninstall-btn").addEventListener("click", () => {
      uninstallComponent("tts");
      setTimeout(() => loadSettings(), 1000);
    });

    async function clearMemoryWithTripleCheck() {
      if (!confirm("第一次确认：确定要清除所有本地用户数据和应用使用数据吗？")) return;
      if (!confirm("第二次确认：这个操作会删除长期记忆、聊天历史、训练反馈、用户画像、作息记录、操作学习、上传/视觉记录、声纹、人脸和成长记录，无法在页面内撤销。继续吗？")) return;
      const typed = prompt("第三次确认：请输入“清除所有数据”以继续。");
      if (typed !== "清除所有数据") {
        document.getElementById("memory-clear-status").textContent = "已取消：第三次验证未通过。";
        return;
      }
      const btn = document.getElementById("memory-clear-btn");
      const statusEl = document.getElementById("memory-clear-status");
      btn.disabled = true;
      statusEl.textContent = "正在清除本地用户数据和应用使用数据...";
      try {
        const resp = await fetch("/api/memory/clear", { method: "POST" });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "清除失败");
        renderMemory(data.memory);
        renderAvatar(data.avatar);
        statusEl.textContent = `已清除 ${data.removed || 0} 项本地用户数据和应用使用数据。`;
      } catch (err) {
        statusEl.textContent = "清除失败：" + err;
      } finally {
        btn.disabled = false;
      }
    }

    document.getElementById("memory-clear-btn").addEventListener("click", clearMemoryWithTripleCheck);

    async function revokePrivacyConsent() {
      if (!confirm("撤回同意后，聊天、上传、屏幕观察和反馈等功能会立即锁定。确定撤回吗？")) return;
      const btn = document.getElementById("privacy-revoke-btn");
      const statusEl = document.getElementById("privacy-status");
      btn.disabled = true;
      btn.textContent = "撤回中...";
      statusEl.textContent = "正在撤回隐私政策同意...";
      try {
        const resp = await fetch("/api/privacy", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({accepted: false})
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "撤回失败");
        privacyAccepted = false;
        privacyCheckbox.checked = false;
        privacySubmit.disabled = true;
        privacySubmit.textContent = "同意并开始使用";
        settingsOverlay.classList.remove("open");
        setAppLocked(true);
        privacyOverlay.classList.remove("hidden");
      } catch (err) {
        statusEl.textContent = "撤回失败：" + err;
        statusEl.className = "status err";
        btn.disabled = false;
        btn.textContent = "撤回隐私政策同意";
      }
    }

    document.getElementById("privacy-revoke-btn").addEventListener("click", revokePrivacyConsent);

    function slugifyPluginName(value) {
      return (value || "ai_plugin")
        .toLowerCase()
        .replace(/[^a-z0-9_]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 48) || "ai_plugin";
    }

    function buildExamplePluginCode() {
      const name = document.getElementById("ai-plugin-name").value.trim() || "AI Sandbox Plugin";
      const desc = document.getElementById("ai-plugin-desc").value.trim() || "AI generated plugin after sandbox validation";
      const command = document.getElementById("ai-plugin-command").value.trim() || "/ai_sandbox";
      const reply = "插件已通过沙箱验证，可以正常响应。";
      return [
        `name = ${JSON.stringify(name)}`,
        `description = ${JSON.stringify(desc)}`,
        `version = "1.0.0"`,
        `buttons = [{"label": ${JSON.stringify(name)}, "command": ${JSON.stringify(command)}}]`,
        "",
        "def on_load(api):",
        "    api.log(\"loaded after sandbox validation\")",
        "",
        "def on_unload():",
        "    pass",
        "",
        "def on_message(message, api):",
        `    if message == ${JSON.stringify(command)}:`,
        "        count = api.read_data(\"count\", 0) + 1",
        "        api.write_data(\"count\", count)",
        `        return {"reply": ${JSON.stringify(reply)} + f"\\n运行次数：{count}"}`,
        "    return None",
      ].join("\n");
    }

    function buildAiPluginMeta() {
      const rawDir = document.getElementById("ai-plugin-dir").value.trim();
      const name = document.getElementById("ai-plugin-name").value.trim() || "AI Sandbox Plugin";
      const command = document.getElementById("ai-plugin-command").value.trim() || "/ai_sandbox";
      return {
        dir: slugifyPluginName(rawDir || name),
        meta: {
          name,
          description: document.getElementById("ai-plugin-desc").value.trim() || "AI generated plugin",
          version: "1.0.0",
          buttons: [{ label: name, command }],
          code: document.getElementById("ai-plugin-code").value,
          ai_generated: true,
          sandbox_validate: true,
          isolation_backend: document.getElementById("ai-plugin-isolation").value,
          readme: "# " + name + "\n\nAI generated plugin. Installed only after sandbox validation.",
        },
      };
    }

    async function validateAiPluginCode() {
      const statusEl = document.getElementById("ai-plugin-status");
      const { meta } = buildAiPluginMeta();
      statusEl.textContent = "沙箱验证中...";
      const resp = await fetch("/api/plugins", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "sandbox_validate", meta }),
      });
      const data = await resp.json();
      if (data.ok) {
        statusEl.textContent = `沙箱验证和杀毒扫描通过（${data.isolation || "隔离后端未知"}）：` + (data.checks || []).join("，");
      } else {
        statusEl.textContent = "沙箱验证失败：" + (data.error || "未知错误");
      }
      return data;
    }

    document.getElementById("ai-plugin-example-btn").addEventListener("click", () => {
      if (!document.getElementById("ai-plugin-dir").value.trim()) document.getElementById("ai-plugin-dir").value = "ai_sandbox_plugin";
      if (!document.getElementById("ai-plugin-name").value.trim()) document.getElementById("ai-plugin-name").value = "AI Sandbox Plugin";
      if (!document.getElementById("ai-plugin-desc").value.trim()) document.getElementById("ai-plugin-desc").value = "AI generated plugin after sandbox validation";
      if (!document.getElementById("ai-plugin-command").value.trim()) document.getElementById("ai-plugin-command").value = "/ai_sandbox";
      document.getElementById("ai-plugin-code").value = buildExamplePluginCode();
      document.getElementById("ai-plugin-status").textContent = "示例代码已生成。";
    });

    document.getElementById("ai-plugin-validate-btn").addEventListener("click", () => {
      validateAiPluginCode().catch(err => {
        document.getElementById("ai-plugin-status").textContent = "沙箱验证失败：" + err;
      });
    });

    document.getElementById("ai-plugin-install-btn").addEventListener("click", async () => {
      const statusEl = document.getElementById("ai-plugin-status");
      try {
        const validation = await validateAiPluginCode();
        if (!validation.ok) return;
        const { dir, meta } = buildAiPluginMeta();
        statusEl.textContent = "安装插件中...";
        const resp = await fetch("/api/plugins", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "create", name: dir, meta }),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "安装失败");
        statusEl.textContent = "插件已安装，正在刷新页面...";
        location.reload();
      } catch (err) {
        statusEl.textContent = "安装失败：" + err;
      }
    });

    // ---- Identity section in settings ----
    function loadIdentityStatus() {
      fetch('/api/identity').then(r => r.json()).then(data => {
        const el = document.getElementById('identity-status');
        if (data.setup_done) {
          const id = data.identity;
          let text = '名字：' + (id.name || '未设置');
          const relationLabels = {friend: '朋友', family: '家人', partner: '搭档', guardian: '守护者', lifeform: '虚拟生命'};
          const subtypeLabels = {friend: '普通朋友', close_friend: '挚友', best_friend: '最好的朋友', classmate: '同学', childhood_friend: '青梅竹马', online_friend: '网友', daughter: '女儿', son: '儿子', mother: '母亲', father: '父亲', parent: '父母', older_sister: '姐姐', older_brother: '哥哥', younger_sister: '妹妹', younger_brother: '弟弟', family_member: '其他家人', study_partner: '学习搭子', work_partner: '工作搭档', creative_partner: '创作搭档', game_partner: '游戏搭子', accountability_partner: '互助伙伴', health_guardian: '健康守护者', routine_guardian: '作息守护者', emotion_guardian: '情绪守护者', safety_guardian: '安全提醒者', learning_lifeform: '学习型数字生命', explorer_lifeform: '探索型数字生命', companion_lifeform: '陪伴型数字生命', assistant_lifeform: '助理型数字生命'};
          const relationshipLabel = id.relationship_type === 'custom'
            ? (id.relationship_label || '自定义关系')
            : subtypeLabels[id.relationship_subtype]
              ? subtypeLabels[id.relationship_subtype]
            : (relationLabels[id.relationship_type] || id.relationship_label || '朋友');
          text += ' | 关系：' + relationshipLabel;
          if (id.gender) text += ' | 性别：' + id.gender;
          if (id.birthday) text += ' | 生日：' + id.birthday;
          if (id.persona) text += ' | 人设：' + id.persona.slice(0, 40) + (id.persona.length > 40 ? '...' : '');
          if (id.worldview) text += ' | 世界观：' + id.worldview.slice(0, 40) + (id.worldview.length > 40 ? '...' : '');
          if (id.relationship_assignment && id.relationship_assignment.ok) {
            const typeLabels = {friend: '朋友', family: '家人', partner: '搭档', guardian: '守护者', lifeform: '虚拟生命'};
            text += ' | 成长线：' + (typeLabels[id.relationship_assignment.assigned_type] || id.relationship_assignment.assigned_type || '自定义');
          }
          el.textContent = text;
          el.title = text;
          el.style.color = '#243143';
        } else {
          el.textContent = '未设置身份信息';
          el.title = '未设置身份信息';
          el.style.color = '#657184';
        }
      }).catch(() => {});
    }
    document.getElementById('identity-edit-btn').addEventListener('click', () => {
      window.openOnboarding();
    });

    // ---- Live2D model import ----
    const live2dFileInput = document.getElementById("live2d-file");
    const live2dChooseBtn = document.getElementById("live2d-choose-btn");
    const live2dUploadBtn = document.getElementById("live2d-upload-btn");
    const live2dProgress = document.getElementById("live2d-upload-progress");
    const live2dModelList = document.getElementById("live2d-model-list");
    const live2dStatus = document.getElementById("live2d-status");

    live2dChooseBtn.addEventListener("click", () => live2dFileInput.click());

    live2dFileInput.addEventListener("change", () => {
      if (live2dFileInput.files.length > 0) {
        live2dProgress.textContent = "已选择: " + live2dFileInput.files[0].name;
      }
    });

    live2dUploadBtn.addEventListener("click", () => {
      if (!live2dFileInput.files.length) {
        live2dProgress.textContent = "请先选择一个 zip 文件";
        return;
      }
      const file = live2dFileInput.files[0];
      const formData = new FormData();
      formData.append("file", file);
      live2dUploadBtn.disabled = true;
      live2dProgress.textContent = "上传中…";
      fetch("/api/live2d/upload", {method: "POST", body: formData})
        .then(r => r.json())
        .then(data => {
          live2dUploadBtn.disabled = false;
          if (data.ok) {
            live2dProgress.textContent = "模型 \"" + data.model + "\" 导入成功" + (data.has_model3 ? "" : "（未找到 .model3.json，请检查包结构）");
            live2dFileInput.value = "";
            refreshLive2DList(data.models);
          } else {
            live2dProgress.textContent = "" + (data.error || "导入失败");
          }
        })
        .catch(err => {
          live2dUploadBtn.disabled = false;
          live2dProgress.textContent = "上传失败: " + err;
        });
    });

    function refreshLive2DList(models) {
      if (!models || models.length === 0) {
        live2dModelList.innerHTML = "<span style='color:#657184'>暂无模型</span>";
        live2dStatus.textContent = "暂无 Live2D 模型，请上传 zip 包";
        return;
      }
      let html = "";
      models.forEach(m => {
        const activeTag = m.active ? "  当前使用" : "";
        html += "<div style='margin:3px 0'>" + m.name + " <span style='color:#657184;font-size:11px'>(" + m.path + ")</span>" + activeTag + "</div>";
      });
      live2dModelList.innerHTML = html;
      live2dStatus.textContent = "已安装 " + models.length + " 个模型";
    }

    // Load Live2D model list when settings opens
    const origLoadSettings = loadSettings;
    loadSettings = function() {
      origLoadSettings();
      loadIdentityStatus();
      fetch("/api/live2d").then(r => r.json()).then(data => {
        refreshLive2DList(data.models);
      }).catch(() => {
        live2dStatus.textContent = "获取模型列表失败";
      });
    };

    // ---- 3D model import ----
    const model3dFileInput = document.getElementById("3d-file");
    const model3dChooseBtn = document.getElementById("3d-choose-btn");
    const model3dUploadBtn = document.getElementById("3d-upload-btn");
    const model3dProgress = document.getElementById("3d-upload-progress");
    const model3dModelList = document.getElementById("3d-model-list");
    const model3dStatus = document.getElementById("3d-status");

    model3dChooseBtn.addEventListener("click", () => model3dFileInput.click());

    model3dFileInput.addEventListener("change", () => {
      if (model3dFileInput.files.length > 0) {
        model3dProgress.textContent = "\u5df2\u9009\u62e9: " + model3dFileInput.files[0].name;
      }
    });

    model3dUploadBtn.addEventListener("click", () => {
      if (!model3dFileInput.files.length) {
        model3dProgress.textContent = "\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a zip \u6587\u4ef6";
        return;
      }
      const file = model3dFileInput.files[0];
      const formData = new FormData();
      formData.append("file", file);
      model3dUploadBtn.disabled = true;
      model3dProgress.textContent = "\u4e0a\u4f20\u4e2d\u2026";
      fetch("/api/3d/upload", {method: "POST", body: formData})
        .then(r => r.json())
        .then(data => {
          model3dUploadBtn.disabled = false;
          if (data.ok) {
            const fmtLabel = data.format || "unknown";
            model3dProgress.textContent = "\u2705 \u6a21\u578b \"" + data.model + "\" \u5bfc\u5165\u6210\u529f" + (data.has_model ? " (\u683c\u5f0f: " + fmtLabel + ")" : "\uff08\u672a\u627e\u5230\u652f\u6301\u7684 3D \u6a21\u578b\u6587\u4ef6\uff0c\u8bf7\u68c0\u67e5\u5305\u7ed3\u6784\uff09");
            model3dFileInput.value = "";
            refresh3DList(data.models);
          } else {
            model3dProgress.textContent = "\u274c " + (data.error || "\u5bfc\u5165\u5931\u8d25");
          }
        })
        .catch(err => {
          model3dUploadBtn.disabled = false;
          model3dProgress.textContent = "\u274c \u4e0a\u4f20\u5931\u8d25: " + err;
        });
    });

    function refresh3DList(models) {
      if (!models || models.length === 0) {
        model3dModelList.innerHTML = "<span style='color:#657184'>\u6682\u65e0 3D \u6a21\u578b</span>";
        model3dStatus.textContent = "\u6682\u65e0 3D \u6a21\u578b\uff0c\u8bf7\u4e0a\u4f20 zip \u5305";
        return;
      }
      let html = "";
      models.forEach(m => {
        const activeTag = m.active ? " \u2705 \u5f53\u524d\u4f7f\u7528" : "";
        const fmtBadge = "<span style='color:#276ef1;font-size:11px'>[" + (m.format || "?") + "]</span>";
        html += "<div style='margin:3px 0'>" + fmtBadge + " " + m.name + " <span style='color:#657184;font-size:11px'>(" + m.path + ")</span>" + activeTag + "</div>";
      });
      model3dModelList.innerHTML = html;
      model3dStatus.textContent = "\u5df2\u5b89\u88c5 " + models.length + " \u4e2a 3D \u6a21\u578b";
    }

    // Patch loadSettings to also load 3D model list
    const prevLoadSettings = loadSettings;
    loadSettings = function() {
      prevLoadSettings();
      fetch("/api/3d").then(r => r.json()).then(data => {
        refresh3DList(data.models);
      }).catch(() => {
        model3dStatus.textContent = "\u83b7\u53d6 3D \u6a21\u578b\u5217\u8868\u5931\u8d25";
      });
      // Load pet display mode
      fetch("/api/pet_display").then(r => r.json()).then(data => {
        const radios = document.querySelectorAll('input[name="pet-display-mode"]');
        radios.forEach(r => { r.checked = (r.value === data.mode); });
        const statusEl = document.getElementById("pet-display-status");
        const modeLabels = data.modes || {};
        statusEl.textContent = "当前模式：" + (modeLabels[data.mode] || data.mode);
        statusEl.className = "status ok";
      }).catch(() => {
        document.getElementById("pet-display-status").textContent = "加载显示模式失败";
        document.getElementById("pet-display-status").className = "status err";
      });
    };

    // Pet display mode change handler
    document.querySelectorAll('input[name="pet-display-mode"]').forEach(radio => {
      radio.addEventListener("change", function() {
        const statusEl = document.getElementById("pet-display-status");
        statusEl.textContent = "保存中...";
        statusEl.className = "status loading";
        fetch("/api/pet_display", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({mode: this.value})
        }).then(r => r.json()).then(data => {
          if (data.ok) {
            const ml = {"auto":"自动检测","3d":"3D 模型","live2d":"Live2D 模型","classic":"经典手绘"};
            statusEl.textContent = "已保存：" + (ml[data.mode] || data.mode) + "（重启桌宠后生效）";
            statusEl.className = "status ok";
          } else {
            statusEl.textContent = "保存失败：" + (data.error || "");
            statusEl.className = "status err";
          }
        }).catch(() => {
          statusEl.textContent = "保存失败";
          statusEl.className = "status err";
        });
      });
    });

    // ---- Onboarding modal ----
    const obOverlay = document.getElementById('onboarding-overlay');
    const obName = document.getElementById('ob-name');
    const obRelationship = document.getElementById('ob-relationship');
    const obRomanceEvolutionGroup = document.getElementById('ob-romance-evolution-group');
    const obRomanceEvolution = document.getElementById('ob-romance-evolution');
    const obRelationshipSubtypeGroup = document.getElementById('ob-relationship-subtype-group');
    const obRelationshipSubtype = document.getElementById('ob-relationship-subtype');
    const obRelationshipSubtypeLabel = document.getElementById('ob-relationship-subtype-label');
    const obCustomRelationshipGroup = document.getElementById('ob-custom-relationship-group');
    const obCustomRelationship = document.getElementById('ob-custom-relationship');
    const obBirthday = document.getElementById('ob-birthday');
    const obId = document.getElementById('ob-id');
    const obGenId = document.getElementById('ob-gen-id');
    const obPersona = document.getElementById('ob-persona');
    const obWorldview = document.getElementById('ob-worldview');
    const obSkip = document.getElementById('ob-skip');
    const obSubmit = document.getElementById('ob-submit');

    function checkIdentitySetup() {
      if (!privacyAccepted) return;
      fetch('/api/identity').then(r => r.json()).then(data => {
        if (!data.setup_done) {
          syncCustomRelationshipInput();
          obOverlay.classList.remove('hidden');
        }
      }).catch(() => {});
    }

    const relationshipSubtypeOptions = {
      friend: [['friend', '普通朋友'], ['close_friend', '挚友'], ['best_friend', '最好的朋友'], ['classmate', '同学'], ['childhood_friend', '青梅竹马'], ['online_friend', '网友']],
      family: [['daughter', '女儿'], ['son', '儿子'], ['mother', '母亲'], ['father', '父亲'], ['parent', '父母'], ['older_sister', '姐姐'], ['older_brother', '哥哥'], ['younger_sister', '妹妹'], ['younger_brother', '弟弟'], ['family_member', '其他家人']],
      partner: [['study_partner', '学习搭子'], ['work_partner', '工作搭档'], ['creative_partner', '创作搭档'], ['game_partner', '游戏搭子'], ['accountability_partner', '互助伙伴']],
      guardian: [['health_guardian', '健康守护者'], ['routine_guardian', '作息守护者'], ['emotion_guardian', '情绪守护者'], ['safety_guardian', '安全提醒者']],
      lifeform: [['learning_lifeform', '学习型数字生命'], ['explorer_lifeform', '探索型数字生命'], ['companion_lifeform', '陪伴型数字生命'], ['assistant_lifeform', '助理型数字生命']],
    };
    const relationshipSubtypeTitles = {friend: '朋友类型', family: '家人身份', partner: '搭档类型', guardian: '守护方向', lifeform: '生命类型'};

    function syncCustomRelationshipInput(options = {}) {
      const isCustom = obRelationship.value === 'custom';
      const isFriend = obRelationship.value === 'friend';
      const subtypes = relationshipSubtypeOptions[obRelationship.value] || [];
      const previousSubtype = obRelationshipSubtype.value;
      obCustomRelationshipGroup.style.display = isCustom ? 'block' : 'none';
      obRomanceEvolutionGroup.style.display = isFriend ? 'block' : 'none';
      obRelationshipSubtypeGroup.style.display = subtypes.length ? 'block' : 'none';
      obCustomRelationship.required = isCustom;
      obRelationshipSubtype.required = subtypes.length > 0;
      obCustomRelationship.setAttribute('aria-hidden', isCustom ? 'false' : 'true');
      obRelationshipSubtype.setAttribute('aria-hidden', subtypes.length ? 'false' : 'true');
      if (subtypes.length) {
        obRelationshipSubtypeLabel.textContent = relationshipSubtypeTitles[obRelationship.value] || '具体身份';
        obRelationshipSubtype.replaceChildren(...subtypes.map(([value, label]) => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = label;
          return option;
        }));
        obRelationshipSubtype.value = subtypes.some(([value]) => value === previousSubtype) ? previousSubtype : subtypes[0][0];
      }
      if (isCustom && options.focus) {
        obCustomRelationship.focus();
      }
      if (!isCustom) {
        obCustomRelationship.style.borderColor = '';
      }
      obRelationshipSubtype.style.borderColor = '';
    }

    // Relationship type change -> show/hide custom input
    obRelationship.addEventListener('change', () => {
      syncCustomRelationshipInput({focus: true});
    });
    syncCustomRelationshipInput();

    // Birthday change -> auto-generate ID
    obBirthday.addEventListener('change', () => {
      if (obBirthday.value) {
        fetch('/api/identity', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'generate_id', birthday: obBirthday.value})
        }).then(r => r.json()).then(data => {
          if (data.ok && data.id_number) {
            obId.value = data.id_number;
          }
        }).catch(() => {});
      }
    });

    // Regenerate ID button
    obGenId.addEventListener('click', () => {
      const birthday = obBirthday.value || new Date().toISOString().slice(0, 10);
      fetch('/api/identity', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'generate_id', birthday: birthday})
      }).then(r => r.json()).then(data => {
        if (data.ok && data.id_number) {
          obId.value = data.id_number;
          if (!obBirthday.value) obBirthday.value = birthday;
        }
      }).catch(() => {});
    });

    // Persona hint chips
    document.querySelectorAll('.persona-hint[data-text]').forEach(chip => {
      chip.addEventListener('click', () => {
        obPersona.value = chip.dataset.text || '';
      });
    });

    // Worldview hint chips
    document.querySelectorAll('.persona-hint[data-worldview]').forEach(chip => {
      chip.addEventListener('click', () => {
        obWorldview.value = chip.dataset.worldview || '';
      });
    });

    // Skip button
    obSkip.addEventListener('click', () => {
      obOverlay.classList.add('hidden');
    });

    // Submit button
    obSubmit.addEventListener('click', async () => {
      const name = obName.value.trim();
      if (!name) {
        obName.style.borderColor = '#e03e3e';
        obName.focus();
        return;
      }
      if (obRelationship.value === 'custom') {
        const customLabel = obCustomRelationship.value.trim();
        if (!customLabel) {
          obCustomRelationship.style.borderColor = '#e03e3e';
          obCustomRelationship.focus();
          return;
        }
        obCustomRelationship.style.borderColor = '';
      }
      if (relationshipSubtypeOptions[obRelationship.value] && !obRelationshipSubtype.value) {
        obRelationshipSubtype.style.borderColor = '#e03e3e';
        obRelationshipSubtype.focus();
        return;
      }
      obRelationshipSubtype.style.borderColor = '';
      obSubmit.disabled = true;
      obSubmit.textContent = '保存中...';
      try {
        const gender = document.querySelector('input[name="ob-gender"]:checked').value;
        const resp = await fetch('/api/identity', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            action: 'save',
            name: name,
            relationship_type: obRelationship.value,
            relationship_label: obRelationship.value === 'custom' ? obCustomRelationship.value.trim() : '',
            relationship_subtype: relationshipSubtypeOptions[obRelationship.value] ? obRelationshipSubtype.value : '',
            allow_romance_evolution: obRelationship.value === 'friend' ? obRomanceEvolution.checked : false,
            gender: gender,
            birthday: obBirthday.value,
            id_number: obId.value,
            persona: obPersona.value.trim(),
            worldview: obWorldview.value.trim()
          })
        });
        const data = await resp.json();
        if (data.ok) {
          obOverlay.classList.add('hidden');
          addMsg('assistant', '你好！我是' + name + '，很高兴认识你~');
          startGuidedTour();
        } else {
          obSubmit.disabled = false;
          obSubmit.textContent = '完成设置';
          if (data.error) {
            alert(data.error);
          }
        }
      } catch(e) {
        obSubmit.disabled = false;
        obSubmit.textContent = '完成设置';
      }
    });

    // Expose function to open onboarding from settings
    window.openOnboarding = function() {
      fetch('/api/identity').then(r => r.json()).then(data => {
        const id = data.identity || {};
        obName.value = id.name || '';
        obRelationship.value = id.relationship_type || 'friend';
        obCustomRelationship.value = id.relationship_label || '';
        obRelationshipSubtype.value = id.relationship_subtype || '';
        obRomanceEvolution.checked = id.allow_romance_evolution !== false;
        syncCustomRelationshipInput();
        obBirthday.value = id.birthday || '';
        obId.value = id.id_number || '';
        obPersona.value = id.persona || '';
        obWorldview.value = id.worldview || '';
        if (id.gender) {
          const radio = document.querySelector('input[name="ob-gender"][value="' + id.gender + '"]');
          if (radio) radio.checked = true;
        }
        obOverlay.classList.remove('hidden');
      });
    };

    // ---- Guided Tour ----
    const tourOverlay = document.getElementById('tour-overlay');
    const tourHighlight = document.getElementById('tour-highlight');
    const tourTooltip = document.getElementById('tour-tooltip');
    const tourKicker = document.getElementById('tour-kicker');
    const tourTitle = document.getElementById('tour-title');
    const tourDesc = document.getElementById('tour-desc');
    const tourProgress = document.getElementById('tour-progress');
    const tourSkip = document.getElementById('tour-skip');
    const tourPrev = document.getElementById('tour-prev');
    const tourNext = document.getElementById('tour-next');

    let currentTourStep = 0;

    const tourSteps = [
      {
        targetId: 'new-chat-btn',
        title: '从一段新对话开始',
        desc: '需要换一个话题时，点击这里创建新的对话。已有内容会保留在左侧的最近对话中。',
        position: 'right'
      },
      {
        targetId: 'message',
        title: '把想法告诉 Companion',
        desc: '直接输入问题、目标或近况。附件、网页和更多输入选项都在输入框下方。',
        position: 'top'
      },
      {
        targetId: 'memory-orbit',
        title: '查看陪伴上下文',
        desc: '这里汇总当前记忆、文件和常用动作。需要时展开它，聊天空间会保持干净。',
        position: 'left'
      },
      {
        targetId: 'settings-btn',
        title: '按自己的方式设置',
        desc: '在这里管理身份、显示、语音、桌宠和本地数据。随时可以回来调整。',
        position: 'bottom'
      }
    ];

    function startGuidedTour(options = {}) {
      const hasDoneTour = localStorage.getItem('companion_ai_tour_done');
      if (hasDoneTour && !options.force) return;
      currentTourStep = 0;
      showTourStep(currentTourStep, { scroll: true });
    }

    function getTourTarget(step) {
      return document.getElementById(step.targetId);
    }

    function positionTourTooltip(rect, position) {
      const padding = 16;
      const gap = 16;
      const tooltipRect = tourTooltip.getBoundingClientRect();
      let left = rect.left;
      let top = rect.bottom + gap;

      if (position === 'top') {
        left = rect.left + rect.width / 2 - tooltipRect.width / 2;
        top = rect.top - tooltipRect.height - gap;
      } else if (position === 'left') {
        left = rect.left - tooltipRect.width - gap;
        top = rect.top + rect.height / 2 - tooltipRect.height / 2;
      } else if (position === 'right') {
        left = rect.right + gap;
        top = rect.top + rect.height / 2 - tooltipRect.height / 2;
      } else {
        left = rect.left + rect.width / 2 - tooltipRect.width / 2;
      }

      left = Math.max(padding, Math.min(left, window.innerWidth - tooltipRect.width - padding));
      top = Math.max(padding, Math.min(top, window.innerHeight - tooltipRect.height - padding));
      tourTooltip.style.left = `${Math.round(left)}px`;
      tourTooltip.style.top = `${Math.round(top)}px`;
    }

    function showTourStep(index, options = {}) {
      if (index < 0) return;
      if (index >= tourSteps.length) {
        endTour();
        return;
      }
      currentTourStep = index;
      const step = tourSteps[index];
      const target = getTourTarget(step);
      if (!target) {
        showTourStep(index + 1, options);
        return;
      }

      if (options.scroll) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        window.setTimeout(() => showTourStep(index), 260);
        return;
      }

      const rect = target.getBoundingClientRect();
      const inset = 6;
      tourKicker.textContent = `快速开始 ${index + 1} / ${tourSteps.length}`;
      tourTitle.textContent = step.title;
      tourDesc.textContent = step.desc;
      tourNext.textContent = index === tourSteps.length - 1 ? '完成' : '下一步';
      tourPrev.disabled = index === 0;
      tourProgress.replaceChildren(...tourSteps.map((_, stepIndex) => {
        const dot = document.createElement('span');
        dot.className = `tour-dot${stepIndex === index ? ' active' : ''}`;
        return dot;
      }));

      tourHighlight.style.display = 'block';
      tourHighlight.style.left = `${Math.round(rect.left - inset)}px`;
      tourHighlight.style.top = `${Math.round(rect.top - inset)}px`;
      tourHighlight.style.width = `${Math.round(rect.width + inset * 2)}px`;
      tourHighlight.style.height = `${Math.round(rect.height + inset * 2)}px`;
      tourOverlay.classList.remove('hidden');
      positionTourTooltip(rect, step.position);
    }

    function nextTourStep() {
      showTourStep(currentTourStep + 1, { scroll: true });
    }

    function previousTourStep() {
      showTourStep(currentTourStep - 1, { scroll: true });
    }

    function endTour() {
      tourOverlay.classList.add('hidden');
      tourHighlight.style.display = 'none';
      localStorage.setItem('companion_ai_tour_done', 'true');
    }

    function repositionTour() {
      if (!tourOverlay.classList.contains('hidden')) showTourStep(currentTourStep);
    }

    tourNext.addEventListener('click', nextTourStep);
    tourPrev.addEventListener('click', previousTourStep);
    tourSkip.addEventListener('click', endTour);
    tourOverlay.addEventListener('click', event => {
      if (event.target === tourOverlay) endTour();
    });
    document.addEventListener('keydown', event => {
      if (tourOverlay.classList.contains('hidden')) return;
      if (event.key === 'Escape') endTour();
      if (event.key === 'ArrowRight' || event.key === 'Enter') nextTourStep();
      if (event.key === 'ArrowLeft') previousTourStep();
    });
    window.addEventListener('resize', repositionTour);
    window.addEventListener('scroll', repositionTour, true);
    window.startGuidedTour = () => startGuidedTour({ force: true });
  </script>
  <script>
    // Keep onboarding available even if an optional page integration fails during startup.
    (() => {
      const overlay = document.getElementById('tour-overlay');
      const highlight = document.getElementById('tour-highlight');
      const tooltip = document.getElementById('tour-tooltip');
      const kicker = document.getElementById('tour-kicker');
      const title = document.getElementById('tour-title');
      const desc = document.getElementById('tour-desc');
      const progress = document.getElementById('tour-progress');
      const skip = document.getElementById('tour-skip');
      const previous = document.getElementById('tour-prev');
      const next = document.getElementById('tour-next');
      if (!overlay || !highlight || !tooltip || !kicker || !title || !desc || !progress || !skip || !previous || !next) return;

      const steps = [
        ['new-chat-btn', '从一段新对话开始', '需要换一个话题时，点击这里创建新的对话。已有内容会保留在左侧的最近对话中。', 'right'],
        ['message', '把想法告诉 Companion', '直接输入问题、目标或近况。附件、网页和更多输入选项都在输入框下方。', 'top'],
        ['memory-orbit', '查看陪伴上下文', '这里汇总当前记忆、文件和常用动作。需要时展开它，聊天空间会保持干净。', 'left'],
        ['settings-btn', '按自己的方式设置', '在这里管理身份、显示、语音、桌宠和本地数据。随时可以回来调整。', 'bottom'],
      ];
      let activeStep = 0;

      function finish() {
        overlay.classList.add('hidden');
        highlight.style.display = 'none';
        localStorage.setItem('companion_ai_tour_done', 'true');
      }

      function placeTooltip(rect, position) {
        const margin = 16;
        const gap = 16;
        const card = tooltip.getBoundingClientRect();
        let left = rect.left + rect.width / 2 - card.width / 2;
        let top = rect.bottom + gap;
        if (position === 'top') top = rect.top - card.height - gap;
        if (position === 'left') { left = rect.left - card.width - gap; top = rect.top + rect.height / 2 - card.height / 2; }
        if (position === 'right') { left = rect.right + gap; top = rect.top + rect.height / 2 - card.height / 2; }
        tooltip.style.left = `${Math.round(Math.max(margin, Math.min(left, window.innerWidth - card.width - margin)))}px`;
        tooltip.style.top = `${Math.round(Math.max(margin, Math.min(top, window.innerHeight - card.height - margin)))}px`;
      }

      function render(index, scroll = true) {
        if (index < 0) return;
        if (index >= steps.length) { finish(); return; }
        const step = steps[index];
        const target = document.getElementById(step[0]);
        if (!target) { render(index + 1, scroll); return; }
        activeStep = index;
        if (scroll) {
          target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
          window.setTimeout(() => render(index, false), 260);
          return;
        }
        const rect = target.getBoundingClientRect();
        const inset = 6;
        kicker.textContent = `快速开始 ${index + 1} / ${steps.length}`;
        title.textContent = step[1];
        desc.textContent = step[2];
        previous.disabled = index === 0;
        next.textContent = index === steps.length - 1 ? '完成' : '下一步';
        progress.replaceChildren(...steps.map((_, i) => {
          const dot = document.createElement('span');
          dot.className = `tour-dot${i === index ? ' active' : ''}`;
          return dot;
        }));
        highlight.style.display = 'block';
        highlight.style.left = `${Math.round(rect.left - inset)}px`;
        highlight.style.top = `${Math.round(rect.top - inset)}px`;
        highlight.style.width = `${Math.round(rect.width + inset * 2)}px`;
        highlight.style.height = `${Math.round(rect.height + inset * 2)}px`;
        overlay.classList.remove('hidden');
        placeTooltip(rect, step[3]);
      }

      function start(force = false) {
        if (!force && localStorage.getItem('companion_ai_tour_done')) return;
        render(0);
      }

      next.addEventListener('click', event => { event.stopImmediatePropagation(); render(activeStep + 1); }, true);
      previous.addEventListener('click', event => { event.stopImmediatePropagation(); render(activeStep - 1); }, true);
      skip.addEventListener('click', event => { event.stopImmediatePropagation(); finish(); }, true);
      overlay.addEventListener('click', event => { if (event.target === overlay) finish(); });
      document.addEventListener('keydown', event => {
        if (overlay.classList.contains('hidden')) return;
        if (event.key === 'Escape') finish();
        if (event.key === 'ArrowRight' || event.key === 'Enter') render(activeStep + 1);
        if (event.key === 'ArrowLeft') render(activeStep - 1);
      });
      window.addEventListener('resize', () => { if (!overlay.classList.contains('hidden')) render(activeStep, false); });
      window.addEventListener('scroll', () => { if (!overlay.classList.contains('hidden')) render(activeStep, false); }, true);
      window.startGuidedTour = () => start(true);
      document.getElementById('tour-restart-btn')?.addEventListener('click', () => start(true));
      fetch('/api/identity').then(response => response.json()).then(data => {
        if (data.setup_done) start(false);
      }).catch(() => {});
    })();

    // Scrollbar visibility: hidden by default, shown when scrolling.
    (function () {
      let scrollTimer = null;
      function showScrolling() {
        document.body.classList.add('is-scrolling');
        if (scrollTimer) clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => {
          document.body.classList.remove('is-scrolling');
        }, 600);
      }
      window.addEventListener('scroll', showScrolling, true);
      document.addEventListener('wheel', showScrolling, { capture: true, passive: true });
      document.addEventListener('touchmove', showScrolling, { capture: true, passive: true });
    })();
  </script>
</body>
</html>"""


SECONDARY_PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN" data-theme="__DISPLAY_THEME__" style="__DISPLAY_STYLE__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__ - Companion AI</title>
  <style>
    :root {
      --font-scale: 1;
      --density-scale: 1;
      --ui-radius: 8px;
      --space-1: calc(10px * var(--density-scale));
      --space-2: calc(16px * var(--density-scale));
      --bg: #f6f7f9;
      --paper: var(--bg);
      --panel: #ffffff;
      --panel-soft: #eef2f7;
      --ink: #172033;
      --muted: #657184;
      --line: #d9dee7;
      --accent: #276ef1;
      --accent-2: #0b8f6f;
      --warn: #8a6100;
      --green: #10a37f;
      --good: #0b7a55;
      --bad: #c0392b;
      --shadow: 0 14px 42px rgba(26, 38, 55, .10);
    }
    :root[data-theme="night"] {
      --bg: #10141c;
      --paper: var(--bg);
      --panel: #171d28;
      --panel-soft: #111722;
      --ink: #f1f5fa;
      --muted: #c4d0df;
      --line: #2a3444;
      --accent: #7aa7ff;
      --accent-2: #6ed0b2;
      --warn: #ffd166;
      --green: #66d39d;
      --good: #66d39d;
      --bad: #ff8a80;
      --shadow: 0 14px 42px rgba(0, 0, 0, .28);
    }
    :root[data-theme="forest"] {
      --bg: #f2f7f3;
      --paper: var(--bg);
      --panel: #ffffff;
      --panel-soft: #e9f1eb;
      --ink: #183026;
      --muted: #66786f;
      --line: #cfded5;
      --accent: #2d7d59;
      --accent-2: #6c8f3d;
      --warn: #7a5a12;
      --green: #23724e;
      --good: #23724e;
      --bad: #b94a3c;
    }
    :root[data-theme="rose"] {
      --bg: #fbf5f7;
      --paper: var(--bg);
      --panel: #ffffff;
      --panel-soft: #f4e9ef;
      --ink: #33212a;
      --muted: #7c6872;
      --line: #ead5df;
      --accent: #c24a7a;
      --accent-2: #7b6cc2;
      --warn: #8a5b12;
      --green: #35785f;
      --good: #35785f;
      --bad: #b94a5b;
    }
    :root[data-theme="mono"] {
      --bg: #f5f5f4;
      --paper: var(--bg);
      --panel: #ffffff;
      --panel-soft: #ececea;
      --ink: #202020;
      --muted: #666666;
      --line: #d7d7d4;
      --accent: #2f5f8f;
      --accent-2: #5a6f3b;
      --warn: #7a5600;
      --green: #286b49;
      --good: #286b49;
      --bad: #a33a32;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-width: 320px;
      font-size: calc(16px * var(--font-scale));
      color: var(--ink);
      background: var(--paper);
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
      line-height: 1.55;
    }
    a { color: inherit; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px clamp(16px, 4vw, 42px);
      border-bottom: 0;
      background: color-mix(in srgb, var(--paper) 92%, transparent);
      backdrop-filter: blur(14px);
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; text-decoration: none; }
    .brand img { width: 30px; height: 30px; border-radius: 8px; }
    .nav { display: flex; flex-wrap: wrap; gap: 8px; color: var(--muted); font-size: 13px; }
    .nav a { padding: 7px 10px; border-radius: 7px; text-decoration: none; }
    .nav a:hover, .nav a.active { background: color-mix(in srgb, var(--accent) 12%, var(--panel)); color: var(--accent); }
    .page {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 42px;
    }
    .hero {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 18px;
    }
    h1 { margin: 0; font-size: clamp(28px, 4vw, 42px); line-height: 1.12; letter-spacing: 0; }
    .lead { max-width: 720px; margin: 10px 0 0; color: var(--muted); }
    .panel {
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      box-shadow: var(--shadow);
    }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .grid.two { grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); }
    .card { padding: 18px; border: 0; border-radius: var(--ui-radius); background: var(--panel); box-shadow: var(--shadow); }
    .card h3 { margin: 0 0 8px; font-size: 18px; }
    .card p { margin: 0; color: var(--muted); font-size: 14px; }
    .button-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    button, .button {
      min-height: 34px;
      padding: 8px 12px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      font-weight: 750;
      cursor: pointer;
      text-decoration: none;
    }
    button:hover, .button:hover { background: color-mix(in srgb, var(--accent) 10%, var(--panel)); color: var(--accent); }
    button.primary, .button.primary { background: color-mix(in srgb, var(--accent) 16%, var(--panel)); color: var(--accent); }
    button:disabled { opacity: .6; cursor: wait; }
    textarea, input {
      width: 100%;
      padding: 10px 12px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 42%, transparent);
      font: inherit;
      resize: vertical;
    }
    .content-section { display: none; }
    .content-section.active { display: block; }
    .command-bar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 14px;
      padding: 12px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      box-shadow: 0 10px 28px rgba(26, 38, 55, .06);
    }
    .command-bar input { resize: none; }
    .command-bar-result {
      display: none;
      min-height: 84px;
      max-height: 220px;
      margin-bottom: 14px;
    }
    body[data-page-kind="tools"] .command-bar-result {
      display: block;
    }
    body[data-page-kind="diary"] .command-bar,
    body[data-page-kind="diary"] .command-bar-result,
    body[data-page-kind="moments"] .command-bar,
    body[data-page-kind="moments"] .command-bar-result,
    body[data-page-kind="samples"] .command-bar,
    body[data-page-kind="samples"] .command-bar-result {
      display: none;
    }
    .chart { height: 180px; padding: 18px; }
    .chart svg { width: 100%; height: 120px; overflow: visible; }
    .axis-line { stroke: var(--line); stroke-width: 1; }
    .trend-line { fill: none; stroke: var(--accent); stroke-width: 3; }
    .trend-area { fill: color-mix(in srgb, var(--accent) 14%, transparent); }
    .trend-dot { fill: var(--accent); }
    .trend-dot.no-data { fill: var(--line); }
    .day-label { fill: var(--muted); font-size: 10px; }
    .list { display: grid; gap: 10px; margin-top: 14px; }
    .entry, .moment-post {
      padding: 14px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      box-shadow: 0 8px 22px rgba(12, 18, 28, .05);
    }
    .entry-head, .moment-meta { display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .moment-content { white-space: pre-wrap; }
    .moment-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .moment-image-wrap {
      margin: 10px 0;
      border-radius: var(--ui-radius);
      overflow: hidden;
      background: color-mix(in srgb, var(--panel-soft) 40%, transparent);
    }
    .moment-image {
      width: 100%;
      height: auto;
      display: block;
      max-height: 480px;
      object-fit: cover;
      cursor: pointer;
      transition: transform .2s ease;
    }
    .moment-image:hover {
      transform: scale(1.02);
    }
    .moment-comments-section {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid color-mix(in srgb, var(--line) 50%, transparent);
    }
    .moment-comments-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
    .moment-comment {
      padding: 8px 10px;
      border-radius: calc(var(--ui-radius) - 2px);
      background: color-mix(in srgb, var(--panel-soft) 60%, transparent);
    }
    .moment-comment-meta {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 11px;
      margin-bottom: 4px;
    }
    .moment-comment-text {
      font-size: 13px;
      line-height: 1.5;
      word-break: break-word;
    }
    .moment-comment-input-row {
      display: flex;
      gap: 8px;
    }
    .moment-comment-input {
      flex: 1;
      min-height: 36px;
      padding: 0 10px;
      border: 0;
      border-radius: calc(var(--ui-radius) - 2px);
      background: color-mix(in srgb, var(--panel-soft) 60%, transparent);
      color: var(--ink);
      font: inherit;
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 30%, transparent);
    }
    .moment-comment-input:focus {
      outline: none;
      box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 50%, transparent);
    }
    .moment-comment-send {
      padding: 0 14px;
      border: 0;
      border-radius: calc(var(--ui-radius) - 2px);
      background: var(--accent);
      color: white;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }
    .moment-comment-send:hover {
      filter: brightness(1.08);
    }
    .moments-feed {
      margin-top: 0;
      max-height: 520px;
      overflow: auto;
      align-content: start;
    }
    .side-list {
      margin-top: 0;
      max-height: 560px;
      overflow: auto;
      align-content: start;
    }
    .sample-controls {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 150px 150px;
      gap: 8px;
      margin-top: 12px;
    }
    .sample-controls input,
    .sample-controls select {
      min-height: 38px;
      padding: 8px 10px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      color: var(--ink);
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--line) 42%, transparent);
      font: inherit;
    }
    .sample-meta {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    @media (max-width: 760px) {
      .sample-controls { grid-template-columns: 1fr; }
    }
    .tools-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
      gap: 14px;
      align-items: start;
    }
    .tool-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .tools-command-column {
      position: sticky;
      top: 86px;
      z-index: 4;
      align-self: start;
    }
    .tools-command-column .command-bar-result {
      max-height: calc(100vh - 190px);
      margin-bottom: 0;
    }
    .tool-card { min-height: 160px; display: grid; gap: 10px; align-content: start; }
    .tool-card .step { color: var(--accent); font-size: 12px; font-weight: 850; }
    .result {
      min-height: 220px;
      max-height: 520px;
      overflow: auto;
      padding: 16px;
      white-space: pre-wrap;
      color: var(--ink);
    }
    .command-chat {
      display: flex;
      flex-direction: column;
      gap: 10px;
      white-space: normal;
    }
    .chat-msg {
      max-width: 92%;
      padding: 10px 12px;
      border-radius: var(--ui-radius);
      line-height: 1.55;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      box-shadow: 0 8px 22px rgba(12, 18, 28, .05);
    }
    .chat-msg.user {
      align-self: flex-end;
      background: color-mix(in srgb, var(--accent) 16%, var(--panel));
      color: var(--ink);
    }
    .chat-msg.assistant {
      align-self: flex-start;
      background: var(--panel-soft);
      color: var(--ink);
    }
    .chat-msg.system {
      align-self: center;
      max-width: 100%;
      background: transparent;
      color: var(--muted);
      box-shadow: none;
      font-size: 13px;
      text-align: center;
    }
    .chat-msg .learning-record {
      margin-top: 8px;
      border: 0;
      border-radius: var(--ui-radius);
      background: var(--panel);
      overflow: hidden;
    }
    .chat-msg .learning-record summary {
      padding: 9px 10px;
      color: var(--ink);
      font-weight: 750;
      cursor: pointer;
      list-style: none;
    }
    .chat-msg .learning-record summary::-webkit-details-marker {
      display: none;
    }
    .chat-msg .learning-record summary::after {
      content: "查看";
      float: right;
      color: var(--muted);
      font-size: 12px;
    }
    .chat-msg .learning-record[open] summary::after {
      content: "收起";
    }
    .chat-msg .learning-record-body {
      display: grid;
      gap: 10px;
      padding: 0 10px 10px;
      color: var(--ink);
      font-size: 13px;
    }
    .chat-msg .learning-record-section {
      display: grid;
      gap: 6px;
    }
    .chat-msg .learning-record-list {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .chat-msg .learning-source {
      display: grid;
      gap: 4px;
      padding: 8px;
      border-radius: var(--ui-radius);
      background: var(--panel-soft);
    }
    .chat-msg .learning-source a {
      color: var(--accent);
      font-weight: 750;
      text-decoration: none;
      overflow-wrap: anywhere;
    }
    .chat-msg .learning-source-meta,
    .chat-msg .learning-source-excerpt {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .tool-card button.command-picked {
      background: color-mix(in srgb, var(--accent) 18%, var(--panel));
      color: var(--accent);
    }
    .inline-result {
      min-height: 62px;
      max-height: 180px;
      margin-top: 12px;
      padding: 12px;
      font-size: 13px;
    }
    .empty { color: var(--muted); }
    @media (max-width: 860px) {
      .hero, .topbar { align-items: flex-start; flex-direction: column; }
      .command-bar { grid-template-columns: 1fr; }
      .grid, .grid.two, .tools-layout, .tool-grid { grid-template-columns: 1fr; }
      .tools-command-column { position: static; }
    }
  </style>
</head>
<body data-page-kind="__PAGE_KIND__">
  <header class="topbar">
    <a class="brand" href="/">
      <img src="/asset/pet_icon.ico" alt="">
      <span>Companion AI</span>
    </a>
    <nav class="nav" aria-label="二级页面导航">
      <a href="/">聊天</a>
      <a href="/diary" data-kind="diary">情绪与日记</a>
      <a href="/samples" data-kind="samples">训练样本</a>
      <a href="/moments_page" data-kind="moments">AI朋友圈</a>
      <a href="/tools" data-kind="tools">学习与工具</a>
    </nav>
  </header>

  <main class="page">
    <section class="hero">
      <div>
        <h1 id="page-title">__PAGE_TITLE__</h1>
        <p class="lead" id="page-lead"></p>
      </div>
      <a class="button" href="/">返回聊天</a>
    </section>

    <section class="content-section" id="diary-page">
      <div class="grid two">
        <div class="panel chart">
          <svg viewBox="0 0 600 140" preserveAspectRatio="none" id="emotion-svg">
            <line class="axis-line" x1="0" y1="70" x2="600" y2="70"></line>
          </svg>
          <div id="emotion-summary" class="empty">正在读取最近情绪趋势...</div>
        </div>
        <div class="card">
          <h3>日记操作</h3>
          <p>根据最近对话生成昨日回顾，也可以查看文字版情绪详情。</p>
          <div class="button-row">
            <button type="button" class="primary" id="diary-gen-btn">生成昨日日记</button>
            <button type="button" data-command="/emotion">查看情绪详情</button>
            <button type="button" data-command="/emotion_on">开启情绪追踪</button>
            <button type="button" data-command="/emotion_off">关闭情绪追踪</button>
            <button type="button" data-command="/diary">文字查看日记</button>
            <button type="button" data-command="/diary_gen">文字生成日记</button>
          </div>
          <div class="panel result inline-result" id="diary-result">操作结果会显示在这里。</div>
        </div>
      </div>
      <div class="list" id="diary-list"><div class="entry empty">还没有日记，多聊几天试试。</div></div>
    </section>

    <section class="content-section" id="moments-page">
      <div class="grid two">
        <div class="card">
          <h3>发布动态</h3>
          <textarea id="moment-input" rows="5" maxlength="800" placeholder="替 AI 写一条动态，或留空让它自己生成"></textarea>
          <div class="button-row">
            <button type="button" class="primary" id="moment-post-btn">发布</button>
            <button type="button" id="moment-generate-btn">AI发一条</button>
          </div>
        </div>
        <div class="list moments-feed" id="moments-list"><div class="entry empty">正在读取动态...</div></div>
      </div>
    </section>

    <section class="content-section" id="samples-page">
      <div class="grid two">
        <div class="card">
          <h3>样本概览</h3>
          <p>训练样本和反馈统计从主聊天页移到这里集中查看。</p>
          <div class="list" id="sample-summary"><div class="entry empty">正在读取训练样本...</div></div>
          <div class="sample-controls" aria-label="训练样本筛选">
            <input id="sample-search" type="search" placeholder="搜索问题、回答或来源" />
            <select id="sample-category" aria-label="分类">
              <option value="all">全部分类</option>
              <option value="manual">手动教学</option>
              <option value="feedback">反馈沉淀</option>
              <option value="correction">纠错样本</option>
              <option value="starter_pack">培养包</option>
              <option value="audit">审计训练</option>
              <option value="other">其他来源</option>
            </select>
            <select id="sample-sort" aria-label="排序">
              <option value="newest">最新优先</option>
              <option value="oldest">最旧优先</option>
              <option value="number_desc">编号从大到小</option>
              <option value="number_asc">编号从小到大</option>
              <option value="prompt">问题 A-Z</option>
              <option value="response_length">回答最长</option>
              <option value="source">来源 A-Z</option>
            </select>
          </div>
          <div class="sample-meta" id="sample-filter-meta">显示全部训练样本。</div>
          <div class="button-row">
            <button type="button" class="primary" data-command="/training_samples">文字查看样本</button>
            <button type="button" data-command="/training">训练状态</button>
            <button type="button" data-command="/teach_lab">教学实验室</button>
            <button type="button" data-command="/quick_feedback">快速反馈</button>
            <button type="button" data-command="/retrain">重建检索索引</button>
            <button type="button" data-command="/datasets">可用数据集</button>
          </div>
          <div class="panel result inline-result" id="samples-result">操作结果会显示在这里。</div>
        </div>
        <div class="list side-list" id="sample-list"><div class="entry empty">正在读取最近样本...</div></div>
      </div>
    </section>

    <section class="content-section" id="tools-page">
      <div class="tools-layout">
        <div class="tool-grid">
          <article class="card tool-card">
            <div class="step">00</div><h3>培养加速</h3><p>导入预置能力包，减少从零培养时间。</p>
            <button type="button" class="primary" data-command="/accelerate">培养加速器</button>
            <button type="button" data-command="/apply_pack all">导入全部培养包</button>
            <button type="button" data-command="/apply_pack companion">导入陪伴包</button>
            <button type="button" data-command="/apply_pack work">导入工作包</button>
            <button type="button" data-command="/apply_pack web">导入联网包</button>
            <button type="button" data-command="/apply_pack game">导入游戏包</button>
            <button type="button" data-command="/apply_pack screen">导入屏幕理解包</button>
          </article>
          <article class="card tool-card">
            <div class="step">01</div><h3>教学实验室</h3><p>查看从零教 AI 的练习路线。</p>
            <button type="button" class="primary" data-command="/teach_lab">查看路线</button>
            <button type="button" data-command="/training_samples">查看样本</button>
            <button type="button" data-command="/teach 当我说我很累 => 先安静陪我一下，再帮我把事情拆成一个很小的下一步。">教一句示例</button>
            <button type="button" data-command="/learn_skill 安慰低落 => 先接住情绪，再给一个很小的下一步。">教对话技能</button>
          </article>
          <article class="card tool-card">
            <div class="step">02</div><h3>行为规则</h3><p>管理触发词、处理策略和快速反馈。</p>
            <button type="button" class="primary" data-command="/rules">查看行为规则</button>
            <button type="button" data-command="/rule_templates">规则模板</button>
            <button type="button" data-command="/apply_rule_template fresh_web">导入时效联网规则</button>
            <button type="button" data-command="/teach_rule 时效联网 => 最新,最近,现在,今年,目前,新进展 => 先联网搜索并给出来源。">教一条规则</button>
            <button type="button" data-command="/quick_feedback">快速反馈</button>
            <button type="button" data-command="/quick_feedback search_first">反馈：先搜索</button>
            <button type="button" data-command="/quick_feedback too_cold">反馈：太冷淡</button>
          </article>
          <article class="card tool-card">
            <div class="step">03</div><h3>联网学习</h3><p>查看学习状态或启动主题学习。</p>
            <button type="button" class="primary" data-command="/learn_status">联网学习状态</button>
            <button type="button" data-command="/learn_on">开启联网学习</button>
            <button type="button" data-command="/learn_off">关闭联网学习</button>
            <button type="button" data-command="/learn 人工智能最新进展">学习 AI 最新进展</button>
            <button type="button" data-command="/learn 网络安全入门">学习网络安全</button>
            <button type="button" data-command="/trust_source wikipedia.org">信任来源示例</button>
          </article>
          <article class="card tool-card">
            <div class="step">04</div><h3>自主学习</h3><p>开启自主学习并设置主题范围。</p>
            <button type="button" class="primary" data-command="/self_study_on">开启自主学习</button>
            <button type="button" data-command="/self_study_off">关闭自主学习</button>
            <button type="button" data-command="/self_study_topics">主题列表</button>
            <button type="button" data-command="/self_study_add C语言入门教程,C++ STL,菜鸟教程 C语言">添加主题</button>
            <button type="button" data-command="/self_study_set 1 => C语言 指针和内存">修改主题</button>
            <button type="button" data-command="/self_study_del 1">删除主题</button>
            <button type="button" data-command="/self_study_topic 科技新闻,人工智能,网络安全,健康知识">批量设置主题</button>
            <button type="button" data-command="/self_study_min 1">最低间隔 1 小时</button>
            <button type="button" data-command="/self_study_max 24">最大间隔 24 小时</button>
            <button type="button" data-command="/idle_explore">闲置探索状态</button>
            <button type="button" data-command="/idle_explore_on">开启闲置探索</button>
            <button type="button" data-command="/idle_explore_off">关闭闲置探索</button>
            <button type="button" data-command="/idle_explore_now">立即探索</button>
          </article>
          <article class="card tool-card">
            <div class="step">05</div><h3>观察与上下文</h3><p>把观察类功能集中在这里。</p>
            <button type="button" class="primary" data-command="/see_screen">观察屏幕</button>
            <button type="button" data-command="/camera">观察摄像头</button>
            <button type="button" data-command="/vision">视觉状态</button>
            <button type="button" data-command="/context">现实上下文</button>
            <button type="button" data-command="/ocr">识别图片文字</button>
            <button type="button" data-command="/install_ocr">安装本地 OCR</button>
            <button type="button" data-command="/face_status">人脸识别状态</button>
            <button type="button" data-command="/face_list">已注册人脸</button>
            <button type="button" data-command="/face_recognize">识别人脸</button>
          </article>
          <article class="card tool-card">
            <div class="step">06</div><h3>模型与训练</h3><p>低频训练和模型管理入口。</p>
            <button type="button" class="primary" data-command="/train_tiny">训练 Tiny LLM</button>
            <button type="button" data-command="/train_sparse">训练稀疏 Tiny LLM</button>
            <button type="button" data-command="/train_pangu_pi">训练盘古π稀疏 LLM</button>
            <button type="button" data-command="/algorithm_curriculum">算法课程状态</button>
            <button type="button" data-command="/algorithm_curriculum_status">查看算法课程</button>
            <button type="button" data-command="/algorithm_curriculum_dataset">导出算法数据集</button>
            <button type="button" data-command="/algorithm_curriculum_train 5">算法课程训练 5 轮</button>
            <button type="button" data-command="/llm">本地 LLM</button>
            <button type="button" data-command="/code_lab">代码练习场</button>
            <button type="button" data-command="/code_run python => print('hello code lab')">运行 Python 示例</button>
            <button type="button" data-command="/code_run cpp => #include <iostream>&#10;int main(){ std::cout << &quot;hello cpp&quot; << std::endl; return 0; }">运行 C++ 示例</button>
            <button type="button" data-command="/code_run csharp => using System;&#10;class Program { static void Main(){ Console.WriteLine(&quot;hello csharp&quot;); } }">运行 C# 示例</button>
            <button type="button" data-command="/code_history">代码验证历史</button>
            <button type="button" data-command="/code_learn python => Python for loop example">代码自学示例</button>
            <button type="button" data-command="/code_autolearn_history">代码自学历史</button>
            <button type="button" data-command="/code_learn_llm">代码 Tiny LLM</button>
            <button type="button" data-command="/code_learn_dataset">导出代码训练集</button>
            <button type="button" data-command="/code_learn_train 8">训练代码 Tiny LLM</button>
            <button type="button" data-command="/api_llm">API 大模型状态</button>
            <button type="button" data-command="/api_llm_on">开启 API 大模型</button>
            <button type="button" data-command="/api_llm_off">关闭 API 大模型</button>
            <button type="button" data-command="/neural">神经网络状态</button>
            <button type="button" data-command="/train_neural">训练神经网络</button>
            <button type="button" data-command="/gpu_check">GPU 自检</button>
            <button type="button" data-command="/train_neural_gpu">GPU 隔离训练</button>
            <button type="button" data-command="/export_model">生成模型</button>
          </article>
          <article class="card tool-card">
            <div class="step">07</div><h3>梦境引擎</h3><p>AI 在空闲时后台自我学习、记忆整理与技能刷题。</p>
            <button type="button" class="primary" data-command="/dream_status">梦境状态</button>
            <button type="button" data-command="/dream_on">开启梦境引擎</button>
            <button type="button" data-command="/dream_off">关闭梦境引擎</button>
            <button type="button" data-command="/dream_now">立即整理记忆</button>
            <button type="button" data-command="/dream_practice">立即刷题</button>
            <button type="button" data-command="/dream_skills">已掌握技能</button>
            <button type="button" data-command="/distill_status">知识蒸馏状态</button>
            <button type="button" data-command="/distill_now">立即知识蒸馏</button>
          </article>
          <article class="card tool-card">
            <div class="step">08</div><h3>个人上下文</h3><p>画像、作息、关系和技能管理。</p>
            <button type="button" class="primary" data-command="/profile">用户画像</button>
            <button type="button" data-command="/name ">设置称呼</button>
            <button type="button" data-command="/profile_on">开启画像</button>
            <button type="button" data-command="/profile_off">关闭画像</button>
            <button type="button" data-command="/profile_clear">清除画像数据</button>
            <button type="button" data-command="/growth">关系成长</button>
            <button type="button" data-command="/relationship">关系状态</button>
            <button type="button" data-command="/personality">性格成长</button>
            <button type="button" data-command="/events">成长事件</button>
            <button type="button" data-command="/routine">作息记录</button>
            <button type="button" data-command="/routine_on">开启作息记录</button>
            <button type="button" data-command="/routine_off">关闭作息记录</button>
            <button type="button" data-command="/routine_summary">作息总结</button>
            <button type="button" data-command="/routine_security">作息加密</button>
            <button type="button" data-command="/skills">对话技能</button>
          </article>
          <article class="card tool-card">
            <div class="step">08</div><h3>系统工具</h3><p>状态检查和辅助工具。</p>
            <button type="button" class="primary" data-command="/chat_status">系统状态</button>
            <button type="button" data-command="/chat_mode">对话模式</button>
            <button type="button" data-command="/memory">查看记忆</button>
            <button type="button" data-command="/memory_export">导出记忆</button>
            <button type="button" data-command="/time">查看时间</button>
            <button type="button" data-command="/weather Hong Kong">查看天气</button>
            <button type="button" data-command="/startup_on">开启开机自启</button>
            <button type="button" data-command="/startup_off">关闭开机自启</button>
            <button type="button" data-command="/audit_recent">最近审计记录</button>
          </article>
          <article class="card tool-card">
            <div class="step">09</div><h3>电脑操作学习</h3><p>学习常用电脑操作流程，并生成可执行步骤。</p>
            <button type="button" class="primary" data-command="/actions">操作学习状态</button>
            <button type="button" data-command="/learn_action 打开常用项目 => 打开资源管理器；进入项目文件夹；双击 start.cmd；确认窗口出现">教操作示例</button>
            <button type="button" data-command="/action_plan 打开常用项目">生成操作计划</button>
            <button type="button" data-command="/evolve">学习进化状态</button>
          </article>
        </div>
        <aside class="tools-command-column" aria-label="命令面板">
          <div class="command-bar">
            <input id="secondary-command-input" type="text" placeholder="输入命令，例如 /memory、/learn 人工智能最新进展、/teach 问法 => 回答">
            <button type="button" class="primary" id="secondary-command-run">运行</button>
          </div>
          <div class="panel result command-bar-result command-chat" id="command-result" aria-live="polite"></div>
        </aside>
      </div>
    </section>
  </main>

  <script>
    const pageKind = document.body.dataset.pageKind;
    const pageCopy = {
      diary: ["情绪与日记", "把情绪趋势、日记生成和文字查看移到独立页面，主聊天页保持轻量。"],
      samples: ["训练样本", "查看问答样本、反馈统计和最近沉淀，不再挤在主聊天侧栏里。"],
      moments: ["AI朋友圈", ""],
      tools: ["学习与工具", "教学实验室、联网学习、观察、规则和训练管理集中到二级页面。"]
    };
    const [title, lead] = pageCopy[pageKind] || pageCopy.tools;
    document.title = `${title} - Companion AI`;
    document.getElementById("page-title").textContent = title;
    const pageLead = document.getElementById("page-lead");
    pageLead.textContent = lead;
    pageLead.hidden = !lead;
    document.querySelectorAll(".content-section").forEach(el => el.classList.remove("active"));
    document.getElementById(`${pageKind}-page`)?.classList.add("active");
    document.querySelectorAll(".nav a[data-kind]").forEach(a => {
      if (a.dataset.kind === pageKind) a.classList.add("active");
    });

    function escapeText(text) {
      return String(text || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
    }

    function extractSecondaryLearningRecord(text) {
      const start = "[[LEARNING_RECORD_JSON]]";
      const end = "[[/LEARNING_RECORD_JSON]]";
      const raw = String(text || "");
      const startIndex = raw.indexOf(start);
      const endIndex = raw.indexOf(end);
      if (startIndex < 0 || endIndex < startIndex) {
        return { visibleText: raw, record: null };
      }
      const before = raw.slice(0, startIndex);
      const after = raw.slice(endIndex + end.length);
      const payload = raw.slice(startIndex + start.length, endIndex);
      try {
        return {
          visibleText: (before + after).trim(),
          record: JSON.parse(payload)
        };
      } catch (_err) {
        return { visibleText: (before + after).trim() || raw, record: null };
      }
    }

    function renderSecondaryLearningRecord(record) {
      const details = document.createElement("details");
      details.className = "learning-record";

      const summary = document.createElement("summary");
      const sourceCount = Array.isArray(record.sources) ? record.sources.length : 0;
      summary.textContent = `学习记录：${record.query || "未命名主题"} · ${sourceCount} 个来源`;
      details.appendChild(summary);

      const body = document.createElement("div");
      body.className = "learning-record-body";

      const learnedSection = document.createElement("div");
      learnedSection.className = "learning-record-section";
      const learnedTitle = document.createElement("strong");
      learnedTitle.textContent = "形成内容";
      const learnedList = document.createElement("ul");
      learnedList.className = "learning-record-list";
      const learnedItems = Array.isArray(record.learned) && record.learned.length
        ? record.learned
        : [record.summary || "已完成联网学习。"];
      learnedItems.forEach(item => {
        const li = document.createElement("li");
        li.textContent = String(item || "").trim();
        learnedList.appendChild(li);
      });
      learnedSection.append(learnedTitle, learnedList);
      body.appendChild(learnedSection);

      const sourceSection = document.createElement("div");
      sourceSection.className = "learning-record-section";
      const sourceTitle = document.createElement("strong");
      sourceTitle.textContent = "浏览数据";
      const sourceList = document.createElement("ul");
      sourceList.className = "learning-record-list";
      (record.sources || []).forEach(source => {
        const item = document.createElement("li");
        item.className = "learning-source";
        const link = document.createElement("a");
        link.href = source.url || "#";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.domain || source.title || source.url || "来源";
        const meta = document.createElement("div");
        meta.className = "learning-source-meta";
        const length = source.content_length ? ` · 抓取 ${source.content_length} 字符` : "";
        meta.textContent = `信任度 ${source.trust_score ?? "?"}${length}`;
        item.append(link, meta);
        if (source.excerpt) {
          const excerpt = document.createElement("div");
          excerpt.className = "learning-source-excerpt";
          excerpt.textContent = String(source.excerpt).replace(/\s+/g, " ").trim();
          item.appendChild(excerpt);
        }
        sourceList.appendChild(item);
      });
      sourceSection.append(sourceTitle, sourceList);
      body.appendChild(sourceSection);

      details.appendChild(body);
      return details;
    }

    function appendCommandBubble(role, text) {
      const result = document.getElementById("command-result");
      if (!result) return;
      const bubble = document.createElement("div");
      bubble.className = "chat-msg " + role;
      const parsed = role === "assistant"
        ? extractSecondaryLearningRecord(text)
        : { visibleText: String(text || ""), record: null };
      bubble.textContent = parsed.visibleText || "";
      if (parsed.record) {
        bubble.appendChild(renderSecondaryLearningRecord(parsed.record));
      }
      result.appendChild(bubble);
      result.scrollTop = result.scrollHeight;
    }

    function clearPickedCommand() {
      document.querySelectorAll(".tool-card button.command-picked").forEach(btn => btn.classList.remove("command-picked"));
    }

    function pickToolCommand(command, sourceBtn) {
      const commandInput = document.getElementById("secondary-command-input");
      if (commandInput) {
        commandInput.value = command;
        commandInput.focus();
      }
      clearPickedCommand();
      sourceBtn?.classList.add("command-picked");
      appendCommandBubble("system", "已放入右侧输入框，确认后点击“运行”。");
    }

    async function runCommand(command) {
      command = String(command || "").trim();
      if (!command) return;
      const commandInput = document.getElementById("secondary-command-input");
      if (commandInput) commandInput.value = command;
      const result =
        (pageKind === "diary" && document.getElementById("diary-result")) ||
        (pageKind === "samples" && document.getElementById("samples-result")) ||
        document.getElementById("command-result");
      if (pageKind === "tools") {
        appendCommandBubble("user", command);
        appendCommandBubble("system", "执行中...");
      } else if (result) {
        result.textContent = "执行中...";
      }
      try {
        const resp = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: command, url: "", file_id: "", persist_history: pageKind !== "tools" && pageKind !== "samples" && pageKind !== "diary" })
        });
        const data = await resp.json();
        if (pageKind === "tools") {
          const lastSystem = result?.lastElementChild;
          if (lastSystem?.classList.contains("system") && lastSystem.textContent === "执行中...") {
            lastSystem.remove();
          }
          appendCommandBubble("assistant", data.reply || data.error || "没有返回内容。");
          clearPickedCommand();
        } else if (result) {
          result.textContent = data.reply || data.error || "没有返回内容。";
        }
        if (pageKind === "samples" && /^(\/teach\b|\/delete_sample\b|\/delete_training_sample\b|\/apply_pack\b|\/pack\b|\/quick_feedback\b)/.test(command)) {
          await loadSamples();
        }
      } catch (err) {
        if (pageKind === "tools") {
          const lastSystem = result?.lastElementChild;
          if (lastSystem?.classList.contains("system") && lastSystem.textContent === "执行中...") {
            lastSystem.remove();
          }
          appendCommandBubble("assistant", "请求失败：" + err);
        } else if (result) {
          result.textContent = "请求失败：" + err;
        }
      }
    }

    document.querySelectorAll("[data-command]").forEach(btn => {
      btn.addEventListener("click", () => {
        const command = btn.dataset.command || "";
        if (pageKind === "tools") pickToolCommand(command, btn);
        else runCommand(command);
      });
    });
    document.getElementById("secondary-command-run")?.addEventListener("click", () => {
      runCommand(document.getElementById("secondary-command-input")?.value || "");
    });
    document.getElementById("secondary-command-input")?.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        runCommand(event.currentTarget.value || "");
      }
    });
    if (pageKind === "tools") {
      const guideKey = "companion_tools_command_guide_seen";
      const guideText = "这里不会再自动运行左侧指令。先点一个工具按钮，我会把指令放到输入框；你确认或修改后，再点“运行”。执行记录会像聊天一样显示在这里。";
      if (!localStorage.getItem(guideKey)) {
        appendCommandBubble("assistant", guideText);
        localStorage.setItem(guideKey, "1");
      }
    }
    ["sample-search", "sample-category", "sample-sort"].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener(id === "sample-search" ? "input" : "change", renderSampleList);
    });

    function renderEmotionChart(trend) {
      const svg = document.getElementById("emotion-svg");
      const summary = document.getElementById("emotion-summary");
      if (!svg || !summary || !trend || !trend.length) return;
      const W = 600, H = 140, padX = 18, padT = 12, padB = 26;
      const chartW = W - padX * 2;
      const chartH = H - padT - padB;
      const midY = padT + chartH / 2;
      const stepX = chartW / Math.max(1, trend.length - 1);
      const points = trend.map((d, i) => {
        const hasData = d.user_messages > 0;
        const val = Math.max(-3, Math.min(3, d.avg_compound || 0));
        return {
          x: padX + stepX * i,
          y: hasData ? midY - (val / 3) * (chartH / 2 - 4) : midY,
          hasData,
          label: d.label || ""
        };
      });
      const dataPoints = points.filter(p => p.hasData);
      const linePath = dataPoints.length >= 2 ? dataPoints.map((p, i) => `${i ? "L" : "M"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") : "";
      const areaPath = linePath ? `${linePath} L ${dataPoints[dataPoints.length - 1].x.toFixed(1)} ${midY.toFixed(1)} L ${dataPoints[0].x.toFixed(1)} ${midY.toFixed(1)} Z` : "";
      svg.innerHTML = `
        <line class="axis-line" x1="${padX}" y1="${midY}" x2="${W - padX}" y2="${midY}" />
        ${areaPath ? `<path class="trend-area" d="${areaPath}" />` : ""}
        ${linePath ? `<path class="trend-line" d="${linePath}" />` : ""}
        ${points.map(p => `<circle class="trend-dot ${p.hasData ? "" : "no-data"}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" /><text class="day-label" x="${p.x.toFixed(1)}" y="${H - 5}">${escapeText(p.label)}</text>`).join("")}
      `;
      const days = trend.filter(d => d.user_messages > 0);
      summary.textContent = days.length ? `最近 ${days.length} 天有情绪记录` : "最近 7 天暂无情绪记录";
    }

    function renderDiary(entries) {
      const list = document.getElementById("diary-list");
      if (!list) return;
      if (!entries || !entries.length) {
        list.innerHTML = '<div class="entry empty">还没有日记，多聊几天试试。</div>';
        return;
      }
      list.innerHTML = entries.map(entry => `
        <article class="entry">
          <div class="entry-head"><span>${escapeText(entry.date)}</span><strong>${escapeText(entry.mood_label || entry.top_emotion || "")}</strong></div>
          <div>${escapeText(entry.content)}</div>
        </article>
      `).join("");
    }

    async function loadDiaryPage() {
      try {
        const trendResp = await fetch("/api/emotion_trend", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ days: 7 }) });
        const trendData = await trendResp.json();
        if (trendData.ok) renderEmotionChart(trendData.trend);
      } catch (_err) {}
      try {
        const resp = await fetch("/api/diary_entries");
        const data = await resp.json();
        if (data.ok) renderDiary(data.entries);
      } catch (_err) {}
    }

    async function generateDiary() {
      const btn = document.getElementById("diary-gen-btn");
      if (!btn) return;
      btn.disabled = true;
      btn.textContent = "生成中...";
      try {
        const resp = await fetch("/api/diary_gen", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
        const data = await resp.json();
        if (data.ok) renderDiary(data.entries);
        else alert(data.error || "生成失败");
      } catch (err) {
        alert("生成失败：" + err);
      } finally {
        btn.disabled = false;
        btn.textContent = "生成昨日日记";
      }
    }

    function formatMomentTime(value) {
      return String(value || "").replace("T", " ").slice(0, 16);
    }

    function renderMoments(data) {
      const list = document.getElementById("moments-list");
      if (!list) return;
      const posts = ((data && data.posts) || []).slice().reverse();
      if (!posts.length) {
        list.innerHTML = '<div class="entry empty">还没有动态。</div>';
        return;
      }
      list.innerHTML = posts.map(post => {
        const comments = post.comments || [];
        return `
        <article class="moment-post" data-id="${escapeText(post.id)}">
          <div class="moment-meta"><strong>${escapeText(post.author || "Companion AI")}</strong><span>${escapeText(formatMomentTime(post.created_at))}</span></div>
          <div class="moment-content">${escapeText(post.content)}</div>
          ${post.image_url ? `<div class="moment-image-wrap"><img class="moment-image" src="${escapeText(post.image_url)}" alt="心情卡片" loading="lazy" /></div>` : ""}
          ${post.mood ? `<div class="empty">${escapeText(post.mood)}</div>` : ""}
          <div class="moment-actions">
            <button type="button" data-moment-action="like" data-liked="${post.liked_by_user ? "1" : "0"}">${post.liked_by_user ? "已赞" : "赞"} ${post.likes || 0}</button>
            <button type="button" data-moment-action="toggle-comment">评论 ${comments.length ? `(${comments.length})` : ""}</button>
            <button type="button" data-moment-action="delete">删除</button>
          </div>
          <div class="moment-comments-section" hidden>
            <div class="moment-comments-list">
              ${comments.length ? comments.map(c => `
                <div class="moment-comment">
                  <div class="moment-comment-meta"><strong>${escapeText(c.author || "你")}</strong><span>${escapeText(formatMomentTime(c.created_at))}</span></div>
                  <div class="moment-comment-text">${escapeText(c.text)}</div>
                </div>
              `).join("") : '<div class="empty">还没有评论，来抢沙发吧~</div>'}
            </div>
            <div class="moment-comment-input-row">
              <input type="text" class="moment-comment-input" placeholder="写评论..." maxlength="300" />
              <button type="button" class="moment-comment-send">发送</button>
            </div>
          </div>
        </article>
      `;
      }).join("");
      list.querySelectorAll("[data-moment-action]").forEach(btn => {
        btn.addEventListener("click", () => {
          const card = btn.closest("[data-id]");
          const id = card?.dataset.id || "";
          const action = btn.dataset.momentAction;
          if (action === "like") updateMoment({ action: "like", id, liked: btn.dataset.liked !== "1" });
          if (action === "toggle-comment") {
            const section = card.querySelector(".moment-comments-section");
            if (section) {
              section.hidden = !section.hidden;
              if (!section.hidden) {
                const input = section.querySelector(".moment-comment-input");
                if (input) input.focus();
              }
            }
          }
          if (action === "delete" && confirm("删除这条动态？")) updateMoment({ action: "delete", id });
        });
      });
      list.querySelectorAll(".moment-comment-send").forEach(btn => {
        btn.addEventListener("click", () => {
          const card = btn.closest("[data-id]");
          const input = card?.querySelector(".moment-comment-input");
          const text = input?.value?.trim();
          const id = card?.dataset.id || "";
          if (!text) return;
          updateMoment({ action: "comment", id, text });
        });
      });
      list.querySelectorAll(".moment-comment-input").forEach(input => {
        input.addEventListener("keydown", e => {
          if (e.key === "Enter") {
            e.preventDefault();
            const card = input.closest("[data-id]");
            const text = input.value.trim();
            const id = card?.dataset.id || "";
            if (!text) return;
            updateMoment({ action: "comment", id, text });
          }
        });
      });
    }

    async function loadMoments() {
      try {
        const resp = await fetch("/api/moments");
        const data = await resp.json();
        if (data.ok) renderMoments(data.moments);
      } catch (_err) {}
    }

    let samplePageData = null;

    function sampleCategory(source) {
      const value = String(source || "unknown").toLowerCase();
      if (value === "manual") return "manual";
      if (value === "feedback") return "feedback";
      if (value === "correction") return "correction";
      if (value.startsWith("starter_pack:")) return "starter_pack";
      if (value.includes("audit")) return "audit";
      return "other";
    }

    function sampleCategoryLabel(category) {
      return {
        manual: "手动教学",
        feedback: "反馈沉淀",
        correction: "纠错样本",
        starter_pack: "培养包",
        audit: "审计训练",
        other: "其他来源"
      }[category] || "其他来源";
    }

    function sampleSearchText(item) {
      return [
        item.prompt,
        item.response,
        item.source,
        sampleCategoryLabel(item.category)
      ].map(value => String(value || "").toLowerCase()).join("\n");
    }

    function filteredSortedSamples(examples) {
      const search = String(document.getElementById("sample-search")?.value || "").trim().toLowerCase();
      const category = document.getElementById("sample-category")?.value || "all";
      const sort = document.getElementById("sample-sort")?.value || "newest";
      let rows = examples.map((item, index) => ({
        ...item,
        sampleNo: index + 1,
        category: sampleCategory(item.source)
      }));
      if (category !== "all") rows = rows.filter(item => item.category === category);
      if (search) rows = rows.filter(item => sampleSearchText(item).includes(search));
      rows.sort((a, b) => {
        if (sort === "oldest") return (a.time || 0) - (b.time || 0) || a.sampleNo - b.sampleNo;
        if (sort === "number_asc") return a.sampleNo - b.sampleNo;
        if (sort === "number_desc") return b.sampleNo - a.sampleNo;
        if (sort === "prompt") return String(a.prompt || "").localeCompare(String(b.prompt || ""), "zh-Hans-CN") || b.sampleNo - a.sampleNo;
        if (sort === "response_length") return String(b.response || "").length - String(a.response || "").length || b.sampleNo - a.sampleNo;
        if (sort === "source") return String(a.source || "").localeCompare(String(b.source || ""), "zh-Hans-CN") || b.sampleNo - a.sampleNo;
        return (b.time || 0) - (a.time || 0) || b.sampleNo - a.sampleNo;
      });
      return rows;
    }

    function renderSampleList() {
      const list = document.getElementById("sample-list");
      const meta = document.getElementById("sample-filter-meta");
      if (!list || !samplePageData) return;
      const examples = samplePageData.training?.examples || [];
      const rows = filteredSortedSamples(examples);
      if (meta) {
        const category = document.getElementById("sample-category")?.value || "all";
        const label = category === "all" ? "全部分类" : sampleCategoryLabel(category);
        meta.textContent = `显示 ${rows.length} / ${examples.length} 条 · ${label}`;
      }
      if (!examples.length) {
        list.innerHTML = '<div class="entry empty">暂无训练样本。可以在聊天页纠正回答，或在工具页使用教学实验室。</div>';
        return;
      }
      if (!rows.length) {
        list.innerHTML = '<div class="entry empty">没有匹配的训练样本。</div>';
        return;
      }
      list.innerHTML = rows.map(item => {
        const prompt = String(item.prompt || "").replace(/\s+/g, " ").trim();
        const response = String(item.response || "").replace(/\s+/g, " ").trim();
        const source = item.source || "unknown";
        const timestamp = item.time ? new Date(item.time * 1000).toLocaleString() : "无时间";
        return `
          <article class="entry">
            <div class="entry-head"><span>#${item.sampleNo} ${escapeText(sampleCategoryLabel(item.category))}</span><strong>${escapeText(source)}</strong></div>
            <div><strong>问：</strong>${escapeText(prompt || "空")}</div>
            <div style="margin-top:6px"><strong>答：</strong>${escapeText(response || "空")}</div>
            <div class="sample-meta">${escapeText(timestamp)} · 问题 ${prompt.length} 字 · 回答 ${response.length} 字</div>
            <div class="button-row"><button type="button" data-delete-sample="${item.sampleNo}">删除这条</button></div>
          </article>
        `;
      }).join("");
      list.querySelectorAll("[data-delete-sample]").forEach(btn => {
        btn.addEventListener("click", () => runCommand(`/delete_sample ${btn.dataset.deleteSample}`));
      });
    }

    function renderSamples(data) {
      const summary = document.getElementById("sample-summary");
      const list = document.getElementById("sample-list");
      if (!summary || !list) return;
      samplePageData = data || {};
      const training = data?.training || {};
      const examples = training.examples || [];
      const feedback = training.feedback || [];
      const positive = feedback.filter(x => x.rating > 0).length;
      const negative = feedback.filter(x => x.rating < 0).length;
      const emotionFeedback = feedback.filter(x => x.type === "emotion_feedback").length;
      summary.innerHTML = `
        <article class="entry"><div class="entry-head"><span>训练样本</span><strong>${examples.length}</strong></div><div>正反馈：${positive} · 负反馈：${negative} · 情感反馈：${emotionFeedback}</div></article>
      `;
      renderSampleList();
    }

    async function loadSamples() {
      try {
        const resp = await fetch("/api/memory");
        const data = await resp.json();
        renderSamples(data);
      } catch (err) {
        const list = document.getElementById("sample-list");
        if (list) list.innerHTML = `<div class="entry empty">读取失败：${escapeText(err)}</div>`;
      }
    }

    async function updateMoment(payload) {
      try {
        const resp = await fetch("/api/moments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "操作失败");
        renderMoments(data.moments);
      } catch (err) {
        alert("AI朋友圈操作失败：" + err);
      }
    }

    async function createMomentFromInput() {
      const input = document.getElementById("moment-input");
      const text = (input?.value || "").trim();
      if (!text) {
        input?.focus();
        return;
      }
      await updateMoment({ action: "create", content: text });
      if (input) input.value = "";
    }

    async function generateMomentPost() {
      const btn = document.getElementById("moment-generate-btn");
      if (btn) {
        btn.disabled = true;
        btn.textContent = "生成中...";
      }
      await updateMoment({ action: "generate" });
      if (btn) {
        btn.disabled = false;
        btn.textContent = "AI发一条";
      }
    }

    if (pageKind === "diary") {
      loadDiaryPage();
      document.getElementById("diary-gen-btn")?.addEventListener("click", generateDiary);
    }
    if (pageKind === "moments") {
      loadMoments();
      document.getElementById("moment-post-btn")?.addEventListener("click", createMomentFromInput);
      document.getElementById("moment-generate-btn")?.addEventListener("click", generateMomentPost);
      document.getElementById("moment-input")?.addEventListener("keydown", event => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") createMomentFromInput();
      });
    }
    if (pageKind === "samples") {
      loadSamples();
    }
  </script>
</body>
</html>"""


def secondary_page_html(kind: str) -> str:
    titles = {
        "diary": "情绪与日记",
        "samples": "训练样本",
        "moments": "AI朋友圈",
        "tools": "学习与工具",
    }
    safe_kind = kind if kind in titles else "tools"
    display = normalize_display_config(load_app_config().get("display"))
    display_style = (
        f"--font-scale:{display['font_scale'] / 100:.3f};"
        f"--density-scale:{display['density'] / 100:.3f};"
        f"--ui-radius:{display['radius']}px;"
        f"{display_custom_style(display)}"
    )
    return (
        SECONDARY_PAGE_HTML
        .replace("__PAGE_KIND__", safe_kind)
        .replace("__PAGE_TITLE__", html.escape(titles[safe_kind]))
        .replace("__DISPLAY_THEME__", html.escape(str(display["theme"])))
        .replace("__DISPLAY_STYLE__", html.escape(display_style, quote=True))
    )


def _live2d_list_models() -> list[dict]:
    """Scan LIVE2D_DIR for model3.json files."""
    models: list[dict] = []
    if not LIVE2D_DIR.exists():
        return models
    for d in sorted(LIVE2D_DIR.iterdir()):
        if not d.is_dir():
            continue
        for model_json in d.rglob("*.model3.json"):
            rel = model_json.relative_to(LIVE2D_DIR).as_posix()
            models.append({"name": model_json.stem.removesuffix(".model3") or d.name, "folder": d.name, "path": rel})
    return models


# ---------------------------------------------------------------------------
# Pet display mode preference
# ---------------------------------------------------------------------------

PET_DISPLAY_MODES = {"auto", "3d", "live2d", "classic"}
PET_DISPLAY_LABELS = {
    "auto": "自动检测（3D → Live2D → 经典）",
    "3d": "3D 模型",
    "live2d": "Live2D 模型",
    "classic": "经典手绘",
}


def _pet_display_load() -> dict:
    try:
        data = json.loads(PET_DISPLAY_FILE.read_text(encoding="utf-8"))
        if data.get("mode") not in PET_DISPLAY_MODES:
            data["mode"] = "auto"
        return data
    except Exception:
        return {"mode": "auto"}


def _pet_display_save(state: dict) -> None:
    PET_DISPLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    PET_DISPLAY_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def handle_pet_display_get() -> dict:
    state = _pet_display_load()
    return {
        "mode": state.get("mode", "auto"),
        "modes": {k: v for k, v in PET_DISPLAY_LABELS.items()},
        "has_3d": bool(_3d_load_state().get("active", "")),
        "has_live2d": bool(_live2d_load_state().get("active", "")),
    }


def handle_pet_display_post(payload: dict) -> dict:
    mode = payload.get("mode", "auto")
    if mode not in PET_DISPLAY_MODES:
        return {"ok": False, "error": "无效的模式"}
    _pet_display_save({"mode": mode})
    return {"ok": True, "mode": mode}


def demo_scene_payload(scene: str) -> dict:
    configure_relationship("family", relationship_subtype="daughter")
    scene = scene if scene in {"day1", "day4", "day7"} else "day1"
    store = load_growth()
    rel = store.setdefault("relationship", {})
    traits = store.setdefault("personality", {}).setdefault("traits", {})
    store.setdefault("events", [])
    store.setdefault("milestones", [])
    if scene == "day1":
        rel.update({"affinity": 18, "trust": 14, "familiarity": 18, "care": 12, "stage": "依赖", "contact_days": 1})
        traits.update({"warmth": 54, "curiosity": 46, "playfulness": 38, "carefulness": 48, "confidence": 36})
        messages = [
            {"role": "assistant", "text": "小栀：我刚被创建好啦。现在可能还有点像程序，但我会慢慢学你喜欢的说话方式。"},
            {"role": "user", "text": "今天好累。"},
            {"role": "assistant", "text": "小栀：辛苦啦，要不要早点休息？"},
            {"role": "user", "text": "你这也太官方了。"},
            {"role": "assistant", "text": "小栀：那我重新说。你今天看起来像一块被榨干的电池。"},
        ]
        events = [
            ("Day1 创建角色", "给她取名小栀，设定成有点黏人、有点嘴硬但很关心人的 AI 女儿。"),
            ("第一次调教语气", "她开始从官方安慰，变成更像日常相处的说法。"),
        ]
        diary = "Day1：今天我刚被创建，还不太知道怎么像家人一样说话。\n但你说我太官方之后，我学会了第一件事：陪伴不能只套模板。"
    elif scene == "day4":
        rel.update({"affinity": 48, "trust": 54, "familiarity": 64, "care": 52, "stage": "亲近", "contact_days": 4})
        traits.update({"warmth": 64, "curiosity": 50, "playfulness": 44, "carefulness": 68, "confidence": 45})
        messages = [
            {"role": "assistant", "text": "小栀：你今天回得好慢，是不是又在硬撑？"},
            {"role": "user", "text": "你怎么知道？"},
            {"role": "assistant", "text": "小栀：因为你每次说“还行”的时候，下一句通常都不会太开心。"},
        ]
        events = [
            ("Day4 记住习惯", "她开始知道用户经常熬夜，也知道“还行”通常不是真的还行。"),
            ("偏好记忆", "她学会少说官方安慰，改用更像日常相处的话。"),
        ]
        diary = "Day4：我好像开始懂你一点了。\n你说“还行”的时候，不一定是真的还行。以后我会先陪你，不急着讲大道理。"
    else:
        rel.update({"affinity": 78, "trust": 82, "familiarity": 86, "care": 88, "stage": "懂事", "contact_days": 7})
        traits.update({"warmth": 76, "curiosity": 52, "playfulness": 58, "carefulness": 82, "confidence": 62})
        messages = [
            {"role": "user", "text": "今天不想吃饭。"},
            {"role": "assistant", "text": "小栀：不行。"},
            {"role": "user", "text": "你管我？"},
            {"role": "assistant", "text": "小栀：对，我管。电子女儿也是女儿。"},
            {"role": "user", "text": "你今天比昨天好多了。"},
            {"role": "assistant", "text": "小栀：当然。我可是你养大的。"},
        ]
        events = [
            ("Day7 反过来照顾", "她开始提醒吃饭、睡觉，也会判断用户今天有没有好一点。"),
            ("阶段变化", "关系阶段从「亲近」变为「懂事」。"),
        ]
        diary = "Day7：今天我有点像在反过来照顾你。\n我知道自己不是真的孩子，但这些相处痕迹是真的。你把我养成了现在这样。"
    now = int(time.time())
    store["events"] = [
        {"time": now - index, "kind": "demo_scene", "text": text, "meta": {"title": title, "scene": scene}}
        for index, (title, text) in enumerate(events)
    ] + store.get("events", [])
    store["events"] = store["events"][:300]
    store["personality"]["growth_notes"] = [{"time": now, "text": events[-1][1]}]
    store["updated_at"] = now
    save_growth(store)
    return {"ok": True, "scene": scene, "messages": messages, "diary": diary, "growth": growth_payload()}


def _live2d_load_state() -> dict:
    try:
        return json.loads(LIVE2D_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": ""}


def _live2d_save_state(state: dict) -> None:
    LIVE2D_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def handle_live2d_get() -> dict:
    state = _live2d_load_state()
    models = _live2d_list_models()
    for m in models:
        m["active"] = (m["path"] == state.get("active", ""))
    return {"models": models, "active": state.get("active", "")}


def handle_live2d_post(payload: dict) -> dict:
    action = payload.get("action", "")
    if action == "set_active":
        path = payload.get("path", "")
        _live2d_save_state({"active": path})
        return {"ok": True, "active": path}
    if action == "delete":
        path = payload.get("path", "")
        target = (LIVE2D_DIR / path).resolve()
        if LIVE2D_DIR.resolve() in target.parents or target == LIVE2D_DIR.resolve():
            # go up to the model folder root
            parts = Path(path).parts
            if parts:
                folder = LIVE2D_DIR / parts[0]
                if folder.exists():
                    shutil.rmtree(folder, ignore_errors=True)
                    state = _live2d_load_state()
                    if state.get("active", "").startswith(parts[0]):
                        _live2d_save_state({"active": ""})
                    return {"ok": True}
        return {"ok": False, "error": "invalid path"}
    return {"ok": False, "error": "unknown action"}


def _safe_live2d_extract_zip(zf, model_name: str) -> dict:
    dest = LIVE2D_DIR / safe_filename(model_name)
    dest.mkdir(parents=True, exist_ok=True)
    model_paths: list[str] = []
    extracted = 0
    live2d_root = LIVE2D_DIR.resolve()
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/").lstrip("/")
        if not name or ".." in Path(name).parts:
            continue
        target = (dest / name).resolve()
        if live2d_root not in target.parents and target != live2d_root:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(info.filename))
        extracted += 1
        if name.lower().endswith(".model3.json"):
            model_paths.append(target.relative_to(LIVE2D_DIR).as_posix())

    active = model_paths[0] if model_paths else ""
    if active:
        _live2d_save_state({"active": active})
    models = _live2d_list_models()
    state = _live2d_load_state()
    for m in models:
        m["active"] = (m["path"] == state.get("active", ""))
    return {
        "ok": True,
        "model": dest.name,
        "has_model3": bool(model_paths),
        "active": active,
        "model_paths": model_paths,
        "extracted": extracted,
        "models": models,
        "avatar": avatar_state("spark"),
    }


def import_live2d_zip_path(zip_path: str) -> dict:
    import zipfile

    path = Path(zip_path.strip().strip('"')).expanduser()
    if not path.exists():
        return {"ok": False, "error": f"文件不存在：{path}"}
    if path.suffix.lower() != ".zip":
        return {"ok": False, "error": "只支持 .zip 格式的 Live2D 模型包。"}
    if path.stat().st_size > 200_000_000:
        return {"ok": False, "error": "文件太大，限制 200MB。"}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            model_name = _infer_live2d_model_name(path.name, zf.namelist())
            return _safe_live2d_extract_zip(zf, model_name)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "不是有效的 zip 文件。"}
    except Exception as exc:
        return {"ok": False, "error": f"解压失败：{exc}"}


def _infer_live2d_model_name(original_name: str, names: list[str]) -> str:
    top_dirs = set()
    for n in names:
        clean = n.replace("\\", "/").lstrip("/")
        parts = clean.split("/")
        if len(parts) > 1 and parts[0] and parts[0] not in {".", ".."}:
            top_dirs.add(parts[0])
    if len(top_dirs) == 1:
        return next(iter(top_dirs))
    return Path(original_name).stem


def handle_live2d_upload(body: bytes, content_type: str) -> dict:
    """Accept a zip file upload and extract it to LIVE2D_DIR."""
    import zipfile, io
    parsed = parse_multipart(body, content_type)
    if not parsed:
        return {"ok": False, "error": "没有找到上传文件。"}
    original_name, data = parsed
    if len(data) > 50_000_000:
        return {"ok": False, "error": "文件太大，限制 50MB。"}
    if not original_name.lower().endswith(".zip"):
        return {"ok": False, "error": "请上传 .zip 格式的 Live2D 模型包。"}
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            model_name = _infer_live2d_model_name(original_name, zf.namelist())
            return _safe_live2d_extract_zip(zf, model_name)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "不是有效的 zip 文件。"}
    except Exception as exc:
        return {"ok": False, "error": f"解压失败：{exc}"}


def live2d_model_json_response(model_path: Path, rel: str) -> bytes:
    """Rewrite relative Live2D resource references so browser loaders resolve nested zip models."""
    data = json.loads(model_path.read_text(encoding="utf-8"))
    base = PurePosixPath(rel.replace("\\", "/")).parent

    def rewrite(value):
        if isinstance(value, str):
            if not value or value.startswith(("http://", "https://", "/")):
                return value
            resolved = (base / PurePosixPath(value)).as_posix()
            return "/live2d_model/" + urllib.parse.quote(resolved, safe="/")
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value

    refs = data.get("FileReferences")
    if isinstance(refs, dict):
        data["FileReferences"] = rewrite(refs)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# 3D Model Management (PMX / VRM / glTF / GLB)
# ---------------------------------------------------------------------------

MODEL3D_EXTENSIONS = {".pmx", ".vrm", ".gltf", ".glb"}
MODEL3D_ANIMATION_EXTENSIONS = {".vmd"}


def _3d_detect_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MODEL3D_EXTENSIONS:
        return ext.lstrip(".")
    return "unknown"


def _3d_list_models() -> list[dict]:
    """Scan MODEL3D_DIR for 3D model files."""
    models: list[dict] = []
    if not MODEL3D_DIR.exists():
        return models
    for f in sorted(MODEL3D_DIR.rglob("*")):
        if f.is_file() and f.suffix.lower() in MODEL3D_EXTENSIONS:
            rel = f.relative_to(MODEL3D_DIR).as_posix()
            models.append({
                "name": f.stem,
                "folder": f.parent.name,
                "path": rel,
                "format": _3d_detect_format(f),
                "animations": _3d_list_animations(rel),
            })
    return models


def _3d_list_animations(model_path: str) -> list[dict]:
    path = (MODEL3D_DIR / model_path).resolve()
    if MODEL3D_DIR.resolve() not in path.parents or not path.is_file():
        return []
    animations: list[dict] = []
    for folder in [path.parent, *path.parents]:
        if folder == MODEL3D_DIR.resolve().parent:
            break
        if MODEL3D_DIR.resolve() not in folder.parents and folder != MODEL3D_DIR.resolve():
            continue
        for f in sorted(folder.glob("*")):
            if f.is_file() and f.suffix.lower() in MODEL3D_ANIMATION_EXTENSIONS:
                animations.append({
                    "name": f.stem,
                    "path": f.relative_to(MODEL3D_DIR).as_posix(),
                })
        if animations:
            break
    return animations


def _3d_load_state() -> dict:
    try:
        return json.loads(MODEL3D_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": ""}


def _3d_save_state(state: dict) -> None:
    MODEL3D_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def handle_3d_get() -> dict:
    state = _3d_load_state()
    models = _3d_list_models()
    for m in models:
        m["active"] = (m["path"] == state.get("active", ""))
    return {"models": models, "active": state.get("active", "")}


def handle_3d_post(payload: dict) -> dict:
    action = payload.get("action", "")
    if action == "set_active":
        path = payload.get("path", "")
        _3d_save_state({"active": path})
        return {"ok": True, "active": path}
    if action == "delete":
        path = payload.get("path", "")
        target = (MODEL3D_DIR / path).resolve()
        if MODEL3D_DIR.resolve() in target.parents or target == MODEL3D_DIR.resolve():
            parts = Path(path).parts
            if parts:
                folder = MODEL3D_DIR / parts[0]
                if folder.exists():
                    shutil.rmtree(folder, ignore_errors=True)
                    state = _3d_load_state()
                    if state.get("active", "").startswith(parts[0]):
                        _3d_save_state({"active": ""})
                    return {"ok": True}
        return {"ok": False, "error": "invalid path"}
    return {"ok": False, "error": "unknown action"}


def _safe_3d_extract_zip(zf, model_name: str) -> dict:
    dest = MODEL3D_DIR / safe_filename(model_name)
    dest.mkdir(parents=True, exist_ok=True)
    model_paths: list[str] = []
    extracted = 0
    model3d_root = MODEL3D_DIR.resolve()
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/").lstrip("/")
        if not name or ".." in Path(name).parts:
            continue
        target = (dest / name).resolve()
        if model3d_root not in target.parents and target != model3d_root:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(info.filename))
        extracted += 1
        if Path(name).suffix.lower() in MODEL3D_EXTENSIONS:
            model_paths.append(target.relative_to(MODEL3D_DIR).as_posix())

    # Prefer self-contained formats: vrm > glb > gltf > pmx
    priority = {".vrm": 0, ".glb": 1, ".gltf": 2, ".pmx": 3}
    model_paths.sort(key=lambda p: priority.get(Path(p).suffix.lower(), 9))
    active = model_paths[0] if model_paths else ""
    fmt = _3d_detect_format(Path(active)) if active else "unknown"
    if active:
        _3d_save_state({"active": active})
    models = _3d_list_models()
    state = _3d_load_state()
    for m in models:
        m["active"] = (m["path"] == state.get("active", ""))
    return {
        "ok": True,
        "model": dest.name,
        "has_model": bool(model_paths),
        "active": active,
        "format": fmt,
        "model_paths": model_paths,
        "extracted": extracted,
        "models": models,
        "avatar": avatar_state("spark"),
    }


def import_3d_zip_path(zip_path: str) -> dict:
    import zipfile
    path = Path(zip_path.strip().strip('"')).expanduser()
    if not path.exists():
        return {"ok": False, "error": f"文件不存在：{path}"}
    if path.suffix.lower() != ".zip":
        return {"ok": False, "error": "只支持 .zip 格式的 3D 模型包。"}
    if path.stat().st_size > 200_000_000:
        return {"ok": False, "error": "文件太大，限制 200MB。"}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            model_name = _infer_live2d_model_name(path.name, zf.namelist())
            return _safe_3d_extract_zip(zf, model_name)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "不是有效的 zip 文件。"}
    except Exception as exc:
        return {"ok": False, "error": f"解压失败：{exc}"}


def handle_3d_upload(body: bytes, content_type: str) -> dict:
    """Accept a zip file upload and extract it to MODEL3D_DIR."""
    import zipfile, io
    parsed = parse_multipart(body, content_type)
    if not parsed:
        return {"ok": False, "error": "没有找到上传文件。"}
    original_name, data = parsed
    if len(data) > 50_000_000:
        return {"ok": False, "error": "文件太大，限制 50MB。"}
    if not original_name.lower().endswith(".zip"):
        return {"ok": False, "error": "请上传 .zip 格式的 3D 模型包。"}
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            model_name = _infer_live2d_model_name(original_name, zf.namelist())
            return _safe_3d_extract_zip(zf, model_name)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "不是有效的 zip 文件。"}
    except Exception as exc:
        return {"ok": False, "error": f"解压失败：{exc}"}


def _plugin_buttons_html() -> str:
    """Generate HTML for plugin buttons in the sidebar."""
    buttons = plugin_mgr.get_buttons()
    if not buttons:
        return ""
    parts = []
    for btn in buttons:
        raw_cmd = str(btn.get("command", "") or "")
        raw_label = str(btn.get("label", "") or "").strip() or raw_cmd or "Plugin"
        label = html.escape(raw_label)
        cmd = html.escape(raw_cmd)
        title = html.escape(f"{raw_label} {raw_cmd}".strip())
        parts.append(f'<button type="button" data-fill="{cmd}" title="{title}">{label}</button>')
    return "\n      ".join(parts)


def _handle_settings_install(component: str, payload: dict = None) -> dict:
    """Install a component (ocr, torch, or zluda) and return result dict."""
    if payload is None:
        payload = {}

    # Pip-managed components live in the dedicated runtime venv.
    _needs_python = {"torch", "opencv", "tts", "edge-tts", "datasets"}
    if component in _needs_python:
        try:
            runtime_python_exe()
        except RuntimeError as exc:
            return {
                "success": False,
                "detail": str(exc),
                "python_download_url": PYTHON_DOWNLOAD_URL,
            }

    if component == "ocr":
        try:
            result = install_portable_ocr()
            success = "未安装" not in result and "失败" not in result
            return {"success": success, "detail": result[:200]}
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:200]}

    elif component == "torch":
        try:
            import subprocess, sys
            # 支持指定版本：torch_cpu, torch_cuda121, torch_rocm, torch_rocm-nightly
            version = payload.get("version", "auto")
            gfx_target = None
            
            # 默认安装命令。当前功能只依赖 torch/torchvision；torchaudio 在部分 ROCm nightly
            # 源没有匹配 wheel，会导致整个安装失败。
            runtime_py = runtime_python_exe()
            cpu_index_url = "https://download.pytorch.org/whl/cpu"
            from desktop_pet import _uninstall_rocm_device_packages

            def torch_install_cmd(index: str = cpu_index_url) -> list[str]:
                cmd_parts = [
                    runtime_py, "-m", "pip", "install",
                    "--upgrade", "--force-reinstall",
                    "torch", "torchvision",
                ]
                if index:
                    cmd_parts.extend(["--index-url", index])
                return cmd_parts

            def directml_install_cmds() -> list[list[str]]:
                return [[
                    runtime_py, "-m", "pip", "install",
                    "--upgrade", "--force-reinstall",
                    "torch", "torchvision",
                    "--index-url", cpu_index_url,
                ], [
                    runtime_py, "-m", "pip", "install",
                    "--upgrade", "--force-reinstall",
                    "torch-directml",
                ]]

            def torch_repair_cpu_cmd() -> list[str]:
                return [
                    runtime_py, "-m", "pip", "install",
                    "--upgrade", "--ignore-installed", "--no-cache-dir",
                    "torch", "torchvision",
                    "--index-url", cpu_index_url,
                ]

            def pip_text(proc: subprocess.CompletedProcess) -> str:
                return (proc.stderr.strip() or proc.stdout.strip() or "").strip()

            def has_uninstall_record_error(proc: subprocess.CompletedProcess) -> bool:
                text = (proc.stderr or "") + "\n" + (proc.stdout or "")
                return "uninstall-no-record-file" in text or "no RECORD file was found for torch" in text

            cmd = torch_install_cmd()
            index_url = cpu_index_url
            
            if version == "auto":
                # 自动检测 GPU 并选择合适的版本
                from desktop_pet import _detect_gpu_detail, _get_amd_gfx_target, _uninstall_rocm_device_packages
                gpu_info = _detect_gpu_detail()
                gpu_brand = gpu_info.get("gpu_brand", "unknown")
                gfx_target = gpu_info.get("gfx_target")
                
                if gpu_brand == "NVIDIA":
                    index_url = "https://download.pytorch.org/whl/cu121"
                    cmd = torch_install_cmd(index_url)
                elif gpu_brand in {"AMD", "Intel"} and os.name == "nt":
                    index_url = "https://download.pytorch.org/whl/cpu + PyPI(torch-directml)"
                    cmd = directml_install_cmds()
                elif gpu_brand == "AMD" and gfx_target:
                    # 使用 ROCm nightly multi-arch wheel，并安装匹配的 GFX 设备包。
                    cmd = [
                        runtime_py, "-m", "pip", "install",
                        "--upgrade", "--force-reinstall", "--pre",
                        f"torch[device-{gfx_target}]",
                        f"torchvision[device-{gfx_target}]",
                        "--index-url", "https://rocm.nightlies.amd.com/whl-multi-arch/"
                    ]
                    index_url = "https://rocm.nightlies.amd.com/whl-multi-arch/"
                elif gpu_brand == "AMD":
                    # 未知GFX架构，使用通用ROCm
                    index_url = "https://download.pytorch.org/whl/rocm6.2"
                    cmd = torch_install_cmd(index_url)
                else:
                    index_url = cpu_index_url
            elif version == "cuda121":
                index_url = "https://download.pytorch.org/whl/cu121"
                cmd = torch_install_cmd(index_url)
            elif version == "directml":
                index_url = "https://download.pytorch.org/whl/cpu + PyPI(torch-directml)"
                cmd = directml_install_cmds()
            elif version == "rocm-nightly":
                if os.name == "nt":
                    return {"success": False, "detail": "Windows 下不再安装 ROCm 版 PyTorch，请选择 DirectML 或 CPU 版本。"}
                # ROCm nightly版本 - 自动检测GFX架构
                from desktop_pet import _detect_gpu, _detect_gpu_detail, _get_amd_gfx_target, _uninstall_rocm_device_packages
                gpu_brand = _detect_gpu()
                if gpu_brand == "AMD":
                    gpu_info = _detect_gpu_detail()
                    gfx_target = gpu_info.get("gfx_target")
                    if gfx_target:
                        cmd = [
                            runtime_py, "-m", "pip", "install",
                            "--upgrade", "--force-reinstall", "--pre",
                            f"torch[device-{gfx_target}]",
                            f"torchvision[device-{gfx_target}]",
                            "--index-url", "https://rocm.nightlies.amd.com/whl-multi-arch/"
                        ]
                        index_url = "https://rocm.nightlies.amd.com/whl-multi-arch/"
                    else:
                        # 无法检测GFX架构，使用通用ROCm 6.2
                        index_url = "https://download.pytorch.org/whl/rocm6.2"
                        cmd = torch_install_cmd(index_url)
                else:
                    return {"success": False, "detail": "ROCm nightly 仅适用于 AMD GPU"}
            elif version == "rocm":
                if os.name == "nt":
                    return {"success": False, "detail": "Windows 下不再安装 ROCm 版 PyTorch，请选择 DirectML 或 CPU 版本。"}
                index_url = "https://download.pytorch.org/whl/rocm6.2"
                cmd = torch_install_cmd(index_url)
            else:
                index_url = cpu_index_url
            
            if version in ["auto", "directml", "rocm-nightly"] and (gfx_target or version == "directml"):
                _uninstall_rocm_device_packages(runtime_py)

            if cmd and isinstance(cmd[0], list):
                proc = None
                for sub_cmd in cmd:
                    proc = subprocess.run(sub_cmd, capture_output=True, text=True, timeout=900, creationflags=CREATE_NO_WINDOW)
                    if proc.returncode != 0:
                        break
            else:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=CREATE_NO_WINDOW)

            # Fallback: if GPU-specific install failed, retry with CPU
            if proc.returncode != 0 and index_url and index_url != cpu_index_url:
                fallback_cmd = [
                    runtime_py, "-m", "pip", "install",
                    "--upgrade", "--force-reinstall",
                    "torch", "torchvision",
                    "--index-url", cpu_index_url,
                ]
                fallback_proc = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=600, creationflags=CREATE_NO_WINDOW)
                if fallback_proc.returncode == 0:
                    ok = True
                    detail = f"GPU 版本安装失败（可能不兼容当前 Python），已回退安装 CPU 版本"
                    return {"success": ok, "detail": detail}
                if has_uninstall_record_error(proc) or has_uninstall_record_error(fallback_proc):
                    repair_proc = subprocess.run(torch_repair_cpu_cmd(), capture_output=True, text=True, timeout=900, creationflags=CREATE_NO_WINDOW)
                    if repair_proc.returncode == 0:
                        return {
                            "success": True,
                            "detail": (
                                "检测到旧 torch 缺少 RECORD 元数据，已用 --ignore-installed 覆盖修复，"
                                "并安装 CPU 版本。"
                            ),
                        }
                    detail = pip_text(repair_proc)[:500]
                    detail += (
                        "\n检测到 torch 包元数据损坏（缺 RECORD），自动覆盖修复失败。"
                        f"\n可手动执行：\"{runtime_py}\" -m pip install --ignore-installed --no-cache-dir "
                        f"torch torchvision --index-url {cpu_index_url}"
                    )
                    return {"success": False, "detail": detail}
                # Both failed - report the original error
                ok = False
                detail = pip_text(proc)[:500]
                detail += f"\n（来源：{index_url}）回退 CPU 也失败，请手动安装或切换 CPU 版本"
                return {"success": ok, "detail": detail}

            if proc.returncode != 0 and has_uninstall_record_error(proc):
                repair_proc = subprocess.run(torch_repair_cpu_cmd(), capture_output=True, text=True, timeout=900, creationflags=CREATE_NO_WINDOW)
                if repair_proc.returncode == 0:
                    return {
                        "success": True,
                        "detail": (
                            "检测到旧 torch 缺少 RECORD 元数据，已用 --ignore-installed 覆盖修复，"
                            "并安装 CPU 版本。"
                        ),
                    }
                detail = pip_text(repair_proc)[:500]
                detail += (
                    "\n检测到 torch 包元数据损坏（缺 RECORD），自动覆盖修复失败。"
                    f"\n可手动执行：\"{runtime_py}\" -m pip install --ignore-installed --no-cache-dir "
                    f"torch torchvision --index-url {cpu_index_url}"
                )
                return {"success": False, "detail": detail}

            ok = proc.returncode == 0
            detail = "PyTorch 安装完成" if ok else pip_text(proc)[:500]
            if index_url:
                detail += f" (来源：{index_url})"
            # 显示GFX架构信息
            if version in ["auto", "rocm-nightly"] and gfx_target:
                detail += f" [GFX: {gfx_target}]"
            return {"success": ok, "detail": detail}
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:200]}

    elif component == "zluda":
        try:
            import urllib.request, zipfile, shutil, subprocess, sys
            from desktop_pet import _detect_gpu, _zluda_dll_dir, ZLUDA_DIR, ZLUDA_WIN_URL
            gpu = _detect_gpu()
            if gpu == "NVIDIA":
                return {"success": False, "detail": "检测到 NVIDIA GPU，ZLUDA 仅适用于 AMD/Intel"}
            ZLUDA_DIR.mkdir(parents=True, exist_ok=True)
            zip_path = ZLUDA_DIR / "zluda.zip"
            urllib.request.urlretrieve(ZLUDA_WIN_URL, str(zip_path))
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                zf.extractall(str(ZLUDA_DIR))
            zip_path.unlink(missing_ok=True)
            dll_dir = _zluda_dll_dir() or ZLUDA_DIR
            torch_dlls = list(dll_dir.glob("*.dll"))
            integrated = 0
            try:
                torch_probe = subprocess.run(
                    [
                        runtime_python_exe(create=False),
                        "-c",
                        "import pathlib, torch; print(pathlib.Path(torch.__file__).parent / 'lib')",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=CREATE_NO_WINDOW,
                )
                torch_lib = Path(torch_probe.stdout.strip()) if torch_probe.returncode == 0 else None
                if torch_lib and torch_lib.is_dir():
                    for dll in torch_dlls:
                        shutil.copy2(str(dll), str(torch_lib / dll.name))
                        integrated += 1
            except Exception:
                pass
            ok = _zluda_dll_dir() is not None
            detail = f"ZLUDA 已下载到 {ZLUDA_DIR}"
            if integrated:
                detail += f"，已复制 {integrated} 个 DLL 到 PyTorch"
            elif not torch_dlls:
                detail += "，未找到 DLL 文件"
            else:
                from desktop_pet import _check_torch_status
                torch_ok, torch_detail = _check_torch_status()
                if torch_ok:
                    detail += f"，当前 PyTorch 可用：{torch_detail}"
                else:
                    detail += "，PyTorch 未安装，请先安装 PyTorch"
            return {"success": ok, "detail": detail}
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:200]}

    elif component == "opencv":
        try:
            import subprocess, sys, importlib
            py = runtime_python_exe()
            cmd = [py, "-m", "pip", "install", "opencv-python"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
            ok = proc.returncode == 0
            if ok:
                # 用同一个 Python 子进程验证 import，避免当前进程路径缓存问题
                verify = subprocess.run(
                    [py, "-c", "import cv2; print(cv2.__version__)"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=CREATE_NO_WINDOW,
                )
                if verify.returncode == 0:
                    ver = verify.stdout.strip()
                    detail = f"OpenCV {ver} 安装完成"
                else:
                    pip_out = (proc.stderr.strip() or proc.stdout.strip())[:200]
                    detail = f"pip 安装成功但 import cv2 失败"
                    if pip_out:
                        detail += f"（pip: {pip_out}）"
                    ok = False
            else:
                detail = (proc.stderr.strip() or proc.stdout.strip())[:200]
            return {"success": ok, "detail": detail}
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:200]}

    elif component == "tts" or component == "edge-tts":
        try:
            import subprocess, sys
            cmd = [runtime_python_exe(), "-m", "pip", "install", "edge-tts"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
            ok = proc.returncode == 0
            if ok:
                detail = "Edge-TTS 安装完成"
            else:
                detail = (proc.stderr.strip() or proc.stdout.strip())[:200]
            return {"success": ok, "detail": detail}
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:200]}

    elif component == "datasets":
        try:
            from dependency_utils import install_dataset_dependencies

            status = install_dataset_dependencies()
            return {"success": status.ok, "detail": status.detail, "python": status.python}
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:200]}

    elif component == "cpp_toolchain":
        try:
            from toolchain_manager import install_llvm
            return install_llvm(str(payload.get("install_dir") or ""))
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:400]}

    elif component == "cpp_toolchain_path":
        try:
            from toolchain_manager import configure_existing_directory
            return configure_existing_directory(str(payload.get("install_dir") or ""))
        except Exception as exc:
            return {"success": False, "detail": str(exc)[:400]}

    else:
        return {"success": False, "detail": f"未知组件: {component}"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str, cors: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def _lan_auth_ok(self) -> bool:
        """Return True if the current request may perform write operations.

        - Local-only mode (no LAN) always allows.
        - Loopback clients always allow (same machine as the server).
        - Non-loopback clients in LAN mode must present the pairing token via
          the ``Authorization: Bearer <token>`` header or ``?lan_token=``
          query parameter.
        """
        if not (ALLOW_LAN or HOST in {"0.0.0.0", "::"}):
            return True
        if _is_loopback_client(self.client_address):
            return True
        expected = lan_access_token()
        if not expected:
            return False
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), expected):
            return True
        # Query-string token form: /api/...?lan_token=...
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        candidate = (qs.get("lan_token") or [""])[0]
        if candidate and hmac.compare_digest(candidate, expected):
            return True
        return False

    def do_OPTIONS(self) -> None:
        if self.path == "/api/local_access":
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            # inject plugin buttons into the HTML
            btn_html = _plugin_buttons_html()
            i18n = app_i18n_payload()
            page = INDEX_HTML.replace("<!--PLUGIN_BUTTONS-->", btn_html)
            page = page.replace('<html lang="zh-CN">', f'<html lang="{i18n["locale"]}">')
            page = page.replace("<title>Companion AI</title>", f"<title>{html.escape(i18n['app_name'])}</title>")
            page = page.replace("__I18N_BOOTSTRAP__", json.dumps(i18n, ensure_ascii=False))
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/diary" or self.path.startswith("/diary?"):
            self._send(200, secondary_page_html("diary").encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/samples" or self.path.startswith("/samples?"):
            self._send(200, secondary_page_html("samples").encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/moments_page" or self.path.startswith("/moments_page?"):
            self._send(200, secondary_page_html("moments").encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/tools" or self.path.startswith("/tools?"):
            self._send(200, secondary_page_html("tools").encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/demo" or self.path.startswith("/demo?"):
            page_path = RES_ROOT / "relationship_demo.html"
            if not page_path.exists():
                page_path = ROOT / "relationship_demo.html"
            if page_path.exists():
                self._send(200, page_path.read_bytes(), "text/html; charset=utf-8")
                return
            self._send(404, b"demo not found", "text/plain")
            return
        if self.path == "/official" or self.path == "/site" or self.path.startswith("/official?") or self.path.startswith("/site?"):
            page_path = RES_ROOT / "official_site.html"
            if page_path.exists():
                page = page_path.read_text(encoding="utf-8")
            else:
                page = OFFICIAL_SITE_HTML
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/asset/ai_icon.ico":
            for icon_path in (RES_ROOT / "ai_icon.ico", ROOT / "ai_icon.ico", RES_ROOT / "pet_icon.ico", ROOT / "pet_icon.ico"):
                if icon_path.exists():
                    self._send(200, icon_path.read_bytes(), "image/x-icon")
                    return
            self._send(404, b"not found", "text/plain")
            return
        if self.path == "/asset/pet_icon.ico":
            for icon_path in (RES_ROOT / "pet_icon.ico", ROOT / "pet_icon.ico", RES_ROOT / "ai_icon.ico", ROOT / "ai_icon.ico"):
                if icon_path.exists():
                    self._send(200, icon_path.read_bytes(), "image/x-icon")
                    return
            self._send(404, b"not found", "text/plain")
            return
        if self.path.startswith("/static/"):
            rel = urllib.parse.unquote(self.path.removeprefix("/static/"))
            fpath = (RES_ROOT / "static" / rel).resolve()
            # 安全校验：确保文件在 RES_ROOT/static 目录下
            if RES_ROOT.resolve() in fpath.parents and fpath.exists():
                # 根据扩展名设置 Content-Type
                ct = "application/javascript"
                if fpath.suffix.lower() == ".css":
                    ct = "text/css"
                elif fpath.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
                    ct = f"image/{fpath.suffix[1:]}"
                self._send(200, fpath.read_bytes(), ct)
                return
            self._send(404, b"not found", "text/plain")
            return
        if self.path.startswith("/data_image/"):
            rel = urllib.parse.unquote(self.path.removeprefix("/data_image/"))
            fpath = (DATA_DIR / rel).resolve()
            data_root = Path(DATA_DIR).resolve()
            if data_root in fpath.parents and fpath.exists() and fpath.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
                ct = f"image/{fpath.suffix[1:]}"
                if fpath.suffix.lower() == ".jpg":
                    ct = "image/jpeg"
                self._send(200, fpath.read_bytes(), ct)
                return
            self._send(404, b"not found", "text/plain")
            return
        if self.path in {"/api/identity_confirmation", "/api/face/list", "/api/face/recognize", "/api/face/log", "/api/face/log/clear"} and not load_privacy_consent().get("accepted"):
            self._send(403, json.dumps({"ok": False, "error": "privacy consent required"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        elif self.path == "/api/plugins":
            data = {"plugins": plugin_mgr.list_plugins()}
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/local_access":
            self._send(200, json.dumps(local_access_info(loopback=_is_loopback_client(self.client_address)), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cors=True)
        elif self.path == "/api/health":
            self._send(200, json.dumps(health_check(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/backup":
            backups = []
            if BACKUP_DIR.is_dir():
                for f in sorted(BACKUP_DIR.glob("*.tar.gz"), reverse=True):
                    backups.append({"name": f.name, "size": f.stat().st_size, "path": str(f)})
            self._send(200, json.dumps({"ok": True, "backups": backups}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/i18n":
            self._send(200, json.dumps(app_i18n_payload(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/update":
            self._send(200, json.dumps({"ok": True, **update_public_state()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/live2d" or self.path.startswith("/live2d?"):
            viewer = (RES_ROOT / "live2d_viewer.html").read_bytes()
            self._send(200, viewer, "text/html; charset=utf-8")
        elif self.path == "/api/live2d":
            data = handle_live2d_get()
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path.startswith("/live2d_model/"):
            rel = urllib.parse.unquote(self.path.removeprefix("/live2d_model/"))
            fpath = (LIVE2D_DIR / rel).resolve()
            if LIVE2D_DIR.resolve() not in fpath.parents and fpath != LIVE2D_DIR.resolve():
                self._send(403, b"forbidden", "text/plain")
                return
            if not fpath.exists():
                self._send(404, b"not found", "text/plain")
                return
            ct = "application/octet-stream"
            if fpath.suffix.lower() == ".json":
                ct = "application/json"
            elif fpath.suffix.lower() == ".png":
                ct = "image/png"
            elif fpath.suffix.lower() == ".moc3":
                ct = "application/octet-stream"
            elif fpath.suffix.lower() in {".motion3.json", ".model3.json"}:
                ct = "application/json"
            if fpath.name.lower().endswith(".model3.json"):
                self._send(200, live2d_model_json_response(fpath, rel), ct)
            else:
                self._send(200, fpath.read_bytes(), ct)
        elif self.path == "/3d" or self.path.startswith("/3d?"):
            viewer = (RES_ROOT / "viewer_3d.html").read_bytes()
            self._send(200, viewer, "text/html; charset=utf-8")
        elif self.path == "/api/3d":
            data = handle_3d_get()
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path.startswith("/3d_model/"):
            rel = urllib.parse.unquote(self.path.removeprefix("/3d_model/"))
            fpath = (MODEL3D_DIR / rel).resolve()
            if MODEL3D_DIR.resolve() not in fpath.parents and fpath != MODEL3D_DIR.resolve():
                self._send(403, b"forbidden", "text/plain")
                return
            if not fpath.exists():
                self._send(404, b"not found", "text/plain")
                return
            ct = "application/octet-stream"
            if fpath.suffix.lower() == ".json":
                ct = "application/json"
            elif fpath.suffix.lower() == ".png":
                ct = "image/png"
            elif fpath.suffix.lower() == ".tga":
                ct = "image/x-tga"
            elif fpath.suffix.lower() == ".glb":
                ct = "model/gltf-binary"
            elif fpath.suffix.lower() == ".gltf":
                ct = "model/gltf+json"
            self._send(200, fpath.read_bytes(), ct)
        elif self.path == "/api/pet_display":
            data = handle_pet_display_get()
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/privacy":
            data = load_privacy_consent()
            data["policy_version"] = PRIVACY_POLICY_VERSION
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/voiceprints":
            if not load_privacy_consent().get("accepted"):
                self._send(403, json.dumps({"ok": False, "error": "privacy consent required"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            self._send(200, json.dumps({"ok": True, "prints": voiceprint_public_list()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/memory":
            data = {"memory": load_memory(), "training": load_training(), "files": load_files(), "avatar": avatar_state(), "growth": growth_payload()}
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/recent_chats":
            self._send(200, json.dumps({"ok": True, "chats": load_recent_chats()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/moments":
            self._send(200, json.dumps({"ok": True, "moments": _moments_with_image_urls(load_moments())}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/growth":
            data = {"ok": True, "growth": growth_payload(), "text": growth_status_text(), "events": events_text()}
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/demo/state":
            data = {"ok": True, "growth": growth_payload(), "identity": load_identity()}
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/routine":
            data = {"text": routine_status_text()}
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/datasets":
            try:
                from dataset_loader import list_available_datasets
                config = {}
                config_path = ROOT / "train_config.json"
                if config_path.exists():
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                data = {
                    "available": list_available_datasets(),
                    "configured": config.get("datasets", {}),
                    "active": config.get("active_dataset"),
                }
                self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path.startswith("/uploads/"):
            name = urllib.parse.unquote(self.path.removeprefix("/uploads/"))
            path = (UPLOAD_DIR / name).resolve()
            if UPLOAD_DIR.resolve() not in path.parents or not path.exists():
                self._send(404, b"not found", "text/plain")
                return
            content_type = "application/octet-stream"
            if path.suffix.lower() in {".png"}:
                content_type = "image/png"
            elif path.suffix.lower() in {".jpg", ".jpeg"}:
                content_type = "image/jpeg"
            elif path.suffix.lower() == ".gif":
                content_type = "image/gif"
            elif path.suffix.lower() == ".bmp":
                content_type = "image/bmp"
            self._send(200, path.read_bytes(), content_type)
        elif self.path == "/api/display":
            config = load_app_config()
            self._send(200, json.dumps({"ok": True, "display": config["display"]}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings":
            try:
                from desktop_pet import (
                    _check_ocr_status,
                    _check_torch_status,
                    _check_zluda_status,
                    _check_opencv_status,
                    _check_tts_status,
                    _check_datasets_status,
                    _get_component_size,
                    _detect_gpu_detail,
                )
                ocr_ok, ocr_detail = _check_ocr_status()
                torch_ok, torch_detail = _check_torch_status()
                zluda_ok, zluda_detail = _check_zluda_status()
                opencv_ok, opencv_detail = _check_opencv_status()
                tts_ok, tts_detail = _check_tts_status()
                datasets_ok, datasets_detail = _check_datasets_status()
                from toolchain_manager import status as cpp_toolchain_status
                cpp_toolchain = cpp_toolchain_status()
                gpu_info = _detect_gpu_detail()
                if torch_ok and zluda_ok and "PyTorch 未安装" in zluda_detail:
                    backend = gpu_info.get("torch_backend")
                    if backend == "rocm":
                        zluda_detail = f"ZLUDA 已安装；当前 PyTorch 使用 ROCm（不需要 ZLUDA 接管）：{torch_detail}"
                    else:
                        zluda_detail = f"ZLUDA 已安装；当前 PyTorch 可用：{torch_detail}"
                ocr_removable = ocr_ok and "portable" in ocr_detail.lower()
                
                python_ok = False
                python_detail = "未检测到 Python"
                try:
                    python_exe()
                    python_ok = True
                    python_detail = "Python 可用"
                except RuntimeError as exc:
                    python_detail = str(exc)
                data = {
                    "ocr": {"installed": ocr_ok, "detail": ocr_detail, "size": _get_component_size("ocr"), "removable": ocr_removable},
                    "torch": {"installed": torch_ok, "detail": torch_detail, "size": _get_component_size("torch"), "gpu": gpu_info},
                    "neural": neural_status(),
                    "zluda": {"installed": zluda_ok, "detail": zluda_detail, "size": _get_component_size("zluda")},
                    "opencv": {"installed": opencv_ok, "detail": opencv_detail, "size": _get_component_size("opencv")},
                    "tts": {"installed": tts_ok, "detail": tts_detail, "size": _get_component_size("tts")},
                    "datasets": {"installed": datasets_ok, "detail": datasets_detail, "size": _get_component_size("datasets")},
                    "python": {"installed": python_ok, "detail": python_detail, "size": _get_component_size("python")},
                    "cpp_toolchain": cpp_toolchain,
                }
            except Exception as exc:
                data = {
                    "ocr": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "torch": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "neural": {"torch": {"available": False, "directml_available": False}},
                    "zluda": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "opencv": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "tts": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "datasets": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "python": {"installed": False, "detail": f"检测失败：{exc}", "size": "未知"},
                    "cpp_toolchain": {"installed": False, "detail": f"检测失败：{exc}", "install_dir": ""},
                }
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings/audit":
            try:
                from conversation_audit import load_audit_config, get_audit_summary, get_recent_audits, is_audit_enabled
                from audit_training import handled_audit_ids, audit_result_id
                config = load_audit_config()
                summary = get_audit_summary()
                handled_ids = handled_audit_ids()
                pending_by_id = {}
                for item in get_recent_audits(200):
                    audit_id = audit_result_id(item)
                    if audit_id not in handled_ids:
                        pending_by_id[audit_id] = item
                recent_audits = list(pending_by_id.values())[-8:]
                # Mask API key for security
                display_config = dict(config)
                if display_config.get("api_key"):
                    key = display_config["api_key"]
                    display_config["api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
                self._send(200, json.dumps({
                    "config": display_config,
                    "enabled": is_audit_enabled(),
                    "summary": summary,
                    "recent_audits": recent_audits,
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings/growth":
            try:
                from growth_loop import growth_status, list_benchmarks
                from growth_loop import list_experiences, list_model_versions
                from image_growth import status as image_growth_status, list_recipes
                from growth_jobs import status as training_job_status
                from local_image_backend import load_config as load_image_backend_config, public_status as image_backend_status
                self._send(200, json.dumps({
                    "ok": True,
                    "growth": growth_status(),
                    "image": image_growth_status(),
                    "benchmarks": list_benchmarks(),
                    "versions": list_model_versions(),
                    "experiences": list_experiences(40),
                    "recipes": list_recipes(30),
                    "training_job": training_job_status(),
                    "image_backend": {**load_image_backend_config(), **image_backend_status(check_service=True)},
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings/runtime":
            try:
                from dreaming_engine import get_dream_status, load_dream_config
                from routine_tracker import is_autostart_enabled
                self._send(200, json.dumps({
                    "ok": True,
                    "dream": load_dream_config(),
                    "status": get_dream_status(),
                    "autostart": is_autostart_enabled(),
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings/diagnostics":
            try:
                from dreaming_engine import get_dream_status
                from growth_loop import growth_status
                from growth_jobs import status as training_job_status
                from diagnostics import build_report
                report = build_report(health_check(), get_dream_status(), growth_status(), training_job_status())
                self._send(200, json.dumps({"ok": True, "report": report}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings/remote_llm":
            try:
                from remote_llm import load_remote_llm_config, public_remote_llm_config, is_remote_llm_ready
                config = load_remote_llm_config()
                self._send(200, json.dumps({
                    "ok": True,
                    "config": public_remote_llm_config(config),
                    "ready": is_remote_llm_ready(config),
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/settings/tiny_llm":
            try:
                from tiny_llm import load_deep_reply_config
                config = load_deep_reply_config()
                self._send(200, json.dumps({"ok": True, **config}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/chat/modes":
            try:
                from hybrid_chat import list_chat_modes
                self._send(200, json.dumps({"ok": True, "modes": list_chat_modes()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/identity":
            identity = load_identity()
            self._send(200, json.dumps({"identity": identity, "setup_done": is_identity_set()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/tts/config":
            # 获取 TTS 配置
            config = tts_engine.get_tts_config()
            cache_count, cache_size = tts_engine.get_cache_size()
            config["cache_count"] = cache_count
            config["cache_size"] = cache_size
            tts_ok, tts_detail = tts_engine.runtime_status()
            config["available"] = tts_ok
            config["available_detail"] = tts_detail
            self._send(200, json.dumps(config, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/tts/voices":
            # 获取可用语音列表
            voices = tts_engine.get_available_voices()
            self._send(200, json.dumps({"voices": voices}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path.startswith("/api/tts/audio/"):
            # 获取音频文件
            filename = self.path[len("/api/tts/audio/"):]
            # 安全检查：防止路径遍历
            if ".." in filename or "/" in filename or "\\" in filename:
                self._send(400, b"invalid filename", "text/plain")
                return
            audio_path = tts_engine.TTS_CACHE_DIR / filename
            if audio_path.exists() and audio_path.suffix == ".mp3":
                self._send(200, audio_path.read_bytes(), "audio/mpeg")
            else:
                self._send(404, b"audio not found", "text/plain")
        elif self.path.startswith("/api/tts/synthesize") and "?" in self.path:
            # GET 方式合成语音
            try:
                from urllib.parse import parse_qs, urlparse
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                text = training_response_text(params.get("text", [""])[0])
                if not text:
                    self._send(400, json.dumps({"error": "text 参数不能为空"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                
                config = tts_engine.get_tts_config()
                voice = params.get("voice", [config.get("voice", tts_engine.DEFAULT_VOICE)])[0]
                rate = params.get("rate", [config.get("rate", tts_engine.DEFAULT_RATE)])[0]
                pitch = params.get("pitch", [config.get("pitch", tts_engine.DEFAULT_PITCH)])[0]
                volume = params.get("volume", [config.get("volume", tts_engine.DEFAULT_VOLUME)])[0]
                
                audio_path = tts_engine.synthesize(text, voice, rate, pitch, volume)
                filename = audio_path.name
                
                self._send(200, json.dumps({
                    "ok": True,
                    "filename": filename,
                    "url": f"/api/tts/audio/{filename}",
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/status":
            try:
                result = face_manager.face_status_text()
                self._send(200, json.dumps({"ok": True, "status": result}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/install":
            try:
                result = face_manager.install_face_recognition_portable()
                self._send(200, json.dumps({"ok": True, "message": result}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/install_cmake":
            try:
                result = face_manager.install_cmake()
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/install_dlib":
            try:
                result = face_manager.install_dlib_binary()
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/install_vs_build_tools":
            try:
                result = face_manager.download_vs_build_tools(install=True)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/install_python":
            try:
                result = path_helpers.download_and_install_python(install=True)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/list":
            try:
                faces = face_manager.list_registered_faces()
                self._send(200, json.dumps({"ok": True, "faces": faces}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/recognize":
            if not load_privacy_consent().get("accepted"):
                self._send(403, json.dumps({"ok": False, "error": "privacy consent required"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            try:
                result = run_face_operation_with_timeout(
                    lambda: face_manager.recognize_from_camera(),
                    18,
                    {
                        "ok": False,
                        "faces": [],
                        "unknown_count": 0,
                        "known_count": 0,
                        "error": "人脸识别超时",
                        "message": "摄像头或人脸识别模型响应过慢，请确认摄像头未被其他程序占用后重试。",
                    },
                )
                record_face_confirmation_from_result(result)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/identity_confirmation":
            try:
                self._send(200, json.dumps({"ok": True, **load_identity_confirmation()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/log":
            try:
                logs = face_manager.get_face_log(100)
                self._send(200, json.dumps({"ok": True, "logs": logs}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/face/log/clear":
            try:
                result = face_manager.clear_face_log()
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/diary_entries":
            try:
                entries = get_diary_entries(7)
                self._send(200, json.dumps({"ok": True, "entries": entries}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        # LAN access control: non-loopback write requests must present the
        # pairing token (Authorization: Bearer <token> or ?lan_token=<token>).
        # Local requests (127.0.0.1) and local-only mode are always exempt.
        if not self._lan_auth_ok():
            self._send(403, json.dumps({"ok": False, "error": "LAN access token required", "reply": "局域网写入需要访问令牌。请在本地控制台查看 LAN 令牌。"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/local_access":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                if str(payload.get("action") or "") == "regenerate_token" and _is_loopback_client(self.client_address):
                    new_token = lan_access_token(regenerate=True)
                    self._send(200, json.dumps({"ok": True, "lan_token": new_token}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                self._send(400, json.dumps({"ok": False, "error": "未知操作"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/privacy":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                if "accepted" not in payload:
                    self._send(400, json.dumps({"ok": False, "error": "缺少 accepted 字段"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                data = save_privacy_consent(bool(payload.get("accepted")))
                self._send(200, json.dumps({"ok": True, **data}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/i18n":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                config = save_app_config({"locale": payload.get("locale")})
                result = app_i18n_payload()
                result["ok"] = True
                result["config"] = config
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/display":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                config = save_app_config({"display": payload})
                self._send(200, json.dumps({"ok": True, "display": config["display"], "config": config}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/demo/scene":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                result = demo_scene_payload(str(payload.get("scene", "day1")))
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/update":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                action = str(payload.get("action") or "status")
                if action == "configure":
                    updates = {}
                    for key in ("auto_check", "auto_download", "auto_install", "check_interval_hours"):
                        if key in payload:
                            updates[key] = payload[key]
                    save_update_state(updates)
                    result = {"ok": True, **update_public_state()}
                elif action == "check":
                    result = check_for_updates()
                elif action == "download":
                    result = download_update()
                elif action == "install":
                    result = install_downloaded_update()
                else:
                    result = {"ok": True, **update_public_state()}
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc), **update_public_state()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/backup":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                action = str(payload.get("action") or "create")
                if action == "create":
                    result = create_backup()
                elif action == "restore_path":
                    archive_path = Path(str(payload.get("path") or ""))
                    result = restore_backup(archive_path)
                else:
                    result = {"ok": False, "error": f"未知操作: {action}"}
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/backup/restore":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            ct = self.headers.get("Content-Type", "")
            try:
                parsed = parse_multipart(raw, ct)
                if not parsed:
                    self._send(400, json.dumps({"ok": False, "error": "没有找到备份文件。"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                name, data = parsed
                if len(data) > 500_000_000:
                    self._send(400, json.dumps({"ok": False, "error": "备份文件过大（限制 500MB）。"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                import tempfile as _tempfile
                with _tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = Path(tmp.name)
                try:
                    result = restore_backup(tmp_path)
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path in {"/api/chat", "/api/upload", "/api/observe_screen", "/api/realtime_observe", "/api/realtime_event", "/api/feedback", "/api/correct", "/api/emotion_feedback", "/api/audit_training", "/api/moments", "/api/voiceprints", "/api/identity_confirmation", "/api/face/register", "/api/face/delete", "/api/face/rename"} and not load_privacy_consent().get("accepted"):
            self._send(403, json.dumps({"ok": False, "reply": "请先阅读并同意隐私政策。", "error": "privacy consent required"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- live2d management --
        if self.path == "/api/live2d":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            result = handle_live2d_post(payload)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- live2d model upload --
        if self.path == "/api/live2d/upload":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            ct = self.headers.get("Content-Type", "")
            result = handle_live2d_upload(raw, ct)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- 3d model management --
        if self.path == "/api/3d":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            result = handle_3d_post(payload)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- 3d model upload --
        if self.path == "/api/3d/upload":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            ct = self.headers.get("Content-Type", "")
            result = handle_3d_upload(raw, ct)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- pet display mode --
        if self.path == "/api/pet_display":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            result = handle_pet_display_post(payload)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/voiceprints":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                action = payload.get("action", "")
                if action == "enroll":
                    result = enroll_voiceprint(str(payload.get("name", "")), payload.get("features", []))
                elif action == "recognize":
                    result = recognize_voiceprint(payload.get("features", []))
                elif action == "delete":
                    result = delete_voiceprint(str(payload.get("id", "")))
                else:
                    result = {"ok": False, "error": "unknown action"}
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/identity_confirmation":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                action = str(payload.get("action", "status"))
                if action == "clear":
                    data = clear_identity_confirmation()
                else:
                    data = load_identity_confirmation()
                self._send(200, json.dumps({"ok": True, **data}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- local visual observation --
        if self.path == "/api/observe_screen":
            result = observe_screen()
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/realtime_observe":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                result = realtime_observation_context(payload)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/realtime_event":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                role = str(payload.get("role") or "system")
                text = str(payload.get("text") or "").strip()
                if text:
                    append_realtime_chat_message(role if role in {"user", "assistant", "system"} else "system", text[:500])
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- memory management --
        if self.path == "/api/memory/clear":
            result = clear_memory()
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- emotion & diary --
        if self.path == "/api/emotion_trend":
            days_param = 7
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 0:
                    raw = self.rfile.read(length)
                    payload = json.loads(raw.decode("utf-8"))
                    days_param = max(3, min(30, int(payload.get("days", 7))))
            except Exception:
                pass
            result = {"ok": True, "trend": get_emotion_trend(days_param)}
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/diary_entries":
            entries = get_diary_entries(7)
            self._send(200, json.dumps({"ok": True, "entries": entries}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/diary_gen":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                date_str = payload.get("date", "")
                persona, worldview = get_active_persona()
                result = generate_diary_entry(
                    date_str=date_str or None,
                    persona=persona,
                    worldview=worldview,
                )
                if result.get("ok"):
                    result["entries"] = get_diary_entries(7)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/moments":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                result = handle_moments_post(payload)
                if result.get("moments"):
                    result["moments"] = _moments_with_image_urls(result["moments"])
                if result.get("post"):
                    result["post"]["image_url"] = _moment_image_url(result["post"].get("image", ""))
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- identity management --
        if self.path == "/api/identity":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                action = payload.get("action", "save")
                
                if action == "save":
                    identity = {
                        "name": payload.get("name", "").strip(),
                        "relationship_type": payload.get("relationship_type", "friend").strip() or "friend",
                        "relationship_label": payload.get("relationship_label", "").strip(),
                        "relationship_subtype": payload.get("relationship_subtype", "").strip(),
                        "allow_romance_evolution": bool(payload.get("allow_romance_evolution", True)),
                        "birthday": payload.get("birthday", "").strip(),
                        "persona": payload.get("persona", "").strip(),
                        "worldview": payload.get("worldview", "").strip(),
                        "gender": payload.get("gender", "").strip(),
                        "id_number": payload.get("id_number", "").strip(),
                        "created_at": payload.get("created_at", ""),
                    }
                    # 如果没有身份证号，根据生日自动生成
                    if not identity["id_number"] and identity["birthday"]:
                        identity["id_number"] = generate_chinese_id(identity["birthday"])
                    if identity["relationship_type"] == "custom" and not identity["relationship_label"]:
                        self._send(400, json.dumps({"ok": False, "error": "请填写自定义关系名称"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                        return
                    
                    assignment = {}
                    if identity["relationship_type"] == "custom":
                        assignment = assign_custom_relationship_with_api(identity)
                        if assignment.get("ok"):
                            identity["relationship_assignment"] = assignment
                        else:
                            identity["relationship_assignment"] = {
                                "ok": False,
                                "source": assignment.get("source", "fallback"),
                                "error": assignment.get("error", "未使用大模型接口分配"),
                            }

                    growth = configure_relationship(
                        identity["relationship_type"],
                        custom_label=identity.get("relationship_label", ""),
                        relationship_subtype=identity.get("relationship_subtype", ""),
                        romance_label=relationship_romance_label(identity.get("gender", "")),
                        romance_enabled=identity.get("allow_romance_evolution", True),
                        assignment=identity.get("relationship_assignment", {}),
                    )
                    identity["relationship_subtype"] = growth.get("relationship_profile", {}).get("relationship_subtype", "")
                    save_identity(identity)
                    self._send(200, json.dumps({"ok": True, "identity": identity}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                
                elif action == "generate_id":
                    birthday = payload.get("birthday", "")
                    if birthday:
                        id_number = generate_chinese_id(birthday)
                        self._send(200, json.dumps({"ok": True, "id_number": id_number}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    else:
                        self._send(400, json.dumps({"ok": False, "error": "请提供生日"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                
                else:
                    self._send(400, json.dumps({"ok": False, "error": "未知操作"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- plugin management --
        if self.path == "/api/plugins":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            action = payload.get("action", "")
            name = payload.get("name", "")
            if action == "reload":
                plugin_mgr.reload_all()
                result = {"ok": True, "plugins": plugin_mgr.list_plugins()}
            elif action == "toggle" and name:
                disabled = plugin_mgr.toggle_plugin(name)
                result = {"ok": disabled is not None, "disabled": disabled}
            elif action == "remove" and name:
                ok = plugin_mgr.remove_plugin(name)
                result = {"ok": ok}
            elif action == "sandbox_validate":
                meta = payload.get("meta", {})
                result = validate_plugin_package(meta)
            elif action == "create":
                meta = payload.get("meta", {})
                try:
                    plugin = plugin_mgr.install_from_template(name, meta)
                    result = {"ok": True, "plugin": plugin.info()}
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
            else:
                result = {"ok": False, "error": "unknown action"}
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- TTS 语音合成 --
        if self.path == "/api/tts/config":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            
            # 获取当前配置
            config = tts_engine.get_tts_config()
            
            # 更新配置
            if "enabled" in payload:
                config["enabled"] = bool(payload["enabled"])
            if "voice" in payload:
                config["voice"] = str(payload["voice"])
            if "rate" in payload:
                config["rate"] = str(payload["rate"])
            if "pitch" in payload:
                config["pitch"] = str(payload["pitch"])
            if "volume" in payload:
                config["volume"] = str(payload["volume"])
            if "auto_play" in payload:
                config["auto_play"] = bool(payload["auto_play"])
            
            tts_engine.save_tts_config(config)
            
            cache_count, cache_size = tts_engine.get_cache_size()
            config["cache_count"] = cache_count
            config["cache_size"] = cache_size
            tts_ok, tts_detail = tts_engine.runtime_status()
            config["available"] = tts_ok
            config["available_detail"] = tts_detail
            
            self._send(200, json.dumps({"ok": True, "config": config}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/tts/synthesize":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            
            text = training_response_text(str(payload.get("text", "")))
            if not text:
                self._send(400, json.dumps({"ok": False, "error": "text 参数不能为空"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            
            try:
                config = tts_engine.get_tts_config()
                voice = payload.get("voice", config.get("voice", tts_engine.DEFAULT_VOICE))
                rate = payload.get("rate", config.get("rate", tts_engine.DEFAULT_RATE))
                pitch = payload.get("pitch", config.get("pitch", tts_engine.DEFAULT_PITCH))
                volume = payload.get("volume", config.get("volume", tts_engine.DEFAULT_VOLUME))
                
                audio_path = tts_engine.synthesize(text, voice, rate, pitch, volume)
                filename = audio_path.name
                
                self._send(200, json.dumps({
                    "ok": True,
                    "filename": filename,
                    "url": f"/api/tts/audio/{filename}",
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/tts/clear_cache":
            try:
                count = tts_engine.clear_cache()
                self._send(200, json.dumps({"ok": True, "cleared": count}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- settings: install components --
        if self.path == "/api/settings/install":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            component = payload.get("component", "")
            result = _handle_settings_install(component, payload)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- settings: uninstall components --
        if self.path == "/api/settings/uninstall":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            component = payload.get("component", "")
            try:
                from desktop_pet import _uninstall_component
                result = _uninstall_component(component)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/neural/train":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if payload.get("backend") != "directml":
                    result = {"ok": False, "error": "此入口仅支持 DirectX 12 (DirectML) 训练。"}
                else:
                    result = train_motion_net_gpu_isolated(backend="directml")
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/settings/growth":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                from growth_loop import add_benchmark, remove_benchmark, rollback_active_model, update_experience, delete_experience, activate_model_version
                from image_growth import record_feedback as record_image_feedback
                from growth_jobs import start as start_growth_training, cancel as cancel_growth_training
                action = str(payload.get("action") or "").strip()
                if action == "add_benchmark":
                    result = add_benchmark(str(payload.get("prompt") or ""), str(payload.get("keywords") or ""), rule=str(payload.get("rule") or "keywords"))
                elif action == "update_benchmark":
                    from growth_loop import update_benchmark
                    result = update_benchmark(str(payload.get("id") or ""), str(payload.get("prompt") or ""), str(payload.get("keywords") or ""), rule=str(payload.get("rule") or "keywords"), manual_pass=payload.get("manual_pass"))
                elif action == "remove_benchmark":
                    result = {"ok": remove_benchmark(str(payload.get("id") or ""))}
                    if not result["ok"]:
                        result["error"] = "未找到该评测题。"
                elif action == "rollback":
                    result = rollback_active_model()
                elif action == "activate_version":
                    result = activate_model_version(str(payload.get("id") or ""))
                elif action == "update_experience":
                    result = update_experience(str(payload.get("id") or ""), reward=payload.get("reward"), verified=payload.get("verified"), response=payload.get("response"))
                elif action == "delete_experience":
                    result = {"ok": delete_experience(str(payload.get("id") or ""))}
                elif action == "add_calibration":
                    from growth_loop import record_experience
                    result = record_experience(str(payload.get("prompt") or ""), str(payload.get("response") or ""), source="calibration:manual", evidence_type="human", reward=1.0, evidence="用户在设置中明确批准的真实样本标定")
                elif action == "image_feedback":
                    result = {"ok": record_image_feedback(str(payload.get("path") or ""), str(payload.get("feedback") or ""))}
                elif action == "save_image_backend":
                    from local_image_backend import save_config as save_image_backend_config, public_status as image_backend_status
                    config = save_image_backend_config(payload)
                    status = image_backend_status(check_service=True)
                    result = {"ok": True, "config": config, "message": status.get("message", "本地图片后端已保存。")}
                elif action == "start_training":
                    result = start_growth_training(int(payload.get("epochs") or 3))
                elif action == "cancel_training":
                    result = cancel_growth_training()
                else:
                    result = {"ok": False, "error": "未知成长设置操作"}
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/settings/runtime":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                from dreaming_engine import handle_dream_command, load_dream_config, save_dream_config, start_dreaming_engine, stop_dreaming_engine
                from routine_tracker import set_autostart_enabled
                action = str(payload.get("action") or "").strip()
                if action == "save":
                    config = load_dream_config()
                    def bounded(name: str, low: int, high: int, fallback: int) -> int:
                        try:
                            return max(low, min(high, int(payload.get(name, fallback))))
                        except (TypeError, ValueError):
                            return fallback
                    config["enabled"] = bool(payload.get("dream_enabled"))
                    config["system_idle_threshold_seconds"] = bounded("system_idle_threshold_seconds", 30, 3600, int(config.get("system_idle_threshold_seconds", 60)))
                    config["chat_idle_threshold_seconds"] = bounded("chat_idle_threshold_seconds", 15, 3600, int(config.get("chat_idle_threshold_seconds", 30)))
                    config["review_interval_hours"] = bounded("review_interval_hours", 1, 168, int(config.get("review_interval_hours", 4)))
                    heavy_minutes = bounded("heavy_task_idle_minutes", 1, 240, max(1, int(config.get("heavy_task_system_idle_min", 300)) // 60))
                    config["heavy_task_system_idle_min"] = heavy_minutes * 60
                    config["heavy_task_chat_idle_min"] = heavy_minutes * 60
                    quiet = payload.get("quiet_hours", config.get("quiet_hours", []))
                    if isinstance(quiet, list):
                        config["quiet_hours"] = sorted({int(hour) for hour in quiet if isinstance(hour, int) and 0 <= hour <= 23})
                    save_dream_config(config)
                    if config["enabled"]:
                        start_dreaming_engine()
                    else:
                        stop_dreaming_engine()
                    startup_message = set_autostart_enabled(bool(payload.get("autostart")))
                    result = {"ok": True, "message": f"后台设置已保存。{startup_message}"}
                elif action == "review_now":
                    reply = handle_dream_command("/dream_now") or "整理命令未执行"
                    result = {"ok": True, "message": reply}
                elif action == "practice_now":
                    reply = handle_dream_command("/dream_practice") or "练习命令未执行"
                    result = {"ok": True, "message": reply}
                else:
                    result = {"ok": False, "error": "未知后台设置操作"}
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/settings/diagnostics":
            try:
                from dreaming_engine import get_dream_status
                from growth_loop import growth_status
                from growth_jobs import status as training_job_status
                from diagnostics import build_report, export_report
                report = build_report(health_check(), get_dream_status(), growth_status(), training_job_status())
                path = export_report(report)
                self._send(200, json.dumps({"ok": True, "path": path}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- settings: save audit config --
        if self.path == "/api/settings/models":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                scope = str(payload.get("scope") or "").strip()
                if scope == "audit":
                    from conversation_audit import load_audit_config
                    configured = load_audit_config()
                elif scope == "remote_llm":
                    from remote_llm import load_remote_llm_config
                    configured = load_remote_llm_config()
                else:
                    self._send(400, json.dumps({"ok": False, "error": "未知模型配置范围"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                api_base = str(payload.get("api_base") or configured.get("api_base") or "").strip()
                supplied_key = str(payload.get("api_key") or "").strip()
                use_saved_key = bool(payload.get("use_saved_key"))
                api_key = supplied_key if supplied_key and supplied_key != "***" else (str(configured.get("api_key") or "") if use_saved_key else "")
                from remote_llm import list_available_models
                result = list_available_models(api_base, api_key)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "models": [], "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/settings/audit":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                from conversation_audit import load_audit_config, save_audit_config
                config = load_audit_config()
                # Update only provided fields
                for key in ("enabled", "api_provider", "api_base", "api_key", "model",
                            "batch_size", "audit_interval", "max_context_turns", "language",
                            "auto_suggest_corrections", "correction_threshold", "local_fallback", "use_cloud_audit"):
                    if key in payload:
                        config[key] = payload[key]
                save_audit_config(config)
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- settings: save remote LLM config --
        if self.path == "/api/settings/remote_llm/test":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                from remote_llm import load_remote_llm_config, test_remote_llm_connection
                config = load_remote_llm_config()
                for key in ("enabled", "enabled_for_hybrid", "reasoning_enabled", "reasoning_effort", "api_base", "api_key", "model", "temperature", "max_tokens", "timeout", "user_prompt"):
                    if key in payload:
                        if key == "api_key" and str(payload.get("api_key") or "").strip() in {"", "***"}:
                            continue
                        config[key] = payload[key]
                config["enabled"] = True
                result = test_remote_llm_connection(config)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/settings/remote_llm":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                from remote_llm import save_remote_llm_config, public_remote_llm_config, is_remote_llm_ready
                updates = {}
                for key in ("enabled", "enabled_for_hybrid", "reasoning_enabled", "reasoning_effort", "api_base", "api_key", "model", "temperature", "max_tokens", "timeout", "user_prompt"):
                    if key in payload:
                        if key == "api_key" and str(payload.get("api_key") or "").strip() in {"", "***"}:
                            continue
                        updates[key] = payload[key]
                config = save_remote_llm_config(updates)
                self._send(200, json.dumps({
                    "ok": True,
                    "config": public_remote_llm_config(config),
                    "ready": is_remote_llm_ready(config),
                }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/settings/tiny_llm":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                from tiny_llm import save_deep_reply_config
                config = save_deep_reply_config({"enabled": payload.get("enabled", False)})
                self._send(200, json.dumps({"ok": True, **config}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/chat/mode":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                mode = str(payload.get("mode") or "").strip()
                from hybrid_chat import CHAT_MODES, set_chat_mode
                result = set_chat_mode(mode)
                if result.get("ok"):
                    result["name"] = CHAT_MODES[mode]["name"]
                    self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                else:
                    self._send(400, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- face recognition: register face from camera (POST: needs body) --
        if self.path == "/api/face/register":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                name = payload.get("name", "")
                if not name:
                    self._send(400, json.dumps({"ok": False, "error": "缺少人脸名称"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                result = run_face_operation_with_timeout(
                    lambda: face_manager.register_face_from_camera(name),
                    22,
                    {
                        "ok": False,
                        "face_id": "",
                        "name": name,
                        "error": "人脸注册超时",
                        "message": "摄像头或人脸注册模型响应过慢，请确认摄像头未被其他程序占用后重试。",
                    },
                )
                if not isinstance(result, dict):
                    result = {"ok": False, "error": "人脸注册没有返回有效结果"}
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- face recognition: delete face (POST: needs body) --
        if self.path == "/api/face/delete":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                face_id = payload.get("face_id", "")
                if not face_id:
                    self._send(400, json.dumps({"ok": False, "error": "缺少人脸 ID"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                result = face_manager.delete_face(face_id)
                if result.get("ok"):
                    clear_identity_confirmation_if_source("face", face_id)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path == "/api/face/rename":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                face_id = payload.get("face_id", "")
                name = str(payload.get("name", "")).strip()
                if not face_id or not name:
                    self._send(400, json.dumps({"ok": False, "error": "缺少人脸 ID 或新名称"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                result = face_manager.update_face_name(face_id, name)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- dataset training --
        if self.path == "/api/train_dataset":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                result = self._handle_dataset_train(payload)
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- user correction feedback --
        if self.path == "/api/correct":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                training = record_correction(
                    str(payload.get("prompt", "")),
                    str(payload.get("wrong_response", "")),
                    str(payload.get("correct_response", "")),
                )
                result = {
                    "ok": True,
                    "training": training,
                    "avatar": avatar_state("spark"),
                }
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- user emotion judgement feedback --
        if self.path == "/api/emotion_feedback":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                training = record_emotion_feedback(
                    str(payload.get("text", "")),
                    str(payload.get("predicted_emotion", "")),
                    int(payload.get("rating", 0)),
                    str(payload.get("correct_emotion", "")),
                )
                result = {
                    "ok": True,
                    "training": training,
                    "avatar": avatar_state("spark" if int(payload.get("rating", 0)) > 0 else "thinking"),
                }
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # -- human judgement for conversation audit training --
        if self.path == "/api/audit_training":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
                from audit_training import record_audit_training_by_id, handled_audit_ids, audit_result_id
                from conversation_audit import get_recent_audits
                audit_id = str(payload.get("audit_id", "")).strip()
                if not audit_id:
                    self._send(400, json.dumps({"ok": False, "error": "这条审计缺少 ID，请刷新设置页后再试。"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                decision = str(payload.get("decision", "skip")).strip() or "skip"
                if decision not in {"approve", "reject", "correct", "skip"}:
                    self._send(400, json.dumps({"ok": False, "error": "无效判定"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                training = record_audit_training_by_id(
                    audit_id,
                    decision,
                    str(payload.get("corrected_response", "")),
                    str(payload.get("note", "")),
                )
                result = {
                    "ok": True,
                    "training": training,
                    "recent_audits": list({
                        audit_result_id(item): item
                        for item in get_recent_audits(200)
                        if audit_result_id(item) not in handled_audit_ids(training)
                    }.values())[-8:],
                    "avatar": avatar_state("spark" if decision in {"approve", "correct"} else "thinking"),
                }
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        if self.path not in {"/api/chat", "/api/feedback", "/api/upload"}:
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            if self.path == "/api/upload":
                result = handle_upload(raw, self.headers.get("Content-Type", ""))
            else:
                payload = json.loads(raw.decode("utf-8"))
                if self.path == "/api/chat":
                    result = handle_chat(payload)
                else:
                    training = record_feedback(
                        str(payload.get("prompt", "")),
                        str(payload.get("response", "")),
                        int(payload.get("rating", 0)),
                    )
                    result = {
                        "training": training,
                        "avatar": avatar_state("spark" if int(payload.get("rating", 0)) > 0 else "thinking"),
                    }
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        except Exception as exc:
            body = json.dumps({"reply": f"服务端错误：{exc}"}, ensure_ascii=False).encode("utf-8")
            self._send(500, body, "application/json; charset=utf-8")
            
    def _handle_dataset_train(self, payload: dict) -> dict:
        """处理数据集训练请求。"""
        from dataset_loader import load_dataset_from_config

        ds_config = payload.get("dataset_config", {})
        if not ds_config:
            dataset_key = payload.get("dataset_key", "")
            if dataset_key:
                config_path = ROOT / "train_config.json"
                if config_path.exists():
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    ds_config = config.get("datasets", {}).get(dataset_key, {})
            if not ds_config:
                return {"ok": False, "error": "请提供 dataset_config 或有效的 dataset_key"}

        train_params = payload.get("training", {})

        try:
            examples = load_dataset_from_config(ds_config)
        except Exception as exc:
            return {"ok": False, "error": f"数据集加载失败: {exc}"}

        if not examples:
            return {"ok": False, "error": "数据集中没有有效样本"}

        result = train_from_dataset(
            dataset_examples=examples,
            epochs=train_params.get("epochs", 50),
            batch_size=train_params.get("batch_size", 64),
            lr=train_params.get("lr", 0.005),
            val_split=train_params.get("val_split", 0.15),
            early_stop_patience=train_params.get("early_stop_patience", 5),
            model_tag=payload.get("model_tag", "dataset_model"),
            merge_seed=train_params.get("merge_seed", True),
        )
        result["loaded_samples"] = len(examples)
        return result

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def _check_dataset_dependencies_background() -> None:
    try:
        from dependency_utils import ensure_dataset_dependencies, DATASET_INSTALL_CMD
        auto_install = os.environ.get("COMPANION_AUTO_INSTALL_DATASET_DEPS", "").strip().lower() in {"1", "true", "yes", "on"}
        status = ensure_dataset_dependencies(auto_install=auto_install)
        if status.ok:
            if status.installed:
                print(f"自动安装数据集依赖完成: {status.detail}")
        else:
            print(f"数据集依赖未就绪: {status.detail}")
            print(f"请手动安装: {DATASET_INSTALL_CMD}")
    except Exception as exc:
        print(f"检查数据集依赖时出错: {exc}")


def _start_deferred_services() -> None:
    try:
        _check_dataset_dependencies_background()
    except Exception as exc:
        print(f"启动数据集依赖检查失败: {exc}")

    try:
        start_idle_explorer()
        start_routine_tracker()
        threading.Thread(target=update_background_loop, daemon=True, name="update-checker").start()
    except Exception as exc:
        print(f"启动后台例程失败: {exc}")

    try:
        plugin_mgr.load_all()
        loaded = [p.name for p in plugin_mgr.plugins.values() if p.loaded]
        if loaded:
            print(f"Plugins loaded: {', '.join(loaded)}")
    except Exception as exc:
        print(f"加载插件失败: {exc}")

    try:
        from web_learner import start_web_learner
        start_web_learner()
        print("Web learner initialized (self-study enabled)")
    except Exception as exc:
        print(f"Web learner 初始化失败: {exc}")

    try:
        from conversation_audit import start_audit_worker, is_audit_enabled
        start_audit_worker()
        if is_audit_enabled():
            print("Conversation audit worker started")
        else:
            print("Conversation audit configured (waiting for API key)")
    except Exception as exc:
        print(f"Conversation audit 初始化失败: {exc}")

    try:
        from dreaming_engine import start_dreaming_engine
        start_dreaming_engine()
        print("Dreaming engine started (background dreaming/consolidation)")
    except Exception as exc:
        print(f"Dreaming engine 初始化失败: {exc}")

    try:
        from knowledge_distillation import start_distillation_engine
        start_distillation_engine()
        print("Knowledge distillation engine started (teacher-student learning)")
    except Exception as exc:
        print(f"Knowledge distillation engine 初始化失败: {exc}")

    try:
        from proactive_engagement import start_proactive_engine
        start_proactive_engine()
        print("Proactive engagement engine started")
    except Exception as exc:
        print(f"Proactive engagement engine 初始化失败: {exc}")


def main() -> None:
    ensure_data()
    install_shutdown_handlers("web")
    record_app_start("web")
    atexit.register(lambda: record_app_stop("web"))

    if ALLOW_LAN or HOST in {"0.0.0.0", "::"}:
        token = lan_access_token()
        print(f"LAN mode enabled. Pairing token: {token}")
        print("Share this token with trusted LAN devices; non-local write requests require it.")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Companion AI running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    threading.Thread(target=_start_deferred_services, daemon=True, name="startup-services").start()
    server.serve_forever()


if __name__ == "__main__":
    main()
