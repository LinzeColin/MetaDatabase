#!/usr/bin/env python3
"""Fail-closed scan for values forbidden from the publishable MooMooAU tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?![A-Za-z0-9_.-])"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SECRET_PATTERNS = [
    re.compile(r"AGE-SECRET-KEY-1[0-9a-z]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"1//[A-Za-z0-9_-]{20,}"),
]
LOCAL_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
JSON_KEY = re.compile(r'"([^"\\]+)"\s*:')
FORBIDDEN_FIELD_HASHES = {
    "49648d40785d1147c8bb3d7e0239f0eec2ab378acba9b2a16d0edddad34144ca",
    "210ef1a68f8a9930ef9a7fe4a0d146076e0b4ceb97de579111fa8557a2bb9bd9",
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".zip", ".parquet", ".pyc"}
SKIP_DIRECTORY_NAMES = {
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scan_tree(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    contract = _load(root / "machine/contracts/publication_safety.json")
    forbidden_hashes = set(contract["forbidden_locator_sha256_casefold"])
    counts = {
        "private_locator": 0,
        "email": 0,
        "live_secret": 0,
        "local_absolute_path": 0,
        "forbidden_field": 0,
    }
    matched_files: set[str] = set()
    scanned = 0
    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root)
        if (
            any(part in SKIP_DIRECTORY_NAMES for part in relative_path.parts)
            or not path.is_file()
            or path.is_symlink()
            or path.suffix.lower() in SKIP_SUFFIXES
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        relative = relative_path.as_posix()
        file_matches = 0
        for token in REPOSITORY_TOKEN.findall(text):
            digest = hashlib.sha256(token.casefold().encode("utf-8")).hexdigest()
            if digest in forbidden_hashes:
                counts["private_locator"] += 1
                file_matches += 1
        email_count = len(EMAIL.findall(text))
        secret_count = sum(len(pattern.findall(text)) for pattern in SECRET_PATTERNS)
        local_path_count = len(LOCAL_PATH.findall(text))
        field_count = sum(
            hashlib.sha256(key.casefold().encode("utf-8")).hexdigest() in FORBIDDEN_FIELD_HASHES
            for key in JSON_KEY.findall(text)
        )
        counts["email"] += email_count
        counts["live_secret"] += secret_count
        counts["local_absolute_path"] += local_path_count
        counts["forbidden_field"] += field_count
        file_matches += email_count + secret_count + local_path_count + field_count
        if file_matches:
            matched_files.add(relative)
    total = sum(counts.values())
    return {
        "schema_version": "moomooau.publication-scan.v1",
        "status": "PASS" if total == 0 else "FAIL",
        "files_scanned": scanned,
        "match_counts": counts,
        "matched_files": sorted(matched_files),
        "total_matches": total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = scan_tree(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
