from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_assurance_005_source_lane",
    PROJECT_ROOT / "scripts/verify_assurance_005_source_lane.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


def _report() -> dict[str, object]:
    return {
        "blocking_commands": len(VERIFY.EXPECTED_GATES),
        "blocking_executions": len(VERIFY.EXPECTED_GATES),
        "blocking_failures": 0,
        "blocking_repetitions": 1,
        "blocking_results": [
            {
                "blocking": True,
                "gate": gate,
                "label": f"{gate}_r1",
                "repetition": 1,
                "status": "PASS",
            }
            for gate in VERIFY.EXPECTED_GATES
        ],
        "explicit_nonblocking_skips": 0,
        "flaky_blocking_tests": 0,
        "lane": "fast",
        "model_calls": 0,
        "platform_calls": 0,
        "real_accounts": 0,
        "remote_github_actions": "NOT_RUN_LOCAL_BASELINE",
        "silent_blocking_skips": 0,
        "stage_gate_evaluation": "NOT_PERFORMED_BY_SOFTWARE_LANE",
        "status": "PASS",
        "toolchain": {"actual": VERIFY.EXPECTED_TOOLCHAIN},
    }


class Assurance005SourceLaneTests(unittest.TestCase):
    def test_lane_report_requires_each_current_blocking_gate_and_zero_external_execution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a005-source-lane-") as directory:
            report_path = Path(directory) / "lane.json"
            report_path.write_text(json.dumps(_report()), encoding="utf-8")
            lane = VERIFY.validate_lane_report(report_path)
            self.assertEqual(lane["gates"], VERIFY.EXPECTED_GATES)
            self.assertEqual(lane["blocking_executions"], 9)

            changed = copy.deepcopy(_report())
            changed["platform_calls"] = 1
            report_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(VERIFY.SourceLaneError):
                VERIFY.validate_lane_report(report_path)

    def test_evidence_payload_is_aggregate_only_and_not_a_go_live_claim(self) -> None:
        lane = {
            "blocking_executions": 9,
            "gates": VERIFY.EXPECTED_GATES,
            "report_sha256": "a" * 64,
            "toolchain": VERIFY.EXPECTED_TOOLCHAIN,
        }
        evidence = VERIFY._build_evidence(lane)
        self.assertEqual(evidence["task_id"], "TSK.x2n.assurance.005")
        self.assertEqual(evidence["release_claim"], "SOURCE_LANE_ONLY_NO_OWNER_RUNTIME_CAPTURE_OR_GO_LIVE")
        self.assertEqual(evidence["execution"]["platform_calls"], 0)
        self.assertNotIn("/" + "Users/", json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
