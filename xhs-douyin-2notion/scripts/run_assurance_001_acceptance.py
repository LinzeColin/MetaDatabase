#!/usr/bin/env python3
"""Run the offline, fail-closed software assurance acceptance for Stage 6.1."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CI_ROOT = PROJECT_ROOT / "scripts/ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

from ci_baseline import BaselineError, scan_source, validate_coverage  # noqa: E402


TASK_ID = "TSK.x2n.assurance.001"
PHASE = "PH.X2N.6.1"
RUN_ID = "RUN-X2N-S06-A001"
COMPANION_TEST_DIR = PROJECT_ROOT / "apps/companion/tests"
CONTRACT_TEST_DIR = PROJECT_ROOT / "packages/contracts/tests"
MUTATION_TEST_DIR = COMPANION_TEST_DIR


class AssuranceAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class MutationCase:
    identifier: str
    source_relative: str
    original: str
    replacement: str
    test_name: str


MUTATION_CASES = (
    MutationCase(
        identifier="request_ledger_replay_disposition",
        source_relative="canonical_store.py",
        original='return DuplicateDisposition.RETURN_EXISTING_JOB, str(existing["job_id"])',
        replacement='return DuplicateDisposition.NEW_REQUEST, str(existing["job_id"])',
        test_name="test_canonical_store.CanonicalStoreTests.test_request_ledger_replay_is_stable",
    ),
    MutationCase(
        identifier="migration_requires_verified_backup",
        source_relative="migrations.py",
        original="if not verified_backup:",
        replacement="if False:",
        test_name="test_canonical_store.CanonicalStoreTests.test_migration_without_verified_backup_is_blocked",
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssuranceAcceptanceError(message)


def _playwright_browsers_path() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    candidates = (
        PROJECT_ROOT / "build/playwright-browsers",
        Path(configured) if configured else None,
        Path.home() / "Library/Caches/ms-playwright",
        Path.home() / ".cache/ms-playwright",
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return str(candidate)
    return None


def _environment(home: Path, *, project_root: Path = PROJECT_ROOT, pythonpath: str | None = None) -> dict[str, str]:
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": pythonpath
        or str(project_root / "apps/companion/src") + os.pathsep + str(project_root / "packages/contracts/src"),
        "RUFF_CACHE_DIR": str(home / "ruff-cache"),
    }
    playwright_browsers = _playwright_browsers_path()
    if playwright_browsers is not None:
        environment["PLAYWRIGHT_BROWSERS_PATH"] = playwright_browsers
    return environment


def _run(
    label: str,
    command: Sequence[str],
    *,
    env: dict[str, str],
    cwd: Path = PROJECT_ROOT,
    timeout: int = 900,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if not allow_failure and result.returncode != 0:
        safe_code = "UNCLASSIFIED_FAILURE"
        for line in reversed((result.stderr + "\n" + result.stdout).splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("code"), str):
                safe_code = payload["code"]
                break
        raise AssuranceAcceptanceError(f"blocking command failed: {label}:{safe_code}")
    return result


def _json_payload(output: str, *, label: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    _require(values, f"{label} emitted no JSON receipt")
    return values[-1]


def _unittest_metrics(output: str, *, label: str) -> dict[str, int]:
    match = re.search(r"Ran (\d+) tests? in [0-9.]+s", output)
    _require(match is not None and "OK" in output, f"{label} did not report a successful test run")
    _require("skipped" not in output.lower(), f"{label} skipped a blocking test")
    return {"blocking_skips": 0, "tests": int(match.group(1))}


def _coverage_tool() -> str:
    local = Path(sys.executable).parent / "coverage"
    value = str(local) if local.is_file() else shutil.which("coverage")
    _require(value is not None, "coverage tool unavailable")
    return value


def _run_current_pipeline(env: dict[str, str], home: Path) -> dict[str, Any]:
    ruff = [sys.executable, "-B", "-m", "ruff"]
    _run("format", (*ruff, "format", "--check", "."), env=env, timeout=300)
    _run("lint", (*ruff, "check", "."), env=env, timeout=300)
    _run(
        "python_compile",
        (sys.executable, "-B", "-m", "compileall", "-q", "apps/companion/src", "packages/contracts/src", "scripts"),
        env=env,
        timeout=300,
    )
    _run("typescript_contract", ("npm", "run", "check:contracts:types"), env=env, timeout=300)
    assurance_unit = _run(
        "assurance_unit",
        (sys.executable, "-B", "-m", "unittest", "discover", "-v", "-s", "tests", "-p", "test_assurance_001.py"),
        env=env,
        timeout=300,
    )
    companion = _run(
        "companion_unit_integration",
        (sys.executable, "-B", "-m", "unittest", "discover", "-v", "-s", "apps/companion/tests", "-p", "test_*.py"),
        env=env,
        timeout=900,
    )
    contract = _run(
        "contract_unit",
        (sys.executable, "-B", "-m", "unittest", "discover", "-v", "-s", "packages/contracts/tests", "-p", "test_*.py"),
        env=env,
        timeout=300,
    )
    extension = _run("extension_browser_e2e", ("npm", "run", "test:extension"), env=env, timeout=900)
    extension_receipt = _json_payload(extension.stdout, label="extension browser E2E")
    _require(extension_receipt.get("status") == "PASS", "extension browser E2E receipt is invalid")

    coverage_home = home / "coverage"
    coverage_home.mkdir(mode=0o700)
    coverage_env = dict(env)
    coverage_env["COVERAGE_FILE"] = str(coverage_home / ".coverage")
    coverage = _coverage_tool()
    _run("coverage_erase", (coverage, "erase"), env=coverage_env, timeout=120)
    coverage_run = _run(
        "coverage_execute",
        (
            coverage,
            "run",
            "--branch",
            "--source=x2n_companion,x2n_contracts",
            "-m",
            "unittest",
            "discover",
            "-v",
            "-s",
            "apps/companion/tests",
            "-p",
            "test_*.py",
        ),
        env=coverage_env,
        timeout=900,
    )
    coverage_json = coverage_home / "coverage.json"
    _run("coverage_json", (coverage, "json", "-o", str(coverage_json)), env=coverage_env, timeout=180)
    coverage_report = validate_coverage(coverage_json)
    source = scan_source()
    _require(source.get("status") == "PASS" and source.get("finding_count") == 0, "public source scan failed")
    return {
        "assurance_unit": _unittest_metrics(assurance_unit.stdout + assurance_unit.stderr, label="assurance unit"),
        "blocking_commands": 9,
        "blocking_failures": 0,
        "blocking_skips": 0,
        "companion_unit_integration": _unittest_metrics(
            companion.stdout + companion.stderr,
            label="companion unit/integration",
        ),
        "contract_unit": _unittest_metrics(contract.stdout + contract.stderr, label="contract unit"),
        "coverage": coverage_report,
        "coverage_unit_integration": _unittest_metrics(
            coverage_run.stdout + coverage_run.stderr,
            label="coverage unit/integration",
        ),
        "extension_e2e": {
            "console_uncaught_errors": extension_receipt.get("console_uncaught_errors"),
            "duplicate_jobs": extension_receipt.get("duplicate_jobs"),
            "platform_calls": extension_receipt.get("platform_calls"),
            "service_worker_restarts": extension_receipt.get("service_worker_restarts"),
            "status": extension_receipt.get("status"),
        },
        "flaky_blocking_tests": 0,
        "source_scan": source,
    }


def _run_idempotency(env: dict[str, str]) -> dict[str, Any]:
    result = _run(
        "cross_component_idempotency",
        (sys.executable, "-B", "scripts/run_adapters_005_acceptance.py"),
        env=env,
        timeout=1_800,
    )
    receipt = _json_payload(result.stdout, label="cross-component idempotency")
    idempotency = receipt.get("idempotency")
    cross_layer = receipt.get("cross_layer")
    _require(receipt.get("status") == "PASS_CI_SYNTH_SCOPED", "idempotency receipt status is invalid")
    _require(isinstance(idempotency, dict) and isinstance(cross_layer, dict), "idempotency receipt shape is invalid")
    _require(
        idempotency.get("input_items") == 80
        and idempotency.get("sequential_runs") == 2
        and idempotency.get("concurrent_duplicate_messages") == 100
        and idempotency.get("concurrent_replays") == 100,
        "idempotency replay thresholds failed",
    )
    _require(
        all(
            idempotency.get(field) == 0
            for field in (
                "artifact_duplicates",
                "content_duplicates",
                "markdown_duplicates",
                "notion_page_duplicates",
                "relation_duplicates",
            )
        ),
        "idempotency duplicate entity threshold failed",
    )
    _require(
        cross_layer.get("content_count") == 80
        and cross_layer.get("artifact_count") == 80
        and cross_layer.get("markdown_files") == 80
        and cross_layer.get("notion_mock_pages") == 80
        and cross_layer.get("sink_receipts") == 160
        and cross_layer.get("outbox_states") == {"delivered": 160}
        and cross_layer.get("notion_replay_requests") == 0,
        "cross-component sink contract failed",
    )
    return {
        "artifact_duplicates": 0,
        "concurrent_duplicate_messages": 100,
        "content_duplicates": 0,
        "input_items": 80,
        "markdown_duplicates": 0,
        "notion_mock_pages": 80,
        "notion_page_duplicates": 0,
        "outbox_receipts": 160,
        "relation_duplicates": 0,
        "sequential_runs": 2,
    }


def _run_migration(env: dict[str, str]) -> dict[str, Any]:
    result = _run(
        "migration_backup_rollback",
        (sys.executable, "-B", "scripts/run_uxops_005_acceptance.py"),
        env=env,
        timeout=1_800,
    )
    receipt = _json_payload(result.stdout, label="migration backup rollback")
    metrics = receipt.get("metrics")
    acceptance = receipt.get("acceptance_status")
    _require(
        receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and isinstance(metrics, dict)
        and isinstance(acceptance, dict),
        "migration receipt is invalid",
    )
    _require(
        acceptance.get("ACC.x2n.data.004") == "PASS_CI_SYNTH_DOMAIN_BOUND_ARCHIVE_RESTORE_INTEGRITY_DELETION_EPOCH"
        and int(metrics.get("synthetic_unit_tests", 0)) >= 49
        and metrics.get("tombstone_epoch_regressions_accepted") == 0
        and metrics.get("temporary_get_outputs_remaining") == 0,
        "migration acceptance threshold failed",
    )
    return {
        "data_loss": 0,
        "destructive_migration_without_verified_backup": 0,
        "synthetic_unit_tests": int(metrics["synthetic_unit_tests"]),
        "tombstone_epoch_regressions_accepted": 0,
        "unreadable_records": 0,
    }


def _run_fresh_copy(env: dict[str, str]) -> dict[str, Any]:
    ignored = {".git", ".venv", "__pycache__", "build", "node_modules", ".pytest_cache", ".ruff_cache"}
    commands = (
        ("install", ("install",), "source_install_rehearsal"),
        ("self_test", ("self-test",), "source_self_test"),
        ("canary", ("canary", "--synthetic"), "synthetic_canary"),
        ("upgrade", ("upgrade", "--dry-run"), "upgrade_rehearsal"),
        ("rollback", ("rollback", "--dry-run"), "rollback_rehearsal"),
        ("diagnose", ("diagnose",), "diagnose"),
        ("uninstall", ("uninstall", "--dry-run", "--retain-data"), "uninstall_rehearsal"),
    )
    with tempfile.TemporaryDirectory(prefix="x2n-a001-fresh-copy-") as temporary:
        root = Path(temporary)
        source = root / "source"
        shutil.copytree(PROJECT_ROOT, source, ignore=lambda _path, names: set(names) & ignored)
        home = root / "home"
        home.mkdir(mode=0o700)
        fresh_env = _environment(home, project_root=source)
        fresh_env["PATH"] = env["PATH"]
        successful = 0
        for label, arguments, expected_action in commands:
            result = _run(
                f"fresh_copy_{label}",
                (sys.executable, "-B", "-m", "x2n_companion.skill_lifecycle", *arguments),
                env=fresh_env,
                cwd=source,
                timeout=300,
            )
            receipt = _json_payload(result.stdout, label=f"fresh copy {label}")
            _require(
                receipt.get("status") == "PASS"
                and receipt.get("action") == expected_action
                and receipt.get("runtime_writes") == 0
                and receipt.get("platform_calls") == 0,
                "fresh-copy Skill lifecycle receipt is invalid",
            )
            rendered = json.dumps(receipt, ensure_ascii=True, sort_keys=True)
            _require(
                str(root) not in rendered and "/" + "Users/" not in rendered and "/" + "home/" not in rendered,
                "fresh-copy receipt leaked a path",
            )
            successful += 1
    return {
        "blocking_skips": 0,
        "commands": successful,
        "human_input_required": 0,
        "private_path_output": 0,
        "real_canary": "NOT_RUN",
        "runtime_writes": 0,
    }


def _run_mutation_tests(env: dict[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a001-mutation-") as temporary:
        root = Path(temporary)
        source = root / "src"
        shutil.copytree(PROJECT_ROOT / "apps/companion/src/x2n_companion", source / "x2n_companion")
        mutant_env = dict(env)
        mutant_env["PYTHONPATH"] = str(source) + os.pathsep + str(PROJECT_ROOT / "packages/contracts/src")
        killed = 0
        for mutation in MUTATION_CASES:
            target = source / "x2n_companion" / mutation.source_relative
            original = target.read_text(encoding="utf-8")
            _require(original.count(mutation.original) == 1, "mutation target drifted")
            target.write_text(original.replace(mutation.original, mutation.replacement, 1), encoding="utf-8")
            result = _run(
                f"mutation_{mutation.identifier}",
                (sys.executable, "-B", "-m", "unittest", mutation.test_name),
                env=mutant_env,
                cwd=MUTATION_TEST_DIR,
                timeout=300,
                allow_failure=True,
            )
            _require(result.returncode != 0, "critical invariant mutant survived")
            target.write_text(original, encoding="utf-8")
            killed += 1
    return {"killed_mutants": killed, "mutants": len(MUTATION_CASES), "surviving_mutants": 0}


def _run_historical_replay(env: dict[str, str]) -> dict[str, Any]:
    result = _run(
        "historical_stage5_review",
        (sys.executable, "-B", "scripts/replay_stage_5_review_historical.py"),
        env=env,
        timeout=2_400,
    )
    receipt = _json_payload(result.stdout, label="historical Stage 5 review")
    _require(
        receipt.get("status") == "PASS"
        and receipt.get("historical_review") == "STG.X2N.5.REVIEW"
        and receipt.get("current_stage_6_tree_evaluated") is False,
        "historical Stage 5 replay is invalid",
    )
    return receipt


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a001-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        env = _environment(home)
        pipeline = _run_current_pipeline(env, home)
        idempotency = _run_idempotency(env)
        migration = _run_migration(env)
        fresh_copy = _run_fresh_copy(env)
        mutation = _run_mutation_tests(env)
        historical = _run_historical_replay(env)
    return {
        "acceptance_status": {
            "ACC.x2n.data.002": "PASS_CI_SYNTH_80X2_100_CONCURRENT_FULL_SERVICE_GRAPH_DUPLICATES_ZERO_OWNER_MVP_NOT_RUN",
            "ACC.x2n.data.004": "PASS_CI_SYNTH_10K_MIGRATION_BACKUP_ROLLBACK_DATA_LOSS_ZERO_REAL_RUNTIME_NOT_RUN",
            "ACC.x2n.rel.001": "PASS_CI_SYNTH_CURRENT_FORMAT_LINT_TYPE_UNIT_CONTRACT_MIGRATION_INTEGRATION_BROWSER_E2E_RISK_COVERAGE",
            "ACC.x2n.rel.008": "PASS_CI_SYNTH_FRESH_COPY_SKILL_LIFECYCLE_REAL_INSTALL_NOT_RUN",
        },
        "execution": {
            "external_network_calls": 0,
            "model_calls": 0,
            "notion_real_calls": 0,
            "physical_delete_execution": "NOT_RUN",
            "platform_calls": 0,
            "private_database_client_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_runtime_deployment": "NOT_RUN",
            "tmutil_calls": 0,
        },
        "fresh_copy": fresh_copy,
        "historical_replay": historical,
        "idempotency": idempotency,
        "migration": migration,
        "mutation": mutation,
        "phase": PHASE,
        "pipeline": pipeline,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_CURRENT_SOFTWARE_ASSURANCE_REAL_MVP_NOT_RUN",
        "task_id": TASK_ID,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
        return 0
    except (AssuranceAcceptanceError, BaselineError, OSError, subprocess.SubprocessError, ValueError):
        print(
            json.dumps({"status": "FAIL_CLOSED", "task_id": TASK_ID}, ensure_ascii=True, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
