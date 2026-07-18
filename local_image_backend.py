"""Optional, local-only ComfyUI bridge for Companion AI mood images.

The bridge is deliberately opt-in.  It talks only to a ComfyUI service the
user has started on this computer (normally ``127.0.0.1:8188``), uses an API
workflow exported by that user, and falls back to the built-in mood-card
renderer whenever the bridge is disabled or fails.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import parse, request

from _paths import data_dir, module_root
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
CONFIG_FILE = DATA_DIR / "local_image_backend.json"
OUTPUT_DIR = DATA_DIR / "comfyui_images"
DEFAULT_CONFIG = {
    "enabled": False,
    "backend": "mood_card",
    "endpoint": "http://127.0.0.1:8188",
    "workflow_path": "",
    "prompt_node_id": "",
    "negative_prompt_node_id": "",
    "seed_node_id": "",
}


def load_config() -> dict[str, Any]:
    saved = read_sensitive_json(CONFIG_FILE, {})
    config = dict(DEFAULT_CONFIG)
    if isinstance(saved, dict):
        config.update({key: saved.get(key, value) for key, value in DEFAULT_CONFIG.items()})
    return config


def save_config(updates: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    config["enabled"] = bool(updates.get("enabled", config["enabled"]))
    backend = str(updates.get("backend", config["backend"])).strip().lower()
    config["backend"] = backend if backend in {"mood_card", "comfyui"} else "mood_card"
    endpoint = str(updates.get("endpoint", config["endpoint"])).strip().rstrip("/")
    config["endpoint"] = endpoint or DEFAULT_CONFIG["endpoint"]
    for key in ("workflow_path", "prompt_node_id", "negative_prompt_node_id", "seed_node_id"):
        if key in updates:
            config[key] = str(updates.get(key) or "").strip()
    write_sensitive_json(CONFIG_FILE, config)
    return config


def public_status(check_service: bool = False) -> dict[str, Any]:
    config = load_config()
    workflow = Path(str(config.get("workflow_path") or ""))
    configured = bool(workflow.is_file() and str(config.get("prompt_node_id") or ""))
    status = {
        "enabled": bool(config["enabled"] and config["backend"] == "comfyui"),
        "backend": config["backend"],
        "endpoint": config["endpoint"],
        "workflow_configured": configured,
        "service_reachable": False,
        "message": "内置心情卡片正在使用。",
    }
    if config["backend"] == "comfyui":
        status["message"] = "ComfyUI 已配置，等待启用。" if configured else "请填写 API workflow 文件路径和正向提示词节点 ID。"
        if check_service and configured:
            try:
                with request.urlopen(f"{config['endpoint']}/system_stats", timeout=2) as response:
                    status["service_reachable"] = 200 <= response.status < 300
            except Exception:
                status["service_reachable"] = False
            status["message"] = "ComfyUI 本机服务可用。" if status["service_reachable"] else "未连接到本机 ComfyUI；生成时会回退到心情卡片。"
    return status


def _set_node_text(workflow: dict[str, Any], node_id: str, text: str) -> None:
    if not node_id:
        return
    node = workflow.get(str(node_id))
    if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
        raise ValueError(f"ComfyUI workflow 中没有可写入的节点：{node_id}")
    node["inputs"]["text"] = text


def _set_node_seed(workflow: dict[str, Any], node_id: str, seed: str) -> None:
    if not node_id:
        return
    node = workflow.get(str(node_id))
    if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
        raise ValueError(f"ComfyUI workflow 中没有可写入的种子节点：{node_id}")
    try:
        value = int(str(seed), 16) if any(ch in str(seed).lower() for ch in "abcdef") else int(str(seed))
    except ValueError:
        value = int(uuid.uuid5(uuid.NAMESPACE_URL, str(seed)).int % (2**63 - 1))
    node["inputs"]["seed"] = value % (2**63 - 1)


def generate_comfyui_image(prompt: str, *, seed: str = "", negative_prompt: str = "") -> str:
    """Queue an exported ComfyUI API workflow and copy its first image locally."""
    config = load_config()
    status = public_status()
    if not status["enabled"] or not status["workflow_configured"]:
        raise RuntimeError("ComfyUI 未启用或配置不完整")
    workflow_path = Path(str(config["workflow_path"])).expanduser()
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"无法读取 ComfyUI API workflow：{exc}") from exc
    if not isinstance(workflow, dict):
        raise RuntimeError("ComfyUI workflow 必须是 API 格式 JSON 对象")
    workflow = copy.deepcopy(workflow)
    _set_node_text(workflow, str(config["prompt_node_id"]), prompt)
    _set_node_text(workflow, str(config.get("negative_prompt_node_id") or ""), negative_prompt)
    _set_node_seed(workflow, str(config.get("seed_node_id") or ""), seed)
    payload = json.dumps({"prompt": workflow, "client_id": str(uuid.uuid4())}).encode("utf-8")
    req = request.Request(f"{config['endpoint']}/prompt", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=10) as response:
            queued = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"无法提交到本机 ComfyUI：{exc}") from exc
    prompt_id = str(queued.get("prompt_id") or "")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI 没有返回任务 ID：{queued}")
    history: dict[str, Any] = {}
    for _ in range(90):
        try:
            with request.urlopen(f"{config['endpoint']}/history/{prompt_id}", timeout=5) as response:
                history = json.loads(response.read().decode("utf-8"))
        except Exception:
            history = {}
        result = history.get(prompt_id, {}) if isinstance(history, dict) else {}
        outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
        for node in outputs.values() if isinstance(outputs, dict) else []:
            images = node.get("images", []) if isinstance(node, dict) else []
            if images:
                image = images[0]
                filename = str(image.get("filename") or "")
                if not filename:
                    continue
                query = f"filename={parse.quote(filename)}&subfolder={parse.quote(str(image.get('subfolder') or ''))}&type={parse.quote(str(image.get('type') or 'output'))}"
                with request.urlopen(f"{config['endpoint']}/view?{query}", timeout=30) as response:
                    content = response.read()
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                suffix = Path(filename).suffix or ".png"
                output = OUTPUT_DIR / f"comfy-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{suffix}"
                output.write_bytes(content)
                return str(output)
        time.sleep(1)
    raise RuntimeError("等待 ComfyUI 生成超时（90 秒）")
