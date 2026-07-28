#!/usr/bin/env python3
"""Execute the public, zero-platform-call acceptance for Task010."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "TSK.x2n.adapters.010"
PHASE = "PH.X2N.3.10"


def _playwright_browsers_path() -> str | None:
    """Locate only the local Playwright browser binary cache, never Owner data."""

    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        return configured
    default_cache = Path.home() / "Library/Caches/ms-playwright"
    return str(default_cache) if default_cache.is_dir() else None


def _isolated_env(home: Path) -> dict[str, str]:
    """Keep acceptance independent from credentials and Owner runtime data."""

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


def _run(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int = 180) -> str:
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
        raise RuntimeError(f"{label} failed")
    return result.stdout + result.stderr


def _json_line(output: str, *, label: str) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    if not parsed:
        raise RuntimeError(f"{label} did not emit a JSON receipt")
    return parsed[-1]


def _test_count(output: str, *, label: str) -> int:
    matches = re.findall(r"Ran (\d+) tests?", output)
    if not matches:
        raise RuntimeError(f"{label} did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a010-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        python_tests = _run(
            "Task010 Python suite",
            (
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "apps.companion.tests.test_adapter_dispatch",
                "apps.companion.tests.test_native_host",
                "apps.companion.tests.test_canonical_store",
                "packages.contracts.tests.test_adapter_dispatch_contracts",
                "packages.contracts.tests.test_contracts",
            ),
            env=environment,
        )
        _run(
            "generated contract drift check",
            (sys.executable, "-B", "-m", "x2n_contracts.generate", "--check"),
            env=environment,
        )
        _run(
            "Task010 ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "apps/companion/src/x2n_companion",
                "apps/companion/tests/test_adapter_dispatch.py",
                "packages/contracts/src/x2n_contracts",
                "packages/contracts/tests/test_adapter_dispatch_contracts.py",
                "scripts/run_adapters_010_acceptance.py",
            ),
            env=environment,
        )
        _run("TypeScript contracts", ("npm", "run", "check:contracts:types"), env=environment)
        extension_self_test = _json_line(
            _run("Extension static self-test", ("npm", "run", "self-test", "--workspace", "@x2n/extension"), env=environment),
            label="Extension static self-test",
        )
        extension_e2e = _json_line(
            _run("Extension E2E", ("npm", "run", "test:e2e", "--workspace", "@x2n/extension"), env=environment, timeout=240),
            label="Extension E2E",
        )

    if (
        extension_self_test.get("status") != "PASS"
        or extension_e2e.get("status") != "PASS"
        or extension_e2e.get("scope_dispatches") != 8
        or extension_e2e.get("scope_dispatch_platform_calls") != 0
        or extension_e2e.get("platform_calls") != 0
        or extension_e2e.get("real_accounts") != 0
        or extension_e2e.get("duplicate_jobs") != 0
        or extension_e2e.get("lost_jobs") != 0
        or extension_e2e.get("wrong_statuses") != 0
    ):
        raise RuntimeError("Task010 Extension acceptance metrics drifted")

    return {
        "acceptance_scope": "ADAPTERS_010_NATIVE_DISPATCH_AND_EXPLICIT_FALLBACK_CI_SYNTH",
        "automatic_fallbacks": 0,
        "capability_scope_count": 8,
        "extension_e2e_status": "PASS",
        "generated_contracts": "PASS",
        "media_processing": "NOT_RUN",
        "model_calls": 0,
        "owner_alpha": "NOT_RUN",
        "owner_beta": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "python_tests": _test_count(python_tests, label="Task010 Python suite"),
        "real_account_execution": "NOT_RUN",
        "scope_dispatch_platform_calls": 0,
        "scope_dispatches": 8,
        "stage_3_upload": "NOT_RUN",
        "stage_4": "NOT_RUN",
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "typed_capability_rows": 8,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps({"reason": str(error), "status": "FAIL_CLOSED", "task_id": TASK_ID}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
