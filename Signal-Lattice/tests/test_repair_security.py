from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RepairSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.env = {**os.environ, "PYTHONPATH": str(cls.root / "src")}

    def test_repair_authorization_is_self_hashed_and_scoped(self):
        result = subprocess.run(
            [os.sys.executable, str(self.root / "scripts/verify_northstar_repair_authorization.py"), "--receipt", str(self.root / "evidence/repair/northstar_repair_authorization.json"), "--version", "0.0.0.1.40"],
            env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_audit_does_not_hide_other_forbidden_processes(self):
        text = (self.root / "scripts/runtime_audit.py").read_text(encoding="utf-8")
        self.assertIn('if "runtime_audit.py" in lowered', text)
        self.assertIn("external_forbidden_process_matches", text)
        self.assertIn("external_agent_process_count", text)
        self.assertIn("signal-lattice-cloudflared.service", text)

    def test_runtime_audit_separates_signal_lattice_and_external_host_processes(self):
        spec = importlib.util.spec_from_file_location("runtime_audit", self.root / "scripts" / "runtime_audit.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertTrue(module.is_signal_lattice_process("1 python /opt/signal-lattice/current/bin", ""))
        self.assertTrue(module.is_signal_lattice_process("1 python worker", "signal-lattice-api.service"))
        self.assertFalse(module.is_signal_lattice_process("1 codex worker", "cyberboss-cloud.service"))
        record = module.process_record("42 codex --opaque-argument", "codex", False)
        self.assertEqual(record["scope"], "external-host")
        self.assertNotIn("line", record)

    def test_deploy_creates_required_status_evidence_aliases(self):
        text = (self.root / "scripts/deploy_northstar.sh").read_text(encoding="utf-8")
        self.assertIn('ARTIFACTS/release.json', text)
        self.assertIn('cloudflare_tunnel_install.json', text)
        self.assertNotIn('lib/python3.11/site-packages', text)

    def test_release_installer_relocates_direct_and_shell_wrapped_entrypoints(self):
        text = (self.root / "scripts/install_release.sh").read_text(encoding="utf-8")
        self.assertIn('raw.count(temporary_bin) != 1', text)
        self.assertIn('raw.replace(temporary_bin, release_bin)', text)

    def test_same_version_repair_binds_the_release_payload_digest(self):
        text = (self.root / "scripts/install_release.sh").read_text(encoding="utf-8")
        self.assertIn('RELEASE_PAYLOAD_SHA=', text)
        self.assertIn('release_payload_sha256', text)
        self.assertIn('repair-${WHEEL_SHA}-${RELEASE_PAYLOAD_SHA}', text)

    def test_status_closure_uses_release_venv_when_installed(self):
        text = (self.root / "scripts/status_closure.sh").read_text(encoding="utf-8")
        self.assertIn('"$ROOT/venv/bin/python"', text)
        self.assertIn('PYTHON_BIN="python3"', text)

    def test_source_registry_has_all_six_peer_sources(self):
        data = json.loads((self.root / "config/source_registry.json").read_text(encoding="utf-8"))
        ids = {row["skill_id"] for row in data["sources"]}
        self.assertEqual(ids, {
            "stock-commercial-opportunities", "bottleneck-serenity-skill", "equity-foresight-signal",
            "global-equity-lead-lag-atlas", "equity-event-atlas", "serenity-skill",
        })

    def test_stock_sources_use_the_canonical_nested_stock_skill_path(self):
        data = json.loads((self.root / "config/source_registry.json").read_text(encoding="utf-8"))
        stock_rows = [row for row in data["sources"] if row["skill_id"] != "serenity-skill"]
        self.assertEqual(len(stock_rows), 5)
        for row in stock_rows:
            self.assertIn("/Signal-Lattice/Stock_Skill/", row["url"])
            self.assertTrue(row["url"].endswith("/README.md"))


if __name__ == "__main__":
    unittest.main()
