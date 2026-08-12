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

from shadow_runtime_source_provenance_promotion import (
    FAIL_STATUS,
    PASS_STATUS,
    ShadowSourceProvenancePromotionError,
    build_receipt,
    evaluate_promotion_facts,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "shadow_runtime_source_provenance_promotion_contract.json"
VALIDATOR_PATH = RUNTIME / "shadow_runtime_source_provenance_promotion.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, bool]:
    values: dict[str, bool] = {
        "source_archive_exact": True,
        "source_receipt_exact": True,
        "candidate_archive_exact": True,
        "candidate_loaded_untagged_precondition": True,
        "previous_image_attestation_pass": True,
        "previous_control_plane_exact": True,
        "candidate_identity_attestation_pass": True,
        "candidate_runtime_shape_exact": True,
        "candidate_control_plane_exact": True,
        "current_release_blue": True,
        "exactly_one_shadow": True,
        "core_runtime_absent": True,
        "prior_container_removed_after_success": True,
        "prior_image_retained_untagged": True,
    }
    values.update(overrides)  # type: ignore[arg-type]
    return values


def test_contract_is_exact_and_preserves_source_to_oci_and_blue_only_boundaries() -> None:
    contract = _contract()

    validate_contract(contract)

    assert contract["source_provenance"] == {
        "source_commit": "b7df8bee5bc91987970ce51d540c68f3fc324f36",
        "source_archive_sha256": "7ad7b97aeaaec84b747dc3002a849851cba7625fa7e300dd1015ff83d023d6d6",
        "source_to_oci_receipt_sha256": "f6052b31867d35bed665662831aa51f4321c7ef86129fac901190552aca04395",
        "oci_archive_sha256": "2cbfde404f1d21b3241da4f31eb67f44708798c959e62c2213265647c2db332d",
        "oci_manifest_digest": "sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "oci_config_digest": "sha256:e9a3d81370ec722178393f1d153fc8c1540987ec44740aa435603977b1688702",
    }
    assert contract["candidate"]["docker_image_id"] == contract["source_provenance"]["oci_manifest_digest"]
    assert contract["source_boundary"]["external_network_accessed"] is False
    assert contract["source_boundary"]["core_runtime_started"] is False
    assert contract["source_boundary"]["real_time_soak_waited"] is False
    assert contract["rollback"]["preserve_prior_container_until_candidate_attested"] is True


def test_contract_mutation_fails_closed() -> None:
    contract = deepcopy(_contract())
    contract["candidate"]["repo_digests_before_promotion"] = ["unexpected"]

    with pytest.raises(ShadowSourceProvenancePromotionError):
        validate_contract(contract)


@pytest.mark.parametrize(
    ("overrides", "failure_code"),
    [
        ({"source_receipt_exact": False}, "SOURCE_ARCHIVE_AND_RECEIPT_EXACT"),
        ({"candidate_loaded_untagged_precondition": False}, "CANDIDATE_LOADED_UNTAGGED_PRECONDITION"),
        ({"previous_image_attestation_pass": False}, "PRIOR_IMAGE_ATTESTATION_PASS"),
        ({"candidate_identity_attestation_pass": False}, "CANDIDATE_IMAGE_AND_DUAL_ENDPOINT_ATTESTATION_PASS"),
        ({"candidate_runtime_shape_exact": False}, "CANDIDATE_RUNTIME_SHAPE_EXACT"),
        ({"current_release_blue": False}, "CURRENT_RELEASE_REMAINS_BLUE"),
        ({"core_runtime_absent": False}, "CORE_RUNTIME_ABSENT"),
        ({"prior_container_removed_after_success": False}, "PRIOR_CONTAINER_REMOVED_AFTER_SUCCESS"),
    ],
)
def test_each_promotion_boundary_fails_closed(overrides: dict[str, bool], failure_code: str) -> None:
    result = evaluate_promotion_facts(_contract(), _facts(**overrides))

    assert result["status"] == FAIL_STATUS
    assert result["promotion_valid"] is False
    assert failure_code in result["failure_codes"]


def test_success_receipt_is_redacted_and_bounded() -> None:
    receipt = build_receipt(
        _contract(),
        _facts(),
        observed_on="2026-08-10",
        contract_sha256="a" * 64,
        validator_sha256="b" * 64,
        readiness_attempts=2,
    )

    assert receipt["status"] == PASS_STATUS
    assert receipt["promotion_valid"] is True
    assert receipt["failure_codes"] == []
    assert receipt["readiness_attempts"] == 2
    assert receipt["source_provenance"]["docker_image_id"] == _contract()["candidate"]["docker_image_id"]
    assert "container_id" not in receipt["observed"]
    assert receipt["source_boundary"]["runtime_secret_content_read"] is False
    assert receipt["source_boundary"]["external_network_accessed"] is False
    assert receipt["source_boundary"]["real_time_soak_waited"] is False


def test_promotion_source_is_bounded_to_local_docker_and_loopback_control() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    assert "range(1, 4)" in source
    assert "time.sleep(1)" in source
    assert '"docker", "tag"' in source
    assert '"docker", "create"' in source
    assert '"docker", "start"' in source
    for forbidden in (
        "requests",
        "urllib",
        "cloudflared",
        "systemctl",
        "docker pull",
        "docker build",
        "docker load",
        "docker exec",
        "docker run",
    ):
        assert forbidden not in source
    assert '"runtime_secret_content_read": False' in source
    assert '"external_network_accessed": False' in source
    assert '"recommendation_generated_or_enabled": False' in source
    assert '"order_submission_enabled": False' in source
