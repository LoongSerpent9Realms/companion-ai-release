"""
llm_inference.py - 本地 LLM 推理引擎
加载训练好的模型进行对话
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

from _paths import module_root

ROOT = module_root(__file__)
MODEL_DIR = ROOT / "data" / "llm"
ADAPTER_DIR = MODEL_DIR / "adapters"
MERGED_DIR = MODEL_DIR / "merged"


class LocalLLM:
    """本地 LLM 推理器。"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.model_path = None
        self.adapter_path = None
        self.device = None
    
    @property
    def loaded(self) -> bool:
        return self.model is not None and self.tokenizer is not None
    
    def load(
        self,
        model_path: str | None = None,
        adapter_path: str | None = None,
        load_in_4bit: bool = True,
        use_directml: bool = False,
    ) -> dict:
        """
        加载模型。支持 NVIDIA CUDA、AMD ROCm/ZLUDA、DirectML。
        
        参数:
            model_path: 合并后的完整模型路径，或基座模型 ID
            adapter_path: LoRA adapter 路径 (可选，如果有则加载 adapter)
            load_in_4bit: 是否 4-bit 量化加载 (仅 NVIDIA/ROCm/ZLUDA)
            use_directml: 强制使用 DirectML (AMD/Intel GPU 推理)
        """
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            return {"ok": False, "error": f"缺少依赖: {e}"}
        
        if model_path is None:
            # 尝试自动查找
            model_path = self._find_model()
            if model_path is None:
                return {"ok": False, "error": "没有找到已训练的模型。请先训练或指定模型路径。"}
        
        print(f"[llm_inference] 加载模型: {model_path}")
        
        try:
            # 检测 GPU 类型
            gpu_type = "none"
            if torch.cuda.is_available():
                gpu_type = "cuda"
            else:
                try:
                    import torch_directml
                    gpu_type = "directml"
                except ImportError:
                    pass
            
            # DirectML 模式
            if use_directml or gpu_type == "directml":
                try:
                    import torch_directml
                    from peft import PeftModel
                    
                    print("[llm_inference] 使用 DirectML 模式")
                    
                    # 加载 tokenizer
                    self.tokenizer = AutoTokenizer.from_pretrained(
                        model_path,
                        trust_remote_code=True,
                    )
                    if self.tokenizer.pad_token is None:
                        self.tokenizer.pad_token = self.tokenizer.eos_token
                    
                    # 加载模型到 CPU，然后移到 DirectML 设备
                    self.model = AutoModelForCausalLM.from_pretrained(
                        model_path,
                        torch_dtype=torch.float32,
                        device_map=None,
                        trust_remote_code=True,
                    )
                    
                    # 加载 adapter (如果有)
                    if adapter_path and Path(adapter_path).exists():
                        print(f"[llm_inference] 加载 adapter: {adapter_path}")
                        self.model = PeftModel.from_pretrained(self.model, adapter_path)
                        self.adapter_path = adapter_path
                    
                    # 移到 DirectML 设备
                    dml_device = torch_directml.device()
                    self.model = self.model.to(dml_device)
                    
                    self.model_path = model_path
                    self.device = "directml"
                    
                    return {
                        "ok": True,
                        "model_path": model_path,
                        "adapter_path": adapter_path,
                        "device": self.device,
                    }
                except ImportError:
                    return {"ok": False, "error": "DirectML 不可用。请安装 torch-directml。"}
            
            # CUDA/ROCm/ZLUDA/CPU 模式
            from transformers import BitsAndBytesConfig
            from peft import PeftModel
            
            # 量化配置 (DirectML/CPU 不支持)
            bnb_config = None
            if load_in_4bit and torch.cuda.is_available():
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                )
            
            # CPU 模式使用 fp32
            torch_dtype = torch.float32 if gpu_type in ("cpu", "none") else torch.float16
            
            # 加载 tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # 加载模型
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=bnb_config,
                torch_dtype=torch_dtype if not bnb_config else None,
                device_map="auto" if torch.cuda.is_available() else None,
                trust_remote_code=True,
            )
            
            # CPU 模式手动移到 CPU
            if gpu_type in ("cpu", "none"):
                self.model = self.model.to("cpu")
            
            # 加载 adapter (如果有)
            if adapter_path and Path(adapter_path).exists():
                print(f"[llm_inference] 加载 adapter: {adapter_path}")
                self.model = PeftModel.from_pretrained(self.model, adapter_path)
                self.adapter_path = adapter_path
            
            self.model_path = model_path
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            
            return {
                "ok": True,
                "model_path": model_path,
                "adapter_path": adapter_path,
                "device": self.device,
            }
        except Exception as e:
            return {"ok": False, "error": f"加载失败: {e}"}
    
    def _find_model(self) -> str | None:
        """自动查找可用的模型。"""
        # 优先使用合并后的模型
        if MERGED_DIR.exists():
            for d in sorted(MERGED_DIR.iterdir(), reverse=True):
                if d.is_dir() and (d / "config.json").exists():
                    return str(d)
        
        # 其次使用 adapter
        if ADAPTER_DIR.exists():
            for d in sorted(ADAPTER_DIR.iterdir(), reverse=True):
                if d.is_dir() and (d / "adapter_config.json").exists():
                    # 读取基座模型
                    config_file = d / "train_config.json"
                    if config_file.exists():
                        config = json.loads(config_file.read_text(encoding="utf-8"))
                        return config.get("base_model")
        
        return None
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repetition_penalty: float = 1.1,
    ) -> str:
        """生成回复。"""
        if not self.loaded:
            return "[模型未加载]"
        
        import torch
        
        inputs = self.tokenizer(prompt, return_tensors="pt")
        
        # 移到正确的设备
        if self.device == "directml":
            try:
                import torch_directml
                dml_device = torch_directml.device()
                inputs = {k: v.to(dml_device) for k, v in inputs.items()}
            except ImportError:
                pass
        elif self.device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        
        # 只解码新生成的部分
        new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        response = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        
        return response.strip()
    
    def chat(
        self,
        message: str,
        history: list[tuple[str, str]] | None = None,
        system_prompt: str = "你是一个友好的桌面宠物助手。",
        **kwargs,
    ) -> str:
        """
        对话模式。
        
        参数:
            message: 用户消息
            history: 历史对话 [(user, assistant), ...]
            system_prompt: 系统提示
        """
        if not self.loaded:
            return "[模型未加载]"
        
        # 构建 prompt
        prompt = self._build_chat_prompt(message, history, system_prompt)
        
        # 生成
        response = self.generate(prompt, **kwargs)
        
        # 清理响应 (移除可能的重复指令部分)
        response = self._clean_response(response)
        
        return response
    
    def _build_chat_prompt(
        self,
        message: str,
        history: list[tuple[str, str]] | None,
        system_prompt: str,
    ) -> str:
        """构建对话 prompt。"""
        parts = [f"<|system|>\n{system_prompt}\n"]
        
        if history:
            for user_msg, assistant_msg in history[-5:]:  # 只保留最近5轮
                parts.append(f"<|user|>\n{user_msg}\n")
                parts.append(f"<|assistant|>\n{assistant_msg}\n")
        
        parts.append(f"<|user|>\n{message}\n")
        parts.append("<|assistant|>\n")
        
        return "".join(parts)
    
    def _clean_response(self, response: str) -> str:
        """清理生成的响应。"""
        # 移除可能的标记
        for marker in ["<|user|>", "<|assistant|>", "<|system|>", "###"]:
            if marker in response:
                response = response.split(marker)[0]
        
        # 移除空行
        lines = [line.strip() for line in response.split("\n") if line.strip()]
        return "\n".join(lines)
    
    def stream_chat(
        self,
        message: str,
        history: list[tuple[str, str]] | None = None,
        system_prompt: str = "你是一个友好的桌面宠物助手。",
        **kwargs,
    ) -> Generator[str, None, None]:
        """流式对话。"""
        if not self.loaded:
            yield "[模型未加载]"
            return
        
        import torch
        
        prompt = self._build_chat_prompt(message, history, system_prompt)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        max_new_tokens = kwargs.get("max_new_tokens", 256)
        temperature = kwargs.get("temperature", 0.7)
        
        with torch.no_grad():
            for outputs in self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                return_dict_in_generate=True,
                output_scores=False,
            ):
                pass  # 简化版，实际流式需要更复杂的实现
        
        # 简化：直接返回完整响应
        response = self.generate(prompt, **kwargs)
        yield self._clean_response(response)
    
    def unload(self):
        """卸载模型释放显存。"""
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        
        self.model_path = None
        self.adapter_path = None


# 全局实例
_local_llm = LocalLLM()


def get_local_llm() -> LocalLLM:
    """获取全局 LLM 实例。"""
    return _local_llm


def is_local_model_available() -> bool:
    """检查本地模型是否可用。"""
    return _local_llm.loaded


def local_chat(message: str, history: list[tuple[str, str]] | None = None, **kwargs) -> str:
    """使用本地模型对话。"""
    if not _local_llm.loaded:
        # 尝试自动加载
        result = _local_llm.load()
        if not result.get("ok"):
            return f"[本地模型不可用: {result.get('error', '未知错误')}]"
    
    return _local_llm.chat(message, history, **kwargs)
