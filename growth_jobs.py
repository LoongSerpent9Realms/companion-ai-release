"""Single local background queue for candidate TinyLLM training."""

from __future__ import annotations

import threading
import time
from typing import Any


_lock = threading.Lock()
_thread: threading.Thread | None = None
_cancel = threading.Event()
_status: dict[str, Any] = {"state": "idle", "stage": "idle", "progress": 0, "message": "暂无训练任务", "started_at": 0, "finished_at": 0, "result": None}


def status() -> dict[str, Any]:
    with _lock:
        return dict(_status)


def start(epochs: int = 3) -> dict[str, Any]:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return {"ok": False, "error": "已有训练任务正在运行。", **_status}
        _cancel.clear()
        _status.update({"state": "queued", "stage": "queued", "progress": 0, "message": "训练任务已排队", "started_at": int(time.time()), "finished_at": 0, "result": None, "epochs": max(1, min(int(epochs), 50))})

        def run() -> None:
            with _lock:
                _status.update({"state": "training", "stage": "prepare", "progress": 2, "message": "正在准备候选 TinyLLM；取消会阻止后续激活"})
            try:
                def update_progress(stage: str, message: str, progress: int) -> None:
                    with _lock:
                        _status.update({"state": "training", "stage": stage, "progress": progress, "message": message})
                from growth_loop import train_candidate
                if _cancel.is_set():
                    result = {"ok": False, "cancelled": True, "error": "训练在开始前已取消。"}
                else:
                    result = train_candidate(epochs=_status["epochs"], cancel_check=_cancel.is_set, progress_callback=update_progress)
                with _lock:
                    cancelled = bool(_cancel.is_set() or result.get("cancelled"))
                    _status.update({"state": "cancelled" if cancelled else ("done" if result.get("ok") else "failed"), "stage": "cancelled" if cancelled else "done", "progress": 100, "message": "训练已取消，候选不会激活。" if cancelled else ("候选模型已通过并激活。" if result.get("ok") else result.get("error", "候选未通过评测")), "finished_at": int(time.time()), "result": result})
            except Exception as exc:
                with _lock:
                    _status.update({"state": "failed", "message": str(exc), "finished_at": int(time.time()), "result": {"ok": False, "error": str(exc)}})

        _thread = threading.Thread(target=run, daemon=True, name="growth-training")
        _thread.start()
        return {"ok": True, **_status}


def cancel() -> dict[str, Any]:
    with _lock:
        if not _thread or not _thread.is_alive():
            return {"ok": False, "error": "没有可取消的训练任务。", **_status}
        _cancel.set()
        _status["message"] = "已请求取消；当前训练批次结束后将停止，且候选不会激活。"
        return {"ok": True, **_status}
