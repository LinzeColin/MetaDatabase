#!/usr/bin/env python3
"""Run the public-safe Adapters001 Profile/session acceptance matrix."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

TASK_ID = "TSK.x2n.adapters.001"
PHASE = "PH.X2N.3.1"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/profile_session/fixture_manifest.json"


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_001_tests",
        PROJECT_ROOT / "apps/companion/tests/test_profile_session.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters001 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Adapters001 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("fixture_id") != "FIXTURE.X2N.S03.A001.001" or fixture.get("synthetic") is not True:
        raise AssertionError("Adapters001 fixture identity drifted")
    for field in (
        "contains_accounts",
        "contains_cookies",
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_profile_paths",
    ):
        if fixture.get(field) is not False:
            raise AssertionError(f"Adapters001 fixture privacy boundary drifted: {field}")
    sessions = fixture.get("session_cases")
    batches = fixture.get("batch_cases")
    if not isinstance(sessions, list) or len(sessions) != 7 or not isinstance(batches, list) or len(batches) != 7:
        raise AssertionError("Adapters001 fixture matrix is incomplete")
    non_authoritative = [item for item in batches if item.get("outcome") != "complete_success"]
    if len(non_authoritative) != 5 or any(item.get("expected_removed") != 0 for item in batches):
        raise AssertionError("Batch deletion oracle drifted")
    if [item.get("expected_tombstone_candidates") for item in batches[-2:]] != [0, 1]:
        raise AssertionError("Two-complete-success candidate oracle drifted")
    return {
        "acceptance_scope": "ADAPTERS_001_PROFILE_SESSION_CI_SYNTH",
        "batch_cases": len(batches),
        "complete_successes_required_for_candidate": 2,
        "fixture_id": fixture["fixture_id"],
        "non_authoritative_batch_cases": len(non_authoritative),
        "owner_canary": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "physical_delete_cases": fixture.get("physical_delete_cases"),
        "platform_calls": 0,
        "profile_path_findings": 0,
        "real_account_execution": "NOT_RUN",
        "removed_relations": 0,
        "session_cases": len(sessions),
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "unit_suite": _run_unit_suite(),
    }


def main() -> int:
    try:
        payload = run()
    except Exception as error:
        print(
            json.dumps(
                {"reason": str(error), "status": "FAIL_CLOSED", "task_id": TASK_ID},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
