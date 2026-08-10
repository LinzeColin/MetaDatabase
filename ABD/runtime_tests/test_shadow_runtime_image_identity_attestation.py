from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from shadow_runtime_image_identity_attestation import (
    PASS_STATUS,
    ShadowImageIdentityAttestationError,
    build_receipt,
    collect_shadow_image_identity_facts,
    evaluate_shadow_image_identity_facts,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "shadow_runtime_image_identity_attestation_contract.json"
VALIDATOR_PATH = RUNTIME / "shadow_runtime_image_identity_attestation.py"
INSTALLER_PATH = RUNTIME / "install_shadow_runtime_image_identity_attestation.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    contract = _contract()
    expected = contract["expected"]
    facts: dict[str, object] = {
        "shadow_container_count": expected["shadow_container_count"],
        "core_container_count": expected["core_container_count"],
        "shadow_running": True,
        "image_id": expected["image_id"],
        "repo_digests": [expected["image_reference"]],
        "labels": expected["labels"],
        "memory_limit_bytes": expected["memory_limit_bytes"],
        "memory_swap_limit_bytes": expected["memory_swap_limit_bytes"],
        "port_mapping": expected["port_mapping"],
        "status_payload": expected["status_payload"],
    }
    facts.update(overrides)
    return facts


def test_contract_keeps_one_shot_identity_scope_and_no_runtime_mutation() -> None:
    contract = _contract()

    validate_contract(contract)
    assert contract["source_claim"] == "RUNNING_IMAGE_IDENTITY_ONLY_NOT_SOURCE_COMMIT_OR_OCI_ARCHIVE_PROVENANCE"
    assert contract["runtime_boundary"]["runtime_config_or_secret_read"] is False
    assert contract["runtime_boundary"]["runtime_state_changed"] is False
    assert contract["runtime_boundary"]["real_time_soak_waited"] is False


def test_exact_shadow_image_identity_snapshot_passes_and_is_redacted() -> None:
    contract = _contract()
    result = evaluate_shadow_image_identity_facts(contract, _facts())
    receipt = build_receipt(
        contract,
        _facts(),
        hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest(),
        "2026-08-10",
    )

    assert result["status"] == PASS_STATUS
    assert result["attestation_valid"] is True
    assert receipt["status"] == PASS_STATUS
    assert "container_id" not in receipt["observed"]
    assert receipt["observed"]["image_identity_exact"] is True
    assert receipt["runtime_boundary"]["order_submission_enabled"] is False


@pytest.mark.parametrize(
    ("overrides", "failure_code"),
    [
        ({"shadow_container_count": 0}, "EXACTLY_ONE_SHADOW_CONTAINER"),
        ({"core_container_count": 1}, "CORE_RUNTIME_ABSENT"),
        ({"image_id": "sha256:" + "0" * 64}, "SHADOW_IMAGE_ID_EXACT"),
        ({"repo_digests": []}, "SHADOW_IMAGE_REFERENCE_EXACT"),
        ({"labels": {"product_version": "0.0.0.1", "runtime_role": "candidate-shadow", "order_submission": "enabled"}}, "SHADOW_IMAGE_LABELS_EXACT"),
        ({"memory_swap_limit_bytes": 0}, "SHADOW_NO_ADDITIONAL_SWAP"),
        ({"status_payload": {}}, "SAFE_STATUS_PAYLOAD_EXACT"),
    ],
)
def test_each_image_or_runtime_boundary_divergence_fails_closed(overrides: dict[str, object], failure_code: str) -> None:
    result = evaluate_shadow_image_identity_facts(_contract(), _facts(**overrides))

    assert result["status"] != PASS_STATUS
    assert result["attestation_valid"] is False
    assert failure_code in result["failure_codes"]


def test_invalid_contract_or_fact_shape_is_rejected() -> None:
    contract = _contract()
    mutated = deepcopy(contract)
    mutated["source_claim"] = "SOURCE_COMMIT_PROVEN"

    with pytest.raises(ShadowImageIdentityAttestationError, match="source claim"):
        validate_contract(mutated)
    with pytest.raises(ShadowImageIdentityAttestationError, match="unexpected shape"):
        evaluate_shadow_image_identity_facts(contract, {"shadow_container_count": 1})


def test_collection_reads_only_docker_metadata_and_fixed_loopback_status() -> None:
    contract = _contract()
    expected = contract["expected"]
    calls: list[tuple[str, ...]] = []

    def run(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments == ("docker", "ps", "-q", "--filter", "label=" + expected["shadow_label"]):
            return "shadow-id"
        if arguments == ("docker", "ps", "-q", "--filter", "label=" + expected["core_label"]):
            return ""
        if arguments == ("docker", "inspect", "--format", "{{.State.Running}}", "shadow-id"):
            return "true"
        if arguments == ("docker", "inspect", "--format", "{{.Image}}", "shadow-id"):
            return expected["image_id"]
        if arguments == ("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", expected["image_id"]):
            return json.dumps([expected["image_reference"]])
        if arguments == ("docker", "inspect", "--format", "{{index .Config.Labels \"com.linze.abd.product-version\"}}", "shadow-id"):
            return expected["labels"]["product_version"]
        if arguments == ("docker", "inspect", "--format", "{{index .Config.Labels \"com.linze.abd.runtime-role\"}}", "shadow-id"):
            return expected["labels"]["runtime_role"]
        if arguments == ("docker", "inspect", "--format", "{{index .Config.Labels \"com.linze.abd.order-submission\"}}", "shadow-id"):
            return expected["labels"]["order_submission"]
        if arguments == ("docker", "inspect", "--format", "{{.HostConfig.Memory}}/{{.HostConfig.MemorySwap}}", "shadow-id"):
            return "%s/%s" % (expected["memory_limit_bytes"], expected["memory_swap_limit_bytes"])
        if arguments == ("docker", "port", "shadow-id", "8080/tcp"):
            return expected["port_mapping"]
        raise AssertionError("unexpected command: %r" % (arguments,))

    probes: list[tuple[str, int]] = []

    def probe(host: str, port: int) -> dict[str, object]:
        probes.append((host, port))
        return dict(expected["status_payload"])

    facts = collect_shadow_image_identity_facts(contract, run=run, probe=probe)

    assert facts == _facts()
    assert probes == [("127.0.0.1", 8081)]
    assert all(call[0] == "docker" for call in calls)
    assert all("/etc/abd" not in value for call in calls for value in call)


def test_attester_and_installer_have_no_service_or_external_network_capability() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    installer = INSTALLER_PATH.read_text(encoding="utf-8")

    for forbidden in ("import requests", "import urllib", "import socket", "time.sleep(", "systemctl", "cloudflared", "/etc/abd"):
        assert forbidden not in source
    for forbidden in ("systemctl", "docker", "cloudflared", "sleep", "/etc/abd"):
        assert forbidden not in installer
    assert "/usr/local/lib/abd/shadow_runtime_image_identity_attestation.py" in installer
