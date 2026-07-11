from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


import _paths as path_helpers
from _paths import module_root, data_dir, python_exe
from sensitive_json import read_sensitive_json

runtime_python_exe = getattr(path_helpers, "runtime_python_exe", lambda root=None, create=True: python_exe())


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
TRAINING_FILE = DATA_DIR / "training.json"
NEURAL_DIR = DATA_DIR / "neural"
MODEL_FILE = NEURAL_DIR / "motion_net.pt"
GPU_STATE_FILE = NEURAL_DIR / "gpu_backend_state.json"

LABELS = ["idle", "nod", "happy", "thinking", "encourage", "celebrate", "read", "scan", "spark"]
STOPWORDS = {"的", "了", "和", "是", "我", "你", "在", "有", "就", "也", "都", "很"}

SEED_EXAMPLES = [
    ("你好", "nod"),
    ("谢谢你", "happy"),
    ("成功了", "celebrate"),
    ("训练完成", "celebrate"),
    ("我今天很累", "encourage"),
    ("我有点难过", "encourage"),
    ("压力好大", "encourage"),
    ("帮我做计划", "thinking"),
    ("这个怎么做", "thinking"),
    ("总结这个文件", "read"),
    ("读取文件", "read"),
    ("识别图片文字", "scan"),
    ("OCR 图片", "scan"),
    ("现在几点", "nod"),
    ("天气怎么样", "nod"),
    ("这个回答很好", "spark"),
]


def torch_info() -> dict:
    try:
        import torch
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "install": "当前 Python 未安装 PyTorch。建议新建 Python 3.12 环境后安装 CUDA 版 PyTorch。",
        }
    directml_available = False
    directml_error = ""
    try:
        import torch_directml

        _dml = torch_directml.device()
        directml_available = True
    except Exception as exc:
        directml_error = str(exc)

    gpu_available = bool(torch.cuda.is_available())
    hip_runtime = bool(getattr(torch.version, "hip", None))
    requested_gpu = _gpu_training_enabled()
    if requested_gpu and gpu_available:
        device = "cuda"
    elif requested_gpu and directml_available:
        device = "directml"
    else:
        device = "cpu"
    return {
        "available": True,
        "torch_version": torch.__version__,
        "cuda_available": gpu_available,
        "hip_runtime": hip_runtime,
        "directml_available": directml_available,
        "directml_error": directml_error,
        "device": device,
        "gpu_training_enabled": requested_gpu,
        "cuda_device": torch.cuda.get_device_name(0) if gpu_available else "",
    }


def _gpu_training_enabled() -> bool:
    return os.environ.get("COMPANION_ENABLE_GPU_TRAINING", "").strip().lower() in {"1", "true", "yes", "on"}


def best_torch_device():
    import torch

    if not _gpu_training_enabled():
        return torch.device("cpu"), "cpu"
    if torch.cuda.is_available():
        return torch.device("cuda"), "cuda"
    try:
        import torch_directml

        return torch_directml.device(), "directml"
    except Exception:
        return torch.device("cpu"), "cpu"


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", text.lower())
    return [word for word in words if word not in STOPWORDS]


def infer_label(text: str) -> str:
    if any(key in text for key in ["已学到", "训练", "生成", "完成", "成功"]):
        return "celebrate"
    if any(key in text for key in ["累", "难过", "压力", "撑着", "焦虑"]):
        return "encourage"
    if any(key in text for key in ["文件", "读", "总结", "csv", "json"]):
        return "read"
    if any(key in text for key in ["ocr", "图片", "识别", "文字"]):
        return "scan"
    if any(key in text for key in ["计划", "怎么做", "思考", "为什么"]):
        return "thinking"
    if any(key in text for key in ["谢谢", "很好", "有帮助", "喜欢"]):
        return "spark"
    if any(key in text for key in ["天气", "时间", "几点"]):
        return "nod"
    return "happy" if len(text) > 18 else "idle"


def load_training_examples() -> list[tuple[str, str]]:
    examples = list(SEED_EXAMPLES)
    if TRAINING_FILE.exists():
        data = read_sensitive_json(TRAINING_FILE, {"examples": [], "feedback": []})
        for item in data.get("examples", []):
            if item.get("rating", 1) <= 0:
                continue
            prompt = item.get("prompt", "")
            response = item.get("response", "")
            text = f"{prompt}\n{response}".strip()
            if text:
                examples.append((text, infer_label(text)))
        for item in data.get("feedback", []):
            if item.get("rating", 0) > 0:
                text = f"{item.get('prompt', '')}\n{item.get('response', '')}".strip()
                if text:
                    examples.append((text, "spark"))
    return examples


def build_vocab(examples: list[tuple[str, str]]) -> dict[str, int]:
    vocab = {"<pad>": 0, "<unk>": 1}
    for text, _label in examples:
        for token in tokenize(text):
            if token not in vocab:
                vocab[token] = len(vocab)
    return vocab


def encode(text: str, vocab: dict[str, int], max_len: int = 48) -> list[int]:
    ids = [vocab.get(token, 1) for token in tokenize(text)[:max_len]]
    return ids + [0] * (max_len - len(ids))


def train_motion_net(epochs: int = 120) -> dict:
    info = torch_info()
    if not info["available"]:
        return {"ok": False, **info}

    import torch
    import torch.nn as nn

    examples = load_training_examples()
    labels = sorted(set(label for _, label in examples))
    return _train_model(examples, labels, epochs=epochs, model_tag="motion_net")


def _worker_python() -> str:
    try:
        return runtime_python_exe(create=False)
    except Exception:
        pass
    try:
        return python_exe()
    except Exception:
        return sys.executable


def _read_gpu_state() -> dict:
    try:
        if GPU_STATE_FILE.exists():
            return json.loads(GPU_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_gpu_state(state: dict) -> None:
    try:
        NEURAL_DIR.mkdir(parents=True, exist_ok=True)
        GPU_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _runtime_torch_fingerprint(worker: str) -> dict:
    code = """
import json
import sys
from importlib import metadata

try:
    torch_version = metadata.version("torch")
except Exception:
    torch_version = "not-installed"

print(json.dumps({
    "python": sys.executable,
    "version": sys.version.split()[0],
    "torch": torch_version,
}))
"""
    try:
        proc = subprocess.run(
            [worker, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.splitlines()[-1])
    except Exception:
        pass
    return {"python": worker, "version": "", "torch": "unknown"}


def _gpu_state_blocks(action: str, fingerprint: dict) -> dict | None:
    if os.environ.get("COMPANION_GPU_RETRY", "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    state = _read_gpu_state()
    blocked = state.get("blocked_native_crash")
    if not isinstance(blocked, dict):
        return None
    if blocked.get("action") != action:
        return None
    blocked_fingerprint = blocked.get("fingerprint")
    if not isinstance(blocked_fingerprint, dict):
        return None
    blocked_key = (blocked_fingerprint.get("version"), blocked_fingerprint.get("torch"))
    current_key = (fingerprint.get("version"), fingerprint.get("torch"))
    if blocked_key != current_key:
        return None
    return blocked


def _run_gpu_worker(action: str, timeout: int = 180) -> dict:
    worker = _worker_python()
    fingerprint = _runtime_torch_fingerprint(worker)
    blocked = _gpu_state_blocks(action, fingerprint)
    if blocked:
        return {
            "ok": False,
            "error": (
                "同一 PyTorch/GPU 运行时上次发生原生崩溃，已暂停本次 GPU 子进程自检，"
                "避免重复触发 0xC0000005。请在设置里重装 PyTorch 后再试；"
                "如需强制重试，可设置环境变量 COMPANION_GPU_RETRY=1。"
            ),
            "returncode": blocked.get("returncode", ""),
            "stdout": "",
            "stderr": blocked.get("stderr", ""),
            "worker_python": worker,
            "torch_runtime": fingerprint,
        }
    env = os.environ.copy()
    env["COMPANION_ENABLE_GPU_TRAINING"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [worker, str(Path(__file__).resolve()), action]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"GPU 子进程超时（{timeout}s）"}
    except Exception as exc:
        return {"ok": False, "error": f"GPU 子进程启动失败：{exc}"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        native_crash = proc.returncode in {3221225477, -1073741819}
        if native_crash:
            _write_gpu_state(
                {
                    "blocked_native_crash": {
                        "action": action,
                        "returncode": proc.returncode,
                        "fingerprint": fingerprint,
                        "stderr": stderr[-1200:],
                    }
                }
            )
        return {
            "ok": False,
            "error": "GPU 子进程发生原生崩溃（0xC0000005），主服务已隔离保护" if native_crash else "GPU 子进程异常退出",
            "returncode": proc.returncode,
            "stdout": stdout[-800:],
            "stderr": stderr[-1200:],
            "worker_python": worker,
            "torch_runtime": fingerprint,
        }
    try:
        data = json.loads(stdout.splitlines()[-1] if stdout else "{}")
    except Exception:
        return {"ok": False, "error": "GPU 子进程没有返回有效 JSON", "stdout": stdout[-2000:], "stderr": stderr[-4000:]}
    if stderr:
        data.setdefault("stderr", stderr[-2000:])
    data.setdefault("worker_python", worker)
    data.setdefault("torch_runtime", fingerprint)
    return data


def gpu_self_check_isolated() -> dict:
    return _run_gpu_worker("--gpu-check", timeout=90)


def train_motion_net_gpu_isolated() -> dict:
    return _run_gpu_worker("--train-motion-gpu", timeout=240)


def train_from_dataset(
    dataset_examples: list[dict],
    labels: list[str] | None = None,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 0.005,
    val_split: float = 0.15,
    early_stop_patience: int = 5,
    model_tag: str = "dataset_model",
    merge_seed: bool = True,
) -> dict:
    """
    使用外部数据集训练模型。

    参数:
        dataset_examples: [{"text": str, "label": str}, ...]
        labels: 标签列表，None 则从数据中自动提取
        epochs: 最大训练轮数
        batch_size: 批大小
        lr: 学习率
        val_split: 验证集比例
        early_stop_patience: 早停耐心值（val loss 连续不降则停止）
        model_tag: 模型文件标签（区分不同模型）
        merge_seed: 是否合并内置种子样本
    """
    info = torch_info()
    if not info["available"]:
        return {"ok": False, **info}

    examples = [(item["text"], item["label"]) for item in dataset_examples if item.get("text") and item.get("label")]

    if merge_seed:
        examples = list(SEED_EXAMPLES) + examples

    if labels is None:
        labels = sorted(set(label for _, label in examples))

    return _train_model(
        examples, labels,
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        val_split=val_split,
        early_stop_patience=early_stop_patience,
        model_tag=model_tag,
    )


def _train_model(
    examples: list[tuple[str, str]],
    labels: list[str],
    epochs: int = 120,
    batch_size: int = 0,
    lr: float = 0.01,
    val_split: float = 0.0,
    early_stop_patience: int = 0,
    model_tag: str = "motion_net",
) -> dict:
    """
    通用训练函数。

    参数:
        examples: [(text, label), ...]
        labels: 标签列表
        epochs: 训练轮数
        batch_size: 批大小，0 表示全批
        lr: 学习率
        val_split: 验证集比例 (0.0-1.0)
        early_stop_patience: 早停耐心值，0 表示不早停
        model_tag: 模型文件名标签
    """
    import torch
    import torch.nn as nn

    class MotionNet(nn.Module):
        def __init__(self, vocab_size: int, label_count: int) -> None:
            super().__init__()
            self.embedding = nn.Embedding(vocab_size, 64, padding_idx=0)
            self.net = nn.Sequential(
                nn.Linear(64, 128),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(128, label_count),
            )

        def forward(self, token_ids):
            mask = (token_ids != 0).float().unsqueeze(-1)
            emb = self.embedding(token_ids) * mask
            pooled = emb.sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
            return self.net(pooled)

    label_to_idx = {label: i for i, label in enumerate(labels)}
    valid_examples = [(text, label) for text, label in examples if label in label_to_idx]

    if not valid_examples:
        return {"ok": False, "error": "没有有效的训练样本"}

    vocab = build_vocab(valid_examples)
    device, device_name = best_torch_device()

    all_x = torch.tensor([encode(text, vocab) for text, _ in valid_examples], dtype=torch.long, device=device)
    all_y = torch.tensor([label_to_idx[label] for _, label in valid_examples], dtype=torch.long, device=device)

    n = len(valid_examples)
    val_n = int(n * val_split) if val_split > 0 else 0
    if val_n > 0:
        indices = torch.randperm(n, device=device)
        val_idx = indices[:val_n]
        train_idx = indices[val_n:]
        train_x, train_y = all_x[train_idx], all_y[train_idx]
        val_x, val_y = all_x[val_idx], all_y[val_idx]
    else:
        train_x, train_y = all_x, all_y
        val_x, val_y = None, None

    model = MotionNet(len(vocab), len(labels)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.001)
    loss_fn = nn.CrossEntropyLoss()

    actual_batch = batch_size if batch_size > 0 else len(train_x)
    best_val_loss = float("inf")
    patience_counter = 0
    final_loss = 0.0
    best_state = None

    model.train()
    epochs_trained = 0
    for epoch in range(epochs):
        epochs_trained = epoch + 1
        perm = torch.randperm(len(train_x), device=device)
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, len(train_x), actual_batch):
            end = min(start + actual_batch, len(train_x))
            batch_idx = perm[start:end]
            logits = model(train_x[batch_idx])
            loss = loss_fn(logits, train_y[batch_idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach().cpu())
            n_batches += 1

        final_loss = epoch_loss / max(n_batches, 1)

        if val_x is not None and early_stop_patience > 0:
            model.eval()
            with torch.no_grad():
                val_logits = model(val_x)
                val_loss = float(loss_fn(val_logits, val_y).detach().cpu())
            model.train()
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
            else:
                patience_counter += 1
                if patience_counter >= early_stop_patience:
                    break

    if best_state is not None:
        model.load_state_dict(best_state)

    NEURAL_DIR.mkdir(parents=True, exist_ok=True)
    out_file = NEURAL_DIR / f"{model_tag}.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "vocab": vocab,
            "labels": labels,
            "examples": len(valid_examples),
            "device": device_name,
            "loss": round(final_loss, 4),
            "val_loss": round(best_val_loss, 4) if val_x is not None else None,
            "epochs_trained": epochs_trained,
            "model_class": "MotionNet",
        },
        out_file,
    )
    return {
        "ok": True,
        "model": str(out_file),
        "device": device_name,
        "cuda": bool(torch.cuda.is_available()),
        "directml": device_name == "directml",
        "examples": len(valid_examples),
        "vocab_size": len(vocab),
        "labels": labels,
        "label_count": len(labels),
        "loss": round(final_loss, 4),
        "val_loss": round(best_val_loss, 4) if val_x is not None else None,
        "epochs_trained": epochs_trained,
    }


def predict_motion(text: str) -> dict:
    """预测动作标签。优先使用 dataset_model.pt，回退到 motion_net.pt。"""
    dataset_model = NEURAL_DIR / "dataset_model.pt"
    model_file = dataset_model if dataset_model.exists() else MODEL_FILE
    return predict_with_model(text, model_file)


def predict_with_model(text: str, model_file: Path) -> dict:
    """用指定的模型文件预测。"""
    info = torch_info()
    if not info["available"] or not model_file.exists():
        return {"ok": False, "motion": "", "reason": "neural model unavailable"}

    import torch
    import torch.nn as nn

    class MotionNet(nn.Module):
        def __init__(self, vocab_size: int, label_count: int) -> None:
            super().__init__()
            self.embedding = nn.Embedding(vocab_size, 64, padding_idx=0)
            self.net = nn.Sequential(
                nn.Linear(64, 128),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(128, label_count),
            )

        def forward(self, token_ids):
            mask = (token_ids != 0).float().unsqueeze(-1)
            emb = self.embedding(token_ids) * mask
            pooled = emb.sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
            return self.net(pooled)

    device, device_name = best_torch_device()
    checkpoint = torch.load(model_file, map_location="cpu")
    vocab = checkpoint["vocab"]
    labels = checkpoint["labels"]
    model = MotionNet(len(vocab), len(labels)).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    x = torch.tensor([encode(text, vocab)], dtype=torch.long, device=device)
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=-1)[0]
    score, index = torch.max(probs, dim=0)
    return {
        "ok": True,
        "motion": labels[int(index)],
        "confidence": round(float(score.detach().cpu()), 4),
        "device": device_name,
        "model": str(model_file.name),
    }


def neural_status() -> dict:
    info = torch_info()
    status = {"torch": info, "model_exists": MODEL_FILE.exists(), "model": str(MODEL_FILE)}
    if MODEL_FILE.exists() and info["available"]:
        try:
            import torch

            checkpoint = torch.load(MODEL_FILE, map_location="cpu")
            status["model_meta"] = {
                "examples": checkpoint.get("examples", 0),
                "vocab_size": len(checkpoint.get("vocab", {})),
                "labels": checkpoint.get("labels", LABELS),
                "trained_device": checkpoint.get("device", ""),
                "loss": checkpoint.get("loss", None),
            }
        except Exception as exc:
            status["model_error"] = str(exc)
    return status


def neural_status_text() -> str:
    status = neural_status()
    torch_data = status["torch"]
    lines = ["神经网络状态："]
    if torch_data.get("available"):
        lines.append(f"- PyTorch：{torch_data.get('torch_version')}")
        lines.append(f"- 设备：{torch_data.get('device')}")
        if torch_data.get("hip_runtime"):
            lines.append("- ROCm/HIP：已检测到，GPU 训练需通过 /gpu_check 或 /train_neural_gpu 子进程隔离运行")
        if not torch_data.get("gpu_training_enabled"):
            lines.append("- GPU 训练：默认关闭（保护主服务稳定）")
        if torch_data.get("cuda_device"):
            lines.append(f"- GPU：{torch_data.get('cuda_device')}")
        if torch_data.get("directml_available"):
            lines.append("- DirectML：可用（适合 AMD/Intel/NVIDIA Windows GPU）")
    else:
        lines.append("- PyTorch：未安装")
        lines.append("- GPU：等待安装 CUDA 版 PyTorch 或 torch-directml 后启用")
    lines.append(f"- 模型文件：{'已生成' if status['model_exists'] else '未生成'}")
    if "model_meta" in status:
        meta = status["model_meta"]
        lines.append(f"- 训练样本：{meta['examples']} 条")
        lines.append(f"- 词表：{meta['vocab_size']} 个词")
        lines.append(f"- loss：{meta['loss']}")
    return "\n".join(lines)


def _gpu_check_worker() -> dict:
    import torch

    info = torch_info()
    device, device_name = best_torch_device()
    x = torch.arange(16, dtype=torch.float32, device=device).reshape(4, 4)
    y = (x @ x).sum()
    value = float(y.detach().cpu())
    return {"ok": True, "device": device_name, "value": round(value, 4), "torch": info}


def _main() -> int:
    if len(sys.argv) < 2:
        return 0
    action = sys.argv[1]
    try:
        if action == "--gpu-check":
            result = _gpu_check_worker()
        elif action == "--train-motion-gpu":
            result = train_motion_net()
        else:
            result = {"ok": False, "error": f"unknown action: {action}"}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(_main())
