"""Exact, S08-scoped successor hashes for legacy ABD receipt replay.

Older signed receipts record source files that were intentionally marked
``SUCCESSOR_EVOLVABLE_SIGNED_INPUTS``.  This module does not weaken those
allow-lists: it supplies only the exact, stage-review-pinned successor hash
for a path that a legacy oracle has already explicitly declared evolvable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .canonical_facts import sha256_file, strict_json_load


MANIFEST_PATH = Path("machine/facts/s08_legacy_receipt_compatibility.json")
COMPATIBILITY_ID = "ABD-S08-LEGACY-RECEIPT-COMPATIBILITY"
PINNED_MANIFEST_SHA256 = "3bed7a52a99769120179d56a6e49b49c59e4f90f1b51d1c004b70bfeefec5454"


def approved_successor_sha256(root: Path, relative: str) -> Optional[str]:
    """Return an exact approved successor hash, or ``None`` fail-closed."""

    manifest_path = root / MANIFEST_PATH
    if PINNED_MANIFEST_SHA256 == "TO_BE_FILLED" or not manifest_path.is_file():
        return None
    try:
        if sha256_file(manifest_path) != PINNED_MANIFEST_SHA256:
            return None
        document = strict_json_load(manifest_path)
        hashes = document.get("approved_successor_hashes") if isinstance(document, dict) else None
        value = hashes.get(relative) if isinstance(hashes, dict) else None
        if (
            document.get("schema_version") != "1.0.0"
            or document.get("compatibility_id") != COMPATIBILITY_ID
            or document.get("stage_id") != "S08"
            or not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            return None
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            return None
        current = root.parent / candidate if relative.startswith(".github/") else root / candidate
        return value if current.is_file() and sha256_file(current) == value else None
    except Exception:
        return None


__all__ = ["COMPATIBILITY_ID", "MANIFEST_PATH", "PINNED_MANIFEST_SHA256", "approved_successor_sha256"]
