#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "machine/evidence"
MANIFEST = EVIDENCE / "artifact_manifest.json"
SUMS = EVIDENCE / "SHA256SUMS"
EXCLUDED_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix in {".pyc", ".pyo"} or path.name == ".DS_Store":
        return False
    return path not in {MANIFEST, SUMS}


def payload_files():
    return sorted(
        (path for path in ROOT.rglob("*") if path.is_file() and included(path)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def main() -> int:
    files = payload_files()
    manifest = {
        "schema_version": "1.0.0",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generated_at": "2026-07-19T00:00:00+10:00",
        "scope": "All ABD project files except caches, this manifest, and SHA256SUMS.",
        "file_count": len(files),
        "files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    write_atomic(
        MANIFEST,
        (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )

    checksum_files = sorted(
        (
            path
            for path in ROOT.rglob("*")
            if path.is_file() and path != SUMS and (included(path) or path == MANIFEST)
        ),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    lines = [
        "%s  %s\n" % (sha256(path), path.relative_to(ROOT).as_posix())
        for path in checksum_files
    ]
    write_atomic(SUMS, "".join(lines).encode("utf-8"))
    print(
        json.dumps(
            {"status": "PASS", "manifest_files": len(files), "checksum_files": len(checksum_files)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
