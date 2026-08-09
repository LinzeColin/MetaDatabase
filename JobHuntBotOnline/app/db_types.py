from __future__ import annotations

from typing import Any

from sqlalchemy import Text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

from app.services.security import decrypt_bytes, encrypt_bytes


ENCRYPTED_PREFIX = "enc:v1:"


def seal_text(value: str) -> str:
    """Return an authenticated encrypted token for one plaintext string."""
    token = encrypt_bytes(value.encode("utf-8")).decode("ascii")
    return ENCRYPTED_PREFIX + token


def unseal_text(value: str) -> str:
    """Decrypt a token, while allowing controlled reads of legacy plaintext."""
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    token = value.removeprefix(ENCRYPTED_PREFIX).encode("ascii")
    try:
        return decrypt_bytes(token).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("加密结构化字段无法读取，请检查数据恢复密钥。") from exc


def seal_legacy_value(value: Any) -> str:
    """Encrypt a raw legacy value unless it is already a current token."""
    text = str(value)
    if text.startswith(ENCRYPTED_PREFIX):
        return text
    return seal_text(text)


class EncryptedText(TypeDecorator[str]):
    """Store sensitive text as an authenticated encrypted token.

    Existing unprefixed values remain readable for a controlled migration;
    every ORM write uses the encrypted representation.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str:
        if value is None or value == "":
            return ""
        return seal_text(str(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> str:
        if value is None or value == "":
            return ""
        return unseal_text(str(value))


class EncryptedBoolean(TypeDecorator[bool]):
    """Store an optional boolean as encrypted text; read legacy SQLite booleans."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: bool | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return seal_text("true" if bool(value) else "false")

    def process_result_value(self, value: Any, dialect: Dialect) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        text = unseal_text(str(value)).strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
        raise ValueError("加密布尔字段内容无效。")


class EncryptedInteger(TypeDecorator[int]):
    """Store an optional integer as encrypted text; read legacy SQLite integers."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: int | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return seal_text(str(int(value)))

    def process_result_value(self, value: Any, dialect: Dialect) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value
        try:
            return int(unseal_text(str(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError("加密整数段内容无效。") from exc
