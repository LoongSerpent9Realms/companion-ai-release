"""Local routine tracking and reminders for Companion AI."""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path

from _paths import module_root, data_dir
from secure_json import read_secure_json, write_secure_json

try:
    import ctypes
    _HAS_CTYPES = True
except ImportError:
    _HAS_CTYPES = False


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
ROUTINE_FILE = DATA_DIR / "routine.json"
ROUTINE_KEY_FILE = DATA_DIR / "routine.key"
STARTUP_CMD_NAME = "CompanionAI-Routine.cmd"
_shutdown_handler_ref = None
_shutdown_recorded = False


def _default_store() -> dict:
    return {
        "enabled": False,
        "reminders_enabled": True,
        "autostart_enabled": False,
        "idle_rest_seconds": 45 * 60,
        "break_reminder_seconds": 2 * 60 * 60,
        "last_tick": 0,
        "active_since": 0,
        "in_rest": False,
        "rest_started_at": 0,
        "last_break_reminder": 0,
        "last_daily_summary": "",
        "events": [],
        "reminders": [],
    }


def load_routine() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    default = _default_store()
    data, state = read_secure_json(ROUTINE_FILE, ROUTINE_KEY_FILE, default)
    if state in {"missing", "plaintext", "reset"}:
        data = _normalize_store(data)
        save_routine(data)
    return _normalize_store(data)


def _normalize_store(data: dict) -> dict:
    defaults = _default_store()
    if isinstance(data, dict):
        defaults.update(data)
    defaults.setdefault("events", [])
    defaults.setdefault("reminders", [])
    return defaults


def save_routine(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_secure_json(ROUTINE_FILE, ROUTINE_KEY_FILE, _normalize_store(store))


def reset_routine_encryption_key() -> str:
    if ROUTINE_KEY_FILE.exists():
        ROUTINE_KEY_FILE.unlink()
    save_routine(_default_store())
    return "已重置作息记录密钥，并清空作息记录。"


def routine_security_text() -> str:
    load_routine()
    return (
        "作息记录加密：已开启\n"
        f"数据文件：{ROUTINE_FILE}\n"
        f"密钥文件：{ROUTINE_KEY_FILE}\n"
        "说明：routine.json 使用本机专用密钥加密并带校验；如果密钥不匹配或文件被篡改，程序会清空并重建作息记录。"
    )


def _now() -> int:
    return int(time.time())


def _fmt(ts: int) -> str:
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.now().date().isoformat()


def _append_event(store: dict, kind: str, note: str = "", ts: int | None = None, meta: dict | None = None) -> dict:
    event = {
        "time": int(ts or _now()),
        "kind": kind,
        "note": note,
        "meta": meta or {},
    }
    events = list(store.get("events", []))
    events.append(event)
    store["events"] = events[-1000:]
    return event


def _enqueue_reminder(store: dict, text: str, category: str, due_at: int | None = None) -> None:
    if not store.get("reminders_enabled", True):
        return
    now = _now()
    reminders = list(store.get("reminders", []))
    if any(item.get("category") == category and not item.get("delivered") and item.get("text") == text for item in reminders[-8:]):
        return
    reminders.append({
        "id": f"{category}-{now}",
        "time": now,
        "due_at": int(due_at or now),
        "category": category,
        "text": text,
        "delivered": False,
    })
    store["reminders"] = reminders[-100:]


def set_routine_enabled(enabled: bool) -> dict:
    store = load_routine()
    store["enabled"] = enabled
    if enabled:
        now = _now()
        store["active_since"] = store.get("active_since") or now
        _append_event(store, "routine_on", "作息记录开启", now)
    else:
        _append_event(store, "routine_off", "作息记录暂停")
    save_routine(store)
    return store


def set_routine_reminders_enabled(enabled: bool) -> dict:
    store = load_routine()
    store["reminders_enabled"] = enabled
    _append_event(store, "reminders_on" if enabled else "reminders_off", "作息提醒开关变更")
    save_routine(store)
    return store


def record_app_start(source: str = "app") -> None:
    store = load_routine()
    now = _now()
    store["active_since"] = now
    store["last_tick"] = now
    _append_event(store, "app_start", f"{source} 启动", now, {"boot_time": system_boot_time()})
    _record_boot_seen(store, now)
    if store.get("enabled"):
        maybe_enqueue_daily_summary(store, now)
    save_routine(store)


def record_app_stop(source: str = "app") -> None:
    store = load_routine()
    _append_event(store, "app_stop", f"{source} 退出")
    store["active_since"] = 0
    save_routine(store)


def record_system_shutdown(source: str = "app", reason: str = "system_shutdown") -> None:
    global _shutdown_recorded
    if _shutdown_recorded:
        return
    _shutdown_recorded = True
    store = load_routine()
    _append_event(store, reason, f"{source} 收到系统关闭/退出信号")
    store["active_since"] = 0
    save_routine(store)


def install_shutdown_handlers(source: str = "app") -> None:
    """Best-effort shutdown recording for console/hidden Windows processes."""
    global _shutdown_handler_ref

    def _signal_handler(signum, _frame) -> None:
        record_system_shutdown(source, f"signal_{signum}")
        raise SystemExit(0)

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, _signal_handler)
            except Exception:
                pass

    if not _HAS_CTYPES:
        return

    try:
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        def _console_handler(ctrl_type: int) -> bool:
            reasons = {
                0: "ctrl_c",
                1: "ctrl_break",
                2: "console_close",
                5: "system_logoff",
                6: "system_shutdown",
            }
            record_system_shutdown(source, reasons.get(ctrl_type, f"console_ctrl_{ctrl_type}"))
            return False

        _shutdown_handler_ref = handler_type(_console_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_shutdown_handler_ref, True)
    except Exception:
        _shutdown_handler_ref = None


def _record_boot_seen(store: dict, now: int) -> None:
    boot = system_boot_time()
    if not boot:
        return
    today_events = [
        item for item in store.get("events", [])
        if item.get("kind") == "boot_seen" and abs(int(item.get("time", 0)) - boot) < 120
    ]
    if today_events:
        return
    _append_event(store, "boot_seen", "检测到本次系统开机时间", boot, {"seen_at": now})


def system_boot_time() -> int:
    if not _HAS_CTYPES:
        return 0
    try:
        tick_ms = ctypes.windll.kernel32.GetTickCount64()
        return int(time.time() - tick_ms / 1000)
    except Exception:
        return 0


def system_idle_seconds() -> int:
    if not _HAS_CTYPES:
        return 0

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    tick = ctypes.windll.kernel32.GetTickCount()
    return max(0, int((tick - info.dwTime) / 1000))


def routine_tick() -> None:
    store = load_routine()
    now = _now()
    last_tick = int(store.get("last_tick", 0))
    store["last_tick"] = now
    _record_boot_seen(store, now)

    if not store.get("enabled"):
        save_routine(store)
        return

    if last_tick and now - last_tick > 5 * 60:
        _append_event(store, "resume", "检测到应用计时中断，可能经历了休眠/锁屏/系统暂停", now, {"gap_seconds": now - last_tick})

    idle = system_idle_seconds()
    rest_threshold = int(store.get("idle_rest_seconds", 45 * 60))
    if idle >= rest_threshold and not store.get("in_rest"):
        start_at = now - idle
        store["in_rest"] = True
        store["rest_started_at"] = start_at
        _append_event(store, "rest_start", "系统长时间无输入，记录为休息/离开开始", start_at, {"idle_seconds": idle})
    elif idle < 90 and store.get("in_rest"):
        start_at = int(store.get("rest_started_at", 0))
        duration = max(0, now - start_at) if start_at else 0
        store["in_rest"] = False
        store["rest_started_at"] = 0
        _append_event(store, "rest_end", "检测到重新活动", now, {"duration_seconds": duration})
        if duration >= rest_threshold:
            _enqueue_reminder(store, f"欢迎回来。你刚离开/休息了约 {duration // 60} 分钟，要不要先用一句话记录刚才在做什么？", "return_checkin")

    active_since = int(store.get("active_since", now) or now)
    break_interval = int(store.get("break_reminder_seconds", 2 * 60 * 60))
    last_break = int(store.get("last_break_reminder", 0))
    if not store.get("in_rest") and now - active_since >= break_interval and now - last_break >= break_interval:
        store["last_break_reminder"] = now
        _enqueue_reminder(store, "你已经连续开着电脑一段时间了。要不要休息 5 分钟，顺便让我帮你总结一下当前进度？", "break")

    maybe_enqueue_daily_summary(store, now)
    save_routine(store)


def maybe_enqueue_daily_summary(store: dict, now: int) -> None:
    today = datetime.fromtimestamp(now).date().isoformat()
    if store.get("last_daily_summary") == today:
        return
    hour = datetime.fromtimestamp(now).hour
    if hour < 6:
        return
    store["last_daily_summary"] = today
    text = "早上好。我记录到今天已经启动，可以先花半分钟定一下今天最重要的一件事。"
    yesterday = daily_summary_text((datetime.fromtimestamp(now) - timedelta(days=1)).date().isoformat())
    if "暂无" not in yesterday:
        text += "\n\n昨天作息简报：\n" + "\n".join(yesterday.splitlines()[1:5])
    _enqueue_reminder(store, text, "daily_summary")


def pop_due_reminder() -> str:
    store = load_routine()
    if not store.get("enabled") or not store.get("reminders_enabled", True):
        return ""
    now = _now()
    for item in store.get("reminders", []):
        if not item.get("delivered") and int(item.get("due_at", 0)) <= now:
            item["delivered"] = True
            item["delivered_at"] = now
            save_routine(store)
            return str(item.get("text", ""))
    save_routine(store)
    return ""


def pending_reminders_text() -> str:
    store = load_routine()
    pending = [item for item in store.get("reminders", []) if not item.get("delivered")]
    if not pending:
        return "待提醒：暂无。"
    lines = ["待提醒："]
    for item in pending[-8:]:
        lines.append(f"- {_fmt(int(item.get('due_at', 0)))} {item.get('text', '')}")
    return "\n".join(lines)


def _events_for_day(day: str) -> list[dict]:
    events = []
    for event in load_routine().get("events", []):
        ts = int(event.get("time", 0))
        if ts and datetime.fromtimestamp(ts).date().isoformat() == day:
            events.append(event)
    return events


def daily_summary_text(day: str | None = None) -> str:
    day = day or _today()
    events = _events_for_day(day)
    if not events:
        return f"{day} 作息简报：暂无记录。"

    starts = [e for e in events if e.get("kind") in {"boot_seen", "app_start"}]
    rest_starts = [e for e in events if e.get("kind") == "rest_start"]
    rest_ends = [e for e in events if e.get("kind") == "rest_end"]
    first = min(events, key=lambda e: int(e.get("time", 0)))
    last = max(events, key=lambda e: int(e.get("time", 0)))
    rest_minutes = sum(int(e.get("meta", {}).get("duration_seconds", 0)) for e in rest_ends) // 60
    lines = [
        f"{day} 作息简报：",
        f"首次记录：{_fmt(int(first.get('time', 0)))}（{first.get('kind')}）",
        f"最近记录：{_fmt(int(last.get('time', 0)))}（{last.get('kind')}）",
        f"启动/开机相关：{len(starts)} 次",
        f"长时间离开/休息：{len(rest_starts)} 次，已确认恢复 {len(rest_ends)} 次，合计约 {rest_minutes} 分钟",
    ]
    if rest_starts:
        latest_rest = rest_starts[-1]
        lines.append(f"最近休息开始：{_fmt(int(latest_rest.get('time', 0)))}")
    lines.append("建议：如果这个节奏准确，可以让我在启动后先总结昨天，并在连续使用过久时提醒你休息。")
    return "\n".join(lines)


def routine_status_text() -> str:
    store = load_routine()
    events = store.get("events", [])
    latest = events[-1] if events else None
    lines = [
        "作息记录：",
        f"记录开关：{'开启' if store.get('enabled') else '关闭'}",
        f"提醒开关：{'开启' if store.get('reminders_enabled') else '关闭'}",
        f"开机自启：{'开启' if is_autostart_enabled() else '关闭'}",
        f"系统空闲：{system_idle_seconds()} 秒",
        f"记录事件：{len(events)} 条",
    ]
    if latest:
        lines.append(f"最近事件：{_fmt(int(latest.get('time', 0)))} {latest.get('kind')} {latest.get('note', '')}")
    lines.append("")
    lines.append(daily_summary_text())
    lines.append("")
    lines.append(pending_reminders_text())
    lines.append("")
    lines.append("命令：/routine_on /routine_off /routine_summary /routine_reminders_on /routine_reminders_off /startup_on /startup_off")
    return "\n".join(lines)


def startup_folder() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_cmd_path() -> Path:
    return startup_folder() / STARTUP_CMD_NAME


def is_autostart_enabled() -> bool:
    return startup_cmd_path().exists()


def set_autostart_enabled(enabled: bool) -> str:
    folder = startup_folder()
    path = startup_cmd_path()
    store = load_routine()
    if enabled:
        folder.mkdir(parents=True, exist_ok=True)
        launcher_ai = ROOT / "Launch Companion AI.ps1"
        launcher_pet = ROOT / "Launch Companion Pet.ps1"
        lines = [
            "@echo off",
            f'cd /d "{ROOT}"',
            f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{launcher_ai}"',
            f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{launcher_pet}"',
        ]
        path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        store["autostart_enabled"] = True
        _append_event(store, "startup_on", "已创建开机自启入口")
        save_routine(store)
        return f"已开启开机自启：{path}"
    if path.exists():
        path.unlink()
    store["autostart_enabled"] = False
    _append_event(store, "startup_off", "已移除开机自启入口")
    save_routine(store)
    return "已关闭开机自启。"


def handle_routine_command(message: str) -> str | None:
    if message in {"/routine", "/routine_status"}:
        return routine_status_text()
    if message == "/routine_security":
        return routine_security_text()
    if message == "/routine_reset_key":
        return reset_routine_encryption_key()
    if message == "/routine_on":
        set_routine_enabled(True)
        return "已开启作息记录：会记录应用启动/退出、系统开机时间、长时间无输入和恢复活动，用于本地作息总结。"
    if message == "/routine_off":
        set_routine_enabled(False)
        return "已关闭作息记录。已有记录保留，可继续用 /routine 查看。"
    if message == "/routine_summary":
        return daily_summary_text()
    if message == "/routine_reminders_on":
        set_routine_reminders_enabled(True)
        return "已开启作息提醒。"
    if message == "/routine_reminders_off":
        set_routine_reminders_enabled(False)
        return "已关闭作息提醒，但作息记录仍可继续保存。"
    if message == "/routine_pop":
        return pop_due_reminder() or "当前没有到期提醒。"
    if message == "/startup_on":
        return set_autostart_enabled(True)
    if message == "/startup_off":
        return set_autostart_enabled(False)
    return None
