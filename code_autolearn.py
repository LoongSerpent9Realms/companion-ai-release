from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Any

from _paths import module_root, data_dir
from code_lab import format_run_result, run_code


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
CODE_AUTOLEARN_DIR = DATA_DIR / "code_autolearn"
HISTORY_FILE = CODE_AUTOLEARN_DIR / "history.jsonl"
TRAINING_JSONL_FILE = CODE_AUTOLEARN_DIR / "tiny_training.jsonl"
MAX_SNIPPETS = 3
MAX_FIX_ATTEMPTS = 2


def _ensure_dirs() -> None:
    CODE_AUTOLEARN_DIR.mkdir(parents=True, exist_ok=True)


def _append_history(record: dict[str, Any]) -> None:
    _ensure_dirs()
    with open(HISTORY_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_history_records() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _infer_language(topic: str, explicit: str = "") -> str:
    text = f"{explicit} {topic}".lower()
    if explicit.lower() in {"python", "py"}:
        return "python"
    if explicit.lower() in {"cpp", "c++", "cc"}:
        return "cpp"
    if explicit.lower() in {"csharp", "cs", "c#"}:
        return "csharp"
    if explicit.lower() == "c":
        return "c"
    if any(key in text for key in ("c#", "csharp", "dotnet", "console.writeline", "using system")):
        return "csharp"
    if any(key in text for key in ("c++", "cpp", "stl", "iostream", "vector")):
        return "cpp"
    if any(key in text for key in ("python", "py", "pip")):
        return "python"
    if any(key in text for key in ("c语言", " c ", "stdio", "指针")):
        return "c"
    return "python"


def _strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</(?:p|div|li|tr|pre|code)>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def _extract_code_snippets(raw_html: str, language: str) -> list[str]:
    snippets: list[str] = []
    blocks = re.findall(r"<pre[^>]*>(.*?)</pre>", raw_html, flags=re.I | re.S)
    blocks += re.findall(r"<code[^>]*>(.*?)</code>", raw_html, flags=re.I | re.S)
    for block in blocks:
        code = _strip_tags(block)
        code = re.sub(r"\n{3,}", "\n\n", code).strip()
        if _looks_like_code(code, language):
            snippets.append(code)
    return _dedupe_snippets(snippets)[:MAX_SNIPPETS]


def _looks_like_code(code: str, language: str) -> bool:
    if len(code) < 20 or len(code) > 12_000:
        return False
    lowered = code.lower()
    if language == "python":
        return any(key in lowered for key in ("print(", "def ", "import ", "for ", "if "))
    if language == "c":
        return any(key in lowered for key in ("#include", "int main", "printf(", "scanf(", "malloc("))
    if language == "cpp":
        return any(key in lowered for key in ("#include", "int main", "std::", "cout", "vector<"))
    if language == "csharp":
        return any(key in lowered for key in ("using system", "console.writeline", "static void main", "class program"))
    return False


def _dedupe_snippets(snippets: list[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for snippet in snippets:
        key = re.sub(r"\s+", " ", snippet)[:300]
        if key in seen:
            continue
        seen.add(key)
        result.append(snippet)
    return result


def _extract_code_from_llm_reply(text: str) -> str:
    match = re.search(r"```(?:csharp|cs|c#|c\+\+|cpp|c|python|py)?\s*(.*?)```", text or "", flags=re.I | re.S)
    if match:
        return match.group(1).strip()
    return (text or "").strip()


def _try_learned_llm_fix(language: str, topic: str, code: str, result: dict[str, Any]) -> str:
    """Reserved hook for the self-trained Tiny LLM backend.

    This never calls a remote model or a pretrained local model. It only uses
    the app's own tiny_llm checkpoint after /code_learn_train has created one.
    The current runtime keeps rule-fix as the default so this hook can be
    extended later without changing the learning loop.
    """
    try:
        from tiny_llm import tiny_llm_chat

        compile_err = result.get("compile", {}).get("stderr", "")
        run_err = result.get("run", {}).get("stderr", "")
        prompt = (
            f"语言：{language}\n"
            f"主题：{topic}\n"
            "请把下面代码修成可独立运行的最小示例，只返回完整代码。\n"
            f"原代码：\n```{language}\n{code[:4000]}\n```\n"
            f"错误：\n{(compile_err or run_err)[:1200]}"
        )
        reply = tiny_llm_chat(prompt, history=[])
        fixed = _extract_code_from_llm_reply(reply)
        return fixed if _looks_like_code(fixed, language) else ""
    except Exception:
        return ""


def _try_rule_fix(language: str, code: str, result: dict[str, Any]) -> str:
    """Apply tiny deterministic cleanups only; never call any LLM."""
    fixed = code.strip()
    if not fixed:
        return ""
    if language == "python":
        fixed = fixed.replace("\r\n", "\n")
    elif language == "c":
        if "printf(" in fixed and "#include <stdio.h>" not in fixed:
            fixed = "#include <stdio.h>\n" + fixed
        if "int main" not in fixed and not re.search(r"\bmain\s*\(", fixed):
            fixed = f"#include <stdio.h>\nint main(void) {{\n{_indent_code(fixed)}\n    return 0;\n}}"
    elif language == "cpp":
        if any(token in fixed for token in ("cout", "cin", "vector<", "string ")) and "#include" not in fixed:
            fixed = "#include <iostream>\n#include <vector>\n#include <string>\nusing namespace std;\n" + fixed
        if "int main" not in fixed and not re.search(r"\bmain\s*\(", fixed):
            fixed = f"int main() {{\n{_indent_code(fixed)}\n    return 0;\n}}"
    elif language == "csharp":
        if "Console." in fixed and "using System" not in fixed:
            fixed = "using System;\n" + fixed
        if "static void Main" not in fixed and "static int Main" not in fixed:
            fixed = f"using System;\nclass Program {{\n    static void Main() {{\n{_indent_code(_indent_code(fixed))}\n    }}\n}}"
    return fixed if fixed != code and _looks_like_code(fixed, language) else ""


def _indent_code(code: str) -> str:
    return "\n".join("    " + line if line.strip() else line for line in code.splitlines())


def _search_error_hints(language: str, topic: str, result: dict[str, Any]) -> list[dict[str, str]]:
    error_text = (result.get("compile", {}).get("stderr") or result.get("run", {}).get("stderr") or "")[:300]
    if not error_text.strip():
        return []
    try:
        from web_learner import web_search

        query = f"{language} {topic} 编译错误 {error_text}"
        hits = web_search(query, max_results=3)
        return [{"domain": hit.get("domain", ""), "url": hit.get("url", ""), "title": hit.get("title", "")} for hit in hits]
    except Exception:
        return []


def code_autolearn(topic: str, language: str = "") -> dict[str, Any]:
    topic = topic.strip()
    if not topic:
        return {"ok": False, "error": "主题不能为空。"}
    language = _infer_language(topic, language)
    try:
        from web_learner import _request_html, fetch_and_extract, web_search
    except Exception as exc:
        return {"ok": False, "error": f"联网学习模块不可用：{exc}"}

    search_query = f"{topic} {language} 示例代码 官方文档 教程"
    results = web_search(search_query, max_results=5)
    if not results:
        return {"ok": False, "error": "没有搜索到可用资料。"}

    attempts: list[dict[str, Any]] = []
    for source in results:
        raw_html, fetch_error = _request_html(source.get("url", ""))
        if fetch_error or not raw_html:
            continue
        page = fetch_and_extract(source.get("url", ""))
        page_text = page.get("text", "") if page.get("ok") else ""
        snippets = _extract_code_snippets(raw_html, language)
        for snippet in snippets:
            run_record = run_code(language, snippet)
            attempt = {
                "source": source,
                "code": snippet,
                "result": run_record,
                "fixes": [],
                "error_hints": [],
            }
            if run_record.get("ok"):
                attempts.append(attempt)
                record = _history_record(topic, language, attempts, ok=True)
                _append_history(record)
                return {"ok": True, "record": record}

            attempt["error_hints"] = _search_error_hints(language, topic, run_record)
            fixed_code = snippet
            fixed_result = run_record
            for _ in range(MAX_FIX_ATTEMPTS):
                candidate = _try_rule_fix(language, fixed_code, fixed_result)
                if not candidate or candidate == fixed_code:
                    break
                fixed_code = candidate
                fixed_result = run_code(language, fixed_code)
                attempt["fixes"].append({"code": fixed_code, "result": fixed_result})
                if fixed_result.get("ok"):
                    attempts.append(attempt)
                    record = _history_record(topic, language, attempts, ok=True)
                    _append_history(record)
                    return {"ok": True, "record": record}
            attempts.append(attempt)
            if len(attempts) >= MAX_SNIPPETS:
                record = _history_record(topic, language, attempts, ok=False)
                _append_history(record)
                return {"ok": False, "record": record}

    record = _history_record(topic, language, attempts, ok=False)
    _append_history(record)
    if not attempts:
        return {"ok": False, "error": "找到了资料，但没有提取到可验证的代码片段。", "record": record}
    return {"ok": False, "record": record}


def _history_record(topic: str, language: str, attempts: list[dict[str, Any]], ok: bool) -> dict[str, Any]:
    return {
        "time": int(time.time()),
        "topic": topic,
        "language": language,
        "ok": ok,
        "attempts": attempts,
        "summary": "验证通过并学习" if ok else "未能自动修复到通过",
    }


def build_code_training_texts(records: list[dict[str, Any]] | None = None) -> list[str]:
    records = records if records is not None else _load_history_records()
    texts: list[str] = []
    for record in records:
        topic = str(record.get("topic", "")).strip()
        language = str(record.get("language", "")).strip() or "python"
        for attempt in record.get("attempts", []):
            source = attempt.get("source", {})
            source_title = str(source.get("title", "")).strip()
            source_url = str(source.get("url", "")).strip()
            run_result = attempt.get("result", {})
            code = str(attempt.get("code", "")).strip()
            if code and run_result.get("ok"):
                texts.append(_format_training_text(topic, language, "写一个可运行的学习示例", code, source_title, source_url))
            for fix in attempt.get("fixes", []):
                fixed_code = str(fix.get("code", "")).strip()
                fixed_result = fix.get("result", {})
                if fixed_code and fixed_result.get("ok"):
                    error_text = _attempt_error_text(run_result)
                    request = f"修复这个{language}示例。错误：{error_text[:600]}"
                    texts.append(_format_training_text(topic, language, request, fixed_code, source_title, source_url))
    return _dedupe_texts(texts)


def _format_training_text(topic: str, language: str, request: str, code: str, source_title: str, source_url: str) -> str:
    source_line = f"\n来源：{source_title} {source_url}".strip()
    return (
        f"用户：主题：{topic}\n语言：{language}\n任务：{request}{source_line}\n"
        f"助手：```{language}\n{code}\n```"
    )


def _attempt_error_text(result: dict[str, Any]) -> str:
    compile_err = result.get("compile", {}).get("stderr", "")
    run_err = result.get("run", {}).get("stderr", "")
    return (compile_err or run_err or "无错误输出").strip()


def _dedupe_texts(texts: list[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for text in texts:
        key = re.sub(r"\s+", " ", text)[:600]
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def export_code_training_dataset() -> dict[str, Any]:
    texts = build_code_training_texts()
    _ensure_dirs()
    with open(TRAINING_JSONL_FILE, "w", encoding="utf-8") as handle:
        for text in texts:
            handle.write(json.dumps({"text": text, "source": "code_autolearn"}, ensure_ascii=False) + "\n")
    return {"ok": True, "path": str(TRAINING_JSONL_FILE), "samples": len(texts)}


def train_code_tiny_llm(epochs: int = 8) -> dict[str, Any]:
    texts = build_code_training_texts()
    if not texts:
        return {"ok": False, "error": "还没有可用于训练的代码自学样本。先运行 /code_learn 收集通过验证的示例。"}
    try:
        from tiny_llm import train_tiny_llm
    except Exception as exc:
        return {"ok": False, "error": f"tiny_llm 模块不可用：{exc}"}
    export_code_training_dataset()
    return train_tiny_llm(
        texts=texts,
        epochs=max(1, min(int(epochs), 50)),
        batch_size=min(16, max(1, len(texts))),
        max_seq_len=256,
        config={
            "embed_dim": 192,
            "num_heads": 4,
            "num_layers": 3,
            "ffn_dim": 384,
            "max_seq_len": 256,
            "dropout": 0.1,
        },
    )


def code_learn_llm_status_text() -> str:
    records = _load_history_records()
    texts = build_code_training_texts(records)
    model_status = "未知"
    try:
        from tiny_llm import MODEL_FILE, VOCAB_FILE

        model_status = "已训练" if MODEL_FILE.exists() and VOCAB_FILE.exists() else "未训练"
    except Exception:
        model_status = "tiny_llm 模块不可用"
    return (
        "代码自学 Tiny LLM：\n"
        f"  历史记录: {len(records)} 条\n"
        f"  可训练样本: {len(texts)} 条\n"
        f"  训练集文件: {TRAINING_JSONL_FILE}\n"
        f"  模型状态: {model_status}\n\n"
        "命令：\n"
        "  /code_learn_dataset 导出训练集\n"
        "  /code_learn_train 8 从自学记录训练 tiny LLM"
    )


def code_autolearn_history_text(limit: int = 8) -> str:
    try:
        records = _load_history_records()
    except Exception:
        return "读取代码自学记录失败。"
    if not records:
        return "还没有代码自学记录。"
    lines = [f"最近代码自学记录（{min(limit, len(records))}/{len(records)}）："]
    for item in records[-limit:]:
        timestamp = time.strftime("%m-%d %H:%M", time.localtime(int(item.get("time", 0))))
        status = "通过" if item.get("ok") else "未通过"
        lines.append(f"- {timestamp} [{item.get('language')}] {status}: {item.get('topic')} ({len(item.get('attempts', []))} 次尝试)")
    return "\n".join(lines)


def format_code_autolearn_result(result: dict[str, Any]) -> str:
    if not result.get("record"):
        return f"代码自学失败：{result.get('error', '未知错误')}"
    record = result["record"]
    lines = [
        f"代码自学结果：{'通过' if record.get('ok') else '未通过'}",
        f"主题：{record.get('topic')}",
        f"语言：{record.get('language')}",
        f"尝试：{len(record.get('attempts', []))} 次",
    ]
    for index, attempt in enumerate(record.get("attempts", [])[:3], start=1):
        source = attempt.get("source", {})
        run_result = attempt.get("result", {})
        lines.append(f"\n#{index} 来源：{source.get('domain', '')}")
        lines.append(source.get("url", ""))
        lines.append(f"初次验证：{'通过' if run_result.get('ok') else '失败'}")
        if not run_result.get("ok"):
            compile_err = run_result.get("compile", {}).get("stderr", "")
            run_err = run_result.get("run", {}).get("stderr", "")
            detail = (compile_err or run_err or "无错误输出").strip()
            lines.append("错误摘要：\n" + detail[:1200])
            hints = attempt.get("error_hints") or []
            if hints:
                lines.append("已搜索修复线索：")
                for hint in hints[:2]:
                    lines.append(f"- {hint.get('domain', '')}: {hint.get('title', '')}")
            fixes = attempt.get("fixes") or []
            if fixes:
                last = fixes[-1].get("result", {})
                lines.append(f"自动修复尝试：{len(fixes)} 次，最后结果：{'通过' if last.get('ok') else '失败'}")
            else:
                lines.append("自动修复尝试：0 次（未调用任何 LLM，只记录错误和搜索线索）")
        else:
            lines.append(format_run_result(run_result))
    lines.append("\n记录已保存，可用 /code_autolearn_history 查看。")
    return "\n".join(lines)


def handle_code_autolearn_command(message: str) -> str | None:
    if message == "/code_autolearn_history":
        return code_autolearn_history_text()
    if message in {"/code_learn_llm", "/code_learn_llm_status"}:
        return code_learn_llm_status_text()
    if message == "/code_learn_dataset":
        result = export_code_training_dataset()
        return f"代码自学训练集已导出：{result['samples']} 条\n{result['path']}"
    if message == "/code_learn_train" or message.startswith("/code_learn_train "):
        epochs = 8
        parts = message.split()
        if len(parts) > 1:
            try:
                epochs = int(parts[1])
            except ValueError:
                pass
        result = train_code_tiny_llm(epochs=epochs)
        if not result.get("ok"):
            return f"代码 Tiny LLM 训练失败：{result.get('error', '未知错误')}"
        return (
            "代码 Tiny LLM 训练完成：\n"
            f"  样本: {result.get('samples', result.get('examples', '?'))} 条\n"
            f"  词表: {result.get('vocab_size', '?')} 个\n"
            f"  轮数: {result.get('epochs', epochs)}\n"
            f"  loss: {result.get('final_loss', result.get('loss', '?'))}\n"
            f"  模型: {result.get('model_path', '?')}"
        )
    if message.startswith("/code_learn "):
        body = message.removeprefix("/code_learn ").strip()
        language = ""
        topic = body
        if "=>" in body:
            language, topic = [part.strip() for part in body.split("=>", 1)]
        return format_code_autolearn_result(code_autolearn(topic, language))
    return None
