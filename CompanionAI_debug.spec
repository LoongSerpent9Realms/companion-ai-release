# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['companion_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('data', 'data'), ('plugins', 'plugins'), ('static', 'static'), ('live2d_viewer.html', '.'), ('viewer_3d.html', '.'), ('official_site.html', '.'), ('version.txt', '.'), ('dataset_runtime_worker.py', '.'), ('face_manager.py', '.'), ('sensitive_json.py', '.'), ('secure_json.py', '.')],
    hiddenimports=['hybrid_chat', 'retrieval_chat', 'tiny_llm', 'embedding_retrieval', 'dataset_loader', 'plugin_manager', 'rapidocr_runner', 'face_manager', 'neural_companion', 'llm_inference', 'llm_trainer', 'operation_learning', 'procedural_rules', 'train_llm', '_paths', 'app', 'desktop_pet', 'webview', 'pystray', 'PIL', 'certifi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'torch_directml', 'triton', 'pytorch_triton', 'cv2', 'numpy', 'edge_tts', 'datasets', 'modelscope', 'modelscope_hub', 'huggingface_hub', 'pandas', 'pyarrow', 'fsspec', 'dill', 'multiprocess', 'xxhash', 'addict'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CompanionAI_debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['pet_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CompanionAI_debug',
)
