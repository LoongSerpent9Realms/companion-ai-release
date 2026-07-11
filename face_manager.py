"""Face recognition manager for Companion AI.

Provides face detection, registration, recognition and logging using face_recognition library.
Data is stored in DATA_DIR/faces/ directory.
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sensitive_json import read_sensitive_json, write_sensitive_json


def _refresh_external_runtime_paths() -> None:
    """Expose packages installed into the shared component runtime when possible."""
    try:
        import _paths as path_helpers

        ensure_external_site_packages = getattr(path_helpers, "ensure_external_site_packages", None)
        if ensure_external_site_packages is not None:
            ensure_external_site_packages()
    except Exception:
        pass

# Try to import face_recognition using importlib to avoid quit() call in library
# Fix for Python 3.14+: pkg_resources is removed from setuptools
# The face_recognition_models package uses pkg_resources.resource_filename which was removed
# We create a patched module before importing face_recognition
_HAS_FACE_RECOGNITION = False
_FACE_RECOGNITION_IMPORT_ERROR = ""
face_recognition = None
cv2 = None
np = None


def _try_import_face_recognition() -> tuple[bool, str]:
    global face_recognition
    try:
        import sys
        import os
        import importlib.resources
        import importlib.util

        _models_spec = importlib.util.find_spec("face_recognition_models")
        if _models_spec is not None:
            _models_module = type(sys)("face_recognition_models")
            _models_module.__author__ = "Adam Geitgey"
            _models_module.__email__ = 'ageitgey@gmail.com'
            _models_module.__version__ = '0.1.0'
            _models_module.__file__ = str(_models_spec.origin) if _models_spec.origin else ""
            _models_module.__path__ = _models_spec.submodule_search_locations or []

            def _get_model_path(model_name):
                try:
                    return str(importlib.resources.files("face_recognition_models") / "models" / model_name)
                except Exception:
                    pass

                try:
                    for path in _models_module.__path__:
                        model_path = Path(path) / "models" / model_name
                        if model_path.exists():
                            return str(model_path)
                except Exception:
                    pass

                try:
                    import pkg_resources
                    return pkg_resources.resource_filename("face_recognition_models", f"models/{model_name}")
                except Exception:
                    pass

                try:
                    for site_packages in sys.path:
                        if not isinstance(site_packages, str):
                            continue
                        model_path = Path(site_packages) / "face_recognition_models" / "models" / model_name
                        if model_path.exists():
                            return str(model_path)
                except Exception:
                    pass

                raise FileNotFoundError(f"Model file not found: {model_name}")

            _models_module.pose_predictor_model_location = lambda: _get_model_path("shape_predictor_68_face_landmarks.dat")
            _models_module.pose_predictor_five_point_model_location = lambda: _get_model_path("shape_predictor_5_face_landmarks.dat")
            _models_module.face_recognition_model_location = lambda: _get_model_path("dlib_face_recognition_resnet_model_v1.dat")
            _models_module.cnn_face_detector_model_location = lambda: _get_model_path("mmod_human_face_detector.dat")

            sys.modules["face_recognition_models"] = _models_module

        face_recognition = importlib.import_module("face_recognition")
        return True, ""
    except Exception as exc:
        face_recognition = None
        return False, str(exc)


def _try_import_cv2() -> tuple[bool, str]:
    global cv2, np
    try:
        cv2 = importlib.import_module("cv2")
        np = importlib.import_module("numpy")
        return True, ""
    except Exception as exc:
        cv2 = None
        np = None
        return False, str(exc)


def _probe_optional_deps(refresh_paths: bool = False) -> None:
    global _HAS_FACE_RECOGNITION, _FACE_RECOGNITION_IMPORT_ERROR, _HAS_CV2, _CV2_IMPORT_ERROR
    if refresh_paths:
        _refresh_external_runtime_paths()
        importlib.invalidate_caches()

    if not _HAS_FACE_RECOGNITION:
        _HAS_FACE_RECOGNITION, _FACE_RECOGNITION_IMPORT_ERROR = _try_import_face_recognition()
    if not _HAS_CV2:
        _HAS_CV2, _CV2_IMPORT_ERROR = _try_import_cv2()


_refresh_external_runtime_paths()
try:
    import sys
    import os
    import importlib.resources
    import importlib.util
    
    _models_spec = importlib.util.find_spec("face_recognition_models")
    if _models_spec is not None:
        _models_module = type(sys)("face_recognition_models")
        _models_module.__author__ = "Adam Geitgey"
        _models_module.__email__ = 'ageitgey@gmail.com'
        _models_module.__version__ = '0.1.0'
        _models_module.__file__ = str(_models_spec.origin) if _models_spec.origin else ""
        _models_module.__path__ = _models_spec.submodule_search_locations or []
        
        def _get_model_path(model_name):
            try:
                return str(importlib.resources.files("face_recognition_models") / "models" / model_name)
            except Exception:
                pass
            
            try:
                for path in _models_module.__path__:
                    model_path = Path(path) / "models" / model_name
                    if model_path.exists():
                        return str(model_path)
            except Exception:
                pass
            
            try:
                import pkg_resources
                return pkg_resources.resource_filename("face_recognition_models", f"models/{model_name}")
            except Exception:
                pass
            
            try:
                for site_packages in sys.path:
                    if not isinstance(site_packages, str):
                        continue
                    model_path = Path(site_packages) / "face_recognition_models" / "models" / model_name
                    if model_path.exists():
                        return str(model_path)
            except Exception:
                pass
            
            raise FileNotFoundError(f"Model file not found: {model_name}")
        
        _models_module.pose_predictor_model_location = lambda: _get_model_path("shape_predictor_68_face_landmarks.dat")
        _models_module.pose_predictor_five_point_model_location = lambda: _get_model_path("shape_predictor_5_face_landmarks.dat")
        _models_module.face_recognition_model_location = lambda: _get_model_path("dlib_face_recognition_resnet_model_v1.dat")
        _models_module.cnn_face_detector_model_location = lambda: _get_model_path("mmod_human_face_detector.dat")
        
        sys.modules["face_recognition_models"] = _models_module
    
    face_recognition = importlib.import_module("face_recognition")
    _HAS_FACE_RECOGNITION = True
except Exception as exc:
    _FACE_RECOGNITION_IMPORT_ERROR = str(exc)

# Try to import cv2 for image loading
_HAS_CV2 = False
_CV2_IMPORT_ERROR = ""
try:
    cv2 = importlib.import_module("cv2")
    np = importlib.import_module("numpy")
    _HAS_CV2 = True
except Exception as exc:
    _CV2_IMPORT_ERROR = str(exc)


# Default paths - will be updated by init_face_manager
FACE_DIR: Path = Path(".")
KNOWN_FACES_DIR: Path = Path(".")
ENCODINGS_FILE: Path = Path(".")
FACE_LOG_FILE: Path = Path(".")
FACE_VENV: Path = Path(".")
CAMERA_OPEN_TIMEOUT_SEC = 4.0
CAMERA_READ_TIMEOUT_SEC = 5.0


def init_face_manager(data_dir: Path) -> None:
    """Initialize face manager with the correct data directory."""
    global FACE_DIR, KNOWN_FACES_DIR, ENCODINGS_FILE, FACE_LOG_FILE, FACE_VENV
    FACE_DIR = data_dir / "faces"
    KNOWN_FACES_DIR = FACE_DIR / "known"
    ENCODINGS_FILE = FACE_DIR / "encodings.json"
    FACE_LOG_FILE = FACE_DIR / "log.json"
    FACE_VENV = FACE_DIR / ".venv"
    FACE_DIR.mkdir(parents=True, exist_ok=True)
    KNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)


def face_recognition_available() -> bool:
    """Check if face_recognition is available in current environment."""
    _probe_optional_deps(refresh_paths=True)
    return bool(_HAS_FACE_RECOGNITION and _HAS_CV2)


def _get_cv2_module():
    _probe_optional_deps(refresh_paths=True)
    return cv2 if _HAS_CV2 else None


def face_python() -> Path:
    """Return the Python executable for face recognition subprocess."""
    return FACE_VENV / "Scripts" / "python.exe"


def _runtime_python_status() -> tuple[str | None, str]:
    try:
        import _paths as path_helpers

        runtime_python = getattr(path_helpers, "runtime_python_exe", None)
        if runtime_python is None:
            return _get_python_exe(), ""
        return runtime_python(create=False), ""
    except Exception as exc:
        return None, str(exc)


def _probe_runtime_face_deps() -> dict[str, Any]:
    py, py_error = _runtime_python_status()
    if not py:
        return {
            "runtime_available": False,
            "cv2": False,
            "face_recognition": False,
            "cv2_error": py_error,
            "face_error": py_error,
            "python": "",
        }

    code = r'''
import importlib
import json

def check_module(name, version_attr="__version__"):
    try:
        mod = importlib.import_module(name)
        return {"ok": True, "version": str(getattr(mod, version_attr, "") or "installed"), "error": ""}
    except Exception as exc:
        return {"ok": False, "version": "", "error": str(exc)}

cv2 = check_module("cv2")
face = check_module("face_recognition")
print(json.dumps({
    "runtime_available": True,
    "cv2": cv2["ok"],
    "cv2_version": cv2["version"],
    "cv2_error": cv2["error"],
    "face_recognition": face["ok"],
    "face_version": face["version"],
    "face_error": face["error"],
}, ensure_ascii=False))
'''
    try:
        proc = subprocess.run(
            [py, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return {
                "runtime_available": False,
                "cv2": False,
                "face_recognition": False,
                "cv2_error": detail,
                "face_error": detail,
                "python": py,
            }
        data = json.loads((proc.stdout or "{}").strip().splitlines()[-1])
        data["python"] = py
        return data
    except Exception as exc:
        return {
            "runtime_available": False,
            "cv2": False,
            "face_recognition": False,
            "cv2_error": str(exc),
            "face_error": str(exc),
            "python": py,
        }


def check_face_recognition_deps() -> dict[str, Any]:
    """Check face recognition dependencies status."""
    _probe_optional_deps(refresh_paths=True)
    has_face_rec = False
    has_cv2 = False
    face_error = ""
    cv2_error = ""
    
    has_face_rec = _HAS_FACE_RECOGNITION
    face_error = _FACE_RECOGNITION_IMPORT_ERROR
    
    has_cv2 = _HAS_CV2
    cv2_error = _CV2_IMPORT_ERROR
    
    result = {
        "face_recognition": has_face_rec,
        "cv2": has_cv2,
        "error": None,
        "detail": "",
        "runtime": None,
    }
    if has_face_rec and has_cv2:
        result["detail"] = "face_recognition + cv2 可用"
        return result

    runtime = _probe_runtime_face_deps()
    result["runtime"] = runtime
    if runtime.get("cv2") and runtime.get("face_recognition"):
        result["face_recognition"] = True
        result["cv2"] = True
        result["detail"] = "face_recognition + cv2 可用（组件运行环境）"
    elif runtime.get("cv2") and not runtime.get("face_recognition"):
        version = runtime.get("cv2_version") or "installed"
        result["cv2"] = True
        result["detail"] = f"OpenCV {version} 可用（组件运行环境），但缺少 face_recognition: {runtime.get('face_error') or face_error}"
        result["error"] = "需要安装 face_recognition 或补齐人脸模型文件"
    elif has_cv2 and not has_face_rec:
        result["detail"] = f"人脸识别不可用: {face_error}"
        result["error"] = "需要安装 face_recognition 或补齐人脸模型文件"
    elif runtime.get("runtime_available") is False and runtime.get("cv2_error"):
        result["detail"] = f"组件运行环境不可用: {runtime.get('cv2_error')}"
        result["error"] = "需要修复组件虚拟环境"
    elif not has_cv2:
        result["detail"] = f"缺少 OpenCV: {cv2_error}"
        result["error"] = "需要安装 opencv-python"
    else:
        result["detail"] = "缺少依赖"
        result["error"] = "需要安装 face_recognition 和 opencv-python"
    return result


def _module_source_text(module_name: str) -> str:
    module = sys.modules.get(module_name)
    if module is None:
        module = importlib.import_module(module_name)

    module_file = getattr(module, "__file__", "")
    if module_file:
        path = Path(module_file)
        if path.is_file():
            return path.read_text(encoding="utf-8")

    loader = getattr(module, "__loader__", None)
    get_source = getattr(loader, "get_source", None)
    if get_source is not None:
        source = get_source(module_name)
        if source:
            return source

    raise RuntimeError(f"无法导出组件模块源码：{module_name}")


def _prepare_face_runtime_modules() -> Path:
    modules_dir = FACE_DIR / "runtime_modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    for module_name in ("face_manager", "sensitive_json", "secure_json"):
        target = modules_dir / f"{module_name}.py"
        source = _module_source_text(module_name)
        if not target.exists() or target.read_text(encoding="utf-8") != source:
            target.write_text(source, encoding="utf-8")
    return modules_dir


def _run_face_call_in_runtime(function_name: str, payload: dict[str, Any], timeout: int = 35) -> dict[str, Any]:
    py, py_error = _runtime_python_status()
    if not py:
        return {"ok": False, "error": f"组件运行环境不可用：{py_error}"}

    try:
        module_dir = _prepare_face_runtime_modules()
    except Exception as exc:
        return {"ok": False, "error": f"准备人脸识别组件模块失败：{exc}"}

    script = r'''
import json
import os
import sys
from pathlib import Path

os.environ["COMPANION_FACE_SUBPROCESS"] = "1"

payload = json.loads(sys.argv[1])
data_dir = Path(payload["data_dir"])
function_name = payload["function"]
args = payload.get("args", {})

import face_manager

face_manager.init_face_manager(data_dir)
func = getattr(face_manager, function_name)
result = func(**args)
print("__FACE_RESULT__" + json.dumps(result, ensure_ascii=False))
'''
    call_payload = {
        "data_dir": str(FACE_DIR.parent),
        "function": function_name,
        "args": payload,
    }
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["COMPANION_FACE_SUBPROCESS"] = "1"
    module_dir_text = str(module_dir)
    env["PYTHONPATH"] = module_dir_text + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        proc = subprocess.run(
            [py, "-c", script, json.dumps(call_payload, ensure_ascii=False)],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=env,
            cwd=module_dir_text,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "组件运行环境执行超时", "message": "人脸识别组件响应过慢，请确认摄像头未被其他程序占用后重试。"}
    except Exception as exc:
        return {"ok": False, "error": f"组件运行环境执行失败：{exc}"}

    output = (proc.stdout or "").splitlines()
    for line in reversed(output):
        if line.startswith("__FACE_RESULT__"):
            try:
                result = json.loads(line[len("__FACE_RESULT__"):])
                if isinstance(result, dict):
                    result.setdefault("runtime", "component")
                    return result
            except Exception as exc:
                return {"ok": False, "error": f"组件返回解析失败：{exc}"}
    detail = (proc.stderr or proc.stdout or "").strip()
    return {"ok": False, "error": detail or f"组件运行环境退出：{proc.returncode}"}


def _open_camera(cv2_mod, camera_index: int):
    camera = cv2_mod.VideoCapture(camera_index, cv2_mod.CAP_DSHOW)
    deadline = time.monotonic() + CAMERA_OPEN_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if camera.isOpened():
            return camera
        time.sleep(0.05)
    try:
        camera.release()
    except Exception:
        pass

    camera = cv2_mod.VideoCapture(camera_index)
    deadline = time.monotonic() + CAMERA_OPEN_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if camera.isOpened():
            return camera
        time.sleep(0.05)
    try:
        camera.release()
    except Exception:
        pass
    return None


def _read_camera_frame(cv2_mod, camera):
    try:
        if hasattr(cv2_mod, "CAP_PROP_BUFFERSIZE"):
            camera.set(cv2_mod.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    deadline = time.monotonic() + CAMERA_READ_TIMEOUT_SEC
    last_frame = None
    while time.monotonic() < deadline:
        ok, frame = camera.read()
        if ok and frame is not None:
            last_frame = frame
            break
        time.sleep(0.08)
    if last_frame is None:
        return False, None
    return True, last_frame


def _load_encodings() -> dict[str, Any]:
    """Load face encodings from file."""
    data = read_sensitive_json(ENCODINGS_FILE, {"faces": [], "version": 1})
    if "faces" not in data:
        data["faces"] = []
    return data


def _save_encodings(data: dict[str, Any]) -> None:
    """Save face encodings to file."""
    write_sensitive_json(ENCODINGS_FILE, data)


def _load_log() -> list[dict[str, Any]]:
    """Load face recognition log."""
    data = read_sensitive_json(FACE_LOG_FILE, {"logs": []})
    if isinstance(data, dict) and isinstance(data.get("logs"), list):
        return data["logs"]
    return []


def _save_log(logs: list[dict[str, Any]]) -> None:
    """Save face recognition log."""
    write_sensitive_json(FACE_LOG_FILE, {"logs": logs})


def _log_recognition(event_type: str, details: dict[str, Any]) -> None:
    """Add a log entry."""
    logs = _load_log()
    entry = {
        "time": datetime.now().isoformat(),
        "type": event_type,
        **details,
    }
    logs.append(entry)
    # Keep only last 1000 entries
    if len(logs) > 1000:
        logs = logs[-1000:]
    _save_log(logs)


# ---------------------------------------------------------------------------
# Face detection (detect faces in image, return locations)
# ---------------------------------------------------------------------------

def detect_faces_in_image(image_path: Path) -> dict[str, Any]:
    """Detect faces in an image and return their locations.

    Returns:
        {
            "ok": bool,
            "faces": [{"top": int, "right": int, "bottom": int, "left": int, "confidence": float}],
            "count": int,
            "error": str or None
        }
    """
    if not face_recognition_available():
        return {"ok": False, "faces": [], "count": 0, "error": "face_recognition 或 cv2 未安装"}

    try:
        # Load image
        image = face_recognition.load_image_file(str(image_path))
        
        # Detect faces using HOG model (faster) or CNN model (more accurate)
        # Use HOG for speed, can switch to CNN for better accuracy
        face_locations = face_recognition.face_locations(image, model="hog")
        
        faces = []
        for top, right, bottom, left in face_locations:
            faces.append({
                "top": top,
                "right": right,
                "bottom": bottom,
                "left": left,
            })
        
        return {
            "ok": True,
            "faces": faces,
            "count": len(faces),
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "faces": [], "count": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Face registration (save face encoding with label)
# ---------------------------------------------------------------------------

def register_face_from_image(image_path: Path, name: str) -> dict[str, Any]:
    """Register a face from an image file.

    Args:
        image_path: Path to the image containing the face
        name: Label/name for this face

    Returns:
        {
            "ok": bool,
            "face_id": str,
            "name": str,
            "error": str or None,
            "message": str
        }
    """
    if not face_recognition_available():
        return {"ok": False, "face_id": "", "name": name, "error": "face_recognition 或 cv2 未安装"}

    try:
        # Load image
        image = face_recognition.load_image_file(str(image_path))
        
        # Detect faces
        face_locations = face_recognition.face_locations(image, model="hog")
        face_encodings = face_recognition.face_encodings(image, face_locations)
        
        if len(face_encodings) == 0:
            return {
                "ok": False,
                "face_id": "",
                "name": name,
                "error": "图片中未检测到人脸",
                "message": "请确保图片中有清晰可见的人脸",
            }
        
        if len(face_encodings) > 1:
            return {
                "ok": False,
                "face_id": "",
                "name": name,
                "error": f"图片中检测到 {len(face_encodings)} 张人脸，请使用只有一张人脸的图片",
                "message": "注册人脸时图片应该只包含一张人脸",
            }
        
        # Generate face ID
        face_id = f"face_{int(time.time() * 1000)}"
        
        # Save encoding
        encoding = face_encodings[0].tolist()  # Convert numpy array to list
        
        # Save original image (copy to known faces directory)
        safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        saved_image_path = KNOWN_FACES_DIR / f"{safe_name}_{face_id}.jpg"
        shutil.copy2(image_path, saved_image_path)
        
        # Update encodings file
        data = _load_encodings()
        data["faces"].append({
            "id": face_id,
            "name": name,
            "encoding": encoding,
            "image": saved_image_path.name,
            "registered_at": datetime.now().isoformat(),
        })
        _save_encodings(data)
        
        # Log registration
        _log_recognition("register", {"face_id": face_id, "name": name})
        
        return {
            "ok": True,
            "face_id": face_id,
            "name": name,
            "error": None,
            "message": f"已注册人脸：{name}",
        }
    except Exception as exc:
        return {"ok": False, "face_id": "", "name": name, "error": str(exc), "message": f"注册失败：{exc}"}


def register_face_from_camera(name: str, camera_index: int = 0) -> dict[str, Any]:
    """Register a face from camera capture.

    Args:
        name: Label/name for this face
        camera_index: Camera device index

    Returns:
        {
            "ok": bool,
            "face_id": str,
            "name": str,
            "error": str or None,
            "message": str,
            "image_path": str (temporary image path)
        }
    """
    if not face_recognition_available():
        if os.environ.get("COMPANION_FACE_SUBPROCESS") != "1":
            return _run_face_call_in_runtime(
                "register_face_from_camera",
                {"name": name, "camera_index": camera_index},
                timeout=35,
            )
        return {"ok": False, "face_id": "", "name": name, "error": "face_recognition 或 cv2 未安装"}

    cv2_mod = _get_cv2_module()
    if cv2_mod is None:
        return {"ok": False, "face_id": "", "name": name, "error": "cv2 未安装"}

    camera = None
    try:
        camera = _open_camera(cv2_mod, camera_index)
        if camera is None:
            return {
                "ok": False,
                "face_id": "",
                "name": name,
                "error": f"无法打开摄像头 {camera_index}",
                "message": "请确认摄像头权限和设备状态",
            }

        ok, frame = _read_camera_frame(cv2_mod, camera)
        if not ok:
            return {
                "ok": False,
                "face_id": "",
                "name": name,
                "error": "摄像头读取超时",
                "message": "摄像头已打开，但在限定时间内没有读到画面",
            }

        # Save frame temporarily
        temp_path = FACE_DIR / f"temp_capture_{int(time.time() * 1000)}.jpg"
        cv2_mod.imwrite(str(temp_path), frame)

        # Register from this image
        result = register_face_from_image(temp_path, name)
        if not isinstance(result, dict):
            result = {
                "ok": False,
                "face_id": "",
                "name": name,
                "error": "注册流程没有返回有效结果",
                "message": "摄像头捕获成功，但人脸注册没有返回有效结果",
            }

        # Clean up temp file if registration failed
        if not result.get("ok") and temp_path.exists():
            temp_path.unlink()

        result["image_path"] = str(temp_path) if temp_path.exists() else ""
        return result

    except Exception as exc:
        return {"ok": False, "face_id": "", "name": name, "error": str(exc), "message": f"摄像头注册失败：{exc}"}

    finally:
        if camera is not None:
            camera.release()


# ---------------------------------------------------------------------------
# Face recognition (identify faces in image)
# ---------------------------------------------------------------------------

def recognize_faces_in_image(image_path: Path, tolerance: float = 0.6) -> dict[str, Any]:
    """Recognize faces in an image against registered faces.

    Args:
        image_path: Path to the image to recognize
        tolerance: Recognition tolerance (lower = stricter, default 0.6)

    Returns:
        {
            "ok": bool,
            "faces": [{"name": str, "location": dict, "confidence": float, "known": bool}],
            "unknown_count": int,
            "known_count": int,
            "error": str or None
        }
    """
    if not face_recognition_available():
        return {"ok": False, "faces": [], "unknown_count": 0, "known_count": 0, "error": "face_recognition 或 cv2 未安装"}

    try:
        # Load registered encodings
        data = _load_encodings()
        known_encodings = []
        known_faces = []
        for face in data.get("faces", []):
            if "encoding" in face and "name" in face:
                known_encodings.append(face["encoding"])
                known_faces.append(face)
        
        # Load image
        image = face_recognition.load_image_file(str(image_path))
        
        # Detect and encode faces in image
        face_locations = face_recognition.face_locations(image, model="hog")
        face_encodings = face_recognition.face_encodings(image, face_locations)
        
        recognized_faces = []
        unknown_count = 0
        known_count = 0
        
        for i, encoding in enumerate(face_encodings):
            location = face_locations[i]
            
            # Compare with known faces
            matches = face_recognition.compare_faces(known_encodings, encoding, tolerance=tolerance)
            face_distances = face_recognition.face_distance(known_encodings, encoding)
            
            name = "未知"
            confidence = 0.0
            known = False
            
            if len(face_distances) > 0:
                best_match_index = face_distances.argmin()
                if matches[best_match_index]:
                    matched_face = known_faces[best_match_index]
                    name = matched_face.get("name", "")
                    confidence = 1 - face_distances[best_match_index]
                    known = True
                    known_count += 1
                else:
                    unknown_count += 1
            else:
                unknown_count += 1
            
            recognized_faces.append({
                "name": name,
                "location": {
                    "top": location[0],
                    "right": location[1],
                    "bottom": location[2],
                    "left": location[3],
                },
                "confidence": round(confidence, 3),
                "known": known,
                "id": matched_face.get("id", "") if known else "",
            })
        
        # Log recognition
        if recognized_faces:
            known_names_found = [f["name"] for f in recognized_faces if f["known"]]
            _log_recognition("recognize", {
                "total": len(recognized_faces),
                "known": known_count,
                "unknown": unknown_count,
                "names": known_names_found,
            })
        
        return {
            "ok": True,
            "faces": recognized_faces,
            "unknown_count": unknown_count,
            "known_count": known_count,
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "faces": [], "unknown_count": 0, "known_count": 0, "error": str(exc)}


def recognize_from_camera(camera_index: int = 0, tolerance: float = 0.6) -> dict[str, Any]:
    """Recognize faces from camera capture.

    Args:
        camera_index: Camera device index
        tolerance: Recognition tolerance

    Returns:
        {
            "ok": bool,
            "faces": [...],
            "unknown_count": int,
            "known_count": int,
            "error": str or None,
            "message": str,
            "image_path": str
        }
    """
    if not face_recognition_available():
        if os.environ.get("COMPANION_FACE_SUBPROCESS") != "1":
            return _run_face_call_in_runtime(
                "recognize_from_camera",
                {"camera_index": camera_index, "tolerance": tolerance},
                timeout=30,
            )
        return {"ok": False, "faces": [], "unknown_count": 0, "known_count": 0, "error": "face_recognition 或 cv2 未安装"}

    cv2_mod = _get_cv2_module()
    if cv2_mod is None:
        return {"ok": False, "faces": [], "unknown_count": 0, "known_count": 0, "error": "cv2 未安装"}

    camera = None
    try:
        camera = _open_camera(cv2_mod, camera_index)
        if camera is None:
            return {
                "ok": False,
                "faces": [],
                "unknown_count": 0,
                "known_count": 0,
                "error": f"无法打开摄像头 {camera_index}",
                "message": "请确认摄像头权限和设备状态",
            }

        ok, frame = _read_camera_frame(cv2_mod, camera)
        if not ok:
            return {
                "ok": False,
                "faces": [],
                "unknown_count": 0,
                "known_count": 0,
                "error": "摄像头读取超时",
                "message": "摄像头已打开，但在限定时间内没有读到画面",
            }

        capture_path = FACE_DIR / f"recognize_capture_{int(time.time() * 1000)}.jpg"
        cv2_mod.imwrite(str(capture_path), frame)
        result = recognize_faces_in_image(capture_path, tolerance)

        if result.get("ok"):
            faces = result.get("faces", [])
            if len(faces) == 0:
                result["message"] = "摄像头画面中未检测到人脸"
            else:
                known_names = [f["name"] for f in faces if f["known"]]
                if known_names:
                    result["message"] = f"识别到 {len(faces)} 张人脸，已知人脸：{', '.join(known_names)}"
                else:
                    result["message"] = f"识别到 {len(faces)} 张人脸，全部为未知人脸"

        result["image_path"] = str(capture_path)
        return result
    except Exception as exc:
        return {"ok": False, "faces": [], "unknown_count": 0, "known_count": 0, "error": str(exc)}
    finally:
        if camera is not None:
            camera.release()


# ---------------------------------------------------------------------------
# Face management (list, delete, update)
# ---------------------------------------------------------------------------

def list_registered_faces() -> list[dict[str, Any]]:
    """List all registered faces."""
    data = _load_encodings()
    faces = []
    for face in data.get("faces", []):
        faces.append({
            "id": face.get("id", ""),
            "name": face.get("name", ""),
            "image": face.get("image", ""),
            "registered_at": face.get("registered_at", ""),
        })
    return faces


def delete_face(face_id: str) -> dict[str, Any]:
    """Delete a registered face by ID."""
    data = _load_encodings()
    faces = data.get("faces", [])
    
    deleted = None
    new_faces = []
    for face in faces:
        if face.get("id") == face_id:
            deleted = face
            # Delete image file
            image_name = face.get("image", "")
            if image_name:
                image_path = KNOWN_FACES_DIR / image_name
                if image_path.exists():
                    try:
                        image_path.unlink()
                    except Exception:
                        pass
        else:
            new_faces.append(face)
    
    if deleted is None:
        return {"ok": False, "error": f"未找到人脸 ID: {face_id}", "message": "删除失败"}
    
    data["faces"] = new_faces
    _save_encodings(data)
    
    # Log deletion
    _log_recognition("delete", {"face_id": face_id, "name": deleted.get("name", "")})
    
    return {"ok": True, "error": None, "message": f"已删除人脸：{deleted.get('name', '')}"}


def update_face_name(face_id: str, new_name: str) -> dict[str, Any]:
    """Update the name of a registered face."""
    data = _load_encodings()
    faces = data.get("faces", [])
    
    found = False
    old_name = ""
    for face in faces:
        if face.get("id") == face_id:
            old_name = face.get("name", "")
            face["name"] = new_name
            found = True
            break
    
    if not found:
        return {"ok": False, "error": f"未找到人脸 ID: {face_id}", "message": "更新失败"}
    
    _save_encodings(data)
    
    # Rename image file
    old_image_name = face.get("image", "")
    if old_image_name:
        old_image_path = KNOWN_FACES_DIR / old_image_name
        if old_image_path.exists():
            safe_new_name = new_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            new_image_name = f"{safe_new_name}_{face_id}.jpg"
            new_image_path = KNOWN_FACES_DIR / new_image_name
            try:
                old_image_path.rename(new_image_path)
                face["image"] = new_image_name
                _save_encodings(data)
            except Exception:
                pass
    
    # Log update
    _log_recognition("update", {"face_id": face_id, "old_name": old_name, "new_name": new_name})
    
    return {"ok": True, "error": None, "message": f"已更新人脸名称：{old_name} → {new_name}"}


# ---------------------------------------------------------------------------
# Face log management
# ---------------------------------------------------------------------------

def get_face_log(limit: int = 100) -> list[dict[str, Any]]:
    """Get recent face recognition log entries."""
    logs = _load_log()
    return logs[-limit:] if len(logs) > limit else logs


def clear_face_log() -> dict[str, Any]:
    """Clear face recognition log."""
    _save_log([])
    return {"ok": True, "message": "人脸识别日志已清空"}


# ---------------------------------------------------------------------------
# Face recognition status and summary
# ---------------------------------------------------------------------------

def face_status_text() -> str:
    """Get face recognition status summary."""
    deps = check_face_recognition_deps()
    faces = list_registered_faces()
    logs = _load_log()
    
    lines = [
        f"依赖状态：{deps['detail']}",
        f"已注册人脸：{len(faces)} 张",
        f"识别日志：{len(logs)} 条记录",
    ]
    
    if faces:
        names = [f.get("name", "") for f in faces[:5]]
        lines.append(f"人脸列表：{', '.join(names)}{'...' if len(faces) > 5 else ''}")
    
    return "\n".join(lines)


def _get_python_exe() -> str:
    """获取组件虚拟环境 Python 可执行文件路径。"""
    import _paths as path_helpers
    from _paths import python_exe

    runtime_python = getattr(path_helpers, "runtime_python_exe", None)
    if runtime_python is None:
        return python_exe()
    return runtime_python()


def _run_pip_install(packages: list[str], timeout: int = 600, utf8_mode: bool = False, no_build_isolation: bool = False) -> dict[str, Any]:
    """运行 pip install 安装指定包，返回结果字典。"""
    import subprocess, os
    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    py = _get_python_exe()

    # 强制使用国内镜像源，清除可能存在的错误环境变量和代理设置
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PIP_INDEX_URL", None)
    env.pop("PIP_EXTRA_INDEX_URL", None)
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("ALL_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    env.pop("all_proxy", None)

    # 使用国内镜像源
    index_url = "https://pypi.tuna.tsinghua.edu.cn/simple"

    # 先升级 pip
    subprocess.run(
        [py, "-m", "pip", "install", "--upgrade", "pip", "--index-url", index_url],
        check=False,
        timeout=180,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        env=env,
    )

    install_cmd = [py, "-m", "pip", "install", "--index-url", index_url]
    if no_build_isolation:
        install_cmd.append("--no-build-isolation")
    install_cmd += packages

    proc = subprocess.run(
        install_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        env=env,
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "returncode": proc.returncode,
    }


def install_cmake() -> dict[str, Any]:
    """安装 CMake（dlib 编译需要）。"""
    result = _run_pip_install(["cmake"], timeout=300)
    if result["ok"]:
        return {
            "ok": True,
            "message": " CMake 安装成功！\n\n现在可以继续安装 dlib 或 face_recognition。",
        }
    return {
        "ok": False,
        "message": f" CMake 安装失败：\n{result['stderr'][-800:] or result['stdout'][-800:]}",
    }


def _install_dlib_from_source_patched() -> dict[str, Any]:
    """下载 dlib 源码，修复 setup.py 编码问题，然后本地安装（解决中文 Windows GBK 编码错误）。"""
    import subprocess, os, tempfile, shutil
    from pathlib import Path

    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    py = _get_python_exe()
    FACE_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        # Step 1: 下载 dlib 源码
        download_dir = Path(tempfile.mkdtemp(prefix="dlib_src_", dir=str(FACE_DIR)))
        download_result = subprocess.run(
            [py, "-m", "pip", "download", "--no-binary=:all:", "--no-deps", "-d", str(download_dir), "dlib"],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            env=env,
        )
        if download_result.returncode != 0:
            return {
                "ok": False,
                "message": f" 下载 dlib 源码失败：\n{download_result.stderr[-600:] or download_result.stdout[-600:]}",
            }

        # Step 2: 找到下载的源码包并解压
        tar_files = list(download_dir.glob("dlib-*.tar.gz")) + list(download_dir.glob("dlib-*.zip"))
        if not tar_files:
            return {"ok": False, "message": " 未找到下载的 dlib 源码包。"}
        src_archive = tar_files[0]

        import tarfile
        with tarfile.open(src_archive, "r:*") as tar:
            tar.extractall(path=download_dir)

        # 找到解压后的 dlib 源码目录
        extracted_dirs = [d for d in download_dir.iterdir() if d.is_dir() and d.name.startswith("dlib-")]
        if not extracted_dirs:
            return {"ok": False, "message": " 解压 dlib 源码失败。"}
        dlib_src_dir = extracted_dirs[0]

        # Step 3: 修复 setup.py 中的编码问题
        setup_py = dlib_src_dir / "setup.py"
        if setup_py.exists():
            content = setup_py.read_text(encoding="utf-8", errors="replace")
            # 修复 read_version_from_cmakelists 函数中的 open 调用
            if "read_version_from_cmakelists" in content:
                content = content.replace(
                    "open(cmake_file)",
                    "open(cmake_file, encoding='utf-8', errors='replace')"
                )
                content = content.replace(
                    "open(os.path.join(folder, 'version.txt'))",
                    "open(os.path.join(folder, 'version.txt'), encoding='utf-8', errors='replace')"
                )
                setup_py.write_text(content, encoding="utf-8")

        # 同时修复 CMakeLists.txt 中的编码问题（如果有 BOM 等）
        cmake_file = dlib_src_dir / "CMakeLists.txt"
        if cmake_file.exists():
            content = cmake_file.read_text(encoding="utf-8-sig", errors="replace")
            cmake_file.write_text(content, encoding="utf-8")

        # Step 4: 本地安装 dlib
        install_result = subprocess.run(
            [py, "-X", "utf8", "-m", "pip", "install", "--no-build-isolation", str(dlib_src_dir)],
            capture_output=True,
            text=True,
            timeout=900,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            env=env,
            cwd=str(dlib_src_dir),
        )

        # 清理临时目录
        shutil.rmtree(download_dir, ignore_errors=True)

        if install_result.returncode == 0:
            return {
                "ok": True,
                "message": " dlib 安装成功（源码编译 + 编码修复）！\n\n现在可以继续安装 face_recognition。",
            }
        else:
            return {
                "ok": False,
                "message": (
                    " dlib 源码编译安装失败。\n\n"
                    f"错误信息：{install_result.stderr[-800:] or install_result.stdout[-800:]}\n\n"
                    "dlib 编译需要 Visual Studio Build Tools (C++ 工作负载)。\n"
                    "下载地址：https://visualstudio.microsoft.com/visual-cpp-build-tools/"
                ),
            }
    except Exception as e:
        return {"ok": False, "message": f" dlib 源码安装异常：{str(e)}"}


def install_dlib_binary() -> dict[str, Any]:
    """安装预编译的 dlib（优先 dlib-binary，失败则用 cmake 编译 dlib）。"""
    # 先尝试 dlib-binary（预编译版本，不需要编译）
    result = _run_pip_install(["dlib-binary"], timeout=600)
    if result["ok"]:
        return {
            "ok": True,
            "message": " dlib-binary 安装成功！\n\n现在可以继续安装 face_recognition。",
        }

    # dlib-binary 失败，尝试先装 cmake 再编译 dlib
    cmake_result = _run_pip_install(["cmake"], timeout=300)
    if not cmake_result["ok"]:
        return {
            "ok": False,
            "message": (
                " dlib-binary 安装失败，且 CMake 也安装失败。\n\n"
                f"dlib-binary 错误：{result['stderr'][-400:]}\n"
                f"cmake 错误：{cmake_result['stderr'][-400:]}\n\n"
                "请确保已安装 Visual Studio Build Tools (C++ 工作负载)。"
            ),
        }

    # 先安装构建依赖（setuptools + wheel），用于 --no-build-isolation
    _run_pip_install(["setuptools", "wheel"], timeout=300, utf8_mode=True)

    # 尝试方式1：--no-build-isolation + UTF-8 模式
    dlib_result = _run_pip_install(["dlib"], timeout=900, utf8_mode=True, no_build_isolation=True)
    if dlib_result["ok"]:
        return {
            "ok": True,
            "message": " dlib 安装成功（通过 CMake 编译）！\n\n现在可以继续安装 face_recognition。",
        }

    # 尝试方式2：默认方式 + UTF-8 环境变量
    dlib_result2 = _run_pip_install(["dlib"], timeout=900, utf8_mode=True)
    if dlib_result2["ok"]:
        return {
            "ok": True,
            "message": " dlib 安装成功（通过 CMake 编译）！\n\n现在可以继续安装 face_recognition。",
        }

    # 尝试方式3：下载源码手动修复编码后安装（终极方案）
    source_result = _install_dlib_from_source_patched()
    if source_result["ok"]:
        return source_result

    # 所有方式都失败
    last_error = source_result["message"]
    if "UnicodeDecodeError" in dlib_result.get("stderr", "") or "gbk" in dlib_result.get("stderr", "").lower():
        last_error = (
            " dlib 编译失败（编码问题）。\n\n"
            "已尝试多种 UTF-8 编码方案均失败。\n\n"
            "建议方案：\n"
            "1. 安装 Visual Studio Build Tools (C++ 工作负载)\n"
            "2. 下载地址：https://visualstudio.microsoft.com/visual-cpp-build-tools/\n"
            "3. 安装后重试\n\n"
            f"最后错误：{dlib_result['stderr'][-500:] or dlib_result['stdout'][-500:]}"
        )
    return {"ok": False, "message": last_error}


def install_face_recognition_portable() -> str:
    """一键安装人脸识别全部依赖（cmake → dlib → face_recognition + opencv）。"""
    FACE_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: 安装 cmake
    cmake_result = install_cmake()
    if not cmake_result["ok"]:
        return cmake_result["message"]

    # Step 2: 安装 dlib-binary（预编译版本优先）
    dlib_result = install_dlib_binary()
    if not dlib_result["ok"]:
        return dlib_result["message"]

    # Step 3: 安装 face_recognition + opencv-python + face_recognition_models
    face_result = _run_pip_install(["face-recognition", "opencv-python", "face_recognition_models"], timeout=600)
    if not face_result["ok"]:
        return (
            " face_recognition 安装失败：\n\n"
            f"{face_result['stderr'][-800:] or face_result['stdout'][-800:]}"
        )

    _probe_optional_deps(refresh_paths=True)
    return (
        " 人脸识别全部依赖安装完成！\n\n"
        "已安装：cmake + dlib + face_recognition + opencv-python\n\n"
        "现在可以使用人脸识别功能：\n"
        "• /face_register 名字 - 从摄像头注册人脸\n"
        "• /face_recognize - 从摄像头识别人脸\n"
        "• /face_list - 查看已注册的人脸\n"
        "• /face_log - 查看识别日志"
    )


def download_vs_build_tools(install: bool = True) -> dict[str, Any]:
    """下载 Visual Studio Build Tools 安装器并可选自动安装 C++ 工作负载。

    Args:
        install: True=下载后自动启动安装（需要管理员权限），False=仅下载
    """
    import subprocess, os, urllib.request, ctypes
    from pathlib import Path

    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # VS Build Tools 官方下载链接（引导安装器，约 1-2MB）
    url = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
    download_path = FACE_DIR / "vs_BuildTools.exe"
    FACE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # 下载安装器
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        download_path.write_bytes(data)

        if not download_path.exists():
            return {"ok": False, "message": " VS Build Tools 安装器下载失败。"}

        if not install:
            return {
                "ok": True,
                "message": (
                    f" VS Build Tools 安装器已下载到：\n{download_path}\n\n"
                    "请双击运行安装，安装时勾选「使用 C++ 的桌面开发」工作负载。"
                ),
            }

        # 自动安装：使用静默模式安装 C++ 工作负载
        # --quiet: 无界面静默安装  --wait: 等待完成  --norestart: 不重启
        # --add Microsoft.VisualStudio.Workload.VCTools: C++ 桌面开发工作负载
        # --includeRecommended: 包含推荐组件（Windows SDK 等）
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not is_admin:
            # 非管理员：尝试以管理员权限启动（UAC 弹窗）
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", str(download_path),
                "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended",
                None, 1  # SW_SHOWNORMAL
            )
            if ret <= 32:
                return {
                    "ok": False,
                    "message": (
                        " 需要管理员权限来安装 VS Build Tools。\n\n"
                        f"安装器已下载到：{download_path}\n"
                        "请右键「以管理员身份运行」。"
                    ),
                }
            return {
                "ok": True,
                "message": (
                    " VS Build Tools 安装器已启动（需要管理员权限）。\n\n"
                    "正在后台静默安装 C++ 工作负载，这可能需要 10-30 分钟。\n"
                    "安装完成后请重新安装 dlib。"
                ),
            }

        # 已有管理员权限：直接静默安装
        proc = subprocess.run(
            [str(download_path), "--quiet", "--wait", "--norestart",
             "--add", "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended"],
            capture_output=True,
            text=True,
            timeout=3600,  # 最多等 1 小时
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )

        if proc.returncode == 0:
            return {
                "ok": True,
                "message": (
                    " Visual Studio Build Tools (C++ 工作负载) 安装完成！\n\n"
                    "现在可以重新安装 dlib 了。"
                ),
            }
        else:
            # 安装器返回码含义：0=成功, 3010=成功但需重启, 其他=失败
            if proc.returncode == 3010:
                return {
                    "ok": True,
                    "message": (
                        " Visual Studio Build Tools 安装完成！\n\n"
                        "警告： 需要重启电脑才能完成安装。\n"
                        "重启后可以重新安装 dlib。"
                    ),
                }
            return {
                "ok": False,
                "message": (
                    f" VS Build Tools 安装失败（返回码 {proc.returncode}）。\n\n"
                    f"输出：{(proc.stdout or '')[-500:]}\n"
                    f"错误：{(proc.stderr or '')[-500:]}\n\n"
                    f"安装器路径：{download_path}\n"
                    "可手动运行安装。"
                ),
            }
    except Exception as e:
        return {"ok": False, "message": f" VS Build Tools 下载/安装异常：{str(e)}"}
