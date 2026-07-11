# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH)


def optional_data(source, target):
    path = ROOT / source
    return (str(path), target) if path.exists() else None


datas = [
    optional_data("data", "data"),
    optional_data("plugins", "plugins"),
    optional_data("static", "static"),
    optional_data("live2d_viewer.html", "."),
    optional_data("viewer_3d.html", "."),
    optional_data("official_site.html", "."),
    optional_data("version.txt", "."),
    optional_data("dataset_runtime_worker.py", "."),
    optional_data("face_manager.py", "."),
    optional_data("sensitive_json.py", "."),
    optional_data("secure_json.py", "."),
    optional_data("electron_pet", "electron_pet"),
]
datas = [item for item in datas if item is not None]


a = Analysis(
    [str(ROOT / "companion_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "hybrid_chat", "retrieval_chat", "tiny_llm", "embedding_retrieval",
        "emotion_diary", "dataset_loader", "plugin_manager", "rapidocr_runner",
        "face_manager", "neural_companion", "llm_inference", "llm_trainer",
        "operation_learning", "procedural_rules", "conversation_audit",
        "audit_training", "train_llm", "_paths", "app", "desktop_pet",
        "webview", "pystray", "PIL", "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "torchvision", "torchaudio", "torch_directml", "triton",
        "pytorch_triton", "cv2", "edge_tts", "datasets", "modelscope",
        "modelscope_hub", "huggingface_hub", "pandas", "pyarrow", "fsspec",
        "dill", "multiprocess", "xxhash", "addict",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CompanionAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "pet_icon.ico")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CompanionAI",
)
