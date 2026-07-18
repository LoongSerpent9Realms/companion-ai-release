"""JSON worker for Tiny LLM operations in Companion's component runtime."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
# Append to the END of sys.path so the venv's site-packages (cp312 wheels)
# take priority over _internal/ (which contains cp314 wheels from the
# PyInstaller build).  Putting _internal first would make torch load the
# wrong numpy and trigger "python314.dll conflicts with this version".
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        action = request.get("action")
        architecture = str(request.get("attention_type") or "dense")
        import tiny_llm

        # Library diagnostics are useful interactively but would corrupt this
        # process's single JSON response, so keep them out of stdout.
        with contextlib.redirect_stdout(io.StringIO()):
            if action == "train":
                result = tiny_llm.train_tiny_llm(
                    texts=list(request.get("texts") or []),
                    epochs=int(request.get("epochs", 3)),
                    batch_size=int(request.get("batch_size", 32)),
                    lr=float(request.get("lr", 0.001)),
                    max_seq_len=int(request.get("max_seq_len", 128)),
                    config=request.get("config"),
                    attention_type=architecture,
                    output_dir=request.get("output_dir"),
                )
            elif action == "evaluate":
                result = tiny_llm.evaluate_tiny_llm(
                    texts=list(request.get("texts") or []),
                    attention_type=architecture,
                    model_dir=request.get("model_dir"),
                )
            elif action in {"load", "chat"}:
                inference = tiny_llm.TinyLLMInference(architecture, request.get("model_dir"))
                loaded = inference.load()
                if not loaded.get("ok"):
                    result = loaded
                elif action == "load":
                    result = loaded
                else:
                    result = {"ok": True, "reply": inference.chat(str(request.get("message") or ""), request.get("history"))}
            else:
                result = {"ok": False, "error": "unknown worker action"}
    except Exception as exc:
        result = {"ok": False, "error": f"runtime worker failed: {exc}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
