import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class T(unittest.TestCase):
    def test_baseline_is_current_and_fail_closed(self):
        baseline = json.loads((ROOT / "machine/facts/upstream_baseline.json").read_text())
        self.assertEqual(baseline["agent_database"]["skill_instance_count"], 100)
        self.assertEqual(baseline["agent_database"]["unique_slug_count"], 84)
        self.assertEqual(baseline["meta_database"]["stock_skill_count"], 5)
        self.assertFalse(baseline["runtime_upstream_write_allowed"])

    def test_missing_checkouts_create_hashed_blocked_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "upstream_precheck.json"
            completed = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/build_upstream_precheck.py"),
                    "--root",
                    str(ROOT),
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 2)
            receipt = json.loads(output.read_text())
            recorded = receipt.pop("receipt_sha256")
            self.assertEqual(recorded, hashlib.sha256(canonical(receipt)).hexdigest())
            self.assertEqual(receipt["state"], "BLOCKED")
            self.assertEqual(receipt["reason_code"], "FIXED_UPSTREAM_INPUT_UNAVAILABLE")
            self.assertFalse(receipt["upstream_write_allowed"])
            self.assertFalse(receipt["developer_research_required"])
            self.assertFalse(receipt["formal_seal_present"])
            self.assertEqual(len(receipt["required_sources"]), 2)
            self.assertIn("VERIFIED_EXACT_OFFLINE_GIT_BUNDLE", receipt["accepted_inputs"])
            self.assertTrue(
                all(row["reason"] == "FIXED_CHECKOUT_NOT_PROVIDED" for row in receipt["repositories"])
            )

    def test_formal_seal_if_present(self):
        path = ROOT / "evidence/upstream/upstream_seal.json"
        if not path.exists():
            self.skipTest("Formal upstream seal requires exact fixed checkouts or bundles")
        data = json.loads(path.read_text())
        recorded = data.pop("receipt_sha256")
        self.assertEqual(recorded, hashlib.sha256(canonical(data)).hexdigest())
        baseline = json.loads((ROOT / "machine/facts/upstream_baseline.json").read_text())
        self.assertEqual(data["state"], "PASS")
        self.assertEqual(data["skill_instance_count"], baseline["agent_database"]["skill_instance_count"])
        self.assertEqual(data["unique_slug_count"], baseline["agent_database"]["unique_slug_count"])
        self.assertEqual(data["stock_skill_count"], baseline["meta_database"]["stock_skill_count"])
        self.assertFalse(data["upstream_write_allowed"])
