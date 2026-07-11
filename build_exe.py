from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# 版本号文件（集中管理，build_exe.py 与 companion_ai_setup.nsi 同步读取）
VERSION_FILE = ROOT / "version.txt"
NSI_FILE = ROOT / "companion_ai_setup.nsi"
EXCLUDED_RUNTIME_MODULES = [
    "torch",
    "torchvision",
    "torchaudio",
    "torch_directml",
    "triton",
    "pytorch_triton",
    "cv2",
    "edge_tts",
    "datasets",
    "modelscope",
    "modelscope_hub",
    "huggingface_hub",
    "pandas",
    "pyarrow",
    "fsspec",
    "dill",
    "multiprocess",
    "xxhash",
    "addict",
]
PRUNED_DIST_PREFIXES = (
    "torch",
    "torchvision",
    "torchaudio",
    "torch_directml",
    "triton",
    "pytorch_triton",
    "pandas",
    "pyarrow",
    "fsspec",
    "datasets",
    "modelscope",
    "modelscope_hub",
    "huggingface_hub",
    "dill",
    "multiprocess",
    "xxhash",
    "addict",
    "scipy",
    "sklearn",
    "onnx",
    "onnxruntime",
    "cv2",
    "edge_tts",
)
RUNTIME_REL = Path("runtime") / "python"


def electron_data_args() -> list[str]:
    """Return PyInstaller data arguments for the Electron pet shell."""
    items: list[tuple[Path, str]] = []
    electron_pet = ROOT / "electron_pet"
    if electron_pet.exists():
        items.append((electron_pet, "electron_pet"))

    electron_dist = ROOT / "node_modules" / "electron" / "dist"
    if electron_dist.exists():
        items.append((electron_dist, "node_modules/electron/dist"))

    args: list[str] = []
    for src, dest in items:
        args.extend(["--add-data", f"{src};{dest}"])
    return args


def local_data_args() -> list[str]:
    """Return data arguments for resources that exist in a clean checkout."""
    items = [
        (ROOT / "data", "data"),
        (ROOT / "plugins", "plugins"),
        (ROOT / "static", "static"),
        (ROOT / "live2d_viewer.html", "."),
        (ROOT / "viewer_3d.html", "."),
        (ROOT / "official_site.html", "."),
        (ROOT / "version.txt", "."),
        (ROOT / "dataset_runtime_worker.py", "."),
        (ROOT / "face_manager.py", "."),
        (ROOT / "sensitive_json.py", "."),
        (ROOT / "secure_json.py", "."),
    ]
    args: list[str] = []
    for source, target in items:
        if source.exists():
            args.extend(["--add-data", f"{source};{target}"])
    return args


def face_recognition_model_data_args() -> list[str]:
    """Return PyInstaller data arguments for face_recognition model files."""
    spec = importlib.util.find_spec("face_recognition_models")
    if spec is None or not spec.submodule_search_locations:
        return []
    models_dir = Path(next(iter(spec.submodule_search_locations))) / "models"
    if not models_dir.is_dir():
        return []
    return ["--add-data", f"{models_dir};face_recognition_models/models"]


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    print("[build] Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def read_version() -> str:
    """从 version.txt 读取当前版本号"""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "1.0.0"


def write_version(version: str) -> None:
    """写入版本号到 version.txt"""
    VERSION_FILE.write_text(version, encoding="utf-8")
    print(f"[build] 版本号已更新: {version}")


def bump_version(current: str, part: str = "patch") -> str:
    """自动递增版本号 (major/minor/patch)"""
    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")
    
    if part == "major":
        parts[0] = str(int(parts[0]) + 1)
        parts[1] = "0"
        parts[2] = "0"
    elif part == "minor":
        parts[1] = str(int(parts[1]) + 1)
        parts[2] = "0"
    else:  # patch
        parts[2] = str(int(parts[2]) + 1)
    
    return ".".join(parts)


def sync_nsi_version(version: str) -> None:
    """同步更新 NSIS 脚本中的版本号"""
    if not NSI_FILE.exists():
        return

    content = NSI_FILE.read_text(encoding="utf-8")
    # 替换 !define MyAppVersion "x.x.x"
    content = re.sub(
        r'!define\s+MyAppVersion\s+"[^"]*"',
        f'!define MyAppVersion "{version}"',
        content
    )
    # 同步 VIProductVersion "x.x.x.0" (补 0 作为第 4 段)
    vi_version = ".".join(version.split(".")[:3] + ["0"]) if len(version.split(".")) == 3 else version + ".0"
    content = re.sub(
        r'VIProductVersion\s+"[^"]*"',
        f'VIProductVersion "{vi_version}"',
        content
    )
    NSI_FILE.write_text(content, encoding="utf-8")
    print(f"[build] NSIS 版本号已同步: {version}")


def prune_optional_runtime_packages(dist_dir: Path) -> None:
    """Keep optional ML/data runtimes out of the installer bundle."""
    internal = (dist_dir / "_internal").resolve()
    if not internal.is_dir():
        return
    removed: list[str] = []
    for item in internal.iterdir():
        name = item.name.lower()
        if not any(name == prefix or name.startswith(prefix + "-") or name.startswith(prefix + ".") for prefix in PRUNED_DIST_PREFIXES):
            continue
        target = item.resolve()
        if internal not in target.parents:
            raise RuntimeError(f"refusing to prune outside dist internal dir: {target}")
        if item.is_dir():
            import shutil
            shutil.rmtree(item)
        else:
            item.unlink()
        removed.append(item.name)
    if removed:
        print("[build] 已从安装包中排除可选运行时: " + ", ".join(sorted(removed)))


def bundle_component_runtime(dist_dir: Path) -> None:
    """Put a supported Python 3.10-3.13 venv inside the app directory."""
    from _paths import runtime_python_exe

    source_python = Path(runtime_python_exe(create=True))
    source = source_python.parent.parent
    if not source.is_dir():
        raise RuntimeError(f"组件运行时不存在: {source}")

    target = dist_dir / RUNTIME_REL
    if target.exists():
        shutil.rmtree(target)

    print(f"[build] 复制自带组件运行时: {source} -> {target}")
    
    def _ignore_rocm_and_large_files(path: str, names: list[str]) -> list[str]:
        ignore_list = []
        for name in names:
            if name in {"__pycache__", ".git"}:
                ignore_list.append(name)
                continue
            full_path = Path(path) / name
            if name.endswith(".pyc") or name == "pip-selfcheck.json":
                ignore_list.append(name)
                continue
            if name.startswith("_rocm_sdk"):
                ignore_list.append(name)
                continue
            if name == ".kpack":
                ignore_list.append(name)
                continue
        return ignore_list
    
    shutil.copytree(source, target, ignore=_ignore_rocm_and_large_files)
    
    removed_dirs = []
    for item in (target / "Lib" / "site-packages").iterdir():
        if item.is_dir() and item.name.startswith("_rocm_sdk"):
            shutil.rmtree(item)
            removed_dirs.append(item.name)
    if removed_dirs:
        print("[build] 已从安装包中排除 ROCm SDK: " + ", ".join(removed_dirs))

    bundled_python = target / "Scripts" / "python.exe"
    if not bundled_python.is_file():
        raise RuntimeError(f"自带组件运行时缺少 python.exe: {bundled_python}")

    probe = subprocess.run(
        [str(bundled_python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "").strip()
        raise RuntimeError(f"自带组件运行时验证失败: {detail}")
    version = probe.stdout.strip()
    if version not in {"3.10", "3.11", "3.12", "3.13"}:
        raise RuntimeError(f"自带组件运行时版本不受支持: Python {version}")
    print(f"[build] 自带组件运行时验证通过: Python {version}")


def prompt_version_update() -> str | None:
    """交互式询问是否更新版本号，返回新版本号或 None（不更新）"""
    current = read_version()
    if not sys.stdin.isatty():
        print(f"\n[build] 当前版本: {current}")
        print("[build] 非交互环境，跳过版本号更新")
        return None

    print(f"\n[build] 当前版本: {current}")
    print("请选择是否更新版本号:")
    print("  1) 不更新，使用当前版本")
    print(f"  2) Patch 版本 ({bump_version(current, 'patch')})")
    print(f"  3) Minor 版本 ({bump_version(current, 'minor')})")
    print(f"  4) Major 版本 ({bump_version(current, 'major')})")
    print("  5) 手动输入版本号")
    
    try:
        choice = input("\n请选择 [1-5] (默认 2): ").strip() or "2"
    except EOFError:
        print("\n[build] 未收到输入，保持当前版本")
        return None
    
    if choice == "1":
        return None
    elif choice == "2":
        return bump_version(current, "patch")
    elif choice == "3":
        return bump_version(current, "minor")
    elif choice == "4":
        return bump_version(current, "major")
    elif choice == "5":
        try:
            new_ver = input("请输入新版本号 (如 1.2.3): ").strip()
        except EOFError:
            print("[build] 未收到版本号，保持当前版本")
            return None
        if re.match(r"^\d+(\.\d+)*$", new_ver):
            return new_ver
        print("[build] 格式无效，保持当前版本")
        return None
    else:
        print("[build] 无效选择，保持当前版本")
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CompanionAI with PyInstaller.")
    parser.add_argument(
        "--no-version-prompt",
        action="store_true",
        help="Keep the current version and skip the interactive version prompt.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # 询问是否更新版本号
    new_version = None if args.no_version_prompt else prompt_version_update()
    if args.no_version_prompt:
        print(f"\n[build] 当前版本: {read_version()}")
        print("[build] 已跳过版本号更新")
    if new_version:
        write_version(new_version)
        sync_nsi_version(new_version)
    
    current_version = read_version()
    print(f"\n[build] 开始打包，版本: {current_version}")
    
    ensure_pyinstaller()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "CompanionAI",
        "--icon",
        str(ROOT / "pet_icon.ico"),
        *local_data_args(),
        *electron_data_args(),
        *face_recognition_model_data_args(),
        "--hidden-import",
        "hybrid_chat",
        "--hidden-import",
        "retrieval_chat",
        "--hidden-import",
        "tiny_llm",
        "--hidden-import",
        "embedding_retrieval",
        "--hidden-import",
        "emotion_diary",
        "--hidden-import",
        "dataset_loader",
        "--hidden-import",
        "plugin_manager",
        "--hidden-import",
        "rapidocr_runner",
        "--hidden-import",
        "face_manager",
        "--hidden-import",
        "neural_companion",
        "--hidden-import",
        "llm_inference",
        "--hidden-import",
        "llm_trainer",
        "--hidden-import",
        "operation_learning",
        "--hidden-import",
        "procedural_rules",
        "--hidden-import",
        "conversation_audit",
        "--hidden-import",
        "audit_training",
        "--hidden-import",
        "train_llm",
        "--hidden-import",
        "_paths",
        "--hidden-import",
        "app",
        "--hidden-import",
        "desktop_pet",
        "--hidden-import",
        "webview",
        "--hidden-import",
        "pystray",
        "--hidden-import",
        "PIL",
        "--hidden-import",
        "certifi",
    ]
    for module in EXCLUDED_RUNTIME_MODULES:
        cmd.extend(["--exclude-module", module])
    cmd.append(str(ROOT / "companion_launcher.py"))
    print("[build] Running PyInstaller...")
    subprocess.check_call(cmd, cwd=ROOT)
    dist_dir = ROOT / "dist" / "CompanionAI"
    prune_optional_runtime_packages(dist_dir)
    
    runtime_dir = dist_dir / RUNTIME_REL
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
        print("[build] 已排除 runtime/python 目录（将在首次启动时自动创建）")
    exe = dist_dir / "CompanionAI.exe"
    print(f"[build] 打包完成: {exe}")
    print("[build] Next: compile companion_ai_setup.nsi with NSIS (makensis).")


if __name__ == "__main__":
    main()
