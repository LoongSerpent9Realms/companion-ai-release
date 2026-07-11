from __future__ import annotations

import json
import locale
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "build_release.ps1"
CONFIG_FILE = ROOT / "release_builder_config.json"


class ReleaseBuilderGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Companion AI 发布打包")
        self.root.geometry("900x680")
        self.root.minsize(780, 580)

        self.skip_signing = BooleanVar(value=False)
        self.timestamp_url = StringVar(value="http://timestamp.digicert.com")
        self.cert_mode = StringVar(value="auto")
        self.cert_subject = StringVar()
        self.cert_thumbprint = StringVar()
        self.pfx_path = StringVar()
        self.pfx_password = StringVar()
        self.signtool_path = StringVar()
        self.makensis_path = StringVar()

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._load_config()
        self._update_cert_fields()
        self._auto_search_tools(silent=True)
        self._poll_output()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        main = ttk.Frame(self.root, padding=16)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="签名设置", font=("", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Checkbutton(
            main,
            text="跳过签名（只打包测试版）",
            variable=self.skip_signing,
            command=self._update_cert_fields,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 6))

        ttk.Label(main, text="时间戳 URL").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(main, textvariable=self.timestamp_url).grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)

        mode_frame = ttk.LabelFrame(main, text="证书来源", padding=10)
        mode_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        for col in range(4):
            mode_frame.columnconfigure(col, weight=1)
        for col, (value, label) in enumerate((
            ("auto", "自动选择"),
            ("subject", "发布者名称"),
            ("thumbprint", "证书指纹"),
            ("pfx", "PFX 文件"),
        )):
            ttk.Radiobutton(
                mode_frame,
                text=label,
                value=value,
                variable=self.cert_mode,
                command=self._update_cert_fields,
            ).grid(row=0, column=col, sticky="w", padx=(0, 12))

        self.subject_label = ttk.Label(main, text="发布者名称")
        self.subject_entry = ttk.Entry(main, textvariable=self.cert_subject)
        self.subject_label.grid(row=4, column=0, sticky="w", pady=5)
        self.subject_entry.grid(row=4, column=1, columnspan=2, sticky="ew", pady=5)

        self.thumbprint_label = ttk.Label(main, text="证书指纹")
        self.thumbprint_entry = ttk.Entry(main, textvariable=self.cert_thumbprint)
        self.thumbprint_label.grid(row=5, column=0, sticky="w", pady=5)
        self.thumbprint_entry.grid(row=5, column=1, columnspan=2, sticky="ew", pady=5)

        self.pfx_label = ttk.Label(main, text="PFX 文件")
        self.pfx_entry = ttk.Entry(main, textvariable=self.pfx_path)
        self.pfx_button = ttk.Button(main, text="浏览", command=self._browse_pfx)
        self.pfx_label.grid(row=6, column=0, sticky="w", pady=5)
        self.pfx_entry.grid(row=6, column=1, sticky="ew", pady=5)
        self.pfx_button.grid(row=6, column=2, sticky="ew", padx=(8, 0), pady=5)

        self.password_label = ttk.Label(main, text="PFX 密码")
        self.password_entry = ttk.Entry(main, textvariable=self.pfx_password, show="*")
        self.password_label.grid(row=7, column=0, sticky="w", pady=5)
        self.password_entry.grid(row=7, column=1, columnspan=2, sticky="ew", pady=5)

        ttk.Label(main, text="工具路径", font=("", 13, "bold")).grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(18, 6)
        )

        ttk.Label(main, text="signtool.exe").grid(row=9, column=0, sticky="w", pady=5)
        ttk.Entry(main, textvariable=self.signtool_path).grid(row=9, column=1, sticky="ew", pady=5)
        ttk.Button(main, text="浏览", command=self._browse_signtool).grid(row=9, column=2, sticky="ew", padx=(8, 0), pady=5)

        ttk.Label(main, text="makensis.exe").grid(row=10, column=0, sticky="w", pady=5)
        ttk.Entry(main, textvariable=self.makensis_path).grid(row=10, column=1, sticky="ew", pady=5)
        ttk.Button(main, text="浏览", command=self._browse_makensis).grid(row=10, column=2, sticky="ew", padx=(8, 0), pady=5)

        actions = ttk.Frame(main)
        actions.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        actions.columnconfigure(0, weight=1)
        self.search_button = ttk.Button(actions, text="自动搜索工具", command=self._auto_search_tools)
        self.search_button.grid(row=0, column=0, sticky="e")
        self.build_button = ttk.Button(actions, text="开始打包", command=self._start_build)
        self.build_button.grid(row=0, column=1, padx=(8, 0))
        self.open_output_button = ttk.Button(actions, text="打开输出目录", command=self._open_output_dir)
        self.open_output_button.grid(row=0, column=2, padx=(8, 0))

        output_frame = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        output_frame.grid(row=1, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(1, weight=1)
        ttk.Label(output_frame, text="构建日志", font=("", 13, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.output = ScrolledText(output_frame, wrap="word", height=18)
        self.output.grid(row=1, column=0, sticky="nsew")

    def _set_row_enabled(self, widgets: list[ttk.Widget], enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in widgets:
            widget.configure(state=state)

    def _update_cert_fields(self) -> None:
        signing_enabled = not self.skip_signing.get()
        mode = self.cert_mode.get()
        self._set_row_enabled([self.subject_label, self.subject_entry], signing_enabled and mode == "subject")
        self._set_row_enabled([self.thumbprint_label, self.thumbprint_entry], signing_enabled and mode == "thumbprint")
        self._set_row_enabled([self.pfx_label, self.pfx_entry, self.pfx_button], signing_enabled and mode == "pfx")
        self._set_row_enabled([self.password_label, self.password_entry], signing_enabled and mode == "pfx")

    def _browse_pfx(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PFX certificates", "*.pfx;*.p12"), ("All files", "*.*")])
        if path:
            self.pfx_path.set(path)

    def _browse_signtool(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("signtool.exe", "signtool.exe"), ("Executable", "*.exe"), ("All files", "*.*")])
        if path:
            self.signtool_path.set(path)

    def _browse_makensis(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("makensis.exe", "makensis.exe"), ("Executable", "*.exe"), ("All files", "*.*")])
        if path:
            self.makensis_path.set(path)

    def _candidate_roots(self, *parts: str) -> list[Path]:
        roots: list[Path] = []
        for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
            root = os.environ.get(env_name)
            if root:
                roots.append(Path(root, *parts))
        return roots

    def _find_signtool(self) -> str:
        path = shutil.which("signtool.exe") or shutil.which("signtool")
        if path:
            return path

        candidates: list[Path] = []
        for kit_root in self._candidate_roots("Windows Kits", "10", "bin"):
            if not kit_root.exists():
                continue
            candidates.extend(sorted(kit_root.glob("*/x64/signtool.exe"), reverse=True))
            candidates.extend(sorted(kit_root.glob("*/x86/signtool.exe"), reverse=True))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return ""

    def _find_makensis(self) -> str:
        path = shutil.which("makensis.exe") or shutil.which("makensis")
        if path:
            return path

        for candidate in self._candidate_roots("NSIS", "makensis.exe"):
            if candidate.is_file():
                return str(candidate)
        return ""

    def _auto_search_tools(self, silent: bool = False) -> None:
        def worker() -> None:
            if not silent:
                self.output_queue.put("[gui] 正在自动搜索 signtool.exe 和 makensis.exe...\n")
            signtool = self._find_signtool()
            makensis = self._find_makensis()
            self.output_queue.put(("__SET_TOOL_PATHS__", signtool, makensis, silent))

        threading.Thread(target=worker, daemon=True).start()

    def _append_output(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _validate(self) -> bool:
        if not SCRIPT.exists():
            messagebox.showerror("缺少脚本", f"找不到 {SCRIPT}")
            return False
        if self.skip_signing.get():
            return True
        if self.cert_mode.get() == "subject" and not self.cert_subject.get().strip():
            messagebox.showwarning("缺少发布者名称", "请填写证书发布者名称。")
            return False
        if self.cert_mode.get() == "thumbprint" and not self.cert_thumbprint.get().strip():
            messagebox.showwarning("缺少证书指纹", "请填写证书 SHA1 指纹。")
            return False
        if self.cert_mode.get() == "pfx" and not self.pfx_path.get().strip():
            messagebox.showwarning("缺少 PFX", "请选择 PFX 证书文件。")
            return False
        return True

    def _build_command(self) -> list[str]:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-TimestampUrl",
            self.timestamp_url.get().strip() or "http://timestamp.digicert.com",
        ]
        if self.skip_signing.get():
            cmd.append("-SkipSigning")
            return cmd

        mode = self.cert_mode.get()
        if mode == "subject":
            cmd.extend(["-CertificateSubject", self.cert_subject.get().strip()])
        elif mode == "thumbprint":
            cmd.extend(["-CertificateThumbprint", self.cert_thumbprint.get().strip().replace(" ", "")])
        elif mode == "pfx":
            cmd.extend(["-PfxPath", self.pfx_path.get().strip()])
            if self.pfx_password.get():
                cmd.extend(["-PfxPassword", self.pfx_password.get()])

        if self.signtool_path.get().strip():
            cmd.extend(["-SignToolPath", self.signtool_path.get().strip()])
        if self.makensis_path.get().strip():
            cmd.extend(["-MakeNsisPath", self.makensis_path.get().strip()])
        return cmd

    def _start_build(self) -> None:
        if self.process is not None:
            messagebox.showinfo("正在构建", "当前构建还在运行。")
            return
        if not self._validate():
            return

        self._save_config()
        self.output.delete("1.0", "end")
        self._append_output("[gui] 开始发布构建...\n")
        self.build_button.configure(state="disabled")

        threading.Thread(target=self._run_build, args=(self._build_command(),), daemon=True).start()

    def _run_build(self, cmd: list[str]) -> None:
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=locale.getpreferredencoding(False),
                errors="replace",
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.output_queue.put(line)
            return_code = self.process.wait()
            if return_code == 0:
                self.output_queue.put("\n[gui] 构建完成。\n")
            else:
                self.output_queue.put(f"\n[gui] 构建失败，退出码: {return_code}\n")
        except Exception as exc:
            self.output_queue.put(f"\n[gui] 构建启动失败: {exc}\n")
        finally:
            self.process = None
            self.output_queue.put("__BUILD_DONE__")

    def _poll_output(self) -> None:
        while True:
            try:
                item = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__BUILD_DONE__":
                self.build_button.configure(state="normal")
            elif isinstance(item, tuple) and item[0] == "__SET_TOOL_PATHS__":
                _, signtool, makensis, silent = item
                if signtool and not self.signtool_path.get().strip():
                    self.signtool_path.set(signtool)
                if makensis and not self.makensis_path.get().strip():
                    self.makensis_path.set(makensis)
                if not silent:
                    self._append_output(f"[gui] signtool.exe: {signtool or '未找到'}\n")
                    self._append_output(f"[gui] makensis.exe: {makensis or '未找到'}\n")
            else:
                self._append_output(item)
        self.root.after(100, self._poll_output)

    def _open_output_dir(self) -> None:
        output_dir = ROOT / "installer_output"
        output_dir.mkdir(exist_ok=True)
        subprocess.Popen(["explorer", str(output_dir)])

    def _load_config(self) -> None:
        if not CONFIG_FILE.exists():
            return
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.skip_signing.set(bool(config.get("skip_signing", False)))
        self.timestamp_url.set(config.get("timestamp_url", self.timestamp_url.get()))
        self.cert_mode.set(config.get("cert_mode", "auto"))
        self.cert_subject.set(config.get("cert_subject", ""))
        self.cert_thumbprint.set(config.get("cert_thumbprint", ""))
        self.pfx_path.set(config.get("pfx_path", ""))
        self.signtool_path.set(config.get("signtool_path", ""))
        self.makensis_path.set(config.get("makensis_path", ""))

    def _save_config(self) -> None:
        config = {
            "skip_signing": self.skip_signing.get(),
            "timestamp_url": self.timestamp_url.get().strip(),
            "cert_mode": self.cert_mode.get(),
            "cert_subject": self.cert_subject.get().strip(),
            "cert_thumbprint": self.cert_thumbprint.get().strip(),
            "pfx_path": self.pfx_path.get().strip(),
            "signtool_path": self.signtool_path.get().strip(),
            "makensis_path": self.makensis_path.get().strip(),
        }
        CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    root = Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    ReleaseBuilderGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
