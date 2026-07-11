from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any


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


def _pick_text(row: dict, text_keys: list[str]) -> str:
    for key in text_keys:
        val = row.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return ""


def _pick_label(row: dict, label_keys: list[str]) -> Any:
    for key in label_keys:
        val = row.get(key)
        if val is not None:
            return val
    return None


def _column_names(ds) -> list[str]:
    cols = ds.column_names if hasattr(ds, "column_names") else []
    if isinstance(cols, dict):
        cols = list(cols.values())[0] if cols else []
    return list(cols or [])


def _auto_detect_text_keys(ds) -> list[str]:
    try:
        cols = _column_names(ds)
        found = [c for c in _COMMON_TEXT_KEYS if c in cols]
        return found if found else cols[:2]
    except Exception:
        return _COMMON_TEXT_KEYS[:3]


def _auto_detect_label_keys(ds) -> list[str]:
    try:
        cols = _column_names(ds)
        found = [c for c in _COMMON_LABEL_KEYS if c in cols]
        return found if found else [c for c in cols if c not in _COMMON_TEXT_KEYS][:1]
    except Exception:
        return _COMMON_LABEL_KEYS[:2]


def _convert_rows(
    ds,
    text_keys: list[str],
    label_keys: list[str],
    label_map: dict | None,
    max_samples: int | None,
) -> list[dict]:
    result = []
    for row in ds:
        if max_samples and len(result) >= max_samples:
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
    return result


def _load_from_file(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"数据集文件不存在: {path}")

    if path.suffix == ".jsonl":
        items = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("data", data.get("examples", [])) if isinstance(data, dict) else data

    result = []
    for item in items:
        text = item.get("text", item.get("content", item.get("prompt", "")))
        label = item.get("label", item.get("tag", item.get("category", "")))
        if text and label is not None:
            result.append({"text": str(text).strip(), "label": str(label).strip()})
    return result


def load_dataset(config: dict) -> list[dict]:
    source = str(config.get("source", "huggingface")).lower()
    dataset_id = config.get("dataset_id", "")
    split = config.get("split", "train")
    subset = config.get("subset")
    text_keys = config.get("text_keys")
    label_keys = config.get("label_keys")
    label_map = config.get("label_map")
    max_samples = config.get("max_samples")

    if source in {"file", "local"}:
        return _load_from_file(dataset_id)

    if source in {"huggingface", "hf"}:
        from datasets import load_dataset as hf_load_dataset

        ds = hf_load_dataset(dataset_id, subset, split=split, trust_remote_code=True)
        if isinstance(ds, dict):
            ds = ds.get(split, list(ds.values())[0] if ds else [])
    elif source in {"modelscope", "ms"}:
        from modelscope.msdatasets import MsDataset

        ds = MsDataset.load(dataset_id, subset_name=subset, split=split)
    else:
        raise ValueError(f"不支持的数据源: {source}，可选: huggingface, modelscope, file")

    text_keys = text_keys or _auto_detect_text_keys(ds)
    label_keys = label_keys or _auto_detect_label_keys(ds)
    return _convert_rows(ds, text_keys, label_keys, label_map, max_samples)


def main() -> int:
    try:
        raw = sys.stdin.read()
        config = json.loads(raw or "{}")
        with contextlib.redirect_stdout(sys.stderr):
            items = load_dataset(config)
        print(json.dumps({"ok": True, "items": items}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
