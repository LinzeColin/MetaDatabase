from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_phase_0_2", PROJECT_ROOT / "scripts/verify_phase_0_2.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Phase02Tests(unittest.TestCase):
    def test_core_checks_pass(self) -> None:
        checks = VERIFY.run_core_checks()
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_all_candidates_are_exact_and_disabled(self) -> None:
        registry = json.loads((PROJECT_ROOT / "machine/facts/upstream_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["actual_runtime_dependencies"], [])
        for repository in registry["repositories"]:
            self.assertRegex(repository["selected_commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(repository["selected_commit"], repository["observed_main_commit"])
            self.assertFalse(repository["integration"]["enabled"])
            self.assertFalse(repository["integration"]["bundled"])
            self.assertFalse(repository["integration"]["runtime_dependency"])

    def test_license_and_distribution_gates_fail_closed(self) -> None:
        registry = json.loads((PROJECT_ROOT / "machine/facts/upstream_registry.json").read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in registry["repositories"]}
        self.assertEqual(by_id["xiaohongshu-exporter"]["license"]["verification"], "unverified_missing_license_file")
        self.assertFalse(by_id["xiaohongshu-exporter"]["license"]["code_copy_allowed"])
        self.assertEqual(by_id["douyin-downloader"]["license"]["spdx"], "MIT")
        self.assertFalse(by_id["douyin-downloader"]["dependency_state"]["reproducible_environment"])
        self.assertEqual(by_id["MediaCrawler"]["license"]["spdx"], "LicenseRef-NON-COMMERCIAL-LEARNING-1.1")
        self.assertFalse(by_id["MediaCrawler"]["integration"]["core_dependency"])

    def test_sbom_matches_zero_actual_runtime_dependencies(self) -> None:
        sbom = json.loads((PROJECT_ROOT / "machine/sbom/stage_0_phase_0_2.cdx.json").read_text(encoding="utf-8"))
        self.assertEqual(sbom["dependencies"], [{"ref": "x2n@v0.0.0.1", "dependsOn": []}])
        properties = {item["name"]: item["value"] for item in sbom["metadata"]["properties"]}
        self.assertEqual(properties["x2n:actual-runtime-dependency-count"], "0")
        for component in sbom["components"]:
            values = {item["name"]: item["value"] for item in component.get("properties", [])}
            self.assertEqual(values["x2n:actual-runtime"], "false")

    def test_adapter_acceptance_is_not_overstated(self) -> None:
        state = json.loads((PROJECT_ROOT / "machine/facts/task_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["acceptance_status"]["ACC.x2n.dy.003"], "baseline_pass_downstream_not_run")
        self.assertFalse(state["next_phase_authorized"])
        self.assertFalse(state["stage_1_authorized"])
        self.assertEqual(state["stage_gate"], "blocked_owner_action")
        self.assertEqual(state["remote_upload"], "forbidden_until_g0_pass")

    def test_private_source_snapshots_when_explicitly_supplied(self) -> None:
        value = os.environ.get("X2N_UPSTREAM_SNAPSHOT_ROOT")
        if not value:
            self.skipTest("private source snapshots are intentionally absent in public CI")
        check = VERIFY.validate_source_snapshots(Path(value))
        self.assertEqual(check.status, "PASS")


if __name__ == "__main__":
    unittest.main()
