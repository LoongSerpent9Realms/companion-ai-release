"""Shared path helper for Companion AI modules.

In frozen (PyInstaller) mode, ``__file__`` resolves to the ``_internal/``
bundle directory which is not suitable for writing user data.  The launcher
(``companion_launcher.py``) sets ``_COMPANION_BASE_DIR`` to the exe's parent
directory and copies bundled resources there on first run.  All modules use
this helper to resolve their ROOT consistently.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def module_root(caller_file: str) -> Path:
    """Return the project base directory.

    In frozen mode the launcher sets ``_COMPANION_BASE_DIR`` to the exe's
    parent.  Otherwise the base is the directory that contains *caller_file*.
    """
    base = os.environ.get("_COMPANION_BASE_DIR")
    if base:
        base_path = Path(base)
        # Validate: the env var may point to a stale/removed installation.
        # Accept the path if it looks like a valid Companion AI base dir
        # (frozen mode: has _internal/ subdir; dev mode: has app.py).
        if base_path.is_dir():
            if (base_path / "_internal").is_dir() or (base_path / "app.py").is_file():
                return base_path
        # Stale env var - ignore and fall back to actual location.
    return Path(caller_file).resolve().parent


def resource_dir(caller_file: str) -> Path:
    """Return the directory containing bundled read-only resources.

    In frozen (PyInstaller) mode the launcher sets ``_COMPANION_BASE_DIR``
    to the exe parent, but static files / HTML templates are bundled inside
    ``_internal/``.  This helper resolves to the correct location so that
    ``resource_dir(__file__) / "static"`` always works.
    """
    base = module_root(caller_file)
    internal = base / "_internal"
    if internal.is_dir():
        return internal
    return base


def data_dir(root: Path | None = None) -> Path:
    """Return a persistent directory for user data (identity, memory, models).

    Uses ``%APPDATA%/CompanionAI`` on Windows and
    ``$XDG_DATA_HOME/CompanionAI`` (or ``~/.local/share/CompanionAI``) on
    Linux. This keeps data outside installed application directories so it
    survives code updates and works when the app is installed under ``/opt``.
    Falls back to ``<root>/data`` when no user data directory is available.

    On first call the function migrates any existing ``<root>/data`` content
    to the new location.
    """
    fallback = (root or Path.cwd()) / "data"
    if os.name == "nt" and os.environ.get("APPDATA"):
        dest = Path(os.environ["APPDATA"]) / "CompanionAI"
    elif os.name == "posix":
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        dest = (
            Path(xdg_data_home) / "CompanionAI"
            if xdg_data_home
            else Path.home() / ".local" / "share" / "CompanionAI"
        )
    else:
        dest = fallback

    try:
        dest.mkdir(parents=True, exist_ok=True)
        probe = dest / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception:
        # Some launch contexts can see %APPDATA% but cannot write there
        # (for example restricted sandboxes). Keep startup alive by falling
        # back to the project-local data directory.
        dest = fallback
        dest.mkdir(parents=True, exist_ok=True)

    # One-time migration from old in-tree data/ directory
    if root is not None:
        old = root / "data"
        if old.is_dir() and old.resolve() != dest.resolve():
            marker = dest / ".migrated"
            if not marker.exists():
                for item in old.iterdir():
                    target = dest / item.name
                    if not target.exists():
                        try:
                            shutil.move(str(item), str(target))
                        except Exception:
                            pass
                try:
                    marker.write_text("ok", encoding="utf-8")
                except Exception:
                    pass

    return dest


PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"
SUPPORTED_RUNTIME_PYTHON = "Python 3.10-3.13"
RUNTIME_VENV_REL = Path("runtime") / "python"


def _usable_runtime_python(candidate: str) -> tuple[bool, str]:
    """Return whether *candidate* can run optional pip-managed runtimes."""
    import subprocess

    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    code = (
        "import sys; "
        "v=sys.version_info; "
        "raise SystemExit(0 if (3, 10) <= v[:2] < (3, 14) else "
        "f'当前 Python {v.major}.{v.minor} 暂不适合安装本地 AI 组件，请使用 Python 3.10-3.13')"
    )
    try:
        version_check = subprocess.run(
            [candidate, "-c", code],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        if version_check.returncode != 0:
            detail = (version_check.stderr or version_check.stdout or "").strip()
            return False, detail or "Python 版本不兼容"
        pip_check = subprocess.run(
            [candidate, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        if pip_check.returncode != 0:
            detail = (pip_check.stderr or pip_check.stdout or "").strip()
            return False, detail or "pip 不可用"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def python_exe() -> str:
    """Return the path to a real Python interpreter for running ``-m pip``.

    In frozen (PyInstaller) mode ``sys.executable`` is the app .exe which
    cannot run ``-m pip``.  We locate the real system Python via the ``py``
    launcher, the Windows registry, or common install paths.  In dev mode
    we just return ``sys.executable``.

    Raises ``RuntimeError`` when no usable Python interpreter is found in
    frozen mode, so callers can show a helpful message with a download link.
    """
    import sys, subprocess, shutil
    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    rejected: list[str] = []

    def accept(candidate: str) -> str | None:
        ok, reason = _usable_runtime_python(candidate)
        if ok:
            return candidate
        rejected.append(f"{candidate}: {reason}")
        return None

    if not getattr(sys, "frozen", False):
        current = accept(sys.executable)
        if current:
            return current

    # 1) py launcher (ships with official Python Windows installer)
    py = shutil.which("py")
    if py:
        for ver in ["-3.12", "-3.11", "-3.10", "-3.13", "-3", ""]:
            try:
                r = subprocess.run(
                    [py, ver, "-c", "import sys; print(sys.executable)"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=CREATE_NO_WINDOW,
                )
                if r.returncode == 0 and r.stdout.strip():
                    candidate = accept(r.stdout.strip())
                    if candidate:
                        return candidate
            except Exception:
                continue

    # 2) Windows registry: HKCU/HKLM SOFTWARE\Python\PythonCore
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(hive, r"SOFTWARE\Python\PythonCore")
            i = 0
            while True:
                try:
                    ver = winreg.EnumKey(key, i)
                    i += 1
                    exe = winreg.QueryValue(
                        winreg.OpenKey(key, f"{ver}\\InstallPath"), ""
                    )
                    candidate = Path(exe) / "python.exe"
                    if candidate.is_file():
                        accepted = accept(str(candidate))
                        if accepted:
                            return accepted
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass

    # 3) Common install locations
    localapp = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    if localapp.is_dir():
        for d in sorted(localapp.iterdir(), reverse=True):
            candidate = d / "python.exe"
            if candidate.is_file():
                accepted = accept(str(candidate))
                if accepted:
                    return accepted

    # No real Python found - raise instead of silently returning a broken path
    details = "\n".join(rejected[-5:])
    raise RuntimeError(
        f"未检测到可用于本地 AI 组件的 Python 解释器，请先安装 {SUPPORTED_RUNTIME_PYTHON} 后重试。\n"
        f"下载地址：{PYTHON_DOWNLOAD_URL}"
        + (f"\n已跳过：\n{details}" if details else "")
    )


def download_and_install_python(install: bool = True) -> dict[str, any]:
    """下载 Python 安装器并可选自动安装（Windows 专用）。

    Args:
        install: True=下载后自动静默安装，False=仅下载

    Returns:
        dict with keys: ok (bool), message (str), path (str, optional)
    """
    import subprocess, urllib.request, ctypes

    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    PYTHON_VERSION = "3.12.0"
    url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-amd64.exe"
    install_dir = data_dir()
    download_path = install_dir / f"python-{PYTHON_VERSION}-amd64.exe"
    install_dir.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        download_path.write_bytes(data)

        if not download_path.exists():
            return {"ok": False, "message": " Python 安装器下载失败。"}

        if not install:
            return {
                "ok": True,
                "message": (
                    f" Python 安装器已下载到：\n{download_path}\n\n"
                    "请双击运行安装，安装时勾选「Add Python to PATH」。"
                ),
                "path": str(download_path),
            }

        install_args = (
            "/quiet",
            "InstallAllUsers=1",
            "PrependPath=1",
            "Include_pip=1",
            "Include_test=0",
            "SimpleInstall=1",
        )

        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not is_admin:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", str(download_path),
                " ".join(install_args),
                None, 1
            )
            if ret <= 32:
                return {
                    "ok": False,
                    "message": (
                        " 需要管理员权限来安装 Python。\n\n"
                        f"安装器已下载到：{download_path}\n"
                        "请右键「以管理员身份运行」。"
                    ),
                    "path": str(download_path),
                }
            return {
                "ok": True,
                "message": (
                    " Python 安装器已启动（需要管理员权限）。\n\n"
                    "正在后台安装 Python 3.12，这可能需要 5-15 分钟。\n"
                    "安装完成后请重启 Companion AI。"
                ),
            }

        proc = subprocess.run(
            [str(download_path), *install_args],
            capture_output=True,
            text=True,
            timeout=600,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )

        if proc.returncode == 0 or proc.returncode == 3010:
            message = " Python 安装完成！"
            if proc.returncode == 3010:
                message += " 需要重启计算机才能生效。"
            return {"ok": True, "message": message + "\n\n请重启 Companion AI。"}
        else:
            detail = (proc.stderr or proc.stdout or "").strip()[-500:]
            return {"ok": False, "message": f" Python 安装失败：\n{detail}"}

    except Exception as exc:
        return {"ok": False, "message": f" Python 安装失败：{exc}"}


def runtime_venv_dir(root: Path | None = None) -> Path:
    """Return the dedicated venv directory for pip-managed components."""
    if root is None:
        root = module_root(__file__)
    if root is not None:
        bundled = root / RUNTIME_VENV_REL
        if _venv_python_path(bundled).is_file():
            return bundled
    return data_dir(root) / RUNTIME_VENV_REL


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def runtime_python_exe(root: Path | None = None, create: bool = True) -> str:
    """Return the dedicated runtime venv Python, creating it when needed."""
    import subprocess

    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    venv_dir = runtime_venv_dir(root)
    venv_python = _venv_python_path(venv_dir)
    if venv_python.is_file():
        ok, reason = _usable_runtime_python(str(venv_python))
        if ok:
            return str(venv_python)
        if not create:
            raise RuntimeError(f"组件虚拟环境不可用：{reason}")
        shutil.rmtree(venv_dir, ignore_errors=True)

    if not create:
        raise RuntimeError("组件虚拟环境尚未创建")

    base_python = python_exe()
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [base_python, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "创建虚拟环境失败").strip()
        raise RuntimeError(f"创建组件虚拟环境失败：{detail}")
    if not venv_python.is_file():
        raise RuntimeError(f"创建组件虚拟环境失败：找不到 {venv_python}")

    pip_result = subprocess.run(
        [str(venv_python), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    if pip_result.returncode != 0:
        detail = (pip_result.stderr or pip_result.stdout or "pip 不可用").strip()
        raise RuntimeError(f"组件虚拟环境 pip 不可用：{detail}")
    return str(venv_python)


def external_site_packages() -> list[Path]:
    """Return site-packages directories for the component runtime venv."""
    import json
    import subprocess
    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        py = runtime_python_exe(create=False)
    except RuntimeError:
        return []

    code = (
        "import json, site, sysconfig; "
        "paths = []; "
        "paths.extend(site.getsitepackages() if hasattr(site, 'getsitepackages') else []); "
        "paths.append(sysconfig.get_paths().get('purelib', '')); "
        "paths.append(sysconfig.get_paths().get('platlib', '')); "
        "print(json.dumps([p for p in dict.fromkeys(paths) if p]))"
    )
    result = subprocess.run(
        [py, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        return []
    try:
        return [Path(p) for p in json.loads(result.stdout) if Path(p).exists()]
    except Exception:
        return []


def ensure_external_site_packages() -> None:
    """Expose optional venv packages when they match the running Python ABI."""
    import sys
    import re

    runtime_version = None
    try:
        runtime_version = runtime_python_exe(create=False)
    except RuntimeError:
        return
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    try:
        import subprocess
        CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [runtime_version, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.returncode != 0 or proc.stdout.strip() != current:
            return
    except Exception:
        return
    current_tag = f"{sys.version_info.major}{sys.version_info.minor}"

    def compatible_native_abi(path: Path) -> bool:
        patterns = (
            re.compile(r"\.cp(\d{2,3})-", re.IGNORECASE),
            re.compile(r"python(\d{2,3})\.dll$", re.IGNORECASE),
        )
        try:
            candidates = list(path.rglob("*.pyd"))[:500] + list(path.rglob("python*.dll"))[:50]
        except Exception:
            return True
        for candidate in candidates:
            name = candidate.name
            for pattern in patterns:
                match = pattern.search(name)
                if match and match.group(1) != current_tag:
                    return False
        return True

    for path in reversed(external_site_packages()):
        if not compatible_native_abi(path):
            continue
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
