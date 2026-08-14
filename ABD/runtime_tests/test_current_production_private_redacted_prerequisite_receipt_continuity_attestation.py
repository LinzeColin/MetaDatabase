from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_private_redacted_prerequisite_receipt_continuity_attestation as attestation
from current_production_core_activation_prerequisite_static_evidence_classification_diagnostic import PREREQUISITES
from current_production_private_redacted_prerequisite_receipt_continuity_attestation import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError,
    _receipt_filename,
    build_receipt,
    discover_private_continuity,
    evaluate_attestation,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_private_redacted_prerequisite_receipt_continuity_attestation_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_private_redacted_prerequisite_receipt_continuity_attestation.sh"
MODULE_PATH = RUNTIME / "current_production_private_redacted_prerequisite_receipt_continuity_attestation.py"


class FakePrivateClient:
    REPO = "private-repository"
    BRANCH = "main"
    AREAS = {"Private-MetaDatabase"}

    def __init__(self, manifest: bytes | Exception, objects: dict[str, bytes | Exception]) -> None:
        self.manifest = manifest
        self.objects = objects
        self.calls: list[str] = []

    def _gh(self, args: list[str], retries: int = 1) -> bytes:
        assert retries == 1
        path = args[0]
        self.calls.append(path)
        prefix = "repos/%s/contents/Private-MetaDatabase/" % self.REPO
        relative = path.split(prefix, 1)[1].split("?", 1)[0]
        if relative == "manifest.jsonl":
            if isinstance(self.manifest, Exception):
                raise self.manifest
            return self.manifest
        value = self.objects[relative]
        if isinstance(value, Exception):
            raise value
        return value


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _states(value: str) -> dict[str, str]:
    return {spec.identifier: value for spec in PREREQUISITES}


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "private_manifest_state": "OBSERVED_IN_MEMORY",
        "private_manifest_metadata_read_in_memory_only": True,
        "selected_private_redacted_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 1,
        "prerequisite_states": _states("CANDIDATE_NOT_OBSERVED_REDACTED"),
        "core_activation_prerequisites_ready": False,
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _record(spec: object, observed_on: str = "2026-08-12", suffix: str = "a") -> dict[str, object]:
    assert isinstance(spec, attestation.Prerequisite)
    name = _receipt_filename(spec, observed_on)
    sha = (suffix * 64)[:64]
    return {
        "sha256": sha,
        "original_name": name,
        "size_bytes": 512,
        "domain": "ABD",
        "batch": "current-production",
        "object_path": "objects/%s/%s_%s" % (sha[:2], sha, name),
        "ingested_at": observed_on,
    }


def _receipt(spec: object, ready: bool = True, observed_on: str = "2026-08-12") -> bytes:
    assert isinstance(spec, attestation.Prerequisite)
    payload: dict[str, object] = {field: "REDACTED" for field in spec.receipt_fields}
    payload.update({
        "schema_version": "1.0.0",
        "receipt_type": spec.receipt_type,
        "status": spec.pass_status,
        "decision": "REDACTED_STATIC_EVIDENCE_ONLY",
        "observed_on": observed_on,
        "checks": [],
        "failure_codes": [],
        "source_boundary": {},
        "claim_boundary": "static only",
        spec.ready_field: ready,
        spec.authorization_field: False,
    })
    return json.dumps(payload).encode("utf-8")


def _manifest(records: list[dict[str, object]]) -> bytes:
    return ("\n".join(json.dumps(record) for record in records) + "\n").encode("utf-8")


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_contract_preserves_private_read_only_single_candidate_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["prerequisite_ids"] == [spec.identifier for spec in PREREQUISITES]
    assert expected["maximum_private_database_read_requests"] == 6
    assert boundary["at_most_one_current_candidate_per_prerequisite_receipt_type"] is True
    assert boundary["private_object_path_hash_or_raw_content_emitted_copied_or_persisted"] is False
    assert boundary["provider_api_request_sent"] is False


def test_all_current_redacted_receipts_attest_ready_but_never_authorize_core(tmp_path: Path) -> None:
    records = [_record(spec, suffix=chr(ord("a") + index)) for index, spec in enumerate(PREREQUISITES)]
    objects = {str(record["object_path"]): _receipt(spec) for record, spec in zip(records, PREREQUISITES, strict=True)}
    client = FakePrivateClient(_manifest(records), objects)

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")
    result = evaluate_attestation(_contract(), facts)

    assert facts["private_database_read_requests"] == 6
    assert set(facts["prerequisite_states"].values()) == {"READY_EVIDENCE_OBSERVED_REDACTED"}
    assert result["status"] == PASS_STATUS
    assert result["core_activation_prerequisites_ready"] is True
    assert result["product_outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_unrelated_manifest_record_never_fetches_unrelated_object(tmp_path: Path) -> None:
    record = _record(PREREQUISITES[0])
    unrelated = {
        "sha256": "f" * 64,
        "original_name": "unrelated.json",
        "size_bytes": 10,
        "domain": "ABD",
        "batch": "other",
        "object_path": "objects/ff/%s_unrelated.json" % ("f" * 64),
        "ingested_at": "2026-08-12",
    }
    client = FakePrivateClient(_manifest([record, unrelated]), {str(record["object_path"]): _receipt(PREREQUISITES[0])})

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["prerequisite_states"]["CONTROLLED_ENTRY"] == "READY_EVIDENCE_OBSERVED_REDACTED"
    assert len(client.calls) == 2
    assert "unrelated.json" not in "\n".join(client.calls)


def test_duplicate_current_candidate_fails_closed_without_receipt_fetch(tmp_path: Path) -> None:
    first = _record(PREREQUISITES[0], suffix="a")
    second = _record(PREREQUISITES[0], suffix="b")
    client = FakePrivateClient(_manifest([first, second]), {})

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["prerequisite_states"]["CONTROLLED_ENTRY"] == "CANDIDATE_AMBIGUOUS_REDACTED"
    assert facts["private_database_read_requests"] == 1
    assert len(client.calls) == 1


def test_nonready_current_receipt_stays_unready(tmp_path: Path) -> None:
    record = _record(PREREQUISITES[2])
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _receipt(PREREQUISITES[2], ready=False)})

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["prerequisite_states"]["SSH_TRANSPORT"] == "NOT_READY_EVIDENCE_OBSERVED_REDACTED"
    assert facts["core_activation_prerequisites_ready"] is False


def test_receipt_with_wrong_current_date_is_rejected_and_not_emitted(tmp_path: Path) -> None:
    record = _record(PREREQUISITES[0])
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _receipt(PREREQUISITES[0], observed_on="2026-08-11")})

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")
    receipt = build_receipt(_contract(), facts)
    serialized = json.dumps(receipt, sort_keys=True)

    assert facts["prerequisite_states"]["CONTROLLED_ENTRY"] == "REDACTED_RECEIPT_REJECTED_REDACTED"
    assert str(record["object_path"]) not in serialized
    assert str(record["sha256"]) not in serialized


def test_manifest_unavailable_fails_closed(tmp_path: Path) -> None:
    client = FakePrivateClient(RuntimeError("unavailable"), {})

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")
    result = evaluate_attestation(_contract(), facts)

    assert facts["private_manifest_state"] == "UNAVAILABLE_REDACTED"
    assert set(facts["prerequisite_states"].values()) == {"PRIVATE_MANIFEST_UNAVAILABLE_REDACTED"}
    assert result["core_start_authorized"] is False


def test_manifest_schema_rejection_fails_closed(tmp_path: Path) -> None:
    client = FakePrivateClient(b'{"unexpected":true}\n', {})

    facts = discover_private_continuity(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["private_manifest_state"] == "REJECTED_REDACTED"
    assert set(facts["prerequisite_states"].values()) == {"PRIVATE_MANIFEST_REJECTED_REDACTED"}


def test_facts_reject_product_outbound_counts_and_inconsistent_readiness() -> None:
    with pytest.raises(CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError, match="outbound operation count"):
        validate_facts(_facts(product_github_api_requests=1))

    with pytest.raises(CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError, match="core activation readiness"):
        validate_facts(_facts(
            prerequisite_states=_states("READY_EVIDENCE_OBSERVED_REDACTED"),
            core_activation_prerequisites_ready=False,
        ))


def test_contract_cannot_relax_private_request_bound() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["maximum_private_database_read_requests"] = 7

    with pytest.raises(CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError, match="attestation expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_direct_product_network_or_command_execution_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--repo-root" in runner
    assert "current_production_private_redacted_prerequisite_receipt_continuity_attestation.py" in runner
    assert "private_db_client.py" in runner
    for forbidden in (
        "socket.",
        "urllib.request",
        "import requests",
        "requests.",
        "urlopen",
        "subprocess",
        "ssh ",
        "curl ",
        "wget ",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
    ):
        assert forbidden not in runner
        assert forbidden not in module


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError):
        evaluate_attestation(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION"
