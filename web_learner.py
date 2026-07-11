"""Web learner module for Companion AI.

Enables AI to autonomously search the web, evaluate source trustworthiness,
and learn from online content. Features:

- DuckDuckGo HTML search (no API key required)
- Source trustworthiness assessment (teachable by user)
- Knowledge extraction and storage to long-term memory
- Automatic learning triggers when AI detects knowledge gaps
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Optional

from _paths import module_root, data_dir

ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
TRUST_CONFIG_FILE = DATA_DIR / "web_trust.json"
LEARNING_HISTORY_FILE = DATA_DIR / "learning_history.jsonl"
_LAST_SEARCH_ERRORS: list[str] = []
LEARNING_RECORD_START = "[[LEARNING_RECORD_JSON]]"
LEARNING_RECORD_END = "[[/LEARNING_RECORD_JSON]]"

DEFAULT_TRUST_CONFIG = {
    "enabled": True,
    "auto_learn": True,
    "require_user_consent": False,
    "wifi_only": True,
    "min_trust_score": 30,
    "max_results": 5,
    "trust_levels": {
        "high": ["gov.cn", ".edu.cn", ".ac.cn", "wikipedia.org", "zh.wikipedia.org", "baike.baidu.com"],
        "medium": ["news.qq.com", "news.sina.com.cn", "news.sohu.com", "zhihu.com", "bilibili.com"],
        "low": ["weibo.com", "tieba.baidu.com", "douban.com"],
    },
    "domain_trust": {},
    "self_study_enabled": True,
    "self_study_min_interval_hours": 1,
    "self_study_max_interval_hours": 24,
    "self_study_interval_hours": 6,
    "self_study_topics": ["科技新闻", "人工智能", "网络安全", "健康知识"],
}


def _load_trust_config() -> dict:
    if TRUST_CONFIG_FILE.exists():
        try:
            raw = json.loads(TRUST_CONFIG_FILE.read_text(encoding="utf-8"))
            config = dict(DEFAULT_TRUST_CONFIG)
            config.update(raw)
            return config
        except Exception:
            pass
    return dict(DEFAULT_TRUST_CONFIG)


def _save_trust_config(config: dict) -> None:
    TRUST_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def is_wifi_connected() -> bool:
    """Check if connected via WiFi on Windows."""
    try:
        import subprocess
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if "状态" in line or "State" in line:
                if "已连接" in line or "connected" in line.lower():
                    return True
        return False
    except Exception:
        return True


def is_network_available() -> bool:
    """Check if network is available."""
    try:
        urllib.request.urlopen("http://www.baidu.com", timeout=5)
        return True
    except Exception:
        return False


def assess_trust(domain: str) -> int:
    """Assess trustworthiness of a domain (0-100)."""
    config = _load_trust_config()

    if domain in config.get("domain_trust", {}):
        return config["domain_trust"][domain]

    for level, domains in config.get("trust_levels", {}).items():
        for trusted_domain in domains:
            if trusted_domain in domain or domain.endswith(trusted_domain):
                if level == "high":
                    return 80
                elif level == "medium":
                    return 50
                elif level == "low":
                    return 20

    return 50


def set_domain_trust(domain: str, score: int) -> None:
    """Set trust score for a domain (0-100)."""
    config = _load_trust_config()
    config["domain_trust"][domain] = max(0, min(100, score))
    _save_trust_config(config)


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _normalize_result_url(href: str) -> str:
    href = unescape(href or "").strip()
    href = urllib.parse.unquote(href)
    parsed = urllib.parse.urlparse(href)

    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        if params.get("uddg"):
            href = params["uddg"][0]
            parsed = urllib.parse.urlparse(href)

    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("u") or params.get("r")
        if target:
            href = target[0]
            if href.startswith("a1"):
                try:
                    href = urllib.parse.unquote(href[2:])
                except Exception:
                    pass
            parsed = urllib.parse.urlparse(href)

    if "yandex." in parsed.netloc and parsed.path.startswith("/clck/"):
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("url") or params.get("to")
        if target:
            href = target[0]
            parsed = urllib.parse.urlparse(href)

    if not parsed.scheme and href.startswith("//"):
        href = "https:" + href
        parsed = urllib.parse.urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    return href


def _build_result(title: str, href: str, snippet: str) -> dict | None:
    url = _normalize_result_url(href)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if not domain or any(blocked in domain for blocked in ("duckduckgo.com", "bing.com", "yandex.")):
        return None
    return {
        "title": _clean_html_text(title),
        "url": url,
        "domain": domain,
        "snippet": _clean_html_text(snippet),
        "trust_score": assess_trust(domain),
    }


def _request_html(url: str, timeout: int = 12) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("content-type", "")
            raw = resp.read(1_500_000)
    except Exception as exc:
        return "", str(exc)

    encoding = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    try:
        return raw.decode(encoding, errors="replace"), ""
    except Exception:
        return raw.decode("utf-8", errors="replace"), ""


def _dedupe_and_sort(results: list[dict], max_results: int) -> list[dict]:
    deduped = []
    seen = set()
    for result in results:
        key = result["url"].split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return sorted(deduped, key=lambda x: x["trust_score"], reverse=True)[:max_results]


def _parse_duckduckgo_results(html: str, max_results: int) -> list[dict]:
    results = []
    blocks = re.findall(r'<div[^>]+class="[^"]*\bresult__body\b[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'<a[^>]+class="[^"]*\bresult__a\b[^"]*"[^>]*>.*?</a>.*?(?=<a[^>]+class="[^"]*\bresult__a\b|$)', html, re.DOTALL)

    for block in blocks:
        link = re.search(r'<a[^>]+class="[^"]*\bresult__a\b[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not link:
            continue
        snippet_match = re.search(r'class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
        result = _build_result(link.group(2), link.group(1), snippet_match.group(1) if snippet_match else "")
        if result:
            results.append(result)
        if len(results) >= max_results:
            break
    return results


def _parse_bing_results(html: str, max_results: int) -> list[dict]:
    results = []
    blocks = re.findall(r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL)
    for block in blocks:
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>', block, re.DOTALL)
        if not link:
            continue
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        result = _build_result(link.group(2), link.group(1), snippet_match.group(1) if snippet_match else "")
        if result:
            results.append(result)
        if len(results) >= max_results:
            break
    return results


def _parse_yandex_results(html: str, max_results: int) -> list[dict]:
    results = []
    link_pattern = re.compile(
        r'<a[^>]+class="[^"]*(?:\bOrganicTitle-Link\b|\borganic__url\b)[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    matches = list(link_pattern.finditer(html))

    for index, link in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else min(len(html), link.end() + 5000)
        block = html[link.start():next_start]
        snippet = ""
        for snippet_pattern in (
            r'<span[^>]+class="[^"]*\bOrganicTextContentSpan\b[^"]*"[^>]*>(.*?)</span>',
            r'<div[^>]+class="[^"]*\bOrganicTextContent\b[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]+class="[^"]*\borganic__text\b[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]+class="[^"]*\borganic__text\b[^"]*"[^>]*>(.*?)</span>',
        ):
            snippet_match = re.search(snippet_pattern, block, re.DOTALL)
            if snippet_match:
                snippet = snippet_match.group(1)
                break

        result = _build_result(link.group(2), link.group(1), snippet)
        if result:
            results.append(result)
        if len(results) >= max_results:
            break

    return results


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web for query and return trusted-looking organic results."""
    global _LAST_SEARCH_ERRORS
    _LAST_SEARCH_ERRORS = []

    encoded = urllib.parse.quote_plus(query)
    providers = [
        (
            "Bing",
            f"https://www.bing.com/search?q={encoded}&setlang=zh-CN&mkt=zh-CN",
            _parse_bing_results,
        ),
        (
            "Yandex",
            f"https://yandex.com/search/?text={encoded}&lang=zh",
            _parse_yandex_results,
        ),
        (
            "DuckDuckGo",
            f"https://html.duckduckgo.com/html/?q={encoded}&kl=zh-CN&kp=-1",
            _parse_duckduckgo_results,
        ),
    ]

    all_results = []
    for name, url, parser in providers:
        html, error = _request_html(url)
        if error:
            _LAST_SEARCH_ERRORS.append(f"{name}: {error}")
            continue
        provider_results = parser(html, max_results)
        if not provider_results:
            _LAST_SEARCH_ERRORS.append(f"{name}: 未解析到搜索结果")
            continue
        all_results.extend(provider_results)
        if len(all_results) >= max_results:
            break

    return _dedupe_and_sort(all_results, max_results)


def get_last_search_errors() -> list[str]:
    return list(_LAST_SEARCH_ERRORS)



def fetch_and_extract(url: str) -> dict:
    """Fetch URL and extract text content."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"ok": False, "error": "只支持 http/https"}

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,text/plain",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("content-type", "")
            raw = resp.read(1_000_000)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    encoding = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)

    try:
        body = raw.decode(encoding, errors="replace")
    except Exception:
        body = raw.decode("utf-8", errors="replace")

    if "html" in content_type or "<html" in body[:1000].lower():
        text = re.sub(r"<[^>]+>", " ", body)
        text = re.sub(r"\s+", " ", text).strip()
    else:
        text = re.sub(r"\s+", " ", body).strip()

    return {
        "ok": True,
        "title": parsed.netloc,
        "text": text[:8000],
        "url": url,
        "domain": parsed.netloc.lower(),
        "trust_score": assess_trust(parsed.netloc.lower()),
    }


def learn_from_web(query: str, context: str = "") -> dict:
    """Complete web learning flow: search -> fetch -> extract -> summarize."""
    config = _load_trust_config()
    if not config.get("enabled", True):
        return {"ok": False, "error": "联网学习未启用"}

    if not is_network_available():
        return {"ok": False, "error": "网络不可用"}

    if config.get("wifi_only", True) and not is_wifi_connected():
        return {"ok": False, "error": "仅在WiFi环境下学习"}

    results = web_search(query, max_results=config.get("max_results", 5))
    if not results:
        details = "；".join(get_last_search_errors()[:2])
        if details:
            return {"ok": False, "error": f"搜索无结果（{details}）"}
        return {"ok": False, "error": "搜索无结果"}

    min_trust = config.get("min_trust_score", 30)
    trusted_results = [r for r in results if r["trust_score"] >= min_trust]

    if not trusted_results:
        return {"ok": False, "error": "无足够信任度的来源"}

    fetch_results = []
    for result in trusted_results[:3]:
        fetched = fetch_and_extract(result["url"])
        if fetched.get("ok"):
            fetch_results.append(fetched)

    if not fetch_results:
        return {"ok": False, "error": "无法获取内容"}

    combined = "\n\n".join([
        f"【来源】{r['domain']} (信任度:{r['trust_score']})\n{r['text']}"
        for r in fetch_results
    ])

    now = int(time.time())
    LEARNING_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARNING_HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "time": now,
            "query": query,
            "sources": [r["url"] for r in fetch_results],
            "trust_scores": [r["trust_score"] for r in fetch_results],
            "content_length": len(combined),
            "source_details": [{
                "domain": r["domain"],
                "url": r["url"],
                "trust_score": r["trust_score"],
                "title": r.get("title", ""),
                "content_length": len(r.get("text", "")),
            } for r in fetch_results],
        }, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "query": query,
        "sources": [{
            "url": r["url"],
            "domain": r["domain"],
            "trust_score": r["trust_score"],
            "title": r.get("title", ""),
            "content_length": len(r.get("text", "")),
            "excerpt": r.get("text", "")[:360],
        } for r in fetch_results],
        "content": combined,
        "content_length": len(combined),
        "summary": f"已从 {len(fetch_results)} 个来源学习关于「{query}」的知识",
    }


def learning_record_payload(result: dict) -> str:
    """Return a hidden JSON payload for the chat UI learning record card."""
    record = {
        "type": "learning_record",
        "time": int(time.time()),
        "query": result.get("query", ""),
        "summary": result.get("summary", ""),
        "content_length": result.get("content_length", len(result.get("content", ""))),
        "sources": result.get("sources", []),
        "learned": [
            result.get("summary", ""),
            f"整理了 {len(result.get('sources', []))} 个来源，合计约 {result.get('content_length', len(result.get('content', '')))} 字符的学习材料。",
        ],
    }
    return f"{LEARNING_RECORD_START}{json.dumps(record, ensure_ascii=False)}{LEARNING_RECORD_END}"


def update_trust_from_feedback(source_url: str, positive: bool) -> None:
    """Update domain trust based on user feedback."""
    parsed = urllib.parse.urlparse(source_url)
    domain = parsed.netloc.lower()
    current = assess_trust(domain)
    delta = 10 if positive else -10
    new_score = max(0, min(100, current + delta))
    set_domain_trust(domain, new_score)


def _normalize_self_study_topics(raw_topics) -> list[str]:
    topics = []
    seen = set()
    for topic in raw_topics or []:
        text = str(topic).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        topics.append(text)
    return topics


def _parse_topic_list(value: str) -> list[str]:
    return _normalize_self_study_topics(re.split(r"[,，\n]", value or ""))


def _self_study_topics(config: dict) -> list[str]:
    topics = _normalize_self_study_topics(config.get("self_study_topics", []))
    if topics != config.get("self_study_topics", []):
        config["self_study_topics"] = topics
        _save_trust_config(config)
    return topics


def format_self_study_topics(config: Optional[dict] = None) -> str:
    """Return a hidden-list style view of self-study topics."""
    config = config or _load_trust_config()
    topics = _self_study_topics(config)
    lines = ["自主学习主题列表："]
    if not topics:
        lines.append("  暂无主题。")
    else:
        for index, topic in enumerate(topics, start=1):
            lines.append(f"  {index}. {topic}")
    lines.append("\n管理命令：")
    lines.append("  /self_study_add 主题1,主题2")
    lines.append("  /self_study_set 序号 => 新主题")
    lines.append("  /self_study_del 序号或完整主题")
    lines.append("  /self_study_topic 主题1,主题2 - 批量替换整个列表")
    return "\n".join(lines)


def get_trust_status() -> str:
    """Return formatted trust configuration status."""
    config = _load_trust_config()
    lines = ["联网学习信任配置："]
    lines.append(f"  状态: {'已启用' if config.get('enabled') else '未启用'}")
    lines.append(f"  自动学习: {'是' if config.get('auto_learn') else '否'}")
    lines.append(f"  用户同意: {'无需' if not config.get('require_user_consent') else '需要'}")
    lines.append(f"  WiFi限制: {'仅WiFi' if config.get('wifi_only') else '无限制'}")
    lines.append(f"  网络状态: {'在线' if is_network_available() else '离线'}")
    lines.append(f"  当前网络: {'WiFi' if is_wifi_connected() else '移动网络/有线'}")
    lines.append(f"  最低信任阈值: {config.get('min_trust_score', 30)}")
    lines.append(f"  最大搜索结果: {config.get('max_results', 5)}")
    lines.append(f"\n  自主学习: {'已启用' if config.get('self_study_enabled') else '未启用'}")
    lines.append(f"  学习间隔: {config.get('self_study_interval_hours', 6)}小时")
    lines.append(f"  间隔范围: {config.get('self_study_min_interval_hours', 1)} - {config.get('self_study_max_interval_hours', 24)}小时")
    topics = _self_study_topics(config)
    lines.append(f"  学习主题: {', '.join(topics)}")
    if config.get("domain_trust"):
        lines.append("\n  自定义信任等级:")
        for domain, score in sorted(config["domain_trust"].items(), key=lambda x: x[1], reverse=True):
            lines.append(f"    {domain}: {score}")
    lines.append("\n  命令:")
    lines.append("    /learn <主题> - 搜索并学习")
    lines.append("    /learn_on - 开启自动学习")
    lines.append("    /learn_off - 关闭自动学习")
    lines.append("    /self_study_on - 开启自主学习（无需用户询问）")
    lines.append("    /self_study_off - 关闭自主学习")
    lines.append("    /self_study_topics - 查看自主学习主题列表")
    lines.append("    /self_study_add 主题1,主题2 - 添加主题")
    lines.append("    /self_study_set 序号 => 新主题 - 修改主题")
    lines.append("    /self_study_del 序号或完整主题 - 删除主题")
    lines.append("    /self_study_topic 主题1,主题2 - 设置学习主题")
    lines.append("    /self_study_min <小时> - 设置最低学习间隔（AI不能低于此值）")
    lines.append("    /self_study_max <小时> - 设置最大学习间隔（AI不能超过此值）")
    lines.append("    /trust_source <域名> <0-100> - 设置信任等级")
    lines.append("    /learn_status - 查看学习状态")
    return "\n".join(lines)


def get_learning_summary(recent_days: int = 7) -> str:
    """Return summary of recent learning activities."""
    if not LEARNING_HISTORY_FILE.exists():
        return "暂无学习记录。使用 /learn <主题> 开始联网学习。"

    now = int(time.time())
    cutoff = now - (recent_days * 24 * 60 * 60)
    recent = []

    try:
        for line in LEARNING_HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if entry.get("time", 0) >= cutoff:
                    recent.append(entry)
    except Exception:
        return "读取学习记录失败。"

    if not recent:
        return f"最近 {recent_days} 天没有学习记录。"

    lines = [f"最近 {recent_days} 天的学习记录（共 {len(recent)} 次）："]
    for entry in reversed(recent[-10:]):
        timestamp = time.strftime("%m-%d %H:%M", time.localtime(entry["time"]))
        lines.append(f"  {timestamp}: {entry['query']}")
    return "\n".join(lines)


def handle_learn_command(message: str) -> str | None:
    """Handle learning-related commands."""
    if message == "/learn_status" or message == "/learn_info":
        return get_trust_status() + "\n\n" + get_learning_summary()
    if message == "/learn_off":
        config = _load_trust_config()
        config["enabled"] = False
        _save_trust_config(config)
        return "已关闭联网学习功能。"
    if message == "/learn_on":
        config = _load_trust_config()
        config["enabled"] = True
        _save_trust_config(config)
        return "已开启联网学习功能。"
    if message.startswith("/learn "):
        query = message[7:].strip()
        if not query:
            return "用法：/learn <学习主题>"
        result = learn_from_web(query)
        if not result.get("ok"):
            return f"学习失败：{result.get('error', '未知错误')}"
        return (
            f"学习完成！\n"
            f"主题: {result['query']}\n"
            f"来源: {', '.join(s['domain'] for s in result['sources'])}\n"
            f"信任度: {', '.join(str(s['trust_score']) for s in result['sources'])}\n"
            f"\n{result['summary']}\n\n"
            f"{learning_record_payload(result)}"
        )
    if message.startswith("/trust_source "):
        parts = message[14:].strip().split(maxsplit=1)
        if len(parts) < 2:
            return "用法：/trust_source <域名> <0-100>"
        domain = parts[0].strip()
        try:
            score = int(parts[1].strip())
        except ValueError:
            return "信任等级必须是数字（0-100）。"
        set_domain_trust(domain, score)
        return f"已设置域名「{domain}」的信任等级为 {score}。"
    if message == "/self_study_on":
        config = _load_trust_config()
        config["self_study_enabled"] = True
        _save_trust_config(config)
        _start_self_study_thread()
        return "已开启自主学习功能，AI会定期主动学习新知识。"
    if message == "/self_study_off":
        config = _load_trust_config()
        config["self_study_enabled"] = False
        _save_trust_config(config)
        _stop_self_study_thread()
        return "已关闭自主学习功能。"
    if message in {"/self_study_topics", "/self_study_list"}:
        return format_self_study_topics()
    if message.startswith("/self_study_add "):
        new_topics = _parse_topic_list(message.removeprefix("/self_study_add ").strip())
        if not new_topics:
            return "用法：/self_study_add 主题1,主题2"
        config = _load_trust_config()
        topics = _normalize_self_study_topics([*_self_study_topics(config), *new_topics])
        config["self_study_topics"] = topics
        _save_trust_config(config)
        return "已添加自主学习主题。\n\n" + format_self_study_topics(config)
    if message.startswith("/self_study_set "):
        body = message.removeprefix("/self_study_set ").strip()
        if "=>" not in body:
            return "用法：/self_study_set 序号 => 新主题"
        index_text, new_topic = [part.strip() for part in body.split("=>", 1)]
        try:
            index = int(index_text)
        except ValueError:
            return "序号必须是数字。用 /self_study_topics 查看当前列表。"
        new_topic = new_topic.strip()
        if not new_topic:
            return "新主题不能为空。"
        config = _load_trust_config()
        topics = _self_study_topics(config)
        if index < 1 or index > len(topics):
            return f"序号超出范围。当前共有 {len(topics)} 个主题。"
        old_topic = topics[index - 1]
        topics[index - 1] = new_topic
        config["self_study_topics"] = _normalize_self_study_topics(topics)
        _save_trust_config(config)
        return f"已修改主题：{old_topic} => {new_topic}\n\n" + format_self_study_topics(config)
    if message.startswith("/self_study_del ") or message.startswith("/self_study_remove "):
        if message.startswith("/self_study_del "):
            target = message.removeprefix("/self_study_del ").strip()
        else:
            target = message.removeprefix("/self_study_remove ").strip()
        if not target:
            return "用法：/self_study_del 序号或完整主题"
        config = _load_trust_config()
        topics = _self_study_topics(config)
        removed = ""
        try:
            index = int(target)
        except ValueError:
            index = 0
        if index:
            if index < 1 or index > len(topics):
                return f"序号超出范围。当前共有 {len(topics)} 个主题。"
            removed = topics.pop(index - 1)
        else:
            for existing in list(topics):
                if existing == target:
                    topics.remove(existing)
                    removed = existing
                    break
            if not removed:
                return f"没有找到主题：{target}\n\n" + format_self_study_topics(config)
        config["self_study_topics"] = topics
        _save_trust_config(config)
        return f"已删除自主学习主题：{removed}\n\n" + format_self_study_topics(config)
    if message.startswith("/self_study_topic "):
        topics_str = message.removeprefix("/self_study_topic ").strip()
        if not topics_str:
            return "用法：/self_study_topic 主题1,主题2,主题3"
        topics = _parse_topic_list(topics_str)
        if not topics:
            return "学习主题不能为空。"
        config = _load_trust_config()
        config["self_study_topics"] = topics
        _save_trust_config(config)
        return "已批量设置自主学习主题。\n\n" + format_self_study_topics(config)
    if message.startswith("/self_study_min "):
        try:
            min_hours = float(message.removeprefix("/self_study_min ").strip())
        except ValueError:
            return "用法：/self_study_min <小时数>（最小1，最大24）"
        min_hours = max(1, min(24, min_hours))
        config = _load_trust_config()
        config["self_study_min_interval_hours"] = min_hours
        if config.get("self_study_interval_hours", 6) < min_hours:
            config["self_study_interval_hours"] = min_hours
        if config.get("self_study_max_interval_hours", 24) < min_hours:
            config["self_study_max_interval_hours"] = min_hours
        _save_trust_config(config)
        return f"已设置最低学习间隔为 {min_hours} 小时，AI不会低于此间隔学习。"
    if message.startswith("/self_study_max "):
        try:
            max_hours = float(message.removeprefix("/self_study_max ").strip())
        except ValueError:
            return "用法：/self_study_max <小时数>（最小1，最大48）"
        max_hours = max(1, min(48, max_hours))
        config = _load_trust_config()
        config["self_study_max_interval_hours"] = max_hours
        if config.get("self_study_interval_hours", 6) > max_hours:
            config["self_study_interval_hours"] = max_hours
        if config.get("self_study_min_interval_hours", 1) > max_hours:
            config["self_study_min_interval_hours"] = max_hours
        _save_trust_config(config)
        return f"已设置最大学习间隔为 {max_hours} 小时，AI不会超过此间隔学习。"
    return None


_self_study_thread = None
_self_study_running = False


def _self_study_worker():
    """Background worker for AI self-study."""
    global _self_study_running
    _self_study_running = True
    last_interval = None

    while _self_study_running:
        try:
            config = _load_trust_config()
            if not config.get("enabled") or not config.get("self_study_enabled"):
                time.sleep(60)
                continue

            if not is_network_available():
                time.sleep(60)
                continue

            if config.get("wifi_only", True) and not is_wifi_connected():
                time.sleep(60)
                continue

            topics = _self_study_topics(config) or ["科技新闻", "人工智能"]
            import random
            topic = random.choice(topics)

            query = f"最新{topic}"
            result = learn_from_web(query)
            
            quality_score = 0
            if result.get("ok"):
                sources = result.get("sources", [])
                trust_sum = sum(s.get("trust_score", 0) for s in sources)
                quality_score = trust_sum / len(sources) if sources else 0
                
                try:
                    from companion_growth import load_growth, save_growth
                    store = load_growth()
                    notes = store["personality"].setdefault("growth_notes", [])
                    notes.append({
                        "time": int(time.time()),
                        "text": f"自主学习「{result['query']}」，来源：{', '.join(s['domain'] for s in result['sources'])}",
                    })
                    store["personality"]["growth_notes"] = notes[-40:]
                    save_growth(store)
                except Exception:
                    pass

            min_interval = config.get("self_study_min_interval_hours", 1)
            max_interval = config.get("self_study_max_interval_hours", 24)
            base_interval = config.get("self_study_interval_hours", 6)

            if last_interval is None:
                adjusted_interval = base_interval
            else:
                adjusted_interval = last_interval

            if quality_score > 70:
                adjusted_interval = max(min_interval, adjusted_interval * 0.8)
            elif quality_score < 30:
                adjusted_interval = min(max_interval, adjusted_interval * 1.2)

            adjusted_interval = max(min_interval, min(max_interval, adjusted_interval))

            jitter = random.uniform(-0.3, 0.3)
            final_interval = max(min_interval, min(max_interval, adjusted_interval * (1 + jitter)))

            last_interval = final_interval
            interval_seconds = final_interval * 3600

            try:
                from companion_growth import load_growth, save_growth
                store = load_growth()
                notes = store["personality"].setdefault("growth_notes", [])
                notes.append({
                    "time": int(time.time()),
                    "text": f"学习间隔调整为 {round(final_interval, 1)} 小时（质量评分: {round(quality_score, 0)}）",
                })
                store["personality"]["growth_notes"] = notes[-40:]
                save_growth(store)
            except Exception:
                pass

            time.sleep(interval_seconds)

        except Exception:
            time.sleep(60)


def _start_self_study_thread():
    """Start the background self-study thread."""
    global _self_study_thread
    if _self_study_thread is None or not _self_study_thread.is_alive():
        import threading
        _self_study_thread = threading.Thread(
            target=_self_study_worker,
            daemon=True,
            name="WebLearner-SelfStudy",
        )
        _self_study_thread.start()


def _stop_self_study_thread():
    """Stop the background self-study thread."""
    global _self_study_running
    _self_study_running = False


def start_web_learner():
    """Initialize web learner module."""
    _start_self_study_thread()
