#!/usr/bin/env python3
"""Scan CyberBoss material without echoing candidate or known secret values."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "openai_key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt": re.compile(
        rb"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "bearer": re.compile(
        rb"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~-]{20,}"
    ),
    "wechat_id": re.compile(rb"\bwxid_[A-Za-z0-9_-]+\b"),
}


def candidate_files(repo: Path, scope: str) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "--", scope],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    files: list[Path] = []
    for relative in result.stdout.splitlines():
        path = repo / relative
        if path.is_file() and path.stat().st_size <= 20 * 1024 * 1024:
            files.append(path)
    return sorted(set(files))


def known_values(paths: Iterable[Path]) -> list[bytes]:
    values: list[bytes] = []
    for path in paths:
        if not path.is_file():
            continue
        value = path.read_bytes().strip()
        if len(value) >= 12:
            values.append(value)
    return values


def scan(files: list[Path], secrets: list[bytes]) -> dict[str, object]:
    pattern_hits = {name: 0 for name in PATTERNS}
    known_hits = 0
    scanned_bytes = 0
    unreadable = 0
    for path in files:
        try:
            content = path.read_bytes()
        except OSError:
            unreadable += 1
            continue
        scanned_bytes += len(content)
        for name, pattern in PATTERNS.items():
            pattern_hits[name] += len(pattern.findall(content))
        known_hits += sum(1 for value in secrets if value in content)
    total_pattern_hits = sum(pattern_hits.values())
    p0 = total_pattern_hits + known_hits
    p1 = unreadable
    return {
        "schema_version": 1,
        "scanner": "CyberBoss bounded secret scanner",
        "scanned_files": len(files),
        "scanned_bytes": scanned_bytes,
        "known_secret_values_loaded": len(secrets),
        "known_secret_hits": known_hits,
        "forbidden_pattern_hits": total_pattern_hits,
        "pattern_hit_counts": pattern_hits,
        "unreadable_files": unreadable,
        "p0_findings": p0,
        "p1_findings": p1,
        "secret_values_emitted": False,
        "paths_with_hits_emitted": False,
        "result": "passed" if p0 == 0 and p1 == 0 else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--scope", default="CyberBoss")
    parser.add_argument("--known-secret-file", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    result = scan(candidate_files(repo, args.scope), known_values(args.known_secret_file))
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        sys.stdout.write(serialized)
    return 0 if result["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
