#!/usr/bin/env python3
"""Refresh or check the deterministic Task Pack source manifest."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath


TASK_PACK = Path(__file__).resolve().parents[1] / "task-pack"
MANIFEST = TASK_PACK / "MANIFEST.sha256"


class ManifestError(RuntimeError):
    """A Task Pack manifest invariant failed."""


def canonical_relative(path: Path) -> str:
    relative = path.relative_to(TASK_PACK).as_posix()
    posix = PurePosixPath(relative)
    if (
        not relative
        or relative != unicodedata.normalize("NFC", relative)
        or relative != posix.as_posix()
        or posix.is_absolute()
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise ManifestError(f"non-canonical Task Pack path: {relative!r}")
    return relative


def render_manifest() -> bytes:
    rows: list[tuple[bytes, str]] = []
    for path in TASK_PACK.rglob("*"):
        if path == MANIFEST:
            continue
        relative = canonical_relative(path)
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            raise ManifestError(f"cache artifact rejected: {relative}")
        mode = path.lstat().st_mode
        if path.is_symlink() or (not stat.S_ISDIR(mode) and not stat.S_ISREG(mode)):
            raise ManifestError(f"non-regular entry rejected: {relative}")
        if not stat.S_ISREG(mode):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append((relative.encode("utf-8"), f"{digest}  ./{relative}\n"))
    if not rows:
        raise ManifestError("empty Task Pack")
    return "".join(row for _, row in sorted(rows)).encode("utf-8")


def atomic_write(payload: bytes) -> None:
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{MANIFEST.name}.", suffix=".tmp", dir=MANIFEST.parent
    )
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, MANIFEST)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh or check the deterministic Task Pack source manifest."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in manifest differs; do not write",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected = render_manifest()
        entries = expected.count(b"\n")
        if args.check:
            if not MANIFEST.is_file() or MANIFEST.is_symlink():
                raise ManifestError("Task Pack manifest is missing or invalid")
            if MANIFEST.read_bytes() != expected:
                raise ManifestError("Task Pack manifest is stale")
            print(f"PASS: Task Pack manifest current; entries={entries}")
            return 0
        atomic_write(expected)
        print(f"PASS: refreshed {MANIFEST}; entries={entries}")
        return 0
    except (ManifestError, OSError, UnicodeError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
