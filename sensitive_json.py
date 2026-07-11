"""Encrypted JSON helpers for user-owned sensitive data.

Legacy plaintext JSON is read once and immediately rewritten as an encrypted
envelope, so existing installs migrate without a manual export/import step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from secure_json import read_secure_json, write_secure_json


KEY_NAME = "sensitive.key"


def sensitive_key_path(path: Path) -> Path:
    return path.parent / KEY_NAME


def read_sensitive_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if path.exists() and path.is_dir():
        return dict(default)
    data, state = read_secure_json(path, sensitive_key_path(path), default)
    if state != "encrypted":
        write_secure_json(path, sensitive_key_path(path), data)
    return data


def write_sensitive_json(path: Path, data: dict[str, Any]) -> None:
    write_secure_json(path, sensitive_key_path(path), data)
