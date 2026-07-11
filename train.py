#!/usr/bin/env python3
"""
train.py - 独立训练脚本
支持从 ModelScope / HuggingFace / 本地文件 加载数据集训练 MotionNet。

用法:
  python train.py --list                        # 列出可用数据集
  python train.py --dataset emotion_en          # 用配置中的数据集训练
  python train.py --hf emotion                  # 直接从 HuggingFace 加载
  python train.py --ms Belle/Belle-3-5M         # 直接从 ModelScope 加载
  python train.py --file data/datasets/my.json  # 从本地文件加载
  python train.py --dataset emotion_en --epochs 100 --batch 32 --lr 0.01
  python train.py --model-tag my_emotion_model  # 自定义模型文件名
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from _paths import module_root

ROOT = module_root(__file__)
sys.path.insert(0, str(ROOT))

CONFIG_FILE = ROOT / "train_config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {"datasets": {}, "training": {}}


def list_datasets():
    """列出配置中的数据集和预置推荐。"""
    config = load_config()
    print("\n=== 配置中的数据集 ===")
    for key, ds in config.get("datasets", {}).items():
        active = " <-- 当前激活" if key == config.get("active_dataset") else ""
        print(f"  {key}: {ds.get('description', ds.get('dataset_id', '?'))}{active}")

    print("\n=== 预置推荐数据集 ===")
    try:
        from dataset_loader import list_available_datasets
        for ds in list_available_datasets():
            print(f"  [{ds['source']}] {ds['id']}: {ds['description']} (~{ds.get('size', '?')} 条)")
    except Exception as e:
        print(f"  (无法加载推荐列表: {e})")

    print("\n用法示例:")
    print("  python train.py --dataset emotion_en")
    print("  python train.py --hf emotion --max-samples 5000")
    print("  python train.py --ms Belle/Belle-3-5M --max-samples 10000")
    print("  python train.py --file data/datasets/custom.json")
    print()


def train_with_config(dataset_key: str, overrides: dict) -> dict:
    """用 train_config.json 中的配置训练。"""
    config = load_config()
    datasets = config.get("datasets", {})
    if dataset_key not in datasets:
        print(f"错误: 数据集 '{dataset_key}' 不在 train_config.json 中。")
        print(f"可用: {', '.join(datasets.keys())}")
        sys.exit(1)

    ds_config = datasets[dataset_key]
    train_cfg = config.get("training", {})

    for k, v in overrides.items():
        if v is not None:
            train_cfg[k] = v

    return _run_training(ds_config, train_cfg, overrides.get("model_tag", dataset_key))


def train_with_direct(source: str, dataset_id: str, overrides: dict) -> dict:
    """直接用参数训练（不依赖配置文件）。"""
    from dataset_loader import load_dataset_from_config

    ds_config = {
        "source": source,
        "dataset_id": dataset_id,
        "split": overrides.get("split", "train"),
        "subset": overrides.get("subset"),
        "max_samples": overrides.get("max_samples"),
        "text_keys": overrides.get("text_keys"),
        "label_keys": overrides.get("label_keys"),
        "label_map": overrides.get("label_map"),
    }

    train_cfg = {
        "epochs": overrides.get("epochs", 50),
        "batch_size": overrides.get("batch_size", 64),
        "lr": overrides.get("lr", 0.005),
        "val_split": overrides.get("val_split", 0.15),
        "early_stop_patience": overrides.get("early_stop_patience", 5),
        "merge_seed": overrides.get("merge_seed", True),
    }

    model_tag = overrides.get("model_tag", "dataset_model")
    return _run_training(ds_config, train_cfg, model_tag)


def _run_training(ds_config: dict, train_cfg: dict, model_tag: str) -> dict:
    """执行训练流程。"""
    from dataset_loader import load_dataset_from_config
    from neural_companion import train_from_dataset

    print(f"\n{'='*60}")
    print(f"  加载数据集: {ds_config.get('dataset_id', '?')}")
    print(f"  来源: {ds_config.get('source', '?')}")
    print(f"{'='*60}\n")

    t0 = time.time()
    examples = load_dataset_from_config(ds_config)
    t_load = time.time() - t0
    print(f"  加载耗时: {t_load:.1f}s，共 {len(examples)} 条样本")

    if not examples:
        print("错误: 没有加载到任何样本，请检查数据集配置。")
        sys.exit(1)

    label_dist = {}
    for item in examples:
        label_dist[item["label"]] = label_dist.get(item["label"], 0) + 1
    print(f"  标签分布: {dict(sorted(label_dist.items(), key=lambda x: -x[1]))}")

    print(f"\n{'='*60}")
    print(f"  开始训练")
    print(f"  epochs={train_cfg.get('epochs')}, batch={train_cfg.get('batch_size')}, lr={train_cfg.get('lr')}")
    print(f"  val_split={train_cfg.get('val_split')}, early_stop={train_cfg.get('early_stop_patience')}")
    print(f"{'='*60}\n")

    t1 = time.time()
    result = train_from_dataset(
        dataset_examples=examples,
        epochs=train_cfg.get("epochs", 50),
        batch_size=train_cfg.get("batch_size", 64),
        lr=train_cfg.get("lr", 0.005),
        val_split=train_cfg.get("val_split", 0.15),
        early_stop_patience=train_cfg.get("early_stop_patience", 5),
        model_tag=model_tag,
        merge_seed=train_cfg.get("merge_seed", True),
    )
    t_train = time.time() - t1

    if result.get("ok"):
        print(f"\n{'='*60}")
        print(f"  训练完成!")
        print(f"{'='*60}")
        print(f"  模型文件: {result['model']}")
        print(f"  设备: {result['device']} (CUDA={result['cuda']}, DirectML={result.get('directml', False)})")
        print(f"  样本数: {result['examples']}")
        print(f"  词表大小: {result['vocab_size']}")
        print(f"  标签数: {result['label_count']} -> {result['labels']}")
        print(f"  训练轮数: {result['epochs_trained']}")
        print(f"  最终 loss: {result['loss']}")
        if result.get('val_loss') is not None:
            print(f"  验证 loss: {result['val_loss']}")
        print(f"  训练耗时: {t_train:.1f}s")
        print(f"{'='*60}\n")
    else:
        print(f"\n训练失败: {result.get('error', '未知错误')}")
        if not result.get('available'):
            print(result.get('install', '请安装 PyTorch。'))

    return result


def main():
    parser = argparse.ArgumentParser(description="Companion AI 数据集训练工具")
    parser.add_argument("--list", action="store_true", help="列出可用数据集")
    parser.add_argument("--dataset", type=str, help="使用 train_config.json 中的数据集")
    parser.add_argument("--hf", type=str, help="直接从 HuggingFace 加载 (dataset_id)")
    parser.add_argument("--ms", type=str, help="直接从 ModelScope 加载 (dataset_id)")
    parser.add_argument("--file", type=str, help="从本地文件加载 (JSON/JSONL)")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch", type=int, default=None, dest="batch_size")
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--val-split", type=float, default=None, dest="val_split")
    parser.add_argument("--patience", type=int, default=None, dest="early_stop_patience")
    parser.add_argument("--max-samples", type=int, default=None, dest="max_samples")
    parser.add_argument("--model-tag", type=str, default=None, dest="model_tag")
    parser.add_argument("--split", type=str, default=None, help="数据集 split (默认 train)")
    parser.add_argument("--subset", type=str, default=None, help="数据集子集")
    parser.add_argument("--no-seed", action="store_true", dest="no_seed", help="不合并内置种子样本")
    parser.add_argument("--text-keys", type=str, nargs="+", default=None, dest="text_keys")
    parser.add_argument("--label-keys", type=str, nargs="+", default=None, dest="label_keys")

    args = parser.parse_args()

    if args.list:
        list_datasets()
        return

    overrides = {k: v for k, v in vars(args).items() if v is not None and k not in ("list", "dataset", "hf", "ms", "file")}
    if args.no_seed:
        overrides["merge_seed"] = False

    if args.dataset:
        result = train_with_config(args.dataset, overrides)
    elif args.hf:
        overrides.setdefault("model_tag", "dataset_model")
        result = train_with_direct("huggingface", args.hf, overrides)
    elif args.ms:
        overrides.setdefault("model_tag", "dataset_model")
        result = train_with_direct("modelscope", args.ms, overrides)
    elif args.file:
        overrides.setdefault("model_tag", "dataset_model")
        result = train_with_direct("file", args.file, overrides)
    else:
        parser.print_help()
        print("\n请指定 --dataset, --hf, --ms, 或 --file")
        sys.exit(1)

    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
