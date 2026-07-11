#!/usr/bin/env python3
"""
train_llm.py - LLM 对话模型训练脚本
用魔塔/HuggingFace 对话数据集微调本地 LLM

用法:
  python train_llm.py --check-gpu                    # 检查 GPU 状态
  python train_llm.py --list                         # 列出可用数据集和预设
  python train_llm.py --preset quick_1.8b            # 用预设快速训练
  python train_llm.py --model qwen_1.8b --dataset belle_0.5m
  python train_llm.py --model Qwen/Qwen1.5-1.8B-Chat --dataset belle_0.5m --epochs 3
  python train_llm.py --merge --adapter data/llm/adapters/xxx  # 合并 adapter
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _paths import module_root, data_dir

ROOT = module_root(__file__)
_DATA_DIR = data_dir(ROOT)
sys.path.insert(0, str(ROOT))

CONFIG_FILE = ROOT / "dialogue_datasets.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {"base_models": {}, "datasets": {}, "training_presets": {}}


def check_gpu():
    """检查 GPU 状态和推荐配置。支持 NVIDIA/AMD/Intel GPU。"""
    from llm_trainer import get_device_info
    info = get_device_info()
    
    print(f"\n{'='*50}")
    print(f"  GPU 状态检查")
    print(f"{'='*50}")
    print(f"  {info['message']}")
    
    if info.get("gpu_name"):
        print(f"  GPU: {info['gpu_name']}")
        print(f"  VRAM: {info.get('vram_gb', '?')} GB")
        print(f"  类型: {info.get('gpu_type', 'unknown')}")
        print(f"  推荐: {info.get('recommendation', 'unknown')}")
    
    print(f"\n{'='*50}")
    print(f"  GPU 支持说明")
    print(f"{'='*50}")
    
    gpu_type = info.get("gpu_type", "none")
    
    if gpu_type == "nvidia":
        print("  NVIDIA GPU: 完整支持训练和推理")
    elif gpu_type == "amd_rocm":
        print("  AMD GPU (ROCm): 完整支持训练和推理")
    elif gpu_type == "amd_zluda":
        print("  AMD GPU (ZLUDA): 支持训练和推理 (通过 CUDA 模拟)")
    elif gpu_type == "amd_directml":
        print("  AMD GPU (DirectML): 仅支持推理")
        print("  训练建议: 安装 ZLUDA (Windows) 或 ROCm (Linux)")
        print("  ZLUDA 下载: https://github.com/vosen/ZLUDA/releases")
    else:
        print("  未检测到 GPU，将使用 CPU")
        print("  CPU 训练会非常慢，建议:")
        print("    - 使用小模型 (MiniCPM-2B, Qwen-1.8B)")
        print("    - 减少数据量 (--max-samples 1000)")
        print("    - 预计 1000 条数据需要 2-4 小时")
        print("\n  如有 GPU，支持列表:")
        print("    - NVIDIA GPU: 安装 CUDA 版 PyTorch")
        print("    - AMD GPU (Windows): 安装 ZLUDA + CUDA 版 PyTorch")
        print("    - AMD GPU (Linux): 安装 ROCm 版 PyTorch")
        print("    - Intel GPU: 安装 DirectML 版 PyTorch (仅推理)")
    
    print(f"\n{'='*50}")
    print(f"  推荐基座模型")
    print(f"{'='*50}")
    
    config = load_config()
    vram = info.get("vram_gb", 0)
    
    for key, model in config.get("base_models", {}).items():
        min_vram = model.get("min_vram_gb", 0)
        status = "OK" if vram >= min_vram else "NO"
        print(f"  {status} {key}: {model['description']}")
    
    print()


def list_available():
    """列出可用的数据集和训练预设。"""
    config = load_config()
    
    print(f"\n{'='*50}")
    print(f"  可用基座模型")
    print(f"{'='*50}")
    for key, model in config.get("base_models", {}).items():
        print(f"  {key}: {model['description']}")
    
    print(f"\n{'='*50}")
    print(f"  可用数据集")
    print(f"{'='*50}")
    for key, ds in config.get("datasets", {}).items():
        print(f"  {key}: {ds.get('description', ds.get('dataset_id', '?'))}")
    
    print(f"\n{'='*50}")
    print(f"  训练预设")
    print(f"{'='*50}")
    for key, preset in config.get("training_presets", {}).items():
        print(f"  {key}: {preset.get('description', '?')}")
    
    print(f"\n用法示例:")
    print(f"  python train_llm.py --preset quick_1.8b")
    print(f"  python train_llm.py --model qwen_1.8b --dataset belle_0.5m")
    print(f"  python train_llm.py --model Qwen/Qwen1.5-1.8B-Chat --dataset belle_0.5m --epochs 3")
    print()


def train_with_preset(preset_name: str, overrides: dict) -> dict:
    """用预设训练。"""
    from llm_trainer import train_llm, load_dialogue_dataset
    
    config = load_config()
    presets = config.get("training_presets", {})
    
    if preset_name not in presets:
        print(f"错误: 预设 '{preset_name}' 不存在。")
        print(f"可用: {', '.join(presets.keys())}")
        sys.exit(1)
    
    preset = presets[preset_name]
    
    # 获取数据集配置
    dataset_key = overrides.get("dataset")
    if dataset_key:
        datasets = config.get("datasets", {})
        if dataset_key not in datasets:
            print(f"错误: 数据集 '{dataset_key}' 不存在。")
            print(f"可用: {', '.join(datasets.keys())}")
            sys.exit(1)
        dataset_config = datasets[dataset_key]
    else:
        # 使用默认数据集
        dataset_config = config.get("datasets", {}).get("belle_0.5m", {})
    
    # 合并参数
    max_samples = overrides.get("max_samples") or dataset_config.get("max_samples") or preset.get("max_samples")
    
    print(f"\n使用预设: {preset_name}")
    print(f"基座模型: {preset.get('base_model')}")
    print(f"数据集: {dataset_config.get('dataset_id', dataset_key)}")
    
    # 加载数据
    dataset_examples = load_dialogue_dataset({**dataset_config, "max_samples": max_samples})
    
    # 训练
    return train_llm(
        base_model=preset.get("base_model", "Qwen/Qwen1.5-1.8B-Chat"),
        dataset_examples=dataset_examples,
        epochs=overrides.get("epochs") or preset.get("epochs", 3),
        batch_size=overrides.get("batch_size") or preset.get("batch_size", 4),
        lr=overrides.get("lr") or preset.get("lr", 2e-4),
        lora_r=overrides.get("lora_r") or preset.get("lora_r", 16),
        max_seq_length=overrides.get("max_seq_length", 512),
    )


def train_with_args(args) -> dict:
    """用命令行参数训练。"""
    from llm_trainer import train_llm, load_dialogue_dataset
    
    config = load_config()
    
    # 解析模型
    base_model = args.model
    if base_model in config.get("base_models", {}):
        base_model = config["base_models"][base_model]["id"]
    
    # 解析数据集
    dataset_key = args.dataset
    if dataset_key in config.get("datasets", {}):
        dataset_config = config["datasets"][dataset_key]
    else:
        # 假设是直接的 dataset ID
        dataset_config = {
            "source": "huggingface",
            "dataset_id": dataset_key,
            "split": "train",
        }
    
    if args.max_samples:
        dataset_config["max_samples"] = args.max_samples
    
    print(f"\n基座模型: {base_model}")
    print(f"数据集: {dataset_config.get('dataset_id')}")
    
    # 加载数据
    dataset_examples = load_dialogue_dataset(dataset_config)
    
    # 训练
    return train_llm(
        base_model=base_model,
        dataset_examples=dataset_examples,
        epochs=args.epochs or 3,
        batch_size=args.batch_size or 4,
        lr=args.lr or 2e-4,
        lora_r=args.lora_r or 16,
        lora_alpha=args.lora_alpha or 32,
        max_seq_length=args.max_seq_length or 512,
        load_in_4bit=not args.no_4bit,
        use_directml=getattr(args, 'directml', False),
    )


def merge_adapter(adapter_path: str, output_name: str | None = None) -> dict:
    """合并 adapter 到基座模型。"""
    from llm_trainer import merge_adapter as _merge
    
    adapter_dir = Path(adapter_path)
    if not adapter_dir.exists():
        print(f"错误: adapter 目录不存在: {adapter_path}")
        sys.exit(1)
    
    # 读取基座模型
    config_file = adapter_dir / "train_config.json"
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
        base_model = config.get("base_model")
    else:
        print("错误: 找不到 train_config.json，无法确定基座模型")
        sys.exit(1)
    
    if output_name is None:
        output_name = f"{adapter_dir.name}_merged"
    
    output_dir = _DATA_DIR / "llm" / "merged" / output_name
    
    print(f"\n合并模型:")
    print(f"  基座: {base_model}")
    print(f"  Adapter: {adapter_path}")
    print(f"  输出: {output_dir}")
    
    return _merge(base_model, str(adapter_dir), str(output_dir))


def main():
    parser = argparse.ArgumentParser(description="LLM 对话模型训练工具")
    
    parser.add_argument("--check-gpu", action="store_true", help="检查 GPU 状态")
    parser.add_argument("--list", action="store_true", help="列出可用数据集和预设")
    parser.add_argument("--preset", type=str, help="使用训练预设")
    parser.add_argument("--model", type=str, help="基座模型 (ID 或配置名)")
    parser.add_argument("--dataset", type=str, help="数据集 (配置名或 HF ID)")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch-size", type=int, dest="batch_size")
    parser.add_argument("--lr", type=float)
    parser.add_argument("--lora-r", type=int, dest="lora_r")
    parser.add_argument("--lora-alpha", type=int, dest="lora_alpha")
    parser.add_argument("--max-samples", type=int, dest="max_samples")
    parser.add_argument("--max-seq-length", type=int, default=512, dest="max_seq_length")
    parser.add_argument("--no-4bit", action="store_true", dest="no_4bit", help="禁用 4-bit 量化")
    parser.add_argument("--directml", action="store_true", help="强制使用 DirectML (AMD/Intel GPU)")
    parser.add_argument("--cpu", action="store_true", help="强制使用 CPU (无 GPU 时自动使用)")
    
    parser.add_argument("--merge", action="store_true", help="合并 adapter 模式")
    parser.add_argument("--adapter", type=str, help="adapter 路径 (合并模式)")
    parser.add_argument("--output-name", type=str, dest="output_name", help="合并输出名称")
    
    args = parser.parse_args()
    
    if args.check_gpu:
        check_gpu()
        return
    
    if args.list:
        list_available()
        return
    
    if args.merge:
        if not args.adapter:
            print("错误: 合并模式需要 --adapter 参数")
            sys.exit(1)
        result = merge_adapter(args.adapter, args.output_name)
        if result.get("ok"):
            print(f"\n合并完成: {result['output_dir']}")
        else:
            print(f"\n合并失败: {result.get('error')}")
        sys.exit(0 if result.get("ok") else 1)
    
    if args.preset:
        overrides = {k: v for k, v in vars(args).items() if v is not None and k not in ("check_gpu", "list", "preset", "merge", "adapter", "output_name")}
        result = train_with_preset(args.preset, overrides)
    elif args.model and args.dataset:
        result = train_with_args(args)
    else:
        parser.print_help()
        print("\n请指定 --preset 或 --model + --dataset")
        sys.exit(1)
    
    if result.get("ok"):
        print(f"\n训练完成!")
        print(f"输出目录: {result['output_dir']}")
        print(f"训练 Loss: {result['train_loss']}")
        print(f"\n可以运行以下命令合并模型:")
        print(f"  python train_llm.py --merge --adapter {result['output_dir']}")
    else:
        print(f"\n训练失败: {result.get('error')}")
    
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
