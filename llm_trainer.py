"""
llm_trainer.py - LLM 微调训练器
基于 transformers + PEFT (LoRA) 微调对话模型
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from _paths import module_root, data_dir
from dependency_utils import ensure_dataset_dependencies

ROOT = module_root(__file__)
MODEL_DIR = data_dir(ROOT) / "llm"
ADAPTER_DIR = MODEL_DIR / "adapters"


def get_device_info() -> dict:
    """获取 GPU 信息，用于决定训练策略。支持 NVIDIA/AMD/Intel GPU。"""
    try:
        import torch
    except ImportError:
        return {
            "cuda": False,
            "directml": False,
            "vram_gb": 0,
            "recommendation": "no_torch",
            "message": "PyTorch 未安装。"
        }
    
    # 检查 CUDA (NVIDIA)
    if torch.cuda.is_available():
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        name = torch.cuda.get_device_name(0)
        
        if vram >= 24:
            rec = "full_ft"
        elif vram >= 16:
            rec = "lora_7b"
        elif vram >= 8:
            rec = "qlora_7b"
        else:
            rec = "small_model"
        
        return {
            "cuda": True,
            "directml": False,
            "vram_gb": round(vram, 1),
            "gpu_name": name,
            "gpu_type": "nvidia",
            "recommendation": rec,
            "message": f"NVIDIA GPU: {name}, VRAM: {vram:.1f}GB, 建议: {rec}"
        }
    
    # 检查 DirectML (AMD/Intel on Windows)
    try:
        import torch_directml
        dml_device = torch_directml.device()
        # DirectML 不提供 VRAM 信息，尝试通过其他方式估算
        # 通常 AMD GPU 至少有 4GB VRAM
        return {
            "cuda": False,
            "directml": True,
            "vram_gb": 4,  # 保守估计
            "gpu_name": "AMD/Intel GPU (DirectML)",
            "gpu_type": "amd_directml",
            "recommendation": "directml_inference",
            "message": "检测到 AMD/Intel GPU (DirectML)。可用于推理，训练支持有限。建议安装 ZLUDA 获得更好支持。"
        }
    except ImportError:
        pass
    
    # 检查 ROCm (AMD on Linux)
    if hasattr(torch.version, 'hip') and torch.version.hip:
        try:
            props = torch.cuda.get_device_properties(0)
            vram = props.total_memory / 1e9
            name = props.name
            
            if vram >= 16:
                rec = "lora_7b"
            elif vram >= 8:
                rec = "qlora_7b"
            else:
                rec = "small_model"
            
            return {
                "cuda": True,  # ROCm 模拟 CUDA API
                "directml": False,
                "vram_gb": round(vram, 1),
                "gpu_name": name,
                "gpu_type": "amd_rocm",
                "recommendation": rec,
                "message": f"AMD GPU (ROCm): {name}, VRAM: {vram:.1f}GB, 建议: {rec}"
            }
        except Exception:
            pass
    
    # 检查 ZLUDA (AMD GPU 模拟 CUDA)
    import os
    if os.environ.get("ZLUDA_CUDA") or os.path.exists("zluda.dll") or os.path.exists("nvcuda.dll"):
        try:
            # ZLUDA 让 torch.cuda 可用
            if torch.cuda.is_available():
                vram = torch.cuda.get_device_properties(0).total_memory / 1e9
                name = torch.cuda.get_device_name(0)
                
                return {
                    "cuda": True,
                    "directml": False,
                    "vram_gb": round(vram, 1),
                    "gpu_name": f"{name} (ZLUDA)",
                    "gpu_type": "amd_zluda",
                    "recommendation": "qlora_7b" if vram >= 8 else "small_model",
                    "message": f"AMD GPU (ZLUDA): {name}, VRAM: {vram:.1f}GB"
                }
        except Exception:
            pass
    
    return {
        "cuda": False,
        "directml": False,
        "vram_gb": 0,
        "gpu_type": "cpu",
        "recommendation": "cpu_only",
        "message": "未检测到 GPU，将使用 CPU。训练会非常慢，建议使用小模型 (1.8B 以下) 和少量数据。"
    }


def load_dialogue_dataset(config: dict) -> list[dict]:
    """
    加载对话数据集，转换为统一格式。
    
    输出格式: [{"instruction": str, "input": str, "output": str}, ...]
    """
    source = config.get("source", "huggingface")
    dataset_id = config.get("dataset_id", "")
    split = config.get("split", "train")
    max_samples = config.get("max_samples")
    
    # 字段映射
    instruction_keys = config.get("instruction_keys", ["instruction", "question", "prompt", "input"])
    input_keys = config.get("input_keys", ["input", "context", "history"])
    output_keys = config.get("output_keys", ["output", "response", "answer", "target"])
    
    if source in ("huggingface", "hf"):
        status = ensure_dataset_dependencies(auto_install=True)
        if not status.ok:
            from dependency_utils import DATASET_INSTALL_CMD
            raise ImportError(f"{status.detail}\n运行时 Python: {status.python}\n请安装: {DATASET_INSTALL_CMD}")
        from datasets import load_dataset
        ds = load_dataset(dataset_id, split=split, trust_remote_code=True)
    elif source in ("modelscope", "ms"):
        status = ensure_dataset_dependencies(auto_install=True)
        if not status.ok:
            from dependency_utils import DATASET_INSTALL_CMD
            raise ImportError(f"{status.detail}\n运行时 Python: {status.python}\n请安装: {DATASET_INSTALL_CMD}")
        from modelscope.msdatasets import MsDataset
        ds = MsDataset.load(dataset_id, split=split)
    elif source in ("file", "local"):
        path = Path(dataset_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        ds = data if isinstance(data, list) else data.get("data", [])
    else:
        raise ValueError(f"Unknown source: {source}")
    
    result = []
    for row in ds:
        if max_samples and len(result) >= max_samples:
            break
        
        instruction = _pick_field(row, instruction_keys)
        input_text = _pick_field(row, input_keys, default="")
        output = _pick_field(row, output_keys)
        
        if instruction and output:
            result.append({
                "instruction": instruction,
                "input": input_text,
                "output": output,
            })
    
    print(f"[llm_trainer] 加载 {len(result)} 条对话样本")
    return result


def _pick_field(row: dict, keys: list[str], default: str | None = None) -> str | None:
    for key in keys:
        val = row.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return default


def format_alpaca(example: dict) -> str:
    """将样本格式化为 Alpaca 风格的 prompt。"""
    if example.get("input"):
        return f"""### 指令：
{example['instruction']}

### 输入：
{example['input']}

### 回答：
{example['output']}"""
    else:
        return f"""### 指令：
{example['instruction']}

### 回答：
{example['output']}"""


def train_llm(
    base_model: str = "Qwen/Qwen1.5-1.8B-Chat",
    dataset_config: dict | None = None,
    dataset_examples: list[dict] | None = None,
    output_dir: str | None = None,
    # LoRA 参数
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    lora_target_modules: list[str] | None = None,
    # 训练参数
    epochs: int = 3,
    batch_size: int = 4,
    gradient_accumulation: int = 4,
    lr: float = 2e-4,
    max_seq_length: int = 512,
    # 量化参数
    load_in_4bit: bool = True,
    bnb_4bit_compute_dtype: str = "float16",
    # 其他
    use_gradient_checkpointing: bool = True,
    save_strategy: str = "epoch",
    # AMD GPU 参数
    use_directml: bool = False,
    device_id: int = 0,
) -> dict:
    """
    微调 LLM。支持 NVIDIA CUDA、AMD ROCm、AMD ZLUDA、DirectML。
    
    参数:
        base_model: 基座模型 ID (HuggingFace)
        dataset_config: 数据集加载配置
        dataset_examples: 直接提供数据 (优先于 dataset_config)
        output_dir: 输出目录
        use_directml: 强制使用 DirectML (AMD/Intel GPU)
        device_id: GPU 设备 ID
        ...其他为 LoRA/训练参数
    """
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
            BitsAndBytesConfig,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from datasets import Dataset
    except ImportError as e:
        return {
            "ok": False,
            "error": f"缺少依赖: {e}\n请安装: pip install transformers peft accelerate bitsandbytes datasets"
        }
    
    # 设备检测与选择
    device_info = get_device_info()
    gpu_type = device_info.get("gpu_type", "cpu")
    
    # CPU 模式警告
    if gpu_type == "cpu":
        print("\n警告： 警告: 使用 CPU 训练会非常慢！")
        print("   建议: 使用小模型 (如 MiniCPM-2B) + 少量数据 (--max-samples 1000)")
        print("   预计时间: 1000 条数据约需 2-4 小时\n")
    
    # 确定设备和量化策略
    use_quantization = False
    device_map = "auto"
    
    if gpu_type == "cpu":
        # CPU 模式 - 不支持量化，使用 fp32
        use_quantization = False
        device_map = None
        print("使用 CPU 模式 (fp32)")
    elif use_directml or gpu_type == "amd_directml":
        # DirectML 模式 - 不支持量化训练，只能做推理
        # 训练建议使用 ZLUDA 或 ROCm
        return {
            "ok": False,
            "error": "DirectML 不支持 LLM 训练。请安装 ZLUDA (Windows) 或 ROCm (Linux) 来使用 AMD GPU 训练。\n"
                     "DirectML 只能用于推理，训练需要完整的 CUDA 兼容性。"
        }
    elif gpu_type == "amd_zluda":
        # ZLUDA 模式 - 模拟 CUDA，支持大部分功能
        use_quantization = load_in_4bit
        print("使用 AMD GPU (ZLUDA 模式)")
    elif gpu_type == "amd_rocm":
        # ROCm 模式 - 原生 AMD 支持
        use_quantization = load_in_4bit
        print("使用 AMD GPU (ROCm 模式)")
    else:
        # NVIDIA CUDA 模式
        use_quantization = load_in_4bit
    
    # 加载数据
    if dataset_examples is None:
        if dataset_config is None:
            return {"ok": False, "error": "需要提供 dataset_config 或 dataset_examples"}
        dataset_examples = load_dialogue_dataset(dataset_config)
    
    if not dataset_examples:
        return {"ok": False, "error": "没有训练数据"}
    
    # 设置输出目录
    if output_dir is None:
        model_name = base_model.split("/")[-1]
        output_dir = str(ADAPTER_DIR / f"{model_name}_lora")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"  基座模型: {base_model}")
    print(f"  训练样本: {len(dataset_examples)} 条")
    print(f"  输出目录: {output_dir}")
    print(f"  GPU 类型: {gpu_type}")
    print(f"  量化: {use_quantization}")
    print(f"  LoRA: r={lora_r}, alpha={lora_alpha}")
    print(f"  训练: epochs={epochs}, batch={batch_size}, lr={lr}")
    print(f"{'='*60}\n")
    
    # 量化配置
    bnb_config = None
    if use_quantization:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=getattr(torch, bnb_4bit_compute_dtype),
            bnb_4bit_use_double_quant=True,
        )
    
    # 加载 tokenizer
    print("加载 tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        base_model,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # 加载模型
    print("加载模型...")
    
    # CPU 模式使用 fp32
    torch_dtype = torch.float32 if gpu_type == "cpu" else torch.float16
    
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        torch_dtype=torch_dtype if not use_quantization else None,
        device_map=device_map if use_quantization else None,
        trust_remote_code=True,
    )
    
    # CPU 模式手动移到 CPU
    if gpu_type == "cpu":
        model = model.to("cpu")
    
    if use_quantization:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=use_gradient_checkpointing)
    
    # LoRA 配置
    if lora_target_modules is None:
        # 默认目标模块 (适用于大多数模型)
        lora_target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=lora_target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    # 准备数据集
    print("准备数据集...")
    texts = [format_alpaca(ex) + tokenizer.eos_token for ex in dataset_examples]
    
    def tokenize_fn(text):
        encoding = tokenizer(
            text,
            truncation=True,
            max_length=max_seq_length,
            padding="max_length",
            return_tensors="pt",
        )
        encoding["labels"] = encoding["input_ids"].clone()
        return encoding
    
    train_dataset = Dataset.from_dict({"text": texts})
    train_dataset = train_dataset.map(
        lambda x: tokenize_fn(x["text"]),
        remove_columns=["text"],
    )
    
    # 训练参数
    # CPU 模式禁用 fp16
    use_fp16 = gpu_type != "cpu" and torch.cuda.is_available()
    
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation,
        learning_rate=lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        fp16=use_fp16,
        bf16=False,
        logging_steps=10,
        save_strategy=save_strategy,
        save_total_limit=3,
        report_to="none",
        no_cuda=(gpu_type == "cpu"),
    )
    
    # 训练器
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        tokenizer=tokenizer,
    )
    
    print("开始训练...")
    train_result = trainer.train()
    
    # 保存
    print("保存模型...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    # 保存训练配置
    config_path = Path(output_dir) / "train_config.json"
    config_path.write_text(json.dumps({
        "base_model": base_model,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "samples": len(dataset_examples),
        "train_loss": train_result.training_loss,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    
    result = {
        "ok": True,
        "output_dir": output_dir,
        "base_model": base_model,
        "samples": len(dataset_examples),
        "train_loss": round(train_result.training_loss, 4),
        "epochs": epochs,
        "lora_r": lora_r,
        "gpu_type": gpu_type,
    }
    
    print(f"\n{'='*60}")
    print(f"  训练完成!")
    print(f"  输出: {output_dir}")
    print(f"  Loss: {result['train_loss']}")
    print(f"{'='*60}\n")
    
    return result


def merge_adapter(
    base_model: str,
    adapter_dir: str,
    output_dir: str,
) -> dict:
    """将 LoRA adapter 合并到基座模型。"""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError as e:
        return {"ok": False, "error": f"缺少依赖: {e}"}
    
    print(f"合并模型: {base_model} + {adapter_dir} -> {output_dir}")
    
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, adapter_dir)
    merged = model.merge_and_unload()
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    return {"ok": True, "output_dir": output_dir}


def list_adapters() -> list[dict]:
    """列出已训练的 adapter。"""
    adapters = []
    if ADAPTER_DIR.exists():
        for d in ADAPTER_DIR.iterdir():
            if d.is_dir():
                config_file = d / "train_config.json"
                if config_file.exists():
                    config = json.loads(config_file.read_text(encoding="utf-8"))
                    adapters.append({
                        "name": d.name,
                        "path": str(d),
                        **config,
                    })
    return adapters
