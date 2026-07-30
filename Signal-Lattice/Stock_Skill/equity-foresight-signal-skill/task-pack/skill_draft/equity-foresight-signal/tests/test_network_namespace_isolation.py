from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_network_namespace_isolation",
    ROOT / "tools" / "run_network_namespace_isolation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class NetworkNamespaceIsolationTests(unittest.TestCase):
    def test_822_contract_is_explicit(self):
        self.assertEqual(MODULE.SCHEMA, "efs.network_namespace_isolation_execution.v1")
        self.assertIn(MODULE.errno.ENETUNREACH, MODULE.EXPECTED_NETWORK_ERRNOS)

    def test_823_worker_result_is_integrity_bound(self):
        result = MODULE._worker()
        claimed = result.pop("worker_sha256")
        self.assertEqual(MODULE.sha256_hex(result), claimed)
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)


if __name__ == "__main__":
    unittest.main()
