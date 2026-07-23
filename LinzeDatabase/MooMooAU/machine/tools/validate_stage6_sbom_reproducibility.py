#!/usr/bin/env python3
"""Rebuild and byte-compare the sanitized Stage 6 SBOM in an ephemeral directory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(argv: list[str], root: Path) -> tuple[int, str]:
    completed = subprocess.run(
        argv,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode, output


def validate(root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix="moomooau-stage6-sbom-") as temporary:
        temp = Path(temporary)
        raw = temp / "stage6-sbom.raw.cdx.json"
        sanitized = temp / "stage6-sbom.cdx.json"
        commands = (
            [
                str(Path(sys.executable).parent / "cyclonedx-py"),
                "requirements",
                "requirements/stage6.lock",
                "--pyproject",
                "pyproject.toml",
                "--output-reproducible",
                "--validate",
                "--output-format",
                "JSON",
                "--output-file",
                str(raw),
            ],
            [
                sys.executable,
                "machine/stages/S2/tools/sanitize_sbom.py",
                "--input",
                str(raw),
                "--lock",
                "requirements/stage6.lock",
                "--output",
                str(sanitized),
            ],
        )
        failures: list[str] = []
        for index, argv in enumerate(commands, start=1):
            returncode, output = _run(argv, root)
            if returncode != 0:
                failures.append(f"SBOM step {index} exited {returncode}: {output[:500]}")
                break
        expected = root / "machine/stages/S6/supply-chain/sbom.cdx.json"
        byte_equal = (
            not failures and sanitized.is_file() and sanitized.read_bytes() == expected.read_bytes()
        )
        if not byte_equal and not failures:
            failures.append("sanitized Stage 6 SBOM differs byte-for-byte")
    return {
        "schema_version": "moomooau.stage6-sbom-reproducibility.v1",
        "status": "PASS" if not failures else "FAIL",
        "byte_equal": byte_equal,
        "ephemeral_outputs_removed": True,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = validate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
