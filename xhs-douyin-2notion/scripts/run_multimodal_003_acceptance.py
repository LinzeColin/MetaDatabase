#!/usr/bin/env python3
"""Run the zero-platform-call synthetic acceptance for TSK.x2n.multimodal.003."""

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
TASK_ID = "TSK.x2n.multimodal.003"
PHASE = "PH.X2N.4.3"
RUN_ID = "RUN-X2N-S04-M003"


def _isolated_env(home: Path) -> dict[str, str]:
    """Keep acceptance independent from Owner credentials, models and runtime data."""

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
        raise RuntimeError("OCR/Vision test suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-m003-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "OCR/Vision synthetic suite",
            (sys.executable, "-B", "-m", "unittest", "apps.companion.tests.test_ocr_vision"),
            env=environment,
        )
        _run(
            "OCR/Vision ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "apps/companion/src/x2n_companion/ocr_vision.py",
                "apps/companion/src/x2n_companion/runtime_cli.py",
                "apps/companion/tests/test_ocr_vision.py",
                "scripts/run_multimodal_003_acceptance.py",
            ),
            env=environment,
        )
    return {
        "acceptance_status": {
            "ACC.x2n.ai.002": "PENDING_PRIVATE_GOLD_OCR_DISABLED_CI_CONTRACT_PASS",
            "ACC.x2n.ai.003": "PENDING_PRIVATE_GOLD_VISION_DISABLED_CI_CONTRACT_PASS",
            "ACC.x2n.ai.007": "PASS_CI_SYNTH_TASK003_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO",
        },
        "execution": {
            "cloud_uploads": 0,
            "local_model_execution": "NOT_RUN_OWNER_MANAGED_MODEL_NOT_PROVISIONED",
            "model_calls": 0,
            "notion_calls": 0,
            "owner_profile_login": "NOT_RUN",
            "platform_calls": 0,
            "private_gold_ocr_evaluation": "NOT_RUN",
            "private_gold_vision_evaluation": "NOT_RUN",
            "real_account_execution": "NOT_RUN",
            "real_platform_media": "NOT_RUN",
        },
        "metrics": {
            "cloud_cost_microunits": 0,
            "same_input_duplicate_provider_calls": 0,
            "synthetic_unit_tests": _test_count(tests),
            "url_uploads": 0,
        },
        "policy": {
            "cloud_provider": "DISABLED",
            "local_paths_emitted": False,
            "ocr_text_persisted": False,
            "raw_media_persisted": False,
            "raw_media_url_persisted": False,
            "vision_description_persisted": False,
        },
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
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
