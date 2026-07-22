from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from arxiv_daily_push.owner_controls import load_owner_controls, render_owner_documents


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
VERIFY = ROOT / "tools" / "verify_google_news_candidate.mjs"
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


class GoogleNewsCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            ["node", str(VERIFY)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            cls.report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"candidate verifier emitted invalid JSON; stderr={completed.stderr!r}"
            ) from exc
        cls.verifier_returncode = completed.returncode
        cls.verifier_stderr = completed.stderr

    def scenario(self, name: str) -> dict:
        return self.report["scenarios"][name]

    def test_TST_V12_GNEWS_503_200(self) -> None:
        case = self.scenario("503_to_200")
        self.assertEqual(case["fetch_calls"], 2)
        self.assertEqual(case["sleeps_ms"], [1000])
        self.assertEqual(case["result"]["attempt_count"], 2)
        self.assertEqual(case["result"]["reason_code"], "SUCCESS")
        self.assertEqual(len(case["result"]["items"]), 2)

    def test_required_retry_status_allowlist(self) -> None:
        self.assertTrue(self.report["checks"]["TST-V12-GNEWS-RETRY-ALLOWLIST"])
        for name in ("502_to_200", "504_to_200"):
            with self.subTest(name=name):
                case = self.scenario(name)
                self.assertEqual(case["fetch_calls"], 2)
                self.assertEqual(case["sleeps_ms"], [1000])
                self.assertEqual(case["result"]["reason_code"], "SUCCESS")

    def test_required_client_error_denylist(self) -> None:
        self.assertTrue(self.report["checks"]["TST-V12-GNEWS-CLIENT-ERROR-DENYLIST"])
        for status in (400, 401):
            with self.subTest(status=status):
                case = self.scenario(f"{status}_terminal")
                self.assertEqual(case["fetch_calls"], 1)
                self.assertEqual(case["sleeps_ms"], [])
                self.assertEqual(case["result"]["reason_code"], f"HTTP_{status}")

    def test_TST_V12_GNEWS_503_503_200(self) -> None:
        case = self.scenario("503_to_503_to_200")
        self.assertEqual(case["fetch_calls"], 3)
        self.assertEqual(case["sleeps_ms"], [1000, 3000])
        self.assertEqual(case["result"]["attempt_count"], 3)
        self.assertEqual(case["result"]["reason_code"], "SUCCESS")

    def test_TST_V12_GNEWS_403(self) -> None:
        case = self.scenario("403_terminal")
        self.assertEqual(case["fetch_calls"], 1)
        self.assertEqual(case["sleeps_ms"], [])
        self.assertEqual(case["result"]["reason_code"], "HTTP_403")
        self.assertEqual(case["result"]["terminal_status"], "HTTP_ERROR")

    def test_TST_V12_GNEWS_404(self) -> None:
        case = self.scenario("404_terminal")
        self.assertEqual(case["fetch_calls"], 1)
        self.assertEqual(case["sleeps_ms"], [])
        self.assertEqual(case["result"]["reason_code"], "HTTP_404")
        self.assertEqual(case["result"]["terminal_status"], "HTTP_ERROR")

    def test_TST_V12_GNEWS_503_EXHAUSTED(self) -> None:
        case = self.scenario("503_exhausted")
        self.assertEqual(case["fetch_calls"], 3)
        self.assertEqual(case["sleeps_ms"], [1000, 3000])
        self.assertEqual(case["result"]["reason_code"], "HTTP_503_EXHAUSTED")
        self.assertEqual(case["result"]["attempt_count"], 3)

    def test_TST_V12_GNEWS_TIMEOUT_EXHAUSTED(self) -> None:
        case = self.scenario("timeout_exhausted")
        self.assertEqual(case["fetch_calls"], 3)
        self.assertEqual(case["sleeps_ms"], [1000, 3000])
        self.assertEqual(case["result"]["reason_code"], "TIMEOUT_EXHAUSTED")
        self.assertEqual(case["result"]["attempt_count"], 3)

    def test_TST_V12_GNEWS_PARSE_ZERO(self) -> None:
        case = self.scenario("parse_zero")
        self.assertEqual(case["fetch_calls"], 1)
        self.assertEqual(case["sleeps_ms"], [])
        self.assertEqual(case["result"]["reason_code"], "PARSE_ZERO")
        self.assertFalse(case["result"]["write_allowed"])
        self.assertEqual(case["result"]["persistence_action"], "NO_WRITE")

    def test_TST_V12_GNEWS_RESULT_EVIDENCE(self) -> None:
        for name, case in self.report["scenarios"].items():
            with self.subTest(name=name):
                result = case["result"]
                self.assertEqual(result["fallback"]["source_id"], "gnews-us-tech")
                self.assertEqual(result["fallback"]["state"], "active_live")
                self.assertFalse(result["fallback_used"])
                self.assertEqual(result["external_subrequests"], result["attempt_count"])
                self.assertFalse(result["write_allowed"])
                self.assertEqual(len(result["attempts"]), result["attempt_count"])

    def test_TST_V12_GNEWS_SYNC(self) -> None:
        self.assertTrue(self.report["checks"]["TST-V12-GNEWS-SYNC"])
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(registry["live_route"]["source_id"], "gnews-us-tech")
        self.assertEqual(registry["candidate_routes"][0]["state"], "candidate_not_live")

    def test_TST_V12_GNEWS_NO_LIVE_SWITCH(self) -> None:
        self.assertTrue(self.report["checks"]["TST-V12-GNEWS-NO-LIVE-SWITCH"])
        self.assertEqual(self.report["sync"]["worker_main"], "worker_cloud.js")
        self.assertEqual(self.report["sync"]["cron_count"], 3)
        self.assertFalse(self.report["sync"]["candidate_module_imported_by_worker"])
        self.assertIn("https://www.bing.com/news/search?", self.report["sync"]["live_feed_url"])

    def test_TST_V12_GNEWS_SUBREQUEST_BUDGET(self) -> None:
        budget = self.report["budget"]
        self.assertTrue(self.report["checks"]["TST-V12-GNEWS-SUBREQUEST-BUDGET"])
        self.assertEqual(budget["current_live_max"], 32)
        self.assertEqual(budget["candidate_retry_increment_max"], 2)
        self.assertEqual(budget["projected_max_if_enabled"], 34)
        self.assertLess(budget["projected_max_if_enabled"], budget["cloudflare_workers_free_limit"])
        self.assertEqual(budget["projected_headroom"], 16)
        self.assertEqual(budget["redirect_policy"], "manual_fail_closed")
        self.assertEqual(budget["redirect_network_requests_observed"], 1)
        redirect = self.scenario("redirect_manual")
        self.assertEqual(redirect["network_requests"], 1)
        self.assertEqual(redirect["result"]["attempt_count"], 1)
        self.assertEqual(redirect["result"]["external_subrequests"], 1)
        self.assertEqual(redirect["result"]["reason_code"], "HTTP_302")

    def test_TST_V12_GNEWS_OWNER_SYNC(self) -> None:
        required = (
            "ADP-V12-S1-T001",
            "gnews-us-tech",
            "gnews-us-tech-google-candidate",
            "Bing News RSS",
            "Google News RSS",
            "candidate_not_live",
        )
        for page_path in OWNER_PAGES:
            with self.subTest(page=page_path.name):
                text = page_path.read_text(encoding="utf-8")
                for phrase in required:
                    self.assertIn(phrase, text)
        for page_path in (OWNER_PAGES[0], OWNER_PAGES[4], OWNER_PAGES[5]):
            with self.subTest(budget_page=page_path.name):
                text = page_path.read_text(encoding="utf-8")
                self.assertIn("32", text)
                self.assertIn("34/50", text)
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
                generated_at="2026-07-22T18:00:00+10:00",
                write=True,
            )
            rendered_catalog = (
                temporary_root / "docs" / "owner" / "SOURCE_CATALOG.md"
            ).read_text(encoding="utf-8")
            self.assertIn(REGISTRY.name, rendered_catalog)
            self.assertIn("ADP-V12-S1-T001", rendered_catalog)
            self.assertIn("gnews-us-tech", rendered_catalog)
            self.assertIn("gnews-us-tech-google-candidate", rendered_catalog)
            self.assertIn("Google News RSS", rendered_catalog)
            self.assertIn("candidate_not_live", rendered_catalog)
            self.assertIn("34/50", rendered_catalog)
            self.assertEqual(
                report["source_catalog_inputs"],
                [
                    "config/owner_controls.yaml",
                    f"config/{REGISTRY.name}",
                    str(DIAGNOSIS_RECEIPT.relative_to(ROOT)),
                ],
            )
        for removed_legacy_file in ("功能清单.md", "开发记录.md", "模型参数文件.md"):
            self.assertFalse(
                (ROOT / removed_legacy_file).exists(),
                f"do not restore CodexProject legacy source: {removed_legacy_file}",
            )

    def test_executable_verifier_has_no_internal_failures(self) -> None:
        self.assertEqual(self.verifier_returncode, 0, self.verifier_stderr)
        self.assertEqual(self.report["status"], "pass", self.report["failures"])
        self.assertEqual(self.report["failures"], [])

    def test_worker_file_is_not_modified_by_candidate_module(self) -> None:
        worker = WORKER.read_text(encoding="utf-8")
        self.assertNotIn("google_news_candidate.mjs", worker)
        self.assertNotIn("gnews-us-tech-google-candidate", worker)


if __name__ == "__main__":
    unittest.main()
