import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from signal_lattice.status import default_matrix, reconcile


ROOT = Path(__file__).resolve().parents[1]


class T(unittest.TestCase):
    def test_shape(self):
        matrix = default_matrix()
        result = reconcile(matrix)
        self.assertEqual(result["line_count"], 13)
        self.assertEqual(result["cell_count"], 117)
        self.assertEqual(result["state"], "PASS")

    def test_target_requires_measurement(self):
        self.assertEqual(reconcile(default_matrix(), target=True)["state"], "BLOCKED")

    def test_target_pass(self):
        matrix = default_matrix("TARGET_ENVIRONMENT")
        for line in matrix["lines"]:
            for cell in line["cells"]:
                cell["measured"] = True
                cell["evidence_ref"] = "sha256:x"
                cell["state"] = "PASS"
        self.assertEqual(reconcile(matrix, target=True)["state"], "PASS")

    def test_installed_release_receipt_is_accepted_as_code_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            output_dir = root / "status-evidence"
            summary = root / "summary.json"
            artifacts.mkdir()
            names = {
                "release.json", "local_health.json", "systemd_install.json",
                "cloudflare_tunnel_install.json", "runtime_audit.json",
                "public_release.json", "source_sync.json", "status_snapshot.json",
                "target_backup_recovery.json",
            }
            for name in names:
                state = "INSTALLED" if name == "release.json" else "PASS"
                (artifacts / name).write_text(json.dumps({"state": state}))
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts/generate_status_evidence.py"),
                    "--artifact-dir", str(artifacts), "--output-dir", str(output_dir),
                    "--summary", str(summary),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(summary.read_text())
            self.assertEqual(receipt["state"], "PASS")
            self.assertEqual(receipt["degraded_count"], 0)
