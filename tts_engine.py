"""
Edge-TTS 语音引擎模块
使用微软 Edge 浏览器在线语音合成服务
"""

import asyncio
import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

from _paths import module_root, data_dir, runtime_python_exe

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
TTS_CACHE_DIR = DATA_DIR / "tts_cache"

# 默认配置
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # 中文女声
DEFAULT_RATE = "+0%"  # 语速
DEFAULT_PITCH = "+0Hz"  # 音调
DEFAULT_VOLUME = "+0%"  # 音量

# 可用的中文语音列表
CHINESE_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 (女声)", "gender": "Female"},
    {"id": "zh-CN-YunxiNeural", "name": "云希 (男声)", "gender": "Male"},
    {"id": "zh-CN-YunjianNeural", "name": "云健 (男声)", "gender": "Male"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊 (女声)", "gender": "Female"},
    {"id": "zh-CN-YunyangNeural", "name": "云扬 (男声)", "gender": "Male"},
    {"id": "zh-CN-XiaochenNeural", "name": "晓辰 (女声)", "gender": "Female"},
    {"id": "zh-CN-XiaohanNeural", "name": "晓涵 (女声)", "gender": "Female"},
    {"id": "zh-CN-XiaomengNeural", "name": "晓梦 (女声)", "gender": "Female"},
    {"id": "zh-CN-XiaoqiuNeural", "name": "晓秋 (女声)", "gender": "Female"},
    {"id": "zh-CN-XiaorouNeural", "name": "晓柔 (女声)", "gender": "Female"},
]


def ensure_cache_dir() -> None:
    """确保缓存目录存在"""
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    """生成缓存键"""
    content = f"{text}|{voice}|{rate}|{pitch}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def get_cached_audio(text: str, voice: str, rate: str, pitch: str) -> Optional[Path]:
    """获取缓存的音频文件"""
    ensure_cache_dir()
    cache_key = get_cache_key(text, voice, rate, pitch)
    cache_file = TTS_CACHE_DIR / f"{cache_key}.mp3"
    if cache_file.exists():
        return cache_file
    return None


def is_available() -> bool:
    """检查 Edge-TTS 是否可用（动态检测，支持运行时安装）"""
    global _HAS_EDGE_TTS, edge_tts
    if _HAS_EDGE_TTS:
        return True
    # edge_tts was not available at import time — check again in case it was installed since
    try:
        import importlib
        importlib.invalidate_caches()
        import edge_tts as _et
        edge_tts = _et
        _HAS_EDGE_TTS = True
        return True
    except ImportError:
        return False


def runtime_status() -> tuple[bool, str]:
    """Check Edge-TTS in the app runtime without importing desktop UI modules."""
    if is_available():
        return True, "Edge-TTS 已安装"

    code = """
import importlib
try:
    mod = importlib.import_module("edge_tts")
    version = getattr(mod, "__version__", "")
    print(version or "installed")
except Exception as exc:
    raise SystemExit(str(exc))
"""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [runtime_python_exe(create=False), "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creationflags,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, f"Edge-TTS {version}" if version and version != "installed" else "Edge-TTS 已安装"
        return False, "未安装"
    except RuntimeError:
        return False, "未安装"
    except Exception as exc:
        return False, f"检测失败：{exc}"


def get_available_voices() -> list[dict]:
    """获取可用语音列表"""
    return CHINESE_VOICES


def get_tts_config() -> dict:
    """获取 TTS 配置"""
    config_file = DATA_DIR / "tts_config.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "enabled": False,
        "voice": DEFAULT_VOICE,
        "rate": DEFAULT_RATE,
        "pitch": DEFAULT_PITCH,
        "volume": DEFAULT_VOLUME,
        "auto_play": False,
    }


def save_tts_config(config: dict) -> None:
    """保存 TTS 配置"""
    config_file = DATA_DIR / "tts_config.json"
    config_file.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


async def _synthesize_async(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
    volume: str = DEFAULT_VOLUME,
    output_path: Optional[Path] = None,
) -> Path:
    """异步合成语音"""
    if not is_available():
        raise ImportError("edge-tts 未安装，请运行: pip install edge-tts")

    ensure_cache_dir()

    if output_path is None:
        cache_key = get_cache_key(text, voice, rate, pitch)
        output_path = TTS_CACHE_DIR / f"{cache_key}.mp3"

    # 如果缓存已存在，直接返回
    if output_path.exists():
        return output_path

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        volume=volume,
    )

    await communicate.save(str(output_path))
    return output_path


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
    volume: str = DEFAULT_VOLUME,
    use_cache: bool = True,
) -> Path:
    """
    同步合成语音
    
    Args:
        text: 要合成的文本
        voice: 语音ID
        rate: 语速 (如 "+0%", "-10%", "+20%")
        pitch: 音调 (如 "+0Hz", "+50Hz", "-50Hz")
        volume: 音量 (如 "+0%", "+10%", "-10%")
        use_cache: 是否使用缓存
    
    Returns:
        音频文件路径
    """
    # 检查缓存
    if use_cache:
        cached = get_cached_audio(text, voice, rate, pitch)
        if cached:
            return cached

    # 在新线程中运行异步代码
    result = {}
    error = {}

    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result["path"] = loop.run_until_complete(
                    _synthesize_async(text, voice, rate, pitch, volume)
                )
            finally:
                loop.close()
        except Exception as e:
            error["exc"] = e

    thread = threading.Thread(target=run_async)
    thread.start()
    thread.join()

    if error:
        raise error["exc"]

    return result["path"]


def clear_cache() -> int:
    """清空缓存，返回删除的文件数"""
    ensure_cache_dir()
    count = 0
    for file in TTS_CACHE_DIR.glob("*.mp3"):
        file.unlink()
        count += 1
    return count


def get_cache_size() -> tuple[int, int]:
    """获取缓存大小 (文件数, 字节数)"""
    ensure_cache_dir()
    count = 0
    size = 0
    for file in TTS_CACHE_DIR.glob("*.mp3"):
        count += 1
        size += file.stat().st_size
    return count, size
