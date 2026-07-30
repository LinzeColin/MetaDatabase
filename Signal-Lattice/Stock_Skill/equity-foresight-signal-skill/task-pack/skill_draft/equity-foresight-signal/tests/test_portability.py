from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from equity_foresight_signal import build_golden_vector, verify_golden_vector
from equity_foresight_signal.canonical import sha256_hex
from equity_foresight_signal.errors import EFSError

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class PortabilityGoldenTests(unittest.TestCase):
    def kwargs(self):
        return {
            "bundle": load("bundle.json"),
            "request": load("request.json"),
            "pit_dataset": load("pit_dataset.json"),
            "training_config": load("training_config.json"),
        }

    def test_501_frozen_golden_vector_passes(self):
        report = verify_golden_vector(load("golden_vector.json"), **self.kwargs())
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["claim_boundary"]["cross_python_matrix_proven"])

    def test_502_build_is_deterministic(self):
        self.assertEqual(build_golden_vector(**self.kwargs()), build_golden_vector(**self.kwargs()))

    def test_503_vector_tamper_rejected(self):
        vector = load("golden_vector.json")
        vector["expected_hashes"]["forecast_result_sha256"] = "0" * 64
        with self.assertRaisesRegex(EFSError, "HASH_MISMATCH"):
            verify_golden_vector(vector, **self.kwargs())

    def test_504_changed_request_is_reported_fail(self):
        kwargs = self.kwargs()
        kwargs["request"] = copy.deepcopy(kwargs["request"])
        kwargs["request"]["request_id"] = "changed_request"
        report = verify_golden_vector(load("golden_vector.json"), **kwargs)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["checks"]["request_input"])

    def test_505_hash_seed_processes_match(self):
        code = '''
import json
from pathlib import Path
from equity_foresight_signal import verify_golden_vector
root=Path(r"%s")
def load(name): return json.loads((root/"fixtures"/name).read_text())
r=verify_golden_vector(load("golden_vector.json"),bundle=load("bundle.json"),request=load("request.json"),pit_dataset=load("pit_dataset.json"),training_config=load("training_config.json"))
print(r["report_sha256"])
''' % ROOT
        outputs = set()
        for seed in ("0", "1", "7", "123", "999"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            env["PYTHONPATH"] = str(ROOT)
            outputs.add(subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=env, text=True).strip())
        self.assertEqual(len(outputs), 1)

    def test_506_zero_agent_token_network(self):
        report = verify_golden_vector(load("golden_vector.json"), **self.kwargs())
        self.assertEqual(report["agent_invocations_total"], 0)
        self.assertEqual(report["llm_requests_total"], 0)
        self.assertEqual(report["network_requests_total"], 0)

    def test_507_nested_golden_vector_shapes_fail_as_controlled_errors(self):
        for key in ("input_hashes", "expected_hashes", "claim_boundary"):
            for malformed in (None, 1, [], {}):
                vector = load("golden_vector.json")
                vector[key] = malformed
                vector.pop("vector_sha256")
                vector["vector_sha256"] = sha256_hex(vector)
                with self.subTest(key=key, malformed=type(malformed).__name__):
                    with self.assertRaises(EFSError):
                        verify_golden_vector(vector, **self.kwargs())


if __name__ == "__main__":
    unittest.main()
