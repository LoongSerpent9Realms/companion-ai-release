from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import _paths as path_helpers
from _paths import python_exe


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DATASET_PACKAGES = [
    "datasets",
    "modelscope",
    "huggingface-hub",
    "addict",
    "pyarrow",
    "pandas",
    "fsspec",
    "dill",
    "multiprocess",
    "xxhash",
]
DATASET_UNINSTALL_PACKAGES = [*DATASET_PACKAGES, "modelscope-hub"]
DATASET_IMPORTS = [
    "pandas",
    "pandas._libs.pandas_parser",
    "pyarrow",
    "datasets",
    "modelscope",
    "modelscope.msdatasets",
]
DATASET_INSTALL_CMD = "pip install " + " ".join(DATASET_PACKAGES)

runtime_python_exe = getattr(path_helpers, "runtime_python_exe", lambda root=None, create=True: python_exe())


@dataclass
class DependencyStatus:
    ok: bool
    detail: str
    python: str
    installed: bool = False


def short_pip_error(text: str, limit: int = 320) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "安装失败，pip 没有返回详细信息"
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    for prefix in ("ERROR:", "Exception:", "Traceback"):
        for line in lines:
            if line.startswith(prefix):
                return line[:limit]
    return lines[-1][:limit] if lines else cleaned[:limit]


def get_runtime_python(create: bool = True) -> str:
    try:
        return runtime_python_exe(create=create)
    except Exception:
        if create:
            raise
        try:
            return python_exe()
        except Exception:
            if getattr(sys, "frozen", False):
                raise
            return sys.executable


def refresh_external_site_packages() -> None:
    try:
        path_helpers.ensure_external_site_packages()
    except Exception:
        pass


def check_runtime_imports(modules: list[str]) -> DependencyStatus:
    try:
        py = get_runtime_python(create=False)
    except Exception as exc:
        return DependencyStatus(False, f"检测失败：{exc}", "")
    code = """
import importlib
import json
from importlib import metadata
missing = []
versions = {}
DIST_NAMES = {
    "datasets": "datasets",
    "modelscope": "modelscope",
    "modelscope.msdatasets": "modelscope",
    "pandas": "pandas",
    "pandas._libs.pandas_parser": "pandas",
    "pyarrow": "pyarrow",
}
for name in MODULES:
    try:
        importlib.import_module(name)
        dist_name = DIST_NAMES.get(name, name.split(".", 1)[0])
        try:
            versions[name] = metadata.version(dist_name)
        except Exception:
            versions[name] = "installed"
    except Exception as exc:
        missing.append(f"{name}: {exc}")
print(json.dumps({"missing": missing, "versions": versions}, ensure_ascii=False))
""".replace("MODULES", repr(modules))
    try:
        proc = subprocess.run(
            [py, "-c", code],
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return DependencyStatus(False, f"检测失败：{exc}", py)
    if proc.returncode != 0:
        return DependencyStatus(False, short_pip_error(proc.stderr or proc.stdout), py)
    try:
        import json

        data = json.loads(proc.stdout.strip() or "{}")
    except Exception:
        return DependencyStatus(False, "检测失败：无法解析 import 检测结果", py)
    missing = data.get("missing") or []
    if missing:
        return DependencyStatus(False, "缺少依赖：" + "；".join(str(x) for x in missing), py)
    versions = data.get("versions") or {}
    detail = ", ".join(f"{name} {version}" for name, version in versions.items())
    return DependencyStatus(True, detail or "已安装", py)


def check_dataset_dependencies() -> DependencyStatus:
    status = check_runtime_imports(DATASET_IMPORTS)
    if status.ok:
        refresh_external_site_packages()
    return status


def install_dataset_dependencies() -> DependencyStatus:
    py = get_runtime_python(create=True)
    cmd = [py, "-m", "pip", "install", *DATASET_PACKAGES]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return DependencyStatus(False, f"安装失败：{exc}", py)
    if proc.returncode != 0:
        return DependencyStatus(False, short_pip_error(proc.stderr or proc.stdout), py)
    status = check_dataset_dependencies()
    if status.ok:
        refresh_external_site_packages()
        return DependencyStatus(True, f"安装并验证完成：{status.detail}", py, installed=True)
    return DependencyStatus(False, f"pip 安装完成，但验证失败：{status.detail}", py)


def ensure_dataset_dependencies(auto_install: bool = True) -> DependencyStatus:
    status = check_dataset_dependencies()
    if status.ok or not auto_install:
        return status
    return install_dataset_dependencies()
