from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing image path"}))
        return 2
    image_path = sys.argv[1]
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception:
            from rapidocr import RapidOCR

        engine = RapidOCR()
        result, _elapsed = engine(image_path)
        lines = []
        for item in result or []:
            if len(item) >= 2:
                text = item[1]
                score = item[2] if len(item) >= 3 else None
                lines.append({"text": str(text), "score": float(score) if score is not None else None})
        print(json.dumps({"ok": True, "lines": lines}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
