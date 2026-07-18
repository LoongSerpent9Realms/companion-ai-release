"""Structured, local-first long-term memory for Companion AI.

This module keeps the existing three memory buckets compatible while adding
the minimum durable semantics needed for useful recall: provenance, confidence,
entities, conflict history and privacy-aware context cards.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from sensitive_json import read_sensitive_json, write_sensitive_json


BUCKETS = ("profile", "preferences", "facts")
BUCKET_LABELS = {
    "profile": "个人背景",
    "preferences": "偏好",
    "facts": "事实/待办",
}
SOURCE_LABELS = {
    "explicit": "用户主动记住",
    "auto": "聊天自动提取",
    "training": "训练包导入",
    "legacy": "旧版记忆迁移",
}
SENSITIVE_HINTS = (
    "密码", "验证码", "密钥", "token", "api key", "apikey", "secret",
    "身份证", "银行卡", "手机号", "电话", "住址", "地址",
)
_STOPWORDS = {"的", "了", "和", "是", "我", "你", "在", "有", "就", "也", "都", "很", "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on"}

EBBINGHAUS_HALF_LIFE = 14 * 86400
EBBINGHAUS_FORGET_THRESHOLD = 0.05
EBBINGHAUS_MIN_CONFIDENCE = 0.1


def _default_store() -> dict[str, Any]:
    return {"schema_version": 2, "profile": [], "preferences": [], "facts": []}


def _clean(text: object, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in SENSITIVE_HINTS)


def _tokens(text: str) -> set[str]:
    """Chinese characters + bigrams and English words give a cheap local recall signal."""
    lowered = _clean(text).lower()
    tokens = {word for word in re.findall(r"[a-z0-9_]{2,}", lowered) if word not in _STOPWORDS}
    chinese = "".join(char for char in lowered if "\u4e00" <= char <= "\u9fff" and char not in _STOPWORDS)
    tokens.update(chinese)
    tokens.update(chinese[index:index + 2] for index in range(max(0, len(chinese) - 1)))
    return {token for token in tokens if token}


def _extract_entities(text: str, bucket: str) -> list[dict[str, str]]:
    patterns = (
        ("person", r"(?:我叫|叫我|我的名字是)\s*([^，。；;,.！!？?]{1,30})"),
        ("location", r"(?:我住在|住在|居住在)\s*([^，。；;,.！!？?]{1,60})"),
        ("project", r"(?:我的项目是|我的项目|我正在做|我在做)\s*([^，。；;,.！!？?]{2,80})"),
        ("deadline", r"(?:截止|deadline)\s*(?:是|在|：|:)?\s*([^，。；;,.！!？?]{2,40})"),
    )
    entities: list[dict[str, str]] = []
    for entity_type, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _clean(match.group(1), 80)
            if value:
                entities.append({"type": entity_type, "value": value})
    if bucket == "preferences" and any(marker in text for marker in ("用中文", "英文", "简短", "详细", "语气", "回答时", "以后请")):
        entities.append({"type": "communication_preference", "value": _clean(text, 100)})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        marker = (entity["type"], entity["value"])
        if marker not in seen:
            deduped.append(entity)
            seen.add(marker)
    return deduped


def _field_key(text: str, bucket: str) -> str | None:
    """Return a key only for facts that are safely single-valued."""
    lowered = text.lower()
    if re.search(r"(?:我叫|叫我|我的名字是)", text):
        return "identity.name"
    if re.search(r"(?:我住在|住在|居住在)", text):
        return "profile.residence"
    if bucket == "preferences" and ("用中文" in text or "中文回答" in text):
        return "communication.language"
    if bucket == "preferences" and ("用英文" in text or "英文回答" in text):
        return "communication.language"
    if bucket == "preferences" and any(marker in text for marker in ("回答时", "以后请", "语气", "简短", "详细", "别太")):
        return "communication.reply_style"
    if "deadline" in lowered and bucket == "facts":
        return None  # A user can legitimately have several deadlines.
    return None


class MemoryStore:
    """Encrypted local memory store with backward-compatible bucket records."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = read_sensitive_json(self.path, _default_store())
        store, changed = self._normalise_store(raw)
        if changed:
            write_sensitive_json(self.path, store)
        return store

    def save(self, store: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalised, _ = self._normalise_store(store)
        write_sensitive_json(self.path, normalised)

    def active_view(self) -> dict[str, Any]:
        """Return only current records for UI, API and prompt compatibility."""
        store = self.load()
        return {
            "schema_version": store["schema_version"],
            **{bucket: [item for item in store[bucket] if item.get("status") == "active"] for bucket in BUCKETS},
        }

    def _normalise_store(self, raw: object) -> tuple[dict[str, Any], bool]:
        source = raw if isinstance(raw, dict) else {}
        changed = source.get("schema_version") != 2
        store: dict[str, Any] = {"schema_version": 2}
        for bucket in BUCKETS:
            source_items = source.get(bucket, [])
            if not isinstance(source_items, list):
                source_items = []
                changed = True
            items: list[dict[str, Any]] = []
            for item in source_items:
                normalised, item_changed = self._normalise_item(item, bucket)
                changed = changed or item_changed
                if normalised["text"]:
                    items.append(normalised)
            store[bucket] = items
        return store, changed

    def _normalise_item(self, item: object, bucket: str) -> tuple[dict[str, Any], bool]:
        raw = item if isinstance(item, dict) else {"text": item}
        text = _clean(raw.get("text", ""))
        created_at = int(raw.get("created_at") or raw.get("time") or time.time())
        updated_at = int(raw.get("updated_at") or created_at)
        source = str(raw.get("source") or "legacy")
        record_id = str(raw.get("id") or hashlib.sha256(f"{bucket}|{created_at}|{text}".encode("utf-8")).hexdigest()[:16])
        confidence = raw.get("confidence", 0.65 if source == "legacy" else 0.8)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.65
        status = str(raw.get("status") or "active")
        if status not in {"active", "superseded"}:
            status = "active"
        entities = raw.get("entities") if isinstance(raw.get("entities"), list) else _extract_entities(text, bucket)
        supersedes = raw.get("supersedes") if isinstance(raw.get("supersedes"), list) else []
        record = {
            "id": record_id,
            "text": text,
            "time": created_at,  # Existing UI and exports still read this key.
            "created_at": created_at,
            "updated_at": updated_at,
            "source": source,
            "confidence": confidence,
            "entities": entities,
            "field_key": raw.get("field_key") or _field_key(text, bucket),
            "status": status,
            "supersedes": list(supersedes),
            "superseded_by": raw.get("superseded_by"),
            "valid_until": raw.get("valid_until"),
            "sensitive": bool(raw.get("sensitive", _is_sensitive(text))),
        }
        return record, record != raw

    def add(self, text: str, bucket: str = "facts", source: str = "explicit", confidence: float | None = None) -> dict[str, Any]:
        clean_text = _clean(text)
        if not clean_text:
            return {"created": False, "duplicate": False, "record": None, "superseded": 0}
        bucket = bucket if bucket in BUCKETS else "facts"
        store = self.load()
        active = [item for item in store[bucket] if item.get("status") == "active"]
        for item in active:
            if item.get("text") == clean_text:
                return {"created": False, "duplicate": True, "record": item, "superseded": 0}

        now = int(time.time())
        record_confidence = 0.98 if source == "explicit" else (0.65 if source == "auto" else 0.8)
        if confidence is not None:
            record_confidence = confidence
        record = self._normalise_item({
            "text": clean_text,
            "time": now,
            "created_at": now,
            "updated_at": now,
            "source": source,
            "confidence": record_confidence,
        }, bucket)[0]
        key = record.get("field_key")
        superseded: list[dict[str, Any]] = []
        if key:
            for item in active:
                if item.get("field_key") == key:
                    item["status"] = "superseded"
                    item["superseded_by"] = record["id"]
                    item["updated_at"] = now
                    superseded.append(item)
            record["supersedes"] = [item["id"] for item in superseded]
        store[bucket].append(record)
        self.save(store)
        return {"created": True, "duplicate": False, "record": record, "superseded": len(superseded)}

    def forget(self, keyword: str) -> int:
        needle = _clean(keyword).lower()
        if not needle:
            return 0
        store = self.load()
        removed = 0
        for bucket in BUCKETS:
            items = store[bucket]
            kept = [item for item in items if needle not in str(item.get("text", "")).lower()]
            removed += len(items) - len(kept)
            store[bucket] = kept
        self.save(store)
        return removed

    def recall(self, query: str, limit: int = 4, include_sensitive: bool = False) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        now = int(time.time())
        store = self.load()
        scored: list[tuple[float, dict[str, Any]]] = []
        for bucket in BUCKETS:
            for item in store.get(bucket, []):
                if item.get("status") != "active":
                    continue
                if not include_sensitive and item.get("sensitive"):
                    continue
                memory_tokens = _tokens(str(item.get("text", "")))
                overlap = query_tokens & memory_tokens
                if not overlap:
                    continue
                lexical = len(overlap) / max(1, len(query_tokens | memory_tokens))
                phrase_bonus = 0.18 if _clean(query).lower() in str(item.get("text", "")).lower() else 0.0
                age_days = max(0, now - int(item.get("updated_at") or now)) / 86400
                recency = max(0.0, 0.08 - min(age_days, 365) / 365 * 0.08)
                score = lexical + phrase_bonus + recency + float(item.get("confidence") or 0.0) * 0.05
                scored.append((score, {**item, "bucket": bucket, "score": round(score, 4)}))
        scored.sort(key=lambda pair: (-pair[0], -int(pair[1].get("updated_at") or 0)))
        return [item for _, item in scored[:max(1, limit)]]

    def context_for(self, query: str, limit: int = 4) -> str:
        memories = self.recall(query, limit=limit, include_sensitive=False)
        if not memories:
            return ""
        lines = ["[相关长期记忆（本地、可管理）]", "以下是与当前问题相关的稳定信息；若用户当前消息冲突，以当前消息为准。"]
        for item in memories:
            label = BUCKET_LABELS.get(str(item.get("bucket")), "记忆")
            source = SOURCE_LABELS.get(str(item.get("source")), "本地记录")
            lines.append(f"- {label}：{item.get('text', '')}（来源：{source}）")
        return "\n".join(lines)

    def text_summary(self, limit_per_bucket: int = 12) -> str:
        store = self.load()
        lines: list[str] = []
        for bucket in BUCKETS:
            lines.append(f"{BUCKET_LABELS[bucket]}：")
            items = [item for item in store[bucket] if item.get("status") == "active"][-limit_per_bucket:]
            if not items:
                lines.append("- 暂无")
            for item in items:
                source = SOURCE_LABELS.get(str(item.get("source")), "本地记录")
                lines.append(f"- {item.get('text', '')}（{source}）")
        return "\n".join(lines)

    def apply_forgetting_decay(self) -> int:
        store = self.load()
        now = int(time.time())
        changed = False
        forgotten_count = 0

        for bucket in BUCKETS:
            for item in store.get(bucket, []):
                if item.get("status") != "active":
                    continue
                if item.get("sensitive"):
                    continue

                last_touch = max(
                    int(item.get("updated_at", 0)),
                    int(item.get("created_at", 0)),
                )
                age = now - last_touch
                if age < 86400:
                    continue

                decay = 0.5 ** (age / EBBINGHAUS_HALF_LIFE)
                current_conf = float(item.get("confidence", 0.5))
                new_conf = round(current_conf * decay, 4)

                if new_conf != current_conf:
                    item["confidence"] = max(EBBINGHAUS_MIN_CONFIDENCE, new_conf)
                    item["updated_at"] = now
                    changed = True

                if new_conf < EBBINGHAUS_FORGET_THRESHOLD:
                    item["status"] = "forgotten"
                    item["updated_at"] = now
                    forgotten_count += 1
                    changed = True

        if changed:
            self.save(store)
        return forgotten_count

    def touch_memory(self, record_id: str) -> bool:
        store = self.load()
        now = int(time.time())
        found = False

        for bucket in BUCKETS:
            for item in store.get(bucket, []):
                if item.get("id") == record_id:
                    item["updated_at"] = now
                    item["status"] = "active"
                    current_conf = float(item.get("confidence", 0.5))
                    item["confidence"] = min(1.0, current_conf + 0.1)
                    found = True
                    break
            if found:
                break

        if found:
            self.save(store)
        return found

    def get_memory_health(self) -> dict[str, Any]:
        store = self.load()
        now = int(time.time())
        stats = {
            "total": 0,
            "active": 0,
            "forgotten": 0,
            "superseded": 0,
            "avg_confidence": 0.0,
            "oldest_days": 0,
            "youngest_days": 0,
            "buckets": {},
        }
        total_confidence = 0.0
        oldest_time = now
        youngest_time = 0

        for bucket in BUCKETS:
            bucket_stats = {"total": 0, "active": 0, "forgotten": 0, "superseded": 0}
            for item in store.get(bucket, []):
                stats["total"] += 1
                bucket_stats["total"] += 1

                status = item.get("status", "active")
                if status == "active":
                    stats["active"] += 1
                    bucket_stats["active"] += 1
                    total_confidence += float(item.get("confidence", 0.5))
                elif status == "forgotten":
                    stats["forgotten"] += 1
                    bucket_stats["forgotten"] += 1
                elif status == "superseded":
                    stats["superseded"] += 1
                    bucket_stats["superseded"] += 1

                created = int(item.get("created_at", 0))
                if created and created < oldest_time:
                    oldest_time = created
                if created and created > youngest_time:
                    youngest_time = created

            stats["buckets"][bucket] = bucket_stats

        if stats["active"] > 0:
            stats["avg_confidence"] = round(total_confidence / stats["active"], 4)
        if oldest_time < now:
            stats["oldest_days"] = round((now - oldest_time) / 86400, 1)
        if youngest_time > 0:
            stats["youngest_days"] = round((now - youngest_time) / 86400, 1)

        return stats
