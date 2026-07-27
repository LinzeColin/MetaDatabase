from __future__ import annotations

import json
import re
from typing import Any

_FORBIDDEN_KEY = re.compile(
    r"(?:authorization|credential|secret|token|cookie|password|api[_-]?key|weread[_-]?key|note|highlight|thought|review[_-]?text|book[_-]?title|author|search[_-]?term|query[_-]?text|raw[_-]?response)",
    re.IGNORECASE,
)
_VALUE_PATTERNS = [
    re.compile(r"wrk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
_ALLOWED_SCALARS = (str, int, float, bool, type(None))


def sanitize_public(value: Any, *, max_depth: int = 8) -> Any:
    return _sanitize(value, depth=0, max_depth=max_depth)


def _sanitize(value: Any, *, depth: int, max_depth: int) -> Any:
    if depth > max_depth:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)[:120]
            if _FORBIDDEN_KEY.search(name):
                result[name] = "[REDACTED]"
            else:
                result[name] = _sanitize(item, depth=depth + 1, max_depth=max_depth)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1, max_depth=max_depth) for item in value[:500]]
    if isinstance(value, _ALLOWED_SCALARS):
        if isinstance(value, str):
            text = value[:4000]
            for pattern in _VALUE_PATTERNS:
                text = pattern.sub("[REDACTED]", text)
            return text
        return value
    return str(value)[:1000]


def assert_public_safe(value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if _FORBIDDEN_KEY.search(encoded):
        # Sanitized objects may retain a forbidden field name, but its value must be redacted.
        for key, item in _walk(value):
            if _FORBIDDEN_KEY.search(key) and item != "[REDACTED]":
                raise ValueError(f"Unsafe public field: {key}")
    for pattern in _VALUE_PATTERNS:
        if pattern.search(encoded):
            raise ValueError("Credential-like value found in public payload")


def _walk(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
