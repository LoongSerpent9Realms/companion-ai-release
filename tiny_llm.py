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
import re
from pathlib import Path
from typing import Generator

from _paths import module_root, data_dir

ROOT = module_root(__file__)
MODEL_DIR = data_dir(ROOT) / "tiny_llm"
MODEL_FILE = MODEL_DIR / "model.pt"
VOCAB_FILE = MODEL_DIR / "vocab.json"
CONFIG_FILE = MODEL_DIR / "config.json"


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
    except ImportError:
        raise ImportError("需要安装 PyTorch")
    
    if config is None:
        config = {
            "embed_dim": 256,
            "num_heads": 4,
            "num_layers": 4,
            "ffn_dim": 512,
            "max_seq_len": 128,
            "dropout": 0.1,
        }
    
    class TinyAttention(nn.Module):
        def __init__(self, embed_dim, num_heads, dropout):
            super().__init__()
            self.attention = nn.MultiheadAttention(embed_dim, num_heads, dropout=dropout, batch_first=True)
            self.norm = nn.LayerNorm(embed_dim)
            self.dropout = nn.Dropout(dropout)
        
        def forward(self, x, mask=None):
            attn_out, _ = self.attention(x, x, x, attn_mask=mask, need_weights=False)
            return self.norm(x + self.dropout(attn_out))
    
    class TinyFFN(nn.Module):
        def __init__(self, embed_dim, ffn_dim, dropout):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(embed_dim, ffn_dim),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(ffn_dim, embed_dim),
                nn.Dropout(dropout),
            )
            self.norm = nn.LayerNorm(embed_dim)
        
        def forward(self, x):
            return self.norm(x + self.net(x))
    
    class TinyTransformerBlock(nn.Module):
        def __init__(self, embed_dim, num_heads, ffn_dim, dropout):
            super().__init__()
            self.attn = TinyAttention(embed_dim, num_heads, dropout)
            self.ffn = TinyFFN(embed_dim, ffn_dim, dropout)
        
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
            
            # 因果掩码
            mask = self.causal_mask[:seq_len, :seq_len]
            mask = mask.float() * -1e9
            
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
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        return {"ok": False, "error": "需要安装 PyTorch"}
    
    if not texts:
        return {"ok": False, "error": "没有训练数据"}
    
    print(f"\n{'='*50}")
    print(f"  从零训练 Tiny LLM")
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
        }
    
    model, config = create_tiny_model(tokenizer.vocab_size, config)
    
    # 设备
    if torch.cuda.is_available():
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
    all_ids = [tokenizer.encode(text, max_seq_len) for text in texts]
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
    
    # 保存
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    torch.save({
        "model_state": model.state_dict(),
        "config": config,
        "vocab_size": tokenizer.vocab_size,
        "epochs": epochs,
        "samples": len(texts),
        "final_loss": final_loss,
    }, MODEL_FILE)
    
    tokenizer.save(VOCAB_FILE)
    
    train_config = {
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "samples": len(texts),
        "final_loss": round(final_loss, 4),
        "model_type": "tiny_llm",
    }
    CONFIG_FILE.write_text(json.dumps(train_config, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n{'='*50}")
    print(f"  训练完成!")
    print(f"  最终 Loss: {final_loss:.4f}")
    print(f"  模型: {MODEL_FILE}")
    print(f"{'='*50}\n")
    
    return {
        "ok": True,
        "model_path": str(MODEL_FILE),
        "samples": len(texts),
        "epochs": epochs,
        "final_loss": round(final_loss, 4),
        "vocab_size": tokenizer.vocab_size,
    }


# ---------------------------------------------------------------------------
# 推理
# ---------------------------------------------------------------------------

class TinyLLMInference:
    """Tiny LLM 推理器。"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.config = None
        self.device = None
        self.loaded = False
    
    def load(self) -> dict:
        """加载训练好的模型。"""
        if not MODEL_FILE.exists() or not VOCAB_FILE.exists():
            return {"ok": False, "error": "模型未训练。请先训练 Tiny LLM。"}
        
        try:
            import torch
        except ImportError:
            return {"ok": False, "error": "需要安装 PyTorch"}
        
        try:
            # 加载词表
            self.tokenizer = SimpleTokenizer()
            self.tokenizer.load(VOCAB_FILE)
            
            # 加载配置和模型
            checkpoint = torch.load(MODEL_FILE, map_location="cpu")
            self.config = checkpoint["config"]
            
            self.model, _ = create_tiny_model(self.tokenizer.vocab_size, self.config)
            self.model.load_state_dict(checkpoint["model_state"])
            
            # 设备
            if torch.cuda.is_available():
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
                "model_path": str(MODEL_FILE),
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
    
    def chat(self, message: str, history: list[tuple[str, str]] | None = None) -> str:
        """对话模式。"""
        # 构建 prompt
        parts = []
        if history:
            for user_msg, bot_msg in history[-3:]:
                parts.append(f"用户：{user_msg}")
                parts.append(f"助手：{bot_msg}")
        
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
        self.loaded = False


# 全局实例
_tiny_llm = TinyLLMInference()


def get_tiny_llm() -> TinyLLMInference:
    return _tiny_llm


def is_tiny_llm_available() -> bool:
    return _tiny_llm.loaded


def tiny_llm_chat(message: str, history: list[tuple[str, str]] | None = None) -> str:
    if not _tiny_llm.loaded:
        result = _tiny_llm.load()
        if not result.get("ok"):
            return ""
    return _tiny_llm.chat(message, history)
