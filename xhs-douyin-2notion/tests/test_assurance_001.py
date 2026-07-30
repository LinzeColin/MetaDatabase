from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (PROJECT_ROOT / "apps/companion/src", PROJECT_ROOT / "packages/contracts/src", PROJECT_ROOT / "scripts/ci"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from x2n_companion import runtime_cli  # noqa: E402
from x2n_companion.migrations import LATEST_SCHEMA_VERSION  # noqa: E402

import run_lane as LANE  # noqa: E402


def _load_acceptance_runner() -> object:
    spec = importlib.util.spec_from_file_location(
        "run_assurance_001_acceptance",
        PROJECT_ROOT / "scripts/run_assurance_001_acceptance.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Assurance001Tests(unittest.TestCase):
    def test_runtime_init_reports_the_current_schema_without_a_stale_browser_constant(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a001-runtime-cli-") as value:
            destination = Path(value) / "MediaCrawler"
            destination.mkdir(mode=0o700)
            environment = {
                "X2N_DATA_ROOT": str(destination / "xhs-douyin-2notion"),
                "X2N_DOWNLOAD_DESTINATION": str(destination),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                receipt = runtime_cli.run(runtime_cli.build_parser().parse_args(["init"]))
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["schema_version"], LATEST_SCHEMA_VERSION)
        self.assertEqual(receipt["latest_schema_version"], LATEST_SCHEMA_VERSION)

    def test_current_lane_runs_current_tests_and_replays_history_only_in_full_scope(self) -> None:
        base = {label: command for label, command, _timeout in LANE._base_commands()}
        full = {label: command for label, command, _timeout in LANE._full_commands()}
        self.assertIn("assurance_unit", base)
        self.assertIn("test_assurance_001.py", base["assurance_unit"])
        self.assertIn("extension_self_test", base)
        self.assertIn("historical_stage5_review", full)
        self.assertIn("scripts/replay_stage_5_review_historical.py", full["historical_stage5_review"])

    def test_critical_mutation_catalog_requires_two_independent_kills(self) -> None:
        runner = _load_acceptance_runner()
        identifiers = {item.identifier for item in runner.MUTATION_CASES}
        self.assertEqual(
            identifiers,
            {"migration_requires_verified_backup", "request_ledger_replay_disposition"},
        )


if __name__ == "__main__":
    unittest.main()
