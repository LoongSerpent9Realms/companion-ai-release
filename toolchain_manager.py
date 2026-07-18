"""Manage the optional C++ toolchain used by local code practice."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
CONFIG_FILE = DATA_DIR / "toolchain_config.json"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LLVM_WINGET_ID = "LLVM.LLVM"


def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "CompanionAI" / "toolchains" / "llvm"


def _load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_config(config: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_bin_dir(directory: str | Path) -> Path:
    """Accept either a toolchain root or its bin directory."""
    raw = os.path.expandvars(os.path.expanduser(str(directory or "").strip()))
    if not raw:
        raise ValueError("请填写工具链安装目录或 bin 目录。")
    path = Path(raw).resolve()
    return path if path.name.lower() == "bin" else path / "bin"


def merge_path_entry(existing: str, entry: str) -> str:
    """Add an entry to PATH once, preserving the existing order."""
    normalized = os.path.normcase(os.path.normpath(entry))
    parts = [part for part in str(existing or "").split(os.pathsep) if part]
    if any(os.path.normcase(os.path.normpath(part)) == normalized for part in parts):
        return os.pathsep.join(parts)
    return os.pathsep.join([entry, *parts]) if parts else entry


def add_to_user_path(bin_dir: str | Path) -> dict[str, Any]:
    """Persist a bin directory in the Windows user PATH and refresh this process."""
    path = Path(bin_dir).resolve()
    if not path.is_dir():
        return {"ok": False, "detail": f"目录不存在：{path}"}
    if os.name != "nt":
        return {"ok": False, "detail": "将目录写入用户 PATH 仅支持 Windows。"}
    try:
        import winreg

        key_path = r"Environment"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                existing, value_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                existing, value_type = "", winreg.REG_EXPAND_SZ
            updated = merge_path_entry(str(existing or ""), str(path))
            winreg.SetValueEx(key, "Path", 0, value_type, updated)
        os.environ["PATH"] = merge_path_entry(os.environ.get("PATH", ""), str(path))
        try:
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0, 3000, None)
        except Exception:
            pass
        return {"ok": True, "detail": f"已加入用户 PATH：{path}。新启动的终端和应用可直接使用。", "bin_dir": str(path)}
    except Exception as exc:
        return {"ok": False, "detail": f"写入用户 PATH 失败：{exc}"}


def _compiler_paths() -> dict[str, str]:
    return {name: shutil.which(name) or "" for name in ("g++", "clang++", "cl")}


def status() -> dict[str, Any]:
    config = _load_config()
    compilers = _compiler_paths()
    compiler = next((value for value in compilers.values() if value), "")
    configured_bin = str(config.get("bin_dir") or "")
    install_dir = str(config.get("install_dir") or default_install_dir())
    if compiler:
        return {
            "installed": True,
            "detail": f"C++ 工具链可用：{compiler}",
            "compiler": compiler,
            "compilers": compilers,
            "install_dir": install_dir,
            "bin_dir": configured_bin,
        }
    return {
        "installed": False,
        "detail": "未检测到 g++、clang++ 或 cl。可安装 LLVM，或填写现有工具链目录并加入用户 PATH。",
        "compiler": "",
        "compilers": compilers,
        "install_dir": install_dir,
        "bin_dir": configured_bin,
        "winget_id": LLVM_WINGET_ID,
    }


def configure_existing_directory(directory: str | Path) -> dict[str, Any]:
    bin_dir = normalize_bin_dir(directory)
    if not bin_dir.is_dir():
        return {"success": False, "detail": f"未找到工具链 bin 目录：{bin_dir}"}
    paths = [bin_dir / name for name in ("g++.exe", "clang++.exe", "cl.exe", "g++", "clang++", "cl")]
    if not any(path.exists() for path in paths):
        return {"success": False, "detail": f"目录中未找到 g++、clang++ 或 cl：{bin_dir}"}
    added = add_to_user_path(bin_dir)
    if not added.get("ok"):
        return {"success": False, "detail": added.get("detail", "加入 PATH 失败")}
    config = _load_config()
    config.update({"install_dir": str(bin_dir.parent), "bin_dir": str(bin_dir)})
    _save_config(config)
    return {"success": True, "detail": added["detail"], "status": status()}


def install_llvm(install_dir: str | Path = "") -> dict[str, Any]:
    """Install LLVM using winget, then publish its bin directory to user PATH."""
    if os.name != "nt":
        return {"success": False, "detail": "自动安装 LLVM 目前仅支持 Windows。"}
    winget = shutil.which("winget")
    if not winget:
        return {
            "success": False,
            "detail": "未检测到 winget。请安装 App Installer，或手动安装 LLVM 后使用“加入已有目录”。",
            "download_url": "https://aka.ms/getwinget",
        }
    target = Path(os.path.expandvars(os.path.expanduser(str(install_dir or default_install_dir())))).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        winget, "install", "--id", LLVM_WINGET_ID, "--exact", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements", "--location", str(target),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return {"success": False, "detail": f"启动 LLVM 安装失败：{exc}"}
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "winget 未返回错误详情").strip()
        return {"success": False, "detail": f"LLVM 安装失败：{detail[-800:]}"}

    candidates = [target / "bin", target]
    for candidate in candidates:
        if (candidate / "clang++.exe").exists() or (candidate / "clang++").exists():
            result = configure_existing_directory(candidate)
            if result.get("success"):
                return {"success": True, "detail": "LLVM 安装并验证完成。" + result["detail"], "status": status()}
            return result
    return {
        "success": False,
        "detail": "LLVM 已安装，但未在指定目录找到 clang++。请在设置中填写实际 LLVM 安装目录后再加入 PATH。",
    }
