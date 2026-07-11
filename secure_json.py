"""Small authenticated local JSON store.

The goal here is local tamper/wrong-key detection for sensitive companion data.
If an encrypted file cannot be authenticated with the configured key, callers
can clear it by rewriting the default store.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path


ALG = "sha256-stream-hmac-v1"


def load_or_create_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        try:
            key = bytes.fromhex(text)
        except ValueError:
            key = b""
        if len(key) >= 32:
            return key[:32]
    key = secrets.token_bytes(32)
    path.write_text(key.hex(), encoding="utf-8")
    return key


def _keys(master: bytes) -> tuple[bytes, bytes]:
    enc_key = hashlib.sha256(master + b":enc").digest()
    mac_key = hashlib.sha256(master + b":mac").digest()
    return enc_key, mac_key


def _stream_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))


def encrypt_json(data: dict, key: bytes) -> dict:
    enc_key, mac_key = _keys(key)
    nonce = secrets.token_bytes(16)
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cipher = _stream_xor(plain, enc_key, nonce)
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    cipher_b64 = base64.b64encode(cipher).decode("ascii")
    mac = hmac.new(mac_key, (ALG + "|" + nonce_b64 + "|" + cipher_b64).encode("utf-8"), hashlib.sha256).hexdigest()
    return {"encrypted": True, "alg": ALG, "nonce": nonce_b64, "payload": cipher_b64, "mac": mac}


def decrypt_json(envelope: dict, key: bytes) -> dict:
    if not envelope.get("encrypted") or envelope.get("alg") != ALG:
        raise ValueError("not an encrypted JSON envelope")
    enc_key, mac_key = _keys(key)
    nonce_b64 = str(envelope.get("nonce", ""))
    cipher_b64 = str(envelope.get("payload", ""))
    expected = hmac.new(mac_key, (ALG + "|" + nonce_b64 + "|" + cipher_b64).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(envelope.get("mac", ""))):
        raise ValueError("encrypted JSON authentication failed")
    nonce = base64.b64decode(nonce_b64.encode("ascii"))
    cipher = base64.b64decode(cipher_b64.encode("ascii"))
    plain = _stream_xor(cipher, enc_key, nonce)
    return json.loads(plain.decode("utf-8"))


def read_secure_json(path: Path, key_path: Path, default: dict) -> tuple[dict, str]:
    """Read encrypted JSON.

    Returns (data, state), where state is one of:
    - missing: file was absent
    - encrypted: decrypted successfully
    - plaintext: legacy plaintext was read and should be migrated
    - reset: encrypted file existed but failed authentication/decoding
    """
    if not path.exists():
        return dict(default), "missing"
    key = load_or_create_key(key_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default), "reset"
    if isinstance(raw, dict) and raw.get("encrypted"):
        try:
            return decrypt_json(raw, key), "encrypted"
        except Exception:
            return dict(default), "reset"
    if isinstance(raw, dict):
        return raw, "plaintext"
    return dict(default), "reset"


def write_secure_json(path: Path, key_path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = load_or_create_key(key_path)
    envelope = encrypt_json(data, key)
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
