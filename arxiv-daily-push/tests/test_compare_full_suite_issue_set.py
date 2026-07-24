from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPARATOR = ROOT / "tools" / "compare_full_suite_issue_set.py"


def load_comparator():
    spec = importlib.util.spec_from_file_location("compare_full_suite_issue_set", COMPARATOR)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load comparator: {COMPARATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FullSuiteIssueSetComparatorTests(unittest.TestCase):
    def test_subtest_failure_is_parsed_and_keeps_baseline_key_compatibility(self) -> None:
        log = """\
FAIL: test_plain (pkg.Tests.test_plain)
FAIL: test_owner_sync (pkg.Tests.test_owner_sync) (page='README.md')
Ran 2 tests in 0.001s
FAILED (failures=2, errors=0, skipped=0)
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner.log"
            path.write_text(log, encoding="utf-8")
            parsed = load_comparator().parse_unittest_log(path)

        self.assertEqual(parsed["summary"]["parsed_failures"], 2)
        self.assertTrue(parsed["summary"]["issue_count_match"])
        self.assertEqual(
            [item["key"] for item in parsed["issues"]],
            [
                "FAILURE|pkg.Tests.test_plain|test_plain",
                "FAILURE|pkg.Tests.test_owner_sync|test_owner_sync|(page='README.md')",
            ],
        )


if __name__ == "__main__":
    unittest.main()
