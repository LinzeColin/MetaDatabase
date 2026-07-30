from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_formal_runtime", ROOT / "tools" / "verify_formal_runtime.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

RELEASE_SPEC = importlib.util.spec_from_file_location(
    "run_release_oracles", ROOT / "tools" / "run_release_oracles.py"
)
RELEASE = importlib.util.module_from_spec(RELEASE_SPEC)
assert RELEASE_SPEC.loader is not None
sys.modules[RELEASE_SPEC.name] = RELEASE
RELEASE_SPEC.loader.exec_module(RELEASE)

SUBJECT_SPEC = importlib.util.spec_from_file_location(
    "formal_subject", ROOT / "tools" / "formal_subject.py"
)
SUBJECT = importlib.util.module_from_spec(SUBJECT_SPEC)
assert SUBJECT_SPEC.loader is not None
SUBJECT_SPEC.loader.exec_module(SUBJECT)


class FormalRuntimeVerifierTests(unittest.TestCase):
    def test_920_subject_hash_is_deterministic(self):
        self.assertEqual(MODULE._subject_sha256(), MODULE._subject_sha256())

    def test_921_component_receipt_is_integrity_bound(self):
        receipt = MODULE._component_report("tests", {"sample": {"status": "PASS"}})
        self.assertEqual(receipt["status"], "PASS")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tests.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            loaded = MODULE._load_component(path, "tests", MODULE._subject_sha256())
        self.assertEqual(loaded["report_sha256"], receipt["report_sha256"])

    def test_922_component_tamper_is_rejected(self):
        receipt = MODULE._component_report("tests", {"sample": {"status": "PASS"}})
        receipt["status"] = "FAIL"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tests.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._load_component(path, "tests", MODULE._subject_sha256())

    def test_923_component_subject_mismatch_is_rejected(self):
        receipt = MODULE._component_report("tests", {"sample": {"status": "PASS"}})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tests.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE._load_component(path, "tests", "0" * 64)

    def test_924_aggregate_requires_all_seven_bound_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in MODULE.COMPONENTS:
                receipt = MODULE._component_report(name, {name: {"status": "PASS"}})
                (root / f"{name}.json").write_text(json.dumps(receipt), encoding="utf-8")
            report = MODULE._aggregate(root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(set(report["component_receipts"]), set(MODULE.COMPONENTS))

    def test_925_aggregate_fails_closed_on_component_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in MODULE.COMPONENTS:
                status = "FAIL" if name == "isolation" else "PASS"
                receipt = MODULE._component_report(name, {name: {"status": status}})
                (root / f"{name}.json").write_text(json.dumps(receipt), encoding="utf-8")
            report = MODULE._aggregate(root)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("isolation", report["failed_checks"])

    def test_926_source_and_packaged_test_profiles_are_explicit(self):
        self.assertIn("tests.test_status_integration", MODULE.SOURCE_TEST_COMPONENT_MODULES["tests_cli_status"])
        self.assertNotIn("tests.test_status_integration", MODULE.PACKAGED_TEST_COMPONENT_MODULES["tests_cli_status"])
        self.assertIn("tests.test_governance", MODULE.SOURCE_TEST_COMPONENT_MODULES["tests_contracts"])
        self.assertNotIn("tests.test_governance", MODULE.PACKAGED_TEST_COMPONENT_MODULES["tests_contracts"])
        expected = (
            MODULE.SOURCE_TEST_COMPONENT_MODULES
            if MODULE._source_worktree_mode()
            else MODULE.PACKAGED_TEST_COMPONENT_MODULES
        )
        self.assertEqual(MODULE._active_test_component_modules(), expected)
        for values in expected.values():
            for module in values:
                relative = Path(*module.split(".")).with_suffix(".py")
                self.assertTrue((ROOT / relative).is_file(), module)

    def test_926_release_runner_forces_no_bytecode_mode(self):
        argv = RELEASE._python_argv([RELEASE.sys.executable, "-c", "print('ok')"])
        self.assertEqual(argv[1], "-B")

    def test_927_release_runner_has_bounded_timeout_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = RELEASE.run_once(
                "timeout_probe",
                [RELEASE.sys.executable, "-c", "import time; time.sleep(2)"],
                timeout=1,
                work_dir=Path(tmp),
            )
        self.assertEqual(row["status"], "FAIL")
        self.assertTrue(row["timed_out"])
        self.assertEqual(row["reason"], "TIMEOUT_1_SECONDS")

    def test_928_component_receipt_can_be_bound_to_precomputed_subject(self):
        expected = MODULE._subject_sha256()
        receipt = MODULE._component_report(
            "tests",
            {"sample": {"status": "PASS"}},
            expected_subject_sha256=expected,
        )
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["subject_sha256"], expected)

        mismatch = MODULE._component_report(
            "tests",
            {"sample": {"status": "PASS"}},
            expected_subject_sha256="0" * 64,
        )
        self.assertEqual(mismatch["status"], "FAIL")
        self.assertIn("subject_integrity", mismatch["failed_checks"])

    def test_929_release_component_workspace_preserves_subject_hash(self):
        expected = RELEASE._read_subject_hash(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            RELEASE._copy_workspace(ROOT, workspace, expected_subject_sha256=expected)
            self.assertEqual(RELEASE._read_subject_hash(workspace), expected)

    def test_929a_release_components_use_independent_workspaces(self):
        expected = RELEASE._read_subject_hash(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "workspaces"
            workspace_root.mkdir()
            workspaces = {}
            for component in RELEASE.COMPONENTS:
                workspace = workspace_root / component
                RELEASE._copy_workspace(ROOT, workspace, expected_subject_sha256=expected)
                workspaces[component] = workspace

            contaminated = workspaces["tests_contracts"] / "fixtures" / "unsafe_dataset_link.json"
            contaminated.symlink_to(workspaces["tests_contracts"] / "fixtures" / "dataset.json")
            try:
                self.assertTrue(contaminated.is_symlink())
                for component, workspace in workspaces.items():
                    if component == "tests_contracts":
                        continue
                    self.assertFalse((workspace / "fixtures" / "unsafe_dataset_link.json").exists())
                    self.assertEqual(RELEASE._read_subject_hash(workspace), expected)
            finally:
                contaminated.unlink(missing_ok=True)

    def test_930_aggregate_rejects_changed_canonical_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in MODULE.COMPONENTS:
                receipt = MODULE._component_report(name, {name: {"status": "PASS"}})
                (root / f"{name}.json").write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "subject changed"):
                MODULE._aggregate(root, expected_subject_sha256="0" * 64)

    def test_931_release_runner_terminates_all_registered_process_groups(self):
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name == "posix"),
        )
        RELEASE._register_process(process)
        try:
            cleaned = RELEASE._terminate_all_active()
            self.assertEqual(cleaned, 1)
            self.assertIsNotNone(process.poll())
            self.assertFalse(RELEASE._ACTIVE_PROCESSES)
        finally:
            if process.poll() is None:
                RELEASE._terminate_process(process)


    @unittest.skipUnless(os.name == "posix", "process group cleanup is a POSIX acceptance feature")
    def test_932_release_runner_kills_descendant_after_successful_parent_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "spawn_child.py"
            script.write_text(
                "import subprocess,sys\n"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                "print(p.pid,flush=True)\n",
                encoding="utf-8",
            )
            row = RELEASE.run_once(
                "successful_parent_with_descendant",
                [sys.executable, str(script)],
                timeout=10,
                work_dir=root,
            )
            self.assertEqual(row["status"], "PASS")
            child_pid = int(str(row["stdout_tail"]).strip())
            state = None
            for _ in range(20):
                stat_path = Path(f"/proc/{child_pid}/stat")
                if not stat_path.exists():
                    state = "ABSENT"
                    break
                fields = stat_path.read_text(encoding="utf-8").split()
                state = fields[2] if len(fields) > 2 else "UNKNOWN"
                if state == "Z":
                    break
                time.sleep(0.05)
            self.assertIn(state, {"ABSENT", "Z"})

    def test_932_finalize_report_writes_full_receipt_and_prints_bounded_summary(self):
        report = {"schema": "example.v1", "status": "PASS", "rows": []}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "receipt.json"
            stream = StringIO()
            with redirect_stdout(stream):
                RELEASE._finalize_report(report, output)
            written = json.loads(output.read_text(encoding="utf-8"))
            printed = json.loads(stream.getvalue())
        self.assertEqual(printed["schema"], "efs.release_oracles.operator_summary.v1")
        self.assertEqual(printed["status"], written["status"])
        self.assertEqual(printed["report_sha256"], written["report_sha256"])
        self.assertEqual(printed["output"], str(output))
        claimed = written.pop("report_sha256")
        canonical = json.dumps(written, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(claimed, RELEASE.hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    def test_933_runtime_source_integrity_rejects_duplicate_definitions_and_literal_keys(self):
        findings = MODULE._python_structure_findings(
            "def repeated():\n    return 1\n\ndef repeated():\n    return 2\nVALUE={'same': 1, 'same': 2}\n",
            "probe.py",
        )
        kinds = {item["kind"] for item in findings}
        self.assertIn("DUPLICATE_DEFINITION", kinds)
        self.assertIn("DUPLICATE_LITERAL_DICT_KEY", kinds)

    def test_934_runtime_strict_json_rejects_duplicate_and_noncanonical_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            MODULE.json.loads('{"same": 1, "same": 2}', object_pairs_hook=MODULE._strict_json_object)
        with self.assertRaisesRegex(ValueError, "noncanonical JSON key"):
            MODULE.json.loads('{"e\u0301": 1}', object_pairs_hook=MODULE._strict_json_object)

    def test_933_release_runner_unexpected_exception_emits_structured_fail_receipt(self):
        stream = StringIO()
        argv = ["run_release_oracles.py", "--determinism-iterations", "10000", "--fuzz-cases", "10000"]
        with mock.patch.object(RELEASE, "_read_subject_hash", side_effect=RuntimeError("synthetic failure")), \
             mock.patch.object(RELEASE.sys, "argv", argv), \
             redirect_stdout(stream):
            returncode = RELEASE.main()
        receipt = json.loads(stream.getvalue())
        self.assertEqual(returncode, 1)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["error_type"], "RuntimeError")
        self.assertEqual(receipt["message"], "synthetic failure")
        self.assertRegex(receipt["report_sha256"], r"^[0-9a-f]{64}$")


    def test_932_formal_subject_binds_exact_installed_skill_inventory(self):
        source_marker = ROOT / "taskpack_blueprint" / "skill_draft" / "equity-foresight-signal" / "SKILL.md"
        if source_marker.is_file():
            rows = SUBJECT.source_subject_rows(ROOT)
            expected = SUBJECT.source_subject_sha256(ROOT)
        else:
            rows = SUBJECT.packaged_subject_rows(ROOT)
            expected = SUBJECT.packaged_subject_sha256(ROOT)
        paths = {row["path"] for row in rows}
        self.assertEqual(MODULE._subject_sha256(), expected)
        self.assertIn("SKILL.md", paths)
        self.assertIn("agents/openai.yaml", paths)
        self.assertIn("tools/formal_subject.py", paths)
        self.assertNotIn("governance/p80_contract.json", paths)
        self.assertNotIn("tests/test_formal_packaging.py", paths)



if __name__ == "__main__":
    unittest.main()
