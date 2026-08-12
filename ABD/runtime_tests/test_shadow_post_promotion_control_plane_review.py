from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from shadow_post_promotion_control_plane_review import (
    FAIL_STATUS,
    PASS_STATUS,
    ShadowPostPromotionReviewError,
    build_receipt,
    collect_review_facts,
    evaluate_review_facts,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "shadow_post_promotion_control_plane_review_contract.json"
VALIDATOR_PATH = RUNTIME / "shadow_post_promotion_control_plane_review.py"
OBSERVED_ON = "2026-08-12"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, bool]:
    values: dict[str, bool] = {
        "installed_identity_attester_pass": True,
        "installed_identity_contract_matches_candidate": True,
        "exactly_one_shadow": True,
        "core_container_absent": True,
        "running_shadow_candidate_image": True,
        "blue_compose_project_exact": True,
        "candidate_tag_and_reference_exact": True,
        "prior_image_retained_untagged": True,
        "current_release_blue": True,
        "blue_green_slot_controls_match_candidate": True,
        "core_service_inactive": True,
        "core_connector_inactive": True,
        "connector_has_no_hostname": True,
    }
    values.update(overrides)  # type: ignore[arg-type]
    return values


def _read_text(contract: dict[str, object]):
    expected = contract["expected"]
    assert isinstance(expected, dict)
    candidate_manifest = json.dumps(
        {
            "image_id": expected["image_id"],
            "image_reference": expected["image_reference"],
        }
    )
    installed_identity_contract = json.dumps(
        {
            "expected": {
                "image_id": expected["image_id"],
                "image_reference": expected["image_reference"],
            }
        }
    )

    def read_text(path: Path) -> str:
        values = {
            str(expected["identity_contract_path"]): installed_identity_contract,
            "/opt/abd/releases/blue/release_manifest.json": candidate_manifest,
            "/opt/abd/releases/green/release_manifest.json": candidate_manifest,
            str(expected["connector_config_path"]): "tunnel: opaque-id\ningress:\n  - service: http_status:404\n",
        }
        return values[str(path)]

    return read_text


def _read_first_line(contract: dict[str, object]):
    expected = contract["expected"]
    assert isinstance(expected, dict)

    def read_first_line(path: Path) -> str:
        assert str(path) in {"/etc/abd/slots/blue.env", "/etc/abd/slots/green.env"}
        return "ABD_IMAGE=" + str(expected["image_reference"])

    return read_first_line


def _runner(contract: dict[str, object], *, failing: tuple[str, ...] | None = None):
    expected = contract["expected"]
    assert isinstance(expected, dict)

    def run(arguments: tuple[str, ...]) -> tuple[int, str]:
        if arguments == (str(expected["identity_attester_path"]), "--contract", str(expected["identity_contract_path"]), "--observed-on", OBSERVED_ON):
            return 0, json.dumps({"status": "PASS_SHADOW_IMAGE_IDENTITY_ATTESTATION", "attestation_valid": True})
        if failing is not None and arguments == failing:
            return 1, ""
        values = {
            ("docker", "ps", "-q", "--filter", "label=" + str(expected["shadow_label"])): (0, "shadow-id"),
            ("docker", "ps", "-q", "--filter", "label=" + str(expected["core_label"])): (0, ""),
            ("docker", "inspect", "--format", "{{.Image}}", "shadow-id"): (0, str(expected["image_id"])),
            ("docker", "inspect", "--format", "{{json .Config.Labels}}", "shadow-id"): (0, json.dumps({"com.docker.compose.project": expected["blue_project"]})),
            ("docker", "image", "inspect", "--format", "{{json .RepoTags}}", str(expected["image_id"])): (0, json.dumps([expected["image_tag"]])),
            ("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", str(expected["image_id"])): (0, json.dumps([expected["image_reference"]])),
            ("docker", "image", "inspect", "--format", "{{json .RepoTags}}", str(expected["prior_image_id"])): (0, "null"),
            ("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", str(expected["prior_image_id"])): (0, "null"),
            ("readlink", "-f", str(expected["current_release_path"])): (0, str(expected["blue_release_path"])),
            ("systemctl", "is-active", str(expected["core_service"])): (3, "inactive"),
            ("systemctl", "is-active", str(expected["core_connector_service"])): (3, "inactive"),
        }
        return values[arguments]

    return run


def test_contract_keeps_read_only_loopback_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["runtime_state_changed"] is False
    assert boundary["external_network_accessed"] is False
    assert boundary["real_time_soak_waited"] is False
    assert boundary["order_submission_enabled"] is False


def test_contract_mutation_or_incomplete_facts_fail_closed() -> None:
    mutated = deepcopy(_contract())
    assert isinstance(mutated["source_boundary"], dict)
    mutated["source_boundary"]["runtime_state_changed"] = True

    with pytest.raises(ShadowPostPromotionReviewError, match="source boundary"):
        validate_contract(mutated)
    with pytest.raises(ShadowPostPromotionReviewError, match="facts"):
        evaluate_review_facts(_contract(), {"exactly_one_shadow": True})


def test_collected_host_facts_cover_only_the_fixed_control_plane() -> None:
    contract = _contract()
    facts = collect_review_facts(
        contract,
        OBSERVED_ON,
        run=_runner(contract),
        read_text=_read_text(contract),
        read_first_line=_read_first_line(contract),
    )

    assert facts == _facts()


def test_command_failure_cannot_be_misread_as_an_absent_core_or_retained_image() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    facts = collect_review_facts(
        contract,
        OBSERVED_ON,
        run=_runner(contract, failing=("docker", "ps", "-q", "--filter", "label=" + str(expected["core_label"]))),
        read_text=_read_text(contract),
        read_first_line=_read_first_line(contract),
    )

    assert facts["core_container_absent"] is False
    assert evaluate_review_facts(contract, facts)["status"] == FAIL_STATUS


@pytest.mark.parametrize(
    ("overrides", "failure_code"),
    [
        ({"installed_identity_attester_pass": False}, "INSTALLED_IDENTITY_ATTESTER_PASS"),
        ({"current_release_blue": False}, "CURRENT_RELEASE_BLUE"),
        ({"connector_has_no_hostname": False}, "CONNECTOR_HAS_NO_HOSTNAME"),
    ],
)
def test_each_observation_boundary_divergence_fails_closed(overrides: dict[str, object], failure_code: str) -> None:
    result = evaluate_review_facts(_contract(), _facts(**overrides))

    assert result["status"] == FAIL_STATUS
    assert result["review_valid"] is False
    assert failure_code in result["failure_codes"]


def test_success_receipt_is_bounded_and_redacted() -> None:
    contract = _contract()
    receipt = build_receipt(contract, _facts(), OBSERVED_ON)
    serialized = json.dumps(receipt, sort_keys=True)
    expected = contract["expected"]
    assert isinstance(expected, dict)

    assert receipt["status"] == PASS_STATUS
    assert receipt["review_valid"] is True
    assert receipt["observed"]["active_slot"] == "blue"
    assert "shadow-id" not in serialized
    assert str(expected["image_id"]) not in serialized
    assert str(expected["image_reference"]) not in serialized
    assert receipt["source_boundary"]["runtime_secret_content_read"] is False
    assert receipt["source_boundary"]["runtime_state_changed"] is False


def test_source_has_no_mutating_or_external_network_capability() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "import hashlib",
        "import requests",
        "import urllib",
        "time.sleep(",
        "docker pull",
        "docker build",
        "docker load",
        "docker run",
        "docker compose",
        "systemctl start",
        "systemctl restart",
        "systemctl stop",
    ):
        assert forbidden not in source
    assert '("systemctl", "is-active"' in source
    assert "runtime_state_changed\": False" in source
    assert "real_time_soak_waited\": False" in source
