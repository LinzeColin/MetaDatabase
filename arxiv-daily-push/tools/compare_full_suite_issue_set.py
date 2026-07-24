#!/usr/bin/env python3
"""Compare unittest failures/errors against a sealed ADP baseline by exact test key."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


ISSUE = re.compile(
    r"^(ERROR|FAIL): ([^( ]+) \(([^)]+)\)(?: (.+))?$",
    re.MULTILINE,
)
RAN = re.compile(r"Ran (\d+) tests")
SUMMARY = re.compile(r"FAILED \(failures=(\d+), errors=(\d+), skipped=(\d+)\)")


def parse_unittest_log(path: Path) -> dict[str, object]:
    log = path.read_text(encoding="utf-8", errors="replace")
    issues = []
    for raw_kind, test_name, context, subtest in ISSUE.findall(log):
        kind = "ERROR" if raw_kind == "ERROR" else "FAILURE"
        key = f"{kind}|{context}|{test_name}"
        subtest = subtest.strip()
        if subtest:
            key = f"{key}|{subtest}"
        issues.append(
            {
                "key": key,
                "kind": kind,
                "test_name": test_name,
                "context": context,
                "subtest": subtest or None,
            }
        )
    ran = RAN.findall(log)
    summary = SUMMARY.findall(log)
    if len(ran) != 1 or len(summary) != 1:
        raise ValueError(f"ambiguous unittest summary: ran={ran!r}, summary={summary!r}")
    failures, errors, skipped = map(int, summary[0])
    parsed_failures = len([item for item in issues if item["kind"] == "FAILURE"])
    parsed_errors = len([item for item in issues if item["kind"] == "ERROR"])
    return {
        "summary": {
            "total": int(ran[0]),
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "parsed_failures": parsed_failures,
            "parsed_errors": parsed_errors,
            "issue_count_match": failures == parsed_failures and errors == parsed_errors,
        },
        "issues": issues,
    }


def load_sealed_candidate(baseline_zip: Path) -> dict[str, object]:
    with zipfile.ZipFile(baseline_zip) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.endswith("raw-results/full-suite-differential.json")
        ]
        if len(names) != 1:
            raise ValueError(f"expected one sealed differential, got {names!r}")
        document = json.loads(archive.read(names[0]))
    return document["candidate_actual"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner-log", type=Path, required=True)
    parser.add_argument("--baseline-zip", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-baseline-resolution",
        action="store_true",
        help="allow inherited issue keys to disappear while still forbidding candidate-only issues",
    )
    args = parser.parse_args()

    current = parse_unittest_log(args.runner_log)
    baseline = load_sealed_candidate(args.baseline_zip)
    current_keys = {item["key"] for item in current["issues"]}
    baseline_keys = {item["key"] for item in baseline["issues"]}
    candidate_only = sorted(current_keys - baseline_keys)
    baseline_only = sorted(baseline_keys - current_keys)
    issue_set_ok = not candidate_only and (args.allow_baseline_resolution or not baseline_only)
    count_ok = (
        current["summary"]["total"] == args.expected_total
        and current["summary"]["issue_count_match"]
    )
    result = {
        "schema_version": "adp-full-suite-exact-issue-set-v2",
        "current": current,
        "sealed_baseline": {
            "summary": baseline["summary"],
            "issue_keys": sorted(baseline_keys),
        },
        "differential": {
            "candidate_only": candidate_only,
            "baseline_only": baseline_only,
            "exact_issue_set_match": current_keys == baseline_keys,
            "expected_total": args.expected_total,
            "total_match": current["summary"]["total"] == args.expected_total,
            "test_count_delta": current["summary"]["total"] - baseline["summary"]["total"],
            "skip_delta": current["summary"]["skipped"] - baseline["summary"]["skipped"],
            "issue_count_match": current["summary"]["issue_count_match"],
        },
        "status": "PASS" if issue_set_ok and count_ok else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["differential"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
