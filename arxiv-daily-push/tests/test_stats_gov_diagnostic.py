from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from arxiv_daily_push.owner_controls import load_owner_controls, render_owner_documents


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "tools" / "verify_stats_gov_diagnostic.mjs"
WORKER = ROOT / "deploy" / "cloudflare" / "worker_cloud.js"
REGISTRY = ROOT / "config" / "cloudflare_source_candidates_v1_2.json"
DIAGNOSIS_RECEIPT = ROOT / "machine" / "runs" / "ADP-V12-S2-T001-diagnosis.json"
CONTROLS = ROOT / "config" / "owner_controls.yaml"
OWNER_PAGES = (
    ROOT / "用户中心" / "数据源与板块健康.md",
    ROOT / "用户中心" / "README.md",
    ROOT / "用户中心" / "一看三查.md",
    ROOT / "用户中心" / "关键结论与用户决策.md",
    ROOT / "docs" / "owner" / "SOURCE_CATALOG.md",
    ROOT / "docs" / "HANDOFF.md",
)


class StatsGovDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["node", str(VERIFY)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        cls.verifier_returncode = result.returncode
        cls.verifier_stderr = result.stderr
        cls.report = json.loads(result.stdout)

    def scenario(self, name: str) -> dict:
        return self.report["scenarios"][name]

    def test_TST_V12_STATS_CLASSIFICATION_is_exact_and_mutually_distinct(self) -> None:
        classifications = self.report["classifications"]
        self.assertEqual(
            classifications,
            {
                "edge_timeout": "EDGE_TIMEOUT",
                "http_status": "HTTP_STATUS",
                "parse_zero": "PARSE_ZERO",
                "success": "SUCCESS",
            },
        )
        self.assertEqual(len(set(classifications.values())), 4)

    def test_TST_V12_STATS_EDGE_TIMEOUT_does_not_invoke_parser(self) -> None:
        scenario = self.scenario("edge_timeout")
        self.assertEqual(scenario["fetch_calls"], 1)
        self.assertEqual(scenario["parser_calls"], 0)
        self.assertIsNone(scenario["result"]["terminal_http_status"])

    def test_TST_V12_STATS_HTTP_STATUS_preserves_status_without_parser(self) -> None:
        scenario = self.scenario("http_status")
        self.assertEqual(scenario["fetch_calls"], 1)
        self.assertEqual(scenario["parser_calls"], 0)
        self.assertEqual(scenario["result"]["terminal_http_status"], 503)

    def test_TST_V12_STATS_PARSE_ZERO_is_explicit_and_read_only(self) -> None:
        scenario = self.scenario("parse_zero")
        self.assertEqual(scenario["parser_calls"], 1)
        self.assertEqual(scenario["result"]["parsed_count"], 0)
        self.assertFalse(scenario["result"]["write_allowed"])
        self.assertEqual(scenario["result"]["persistence_action"], "NO_WRITE")

    def test_TST_V12_STATS_SUCCESS_returns_bounded_official_items(self) -> None:
        scenario = self.scenario("success")
        self.assertEqual(scenario["parser_calls"], 1)
        self.assertEqual(scenario["result"]["parsed_count"], 2)
        first = scenario["result"]["items"][0]
        self.assertEqual(
            first["url"],
            "https://www.stats.gov.cn/sj/zxfb/202607/t20260716_1964142.html",
        )
        self.assertEqual(first["published"], "2026-07-16")

    def test_TST_V12_STATS_PRODUCTION_PARSER_PARITY(self) -> None:
        parity = self.report["parser_parity"]
        self.assertEqual(parity["candidate_items"], parity["worker_items"])
        self.assertEqual(parity["empty_candidate_count"], 0)
        self.assertEqual(parity["empty_worker_count"], 0)

    def test_TST_V12_STATS_COST_BOUNDARY_and_no_live_change(self) -> None:
        boundary = self.report["boundary"]
        self.assertFalse(boundary["worker_imports_candidate"])
        self.assertEqual(boundary["cron_count"], 3)
        self.assertEqual(boundary["max_attempts"], 1)
        self.assertFalse(boundary["write_allowed"])
        self.assertFalse(boundary["live_change_authorized"])
        self.assertNotIn("stats_gov_diagnostic.mjs", WORKER.read_text(encoding="utf-8"))

    def test_TST_V12_STATS_OWNER_SYNC_is_canonical_and_fail_closed(self) -> None:
        required = (
            "ADP-V12-S2-T001",
            "stats-gov",
            "degraded_preserved",
            "EDGE_TIMEOUT",
            "SUCCESS",
            "NO_ADAPTER_FIX",
            "2026-07-22T10:36:47.591Z",
            "ADP-V12-S2-T001-diagnosis.json",
        )
        for page_path in OWNER_PAGES:
            with self.subTest(page=page_path.name):
                text = page_path.read_text(encoding="utf-8")
                for phrase in required:
                    self.assertIn(phrase, text)

        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        diagnostic = registry["diagnostic_routes"][0]
        self.assertFalse(diagnostic["write_allowed"])
        self.assertFalse(diagnostic["live_change_authorized"])
        self.assertEqual(diagnostic["external_subrequests_per_probe"], 1)
        self.assertEqual(diagnostic["edge_classification"], "SUCCESS")
        self.assertEqual(diagnostic["edge_parsed_count"], 15)
        self.assertEqual(diagnostic["edge_observed_at"], "2026-07-22T10:36:47.591Z")
        self.assertEqual(
            diagnostic["historical_edge_observation"]["verification_status"],
            "STALE_UNVERIFIED_RAW_UNAVAILABLE",
        )

        with tempfile.TemporaryDirectory() as tmp:
            temporary_root = Path(tmp)
            temporary_registry = temporary_root / "config" / REGISTRY.name
            temporary_registry.parent.mkdir(parents=True)
            temporary_registry.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
            temporary_receipt = temporary_root / DIAGNOSIS_RECEIPT.relative_to(ROOT)
            temporary_receipt.parent.mkdir(parents=True)
            temporary_receipt.write_bytes(DIAGNOSIS_RECEIPT.read_bytes())
            report = render_owner_documents(
                load_owner_controls(CONTROLS),
                project_path=temporary_root,
                generated_at="2026-06-26T21:51:00+10:00",
                write=True,
            )
            rendered = (temporary_root / "docs" / "owner" / "SOURCE_CATALOG.md").read_text(
                encoding="utf-8"
            )
            for phrase in required:
                self.assertIn(phrase, rendered)
            self.assertEqual(
                rendered,
                (ROOT / "docs" / "owner" / "SOURCE_CATALOG.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                report["source_catalog_inputs"],
                [
                    "config/owner_controls.yaml",
                    f"config/{REGISTRY.name}",
                    str(DIAGNOSIS_RECEIPT.relative_to(ROOT)),
                ],
            )

    def test_TST_V12_STATS_RECEIPT_SYNC_fails_closed(self) -> None:
        registry_data = json.loads(REGISTRY.read_text(encoding="utf-8"))

        def prepare_root(base: Path, *, copy_receipt: bool = True) -> Path:
            registry_path = base / "config" / REGISTRY.name
            registry_path.parent.mkdir(parents=True)
            registry_path.write_text(
                json.dumps(registry_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            receipt_path = base / DIAGNOSIS_RECEIPT.relative_to(ROOT)
            if copy_receipt:
                receipt_path.parent.mkdir(parents=True)
                receipt_path.write_bytes(DIAGNOSIS_RECEIPT.read_bytes())
            return registry_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root, copy_receipt=False)
            with self.assertRaisesRegex(ValueError, "diagnostic receipt not found"):
                render_owner_documents(
                    load_owner_controls(CONTROLS),
                    project_path=root,
                    generated_at="2026-07-22T20:46:59+10:00",
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            receipt_path = root / DIAGNOSIS_RECEIPT.relative_to(ROOT)
            receipt_path.write_bytes(receipt_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "receipt SHA-256 mismatch"):
                render_owner_documents(
                    load_owner_controls(CONTROLS),
                    project_path=root,
                    generated_at="2026-07-22T20:46:59+10:00",
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = prepare_root(root)
            mutated = json.loads(registry_path.read_text(encoding="utf-8"))
            mutated["diagnostic_routes"][0]["edge_observed_at"] = "2026-07-22T10:36:48Z"
            registry_path.write_text(
                json.dumps(mutated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "latest observation mismatch"):
                render_owner_documents(
                    load_owner_controls(CONTROLS),
                    project_path=root,
                    generated_at="2026-07-22T20:46:59+10:00",
                )

    def test_executable_verifier_has_no_internal_failures(self) -> None:
        self.assertEqual(self.verifier_returncode, 0, self.verifier_stderr)
        self.assertEqual(self.report["status"], "pass", self.report["failures"])
        self.assertEqual(self.report["failures"], [])


if __name__ == "__main__":
    unittest.main()
