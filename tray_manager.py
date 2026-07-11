"""System tray icon for Companion AI.

Runs the tray icon in a daemon thread so it coexists with
Tkinter / pywebview main loops.  Provides: show/hide pet,
open settings in browser, and quit (kills pet + web server).
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

try:
    from PIL import Image
    import pystray
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False


_tray_icon = None          # pystray.Icon instance
_visible = True            # current pet visibility flag


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_tray(
    *,
    on_show=None,
    on_hide=None,
    on_quit=None,
    icon_path: str | Path | None = None,
    title: str = "Companion AI - 智能伙伴",
    name: str = "companion_ai",
    extra_items=None,
) -> None:
    """Create and show the system-tray icon (non-blocking, daemon thread).

    Parameters
    ----------
    on_show : callable | None
        Called when the user picks "显示伙伴".
    on_hide : callable | None
        Called when the user picks "隐藏伙伴".
    on_quit : callable | None
        Called when the user picks "退出".  Should terminate the app.
    icon_path : str | Path | None
        Path to a .ico / .png icon.  Falls back to a generated blue circle.
    """
    if not _HAS_TRAY:
        return

    global _tray_icon, _visible
    _visible = True

    # --- icon image --------------------------------------------------------
    img = _load_icon(icon_path)

    # --- menu --------------------------------------------------------------
    show_item = pystray.MenuItem("显示伙伴", _make_show_cb(on_show), default=True)
    hide_item = pystray.MenuItem("隐藏伙伴", _make_hide_cb(on_hide))
    sep = pystray.Menu.SEPARATOR
    settings_item = pystray.MenuItem("打开设置", _on_settings)
    quit_item = pystray.MenuItem("退出", _make_quit_cb(on_quit))

    items = [show_item, hide_item, sep, settings_item]
    if extra_items:
        items.extend([sep, *extra_items])
    items.extend([sep, quit_item])
    menu = pystray.Menu(*items)

    # --- icon --------------------------------------------------------------
    _tray_icon = pystray.Icon(
        name,
        img,
        title,
        menu,
    )

    # Run in a daemon thread so it dies with the main process.
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


def stop_tray() -> None:
    """Remove the tray icon (call before process exit when possible)."""
    global _tray_icon
    if _tray_icon is not None:
        try:
            _tray_icon.stop()
        except Exception:
            pass
        _tray_icon = None


def set_visible(v: bool) -> None:
    """Update internal visibility flag (called by show/hide callbacks)."""
    global _visible
    _visible = v


def is_visible() -> bool:
    return _visible


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _load_icon(icon_path) -> "Image.Image":
    """Load icon from *icon_path*, or generate a simple fallback."""
    # Try the provided path first.
    if icon_path:
        p = Path(icon_path)
        if p.exists():
            try:
                return Image.open(p)
            except Exception:
                pass

    # Try the default location next to this file.
    default = Path(__file__).resolve().parent / "pet_icon.ico"
    if default.exists():
        try:
            return Image.open(default)
        except Exception:
            pass

    # Fallback: draw a simple blue circle with "C".
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(39, 99, 235, 255))
    draw.text((22, 16), "C", fill=(255, 255, 255, 255))
    return img


def _make_show_cb(cb):
    def _handler(icon, item):
        set_visible(True)
        if cb:
            cb()
    return _handler


def _make_hide_cb(cb):
    def _handler(icon, item):
        set_visible(False)
        if cb:
            cb()
    return _handler


def _make_quit_cb(cb):
    def _handler(icon, item):
        stop_tray()
        if cb:
            cb()
        else:
            os._exit(0)
    return _handler


def _on_settings(icon, item) -> None:
    webbrowser.open("http://127.0.0.1:59137/#settings")
