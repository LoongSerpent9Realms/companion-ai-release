from __future__ import annotations

import argparse
import builtins
from datetime import datetime
import json
import math
import os
import random
import shutil
import subprocess
import sys

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
import webbrowser
from pathlib import Path

try:
    import ctypes
    _HAS_CTYPES = True
except ImportError:
    _HAS_CTYPES = False


import _paths as path_helpers
from _paths import (
    module_root,
    data_dir,
    python_exe,
    runtime_venv_dir,
    PYTHON_DOWNLOAD_URL,
)

runtime_python_exe = getattr(path_helpers, "runtime_python_exe", lambda root=None, create=True: python_exe())
runtime_subprocess_env = getattr(path_helpers, "runtime_subprocess_env", lambda python=None: None)
external_site_packages = getattr(path_helpers, "external_site_packages", lambda: [])
ensure_external_site_packages = getattr(path_helpers, "ensure_external_site_packages", lambda: None)
ensure_external_site_packages()

from routine_tracker import install_shutdown_handlers, pop_due_reminder, record_app_start, record_app_stop, routine_tick, is_autostart_enabled, set_autostart_enabled


def _safe_print(*args, **kwargs) -> None:
    try:
        builtins.print(*args, **kwargs)
    except OSError:
        pass


print = _safe_print


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
AVATAR_FILE = DATA_DIR / "avatar.json"
LIVE2D_STATE_FILE = DATA_DIR / "live2d.json"
MODEL3D_STATE_FILE = DATA_DIR / "3d_models.json"
SCALE_FILE = DATA_DIR / "pet_scale.json"
PET_DISPLAY_FILE = DATA_DIR / "pet_display.json"
TOPMOST_FILE = DATA_DIR / "pet_topmost.json"
PET_TALK_FILE = DATA_DIR / "runtime" / "pet_talk.json"
REALTIME_CHAT_FILE = DATA_DIR / "runtime" / "realtime_chat.json"
WEB_URL = "http://127.0.0.1:59137"
PET_STYLE_AUTO = "auto"
PET_STYLE_CLASSIC = "classic"
PET_STYLE_LIVE2D = "live2d"
PET_STYLE_3D = "3d"
PET_STYLES = {PET_STYLE_AUTO, PET_STYLE_CLASSIC, PET_STYLE_LIVE2D, PET_STYLE_3D}
PET_STYLE_LABELS = {
    PET_STYLE_AUTO: "默认桌宠",
    PET_STYLE_CLASSIC: "手绘桌宠",
    PET_STYLE_LIVE2D: "Live2D 桌宠",
    PET_STYLE_3D: "3D 桌宠",
}

PET_STATES = {
    "idle": ("\u5f85\u673a", "idle", "#657184"),
    "curious": ("\u597d\u5947", "thinking", "#276ef1"),
    "listening": ("\u503e\u542c", "read", "#0b7a55"),
    "thinking": ("\u601d\u8003", "thinking", "#8a5cf6"),
    "happy": ("\u5f00\u5fc3", "happy", "#f08a24"),
    "busy": ("\u5fd9\u788c", "scan", "#b66b00"),
}

PET_IDLE_LINES = [
    "\u6211\u5728\u8fd9\u91cc\uff0c\u968f\u65f6\u53ef\u4ee5\u627e\u6211\u3002",
    "\u8981\u4e0d\u8981\u4f11\u606f\u4e00\u4e0b\u773c\u775b\uff1f",
    "\u6211\u521a\u624d\u60f3\u5230\uff1a\u4eca\u5929\u4e5f\u53ef\u4ee5\u6162\u6162\u6765\u3002",
    "\u5982\u679c\u6709\u4e8b\u60f3\u8bb0\u4e0b\u6765\uff0c\u53ef\u4ee5\u544a\u8bc9\u6211\u3002",
    "\u6211\u6b63\u5728\u5f85\u673a\uff0c\u4f46\u6ca1\u6709\u5077\u61d2\u3002",
    "\u70b9\u6211\u6216\u8005\u628a\u9f20\u6807\u653e\u4e0a\u6765\uff0c\u6211\u5c31\u4f1a\u542c\u4f60\u8bf4\u3002",
]

PET_TALK_STARTERS = [
    "有人在吗？我们一起陪着用户吧。",
    "我刚醒，今天也要好好守在桌面上。",
    "你那边看到什么有趣的事了吗？",
    "我们轮流提醒用户休息一下眼睛吧。",
]

PET_TALK_FALLBACK_REPLIES = [
    "收到，我也在旁边看着呢。",
    "好呀，我们一起安静陪着。",
    "我听见啦，保持联系。",
    "嗯嗯，我这边状态也不错。",
]

IDLE_SPEECH_MIN_SECONDS = 18
IDLE_SPEECH_MAX_SECONDS = 38
AUTO_PET_TALK_MIN_SECONDS = 45
AUTO_PET_TALK_MAX_SECONDS = 110

BASE_W = 180
BASE_H = 220
TRANSPARENT_COLOR = "#ff00ff"


def _hex_color_to_colorref(color: str) -> int:
    color = color.lstrip("#")
    if len(color) != 6:
        return 0
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return red | (green << 8) | (blue << 16)


def _apply_window_colorkey(hwnd: int) -> bool:
    if not _HAS_CTYPES or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        GWL_EXSTYLE = -20
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_EX_LAYERED = 0x00080000
        LWA_COLORKEY = 0x00000001
        # Restore system menu and minimize box so taskbar right-click works
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_SYSMENU | WS_MINIMIZEBOX)
        # Apply layered transparency
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(
            hwnd,
            _hex_color_to_colorref(TRANSPARENT_COLOR),
            255,
            LWA_COLORKEY,
        )
        return True
    except Exception:
        return False


def _set_form_backcolor_transparent(form) -> bool:
    """Make the pywebview host form transparent via WinForms TransparencyKey.

    The web page paints pure magenta (#ff00ff) where it wants to be transparent,
    and WinForms chroma-keys that exact color at the window-composition level.
    This keeps WebView2 content visible while making the magenta areas transparent.

    NOTE: Do NOT use AllowTransparency + BackColor = Transparent - that makes
    the ENTIRE form (including WebView2) invisible.
    """
    if form is None:
        return False
    try:
        import clr  # noqa: F401
        from System.Drawing import Color  # type: ignore
    except Exception:
        return False

    try:
        form.TransparencyKey = Color.Magenta
        form.BackColor = Color.Magenta
        return True
    except Exception:
        return False


def _apply_pywebview_transparency(window, delay: float = 0.05) -> None:
    """Make pywebview's host window transparent via chroma-key (#ff00ff).

    Two mechanisms work together:
      1. WinForms: TransparencyKey + BackColor = Magenta (pythonnet), so the
         host form chroma-keys the magenta color at the composition level.
      2. Win32: WS_EX_LAYERED + LWA_COLORKEY on the form HWND as a fallback
         if pythonnet isn't usable.

    The web page (viewer_3d.html / live2d_viewer.html) must paint #ff00ff
    where it wants to be transparent.

    Retries multiple times because WebView2 can recreate the native handle
    after initial load, and the first attempt may fail silently.
    """
    if not _HAS_CTYPES:
        return

    def _try_apply_once() -> bool:
        """Attempt one round of transparency setup. Returns True on success."""
        native = getattr(window, "native", None)
        if native is None:
            return False
        ok = False
        try:
            handle = getattr(native, "Handle", None)
            hwnd = int(
                handle.ToInt64() if hasattr(handle, "ToInt64") else handle.ToInt32()
            )
            if _set_form_backcolor_transparent(native):
                ok = True
            if _apply_window_colorkey(hwnd):
                ok = True
        except Exception:
            pass
        return ok

    def _worker() -> None:
        # Phase 1: poll for native handle (up to ~10s)
        for _ in range(200):
            if _try_apply_once():
                break
            time.sleep(delay)

        # Phase 2: periodic re-application for ~30s to catch handle recreation
        for _ in range(60):
            time.sleep(0.5)
            _try_apply_once()

    threading.Thread(target=_worker, daemon=True).start()


def _check_ocr_status() -> tuple[bool, str]:
    """Return (installed, detail_text) for OCR."""
    try:
        # Check portable RapidOCR first: this is the OCR component managed by settings.
        rapidocr_dir = DATA_DIR / "ocr" / "rapidocr"
        if (rapidocr_dir / ".venv").exists():
            return True, "RapidOCR (portable)"

        # Check Tesseract
        import shutil
        tesseract = shutil.which("tesseract")
        if tesseract:
            return True, f"Tesseract: {tesseract}"
        
        # Check RapidOCR
        try:
            from rapidocr_onnxruntime import RapidOCR
            return True, "RapidOCR (onnxruntime)"
        except ImportError:
            pass

        return False, "未安装"
    except Exception as exc:
        return False, f"检测失败：{exc}"


def _check_external_module_status(module: str, label: str, version_attr: str = "__version__") -> tuple[bool, str]:
    """Check an optional pip component in the dedicated runtime venv."""
    code = f"""
import importlib
try:
    mod = importlib.import_module({module!r})
    version = getattr(mod, {version_attr!r}, "")
    print(version or "installed")
except Exception as exc:
    raise SystemExit(str(exc))
"""
    try:
        result = subprocess.run(
            [runtime_python_exe(create=False), "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
            env=runtime_subprocess_env(runtime_python_exe(create=False)),
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, f"{label} {version}" if version and version != "installed" else f"{label} 已安装"
        return False, "未安装"
    except RuntimeError:
        return False, "未安装"
    except Exception as exc:
        return False, f"检测失败：{exc}"


def _check_opencv_status() -> tuple[bool, str]:
    return _check_external_module_status("cv2", "OpenCV")


def _check_tts_status() -> tuple[bool, str]:
    ok, detail = _check_external_module_status("edge_tts", "Edge-TTS")
    if ok and detail == "Edge-TTS installed":
        return True, "Edge-TTS 已安装"
    return ok, detail


def _short_pip_error(text: str, limit: int = 220) -> str:
    """Extract the useful part of pip output for small status labels."""
    cleaned = (text or "").strip()
    if not cleaned:
        return "安装失败"
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    for prefix in ("ERROR:", "Exception:", "Traceback"):
        for line in lines:
            if line.startswith(prefix):
                return line[:limit]
    return lines[-1][:limit] if lines else cleaned[:limit]


def _check_datasets_status() -> tuple[bool, str]:
    """检查数据集工具（modelscope + datasets）状态。"""
    try:
        from dependency_utils import check_dataset_dependencies

        status = check_dataset_dependencies()
        return status.ok, status.detail if status.ok else status.detail.replace("缺少依赖：", "")
    except Exception as exc:
        return False, f"检测失败：{exc}"


def _check_torch_status() -> tuple[bool, str]:
    """Return (installed, detail_text) for PyTorch."""
    if os.name == "nt":
        try:
            _uninstall_rocm_device_packages(runtime_python_exe(create=False))
        except Exception:
            pass

    code = """
import json
import sys
try:
    import torch
    directml_available = False
    directml_error = ""
    rocm_available = False
    try:
        import torch_directml
        torch_directml.device()
        directml_available = True
    except Exception as exc:
        directml_error = str(exc)

    # 检测ROCm (AMD GPU)
    try:
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            if 'AMD' in device_name or 'Radeon' in device_name:
                rocm_available = True
    except Exception:
        pass

    # 确定设备类型
    if torch.cuda.is_available():
        if rocm_available:
            device = "rocm"
        else:
            device = "cuda"
    elif directml_available:
        device = "directml"
    else:
        device = "cpu"

    print(json.dumps({
        "available": True,
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "rocm_available": rocm_available,
        "directml_available": directml_available,
        "directml_error": directml_error,
        "device": device,
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
        "python_exe": sys.executable,
    }))
except Exception as exc:
    import traceback
    tb = traceback.format_exc()
    try:
        from importlib import metadata
        package_version = metadata.version("torch")
    except Exception:
        package_version = ""
    print(json.dumps({
        "available": False,
        "package_version": package_version,
        "error": str(exc),
        "traceback": tb,
        "python_exe": sys.executable
    }))
"""
    try:
        py = runtime_python_exe(create=False)
        result = subprocess.run(
            [py, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
            env=runtime_subprocess_env(py),
        )
        if result.returncode != 0:
            error_detail = (result.stderr or result.stdout or "PyTorch not installed").strip()
            # 写入诊断日志
            try:
                log_file = DATA_DIR / "logs" / f"torch_check_{datetime.now().strftime('%Y%m%d')}.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] PyTorch check failed\n")
                    f.write(f"Python: {py}\n")
                    f.write(f"Return code: {result.returncode}\n")
                    f.write(f"Stdout: {result.stdout}\n")
                    f.write(f"Stderr: {result.stderr}\n")
            except Exception:
                pass
            return False, error_detail
        info = json.loads(result.stdout)
        if info.get("available"):
            parts = [f"PyTorch {info.get('torch_version', '?')}"]
            dev = info.get("device", "cpu")
            parts.append(f"device={dev}")
            if info.get("cuda_device"):
                parts.append(f"GPU={info['cuda_device']}")
            return True, ", ".join(parts)
        if info.get("package_version"):
            # 写入详细错误日志
            try:
                log_file = DATA_DIR / "logs" / f"torch_check_{datetime.now().strftime('%Y%m%d')}.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] PyTorch installed but import failed\n")
                    f.write(f"Python: {info.get('python_exe', 'unknown')}\n")
                    f.write(f"Version: {info.get('package_version')}\n")
                    f.write(f"Error: {info.get('error')}\n")
                    f.write(f"Traceback:\n{info.get('traceback', 'N/A')}\n")
            except Exception:
                pass
            return False, f"PyTorch {info.get('package_version')} 已安装但不可用：{info.get('error', '导入失败')}"
        return False, "PyTorch not installed"
    except RuntimeError:
        return False, "PyTorch not installed"
    except Exception as exc:
        return False, f"check failed: {exc}"


ZLUDA_DIR = DATA_DIR / "zluda"
ZLUDA_RELEASE = "v6"
ZLUDA_WIN_URL = f"https://github.com/vosen/ZLUDA/releases/download/{ZLUDA_RELEASE}/zluda-windows-3fe1206.zip"


def _zluda_dll_dir() -> Path | None:
    """Return the directory that contains ZLUDA DLLs after extraction."""
    direct = ZLUDA_DIR / "nvcuda.dll"
    if direct.exists():
        return ZLUDA_DIR
    for dll in ZLUDA_DIR.rglob("nvcuda.dll"):
        return dll.parent
    return None


def _check_zluda_status() -> tuple[bool, str]:
    """Return (installed, detail_text) for ZLUDA."""
    dll_dir = _zluda_dll_dir()
    has_dll = dll_dir is not None

    code = """
import json
try:
    import torch
    cuda = bool(torch.cuda.is_available())
    name = torch.cuda.get_device_name(0) if cuda else ""
    version = getattr(torch, "__version__", "unknown")
    backend = "cuda" if cuda else "cpu"
    if cuda and ("AMD" in name or "Radeon" in name):
        backend = "rocm"
    print(json.dumps({"installed": True, "version": version, "cuda": cuda, "name": name, "backend": backend}))
except Exception as exc:
    try:
        from importlib import metadata
        version = metadata.version("torch")
    except Exception:
        version = ""
    print(json.dumps({"installed": False, "version": version, "backend": "broken" if version else "none", "error": str(exc)}))
"""
    try:
        result = subprocess.run(
            [runtime_python_exe(create=False), "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
            env=runtime_subprocess_env(runtime_python_exe(create=False)),
        )
        info = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {"installed": False}
    except Exception as exc:
        info = {"installed": False, "error": str(exc)}

    torch_installed = bool(info.get("installed"))
    backend = info.get("backend", "cpu")
    version = info.get("version", "unknown")
    name = info.get("name", "")

    if has_dll:
        if not torch_installed:
            if version and backend == "broken":
                return True, f"ZLUDA 已安装 (PyTorch {version} 已安装但不可用：{info.get('error', '导入失败')})"
            return True, "ZLUDA 已安装 (PyTorch 未安装)"
        if backend == "rocm":
            return True, f"ZLUDA 已安装；当前 PyTorch 使用 ROCm: {name}"
        if backend == "cuda":
            return True, f"ZLUDA 已安装；当前 PyTorch CUDA 设备: {name}"
        return True, f"ZLUDA 已安装 (当前 PyTorch {version} 为 CPU/无 GPU 后端)"

    if torch_installed:
        if backend == "rocm":
            return False, f"当前 PyTorch 使用 ROCm ({name})，通常不需要 ZLUDA"
        if backend == "cuda":
            return False, f"CUDA 可用 ({name})，ZLUDA 未安装"
        if "cpu" in str(version).lower():
            return False, f"PyTorch 为 CPU 版本 ({version})，需安装 GPU 版才能使用 ZLUDA"
        return False, f"PyTorch {version}，无 CUDA/ROCm 支持"

    if info.get("error"):
        return False, f"PyTorch 未安装或不可用：{info.get('error')}"
    return False, "PyTorch 未安装"


def _get_component_size(component: str) -> str:
    """获取组件占用空间。"""
    def dir_size(path: Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    def format_size(total: int) -> str:
        if total <= 0:
            return "0 MB"
        mb = total / 1024 / 1024
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        if mb >= 100:
            return f"{mb:.0f} MB"
        return f"{mb:.1f} MB"

    def pip_packages_size(names: list[str]) -> str:
        total = 0
        seen: set[Path] = set()
        normalized = {name.lower().replace("-", "_") for name in names}
        for site_dir in _site_package_dirs():
            if not site_dir.exists():
                continue
            for child in site_dir.iterdir():
                child_name = child.name.lower()
                stem = child_name
                for suffix in (".dist-info", ".egg-info"):
                    if stem.endswith(suffix):
                        stem = stem[: -len(suffix)]
                stem = stem.replace("-", "_")
                if stem in normalized or any(stem.startswith(name + ".") for name in normalized):
                    resolved = child.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    total += dir_size(child)
        return format_size(total) if total else "未知"

    try:
        if component == "ocr":
            ocr_dir = DATA_DIR / "ocr"
            if not ocr_dir.exists():
                return "0 MB"
            return format_size(dir_size(ocr_dir))
        
        elif component == "torch":
            # PyTorch is installed in Python site-packages
            try:
                code = """
import json
from pathlib import Path
try:
    import torch
    print(json.dumps({"path": str(Path(torch.__file__).parent)}))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
"""
                result = subprocess.run(
                    [runtime_python_exe(create=False), "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=CREATE_NO_WINDOW,
                )
                if result.returncode != 0:
                    return "未知"
                info = json.loads(result.stdout)
                if not info.get("path"):
                    return "未知"
                torch_dir = Path(info["path"])
                total = dir_size(torch_dir)
                return format_size(total)
            except Exception:
                return "未知"
        
        elif component == "zluda":
            if not ZLUDA_DIR.exists():
                return "0 MB"
            return format_size(dir_size(ZLUDA_DIR))

        elif component == "opencv":
            return pip_packages_size(["cv2", "opencv_python", "opencv_contrib_python", "opencv_python_headless"])

        elif component in {"tts", "edge-tts", "edge_tts"}:
            return pip_packages_size(["edge_tts"])

        elif component == "datasets":
            return pip_packages_size([
                "datasets",
                "modelscope",
                "huggingface_hub",
                "pyarrow",
                "pandas",
                "numpy",
                "tqdm",
                "requests",
            ])

        elif component == "python":
            venv_dir = runtime_venv_dir(ROOT)
            return format_size(dir_size(venv_dir)) if venv_dir.exists() else "0 MB"
        
        return "未知"
    except Exception:
        return "未知"


def _site_package_dirs() -> list[Path]:
    try:
        return external_site_packages()
    except Exception:
        pass
    return []


def _installed_python_packages(packages: list[str]) -> list[str]:
    remaining: list[str] = []
    try:
        py = runtime_python_exe(create=False)
    except RuntimeError:
        return []
    for package in packages:
        result = subprocess.run(
            [py, "-m", "pip", "show", package],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            remaining.append(package)
    return remaining


def _remove_torch_leftovers(packages: list[str]) -> list[str]:
    removed: list[str] = []
    names = set(packages)
    normalized_names = {name.lower().replace("-", "_") for name in names}
    if normalized_names & {"torch", "torchvision", "torchaudio", "torch_directml"}:
        names.update({
            "functorch",
            "torchgen",
            "torch_directml",
            "torchvision.libs",
            "torchaudio.libs",
        })
    names.update(_rocm_leftover_names())
    remove_nvidia = bool(normalized_names & {"torch", "torchvision", "torchaudio"})
    remove_rocm = bool(normalized_names & {"torch", "torchvision", "torchaudio", "torch_directml"}) or any(
        name.startswith(("amd_torch_device_", "amd_torchvision_device_", "rocm_sdk_", "_rocm_sdk"))
        for name in normalized_names
    )
    rocm_prefixes = _rocm_leftover_prefixes()
    nvidia_subdirs = _nvidia_leftover_subdirs()
    for site_dir in _site_package_dirs():
        if remove_nvidia:
            nvidia_dir = site_dir / "nvidia"
            if nvidia_dir.exists():
                for subdir_name in sorted(nvidia_subdirs):
                    subdir = nvidia_dir / subdir_name
                    if subdir.exists():
                        try:
                            shutil.rmtree(subdir, ignore_errors=True)
                            removed.append(str(Path("nvidia") / subdir_name))
                        except Exception:
                            pass
                try:
                    if nvidia_dir.exists() and not any(nvidia_dir.iterdir()):
                        nvidia_dir.rmdir()
                        removed.append("nvidia")
                except Exception:
                    pass
        for name in sorted(names):
            candidates = [
                site_dir / name,
                site_dir / name.replace("-", "_"),
                site_dir / (name.replace("-", "_") + ".py"),
            ]
            for candidate in candidates:
                if not candidate.exists():
                    continue
                try:
                    if candidate.is_dir():
                        shutil.rmtree(candidate, ignore_errors=True)
                    else:
                        candidate.unlink(missing_ok=True)
                    removed.append(candidate.name)
                except Exception:
                    pass
            patterns = {
                f"{name}-*.dist-info",
                f"{name.replace('-', '_')}-*.dist-info",
                f"{name}-*.egg-info",
                f"{name.replace('-', '_')}-*.egg-info",
            }
            for pattern in patterns:
                for metadata_dir in site_dir.glob(pattern):
                    try:
                        shutil.rmtree(metadata_dir, ignore_errors=True)
                        removed.append(metadata_dir.name)
                    except Exception:
                        pass
        if not remove_rocm:
            continue
        removed.extend(_remove_rocm_leftovers_from_site_dir(site_dir, rocm_prefixes))
    return sorted(set(removed))


def _rocm_leftover_names() -> set[str]:
    return {
        "_rocm_sdk_core",
        "_rocm_sdk_libraries",
        "rocm_sdk_core",
        "rocm_sdk_libraries",
    }


def _rocm_leftover_prefixes() -> tuple[str, ...]:
    return (
        "amd_torch_device_",
        "amd_torchvision_device_",
        "rocm_sdk_",
        "_rocm_sdk",
    )


def _nvidia_leftover_subdirs() -> set[str]:
    return {
        "cublas",
        "cuda_cupti",
        "cuda_nvrtc",
        "cuda_runtime",
        "cudnn",
        "cufft",
        "curand",
        "cusolver",
        "cusparse",
        "nccl",
        "nvjitlink",
        "nvtx",
    }


def _remove_rocm_leftovers_from_site_dir(site_dir: Path, prefixes: tuple[str, ...]) -> list[str]:
    removed: list[str] = []
    if not site_dir.exists():
        return removed
    for candidate in site_dir.iterdir():
        candidate_name = candidate.name.lower().replace("-", "_")
        if candidate_name in _rocm_leftover_names() or candidate_name.startswith(prefixes):
            try:
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                else:
                    candidate.unlink(missing_ok=True)
                removed.append(candidate.name)
            except Exception:
                pass
    return removed


def _remove_rocm_leftovers() -> list[str]:
    removed: list[str] = []
    rocm_prefixes = (
        "amd_torch_device_",
        "amd_torchvision_device_",
        "rocm_sdk_",
        "_rocm_sdk",
    )
    for site_dir in _site_package_dirs():
        removed.extend(_remove_rocm_leftovers_from_site_dir(site_dir, rocm_prefixes))
    return sorted(set(removed))


def _uninstall_rocm_device_packages(python: str | None = None) -> None:
    """Remove stale ROCm device wheels before installing a new nightly set."""
    python = python or runtime_python_exe()
    code = (
        "from importlib import metadata;"
        "prefixes=('amd-torch-device-','amd-torchvision-device-','rocm-sdk-','rocm-sdk-device-');"
        "print('\\n'.join(d.metadata['Name'] for d in metadata.distributions() "
        "if any(d.metadata['Name'].lower().startswith(p) for p in prefixes)))"
    )
    proc = subprocess.run(
        [python, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if names:
        subprocess.run(
            [python, "-m", "pip", "uninstall", "-y", *names],
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=CREATE_NO_WINDOW,
        )
    _remove_rocm_leftovers()


def _shortcut_cleanup_dirs() -> list[Path]:
    dirs: list[Path] = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("ProgramData")
    userprofile = os.environ.get("USERPROFILE")
    public = os.environ.get("PUBLIC")
    if userprofile:
        dirs.append(Path(userprofile) / "Desktop")
    if public:
        dirs.append(Path(public) / "Desktop")
    if appdata:
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Companion AI")
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AI陪伴桌宠")
    if programdata:
        dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Companion AI")
        dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AI陪伴桌宠")
    return dirs


def _cleanup_companion_shortcuts() -> list[str]:
    removed: list[str] = []
    shortcut_names = {
        "AI陪伴桌宠 - 桌宠.lnk",
        "AI陪伴桌宠.lnk",
        "Companion AI.lnk",
        "Companion Pet.lnk",
        "Stop Companion AI.lnk",
        "Uninstall Companion AI.lnk",
        "停止 Companion AI.lnk",
        "卸载 Companion AI.lnk",
        "Live2D 查看器.url",
    }
    for directory in _shortcut_cleanup_dirs():
        if not directory.exists():
            continue
        if directory.name in {"Companion AI", "AI陪伴桌宠"}:
            try:
                shutil.rmtree(directory, ignore_errors=True)
                removed.append(str(directory))
            except Exception:
                pass
            continue
        for name in shortcut_names:
            path = directory / name
            if not path.exists():
                continue
            try:
                path.unlink(missing_ok=True)
                removed.append(str(path))
            except Exception:
                pass
    return removed


def _uninstall_component(component: str) -> dict:
    """卸载组件。"""
    try:
        if component in {"shortcuts", "shortcut", "desktop-shortcuts", "start-menu"}:
            removed = _cleanup_companion_shortcuts()
            if removed:
                return {"ok": True, "message": f"已删除快捷方式：{len(removed)} 项"}
            return {"ok": True, "message": "未发现需要删除的 Companion AI 快捷方式"}

        # Pip-managed components live in the dedicated runtime venv.
        if component in {"torch", "opencv", "tts", "edge-tts", "datasets"}:
            try:
                runtime_python_exe()
            except RuntimeError as exc:
                return {"ok": False, "error": str(exc)}

        if component == "ocr":
            ocr_dir = DATA_DIR / "ocr"
            if ocr_dir.exists():
                import shutil
                shutil.rmtree(ocr_dir, ignore_errors=True)
                return {"ok": True, "message": "OCR 已卸载"}
            return {"ok": False, "error": "OCR 未安装"}
        
        elif component == "torch":
            packages = [
                # 核心包
                "torch",
                "torchvision",
                "torchaudio",
                "torch-directml",
                "pytorch-triton",
                "triton",
                # NVIDIA CUDA相关
                "nvidia-cublas-cu11",
                "nvidia-cublas-cu12",
                "nvidia-cublas-cu12",
                "nvidia-cuda-cupti-cu11",
                "nvidia-cuda-cupti-cu12",
                "nvidia-cuda-nvrtc-cu11",
                "nvidia-cuda-nvrtc-cu12",
                "nvidia-cuda-runtime-cu11",
                "nvidia-cuda-runtime-cu12",
                "nvidia-cudnn-cu11",
                "nvidia-cudnn-cu12",
                "nvidia-cufft-cu11",
                "nvidia-cufft-cu12",
                "nvidia-curand-cu11",
                "nvidia-curand-cu12",
                "nvidia-cusolver-cu11",
                "nvidia-cusolver-cu12",
                "nvidia-cusparse-cu11",
                "nvidia-cusparse-cu12",
                "nvidia-nccl-cu11",
                "nvidia-nccl-cu12",
                "nvidia-nvjitlink-cu12",
                "nvidia-nvtx-cu11",
                "nvidia-nvtx-cu12",
                # AMD ROCm相关（新增）
                "rocm-composable-sdk",
                "rocm-core",
                "hipamd",
                "hip",
                "hsa-rocr",
                "hsakmt-roct",
                "rccl",
                "rccl-tests",
                "rdc",
                "rdc-libs",
                "rocm-clang-ocl",
                "rocm-cmake",
                "rocm-dbgapi",
                "rocm-debug-agent",
                "rocm-device-libs",
                "rocm-gcc",
                "rocm-gdb",
                "rocm-llvm",
                "rocm-ml-libraries",
                "rocm-mli-libraries",
                "rocm-opencl-runtime",
                "rocm-openmp-extras",
                "rocm-runtime",
                "rocm-smi",
                "rocm-smi-libs",
                "rocminfo",
                "rocprim",
                "hipblas",
                "hipfft",
                "hipify",
                "hipsolver",
                "hipsparse",
                "hiprng",
                "hipsparse",
                "rocfft",
                "rocsolver",
                "rocsparse",
                "rocm-bandwidth-test",
                "composable_perf_tool",
                "hipcub",
                "rocalution",
                "rocsolver",
                "rocrand",
                "rocThrust",
                "roctracer",
                "rocprofiler",
                "rocm-utils",
                "rocwmma",
                "llvm-amdgpu",
                "flang",
                "misa",
                "clang",
                "lld",
                "lldb",
                "polly",
                "llvm",
            ]
            py = runtime_python_exe()
            cmd = [py, "-m", "pip", "uninstall", *packages, "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)

            removed = _remove_torch_leftovers(packages)
            remaining = _installed_python_packages(packages)
            import_check = subprocess.run(
                [
                    py,
                    "-c",
                    "import importlib.util, sys; sys.exit(1 if importlib.util.find_spec('torch') else 0)",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
            if not remaining and import_check.returncode == 0:
                detail = "PyTorch 已卸载"
                if removed:
                    detail += f"（已清理残留：{', '.join(removed[:8])}"
                    if len(removed) > 8:
                        detail += f" 等 {len(removed)} 项"
                    detail += "）"
                return {"ok": True, "message": detail}

            error_parts = []
            if result.returncode != 0:
                error_parts.append((result.stderr or result.stdout or "pip uninstall failed").strip()[:500])
            if remaining:
                error_parts.append("仍检测到包：" + ", ".join(remaining))
            if import_check.returncode != 0:
                error_parts.append("torch 仍可被当前 Python 导入，可能有进程占用或残留路径。")
            return {"ok": False, "error": "\n".join(error_parts) or "卸载后复检失败"}
        
        elif component == "zluda":
            if ZLUDA_DIR.exists():
                import shutil
                shutil.rmtree(ZLUDA_DIR, ignore_errors=True)
                return {"ok": True, "message": "ZLUDA 已卸载"}
            return {"ok": False, "error": "ZLUDA 未安装"}

        elif component == "opencv":
            packages = ["opencv-python", "opencv-contrib-python", "opencv-python-headless"]
            cmd = [runtime_python_exe(), "-m", "pip", "uninstall", *packages, "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
            removed = _remove_torch_leftovers(["cv2", *packages])
            ok, _detail = _check_opencv_status()
            if not ok:
                detail = "OpenCV 已卸载"
                if removed:
                    detail += f"（已清理残留：{', '.join(removed[:6])}）"
                return {"ok": True, "message": detail}
            error = (result.stderr or result.stdout or "pip uninstall failed").strip()[:500]
            return {"ok": False, "error": error or "OpenCV 卸载后仍可导入"}

        elif component in {"tts", "edge-tts"}:
            packages = ["edge-tts"]
            cmd = [runtime_python_exe(), "-m", "pip", "uninstall", *packages, "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
            removed = _remove_torch_leftovers(["edge-tts", "edge_tts"])
            ok, _detail = _check_tts_status()
            if not ok:
                try:
                    import tts_engine
                    tts_engine._HAS_EDGE_TTS = False
                    tts_engine.edge_tts = None
                except Exception:
                    pass
                detail = "Edge-TTS 已卸载"
                if removed:
                    detail += f"（已清理残留：{', '.join(removed[:6])}）"
                return {"ok": True, "message": detail}
            error = (result.stderr or result.stdout or "pip uninstall failed").strip()[:500]
            return {"ok": False, "error": error or "Edge-TTS 卸载后仍可导入"}

        elif component == "datasets":
            from dependency_utils import DATASET_UNINSTALL_PACKAGES

            packages = DATASET_UNINSTALL_PACKAGES
            cmd = [runtime_python_exe(), "-m", "pip", "uninstall", *packages, "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
            ok, _detail = _check_datasets_status()
            if not ok:
                return {"ok": True, "message": "数据集工具已卸载"}
            error = (result.stderr or result.stdout or "pip uninstall failed").strip()[:500]
            return {"ok": False, "error": error or "卸载后仍可导入"}

        return {"ok": False, "error": f"未知组件：{component}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# AMD GPU 型号到 GFX 架构的映射表（基于ROCm官方文档）
# 参考: https://github.com/ROCm/TheRock/blob/main/RELEASES.md
_AMD_GPU_GFX_MAP = {
    # RX 9000 系列 (RDNA 4)
    "rx 9070 xt": "gfx1201",
    "rx 9070": "gfx1201",
    "rx 9060 xt": "gfx1200",
    "rx 9060": "gfx1200",
    # AI PRO / 专业卡
    "ai pro r9700": "gfx1201",
    "ai pro r9600": "gfx1200",
    # RX 7000 系列 (RDNA 3)
    "rx 7800 xt": "gfx1101",
    "rx 7700 xt": "gfx1101",
    "rx 7900 xtx": "gfx1100",
    "rx 7900 xt": "gfx1100",
    "rx 7600": "gfx1102",
    # RX 6000 系列 (RDNA 2)
    "rx 6900 xt": "gfx1030",
    "rx 6800 xt": "gfx1030",
    "rx 6750 xt": "gfx1031",
    "rx 6700 xt": "gfx1031",
    "rx 6600 xt": "gfx1032",
    "rx 6600": "gfx1032",
    "rx 6500 xt": "gfx1034",
    # RX 5000 系列 (RDNA 1)
    "rx 5700": "gfx1010",
    "rx 5700 xt": "gfx1010",
    # 更早的系列
    "radeon vii": "gfx906",
    "vega": "gfx906",
    "rx 580": "gfx803",
    "rx 570": "gfx803",
    "rx 480": "gfx803",
}


def _get_amd_gfx_target(gpu_name: str) -> str | None:
    """根据AMD GPU型号名称获取GFX架构目标。"""
    name_lower = gpu_name.lower()
    for model, gfx in _AMD_GPU_GFX_MAP.items():
        if model in name_lower:
            return gfx
    return None


def _detect_gpu() -> str:
    """Detect GPU brand on Windows via WMI or PowerShell. Returns 'AMD', 'Intel', 'NVIDIA', or 'unknown'."""
    # 方法1: 尝试使用wmic
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "Name"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        name = result.stdout.lower()
        if "amd" in name or "radeon" in name:
            return "AMD"
        if "intel" in name:
            return "Intel"
        if "nvidia" in name:
            return "NVIDIA"
    except Exception:
        pass
    
    # 方法2: 使用PowerShell作为备用
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-WmiObject Win32_VideoController | Select-Object Name"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        name = result.stdout.lower()
        if "amd" in name or "radeon" in name:
            return "AMD"
        if "intel" in name:
            return "Intel"
        if "nvidia" in name:
            return "NVIDIA"
    except Exception:
        pass
    
    return "unknown"


def _detect_gpu_detail() -> dict:
    """检测 GPU 详细信息并推荐 PyTorch 版本。"""
    gpu_brand = _detect_gpu()
    if os.name == "nt":
        try:
            _uninstall_rocm_device_packages(runtime_python_exe(create=False))
        except Exception:
            pass

    # 获取 GPU 型号（优先选择独立GPU）
    gpu_name = "未知"
    gpu_list = []
    
    # 方法1: 尝试使用wmic
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "Name"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and line.lower() != "name":
                gpu_list.append(line)
    except Exception:
        pass
    
    # 方法2: 如果wmic失败，使用PowerShell
    if not gpu_list:
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-WmiObject Win32_VideoController | Select-Object Name"],
                capture_output=True, text=True, timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line and line.lower() != "name" and not line.startswith("----"):
                    gpu_list.append(line)
        except Exception:
            pass
    
    # 优先选择独立GPU（AMD Radeon / NVIDIA），跳过虚拟显示器和集成显卡
    priority_keywords = ["radeon rx", "nvidia geforce", "nvidia rtx", "nvidia gtx", "amd radeon rx"]
    for gpu in gpu_list:
        gpu_lower = gpu.lower()
        # 跳过虚拟显示器
        if "virtual" in gpu_lower or "mumu" in gpu_lower or "dummy" in gpu_lower:
            continue
        # 优先选择RX系列显卡
        for keyword in priority_keywords:
            if keyword in gpu_lower:
                gpu_name = gpu
                break
        if gpu_name != "未知":
            break
    
    # 如果没找到优先显卡，选择第一个匹配品牌的真实GPU
    if gpu_name == "未知":
        for gpu in gpu_list:
            gpu_lower = gpu.lower()
            # 跳过虚拟显示器
            if "virtual" in gpu_lower or "mumu" in gpu_lower or "dummy" in gpu_lower:
                continue
            if gpu_brand == "AMD" and ("amd" in gpu_lower or "radeon" in gpu_lower):
                gpu_name = gpu
                break
            elif gpu_brand == "NVIDIA" and "nvidia" in gpu_lower:
                gpu_name = gpu
                break
            elif gpu_brand == "Intel" and "intel" in gpu_lower:
                gpu_name = gpu
                break
    
    # 最后，如果还是没找到，使用第一个非虚拟GPU
    if gpu_name == "未知" and gpu_list:
        for gpu in gpu_list:
            gpu_lower = gpu.lower()
            if "virtual" not in gpu_lower and "mumu" not in gpu_lower and "dummy" not in gpu_lower:
                gpu_name = gpu
                break

    # 检查当前 PyTorch 状态
    torch_version = "未安装"
    torch_cuda = False
    torch_backend = "none"
    try:
        code = """
import json
try:
    import torch
    cuda = bool(torch.cuda.is_available())
    name = torch.cuda.get_device_name(0) if cuda else ""
    backend = "cuda" if cuda else "cpu"
    if cuda and ("AMD" in name or "Radeon" in name):
        backend = "rocm"
    print(json.dumps({"version": torch.__version__, "cuda": cuda, "backend": backend}))
except Exception:
    try:
        from importlib import metadata
        version = metadata.version("torch")
        print(json.dumps({"version": version, "cuda": False, "backend": "broken"}))
    except Exception:
        print(json.dumps({"version": "未安装", "cuda": False, "backend": "none"}))
"""
        result = subprocess.run(
            [runtime_python_exe(create=False), "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
            env=runtime_subprocess_env(runtime_python_exe(create=False)),
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            torch_version = info.get("version", "未安装")
            torch_cuda = bool(info.get("cuda"))
            torch_backend = info.get("backend", "none")
    except Exception:
        pass

    # 获取AMD GPU的GFX架构
    gfx_target = None
    if gpu_brand == "AMD":
        gfx_target = _get_amd_gfx_target(gpu_name)

    # 推荐版本
    recommendation = {
        "gpu_brand": gpu_brand,
        "gpu_name": gpu_name,
        "torch_version": torch_version,
        "torch_cuda": torch_cuda,
        "torch_backend": torch_backend,
        "gfx_target": gfx_target,
        "recommended": "cpu",
        "install_command": "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu",
        "index_url": "",
        "reason": "",
    }

    if gpu_brand == "NVIDIA":
        recommendation["recommended"] = "cuda121"
        recommendation["install_command"] = "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121"
        recommendation["index_url"] = "https://download.pytorch.org/whl/cu121"
        recommendation["reason"] = f"检测到 NVIDIA GPU ({gpu_name})，推荐安装 CUDA 12.1 版本以获得最佳性能"
    elif gpu_brand == "AMD":
        if os.name == "nt":
            recommendation["recommended"] = "directml"
            recommendation["install_command"] = "pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu torch-directml --extra-index-url https://pypi.org/simple"
            recommendation["index_url"] = "https://download.pytorch.org/whl/cpu + PyPI(torch-directml)"
            recommendation["reason"] = f"检测到 AMD GPU ({gpu_name})，Windows 推荐安装 DirectML 版本"
        elif gfx_target:
            # 使用ROCm nightly multi-arch wheel（支持特定GFX架构）
            recommendation["recommended"] = "rocm-nightly"
            recommendation["gfx_target"] = gfx_target
            recommendation["install_command"] = f"pip install --upgrade --force-reinstall --pre \"torch[device-{gfx_target}]\" \"torchvision[device-{gfx_target}]\" --index-url https://rocm.nightlies.amd.com/whl-multi-arch/"
            recommendation["index_url"] = "https://rocm.nightlies.amd.com/whl-multi-arch/"
            recommendation["reason"] = f"检测到 AMD GPU ({gpu_name})，GFX架构: {gfx_target}，推荐安装 ROCm nightly 版本"
        else:
            # 未知GFX架构，使用通用ROCm
            recommendation["recommended"] = "rocm"
            recommendation["install_command"] = "pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/rocm6.2"
            recommendation["index_url"] = "https://download.pytorch.org/whl/rocm6.2"
            recommendation["reason"] = f"检测到 AMD GPU ({gpu_name})，无法识别GFX架构，使用通用ROCm 6.2版本"
    elif gpu_brand == "Intel":
        if os.name == "nt":
            recommendation["recommended"] = "directml"
            recommendation["install_command"] = "pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu torch-directml --extra-index-url https://pypi.org/simple"
            recommendation["index_url"] = "https://download.pytorch.org/whl/cpu + PyPI(torch-directml)"
            recommendation["reason"] = f"检测到 Intel GPU ({gpu_name})，Windows 推荐安装 DirectML 版本"
        else:
            recommendation["recommended"] = "cpu"
            recommendation["install_command"] = "pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu"
            recommendation["reason"] = f"检测到 Intel GPU ({gpu_name})，推荐 CPU 版本"
    else:
        recommendation["recommended"] = "cpu"
        recommendation["install_command"] = "pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu"
        recommendation["reason"] = "未检测到独立 GPU，推荐 CPU 版本"

    return recommendation


def _foreground_app_context() -> dict[str, str]:
    if not _HAS_CTYPES:
        return {"title": "", "process": "", "pid": ""}
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"title": "", "process": "", "pid": ""}

        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = _process_name_from_pid(pid.value)
        return {"title": buffer.value.strip(), "process": process, "pid": str(pid.value)}
    except Exception:
        return {"title": "", "process": "", "pid": ""}


def _process_name_from_pid(pid: int) -> str:
    if not pid:
        return ""
    try:
        result = subprocess.run(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=CREATE_NO_WINDOW,
        )
        line = result.stdout.strip().splitlines()[0]
        if line and line != "INFO: No tasks are running which match the specified criteria.":
            return line.split('","')[0].strip('"')
    except Exception:
        pass
    return ""


def _time_context() -> str:
    now = datetime.now()
    hour = now.hour
    if 5 <= hour < 11:
        part = "\u65e9\u4e0a"
    elif 11 <= hour < 14:
        part = "\u4e2d\u5348"
    elif 14 <= hour < 18:
        part = "\u4e0b\u5348"
    elif 18 <= hour < 23:
        part = "\u665a\u4e0a"
    else:
        part = "\u6df1\u591c"
    return f"{part} {now:%H:%M}"


_live2d_window = None
_active_pet_style = PET_STYLE_AUTO


def _pet_style_label(style: str) -> str:
    return PET_STYLE_LABELS.get(style, PET_STYLE_LABELS[PET_STYLE_AUTO])


def _load_pet_talk_bus() -> dict:
    try:
        data = json.loads(PET_TALK_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "companions": data.get("companions", []),
                "messages": data.get("messages", []),
            }
    except Exception:
        pass
    return {"companions": [], "messages": []}


def _save_pet_talk_bus(data: dict) -> None:
    try:
        PET_TALK_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = PET_TALK_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(PET_TALK_FILE)
    except Exception:
        pass


def _prune_pet_talk_bus(data: dict) -> dict:
    now = time.time()
    companions = [
        item for item in data.get("companions", [])
        if now - float(item.get("last_seen", 0) or 0) <= 45
    ]
    messages = [
        item for item in data.get("messages", [])[-80:]
        if now - float(item.get("created_at", 0) or 0) <= 180
    ]
    return {"companions": companions, "messages": messages}


def _write_pet_heartbeat(instance_id: str, name: str, style: str) -> None:
    data = _prune_pet_talk_bus(_load_pet_talk_bus())
    companions = [item for item in data.get("companions", []) if item.get("id") != instance_id]
    companions.append({
        "id": instance_id,
        "name": name,
        "style": style,
        "pid": os.getpid(),
        "last_seen": time.time(),
    })
    data["companions"] = companions
    _save_pet_talk_bus(data)


def _remove_pet_heartbeat(instance_id: str) -> None:
    data = _prune_pet_talk_bus(_load_pet_talk_bus())
    data["companions"] = [item for item in data.get("companions", []) if item.get("id") != instance_id]
    _save_pet_talk_bus(data)


def _append_pet_message(
    *,
    from_id: str,
    from_name: str,
    text: str,
    kind: str = "talk",
    reply_to: str = "",
) -> dict:
    data = _prune_pet_talk_bus(_load_pet_talk_bus())
    message = {
        "id": f"{from_id}-{int(time.time() * 1000)}-{random.randint(1000, 9999)}",
        "from_id": from_id,
        "from_name": from_name,
        "text": text.strip(),
        "kind": kind,
        "reply_to": reply_to,
        "created_at": time.time(),
    }
    if message["text"]:
        data.setdefault("messages", []).append(message)
        _save_pet_talk_bus(data)
    return message


class PetTalkAgent:
    def __init__(self, style: str, show_callback) -> None:
        self.style = style
        self.instance_id = f"{style}-{os.getpid()}-{int(time.time() * 1000)}"
        self.companion_name = f"{_pet_style_label(style)} {str(os.getpid())[-4:]}"
        self._seen_message_ids: set[str] = set()
        self._reply_busy = False
        self._running = False
        self._show_callback = show_callback

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name=f"pet-talk-{self.style}").start()

    def stop(self) -> None:
        self._running = False
        _remove_pet_heartbeat(self.instance_id)

    def start_conversation(self) -> None:
        if self.active_peer_count() <= 0:
            self._show_callback("现在只有我一个桌宠在线。")
            return
        text = random.choice(PET_TALK_STARTERS)
        message = _append_pet_message(
            from_id=self.instance_id,
            from_name=self.companion_name,
            text=text,
            kind="talk",
        )
        if message.get("id"):
            self._seen_message_ids.add(message["id"])
        self._show_callback(text)

    def active_peer_count(self) -> int:
        data = _prune_pet_talk_bus(_load_pet_talk_bus())
        return sum(1 for item in data.get("companions", []) if item.get("id") != self.instance_id)

    def _loop(self) -> None:
        while self._running:
            try:
                _write_pet_heartbeat(self.instance_id, self.companion_name, self.style)
                self.poll_once()
            except Exception:
                pass
            time.sleep(1.1)

    def poll_once(self) -> None:
        data = _prune_pet_talk_bus(_load_pet_talk_bus())
        for message in data.get("messages", []):
            msg_id = str(message.get("id", ""))
            if not msg_id or msg_id in self._seen_message_ids:
                continue
            self._seen_message_ids.add(msg_id)
            if message.get("from_id") == self.instance_id:
                continue
            self._receive(message)

    def _receive(self, message: dict) -> None:
        sender = str(message.get("from_name") or "另一个桌宠")
        text = str(message.get("text") or "").strip()
        if not text:
            return
        self._show_callback(f"{sender}：{text}")
        if message.get("kind") != "talk" or self._reply_busy:
            return
        self._reply_busy = True

        def _reply_later() -> None:
            time.sleep(random.uniform(0.7, 1.8))
            reply = self._make_reply(sender, text)
            _append_pet_message(
                from_id=self.instance_id,
                from_name=self.companion_name,
                text=reply,
                kind="reply",
                reply_to=str(message.get("id", "")),
            )
            self._show_callback(reply)
            self._reply_busy = False

        threading.Thread(target=_reply_later, daemon=True).start()

    def _make_reply(self, sender: str, text: str) -> str:
        prompt = (
            "你是一个桌面宠物，正在和另一个桌宠聊天。"
            "请用一句自然、可爱但不过分夸张的中文回复。"
            "只输出一句话，不要超过24个字。\n"
            f"对方名字：{sender}\n"
            f"对方说：{text}"
        )
        try:
            from hybrid_chat import get_hybrid_chatbot
            reply, _source = get_hybrid_chatbot().chat(prompt, [])
            reply = _clean_short_pet_text(reply)
        except Exception:
            reply = ""
        return reply or random.choice(PET_TALK_FALLBACK_REPLIES)


def _clean_short_pet_text(reply: str, limit: int = 34) -> str:
    text = " ".join((reply or "").strip().split())
    bad_markers = ["不太确定怎么回答", "换个方式问", "没有返回内容", "服务端错误", "失败"]
    if any(marker in text for marker in bad_markers):
        return ""
    for prefix in ("AI:", "我：", "桌宠：", "助手："):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    if "\n" in text:
        text = text.splitlines()[0].strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _show_webview_pet() -> None:
    if _live2d_window:
        try:
            _live2d_window.show()
            return
        except Exception:
            pass
    webbrowser.open(WEB_URL)


def _hide_webview_pet() -> None:
    if _live2d_window:
        try:
            _live2d_window.hide()
        except Exception:
            pass


def _quit_pet_process() -> None:
    try:
        import tray_manager
        tray_manager.stop_tray()
    except Exception:
        pass
    os._exit(0)


def _start_instance_tray(style: str, on_show=None, on_hide=None, on_quit=None, on_talk=None, on_realtime=None) -> None:
    # 如果已有 launcher 级别的托盘，则不再创建桌宠实例托盘，避免冲突
    if os.environ.get("_COMPANION_HAS_LAUNCHER_TRAY"):
        return
    try:
        import tray_manager
        extra_items = None
        if on_talk or on_realtime:
            import pystray
            extra_items = []
            if on_realtime:
                extra_items.append(pystray.MenuItem("实时对话", lambda _icon, _item: on_realtime()))
            if on_talk:
                extra_items.append(pystray.MenuItem("和其他桌宠说话", lambda _icon, _item: on_talk()))
        tray_manager.start_tray(
            on_show=on_show,
            on_hide=on_hide,
            on_quit=on_quit or _quit_pet_process,
            icon_path=ROOT / "pet_icon.ico",
            title=f"{_pet_style_label(style)} - 智能伙伴",
            name=f"companion_ai_pet_{style}_{os.getpid()}",
            extra_items=extra_items,
        )
    except Exception:
        pass


class Live2DPetApi:
    """JS API exposed to live2d_viewer.html via pywebview for right-click menu actions."""

    def __init__(self, style: str = PET_STYLE_LIVE2D) -> None:
        self.style = style
        self.talk_agent = PetTalkAgent(style, self._show_pet_message)
        self.talk_agent.start()

    def _show_pet_message(self, text: str) -> None:
        global _live2d_window
        if not _live2d_window:
            return
        try:
            payload = json.dumps(text, ensure_ascii=False)
            _live2d_window.evaluate_js(f"window.showPetMessage && window.showPetMessage({payload});")
        except Exception:
            pass

    def open_chat(self):
        webbrowser.open(WEB_URL)

    def open_web(self):
        webbrowser.open(WEB_URL)

    def open_realtime(self):
        webbrowser.open(WEB_URL + "/?realtime_prompt=1")

    def open_settings(self):
        import webview
        def _open():
            webview.create_window(
                "Companion Settings",
                WEB_URL + "/#settings",
                width=420,
                height=600,
                on_top=True,
            )
        threading.Thread(target=_open, daemon=True).start()

    def talk_to_pets(self):
        self.talk_agent.start_conversation()

    def quit(self):
        try:
            self.talk_agent.stop()
        except Exception:
            pass
        global _live2d_window
        if _live2d_window:
            try:
                _live2d_window.destroy()
            except Exception:
                pass
        _quit_pet_process()


def _active_live2d_model() -> str:
    try:
        state = json.loads(LIVE2D_STATE_FILE.read_text(encoding="utf-8"))
        return str(state.get("active", "")).strip()
    except Exception:
        return ""


def _active_3d_model() -> str:
    try:
        state = json.loads(MODEL3D_STATE_FILE.read_text(encoding="utf-8"))
        return str(state.get("active", "")).strip()
    except Exception:
        return ""


def _python_command_with_module(module_name: str) -> list[str] | None:
    candidates: list[list[str]] = []
    candidates.append([sys.executable])
    try:
        candidates.append([python_exe()])
        candidates.append([runtime_python_exe(create=False)])
    except Exception:
        pass
    candidates.extend([
        ["py", "-3.14"],
        ["py", "-3.13"],
        ["py", "-3.12"],
        ["py", "-3"],
        ["python"],
    ])
    seen: set[tuple[str, ...]] = set()
    for cmd in candidates:
        key = tuple(cmd)
        if key in seen:
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                [*cmd, "-c", f"import {module_name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return cmd
        except Exception:
            continue
    return None


class EmbeddedModelLayer:
    """A model-only WebView that follows the stable Tk desktop-pet shell."""

    def __init__(self, root: tk.Tk, style: str) -> None:
        self.root = root
        self.style = style
        self.url = WEB_URL + ("/3d?pet=1&shell=1" if style == PET_STYLE_3D else "/live2d?pet=1&shell=1")
        self.window = None
        self.proc: subprocess.Popen | None = None
        self._browser_hwnd: int | None = None
        self._electron_hwnd: int | None = None
        self.geometry_file = DATA_DIR / "runtime" / f"model_layer_{os.getpid()}_{style}.json"
        self._running = False
        self._available = False
        self._use_electron = False
        self._last_geometry: tuple[int, int, int, int] | None = None
        self._last_visible: bool | None = None
        self._last_cursor: tuple[int, int] | None = None
        self._last_cursor_write_at: float = 0.0
        self._last_electron_geometry: tuple[int, int, int, int] | None = None
        self._electron_moved_at: float = 0.0
        self._suppress_tk_sync_until: float = 0.0

    def start(self) -> bool:
        if self.style not in (PET_STYLE_LIVE2D, PET_STYLE_3D):
            return False
        self._running = True
        self.sync(True, force=True)
        if self._start_electron_app():
            self._available = True
            self._use_electron = True
            return True
        if self._start_browser_app():
            self._available = True
            return True
        try:
            python_cmd = _python_command_with_module("webview")
            if not python_cmd:
                raise RuntimeError("No Python interpreter with pywebview is available")
            self.proc = subprocess.Popen(
                [
                    *python_cmd,
                    str(Path(__file__).resolve()),
                    "--model-layer",
                    self.style,
                    "--geometry-file",
                    str(self.geometry_file),
                ],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            self._available = True
        except Exception as exc:
            self._available = False
            _log_startup_error(f"{self.style} embedded model layer spawn failed", exc)
            return False
        return True

    def _start_electron_app(self) -> bool:
        main_js = ROOT / "electron_pet" / "main.cjs"
        direct_electron = ROOT / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
        electron_bin = ROOT / "node_modules" / ".bin" / ("electron.cmd" if os.name == "nt" else "electron")
        if not main_js.exists():
            return False
        if direct_electron.exists():
            electron_cmd = [str(direct_electron)]
        elif electron_bin.exists():
            electron_cmd = [str(electron_bin)]
        else:
            return False
        try:
            self.proc = subprocess.Popen(
                [
                    *electron_cmd,
                    str(main_js),
                    "--style",
                    self.style,
                    "--geometry-file",
                    str(self.geometry_file),
                ],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            return True
        except Exception as exc:
            _log_startup_error(f"{self.style} electron model layer spawn failed", exc)
            return False

    def _browser_executable(self) -> str | None:
        candidates = [
            shutil.which("msedge"),
            shutil.which("chrome"),
            shutil.which("chromium"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return str(path)
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    def _start_browser_app(self) -> bool:
        exe = self._browser_executable()
        if not exe:
            return False
        x, y, w, h = self._current_geometry()
        profile_dir = DATA_DIR / "runtime" / f"model_browser_{os.getpid()}_{self.style}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.proc = subprocess.Popen(
                [
                    exe,
                    f"--app={self.url}",
                    f"--user-data-dir={profile_dir}",
                    f"--window-size={w},{h}",
                    f"--window-position={x},{y}",
                    "--no-first-run",
                    "--disable-extensions",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            return True
        except Exception as exc:
            _log_startup_error(f"{self.style} browser model layer spawn failed", exc)
            return False

    def _current_geometry(self) -> tuple[int, int, int, int]:
        try:
            self.root.update_idletasks()
            w = max(120, int(self.root.winfo_width()))
            h = max(160, int(self.root.winfo_height()))
            x = int(self.root.winfo_x())
            y = int(self.root.winfo_y())
            return x, y, w, h
        except Exception:
            return 500, 300, int(BASE_W), int(BASE_H)

    def _current_cursor(self) -> tuple[int, int] | None:
        try:
            return int(self.root.winfo_pointerx()), int(self.root.winfo_pointery())
        except Exception:
            return None

    def sync(self, visible: bool = True, force: bool = False) -> None:
        if not self._running:
            return
        try:
            now = time.time()
            if self._use_electron:
                self._sync_from_electron()
            geometry = self._current_geometry()
            cursor = None if self._use_electron else self._current_cursor()
            tk_is_moving = now < self._suppress_tk_sync_until
            if not tk_is_moving or force:
                state = {
                    "style": self.style,
                    "url": self.url,
                    "x": geometry[0],
                    "y": geometry[1],
                    "w": geometry[2],
                    "h": geometry[3],
                    "visible": bool(visible),
                    "closed": False,
                    "updated_at": now,
                }
                if cursor:
                    state["cursor"] = {"x": cursor[0], "y": cursor[1]}
                cursor_changed = cursor is not None and cursor != self._last_cursor and (now - self._last_cursor_write_at) >= 0.03
                if force or geometry != self._last_geometry or visible != self._last_visible or cursor_changed:
                    self.geometry_file.parent.mkdir(parents=True, exist_ok=True)
                    tmp = self.geometry_file.with_suffix(".tmp")
                    tmp.write_text(json.dumps(state), encoding="utf-8")
                    tmp.replace(self.geometry_file)
                    self._last_geometry = geometry
                    self._last_visible = visible
                    if cursor:
                        self._last_cursor = cursor
                        self._last_cursor_write_at = now
            self._sync_browser_window(geometry, visible)
            if not self._use_electron:
                try:
                    self.root.lift()
                    self.root.attributes("-topmost", True)
                except Exception:
                    pass
        except Exception:
            pass

    def _sync_from_electron(self) -> None:
        """Read position from Electron via geometry file and update Tk if needed."""
        try:
            if not self.geometry_file.exists():
                return
            data = json.loads(self.geometry_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            electron_moved = bool(data.get("electron_moved", False))
            if not electron_moved:
                return
            x = int(data.get("x", 0))
            y = int(data.get("y", 0))
            w = int(data.get("w", 0))
            h = int(data.get("h", 0))
            if not all((x, y, w, h)):
                return
            new_geom = (x, y, w, h)
            if new_geom == self._last_electron_geometry:
                return
            self._last_electron_geometry = new_geom
            self._electron_moved_at = time.time()
            self._suppress_tk_sync_until = time.time() + 0.15
            current_geom = self._current_geometry()
            if (x, y) != (current_geom[0], current_geom[1]):
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            data["electron_moved"] = False
            try:
                tmp = self.geometry_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(data), encoding="utf-8")
                tmp.replace(self.geometry_file)
            except Exception:
                pass
        except Exception:
            pass

    def _expected_browser_title(self) -> str:
        return "3D Model Viewer" if self.style == PET_STYLE_3D else "Live2D Viewer"

    def _find_browser_window(self) -> int | None:
        if not _HAS_CTYPES:
            return None
        if self._browser_hwnd:
            try:
                if ctypes.windll.user32.IsWindow(self._browser_hwnd):
                    return self._browser_hwnd
            except Exception:
                pass
        target = self._expected_browser_title()
        found: list[int] = []
        try:
            from ctypes import wintypes
            enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _callback(hwnd, _lparam):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if target in buf.value:
                    found.append(int(hwnd))
                return True

            ctypes.windll.user32.EnumWindows(enum_proc(_callback), 0)
        except Exception:
            return None
        if found:
            self._browser_hwnd = found[-1]
            return self._browser_hwnd
        return None

    def _sync_browser_window(self, geometry: tuple[int, int, int, int], visible: bool) -> None:
        if self._use_electron:
            return
        hwnd = self._find_browser_window()
        if not hwnd or not _HAS_CTYPES:
            return
        try:
            x, y, w, h = geometry
            user32 = ctypes.windll.user32
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_SYSMENU = 0x00080000
            WS_EX_TOOLWINDOW = 0x00000080
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TOOLWINDOW)
            user32.ShowWindow(hwnd, 8 if visible else 0)  # SW_SHOWNA / SW_HIDE
            if visible:
                user32.MoveWindow(hwnd, x, y, w, h, True)
                HWND_NOTOPMOST = -2
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_NOACTIVATE = 0x0010
                SWP_FRAMECHANGED = 0x0020
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_FRAMECHANGED)
        except Exception:
            pass

    def close(self) -> None:
        self._running = False
        if self._browser_hwnd and _HAS_CTYPES:
            try:
                ctypes.windll.user32.PostMessageW(self._browser_hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass
        try:
            if self.geometry_file.exists():
                data = json.loads(self.geometry_file.read_text(encoding="utf-8"))
                data["closed"] = True
                self.geometry_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass


def _run_3d_pet_window() -> bool:
    """Run the desktop pet as 3D model when a local model is active."""
    active = _active_3d_model()
    if not active:
        return False
    try:
        import webview
    except Exception:
        return _run_3d_browser_app()

    url = WEB_URL + "/3d?pet=1"
    api = Live2DPetApi(PET_STYLE_3D)
    try:
        _win = webview.create_window(
            "Companion 3D Pet",
            url,
            width=250,
            height=350,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color=TRANSPARENT_COLOR,
            transparent=True,
            shadow=False,
            js_api=api,
            x=500,
            y=300,
        )
    except TypeError:
        _win = webview.create_window(
            "Companion 3D Pet",
            url,
            width=250,
            height=350,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color=TRANSPARENT_COLOR,
            js_api=api,
            x=500,
            y=300,
        )
    global _live2d_window
    _live2d_window = _win
    _start_instance_tray(
        PET_STYLE_3D,
        on_show=_show_webview_pet,
        on_hide=_hide_webview_pet,
        on_quit=api.quit,
        on_talk=api.talk_to_pets,
    )
    print("[Companion AI] 3D 桌宠窗口已创建！位置: (500, 300)，大小: 250x350")
    try:
        webview.start(lambda: _apply_pywebview_transparency(_win))
    except Exception as exc:
        print(f"[Companion AI] pywebview 启动失败: {exc}")
        print("[Companion AI] 回退到浏览器模式...")
        _live2d_window = None
        return _run_3d_browser_app()
    return True


def _run_3d_browser_app() -> bool:
    url = WEB_URL + "/3d?pet=1"
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.exists() and shutil.which(candidate) is None:
            continue
        exe = str(path) if path.exists() else candidate
        subprocess.Popen(
            [
                exe,
                f"--app={url}",
                "--window-size=250,350",
                "--window-position=1080,520",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        _start_instance_tray(PET_STYLE_3D, on_show=lambda: webbrowser.open(url), on_hide=None, on_quit=_quit_pet_process)
        while True:
            time.sleep(1)
    return False


def _run_live2d_pet_window() -> bool:
    """Run the desktop pet as Live2D when a local model is active."""
    active = _active_live2d_model()
    if not active:
        return False
    try:
        import webview
    except Exception:
        return _run_live2d_browser_app()

    url = WEB_URL + "/live2d?pet=1"
    api = Live2DPetApi(PET_STYLE_LIVE2D)
    try:
        _live2d_window_ref = webview.create_window(
            "Companion Live2D Pet",
            url,
            width=250,
            height=350,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color=TRANSPARENT_COLOR,
            transparent=True,
            shadow=False,
            js_api=api,
            x=500,
            y=300,
        )
    except TypeError:
        _live2d_window_ref = webview.create_window(
            "Companion Live2D Pet",
            url,
            width=250,
            height=350,
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color=TRANSPARENT_COLOR,
            js_api=api,
            x=500,
            y=300,
        )
    global _live2d_window
    _live2d_window = _live2d_window_ref
    _start_instance_tray(
        PET_STYLE_LIVE2D,
        on_show=_show_webview_pet,
        on_hide=_hide_webview_pet,
        on_quit=api.quit,
        on_talk=api.talk_to_pets,
    )
    print("[Companion AI] Live2D 桌宠窗口已创建！位置: (500, 300)，大小: 250x350")
    print("[Companion AI] 如果看不到桌宠，请检查：1. 是否有Live2D模型 2. 窗口是否在屏幕上")
    try:
        webview.start(lambda: _apply_pywebview_transparency(_live2d_window_ref))
    except Exception as exc:
        # pywebview failed (WebView2 issue etc.), fall back to browser
        print(f"[Companion AI] pywebview 启动失败: {exc}")
        print("[Companion AI] 回退到浏览器模式...")
        _live2d_window = None
        return _run_live2d_browser_app()
    return True


def _run_live2d_browser_app() -> bool:
    url = WEB_URL + "/live2d?pet=1"
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.exists() and shutil.which(candidate) is None:
            continue
        exe = str(path) if path.exists() else candidate
        subprocess.Popen(
            [
                exe,
                f"--app={url}",
                "--window-size=250,350",
                "--window-position=1080,520",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        _start_instance_tray(PET_STYLE_LIVE2D, on_show=lambda: webbrowser.open(url), on_hide=None, on_quit=_quit_pet_process)
        while True:
            time.sleep(1)
    return False


class DesktopPet:
    def __init__(self, style: str = PET_STYLE_CLASSIC) -> None:
        self.style = style
        self.instance_id = f"{style}-{os.getpid()}-{int(time.time() * 1000)}"
        self.companion_name = f"{_pet_style_label(style)} {str(os.getpid())[-4:]}"
        self._seen_pet_message_ids: set[str] = set()
        self._next_pet_talk_poll_at = 0.0
        self._next_pet_heartbeat_at = 0.0
        self._next_auto_pet_talk_at = self._next_auto_pet_talk_time()
        self._pet_reply_busy = False
        self.root = tk.Tk()
        self.root.title(_pet_style_label(style))
        self.scale = self._load_scale()
        w = int(BASE_W * self.scale)
        h = int(BASE_H * self.scale)
        self.root.geometry(f"{w}x{h}+1200+620")
        self.root.overrideredirect(True)
        # restore taskbar visibility and system menu (overrideredirect strips WS_EX_APPWINDOW and WS_SYSMENU)
        if _HAS_CTYPES:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_SYSMENU = 0x00080000
            WS_MINIMIZEBOX = 0x00020000
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_LAYERED = 0x00080000
            LWA_COLORKEY = 0x00000001
            # Restore system menu and minimize box so taskbar right-click works
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = style | WS_SYSMENU | WS_MINIMIZEBOX
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            # Restore taskbar button and layered transparency
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_APPWINDOW | WS_EX_LAYERED) & ~WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd,
                _hex_color_to_colorref(TRANSPARENT_COLOR),
                255,
                LWA_COLORKEY,
            )
        self._topmost = self._load_topmost()
        self.root.attributes("-topmost", self._topmost)
        self.root.configure(bg=TRANSPARENT_COLOR)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        except tk.TclError:
            pass

        self.canvas = tk.Canvas(self.root, width=w, height=h, bg=TRANSPARENT_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.motion = "idle"
        self.frame = 0
        self.drag_x = 0
        self.drag_y = 0
        self.drag_root_x = 0
        self.drag_root_y = 0
        self.drag_window_x = 0
        self.drag_window_y = 0
        self._dragging = False
        self._mouse_x = w / 2
        self._mouse_y = h / 2
        self._mouse_seen_until = 0.0
        self._drag_last_root_x = 0
        self._drag_last_root_y = 0
        self._drag_speed = 0.0
        self._drag_particles: list[dict[str, float | str]] = []
        self._pickup_until = 0.0
        self._release_bounce_until = 0.0
        self.speech = ""
        self.speech_until = 0.0
        self.next_idle_speech_at = self._next_idle_speech_time()
        self.pet_state = "idle"
        self.state_until = 0.0
        self.motion_override = ""
        self.motion_override_until = 0.0
        self._hovering_pet = False
        self.chat_win = None
        self.chat_log = None
        self.chat_entry = None
        self.chat_history: list[tuple[str, str]] = []
        self._hover_chat_intro_visible = True
        self._chat_busy = False
        self._idle_thought_busy = False
        self._hide_chat_after_id = None
        self.settings_win = None
        self._ctx_menu = None
        self._full_chat_win = None
        self._last_menu_popup_at = 0.0
        self._next_routine_check_at = 0.0
        self._edge_hidden = False
        self._edge_restore_geometry: str | None = None
        self._seen_realtime_message_ids: set[str] = set()
        self._next_realtime_chat_poll_at = 0.0
        self.model_layer = None
        if self._uses_embedded_model():
            self.model_layer = EmbeddedModelLayer(self.root, self.style)
            if not self.model_layer.start():
                self.model_layer = None
                self.speech = "模型层未就绪，先用外壳陪你。"
                self.speech_until = time.time() + 5
        install_shutdown_handlers("pet")
        record_app_start("pet")

        # --- bindings ---
        self.canvas.bind("<Enter>", self.on_hover_enter)
        self.canvas.bind("<Leave>", self.on_hover_leave)
        self.canvas.bind("<Motion>", self.on_mouse_motion)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Double-Button-1>", lambda _e: self.open_full_chat())
        for widget in (self.root, self.canvas):
            widget.bind("<Button-3>", self.show_menu)
            widget.bind("<ButtonRelease-3>", self.show_menu)
            widget.bind("<Button-2>", self.show_menu)
            widget.bind("<Shift-F10>", self.show_menu)
            widget.bind("<Menu>", self.show_menu)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)  # scroll to resize
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        _start_instance_tray(
            style,
            on_show=lambda: self.root.after(0, self.show_from_tray),
            on_hide=lambda: self.root.after(0, self.hide_to_tray),
            on_quit=lambda: self.root.after(0, self.close),
            on_talk=lambda: self.root.after(0, self.start_pet_conversation),
            on_realtime=lambda: self.root.after(0, self.open_realtime_prompt),
        )
        self._sync_pet_talk_bus(force=True)
        self.draw()
        self.tick()

    # ------------------------------------------------------------------
    # avatar / animation (unchanged)
    # ------------------------------------------------------------------

    def _uses_embedded_model(self) -> bool:
        if self.style == PET_STYLE_LIVE2D:
            return bool(_active_live2d_model())
        if self.style == PET_STYLE_3D:
            return bool(_active_3d_model())
        return False

    def load_avatar(self) -> dict:
        try:
            return json.loads(AVATAR_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"last_motion": "idle", "motions": [], "stats": {}}

    def start_drag(self, event) -> None:
        self._dragging = True
        self._pickup_until = time.time() + 0.28
        self._release_bounce_until = 0.0
        self._remember_mouse(event)
        if self._edge_hidden:
            self._edge_hidden = False
            self._edge_restore_geometry = None
        self.drag_x = event.x
        self.drag_y = event.y
        self.drag_root_x = event.x_root
        self.drag_root_y = event.y_root
        self.drag_window_x = self.root.winfo_x()
        self.drag_window_y = self.root.winfo_y()
        self._drag_last_root_x = event.x_root
        self._drag_last_root_y = event.y_root
        self._drag_speed = 0.0
        self.set_pet_state("happy", 1.4, "欸？被提起来啦。")

    def drag(self, event) -> None:
        self._remember_mouse(event)
        step_dx = event.x_root - self._drag_last_root_x
        step_dy = event.y_root - self._drag_last_root_y
        self._drag_speed = min(28.0, math.hypot(step_dx, step_dy))
        self._drag_last_root_x = event.x_root
        self._drag_last_root_y = event.y_root
        self._add_drag_particles(event.x, event.y)
        dx = event.x_root - self.drag_root_x
        dy = event.y_root - self.drag_root_y
        self.root.geometry(f"+{self.drag_window_x + dx}+{self.drag_window_y + dy}")
        if self.model_layer:
            self.model_layer.sync(self.root.state() != "withdrawn")

    def stop_drag(self, event) -> None:
        self._remember_mouse(event)
        self._dragging = False
        self._drag_speed = 0.0
        self._release_bounce_until = time.time() + 0.42
        self.set_pet_state("curious", 1.6, "落地。")
        self.draw()

    def on_mouse_motion(self, event) -> None:
        self._remember_mouse(event)

    def _remember_mouse(self, event) -> None:
        self._mouse_x = float(getattr(event, "x", self._mouse_x))
        self._mouse_y = float(getattr(event, "y", self._mouse_y))
        self._mouse_seen_until = time.time() + 1.2

    def _add_drag_particles(self, x: float, y: float) -> None:
        if self.model_layer:
            return
        now = time.time()
        colors = ("#276ef1", "#0b7a55", "#f08a24", "#8a5cf6")
        for _ in range(2):
            self._drag_particles.append({
                "x": float(x) + random.uniform(-10, 10) * self.scale,
                "y": float(y) + random.uniform(8, 28) * self.scale,
                "vx": random.uniform(-1.4, 1.4) * self.scale,
                "vy": random.uniform(0.6, 2.2) * self.scale,
                "born": now,
                "life": random.uniform(0.42, 0.7),
                "size": random.uniform(2.0, 4.4) * self.scale,
                "color": random.choice(colors),
            })
        if len(self._drag_particles) > 42:
            self._drag_particles = self._drag_particles[-42:]

    def close(self) -> None:
        _remove_pet_heartbeat(self.instance_id)
        record_app_stop("pet")
        try:
            import tray_manager
            tray_manager.stop_tray()
        except Exception:
            pass
        if self.chat_win and self.chat_win.winfo_exists():
            self.chat_win.destroy()
        if self._full_chat_win and self._full_chat_win.winfo_exists():
            self._full_chat_win.destroy()
        if self.model_layer:
            self.model_layer.close()
        self.root.destroy()

    def hide_to_tray(self) -> None:
        try:
            self.root.withdraw()
        except Exception:
            pass
        if self.model_layer:
            self.model_layer.sync(False)

    def show_from_tray(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        if self.model_layer:
            self.model_layer.sync(True)

    def _screen_work_area(self) -> tuple[int, int, int, int]:
        # Tk does not expose the Windows work area directly; screen bounds are
        # enough for a small edge strip and keep this portable.
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def _nearest_edge(self) -> str:
        self.root.update_idletasks()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())
        sx, sy, sw, sh = self._screen_work_area()
        distances = [
            ("left", abs(x - sx)),
            ("right", abs((sx + sw) - (x + w))),
            ("top", abs(y - sy)),
            ("bottom", abs((sy + sh) - (y + h))),
        ]
        return min(distances, key=lambda item: item[1])[0]

    def toggle_edge_hide(self) -> None:
        self.root.update_idletasks()
        if self._edge_hidden:
            if self._edge_restore_geometry:
                try:
                    self.root.geometry(self._edge_restore_geometry)
                except Exception:
                    pass
            self._edge_hidden = False
            self._edge_restore_geometry = None
            if self.model_layer:
                self.model_layer.sync(True)
            return

        self._edge_restore_geometry = self.root.geometry()
        edge = self._nearest_edge()
        visible = max(14, int(18 * self.scale))
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())
        sx, sy, sw, sh = self._screen_work_area()
        if edge == "left":
            x = sx - w + visible
            y = max(sy, min(y, sy + sh - visible))
        elif edge == "right":
            x = sx + sw - visible
            y = max(sy, min(y, sy + sh - visible))
        elif edge == "top":
            y = sy - h + visible
            x = max(sx, min(x, sx + sw - visible))
        else:
            y = sy + sh - visible
            x = max(sx, min(x, sx + sw - visible))
        self._edge_hidden = True
        self.root.geometry(f"+{int(x)}+{int(y)}")
        if self.chat_win and self.chat_win.winfo_exists():
            self.chat_win.withdraw()
        if self.model_layer:
            self.model_layer.sync(True)

    def say_status(self) -> None:
        avatar = self.load_avatar()
        stats = avatar.get("stats", {})
        motion_count = len(avatar.get("motions", []))
        self.speech = f"\u6837\u672c {stats.get('training_examples', 0)} \u6761\n\u52a8\u4f5c {motion_count} \u4e2a"
        self.speech_until = time.time() + 3
        self.next_idle_speech_at = self._next_idle_speech_time()
        self.set_pet_state("busy", 3)

    def _next_idle_speech_time(self) -> float:
        return time.time() + random.uniform(IDLE_SPEECH_MIN_SECONDS, IDLE_SPEECH_MAX_SECONDS)

    def _next_auto_pet_talk_time(self) -> float:
        return time.time() + random.uniform(AUTO_PET_TALK_MIN_SECONDS, AUTO_PET_TALK_MAX_SECONDS)

    def _sync_pet_talk_bus(self, force: bool = False) -> None:
        now = time.time()
        if force or now >= self._next_pet_heartbeat_at:
            _write_pet_heartbeat(self.instance_id, self.companion_name, self.style)
            self._next_pet_heartbeat_at = now + 8
        if not force and now < self._next_pet_talk_poll_at:
            return
        self._next_pet_talk_poll_at = now + 1.1
        data = _prune_pet_talk_bus(_load_pet_talk_bus())
        for message in data.get("messages", []):
            msg_id = str(message.get("id", ""))
            if not msg_id or msg_id in self._seen_pet_message_ids:
                continue
            self._seen_pet_message_ids.add(msg_id)
            if message.get("from_id") == self.instance_id:
                continue
            self._receive_pet_message(message)

    def _poll_realtime_chat(self) -> None:
        now = time.time()
        if now < self._next_realtime_chat_poll_at:
            return
        self._next_realtime_chat_poll_at = now + 0.25
        try:
            data = json.loads(REALTIME_CHAT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            return
        new_items = []
        for item in messages[-12:]:
            msg_id = str(item.get("id", ""))
            if not msg_id or msg_id in self._seen_realtime_message_ids:
                continue
            self._seen_realtime_message_ids.add(msg_id)
            role = str(item.get("role", "system"))
            text = str(item.get("text", "")).strip()
            if text:
                new_items.append((role, text))
        if not new_items:
            return
        self.next_idle_speech_at = self._next_idle_speech_time()
        self.show_chat_panel(focus=False)
        for role, text in new_items:
            if role == "user":
                self._append_chat_line("你", text, role="user")
            elif role == "assistant":
                self._append_chat_line("我", text, role="assistant")
                self.set_pet_state("happy", 4, text)
            else:
                self._append_chat_line("", text, role="system")
                if "听" in text or "唤醒" in text:
                    self.set_pet_state("listening", 2.5, text)
                elif "思考" in text or "观察" in text:
                    self.set_pet_state("thinking", 2.5, text)
                elif "播放" in text:
                    self.set_pet_state("happy", 2.5, text)
                else:
                    self.set_pet_state("curious", 2.5, text)

    def _active_peer_count(self) -> int:
        data = _prune_pet_talk_bus(_load_pet_talk_bus())
        return sum(1 for item in data.get("companions", []) if item.get("id") != self.instance_id)

    def start_pet_conversation(self) -> None:
        peers = self._active_peer_count()
        if peers <= 0:
            self.set_pet_state("curious", 4, "现在只有我一个桌宠在线。")
            return
        text = self._make_pet_starter()
        message = _append_pet_message(
            from_id=self.instance_id,
            from_name=self.companion_name,
            text=text,
            kind="talk",
        )
        if message.get("id"):
            self._seen_pet_message_ids.add(message["id"])
        self.set_pet_state("happy", 4, text)
        self._next_auto_pet_talk_at = self._next_auto_pet_talk_time()

    def _maybe_start_auto_pet_conversation(self) -> None:
        now = time.time()
        if now < self._next_auto_pet_talk_at:
            return
        self._next_auto_pet_talk_at = self._next_auto_pet_talk_time()
        if self._active_peer_count() <= 0:
            return
        if self._dragging or self._hovering_pet or self._chat_busy or self._idle_thought_busy or self._pet_reply_busy:
            return
        if self.speech and now <= self.speech_until:
            return
        if random.random() > 0.55:
            return
        self.start_pet_conversation()

    def _make_pet_starter(self) -> str:
        prompt = (
            "你是一个桌面宠物，现在想主动和另一个桌宠说一句话。"
            "请用一句自然、轻松、不会打扰用户的中文开场。"
            "只输出一句话，不要超过24个字。"
        )
        try:
            from hybrid_chat import get_hybrid_chatbot
            reply, _source = get_hybrid_chatbot().chat(prompt, self.chat_history[-4:])
            reply = self._clean_idle_reply(reply)
        except Exception:
            reply = ""
        return reply or random.choice(PET_TALK_STARTERS)

    def _receive_pet_message(self, message: dict) -> None:
        sender = str(message.get("from_name") or "另一个桌宠")
        text = str(message.get("text") or "").strip()
        if not text:
            return
        self.next_idle_speech_at = self._next_idle_speech_time()
        self.set_pet_state("curious", 5, f"{sender}：{text}")
        if message.get("kind") != "talk" or self._pet_reply_busy:
            return
        self._pet_reply_busy = True

        def _run() -> None:
            reply = self._make_pet_reply(sender, text)
            self.root.after(0, lambda: self._finish_pet_reply(message, reply))

        delay_ms = random.randint(700, 1800)
        self.root.after(delay_ms, lambda: threading.Thread(target=_run, daemon=True).start())

    def _make_pet_reply(self, sender: str, text: str) -> str:
        prompt = (
            "你是一个桌面宠物，正在和另一个桌宠聊天。"
            "请用一句自然、可爱但不过分夸张的中文回复。"
            "只输出一句话，不要超过24个字。\n"
            f"对方名字：{sender}\n"
            f"对方说：{text}"
        )
        try:
            from hybrid_chat import get_hybrid_chatbot
            reply, _source = get_hybrid_chatbot().chat(prompt, self.chat_history[-4:])
            reply = self._clean_idle_reply(reply)
        except Exception:
            reply = ""
        return reply or random.choice(PET_TALK_FALLBACK_REPLIES)

    def _finish_pet_reply(self, source_message: dict, reply: str) -> None:
        self._pet_reply_busy = False
        message = _append_pet_message(
            from_id=self.instance_id,
            from_name=self.companion_name,
            text=reply,
            kind="reply",
            reply_to=str(source_message.get("id", "")),
        )
        if message.get("id"):
            self._seen_pet_message_ids.add(message["id"])
        self.set_pet_state("happy", 4, reply)

    # ------------------------------------------------------------------
    # scale (resize)
    # ------------------------------------------------------------------

    def _load_scale(self) -> float:
        try:
            data = json.loads(SCALE_FILE.read_text(encoding="utf-8"))
            return max(0.5, min(3.0, float(data.get("scale", 1.0))))
        except Exception:
            return 1.0

    def _save_scale(self) -> None:
        SCALE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCALE_FILE.write_text(json.dumps({"scale": self.scale}), encoding="utf-8")

    def _load_topmost(self) -> bool:
        try:
            data = json.loads(TOPMOST_FILE.read_text(encoding="utf-8"))
            return bool(data.get("topmost", True))
        except Exception:
            return True

    def _save_topmost(self) -> None:
        TOPMOST_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOPMOST_FILE.write_text(json.dumps({"topmost": self._topmost}), encoding="utf-8")

    def _toggle_topmost(self) -> None:
        self._topmost = not self._topmost
        self.root.attributes("-topmost", self._topmost)
        self._save_topmost()

    def _toggle_autostart(self) -> None:
        enabled = is_autostart_enabled()
        result = set_autostart_enabled(not enabled)
        print(f"[Companion AI] {result}")

    def _set_scale(self, new_scale: float) -> None:
        new_scale = max(0.5, min(3.0, round(new_scale, 1)))
        if new_scale == self.scale:
            return
        self.scale = new_scale
        self._save_scale()
        w = int(BASE_W * self.scale)
        h = int(BASE_H * self.scale)
        # Keep window at current position
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.config(width=w, height=h)
        if self.model_layer:
            self.model_layer.sync(self.root.state() != "withdrawn")
        self.draw()
        # Reposition chat panel if visible
        if self.chat_win and self.chat_win.winfo_exists():
            self._position_chat_panel()

    def _on_mousewheel(self, event) -> None:
        delta = 1 if event.delta > 0 else -1
        self._set_scale(self.scale + delta * 0.1)

    def maybe_idle_speech(self) -> None:
        now = time.time()
        if now < self.next_idle_speech_at:
            return
        if self._dragging or self._hovering_pet or self._chat_busy or self._idle_thought_busy:
            self.next_idle_speech_at = now + 5
            return
        if self.speech and now <= self.speech_until:
            self.next_idle_speech_at = now + 5
            return
        self._start_contextual_idle_speech()
        self.next_idle_speech_at = self._next_idle_speech_time()

    def _start_contextual_idle_speech(self) -> None:
        self._idle_thought_busy = True
        self.set_pet_state("thinking", 2, "\u6211\u770b\u770b\u73b0\u5728\u9002\u5408\u8bf4\u4ec0\u4e48\u2026")

        def _run() -> None:
            app = _foreground_app_context()
            time_text = _time_context()
            fallback = self._fallback_context_line(time_text, app)
            process_text = app.get("process") or "\u672a\u77e5"
            title_text = app.get("title") or "\u672a\u77e5"
            prompt = (
                "\u4f60\u662f\u4e00\u4e2a\u6e29\u67d4\u7684\u684c\u9762\u5ba0\u7269\u3002"
                "\u6839\u636e\u5f53\u524d\u65f6\u95f4\u548c\u7528\u6237\u6b63\u5728\u770b\u7684\u524d\u53f0\u5e94\u7528\uff0c"
                "\u4e3b\u52a8\u8bf4\u4e00\u53e5\u7b80\u77ed\u3001\u81ea\u7136\u3001\u4e0d\u6253\u6270\u7684\u4e2d\u6587\u3002"
                "\u53ea\u8f93\u51fa\u4e00\u53e5\u8bdd\uff0c\u4e0d\u8981\u89e3\u91ca\uff0c\u4e0d\u8981\u8d85\u8fc726\u4e2a\u5b57\u3002\n"
                f"\u65f6\u95f4\uff1a{time_text}\n"
                f"\u524d\u53f0\u7a0b\u5e8f\uff1a{process_text}\n"
                f"\u7a97\u53e3\u6807\u9898\uff1a{title_text}"
            )
            try:
                from hybrid_chat import get_hybrid_chatbot
                reply, _source = get_hybrid_chatbot().chat(prompt, self.chat_history[-4:])
                reply = self._clean_idle_reply(reply) or fallback
            except Exception:
                reply = fallback
            self.root.after(0, lambda: self._finish_contextual_idle_speech(reply))

        threading.Thread(target=_run, daemon=True).start()

    def _fallback_context_line(self, time_text: str, app: dict[str, str]) -> str:
        title = app.get("title") or ""
        process = (app.get("process") or "").lower()
        if "code" in process or "pycharm" in process or "visual studio" in title.lower():
            return f"{time_text}\uff0c\u5199\u4ee3\u7801\u4e5f\u8bb0\u5f97\u559d\u53e3\u6c34\u3002"
        if "chrome" in process or "edge" in process or "firefox" in process:
            return f"{time_text}\uff0c\u6211\u770b\u4f60\u5728\u6d4f\u89c8\uff0c\u9700\u8981\u6211\u5e2e\u4f60\u6574\u7406\u5417\uff1f"
        if "wechat" in process or "\u5fae\u4fe1" in title:
            return f"{time_text}\uff0c\u56de\u6d88\u606f\u4e5f\u522b\u592a\u7d27\u5f20\u3002"
        if "word" in process or "excel" in process or "powerpnt" in process:
            return f"{time_text}\uff0c\u6587\u6863\u5904\u7406\u6162\u6162\u6765\u5c31\u597d\u3002"
        return random.choice(PET_IDLE_LINES)

    def _clean_idle_reply(self, reply: str) -> str:
        text = " ".join((reply or "").strip().split())
        bad_markers = [
            "\u4e0d\u592a\u786e\u5b9a\u600e\u4e48\u56de\u7b54",
            "\u6362\u4e2a\u65b9\u5f0f\u95ee",
            "\u6ca1\u6709\u8fd4\u56de\u5185\u5bb9",
            "\u670d\u52a1\u7aef\u9519\u8bef",
            "\u5931\u8d25",
        ]
        if any(marker in text for marker in bad_markers):
            return ""
        for prefix in ("AI:", "\u6211\uff1a", "\u684c\u5ba0\uff1a", "\u52a9\u624b\uff1a"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        if "\n" in text:
            text = text.splitlines()[0].strip()
        if len(text) > 34:
            text = text[:33] + "\u2026"
        return text

    def _finish_contextual_idle_speech(self, reply: str) -> None:
        self._idle_thought_busy = False
        if self._dragging or self._hovering_pet or self._chat_busy:
            self.next_idle_speech_at = self._next_idle_speech_time()
            return
        self.set_pet_state(random.choice(["curious", "happy", "idle"]), 5, reply)

    def set_pet_state(self, state: str, seconds: float = 0.0, speech: str | None = None) -> None:
        if state not in PET_STATES:
            state = "idle"
        self.pet_state = state
        self.state_until = time.time() + seconds if seconds else 0.0
        self.motion_override = PET_STATES[state][1]
        self.motion_override_until = self.state_until
        if speech is not None:
            self.speech = self._short_bubble_text(speech)
            self.speech_until = time.time() + max(seconds, 3.0)
        self.draw()

    def _short_bubble_text(self, text: str, limit: int = 42) -> str:
        compact = " ".join(text.strip().split())
        if not compact:
            return ""
        font = tkfont.Font(family="Microsoft YaHei", size=max(8, int(10 * self.scale)))
        return self._wrap_text_pixels(compact, font, int(132 * self.scale), max_lines=3, char_limit=limit)

    def _wrap_text_pixels(
        self,
        text: str,
        font: tkfont.Font,
        max_width: int,
        *,
        max_lines: int = 3,
        char_limit: int = 70,
    ) -> str:
        compact = " ".join((text or "").strip().split())
        if len(compact) > char_limit:
            compact = compact[: char_limit - 1] + "\u2026"
        lines: list[str] = []
        current = ""
        for ch in compact:
            candidate = current + ch
            if current and font.measure(candidate) > max_width:
                lines.append(current.rstrip())
                current = ch.lstrip()
                if len(lines) >= max_lines:
                    break
            else:
                current = candidate
        if len(lines) < max_lines and current:
            lines.append(current.rstrip())
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        if lines and (len(lines) == max_lines) and "".join(lines) != compact:
            while lines[-1] and font.measure(lines[-1] + "\u2026") > max_width:
                lines[-1] = lines[-1][:-1]
            lines[-1] = lines[-1].rstrip() + "\u2026"
        return "\n".join(lines)

    def on_hover_enter(self, _event=None) -> None:
        self._hovering_pet = True
        self._cancel_hide_chat()
        if not self._chat_busy:
            self.set_pet_state("curious", 2.5, "\u6211\u5728\uff0c\u60f3\u804a\u70b9\u4ec0\u4e48\uff1f")
        self.next_idle_speech_at = self._next_idle_speech_time()
        self.show_chat_panel()

    def on_hover_leave(self, _event=None) -> None:
        self._hovering_pet = False
        self._schedule_hide_chat()

    def _cancel_hide_chat(self) -> None:
        if self._hide_chat_after_id:
            self.root.after_cancel(self._hide_chat_after_id)
            self._hide_chat_after_id = None

    def _schedule_hide_chat(self) -> None:
        self._cancel_hide_chat()
        self._hide_chat_after_id = self.root.after(900, self._hide_chat_if_idle)

    def _hide_chat_if_idle(self) -> None:
        self._hide_chat_after_id = None
        if self._hovering_pet or self._chat_busy:
            return
        if self.chat_win and self.chat_win.winfo_exists():
            focused = self.root.focus_get()
            if focused and str(focused).startswith(str(self.chat_win)):
                self._schedule_hide_chat()
                return
            self.chat_win.withdraw()

    def show_chat_panel(self, focus: bool = True) -> None:
        if self.chat_win and self.chat_win.winfo_exists():
            self._position_chat_panel()
            self.chat_win.deiconify()
            if focus:
                self.root.after_idle(lambda: self.chat_entry and self.chat_entry.focus_set())
            return

        win = tk.Toplevel(self.root)
        self.chat_win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#d9dee7")

        frame = tk.Frame(win, bg="#ffffff", highlightthickness=1, highlightbackground="#d9dee7")
        frame.pack(fill="both", expand=True)

        log_frame = tk.Frame(frame, bg="#ffffff")
        log_frame.pack(fill="both", expand=True, padx=8, pady=(8, 6))
        self.chat_log = tk.Text(
            log_frame,
            height=7,
            wrap="word",
            font=("Microsoft YaHei", 9),
            bg="#ffffff",
            fg="#243143",
            relief="flat",
            bd=0,
            padx=2,
            pady=2,
            cursor="arrow",
        )
        scroll = tk.Scrollbar(log_frame, orient="vertical", command=self.chat_log.yview)
        self.chat_log.configure(yscrollcommand=scroll.set)
        self.chat_log.tag_configure("user", justify="right", foreground="#1f5bbf", lmargin1=32, lmargin2=32, rmargin=8, spacing1=3, spacing3=3)
        self.chat_log.tag_configure("assistant", justify="left", foreground="#0b5f49", lmargin1=8, lmargin2=8, rmargin=32, spacing1=3, spacing3=3)
        self.chat_log.tag_configure("system", justify="center", foreground="#657184", spacing1=4, spacing3=4)
        self.chat_log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._append_chat_line("", "\u628a\u9f20\u6807\u653e\u5728\u6211\u8eab\u4e0a\u5c31\u80fd\u804a\u5929\u3002", role="system")

        row = tk.Frame(frame, bg="#ffffff")
        row.pack(fill="x", padx=8, pady=(0, 8))
        self.chat_entry = tk.Entry(row, font=("Microsoft YaHei", 10), relief="flat", bg="#f5f7fa", fg="#243143")
        self.chat_entry.pack(side="left", fill="x", expand=True, ipady=5)
        send_btn = tk.Button(
            row,
            text="\u27a4",
            command=self.send_hover_chat,
            bg="#276ef1",
            fg="white",
            activebackground="#1d5dc7",
            relief="flat",
            width=3,
            padx=8,
            cursor="hand2",
        )
        send_btn.pack(side="left", padx=(6, 0))

        for widget in (win, frame, log_frame, self.chat_log, scroll, row, self.chat_entry, send_btn):
            widget.bind("<Enter>", lambda _e: self._cancel_hide_chat())
            widget.bind("<Leave>", lambda _e: self._schedule_hide_chat())
        self.chat_entry.bind("<Return>", lambda _e: self.send_hover_chat())
        self._position_chat_panel()
        if focus:
            self.root.after_idle(lambda: self.chat_entry and self.chat_entry.focus_set())

    def _position_chat_panel(self) -> None:
        if not self.chat_win or not self.chat_win.winfo_exists():
            return
        x = max(0, self.root.winfo_x() - 306)
        y = max(0, self.root.winfo_y() + 12)
        self.chat_win.geometry(f"306x220+{x}+{y}")

    def send_hover_chat(self) -> None:
        if not self.chat_entry or self._chat_busy:
            return
        message = self.chat_entry.get().strip()
        if not message:
            return
        self.chat_entry.delete(0, "end")
        self._chat_busy = True
        self.next_idle_speech_at = self._next_idle_speech_time()
        self._append_chat_line("你", message, role="user")
        self.set_pet_state("thinking", 0, "我想一下…")
        # Keep chat panel visible while thinking
        self.show_chat_panel()

        def _run() -> None:
            try:
                from hybrid_chat import get_hybrid_chatbot
                reply, _source = get_hybrid_chatbot().chat(message, self.chat_history[-6:])
            except Exception as exc:
                reply = f"对话模块未就绪：{exc}"
            self.root.after(0, lambda: self._finish_hover_chat(message, reply))

        threading.Thread(target=_run, daemon=True).start()

    def _finish_hover_chat(self, message: str, reply: str) -> None:
        self._chat_busy = False
        self.chat_history.append((message, reply))
        self.next_idle_speech_at = self._next_idle_speech_time()
        self._append_chat_line("\u6211", reply, role="assistant")
        self.set_pet_state("happy", 4, reply)
        self.show_chat_panel()
        if self.chat_entry:
            self.chat_entry.focus_set()

    def _append_chat_line(self, who: str, text: str, role: str = "assistant") -> None:
        if not self.chat_log:
            return
        font = tkfont.Font(family="Microsoft YaHei", size=9)
        short = self._wrap_text_pixels(text, font, 238, max_lines=4, char_limit=150)
        line = short if not who else f"{who}: {short}"
        self.chat_log.configure(state="normal")
        if self._hover_chat_intro_visible and role != "system":
            self.chat_log.delete("1.0", "end")
            self._hover_chat_intro_visible = False
        self.chat_log.insert("end", line + "\n", role)
        while int(self.chat_log.index("end-1c").split(".", 1)[0]) > 28:
            self.chat_log.delete("1.0", "2.0")
        self.chat_log.see("end")
        self.chat_log.configure(state="disabled")

    def _active_state(self) -> str:
        if self._chat_busy or self._idle_thought_busy:
            return "thinking"
        if self.state_until and time.time() > self.state_until:
            self.pet_state = "curious" if self._hovering_pet else "idle"
            self.state_until = 0.0
        return self.pet_state

    def draw_state_badge(self) -> None:
        state = self._active_state()
        label, _motion, color = PET_STATES.get(state, PET_STATES["idle"])
        self.round_rect(52, 186, 128, 210, 12, fill="#ffffff", outline="#d9dee7", width=1)
        self.canvas.create_oval(64, 195, 72, 203, fill=color, outline="")
        self.canvas.create_text(94, 199, text=label, fill="#243143", font=("Microsoft YaHei", 9, "bold"))

    def motion_offset(self) -> tuple[float, float, float]:
        t = self.frame / 12
        now = time.time()
        if self._dragging:
            lift = -14 - min(10, self._drag_speed * 0.35)
            sway = max(-10, min(10, (self._mouse_x - 90 * self.scale) / max(1, 11 * self.scale)))
            bob = -4 * abs(math.sin(t * 2.2))
            return sway, lift + bob, sway * 0.45
        if now < self._release_bounce_until:
            progress = 1 - (self._release_bounce_until - now) / 0.42
            bounce = 8 * math.sin(progress * math.pi * 2) * (1 - progress)
            return 0, bounce, 0
        if now < self._pickup_until:
            progress = 1 - (self._pickup_until - now) / 0.28
            return 0, -10 * math.sin(progress * math.pi), 0
        if self.motion == "nod":
            return 0, 8 * math.sin(t), 0
        if self.motion == "happy":
            return 0, -7 * abs(math.sin(t)), 0
        if self.motion == "thinking":
            return 0, 0, -5 * math.sin(t)
        if self.motion == "encourage":
            return 0, -3 * math.sin(t), 0
        if self.motion == "celebrate":
            return 8 * math.sin(t * 1.3), -10 * abs(math.sin(t)), 0
        if self.motion == "read":
            return 7 * math.sin(t), 0, 0
        if self.motion == "scan":
            return 0, 0, 0
        if self.motion == "spark":
            return 0, -4 * abs(math.sin(t * 1.5)), 0
        return 0, 2 * math.sin(t / 2), 0

    # ------------------------------------------------------------------
    # drawing (unchanged)
    # ------------------------------------------------------------------

    def _mouse_follow_offset(self, cx: float, cy: float) -> tuple[float, float]:
        if time.time() > self._mouse_seen_until:
            return 0.0, 0.0
        dx = (self._mouse_x - cx) / max(1, 54 * self.scale)
        dy = (self._mouse_y - cy) / max(1, 54 * self.scale)
        dx = max(-1.0, min(1.0, dx))
        dy = max(-1.0, min(1.0, dy))
        return dx, dy

    def _update_drag_particles(self) -> None:
        if not self._drag_particles:
            return
        now = time.time()
        active: list[dict[str, float | str]] = []
        for particle in self._drag_particles:
            age = now - float(particle["born"])
            if age >= float(particle["life"]):
                continue
            particle["x"] = float(particle["x"]) + float(particle["vx"])
            particle["y"] = float(particle["y"]) + float(particle["vy"])
            active.append(particle)
        self._drag_particles = active

    def draw_drag_particles(self) -> None:
        now = time.time()
        for particle in self._drag_particles:
            age = now - float(particle["born"])
            life = max(0.01, float(particle["life"]))
            fade = max(0.0, 1.0 - age / life)
            size = float(particle["size"]) * (0.65 + fade * 0.55)
            x = float(particle["x"])
            y = float(particle["y"])
            color = str(particle["color"])
            self.canvas.create_oval(x - size, y - size, x + size, y + size, fill=color, outline="")

    def draw_pet(self, cx: float, cy: float) -> None:
        s = self.scale
        xoff, yoff, rot = self.motion_offset()
        cx += xoff * s
        cy += yoff * s
        follow_x, follow_y = self._mouse_follow_offset(cx, cy - 12 * s)
        head_x = cx + follow_x * 7 * s + rot * 0.8 * s
        head_y = cy + follow_y * 4 * s
        face_x = cx + follow_x * 10 * s + rot * 0.9 * s
        face_y = cy + follow_y * 5 * s
        eye_x = follow_x * 5 * s
        eye_y = follow_y * 3 * s
        blink = (self.frame % 90 in {0, 1, 2}) and not self._dragging
        squish = 1.0
        if self._dragging:
            squish = 0.94 + 0.04 * math.sin(self.frame / 3)

        if self.motion in {"scan", "spark", "celebrate"}:
            self.canvas.create_oval(head_x - 58*s, head_y - 70*s, head_x + 58*s, head_y + 48*s, fill="#dff8ef", outline="")

        self.canvas.create_oval(cx - 50*s, cy + 40*s, cx + 50*s, cy + 78*s, fill="#000000", outline="", stipple="gray25")
        self.round_rect(cx - 44*s, cy + 16*s, cx + 44*s, cy + 78*s * squish, 24*s, fill="#b7e4d2", outline="#243143", width=max(1, int(3*s)))
        self.canvas.create_line(cx - 30*s, cy + 24*s, cx - 48*s - rot*s, cy + 44*s, fill="#243143", width=max(1, int(3*s)))
        self.canvas.create_line(cx + 30*s, cy + 24*s, cx + 48*s - rot*s, cy + 44*s, fill="#243143", width=max(1, int(3*s)))
        if self._dragging:
            self.canvas.create_line(self._mouse_x, self._mouse_y, head_x, head_y - 54*s, fill="#8a5cf6", width=max(1, int(2*s)), dash=(3, 4))
            self.canvas.create_oval(self._mouse_x - 5*s, self._mouse_y - 5*s, self._mouse_x + 5*s, self._mouse_y + 5*s, fill="#ffffff", outline="#8a5cf6", width=max(1, int(2*s)))
        self.canvas.create_oval(head_x - 54*s, head_y - 62*s, head_x + 54*s, head_y + 34*s, fill="#263244", outline="#243143", width=max(1, int(3*s)))
        self.canvas.create_oval(face_x - 45*s, face_y - 48*s, face_x + 45*s, face_y + 44*s, fill="#fff4ea", outline="#243143", width=max(1, int(3*s)))
        self.canvas.create_arc(head_x - 50*s, head_y - 56*s, head_x + 50*s, head_y + 20*s, start=20, extent=140, fill="#263244", outline="#263244")

        if blink:
            self.canvas.create_line(face_x - 24*s, face_y - 8*s, face_x - 10*s, face_y - 8*s, fill="#243143", width=max(1, int(3*s)))
            self.canvas.create_line(face_x + 10*s, face_y - 8*s, face_x + 24*s, face_y - 8*s, fill="#243143", width=max(1, int(3*s)))
        else:
            self.canvas.create_oval(face_x - 27*s + eye_x, face_y - 16*s + eye_y, face_x - 15*s + eye_x, face_y - 2*s + eye_y, fill="#243143", outline="")
            self.canvas.create_oval(face_x + 15*s + eye_x, face_y - 16*s + eye_y, face_x + 27*s + eye_x, face_y - 2*s + eye_y, fill="#243143", outline="")

        if self._dragging or self.motion in {"happy", "celebrate", "spark"}:
            self.canvas.create_arc(face_x - 16*s, face_y + 4*s, face_x + 16*s, face_y + 24*s, start=200, extent=140, style="arc", outline="#243143", width=max(1, int(3*s)))
        elif self.motion == "thinking":
            self.canvas.create_line(face_x - 10*s, face_y + 14*s, face_x + 14*s, face_y + 10*s, fill="#243143", width=max(1, int(3*s)))
            self.canvas.create_text(head_x + 48*s, head_y - 58*s, text="?", fill="#276ef1", font=("Segoe UI", max(8, int(20*s)), "bold"))
        else:
            self.canvas.create_arc(face_x - 12*s, face_y + 5*s, face_x + 12*s, face_y + 18*s, start=200, extent=140, style="arc", outline="#243143", width=max(1, int(3*s)))

        if self.motion == "read":
            self.canvas.create_rectangle(cx + 26*s, cy + 28*s, cx + 70*s, cy + 58*s, fill="#ffffff", outline="#243143", width=max(1, int(2*s)))
            self.canvas.create_line(cx + 34*s, cy + 38*s, cx + 62*s, cy + 38*s, fill="#657184")
            self.canvas.create_line(cx + 34*s, cy + 48*s, cx + 58*s, cy + 48*s, fill="#657184")
        if self.motion == "encourage":
            self.canvas.create_text(cx, cy - 82*s, text="加油", fill="#0b7a55", font=("Microsoft YaHei", max(8, int(14*s)), "bold"))
    def draw_speech(self) -> None:
        if not self.speech or time.time() > self.speech_until:
            return
        s = self.scale
        lines = self.speech.splitlines()[:3]
        bubble_h = max(42, 24 + len(lines) * 15) * s
        self.round_rect(10*s, 8*s, 170*s, 8*s + bubble_h, 14*s, fill="#ffffff", outline="#d9dee7", width=max(1, int(2*s)))
        self.canvas.create_text(
            90*s,
            8*s + bubble_h / 2,
            text="\n".join(lines),
            fill="#243143",
            font=("Microsoft YaHei", max(8, int(10*s))),
            justify="center",
            width=144*s,
        )

    def round_rect(self, x1: float, y1: float, x2: float, y2: float, r: float, **kwargs) -> None:
        fill = kwargs.get("fill", "")
        outline = kwargs.get("outline", "")
        width = kwargs.get("width", 1)
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill)
        self.canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline=fill)
        self.canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline=fill)
        self.canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline=fill)
        self.canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline=fill)
        if outline:
            self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="arc", outline=outline, width=width)
            self.canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width)
            self.canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width)
            self.canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width)
            self.canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width)

    def draw(self) -> None:
        self.canvas.delete("all")
        self._update_drag_particles()
        self.draw_drag_particles()
        if not self.model_layer:
            self.draw_pet(90 * self.scale, 96 * self.scale)
        self.draw_speech()
        # self.draw_state_badge()  # hidden

    def tick(self) -> None:
        if not self._dragging:
            self._sync_pet_talk_bus()
            self._poll_realtime_chat()
            self._maybe_start_auto_pet_conversation()
            self._maybe_show_routine_reminder()
            self.maybe_idle_speech()
            avatar = self.load_avatar()
            if self.motion_override_until and time.time() <= self.motion_override_until:
                self.motion = self.motion_override
            elif self._chat_busy or self._idle_thought_busy:
                self.motion = "thinking"
            elif self._hovering_pet:
                self.motion = PET_STATES[self._active_state()][1]
            else:
                self.motion = avatar.get("last_motion", "idle")
            self.frame += 1
            self.draw()
            if self.model_layer:
                self.model_layer.sync(self.root.state() != "withdrawn")
            if self.chat_win and self.chat_win.winfo_exists() and self.chat_win.state() != "withdrawn":
                self._position_chat_panel()
        else:
            self.motion = "happy"
            self.frame += 1
            self.draw()
            if self.chat_win and self.chat_win.winfo_exists() and self.chat_win.state() != "withdrawn":
                self._position_chat_panel()
        self.root.after(80, self.tick)

    def _maybe_show_routine_reminder(self) -> None:
        now = time.time()
        if now < self._next_routine_check_at:
            return
        self._next_routine_check_at = now + 30
        try:
            routine_tick()
            reminder = pop_due_reminder()
        except Exception:
            return
        if reminder:
            self.set_pet_state("curious", 12, reminder[:260])

    # ------------------------------------------------------------------
    # context menu
    # ------------------------------------------------------------------

    def show_menu(self, event) -> None:
        now = time.time()
        if now - self._last_menu_popup_at < 0.18:
            return "break"
        self._last_menu_popup_at = now
        self._close_ctx_menu()
        menu = tk.Menu(self.root, tearoff=0, font=('Microsoft YaHei', 10))
        self._ctx_menu = menu
        menu.add_command(label='对话', command=self.open_full_chat)
        menu.add_command(label='实时对话', command=self.open_realtime_prompt)
        menu.add_command(label='和其他桌宠说话', command=self.start_pet_conversation)
        menu.add_command(label='打开网页', command=self.open_web)
        menu.add_command(label='Live2D', command=self.open_live2d)
        menu.add_command(label='设置', command=self.open_settings)
        menu.add_separator()
        size_menu = tk.Menu(menu, tearoff=0)
        for pct in (75, 100, 125, 150, 200):
            label = f'{pct}%' + (' ' if pct == int(self.scale * 100) else '')
            size_menu.add_command(label=label, command=lambda s=pct/100: self._set_scale(s))
        menu.add_cascade(label='大小', menu=size_menu)
        menu.add_command(label='取消贴边隐藏' if self._edge_hidden else '贴边隐藏', command=self.toggle_edge_hide)
        topmost_label = '  置顶' + (' ' if self._topmost else '')
        menu.add_command(label=topmost_label, command=self._toggle_topmost)
        autostart_label = '  开机自启' + (' ' if is_autostart_enabled() else '')
        menu.add_command(label=autostart_label, command=self._toggle_autostart)
        menu.add_separator()
        menu.add_command(label='退出', command=self.close)
        x = getattr(event, "x_root", None)
        y = getattr(event, "y_root", None)
        if not x or not y:
            x = self.root.winfo_x() + int(80 * self.scale)
            y = self.root.winfo_y() + int(90 * self.scale)
        try:
            menu.tk_popup(x, y)
        except tk.TclError:
            pass
        return "break"

    def _close_ctx_menu(self) -> None:
        if self._ctx_menu is not None:
            try:
                self._ctx_menu.unpost()
            except Exception:
                pass
        self._ctx_menu = None
        self._full_chat_win = None

    def open_web(self) -> None:
        webbrowser.open(WEB_URL)

    def open_realtime_prompt(self) -> None:
        webbrowser.open(WEB_URL + "/?realtime_prompt=1")
        self.set_pet_state("listening", 4, "我把实时对话页面打开了，先确认要不要叠加识别。")

    def open_live2d(self) -> None:
        webbrowser.open(WEB_URL + "/live2d")

    # ------------------------------------------------------------------
    # full chat window (double-click pet to open)
    # ------------------------------------------------------------------

    def _is_ai_configured(self) -> bool:
        """Check if AI is configured by checking identity via HTTP."""
        try:
            import urllib.request
            req = urllib.request.Request(WEB_URL + "/api/identity", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                import json
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("setup_done", False)
        except Exception:
            return False

    def open_full_chat(self) -> None:
        # If AI not configured, open web page for setup instead
        if not self._is_ai_configured():
            webbrowser.open(WEB_URL)
            return

        if self._full_chat_win and self._full_chat_win.winfo_exists():
            self._full_chat_win.lift()
            self._full_chat_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        self._full_chat_win = win
        win.title("智能伙伴 对话")
        win.geometry("360x420")
        win.attributes("-topmost", True)
        win.configure(bg="#f5f7fa")
        win.protocol("WM_DELETE_WINDOW", self._close_full_chat)

        # Header
        header = tk.Frame(win, bg="#276ef1", height=36)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=" 对话", font=("Microsoft YaHei", 11, "bold"),
                 bg="#276ef1", fg="white").pack(side="left", padx=12)
        tk.Button(header, text="", command=self._close_full_chat,
                  bg="#276ef1", fg="white", relief="flat", font=("", 12),
                  cursor="hand2", activebackground="#1d5dc7").pack(side="right", padx=8)

        # Chat log (Text widget for scrollable history)
        log_frame = tk.Frame(win, bg="#f5f7fa")
        log_frame.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._full_chat_text = tk.Text(
            log_frame, font=("Microsoft YaHei", 10), bg="#ffffff", fg="#243143",
            relief="flat", wrap="word", state="disabled", padx=10, pady=8,
            highlightthickness=1, highlightbackground="#d9dee7",
        )
        self._full_chat_text.pack(fill="both", expand=True)
        self._full_chat_text.tag_configure("user", foreground="#276ef1", font=("Microsoft YaHei", 10, "bold"))
        self._full_chat_text.tag_configure("ai", foreground="#0b7a55", font=("Microsoft YaHei", 10, "bold"))
        self._full_chat_text.tag_configure("body", foreground="#243143", font=("Microsoft YaHei", 10))

        # Show existing chat history
        for user_msg, ai_msg in self.chat_history[-10:]:
            self._append_full_chat_line("你", user_msg)
            self._append_full_chat_line("我", ai_msg)

        # Input row
        input_frame = tk.Frame(win, bg="#f5f7fa")
        input_frame.pack(fill="x", padx=8, pady=(4, 8))
        self._full_chat_entry = tk.Entry(
            input_frame, font=("Microsoft YaHei", 11), relief="flat",
            bg="#ffffff", fg="#243143",
            highlightthickness=1, highlightbackground="#d9dee7",
        )
        self._full_chat_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self._full_chat_entry.bind("<Return>", lambda _e: self._send_full_chat())
        send_btn = tk.Button(
            input_frame, text="发送", command=self._send_full_chat,
            bg="#276ef1", fg="white", activebackground="#1d5dc7",
            relief="flat", padx=14, cursor="hand2", font=("Microsoft YaHei", 10),
        )
        send_btn.pack(side="right", padx=(6, 0))

        win.focus_force()
        self._full_chat_entry.focus_set()
        self.set_pet_state("curious", 3, "我在，说吧！")

    def _close_full_chat(self) -> None:
        if self._full_chat_win and self._full_chat_win.winfo_exists():
            self._full_chat_win.destroy()
        self._full_chat_win = None

    def _append_full_chat_line(self, who: str, text: str) -> None:
        if not hasattr(self, '_full_chat_text') or not self._full_chat_text.winfo_exists():
            return
        self._full_chat_text.config(state="normal")
        tag = "user" if who == "你" else "ai"
        self._full_chat_text.insert("end", f"{who}: ", tag)
        self._full_chat_text.insert("end", text + chr(10) + chr(10), "body")
        self._full_chat_text.see("end")
        self._full_chat_text.config(state="disabled")

    def _send_full_chat(self) -> None:
        if not hasattr(self, '_full_chat_entry') or not self._full_chat_entry:
            return
        message = self._full_chat_entry.get().strip()
        if not message:
            return
        self._full_chat_entry.delete(0, "end")
        self._chat_busy = True
        self._append_full_chat_line("你", message)
        self.set_pet_state("thinking", 0, "我想想…")

        def _run() -> None:
            try:
                from hybrid_chat import get_hybrid_chatbot
                reply, _source = get_hybrid_chatbot().chat(message, self.chat_history[-6:])
            except Exception as exc:
                reply = f"对话模块未就绪：{exc}"
            self.root.after(0, lambda: self._finish_full_chat(message, reply))

        threading.Thread(target=_run, daemon=True).start()

    def _finish_full_chat(self, message: str, reply: str) -> None:
        self._chat_busy = False
        self.chat_history.append((message, reply))
        self._append_full_chat_line("我", reply)
        self.set_pet_state("happy", 4, reply)
        if self._full_chat_win and self._full_chat_win.winfo_exists():
            self._full_chat_entry.focus_set()

    # ------------------------------------------------------------------
    # settings window
    # ------------------------------------------------------------------

    def open_settings(self) -> None:
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("\u8bbe\u7f6e")
        win.geometry("380x460")
        win.attributes("-topmost", True)
        win.configure(bg="#f5f7fa")
        win.resizable(False, False)

        # title
        tk.Label(
            win, text="Companion AI \u8bbe\u7f6e",
            font=("Microsoft YaHei", 14, "bold"), bg="#f5f7fa", fg="#243143",
        ).pack(pady=(16, 10))

        # ---- OCR section ----
        tk.Label(
            win, text="\u2501 OCR \u6587\u5b57\u8bc6\u522b",
            font=("Microsoft YaHei", 11, "bold"), bg="#f5f7fa", fg="#243143", anchor="w",
        ).pack(fill="x", padx=20, pady=(4, 2))

        self.ocr_status_lbl = tk.Label(
            win, text="\u68c0\u6d4b\u4e2d\u2026",
            font=("Microsoft YaHei", 9), bg="#f5f7fa", fg="#657184", anchor="w", wraplength=340, justify="left",
        )
        self.ocr_status_lbl.pack(fill="x", padx=20)

        ocr_frame = tk.Frame(win, bg="#f5f7fa")
        ocr_frame.pack(fill="x", padx=20, pady=(4, 8))
        self.ocr_install_btn = tk.Button(
            ocr_frame, text="\u5b89\u88c5 OCR", command=self._install_ocr,
            bg="#276ef1", fg="white", activebackground="#1d5dc7",
            font=("Microsoft YaHei", 10), relief="flat", padx=14, pady=3, cursor="hand2",
        )
        self.ocr_install_btn.pack(side="left")

        # ---- Neural network section ----
        tk.Label(
            win, text="\u2501 \u795e\u7ecf\u7f51\u7edc (PyTorch)",
            font=("Microsoft YaHei", 11, "bold"), bg="#f5f7fa", fg="#243143", anchor="w",
        ).pack(fill="x", padx=20, pady=(12, 2))

        self.torch_status_lbl = tk.Label(
            win, text="\u68c0\u6d4b\u4e2d\u2026",
            font=("Microsoft YaHei", 9), bg="#f5f7fa", fg="#657184", anchor="w", wraplength=340, justify="left",
        )
        self.torch_status_lbl.pack(fill="x", padx=20)

        torch_frame = tk.Frame(win, bg="#f5f7fa")
        torch_frame.pack(fill="x", padx=20, pady=(4, 8))
        self.torch_install_btn = tk.Button(
            torch_frame, text="\u5b89\u88c5 PyTorch", command=self._install_torch,
            bg="#276ef1", fg="white", activebackground="#1d5dc7",
            font=("Microsoft YaHei", 10), relief="flat", padx=14, pady=3, cursor="hand2",
        )
        self.torch_install_btn.pack(side="left")

        # ---- ZLUDA section ----
        tk.Label(
            win, text="\u2501 ZLUDA (AMD/Intel GPU \u52a0\u901f)",
            font=("Microsoft YaHei", 11, "bold"), bg="#f5f7fa", fg="#243143", anchor="w",
        ).pack(fill="x", padx=20, pady=(12, 2))

        self.zluda_status_lbl = tk.Label(
            win, text="\u68c0\u6d4b\u4e2d\u2026",
            font=("Microsoft YaHei", 9), bg="#f5f7fa", fg="#657184", anchor="w", wraplength=340, justify="left",
        )
        self.zluda_status_lbl.pack(fill="x", padx=20)

        zluda_frame = tk.Frame(win, bg="#f5f7fa")
        zluda_frame.pack(fill="x", padx=20, pady=(4, 8))
        self.zluda_install_btn = tk.Button(
            zluda_frame, text="\u5b89\u88c5 ZLUDA", command=self._install_zluda,
            bg="#276ef1", fg="white", activebackground="#1d5dc7",
            font=("Microsoft YaHei", 10), relief="flat", padx=14, pady=3, cursor="hand2",
        )
        self.zluda_install_btn.pack(side="left")

        # ---- Datasets section ----
        tk.Label(
            win, text="\u2501 数据集工具 (ModelScope + Datasets)",
            font=("Microsoft YaHei", 11, "bold"), bg="#f5f7fa", fg="#243143", anchor="w",
        ).pack(fill="x", padx=20, pady=(12, 2))

        self.datasets_status_lbl = tk.Label(
            win, text="\u68c0\u6d4b\u4e2d\u2026",
            font=("Microsoft YaHei", 9), bg="#f5f7fa", fg="#657184", anchor="w", wraplength=340, justify="left",
        )
        self.datasets_status_lbl.pack(fill="x", padx=20)

        datasets_frame = tk.Frame(win, bg="#f5f7fa")
        datasets_frame.pack(fill="x", padx=20, pady=(4, 8))
        self.datasets_install_btn = tk.Button(
            datasets_frame, text="\u5b89\u88c5", command=self._install_datasets,
            bg="#276ef1", fg="white", activebackground="#1d5dc7",
            font=("Microsoft YaHei", 10), relief="flat", padx=14, pady=3, cursor="hand2",
        )
        self.datasets_install_btn.pack(side="left")
        self.datasets_uninstall_btn = tk.Button(
            datasets_frame, text="\u5220\u9664", command=self._uninstall_datasets,
            bg="#e74c3c", fg="white", activebackground="#c0392b",
            font=("Microsoft YaHei", 10), relief="flat", padx=14, pady=3, cursor="hand2",
        )
        self.datasets_uninstall_btn.pack(side="left", padx=(8, 0))

        # ---- close ----
        tk.Button(
            win, text="\u5173\u95ed", command=win.destroy,
            font=("Microsoft YaHei", 10), relief="flat", padx=20, pady=3,
        ).pack(pady=(12, 8))

        # refresh status labels after window is mapped
        win.after(120, self._refresh_settings)

    def _refresh_settings(self) -> None:
        ok, detail = _check_ocr_status()
        self.ocr_status_lbl.config(
            text=("\u2705 " + detail) if ok else ("\u274c " + detail),
            fg="#0b7a55" if ok else "#c0392b",
        )
        self.ocr_install_btn.config(state="normal" if not ok else "disabled")

        ok, detail = _check_torch_status()
        # 获取GPU推荐信息并显示在状态中
        gpu_info = _detect_gpu_detail()
        gpu_brand = gpu_info.get("gpu_brand", "unknown")
        gpu_name = gpu_info.get("gpu_name", "未知")
        gfx_target = gpu_info.get("gfx_target")

        if ok:
            status_text = f"\u2705 {detail}"
        else:
            # 显示GPU检测和推荐信息
            if gpu_brand == "AMD" and os.name == "nt":
                status_text = f"\u274c {detail}\n\n\U0001f4a1 检测到AMD GPU: {gpu_name}\n   点击安装将自动下载 DirectML 版本"
            elif gpu_brand == "AMD" and gfx_target:
                status_text = f"\u274c {detail}\n\n\U0001f4a1 检测到AMD GPU: {gpu_name}\n   GFX架构: {gfx_target}\n   点击安装将自动下载ROCm nightly版本"
            elif gpu_brand == "NVIDIA":
                status_text = f"\u274c {detail}\n\n\U0001f4a1 检测到NVIDIA GPU: {gpu_name}\n   点击安装将自动下载CUDA版本"
            elif gpu_brand == "Intel" and os.name == "nt":
                status_text = f"\u274c {detail}\n\n\U0001f4a1 检测到Intel GPU: {gpu_name}\n   点击安装将自动下载 DirectML 版本"
            elif gpu_brand == "Intel":
                status_text = f"\u274c {detail}\n\n\U0001f4a1 检测到Intel GPU: {gpu_name}\n   建议安装CPU版本"
            else:
                status_text = f"\u274c {detail}\n\n\U0001f4a1 未检测到独立GPU\n   将安装CPU版本"

        self.torch_status_lbl.config(
            text=status_text,
            fg="#0b7a55" if ok else "#c0392b",
        )
        self.torch_install_btn.config(state="normal" if not ok else "disabled")

        ok, detail = _check_zluda_status()
        self.zluda_status_lbl.config(
            text=("\u2705 " + detail) if ok else ("\u274c " + detail),
            fg="#0b7a55" if ok else "#c0392b",
        )
        self.zluda_install_btn.config(state="normal" if not ok else "disabled")

        ok, detail = _check_datasets_status()
        self.datasets_status_lbl.config(
            text=("\u2705 " + detail) if ok else ("\u274c " + detail),
            fg="#0b7a55" if ok else "#c0392b",
        )
        self.datasets_install_btn.config(state="normal" if not ok else "disabled")
        self.datasets_uninstall_btn.config(state="normal" if ok else "disabled")

    # ---- OCR install ----

    def _install_ocr(self) -> None:
        self.ocr_install_btn.config(state="disabled", text="\u5b89\u88c5\u4e2d\u2026")
        self.ocr_status_lbl.config(text="\u6b63\u5728\u5b89\u88c5 OCR\uff0c\u8bf7\u7a0d\u5019\u2026", fg="#657184")

        def _run() -> None:
            try:
                from app import install_portable_ocr
                result = install_portable_ocr()
                success = "未安装" not in result and "失败" not in result
            except Exception as exc:
                result = str(exc)
                success = False
            self.root.after(0, lambda: self._on_ocr_done(result, success))

        threading.Thread(target=_run, daemon=True).start()

    def _on_ocr_done(self, result: str, success: bool) -> None:
        if success:
            self.ocr_status_lbl.config(text="\u2705 OCR \u5b89\u88c5\u5b8c\u6210", fg="#0b7a55")
        else:
            self.ocr_status_lbl.config(text=f"\u274c \u5b89\u88c5\u5931\u8d25: {result[:120]}", fg="#c0392b")
        self.ocr_install_btn.config(text="\u5b89\u88c5 OCR")
        self._refresh_settings()

    # ---- Python not found helper ----

    def _show_python_missing_dialog(self, detail: str) -> None:
        """Show a dialog when no Python interpreter is found."""
        from tkinter import messagebox
        msg = detail + "\n\n是否自动下载并安装 Python 3.12？\n（需要管理员权限，安装过程约 5-15 分钟）"
        if messagebox.askyesno("未检测到 Python", msg, parent=self.root):
            from _paths import download_and_install_python
            self._status("正在下载并安装 Python 3.12...", "info")
            try:
                result = download_and_install_python(install=True)
                self._status(result["message"], "ok" if result["ok"] else "err")
            except Exception as exc:
                self._status(f"Python 安装失败：{exc}", "err")

    # ---- PyTorch install (auto-detect GPU and install appropriate version) ----

    def _install_torch(self) -> None:
        # Check Python availability before starting
        try:
            python = runtime_python_exe()
        except RuntimeError as exc:
            self._show_python_missing_dialog(str(exc))
            return

        # 获取GPU推荐信息
        gpu_info = _detect_gpu_detail()
        gpu_brand = gpu_info.get("gpu_brand", "unknown")
        gfx_target = gpu_info.get("gfx_target")
        index_url = gpu_info.get("index_url", "")
        install_cmd = gpu_info.get("install_command", "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu")

        # 根据GPU类型确定安装版本
        if gpu_brand in {"AMD", "Intel"} and os.name == "nt":
            install_version = "DirectML"
            pip_args = [[
                python, "-m", "pip", "install",
                "--upgrade", "--force-reinstall",
                "torch", "torchvision",
                "--index-url", "https://download.pytorch.org/whl/cpu",
            ], [
                python, "-m", "pip", "install",
                "--upgrade", "--force-reinstall",
                "torch-directml",
            ]]
        elif gpu_brand == "AMD" and gfx_target:
            install_version = f"ROCm nightly ({gfx_target})"
            pip_args = [
                python, "-m", "pip", "install",
                "--upgrade", "--force-reinstall",
                "--pre",
                f"torch[device-{gfx_target}]",
                f"torchvision[device-{gfx_target}]",
                "--index-url", "https://rocm.nightlies.amd.com/whl-multi-arch/"
            ]
        elif gpu_brand == "NVIDIA":
            install_version = "CUDA"
            pip_args = [python, "-m", "pip", "install", "--upgrade", "--force-reinstall", "torch", "torchvision", "--index-url", index_url]
        else:
            install_version = "CPU"
            pip_args = [
                python, "-m", "pip", "install",
                "--upgrade", "--force-reinstall",
                "torch", "torchvision",
                "--index-url", "https://download.pytorch.org/whl/cpu",
            ]

        self.torch_install_btn.config(state="disabled", text="\u5b89\u88c5\u4e2d\u2026")
        self.torch_status_lbl.config(
            text=f"\u6b63\u5728\u5b89\u88c5 PyTorch ({install_version})\uff0c\u8bf7\u7a0d\u5019\u2026",
            fg="#657184",
        )

        def _run() -> None:
            if install_version == "DirectML" or (gpu_brand == "AMD" and gfx_target and install_version.startswith("ROCm")):
                _uninstall_rocm_device_packages(python)
            if pip_args and isinstance(pip_args[0], list):
                proc = None
                for sub_args in pip_args:
                    proc = subprocess.run(
                        sub_args,
                        capture_output=True, text=True, timeout=900,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    if proc.returncode != 0:
                        break
            else:
                proc = subprocess.run(
                    pip_args,
                    capture_output=True, text=True, timeout=900,
                    creationflags=CREATE_NO_WINDOW,
                )
            ok = proc.returncode == 0
            detail = proc.stderr.strip() or proc.stdout.strip()
            if not ok and install_version != "CPU":
                fallback_args = [
                    python, "-m", "pip", "install",
                    "--upgrade", "--force-reinstall",
                    "torch", "torchvision",
                    "--index-url", "https://download.pytorch.org/whl/cpu",
                ]
                fallback = subprocess.run(
                    fallback_args,
                    capture_output=True, text=True, timeout=600,
                    creationflags=CREATE_NO_WINDOW,
                )
                if fallback.returncode == 0:
                    ok = True
                    detail = "GPU 版本安装失败，已回退安装 CPU 版本。"
                    install_label = "CPU"
                else:
                    detail = (
                        (detail or "GPU 版本安装失败")[:500]
                        + "\n\nCPU 回退也失败："
                        + ((fallback.stderr.strip() or fallback.stdout.strip())[:500])
                    )
                    install_label = install_version
            else:
                install_label = install_version
            self.root.after(0, lambda: self._on_torch_done(ok, detail, install_label))

        threading.Thread(target=_run, daemon=True).start()

    def _on_torch_done(self, success: bool, detail: str, install_version: str = "") -> None:
        if success:
            self.torch_status_lbl.config(text=f"\u2705 PyTorch ({install_version}) \u5b89\u88c5\u5b8c\u6210", fg="#0b7a55")
        else:
            short = _short_pip_error(detail, 180).replace("\n", " ")
            self.torch_status_lbl.config(text=f"\u274c \u5b89\u88c5\u5931\u8d25: {short}", fg="#c0392b")
        self.torch_install_btn.config(text="\u5b89\u88c5 PyTorch")
        # 延迟刷新状态，确保pip安装完全完成
        self.root.after(1500, self._refresh_settings)

    # ---- ZLUDA install ----

    def _install_zluda(self) -> None:
        gpu = _detect_gpu()
        if gpu == "NVIDIA":
            self.zluda_status_lbl.config(
                text="\u274c \u68c0\u6d4b\u5230 NVIDIA GPU\uff0cZLUDA \u4ec5\u9002\u7528\u4e8e AMD/Intel",
                fg="#c0392b",
            )
            return
        self.zluda_install_btn.config(state="disabled", text="\u4e0b\u8f7d\u4e2d\u2026")
        self.zluda_status_lbl.config(
            text=f"\u6b63\u5728\u4e0b\u8f7d ZLUDA ({gpu} GPU)\u2026",
            fg="#657184",
        )

        def _run() -> None:
            import urllib.request
            import zipfile
            import shutil
            try:
                ZLUDA_DIR.mkdir(parents=True, exist_ok=True)
                zip_path = ZLUDA_DIR / "zluda.zip"

                # download
                urllib.request.urlretrieve(ZLUDA_WIN_URL, str(zip_path))

                # extract
                with zipfile.ZipFile(str(zip_path), "r") as zf:
                    zf.extractall(str(ZLUDA_DIR))
                zip_path.unlink(missing_ok=True)

                # integrate with PyTorch: copy DLLs into torch/lib
                dll_dir = _zluda_dll_dir() or ZLUDA_DIR
                torch_dlls = list(dll_dir.glob("*.dll"))
                integrated = 0
                try:
                    probe = subprocess.run(
                        [
                            runtime_python_exe(create=False),
                            "-c",
                            "import pathlib, torch; print(pathlib.Path(torch.__file__).parent / 'lib')",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    torch_lib = Path(probe.stdout.strip()) if probe.returncode == 0 else None
                    if torch_lib and torch_lib.is_dir():
                        for dll in torch_dlls:
                            shutil.copy2(str(dll), str(torch_lib / dll.name))
                            integrated += 1
                except Exception:
                    pass

                ok = _zluda_dll_dir() is not None
                detail = f"ZLUDA \u5df2\u4e0b\u8f7d\u5230 {ZLUDA_DIR}"
                if integrated:
                    detail += f"\n\u5df2\u590d\u5236 {integrated} \u4e2a DLL \u5230 PyTorch"
                elif not torch_dlls:
                    detail += "\n\u672a\u627e\u5230 DLL \u6587\u4ef6"
                else:
                    detail += "\nPyTorch \u672a\u5b89\u88c5\uff0c\u8bf7\u5148\u5b89\u88c5 PyTorch"
            except Exception as exc:
                ok = False
                detail = str(exc)
            self.root.after(0, lambda: self._on_zluda_done(ok, detail))

        threading.Thread(target=_run, daemon=True).start()

    def _on_zluda_done(self, success: bool, detail: str) -> None:
        if success:
            self.zluda_status_lbl.config(text=f"\u2705 {detail}", fg="#0b7a55")
        else:
            self.zluda_status_lbl.config(text=f"\u274c {detail[:160]}", fg="#c0392b")
        self.zluda_install_btn.config(text="\u5b89\u88c5 ZLUDA")
        self._refresh_settings()

    # ---- Datasets install/uninstall ----

    def _install_datasets(self) -> None:
        self.datasets_install_btn.config(state="disabled", text="\u5b89\u88c5\u4e2d\u2026")
        self.datasets_uninstall_btn.config(state="disabled")
        self.datasets_status_lbl.config(text="\u6b63\u5728\u5b89\u88c5 ModelScope + Datasets\u2026", fg="#657184")

        def _run() -> None:
            try:
                from dependency_utils import install_dataset_dependencies

                status = install_dataset_dependencies()
                ok = status.ok
                detail = status.detail
                if ok:
                    detail = "安装完成：" + status.detail
            except Exception as exc:
                ok = False
                detail = _short_pip_error(str(exc))
            self.root.after(0, lambda: self._on_datasets_done(ok, detail, "install"))

        threading.Thread(target=_run, daemon=True).start()

    def _uninstall_datasets(self) -> None:
        self.datasets_install_btn.config(state="disabled")
        self.datasets_uninstall_btn.config(state="disabled", text="\u5220\u9664\u4e2d\u2026")
        self.datasets_status_lbl.config(text="\u6b63\u5728\u5220\u9664\u2026", fg="#657184")

        def _run() -> None:
            try:
                py = runtime_python_exe()
                from dependency_utils import DATASET_UNINSTALL_PACKAGES

                packages = DATASET_UNINSTALL_PACKAGES
                result = subprocess.run(
                    [py, "-m", "pip", "uninstall", "-y", *packages],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    creationflags=CREATE_NO_WINDOW,
                )
                ok = result.returncode == 0
                detail = "已卸载" if ok else (result.stderr or "卸载失败").strip()[:200]
            except Exception as exc:
                ok = False
                detail = str(exc)[:200]
            self.root.after(0, lambda: self._on_datasets_done(ok, detail, "uninstall"))

        threading.Thread(target=_run, daemon=True).start()

    def _on_datasets_done(self, success: bool, detail: str, action: str) -> None:
        if success:
            self.datasets_status_lbl.config(text=f"\u2705 {detail}", fg="#0b7a55")
        else:
            self.datasets_status_lbl.config(text=f"\u274c {detail}", fg="#c0392b")
        self.datasets_install_btn.config(text="\u5b89\u88c5")
        self.datasets_uninstall_btn.config(text="\u5220\u9664")
        self._refresh_settings()

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def _load_saved_display_mode() -> str:
    """Read the user's preferred display mode from pet_display.json."""
    try:
        import json as _json
        data = _json.loads(PET_DISPLAY_FILE.read_text(encoding="utf-8"))
        mode = data.get("mode", "auto")
        if mode in PET_STYLES:
            return mode
    except Exception:
        pass
    return PET_STYLE_AUTO


def _log_startup_error(context: str, exc: Exception) -> None:
    try:
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"pet_error_{datetime.now().strftime('%Y%m%d')}.log"
        import traceback
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {context}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


def _try_run_classic_fallback() -> None:
    try:
        print("[Companion AI] 经典桌宠已启动！如果看不到请按 Alt+Tab 查找")
        DesktopPet(PET_STYLE_CLASSIC).run()
    except Exception as exc:
        print(f"[Companion AI] 经典模式也失败了: {exc}")
        _log_startup_error("Classic pet fallback failed", exc)
        raise


def _run_shell_pet(style: str) -> None:
    try:
        print(f"[Companion AI] 启动统一桌宠外壳: {style}")
        DesktopPet(style).run()
    except Exception as exc:
        print(f"[Companion AI] 统一桌宠外壳启动失败: {exc}")
        _log_startup_error(f"Shell pet failed: {style}", exc)
        if style != PET_STYLE_CLASSIC:
            _try_run_classic_fallback()
        else:
            raise


def _electron_command() -> list[str] | None:
    main_js = ROOT / "electron_pet" / "main.cjs"
    direct_electron = ROOT / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
    electron_bin = ROOT / "node_modules" / ".bin" / ("electron.cmd" if os.name == "nt" else "electron")
    if not main_js.exists():
        return None
    if direct_electron.exists():
        return [str(direct_electron), str(main_js)]
    if electron_bin.exists():
        return [str(electron_bin), str(main_js)]
    return None


def _run_electron_pet(style: str) -> bool:
    cmd = _electron_command()
    if not cmd:
        return False
    style = style if style in (PET_STYLE_LIVE2D, PET_STYLE_3D) else PET_STYLE_LIVE2D
    DATA_DIR.joinpath("runtime").mkdir(parents=True, exist_ok=True)
    geometry_file = DATA_DIR / "runtime" / f"electron_pet_{os.getpid()}_{style}.json"
    initial = {
        "style": style,
        "url": WEB_URL + ("/3d?pet=1&shell=1" if style == PET_STYLE_3D else "/live2d?pet=1&shell=1"),
        "x": 500,
        "y": 300,
        "w": int(BASE_W),
        "h": int(BASE_H),
        "visible": True,
        "closed": False,
        "updated_at": time.time(),
    }
    try:
        geometry_file.write_text(json.dumps(initial), encoding="utf-8")
        print(f"[Companion AI] 启动 Electron 桌宠: {style}")
        proc = subprocess.Popen(
            [
                *cmd,
                "--style",
                style,
                "--geometry-file",
                str(geometry_file),
            ],
            cwd=str(ROOT),
            creationflags=CREATE_NO_WINDOW,
        )
        proc.wait()
        return True
    except Exception as exc:
        print(f"[Companion AI] Electron 桌宠启动失败: {exc}")
        _log_startup_error(f"Electron pet failed: {style}", exc)
        return False


def _run_visual_pet(style: str) -> None:
    if _run_electron_pet(style):
        return
    print("[Companion AI] Electron 不可用，回退到旧桌宠外壳...")
    _run_shell_pet(style)


def _print_startup_info(mode: str) -> None:
    print(f"[Companion AI] 正在启动桌宠... 模式: {mode}")
    print(f"[Companion AI] 提示: 关闭此窗口会同时关闭桌宠")
    print(f"[Companion AI] 如果看不到桌宠，请尝试按 Alt+Tab 切换窗口")
    print()


def _ensure_web_server() -> None:
    """Ensure the Companion AI web server is running.
    
    Live2D and 3D pet modes require the web server to serve the viewer pages.
    If the server is not already running on WEB_URL, start it in a subprocess.
    """
    import urllib.request
    try:
        req = urllib.request.Request(WEB_URL, method="GET")
        urllib.request.urlopen(req, timeout=2)
        return
    except Exception:
        pass

    print("[Companion AI] Web 服务器未运行，正在启动...")
    app_py = ROOT / "app.py"
    if not app_py.exists():
        print(f"[Companion AI] 警告: 找不到 app.py: {app_py}")
        return

    try:
        proc = subprocess.Popen(
            [python_exe(), str(app_py)],
            cwd=str(ROOT),
            creationflags=CREATE_NO_WINDOW,
        )
        # 等待服务器启动（最多 10 秒）
        for _ in range(50):
            time.sleep(0.2)
            try:
                req = urllib.request.Request(WEB_URL, method="GET")
                urllib.request.urlopen(req, timeout=1)
                print("[Companion AI] Web 服务器已启动")
                return
            except Exception:
                continue
        print("[Companion AI] 警告: Web 服务器启动超时，可能无法正常显示桌宠")
    except Exception as exc:
        print(f"[Companion AI] 启动 Web 服务器失败: {exc}")


def main(style: str = PET_STYLE_AUTO) -> None:
    style = style if style in PET_STYLES else PET_STYLE_AUTO
    global _active_pet_style
    _active_pet_style = style

    _print_startup_info(style)

    # Live2D 和 3D 模式需要 Web 服务器提供 viewer 页面
    if style in (PET_STYLE_LIVE2D, PET_STYLE_3D, PET_STYLE_AUTO):
        _ensure_web_server()

    try:
        if style == PET_STYLE_3D:
            if _active_3d_model():
                _run_visual_pet(PET_STYLE_3D)
            else:
                print("[Companion AI] 没有可用 3D 模型，回退到经典模式...")
                _try_run_classic_fallback()
            return

        if style == PET_STYLE_LIVE2D:
            if _active_live2d_model():
                _run_visual_pet(PET_STYLE_LIVE2D)
            else:
                print("[Companion AI] 没有可用 Live2D 模型，回退到经典模式...")
                _try_run_classic_fallback()
            return

        if style == PET_STYLE_CLASSIC:
            print("[Companion AI] 启动经典模式...")
            _try_run_classic_fallback()
            return

        # AUTO mode: read saved preference from settings
        saved_mode = _load_saved_display_mode()
        print(f"[Companion AI] 自动模式，已保存的偏好: {saved_mode}")

        if saved_mode == PET_STYLE_3D:
            if _active_3d_model():
                _run_visual_pet(PET_STYLE_3D)
                return
            if _active_live2d_model():
                _run_visual_pet(PET_STYLE_LIVE2D)
                return
            _try_run_classic_fallback()
            return

        if saved_mode == PET_STYLE_LIVE2D:
            if _active_live2d_model():
                _run_visual_pet(PET_STYLE_LIVE2D)
                return
            if _active_3d_model():
                _run_visual_pet(PET_STYLE_3D)
                return
            _try_run_classic_fallback()
            return

        if saved_mode == PET_STYLE_CLASSIC:
            print("[Companion AI] 启动经典模式...")
            _try_run_classic_fallback()
            return

        # Default auto: 3D -> Live2D -> Classic
        print("[Companion AI] 默认自动模式: 3D -> Live2D -> Classic")
        if _active_3d_model():
            _run_visual_pet(PET_STYLE_3D)
            return
        if _active_live2d_model():
            _run_visual_pet(PET_STYLE_LIVE2D)
            return
        _try_run_classic_fallback()
    except Exception as exc:
        print(f"[Companion AI] 致命错误: {exc}")
        _log_startup_error("Fatal: all pet modes failed", exc)


def _read_model_layer_state(path: Path, style: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {
        "style": style,
        "url": WEB_URL + ("/3d?pet=1" if style == PET_STYLE_3D else "/live2d?pet=1"),
        "x": 500,
        "y": 300,
        "w": int(BASE_W),
        "h": int(BASE_H),
        "visible": True,
        "closed": False,
    }


def run_model_layer_process(style: str, geometry_file: str) -> None:
    """Run the WebView model layer in its own main-thread process."""
    state_path = Path(geometry_file)
    style = style if style in (PET_STYLE_LIVE2D, PET_STYLE_3D) else PET_STYLE_LIVE2D
    state = _read_model_layer_state(state_path, style)
    url = str(state.get("url") or (WEB_URL + "/live2d?pet=1"))
    title = "Companion 3D Model Layer" if style == PET_STYLE_3D else "Companion Live2D Model Layer"
    try:
        import webview
    except Exception as exc:
        _log_startup_error(f"{style} model layer import failed", exc)
        return

    try:
        window = webview.create_window(
            title,
            url,
            width=max(120, int(state.get("w", BASE_W))),
            height=max(160, int(state.get("h", BASE_H))),
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color=TRANSPARENT_COLOR,
            shadow=False,
            x=int(state.get("x", 500)),
            y=int(state.get("y", 300)),
        )
    except TypeError:
        window = webview.create_window(
            title,
            url,
            width=max(120, int(state.get("w", BASE_W))),
            height=max(160, int(state.get("h", BASE_H))),
            frameless=True,
            easy_drag=False,
            on_top=True,
            background_color=TRANSPARENT_COLOR,
            x=int(state.get("x", 500)),
            y=int(state.get("y", 300)),
        )

    def _sync_loop() -> None:
        last_geometry = None
        last_visible = None
        last_cursor: tuple[int, int] | None = None
        last_cursor_sent_at = 0.0
        force_show_until = time.time() + 6
        while True:
            state = _read_model_layer_state(state_path, style)
            if state.get("closed"):
                try:
                    window.destroy()
                except Exception:
                    pass
                return
            geometry = (
                int(state.get("x", 500)),
                int(state.get("y", 300)),
                max(120, int(state.get("w", BASE_W))),
                max(160, int(state.get("h", BASE_H))),
            )
            visible = bool(state.get("visible", True))
            if geometry != last_geometry:
                x, y, w, h = geometry
                try:
                    window.move(x, y)
                except Exception:
                    pass
                try:
                    window.resize(w, h)
                except Exception:
                    pass
                last_geometry = geometry
            if visible != last_visible or (visible and time.time() < force_show_until):
                try:
                    if visible:
                        window.show()
                    else:
                        window.hide()
                except Exception:
                    pass
                last_visible = visible
            cursor_raw = state.get("cursor") if isinstance(state, dict) else None
            cursor = None
            if isinstance(cursor_raw, dict):
                try:
                    cursor = (int(cursor_raw.get("x", 0)), int(cursor_raw.get("y", 0)))
                except Exception:
                    cursor = None
            now = time.time()
            if cursor and (cursor != last_cursor or (now - last_cursor_sent_at) >= 0.12):
                payload = {
                    "cursor": {"x": cursor[0], "y": cursor[1]},
                    "windowBounds": {
                        "x": geometry[0],
                        "y": geometry[1],
                        "width": geometry[2],
                        "height": geometry[3],
                    },
                }
                try:
                    window.evaluate_js(
                        "window.postMessage("
                        + json.dumps({"type": "cursor-position", "payload": payload})
                        + ", '*');"
                    )
                    last_cursor = cursor
                    last_cursor_sent_at = now
                except Exception:
                    pass
            time.sleep(0.08)

    def _on_start() -> None:
        _apply_pywebview_transparency(window)
        try:
            window.show()
        except Exception:
            pass
        threading.Thread(target=_sync_loop, daemon=True, name=f"{style}-model-layer-sync").start()

    try:
        webview.start(_on_start)
    except Exception as exc:
        _log_startup_error(f"{style} model layer failed", exc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Companion AI desktop pet")
    parser.add_argument(
        "--style",
        choices=sorted(PET_STYLES),
        default=PET_STYLE_AUTO,
        help="pet style to open",
    )
    parser.add_argument("--model-layer", choices=[PET_STYLE_LIVE2D, PET_STYLE_3D], help=argparse.SUPPRESS)
    parser.add_argument("--geometry-file", default="", help=argparse.SUPPRESS)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.model_layer:
        run_model_layer_process(args.model_layer, args.geometry_file)
    else:
        main(args.style)
