"""
retrieval_chat.py - 检索增强对话系统
不训练模型，使用 embedding 相似度匹配找到最相关的对话

特点:
- 不需要 GPU
- 即时可用
- 可解释性强
- 支持动态添加训练样本
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
RETRIEVAL_INDEX_FILE = DATA_DIR / "retrieval_index.json"


# ---------------------------------------------------------------------------
# 分词和相似度
# ---------------------------------------------------------------------------

STOPWORDS = {
    "的", "了", "和", "是", "我", "你", "在", "有", "就", "也", "都", "很",
    "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on",
}


def tokenize(text: str) -> set[str]:
    """分词：中文按字，英文按词。"""
    words = set()
    text = text.lower()
    
    # 中文按字
    for char in text:
        if '\u4e00' <= char <= '\u9fff' and char not in STOPWORDS:
            words.add(char)
    
    # 英文按词
    for word in re.findall(r'[a-z0-9_]{2,}', text):
        if word not in STOPWORDS:
            words.add(word)
    
    return words


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# 检索索引
# ---------------------------------------------------------------------------

class RetrievalIndex:
    """检索索引：存储对话样本，支持相似度匹配。"""
    
    def __init__(self):
        self.examples: list[dict] = []
        self.token_cache: dict[int, set[str]] = {}
    
    def load(self) -> bool:
        """加载索引。"""
        if RETRIEVAL_INDEX_FILE.exists():
            try:
                data = json.loads(RETRIEVAL_INDEX_FILE.read_text(encoding="utf-8"))
                self.examples = data.get("examples", [])
                self._build_cache()
                return True
            except Exception:
                pass
        return False
    
    def save(self):
        """保存索引。"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {"examples": self.examples}
        RETRIEVAL_INDEX_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def _build_cache(self):
        """构建 token 缓存。"""
        self.token_cache = {}
        for i, ex in enumerate(self.examples):
            prompt = ex.get("prompt", "")
            self.token_cache[i] = tokenize(prompt)
    
    def add_example(self, prompt: str, response: str, source: str = "user") -> int:
        """添加对话样本。"""
        example = {
            "prompt": prompt.strip(),
            "response": response.strip(),
            "source": source,
            "rating": 1,
        }
        self.examples.append(example)
        idx = len(self.examples) - 1
        self.token_cache[idx] = tokenize(prompt)
        self.save()
        return idx
    
    def remove_example(self, index: int) -> bool:
        """删除对话样本。"""
        if 0 <= index < len(self.examples):
            self.examples.pop(index)
            self._build_cache()
            self.save()
            return True
        return False
    
    def search(self, query: str, top_k: int = 3, threshold: float = 0.2) -> list[tuple[dict, float]]:
        """搜索相似对话。"""
        query_tokens = tokenize(query)
        
        scores = []
        for i, ex in enumerate(self.examples):
            if ex.get("rating", 1) <= 0:
                continue
            
            cached_tokens = self.token_cache.get(i)
            if cached_tokens is None:
                cached_tokens = tokenize(ex.get("prompt", ""))
                self.token_cache[i] = cached_tokens
            
            score = jaccard_similarity(query_tokens, cached_tokens)
            if score >= threshold:
                scores.append((ex, score))
        
        # 排序取 top-k
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]
    
    def get_best_match(self, query: str, threshold: float = 0.28) -> tuple[Optional[dict], float]:
        """获取最佳匹配。"""
        results = self.search(query, top_k=1, threshold=threshold)
        if results:
            return results[0]
        return None, 0.0
    
    def import_from_training(self, training_file: Path) -> int:
        """从 training.json 导入样本。"""
        if not training_file.exists():
            return 0
        
        try:
            data = read_sensitive_json(training_file, {"examples": [], "feedback": []})
        except Exception:
            return 0
        
        count = 0
        existing_prompts = {ex.get("prompt", "") for ex in self.examples}
        
        for item in data.get("examples", []):
            if item.get("rating", 1) <= 0:
                continue
            prompt = item.get("prompt", "")
            if prompt and prompt not in existing_prompts:
                self.add_example(
                    prompt,
                    item.get("response", ""),
                    item.get("source", "imported")
                )
                existing_prompts.add(prompt)
                count += 1
        
        return count
    
    def stats(self) -> dict:
        """统计信息。"""
        return {
            "total": len(self.examples),
            "active": sum(1 for ex in self.examples if ex.get("rating", 1) > 0),
        }


# ---------------------------------------------------------------------------
# 对话生成
# ---------------------------------------------------------------------------

# 模板回复
TEMPLATES = {
    "greeting": [
        "你好！有什么我可以帮助你的吗？",
        "嗨！今天过得怎么样？",
        "你好呀，想聊点什么？",
    ],
    "farewell": [
        "再见！下次再聊。",
        "拜拜，期待下次见面！",
        "好的，先这样，有空再来找我。",
    ],
    "thanks": [
        "不客气！很高兴能帮到你。",
        "没事，这是应该的。",
        "不用谢，有什么其他问题随时问我。",
    ],
    "unknown": [
        "这个我还不太懂，你可以教我。",
        "我不太确定怎么回答，你可以换个方式问吗？",
        "这个问题我需要学习一下，你可以用 /teach 教我。",
    ],
    "emotion_comfort": [
        "听起来你现在有点撑着。我在这儿。",
        "我理解你的感受，有时候事情就是这样。",
        "没关系，慢慢来，我会陪着你。",
    ],
}


def classify_intent(text: str) -> str:
    """简单意图分类。"""
    text_lower = text.lower()
    stripped = text.strip()

    # 长文本不可能是简单问候/告别/感谢，跳过模板匹配
    # 避免历史数据、OCR结果等长内容误触发问候模板
    if len(stripped) > 50:
        return "unknown"

    # 问候：仅短消息才匹配
    if any(w in text_lower for w in ["你好", "嗨", "hi", "hello", "早上好", "晚上好"]):
        return "greeting"

    # 告别
    if any(w in text_lower for w in ["再见", "拜拜", "bye", "晚安", "先走了"]):
        return "farewell"

    # 感谢
    if any(w in text_lower for w in ["谢谢", "感谢", "thanks", "thank you", "多谢"]):
        return "thanks"

    # 情绪安慰
    if any(w in text_lower for w in ["难过", "伤心", "累", "压力", "焦虑", "不开心", "郁闷"]):
        return "emotion_comfort"

    return "unknown"


def generate_from_template(intent: str) -> str:
    """从模板生成回复。"""
    import random
    templates = TEMPLATES.get(intent, TEMPLATES["unknown"])
    return random.choice(templates)


# ---------------------------------------------------------------------------
# 主对话类
# ---------------------------------------------------------------------------

class RetrievalChatbot:
    """检索增强对话机器人。"""
    
    def __init__(self):
        self.index = RetrievalIndex()
        self.loaded = False
    
    def load(self) -> dict:
        """加载索引。"""
        # 尝试加载索引
        if self.index.load():
            self.loaded = True
            stats = self.index.stats()
            return {
                "ok": True,
                "samples": stats["total"],
                "active": stats["active"],
            }
        
        # 尝试从 training.json 导入
        training_file = DATA_DIR / "training.json"
        if training_file.exists():
            count = self.index.import_from_training(training_file)
            if count > 0:
                self.loaded = True
                return {
                    "ok": True,
                    "samples": count,
                    "imported": True,
                }
        
        return {"ok": False, "error": "没有对话样本"}
    
    def chat(self, message: str, history: list[tuple[str, str]] | None = None) -> str:
        """对话。"""
        if not self.loaded:
            self.load()
        
        # 搜索相似对话
        match, score = self.index.get_best_match(message, threshold=0.28)
        
        if match and score >= 0.28:
            return match.get("response", "")
        
        # 没有匹配，使用模板
        intent = classify_intent(message)
        return generate_from_template(intent)
    
    def teach(self, prompt: str, response: str) -> dict:
        """教新对话。"""
        idx = self.index.add_example(prompt, response, source="teach")
        return {
            "ok": True,
            "index": idx,
            "message": f"已学习：{prompt} => {response}",
        }
    
    def forget(self, index: int) -> dict:
        """忘记对话。"""
        if self.index.remove_example(index):
            return {"ok": True, "message": f"已删除第 {index} 条"}
        return {"ok": False, "error": "索引不存在"}
    
    def stats(self) -> dict:
        """统计信息。"""
        return self.index.stats()


# 全局实例
_retrieval_chatbot = RetrievalChatbot()


def get_retrieval_chatbot() -> RetrievalChatbot:
    return _retrieval_chatbot


def is_retrieval_available() -> bool:
    return _retrieval_chatbot.loaded


def retrieval_chat(message: str, history: list[tuple[str, str]] | None = None) -> str:
    if not _retrieval_chatbot.loaded:
        _retrieval_chatbot.load()
    return _retrieval_chatbot.chat(message, history)
