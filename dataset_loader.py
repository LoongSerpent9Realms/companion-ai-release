"""
dataset_loader.py - 从 ModelScope / HuggingFace 加载数据集
统一输出格式: list[dict] 每条 {"text": str, "label": str}
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from _paths import module_root, data_dir, resource_dir, runtime_python_exe
from dependency_utils import ensure_dataset_dependencies

ROOT = module_root(__file__)
CACHE_DIR = data_dir(ROOT) / "datasets"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NATIVE_IMPORT_CONFLICT_MARKERS = (
    "python314.dll conflicts",
    "python313.dll conflicts",
    "python312.dll conflicts",
    "python311.dll conflicts",
    "conflicts with this version of Python",
)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _dataset_config(
    source: str,
    dataset_id: str,
    split: str = "train",
    text_keys: list[str] | None = None,
    label_keys: list[str] | None = None,
    label_map: dict[str, str] | dict[int, str] | None = None,
    max_samples: int | None = None,
    subset: str | None = None,
) -> dict:
    return {
        "source": source,
        "dataset_id": dataset_id,
        "split": split,
        "subset": subset,
        "text_keys": text_keys,
        "label_keys": label_keys,
        "label_map": label_map,
        "max_samples": max_samples,
    }


def _worker_path() -> Path:
    candidates = [
        resource_dir(__file__) / "dataset_runtime_worker.py",
        ROOT / "dataset_runtime_worker.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("找不到 dataset_runtime_worker.py")


def _load_with_runtime_worker(config: dict, reason: BaseException | None = None) -> list[dict]:
    status = ensure_dataset_dependencies(auto_install=True)
    if not status.ok:
        from dependency_utils import DATASET_INSTALL_CMD

        detail = f"{status.detail}\n运行时 Python: {status.python}\n请安装: {DATASET_INSTALL_CMD}"
        if reason:
            detail = f"{reason}\n{detail}"
        raise ImportError(detail)

    worker = _worker_path()
    py = status.python or runtime_python_exe(create=True)
    proc = subprocess.run(
        [py, str(worker)],
        input=json.dumps(config, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=1800,
        creationflags=CREATE_NO_WINDOW,
    )
    output = (proc.stdout or "").strip()
    try:
        payload = json.loads(output or "{}")
    except Exception as exc:
        detail = (proc.stderr or proc.stdout or "").strip()[-1000:]
        raise RuntimeError(f"runtime 数据集加载结果无法解析: {detail}") from exc
    if proc.returncode != 0 or not payload.get("ok"):
        detail = payload.get("error") or (proc.stderr or "runtime 数据集加载失败").strip()
        raise RuntimeError(detail)
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("runtime 数据集加载结果格式无效")
    return items


def _should_use_runtime_worker_for_external_datasets() -> bool:
    """Keep native dataset dependencies out of the main app process.

    pandas/pyarrow/modelscope can load CPython-version-specific DLLs.  Loading
    them inside the UI/server process is fragile when the component runtime was
    created by a different Python than the app.  The worker returns plain JSON,
    which avoids python3xx.dll conflicts in the main process.
    """
    return os.environ.get("COMPANION_DATASET_IN_PROCESS", "").strip() not in {"1", "true", "yes"}


def _is_native_import_conflict(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(marker.lower() in text.lower() for marker in NATIVE_IMPORT_CONFLICT_MARKERS)


def _pick_text(row: dict, text_keys: list[str]) -> str:
    """从数据行中提取文本，按 text_keys 优先级尝试。"""
    for key in text_keys:
        val = row.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return ""


def _pick_label(row: dict, label_keys: list[str]) -> Any:
    """从数据行中提取标签（原始值，可能是 int 或 str）。"""
    for key in label_keys:
        val = row.get(key)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# HuggingFace 加载
# ---------------------------------------------------------------------------

def load_from_huggingface(
    dataset_id: str,
    split: str = "train",
    text_keys: list[str] | None = None,
    label_keys: list[str] | None = None,
    label_map: dict[str, str] | dict[int, str] | None = None,
    max_samples: int | None = None,
    subset: str | None = None,
) -> list[dict]:
    """
    从 HuggingFace datasets 加载数据。

    参数:
        dataset_id: 数据集 ID，如 "emotion" 或 "DAMO-NLP-MT/multi-m3e"
        split: 数据划分，默认 "train"
        text_keys: 文本字段名列表（按优先级），默认自动检测
        label_keys: 标签字段名列表（按优先级），默认自动检测
        label_map: 标签映射 {原始标签: 统一标签}，None 则用原始标签
        max_samples: 最大样本数，None 则全部加载
        subset: 数据集子集名称
    """
    config = _dataset_config(
        "huggingface",
        dataset_id,
        split=split,
        text_keys=text_keys,
        label_keys=label_keys,
        label_map=label_map,
        max_samples=max_samples,
        subset=subset,
    )
    if _should_use_runtime_worker_for_external_datasets():
        return _load_with_runtime_worker(config)
    try:
        from datasets import load_dataset
    except ImportError as exc:
        status = ensure_dataset_dependencies(auto_install=True)
        if status.ok:
            try:
                from datasets import load_dataset
            except ImportError:
                return _load_with_runtime_worker(config, exc)
        else:
            from dependency_utils import DATASET_INSTALL_CMD
            raise ImportError(
                "需要安装 datasets 库和 ModelScope 数据集工具。\n"
                f"自动安装失败: {status.detail}\n"
                f"运行时 Python: {status.python}\n"
                f"请安装: {DATASET_INSTALL_CMD}"
            )

    print(f"[dataset_loader] 从 HuggingFace 加载: {dataset_id} (split={split})")
    try:
        ds = load_dataset(dataset_id, subset, split=split, trust_remote_code=True)
    except ImportError as exc:
        return _load_with_runtime_worker(config, exc)
    except Exception as exc:
        if _is_native_import_conflict(exc):
            return _load_with_runtime_worker(config, exc)
        raise

    if isinstance(ds, dict):
        ds = ds.get(split, list(ds.values())[0] if ds else [])

    if text_keys is None:
        text_keys = _auto_detect_text_keys(ds)
    if label_keys is None:
        label_keys = _auto_detect_label_keys(ds)

    return _convert_rows(ds, text_keys, label_keys, label_map, max_samples)


# ---------------------------------------------------------------------------
# ModelScope 加载
# ---------------------------------------------------------------------------

def load_from_modelscope(
    dataset_id: str,
    split: str = "train",
    text_keys: list[str] | None = None,
    label_keys: list[str] | None = None,
    label_map: dict[str, str] | dict[int, str] | None = None,
    max_samples: int | None = None,
    subset: str | None = None,
) -> list[dict]:
    """
    从 ModelScope 加载数据（国内镜像，速度更快）。

    参数同 load_from_huggingface。
    """
    config = _dataset_config(
        "modelscope",
        dataset_id,
        split=split,
        text_keys=text_keys,
        label_keys=label_keys,
        label_map=label_map,
        max_samples=max_samples,
        subset=subset,
    )
    if _should_use_runtime_worker_for_external_datasets():
        return _load_with_runtime_worker(config)
    try:
        from modelscope.msdatasets import MsDataset
    except ImportError as exc:
        status = ensure_dataset_dependencies(auto_install=True)
        if status.ok:
            try:
                from modelscope.msdatasets import MsDataset
            except ImportError:
                return _load_with_runtime_worker(config, exc)
        else:
            from dependency_utils import DATASET_INSTALL_CMD
            raise ImportError(
                "需要安装 modelscope 数据集工具。\n"
                f"自动安装失败: {status.detail}\n"
                f"运行时 Python: {status.python}\n"
                "文档: https://modelscope.cn/docs\n"
                f"请安装: {DATASET_INSTALL_CMD}"
            )

    print(f"[dataset_loader] 从 ModelScope 加载: {dataset_id} (split={split})")
    try:
        ds = MsDataset.load(dataset_id, subset_name=subset, split=split)
    except ImportError as exc:
        return _load_with_runtime_worker(config, exc)
    except Exception as exc:
        if _is_native_import_conflict(exc):
            return _load_with_runtime_worker(config, exc)
        raise

    if text_keys is None:
        text_keys = _auto_detect_text_keys(ds)
    if label_keys is None:
        label_keys = _auto_detect_label_keys(ds)

    return _convert_rows(ds, text_keys, label_keys, label_map, max_samples)


# ---------------------------------------------------------------------------
# 本地 JSON / JSONL 加载
# ---------------------------------------------------------------------------

def load_from_file(file_path: str | Path) -> list[dict]:
    """
    从本地 JSON/JSONL 文件加载。

    JSON 格式:
      - [{"text": "...", "label": "..."}, ...]
      - {"data": [...], "text_key": "xxx", "label_key": "xxx"}

    JSONL 格式: 每行一个 JSON 对象，含 text 和 label 字段。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"数据集文件不存在: {path}")

    items = []
    if path.suffix == ".jsonl":
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("data", data.get("examples", []))
        else:
            items = data

    result = []
    for item in items:
        text = item.get("text", item.get("content", item.get("prompt", "")))
        label = item.get("label", item.get("tag", item.get("category", "")))
        if text and label is not None:
            result.append({"text": str(text).strip(), "label": str(label).strip()})
    return result


# ---------------------------------------------------------------------------
# 自动检测字段
# ---------------------------------------------------------------------------

_COMMON_TEXT_KEYS = [
    "text", "content", "sentence", "input", "prompt",
    "question", "dialogue", "utterance", "message",
    "review", "body", "title", "description",
]
_COMMON_LABEL_KEYS = [
    "label", "label_text", "tag", "category", "class",
    "sentiment", "emotion", "intent", "topic",
    "output", "response", "answer",
]


def _auto_detect_text_keys(ds) -> list[str]:
    try:
        cols = ds.column_names if hasattr(ds, "column_names") else []
        if isinstance(cols, dict):
            cols = list(cols.values())[0] if cols else []
        found = [c for c in _COMMON_TEXT_KEYS if c in cols]
        return found if found else cols[:2]
    except Exception:
        return _COMMON_TEXT_KEYS[:3]


def _auto_detect_label_keys(ds) -> list[str]:
    try:
        cols = ds.column_names if hasattr(ds, "column_names") else []
        if isinstance(cols, dict):
            cols = list(cols.values())[0] if cols else []
        found = [c for c in _COMMON_LABEL_KEYS if c in cols]
        return found if found else [c for c in cols if c not in _COMMON_TEXT_KEYS][:1]
    except Exception:
        return _COMMON_LABEL_KEYS[:2]


# ---------------------------------------------------------------------------
# 行转换
# ---------------------------------------------------------------------------

def _convert_rows(
    ds,
    text_keys: list[str],
    label_keys: list[str],
    label_map: dict | None,
    max_samples: int | None,
) -> list[dict]:
    result = []
    count = 0
    for row in ds:
        if max_samples and count >= max_samples:
            break
        text = _pick_text(row, text_keys)
        if not text:
            continue
        raw_label = _pick_label(row, label_keys)
        if raw_label is None:
            continue

        if label_map:
            label = label_map.get(raw_label, label_map.get(str(raw_label), str(raw_label)))
        else:
            label = str(raw_label)

        result.append({"text": text, "label": label})
        count += 1

    print(f"[dataset_loader] 加载完成: {len(result)} 条样本")
    return result


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def load_dataset_from_config(config: dict) -> list[dict]:
    """
    根据配置字典加载数据集。

    config 格式:
    {
        "source": "huggingface" | "modelscope" | "file",
        "dataset_id": "数据集ID或文件路径",
        "split": "train",            # 可选
        "subset": null,              # 可选
        "text_keys": ["text"],       # 可选，自动检测
        "label_keys": ["label"],     # 可选，自动检测
        "label_map": {},             # 可选，标签映射
        "max_samples": 5000          # 可选，限制样本数
    }
    """
    source = config.get("source", "huggingface").lower()
    dataset_id = config.get("dataset_id", "")
    split = config.get("split", "train")
    subset = config.get("subset")
    text_keys = config.get("text_keys")
    label_keys = config.get("label_keys")
    label_map = config.get("label_map")
    max_samples = config.get("max_samples")

    if source == "huggingface" or source == "hf":
        return load_from_huggingface(
            dataset_id, split=split, text_keys=text_keys,
            label_keys=label_keys, label_map=label_map,
            max_samples=max_samples, subset=subset,
        )
    elif source == "modelscope" or source == "ms":
        return load_from_modelscope(
            dataset_id, split=split, text_keys=text_keys,
            label_keys=label_keys, label_map=label_map,
            max_samples=max_samples, subset=subset,
        )
    elif source == "file" or source == "local":
        return load_from_file(dataset_id)
    else:
        raise ValueError(f"不支持的数据源: {source}，可选: huggingface, modelscope, file")


def list_available_datasets() -> list[dict]:
    """返回预置的推荐数据集列表。"""
    return [
        {
            "id": "emotion",
            "source": "huggingface",
            "description": "英文情感分类 (sadness, joy, love, anger, fear, surprise)",
            "labels": ["sadness", "joy", "love", "anger", "fear", "surprise"],
            "size": "~16000",
            "text_keys": ["text"],
            "label_keys": ["label"],
        },
        {
            "id": "DAMO-NLP-MT/multi-m3e",
            "source": "modelscope",
            "description": "中文多任务理解 (含情感、意图等)",
            "labels": "多任务",
            "size": "~50000",
        },
        {
            "id": "tyqiangz/multilingual-sentiments",
            "source": "huggingface",
            "description": "多语言情感分析 (positive, neutral, negative)",
            "labels": ["positive", "neutral", "negative"],
            "size": "~76000",
            "text_keys": ["text"],
            "label_keys": ["label"],
        },
        {
            "id": "belle-clean",
            "source": "modelscope",
            "description": "中文对话数据集 (BELLE)",
            "labels": "对话",
            "size": "~100000",
            "text_keys": ["instruction", "input"],
            "label_keys": ["output"],
        },
        {
            "id": "MInstruct",
            "source": "modelscope",
            "description": "中文多轮指令数据集",
            "labels": "指令",
            "size": "~20000",
        },
        {
            "id": "local_file",
            "source": "file",
            "description": "本地 JSON/JSONL 文件 (data/datasets/ 目录下)",
            "labels": "自定义",
            "size": "不限",
        },
    ]
