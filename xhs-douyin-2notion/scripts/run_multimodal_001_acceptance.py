#!/usr/bin/env python3
"""Run the zero-platform-call synthetic acceptance for TSK.x2n.multimodal.001."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "TSK.x2n.multimodal.001"
PHASE = "PH.X2N.4.1"
RUN_ID = "RUN-X2N-S04-M001"


def _isolated_env(home: Path) -> dict[str, str]:
    """Keep acceptance independent from owner credentials and runtime data."""

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
        raise RuntimeError("multimodal test suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("bounded media toolchain dependency is unavailable")
    with tempfile.TemporaryDirectory(prefix="x2n-m001-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "multimodal bounded media suite",
            (
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "apps.companion.tests.test_media_safety",
                "apps.companion.tests.test_media_preprocessing",
            ),
            env=environment,
        )
        _run(
            "multimodal ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "apps/companion/src/x2n_companion/media_safety.py",
                "apps/companion/src/x2n_companion/media_preprocessing.py",
                "apps/companion/tests/test_media_safety.py",
                "apps/companion/tests/test_media_preprocessing.py",
                "scripts/run_multimodal_001_acceptance.py",
            ),
            env=environment,
        )
    return {
        "acceptance_status": {
            "ACC.x2n.media.002": "PASS_CI_SYNTH_LEASE_AND_DERIVATIVE_CLEANUP",
            "ACC.x2n.media.004": "PASS_CI_SYNTH_BOUNDED_FFMPEG_FFPROBE",
            "ACC.x2n.rel.004": "PASS_CI_SYNTH_M001_MEDIA_CAPACITY_CONTRIBUTION",
        },
        "execution": {
            "model_calls": 0,
            "notion_calls": 0,
            "owner_profile_login": "NOT_RUN",
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_platform_media": "NOT_RUN",
        },
        "metrics": {
            "active_lease_misdeletes": 0,
            "max_keyframes": 50,
            "max_media_duration_seconds": 7200,
            "platform_calls": 0,
            "synthetic_unit_tests": _test_count(tests),
        },
        "policy": {
            "raw_media_persistence": 0,
            "raw_media_url_persistence": 0,
            "resource_policy": "x2n-media-preprocess-v1",
            "sandbox": "POSIX_CPU_FILESIZE_NOFILE_PLUS_FFMPEG_MAX_ALLOC",
        },
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_SCOPED",
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
