from __future__ import annotations

import json
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
            [os.sys.executable, str(self.root / "scripts/verify_northstar_repair_authorization.py"), "--receipt", str(self.root / "evidence/repair/northstar_repair_authorization.json"), "--version", "0.0.0.1.41"],
            env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_audit_does_not_hide_other_forbidden_processes(self):
        text = (self.root / "scripts/runtime_audit.py").read_text(encoding="utf-8")
        self.assertIn('if "runtime_audit.py" in lowered', text)
        self.assertNotIn("and 'runtime_audit.py' not in text", text)
        self.assertIn("signal-lattice-cloudflared.service", text)

    def test_deploy_creates_required_status_evidence_aliases(self):
        text = (self.root / "scripts/deploy_northstar.sh").read_text(encoding="utf-8")
        self.assertIn('ARTIFACTS/release.json', text)
        self.assertIn('cloudflare_tunnel_install.json', text)
        self.assertNotIn('lib/python3.11/site-packages', text)

    def test_source_registry_has_all_six_peer_sources(self):
        data = json.loads((self.root / "config/source_registry.json").read_text(encoding="utf-8"))
        ids = {row["skill_id"] for row in data["sources"]}
        self.assertEqual(ids, {
            "stock-commercial-opportunities", "bottleneck-serenity-skill", "equity-foresight-signal",
            "global-equity-lead-lag-atlas", "equity-event-atlas", "serenity-skill",
        })


if __name__ == "__main__":
    unittest.main()
