import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class PreparationToolsTest(unittest.TestCase):
    def test_single_human_document_source(self):
        self.assertTrue((ROOT / "machine/facts/human_documents.json").is_file())
        self.assertFalse((ROOT / "machine/facts/human_docs.json").exists())

    def test_memory_reconciliation_exists(self):
        text = (ROOT / "MEMORY_RECONCILIATION.md").read_text()
        for heading in ("ACTIVE", "SUPERSEDED", "CONFLICT", "UNVERIFIED"):
            self.assertIn(heading, text)

    def test_builder_readiness_static(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "receipt.json"
            completed = subprocess.run([
                "python3", str(ROOT / "scripts/builder_readiness_static.py"),
                "--root", str(ROOT), "--output", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = json.loads(output.read_text())
            recorded = data.pop("receipt_sha256")
            self.assertEqual(recorded, hashlib.sha256(canonical(data)).hexdigest())
            self.assertEqual(data["state"], "PASS")
            self.assertTrue(data["formal_fresh_builder_simulation_required"])
            self.assertFalse(data["developer_research_required"])

    def test_build_agent_skill_allowlist(self):
        data = json.loads((ROOT / "machine/facts/build_agent_skill_allowlist.json").read_text())
        allowed = {row["slug"] for row in data["allowed"]}
        forbidden = set(data["forbidden"])
        self.assertFalse(allowed & forbidden)
        self.assertTrue({"teleiosis", "persona-distiller-group", "verifier"}.issubset(forbidden))
        self.assertFalse(data["runtime_agent_allowed"])
        self.assertFalse(data["runtime_llm_allowed"])

    def test_browser_smoke_script_syntax(self):
        compile((ROOT / "scripts/browser_smoke.py").read_text(), "browser_smoke.py", "exec")

    def test_prebuild_script_syntax(self):
        compile((ROOT / "scripts/prebuild.py").read_text(), "prebuild.py", "exec")

    def test_package_guard_is_source_path_independent(self):
        text = (ROOT / "scripts/verify_package.py").read_text()
        self.assertNotIn("from signal_lattice.constants import VERSION", text)
        self.assertIn("pyproject.toml", text)

    def test_package_guard_rejects_option_like_paths(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("verify_package", ROOT / "scripts/verify_package.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(module.unsafe_path_reason("--help"), "LEADING_DASH_COMPONENT")
        self.assertEqual(module.unsafe_path_reason("nested/-output.json"), "LEADING_DASH_COMPONENT")
        self.assertEqual(module.unsafe_path_reason("normal/path.json"), None)

    def test_package_guard_validates_receipt_hashes_and_artifact_refs(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("verify_package_receipts", ROOT / "scripts/verify_package.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            artifact = root / "artifact.txt"
            artifact.write_text("ok")
            body = {
                "state": "PASS",
                "artifact_sha256": {"artifact.txt": hashlib.sha256(b"ok").hexdigest()},
            }
            body["receipt_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
            (root / "evidence/receipt.json").write_text(json.dumps(body))
            findings = []
            module.validate_evidence_receipts(root, findings)
            self.assertEqual(findings, [])
            artifact.write_text("changed")
            findings = []
            module.validate_evidence_receipts(root, findings)
            self.assertTrue(any(item.startswith("EVIDENCE_ARTIFACT_HASH_MISMATCH") for item in findings))
            artifact.write_text("ok")
            local = root / "evidence/local.txt"
            local.write_text("local")
            local_body = {"state": "PASS", "artifact_sha256": {"local.txt": hashlib.sha256(b"local").hexdigest()}}
            local_body["receipt_sha256"] = hashlib.sha256(canonical(local_body)).hexdigest()
            (root / "evidence/local_receipt.json").write_text(json.dumps(local_body))
            findings = []
            module.validate_evidence_receipts(root, findings)
            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()

class TaskValidationTest(unittest.TestCase):
    def test_validate_all_tasks(self):
        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/run_task.py"), "--validate-all"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        data = json.loads(completed.stdout)
        self.assertEqual(data["state"], "PASS")
        self.assertEqual(data["task_count"], 30)

    def test_prebuild_uses_ephemeral_install_root(self):
        text = (ROOT / "scripts/prebuild.py").read_text()
        self.assertIn('"SIGNAL_LATTICE_INSTALL_ROOT": str(install_root)', text)
        self.assertNotIn('install_env = os.environ.copy()', text)

class SystemdVerificationTest(unittest.TestCase):
    def test_systemd_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "systemd.json"
            completed = subprocess.run(
                ["python3", str(ROOT / "scripts/verify_systemd.py"), "--root", str(ROOT), "--output", str(output)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = json.loads(output.read_text())
            self.assertEqual(data["state"], "PASS")
            self.assertEqual(data["unit_count"], 13)
            self.assertEqual(data["macos_launchd_units"], 0)
            self.assertIn(data["systemd_analyze_state"], {"EXECUTED_PASS", "STATIC_FALLBACK_NON_TARGET_HOST"})
            if data["systemd_analyze_state"] == "STATIC_FALLBACK_NON_TARGET_HOST":
                self.assertFalse(data["systemd_analyze_available"])
                self.assertTrue(data["target_runtime_verification_required"])
