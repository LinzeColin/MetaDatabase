from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_self_hash(payload: dict[str, Any], field: str = "receipt_sha256") -> dict[str, Any]:
    body = dict(payload)
    body.pop(field, None)
    body[field] = sha256_bytes(canonical_json_bytes(body))
    return body


def verify_self_hash(payload: dict[str, Any], field: str = "receipt_sha256") -> bool:
    if field not in payload:
        return False
    claimed = payload[field]
    body = dict(payload)
    body.pop(field, None)
    return isinstance(claimed, str) and claimed == sha256_bytes(canonical_json_bytes(body))


def load_self_hashed(path: Path, field: str = "receipt_sha256") -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not verify_self_hash(data, field=field):
        raise ValueError("SELF_HASH_INVALID:" + path.as_posix())
    return data


def atomic_json(path: Path, payload: dict[str, Any], *, self_hash: bool = True, mode: int = 0o600) -> None:
    body = add_self_hash(payload) if self_hash else payload
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
