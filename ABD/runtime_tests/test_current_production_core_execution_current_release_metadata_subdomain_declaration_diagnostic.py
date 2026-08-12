from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_core_execution_current_release_metadata_subdomain_declaration_diagnostic as diagnostic
from current_production_core_execution_current_release_metadata_subdomain_declaration_diagnostic import (
    CHECK_IDENTIFIERS,
    CURRENT_RELEASE_CHECK_IDENTIFIERS,
    CURRENT_RELEASE_SUBDOMAINS,
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError,
    _receipt_filename,
    build_receipt,
    discover_current_release_metadata_subdomains,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_core_execution_current_release_metadata_subdomain_declaration_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_core_execution_current_release_metadata_subdomain_declaration_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_core_execution_current_release_metadata_subdomain_declaration_diagnostic.py"


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
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "private_manifest_state": "OBSERVED_IN_MEMORY",
        "private_manifest_metadata_read_in_memory_only": True,
        "core_execution_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 1,
        "current_release_metadata_subdomain_state": "CANDIDATE_NOT_OBSERVED_REDACTED",
        "current_release_metadata_subdomains": [],
        "current_release_metadata_subdomains_declared": False,
        "private_receipt_check_identifier_or_value_emitted_copied_or_persisted": False,
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
        "size_bytes": 1024,
        "domain": "ABD",
        "batch": "current-production",
        "object_path": "objects/%s/%s_%s" % (sha[:2], sha, name),
        "ingested_at": observed_on,
    }


def _manifest(records: list[dict[str, object]]) -> bytes:
    return ("\n".join(json.dumps(record) for record in records) + "\n").encode("utf-8")


def _canonical_nonready(failed: set[str], observed_on: str = "2026-08-12") -> bytes:
    payload = {
        "schema_version": "1.0.0",
        "receipt_type": diagnostic.CORE_RECEIPT_TYPE,
        "status": diagnostic.CORE_FAIL_STATUS,
        "decision": "REDACTED",
        "observed_on": observed_on,
        "input_ready": False,
        "execution_authorized": False,
        "checks": [{"id": identifier, "passed": identifier not in failed} for identifier in CHECK_IDENTIFIERS],
        "failure_codes": [identifier for identifier in CHECK_IDENTIFIERS if identifier in failed],
        "source_boundary": {},
        "claim_boundary": "REDACTED",
    }
    return json.dumps(payload).encode("utf-8")


def _canonical_ready(observed_on: str = "2026-08-12") -> bytes:
    payload = json.loads(_canonical_nonready({"PRIVILEGED_METADATA_READ"}, observed_on).decode("utf-8"))
    payload["status"] = diagnostic.CORE_PASS_STATUS
    payload["input_ready"] = True
    payload["checks"] = [{"id": identifier, "passed": True} for identifier in CHECK_IDENTIFIERS]
    payload["failure_codes"] = []
    return json.dumps(payload).encode("utf-8")


def _root(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def test_contract_preserves_one_candidate_and_three_subdomain_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_private_database_read_requests"] == 2
    assert expected["current_release_check_identifiers"] == list(CURRENT_RELEASE_CHECK_IDENTIFIERS)
    assert expected["current_release_metadata_subdomains"] == sorted(CURRENT_RELEASE_SUBDOMAINS)
    assert boundary["private_receipt_check_identifier_or_value_emitted_copied_or_persisted"] is False


def test_canonical_nonready_receipt_declares_only_current_release_subdomains(tmp_path: Path) -> None:
    record = _record()
    failed = {"CURRENT_RELEASE_LINK_MANAGED", "CURRENT_RELEASE_REBUILD_FILE_REGULAR"}
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _canonical_nonready(failed)})

    facts = discover_current_release_metadata_subdomains(_root(tmp_path), client, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)
    serialized = json.dumps(build_receipt(_contract(), facts), sort_keys=True)

    assert facts["private_database_read_requests"] == 2
    assert facts["current_release_metadata_subdomain_state"] == "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED"
    assert facts["current_release_metadata_subdomains"] == [
        "CURRENT_RELEASE_LINK_METADATA_INCOMPLETE_REDACTED",
        "CURRENT_RELEASE_REBUILD_METADATA_INCOMPLETE_REDACTED",
    ]
    assert result["status"] == PASS_STATUS
    assert result["core_start_authorized"] is False
    assert str(record["object_path"]) not in serialized
    assert str(record["sha256"]) not in serialized
    assert "CURRENT_RELEASE_LINK_MANAGED" not in serialized


def test_canonical_nonready_without_current_release_failure_is_not_promoted(tmp_path: Path) -> None:
    record = _record()
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): _canonical_nonready({"CONFIG_FILE_REGULAR"})})

    facts = discover_current_release_metadata_subdomains(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["current_release_metadata_subdomain_state"] == "CANONICAL_NONREADY_CURRENT_RELEASE_FAILURE_NOT_OBSERVED_REDACTED"
    assert facts["current_release_metadata_subdomains_declared"] is False
    assert facts["current_release_metadata_subdomains"] == []


def test_canonical_ready_and_unknown_status_are_not_accepted_as_nonready(tmp_path: Path) -> None:
    ready_record = _record()
    ready = FakePrivateClient(_manifest([ready_record]), {str(ready_record["object_path"]): _canonical_ready()})
    ready_facts = discover_current_release_metadata_subdomains(_root(tmp_path, "ready"), ready, observed_on="2026-08-12")
    assert ready_facts["current_release_metadata_subdomain_state"] == "CANONICAL_READY_NOT_APPLICABLE_REDACTED"

    unknown_record = _record("b")
    unknown = json.loads(_canonical_ready().decode("utf-8"))
    unknown["status"] = "UNRECOGNIZED_STATUS"
    unknown_client = FakePrivateClient(_manifest([unknown_record]), {str(unknown_record["object_path"]): json.dumps(unknown).encode("utf-8")})
    unknown_facts = discover_current_release_metadata_subdomains(_root(tmp_path, "unknown"), unknown_client, observed_on="2026-08-12")
    assert unknown_facts["current_release_metadata_subdomain_state"] == "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED"


def test_noncanonical_check_order_or_failure_codes_are_rejected(tmp_path: Path) -> None:
    record = _record()
    raw = json.loads(_canonical_nonready({"CURRENT_RELEASE_LINK_MANAGED"}).decode("utf-8"))
    raw["failure_codes"] = []
    client = FakePrivateClient(_manifest([record]), {str(record["object_path"]): json.dumps(raw).encode("utf-8")})

    facts = discover_current_release_metadata_subdomains(_root(tmp_path), client, observed_on="2026-08-12")

    assert facts["current_release_metadata_subdomain_state"] == "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED"
    assert facts["current_release_metadata_subdomains"] == []


def test_missing_duplicate_and_unavailable_candidates_fail_closed_without_extra_fetch(tmp_path: Path) -> None:
    missing = FakePrivateClient(_manifest([]), {})
    missing_facts = discover_current_release_metadata_subdomains(_root(tmp_path, "missing"), missing, observed_on="2026-08-12")
    assert missing_facts["current_release_metadata_subdomain_state"] == "CANDIDATE_NOT_OBSERVED_REDACTED"
    assert len(missing.calls) == 1

    first = _record("a")
    second = _record("b")
    duplicate = FakePrivateClient(_manifest([first, second]), {})
    duplicate_facts = discover_current_release_metadata_subdomains(_root(tmp_path, "duplicate"), duplicate, observed_on="2026-08-12")
    assert duplicate_facts["current_release_metadata_subdomain_state"] == "CANDIDATE_AMBIGUOUS_REDACTED"
    assert len(duplicate.calls) == 1

    unavailable_record = _record("c")
    unavailable = FakePrivateClient(_manifest([unavailable_record]), {str(unavailable_record["object_path"]): RuntimeError("unavailable")})
    unavailable_facts = discover_current_release_metadata_subdomains(_root(tmp_path, "unavailable"), unavailable, observed_on="2026-08-12")
    assert unavailable_facts["current_release_metadata_subdomain_state"] == "REDACTED_RECEIPT_UNAVAILABLE_REDACTED"
    assert unavailable_facts["private_database_read_requests"] == 2


def test_facts_reject_outbound_operations_and_invalid_subdomain_shape() -> None:
    with pytest.raises(CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(provider_api_requests=1))

    with pytest.raises(CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError, match="subdomain list"):
        validate_facts(_facts(
            current_release_metadata_subdomain_state="CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED",
            current_release_metadata_subdomains=["UNSAFE_DETAIL"],
            current_release_metadata_subdomains_declared=True,
            core_execution_receipt_content_read_in_memory_only=True,
            private_database_read_requests=2,
        ))


def test_contract_cannot_relax_selected_identifiers_or_private_reads() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["maximum_private_database_read_requests"] = 3
    with pytest.raises(CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)

    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["current_release_check_identifiers"] = ["UNSAFE_DETAIL"]
    with pytest.raises(CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_direct_product_network_or_command_execution_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--repo-root" in runner
    assert "current_production_core_execution_current_release_metadata_subdomain_declaration_diagnostic.py" in runner
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

    with pytest.raises(CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC"
