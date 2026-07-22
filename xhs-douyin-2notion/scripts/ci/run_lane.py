#!/usr/bin/env python3
"""Execute the Foundation005 changed-scope or full-release local CI lane."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from ci_baseline import (
    BaselineError,
    PROJECT_ROOT,
    build_artifact,
    fixture_guard,
    run_osv,
    run_sast,
    run_self_test,
    scan_source,
    scan_text,
    validate_coverage,
    validate_csp,
    validate_license,
    validate_model_dataset,
    validate_unittest_skips,
)


class LaneError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LaneError(message)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tool(name: str) -> str:
    local = Path(sys.executable).parent / name
    value = str(local) if local.is_file() else shutil.which(name)
    _require(value is not None, f"required CI tool unavailable: {name}")
    return value


def _safe_environment(home: Path) -> dict[str, str]:
    tool_directories = []
    for name in ("coverage", "node", "npm", "ruff", "uv"):
        try:
            value = _tool(name)
        except LaneError:
            continue
        tool_directories.append(str(Path(value).resolve().parent))
    tool_directories.extend((str(Path(sys.executable).parent), "/opt/homebrew/bin", "/usr/bin", "/bin"))
    path = ":".join(dict.fromkeys(tool_directories))
    environment = {
        "COVERAGE_FILE": str(home / ".coverage"),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": path,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
        "RUFF_CACHE_DIR": str(home / "ruff-cache"),
        "UV_CACHE_DIR": str(home / "uv-cache"),
        "UV_INDEX_URL": "https://pypi.org/simple",
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_NO_CONFIG": "1",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
        "npm_config_update_notifier": "false",
    }
    browser_cache = PROJECT_ROOT / "build/playwright-browsers"
    if browser_cache.is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    return environment


def _sanitize_output(value: str, home: Path) -> str:
    sanitized = value.replace(str(PROJECT_ROOT), "<project>").replace(str(PROJECT_ROOT.parent), "<repository>")
    sanitized = sanitized.replace(str(home), "<temporary-home>")
    sanitized = re.sub(r"/(?:Users|home)/[^/\s]+/", "<local-root>/", sanitized)
    return sanitized[-6000:]


def _run(label: str, command: Sequence[str], *, env: dict[str, str], home: Path, timeout: int = 900) -> str:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        diagnostic = _sanitize_output(result.stdout + result.stderr, home)
        raise LaneError(f"blocking gate failed: {label}\n{diagnostic}")
    return result.stdout + result.stderr


def _base_commands() -> list[tuple[str, list[str], int]]:
    python = sys.executable
    return [
        (
            "format",
            [
                _tool("ruff"),
                "format",
                "--check",
                "scripts/ci",
                "scripts/generate_foundation_005_sbom.py",
                "scripts/verify_foundation_005.py",
                "tests/test_foundation_005.py",
            ],
            180,
        ),
        ("lint", [_tool("ruff"), "check", "."], 180),
        (
            "python_compile",
            [python, "-B", "-m", "compileall", "-q", "apps/companion/src", "packages/contracts/src", "scripts/ci"],
            180,
        ),
        ("typescript_contract", [_tool("npm"), "run", "check:contracts:types"], 240),
        ("root_unit", [python, "-B", "-m", "unittest", "discover", "-v", "-s", "tests", "-p", "test_*.py"], 300),
        (
            "companion_unit_integration",
            [python, "-B", "-m", "unittest", "discover", "-s", "apps/companion/tests", "-p", "test_*.py"],
            300,
        ),
        (
            "contract_unit",
            [python, "-B", "-m", "unittest", "discover", "-s", "packages/contracts/tests", "-p", "test_*.py"],
            240,
        ),
        (
            "contract_acceptance",
            [python, "-B", "scripts/verify_foundation_002.py", "--require-evidence"],
            480,
        ),
        (
            "sbom_drift",
            [python, "-B", "scripts/generate_foundation_005_sbom.py", "--check"],
            120,
        ),
    ]


def _full_commands() -> list[tuple[str, list[str], int]]:
    python = sys.executable
    return [
        ("scaffold_acceptance", [python, "-B", "scripts/verify_foundation_001.py", "--require-evidence"], 600),
        ("migration_integration", [python, "-B", "scripts/verify_foundation_003.py", "--require-evidence"], 900),
        ("extension_native_e2e", [python, "-B", "scripts/verify_foundation_004.py", "--require-evidence"], 1200),
    ]


def _coverage_gate(*, env: dict[str, str], home: Path, reports: Path) -> dict[str, Any]:
    coverage = _tool("coverage")
    _run("coverage_erase", [coverage, "erase"], env=env, home=home, timeout=60)
    _run(
        "coverage_execute",
        [
            coverage,
            "run",
            "--branch",
            "--source=x2n_companion,x2n_contracts",
            "-m",
            "unittest",
            "discover",
            "-s",
            "apps/companion/tests",
            "-p",
            "test_*.py",
        ],
        env=env,
        home=home,
        timeout=600,
    )
    private_report = home / "coverage.json"
    _run("coverage_json", [coverage, "json", "-o", str(private_report)], env=env, home=home, timeout=120)
    report = validate_coverage(private_report)
    _write_json(reports / "coverage-summary.json", report)
    return report


def _scan_public_reports(reports: Path) -> dict[str, Any]:
    findings = []
    scanned = 0
    for path in sorted(reports.rglob("*")):
        if not path.is_file() or path.suffix == ".zip":
            continue
        text = path.read_text(encoding="utf-8")
        findings.extend(scan_text(text, path.relative_to(reports).as_posix()))
        scanned += 1
    _require(not findings, "CI public report contains secret/private/CDN material")
    return {"finding_count": 0, "scanned_reports": scanned, "status": "PASS"}


def run_lane(*, lane: str, repetitions: int, reports: Path) -> dict[str, Any]:
    _require(lane in {"fast", "full"}, "unknown CI lane")
    expected_repetitions = 2 if lane == "full" else 1
    _require(repetitions == expected_repetitions, "blocking repetition count drifted")
    reports.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="x2n-f005-lane-") as value:
        home = Path(value)
        env = _safe_environment(home)
        commands = _base_commands() + (_full_commands() if lane == "full" else [])
        blocking_results: list[dict[str, Any]] = []
        explicit_nonblocking_skips = 0
        labels: list[str] = []
        for repetition in range(1, repetitions + 1):
            for label, command, timeout in commands:
                execution_label = f"{label}_r{repetition}"
                output = _run(execution_label, command, env=env, home=home, timeout=timeout)
                if label == "root_unit":
                    skip_report = validate_unittest_skips(output)
                    explicit_nonblocking_skips += skip_report["explicit_nonblocking_skips"]
                labels.append(execution_label)
                blocking_results.append(
                    {
                        "blocking": True,
                        "gate": label,
                        "label": execution_label,
                        "repetition": repetition,
                        "status": "PASS",
                    }
                )

        self_test = run_self_test()
        fixture = fixture_guard()
        source = scan_source()
        _require(source["status"] == "PASS", "source privacy scan failed")
        sast, sarif = run_sast()
        _require(sast["status"] == "PASS", "SAST failed")
        csp = validate_csp()
        license_report = validate_license()
        model = validate_model_dataset()
        _write_json(reports / "ci-self-test.json", self_test)
        _write_json(reports / "fixture-leak.json", fixture)
        _write_json(reports / "source-privacy.json", source)
        _write_json(reports / "sast.json", sast)
        _write_json(reports / "sast.sarif", sarif)
        _write_json(reports / "csp.json", csp)
        _write_json(reports / "license.json", license_report)
        _write_json(reports / "model-eval.json", model)

        coverage_report: dict[str, Any] | None = None
        osv_report: dict[str, Any] | None = None
        artifact_report: dict[str, Any] | None = None
        artifact_deterministic: bool | None = None
        if lane == "full":
            coverage_report = _coverage_gate(env=env, home=home, reports=reports)
            osv_report = run_osv()
            _write_json(reports / "osv.json", osv_report)
            artifact = reports / "x2n-source-candidate.zip"
            artifact_report = build_artifact(artifact)
            first_digest = artifact_report["artifact_sha256"]
            replay = home / "candidate-replay.zip"
            replay_report = build_artifact(replay)
            artifact_deterministic = first_digest == replay_report["artifact_sha256"]
            _require(artifact_deterministic, "release candidate is not deterministic")
            _write_json(reports / "artifact.json", artifact_report)

        report = {
            "artifact_deterministic": artifact_deterministic,
            "artifact_report": artifact_report,
            "blocking_commands": len(commands),
            "blocking_executions": len(labels),
            "blocking_failures": 0,
            "blocking_repetitions": repetitions,
            "blocking_results": blocking_results,
            "coverage": coverage_report,
            "explicit_nonblocking_skips": explicit_nonblocking_skips,
            "flaky_blocking_tests": 0,
            "g1": "NOT_RUN",
            "lane": lane,
            "model_calls": 0,
            "osv": osv_report,
            "platform_calls": 0,
            "real_accounts": 0,
            "remote_github_actions": "NOT_RUN_LOCAL_BASELINE",
            "silent_blocking_skips": 0,
            "status": "PASS",
        }
        _write_json(reports / "software-lane.json", report)
        public_scan = _scan_public_reports(reports)
        _write_json(reports / "public-report-scan.json", public_scan)
        return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run x2n Foundation005 CI lane")
    parser.add_argument("--lane", choices=("fast", "full"), required=True)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--reports-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repetitions = args.repetitions if args.repetitions is not None else (2 if args.lane == "full" else 1)
    try:
        report = run_lane(lane=args.lane, repetitions=repetitions, reports=args.reports_dir)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (BaselineError, LaneError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps({"reason": str(error), "status": "FAIL_CLOSED"}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
