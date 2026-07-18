"""Local, evidence-gated growth loop for Companion AI.

The module deliberately separates experience, trainable examples, staged model
artifacts and the active model.  It never uses a model's unverified output as
training truth and does not require a cloud reviewer.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Any

from _paths import data_dir, module_root
from sensitive_json import read_sensitive_json, write_sensitive_json


ROOT = module_root(__file__)
DATA_DIR = data_dir(ROOT)
GROWTH_DIR = DATA_DIR / "growth_loop"
EXPERIENCE_FILE = GROWTH_DIR / "experiences.json"
STATE_FILE = GROWTH_DIR / "model_versions.json"
BENCHMARK_FILE = GROWTH_DIR / "benchmarks.json"
CANDIDATE_DIR = GROWTH_DIR / "candidates"
VERSION_DIR = GROWTH_DIR / "versions"
TRAINING_FILE = DATA_DIR / "training.json"

VERIFIED_EVIDENCE = {"human", "tool_success", "test_pass", "user_approved", "local_rule"}
CORE_SOURCES = ("teach:", "correction", "audit_human_", "legacy:manual", "legacy:correction")
DEFAULT_MAX_TRAINING_SAMPLES = 256


def _now() -> int:
    return int(time.time())


def _load_experiences() -> dict[str, Any]:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    return read_sensitive_json(EXPERIENCE_FILE, {"experiences": []})


def _save_experiences(data: dict[str, Any]) -> None:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(EXPERIENCE_FILE, data)


def _load_state() -> dict[str, Any]:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    return read_sensitive_json(STATE_FILE, {"active_version": "", "previous_version": "", "versions": []})


def _save_state(data: dict[str, Any]) -> None:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(STATE_FILE, data)


def _load_benchmarks() -> dict[str, Any]:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    return read_sensitive_json(BENCHMARK_FILE, {"benchmarks": []})


def _save_benchmarks(data: dict[str, Any]) -> None:
    GROWTH_DIR.mkdir(parents=True, exist_ok=True)
    write_sensitive_json(BENCHMARK_FILE, data)


def list_benchmarks() -> list[dict[str, Any]]:
    return list(_load_benchmarks().get("benchmarks", []))


def add_benchmark(prompt: str, expected_keywords: str | list[str], title: str = "", rule: str = "keywords") -> dict[str, Any]:
    """Add a user-owned frozen evaluation question; it is never trainable."""
    prompt = str(prompt).strip()
    keywords = expected_keywords.split(",") if isinstance(expected_keywords, str) else expected_keywords
    keywords = [str(word).strip() for word in keywords if str(word).strip()]
    rule = str(rule or "keywords").lower()
    if rule not in {"keywords", "regex", "exact", "max_length", "manual"}:
        return {"ok": False, "error": "未知评测规则。"}
    if not prompt or (rule != "manual" and not keywords):
        return {"ok": False, "error": "评测题需要问题和期望值。"}
    data = _load_benchmarks()
    item_id = hashlib.sha1(f"{prompt}\n{'|'.join(keywords)}".encode("utf-8")).hexdigest()[:10]
    item = {"id": item_id, "title": str(title).strip() or prompt[:32], "prompt": prompt, "expected_keywords": keywords, "rule": rule, "manual_pass": False, "created_at": _now()}
    data["benchmarks"] = [row for row in data["benchmarks"] if row.get("id") != item_id]
    data["benchmarks"].append(item)
    _save_benchmarks(data)
    return {"ok": True, "benchmark": item}


def remove_benchmark(benchmark_id: str) -> bool:
    data = _load_benchmarks()
    before = len(data["benchmarks"])
    data["benchmarks"] = [row for row in data["benchmarks"] if row.get("id") != benchmark_id.strip()]
    if len(data["benchmarks"]) == before:
        return False
    _save_benchmarks(data)
    return True


def update_benchmark(benchmark_id: str, prompt: str, expected_keywords: str | list[str], rule: str = "keywords", manual_pass: bool | None = None) -> dict[str, Any]:
    """Update a frozen evaluation question without turning it into training data."""
    prompt = str(prompt).strip()
    keywords = expected_keywords.split(",") if isinstance(expected_keywords, str) else expected_keywords
    keywords = [str(word).strip() for word in keywords if str(word).strip()]
    rule = str(rule or "keywords").lower()
    if rule not in {"keywords", "regex", "exact", "max_length", "manual"}:
        return {"ok": False, "error": "未知评测规则。"}
    if not prompt or (rule != "manual" and not keywords):
        return {"ok": False, "error": "评测题需要问题和期望值。"}
    data = _load_benchmarks()
    for item in data["benchmarks"]:
        if item.get("id") == benchmark_id.strip():
            item.update({"prompt": prompt, "title": prompt[:32], "expected_keywords": keywords, "rule": rule, "updated_at": _now()})
            if manual_pass is not None:
                item["manual_pass"] = bool(manual_pass)
            _save_benchmarks(data)
            return {"ok": True, "benchmark": item}
    return {"ok": False, "error": "未找到该评测 ID。"}


def evaluate_benchmarks(model_dir: str | Path | None = None, attention_type: str = "dense") -> dict[str, Any]:
    """Score a checkpoint on user-owned frozen prompts using keyword criteria."""
    benchmarks = list_benchmarks()
    if not benchmarks:
        return {"ok": False, "error": "尚未添加固定能力评测题。", "total": 0, "score": 0}
    from tiny_llm import _run_runtime_worker
    details: list[dict[str, Any]] = []
    score = 0
    for item in benchmarks:
        result = _run_runtime_worker({
            "action": "chat", "attention_type": attention_type, "model_dir": str(model_dir) if model_dir else None,
            "message": item["prompt"], "history": [],
        }, timeout=120)
        reply = str(result.get("reply") or "")
        expected = [str(word) for word in item.get("expected_keywords", [])]
        rule = str(item.get("rule") or "keywords")
        lowered = reply.lower()
        if rule == "regex":
            try:
                passed = bool(result.get("ok")) and all(re.search(pattern, reply, re.IGNORECASE) is not None for pattern in expected)
            except re.error:
                passed = False
        elif rule == "exact":
            passed = bool(result.get("ok")) and bool(expected) and reply.strip() == expected[0].strip()
        elif rule == "max_length":
            try:
                passed = bool(result.get("ok")) and len(re.sub(r"\s+", "", reply)) <= int(expected[0])
            except (ValueError, IndexError):
                passed = False
        elif rule == "manual":
            passed = bool(item.get("manual_pass"))
        else:
            passed = bool(result.get("ok")) and all(word.lower() in lowered for word in expected)
        score += int(passed)
        details.append({"id": item["id"], "title": item["title"], "passed": passed, "reply": reply[:300], "expected_keywords": item["expected_keywords"], "rule": rule})
    return {"ok": True, "total": len(benchmarks), "score": score, "details": details}


def _experience_id(prompt: str, response: str, source: str) -> str:
    raw = f"{prompt.strip()}\n{response.strip()}\n{source.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def record_experience(
    prompt: str,
    response: str,
    *,
    source: str = "local",
    evidence_type: str = "",
    reward: float = 0.0,
    evidence: str = "",
) -> dict[str, Any]:
    """Persist one experience. Only verified, positive records are trainable."""
    prompt, response = str(prompt).strip(), str(response).strip()
    if not prompt or not response:
        return {"ok": False, "error": "经验需要完整的输入和回答"}
    experience_id = _experience_id(prompt, response, source)
    data = _load_experiences()
    for item in data["experiences"]:
        if item.get("id") == experience_id:
            return {"ok": True, "created": False, "experience": item}
    verified = evidence_type in VERIFIED_EVIDENCE
    item = {
        "id": experience_id,
        "time": _now(),
        "prompt": prompt,
        "response": response,
        "source": source,
        "evidence_type": evidence_type,
        "evidence": str(evidence)[:1200],
        "reward": float(reward),
        "verified": verified,
    }
    data["experiences"].append(item)
    _save_experiences(data)
    return {"ok": True, "created": True, "experience": item}


def ingest_legacy_training() -> int:
    """Import accepted existing teaching samples once, with explicit evidence."""
    if not TRAINING_FILE.exists():
        return 0
    training = read_sensitive_json(TRAINING_FILE, {"examples": []})
    count = 0
    for item in training.get("examples", []):
        if float(item.get("rating", 0) or 0) <= 0:
            continue
        source = str(item.get("source") or "legacy")
        evidence_type = "human" if source in {"manual", "audit_human_approve", "audit_human_correct"} else "user_approved"
        result = record_experience(
            str(item.get("prompt") or ""), str(item.get("response") or ""),
            source=f"legacy:{source}", evidence_type=evidence_type, reward=1.0,
            evidence="已接受的既有训练样本",
        )
        count += int(bool(result.get("created")))
    return count


def eligible_examples() -> list[dict[str, Any]]:
    """Return deduplicated, evidence-gated examples suitable for model training."""
    ingest_legacy_training()
    chosen: dict[str, dict[str, Any]] = {}
    for item in _load_experiences().get("experiences", []):
        if not item.get("verified") or float(item.get("reward", 0)) <= 0:
            continue
        prompt, response = str(item.get("prompt") or "").strip(), str(item.get("response") or "").strip()
        if prompt and response:
            chosen.setdefault(f"{prompt}\n{response}", item)
    return list(chosen.values())


def list_experiences(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent local experiences for review without exposing unrelated data."""
    rows = list(_load_experiences().get("experiences", []))
    rows.sort(key=lambda item: int(item.get("time") or 0), reverse=True)
    return rows[:max(1, min(int(limit), 500))]


def update_experience(experience_id: str, *, reward: float | None = None, verified: bool | None = None, response: str | None = None) -> dict[str, Any]:
    data = _load_experiences()
    for item in data["experiences"]:
        if item.get("id") != str(experience_id).strip():
            continue
        if reward is not None:
            item["reward"] = float(reward)
        if verified is not None:
            item["verified"] = bool(verified)
            if verified and not item.get("evidence_type"):
                item["evidence_type"] = "human"
        if response is not None and str(response).strip():
            item["response"] = str(response).strip()
        item["updated_at"] = _now()
        _save_experiences(data)
        return {"ok": True, "experience": item}
    return {"ok": False, "error": "未找到该经验。"}


def delete_experience(experience_id: str) -> bool:
    data = _load_experiences()
    before = len(data["experiences"])
    data["experiences"] = [item for item in data["experiences"] if item.get("id") != str(experience_id).strip()]
    if len(data["experiences"]) == before:
        return False
    _save_experiences(data)
    return True


def _split_examples(examples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train, held_out = [], []
    for example in examples:
        # Stable split: an experience never moves from evaluation into training.
        bucket = int(str(example["id"])[-2:], 16) % 5
        (held_out if bucket == 0 else train).append(example)
    if not held_out and len(train) >= 5:
        held_out.append(train.pop())
    return train, held_out


def _is_core_experience(example: dict[str, Any]) -> bool:
    source = str(example.get("source") or "")
    return source.startswith(CORE_SOURCES)


def select_replay_examples(examples: list[dict[str, Any]], max_samples: int = DEFAULT_MAX_TRAINING_SAMPLES) -> tuple[list[dict[str, Any]], int]:
    """Keep core behaviour and a stable spread of older successes in each run."""
    if len(examples) <= max_samples:
        return list(examples), sum(1 for item in examples if _is_core_experience(item))
    core = [item for item in examples if _is_core_experience(item)]
    others = [item for item in examples if not _is_core_experience(item)]
    # Core examples represent explicit personality, correction and safety
    # choices.  Keep them first; the remaining capacity is filled by a mix of
    # recent data and stable hash-selected history, not just the latest chats.
    selected = core[:max_samples]
    capacity = max_samples - len(selected)
    if capacity > 0:
        recent_count = max(1, capacity // 2)
        recent = sorted(others, key=lambda item: int(item.get("time") or 0), reverse=True)[:recent_count]
        selected.extend(recent)
        used = {item["id"] for item in selected}
        historical = sorted(
            (item for item in others if item["id"] not in used),
            key=lambda item: hashlib.sha256(str(item["id"]).encode("utf-8")).hexdigest(),
        )
        selected.extend(historical[:max(0, max_samples - len(selected))])
    return selected, sum(1 for item in selected if _is_core_experience(item))


def _active_artifacts(attention_type: str) -> list[Path]:
    from tiny_llm import CONFIG_FILE, MODEL_FILE, PANGU_PI_CONFIG_FILE, PANGU_PI_MODEL_FILE, PANGU_PI_VOCAB_FILE, SPARSE_CONFIG_FILE, SPARSE_MODEL_FILE, SPARSE_VOCAB_FILE, VOCAB_FILE
    if attention_type == "pangu_pi_sparse":
        return [PANGU_PI_MODEL_FILE, PANGU_PI_VOCAB_FILE, PANGU_PI_CONFIG_FILE]
    if attention_type == "sparse":
        return [SPARSE_MODEL_FILE, SPARSE_VOCAB_FILE, SPARSE_CONFIG_FILE]
    return [MODEL_FILE, VOCAB_FILE, CONFIG_FILE]


def _version_id() -> str:
    return f"tiny-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"


def _snapshot_active(version_id: str, attention_type: str) -> str:
    sources = _active_artifacts(attention_type)
    if not all(path.exists() for path in sources):
        return ""
    target = VERSION_DIR / version_id
    target.mkdir(parents=True, exist_ok=True)
    for source, name in zip(sources, ("model.pt", "vocab.json", "config.json")):
        shutil.copy2(source, target / name)
    return str(target)


def _reload_active_runtime() -> dict[str, Any]:
    """Make the already-running chat process use the newly activated files."""
    try:
        from hybrid_chat import reload_tiny_models
        return reload_tiny_models()
    except Exception as exc:
        # The model files remain valid; a later app start will load them.
        return {"ok": False, "error": str(exc)}


def _activate(candidate_dir: Path, attention_type: str, record: dict[str, Any]) -> None:
    state = _load_state()
    old_id = str(state.get("active_version") or "")
    snapshot_id = _version_id()
    if _snapshot_active(snapshot_id, attention_type):
        state["versions"].append({"id": snapshot_id, "path": str(VERSION_DIR / snapshot_id), "status": "archived", "attention_type": attention_type})
        state["previous_version"] = snapshot_id
    targets = _active_artifacts(attention_type)
    for target, name in zip(targets, ("model.pt", "vocab.json", "config.json")):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_dir / name, target)
    record["status"] = "active"
    record["activated_at"] = _now()
    record["runtime_reload"] = _reload_active_runtime()
    state["active_version"] = record["id"]
    state["versions"].append(record)
    _save_state(state)


def train_candidate(epochs: int = 3, attention_type: str = "dense", max_validation_loss: float = 9.0, cancel_check: Any = None, progress_callback: Any = None) -> dict[str, Any]:
    """Train a staged candidate, locally evaluate it, then promote only if safe."""
    def progress(stage: str, message: str, percent: int) -> None:
        if callable(progress_callback):
            progress_callback(stage, message, max(0, min(100, int(percent))))

    progress("prepare", "正在校验已批准的本地经验并固定训练/留出划分。", 5)
    examples = eligible_examples()
    if len(examples) < 4:
        return {"ok": False, "error": "至少需要 4 条带正向验证证据的经验，当前不足。", "eligible": len(examples)}
    train, held_out = _split_examples(examples)
    if len(train) < 3 or not held_out:
        return {"ok": False, "error": "需要至少 3 条训练经验和 1 条固定留出评测经验。"}
    candidate_id = _version_id()
    candidate_dir = CANDIDATE_DIR / candidate_id
    replay_train, replay_core_count = select_replay_examples(train)
    texts = [f"用户：{row['prompt']}\n助手：{row['response']}" for row in replay_train]
    eval_texts = [f"用户：{row['prompt']}\n助手：{row['response']}" for row in held_out]
    from tiny_llm import evaluate_tiny_llm_in_runtime, train_tiny_llm_in_runtime
    progress("train", f"正在训练候选 TinyLLM（{len(replay_train)} 条训练、{len(held_out)} 条留出）。", 20)
    trained = train_tiny_llm_in_runtime(texts=texts, epochs=max(1, int(epochs)), attention_type=attention_type, output_dir=str(candidate_dir))
    if not trained.get("ok"):
        return {"ok": False, "stage": "train", **trained}
    if callable(cancel_check) and cancel_check():
        return {"ok": False, "cancelled": True, "error": "训练已取消；候选模型未进入评测或激活。", "train": trained}
    progress("heldout", "正在检查固定留出经验，防止只记住训练样本。", 65)
    evaluated = evaluate_tiny_llm_in_runtime(texts=eval_texts, attention_type=attention_type, model_dir=str(candidate_dir))
    validation_loss = float(evaluated.get("loss", float("inf"))) if evaluated.get("ok") else float("inf")
    progress("benchmark", "正在运行用户维护的固定能力评测集。", 78)
    candidate_benchmarks = evaluate_benchmarks(candidate_dir, attention_type)
    active_exists = all(path.exists() for path in _active_artifacts(attention_type))
    baseline_benchmarks = evaluate_benchmarks(None, attention_type) if active_exists else {"ok": True, "score": 0, "total": candidate_benchmarks.get("total", 0), "details": []}
    benchmark_passed = bool(candidate_benchmarks.get("ok")) and int(candidate_benchmarks.get("score", 0)) >= int(baseline_benchmarks.get("score", 0))
    accepted = bool(evaluated.get("ok")) and validation_loss <= float(max_validation_loss) and benchmark_passed
    record = {
        "id": candidate_id, "path": str(candidate_dir), "status": "rejected", "attention_type": attention_type,
        "created_at": _now(), "train_samples": len(replay_train), "validation_samples": len(held_out),
        "replay_core_samples": replay_core_count, "replay_pool_samples": len(train),
        "train_loss": trained.get("final_loss"), "validation_loss": evaluated.get("loss"),
        "max_validation_loss": max_validation_loss,
        "benchmark_score": candidate_benchmarks.get("score"), "benchmark_total": candidate_benchmarks.get("total"),
        "baseline_benchmark_score": baseline_benchmarks.get("score"),
    }
    if accepted:
        progress("promote", "评测通过，正在安全激活候选模型并保留可回滚版本。", 92)
        _activate(candidate_dir, attention_type, record)
    else:
        state = _load_state()
        state["versions"].append(record)
        _save_state(state)
    progress("done", "候选模型已激活。" if accepted else "候选未通过，当前模型保持不变。", 100)
    return {"ok": accepted, "promoted": accepted, "candidate": record, "train": trained, "evaluation": evaluated, "benchmarks": candidate_benchmarks, "baseline_benchmarks": baseline_benchmarks}


def rollback_active_model() -> dict[str, Any]:
    state = _load_state()
    version_id = str(state.get("previous_version") or "")
    version = next((item for item in state.get("versions", []) if item.get("id") == version_id), None)
    if not version:
        return {"ok": False, "error": "没有可回滚的已归档模型版本。"}
    source = Path(str(version.get("path") or ""))
    if not all((source / name).exists() for name in ("model.pt", "vocab.json", "config.json")):
        return {"ok": False, "error": "归档模型文件不完整，无法回滚。"}
    attention_type = str(version.get("attention_type") or "dense")
    for target, name in zip(_active_artifacts(attention_type), ("model.pt", "vocab.json", "config.json")):
        shutil.copy2(source / name, target)
    runtime_reload = _reload_active_runtime()
    state["active_version"], state["previous_version"] = version_id, ""
    _save_state(state)
    return {"ok": True, "active_version": version_id, "runtime_reload": runtime_reload}


def list_model_versions(limit: int = 50) -> list[dict[str, Any]]:
    state = _load_state()
    active_id = str(state.get("active_version") or "")
    rows = list(state.get("versions", []))
    rows.sort(key=lambda item: int(item.get("activated_at") or item.get("created_at") or 0), reverse=True)
    result = []
    seen: set[str] = set()
    for row in rows:
        row_id = str(row.get("id") or "")
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        result.append({**row, "active": row_id == active_id})
    return result[:max(1, min(int(limit), 100))]


def activate_model_version(version_id: str) -> dict[str, Any]:
    """Restore any archived/previously active checked checkpoint by ID."""
    state = _load_state()
    version = next((row for row in state.get("versions", []) if row.get("id") == str(version_id).strip()), None)
    if not version:
        return {"ok": False, "error": "未找到该模型版本。"}
    if version.get("status") == "rejected":
        return {"ok": False, "error": "被评测拒绝的候选模型不能直接激活。"}
    source = Path(str(version.get("path") or ""))
    if not all((source / name).exists() for name in ("model.pt", "vocab.json", "config.json")):
        return {"ok": False, "error": "模型版本文件不完整。"}
    attention_type = str(version.get("attention_type") or "dense")
    snapshot_id = _version_id()
    if _snapshot_active(snapshot_id, attention_type):
        state["versions"].append({"id": snapshot_id, "path": str(VERSION_DIR / snapshot_id), "status": "archived", "attention_type": attention_type, "created_at": _now()})
        state["previous_version"] = snapshot_id
    for target, name in zip(_active_artifacts(attention_type), ("model.pt", "vocab.json", "config.json")):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    state["active_version"] = version["id"]
    _save_state(state)
    return {"ok": True, "active_version": version["id"], "runtime_reload": _reload_active_runtime()}


def growth_status() -> dict[str, Any]:
    state = _load_state()
    examples = eligible_examples()
    train, held_out = _split_examples(examples)
    replay, core_count = select_replay_examples(train)
    rejected = sum(1 for item in state.get("versions", []) if item.get("status") == "rejected")
    return {
        "eligible_experiences": len(examples),
        "replay_samples": len(replay),
        "replay_core_samples": core_count,
        "held_out_samples": len(held_out),
        "active_version": state.get("active_version") or "未通过成长闭环激活",
        "previous_version": state.get("previous_version") or "无",
        "rejected_candidates": rejected,
    }
