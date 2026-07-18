from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from _paths import data_dir


APP_NAME = "CompanionAI"
WEB_URL = "http://127.0.0.1:59137"
PET_STYLES = {
    "auto": "打开默认桌宠",
    "classic": "打开手绘桌宠",
    "live2d": "打开 Live2D 桌宠",
    "3d": "打开 3D 桌宠",
}
I18N = {
    "zh-CN": {
        "app_name": "AI陪伴桌宠",
        "open_pet": "打开桌宠",
        "open_settings": "打开设置",
        "stop_pets": "关闭已打开桌宠",
        "quit_all": "退出全部",
        "pet_auto": "打开默认桌宠",
        "pet_classic": "打开手绘桌宠",
        "pet_live2d": "打开 Live2D 桌宠",
        "pet_3d": "打开 3D 桌宠",
    },
    "en-US": {
        "app_name": "AI Companion Pet",
        "open_pet": "Open Pet",
        "open_settings": "Open Settings",
        "stop_pets": "Close Open Pets",
        "quit_all": "Quit All",
        "pet_auto": "Open Default Pet",
        "pet_classic": "Open Classic Pet",
        "pet_live2d": "Open Live2D Pet",
        "pet_3d": "Open 3D Pet",
    },
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_dir()
RUNTIME_DIR = data_dir(ROOT) / "runtime"


def _locale() -> str:
    try:
        import json
        raw = json.loads((data_dir(ROOT) / "app_config.json").read_text(encoding="utf-8")).get("locale", "")
    except Exception:
        raw = ""
    raw = str(raw).replace("_", "-").lower()
    if raw in {"en", "en-us"}:
        return "en-US"
    return "zh-CN"


def _t(key: str) -> str:
    locale = _locale()
    return I18N.get(locale, I18N["zh-CN"]).get(key, key)


def _pet_style_label(style: str) -> str:
    return _t(f"pet_{style}") if style in PET_STYLES else _t("pet_auto")


def pid_file(name: str) -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR / f"{name}.pid"


def pet_instances_file() -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR / "pet_instances.json"


def write_pid(name: str) -> None:
    pid_file(name).write_text(str(os.getpid()), encoding="utf-8")


def remove_pid(name: str) -> None:
    try:
        pid_file(name).unlink(missing_ok=True)
    except Exception:
        pass


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def stop_pid_file(name: str) -> None:
    path = pid_file(name)
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return
    if pid == os.getpid():
        return
    _terminate_pid(pid)
    remove_pid(name)


def _read_pet_instance_pids() -> list[int]:
    path = pet_instances_file()
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        return [int(pid) for pid in data.get("pids", [])]
    except Exception:
        return []


def _write_pet_instance_pids(pids: list[int]) -> None:
    import json
    live = []
    for pid in dict.fromkeys(pids):
        if pid > 0 and pid != os.getpid():
            live.append(pid)
    pet_instances_file().write_text(json.dumps({"pids": live}), encoding="utf-8")


def _register_pet_instance(pid: int) -> None:
    _write_pet_instance_pids([*_read_pet_instance_pids(), pid])


def _stop_registered_pet_instances() -> None:
    pids = _read_pet_instance_pids()
    for pid in pids:
        _terminate_pid(pid)
    try:
        pet_instances_file().unlink(missing_ok=True)
    except Exception:
        pass


def _stop_companion_render_processes() -> None:
    """Stop Electron/Edge model-layer children that belong to this app only."""
    if os.name != "nt":
        return
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { "
        "($_.Name -in @('electron.exe','msedge.exe','msedgewebview2.exe')) -and "
        "($_.CommandLine -match 'CompanionAI|electron_pet|model_browser_|model_layer_') "
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _copy_bundled_resources() -> None:
    """In frozen mode, copy bundled resources from _internal/ next to the exe."""
    if not getattr(sys, "frozen", False):
        return
    meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    base = ROOT
    os.environ["_COMPANION_BASE_DIR"] = str(base)
    import shutil

    def copy_file_best_effort(src: Path, dst: Path, *, overwrite: bool = True) -> None:
        if not overwrite and dst.exists():
            return
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except PermissionError:
            # Runtime assets such as Electron .pak/.exe files can be locked by a
            # still-exiting pet process. Keep launching with the existing copy.
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) in {32, 1224}:
                return
            raise

    def copy_tree_best_effort(src: Path, dst: Path, *, overwrite: bool = False) -> None:
        if not src.is_dir():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            rel = item.relative_to(src)
            target = dst / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                copy_file_best_effort(item, target, overwrite=overwrite)

    html_src = meipass / "live2d_viewer.html"
    if html_src.is_file():
        copy_file_best_effort(html_src, base / "live2d_viewer.html")
    viewer3d_src = meipass / "viewer_3d.html"
    if viewer3d_src.is_file():
        copy_file_best_effort(viewer3d_src, base / "viewer_3d.html")
    official_src = meipass / "official_site.html"
    if official_src.is_file():
        copy_file_best_effort(official_src, base / "official_site.html")
    for icon_name in ("ai_icon.ico", "pet_icon.ico"):
        icon_src = meipass / icon_name
        if icon_src.is_file():
            copy_file_best_effort(icon_src, base / icon_name)
    electron_pet_src = meipass / "electron_pet"
    if electron_pet_src.is_dir():
        copy_tree_best_effort(electron_pet_src, base / "electron_pet", overwrite=True)
    electron_src = meipass / "node_modules" / "electron" / "dist"
    electron_dst = base / "node_modules" / "electron" / "dist"
    if electron_src.is_dir():
        electron_ready = (electron_dst / "electron.exe").is_file()
        copy_tree_best_effort(electron_src, electron_dst, overwrite=not electron_ready)
    marker = base / "._resources_copied"
    if marker.exists():
        return
    for name in ("data", "plugins"):
        src = meipass / name
        dst = base / name
        if src.is_dir() and not dst.exists():
            copy_tree_best_effort(src, dst)
        elif src.is_dir():
            for item in src.iterdir():
                target = dst / item.name
                if item.is_dir() and not target.exists():
                    copy_tree_best_effort(item, target)
                elif item.is_file() and not target.exists():
                    copy_file_best_effort(item, target, overwrite=False)
    marker.write_text("ok", encoding="utf-8")


def open_web_when_ready(timeout: float = 60.0) -> None:
    """Open the console only after its local HTTP server accepts requests."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_web_running():
            webbrowser.open(WEB_URL)
            return
        time.sleep(0.25)


def run_web() -> None:
    os.chdir(ROOT)
    if _is_web_running():
        webbrowser.open(WEB_URL)
        return
    write_pid("web")
    threading.Thread(target=open_web_when_ready, daemon=True).start()
    try:
        import app
        app.main()
    finally:
        remove_pid("web")


def _is_web_running() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(WEB_URL, timeout=1.5)
        return True
    except Exception:
        return False


def _ensure_web_server() -> None:
    if _is_web_running():
        return
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--web"]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve()), "--web"]
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(30):
        if _is_web_running():
            return
        time.sleep(0.5)


def _pet_command(style: str, *, manager_tray: bool) -> list[str]:
    style = style if style in PET_STYLES else "auto"
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--pet", "--style", style]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve()), "--pet", "--style", style]
    if not manager_tray:
        cmd.append("--no-manager-tray")
    return cmd


def _spawn_pet_instance(style: str) -> None:
    _ensure_web_server()
    proc = subprocess.Popen(
        _pet_command(style, manager_tray=False),
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _register_pet_instance(proc.pid)


# ---------------------------------------------------------------------------
# System tray (launcher-level — persists after pet window closes)
# ---------------------------------------------------------------------------

_tray_icon = None


def _start_tray() -> None:
    """Start the system-tray icon in a daemon thread."""
    global _tray_icon
    try:
        from PIL import Image
        import pystray
    except Exception:
        return

    # 标记已有 launcher 托盘，避免桌宠实例重复创建托盘
    os.environ["_COMPANION_HAS_LAUNCHER_TRAY"] = "1"

    icon_path = ROOT / "pet_icon.ico"
    img = Image.open(icon_path) if icon_path.exists() else None
    if img is None:
        # fallback: simple blue circle
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(39, 99, 235, 255))
        draw.text((22, 16), "C", fill=(255, 255, 255, 255))

    def _on_settings(icon, item):
        webbrowser.open(WEB_URL + "/#settings")

    def _make_open_style(style: str):
        def _handler(icon, item):
            _spawn_pet_instance(style)
        return _handler

    def _on_stop_pets(icon, item):
        _stop_registered_pet_instances()
        _stop_companion_render_processes()

    def _on_quit(icon, item):
        _stop_registered_pet_instances()
        stop_pid_file("pet")
        stop_pid_file("web")
        try:
            _tray_icon.stop()
        except Exception:
            pass
        os._exit(0)

    pet_menu = pystray.Menu(
        *(pystray.MenuItem(_pet_style_label(style), _make_open_style(style)) for style in PET_STYLES)
    )

    menu = pystray.Menu(
        pystray.MenuItem(_t("open_pet"), pet_menu),
        pystray.MenuItem(_t("open_settings"), _on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_t("stop_pets"), _on_stop_pets),
        pystray.MenuItem(_t("quit_all"), _on_quit),
    )

    _tray_icon = pystray.Icon("companion_ai", img, f"Companion AI - {_t('app_name')}", menu)

    # 在 Windows 上需要初始化 COM 才能正确显示右键菜单
    def _run_tray_with_com():
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            _tray_icon.run()
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    t = threading.Thread(target=_run_tray_with_com, daemon=True)
    t.start()


def run_pet(style: str = "auto", *, manager_tray: bool = True) -> None:
    """Run the desktop pet with a persistent launcher-level tray icon."""
    os.chdir(ROOT)
    _ensure_web_server()
    if manager_tray:
        write_pid("pet")

    # Start the tray BEFORE the pet so it persists after the pet window closes.
    if manager_tray:
        _start_tray()

    try:
        import desktop_pet
        desktop_pet.main(style)
    finally:
        if manager_tray:
            remove_pid("pet")

    # Keep the process alive so the tray icon remains accessible.
    # The user can still open settings or quit the web server from the tray.
    if manager_tray:
        while True:
            time.sleep(1)


def stop_all() -> None:
    _stop_registered_pet_instances()
    stop_pid_file("pet")
    stop_pid_file("web")
    _stop_companion_render_processes()


def health_report() -> dict:
    """Print a cross-platform health report without starting servers.

    Reads launcher pid files, pings the running web server (if any), and
    reports version/port/data directory/process status. Works on Windows,
    Linux and macOS.
    """
    def _read_pid(name: str) -> int:
        try:
            return int(pid_file(name).read_text(encoding="utf-8").strip())
        except Exception:
            return 0

    def _pid_alive(pid: int) -> bool:
        if not pid or pid <= 0:
            return False
        if os.name == "nt":
            try:
                subprocess.run(
                    ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                    capture_output=True, timeout=2,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return True
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except Exception:
            return False

    web_pid = _read_pid("web")
    pet_pid = _read_pid("pet")
    web_responds = _is_web_running()

    try:
        from app import current_app_version, PORT, HOST, ALLOW_LAN, DATA_DIR
    except Exception:
        current_app_version = lambda: "unknown"  # noqa: E731
        PORT, HOST, ALLOW_LAN, DATA_DIR = 59137, "127.0.0.1", False, ""

    report = {
        "ok": True,
        "version": current_app_version(),
        "host": HOST,
        "port": PORT,
        "mode": "lan" if ALLOW_LAN or HOST in {"0.0.0.0", "::"} else "local",
        "data_dir": str(DATA_DIR),
        "web_server": {"responding": web_responds, "pid": web_pid, "alive": _pid_alive(web_pid)},
        "pet": {"pid": pet_pid, "alive": _pid_alive(pet_pid)},
    }
    report["status"] = "running" if web_responds else ("stale_pid" if web_pid else "stopped")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Companion AI launcher")
    parser.add_argument("--web", action="store_true", help="start web app and open browser")
    parser.add_argument("--pet", action="store_true", help="start desktop pet")
    parser.add_argument("--style", choices=sorted(PET_STYLES.keys()), default="auto", help="desktop pet style")
    parser.add_argument("--no-manager-tray", action="store_true", help="do not start the launcher management tray")
    parser.add_argument("--stop", action="store_true", help="stop Companion AI processes")
    parser.add_argument("--health", action="store_true", help="print JSON health report and exit")
    args = parser.parse_args()

    if args.health:
        import json
        print(json.dumps(health_report(), ensure_ascii=False, indent=2))
        return

    _copy_bundled_resources()

    if args.stop:
        stop_all()
    elif args.pet:
        run_pet(args.style, manager_tray=not args.no_manager_tray)
    else:
        run_web()


if __name__ == "__main__":
    main()
