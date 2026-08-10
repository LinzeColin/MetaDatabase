from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from shadow_release_control_plane_recovery import (
    FAIL_STATUS,
    PASS_STATUS,
    ShadowControlPlaneRecoveryError,
    build_receipt,
    build_release_manifest,
    evaluate_control_plane_facts,
    render_slot_env,
    validate_contract,
)


def _contract() -> dict[str, object]:
    return json.loads((RUNTIME / "shadow_release_control_plane_recovery_contract.json").read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, bool]:
    values: dict[str, bool] = {
        "canonical_config_safe": True,
        "slot_files_exact": True,
        "current_symlink_blue": True,
        "shadow_project_blue": True,
        "shadow_count_exact": True,
        "core_count_zero": True,
        "image_attestation_pass": True,
    }
    values.update(overrides)  # type: ignore[arg-type]
    return values


def test_contract_is_exact_and_slot_environment_is_nonsecret_and_deterministic() -> None:
    contract = _contract()

    validate_contract(contract)
    blue = render_slot_env(contract, "blue", "/etc/abd/secrets/runtime-shadow")
    green = render_slot_env(contract, "green", "/etc/abd/secrets/runtime-shadow")

    assert blue.decode("utf-8") == (
        "ABD_IMAGE=local/abd-runtime@sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2\n"
        "ABD_RUNTIME_UID_GID=10001:10001\n"
        "ABD_CONFIG_FILE=/etc/abd/config.json\n"
        "ABD_STATE_DIR=/var/lib/abd\n"
        "ABD_SHADOW_LOG_DIR=/var/log/abd/blue\n"
        "ABD_RUNTIME_SECRET_FILE=/etc/abd/secrets/runtime-shadow\n"
        "ABD_SHADOW_BIND_PORT=8081\n"
    )
    assert "ABD_SHADOW_LOG_DIR=/var/log/abd/green" in green.decode("utf-8")
    assert "ABD_SHADOW_BIND_PORT=8082" in green.decode("utf-8")
    assert "runtime-shadow\n" in blue.decode("utf-8")


def test_contract_or_secret_path_mutation_fails_closed() -> None:
    contract = _contract()
    contract["canonical_layout"] = {"release_root": "/tmp"}

    with pytest.raises(ShadowControlPlaneRecoveryError):
        validate_contract(contract)
    with pytest.raises(ShadowControlPlaneRecoveryError):
        render_slot_env(_contract(), "blue", "relative-secret")
    with pytest.raises(ShadowControlPlaneRecoveryError):
        render_slot_env(_contract(), "blue", "/etc/abd/secrets/runtime\nshadow")


def test_release_manifests_bind_each_slot_without_secret_content() -> None:
    contract = _contract()
    manifest = build_release_manifest(
        contract,
        "blue",
        config_sha256="a" * 64,
        slot_env_sha256="b" * 64,
    )

    assert manifest == {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_SHADOW_CANONICAL_SLOT_MANIFEST",
        "release_id": "blue",
        "product_version": "0.0.0.1",
        "image_reference": "local/abd-runtime@sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "image_id": "sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "compose_sha256": "babed827948b77e28d395b0d36d2142605b8144f7e778302d6c384930aa54808",
        "config_sha256": "a" * 64,
        "slot_env_sha256": "b" * 64,
        "runtime_mode": "SHADOW_READ_ONLY",
        "loopback_port": "127.0.0.1:8081",
        "state_access": "READ_ONLY",
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
    }
    assert "runtime-shadow" not in json.dumps(manifest, sort_keys=True)


@pytest.mark.parametrize(
    ("overrides", "failure_code"),
    [
        ({"canonical_config_safe": False}, "CANONICAL_CONFIG_SAFE"),
        ({"slot_files_exact": False}, "BLUE_GREEN_SLOT_FILES_EXACT"),
        ({"current_symlink_blue": False}, "CURRENT_RELEASE_SYMLINK_BLUE"),
        ({"shadow_project_blue": False}, "BLUE_SHADOW_COMPOSE_PROJECT_EXACT"),
        ({"shadow_count_exact": False}, "EXACTLY_ONE_SHADOW_CONTAINER"),
        ({"core_count_zero": False}, "CORE_RUNTIME_ABSENT"),
        ({"image_attestation_pass": False}, "IMAGE_AND_DUAL_ENDPOINT_ATTESTATION_PASS"),
    ],
)
def test_each_canonical_control_plane_boundary_fails_closed(overrides: dict[str, bool], failure_code: str) -> None:
    result = evaluate_control_plane_facts(_contract(), _facts(**overrides))

    assert result["status"] == FAIL_STATUS
    assert result["recovery_valid"] is False
    assert failure_code in result["failure_codes"]


def test_success_receipt_is_redacted_and_bounded() -> None:
    contract = _contract()
    receipt = build_receipt(
        contract,
        _facts(),
        observed_on="2026-08-10",
        contract_sha256="c" * 64,
        validator_sha256="d" * 64,
        readiness_attempts=3,
    )

    assert receipt["status"] == PASS_STATUS
    assert receipt["recovery_valid"] is True
    assert receipt["failure_codes"] == []
    assert receipt["readiness_attempts"] == 3
    assert receipt["source_boundary"]["runtime_secret_content_read"] is False
    assert receipt["source_boundary"]["external_network_accessed"] is False
    assert receipt["source_boundary"]["real_time_soak_waited"] is False


def test_recovery_source_has_only_bounded_local_control_plane_capabilities() -> None:
    source = (RUNTIME / "shadow_release_control_plane_recovery.py").read_text(encoding="utf-8")

    assert "range(1, 4)" in source
    assert "time.sleep(1)" in source
    for forbidden in ("requests", "urllib", "cloudflared", "systemctl", "docker pull", "docker build", "docker exec"):
        assert forbidden not in source
    assert "runtime_secret_content_read\": False" in source
    assert "external_network_accessed\": False" in source
    assert "recommendation_generated_or_enabled\": False" in source
    assert "order_submission_enabled\": False" in source
