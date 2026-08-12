from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_abd_scoped_explicit_authority_record_intake import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError,
    build_receipt,
    evaluate_intake,
    intake_explicit_authority_record,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_abd_scoped_explicit_authority_record_intake_contract_002.json"
RUNNER_PATH = RUNTIME / "run_current_production_abd_scoped_explicit_authority_record_intake.sh"
MODULE_PATH = RUNTIME / "current_production_abd_scoped_explicit_authority_record_intake.py"
UTC_TODAY = datetime.now(timezone.utc).date().isoformat()


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _record(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "record_type": "ABD_CURRENT_PRODUCTION_AUTHORITY_RECORD",
        "product": "ABD",
        "product_version": "0.0.0.1",
        "observed_on": UTC_TODAY,
        "noninteractive_only": True,
        "controlled_target_reference": "test-target-alias",
        "owner_task_authorization": "CURRENT_TASK_AUTHORIZED",
    }
    values.update(overrides)
    return values


def _write_record(root: Path, record: dict[str, object], name: str = "abd_authority_record.json") -> Path:
    path = root / name
    path.write_text(json.dumps(record), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def test_contract_preserves_read_only_nonsecret_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_tree_depth"] == 12
    assert expected["maximum_tree_entries"] == 512
    assert expected["require_exactly_one_valid_authority_record"] is True
    assert expected["controlled_target_reference_must_be_nonsecret_opaque_identifier"] is True
    assert boundary["candidate_json_key_set_checked_before_value_parse"] is True
    assert boundary["only_one_valid_authority_record_may_authorize_source"] is True
    assert boundary["target_mapping_emitted_or_persisted"] is False
    assert boundary["ssh_connection_attempted"] is False


def test_valid_explicit_record_is_only_ready_for_a_separate_mapping_phase(tmp_path: Path) -> None:
    _write_record(tmp_path, _record())

    facts = intake_explicit_authority_record(tmp_path)
    result = evaluate_intake(_contract(), facts)

    assert facts["authority_record_state"] == "RESOLVED_IN_MEMORY"
    assert facts["authority_record_ready"] is True
    assert facts["candidate_target_reference_parsed_in_memory_only"] is True
    assert facts["unique_valid_authority_record_checked_in_memory_only"] is True
    assert result["status"] == PASS_STATUS
    assert result["source_authority_ready"] is True
    assert result["target_mapping_authorized"] is False
    assert result["transport_retry_authorized"] is False


def test_missing_record_is_a_completed_intake_without_authority(tmp_path: Path) -> None:
    facts = intake_explicit_authority_record(tmp_path)
    result = evaluate_intake(_contract(), facts)

    assert facts["authority_record_state"] == "NO_EXPLICIT_AUTHORITY_RECORD_REDACTED"
    assert facts["authority_record_ready"] is False
    assert result["status"] == PASS_STATUS
    assert result["source_authority_ready"] is False
    assert result["decision"] == "ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_NOT_PROVEN_NO_TARGET_OR_TRANSPORT_ACTION_AUTHORIZED"


def test_unexpected_fields_are_rejected_before_candidate_values_are_parsed(tmp_path: Path) -> None:
    _write_record(tmp_path, _record(unexpected_field="not-permitted"))

    facts = intake_explicit_authority_record(tmp_path)

    assert facts["authority_record_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert facts["authority_record_ready"] is False
    assert facts["candidate_record_key_set_checked_in_memory_only"] is True
    assert facts["candidate_target_reference_parsed_in_memory_only"] is False


def test_stale_record_cannot_be_ready(tmp_path: Path) -> None:
    _write_record(tmp_path, _record(observed_on="2000-01-01"))

    facts = intake_explicit_authority_record(tmp_path)

    assert facts["authority_record_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert facts["authority_record_ready"] is False


def test_multiple_valid_records_cannot_authorize_a_target(tmp_path: Path) -> None:
    _write_record(tmp_path, _record(), "abd_authority_record_one.json")
    _write_record(tmp_path, _record(), "abd_authority_record_two.json")

    facts = intake_explicit_authority_record(tmp_path)
    result = evaluate_intake(_contract(), facts)

    assert facts["authority_record_state"] == "AMBIGUOUS_EXPLICIT_AUTHORITY_RECORD_REDACTED"
    assert facts["authority_record_ready"] is False
    assert facts["unique_valid_authority_record_checked_in_memory_only"] is True
    assert result["source_authority_ready"] is False


@pytest.mark.parametrize(
    "target_reference",
    ("user:password@host", "https://target", "/private/path", " target-alias", "target alias"),
)
def test_credential_bearing_or_endpoint_target_reference_cannot_be_ready(tmp_path: Path, target_reference: str) -> None:
    _write_record(tmp_path, _record(controlled_target_reference=target_reference))

    facts = intake_explicit_authority_record(tmp_path)

    assert facts["authority_record_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert facts["authority_record_ready"] is False


def test_unsafe_permissions_are_not_opened(tmp_path: Path) -> None:
    path = _write_record(tmp_path, _record())
    os.chmod(path, 0o644)

    facts = intake_explicit_authority_record(tmp_path)

    assert facts["authority_record_state"] == "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    assert facts["authority_record_ready"] is False
    assert facts["candidate_record_key_set_checked_in_memory_only"] is False


def test_scan_limit_cannot_authorize_a_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import current_production_abd_scoped_explicit_authority_record_intake as module

    nested = tmp_path / "nested"
    nested.mkdir()
    _write_record(nested, _record())
    monkeypatch.setattr(module, "MAX_TREE_DEPTH", 1)

    facts = module.intake_explicit_authority_record(tmp_path)

    assert facts["bounded_scan_state"] == "TRUNCATED_REDACTED"
    assert facts["authority_record_state"] == "SCAN_LIMIT_REACHED_REDACTED"
    assert facts["authority_record_ready"] is False


def test_fact_validation_rejects_stale_dates_and_outbound_actions() -> None:
    facts = intake_explicit_authority_record(Path("/definitely-not-present"))
    facts["observed_on"] = "2000-01-01"
    with pytest.raises(CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError, match="not current UTC"):
        validate_facts(facts)

    facts = intake_explicit_authority_record(Path("/definitely-not-present"))
    facts["provider_api_requests"] = 1
    with pytest.raises(CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError, match="outbound operation count"):
        validate_facts(facts)


def test_receipt_is_redacted_and_no_action_is_authorized(tmp_path: Path) -> None:
    receipt = build_receipt(_contract(), intake_explicit_authority_record(tmp_path))
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["source_authority_ready"] is False
    assert receipt["target_mapping_authorized"] is False
    assert receipt["core_start_authorized"] is False
    assert '"controlled_target_reference":' not in serialized
    assert '"credential":' not in serialized
    assert '"hostname":' not in serialized


def test_contract_cannot_relax_the_source_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["provider_api_request_sent"] = True

    with pytest.raises(CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError, match="source boundary"):
        validate_contract(contract)


def test_runner_and_module_have_no_network_or_mutation_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--protected-root" in runner
    assert "current_production_abd_scoped_explicit_authority_record_intake.py" in runner
    for forbidden in (
        "import socket",
        "import subprocess",
        "import requests",
        "import urllib",
        "curl ",
        "wget ",
        "gh ",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in module


def test_unavailable_root_fails_closed_without_a_scan() -> None:
    facts = intake_explicit_authority_record(Path("/definitely-not-present"))
    result = evaluate_intake(_contract(), facts)

    assert facts["protected_root_state"] == "UNAVAILABLE_REDACTED"
    assert facts["bounded_scan_state"] == "NOT_ATTEMPTED"
    assert result["status"] == FAIL_STATUS
    assert result["source_authority_ready"] is False
