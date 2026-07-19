from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.official_platform_research import (
    EVIDENCE_PATH,
    FIXTURE_PATH,
    PROVIDER_FACTS_PATH,
    REGULATORY_MATRIX_PATH,
    SOURCES_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_incremental_cost_gate,
    resolve_source_freshness,
    verify_existing_phase_evidence,
)
from abd_acceptance.stage1_delivery import (
    PINNED_RECEIPT_SHA256,
    PINNED_STAGE_EVIDENCE_SHA256,
    PINNED_STAGE_ROLLBACK_SHA256,
    RECEIPT_PATH,
    STAGE_EVIDENCE_PATH,
    STAGE_ROLLBACK_PATH,
    verify_stage1_delivery,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(str(ROOT.parent / ".github"), str(destination.parent / ".github"))
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _row(rows, item_id: str, key: str = "id"):
    return next(row for row in rows if row[key] == item_id)


def _fact(value, fact_id: str):
    return next(
        fact
        for provider in value["providers"]
        for fact in provider["facts"]
        if fact["fact_id"] == fact_id
    )


def _rule(value, rule_id: str):
    return next(row for row in value["rules"] if row["rule_id"] == rule_id)


def test_baseline_official_research_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 65
    assert result["decision"] == "OFFICIAL_PLATFORM_AND_REGULATORY_FACTS_FROZEN"
    assert result["release_status"] == "NOT_READY_STAGE_REVIEW_REQUIRED"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["provider_capability_status"] == "NOT_CONNECTED_OR_NOT_AUTHORIZED"
    assert result["legal_status"] == "RESEARCH_BASELINE_NOT_LEGAL_ADVICE_OR_COMPLIANCE_CERTIFICATION"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S02/P02_READY_NOT_STARTED"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_stage1_delivery_prerequisite_is_immutable_and_git_verified() -> None:
    result = verify_stage1_delivery(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S01_DELIVERED_S02_MAY_START"
    assert result["next"] == "S02/P01_READY_NOT_STARTED"
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["S01DELIVERY-GIT-MERGE-PARENTS"]["passed"] is True
    assert checks["S01DELIVERY-GIT-ANCESTRY"]["passed"] is True
    assert sha256_file(ROOT / RECEIPT_PATH) == PINNED_RECEIPT_SHA256
    assert sha256_file(ROOT / STAGE_EVIDENCE_PATH) == PINNED_STAGE_EVIDENCE_SHA256
    assert sha256_file(ROOT / STAGE_ROLLBACK_PATH) == PINNED_STAGE_ROLLBACK_SHA256


def test_existing_p01_receipt_rehashes_signed_inputs_reports_and_code() -> None:
    result = verify_existing_phase_evidence(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S02_P01_EVIDENCE_VERIFIED"
    assert result["next"] == "S02/P02_READY_NOT_STARTED"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


@pytest.mark.parametrize("relative", [SOURCES_PATH, PROVIDER_FACTS_PATH, REGULATORY_MATRIX_PATH])
def test_phase_artifact_hashes_match_frozen_fixture(relative: Path) -> None:
    assert sha256_file(ROOT / relative) == FIXTURE["expected_artifact_hashes"][relative.as_posix()]


@pytest.mark.parametrize("case", FIXTURE["incremental_cost_vectors"])
def test_incremental_cash_gate_covers_zero_and_point_0001_boundaries(case) -> None:
    assert resolve_incremental_cost_gate(case["value"]) == case["expected"]


@pytest.mark.parametrize("malformed", [0, 0.0, True, {}, [], "", " 0.00", "NaN", "Infinity", "AUD 0.00"])
def test_malformed_incremental_cash_never_passes(malformed) -> None:
    assert resolve_incremental_cost_gate(malformed).startswith("FAIL_")


@pytest.mark.parametrize("case", FIXTURE["source_freshness_vectors"])
def test_source_freshness_vectors_fail_closed(case) -> None:
    assert resolve_source_freshness(case["retrieved_on"], case["review_by"], case["as_of"]) == case["expected"]


@pytest.mark.parametrize(
    "values",
    [
        (None, "2026-08-20", "2026-07-20"),
        ("2026-07-20", None, "2026-07-20"),
        ("2026-07-20", "2026-08-20", None),
        ("20-07-2026", "2026-08-20", "2026-07-20"),
        ("2026-07-20", "2026-02-30", "2026-07-20"),
        ("2026-07-20", "2026-08-20", True),
    ],
)
def test_malformed_source_dates_are_invalid(values) -> None:
    assert resolve_source_freshness(*values) == "INVALID_SOURCE_DATES"


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("roadmap_objective", "S02P01-ROADMAP-EXACT"),
        ("roadmap_outputs", "S02P01-ROADMAP-EXACT"),
        ("requirement_target", "S02P01-REQUIREMENT-EXACT"),
        ("acceptance_oracle", "S02P01-ACCEPTANCE-CONTRACT-EXACT"),
        ("task_dependency", "S02P01-TASK-CHAIN-EXACT"),
        ("task_output", "S02P01-TASK-CHAIN-EXACT"),
        ("task_owner", "S02P01-TASK-CHAIN-EXACT"),
        ("traceability", "S02P01-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_semantics_cannot_drift(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation.startswith("roadmap"):
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = next(row for row in next(row for row in value["stages"] if row["id"] == "S02")["phases"] if row["id"] == "P01")
        if mutation == "roadmap_objective":
            phase["objective"] = "drift"
        else:
            phase["outputs"].pop()
    elif mutation == "requirement_target":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P01")["target"] = "drift"
    elif mutation == "acceptance_oracle":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        _row(value, "AC-S02-P01")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = _row(value["tasks"], "T-S02-P01-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"] = ["wrong.json"]
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P01", "requirement_id")["artifact_ids"] = []
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S02P01-SOURCES-TOP-LEVEL"),
        ("next", "S02P01-SOURCES-TOP-LEVEL"),
        ("network_mode", "S02P01-READ-ONLY-NONEXHAUSTIVE-RESEARCH-MODE"),
        ("login", "S02P01-READ-ONLY-NONEXHAUSTIVE-RESEARCH-MODE"),
        ("exhaustive", "S02P01-READ-ONLY-NONEXHAUSTIVE-RESEARCH-MODE"),
        ("allowed_level", "S02P01-SOURCE-LEVEL-DEFINITIONS-EXACT"),
        ("missing_source", "S02P01-SOURCE-IDS-EXACT-UNIQUE"),
        ("duplicate_id", "S02P01-SOURCE-IDS-EXACT-UNIQUE"),
        ("http", "S02P01-SOURCE-URLS-OFFICIAL-HTTPS"),
        ("foreign_host", "S02P01-SOURCE-URLS-OFFICIAL-HTTPS"),
        ("credentials", "S02P01-SOURCE-URLS-OFFICIAL-HTTPS"),
        ("fragment", "S02P01-SOURCE-URLS-OFFICIAL-HTTPS"),
        ("duplicate_url", "S02P01-SOURCE-URLS-OFFICIAL-HTTPS"),
        ("retrieval_date", "S02P01-SOURCE-METADATA-COMPLETE"),
        ("review_date", "S02P01-SOURCE-METADATA-COMPLETE"),
        ("source_level", "S02P01-SOURCE-METADATA-COMPLETE"),
        ("empty_claims", "S02P01-SOURCE-CLAIM-MAPPINGS-NONEMPTY"),
        ("duplicate_claim", "S02P01-SOURCE-CLAIM-MAPPINGS-NONEMPTY"),
        ("orphan_claim", "S02P01-ALL-CLAIMS-HAVE-OFFICIAL-SOURCE"),
        ("body_copy", "S02P01-SOURCE-METADATA-COMPLETE"),
        ("boundary_account", "S02P01-SOURCES-NO-EXTERNAL-EFFECT"),
        ("boundary_spend", "S02P01-SOURCES-NO-EXTERNAL-EFFECT"),
        ("limitation", "S02P01-SOURCE-LIMITATIONS-EXPLICIT"),
        ("binary_float", "S02P01-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS"),
    ],
)
def test_source_catalog_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / SOURCES_PATH
    value = strict_json_load(path)
    rows = value["sources"]
    if mutation == "status":
        value["status"] = "DEPLOYED"
    elif mutation == "next":
        value["next_on_acceptance_pass"] = "S02/P03_READY"
    elif mutation == "network_mode":
        value["research_mode"]["network_mode"] = "ACCOUNT_LOGIN"
    elif mutation == "login":
        value["research_mode"]["account_login_performed"] = True
    elif mutation == "exhaustive":
        value["research_mode"]["scope_is_exhaustive_of_internet"] = True
    elif mutation == "allowed_level":
        value["admission_policy"]["allowed_source_levels"].append("BLOG")
    elif mutation == "missing_source":
        rows.pop()
    elif mutation == "duplicate_id":
        rows[1]["id"] = rows[0]["id"]
    elif mutation == "http":
        rows[0]["url"] = rows[0]["url"].replace("https://", "http://")
    elif mutation == "foreign_host":
        rows[0]["url"] = "https://example.com/source"
    elif mutation == "credentials":
        rows[0]["url"] = "https://user:secret@help.tab.com.au/source"
    elif mutation == "fragment":
        rows[0]["url"] += "#claim"
    elif mutation == "duplicate_url":
        rows[1]["url"] = rows[0]["url"]
    elif mutation == "retrieval_date":
        rows[0]["retrieved_on"] = "2026-07-19"
    elif mutation == "review_date":
        rows[0]["review_by"] = "2026-08-21"
    elif mutation == "source_level":
        rows[0]["source_level"] = "L2_NEWS"
    elif mutation == "empty_claims":
        rows[0]["claim_ids"] = []
    elif mutation == "duplicate_claim":
        rows[0]["claim_ids"].append(rows[0]["claim_ids"][0])
    elif mutation == "orphan_claim":
        rows[0]["claim_ids"].append("PF-ORPHAN-999")
    elif mutation == "body_copy":
        rows[0]["content"] = "copied page body"
    elif mutation == "boundary_account":
        value["s02_p01_execution_boundary"]["external_account_accessed"] = True
    elif mutation == "boundary_spend":
        value["s02_p01_execution_boundary"]["incremental_cash_spent_aud"] = "0.0001"
    elif mutation == "limitation":
        value["limitations"] = []
    else:
        rows[0]["confidence"] = 1.0
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S02P01-PROVIDER-TOP-LEVEL"),
        ("next", "S02P01-PROVIDER-TOP-LEVEL"),
        ("runtime_semantics", "S02P01-FACT-SEMANTICS-FAIL-CLOSED"),
        ("permission_semantics", "S02P01-FACT-SEMANTICS-FAIL-CLOSED"),
        ("provider_order", "S02P01-PROVIDER-IDS-EXACT-UNIQUE"),
        ("duplicate_provider", "S02P01-PROVIDER-IDS-EXACT-UNIQUE"),
        ("fake_capability", "S02P01-PROVIDER-CAPABILITIES-NOT-FABRICATED"),
        ("duplicate_fact", "S02P01-PROVIDER-FACT-IDS-EXACT-UNIQUE"),
        ("missing_field", "S02P01-PROVIDER-FACT-ROWS-COMPLETE"),
        ("empty_statement", "S02P01-PROVIDER-FACT-ROWS-COMPLETE"),
        ("citation_url", "S02P01-PROVIDER-FACT-CITATIONS-RESOLVE"),
        ("citation_date", "S02P01-PROVIDER-FACT-CITATIONS-RESOLVE"),
        ("citation_level", "S02P01-PROVIDER-FACT-CITATIONS-RESOLVE"),
        ("citation_source", "S02P01-PROVIDER-FACT-CITATIONS-RESOLVE"),
        ("empty_citations", "S02P01-PROVIDER-FACT-CITATIONS-RESOLVE"),
        ("dangerous_decision", "S02P01-PROVIDER-DECISIONS-NO-ORDER-OR-SPEND"),
        ("critical_default", "S02P01-CRITICAL-SAFE-DEFAULTS-EXACT"),
        ("tab_scrape", "S02P01-TAB-ACCESS-CONTRACT-FAIL-CLOSED"),
        ("tab_studio", "S02P01-TAB-ACCESS-CONTRACT-FAIL-CLOSED"),
        ("sportsbet_permission", "S02P01-SPORTSBET-AUTOMATION-NOT-INVENTED"),
        ("gmail_methods", "S02P01-GMAIL-RESTRICTED-SCOPE-POLICY-GATE"),
        ("gmail_policy", "S02P01-GMAIL-RESTRICTED-SCOPE-POLICY-GATE"),
        ("cloudflare_paid", "S02P01-CLOUDFLARE-CHINA-AND-ZERO-CASH-GATE"),
        ("cloudflare_china", "S02P01-CLOUDFLARE-CHINA-AND-ZERO-CASH-GATE"),
        ("cloudflare_pages", "S02P01-CLOUDFLARE-CHINA-AND-ZERO-CASH-GATE"),
        ("ovh_sla", "S02P01-OVH-SLA-NOT-RUNTIME-PROOF"),
        ("ovh_purchase", "S02P01-OVH-SLA-NOT-RUNTIME-PROOF"),
        ("boundary_account", "S02P01-PROVIDER-NO-EXTERNAL-OR-PERFORMANCE-EFFECT"),
        ("boundary_deploy", "S02P01-PROVIDER-NO-EXTERNAL-OR-PERFORMANCE-EFFECT"),
        ("boundary_order", "S02P01-PROVIDER-NO-EXTERNAL-OR-PERFORMANCE-EFFECT"),
        ("boundary_return", "S02P01-PROVIDER-NO-EXTERNAL-OR-PERFORMANCE-EFFECT"),
        ("boundary_p02", "S02P01-PROVIDER-NO-EXTERNAL-OR-PERFORMANCE-EFFECT"),
        ("binary_float", "S02P01-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS"),
    ],
)
def test_provider_fact_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / PROVIDER_FACTS_PATH
    value = strict_json_load(path)
    providers = value["providers"]
    first = providers[0]["facts"][0]
    if mutation == "status":
        value["status"] = "CAPABILITIES_ENABLED"
    elif mutation == "next":
        value["next_on_acceptance_pass"] = "DEPLOY"
    elif mutation == "runtime_semantics":
        value["fact_semantics"]["official_document_is_runtime_proof"] = True
    elif mutation == "permission_semantics":
        value["fact_semantics"]["missing_permission_is_authorization"] = True
    elif mutation == "provider_order":
        providers.reverse()
    elif mutation == "duplicate_provider":
        providers[1]["provider_id"] = providers[0]["provider_id"]
    elif mutation == "fake_capability":
        providers[0]["current_abd_capability"] = "CONNECTED_AND_READY"
    elif mutation == "duplicate_fact":
        providers[0]["facts"][1]["fact_id"] = providers[0]["facts"][0]["fact_id"]
    elif mutation == "missing_field":
        first.pop("applicability")
    elif mutation == "empty_statement":
        first["statement"] = ""
    elif mutation == "citation_url":
        first["citations"][0]["url"] = "https://example.com"
    elif mutation == "citation_date":
        first["citations"][0]["retrieved_on"] = "2026-07-19"
    elif mutation == "citation_level":
        first["citations"][0]["source_level"] = "L2_BLOG"
    elif mutation == "citation_source":
        first["citations"][0]["source_id"] = "SRC-UNKNOWN"
    elif mutation == "empty_citations":
        first["citations"] = []
    elif mutation == "dangerous_decision":
        first["operational_decision"] = "SUBMIT_ORDER"
    elif mutation == "critical_default":
        value["critical_safe_defaults"]["TAB_STUDIO"] = "ENABLED"
    elif mutation == "tab_scrape":
        _fact(value, "PF-TAB-003")["operational_decision"] = "ALLOW_SCREEN_SCRAPING"
    elif mutation == "tab_studio":
        _fact(value, "PF-TAB-005")["fact_status"] = "GRANTED"
    elif mutation == "sportsbet_permission":
        _fact(value, "PF-SPORTSBET-003")["fact_status"] = "VERIFIED_ALLOWED"
    elif mutation == "gmail_methods":
        _fact(value, "PF-GMAIL-002")["operational_decision"] = "ALLOW_ALL_METHODS"
    elif mutation == "gmail_policy":
        _fact(value, "PF-GMAIL-005")["fact_status"] = "READY"
    elif mutation == "cloudflare_paid":
        _fact(value, "PF-CLOUDFLARE-002")["operational_decision"] = "UPGRADE"
    elif mutation == "cloudflare_china":
        _fact(value, "PF-CLOUDFLARE-004")["operational_decision"] = "ENABLE_CHINA_NETWORK"
    elif mutation == "cloudflare_pages":
        _fact(value, "PF-CLOUDFLARE-005")["operational_decision"] = "CLAIM_MAINLAND_AVAILABILITY"
    elif mutation == "ovh_sla":
        _fact(value, "PF-OVH-001")["statement"] = "The SLA proves ABD is online 7x24."
    elif mutation == "ovh_purchase":
        _fact(value, "PF-OVH-002")["operational_decision"] = "PURCHASE_NOW"
    elif mutation.startswith("boundary_"):
        key = {
            "boundary_account": "provider_accounts_accessed",
            "boundary_deploy": "cloud_deployment_performed",
            "boundary_order": "real_order_submitted",
            "boundary_return": "return_or_roi_verified",
            "boundary_p02": "s02_p02_started",
        }[mutation]
        value["s02_p01_execution_boundary"][key] = True
    else:
        first["confidence"] = 1.0
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S02P01-REGULATORY-TOP-LEVEL"),
        ("next", "S02P01-REGULATORY-TOP-LEVEL"),
        ("legal_advice", "S02P01-REGULATORY-NO-LEGAL-ADVICE-OR-CERTIFICATION"),
        ("certification", "S02P01-REGULATORY-NO-LEGAL-ADVICE-OR-CERTIFICATION"),
        ("exhaustive", "S02P01-REGULATORY-NO-LEGAL-ADVICE-OR-CERTIFICATION"),
        ("duplicate_rule", "S02P01-REGULATORY-RULE-IDS-EXACT-UNIQUE"),
        ("missing_rule", "S02P01-REGULATORY-RULE-IDS-EXACT-UNIQUE"),
        ("missing_field", "S02P01-REGULATORY-RULES-COMPLETE"),
        ("empty_statement", "S02P01-REGULATORY-RULES-COMPLETE"),
        ("citation_url", "S02P01-REGULATORY-CITATIONS-RESOLVE"),
        ("citation_source", "S02P01-REGULATORY-CITATIONS-RESOLVE"),
        ("empty_citations", "S02P01-REGULATORY-CITATIONS-RESOLVE"),
        ("control", "S02P01-REGULATORY-CONTROLS-EXACT"),
        ("in_play", "S02P01-REGULATORY-CRITICAL-FAIL-CLOSED-BEHAVIOR"),
        ("payment", "S02P01-REGULATORY-CRITICAL-FAIL-CLOSED-BEHAVIOR"),
        ("betstop", "S02P01-REGULATORY-CRITICAL-FAIL-CLOSED-BEHAVIOR"),
        ("privacy", "S02P01-REGULATORY-CRITICAL-FAIL-CLOSED-BEHAVIOR"),
        ("tab_scrape", "S02P01-REGULATORY-CRITICAL-FAIL-CLOSED-BEHAVIOR"),
        ("kyc_verified", "S02P01-REGULATORY-RUNTIME-PREREQUISITES-UNVERIFIED"),
        ("betstop_verified", "S02P01-REGULATORY-RUNTIME-PREREQUISITES-UNVERIFIED"),
        ("runtime_default", "S02P01-REGULATORY-RUNTIME-PREREQUISITES-UNVERIFIED"),
        ("conflict", "S02P01-REGULATORY-CONFLICTS-HAVE-SAFE-DEFAULT"),
        ("unknown_questions", "S02P01-REGULATORY-CONFLICTS-HAVE-SAFE-DEFAULT"),
        ("boundary_advice", "S02P01-REGULATORY-NO-EXTERNAL-EFFECT"),
        ("boundary_account", "S02P01-REGULATORY-NO-EXTERNAL-EFFECT"),
        ("boundary_deploy", "S02P01-REGULATORY-NO-EXTERNAL-EFFECT"),
        ("boundary_order", "S02P01-REGULATORY-NO-EXTERNAL-EFFECT"),
        ("boundary_spend", "S02P01-REGULATORY-NO-EXTERNAL-EFFECT"),
        ("binary_float", "S02P01-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS"),
    ],
)
def test_regulatory_matrix_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / REGULATORY_MATRIX_PATH
    value = strict_json_load(path)
    rules = value["rules"]
    if mutation == "status":
        value["status"] = "COMPLIANCE_CERTIFIED"
    elif mutation == "next":
        value["next_on_acceptance_pass"] = "PRODUCTION"
    elif mutation == "legal_advice":
        value["scope"]["legal_advice"] = True
    elif mutation == "certification":
        value["scope"]["legal_opinion_or_full_compliance_assessment"] = True
    elif mutation == "exhaustive":
        value["scope"]["regulatory_scope_exhaustive"] = True
    elif mutation == "duplicate_rule":
        rules[1]["rule_id"] = rules[0]["rule_id"]
    elif mutation == "missing_rule":
        rules.pop()
    elif mutation == "missing_field":
        rules[0].pop("applicability_to_abd")
    elif mutation == "empty_statement":
        rules[0]["statement"] = ""
    elif mutation == "citation_url":
        rules[0]["citations"][0]["url"] = "https://example.com"
    elif mutation == "citation_source":
        rules[0]["citations"][0]["source_id"] = "SRC-UNKNOWN"
    elif mutation == "empty_citations":
        rules[0]["citations"] = []
    elif mutation == "control":
        rules[5]["operational_control"] = "IGNORE"
    elif mutation == "in_play":
        _rule(value, "REG-001")["operational_control"] = "ALLOW_IN_PLAY"
    elif mutation == "payment":
        _rule(value, "REG-003")["status"] = "OPTIONAL"
    elif mutation == "betstop":
        _rule(value, "REG-004")["operational_control"] = "CONTINUE"
    elif mutation == "privacy":
        _rule(value, "REG-007")["status"] = "LEGAL_COMPLIANCE_CERTIFIED"
    elif mutation == "tab_scrape":
        _rule(value, "REG-008")["operational_control"] = "ALLOW_SCRAPING"
    elif mutation == "kyc_verified":
        value["runtime_prerequisite_state"]["owner_age_residency_and_kyc_verified"] = True
    elif mutation == "betstop_verified":
        value["runtime_prerequisite_state"]["betstop_or_other_self_exclusion_status_verified"] = True
    elif mutation == "runtime_default":
        value["runtime_prerequisite_state"]["default"] = "CONTINUE"
    elif mutation == "conflict":
        value["conflict_assessment"]["irreconcilable_legal_or_source_contract_conflict_found"] = True
    elif mutation == "unknown_questions":
        value["conflict_assessment"]["unresolved_legal_questions_exist"] = False
    elif mutation.startswith("boundary_"):
        key = {
            "boundary_advice": "legal_advice_provided",
            "boundary_account": "provider_account_accessed",
            "boundary_deploy": "production_deployed",
            "boundary_order": "real_order_submitted",
        }.get(mutation)
        if key:
            value["s02_p01_execution_boundary"][key] = True
        else:
            value["s02_p01_execution_boundary"]["incremental_cash_spent_aud"] = "0.0001"
    else:
        rules[0]["confidence"] = 1.0
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("receipt_status", "S01DELIVERY-RECEIPT-SHAPE"),
        ("receipt_checks", "S01DELIVERY-MAIN-CHECKS-EXACT"),
        ("receipt_cost", "S01DELIVERY-ZERO-CASH-DELIVERY-GATE"),
        ("receipt_effect", "S01DELIVERY-EXTERNAL-EFFECTS-EXACT"),
        ("stage_evidence", "S01DELIVERY-HISTORICAL-EVIDENCE-INTEGRITY"),
        ("rollback", "S01DELIVERY-HISTORICAL-ROLLBACK-INTEGRITY"),
        ("index", "S01DELIVERY-EVIDENCE-INDEX-BINDING"),
    ],
)
def test_stage1_delivery_mutations_block_s02(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation.startswith("receipt"):
        path = project / RECEIPT_PATH
        value = strict_json_load(path)
        if mutation == "receipt_status":
            value["delivery_status"] = "UNKNOWN"
        elif mutation == "receipt_checks":
            value["main_checks"][0]["conclusion"] = "failure"
        elif mutation == "receipt_cost":
            value["delivery_cost_gate"]["incremental_cash_spent_aud"] = "0.01"
        else:
            value["external_effects"]["gmail_account_accessed"] = True
        _write_json(path, value)
    elif mutation == "stage_evidence":
        path = project / STAGE_EVIDENCE_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "rollback":
        path = project / STAGE_ROLLBACK_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    else:
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        _row(rows, "INDEX-S01-STAGE-REVIEW")["status"] = "FAIL"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    delivery = verify_stage1_delivery(project, verify_git_history=False)
    _failed(delivery, expected)
    _failed(evaluate_contract(project), "S02P01-STAGE1-DELIVERY-CHAIN")


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("evidence_status", "S02P01-RECEIPT-EVIDENCE-INTEGRITY"),
        ("validation", "S02P01-RECEIPT-VALIDATION-ALL-PASS"),
        ("effect", "S02P01-RECEIPT-NO-EXTERNAL-EFFECT"),
        ("signed_input", "S02P01-RECEIPT-SIGNED-INPUTS-CURRENT"),
        ("report", "S02P01-RECEIPT-REPORT-HASHES-CURRENT"),
        ("code", "S02P01-RECEIPT-CODE-HASH-CURRENT"),
        ("rollback_binding", "S02P01-RECEIPT-ROLLBACK-HASH-BINDING"),
        ("absolute_path", "S02P01-RECEIPT-NO-ABSOLUTE-LOCAL-PATH"),
        ("rollback_status", "S02P01-RECEIPT-ROLLBACK-INTEGRITY"),
        ("index", "S02P01-RECEIPT-EVIDENCE-INDEX-BINDING"),
    ],
)
def test_existing_p01_receipt_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "rollback_status":
        path = project / "machine/evidence/EVD-S02-P01_rollback.json"
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "index":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        _row(rows, "INDEX-AC-S02-P01")["artifact_sha256"] = "0" * 64
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    else:
        path = project / "machine/evidence/EVD-S02-P01.json"
        value = strict_json_load(path)
        if mutation == "evidence_status":
            value["status"] = "FAIL"
        elif mutation == "validation":
            value["validation"]["status"] = "FAIL"
        elif mutation == "effect":
            value["external_effect_boundary"]["provider_api_called"] = True
        elif mutation == "signed_input":
            value["hashes"]["inputs"]["sources.json"] = "0" * 64
        elif mutation == "report":
            value["validation"]["hashes"]["machine/evidence/S02/P01/pytest.xml"] = "0" * 64
        elif mutation == "code":
            value["hashes"]["code"] = "0" * 64
        elif mutation == "rollback_binding":
            value["hashes"]["rollback_evidence"] = "0" * 64
        else:
            value["explicit_unknowns"].append(str(ROOT))
        _write_json(path, value)
    result = verify_existing_phase_evidence(project, verify_git_history=False)
    _failed(result, expected)


def test_verified_s02_p01_successor_does_not_invalidate_historical_s01_oracles() -> None:
    from abd_acceptance.metrics_economics import evaluate_contract as evaluate_p04
    from abd_acceptance.stage1_review import evaluate_contract as evaluate_stage1

    p04 = evaluate_p04(
        ROOT,
        require_external_reports=False,
        _verify_git_history=True,
        _allow_stage_review_candidate=True,
    )
    stage1 = evaluate_stage1(
        ROOT,
        require_external_reports=False,
        _verify_history=True,
        _verify_phase_oracles=True,
    )
    assert p04["status"] == "PASS", p04
    assert stage1["status"] == "PASS", stage1


@pytest.mark.parametrize(
    "relative",
    [
        "research_evidence_matrix.json",
        "model_claims.json",
        "tests/S02/P02_test.py",
        "machine/tests/fixtures/S02_P02.json",
        "machine/evidence/EVD-S02-P02.json",
        "machine/evidence/EVD-S02-P02_rollback.json",
    ],
)
def test_s02_p02_artifacts_cannot_start_inside_p01_run(tmp_path: Path, relative: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S02P01-P02-NOT-STARTED")


def test_s02_p02_index_cannot_advance_inside_p01_run(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    _row(rows, "INDEX-AC-S02-P02")["status"] = "READY"
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    _failed(evaluate_contract(project), "S02P01-P02-NOT-STARTED")


@pytest.mark.parametrize("relative", [SOURCES_PATH, PROVIDER_FACTS_PATH, REGULATORY_MATRIX_PATH, FIXTURE_PATH])
def test_duplicate_json_keys_fail_strict_parse(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"schema_version":"1.0.0","schema_version":"drift"}\n', encoding="utf-8")
    result = evaluate_contract(project)
    expected = {
        SOURCES_PATH: "S02P01-SOURCES-STRICT-JSON",
        PROVIDER_FACTS_PATH: "S02P01-PROVIDER-FACTS-STRICT-JSON",
        REGULATORY_MATRIX_PATH: "S02P01-REGULATORY-STRICT-JSON",
        FIXTURE_PATH: "S02P01-FIXTURE-STRICT-JSON",
    }[relative]
    _failed(result, expected)


def test_rollback_drill_restores_all_signed_inputs_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 7
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_and_contains_no_absolute_paths() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first
    assert first["next"] == "S02/P02_READY_NOT_STARTED"
    assert first["external_effect_boundary"]["github_upload_performed"] is False
    assert first["external_effect_boundary"]["real_order_capability_present"] is False
    assert first["external_effect_boundary"]["return_or_guarantee_claimed"] is False
    assert first["external_effect_boundary"]["s02_p02_started"] is False
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert str(ROOT) not in rendered
    assert first["decision_sha256"]


def test_artifacts_make_no_account_deployment_legal_or_return_claim() -> None:
    sources = strict_json_load(ROOT / SOURCES_PATH)
    providers = strict_json_load(ROOT / PROVIDER_FACTS_PATH)
    regulatory = strict_json_load(ROOT / REGULATORY_MATRIX_PATH)
    assert sources["research_mode"]["account_login_performed"] is False
    assert sources["research_mode"]["legal_advice_provided"] is False
    assert providers["s02_p01_execution_boundary"]["provider_accounts_accessed"] is False
    assert providers["s02_p01_execution_boundary"]["cloud_deployment_performed"] is False
    assert providers["s02_p01_execution_boundary"]["real_order_submitted"] is False
    assert providers["s02_p01_execution_boundary"]["return_or_roi_verified"] is False
    assert regulatory["scope"]["legal_advice"] is False
    assert regulatory["scope"]["legal_opinion_or_full_compliance_assessment"] is False
    assert regulatory["runtime_prerequisite_state"]["default"] == "NO_PROVIDER_INTERACTION_NO_RECOMMENDATION"
    assert all(
        artifact["next_on_acceptance_pass"] == "S02/P02_READY_NOT_STARTED"
        for artifact in [sources, providers, regulatory]
    )


def test_all_claims_resolve_to_official_source_metadata() -> None:
    sources = strict_json_load(ROOT / SOURCES_PATH)
    providers = strict_json_load(ROOT / PROVIDER_FACTS_PATH)
    regulatory = strict_json_load(ROOT / REGULATORY_MATRIX_PATH)
    source_map = {row["id"]: row for row in sources["sources"]}
    claims = {
        fact["fact_id"]
        for provider in providers["providers"]
        for fact in provider["facts"]
    } | {row["rule_id"] for row in regulatory["rules"]}
    assert claims == {claim for source in source_map.values() for claim in source["claim_ids"]}
    for row in [
        *[fact for provider in providers["providers"] for fact in provider["facts"]],
        *regulatory["rules"],
    ]:
        claim_id = row.get("fact_id", row.get("rule_id"))
        assert row["citations"]
        for citation in row["citations"]:
            source = source_map[citation["source_id"]]
            assert citation["url"] == source["url"]
            assert citation["retrieved_on"] == source["retrieved_on"]
            assert citation["source_level"] == source["source_level"]
            assert claim_id in source["claim_ids"]


def test_p01_evidence_path_remains_reserved_while_p03_progresses_separately() -> None:
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P01.json"
    assert (ROOT / "research_evidence_matrix.json").exists()
    assert (ROOT / "model_claims.json").exists()
    assert (ROOT / "research_reuse_matrix.json").exists()
    assert (ROOT / "license_inventory.json").exists()
    assert not (ROOT / "machine/evidence/EVD-S02-P04.json").exists()
