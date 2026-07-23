#!/usr/bin/env python3
"""Run the scoped Stage 6 detect-secrets gate without persisting its raw report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRUCTURED_RECEIPT_PATHS = (
    Path("machine/stages/S6/reviews/rmd05/execution-receipt.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt2.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt3.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt4.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt5.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt6.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt7.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt8.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt9.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt10.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt11.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt12.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt13.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt14.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt15.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt16.json"),
    Path("machine/stages/S6/reviews/rmd05/execution-receipt17.json"),
)
STRUCTURED_REVIEW_PROVENANCE_PATHS = (
    Path("machine/stages/S6/reviews/gpt-5.6-sol.json"),
    Path("machine/stages/S6/reviews/gpt-5.6-terra.json"),
)
SENSITIVE_RECEIPT_PATTERNS = (
    re.compile(r"AGE-SECRET-KEY-1[0-9a-z]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"1//[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
)


def _relative(path: Path, repository: Path) -> str:
    return path.relative_to(repository).as_posix()


def _structured_json_failures(
    root: Path,
    paths: tuple[Path, ...],
    *,
    label: str,
) -> list[str]:
    failures: list[str] = []
    for relative in paths:
        path = root / relative
        if not path.exists():
            continue
        if not path.is_file() or path.is_symlink():
            failures.append(f"{label} path is unsafe: {relative.as_posix()}")
            continue
        try:
            payload = path.read_text(encoding="utf-8")
            value: Any = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            failures.append(f"{label} is not UTF-8 JSON: {relative.as_posix()}")
            continue
        if not isinstance(value, dict):
            failures.append(f"{label} is not an object: {relative.as_posix()}")
        if any(pattern.search(payload) for pattern in SENSITIVE_RECEIPT_PATTERNS):
            failures.append(f"{label} contains a sensitive pattern: {relative.as_posix()}")
    return failures


def _structured_receipt_failures(root: Path) -> list[str]:
    return _structured_json_failures(
        root,
        STRUCTURED_RECEIPT_PATHS,
        label="structured receipt",
    )


def _structured_review_failures(root: Path) -> list[str]:
    return _structured_json_failures(
        root,
        STRUCTURED_REVIEW_PROVENANCE_PATHS,
        label="structured review provenance",
    )


def validate(root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = root.resolve()
    repository = root.parents[1]
    structured_failures = [
        *_structured_receipt_failures(root),
        *_structured_review_failures(root),
    ]
    task_tests = sorted((root / "tests/tasks").glob("test_t06*.py"))
    targets = [
        _relative(root / "src", repository),
        _relative(root / "tests/stage6_support.py", repository),
        *(_relative(path, repository) for path in task_tests),
        _relative(root / "tests/remediation/test_rmd05.py", repository),
        _relative(root / "machine/stages/S6", repository),
        _relative(root / "machine/contracts/delivery_status_model.json", repository),
        _relative(root / "schemas/delivery-status-v1.schema.json", repository),
        _relative(root / "machine/tools/build_delivery_status.py", repository),
        _relative(root / "machine/tools/build_governance_facts.py", repository),
        _relative(root / "machine/tools/build_package_manifest.py", repository),
        _relative(root / "machine/tools/validate_assurance_reviews.py", repository),
        _relative(root / "machine/tools/capture_candidate_gates.py", repository),
        _relative(root / "machine/tools/validate_delivery_status.py", repository),
        _relative(root / "machine/tools/validate_evidence.py", repository),
        _relative(root / "machine/tools/validate_package.py", repository),
        _relative(root / "machine/tools/validate_stage6_sbom_reproducibility.py", repository),
        _relative(root / "machine/tools/validate_stage6_secret_scan.py", repository),
        ".github/workflows/moomooau-stage6-ci.yml",
        ".github/workflows/moomooau-stage6-model-assurance.yml",
    ]
    argv = [
        str(Path(sys.executable).parent / "detect-secrets"),
        "scan",
        "--all-files",
        "--exclude-lines",
        (
            "baseline_commit|baseline_manifest_sha256|BASELINE_COMMIT|"
            "BASELINE_MANIFEST_SHA256|RMD05_PREDECESSOR_MANIFEST_SHA256|"
            "STAGE6_LOCK_SHA256|STAGE6_SBOM_SHA256|"
            "candidate_commit|candidate_tree|request_sha256|reply_sha256|"
            "dependency_lock_sha256|python_executable_sha256|governance_commit"
        ),
        "--exclude-files",
        (
            r"(?:machine/stages/S6/supply-chain/sbom\.cdx\.json|"
            r"machine/contracts/delivery_status_model\.json|"
            r"machine/stages/S6/reviews/gpt-5\.6-(?:sol|terra)\.json|"
            r"machine/stages/S6/reviews/rmd05/execution-receipt(?:[2-9]|1[0-7])?\.json)"
        ),
        *targets,
    ]
    completed = subprocess.run(
        argv,
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    failures: list[str] = list(structured_failures)
    findings = -1
    finding_locations: list[dict[str, object]] = []
    try:
        report: Any = json.loads(completed.stdout)
        results = report.get("results", {}) if isinstance(report, dict) else {}
        findings = (
            sum(len(items) for items in results.values()) if isinstance(results, dict) else -1
        )
        if isinstance(results, dict):
            finding_locations = [
                {
                    "path": str(path),
                    "line": item.get("line_number"),
                    "type": item.get("type"),
                }
                for path, items in results.items()
                if isinstance(items, list)
                for item in items
                if isinstance(item, dict)
            ]
    except json.JSONDecodeError:
        failures.append("detect-secrets output is not JSON")
    if completed.returncode != 0:
        failures.append(f"detect-secrets exited {completed.returncode}")
    if completed.stderr.strip():
        failures.append("detect-secrets emitted unexpected stderr")
    if findings != 0:
        failures.append(f"scoped Stage 6 secret findings: {findings}")
    return {
        "schema_version": "moomooau.stage6-secret-scan.v1",
        "status": "PASS" if not failures else "FAIL",
        "findings": findings,
        "finding_locations": finding_locations,
        "raw_report_retained": False,
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
