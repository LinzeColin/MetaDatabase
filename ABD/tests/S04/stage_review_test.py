from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.infrastructure_iac import parse_systemd_unit
from abd_acceptance.stage4_review import (
    CLOUDFLARED_UNIT_PATH,
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    FINDINGS_PATH,
    FIXED_CLOCK,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PACK_REPORT_PATH,
    PHASE_DECISIONS,
    PHASE_NEXT,
    PINNED_REVIEW_ARTIFACT_HASHES,
    REVIEW_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    SIGNED_STATE_JUNIT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    TEST_PATH,
    Stage4ReviewContractError,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_signed_receipt_preflight,
    verify_existing_stage_review_evidence,
    write_stage4_review_evidence,
)
from abd_acceptance.capacity_governance import verify_existing_phase_evidence as verify_p04
from abd_acceptance.cloudflare_edge import verify_existing_phase_evidence as verify_p02
from abd_acceptance.infrastructure_iac import verify_existing_phase_evidence as verify_p01
from abd_acceptance.release_control import verify_existing_phase_evidence as verify_p03


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = strict_json_load(ROOT / CONTRACT_PATH)
FINDINGS = strict_json_load(ROOT / FINDINGS_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
COMPOSE = strict_json_load(ROOT / "infra/compose.yml")
SLOTS = strict_json_load(ROOT / "release_slots.json")
CAPACITY = strict_json_load(ROOT / "capacity_budget.json")
PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_candidate_preflight_passes_without_phase_recursion() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_STAGE_REVIEW_CANDIDATE_VALID"
    assert result["summary"]["failed"] == 0
    assert result["next"] == FIXTURE["expected_next"]


def test_whole_stage_review_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_WHOLE_STAGE_REVIEW_PASS"
    assert result["stage_status"] == "S04_WHOLE_STAGE_REVIEW_PASS"
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_contract_identity_scope_and_terminal_state_are_exact() -> None:
    assert CONTRACT_ID == "STAGE-REVIEW-S04"
    assert REVIEW_ID == "ABD-S04-WHOLE-STAGE-REVIEW"
    assert FIXED_CLOCK == "2026-07-22T23:59:00+10:00"
    assert CONTRACT["review_scope"]["phase_ids"] == ["P01", "P02", "P03", "P04"]
    assert CONTRACT["release_status_on_pass"] == "NOT_READY_S05_TO_S19_AND_TARGET_RUNTIME_ACTIVATION_REQUIRED"
    assert CONTRACT["next_on_pass"] == "S04/GITHUB_STAGE_UPLOAD_READY"


@pytest.mark.parametrize("relative", sorted(PINNED_REVIEW_ARTIFACT_HASHES))
def test_review_artifact_hash_matches_pin(relative: str) -> None:
    actual = sha256_file(ROOT / relative)
    assert actual in {PINNED_REVIEW_ARTIFACT_HASHES[relative], SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)}


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


@pytest.mark.parametrize("record", CONTRACT["phase_records"], ids=lambda row: row["phase_id"])
def test_each_phase_record_binds_immutable_evidence_and_rollback(record: dict) -> None:
    phase = record["phase_id"]
    assert sha256_file(ROOT / record["evidence_path"]) == record["evidence_sha256"] == FIXTURE["expected_phase_evidence_sha256"][phase]
    assert sha256_file(ROOT / record["rollback_path"]) == record["rollback_sha256"] == FIXTURE["expected_phase_rollback_sha256"][phase]
    assert len(record["implementation_commit"]) == 40
    assert len(record["implementation_code_sha256"]) == 64
    assert record["expected_next"] == PHASE_NEXT[phase]


@pytest.mark.parametrize("phase", ["P01", "P02", "P03", "P04"])
def test_each_phase_signed_receipt_remains_verifiable(phase: str) -> None:
    result = PHASE_VERIFIERS[phase](ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == PHASE_DECISIONS[phase]
    assert result["next"] == PHASE_NEXT[phase]


def test_active_profile_is_single_writer_loopback_and_hard_bounded() -> None:
    core = COMPOSE["services"]["abd-core"]
    profile = SLOTS["runtime_profiles"]["active"]
    assert [profile["compose_service"], profile["bind_address"], profile["bind_port"]] == ["abd-core", "127.0.0.1", 8080]
    assert [profile["cpu_hard_limit_millicores"], profile["memory_hard_limit_mib"], profile["swap_limit_mib"]] == [1500, 2560, 0]
    assert profile["state_access"] == "READ_WRITE_SINGLE_WRITER"
    assert core["ports"][0]["host_ip"] == "127.0.0.1"
    assert core["environment"]["ABD_ORDER_SUBMISSION_ENABLED"] == "false"


def test_shadow_profile_is_one_instance_read_only_loopback_and_hard_bounded() -> None:
    shadow = COMPOSE["services"]["abd-shadow"]
    profile = SLOTS["runtime_profiles"]["candidate_shadow"]
    volumes = {row["target"]: row for row in shadow["volumes"]}
    assert [profile["compose_service"], profile["compose_profile"]] == ["abd-shadow", "shadow"]
    assert profile["allowed_bind_ports"] == [8081, 8082]
    assert [profile["cpu_hard_limit_millicores"], profile["memory_hard_limit_mib"], profile["swap_limit_mib"]] == [250, 512, 0]
    assert profile["maximum_concurrent_instances"] == 1
    assert profile["state_access"] == "READ_ONLY"
    assert volumes["/var/lib/abd"]["read_only"] is True
    assert shadow["environment"]["ABD_RUNTIME_MODE"] == "SHADOW_READ_ONLY"
    assert shadow["environment"]["ABD_ORDER_SUBMISSION_ENABLED"] == "false"


def test_compose_release_and_capacity_resource_budgets_are_identical() -> None:
    active = SLOTS["runtime_profiles"]["active"]
    shadow = SLOTS["runtime_profiles"]["candidate_shadow"]
    assert active["cpu_hard_limit_millicores"] == CAPACITY["cpu_budget"]["active_slot_outer_hard_limit_millicores"] == 1500
    assert shadow["cpu_hard_limit_millicores"] == CAPACITY["cpu_budget"]["candidate_shadow_outer_hard_limit_millicores"] == 250
    assert active["memory_hard_limit_mib"] == CAPACITY["memory_budget"]["active_slot_outer_hard_limit_mib"] == 2560
    assert shadow["memory_hard_limit_mib"] == CAPACITY["memory_budget"]["candidate_shadow_outer_hard_limit_mib"] == 512
    assert CAPACITY["memory_budget"]["swap_allowed"] is False


def test_active_edge_and_release_origins_align_while_shadow_ports_are_distinct() -> None:
    edge = strict_json_load(ROOT / "infra/cloudflared.yml")
    origin = edge["ingress"][0]["service"]
    assert origin == "http://127.0.0.1:8080"
    assert SLOTS["routing"]["public_origin"] == origin
    assert edge["ingress"][-1] == {"service": "http_status:404"}
    assert [row["bind_port"] for row in SLOTS["slots"]] == [8081, 8082]
    assert all(row["bind_address"] == "127.0.0.1" for row in SLOTS["slots"])


def test_cloudflared_unit_is_outbound_nonroot_and_hardened() -> None:
    unit = parse_systemd_unit((ROOT / CLOUDFLARED_UNIT_PATH).read_text(encoding="utf-8"))
    assert unit["Unit"]["ConditionPathExists"] == ["/usr/bin/cloudflared", "/etc/cloudflared/config.yml"]
    assert unit["Service"]["User"] == ["cloudflared"]
    assert unit["Service"]["Group"] == ["cloudflared"]
    assert unit["Service"]["ExecStart"] == ["/usr/bin/cloudflared --config /etc/cloudflared/config.yml tunnel run"]
    assert unit["Service"]["Restart"] == ["on-failure"]
    assert unit["Service"]["NoNewPrivileges"] == ["true"]
    assert unit["Service"]["ProtectSystem"] == ["strict"]
    assert unit["Service"]["MemoryDenyWriteExecute"] == ["true"]


@pytest.mark.parametrize(
    "path,value,check_id",
    [
        (("services", "abd-core", "cpus"), "2.00", "S04REVIEW-ACTIVE-RUNTIME-BINDING"),
        (("services", "abd-core", "ports", 0, "host_ip"), "0.0.0.0", "S04REVIEW-ACTIVE-RUNTIME-BINDING"),
        (("services", "abd-shadow", "cpus"), "1.50", "S04REVIEW-SHADOW-RUNTIME-BINDING"),
        (("services", "abd-shadow", "volumes", 1, "read_only"), False, "S04REVIEW-SHADOW-RUNTIME-BINDING"),
        (("services", "abd-shadow", "environment", "ABD_ORDER_SUBMISSION_ENABLED"), "true", "S04REVIEW-SHADOW-RUNTIME-BINDING"),
    ],
)
def test_compose_cross_phase_drift_fails_closed(tmp_path: Path, path: tuple, value, check_id: str) -> None:
    root = _clone_project(tmp_path)
    candidate = strict_json_load(root / "infra/compose.yml")
    cursor = candidate
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    _write_json(root / "infra/compose.yml", candidate)
    _failed(validate_candidate_preflight(root), check_id)


@pytest.mark.parametrize(
    "path,value",
    [
        (("runtime_profiles", "active", "bind_port"), 8081),
        (("runtime_profiles", "active", "state_access"), "READ_ONLY"),
        (("runtime_profiles", "candidate_shadow", "allowed_bind_ports"), [8081]),
        (("runtime_profiles", "candidate_shadow", "memory_hard_limit_mib"), 2560),
        (("runtime_profiles", "candidate_shadow", "maximum_concurrent_instances"), 2),
    ],
)
def test_release_profile_drift_fails_closed(tmp_path: Path, path: tuple, value) -> None:
    root = _clone_project(tmp_path)
    candidate = strict_json_load(root / "release_slots.json")
    cursor = candidate
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    _write_json(root / "release_slots.json", candidate)
    result = validate_candidate_preflight(root)
    assert result["status"] == "FAIL", result
    assert {
        "S04REVIEW-RELEASE-SLOTS-VALID",
        "S04REVIEW-ACTIVE-RUNTIME-BINDING",
        "S04REVIEW-SHADOW-RUNTIME-BINDING",
        "S04REVIEW-CAPACITY-SHEDDING-RELEASE-COMPOSE-COUPLING",
    }.intersection(result["summary"]["failed_check_ids"])


def test_cloudflared_lifecycle_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / CLOUDFLARED_UNIT_PATH
    path.write_text(path.read_text(encoding="utf-8").replace("User=cloudflared", "User=root"), encoding="utf-8")
    _failed(validate_candidate_preflight(root), "S04REVIEW-CLOUDFLARED-LIFECYCLE-HARDENED")


def test_claim_boundary_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    contract = strict_json_load(root / CONTRACT_PATH)
    contract["claim_boundary"]["global_chinese_access_verified"] = True
    _write_json(root / CONTRACT_PATH, contract)
    _failed(validate_candidate_preflight(root), "S04REVIEW-RUNTIME-OVERCLAIM-BOUNDARY")


def test_open_finding_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    findings = strict_json_load(root / FINDINGS_PATH)
    findings["findings"][0]["status"] = "OPEN"
    findings["summary"]["resolved_in_review_candidate"] = 5
    findings["summary"]["open"] = 1
    _write_json(root / FINDINGS_PATH, findings)
    _failed(validate_candidate_preflight(root), "S04REVIEW-ALL-FINDINGS-RESOLVED")


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / CONTRACT_PATH
    path.write_text(path.read_text(encoding="utf-8").replace('"schema_version": "1.0.0",', '"schema_version": "1.0.0",\n  "schema_version": "1.0.0",', 1), encoding="utf-8")
    _failed(validate_candidate_preflight(root), "S04REVIEW-PREFLIGHT-CONTRACT-STRICT-JSON")


def test_every_finding_is_resolved_and_has_a_unique_verification_gate() -> None:
    rows = FINDINGS["findings"]
    assert [row["id"] for row in rows] == FIXTURE["expected_finding_ids"]
    assert all(row["status"] == "RESOLVED_IN_REVIEW_CANDIDATE" for row in rows)
    gates = [row["verification_gate"] for row in rows]
    assert len(gates) == len(set(gates)) == 6
    assert FINDINGS["summary"]["open"] == 0


@pytest.mark.parametrize("key", sorted(FIXTURE["expected_claim_boundary"]))
def test_every_runtime_claim_boundary_remains_false(key: str) -> None:
    assert CONTRACT["claim_boundary"][key] is False
    assert FIXTURE["expected_claim_boundary"][key] is False


@pytest.mark.parametrize("key,value", sorted(CONTRACT["external_effect_boundary"].items()))
def test_every_external_effect_boundary_is_false_or_exact_zero(key: str, value) -> None:
    if key == "incremental_cash_spent_aud":
        assert value == "0.00"
    elif key == "owner_final_order_only":
        assert value is True
    else:
        assert value is False


@pytest.mark.parametrize("relative", ROLLBACK_ARTIFACTS, ids=lambda path: path.as_posix())
def test_every_rollback_artifact_is_regular_and_present(relative: Path) -> None:
    assert (ROOT / relative).is_file()
    assert not (ROOT / relative).is_symlink()


def test_rollback_drill_restores_every_signed_stage_artifact() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"] == len(ROLLBACK_ARTIFACTS)
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["target_host_accessed"] is False
    assert result["docker_or_systemd_invoked"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_rollback_drill_is_deterministic() -> None:
    assert perform_rollback_drill(ROOT) == perform_rollback_drill(ROOT)


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["stage_status"] == "S04_WHOLE_STAGE_REVIEW_PASS"
    assert first["review_findings"]["open"] == 0
    assert first["phase_completion"]["phase_count"] == 4
    assert first["phase_completion"]["production_10x_runtime_verified"] is False
    assert first["next"] == FIXTURE["expected_next"]


def test_signed_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = validate_signed_receipt_preflight(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S04_STAGE_REVIEW_SIGNED_PREFLIGHT_VALID"
        verified = verify_existing_stage_review_evidence(ROOT)
        assert verified["status"] == "PASS", verified
        assert verified["decision"] == "S04_STAGE_REVIEW_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S04_STAGE_REVIEW_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED"


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH, SIGNED_STATE_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    for check_id in ["S04REVIEW-TARGETED-PYTEST", "S04REVIEW-FULL-REGRESSION", "S04REVIEW-SIGNED-STATE-REGRESSION"]:
        assert check_id in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(Stage4ReviewContractError, match="inside the ABD project root"):
        write_stage4_review_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "abd_acceptance", "--contract", CONTRACT_ID, "--evidence", "machine/evidence"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert "contract is not implemented" not in result.stderr


def test_taskpack_reports_and_source_receipts_are_exact() -> None:
    assert PACK_REPORT_PATH == Path("machine/evidence/validation_report.json")
    assert SCAN_REPORT_PATH == Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
    sources = CONTRACT["supplied_source_receipts"]
    assert sources[0]["sha256"] == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
    assert sources[1]["sha256"] == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
    assert sources[1]["original_file_count"] == 53


def test_canonical_financial_order_and_no_guarantee_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["product"]["monthly_target_return"] == "0.30"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert parameters["target_30pct"]["guaranteed"] is False
    assert parameters["target_30pct"]["shortfall_behavior"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert set(costs["incremental_cash_budget"].values()) == {"0.00"}


def test_stage5_progression_accepts_only_complete_verified_p03_successor() -> None:
    result = evaluate_contract(ROOT)
    check = next(row for row in result["checks"] if row["id"] == "S04REVIEW-S05-PROGRESSION")
    assert check["passed"] is True, check
    assert len(check["detail"]["index"]) == 4
    assert check["detail"]["mode"] in {"VERIFIED_S05_P03_CANDIDATE", "VERIFIED_S05_P03_SIGNED"}
    assert len(check["detail"]["p01_candidate_present"]) == 8
    assert len(check["detail"]["p02_candidate_present"]) == 5
    assert len(check["detail"]["p03_candidate_present"]) == 6


def test_partial_stage5_p01_candidate_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / "market_ontology.json").unlink()
    result = evaluate_contract(root)
    _failed(result, "S04REVIEW-S05-PROGRESSION")


def test_review_artifacts_contain_no_secret_or_machine_specific_path() -> None:
    paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/stage4_review.py"), CLOUDFLARED_UNIT_PATH]
    rendered = "\n".join((ROOT / path).read_text(encoding="utf-8", errors="replace") for path in paths)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert ("-----BEGIN " + "PRIVATE KEY-----") not in rendered


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_boundary_deltas"])
def test_numeric_stability_boundary_remains_exact(delta: str) -> None:
    assert delta in {"-0.0001", "0", "0.0001"}


def test_degraded_page_is_static_and_not_claimed_as_automatic_fallback() -> None:
    text = (ROOT / "degraded_page.html").read_text(encoding="utf-8")
    assert "停止新建议" in text
    assert "不要使用任何旧建议下单" in text
    assert "不是随机收益保证" in text
    assert "<script" not in text.lower()
    assert CONTRACT["claim_boundary"]["static_degraded_page_automatically_wired"] is False


def test_readme_and_cli_wiring_reference_stage_review_contract() -> None:
    main = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    init = (ROOT / "abd_acceptance/__init__.py").read_text(encoding="utf-8")
    assert '"STAGE-REVIEW-S04": write_stage4_review_evidence' in main
    assert '"STAGE-REVIEW-S04": cli_verify_stage4_delivery' in main
    assert '"AC-S05-P01": write_market_ontology_phase_evidence' in main
    assert '"AC-S05-P02": write_source_capability_phase_evidence' in main
    assert '"AC-S05-P03": write_source_scheduler_phase_evidence' in main
    assert "write_stage4_review_evidence" in init
    assert "validate_stage4_review_candidate" in init
    assert "verify_stage4_delivery" in init
    assert "validate_market_ontology_candidate" in init
