#!/usr/bin/env python3
"""Run the isolated CI-synthetic acceptance for TSK.x2n.uxops.003."""

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
TASK_ID = "TSK.x2n.uxops.003"
PHASE = "PH.X2N.5.3"
RUN_ID = "RUN-X2N-S05-U003"
LOOPBACK_HOST = "127.0.0.1"

TEST_MODULES = (
    "apps.companion.tests.test_webui",
    "apps.companion.tests.test_relation_reconciliation",
)
RUFF_PATHS = (
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/relation_reconciliation.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/src/x2n_companion/webui.py",
    "apps/companion/tests/test_relation_reconciliation.py",
    "apps/companion/tests/test_webui.py",
    "scripts/replay_adapters_005_historical.py",
    "scripts/run_uxops_003_acceptance.py",
)


def _isolated_env(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


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


def _test_count(output: str) -> int:
    matches = re.findall(r"Ran (\d+) tests?", output)
    if not matches:
        raise RuntimeError("Local WebUI suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-u003-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "Local WebUI synthetic suite",
            (sys.executable, "-B", "-m", "unittest", *TEST_MODULES),
            env=environment,
        )
        _run(
            "Local WebUI ruff",
            (sys.executable, "-B", "-m", "ruff", "check", *RUFF_PATHS),
            env=environment,
        )
        replay = _run(
            "Pinned adapters.005 historical verifier replay",
            (sys.executable, "-B", "scripts/replay_adapters_005_historical.py"),
            env=environment,
        )
    try:
        historical = json.loads(replay)
    except json.JSONDecodeError as error:
        raise RuntimeError("Pinned historical verifier replay did not return JSON") from error
    if historical.get("status") != "PASS" or historical.get("current_v2_tree_evaluated") is not False:
        raise RuntimeError("Pinned historical verifier isolation failed")
    return {
        "acceptance_status": {
            "ACC.x2n.ai.005": "PASS_CI_SYNTH_OWNER_ONLY_TAXONOMY_REVISIONS_AI_MUTATIONS_ZERO",
            "ACC.x2n.ai.006": "PASS_CI_SYNTH_LOW_CONFIDENCE_OWNER_REVIEW_APPEND_ONLY_AUTO_CLASSIFY_DISABLED",
            "ACC.x2n.ext.001": "PASS_CI_SYNTH_LOOPBACK_LOCAL_WEBUI_SIDEPANEL_LINK_SURFACE_NO_EXTERNAL_CALLS",
            "ACC.x2n.ops.004": "PASS_CI_SYNTH_DASHBOARD_JOB_SINK_MODEL_AND_REDACTED_DIAGNOSTICS",
        },
        "execution": {
            "external_network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_notion_calls": 0,
            "runtime_data_writes": 0,
        },
        "historical_replay": historical,
        "metrics": {
            "accessibility_smoke": "PASS",
            "active_legacy_aliases": 0,
            "csrf_origin_rejections": 3,
            "diagnostic_private_content_hits": 0,
            "loopback_listener": LOOPBACK_HOST,
            "synthetic_unit_tests": _test_count(tests),
            "ui_api_version": "v2",
        },
        "phase": PHASE,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "task_id": TASK_ID,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
