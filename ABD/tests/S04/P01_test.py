from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from abd_acceptance.canonical_facts import DuplicateKeyError, sha256_file, strict_json_load
from abd_acceptance.cloudflare_edge import verify_existing_phase_evidence as verify_p02_evidence
from abd_acceptance.infrastructure_iac import (
    COMPOSE_PATH,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    InfrastructureContractError,
    JUNIT_PATH,
    PACK_REPORT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    REBUILD_PATH,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    SCHEMA_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    SYSTEMD_PATH,
    TEST_PATH,
    _set_path,
    _structural_self_hash,
    _tree_hash,
    activation_gate,
    build_evidence,
    build_runtime_env,
    evaluate_contract as _evaluate_contract,
    parse_systemd_unit,
    perform_rollback_drill,
    rebuild_bundle,
    validate_config,
    verify_existing_phase_evidence,
)
from abd_acceptance.stage3_delivery import RECEIPT_PATH, verify_stage3_delivery


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
SCHEMA = strict_json_load(ROOT / SCHEMA_PATH)
COMPOSE = strict_json_load(ROOT / COMPOSE_PATH)


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


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "INFRASTRUCTURE_IAC_REBUILD_CONTRACT_FROZEN"
    assert result["phase_status"] == "S04_P01_PASS"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["release_status"] == "NOT_READY_S04_P02_TO_P04_AND_STAGE_REVIEW_REQUIRED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_stage3_github_delivery_is_exact_start_prerequisite() -> None:
    result = verify_stage3_delivery(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_DELIVERED_S04_MAY_START"
    assert result["next"] == "S04/P01_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    actual = sha256_file(ROOT / relative)
    assert actual == PINNED_PHASE_HASHES[relative] or actual == SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_schema_is_valid_draft_2020_12_and_accepts_frozen_config() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert validate_config(SCHEMA, FIXTURE["valid_config"]) == []


@pytest.mark.parametrize("mutation", FIXTURE["invalid_mutations"], ids=lambda row: row["id"])
def test_every_declared_config_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(FIXTURE["valid_config"])
    _set_path(candidate, mutation["path"], mutation["value"])
    assert validate_config(SCHEMA, candidate), mutation["id"]


def test_unknown_config_key_fails_closed() -> None:
    candidate = copy.deepcopy(FIXTURE["valid_config"])
    candidate["undeclared"] = True
    assert validate_config(SCHEMA, candidate)


def test_duplicate_json_key_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"host": 1, "host": 2}\n', encoding="utf-8")
    with pytest.raises(DuplicateKeyError):
        strict_json_load(path)


@pytest.mark.parametrize(
    "name,predicate",
    [
        ("digest-only", lambda core: core["image"].startswith("${ABD_IMAGE:?") and core["pull_policy"] == "never" and "build" not in core),
        ("non-root", lambda core: core["user"] == "${ABD_RUNTIME_UID_GID:?ABD_RUNTIME_UID_GID is required}"),
        ("read-only", lambda core: core["read_only"] is True),
        ("drop-capabilities", lambda core: core["cap_drop"] == ["ALL"]),
        ("no-new-privileges", lambda core: core["security_opt"] == ["no-new-privileges:true"]),
        ("fixed-resources", lambda core: [core["cpus"], core["mem_limit"], core["mem_reservation"], core["memswap_limit"], core["pids_limit"]] == ["1.50", "2560m", "1024m", "2560m", 512]),
        ("loopback-only", lambda core: core["ports"] == [{"target": 8080, "published": "${ABD_BIND_PORT:-8080}", "host_ip": "127.0.0.1", "protocol": "tcp"}]),
        ("order-disabled", lambda core: core["environment"]["ABD_ORDER_SUBMISSION_ENABLED"] == "false"),
        ("bounded-logs", lambda core: core["logging"] == {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}}),
    ],
)
def test_compose_security_and_resource_contract(name: str, predicate) -> None:
    assert name
    assert set(COMPOSE["services"]) == {"abd-core", "abd-shadow"}
    assert predicate(COMPOSE["services"]["abd-core"])


def test_compose_mounts_do_not_create_host_paths_and_secret_is_reference_only() -> None:
    core = COMPOSE["services"]["abd-core"]
    assert len(core["volumes"]) == 3
    assert all(row["bind"]["create_host_path"] is False for row in core["volumes"])
    assert {row["target"] for row in core["volumes"]} == {
        "/etc/abd/config.json",
        "/var/lib/abd",
        "/var/log/abd",
    }
    assert "/etc/abd" not in {row["target"] for row in core["volumes"]}
    assert COMPOSE["secrets"] == {
        "abd_runtime_secret": {
            "file": "${ABD_RUNTIME_SECRET_FILE:?host runtime secret file is required}"
        }
    }
    assert core["secrets"] == [{"source": "abd_runtime_secret", "target": "abd_runtime"}]


def test_shadow_profile_is_loopback_read_only_and_hard_bounded() -> None:
    shadow = COMPOSE["services"]["abd-shadow"]
    volumes = {row["target"]: row for row in shadow["volumes"]}
    assert shadow["profiles"] == ["shadow"]
    assert shadow["restart"] == "no"
    assert [shadow["cpus"], shadow["mem_limit"], shadow["mem_reservation"], shadow["memswap_limit"], shadow["pids_limit"]] == ["0.25", "512m", "128m", "512m", 128]
    assert shadow["ports"] == [{
        "target": 8080,
        "published": "${ABD_SHADOW_BIND_PORT:?ABD_SHADOW_BIND_PORT must be 8081 or 8082}",
        "host_ip": "127.0.0.1",
        "protocol": "tcp",
    }]
    assert volumes["/var/lib/abd"]["read_only"] is True
    assert volumes["/etc/abd/config.json"]["read_only"] is True
    assert all(row["bind"]["create_host_path"] is False for row in shadow["volumes"])
    assert shadow["environment"]["ABD_RUNTIME_MODE"] == "SHADOW_READ_ONLY"
    assert shadow["environment"]["ABD_ORDER_SUBMISSION_ENABLED"] == "false"


def test_systemd_unit_has_exact_offline_preflight_and_bounded_start() -> None:
    unit = parse_systemd_unit((ROOT / SYSTEMD_PATH).read_text(encoding="utf-8"))
    assert set(unit) == {"Unit", "Service", "Install"}
    assert unit["Unit"]["ConditionPathExists"] == [
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ]
    assert unit["Service"]["ExecStartPre"] == [
        "/opt/abd/current/infra/rebuild.sh check --config /etc/abd/config.json",
        "/usr/bin/docker compose --project-name abd --env-file /etc/abd/runtime.env --file /opt/abd/current/infra/compose.yml config --quiet",
    ]
    start = unit["Service"]["ExecStart"][0]
    assert "--detach --remove-orphans --wait --wait-timeout 120" in start
    assert "--build" not in start


@pytest.mark.parametrize(
    "text",
    [
        "Key=value\n",
        "[Unit]\n[Unit]\n",
        "[Unit]\nBroken\n",
        "[Unit]\n=value\n",
        "[Unit]\nKey=value\\\n",
    ],
)
def test_malformed_systemd_units_fail_closed(text: str) -> None:
    with pytest.raises(InfrastructureContractError):
        parse_systemd_unit(text)


def test_runtime_environment_contains_only_expected_references() -> None:
    rendered = build_runtime_env(FIXTURE["valid_config"]).decode("utf-8")
    keys = sorted(line.split("=", 1)[0] for line in rendered.splitlines())
    assert keys == FIXTURE["expected_runtime_env_keys"]
    assert FIXTURE["valid_config"]["secrets"]["runtime_secret_file"] in rendered
    assert "secret_value" not in rendered.lower()


def test_rebuild_materializes_identical_offline_bundles(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = rebuild_bundle(ROOT, FIXTURE["valid_config"], first_dir)
    second = rebuild_bundle(ROOT, FIXTURE["valid_config"], second_dir)
    assert first == second
    assert _tree_hash(first_dir) == _tree_hash(second_dir)
    assert sorted(path.relative_to(first_dir).as_posix() for path in first_dir.rglob("*") if path.is_file()) == FIXTURE["expected_bundle_files"]
    assert first["activation_gate"] == FIXTURE["expected_activation_gate"]
    assert first["activation_performed"] is False
    assert first["secret_value_read_or_stored"] is False
    assert (first_dir / "runtime.env").stat().st_mode & 0o777 == 0o600


def test_one_command_wrapper_checks_and_rebuilds_without_host_runtime(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    destination = tmp_path / "bundle"
    _write_json(config_path, FIXTURE["valid_config"])
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PATH"] = str(ROOT / ".venv/bin") + os.pathsep + environment.get("PATH", "")
    check = subprocess.run(
        [str(ROOT / REBUILD_PATH), "check", "--config", str(config_path)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr
    assert json.loads(check.stdout) == {
        "activation_gate": FIXTURE["expected_activation_gate"],
        "secret_values_read": False,
        "status": "PASS",
    }
    rebuild = subprocess.run(
        [str(ROOT / REBUILD_PATH), "rebuild", "--config", str(config_path), "--destination", str(destination)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rebuild.returncode == 0, rebuild.stderr
    assert json.loads(rebuild.stdout)["status"] == "PASS"
    assert (destination / "rebuild_manifest.json").is_file()


def test_rebuild_rejects_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(InfrastructureContractError, match="must not already exist"):
        rebuild_bundle(ROOT, FIXTURE["valid_config"], destination)


def test_rebuild_rejects_invalid_config_before_writing(tmp_path: Path) -> None:
    candidate = copy.deepcopy(FIXTURE["valid_config"])
    candidate["budget"]["incremental_cash_aud"] = "1.00"
    destination = tmp_path / "rejected"
    with pytest.raises(InfrastructureContractError, match="configuration rejected"):
        rebuild_bundle(ROOT, candidate, destination)
    assert not destination.exists()


def test_activation_gate_stays_blocked_in_p01() -> None:
    assert activation_gate(FIXTURE["valid_config"]) == FIXTURE["expected_activation_gate"]
    assert FIXTURE["valid_config"]["activation_requested"] is False


def test_rollback_restores_all_seven_iac_inputs_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert len(result["artifacts"]) == 7
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert all(row["signed_sha256"] == row["restored_sha256"] for row in result["artifacts"].values())
    assert all(row["corrupted_sha256"] != row["signed_sha256"] for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, rollback_first = build_evidence(ROOT, require_external_reports=False)
    second, rollback_second = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert rollback_first == rollback_second
    assert first["status"] == "PASS"
    assert first["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert first["next"] == FIXTURE["expected_next"]


def test_existing_phase_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S04_P01_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S04_P01_EVIDENCE_INVALID_FAIL_CLOSED"


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S04P01-TARGETED-PYTEST")
    assert "S04P01-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize(
    "path,replacement,check_id",
    [
        (["services", "abd-core", "image"], "abd/core:latest", "S04P01-COMPOSE-DIGEST-INPUT-REQUIRED"),
        (["services", "abd-core", "read_only"], False, "S04P01-COMPOSE-HARDENING"),
        (["services", "abd-core", "cpus"], "2.00", "S04P01-COMPOSE-RESOURCE-LIMITS"),
        (["services", "abd-core", "ports"], [{"target": 8080, "published": "8080", "host_ip": "0.0.0.0", "protocol": "tcp"}], "S04P01-COMPOSE-LOOPBACK-ONLY"),
        (["services", "abd-core", "environment", "ABD_ORDER_SUBMISSION_ENABLED"], "true", "S04P01-COMPOSE-NO-ORDER-CAPABILITY"),
        (["services", "abd-core", "logging", "options", "max-file"], "99", "S04P01-COMPOSE-BOUNDED-LOGGING"),
    ],
)
def test_compose_semantic_mutations_fail_closed(tmp_path: Path, path: list[str], replacement, check_id: str) -> None:
    root = _clone_project(tmp_path)
    candidate = strict_json_load(root / COMPOSE_PATH)
    cursor = candidate
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement
    _write_json(root / COMPOSE_PATH, candidate)
    _failed(evaluate_contract(root), check_id)


@pytest.mark.parametrize(
    "path,replacement,check_id",
    [
        (["delivery_status"], "PENDING", "S03DELIVERY-RECEIPT-SHAPE"),
        (["all_required_main_checks_passed"], False, "S03DELIVERY-MAIN-CHECKS-EXACT"),
        (["delivery_cost_gate", "incremental_cash_spent_aud"], "0.01", "S03DELIVERY-ZERO-CASH-DELIVERY-GATE"),
        (["external_effects", "production_deployment_claimed"], True, "S03DELIVERY-EXTERNAL-EFFECTS-EXACT"),
    ],
)
def test_stage3_delivery_receipt_mutations_fail_closed(tmp_path: Path, path: list[str], replacement, check_id: str) -> None:
    root = _clone_project(tmp_path)
    receipt = strict_json_load(root / RECEIPT_PATH)
    cursor = receipt
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement
    _write_json(root / RECEIPT_PATH, receipt)
    _failed(verify_stage3_delivery(root, verify_git_history=False), check_id)


def test_p02_is_signed_and_transitively_verifies_p03_and_p04_progression() -> None:
    candidate = [
        Path("infra/cloudflared.yml"),
        Path("access_policy.md"),
        Path("degraded_page.html"),
        Path("tests/S04/P02_test.py"),
        Path("machine/tests/fixtures/S04_P02.json"),
        Path("abd_acceptance/cloudflare_edge.py"),
    ]
    signed = [
        Path("machine/evidence/EVD-S04-P02.json"),
        Path("machine/evidence/EVD-S04-P02_rollback.json"),
    ]
    assert all((ROOT / path).is_file() for path in candidate)
    assert all((ROOT / path).is_file() for path in signed)
    rows = [json.loads(line) for line in (ROOT / "machine/evidence/evidence_index.jsonl").read_text(encoding="utf-8-sig").splitlines() if line]
    p02 = [row for row in rows if row["id"] == "INDEX-AC-S04-P02"]
    assert len(p02) == 1
    assert p02[0]["status"] == "PASS"
    assert p02[0]["actual_artifact"] == "machine/evidence/EVD-S04-P02.json"
    assert p02[0]["next"] == "S04/P03_READY_NOT_STARTED"
    result = verify_p02_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_P02_EVIDENCE_VERIFIED"


def test_source_receipts_are_official_current_and_portable() -> None:
    sources = FIXTURE["official_sources"]
    assert [row["publisher"] for row in sources] == ["Docker", "Docker", "GitHub"]
    assert all(row["retrieved_at"] == "2026-07-22" for row in sources)
    assert all(row["url"].startswith("https://") for row in sources)
    rendered = json.dumps(FIXTURE, ensure_ascii=False, sort_keys=True)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered


def test_a300_a0_no_order_and_no_return_guarantee_are_unchanged() -> None:
    product = strict_json_load(ROOT / "machine/facts/canonical_facts.json")["product"]
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    assert product["initial_bankroll_aud"] == "300.00"
    assert product["incremental_cash_budget_aud"] == "0.00"
    assert product["monthly_target_return"] == "0.30"
    assert strict_json_load(ROOT / "machine/facts/canonical_facts.json")["scope"]["order_submission_module_present"] is False
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


def test_testpack_artifacts_and_commands_remain_exact() -> None:
    assert CONTRACT_ID == "AC-S04-P01"
    assert FIXTURE["expected_artifacts"] == {
        "ART-S04-P01-01": "infra/compose.yml",
        "ART-S04-P01-02": "infra/systemd",
        "ART-S04-P01-03": "infra/config.schema.json",
    }
    assert TEST_PATH == Path("tests/S04/P01_test.py")
    assert PACK_REPORT_PATH == Path("machine/evidence/validation_report.json")
    assert SCAN_REPORT_PATH == Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
