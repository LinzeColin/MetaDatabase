from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from arxiv_daily_push.owner_controls import (
    OwnerControlsError,
    load_owner_controls,
    render_owner_documents,
)


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "tools" / "verify_science_advances_pubmed_candidate.mjs"
WORKER = ROOT / "deploy" / "cloudflare" / "worker_cloud.js"
REGISTRY = ROOT / "config" / "cloudflare_source_candidates_v1_2.json"
DIAGNOSIS_RECEIPT = ROOT / "machine" / "runs" / "ADP-V12-S2-T001-diagnosis.json"
CONTROLS = ROOT / "config" / "owner_controls.yaml"
TASK_GRAPH = ROOT / "docs" / "pursuing_goal" / "v1_2" / "TASK_GRAPH.yaml"
RUN_CONTRACT = (
    ROOT
    / "docs"
    / "pursuing_goal"
    / "v1_2"
    / "RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md"
)
OWNER_PAGES = (
    ROOT / "用户中心" / "数据源与板块健康.md",
    ROOT / "用户中心" / "README.md",
    ROOT / "用户中心" / "一看三查.md",
    ROOT / "用户中心" / "关键结论与用户决策.md",
    ROOT / "docs" / "owner" / "SOURCE_CATALOG.md",
    ROOT / "docs" / "HANDOFF.md",
)


class ScienceAdvancesPubmedCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            ["node", str(VERIFY)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            cls.report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"PubMed verifier emitted invalid JSON; stderr={completed.stderr!r}"
            ) from exc
        cls.verifier_returncode = completed.returncode
        cls.verifier_stderr = completed.stderr

    def scenario(self, name: str) -> dict:
        return self.report["scenarios"][name]

    def test_TST_V12_PUBMED_HAPPY_PATH_maps_existing_item_and_provenance(self) -> None:
        case = self.scenario("happy_path")
        result = case["result"]
        self.assertEqual(result["reason_code"], "SUCCESS")
        self.assertEqual(result["parsed_count"], 1)
        self.assertEqual(result["filtered_outside_window"], 1)
        self.assertEqual(result["search_count"], 2)
        self.assertEqual(
            list(result["items"][0]),
            ["guid", "title", "link", "summary", "published"],
        )
        self.assertEqual(result["items"][0]["guid"], "pubmed:99000001")
        self.assertEqual(
            result["items"][0]["link"],
            "https://doi.org/10.1126/sciadv.fixture01",
        )
        self.assertEqual(result["items"][0]["published"], "2024-01-12T00:00:00.000Z")
        provenance = result["records"][0]["provenance"]
        self.assertEqual(provenance["pmid"], "99000001")
        self.assertEqual(provenance["doi"], "10.1126/sciadv.fixture01")
        self.assertEqual(provenance["nlm_unique_id"], "101653440")
        self.assertEqual(provenance["electronic_issn"], "2375-2548")
        self.assertEqual(provenance["endpoints"], ["esearch", "efetch"])
        fallback = self.scenario("incomplete_article_date_fallback")["result"]
        self.assertEqual(fallback["reason_code"], "SUCCESS")
        self.assertEqual(fallback["parsed_count"], 1)
        self.assertEqual(fallback["items"][0]["published"], "2024-01-12T00:00:00.000Z")
        cdata_title = self.scenario("cdata_title_literal")["result"]
        self.assertEqual(cdata_title["reason_code"], "SUCCESS")
        self.assertEqual(
            cdata_title["items"][0]["title"],
            "Fixture record inside the requested publication window.",
        )
        predefined_entities = self.scenario("predefined_entities_title")["result"]
        self.assertEqual(predefined_entities["reason_code"], "SUCCESS")
        self.assertEqual(
            predefined_entities["items"][0]["title"],
            'Fixture & < > " \' record inside the requested publication window.',
        )

    def test_TST_V12_PUBMED_NEGATIVE_MATRIX_is_reason_coded_and_zero_item(self) -> None:
        required_review_regressions = {
            "esearch_missing_claimed_id": "ESEARCH_COUNT_RETMAX_ID_MISMATCH",
            "esearch_count_overflow": "ESEARCH_COUNT_INVALID",
            "esearch_comment_injected_id": "ESEARCH_COUNT_ID_MISMATCH",
            "esearch_cdata_injected_id": "ESEARCH_COUNT_ID_MISMATCH",
            "esearch_nested_id_under_wrapper": "ESEARCH_ID_LIST_STRUCTURE_INVALID",
            "efetch_unquoted_attribute": "EFETCH_XML_MALFORMED",
            "efetch_comment_inside_attribute": "EFETCH_XML_MALFORMED",
            "efetch_cdata_inside_attribute": "EFETCH_XML_MALFORMED",
            "efetch_nested_doctype": "EFETCH_XML_UNSAFE_DECLARATION",
            "efetch_nested_xml_declaration": "EFETCH_XML_MALFORMED",
            "efetch_undefined_entity": "EFETCH_XML_UNKNOWN_ENTITY",
            "efetch_invalid_xml10_character": "EFETCH_XML_MALFORMED",
            "efetch_undeclared_named_entity": "EFETCH_XML_UNKNOWN_ENTITY",
            "efetch_case_folded_predefined_entity": "EFETCH_XML_UNKNOWN_ENTITY",
            "duplicate_conflicting_citation_pmid": "EFETCH_PMID_CARDINALITY_INVALID",
            "duplicate_conflicting_pubmed_provenance_id": (
                "EFETCH_PMID_PROVENANCE_CARDINALITY_INVALID"
            ),
            "duplicate_conflicting_nlm_identity": (
                "EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID"
            ),
            "nested_fake_pubmed_provenance_id": (
                "EFETCH_ARTICLE_ID_LIST_STRUCTURE_INVALID"
            ),
            "case_colliding_attribute_names": "EFETCH_XML_MALFORMED",
            "abortsignal_timeout_missing": "ESEARCH_TIMEOUT_UNSUPPORTED",
        }
        for name, reason in required_review_regressions.items():
            with self.subTest(review_regression=name):
                self.assertEqual(self.report["expected_failures"].get(name), reason)
        for name, expected_reason in self.report["expected_failures"].items():
            with self.subTest(name=name):
                result = self.scenario(name)["result"]
                self.assertEqual(result["reason_code"], expected_reason)
                self.assertEqual(result["terminal_status"], "FAIL_CLOSED")
                self.assertEqual(result["items"], [])
                self.assertEqual(result["records"], [])
                self.assertFalse(result["write_allowed"])
                self.assertEqual(result["persistence_action"], "NO_WRITE")
                self.assertFalse(result["live_change_authorized"])
        for name in required_review_regressions:
            if name.startswith("esearch_"):
                with self.subTest(esearch_stops_before_efetch=name):
                    self.assertEqual(len(self.scenario(name)["calls"]), 1)

        self.assertEqual(self.scenario("abortsignal_timeout_missing")["calls"], [])

    def test_legal_esearch_truncation_is_not_misclassified_as_count_mismatch(self) -> None:
        result = self.scenario("legal_truncated_search")["result"]
        self.assertEqual(result["reason_code"], "SUCCESS")
        self.assertEqual(result["search_count"], 2)
        self.assertTrue(result["search_truncated_by_bound"])
        self.assertEqual(result["parsed_count"], 1)

    def test_empty_search_stops_before_efetch(self) -> None:
        case = self.scenario("empty_search")
        self.assertEqual(len(case["calls"]), 1)
        self.assertEqual(case["sleeps_ms"], [])
        self.assertEqual(case["result"]["reason_code"], "ESEARCH_EMPTY")
        self.assertEqual(case["result"]["external_subrequests"], 1)

    def test_duplicate_and_wrong_journal_cases_never_return_partial_items(self) -> None:
        names = (
            "duplicate_esearch_pmid",
            "duplicate_efetch_pmid",
            "duplicate_doi",
            "unrequested_pmid",
            "missing_requested_pmid",
            "wrong_journal",
            "wrong_issn",
            "wrong_title_and_abbreviation",
            "pmid_provenance_conflict",
        )
        for name in names:
            with self.subTest(name=name):
                result = self.scenario(name)["result"]
                self.assertEqual(result["parsed_count"], 0)
                self.assertEqual(result["items"], [])
                self.assertEqual(result["records"], [])

    def test_TST_V12_PUBMED_RATE_AND_IDENTITY_uses_public_config_without_key(self) -> None:
        case = self.scenario("happy_path")
        result = case["result"]
        self.assertEqual(case["sleeps_ms"], [1000])
        self.assertEqual(result["rate_limit"]["request_start_intervals_ms"], [1000])
        self.assertEqual(result["external_subrequests"], 2)
        controls = load_owner_controls(CONTROLS)
        public_email = controls["email"]["recipients"][0]
        for call in case["calls"]:
            with self.subTest(url=call["url"]):
                query = parse_qs(urlparse(call["url"]).query)
                self.assertEqual(query["tool"], ["adp_cloud"])
                self.assertEqual(query["email"], [public_email])
                self.assertNotIn("api_key", query)
                self.assertEqual(call["method"], "GET")
                self.assertEqual(call["redirect"], "manual")
        self.assertFalse(result["api_key_used"])
        self.assertFalse(result["bulk_download"])

    def test_rate_clock_negative_controls_block_before_second_request(self) -> None:
        for name, reason in (
            ("clock_backward", "RATE_LIMIT_CLOCK_BACKWARD"),
            ("sleeper_no_advance", "RATE_LIMIT_NOT_ENFORCED"),
        ):
            with self.subTest(name=name):
                case = self.scenario(name)
                self.assertEqual(len(case["calls"]), 1)
                self.assertEqual(case["result"]["reason_code"], reason)
                self.assertEqual(case["result"]["items"], [])

    def test_registry_budget_and_candidate_only_state_are_explicit(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        route = registry["pubmed_routes"][0]
        self.assertEqual(route["task_id"], "ADP-V12-S3-T001")
        self.assertEqual(route["source_id"], "science-advances-pubmed-candidate")
        self.assertEqual(route["state"], "candidate_not_live")
        self.assertFalse(route["live"])
        self.assertFalse(route["write_allowed"])
        self.assertFalse(route["live_change_authorized"])
        self.assertFalse(route["request_identity"]["api_key_used"])
        self.assertEqual(route["request_policy"]["max_ids"], 20)
        self.assertEqual(route["request_policy"]["max_external_subrequests"], 2)
        self.assertEqual(route["request_policy"]["min_request_start_interval_ms"], 1000)
        budget = registry["pubmed_subrequest_budget"]
        self.assertEqual(budget["current_live_max"], 32)
        self.assertEqual(budget["pubmed_candidate_net_increment_max"], 1)
        self.assertEqual(budget["projected_max_with_s1_and_s3"], 35)
        self.assertEqual(budget["cloudflare_workers_free_limit"], 50)
        self.assertEqual(budget["projected_headroom_with_s1_and_s3"], 15)

    def test_owner_sync_is_clickable_and_canonical_renderer_reproduces_catalog(self) -> None:
        required = (
            "ADP-V12-S3-T001",
            "science-advances-pubmed-candidate",
            "candidate_not_live",
            "101653440",
            "2375-2548",
            "35/50",
        )
        for page_path in OWNER_PAGES:
            with self.subTest(page=page_path.name):
                text = page_path.read_text(encoding="utf-8")
                for phrase in required:
                    self.assertIn(phrase, text)
                self.assertIn("](", text)

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
            self.assertEqual(
                rendered,
                (ROOT / "docs" / "owner" / "SOURCE_CATALOG.md").read_text(
                    encoding="utf-8"
                ),
            )
            for phrase in required:
                self.assertIn(phrase, rendered)
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

        mutations = (
            ("live state", ("pubmed_routes", 0, "state"), "active_live"),
            ("live authorization", ("pubmed_routes", 0, "live_change_authorized"), True),
            ("request bound", ("pubmed_routes", 0, "request_policy", "max_ids"), 21),
            (
                "budget arithmetic",
                ("pubmed_subrequest_budget", "projected_max_with_s1_and_s3"),
                36,
            ),
        )
        for label, path, value in mutations:
            with self.subTest(renderer_negative=label), tempfile.TemporaryDirectory() as tmp:
                temporary_root = Path(tmp)
                mutated = json.loads(REGISTRY.read_text(encoding="utf-8"))
                target = mutated
                for component in path[:-1]:
                    target = target[component]
                target[path[-1]] = value
                temporary_registry = temporary_root / "config" / REGISTRY.name
                temporary_registry.parent.mkdir(parents=True)
                temporary_registry.write_text(
                    json.dumps(mutated, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary_receipt = temporary_root / DIAGNOSIS_RECEIPT.relative_to(ROOT)
                temporary_receipt.parent.mkdir(parents=True)
                temporary_receipt.write_bytes(DIAGNOSIS_RECEIPT.read_bytes())
                with self.assertRaises(OwnerControlsError):
                    render_owner_documents(
                        load_owner_controls(CONTROLS),
                        project_path=temporary_root,
                        generated_at="2026-06-26T21:51:00+10:00",
                        write=True,
                    )

    def test_run_contract_is_bound_before_candidate_and_forbids_live_wiring(self) -> None:
        task_graph = TASK_GRAPH.read_text(encoding="utf-8")
        contract = RUN_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("run_contract: RUN_CONTRACT_03_SCIENCE_ADVANCES_PUBMED.md", task_graph)
        self.assertIn("ADP-V12-S3-T001", contract)
        self.assertIn("api_key_or_paid_service_required", contract)
        self.assertIn("journal_identity_cannot_be_proven", contract)
        self.assertIn("不导入 candidate 到 `worker_cloud.js`", contract)
        self.assertIn("不进入 S4", contract)

    def test_worker_and_wrangler_live_path_remain_unchanged(self) -> None:
        worker = WORKER.read_text(encoding="utf-8")
        self.assertNotIn("science_advances_pubmed_candidate.mjs", worker)
        self.assertNotIn("science-advances-pubmed-candidate", worker)
        self.assertIn(
            "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
            worker,
        )
        self.assertTrue(self.report["checks"]["TST-V12-PUBMED-NO-LIVE-WIRING"])

    def test_executable_verifier_has_no_internal_failures(self) -> None:
        self.assertEqual(self.verifier_returncode, 0, self.verifier_stderr)
        self.assertEqual(self.report["status"], "pass", self.report["failures"])
        self.assertEqual(self.report["failures"], [])
        self.assertTrue(all(self.report["checks"].values()))


if __name__ == "__main__":
    unittest.main()
