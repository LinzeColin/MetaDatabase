from __future__ import annotations

import hashlib
import json
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .errors import EFSError

MAX_DECIMAL_DIGITS = 48
MAX_DECIMAL_ABS = Decimal("1e18")
MIN_NONZERO_DECIMAL_ABS = Decimal("1e-18")
MAX_INTEGER_ABS = 10**18
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 20_000
MAX_STRING_BYTES = 16_384
MAX_KEY_BYTES = 256
MAX_CONTAINER_ITEMS = 4_096


def _pairs_hook(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    pairs = list(pairs)
    if len(pairs) > MAX_CONTAINER_ITEMS:
        raise EFSError("RESOURCE_LIMIT", "JSON object exceeds item limit")
    result: dict[str, Any] = {}
    seen_normalized: set[str] = set()
    for key, value in pairs:
        if not isinstance(key, str):
            raise EFSError("CONTRACT_INVALID", "JSON object key must be a string")
        normalized = unicodedata.normalize("NFC", key)
        if len(normalized.encode("utf-8")) > MAX_KEY_BYTES:
            raise EFSError("RESOURCE_LIMIT", "JSON object key exceeds byte limit")
        if normalized in seen_normalized:
            raise EFSError("CONTRACT_INVALID", f"duplicate or Unicode-equivalent JSON key: {key}")
        seen_normalized.add(normalized)
        result[normalized] = value
    return result


def _reject_constant(value: str) -> None:
    raise EFSError("CONTRACT_INVALID", f"non-finite JSON number is forbidden: {value}")


def _validate_structure(value: Any) -> None:
    nodes = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise EFSError("RESOURCE_LIMIT", "JSON structure exceeds node limit")
        if depth > MAX_JSON_DEPTH:
            raise EFSError("RESOURCE_LIMIT", "JSON structure exceeds depth limit")
        if isinstance(item, dict):
            if len(item) > MAX_CONTAINER_ITEMS:
                raise EFSError("RESOURCE_LIMIT", "JSON object exceeds item limit")
            for key, child in item.items():
                if len(key.encode("utf-8")) > MAX_KEY_BYTES:
                    raise EFSError("RESOURCE_LIMIT", "JSON object key exceeds byte limit")
                walk(child, depth + 1)
            return
        if isinstance(item, list):
            if len(item) > MAX_CONTAINER_ITEMS:
                raise EFSError("RESOURCE_LIMIT", "JSON array exceeds item limit")
            for child in item:
                walk(child, depth + 1)
            return
        if isinstance(item, str):
            if len(item.encode("utf-8")) > MAX_STRING_BYTES:
                raise EFSError("RESOURCE_LIMIT", "JSON string exceeds byte limit")
            return
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, int):
            if abs(item) > MAX_INTEGER_ABS:
                raise EFSError("RESOURCE_LIMIT", "JSON integer exceeds magnitude limit")
            return
        if isinstance(item, Decimal):
            decimal_from(item, "JSON number")
            return
        raise EFSError("CONTRACT_INVALID", f"unsupported JSON type: {type(item).__name__}")

    walk(value, 0)


def strict_json_loads(raw: str | bytes, *, max_bytes: int = 1_000_000) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > max_bytes:
            raise EFSError("RESOURCE_LIMIT", "JSON payload exceeds byte limit")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise EFSError("CONTRACT_INVALID", "payload must be valid UTF-8") from exc
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > max_bytes:
            raise EFSError("RESOURCE_LIMIT", "JSON payload exceeds byte limit")
        text = raw
    else:
        raise EFSError("CONTRACT_INVALID", "payload must be str or bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_constant,
        )
        _validate_structure(value)
        return value
    except EFSError:
        raise
    except (json.JSONDecodeError, InvalidOperation, RecursionError) as exc:
        raise EFSError("CONTRACT_INVALID", f"invalid JSON: {exc}") from exc


def decimal_from(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise EFSError("CONTRACT_INVALID", f"{field} must not be boolean")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, str):
        if not value or value.strip() != value:
            raise EFSError("CONTRACT_INVALID", f"{field} must be a canonical decimal string")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise EFSError("CONTRACT_INVALID", f"{field} is not a decimal") from exc
    else:
        raise EFSError("CONTRACT_INVALID", f"{field} must be a decimal string")
    if not number.is_finite():
        raise EFSError("CONTRACT_INVALID", f"{field} must be finite")
    digits = len(number.as_tuple().digits)
    if digits > MAX_DECIMAL_DIGITS:
        raise EFSError("RESOURCE_LIMIT", f"{field} exceeds decimal precision limit")
    absolute = abs(number)
    if absolute > MAX_DECIMAL_ABS:
        raise EFSError("RESOURCE_LIMIT", f"{field} exceeds decimal magnitude limit")
    if number != 0 and absolute < MIN_NONZERO_DECIMAL_ABS:
        raise EFSError("RESOURCE_LIMIT", f"{field} exceeds decimal scale limit")
    return number


def canonical_decimal(value: Decimal, places: int = 8) -> str:
    value = decimal_from(value, "canonical decimal")
    quantum = Decimal(1).scaleb(-places)
    try:
        quantized = value.quantize(quantum)
    except InvalidOperation as exc:
        raise EFSError("RESOURCE_LIMIT", "decimal cannot be represented at canonical scale") from exc
    if quantized == 0:
        quantized = abs(quantized)
    return format(quantized, "f")


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        decimal_from(value, "canonical JSON decimal")
        return format(value.normalize(), "f") if value != 0 else "0"
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = unicodedata.normalize("NFC", str(raw_key))
            if key in normalized:
                raise EFSError("CONTRACT_INVALID", f"duplicate canonical key: {key}")
            normalized[key] = _canonicalize(raw_value)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalize(v) for v in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_INTEGER_ABS:
            raise EFSError("RESOURCE_LIMIT", "canonical JSON integer exceeds magnitude limit")
        return value
    raise EFSError("CONTRACT_INVALID", f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _validate_structure(value)
    canonical = _canonicalize(value)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
