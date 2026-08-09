from __future__ import annotations

import re
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import DEVELOPMENT_FERNET_KEY, get_settings


settings = get_settings()
def _cipher() -> Fernet:
    key = settings.data_encryption_key or DEVELOPMENT_FERNET_KEY
    return Fernet(key.encode("utf-8"))


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return (stem or "upload")[:180]


def encrypted_upload_path(original_filename: str) -> Path:
    # The original name is encrypted in the database; the filesystem object
    # remains opaque so directory listings do not disclose candidate data.
    _ = original_filename
    token = secrets.token_hex(20)
    return settings.data_dir / "uploads" / f"{token}.bin"


def encrypt_to_file(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_cipher().encrypt(data))
    destination.chmod(0o640)


def decrypt_from_file(path: Path) -> bytes:
    try:
        return _cipher().decrypt(path.read_bytes())
    except (OSError, InvalidToken) as exc:
        raise ValueError("无法读取加密文件。") from exc


def encrypt_bytes(data: bytes) -> bytes:
    return _cipher().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    try:
        return _cipher().decrypt(data)
    except InvalidToken as exc:
        raise ValueError("备份文件无法解密。") from exc
