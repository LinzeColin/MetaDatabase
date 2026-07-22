from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.cloudflare_edge import (
    ALLOWED_NUMERIC_BOUNDARY_DELTAS,
    CONFIG_PATH,
    CONTRACT_ID,
    DEGRADED_PAGE_PATH,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    OWNER_PLACEHOLDER,
    PACK_REPORT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    PLACEHOLDER_HOSTNAME,
    PLACEHOLDER_TUNNEL_ID,
    POLICY_END,
    POLICY_PATH,
    POLICY_START,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    CloudflareEdgeContractError,
    _set_or_delete_path,
    _structural_self_hash,
    _tree_hash,
    activation_gate,
    analyze_degraded_page,
    build_evidence,
    edge_disposition,
    evaluate_contract as _evaluate_contract,
    materialize_edge_bundle,
    parse_access_policy,
    perform_rollback_drill,
    validate_access_policy,
    validate_cloudflared_config,
    verify_existing_phase_evidence,
)
from abd_acceptance.infrastructure_iac import verify_existing_phase_evidence as verify_p01_evidence


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
CONFIG = strict_json_load(ROOT / CONFIG_PATH)
POLICY_TEXT = (ROOT / POLICY_PATH).read_text(encoding="utf-8")
POLICY = parse_access_policy(POLICY_TEXT)
DEGRADED_PAGE = (ROOT / DEGRADED_PAGE_PATH).read_text(encoding="utf-8")


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
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_policy(path: Path, policy: dict, *, prose: str | None = None) -> None:
    original = path.read_text(encoding="utf-8")
    start = original.index(POLICY_START) + len(POLICY_START)
    end = original.index(POLICY_END, start)
    rendered = original[:start] + "\n" + json.dumps(policy, ensure_ascii=False, sort_keys=True, indent=2) + "\n" + original[end:]
    if prose is not None:
        rendered = prose
    path.write_text(rendered, encoding="utf-8")


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "OUTBOUND_ONLY_EDGE_CONFIGURATION_CONTRACT_FROZEN"
    assert result["phase_status"] == "S04_P02_PASS"
    assert result["pass_gate_interpretation"] == "OFFLINE_CONFIGURATION_PROVES_NO_PUBLIC_BUSINESS_INBOUND_REQUIRED; RUNTIME_ACCESS_REMAINS_UNVERIFIED"
    assert result["activation_gate"] == "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["runtime_access_status"] == "NOT_EXECUTED_OR_VERIFIED"
    assert result["release_status"] == "NOT_READY_S04_P03_TO_P04_AND_STAGE_REVIEW_REQUIRED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_signed_p01_is_exact_phase_prerequisite() -> None:
    result = verify_p01_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_P01_EVIDENCE_VERIFIED"
    assert result["next"] == "S04/P02_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_cloudflared_file_is_strict_json_and_valid_yaml_subset() -> None:
    assert CONFIG == FIXTURE["expected_config"]
    assert validate_cloudflared_config(CONFIG) == []
    assert not any(isinstance(value, float) for value in CONFIG.values())


@pytest.mark.parametrize("mutation", FIXTURE["invalid_config_mutations"], ids=lambda row: row["id"])
def test_every_declared_cloudflared_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(CONFIG)
    _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
    assert validate_cloudflared_config(candidate), mutation


@pytest.mark.parametrize(
    "mutation,error",
    [
        ({"unexpected": True}, "top-level"),
        ({"tunnel": "secret-token-value-1234567890"}, "tunnel identifier"),
        ({"no-autoupdate": False}, "updates"),
        ({"metrics": "[::]:49312"}, "loopback"),
    ],
)
def test_additional_cloudflared_mutations_fail_closed(mutation: dict, error: str) -> None:
    candidate = copy.deepcopy(CONFIG)
    candidate.update(mutation)
    assert any(error in item for item in validate_cloudflared_config(candidate))


def test_named_tunnel_template_contains_no_account_value_or_secret() -> None:
    assert CONFIG["tunnel"] == PLACEHOLDER_TUNNEL_ID
    assert CONFIG["credentials-file"] == f"/etc/cloudflared/{PLACEHOLDER_TUNNEL_ID}.json"
    assert CONFIG["ingress"][0]["hostname"] == PLACEHOLDER_HOSTNAME
    assert PLACEHOLDER_HOSTNAME.endswith(".invalid")
    assert "token" not in json.dumps(CONFIG, sort_keys=True).lower()


def test_origin_and_metrics_are_loopback_and_catch_all_rejects() -> None:
    assert CONFIG["ingress"][0]["service"] == "http://127.0.0.1:8080"
    assert CONFIG["metrics"] == "127.0.0.1:49312"
    assert CONFIG["ingress"][-1] == {"service": "http_status:404"}
    assert CONFIG["no-autoupdate"] is True


def test_access_policy_machine_block_is_unique_strict_and_valid() -> None:
    assert POLICY_TEXT.count(POLICY_START) == 1
    assert POLICY_TEXT.count(POLICY_END) == 1
    assert validate_access_policy(POLICY) == []
    assert POLICY["contract_id"] == CONTRACT_ID


@pytest.mark.parametrize(
    "path,replacement,error",
    [
        (["enforcement", "default_action"], "ALLOW", "deny by default"),
        (["enforcement", "allow_policies", 0, "include", "value"], "*@example.com", "exact external email"),
        (["enforcement", "allow_policies", 0, "include", "exact_owner_count"], 2, "exact external email"),
        (["enforcement", "allow_policies", 0, "require", "mfa"], False, "MFA"),
        (["enforcement", "forbidden_actions"], [], "Bypass"),
        (["enforcement", "everyone_selector_allowed"], True, "Everyone"),
        (["enforcement", "email_domain_wildcard_allowed"], True, "wildcard"),
        (["enforcement", "audit_logging_required"], False, "audit logging"),
        (["network_boundary", "origin_business_inbound_required"], True, "network boundary"),
        (["activation", "requested"], True, "blocked"),
        (["claims", "mainland_china_acceleration_availability_or_reach"], "VERIFIED", "mainland China"),
        (["claims", "ovh_7x24"], "VERIFIED", "runtime"),
        (["budget", "incremental_cash_aud"], "0.01", "A$0"),
        (["budget", "china_network_subscription_allowed"], True, "A$0"),
    ],
)
def test_access_policy_mutations_fail_closed(path: list, replacement, error: str) -> None:
    candidate = copy.deepcopy(POLICY)
    _set_or_delete_path(candidate, path, replacement)
    assert any(error in item for item in validate_access_policy(candidate))


@pytest.mark.parametrize(
    "text",
    [
        POLICY_TEXT.replace(POLICY_START, "", 1),
        POLICY_TEXT.replace(POLICY_END, "", 1),
        POLICY_TEXT.replace('"schema_version": "1.0.0",', '"schema_version": "1.0.0",\n  "schema_version": "1.0.0",', 1),
        POLICY_START + "\n[]\n" + POLICY_END,
    ],
)
def test_malformed_access_policy_blocks_are_rejected(text: str) -> None:
    with pytest.raises(CloudflareEdgeContractError):
        parse_access_policy(text)


def test_owner_identity_is_external_placeholder_not_committed_identity() -> None:
    include = POLICY["enforcement"]["allow_policies"][0]["include"]
    assert include == {"selector": "EMAIL", "value": OWNER_PLACEHOLDER, "exact_owner_count": 1}
    assert "@" not in OWNER_PLACEHOLDER


def test_activation_gate_stays_blocked_for_repository_template() -> None:
    assert activation_gate(CONFIG, POLICY) == "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED"
    assert POLICY["application"]["status"] == "NOT_CREATED_OR_INSPECTED"
    assert set(POLICY["activation"]["prerequisites"].values()) != {"VERIFIED"}


def test_activation_gate_requires_every_external_prerequisite_and_real_external_values() -> None:
    config = copy.deepcopy(CONFIG)
    policy = copy.deepcopy(POLICY)
    policy["activation"]["requested"] = True
    policy["activation"]["prerequisites"] = {key: "VERIFIED" for key in policy["activation"]["prerequisites"]}
    assert activation_gate(config, policy) == "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED"
    config["tunnel"] = "11111111-1111-4111-8111-111111111111"
    config["ingress"][0]["hostname"] = "abd.example.com"
    assert activation_gate(config, policy) == "READY_FOR_EXPLICIT_P03_ACTIVATION"


def test_degraded_page_is_static_chinese_and_fail_closed() -> None:
    result = analyze_degraded_page(DEGRADED_PAGE)
    assert result["status"] == "PASS", result
    assert result["lang"] == "zh-CN"
    assert result["forbidden_tags"] == []
    assert result["external_references"] == []
    assert "default-src 'none'" in result["csp"]


@pytest.mark.parametrize(
    "injection,expected_issue",
    [
        ("<script>alert(1)</script>", "forbidden active"),
        ('<a href="https://example.com">继续</a>', "forbidden active"),
        ('<form action="/order"></form>', "forbidden active"),
        ('<img src="data:image/png;base64,AAAA">', "forbidden active"),
        ('<button onclick="submitOrder()">下单</button>', "forbidden active"),
        ('<iframe src="https://example.com"></iframe>', "forbidden active"),
    ],
)
def test_active_or_external_degraded_page_injections_fail_closed(injection: str, expected_issue: str) -> None:
    candidate = DEGRADED_PAGE.replace("</main>", injection + "</main>")
    result = analyze_degraded_page(candidate)
    assert result["status"] == "FAIL"
    assert any(expected_issue in issue for issue in result["issues"])


@pytest.mark.parametrize(
    "old,new,expected_issue",
    [
        ('lang="zh-CN"', 'lang="en"', "language"),
        ("default-src 'none'; ", "", "CSP"),
        ("停止新建议", "继续新建议", "guidance"),
        ("所有先前建议立即失效", "旧建议仍有效", "guidance"),
        ("不是随机收益保证", "保证月收益", "guidance"),
        ("才由你自行完成最终下单", "系统自动下单", "guidance"),
    ],
)
def test_degraded_page_semantic_mutations_fail_closed(old: str, new: str, expected_issue: str) -> None:
    result = analyze_degraded_page(DEGRADED_PAGE.replace(old, new, 1))
    assert result["status"] == "FAIL"
    assert any(expected_issue in issue for issue in result["issues"])


@pytest.mark.parametrize("delta", sorted(ALLOWED_NUMERIC_BOUNDARY_DELTAS))
@pytest.mark.parametrize("adverse", [False, True])
def test_numeric_boundary_and_adverse_odds_cannot_change_edge_disposition(delta: str, adverse: bool) -> None:
    baseline = edge_disposition(CONFIG, POLICY, DEGRADED_PAGE)
    result = edge_disposition(CONFIG, POLICY, DEGRADED_PAGE, numeric_boundary_delta=delta, adverse_odds_tick=adverse)
    assert result["status"] == baseline["status"] == "PASS"
    assert result["decision"] == baseline["decision"]
    assert result["activation_gate"] == baseline["activation_gate"]
    assert result["runtime_access_verified"] is False


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"numeric_boundary_delta": "0.001"}, "not frozen"),
        ({"adverse_odds_tick": 1}, "must be boolean"),
    ],
)
def test_malformed_numeric_boundary_inputs_fail_closed(kwargs: dict, error: str) -> None:
    with pytest.raises(CloudflareEdgeContractError, match=error):
        edge_disposition(CONFIG, POLICY, DEGRADED_PAGE, **kwargs)


def test_offline_bundle_materialization_is_deterministic_and_contains_only_public_artifacts(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = materialize_edge_bundle(ROOT, first)
    second_manifest = materialize_edge_bundle(ROOT, second)
    assert first_manifest == second_manifest
    assert _tree_hash(first) == _tree_hash(second)
    assert sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file()) == FIXTURE["expected_bundle_files"]
    assert first_manifest["activation_gate"] == "BLOCKED_EXTERNAL_PREREQUISITES_NOT_VERIFIED"
    assert first_manifest["production_activation_performed"] is False
    assert first_manifest["runtime_access_verified"] is False


def test_bundle_refuses_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(CloudflareEdgeContractError, match="must not already exist"):
        materialize_edge_bundle(ROOT, destination)


def test_rollback_drill_restores_all_six_phase_artifacts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 6
    assert all(row["restored_sha256"] == row["signed_sha256"] for row in result["artifacts"].values())
    assert all(row["corrupted_sha256"] != row["signed_sha256"] for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, rollback_first = build_evidence(ROOT, require_external_reports=False)
    second, rollback_second = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert rollback_first == rollback_second
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert first["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert first["runtime_access_status"] == "NOT_EXECUTED_OR_VERIFIED"
    assert first["next"] == FIXTURE["expected_next"]


def test_existing_phase_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S04_P02_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S04_P02_EVIDENCE_INVALID_FAIL_CLOSED"


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S04P02-TARGETED-PYTEST")
    assert "S04P02-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize(
    "path,replacement",
    [
        (["status"], "FAIL"),
        (["next"], "S04/P01_REMEDIATION_REQUIRED"),
        (["external_effect_boundary", "production_activated"], True),
        (["hashes", "code"], "0" * 64),
    ],
)
def test_p01_prerequisite_receipt_mutations_block_p02(tmp_path: Path, path: list[str], replacement) -> None:
    root = _clone_project(tmp_path)
    receipt_path = root / "machine/evidence/EVD-S04-P01.json"
    receipt = strict_json_load(receipt_path)
    _set_or_delete_path(receipt, path, replacement)
    _write_json(receipt_path, receipt)
    _failed(evaluate_contract(root), "S04P02-P01-PREREQUISITE")


def test_p03_and_later_work_is_not_started() -> None:
    forbidden = [
        Path("release_slots.json"),
        Path("feature_flags.json"),
        Path("rollback.sh"),
        Path("tests/S04/P03_test.py"),
        Path("machine/tests/fixtures/S04_P03.json"),
        Path("machine/evidence/EVD-S04-P03.json"),
        Path("machine/evidence/EVD-S04-P03_rollback.json"),
    ]
    assert not [path.as_posix() for path in forbidden if (ROOT / path).exists()]
    rows = [json.loads(line) for line in (ROOT / "machine/evidence/evidence_index.jsonl").read_text(encoding="utf-8-sig").splitlines() if line]
    p03 = [row for row in rows if row["id"] == "INDEX-AC-S04-P03"]
    assert len(p03) == 1
    assert p03[0]["status"] == "PLANNED"
    assert "actual_artifact" not in p03[0]


@pytest.mark.parametrize("source", FIXTURE["official_sources"], ids=lambda row: row["id"])
def test_every_source_receipt_is_current_official_cloudflare_and_portable(source: dict) -> None:
    assert source["publisher"] == "Cloudflare"
    assert source["retrieved_at"] == "2026-07-22"
    assert source["url"].startswith("https://developers.cloudflare.com/")
    assert source["fact"]
    rendered = json.dumps(source, ensure_ascii=False, sort_keys=True)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered


def test_mainland_china_network_is_explicitly_outside_zero_cash_scope() -> None:
    claims = POLICY["claims"]
    budget = POLICY["budget"]
    assert claims["mainland_china_acceleration_availability_or_reach"] == "NOT_IN_ZERO_CASH_SCOPE_NO_CLAIM"
    assert budget["china_network_subscription_allowed"] is False
    assert "Enterprise 单独订阅" in POLICY_TEXT
    assert "ICP" in POLICY_TEXT
    assert "不代表中国大陆境内加速、可用性或可达性保证" in DEGRADED_PAGE


def test_a300_a0_no_order_and_no_return_guarantee_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["product"]["monthly_target_return"] == "0.30"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert parameters["target_30pct"]["guaranteed"] is False
    assert parameters["target_30pct"]["shortfall_behavior"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert set(costs["incremental_cash_budget"].values()) == {"0.00"}


@pytest.mark.parametrize("key,expected", sorted(EXTERNAL_EFFECT_BOUNDARY.items()))
def test_every_external_effect_boundary_is_explicit_and_false_or_zero(key: str, expected) -> None:
    assert FIXTURE["expected_external_effect_boundary"][key] == expected
    if key == "incremental_cash_spent_aud":
        assert expected == "0.00"
    else:
        assert expected is False


def test_taskpack_artifacts_commands_and_local_paths_remain_exact() -> None:
    assert CONTRACT_ID == "AC-S04-P02"
    assert FIXTURE["expected_artifacts"] == {
        "ART-S04-P02-01": "infra/cloudflared.yml",
        "ART-S04-P02-02": "access_policy.md",
        "ART-S04-P02-03": "degraded_page.html",
    }
    assert TEST_PATH == Path("tests/S04/P02_test.py")
    assert PACK_REPORT_PATH == Path("machine/evidence/validation_report.json")
    assert SCAN_REPORT_PATH == Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S04-P02": write_cloudflare_edge_phase_evidence' in source
    rendered = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in [ROOT / CONFIG_PATH, ROOT / POLICY_PATH, ROOT / DEGRADED_PAGE_PATH, ROOT / FIXTURE_PATH])
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
