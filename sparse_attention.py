"""Bounded sparse causal attention used by the optional Tiny LLM backend.

Each token attends to a fixed local window and a fixed number of evenly-spaced
past anchors.  The implementation never creates an n by n attention matrix:
its work grows with ``sequence_length * (window + global_tokens)``.
"""

from __future__ import annotations


def create_sparse_causal_attention(embed_dim: int, num_heads: int, dropout: float, window: int, global_tokens: int):
    """Create the PyTorch module lazily so importing this file needs no torch."""
    import math

    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    if embed_dim % num_heads:
        raise ValueError("embed_dim must be divisible by num_heads")
    if window < 1 or global_tokens < 1:
        raise ValueError("window and global_tokens must be positive")

    class SparseCausalAttention(nn.Module):
        def __init__(self):
            super().__init__()
            self.num_heads = num_heads
            self.head_dim = embed_dim // num_heads
            self.window = window
            self.global_tokens = global_tokens
            self.qkv = nn.Linear(embed_dim, 3 * embed_dim)
            self.output = nn.Linear(embed_dim, embed_dim)
            self.dropout = nn.Dropout(dropout)
            self.last_routing: dict[str, object] = {}

        def forward(self, x):
            batch, seq_len, _ = x.shape
            qkv = self.qkv(x).view(batch, seq_len, 3, self.num_heads, self.head_dim)
            q, k, v = qkv.unbind(dim=2)
            q = q.transpose(1, 2)
            k = k.transpose(1, 2)
            v = v.transpose(1, 2)
            scale = 1.0 / math.sqrt(self.head_dim)

            # A padded rolling view yields only window scores per token.
            padded_k = F.pad(k.transpose(2, 3), (self.window - 1, 0)).transpose(2, 3)
            padded_v = F.pad(v.transpose(2, 3), (self.window - 1, 0)).transpose(2, 3)
            local_k = padded_k.unfold(2, self.window, 1).permute(0, 1, 2, 4, 3)
            local_v = padded_v.unfold(2, self.window, 1).permute(0, 1, 2, 4, 3)
            local_scores = (q.unsqueeze(-2) * local_k).sum(dim=-1) * scale

            # Fixed-size anchors carry long-range information without a dense matrix.
            anchor_count = min(self.global_tokens, seq_len)
            anchors = torch.linspace(0, seq_len - 1, anchor_count, device=x.device).round().long()
            anchor_k = k.index_select(2, anchors)
            anchor_v = v.index_select(2, anchors)
            global_scores = torch.matmul(q, anchor_k.transpose(-2, -1)) * scale
            positions = torch.arange(seq_len, device=x.device).view(seq_len, 1)
            valid_anchor = anchors.view(1, anchor_count) <= positions
            global_scores = global_scores.masked_fill(~valid_anchor.view(1, 1, seq_len, anchor_count), float("-inf"))

            scores = torch.cat((local_scores, global_scores), dim=-1)
            weights = self.dropout(torch.softmax(scores, dim=-1))
            local_out = (weights[..., :self.window].unsqueeze(-1) * local_v).sum(dim=-2)
            global_out = torch.matmul(weights[..., self.window:], anchor_v)
            output = (local_out + global_out).transpose(1, 2).contiguous().view(batch, seq_len, embed_dim)

            # This compact trace lets callers inspect the long-range routing policy.
            self.last_routing = {
                "window": self.window,
                "anchors": anchors.detach().cpu().tolist(),
                "global_tokens": anchor_count,
            }
            return self.output(output)

    return SparseCausalAttention()
