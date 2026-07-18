"""
tiny_llm.py - 从零训练的小型 Transformer 对话模型
不依赖预训练基座模型，直接在对话数据上训练

模型架构: MiniGPT (约 5-15M 参数)
- 词表: 从训练数据构建 (中文按字切分，英文按词切分)
- 嵌入: 256 维
- 层数: 4-6 层 Transformer
- 头数: 4-8 头
- 上下文: 128-256 token

训练: 标准因果语言模型 (next token prediction)
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Generator

from _paths import module_root, data_dir, resource_dir, runtime_python_exe, runtime_subprocess_env

ROOT = module_root(__file__)
MODEL_DIR = data_dir(ROOT) / "tiny_llm"
MODEL_FILE = MODEL_DIR / "model.pt"
VOCAB_FILE = MODEL_DIR / "vocab.json"
CONFIG_FILE = MODEL_DIR / "config.json"
SPARSE_MODEL_FILE = MODEL_DIR / "sparse_model.pt"
SPARSE_VOCAB_FILE = MODEL_DIR / "sparse_vocab.json"
SPARSE_CONFIG_FILE = MODEL_DIR / "sparse_config.json"
PANGU_PI_MODEL_FILE = MODEL_DIR / "pangu_pi_sparse_model.pt"
PANGU_PI_VOCAB_FILE = MODEL_DIR / "pangu_pi_sparse_vocab.json"
PANGU_PI_CONFIG_FILE = MODEL_DIR / "pangu_pi_sparse_config.json"
DEEP_REPLY_CONFIG_FILE = MODEL_DIR / "deep_reply_config.json"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DEFAULT_DEEP_REPLY_CONFIG = {
    "enabled": False,
}


def load_deep_reply_config() -> dict:
    """Load the optional local answer-structuring preference.

    This is deliberately not presented as a reasoning or chain-of-thought
    feature: TinyLLM has not been trained to produce reliable hidden traces.
    """
    config = dict(DEFAULT_DEEP_REPLY_CONFIG)
    try:
        if DEEP_REPLY_CONFIG_FILE.exists():
            saved = json.loads(DEEP_REPLY_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update(saved)
    except (OSError, json.JSONDecodeError):
        pass
    config["enabled"] = bool(config.get("enabled"))
    return config


def save_deep_reply_config(updates: dict | None = None) -> dict:
    """Persist the local deep-answer preference without storing chat content."""
    config = load_deep_reply_config()
    if isinstance(updates, dict) and "enabled" in updates:
        config["enabled"] = bool(updates["enabled"])
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    DEEP_REPLY_CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return config


def _runtime_worker_path() -> Path:
    return resource_dir(__file__) / "tiny_llm_runtime_worker.py"


def _run_runtime_worker(payload: dict, timeout: int = 900) -> dict:
    """Execute a Tiny LLM operation in the PyTorch component environment."""
    worker = _runtime_worker_path()
    if not worker.is_file():
        return {"ok": False, "error": f"缺少 Tiny LLM 运行时工作器：{worker}"}
    runtime = os.environ.get("COMPANION_RUNTIME_PYTHON", "").strip()
    if not runtime:
        try:
            runtime = runtime_python_exe(create=False)
        except Exception as exc:
            return {"ok": False, "error": f"组件 Python 不可用：{exc}"}
    if not Path(runtime).is_file():
        return {"ok": False, "error": f"组件 Python 不存在：{runtime}"}
    env = runtime_subprocess_env(runtime)
    # Never put the PyInstaller _internal directory on PYTHONPATH. It contains
    # the launcher's python314.dll, which conflicts with the component venv's
    # Python 3.12 extension modules. Executing the worker by absolute path
    # already makes its source modules importable.
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        process = subprocess.run(
            [runtime, str(worker)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(Path(runtime).parent),
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return {"ok": False, "error": f"启动 Tiny LLM 运行时失败：{exc}"}
    try:
        result = json.loads((process.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        detail = (process.stderr or process.stdout or "运行时没有返回结果").strip()
        return {"ok": False, "error": f"Tiny LLM 运行时失败：{detail[:500]}"}
    if not result.get("ok") and process.returncode and not result.get("error"):
        result["error"] = (process.stderr or "Tiny LLM 运行时执行失败").strip()[:500]
    return result


def train_tiny_llm_in_runtime(**kwargs) -> dict:
    """Train with the Python environment whose torch state Settings reports."""
    return _run_runtime_worker({"action": "train", **kwargs})


def evaluate_tiny_llm_in_runtime(**kwargs) -> dict:
    """Evaluate an active or staged checkpoint in the component runtime."""
    return _run_runtime_worker({"action": "evaluate", **kwargs})


# ---------------------------------------------------------------------------
# 分词器
# ---------------------------------------------------------------------------

class SimpleTokenizer:
    """简单分词器：中文按字，英文按词，支持 BPE 基础。"""
    
    def __init__(self):
        self.token_to_id = {"<pad>": 0, "<unk>": 1, "<bos>": 2, "<eos>": 3}
        self.id_to_token = {v: k for k, v in self.token_to_id.items()}
        self.vocab_size = len(self.token_to_id)
    
    def build_vocab(self, texts: list[str], min_freq: int = 2, max_vocab: int = 8000):
        """从文本列表构建词表。"""
        # 统计频率
        freq = {}
        for text in texts:
            for token in self._tokenize(text):
                freq[token] = freq.get(token, 0) + 1
        
        # 按频率排序，取 top N
        sorted_tokens = sorted(freq.items(), key=lambda x: -x[1])
        for token, count in sorted_tokens:
            if count < min_freq:
                break
            if len(self.token_to_id) >= max_vocab:
                break
            if token not in self.token_to_id:
                idx = len(self.token_to_id)
                self.token_to_id[token] = idx
                self.id_to_token[idx] = token
        
        self.vocab_size = len(self.token_to_id)
        print(f"[tiny_llm] 词表大小: {self.vocab_size}")
    
    def _tokenize(self, text: str) -> list[str]:
        """分词：中文按字，英文按词。"""
        tokens = []
        text = text.lower().strip()
        
        # 分离中文和英文
        i = 0
        while i < len(text):
            char = text[i]
            if '\u4e00' <= char <= '\u9fff':
                # 中文字符
                tokens.append(char)
                i += 1
            elif char.isalnum():
                # 英文单词
                word = ""
                while i < len(text) and text[i].isalnum():
                    word += text[i]
                    i += 1
                if len(word) >= 2:
                    tokens.append(word)
            else:
                # 标点/空格
                if char.strip():
                    tokens.append(char)
                i += 1
        
        return tokens
    
    def encode(self, text: str, max_len: int = 128) -> list[int]:
        """文本转 token ID。"""
        tokens = self._tokenize(text)
        ids = [self.token_to_id.get(t, 1) for t in tokens]  # 1 = <unk>
        ids = [2] + ids[:max_len - 2] + [3]  # <bos> ... <eos>
        # 填充
        ids = ids + [0] * (max_len - len(ids))
        return ids[:max_len]
    
    def decode(self, ids: list[int]) -> str:
        """token ID 转文本。"""
        tokens = []
        for idx in ids:
            if idx == 3:  # <eos>
                break
            if idx in (0, 1, 2):  # <pad>, <unk>, <bos>
                continue
            token = self.id_to_token.get(idx, "")
            tokens.append(token)
        
        # 合并中文和英文
        result = ""
        for token in tokens:
            if '\u4e00' <= token <= '\u9fff' or token in "，。！？、；：""''（）【】":
                result += token
            elif result and not result.endswith(" "):
                result += " " + token
            else:
                result += token
        
        return result.strip()
    
    def save(self, path: Path):
        data = {
            "token_to_id": self.token_to_id,
            "vocab_size": self.vocab_size,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def load(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.token_to_id = data["token_to_id"]
        self.id_to_token = {int(v): k for k, v in self.token_to_id.items()}
        self.vocab_size = data["vocab_size"]


# ---------------------------------------------------------------------------
# 模型定义
# ---------------------------------------------------------------------------

def create_tiny_model(vocab_size: int, config: dict | None = None):
    """创建小型 GPT 模型。"""
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        raise ImportError(f"当前 Python 无法导入 PyTorch ({__import__('sys').executable}): {exc}") from exc
    
    if config is None:
        config = {
            "embed_dim": 256,
            "num_heads": 4,
            "num_layers": 4,
            "ffn_dim": 512,
            "max_seq_len": 128,
            "dropout": 0.1,
            "attention_type": "dense",
        }

    # Fill in any missing defaults so callers can pass a partial config (e.g.
    # only embed_dim/num_heads/num_layers from algorithm_curriculum).
    defaults = {
        "embed_dim": 256,
        "num_heads": 4,
        "num_layers": 4,
        "ffn_dim": 512,
        "max_seq_len": 128,
        "dropout": 0.1,
        "attention_type": "dense",
    }
    merged = dict(defaults)
    merged.update(config)
    config = merged
    
    class TinyAttention(nn.Module):
        def __init__(self, embed_dim, num_heads, dropout):
            super().__init__()
            self.attention = nn.MultiheadAttention(embed_dim, num_heads, dropout=dropout, batch_first=True)
            self.norm = nn.LayerNorm(embed_dim)
            self.dropout = nn.Dropout(dropout)
        
        def forward(self, x, mask=None):
            attn_out, _ = self.attention(x, x, x, attn_mask=mask, need_weights=False)
            return self.norm(x + self.dropout(attn_out))

    class SparseTinyAttention(nn.Module):
        def __init__(self, embed_dim, num_heads, dropout, window, global_tokens):
            super().__init__()
            from sparse_attention import create_sparse_causal_attention

            self.attention = create_sparse_causal_attention(
                embed_dim, num_heads, dropout, window, global_tokens
            )
            self.norm = nn.LayerNorm(embed_dim)
            self.dropout = nn.Dropout(dropout)

        def forward(self, x, mask=None):
            return self.norm(x + self.dropout(self.attention(x)))

    class PanguPiSparseAttention(nn.Module):
        """Sparse AugMSA: MSA(x) + x + sum(GELU(x @ Theta_i))."""
        def __init__(self, embed_dim, num_heads, dropout, window, global_tokens, shortcut_count):
            super().__init__()
            from sparse_attention import create_sparse_causal_attention

            self.attention = create_sparse_causal_attention(
                embed_dim, num_heads, dropout, window, global_tokens
            )
            self.shortcuts = nn.ModuleList([nn.Linear(embed_dim, embed_dim, bias=False) for _ in range(shortcut_count)])
            for shortcut in self.shortcuts:
                nn.init.zeros_(shortcut.weight)
            self.norm = nn.LayerNorm(embed_dim)
            self.dropout = nn.Dropout(dropout)

        def forward(self, x, mask=None):
            augmented = sum((nn.functional.gelu(shortcut(x)) for shortcut in self.shortcuts), start=torch.zeros_like(x))
            return self.norm(x + self.dropout(self.attention(x)) + augmented)
    
    class SeriesInformedActivation(nn.Module):
        """PanGu-pi SIAF: sum_i sigma_i(a_i * x + b_i).

        Per-channel affine terms add nonlinearity with O(series_terms * d)
        work and no sequence-length-dependent state.
        """
        def __init__(self, features, series_terms):
            super().__init__()
            self.scale = nn.Parameter(torch.zeros(series_terms, features))
            self.bias = nn.Parameter(torch.zeros(series_terms, features))
            with torch.no_grad():
                self.scale[0].fill_(1.0)

        def forward(self, x):
            terms = nn.functional.gelu(x.unsqueeze(-2) * self.scale + self.bias)
            return terms.sum(dim=-2)

    class TinyFFN(nn.Module):
        def __init__(self, embed_dim, ffn_dim, dropout, pangu_pi=False, series_terms=2):
            super().__init__()
            activation = SeriesInformedActivation(ffn_dim, series_terms) if pangu_pi else nn.GELU()
            self.net = nn.Sequential(
                nn.Linear(embed_dim, ffn_dim),
                activation,
                nn.Dropout(dropout),
                nn.Linear(ffn_dim, embed_dim),
                nn.Dropout(dropout),
            )
            self.norm = nn.LayerNorm(embed_dim)
        
        def forward(self, x):
            return self.norm(x + self.net(x))
    
    class TinyTransformerBlock(nn.Module):
        def __init__(self, embed_dim, num_heads, ffn_dim, dropout, attention_type, window, global_tokens, pangu_pi, series_terms, shortcut_count):
            super().__init__()
            if pangu_pi:
                self.attn = PanguPiSparseAttention(
                    embed_dim, num_heads, dropout, window, global_tokens, shortcut_count
                )
            elif attention_type == "sparse":
                self.attn = SparseTinyAttention(embed_dim, num_heads, dropout, window, global_tokens)
            else:
                self.attn = TinyAttention(embed_dim, num_heads, dropout)
            self.ffn = TinyFFN(embed_dim, ffn_dim, dropout, pangu_pi=pangu_pi, series_terms=series_terms)
        
        def forward(self, x, mask=None):
            x = self.attn(x, mask)
            x = self.ffn(x)
            return x
    
    class TinyGPT(nn.Module):
        def __init__(self, vocab_size, config):
            super().__init__()
            self.config = config
            embed_dim = config["embed_dim"]
            max_seq_len = config["max_seq_len"]
            
            self.token_embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
            self.pos_embed = nn.Embedding(max_seq_len, embed_dim)
            self.dropout = nn.Dropout(config["dropout"])
            
            self.blocks = nn.ModuleList([
                TinyTransformerBlock(
                    embed_dim,
                    config["num_heads"],
                    config["ffn_dim"],
                    config["dropout"],
                    config.get("attention_type", "dense"),
                    int(config.get("attention_window", 32)),
                    int(config.get("global_tokens", 8)),
                    bool(config.get("pangu_pi", False)),
                    int(config.get("series_terms", 2)),
                    int(config.get("augmented_shortcuts", 1)),
                )
                for _ in range(config["num_layers"])
            ])
            
            self.head = nn.Linear(embed_dim, vocab_size, bias=False)
            
            # 因果掩码
            self.register_buffer(
                "causal_mask",
                torch.triu(torch.ones(max_seq_len, max_seq_len), diagonal=1).bool()
            )
        
        def forward(self, input_ids):
            seq_len = input_ids.size(1)
            positions = torch.arange(seq_len, device=input_ids.device)
            
            x = self.token_embed(input_ids) + self.pos_embed(positions)
            x = self.dropout(x)
            
            # Sparse attention enforces causality internally and has no dense mask.
            mask = None if self.config.get("attention_type") == "sparse" else self.causal_mask[:seq_len, :seq_len].float() * -1e9
            
            for block in self.blocks:
                x = block(x, mask)
            
            logits = self.head(x)
            return logits
    
    model = TinyGPT(vocab_size, config)
    
    # 计算参数量
    total_params = sum(p.numel() for p in model.parameters())
    print(f"[tiny_llm] 模型参数量: {total_params:,} ({total_params/1e6:.1f}M)")
    
    return model, config


# ---------------------------------------------------------------------------
# 训练
# ---------------------------------------------------------------------------

def train_tiny_llm(
    texts: list[str],
    epochs: int = 20,
    batch_size: int = 32,
    lr: float = 0.001,
    max_seq_len: int = 128,
    config: dict | None = None,
    attention_type: str = "dense",
    output_dir: str | Path | None = None,
) -> dict:
    """
    从零训练小型 LLM。
    
    参数:
        texts: 对话文本列表 (每条为完整对话，用换行分隔角色)
        epochs: 训练轮数
        batch_size: 批大小
        lr: 学习率
        max_seq_len: 最大序列长度
        config: 模型配置
    """
    # A PyInstaller executable has no normal Python standard library or torch
    # installation. Keep direct callers safe by forwarding them to the managed
    # component Python; the worker imports this same function unfrozen.
    if getattr(sys, "frozen", False):
        return train_tiny_llm_in_runtime(
            texts=texts,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            max_seq_len=max_seq_len,
            config=config,
            attention_type=attention_type,
            output_dir=str(output_dir) if output_dir else None,
        )

    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        return {"ok": False, "error": f"当前 Python 无法导入 PyTorch ({__import__('sys').executable}): {exc}"}
    
    if not texts:
        return {"ok": False, "error": "没有训练数据"}
    
    print(f"\n{'='*50}")
    if attention_type not in {"dense", "sparse", "pangu_pi_sparse"}:
        return {"ok": False, "error": f"未知注意力类型：{attention_type}"}

    print(f"  从零训练 Tiny LLM ({attention_type})")
    print(f"  数据量: {len(texts)} 条")
    print(f"  训练轮数: {epochs}")
    print(f"{'='*50}\n")
    
    # 构建词表
    tokenizer = SimpleTokenizer()
    tokenizer.build_vocab(texts)
    
    # 创建模型
    if config is None:
        config = {
            "embed_dim": 256,
            "num_heads": 4,
            "num_layers": 4,
            "ffn_dim": 512,
            "max_seq_len": max_seq_len,
            "dropout": 0.1,
            "attention_type": attention_type,
        }
    else:
        config = dict(config)
        config["attention_type"] = "sparse" if attention_type == "pangu_pi_sparse" else attention_type

    if attention_type == "pangu_pi_sparse":
        config["attention_type"] = "sparse"
    if attention_type in {"sparse", "pangu_pi_sparse"}:
        config.setdefault("attention_window", 32)
        config.setdefault("global_tokens", 8)
    if attention_type == "pangu_pi_sparse":
        config["pangu_pi"] = True
        config.setdefault("series_terms", 2)
        config.setdefault("augmented_shortcuts", 1)
    
    model, config = create_tiny_model(tokenizer.vocab_size, config)
    
    # The sparse backend relies on rolling tensor views which are reliable on
    # CPU across all supported Windows torch builds. Keep the legacy backend's
    # GPU preference unchanged.
    if attention_type in {"sparse", "pangu_pi_sparse"}:
        device = torch.device("cpu")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        try:
            import torch_directml
            device = torch_directml.device()
        except ImportError:
            device = torch.device("cpu")
    
    model = model.to(device)
    print(f"[tiny_llm] 设备: {device}")
    
    # 准备数据
    sequence_length = int(config["max_seq_len"])
    all_ids = [tokenizer.encode(text, sequence_length) for text in texts]
    data = torch.tensor(all_ids, dtype=torch.long, device=device)
    
    # 训练
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, epochs * len(data) // batch_size)
    loss_fn = nn.CrossEntropyLoss(ignore_index=0)  # 忽略 padding
    
    model.train()
    final_loss = 0.0
    
    for epoch in range(epochs):
        # 打乱数据
        perm = torch.randperm(len(data), device=device)
        data = data[perm]
        
        epoch_loss = 0.0
        n_batches = 0
        
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            
            # 输入和标签
            input_ids = batch[:, :-1]
            target_ids = batch[:, 1:]
            
            logits = model(input_ids)
            loss = loss_fn(logits.reshape(-1, logits.size(-1)), target_ids.reshape(-1))
            
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            
            epoch_loss += float(loss.detach().cpu())
            n_batches += 1
        
        final_loss = epoch_loss / max(n_batches, 1)
        
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  Epoch {epoch + 1}/{epochs}, Loss: {final_loss:.4f}")
    
    # 保存。output_dir 用于候选模型：训练不会碰当前激活模型。
    if output_dir:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        model_file = target_dir / "model.pt"
        vocab_file = target_dir / "vocab.json"
        config_file = target_dir / "config.json"
    else:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        if attention_type == "pangu_pi_sparse":
            model_file, vocab_file, config_file = PANGU_PI_MODEL_FILE, PANGU_PI_VOCAB_FILE, PANGU_PI_CONFIG_FILE
        elif attention_type == "sparse":
            model_file, vocab_file, config_file = SPARSE_MODEL_FILE, SPARSE_VOCAB_FILE, SPARSE_CONFIG_FILE
        else:
            model_file, vocab_file, config_file = MODEL_FILE, VOCAB_FILE, CONFIG_FILE
    torch.save({
        "model_state": model.state_dict(),
        "config": config,
        "vocab_size": tokenizer.vocab_size,
        "epochs": epochs,
        "samples": len(texts),
        "final_loss": final_loss,
    }, model_file)
    
    tokenizer.save(vocab_file)
    
    train_config = {
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "samples": len(texts),
        "final_loss": round(final_loss, 4),
        "model_type": f"tiny_llm_{attention_type}",
        "attention_type": attention_type,
    }
    config_file.write_text(json.dumps(train_config, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n{'='*50}")
    print(f"  训练完成!")
    print(f"  最终 Loss: {final_loss:.4f}")
    print(f"  模型: {model_file}")
    print(f"{'='*50}\n")
    
    return {
        "ok": True,
        "model_path": str(model_file),
        "samples": len(texts),
        "epochs": epochs,
        "final_loss": round(final_loss, 4),
        "vocab_size": tokenizer.vocab_size,
    }


def evaluate_tiny_llm(
    texts: list[str],
    attention_type: str = "dense",
    model_dir: str | Path | None = None,
) -> dict:
    """Return mean next-token loss for an existing checkpoint without updating it."""
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        return {"ok": False, "error": f"当前 Python 无法导入 PyTorch：{exc}"}
    if not texts:
        return {"ok": False, "error": "没有评测数据"}
    if model_dir:
        checkpoint_file = Path(model_dir) / "model.pt"
        vocab_file = Path(model_dir) / "vocab.json"
    elif attention_type == "pangu_pi_sparse":
        checkpoint_file, vocab_file = PANGU_PI_MODEL_FILE, PANGU_PI_VOCAB_FILE
    elif attention_type == "sparse":
        checkpoint_file, vocab_file = SPARSE_MODEL_FILE, SPARSE_VOCAB_FILE
    else:
        checkpoint_file, vocab_file = MODEL_FILE, VOCAB_FILE
    if not checkpoint_file.exists() or not vocab_file.exists():
        return {"ok": False, "error": "待评测模型或词表不存在"}
    try:
        tokenizer = SimpleTokenizer()
        tokenizer.load(vocab_file)
        checkpoint = torch.load(checkpoint_file, map_location="cpu", weights_only=False)
        model, config = create_tiny_model(tokenizer.vocab_size, checkpoint.get("config") or {})
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        length = int(config.get("max_seq_len", 128))
        data = torch.tensor([tokenizer.encode(text, length) for text in texts], dtype=torch.long)
        loss_fn = nn.CrossEntropyLoss(ignore_index=0)
        with torch.no_grad():
            logits = model(data[:, :-1])
            loss = loss_fn(logits.reshape(-1, logits.size(-1)), data[:, 1:].reshape(-1))
        value = float(loss.detach().cpu())
        return {"ok": True, "loss": round(value, 4), "samples": len(texts)}
    except Exception as exc:
        return {"ok": False, "error": f"Tiny LLM 评测失败：{exc}"}


# ---------------------------------------------------------------------------
# 推理
# ---------------------------------------------------------------------------

class TinyLLMInference:
    """Tiny LLM 推理器。"""
    
    def __init__(self, attention_type: str = "dense", model_dir: str | Path | None = None):
        if attention_type not in {"dense", "sparse", "pangu_pi_sparse"}:
            raise ValueError(f"未知注意力类型：{attention_type}")
        self.attention_type = attention_type
        self.model_dir = Path(model_dir) if model_dir else None
        if self.model_dir:
            self.model_file = self.model_dir / "model.pt"
            self.vocab_file = self.model_dir / "vocab.json"
        elif attention_type == "pangu_pi_sparse":
            self.model_file, self.vocab_file = PANGU_PI_MODEL_FILE, PANGU_PI_VOCAB_FILE
        elif attention_type == "sparse":
            self.model_file, self.vocab_file = SPARSE_MODEL_FILE, SPARSE_VOCAB_FILE
        else:
            self.model_file, self.vocab_file = MODEL_FILE, VOCAB_FILE
        self.model = None
        self.tokenizer = None
        self.config = None
        self.device = None
        self.loaded = False
        self.runtime_proxy = False
    
    def load(self) -> dict:
        """加载训练好的模型。"""
        if not self.model_file.exists() or not self.vocab_file.exists():
            label = {"sparse": "稀疏注意力 Tiny LLM", "pangu_pi_sparse": "盘古 pi 稀疏 Tiny LLM"}.get(self.attention_type, "Tiny LLM")
            return {"ok": False, "error": f"{label} 未训练。请先训练。"}
        
        try:
            import torch
        except Exception:
            result = _run_runtime_worker({
                "action": "load", "attention_type": self.attention_type,
                "model_dir": str(self.model_dir) if self.model_dir else None,
            }, timeout=120)
            if result.get("ok"):
                self.runtime_proxy = True
                self.loaded = True
                self.device = "component-runtime"
                return {**result, "device": self.device}
            return result
        
        try:
            # 加载词表
            self.tokenizer = SimpleTokenizer()
            self.tokenizer.load(self.vocab_file)
            
            # 加载配置和模型
            checkpoint = torch.load(self.model_file, map_location="cpu")
            self.config = checkpoint["config"]
            
            self.model, _ = create_tiny_model(self.tokenizer.vocab_size, self.config)
            self.model.load_state_dict(checkpoint["model_state"])
            
            # Sparse checkpoints run on CPU by design; this avoids backend
            # dependent view/unfold support and keeps mode switching portable.
            if self.attention_type in {"sparse", "pangu_pi_sparse"}:
                self.device = torch.device("cpu")
            elif torch.cuda.is_available():
                self.device = torch.device("cuda")
            else:
                try:
                    import torch_directml
                    self.device = torch_directml.device()
                except ImportError:
                    self.device = torch.device("cpu")
            
            self.model = self.model.to(self.device)
            self.model.eval()
            self.loaded = True
            
            return {
                "ok": True,
                "model_path": str(self.model_file),
                "device": str(self.device),
                "vocab_size": self.tokenizer.vocab_size,
            }
        except Exception as e:
            return {"ok": False, "error": f"加载失败: {e}"}
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.8,
        top_k: int = 40,
    ) -> str:
        """生成回复。"""
        if not self.loaded:
            return "[模型未加载]"

        if self.runtime_proxy:
            return "[请使用 chat() 通过组件运行时生成回复]"
        
        import torch
        
        # 编码输入
        input_ids = self.tokenizer.encode(prompt, self.config["max_seq_len"])
        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=self.device)
        
        # 生成
        self.model.eval()
        with torch.no_grad():
            generated = input_ids.copy()
            
            for _ in range(max_new_tokens):
                input_tensor = torch.tensor([generated[-self.config["max_seq_len"]:]], 
                                           dtype=torch.long, device=self.device)
                logits = self.model(input_tensor)
                
                # 取最后一个 token 的 logits
                next_logits = logits[0, -1, :]
                
                # Temperature
                if temperature > 0:
                    next_logits = next_logits / temperature
                
                # Top-K
                if top_k > 0:
                    top_k_vals, _ = torch.topk(next_logits, top_k)
                    threshold = top_k_vals[-1]
                    next_logits[next_logits < threshold] = float("-inf")
                
                # 采样
                probs = torch.softmax(next_logits, dim=-1)
                next_token = torch.multinomial(probs, 1).item()
                
                if next_token == 3:  # <eos>
                    break
                
                generated.append(next_token)
            
            # 解码
            response = self.tokenizer.decode(generated[len(input_ids):])
        
        return response
    
    def chat(
        self,
        message: str,
        history: list[tuple[str, str]] | None = None,
        deep_reply: bool | None = None,
    ) -> str:
        """对话模式。"""
        if self.runtime_proxy:
            result = _run_runtime_worker({
                "action": "chat",
                "attention_type": self.attention_type,
                "message": message,
                "history": history or [],
                "model_dir": str(self.model_dir) if self.model_dir else None,
            }, timeout=120)
            return str(result.get("reply") or "...") if result.get("ok") else "..."

        # 构建 prompt
        parts = []
        if history:
            for user_msg, bot_msg in history[-3:]:
                parts.append(f"用户：{user_msg}")
                parts.append(f"助手：{bot_msg}")
        
        if deep_reply is None:
            deep_reply = load_deep_reply_config()["enabled"]
        if deep_reply:
            # This is a concise, visible prompt instruction—not an attempt to
            # fabricate hidden reasoning.  It keeps the small model focused on
            # a clear conclusion while preserving the user's original question.
            parts.append("回答要求：先抓住问题重点，给出清晰、可执行的结论；不要展示推理过程。")
        parts.append(f"用户：{message}")
        parts.append("助手：")
        
        prompt = "\n".join(parts)
        
        # 生成
        response = self.generate(prompt, max_new_tokens=64)
        
        # 清理
        response = response.split("\n")[0]  # 只取第一行
        response = response.strip()
        
        return response or "..."
    
    def unload(self):
        """卸载模型。"""
        self.model = None
        self.tokenizer = None
        self.config = None
        self.runtime_proxy = False
        self.loaded = False


# 全局实例
_tiny_llm = TinyLLMInference()
_sparse_tiny_llm = TinyLLMInference("sparse")
_pangu_pi_tiny_llm = TinyLLMInference("pangu_pi_sparse")


def get_tiny_llm() -> TinyLLMInference:
    return _tiny_llm


def get_sparse_tiny_llm() -> TinyLLMInference:
    return _sparse_tiny_llm


def get_pangu_pi_tiny_llm() -> TinyLLMInference:
    return _pangu_pi_tiny_llm


def is_tiny_llm_available() -> bool:
    return _tiny_llm.loaded


def tiny_llm_chat(message: str, history: list[tuple[str, str]] | None = None) -> str:
    if not _tiny_llm.loaded:
        result = _tiny_llm.load()
        if not result.get("ok"):
            return ""
    return _tiny_llm.chat(message, history)
