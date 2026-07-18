"""
hybrid_chat.py - 混合对话系统（深度学习增强版）
结合检索、Tiny LLM 和规则系统

策略:
1. 先检索高相似度匹配 (使用 embedding 语义检索)
2. 如果检索不到，尝试 Tiny LLM 生成
3. 如果 Tiny LLM 不可用或置信度低，使用规则模板
4. 自动从对话历史中学习
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from _paths import module_root, data_dir
from dialogue_skills import handle_dialogue_skill_command, match_dialogue_skill, skill_reply
from memory_transfer import handle_memory_transfer_command
from remote_llm import call_remote_llm, handle_remote_llm_command, is_remote_llm_ready, load_remote_llm_config
from routine_tracker import handle_routine_command
from user_profile import handle_profile_command, observe_user_message, profile_context

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
CHAT_MODE_FILE = DATA_DIR / "chat_mode.json"
AUTO_LEARN_FILE = DATA_DIR / "auto_learn.json"


# ---------------------------------------------------------------------------
# 对话模式配置
# ---------------------------------------------------------------------------

CHAT_MODES = {
    "retrieval": {
        "name": "检索模式",
        "description": "使用语义相似度匹配，快速稳定",
        "requires_training": False,
        "requires_gpu": False,
    },
    "tiny_llm": {
        "name": "Tiny LLM 模式",
        "description": "小型神经网络生成，需要训练",
        "requires_training": True,
        "requires_gpu": False,  # CPU 也可以，只是慢
    },
    "sparse_tiny_llm": {
        "name": "稀疏增强模式",
        "description": "稀疏注意力 + 盘古 pi 级数激活与增强短路；兼容旧稀疏权重",
        "requires_training": True,
        "requires_gpu": False,
    },
    "pangu_pi_sparse_tiny_llm": {
        "name": "盘古 pi 稀疏模式",
        "description": "稀疏注意力 + 增强短路 + 级数激活；需要单独训练",
        "requires_training": True,
        "requires_gpu": False,
        "hidden": True,
    },
    "hybrid": {
        "name": "混合模式",
        "description": "检索 + 可用大模型 + 盘古 pi/稀疏 Tiny LLM + 规则",
        "requires_training": True,
        "requires_gpu": False,
    },
    "local_llm": {
        "name": "本地 LLM 模式",
        "description": "使用微调的大模型，需要 GPU",
        "requires_training": True,
        "requires_gpu": True,
    },
    "api_llm": {
        "name": "大模型接口模式",
        "description": "使用 OpenAI-compatible API 生成回复，记忆和技能仍保存在本机",
        "requires_training": False,
        "requires_gpu": False,
    },
}


def get_chat_mode() -> str:
    """获取当前对话模式。"""
    if CHAT_MODE_FILE.exists():
        try:
            data = json.loads(CHAT_MODE_FILE.read_text(encoding="utf-8"))
            mode = data.get("mode", "hybrid")
            return "sparse_tiny_llm" if mode == "pangu_pi_sparse_tiny_llm" else mode
        except Exception:
            pass
    return "hybrid"  # 默认混合模式


def set_chat_mode(mode: str) -> dict:
    """设置对话模式。"""
    if mode == "pangu_pi_sparse_tiny_llm":
        mode = "sparse_tiny_llm"
    if mode not in CHAT_MODES:
        return {"ok": False, "error": f"未知模式：{mode}"}
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHAT_MODE_FILE.write_text(
        json.dumps({"mode": mode}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return {"ok": True, "mode": mode}


def list_chat_modes() -> list[dict]:
    """列出所有对话模式。"""
    current = get_chat_mode()
    result = []
    for key, info in CHAT_MODES.items():
        if info.get("hidden"):
            continue
        result.append({
            "id": key,
            "name": info["name"],
            "description": info["description"],
            "requires_training": info["requires_training"],
            "requires_gpu": info["requires_gpu"],
            "active": key == current,
        })
    return result


# ---------------------------------------------------------------------------
# 自动学习
# ---------------------------------------------------------------------------

def load_auto_learn_config() -> dict:
    """加载自动学习配置。"""
    if AUTO_LEARN_FILE.exists():
        try:
            return json.loads(AUTO_LEARN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"enabled": True, "min_confidence": 0.7, "learned_count": 0}


def save_auto_learn_config(config: dict):
    """保存自动学习配置。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_LEARN_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def auto_learn_from_conversation(user_msg: str, ai_reply: str, source: str = "auto"):
    """
    自动从对话中学习。
    
    当 AI 的回复被用户接受（没有点"不对"），自动将这对 Q&A 保存为训练样本。
    """
    config = load_auto_learn_config()
    if not config.get("enabled", True):
        return
    
    # 检查是否已经有这个样本
    from embedding_retrieval import get_embedding_index, _looks_like_rule_instruction
    index = get_embedding_index()
    if _looks_like_rule_instruction(user_msg, ai_reply, source):
        return
    
    # 简单去重：检查是否已存在相似的 prompt
    for ex in index.examples:
        if ex.get("prompt", "") == user_msg.strip():
            return  # 已存在
    
    # 添加为训练样本
    index.add_example(user_msg.strip(), ai_reply.strip(), source=source)
    
    # 更新计数
    config["learned_count"] = config.get("learned_count", 0) + 1
    save_auto_learn_config(config)


# ---------------------------------------------------------------------------
# 混合对话引擎
# ---------------------------------------------------------------------------

class HybridChatbot:
    """混合对话系统（深度学习增强版）。"""
    
    def __init__(self):
        self.retrieval = None
        self.embedding_index = None
        self.tiny_llm = None
        self.sparse_tiny_llm = None
        self.pangu_pi_tiny_llm = None
        self.local_llm = None
        self.initialized = False

    @staticmethod
    def _tiny_reply(message: str, history: list[tuple[str, str]] | None, model) -> str:
        """Generate a TinyLLM reply using the persisted local answer preference."""
        try:
            from tiny_llm import load_deep_reply_config
            deep_reply = load_deep_reply_config()["enabled"]
        except Exception:
            deep_reply = False
        return model.chat(message, history, deep_reply=deep_reply)
    
    def initialize(self) -> dict:
        """初始化各组件。"""
        status = {"retrieval": False, "embedding": False, "tiny_llm": False, "sparse_tiny_llm": False, "pangu_pi_tiny_llm": False, "local_llm": False}
        
        # 初始化 embedding 检索（优先）
        try:
            from embedding_retrieval import get_embedding_index
            self.embedding_index = get_embedding_index()
            result = self.embedding_index.load()
            status["embedding"] = result.get("ok", False)
            status["embedding_samples"] = result.get("samples", 0)
            status["embedding_model"] = result.get("model_type", "unknown")
        except Exception as e:
            status["embedding_error"] = str(e)
        
        # 初始化传统检索（回退）
        try:
            from retrieval_chat import get_retrieval_chatbot
            self.retrieval = get_retrieval_chatbot()
            result = self.retrieval.load()
            status["retrieval"] = result.get("ok", False)
            status["retrieval_samples"] = result.get("samples", 0)
        except Exception as e:
            status["retrieval_error"] = str(e)
        
        # 初始化 Tiny LLM
        try:
            from tiny_llm import get_tiny_llm, MODEL_FILE
            if MODEL_FILE.exists():
                self.tiny_llm = get_tiny_llm()
                result = self.tiny_llm.load()
                status["tiny_llm"] = result.get("ok", False)
        except Exception as e:
            status["tiny_llm_error"] = str(e)

        try:
            from tiny_llm import get_sparse_tiny_llm, SPARSE_MODEL_FILE
            if SPARSE_MODEL_FILE.exists():
                self.sparse_tiny_llm = get_sparse_tiny_llm()
                result = self.sparse_tiny_llm.load()
                status["sparse_tiny_llm"] = result.get("ok", False)
        except Exception as e:
            status["sparse_tiny_llm_error"] = str(e)

        try:
            from tiny_llm import get_pangu_pi_tiny_llm, PANGU_PI_MODEL_FILE
            if PANGU_PI_MODEL_FILE.exists():
                self.pangu_pi_tiny_llm = get_pangu_pi_tiny_llm()
                result = self.pangu_pi_tiny_llm.load()
                status["pangu_pi_tiny_llm"] = result.get("ok", False)
        except Exception as e:
            status["pangu_pi_tiny_llm_error"] = str(e)
        
        # 初始化本地 LLM (大模型)
        try:
            from llm_inference import get_local_llm
            self.local_llm = get_local_llm()
            if self.local_llm.loaded:
                status["local_llm"] = True
        except Exception as e:
            status["local_llm_error"] = str(e)
        
        self.initialized = True
        return status
    
    def chat(self, message: str, history: list[tuple[str, str]] | None = None) -> tuple[str, str]:
        """
        对话。
        
        返回：(回复，来源)
        来源："embedding", "retrieval", "tiny_llm", "local_llm", "rules"
        """
        user_message = self._extract_user_message(message)
        profile_command_reply = handle_profile_command(user_message)
        if profile_command_reply is not None:
            return profile_command_reply, "profile"

        memory_transfer_reply = handle_memory_transfer_command(user_message)
        if memory_transfer_reply is not None:
            return memory_transfer_reply, "memory_transfer"

        routine_command_reply = handle_routine_command(user_message)
        if routine_command_reply is not None:
            return routine_command_reply, "routine"

        skill_command_reply = handle_dialogue_skill_command(user_message)
        if skill_command_reply is not None:
            return skill_command_reply, "dialogue_skill"

        remote_command_reply = handle_remote_llm_command(user_message)
        if remote_command_reply is not None:
            return remote_command_reply, "api_llm_config"

        observe_user_message(user_message)
        matched_skill = match_dialogue_skill(user_message)
        if matched_skill:
            return skill_reply(matched_skill, profile_context()), "dialogue_skill"

        profile_note = profile_context()
        if profile_note and "[用户画像]" not in message:
            message = f"[用户画像]\n{profile_note}\n\n{message}"

        if not self.initialized:
            self.initialize()
        
        mode = get_chat_mode()
        retrieval_query = user_message or message
        
        # 1. 检索模式
        if mode == "retrieval":
            # 优先使用 embedding 检索
            if self.embedding_index and self.embedding_index.loaded:
                match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.5)
                if match:
                    return match.get("response", ""), "embedding"
            # 回退到传统检索
            if self.retrieval:
                reply = self.retrieval.chat(retrieval_query, history)
                if reply:
                    return reply, "retrieval"
            return self._fallback_reply(retrieval_query), "rules"
        
        # 2. Tiny LLM 模式
        if mode == "tiny_llm":
            if self.tiny_llm and self.tiny_llm.loaded:
                reply = self._tiny_reply(message, history, self.tiny_llm)
                if reply and reply != "...":
                    return reply, "tiny_llm"
            # 回退到检索
            if self.embedding_index and self.embedding_index.loaded:
                match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.4)
                if match:
                    return match.get("response", ""), "embedding"
            if self.retrieval:
                reply = self.retrieval.chat(retrieval_query, history)
                if reply:
                    return reply, "retrieval"
            return self._fallback_reply(retrieval_query), "rules"

        # 2.1 Sparse Tiny LLM mode. It uses separately trained weights so a
        # dense checkpoint can never be loaded into the sparse architecture.
        if mode == "sparse_tiny_llm":
            if self.pangu_pi_tiny_llm and self.pangu_pi_tiny_llm.loaded:
                reply = self._tiny_reply(message, history, self.pangu_pi_tiny_llm)
                if reply and reply != "...":
                    return reply, "pangu_pi_sparse_tiny_llm"
            if self.sparse_tiny_llm and self.sparse_tiny_llm.loaded:
                reply = self._tiny_reply(message, history, self.sparse_tiny_llm)
                if reply and reply != "...":
                    return reply, "sparse_tiny_llm"
            if self.embedding_index and self.embedding_index.loaded:
                match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.4)
                if match:
                    return match.get("response", ""), "embedding"
            if self.retrieval:
                reply = self.retrieval.chat(retrieval_query, history)
                if reply:
                    return reply, "retrieval"
            return self._fallback_reply(retrieval_query), "rules"

        if mode == "pangu_pi_sparse_tiny_llm":
            if self.pangu_pi_tiny_llm and self.pangu_pi_tiny_llm.loaded:
                reply = self._tiny_reply(message, history, self.pangu_pi_tiny_llm)
                if reply and reply != "...":
                    return reply, "pangu_pi_sparse_tiny_llm"
            if self.embedding_index and self.embedding_index.loaded:
                match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.4)
                if match:
                    return match.get("response", ""), "embedding"
            if self.retrieval:
                reply = self.retrieval.chat(retrieval_query, history)
                if reply:
                    return reply, "retrieval"
            return self._fallback_reply(retrieval_query), "rules"
        
        # 3. 本地 LLM 模式
        if mode == "local_llm":
            if self.local_llm and self.local_llm.loaded:
                reply = self.local_llm.chat(message, history)
                if reply and not reply.startswith("["):
                    return reply, "local_llm"
            # 回退
            if self.embedding_index and self.embedding_index.loaded:
                match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.4)
                if match:
                    return match.get("response", ""), "embedding"
            if self.retrieval:
                reply = self.retrieval.chat(retrieval_query, history)
                if reply:
                    return reply, "retrieval"
            return self._fallback_reply(retrieval_query), "rules"

        # 4. 大模型接口模式
        if mode == "api_llm":
            if is_remote_llm_ready():
                reply = call_remote_llm(message, history)
                if reply and not reply.startswith("["):
                    return reply, "api_llm"
            if self.embedding_index and self.embedding_index.loaded:
                match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.4)
                if match:
                    return match.get("response", ""), "embedding"
            if self.retrieval:
                reply = self.retrieval.chat(retrieval_query, history)
                if reply:
                    return reply, "retrieval"
            return self._fallback_reply(retrieval_query), "rules"
        
        # 5. 混合模式 (默认)
        # 5.1 尝试本地大模型
        if self.local_llm and self.local_llm.loaded:
            reply = self.local_llm.chat(message, history)
            if reply and not reply.startswith("["):
                return reply, "local_llm"
        
        # 5.2 尝试大模型接口
        remote_config = load_remote_llm_config()
        if remote_config.get("enabled_for_hybrid") and is_remote_llm_ready(remote_config):
            reply = call_remote_llm(message, history, remote_config)
            if reply and not reply.startswith("["):
                return reply, "api_llm"

        # 5.3 统一的稀疏增强模型：优先盘古 pi 权重，随后兼容旧稀疏权重。
        if self.pangu_pi_tiny_llm and self.pangu_pi_tiny_llm.loaded:
            reply = self._tiny_reply(message, history, self.pangu_pi_tiny_llm)
            if reply and reply != "...":
                return reply, "pangu_pi_sparse_tiny_llm"

        # 5.4 尝试普通稀疏 Tiny LLM。
        if self.sparse_tiny_llm and self.sparse_tiny_llm.loaded:
            reply = self._tiny_reply(message, history, self.sparse_tiny_llm)
            if reply and reply != "...":
                return reply, "sparse_tiny_llm"

        # 5.5 高置信度检索。
        if self.embedding_index and self.embedding_index.loaded:
            match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.6)
            if match:
                return match.get("response", ""), "embedding"
        if self.retrieval:
            match, score = self.retrieval.index.get_best_match(retrieval_query, threshold=0.5)
            if match:
                return match.get("response", ""), "retrieval"

        # 5.6 尝试普通 Tiny LLM
        if self.tiny_llm and self.tiny_llm.loaded:
            reply = self._tiny_reply(message, history, self.tiny_llm)
            if reply and reply != "...":
                return reply, "tiny_llm"
        
        # 5.7 低阈值 embedding 检索
        if self.embedding_index and self.embedding_index.loaded:
            match, score = self.embedding_index.get_best_match(retrieval_query, threshold=0.35)
            if match:
                return match.get("response", ""), "embedding"
        
        # 5.8 低阈值传统检索
        if self.retrieval:
            match, score = self.retrieval.index.get_best_match(retrieval_query, threshold=0.28)
            if match:
                return match.get("response", ""), "retrieval"
        
        # 5.9 规则兜底
        return self._fallback_reply(retrieval_query), "rules"
    
    def _fallback_reply(self, message: str) -> str:
        """规则兜底回复。"""
        from retrieval_chat import classify_intent, generate_from_template
        intent = classify_intent(message)
        return generate_from_template(intent)

    def _extract_user_message(self, message: str) -> str:
        marker = "[用户消息]\n"
        if marker in message:
            return message.split(marker, 1)[1].split("\n\n", 1)[0].strip()
        return message.strip()
    
    def status(self) -> dict:
        """状态信息。"""
        return {
            "mode": get_chat_mode(),
            "modes": list_chat_modes(),
            "embedding": self.embedding_index.stats() if self.embedding_index and self.embedding_index.loaded else None,
            "retrieval": self.retrieval.stats() if self.retrieval else None,
            "tiny_llm": self.tiny_llm.loaded if self.tiny_llm else False,
            "sparse_tiny_llm": self.sparse_tiny_llm.loaded if self.sparse_tiny_llm else False,
            "pangu_pi_tiny_llm": self.pangu_pi_tiny_llm.loaded if self.pangu_pi_tiny_llm else False,
            "local_llm": self.local_llm.loaded if self.local_llm else False,
            "api_llm": is_remote_llm_ready(),
        }


# 全局实例
_hybrid_chatbot = HybridChatbot()


def get_hybrid_chatbot() -> HybridChatbot:
    return _hybrid_chatbot


def reload_tiny_models() -> dict:
    """Reload persisted TinyLLM artifacts after a local model version switch."""
    from tiny_llm import (
        MODEL_FILE, PANGU_PI_MODEL_FILE, SPARSE_MODEL_FILE,
        get_pangu_pi_tiny_llm, get_sparse_tiny_llm, get_tiny_llm,
    )
    targets = [
        ("tiny_llm", get_tiny_llm, MODEL_FILE),
        ("sparse_tiny_llm", get_sparse_tiny_llm, SPARSE_MODEL_FILE),
        ("pangu_pi_tiny_llm", get_pangu_pi_tiny_llm, PANGU_PI_MODEL_FILE),
    ]
    result: dict[str, object] = {"ok": True, "models": {}}
    for attribute, getter, path in targets:
        model = getter()
        model.unload()
        if path.exists():
            loaded = model.load()
            result["models"][attribute] = loaded
            if not loaded.get("ok"):
                result["ok"] = False
        else:
            result["models"][attribute] = {"ok": True, "skipped": True}
        setattr(_hybrid_chatbot, attribute, model if model.loaded else None)
    _hybrid_chatbot.initialized = True
    return result


def hybrid_chat(message: str, history: list[tuple[str, str]] | None = None) -> tuple[str, str]:
    """混合对话，返回 (回复，来源)。"""
    return _hybrid_chatbot.chat(message, history)


def hybrid_chat_simple(message: str, history: list[tuple[str, str]] | None = None) -> str:
    """简化版混合对话，只返回回复。"""
    reply, _ = _hybrid_chatbot.chat(message, history)
    return reply


def rebuild_embedding_index() -> dict:
    """重建 embedding 索引。"""
    from embedding_retrieval import get_embedding_index
    from app import TRAINING_FILE
    
    index = get_embedding_index()
    count = index.rebuild_from_training(TRAINING_FILE)
    
    return {
        "ok": True,
        "rebuilt": count,
        "total": len(index.examples),
        "model_type": "neural" if index.model.is_neural else "tfidf",
    }
