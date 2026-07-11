"""
embedding_retrieval.py - 基于深度学习的语义检索系统

使用神经网络 embedding 模型进行语义相似度匹配，
比传统的 Jaccard 相似度更准确地理解语义。

支持:
- 使用 sentence-transformers (需要安装)
- 回退到 TF-IDF (无需额外依赖)
- 自动从对话历史学习
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Optional

from _paths import module_root, data_dir
from sensitive_json import read_sensitive_json

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
EMBEDDING_INDEX_FILE = DATA_DIR / "embedding_index.json"
EMBEDDING_MODEL_DIR = DATA_DIR / "embedding_model"

RULE_INSTRUCTION_MARKERS = (
    "遇到“",
    "遇到\"",
    "这类",
    "必须先",
    "先联网",
    "给出来源",
    "行为规则",
)


def _simple_tokens(text: str) -> set[str]:
    tokens = set()
    lowered = str(text or "").lower()
    for char in lowered:
        if "\u4e00" <= char <= "\u9fff":
            tokens.add(char)
    tokens.update(re.findall(r"[a-z0-9_]{2,}", lowered))
    return tokens


def _looks_like_rule_instruction(prompt: str, response: str, source: str = "") -> bool:
    response_text = str(response or "")
    source_text = str(source or "").lower()
    if source_text in {"rule", "manual_rule", "procedural_rule"}:
        return True
    marker_hits = sum(1 for marker in RULE_INSTRUCTION_MARKERS if marker in response_text)
    if marker_hits >= 2:
        return True
    return bool("最近/新进展" in response_text and "联网" in response_text)


def _safe_retrieval_match(query: str, example: dict, score: float, threshold: float) -> bool:
    prompt = str(example.get("prompt") or "")
    response = str(example.get("response") or "")
    if _looks_like_rule_instruction(prompt, response, str(example.get("source") or "")):
        return False

    query_tokens = _simple_tokens(query)
    prompt_tokens = _simple_tokens(prompt)
    if not query_tokens or not prompt_tokens:
        return False

    overlap = len(query_tokens & prompt_tokens)
    short_query = len(str(query or "").strip()) <= 4 or len(query_tokens) <= 2
    if short_query:
        return overlap >= len(query_tokens) and score >= max(threshold, 0.72)
    return overlap > 0


# ---------------------------------------------------------------------------
# Embedding 模型
# ---------------------------------------------------------------------------

class EmbeddingModel:
    """Embedding 模型：将文本转换为向量。"""
    
    def __init__(self):
        self.model = None
        self.is_neural = False
        self._tfidf_vocab = {}
        self._tfidf_idf = {}
    
    def load(self) -> bool:
        """加载模型。优先使用神经网络模型，回退到 TF-IDF。"""
        # 尝试加载 sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            model_path = EMBEDDING_MODEL_DIR / "model"
            if model_path.exists():
                self.model = SentenceTransformer(str(model_path))
                self.is_neural = True
                print("[embedding] 已加载神经网络 embedding 模型")
                return True
        except ImportError:
            pass
        
        # 回退到 TF-IDF
        self._load_tfidf()
        print("[embedding] 使用 TF-IDF 作为回退方案")
        return True
    
    def _load_tfidf(self):
        """加载 TF-IDF 模型。"""
        vocab_file = EMBEDDING_MODEL_DIR / "tfidf_vocab.json"
        idf_file = EMBEDDING_MODEL_DIR / "tfidf_idf.json"
        
        if vocab_file.exists() and idf_file.exists():
            try:
                self._tfidf_vocab = json.loads(vocab_file.read_text(encoding="utf-8"))
                self._tfidf_idf = json.loads(idf_file.read_text(encoding="utf-8"))
            except Exception:
                pass
    
    def _save_tfidf(self):
        """保存 TF-IDF 模型。"""
        EMBEDDING_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        vocab_file = EMBEDDING_MODEL_DIR / "tfidf_vocab.json"
        idf_file = EMBEDDING_MODEL_DIR / "tfidf_idf.json"
        vocab_file.write_text(json.dumps(self._tfidf_vocab, ensure_ascii=False), encoding="utf-8")
        idf_file.write_text(json.dumps(self._tfidf_idf, ensure_ascii=False), encoding="utf-8")
    
    def encode(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转换为 embedding 向量。"""
        if self.is_neural and self.model:
            embeddings = self.model.encode(texts)
            return embeddings.tolist()
        else:
            return [self._tfidf_encode(text) for text in texts]
    
    def _tfidf_encode(self, text: str) -> list[float]:
        """TF-IDF 编码。"""
        tokens = self._tokenize(text)
        vector = [0.0] * len(self._tfidf_vocab)
        
        # 计算 TF
        token_counts = {}
        for token in tokens:
            token_counts[token] = token_counts.get(token, 0) + 1
        
        # 计算 TF-IDF
        for token, count in token_counts.items():
            if token in self._tfidf_vocab:
                idx = self._tfidf_vocab[token]
                tf = count / len(tokens) if tokens else 0
                idf = self._tfidf_idf.get(token, 1.0)
                vector[idx] = tf * idf
        
        # 归一化
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        
        return vector
    
    def _tokenize(self, text: str) -> list[str]:
        """分词。"""
        tokens = []
        text = text.lower()
        
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                tokens.append(char)
        
        for word in re.findall(r'[a-z0-9_]{2,}', text):
            tokens.append(word)
        
        return tokens
    
    def train_tfidf(self, texts: list[str]):
        """从文本列表训练 TF-IDF 模型。"""
        # 构建词表
        vocab = {}
        doc_freq = {}
        
        for text in texts:
            tokens = set(self._tokenize(text))
            for token in tokens:
                if token not in vocab:
                    vocab[token] = len(vocab)
                doc_freq[token] = doc_freq.get(token, 0) + 1
        
        # 计算 IDF
        n_docs = len(texts)
        idf = {}
        for token, df in doc_freq.items():
            idf[token] = math.log((n_docs + 1) / (df + 1)) + 1
        
        self._tfidf_vocab = vocab
        self._tfidf_idf = idf
        self._save_tfidf()
    
    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """计算余弦相似度。"""
        if len(a) != len(b):
            return 0.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Embedding 检索索引
# ---------------------------------------------------------------------------

class EmbeddingIndex:
    """基于 embedding 的检索索引。"""
    
    def __init__(self):
        self.model = EmbeddingModel()
        self.examples: list[dict] = []
        self.embeddings: list[list[float]] = []
        self.loaded = False
    
    def load(self) -> dict:
        """加载索引和模型。"""
        # 加载模型
        if not self.model.load():
            return {"ok": False, "error": "模型加载失败"}
        
        # 加载索引
        if EMBEDDING_INDEX_FILE.exists():
            try:
                data = json.loads(EMBEDDING_INDEX_FILE.read_text(encoding="utf-8"))
                self.examples = data.get("examples", [])
                self.embeddings = data.get("embeddings", [])
                self.loaded = True
                return {
                    "ok": True,
                    "samples": len(self.examples),
                    "model_type": "neural" if self.model.is_neural else "tfidf"
                }
            except Exception as e:
                return {"ok": False, "error": str(e)}
        
        return {"ok": False, "error": "索引文件不存在"}
    
    def save(self):
        """保存索引。"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "examples": self.examples,
            "embeddings": self.embeddings,
        }
        EMBEDDING_INDEX_FILE.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def add_example(self, prompt: str, response: str, source: str = "user") -> int:
        """添加对话样本。"""
        example = {
            "prompt": prompt.strip(),
            "response": response.strip(),
            "source": source,
            "rating": 1,
            "timestamp": int(__import__('time').time()),
        }
        self.examples.append(example)
        
        # 计算 embedding
        embedding = self.model.encode([prompt.strip()])[0]
        self.embeddings.append(embedding)
        
        self.save()
        return len(self.examples) - 1
    
    def search(self, query: str, top_k: int = 3, threshold: float = 0.5) -> list[tuple[dict, float]]:
        """搜索相似对话。"""
        if not self.loaded or not self.examples:
            return []
        
        # 编码查询
        query_embedding = self.model.encode([query])[0]
        
        # 计算相似度
        scores = []
        for i, ex in enumerate(self.examples):
            if ex.get("rating", 1) <= 0:
                continue
            
            if i < len(self.embeddings):
                score = self.model.cosine_similarity(query_embedding, self.embeddings[i])
                if score >= threshold and _safe_retrieval_match(query, ex, score, threshold):
                    scores.append((ex, score))
        
        # 排序
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]
    
    def get_best_match(self, query: str, threshold: float = 0.5) -> tuple[Optional[dict], float]:
        """获取最佳匹配。"""
        results = self.search(query, top_k=1, threshold=threshold)
        if results:
            return results[0]
        return None, 0.0
    
    def rebuild_from_training(self, training_file: Path) -> int:
        """从 training.json 重建索引。"""
        if not training_file.exists():
            return 0
        
        try:
            data = read_sensitive_json(training_file, {"examples": [], "feedback": []})
        except Exception:
            return 0
        
        # 清空现有数据
        self.examples = []
        self.embeddings = []
        
        # 收集所有文本用于训练 TF-IDF
        texts = []
        examples_to_add = []
        
        for item in data.get("examples", []):
            if item.get("rating", 1) <= 0:
                continue
            prompt = item.get("prompt", "")
            response = item.get("response", "")
            source = item.get("source", "imported")
            if prompt and not _looks_like_rule_instruction(prompt, response, source):
                texts.append(prompt)
                examples_to_add.append(item)
        
        # 训练 TF-IDF（如果使用）
        if not self.model.is_neural:
            self.model.train_tfidf(texts)
        
        # 添加样本
        for item in examples_to_add:
            self.add_example(
                item.get("prompt", ""),
                item.get("response", ""),
                item.get("source", "imported")
            )
        
        self.loaded = True
        return len(self.examples)
    
    def stats(self) -> dict:
        """统计信息。"""
        return {
            "total": len(self.examples),
            "active": sum(1 for ex in self.examples if ex.get("rating", 1) > 0),
            "model_type": "neural" if self.model.is_neural else "tfidf",
        }


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------

_embedding_index = EmbeddingIndex()


def get_embedding_index() -> EmbeddingIndex:
    return _embedding_index


def is_embedding_available() -> bool:
    return _embedding_index.loaded
