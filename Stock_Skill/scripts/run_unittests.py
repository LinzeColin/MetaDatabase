#!/usr/bin/env python3
"""Discover and run every active Stock Skill unittest with a zero-case gate."""

from __future__ import annotations

import argparse
import re
import stat
import subprocess
import sys
import unittest
from pathlib import Path


EXCLUDED_PARTS = {"archives", "releases", "__pycache__"}
SUITE_MARKER = re.compile(r"^SUITE_CASES=(\d+)$", flags=re.MULTILINE)


def discover_test_files(stock_root: Path) -> list[Path]:
    if stock_root.is_symlink() or not stock_root.is_dir():
        raise RuntimeError(f"Stock Skill root must be a non-symlink directory: {stock_root}")
    test_files: list[Path] = []
    for path in stock_root.rglob("test_*.py"):
        relative = path.relative_to(stock_root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            raise RuntimeError(f"unittest path must be a regular non-symlink: {path}")
        test_files.append(path)
    return sorted(test_files, key=lambda path: path.as_posix())


def run_one_suite(test_dir: Path) -> int:
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(test_dir), pattern="test_*.py"
    )
    case_count = suite.countTestCases()
    if case_count == 0:
        print(f"FAIL: unittest discovery found zero test cases in {test_dir}", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print(f"SUITE_CASES={case_count}")
    return 0


def run_all(repo_root: Path) -> int:
    stock_root = repo_root / "Stock_Skill"
    try:
        test_files = discover_test_files(stock_root)
    except (OSError, RuntimeError) as exc:
        print(f"FAIL: cannot discover Stock Skill unittests: {exc}", file=sys.stderr)
        return 1
    if not test_files:
        print("FAIL: no Stock Skill unittest files discovered", file=sys.stderr)
        return 1
    test_dirs = sorted({path.parent for path in test_files}, key=lambda path: path.as_posix())
    total_cases = 0
    script = Path(__file__).resolve()
    for test_dir in test_dirs:
        print(f"RUN: unittest discovery in {test_dir}", flush=True)
        result = subprocess.run(
            [sys.executable, "-B", str(script), "--suite-dir", str(test_dir)],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode != 0:
            return result.returncode
        matches = SUITE_MARKER.findall(result.stdout)
        if len(matches) != 1 or int(matches[0]) <= 0:
            print(
                f"FAIL: suite did not report one positive case count: {test_dir}",
                file=sys.stderr,
            )
            return 1
        total_cases += int(matches[0])
    print(
        f"PASS: {total_cases} test case(s) from {len(test_files)} file(s) "
        f"across {len(test_dirs)} suite(s)"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--suite-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.suite_dir is not None:
        return run_one_suite(args.suite_dir)
    try:
        repo_root = args.repo_root.resolve(strict=True)
    except OSError as exc:
        print(f"FAIL: invalid repository root: {exc}", file=sys.stderr)
        return 1
    return run_all(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
