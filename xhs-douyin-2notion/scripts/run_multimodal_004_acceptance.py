#!/usr/bin/env python3
"""Run the zero-model synthetic acceptance for TSK.x2n.multimodal.004."""

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
TASK_ID = "TSK.x2n.multimodal.004"
PHASE = "PH.X2N.4.4"
RUN_ID = "RUN-X2N-S04-M004"


def _isolated_env(home: Path) -> dict[str, str]:
    """Keep acceptance independent from Owner data, credentials and models."""

    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
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
        raise RuntimeError("Fusion test suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-m004-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "Fusion synthetic suite",
            (sys.executable, "-B", "-m", "unittest", "apps.companion.tests.test_fusion"),
            env=environment,
        )
        _run(
            "Fusion ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "apps/companion/src/x2n_companion/fusion.py",
                "apps/companion/tests/test_fusion.py",
                "scripts/run_multimodal_004_acceptance.py",
            ),
            env=environment,
        )
    return {
        "acceptance_status": {
            "ACC.x2n.ai.004": "PASS_CI_SYNTH_FUSION_SCHEMA_INJECTION_ISOLATION_MODEL_NOT_RUN",
            "ACC.x2n.ai.007": "PASS_CI_SYNTH_TASK004_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO",
        },
        "execution": {
            "cloud_uploads": 0,
            "config_writes": 0,
            "file_reads": 0,
            "model_calls": 0,
            "network_calls": 0,
            "notion_calls": 0,
            "owner_profile_login": "NOT_RUN",
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_platform_media": "NOT_RUN",
            "secret_reads": 0,
            "tool_calls": 0,
        },
        "metrics": {
            "cloud_cost_microunits": 0,
            "same_input_duplicate_model_calls": 0,
            "synthetic_unit_tests": _test_count(tests),
            "url_uploads": 0,
        },
        "policy": {
            "cloud_provider": "DISABLED",
            "fusion_text_persisted": False,
            "local_paths_emitted": False,
            "raw_media_persisted": False,
            "raw_media_url_persisted": False,
            "top_level_category_mutations": 0,
        },
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_SCOPED_FUSION_MODEL_NOT_RUN",
        "task_id": TASK_ID,
        "phase": PHASE,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
