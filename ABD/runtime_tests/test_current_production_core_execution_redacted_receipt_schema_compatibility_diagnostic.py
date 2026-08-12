from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic as diagnostic
from current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic import (
    CANONICAL_NON_READY_STATE,
    CANONICAL_READY_STATE,
    FAIL_STATUS,
    OFFICIAL_FAIL_CLOSED_STATE,
    PASS_STATUS,
    CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError,
    _receipt_filename,
    build_receipt,
    discover_schema_compatibility,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic.py"


class FakePrivateClient:
    REPO = "private-repository"
    BRANCH = "main"

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


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "private_manifest_state": "OBSERVED_IN_MEMORY",
        "private_manifest_metadata_read_in_memory_only": True,
        "core_execution_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 1,
        "core_execution_receipt_schema_state": "CANDIDATE_NOT_OBSERVED_REDACTED",
        "core_execution_current_ready_evidence": False,
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


def _record(suffix: str = "a", observed_on: str = "2026-08-12") -> dict[str, object]:
    name = _receipt_filename(diagnostic.CORE_SPEC, observed_on)
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


def _manifest(records: list[dict[str, object]]) -> bytes:
    return ("\n".join(json.dumps(record) for record in records) + "\n").encode("utf-8")


def _canonical(ready: bool, observed_on: str = "2026-08-12") -> bytes:
    payload = {
        "schema_version": "1.0.0",
        "receipt_type": diagnostic.CORE_RECEIPT_TYPE,
        "status": diagnostic.CORE_PASS_STATUS if ready else diagnostic.CORE_FAIL_STATUS,
        "decision": "REDACTED",
        "observed_on": observed_on,
        "input_ready": ready,
        "execution_authorized": False,
        "checks": [],
        "failure_codes": [],
        "source_boundary": {},
        "claim_boundary": "REDACTED",
    }
    return json.dumps(payload).encode("utf-8")


def _official_fail_closed() -> bytes:
    payload = {
        "schema_version": "1.0.0",
        "receipt_type": diagnostic.CORE_RECEIPT_TYPE,
        "status": diagnostic.CORE_FAIL_STATUS,
        "decision": diagnostic.FAIL_CLOSED_DECISION,
        "observed_on": "INVALID",
        "input_ready": False,
        "execution_authorized": False,
        "checks": [],
        "failure_codes": [diagnostic.FAIL_CLOSED_CODE],
        "error_type": "RedactedInputError",
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }
    return json.dumps(payload).encode("utf-8")


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_contract_preserves_one_candidate_compatibility_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["core_execution_receipt_type"] == diagnostic.CORE_RECEIPT_TYPE
    assert expected["maximum_private_database_read_requests"] == 2
    assert boundary["at_most_one_current_core_execution_candidate_read_in_memory"] is True
    assert boundary["private_object_path_hash_or_raw_content_emitted_copied_or_persisted"] is False


def test_canonical_ready_receipt_is_observed_but_never_starts_core(tmp_path: Path) -> None:
    record = _record()
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _canonical(True)})

    facts = discover_schema_compatibility(_root(tmp_path), client, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["private_database_read_requests"] == 2
    assert facts["core_execution_receipt_schema_state"] == CANONICAL_READY_STATE
    assert result["status"] == PASS_STATUS
    assert result["core_execution_current_ready_evidence"] is True
    assert result["core_start_authorized"] is False


def test_canonical_nonready_receipt_is_not_promoted(tmp_path: Path) -> None:
    record = _record()
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _canonical(False)})

    facts = discover_schema_compatibility(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["core_execution_receipt_schema_state"] == CANONICAL_NON_READY_STATE
    assert facts["core_execution_current_ready_evidence"] is False


def test_official_fail_closed_schema_is_distinguished_from_noncanonical(tmp_path: Path) -> None:
    record = _record()
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _official_fail_closed()})

    facts = discover_schema_compatibility(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["core_execution_receipt_schema_state"] == OFFICIAL_FAIL_CLOSED_STATE
    assert facts["core_execution_current_ready_evidence"] is False


def test_noncanonical_receipt_is_rejected_without_path_or_hash_emission(tmp_path: Path) -> None:
    record = _record()
    raw = json.loads(_canonical(False).decode("utf-8"))
    raw["unexpected"] = "must-not-appear"
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): json.dumps(raw).encode("utf-8")})

    facts = discover_schema_compatibility(_root(tmp_path), client, observed_on="2026-08-12")
    receipt = build_receipt(_contract(), facts)
    serialized = json.dumps(receipt, sort_keys=True)

    assert facts["core_execution_receipt_schema_state"] == "NONCANONICAL_REJECTED_REDACTED"
    assert str(record["object_path"]) not in serialized
    assert str(record["sha256"]) not in serialized
    assert "must-not-appear" not in serialized


def test_missing_or_duplicate_candidate_fails_closed_without_receipt_fetch(tmp_path: Path) -> None:
    missing = FakePrivateClient(_manifest([]), {})
    missing_facts = discover_schema_compatibility(_root(tmp_path), missing, observed_on="2026-08-12")
    assert missing_facts["core_execution_receipt_schema_state"] == "CANDIDATE_NOT_OBSERVED_REDACTED"
    assert len(missing.calls) == 1

    duplicate_root = tmp_path / "duplicate-repository-root"
    duplicate_root.mkdir()
    first = _record("a")
    second = _record("b")
    duplicate = FakePrivateClient(_manifest([first, second]), {})
    duplicate_facts = discover_schema_compatibility(duplicate_root, duplicate, observed_on="2026-08-12")
    assert duplicate_facts["core_execution_receipt_schema_state"] == "CANDIDATE_AMBIGUOUS_REDACTED"
    assert len(duplicate.calls) == 1


def test_private_manifest_unavailable_fails_closed(tmp_path: Path) -> None:
    client = FakePrivateClient(RuntimeError("unavailable"), {})

    facts = discover_schema_compatibility(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["private_manifest_state"] == "UNAVAILABLE_REDACTED"
    assert facts["core_execution_current_ready_evidence"] is False


def test_facts_reject_product_outbound_counts_and_inconsistent_ready_state() -> None:
    with pytest.raises(CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(product_github_api_requests=1))

    with pytest.raises(CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError, match="core execution readiness"):
        validate_facts(_facts(
            core_execution_receipt_schema_state=CANONICAL_READY_STATE,
            core_execution_current_ready_evidence=False,
        ))


def test_contract_cannot_relax_private_read_bound() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["maximum_private_database_read_requests"] = 3

    with pytest.raises(CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_direct_product_network_or_command_execution_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--repo-root" in runner
    assert "current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic.py" in runner
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

    with pytest.raises(CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC"
