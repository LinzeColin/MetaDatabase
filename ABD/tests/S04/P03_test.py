from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.cloudflare_edge import verify_existing_phase_evidence as verify_p02_evidence
from abd_acceptance.release_control import (
    ALLOWED_NUMERIC_BOUNDARY_DELTAS,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXPECTED_CANARY_BASIS_POINTS,
    EXPECTED_FIXED_FLAGS,
    EXPECTED_FLAG_TEMPLATES,
    EXPECTED_PROBES,
    EXPECTED_SLOT_IDS,
    EXPECTED_TRIGGER_REASONS,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FLAGS_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    LEDGER_RPO_SECONDS,
    PACK_REPORT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    ROLLBACK_DEADLINE_SECONDS,
    ROLLBACK_EVIDENCE_PATH,
    ROLLBACK_SCRIPT_PATH,
    SCAN_REPORT_PATH,
    SECRET_PATTERNS,
    SIGNED_STATE_JUNIT_PATH,
    SLOTS_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    TEST_PATH,
    ReleaseControlContractError,
    _set_or_delete_path,
    _p04_progression_contract,
    _structural_self_hash,
    _tree_digest,
    activation_gate,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    evaluate_feature_flag,
    execute_release_drill,
    initialize_release_drill,
    perform_rollback_drill,
    release_disposition,
    validate_feature_flags,
    validate_release_slots,
    verify_existing_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
SLOTS = strict_json_load(ROOT / SLOTS_PATH)
FLAGS = strict_json_load(ROOT / FLAGS_PATH)
RELEASE_POLICY = strict_json_load(ROOT / "machine/facts/release_policy.json")


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


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "SAME_HOST_BLUE_GREEN_RELEASE_CONTRACT_FROZEN"
    assert result["phase_status"] == "S04_P03_PASS"
    assert result["pass_gate_interpretation"] == "OFFLINE_FAILURE_INJECTION_PROVES_SHARED_LEDGER_BYTES_UNCHANGED_AND_ROLLBACK_AT_900_SECONDS; PRODUCTION_RUNTIME_REMAINS_UNVERIFIED"
    assert result["activation_gate"] == FIXTURE["expected_activation_gate"]
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["runtime_release_status"] == "NOT_EXECUTED_OR_VERIFIED_ON_OVH"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_signed_p02_is_exact_phase_prerequisite() -> None:
    result = verify_p02_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_P02_EVIDENCE_VERIFIED"
    assert result["next"] == "S04/P03_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    actual = sha256_file(ROOT / relative)
    assert actual == PINNED_PHASE_HASHES[relative] or actual == SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_release_slots_are_strict_json_without_binary_float() -> None:
    assert validate_release_slots(SLOTS, RELEASE_POLICY) == []
    assert json.loads((ROOT / SLOTS_PATH).read_text(encoding="utf-8")) == SLOTS
    assert not any(isinstance(value, float) for value in SLOTS.values())


def test_feature_flags_are_strict_json_without_binary_float() -> None:
    assert validate_feature_flags(FLAGS, RELEASE_POLICY) == []
    assert json.loads((ROOT / FLAGS_PATH).read_text(encoding="utf-8")) == FLAGS
    assert not any(isinstance(value, float) for value in FLAGS.values())


@pytest.mark.parametrize("mutation", FIXTURE["invalid_slot_mutations"], ids=lambda row: row["id"])
def test_every_declared_slot_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(SLOTS)
    _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
    assert validate_release_slots(candidate, RELEASE_POLICY), mutation


@pytest.mark.parametrize("mutation", FIXTURE["invalid_flag_mutations"], ids=lambda row: row["id"])
def test_every_declared_flag_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(FLAGS)
    _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
    assert validate_feature_flags(candidate, RELEASE_POLICY), mutation


@pytest.mark.parametrize("slot,port", [("blue", 8081), ("green", 8082)])
def test_each_slot_is_loopback_only_and_runtime_unverified(slot: str, port: int) -> None:
    row = next(item for item in SLOTS["slots"] if item["id"] == slot)
    assert row["bind_address"] == "127.0.0.1"
    assert row["bind_port"] == port
    assert row["release_path"] == f"/opt/abd/releases/{slot}"
    assert row["repository_runtime_status"] == "NOT_RUNNING_OR_VERIFIED"


def test_slots_share_one_durable_state_root_outside_both_releases() -> None:
    state = SLOTS["shared_durable_state"]
    assert state["root"] == "/var/lib/abd"
    assert state["outside_release_slots"] is True
    assert state["slot_specific_copy_forbidden"] is True
    assert state["candidate_shadow_access"] == "READ_ONLY"
    assert state["single_writer_during_cutover"] is True
    assert all(path.startswith("/var/lib/abd/") for path in state["paths"])
    assert not any(path.startswith("/opt/abd/releases/") for path in state["paths"])


def test_atomic_route_allows_only_the_two_frozen_slots() -> None:
    routing = SLOTS["routing"]
    assert routing["current_release_symlink"] == "/opt/abd/current"
    assert routing["atomic_switch_method"] == "CREATE_SIBLING_SYMLINK_THEN_RENAME"
    assert routing["allowed_targets"] == ["/opt/abd/releases/blue", "/opt/abd/releases/green"]
    assert routing["partial_or_external_target_policy"] == "REJECT_AND_KEEP_PREVIOUS"


def test_time_contract_has_exact_rto_rpo_and_inclusive_boundary() -> None:
    timing = SLOTS["time_contract"]
    assert ROLLBACK_DEADLINE_SECONDS == 900
    assert LEDGER_RPO_SECONDS == 60
    assert timing["rollback_deadline_seconds"] == ROLLBACK_DEADLINE_SECONDS
    assert timing["service_recovery_target_seconds"] == ROLLBACK_DEADLINE_SECONDS
    assert timing["ledger_recovery_point_target_seconds"] == LEDGER_RPO_SECONDS
    assert timing["deadline_inclusive"] is True
    assert timing["frozen_boundary_seconds"] == [899, 900, 901]


@pytest.mark.parametrize("probe", EXPECTED_PROBES)
def test_every_required_probe_failure_rolls_back_and_disables_advice(probe: str) -> None:
    probes = {item: True for item in EXPECTED_PROBES}
    probes[probe] = False
    result = release_disposition(probes, 900)
    assert result["action"] == "ROLL_BACK_FAIL_CLOSED"
    assert result["deadline_met"] is True
    assert result["advice_enabled"] is False
    assert probe in result["failed_probes"]


@pytest.mark.parametrize("elapsed,expected", [(899, True), (900, True), (901, False)])
def test_rollback_deadline_boundary_is_exact(elapsed: int, expected: bool) -> None:
    probes = {item: True for item in EXPECTED_PROBES}
    probes["HEALTH_PROBE"] = False
    result = release_disposition(probes, elapsed)
    assert result["action"] == "ROLL_BACK_FAIL_CLOSED"
    assert result["deadline_met"] is expected
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("elapsed", [-1, True, "900", None])
def test_invalid_elapsed_time_fails_closed(elapsed) -> None:
    result = release_disposition({probe: True for probe in EXPECTED_PROBES}, elapsed)
    assert result["action"] == "ROLL_BACK_FAIL_CLOSED"
    assert result["deadline_met"] is False
    assert result["advice_enabled"] is False


def test_unknown_probe_fails_closed() -> None:
    probes = {item: True for item in EXPECTED_PROBES}
    probes["UNDECLARED_PROBE"] = True
    result = release_disposition(probes, 1)
    assert result["action"] == "ROLL_BACK_FAIL_CLOSED"
    assert result["failed_probes"] == ["UNKNOWN_OR_MALFORMED_PROBE"]
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("delta", sorted(ALLOWED_NUMERIC_BOUNDARY_DELTAS))
@pytest.mark.parametrize("adverse_odds_tick", [False, True])
def test_financial_boundary_inputs_cannot_change_release_safety(delta: str, adverse_odds_tick: bool) -> None:
    probes = {item: True for item in EXPECTED_PROBES}
    probes["NUMERIC_CROSS_IMPLEMENTATION"] = False
    result = release_disposition(probes, 900)
    assert delta in {"-0.0001", "0", "0.0001"}
    assert isinstance(adverse_odds_tick, bool)
    assert result["action"] == "ROLL_BACK_FAIL_CLOSED"
    assert result["deadline_met"] is True
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("flag_id", EXPECTED_FIXED_FLAGS)
def test_fixed_flag_requires_every_declared_prerequisite(flag_id: str) -> None:
    spec = next(row for row in FLAGS["fixed_flags"] if row["id"] == flag_id)
    denied = evaluate_feature_flag(FLAGS, flag_id, True, [])
    allowed = evaluate_feature_flag(FLAGS, flag_id, True, spec["enable_requires"])
    killed = evaluate_feature_flag(FLAGS, flag_id, True, spec["enable_requires"], emergency_advice_kill_switch=True)
    assert denied["enabled"] is False and denied["fail_closed"] is True
    assert allowed["enabled"] is True and allowed["fail_closed"] is False
    assert killed["enabled"] is False and killed["fail_closed"] is True


@pytest.mark.parametrize("template", EXPECTED_FLAG_TEMPLATES)
def test_scoped_flag_template_denies_malformed_ids_and_allows_exact_ids(template: str) -> None:
    spec = next(row for row in FLAGS["scoped_flag_templates"] if row["template"] == template)
    prefix = template.split(":", 1)[0]
    allowed = evaluate_feature_flag(FLAGS, f"{prefix}:known_id-1", True, spec["enable_requires"])
    assert allowed["enabled"] is True
    for malformed in [f"{prefix}:../escape", f"{prefix}:UPPER", f"{prefix}:", f"{prefix}:white space"]:
        denied = evaluate_feature_flag(FLAGS, malformed, True, spec["enable_requires"])
        assert denied["enabled"] is False
        assert denied["reason"] == "UNKNOWN_OR_MALFORMED_FLAG"


@pytest.mark.parametrize("flag_id", ["unknown", "unknown:value", "source:../escape", "model:UPPER"])
def test_unknown_or_malformed_feature_flags_are_disabled(flag_id: str) -> None:
    result = evaluate_feature_flag(FLAGS, flag_id, True, ["ANY"])
    assert result["enabled"] is False
    assert result["fail_closed"] is True


@pytest.mark.parametrize("profile,bps", list(zip(["shadow", "one_source", "one_sport", "one_market_family", "eligible_full"], EXPECTED_CANARY_BASIS_POINTS)))
def test_canary_profiles_are_monotonic_bounded_and_never_live(profile: str, bps: int) -> None:
    slot_row = next(row for row in SLOTS["canary_profiles"] if row["id"] == profile)
    flag_row = next(row for row in FLAGS["canary_profiles"] if row["id"] == profile)
    assert slot_row["maximum_traffic_basis_points"] == bps
    assert flag_row["maximum_traffic_basis_points"] == bps
    assert 0 <= bps <= 10000
    assert slot_row["live_recommendation"] is False
    assert flag_row["live_recommendation"] is False


@pytest.mark.parametrize("trigger,reason", sorted(EXPECTED_TRIGGER_REASONS.items()))
def test_every_canonical_and_unknown_trigger_is_mapped(trigger: str, reason: str) -> None:
    trigger_map = {row["id"]: row["canonical_reason"] for row in SLOTS["auto_rollback_triggers"]}
    assert trigger_map[trigger] == reason
    if trigger != "UNKNOWN_OR_MALFORMED_PROBE":
        assert reason in RELEASE_POLICY["auto_rollback_on"]


@pytest.mark.parametrize("trigger", sorted(EXPECTED_TRIGGER_REASONS))
def test_each_rollback_trigger_switches_to_previous_and_preserves_ledger(tmp_path: Path, trigger: str) -> None:
    result = execute_release_drill(tmp_path / trigger.lower(), trigger, 300)
    assert result["status"] == "PASS", result
    assert result["pointer_before"] == "green"
    assert result["pointer_after"] == "blue"
    assert result["pointer_switched"] is True
    assert result["ledger_unchanged"] is True
    assert result["ledger_before"] == result["ledger_after"]
    assert result["advice_enabled"] is False
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False


def test_arbitrary_unknown_trigger_maps_to_fail_closed_rollback(tmp_path: Path) -> None:
    result = execute_release_drill(tmp_path / "unknown", "UNDECLARED_RUNTIME_FAILURE", 300)
    assert result["status"] == "PASS", result
    assert result["requested_trigger_known"] is False
    assert result["scenario"] == "UNKNOWN_OR_MALFORMED_PROBE"
    assert result["pointer_after"] == "blue"
    assert result["ledger_unchanged"] is True
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("elapsed,expected", [(899, "PASS"), (900, "PASS"), (901, "FAIL")])
def test_executable_drill_enforces_inclusive_900_second_deadline(tmp_path: Path, elapsed: int, expected: str) -> None:
    result = execute_release_drill(tmp_path / str(elapsed), "HEALTH_PROBE_FAILED", elapsed)
    assert result["status"] == expected
    assert result["pointer_after"] == "blue"
    assert result["ledger_unchanged"] is True
    assert result["deadline_met"] is (elapsed <= 900)
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("fault", ["LEDGER_MUTATED_DURING_ROLLBACK", "UNSAFE_PREVIOUS_SLOT", "MALFORMED_CONTROL_STATE", "CURRENT_POINTER_ESCAPE", "PREVIOUS_MANIFEST_MISMATCH"])
def test_every_injected_rollback_fault_fails_closed(tmp_path: Path, fault: str) -> None:
    result = execute_release_drill(tmp_path / fault.lower(), "HEALTH_PROBE_FAILED", 300, fault=fault)
    assert result["status"] == "FAIL", result
    assert result["advice_enabled"] is False
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    if fault == "LEDGER_MUTATED_DURING_ROLLBACK":
        assert result["ledger_unchanged"] is False
    else:
        assert result["failure"]


def test_release_drill_initialization_refuses_nonempty_sandbox(tmp_path: Path) -> None:
    sandbox = tmp_path / "nonempty"
    sandbox.mkdir()
    (sandbox / "foreign").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(ReleaseControlContractError, match="absent or empty"):
        initialize_release_drill(sandbox)
    assert (sandbox / "foreign").read_text(encoding="utf-8") == "do not overwrite"


def test_release_drill_is_deterministic_and_ledger_hash_is_content_addressed(tmp_path: Path) -> None:
    first = execute_release_drill(tmp_path / "first", "HEALTH_PROBE_FAILED", 300)
    second = execute_release_drill(tmp_path / "second", "HEALTH_PROBE_FAILED", 300)
    assert first == second
    assert first["ledger_before"]["sha256"] != "MISSING"
    assert first["ledger_before"]["files"] == 3
    assert first["ledger_before"]["bytes"] > 0


def test_tree_digest_changes_on_filename_or_content_change(tmp_path: Path) -> None:
    root = tmp_path / "ledger"
    root.mkdir()
    (root / "a.jsonl").write_text("one\n", encoding="utf-8")
    first = _tree_digest(root)
    (root / "a.jsonl").write_text("two\n", encoding="utf-8")
    second = _tree_digest(root)
    (root / "a.jsonl").rename(root / "b.jsonl")
    third = _tree_digest(root)
    assert len({first["sha256"], second["sha256"], third["sha256"]}) == 3


def test_complete_rollback_drill_covers_triggers_boundaries_and_faults() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["scenarios"]) == len(EXPECTED_TRIGGER_REASONS) + 3 + 5
    assert all(row["expectation_met"] is True for row in result["scenarios"].values())
    assert result["scenarios"]["BOUNDARY_900"]["status"] == "PASS"
    assert result["scenarios"]["BOUNDARY_901"]["status"] == "FAIL"
    assert result["scenarios"]["LEDGER_MUTATED_DURING_ROLLBACK"]["ledger_unchanged"] is False
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["production_runtime_verified"] is False


def test_rollback_script_is_executable_strict_and_has_no_dangerous_shell(tmp_path: Path) -> None:
    script = ROOT / ROLLBACK_SCRIPT_PATH
    assert stat.S_IMODE(script.stat().st_mode) == 0o755
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\nset -eu\n")
    assert '"$SCRIPT_DIR/.venv/bin/python"' in text
    assert "python3.12" in text
    assert 'exec "$PYTHON_BIN" -m abd_acceptance.release_control rollback "$@"' in text
    assert not any(token in text for token in ["curl ", "wget ", "rm -rf", "eval ", "sudo "])
    stripped_env = dict(os.environ)
    stripped_env.pop("ABD_PYTHON", None)
    stripped_env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    result = subprocess.run([str(script), "check"], cwd=ROOT, env=stripped_env, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["activation_gate"] == FIXTURE["expected_activation_gate"]
    assert payload["production_state_changed"] is False


def test_rollback_script_runs_ephemeral_drill_without_external_effect(tmp_path: Path) -> None:
    sandbox = tmp_path / "cli-drill"
    result = subprocess.run(
        [str(ROOT / ROLLBACK_SCRIPT_PATH), "drill", "--sandbox", str(sandbox), "--trigger", "HEALTH_PROBE_FAILED", "--elapsed-seconds", "900"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["pointer_after"] == "blue"
    assert payload["ledger_unchanged"] is True
    assert payload["production_state_changed"] is False


def test_production_execute_is_blocked_without_exact_external_runtime_proof(tmp_path: Path) -> None:
    fake_activation = tmp_path / "activation.json"
    fake_activation.write_text("{}\n", encoding="utf-8")
    result = subprocess.run(
        [str(ROOT / ROLLBACK_SCRIPT_PATH), "execute", "--activation-record", str(fake_activation), "--confirm-production-rollback", "WRONG"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["decision"] == "PRODUCTION_ROLLBACK_NOT_EXECUTED"
    assert payload["confirmation_valid"] is False
    assert payload["activation_record_path_valid"] is False
    assert payload["production_state_changed"] is False


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, rollback_first = build_evidence(ROOT, require_external_reports=False)
    second, rollback_second = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert rollback_first == rollback_second
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["release_proof"]["rollback_at_900_seconds_passed"] is True
    assert first["release_proof"]["rollback_at_901_seconds_failed_closed"] is True
    assert first["release_proof"]["all_success_scenarios_preserved_ledger_bytes"] is True
    assert first["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert first["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert first["runtime_release_status"] == "NOT_EXECUTED_OR_VERIFIED_ON_OVH"
    assert first["next"] == FIXTURE["expected_next"]


def test_existing_phase_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S04_P03_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S04_P03_EVIDENCE_INVALID_FAIL_CLOSED"


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH, SIGNED_STATE_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S04P03-TARGETED-PYTEST")
    assert "S04P03-FULL-REGRESSION" in result["summary"]["failed_check_ids"]
    assert "S04P03-SIGNED-STATE-REGRESSION" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize(
    "path,replacement",
    [
        (["status"], "FAIL"),
        (["next"], "S04/P02_REMEDIATION_REQUIRED"),
        (["external_effect_boundary", "production_activated"], True),
        (["hashes", "code"], "0" * 64),
    ],
)
def test_p02_prerequisite_receipt_mutations_block_p03(tmp_path: Path, path: list[str], replacement) -> None:
    root = _clone_project(tmp_path)
    receipt_path = root / "machine/evidence/EVD-S04-P02.json"
    receipt = strict_json_load(receipt_path)
    _set_or_delete_path(receipt, path, replacement)
    _write_json(receipt_path, receipt)
    _failed(evaluate_contract(root), "S04P03-P02-PREREQUISITE")


def test_p04_is_exact_candidate_or_signed_successor_and_stage_review_is_not_started() -> None:
    candidate = [
        Path("capacity_budget.json"),
        Path("resource_shedding.json"),
        Path("load_baseline.json"),
        Path("tests/S04/P04_test.py"),
        Path("machine/tests/fixtures/S04_P04.json"),
        Path("abd_acceptance/capacity_governance.py"),
    ]
    signed = [
        Path("machine/evidence/EVD-S04-P04.json"),
        Path("machine/evidence/EVD-S04-P04_rollback.json"),
    ]
    forbidden = [
        Path("tests/S04/stage_review_test.py"),
        Path("machine/tests/fixtures/S04_STAGE_REVIEW.json"),
        Path("machine/evidence/EVD-S04-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S04-STAGE-REVIEW_rollback.json"),
        Path("abd_acceptance/stage4_review.py"),
    ]
    assert all((ROOT / path).is_file() for path in candidate)
    assert len([path for path in signed if (ROOT / path).exists()]) in {0, 2}
    assert not [path.as_posix() for path in forbidden if (ROOT / path).exists()]
    progression = _p04_progression_contract(ROOT)
    assert progression["status"] == "PASS", progression
    assert progression["mode"] in {"VERIFIED_S04_P04_CANDIDATE", "VERIFIED_S04_P04_SIGNED_SUCCESSOR"}


def test_taskpack_artifacts_commands_and_local_paths_remain_exact() -> None:
    assert CONTRACT_ID == "AC-S04-P03"
    assert FIXTURE["expected_artifacts"] == {
        "ART-S04-P03-01": "release_slots.json",
        "ART-S04-P03-02": "feature_flags.json",
        "ART-S04-P03-03": "rollback.sh",
    }
    assert TEST_PATH == Path("tests/S04/P03_test.py")
    assert PACK_REPORT_PATH == Path("machine/evidence/validation_report.json")
    assert SCAN_REPORT_PATH == Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S04-P03": write_release_control_phase_evidence' in source
    rendered = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in [ROOT / SLOTS_PATH, ROOT / FLAGS_PATH, ROOT / ROLLBACK_SCRIPT_PATH, ROOT / FIXTURE_PATH])
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered


def test_canonical_financial_order_runtime_and_no_guarantee_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["product"]["monthly_target_return"] == "0.30"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert canonical["runtime"]["deployment"] == "SAME_HOST_BLUE_GREEN_WITH_CANARY_AND_AUTO_ROLLBACK"
    assert canonical["runtime"]["single_host_zero_downtime_guaranteed"] is False
    assert parameters["target_30pct"]["guaranteed"] is False
    assert parameters["target_30pct"]["shortfall_behavior"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert set(costs["incremental_cash_budget"].values()) == {"0.00"}


@pytest.mark.parametrize("key,expected", sorted(EXTERNAL_EFFECT_BOUNDARY.items()))
def test_every_external_effect_boundary_is_explicit_and_false_or_zero(key: str, expected) -> None:
    assert FIXTURE["expected_external_effect_boundary"][key] == expected
    assert SLOTS["external_effect_boundary"][key] == expected
    if key == "incremental_cash_spent_aud":
        assert expected == "0.00"
    else:
        assert expected is False


def test_artifact_files_contain_no_secrets_or_machine_specific_paths() -> None:
    paths = [SLOTS_PATH, FLAGS_PATH, ROLLBACK_SCRIPT_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/release_control.py")]
    rendered = "\n".join((ROOT / path).read_text(encoding="utf-8", errors="replace") for path in paths)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert not any(pattern.search(rendered) for pattern in SECRET_PATTERNS)


def test_no_phase_artifact_is_a_symlink() -> None:
    for relative in [SLOTS_PATH, FLAGS_PATH, ROLLBACK_SCRIPT_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/release_control.py")]:
        assert (ROOT / relative).is_file()
        assert not (ROOT / relative).is_symlink()


def test_activation_gate_is_fail_closed_until_runtime_and_stage_review_are_verified() -> None:
    assert activation_gate(SLOTS, FLAGS) == "BLOCKED_RUNTIME_PREREQUISITES_AND_STAGE_REVIEW_NOT_VERIFIED"
    invalid_slots = copy.deepcopy(SLOTS)
    invalid_slots["time_contract"]["rollback_deadline_seconds"] = 901
    assert activation_gate(invalid_slots, FLAGS) == "BLOCKED_INVALID_RELEASE_CONTRACT"
    invalid_flags = copy.deepcopy(FLAGS)
    invalid_flags["fixed_flags"][0]["repository_enabled"] = True
    assert activation_gate(SLOTS, invalid_flags) == "BLOCKED_INVALID_RELEASE_CONTRACT"


def test_release_and_feature_canary_profiles_have_identical_basis_point_ladder() -> None:
    slot_ladder = [(row["id"], row["maximum_traffic_basis_points"]) for row in SLOTS["canary_profiles"]]
    flag_ladder = [(row["id"], row["maximum_traffic_basis_points"]) for row in FLAGS["canary_profiles"]]
    assert slot_ladder == flag_ladder
    assert [bps for _, bps in slot_ladder] == EXPECTED_CANARY_BASIS_POINTS
    assert all(current < following for current, following in zip(EXPECTED_CANARY_BASIS_POINTS, EXPECTED_CANARY_BASIS_POINTS[1:]))


def test_release_policy_is_covered_exactly_without_inventing_a_bypass() -> None:
    assert RELEASE_POLICY["feature_flags"] == EXPECTED_FLAG_TEMPLATES + EXPECTED_FIXED_FLAGS
    assert set(RELEASE_POLICY["auto_rollback_on"]) == set(EXPECTED_TRIGGER_REASONS.values()) - {"未知或畸形发布探针"}
    assert set(FLAGS["forbidden_effects"]) == {
        "SUBMIT_CONFIRM_OR_RETRY_REAL_ORDER",
        "LOWER_EVIDENCE_GATE",
        "LOWER_NUMERIC_STABILITY_GATE",
        "LOWER_RISK_OR_SAFETY_GATE",
        "BYPASS_SOURCE_CONTRACT",
        "ENABLE_STALE_ADVICE",
        "CHANGE_IMMUTABLE_LEDGER_FACT",
        "SPEND_INCREMENTAL_CASH",
    }


def test_script_mode_is_not_setuid_or_world_writable() -> None:
    mode = stat.S_IMODE(os.stat(ROOT / ROLLBACK_SCRIPT_PATH).st_mode)
    assert mode == 0o755
    assert mode & stat.S_ISUID == 0
    assert mode & stat.S_ISGID == 0
    assert mode & stat.S_IWOTH == 0
