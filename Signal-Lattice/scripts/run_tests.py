#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RAN_RE = re.compile(r"Ran\s+(\d+)\s+tests?\s+in\s+([0-9.]+)s")
SKIP_RE = re.compile(r"OK\s+\(skipped=(\d+)\)")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description="在隔离子进程中逐文件执行 Signal Lattice 单元测试。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout-per-file", type=int, default=120)
    parser.add_argument("--receipt", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    tests = sorted((root / "tests").glob("test_*.py"))
    if not tests:
        print("NO_TEST_FILES", file=sys.stderr)
        return 2

    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {
            "PYTHONHOME",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
        }
    }
    env.update(
        {
            "PYTHONPATH": str(root / "src"),
            "PYTHONWARNINGS": "error",
            "PYTHONHASHSEED": "0",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
    )

    rows: list[dict[str, Any]] = []
    total_tests = 0
    total_skipped = 0
    started_all = time.monotonic()

    for path in tests:
        rel = path.relative_to(root).as_posix()
        started = time.monotonic()
        print(json.dumps({"event": "test_file_started", "path": rel}, ensure_ascii=False), flush=True)
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(root / "tests"),
                    "-p",
                    path.name,
                    "-v",
                ],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout_per_file,
            )
            code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            state = "PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired as exc:
            code = 124
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\nTEST_FILE_TIMEOUT"
            state = "FAIL"

        combined = stdout + "\n" + stderr
        match = RAN_RE.search(combined)
        test_count = int(match.group(1)) if match else 0
        skip_match = SKIP_RE.search(combined)
        skipped = int(skip_match.group(1)) if skip_match else 0
        total_tests += test_count
        total_skipped += skipped
        duration = round(time.monotonic() - started, 3)
        row = {
            "path": rel,
            "state": state,
            "returncode": code,
            "test_count": test_count,
            "skipped": skipped,
            "duration_seconds": duration,
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
            "stdout_tail": stdout[-1200:],
            "stderr_tail": stderr[-1600:],
        }
        rows.append(row)
        print(
            json.dumps(
                {
                    "event": "test_file_finished",
                    "path": rel,
                    "state": state,
                    "returncode": code,
                    "test_count": test_count,
                    "duration_seconds": duration,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    failures = [row["path"] for row in rows if row["state"] != "PASS"]
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": "PASS" if not failures else "FAIL",
        "runner": "isolated_test_file_subprocesses",
        "file_count": len(rows),
        "test_count": total_tests,
        "skipped": total_skipped,
        "failure_count": len(failures),
        "failures": failures,
        "timeout_per_file_seconds": args.timeout_per_file,
        "duration_seconds": round(time.monotonic() - started_all, 3),
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "files": rows,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()

    receipt_path = args.receipt
    if receipt_path is None:
        receipt_path = root / "evidence" / "tests" / "unit_suite.json"
    elif not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    print(
        json.dumps(
            {
                "state": receipt["state"],
                "file_count": len(rows),
                "test_count": total_tests,
                "skipped": total_skipped,
                "failure_count": len(failures),
                "receipt": str(receipt_path),
                "receipt_sha256": receipt["receipt_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
