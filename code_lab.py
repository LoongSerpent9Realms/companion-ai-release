from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from _paths import module_root, data_dir, python_exe


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
CODE_LAB_DIR = DATA_DIR / "code_lab"
RUNS_DIR = CODE_LAB_DIR / "runs"
HISTORY_FILE = CODE_LAB_DIR / "history.jsonl"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_CODE_CHARS = 20_000
MAX_OUTPUT_CHARS = 4_000


def _ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _short(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[输出已截断]"


def _strip_fence(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        lines = code.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code.strip()


def _python_runner_command() -> list[str]:
    """Return a command prefix for a real Python interpreter.

    PyInstaller sets ``sys.executable`` to CompanionAI.exe, which can launch
    the application but cannot execute an arbitrary ``.py`` learning sample.
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable]

    try:
        return [python_exe()]
    except RuntimeError:
        pass

    candidate = shutil.which("python")
    if candidate:
        try:
            probe = subprocess.run(
                [candidate, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            if probe.returncode == 0:
                return [candidate]
        except Exception:
            pass

    py_launcher = shutil.which("py")
    if py_launcher:
        try:
            probe = subprocess.run(
                [py_launcher, "-3", "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            if probe.returncode == 0:
                return [py_launcher, "-3"]
        except Exception:
            pass

    raise RuntimeError("未检测到可执行 Python 解释器。请安装 Python 3.10 或更高版本后重试。")


def _compiler_status() -> dict[str, str]:
    try:
        python_runner = " ".join(_python_runner_command())
    except RuntimeError as exc:
        python_runner = f"未检测到（{exc}）"
    return {
        "python": python_runner,
        "gcc": shutil.which("gcc") or "",
        "g++": shutil.which("g++") or "",
        "clang": shutil.which("clang") or "",
        "clang++": shutil.which("clang++") or "",
        "cl": shutil.which("cl") or "",
        "dotnet": shutil.which("dotnet") or "",
        "csc": shutil.which("csc") or "",
    }


def code_lab_status_text() -> str:
    compilers = _compiler_status()
    lines = [
        "代码练习场：",
        f"工作区：{CODE_LAB_DIR}",
        f"Python：{compilers['python']}",
        f"C 编译器：{compilers['gcc'] or compilers['clang'] or compilers['cl'] or '未检测到'}",
        f"C++ 编译器：{compilers['g++'] or compilers['clang++'] or compilers['cl'] or '未检测到'}",
        f"C# 编译器：{compilers['dotnet'] or compilers['csc'] or '未检测到'}",
        "",
        "命令：",
        "  /code_run python => print('hello')",
        "  /code_run c => int main(){return 0;}",
        "  /code_run cpp => #include <iostream> ...",
        "  /code_run csharp => using System; class Program { static void Main(){ Console.WriteLine(\"hello\"); } }",
        "  /code_history - 查看最近验证记录",
    ]
    return "\n".join(lines)


def _append_history(record: dict[str, Any]) -> None:
    _ensure_dirs()
    with open(HISTORY_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def code_history_text(limit: int = 10) -> str:
    if not HISTORY_FILE.exists():
        return "代码练习场还没有验证记录。"
    records: list[dict[str, Any]] = []
    try:
        for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    except Exception:
        return "读取代码练习记录失败。"
    if not records:
        return "代码练习场还没有验证记录。"
    lines = [f"最近代码验证记录（{min(limit, len(records))}/{len(records)}）："]
    for item in records[-limit:]:
        timestamp = time.strftime("%m-%d %H:%M", time.localtime(int(item.get("time", 0))))
        status = "通过" if item.get("ok") else "失败"
        lines.append(f"- {timestamp} [{item.get('language', '?')}] {status}: {item.get('summary', '')}")
    return "\n".join(lines)


def _run_command(cmd: list[str], cwd: Path, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=run_env,
            creationflags=CREATE_NO_WINDOW,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": _short(proc.stdout),
            "stderr": _short(proc.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": _short(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr": f"运行超时（{timeout} 秒）",
        }
    except Exception as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def _run_python(code: str, run_dir: Path) -> dict[str, Any]:
    source = run_dir / "main.py"
    source.write_text(code, encoding="utf-8")
    try:
        command = _python_runner_command()
    except RuntimeError as exc:
        return {
            "compile": {"ok": False, "stdout": "", "stderr": str(exc), "returncode": -1},
            "run": {"ok": False, "stdout": "", "stderr": "未运行：Python 解释器不可用。", "returncode": -1},
            "source": source.name,
        }
    return {
        "compile": {"ok": True, "stdout": "", "stderr": "", "returncode": 0},
        "run": _run_command([*command, str(source)], run_dir, timeout=8),
        "source": source.name,
    }


def _compile_c_like(language: str, code: str, run_dir: Path) -> dict[str, Any]:
    compilers = _compiler_status()
    is_cpp = language == "cpp"
    suffix = ".cpp" if is_cpp else ".c"
    source = run_dir / f"main{suffix}"
    exe = run_dir / "main.exe"
    source.write_text(code, encoding="utf-8")

    if is_cpp:
        compiler = compilers["g++"] or compilers["clang++"] or compilers["cl"]
    else:
        compiler = compilers["gcc"] or compilers["clang"] or compilers["cl"]
    if not compiler:
        label = "C++" if is_cpp else "C"
        return {
            "compile": {
                "ok": False,
                "stdout": "",
                "stderr": f"未检测到 {label} 编译器。请安装 MinGW-w64/LLVM/Visual Studio Build Tools，并把编译器加入 PATH。",
                "returncode": -1,
            },
            "run": {"ok": False, "stdout": "", "stderr": "编译未通过，未运行。", "returncode": -1},
            "source": source.name,
        }

    compiler_name = Path(compiler).name.lower()
    if compiler_name in {"cl", "cl.exe"}:
        cmd = [compiler, "/nologo", "/EHsc", str(source), f"/Fe:{exe}"]
    else:
        standard = "-std=c++17" if is_cpp else "-std=c11"
        cmd = [compiler, standard, "-Wall", "-Wextra", str(source), "-o", str(exe)]

    compile_result = _run_command(cmd, run_dir, timeout=20)
    if not compile_result["ok"]:
        return {
            "compile": compile_result,
            "run": {"ok": False, "stdout": "", "stderr": "编译未通过，未运行。", "returncode": -1},
            "source": source.name,
        }
    return {
        "compile": compile_result,
        "run": _run_command([str(exe)], run_dir, timeout=8),
        "source": source.name,
    }


def _dotnet_target_framework(dotnet: str, run_dir: Path) -> str:
    result = _run_command([dotnet, "--list-sdks"], run_dir, timeout=10, env=_dotnet_env(run_dir))
    if result.get("ok"):
        majors: list[int] = []
        for line in str(result.get("stdout", "")).splitlines():
            version = line.split(maxsplit=1)[0].strip()
            match = version.split(".", 1)[0]
            if match.isdigit():
                majors.append(int(match))
        if majors:
            return f"net{max(majors)}.0"
    return "net8.0"


def _dotnet_env(run_dir: Path) -> dict[str, str]:
    return {
        "DOTNET_CLI_HOME": str(run_dir / ".dotnet_home"),
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1",
    }


def _compile_csharp(code: str, run_dir: Path) -> dict[str, Any]:
    compilers = _compiler_status()
    source = run_dir / "Program.cs"
    exe = run_dir / "main.exe"
    source.write_text(code, encoding="utf-8")

    csc = compilers["csc"]
    if csc:
        compile_result = _run_command([csc, "/nologo", f"/out:{exe}", str(source)], run_dir, timeout=20)
        if not compile_result["ok"]:
            return {
                "compile": compile_result,
                "run": {"ok": False, "stdout": "", "stderr": "编译未通过，未运行。", "returncode": -1},
                "source": source.name,
            }
        return {
            "compile": compile_result,
            "run": _run_command([str(exe)], run_dir, timeout=8),
            "source": source.name,
        }

    dotnet = compilers["dotnet"]
    if not dotnet:
        return {
            "compile": {
                "ok": False,
                "stdout": "",
                "stderr": "未检测到 C# 编译器。请安装 .NET SDK 或 Visual Studio Build Tools，并把 dotnet/csc 加入 PATH。",
                "returncode": -1,
            },
            "run": {"ok": False, "stdout": "", "stderr": "编译未通过，未运行。", "returncode": -1},
            "source": source.name,
        }

    target_framework = _dotnet_target_framework(dotnet, run_dir)
    project = run_dir / "CodeLab.csproj"
    project.write_text(
        (
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            "  <PropertyGroup>\n"
            "    <OutputType>Exe</OutputType>\n"
            f"    <TargetFramework>{target_framework}</TargetFramework>\n"
            "    <ImplicitUsings>enable</ImplicitUsings>\n"
            "    <Nullable>enable</Nullable>\n"
            "  </PropertyGroup>\n"
            "</Project>\n"
        ),
        encoding="utf-8",
    )
    env = _dotnet_env(run_dir)
    compile_result = _run_command([dotnet, "build", str(project), "-v:q", "--nologo"], run_dir, timeout=60, env=env)
    if not compile_result["ok"]:
        return {
            "compile": compile_result,
            "run": {"ok": False, "stdout": "", "stderr": "编译未通过，未运行。", "returncode": -1},
            "source": source.name,
        }
    run_result = _run_command([dotnet, "run", "--project", str(project), "--no-build", "--nologo"], run_dir, timeout=12, env=env)
    return {
        "compile": compile_result,
        "run": run_result,
        "source": source.name,
    }


def run_code(language: str, code: str) -> dict[str, Any]:
    language = language.strip().lower()
    aliases = {"py": "python", "python3": "python", "c++": "cpp", "cc": "cpp", "cs": "csharp", "c#": "csharp"}
    language = aliases.get(language, language)
    if language not in {"python", "c", "cpp", "csharp"}:
        return {"ok": False, "error": "语言只支持 python / c / cpp / csharp。"}
    code = _strip_fence(code)
    if not code:
        return {"ok": False, "error": "代码不能为空。"}
    if len(code) > MAX_CODE_CHARS:
        return {"ok": False, "error": f"代码太长，最多 {MAX_CODE_CHARS} 字符。"}

    _ensure_dirs()
    run_id = f"run-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if language == "python":
        result = _run_python(code, run_dir)
    elif language == "csharp":
        result = _compile_csharp(code, run_dir)
    else:
        result = _compile_c_like(language, code, run_dir)

    ok = bool(result.get("compile", {}).get("ok") and result.get("run", {}).get("ok"))
    summary = "编译/运行通过" if ok else "验证失败"
    record = {
        "time": int(time.time()),
        "run_id": run_id,
        "language": language,
        "ok": ok,
        "summary": summary,
        "source": result.get("source", ""),
        "code": code,
        "compile": result.get("compile", {}),
        "run": result.get("run", {}),
    }
    _append_history(record)
    record["run_dir"] = str(run_dir)
    return record


def format_run_result(record: dict[str, Any]) -> str:
    if not record.get("run_id"):
        return f"代码验证失败：{record.get('error', '未知错误')}"
    lines = [
        f"代码验证结果：{'通过' if record.get('ok') else '失败'}",
        f"语言：{record.get('language')}",
        f"运行目录：{record.get('run_dir')}",
    ]
    compile_result = record.get("compile", {})
    run_result = record.get("run", {})
    if compile_result:
        lines.append(f"\n编译：{'通过' if compile_result.get('ok') else '失败'}")
        if compile_result.get("stdout"):
            lines.append("编译输出：\n" + compile_result.get("stdout", ""))
        if compile_result.get("stderr"):
            lines.append("编译错误：\n" + compile_result.get("stderr", ""))
    if run_result:
        lines.append(f"\n运行：{'通过' if run_result.get('ok') else '失败'}")
        if run_result.get("stdout"):
            lines.append("运行输出：\n" + run_result.get("stdout", ""))
        if run_result.get("stderr"):
            lines.append("运行错误：\n" + run_result.get("stderr", ""))
    lines.append("\n已写入代码练习场历史，可用 /code_history 查看。")
    return "\n".join(lines)


def handle_code_lab_command(message: str) -> str | None:
    if message in {"/code_lab", "/code_status"}:
        return code_lab_status_text()
    if message == "/code_history":
        return code_history_text()
    if message.startswith("/code_run "):
        body = message.removeprefix("/code_run ").strip()
        if "=>" not in body:
            return "用法：/code_run cpp => 代码"
        language, code = [part.strip() for part in body.split("=>", 1)]
        return format_run_result(run_code(language, code))
    return None
