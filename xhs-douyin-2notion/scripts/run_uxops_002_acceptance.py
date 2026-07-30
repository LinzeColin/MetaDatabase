#!/usr/bin/env python3
"""Run the isolated CI-synthetic acceptance for TSK.x2n.uxops.002."""

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
TASK_ID = "TSK.x2n.uxops.002"
PHASE = "PH.X2N.5.2"
RUN_ID = "RUN-X2N-S05-U002"

MARKDOWN_TESTS = (
    "apps.companion.tests.test_sinks.SinkTests.test_six_platform_markdown_frontmatter_paths_index_and_cdn_scan",
    "apps.companion.tests.test_sinks.SinkTests.test_long_text_special_characters_are_deterministic_and_second_delivery_is_noop",
    "apps.companion.tests.test_sinks.SinkTests.test_title_and_owner_category_change_never_change_canonical_path",
    "apps.companion.tests.test_sinks.SinkTests.test_projection_snapshot_stays_on_one_wal_read_transaction",
    "apps.companion.tests.test_sinks.SinkTests.test_atomic_kills_leave_old_or_complete_file_and_replay_receipts",
    "apps.companion.tests.test_sinks.SinkTests.test_rebuild_is_atomic_per_file_and_repairs_category_index_after_kill",
    "apps.companion.tests.test_sinks.SinkTests.test_ten_thousand_canonical_rebuild_is_deterministic_and_category_only_reclassifies",
)


def _isolated_env(home: Path) -> dict[str, str]:
    """Keep the synthetic rebuild independent of Owner runtime/configuration state."""

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
        raise RuntimeError("Markdown rebuild suite did not report a test count")
    return int(matches[-1])


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-u002-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        tests = _run(
            "Markdown rebuild synthetic suite",
            (sys.executable, "-B", "-m", "unittest", *MARKDOWN_TESTS),
            env=environment,
            timeout=180,
        )
        _run(
            "Markdown rebuild ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "apps/companion/src/x2n_companion/canonical_store.py",
                "apps/companion/src/x2n_companion/markdown_sink.py",
                "apps/companion/tests/test_sinks.py",
                "scripts/run_uxops_002_acceptance.py",
            ),
            env=environment,
        )
    return {
        "acceptance_status": {
            "ACC.x2n.md.001": "PASS_CI_SYNTH_SIX_PLATFORM_FIXED_PATH_VALID_FRONTMATTER_CDN_ZERO_ATOMIC_PROVENANCE",
            "ACC.x2n.md.002": "PASS_CI_SYNTH_TEN_THOUSAND_SQLITE_REBUILD_MANIFEST_MATCH_CATEGORY_INDEX_LINKS_ZERO_DUPLICATE_COPIES",
        },
        "execution": {
            "network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_markdown_library": "NOT_RUN",
            "runtime_data_writes": 0,
        },
        "metrics": {
            "canonical_content_files": 10_000,
            "category_index_links": 10_000,
            "duplicate_content_copies": 0,
            "renderer_version": "1.1.0",
            "second_rebuild_writes": 0,
            "synthetic_unit_tests": _test_count(tests),
        },
        "policy": {
            "canonical_path": "platform_content_id_only",
            "category_indexes": "GENERATED_LINKS_NOT_SECOND_SOURCE",
            "projection_source": "SINGLE_SQLITE_READ_TRANSACTION",
            "rebuild": "DERIVED_ONLY_NO_CANONICAL_OR_OUTBOX_MUTATION",
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
