# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\companion_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\data', 'data'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\plugins', 'plugins'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\static', 'static'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\live2d_viewer.html', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\viewer_3d.html', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\official_site.html', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\version.txt', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\ai_icon.ico', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\pet_icon.ico', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\dataset_runtime_worker.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\tiny_llm_runtime_worker.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\tiny_llm.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\sparse_attention.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\_paths.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\face_manager.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\sensitive_json.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\secure_json.py', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\code_drills.json', '.'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\electron_pet', 'electron_pet'), ('C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\node_modules\\electron\\dist', 'node_modules/electron/dist'), ('C:\\Users\\24951\\AppData\\Roaming\\Python\\Python314\\site-packages\\face_recognition_models\\models', 'face_recognition_models/models')],
    hiddenimports=['hybrid_chat', 'retrieval_chat', 'tiny_llm', 'embedding_retrieval', 'emotion_diary', 'dataset_loader', 'plugin_manager', 'rapidocr_runner', 'face_manager', 'neural_companion', 'llm_inference', 'llm_trainer', 'operation_learning', 'procedural_rules', 'conversation_audit', 'audit_training', 'train_llm', 'proactive_engagement', 'dreaming_engine', 'knowledge_distillation', 'memory_layer', 'user_profile', 'remote_llm', 'web_learner', 'code_lab', 'algorithm_curriculum', 'toolchain_manager', 'routine_tracker', 'companion_growth', 'dialogue_skills', 'dependency_utils', '_paths', 'app', 'desktop_pet', 'webview', 'pystray', 'PIL', 'certifi', 'image_generator'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'torch_directml', 'triton', 'pytorch_triton', 'cv2', 'edge_tts', 'datasets', 'modelscope', 'modelscope_hub', 'huggingface_hub', 'pandas', 'pyarrow', 'fsspec', 'dill', 'multiprocess', 'xxhash', 'addict'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CompanionAI',
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
    icon=['C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\pet_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CompanionAI',
)
