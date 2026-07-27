from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_macos_zero_footprint", ROOT / "tools" / "verify_macos_zero_footprint.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MacOSZeroFootprintTests(unittest.TestCase):
    def test_zero_persistent_local_footprint_and_no_launchd(self):
        report = MODULE.verify()
        self.assertEqual(report["status"], "PASS", report)
        self.assertFalse(report["macos_runtime_install_permitted"])
        self.assertEqual(report["macos_launchd_entries"], 0)
        self.assertEqual(report["local_persistent_files_after_invocation"], 0)
        self.assertEqual(report["local_persistent_bytes_after_invocation"], 0)
        self.assertEqual(report["resident_background_processes_after_invocation"], 0)
        self.assertEqual(report["agent_invocations_total"], 0)
        self.assertEqual(report["llm_requests_total"], 0)

    def test_release_verifiers_disable_bytecode_cache(self):
        formal = (ROOT / "tools" / "verify_formal_runtime.py").read_text(encoding="utf-8")
        release = (ROOT / "tools" / "run_release_oracles.py").read_text(encoding="utf-8")
        skill_path = ROOT / "SKILL.md"
        if not skill_path.is_file():
            skill_path = (
                ROOT
                / "taskpack_blueprint"
                / "skill_draft"
                / "equity-foresight-signal"
                / "SKILL.md"
            )
        skill_contract = skill_path.read_text(encoding="utf-8")
        self.assertNotIn("compileall", formal)
        self.assertIn("PYTHONDONTWRITEBYTECODE", formal)
        self.assertIn("PYTHONDONTWRITEBYTECODE", release)
        self.assertIn('"-B"', release)
        self.assertIn("REMOTE_HOST_EMBEDDED_ONLY", skill_contract)
        self.assertIn("launchd", skill_contract)

        # The source/release workspace has operator landing instructions, while
        # the installed Skill subpackage intentionally does not duplicate them.
        landing_path = ROOT / "CODEX_LANDING_INSTRUCTIONS.md"
        if landing_path.is_file():
            for line in landing_path.read_text(encoding="utf-8").splitlines():
                if "python3" in line and "`" in line:
                    self.assertIn("python3 -B", line)


if __name__ == "__main__":
    unittest.main()
