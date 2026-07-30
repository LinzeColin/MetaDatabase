from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_assurance_004_acceptance import (
    BENCHMARK_SCALES,
    EXPECTED_ACCEPTANCES,
    EXPECTED_EXECUTION,
    MEMORY_CEILING_BYTES,
    SEED_COUNT,
    _benchmark_rebuild_scale,
    _campaign_parser,
    _critical_seed_matrix,
    _environment,
    _load_sink_tests,
)


class Assurance004Tests(unittest.TestCase):
    def test_equivalent_campaign_commands_are_explicitly_scoped_to_mvp_suite(self) -> None:
        parser = _campaign_parser()
        chaos = parser.parse_args(["chaos", "run", "--suite", "mvp"])
        benchmark = parser.parse_args(["benchmark", "--suite", "mvp"])
        self.assertEqual((chaos.command, chaos.chaos_command, chaos.suite), ("chaos", "run", "mvp"))
        self.assertEqual((benchmark.command, benchmark.suite), ("benchmark", "mvp"))

    def test_critical_matrix_runs_each_defined_core_boundary_for_ten_seeds(self) -> None:
        report = _critical_seed_matrix()
        self.assertEqual(report["seeds_per_critical_scenario"], SEED_COUNT)
        self.assertEqual(report["total_seeded_runs"], SEED_COUNT)
        self.assertGreaterEqual(report["critical_scenarios"], 6)
        self.assertEqual(report["journal_stage_injections"], SEED_COUNT * 10)
        self.assertEqual(report["canonical_loss"], 0)
        self.assertEqual(report["duplicate_notion_pages"], 0)
        self.assertEqual(report["persistence_findings"], 0)
        self.assertEqual(report["unauthorized_deletes"], 0)

    def test_small_real_sqlite_markdown_rebuild_is_idempotent_and_memory_bounded(self) -> None:
        report = _benchmark_rebuild_scale(_load_sink_tests(), 20)
        self.assertEqual(report["items"], 20)
        self.assertEqual(report["content_writes_first"], 20)
        self.assertEqual(report["content_writes_second"], 0)
        self.assertLessEqual(report["peak_tracemalloc_bytes"], MEMORY_CEILING_BYTES)

    def test_public_receipt_retains_direct_mvp_boundary(self) -> None:
        self.assertEqual(
            tuple(EXPECTED_ACCEPTANCES),
            (
                "ACC.x2n.ext.002",
                "ACC.x2n.xhs.003",
                "ACC.x2n.media.002",
                "ACC.x2n.notion.002",
                "ACC.x2n.notion.003",
                "ACC.x2n.ops.001",
                "ACC.x2n.rel.004",
                "ACC.x2n.rel.005",
            ),
        )
        self.assertEqual(BENCHMARK_SCALES, (20, 80, 1_000, 10_000))
        self.assertEqual(EXPECTED_EXECUTION["platform_calls"], 0)
        self.assertEqual(EXPECTED_EXECUTION["runtime_deployment"], "NOT_RUN")

    def test_campaign_environment_is_allowlisted_without_token_surface(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a004-env-") as temporary:
            environment = _environment(Path(temporary))
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("GH_TOKEN", environment)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")


if __name__ == "__main__":
    unittest.main()
