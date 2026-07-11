"""Quick test: does WinForms TransparencyKey work with pywebview + WebView2?"""
import threading
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import webview

TRANSPARENT_COLOR = "#ff00ff"

HTML = f"""
<!doctype html>
<html><head><meta charset="utf-8"><title>test</title>
<style>
html, body {{ width: 100%; height: 100%; margin: 0; padding: 0;
  background: {TRANSPARENT_COLOR}; overflow: hidden; }}
.box {{ width: 120px; height: 120px; background: #276ef1;
  border-radius: 50%; position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%); color: white;
  display: flex; align-items: center; justify-content: center;
  font-family: "Microsoft YaHei", sans-serif; font-size: 18px; }}
</style></head>
<body><div class="box">测试</div></body></html>
"""


def _apply_transparency():
    time.sleep(1.0)
    for _ in range(50):
        native = getattr(win, "native", None)
        if native is not None:
            try:
                import clr  # noqa
                from System.Drawing import Color
                native.TransparencyKey = Color.Magenta
                native.BackColor = Color.Magenta
                print("[OK] TransparencyKey = Magenta 已设置")
                return
            except Exception as e:
                print(f"[ERR] 设置失败: {e}")
                return
        time.sleep(0.1)
    print("[WARN] 没找到 window.native")


if __name__ == "__main__":
    win = webview.create_window(
        "Transparency Test",
        html=HTML,
        width=300,
        height=300,
        frameless=True,
        on_top=True,
        background_color=TRANSPARENT_COLOR,
        transparent=True,
        shadow=False,
    )
    threading.Thread(target=_apply_transparency, daemon=True).start()
    webview.start()
