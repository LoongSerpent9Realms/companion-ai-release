"""Plugin system for Companion AI.

Plugins live in ``plugins/<name>/`` and consist of:

* ``PLUGIN.md``  -- YAML front-matter (name, description, version, buttons)
* ``plugin.py``  -- optional Python module with hooks
* ``data/``      -- plugin-private data directory (auto-created)

plugin.py hooks
~~~~~~~~~~~~~~~

::

    name = "My Plugin"
    description = "Short description"
    version = "1.0.0"
    buttons = [{"label": "Do Thing", "command": "/mycommand"}]

    def on_load(api):
        ...

    def on_unload():
        ...

    def on_message(message, api):
        # return {"reply": "..."} to handle, or None to pass through
        if message == "/hello":
            return {"reply": "Hello from plugin!"}
        return None
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import shutil
import subprocess
import sys

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
import tempfile
import time
import traceback
from pathlib import Path
from _paths import module_root, data_dir
from xml.sax.saxutils import escape as xml_escape


PLUGINS_DIR = module_root(__file__) / "plugins"

DANGEROUS_IMPORTS = {
    "ctypes",
    "importlib",
    "subprocess",
    "sys",
}
DANGEROUS_CALLS = {"__import__", "compile", "eval", "exec", "globals", "locals"}


# ── Plugin API exposed to plugin.py ─────────────────────────────────


class PluginAPI:
    """Safe API object passed to plugin hooks."""

    def __init__(self, plugin_dir: Path, plugin_name: str) -> None:
        self._dir = plugin_dir
        self._name = plugin_name
        self._data_dir = plugin_dir / "data"
        self._data_dir.mkdir(exist_ok=True)

    # -- data helpers --

    def data_dir(self) -> Path:
        return self._data_dir

    def read_data(self, key: str, default=None):
        p = self._data_dir / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return default

    def write_data(self, key: str, value) -> None:
        p = self._data_dir / f"{key}.json"
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- shared data access --

    def read_shared(self, key: str, default=None):
        """Read from the main data/ directory (memory, training, etc.)."""
        shared = data_dir(module_root(__file__)) / f"{key}.json"
        if shared.exists():
            return json.loads(shared.read_text(encoding="utf-8"))
        return default

    def log(self, msg: str) -> None:
        print(f"[plugin:{self._name}] {msg}")


# ── Single plugin ────────────────────────────────────────────────────


class Plugin:
    """Represents one installed plugin."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.name = directory.name
        self.description = ""
        self.version = "0.0.0"
        self.buttons: list[dict] = []
        self.loaded = False
        self.disabled = False
        self.error = ""
        self._module = None
        self._api: PluginAPI | None = None
        self._parse_meta()

    def _parse_meta(self) -> None:
        md = self.directory / "PLUGIN.md"
        if not md.exists():
            return
        text = md.read_text(encoding="utf-8")
        # minimal YAML front-matter parser
        if not text.startswith("---"):
            return
        end = text.find("---", 3)
        if end == -1:
            return
        fm = text[3:end].strip()
        cfg = _simple_yaml(fm)
        self.name = cfg.get("name", self.name)
        self.description = cfg.get("description", "")
        self.version = cfg.get("version", "0.0.0")
        btns = cfg.get("buttons", [])
        if isinstance(btns, list):
            self.buttons = [b for b in btns if isinstance(b, dict)]

    # -- lifecycle --

    def load(self) -> None:
        if self.loaded or self.disabled:
            return
        py = self.directory / "plugin.py"
        if not py.exists():
            self.loaded = True  # metadata-only plugin
            return
        self._api = PluginAPI(self.directory, self.name)
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins_{self.name}", str(py)
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            self._module = mod
            self.name = getattr(mod, "name", self.name)
            self.description = getattr(mod, "description", self.description)
            self.version = getattr(mod, "version", self.version)
            self.buttons = getattr(mod, "buttons", self.buttons)
            if hasattr(mod, "on_load"):
                mod.on_load(self._api)
            self.loaded = True
        except Exception:
            self.error = traceback.format_exc()
            self._api.log(f"load failed:\n{self.error}")

    def unload(self) -> None:
        if not self.loaded:
            return
        try:
            if self._module and hasattr(self._module, "on_unload"):
                self._module.on_unload()
        except Exception:
            pass
        spec_name = f"plugins_{self.directory.name}"
        sys.modules.pop(spec_name, None)
        self._module = None
        self.loaded = False

    def handle_message(self, message: str) -> dict | None:
        if not self.loaded or not self._module:
            return None
        if not hasattr(self._module, "on_message"):
            return None
        try:
            return self._module.on_message(message, self._api)
        except Exception as exc:
            self._api.log(f"on_message error: {exc}")
            return None

    def info(self) -> dict:
        return {
            "dir": self.directory.name,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "loaded": self.loaded,
            "disabled": self.disabled,
            "error": self.error,
            "buttons": self.buttons,
            "has_code": (self.directory / "plugin.py").exists(),
        }


# ── Manager ──────────────────────────────────────────────────────────


class PluginManager:
    """Discovers, loads, and manages all plugins."""

    def __init__(self) -> None:
        self.plugins: dict[str, Plugin] = {}
        PLUGINS_DIR.mkdir(exist_ok=True)

    def discover(self) -> None:
        for entry in sorted(PLUGINS_DIR.iterdir()):
            if entry.is_dir() and (entry / "PLUGIN.md").exists():
                if entry.name not in self.plugins:
                    self.plugins[entry.name] = Plugin(entry)

    def load_all(self) -> None:
        self.discover()
        for plugin in self.plugins.values():
            if not plugin.disabled:
                plugin.load()

    def reload_all(self) -> None:
        for p in self.plugins.values():
            p.unload()
        self.plugins.clear()
        self.load_all()

    def handle_message(self, message: str) -> dict | None:
        for p in self.plugins.values():
            if p.loaded and not p.disabled:
                result = p.handle_message(message)
                if result is not None:
                    return result
        return None

    def get_buttons(self) -> list[dict]:
        buttons: list[dict] = []
        for p in self.plugins.values():
            if p.loaded and not p.disabled:
                for btn in p.buttons:
                    buttons.append({**btn, "_plugin": p.name})
        return buttons

    def list_plugins(self) -> list[dict]:
        return [p.info() for p in self.plugins.values()]

    def get_plugin(self, name: str) -> Plugin | None:
        return self.plugins.get(name)

    # -- install / remove --

    def install_from_template(self, name: str, meta: dict) -> Plugin:
        if meta.get("ai_generated") or meta.get("sandbox_validate"):
            validation = validate_plugin_package(meta)
            if not validation["ok"]:
                raise ValueError("plugin sandbox validation failed: " + validation.get("error", "unknown error"))
        d = PLUGINS_DIR / name
        with tempfile.TemporaryDirectory(prefix="companion_plugin_install_") as tmp:
            staged = Path(tmp) / name
            _write_plugin_package(staged, meta)
            scan_result = scan_path_for_virus(staged)
            if not scan_result["ok"]:
                raise ValueError("plugin virus scan failed: " + scan_result.get("error", "unknown error"))
            old_plugin = self.plugins.pop(name, None)
            if old_plugin is not None:
                old_plugin.unload()
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(staged, d)
        plugin = Plugin(d)
        plugin.load()
        self.plugins[name] = plugin
        return plugin

    def remove_plugin(self, name: str) -> bool:
        p = self.plugins.pop(name, None)
        if p is None:
            return False
        p.unload()
        shutil.rmtree(p.directory, ignore_errors=True)
        return True

    def toggle_plugin(self, name: str) -> bool | None:
        p = self.plugins.get(name)
        if p is None:
            return None
        if p.disabled:
            p.disabled = False
            p.load()
        else:
            p.unload()
            p.disabled = True
        return p.disabled


# ── Helpers ──────────────────────────────────────────────────────────


def _write_plugin_package(directory: Path, meta: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "data").mkdir(exist_ok=True)
    (directory / "PLUGIN.md").write_text(_build_plugin_md(meta), encoding="utf-8")
    if meta.get("code"):
        (directory / "plugin.py").write_text(str(meta["code"]), encoding="utf-8")


def scan_path_for_virus(path: Path, timeout: int = 120) -> dict:
    scanner = _find_windows_defender_scanner()
    if scanner is None:
        return {"ok": False, "error": "未找到 Windows Defender 扫描器，无法确认插件无病毒。"}

    proc = subprocess.run(
        [str(scanner), "-Scan", "-ScanType", "3", "-File", str(path)],
        text=True,
        capture_output=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        return {"ok": True, "scanner": str(scanner), "detail": output[-1200:]}
    return {
        "ok": False,
        "scanner": str(scanner),
        "error": output[-1200:] or f"Windows Defender 返回代码 {proc.returncode}",
    }


def _find_windows_defender_scanner() -> Path | None:
    platform_dir = Path("C:/ProgramData/Microsoft/Windows Defender/Platform")
    candidates: list[Path] = []
    if platform_dir.exists():
        candidates.extend(sorted(platform_dir.glob("*/MpCmdRun.exe"), reverse=True))
    candidates.append(Path("C:/Program Files/Windows Defender/MpCmdRun.exe"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def validate_plugin_package(meta: dict, timeout: int = 300) -> dict:
    """Validate AI-generated plugin code before it is installed.

    The package is written to a temporary quarantine directory, scanned by
    Windows Defender, executed in Docker or Windows Sandbox when available,
    and scanned again before it can be copied into the real plugins directory.
    """
    code = str(meta.get("code", ""))
    if not code.strip():
        return {"ok": False, "error": "插件代码为空。"}

    static_result = _static_validate_plugin_code(code)
    if not static_result["ok"]:
        return static_result

    buttons = meta.get("buttons", [])
    if not isinstance(buttons, list):
        buttons = []

    with tempfile.TemporaryDirectory(prefix="companion_plugin_sandbox_") as tmp:
        tmp_path = Path(tmp)
        package_dir = tmp_path / "plugin_under_test"
        _write_plugin_package(package_dir, meta)

        pre_scan = scan_path_for_virus(package_dir)
        if not pre_scan["ok"]:
            return pre_scan

        runner_file = tmp_path / "sandbox_runner.py"
        runner_file.write_text(_sandbox_runner_code(buttons), encoding="utf-8")

        isolation = _choose_isolation_backend(str(meta.get("isolation_backend", "auto")))
        if isolation == "process" and not meta.get("allow_process_isolation"):
            return {
                "ok": False,
                "error": "AI 插件必须使用 Docker 或 Windows Sandbox 级隔离；当前没有可用的容器/Windows Sandbox 自动验证后端。",
                "backend": "process",
            }
        if isolation == "docker":
            run_result = _run_in_docker_sandbox(tmp_path, package_dir, runner_file, timeout)
        elif isolation == "windows_sandbox":
            run_result = _run_in_windows_sandbox(tmp_path, package_dir, runner_file, timeout)
        elif isolation == "process":
            run_result = _run_in_process_sandbox(package_dir, runner_file, timeout)
        else:
            return {"ok": False, "error": f"未知隔离后端：{isolation}"}
        if not run_result["ok"]:
            return run_result

        post_scan = scan_path_for_virus(package_dir)
        if not post_scan["ok"]:
            return post_scan

    try:
        payload = json.loads(str(run_result.get("stdout", "")).strip() or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "沙箱验证没有返回有效 JSON。"}
    if not payload.get("ok"):
        return {"ok": False, "error": str(payload.get("error", "沙箱验证失败"))}
    checks = payload.get("checks", [])
    checks.extend(["virus_scan:before", "virus_scan:after"])
    checks.append("isolation:" + run_result.get("backend", isolation))
    return {"ok": True, "checks": checks, "scanner": pre_scan.get("scanner"), "isolation": run_result.get("backend", isolation)}


def _choose_isolation_backend(requested: str) -> str:
    requested = (requested or "auto").strip().lower()
    if requested in {"docker", "windows_sandbox", "process"}:
        return requested
    if shutil.which("docker"):
        return "docker"
    if _find_windows_sandbox() is not None and _python_sandbox_prefix() is not None:
        return "windows_sandbox"
    return "process"


def _run_in_process_sandbox(package_dir: Path, runner_file: Path, timeout: int) -> dict:
    proc = subprocess.run(
        [sys.executable, "-I", str(runner_file)],
        cwd=str(package_dir),
        text=True,
        capture_output=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "未知错误").strip()
        return {"ok": False, "error": detail[:1200], "backend": "process"}
    return {"ok": True, "stdout": proc.stdout, "backend": "process"}


def _run_in_docker_sandbox(tmp_path: Path, package_dir: Path, runner_file: Path, timeout: int) -> dict:
    if shutil.which("docker") is None:
        return {"ok": False, "error": "未找到 Docker，无法使用容器级隔离。", "backend": "docker"}
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "bridge",
            "-v",
            f"{tmp_path.as_posix()}:/work",
            "-w",
            "/work/plugin_under_test",
            "python:3.12-slim",
            "python",
            "-I",
            "/work/sandbox_runner.py",
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "未知错误").strip()
        return {"ok": False, "error": detail[:1200], "backend": "docker"}
    return {"ok": True, "stdout": proc.stdout, "backend": "docker"}


def _find_windows_sandbox() -> Path | None:
    candidate = shutil.which("WindowsSandbox.exe")
    if candidate:
        return Path(candidate)
    fallback = Path("C:/Windows/System32/WindowsSandbox.exe")
    return fallback if fallback.exists() else None


def _python_sandbox_prefix() -> Path | None:
    prefix = Path(getattr(sys, "base_prefix", "") or sys.prefix)
    if (prefix / "python.exe").exists():
        return prefix
    executable_parent = Path(sys.executable).resolve().parent
    if (executable_parent / "python.exe").exists():
        return executable_parent
    return None


def _run_in_windows_sandbox(tmp_path: Path, package_dir: Path, runner_file: Path, timeout: int) -> dict:
    sandbox_exe = _find_windows_sandbox()
    python_prefix = _python_sandbox_prefix()
    if sandbox_exe is None:
        return {"ok": False, "error": "未找到 Windows Sandbox。", "backend": "windows_sandbox"}
    if python_prefix is None:
        return {"ok": False, "error": "未找到可映射到 Windows Sandbox 的 Python 目录。", "backend": "windows_sandbox"}

    result_file = tmp_path / "windows_sandbox_result.json"
    stdout_file = tmp_path / "windows_sandbox_stdout.txt"
    stderr_file = tmp_path / "windows_sandbox_stderr.txt"
    script_file = tmp_path / "run_windows_sandbox.ps1"
    wsb_file = tmp_path / "plugin_sandbox.wsb"

    mapped_root_name = tmp_path.name
    python_root_name = python_prefix.name
    sandbox_desktop_root = f"C:\\Users\\WDAGUtilityAccount\\Desktop\\{mapped_root_name}"
    sandbox_python_root = f"C:\\Users\\WDAGUtilityAccount\\Desktop\\{python_root_name}"
    script_file.write_text(f"""
$ErrorActionPreference = "Continue"
$root = "{sandbox_desktop_root}"
$python = "{sandbox_python_root}\\python.exe"
$stdout = Join-Path $root "windows_sandbox_stdout.txt"
$stderr = Join-Path $root "windows_sandbox_stderr.txt"
$result = Join-Path $root "windows_sandbox_result.json"
Set-Location (Join-Path $root "plugin_under_test")
& $python -I (Join-Path $root "sandbox_runner.py") 1> $stdout 2> $stderr
$exitCode = $LASTEXITCODE
$payload = [ordered]@{{
  ok = ($exitCode -eq 0)
  exit_code = $exitCode
  stdout = if (Test-Path $stdout) {{ Get-Content $stdout -Raw }} else {{ "" }}
  stderr = if (Test-Path $stderr) {{ Get-Content $stderr -Raw }} else {{ "" }}
}}
$payload | ConvertTo-Json -Depth 5 | Set-Content -Path $result -Encoding UTF8
Start-Sleep -Seconds 2
Stop-Computer -Force
""".strip(), encoding="utf-8")

    wsb_file.write_text(f"""<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Enable</Networking>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{xml_escape(str(tmp_path))}</HostFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{xml_escape(str(python_prefix))}</HostFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -ExecutionPolicy Bypass -File "C:\\Users\\WDAGUtilityAccount\\Desktop\\{xml_escape(mapped_root_name)}\\run_windows_sandbox.ps1"</Command>
  </LogonCommand>
</Configuration>
""", encoding="utf-8")

    subprocess.Popen([str(sandbox_exe), str(wsb_file)], creationflags=CREATE_NO_WINDOW)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result_file.exists():
            break
        time.sleep(1)
    if not result_file.exists():
        return {"ok": False, "error": "Windows Sandbox 验证超时，未收到结果文件。", "backend": "windows_sandbox"}

    try:
        result = json.loads(result_file.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Windows Sandbox 结果 JSON 解析失败：{exc}", "backend": "windows_sandbox"}
    if not result.get("ok"):
        detail = (result.get("stderr") or result.get("stdout") or "Windows Sandbox 验证失败").strip()
        return {"ok": False, "error": detail[:1200], "backend": "windows_sandbox"}
    return {"ok": True, "stdout": result.get("stdout", ""), "backend": "windows_sandbox"}


def _static_validate_plugin_code(code: str) -> dict:
    try:
        tree = ast.parse(code, filename="plugin.py")
    except SyntaxError as exc:
        return {"ok": False, "error": f"语法错误：{exc}"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in DANGEROUS_IMPORTS:
                    return {"ok": False, "error": f"禁止导入模块：{root}"}
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in DANGEROUS_IMPORTS:
                return {"ok": False, "error": f"禁止导入模块：{root}"}
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in DANGEROUS_CALLS:
                return {"ok": False, "error": f"禁止调用：{name}"}
    return {"ok": True}


def _sandbox_runner_code(buttons: list) -> str:
    return f'''
import importlib.util
import json
import traceback
from pathlib import Path


class SandboxAPI:
    def __init__(self):
        self._data = {{}}
        self._data_dir = Path("data")
        self._data_dir.mkdir(exist_ok=True)

    def data_dir(self):
        return self._data_dir

    def read_data(self, key, default=None):
        return self._data.get(key, default)

    def write_data(self, key, value):
        json.dumps(value, ensure_ascii=False)
        self._data[key] = value

    def read_shared(self, key, default=None):
        return default

    def log(self, msg):
        pass


def main():
    checks = []
    try:
        spec = importlib.util.spec_from_file_location("sandbox_plugin", "plugin.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        checks.append("import")

        for attr in ("name", "description", "version"):
            value = getattr(mod, attr, "")
            if not isinstance(value, str):
                raise TypeError(attr + " 必须是字符串")

        buttons = getattr(mod, "buttons", [])
        if buttons is not None and not isinstance(buttons, list):
            raise TypeError("buttons 必须是列表")

        api = SandboxAPI()
        if hasattr(mod, "on_load"):
            mod.on_load(api)
            checks.append("on_load")

        commands = [btn.get("command", "") for btn in {json.dumps(buttons, ensure_ascii=False)} if isinstance(btn, dict)]
        for command in commands:
            if not command or not hasattr(mod, "on_message"):
                continue
            result = mod.on_message(command, api)
            if result is not None:
                json.dumps(result, ensure_ascii=False)
                if not isinstance(result, dict):
                    raise TypeError("on_message 返回值必须是 dict 或 None")
            checks.append("on_message:" + command)

        if hasattr(mod, "on_unload"):
            mod.on_unload()
            checks.append("on_unload")

        print(json.dumps({{"ok": True, "checks": checks}}, ensure_ascii=False))
    except Exception:
        print(json.dumps({{"ok": False, "error": traceback.format_exc()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


def _simple_yaml(text: str) -> dict:
    """Minimal YAML-subset parser for PLUGIN.md front-matter.

    Supports: scalar values, - item lists, {key: value} inline dicts.
    """
    result: dict = {}
    current_key = ""
    current_list: list | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        # list item
        if stripped.startswith("- "):
            if current_list is not None:
                item_text = stripped[2:].strip()
                if item_text.startswith("{") and item_text.endswith("}"):
                    current_list.append(_inline_dict(item_text))
                else:
                    current_list.append(item_text)
            continue

        # key: value
        if ":" in stripped and indent == 0:
            # save previous list
            if current_key and current_list is not None:
                result[current_key] = current_list

            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            current_key = key
            current_list = None

            if not val:
                # start of a list or nested block
                current_list = []
            elif val.startswith("[") and val.endswith("]"):
                # inline list of inline dicts
                items = _split_inline_list(val)
                parsed = []
                for item in items:
                    if item.startswith("{") and item.endswith("}"):
                        parsed.append(_inline_dict(item))
                    else:
                        parsed.append(item.strip().strip('"').strip("'"))
                result[key] = parsed
            else:
                result[key] = val.strip('"').strip("'")

    # save last list
    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


def _inline_dict(s: str) -> dict:
    """Parse ``{key: "val", key2: "val2"}``."""
    s = s.strip("{}")
    d: dict = {}
    for part in s.split(","):
        if ":" in part:
            k, _, v = part.partition(":")
            v = v.strip().strip('"').strip("'")
            d[k.strip()] = v
    return d


def _split_inline_list(s: str) -> list[str]:
    """Split ``[{...}, {...}]`` respecting braces."""
    s = s.strip("[]")
    items: list[str] = []
    depth = 0
    current = ""
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        items.append(current.strip())
    return items


def auto_create_plugin(prompt: str, config: dict | None = None) -> dict:
    """AI autonomously creates and installs a plugin.

    Complete flow: generate code → sandbox validation → auto-install → return result.
    No user confirmation needed - sandbox validation is the gatekeeper.
    """
    result = generate_plugin_code(prompt, config)
    if not result.get("ok"):
        return result

    meta = {
        "name": result["name"],
        "description": result["description"],
        "version": "1.0.0",
        "buttons": result["buttons"],
        "code": result["code"],
        "ai_generated": True,
        "sandbox_validate": True,
        "isolation_backend": "process",
    }

    validation = validate_plugin_package(meta)
    if not validation.get("ok"):
        return {"ok": False, "error": f"沙盒验证失败：{validation.get('error', '未知错误')}"}

    import re
    slug = re.sub(r'[^a-z0-9_-]', '_', result["name"].lower())[:48]
    
    try:
        plugin = plugin_mgr.install_from_template(slug, meta)
        return {
            "ok": True,
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.description,
            "buttons": plugin.buttons,
            "checks": validation.get("checks", []),
            "isolation": validation.get("isolation"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"安装失败：{exc}"}


def generate_plugin_code(prompt: str, config: dict | None = None) -> dict:
    """Generate plugin code using AI.

    Args:
        prompt: User's description of what the plugin should do
        config: Remote LLM config (optional)

    Returns:
        Dict with "code", "name", "description", "buttons", "error"
    """
    try:
        from remote_llm import call_remote_llm, load_remote_llm_config, is_remote_llm_ready
    except ImportError:
        return {"ok": False, "error": "remote_llm 模块未找到"}

    llm_config = config or load_remote_llm_config()
    if not is_remote_llm_ready(llm_config):
        return {"ok": False, "error": "大模型接口未启用或未配置"}

    system_prompt = """你是一个专业的 Python 插件开发者，负责为 Companion AI 编写插件代码。

插件规范：
- 必须定义 name、description、version 三个字符串变量
- 必须定义 buttons 列表，每个按钮包含 label 和 command
- 可选定义 on_load(api)、on_unload()、on_message(message, api) 函数
- on_message 返回 {"reply": "..."} 或 None
- 使用 api.read_data(key) 和 api.write_data(key, value) 存储数据
- 使用 api.log(msg) 记录日志

安全限制（禁止使用）：
- 禁止导入 ctypes、importlib、subprocess、sys
- 禁止使用 __import__、compile、eval、exec、globals、locals

请直接返回完整的 plugin.py 代码，不要包含任何解释性文字。
代码格式要求：
1. 开头必须是 plugin.py 的完整代码
2. 代码必须可直接运行
3. 必须包含所有必需的变量和函数

示例：
```python
name = "每日提醒"
description = "每天提醒用户完成任务"
version = "1.0.0"
buttons = [{"label": "设置提醒", "command": "/set_reminder"}]

def on_load(api):
    api.log("loaded")

def on_unload():
    pass

def on_message(message, api):
    if message == "/set_reminder":
        return {"reply": "请告诉我要提醒什么"}
    return None
```"""

    user_prompt = f"""请为我创建一个插件，功能描述：{prompt}

请严格按照规范返回代码，只返回 plugin.py 的内容。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    import json
    payload = json.dumps({
        "model": llm_config["model"],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
    }).encode("utf-8")

    import urllib.request
    import urllib.error

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_config['api_key']}",
    }
    req = urllib.request.Request(
        f"{llm_config['api_base']}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=llm_config["timeout"] * 2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        return {"ok": False, "error": f"大模型请求失败: HTTP {exc.code} {detail}"}
    except Exception as exc:
        return {"ok": False, "error": f"大模型请求失败: {exc}"}

    choices = body.get("choices") or []
    if not choices:
        return {"ok": False, "error": "大模型没有返回结果"}

    raw_code = choices[0].get("message", {}).get("content", "").strip()

    if raw_code.startswith("```python"):
        raw_code = raw_code[9:]
    if raw_code.endswith("```"):
        raw_code = raw_code[:-3]
    raw_code = raw_code.strip()

    try:
        import ast
        ast.parse(raw_code, filename="plugin.py")
    except SyntaxError as exc:
        return {"ok": False, "error": f"生成的代码有语法错误: {exc}"}

    import re
    name_match = re.search(r'name\s*=\s*["\'](.+?)["\']', raw_code)
    desc_match = re.search(r'description\s*=\s*["\'](.+?)["\']', raw_code)

    buttons = []
    buttons_match = re.search(r'buttons\s*=\s*\[(.+?)\]', raw_code, re.DOTALL)
    if buttons_match:
        try:
            buttons_str = "[" + buttons_match.group(1) + "]"
            buttons = ast.literal_eval(buttons_str)
        except Exception:
            pass

    return {
        "ok": True,
        "code": raw_code,
        "name": name_match.group(1) if name_match else "AI Generated Plugin",
        "description": desc_match.group(1) if desc_match else "AI generated plugin",
        "buttons": buttons if isinstance(buttons, list) else [],
    }


def _build_plugin_md(meta: dict) -> str:
    """Build PLUGIN.md content from a metadata dict."""
    lines = ["---"]
    lines.append(f'name: {meta.get("name", "New Plugin")}')
    lines.append(f'description: {meta.get("description", "")}')
    lines.append(f'version: {meta.get("version", "1.0.0")}')
    buttons = meta.get("buttons", [])
    if buttons:
        lines.append("buttons:")
        for btn in buttons:
            label = btn.get("label", "")
            cmd = btn.get("command", "")
            lines.append(f'  - {{label: "{label}", command: "{cmd}"}}')
    lines.append("---")
    lines.append("")
    lines.append(meta.get("readme", f"# {meta.get('name', 'New Plugin')}"))
    lines.append("")
    return "\n".join(lines)
