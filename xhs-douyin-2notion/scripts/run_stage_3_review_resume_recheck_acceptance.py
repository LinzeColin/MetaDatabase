#!/usr/bin/env python3
"""Run the independent, zero-platform-call G3 CI-synth recheck."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK010_RUNNER = PROJECT_ROOT / "scripts/run_adapters_010_acceptance.py"
TASK005_RUNNER = PROJECT_ROOT / "scripts/run_adapters_005_acceptance.py"
REVIEW_ID = "STG.X2N.3.REVIEW.RESUME.RECHECK"
RUN_ID = "RUN-X2N-S03-REVIEW-RESUME-RECHECK"


class RecheckError(RuntimeError):
    pass


def _playwright_browsers_path() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        return configured
    default_cache = Path.home() / "Library/Caches/ms-playwright"
    return str(default_cache) if default_cache.is_dir() else None


def _isolated_env(home: Path) -> dict[str, str]:
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }
    browser_path = _playwright_browsers_path()
    if browser_path:
        environment["PLAYWRIGHT_BROWSERS_PATH"] = browser_path
    return environment


def _run(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int) -> str:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RecheckError(f"{label} failed")
    return result.stdout + result.stderr


def _receipt(output: str, *, label: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            values.append(candidate)
    if not values:
        raise RecheckError(f"{label} emitted no JSON receipt")
    return values[-1]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecheckError(message)


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-s03-g3-recheck-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        task010 = _receipt(
            _run(
                "Task010 scoped dispatch acceptance",
                (sys.executable, "-B", str(TASK010_RUNNER)),
                env=environment,
                timeout=600,
            ),
            label="Task010 scoped dispatch acceptance",
        )
        task005 = _receipt(
            _run(
                "Task005 relation reconciliation acceptance",
                (sys.executable, "-B", str(TASK005_RUNNER)),
                env=environment,
                timeout=600,
            ),
            label="Task005 relation reconciliation acceptance",
        )
        extension = _receipt(
            _run(
                "fresh Extension restart reconciliation",
                ("npm", "run", "test:e2e", "--workspace", "@x2n/extension"),
                env=environment,
                timeout=360,
            ),
            label="fresh Extension restart reconciliation",
        )

    _require(
        task010.get("status") == "PASS_CI_SYNTH_SCOPED"
        and task010.get("scope_dispatches") == 8
        and task010.get("typed_capability_rows") == 8
        and task010.get("platform_calls") == 0
        and task010.get("scope_dispatch_platform_calls") == 0
        and task010.get("automatic_fallbacks") == 0
        and task010.get("extension_e2e_status") == "PASS",
        "eight-scope dispatch or capability snapshot replay drifted",
    )
    _require(
        task005.get("status") == "PASS_CI_SYNTH_SCOPED"
        and task005.get("platform_calls") == 0
        and task005.get("automatic_scroll") == 0
        and task005.get("automatic_pagination") == 0
        and task005.get("batch_protection", {}).get("content_auto_deletes") == 0
        and task005.get("batch_protection", {}).get("physical_deletes") == 0
        and task005.get("batch_protection", {}).get("non_authoritative_removed_writes") == 0
        and task005.get("integrity", {}).get("integrity_check") == "ok",
        "empty-response deletion or reconciliation replay drifted",
    )
    _require(
        extension.get("status") == "PASS"
        and extension.get("scope_dispatches") == 8
        and extension.get("scope_dispatch_platform_calls") == 0
        and extension.get("platform_calls") == 0
        and extension.get("real_accounts") == 0
        and extension.get("service_worker_restarts") == 100
        and extension.get("lost_jobs") == 0
        and extension.get("duplicate_jobs") == 0
        and extension.get("wrong_statuses") == 0
        and extension.get("request_ledger_rows") == 9,
        "Extension restart reconciliation replay drifted",
    )
    return {
        "automatic_fallbacks": 0,
        "capability_gate_outcome_rows": 8,
        "checkpoint_resume_restart_reconciliation": "PASS",
        "extension_service_worker_restarts": 100,
        "failed_run_explicit_fallback": "PASS_BY_TASK010_SCOPED_ACCEPTANCE",
        "no_empty_response_deletion": "PASS",
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "scope_dispatches": 8,
        "stage_3_remote_upload": "NOT_RUN",
        "status": "PASS_CI_SYNTH_G3_RECHECK",
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, RecheckError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {"reason": str(error), "review_id": REVIEW_ID, "status": "FAIL_CLOSED"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
