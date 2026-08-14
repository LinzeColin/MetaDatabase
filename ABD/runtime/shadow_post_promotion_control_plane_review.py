#!/usr/bin/env python3
"""Observe the post-promotion ABD blue shadow control plane without changing it."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PASS_STATUS = "PASS_POST_PROMOTION_CONTROL_PLANE_OBSERVATION"
FAIL_STATUS = "FAIL_POST_PROMOTION_CONTROL_PLANE_OBSERVATION"
RECEIPT_TYPE = "ABD_POST_PROMOTION_CONTROL_PLANE_OBSERVATION"
DIAGNOSTIC_PASS_STATUS = "PASS_POST_PROMOTION_CONTROL_PLANE_DIAGNOSTIC"
DIAGNOSTIC_FAIL_STATUS = "FAIL_POST_PROMOTION_CONTROL_PLANE_DIAGNOSTIC"
DIAGNOSTIC_RECEIPT_TYPE = "ABD_POST_PROMOTION_CONTROL_PLANE_DIAGNOSTIC"


class ShadowPostPromotionReviewError(ValueError):
    """Raised when the read-only post-promotion review contract is malformed."""


CommandRunner = Callable[[Sequence[str]], tuple[int, str]]
TextReader = Callable[[Path], str]


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ShadowPostPromotionReviewError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ShadowPostPromotionReviewError("review input must be a regular file")
    return path.read_text(encoding="utf-8")


def _read_first_line(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ShadowPostPromotionReviewError("review input must be a regular file")
    with path.open("r", encoding="utf-8") as handle:
        return handle.readline().rstrip("\r\n")


def _is_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _run(arguments: Sequence[str]) -> tuple[int, str]:
    completed = subprocess.run(arguments, check=False, capture_output=True, text=True)
    return completed.returncode, completed.stdout.strip()


def _json(value: str) -> object | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _lines(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\n" in value or "\x00" in value:
        raise ShadowPostPromotionReviewError("%s must be an absolute path" % name)
    return value


def _image_id(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ShadowPostPromotionReviewError("%s must be a sha256 image id" % name)
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise ShadowPostPromotionReviewError("%s must be a lowercase sha256 image id" % name)
    return value


def _image_reference(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("local/abd-runtime@sha256:"):
        raise ShadowPostPromotionReviewError("%s must be an ABD digest reference" % name)
    _image_id(value.rsplit("@", 1)[-1], name)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "post-promotion review contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowPostPromotionReviewError) as exc:
        raise ShadowPostPromotionReviewError("post-promotion review contract is unreadable") from exc


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise ShadowPostPromotionReviewError("review contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise ShadowPostPromotionReviewError("review contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-SHADOW-POST-PROMOTION-REVIEW-001":
        raise ShadowPostPromotionReviewError("review contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise ShadowPostPromotionReviewError("review product version is not exact")
    if contract.get("status") != "ONE_SHOT_HOST_LOOPBACK_POST_PROMOTION_REVIEW_ONLY":
        raise ShadowPostPromotionReviewError("review must remain one-shot and host-loopback-only")

    expected = _object(contract.get("expected"), "review expected")
    expected_keys = {
        "identity_attester_path",
        "identity_contract_path",
        "image_id",
        "image_reference",
        "image_tag",
        "prior_image_id",
        "shadow_label",
        "core_label",
        "blue_project",
        "current_release_path",
        "blue_release_path",
        "slot_root",
        "slots",
        "core_service",
        "core_connector_service",
        "connector_config_path",
    }
    if set(expected) != expected_keys:
        raise ShadowPostPromotionReviewError("review expected field set is not exact")
    if _path(expected.get("identity_attester_path"), "identity_attester_path") != "/usr/local/lib/abd/shadow_runtime_image_identity_attestation.py":
        raise ShadowPostPromotionReviewError("identity attester path is not exact")
    if _path(expected.get("identity_contract_path"), "identity_contract_path") != "/usr/local/lib/abd/shadow_runtime_image_identity_attestation_contract.json":
        raise ShadowPostPromotionReviewError("identity contract path is not exact")
    image_id = _image_id(expected.get("image_id"), "image_id")
    image_reference = _image_reference(expected.get("image_reference"), "image_reference")
    if image_reference.rsplit("@", 1)[-1] != image_id:
        raise ShadowPostPromotionReviewError("candidate image reference and id disagree")
    _image_id(expected.get("prior_image_id"), "prior_image_id")
    if expected.get("image_tag") != "local/abd-runtime:0.0.0.1":
        raise ShadowPostPromotionReviewError("candidate image tag is not exact")
    if expected.get("shadow_label") != "com.linze.abd.runtime-role=candidate-shadow":
        raise ShadowPostPromotionReviewError("shadow label is not exact")
    if expected.get("core_label") != "com.linze.abd.phase=S04-P01":
        raise ShadowPostPromotionReviewError("core label is not exact")
    if expected.get("blue_project") != "abd-shadow-blue":
        raise ShadowPostPromotionReviewError("blue project is not exact")
    if _path(expected.get("current_release_path"), "current_release_path") != "/opt/abd/current":
        raise ShadowPostPromotionReviewError("current release path is not exact")
    if _path(expected.get("blue_release_path"), "blue_release_path") != "/opt/abd/releases/blue":
        raise ShadowPostPromotionReviewError("blue release path is not exact")
    if _path(expected.get("slot_root"), "slot_root") != "/etc/abd/slots":
        raise ShadowPostPromotionReviewError("slot root is not exact")
    if expected.get("slots") != ["blue", "green"]:
        raise ShadowPostPromotionReviewError("review slots are not exact")
    if expected.get("core_service") != "abd.service" or expected.get("core_connector_service") != "abd-cloudflared.service":
        raise ShadowPostPromotionReviewError("core service names are not exact")
    if _path(expected.get("connector_config_path"), "connector_config_path") != "/etc/cloudflared/config.yml":
        raise ShadowPostPromotionReviewError("connector config path is not exact")

    expected_boundary = {
        "live_docker_metadata_read": True,
        "nonsecret_slot_metadata_read": True,
        "fixed_loopback_identity_attester_invoked": True,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "cloudflare_changed": False,
        "core_runtime_started": False,
        "runtime_state_changed": False,
        "continuous_monitoring_created": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source_boundary") != expected_boundary:
        raise ShadowPostPromotionReviewError("review source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_HOST_LOOPBACK_SHADOW_CONTROL_PLANE_ONLY_NOT_SOURCE_TO_OCI_REVALIDATION_OR_PUBLIC_RELEASE":
        raise ShadowPostPromotionReviewError("review claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_RUNTIME_MUTATION_NO_ROLLBACK_REQUIRED",
        "runtime_or_configuration_changed": False,
        "prior_private_evidence_deleted_automatically": False,
    }:
        raise ShadowPostPromotionReviewError("review rollback boundary is not exact")


def _identity_attester_pass(contract: Mapping[str, Any], observed_on: str, run: CommandRunner) -> bool:
    expected = _object(contract["expected"], "review expected")
    exit_code, stdout = run((str(expected["identity_attester_path"]), "--contract", str(expected["identity_contract_path"]), "--observed-on", observed_on))
    value = _json(stdout)
    return (
        exit_code == 0
        and isinstance(value, dict)
        and value.get("status") == "PASS_SHADOW_IMAGE_IDENTITY_ATTESTATION"
        and value.get("attestation_valid") is True
    )


def collect_review_facts(
    contract: Mapping[str, Any],
    observed_on: str,
    *,
    run: CommandRunner = _run,
    read_text: TextReader = _read_text,
    read_first_line: TextReader = _read_first_line,
) -> dict[str, bool]:
    """Read only host-local Docker and nonsecret control-plane metadata."""

    validate_contract(contract)
    expected = _object(contract["expected"], "review expected")
    facts: dict[str, bool] = {
        "installed_identity_attester_pass": _identity_attester_pass(contract, observed_on, run),
        "installed_identity_contract_matches_candidate": False,
        "exactly_one_shadow": False,
        "core_container_absent": False,
        "running_shadow_candidate_image": False,
        "blue_compose_project_exact": False,
        "candidate_tag_and_reference_exact": False,
        "prior_image_retained_untagged": False,
        "current_release_blue": False,
        "blue_green_slot_controls_match_candidate": False,
        "core_service_inactive": False,
        "core_connector_inactive": False,
        "connector_has_no_hostname": False,
    }
    try:
        identity_contract = _object(json.loads(read_text(Path(str(expected["identity_contract_path"])))), "installed identity contract")
        installed_expected = _object(identity_contract.get("expected"), "installed identity expected")
        facts["installed_identity_contract_matches_candidate"] = (
            installed_expected.get("image_id") == expected["image_id"]
            and installed_expected.get("image_reference") == expected["image_reference"]
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowPostPromotionReviewError):
        pass

    shadow_exit_code, shadow_output = run(("docker", "ps", "-q", "--filter", "label=" + str(expected["shadow_label"])))
    core_exit_code, core_output = run(("docker", "ps", "-q", "--filter", "label=" + str(expected["core_label"])))
    shadow_ids = _lines(shadow_output)
    facts["exactly_one_shadow"] = shadow_exit_code == 0 and len(shadow_ids) == 1
    facts["core_container_absent"] = core_exit_code == 0 and not _lines(core_output)
    if len(shadow_ids) == 1:
        container_id = shadow_ids[0]
        image_exit_code, image_output = run(("docker", "inspect", "--format", "{{.Image}}", container_id))
        facts["running_shadow_candidate_image"] = image_exit_code == 0 and image_output == expected["image_id"]
        labels_exit_code, labels_output = run(("docker", "inspect", "--format", "{{json .Config.Labels}}", container_id))
        labels = _json(labels_output)
        facts["blue_compose_project_exact"] = (
            labels_exit_code == 0 and isinstance(labels, dict) and labels.get("com.docker.compose.project") == expected["blue_project"]
        )

    tag_exit_code, tag_output = run(("docker", "image", "inspect", "--format", "{{json .RepoTags}}", str(expected["image_id"])))
    reference_exit_code, reference_output = run(("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", str(expected["image_id"])))
    facts["candidate_tag_and_reference_exact"] = (
        tag_exit_code == 0
        and reference_exit_code == 0
        and _json(tag_output) == [expected["image_tag"]]
        and _json(reference_output) == [expected["image_reference"]]
    )
    prior_tag_exit_code, prior_tag_output = run(("docker", "image", "inspect", "--format", "{{json .RepoTags}}", str(expected["prior_image_id"])))
    prior_reference_exit_code, prior_reference_output = run(("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", str(expected["prior_image_id"])))
    facts["prior_image_retained_untagged"] = (
        prior_tag_exit_code == 0
        and prior_reference_exit_code == 0
        and _json(prior_tag_output) in ([], None)
        and _json(prior_reference_output) in ([], None)
    )

    current_exit_code, current_output = run(("readlink", "-f", str(expected["current_release_path"])))
    facts["current_release_blue"] = current_exit_code == 0 and current_output == expected["blue_release_path"]
    try:
        slots_exact = True
        for slot_id in expected["slots"]:
            slot = str(slot_id)
            release_manifest = _object(json.loads(read_text(Path("/opt/abd/releases") / slot / "release_manifest.json")), "slot manifest")
            first_line = read_first_line(Path(str(expected["slot_root"])) / (slot + ".env"))
            slots_exact = slots_exact and (
                release_manifest.get("image_id") == expected["image_id"]
                and release_manifest.get("image_reference") == expected["image_reference"]
                and first_line == "ABD_IMAGE=" + str(expected["image_reference"])
            )
        facts["blue_green_slot_controls_match_candidate"] = slots_exact
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowPostPromotionReviewError, IndexError):
        pass

    core_service_exit_code, core_service_state = run(("systemctl", "is-active", str(expected["core_service"])))
    core_connector_exit_code, core_connector_state = run(("systemctl", "is-active", str(expected["core_connector_service"])))
    facts["core_service_inactive"] = core_service_exit_code in (0, 3) and core_service_state == "inactive"
    facts["core_connector_inactive"] = core_connector_exit_code in (0, 3) and core_connector_state == "inactive"
    try:
        connector_config = read_text(Path(str(expected["connector_config_path"])))
        facts["connector_has_no_hostname"] = not any(line.lstrip().startswith("hostname:") for line in connector_config.splitlines())
    except (OSError, UnicodeDecodeError, ShadowPostPromotionReviewError):
        pass
    return facts


def evaluate_review_facts(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    required = {
        "installed_identity_attester_pass",
        "installed_identity_contract_matches_candidate",
        "exactly_one_shadow",
        "core_container_absent",
        "running_shadow_candidate_image",
        "blue_compose_project_exact",
        "candidate_tag_and_reference_exact",
        "prior_image_retained_untagged",
        "current_release_blue",
        "blue_green_slot_controls_match_candidate",
        "core_service_inactive",
        "core_connector_inactive",
        "connector_has_no_hostname",
    }
    if set(facts) != required or not all(isinstance(value, bool) for value in facts.values()):
        raise ShadowPostPromotionReviewError("review facts must be exact booleans")
    checks = [{"id": name.upper(), "passed": facts[name]} for name in sorted(required)]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if not failure_codes else FAIL_STATUS,
        "decision": "CURRENT_BLUE_SHADOW_BOUNDARY_REMAINS_INTACT" if not failure_codes else "CURRENT_BLUE_SHADOW_BOUNDARY_REQUIRES_SEPARATE_REMEDIATION_PHASE",
        "review_valid": not failure_codes,
        "checks": checks,
        "failure_codes": failure_codes,
        "observed": dict(facts),
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any], observed_on: str) -> dict[str, Any]:
    validate_contract(contract)
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowPostPromotionReviewError("observed date is invalid") from exc
    result = evaluate_review_facts(contract, facts)
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": observed_date,
        "review_scope": "HOST_LOCAL_DOCKER_NONSECRET_SLOT_METADATA_SYSTEMD_STATE_AND_NO_HOSTNAME_CONNECTOR_ONLY",
        "review_valid": result["review_valid"],
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "observed": {
            "shadow_container_count": 1 if facts["exactly_one_shadow"] else 0,
            "core_container_count": 0 if facts["core_container_absent"] else 1,
            "active_slot": "blue" if facts["current_release_blue"] else "NOT_BLUE",
            "candidate_running": facts["running_shadow_candidate_image"],
            "connector_hostname_configured": not facts["connector_has_no_hostname"],
        },
        "source_boundary": dict(_object(contract["source_boundary"], "source_boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def build_diagnostic_receipt(
    contract: Mapping[str, Any],
    facts: Mapping[str, Any],
    observed_on: str,
    *,
    connector_config_regular_file: bool,
) -> dict[str, Any]:
    """Return redacted per-stage control-plane diagnostics without remediation."""

    validate_contract(contract)
    if not isinstance(connector_config_regular_file, bool):
        raise ShadowPostPromotionReviewError("connector regular-file observation must be a boolean")
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowPostPromotionReviewError("observed date is invalid") from exc
    result = evaluate_review_facts(contract, facts)
    connector_has_no_hostname = connector_config_regular_file and bool(facts["connector_has_no_hostname"])
    stages = [
        {"id": "IDENTITY_ATTESTER_PASS", "passed": facts["installed_identity_attester_pass"]},
        {"id": "IDENTITY_CONTRACT_MATCHES_CANDIDATE", "passed": facts["installed_identity_contract_matches_candidate"]},
        {"id": "EXACTLY_ONE_SHADOW", "passed": facts["exactly_one_shadow"]},
        {"id": "CORE_RUNTIME_ABSENT", "passed": facts["core_container_absent"]},
        {"id": "RUNNING_SHADOW_CANDIDATE_IMAGE", "passed": facts["running_shadow_candidate_image"]},
        {"id": "BLUE_COMPOSE_PROJECT_EXACT", "passed": facts["blue_compose_project_exact"]},
        {"id": "CANDIDATE_TAG_AND_REFERENCE_EXACT", "passed": facts["candidate_tag_and_reference_exact"]},
        {"id": "PRIOR_IMAGE_RETAINED_UNTAGGED", "passed": facts["prior_image_retained_untagged"]},
        {"id": "CURRENT_RELEASE_BLUE", "passed": facts["current_release_blue"]},
        {"id": "BLUE_GREEN_SLOT_CONTROLS_MATCH_CANDIDATE", "passed": facts["blue_green_slot_controls_match_candidate"]},
        {"id": "CORE_SERVICE_INACTIVE", "passed": facts["core_service_inactive"]},
        {"id": "CORE_CONNECTOR_INACTIVE", "passed": facts["core_connector_inactive"]},
        {"id": "CONNECTOR_CONFIG_REGULAR_FILE", "passed": connector_config_regular_file},
        {"id": "CONNECTOR_HAS_NO_HOSTNAME", "passed": connector_has_no_hostname},
    ]
    failure_codes = [str(stage["id"]) for stage in stages if not stage["passed"]]
    valid = not failure_codes
    return {
        "schema_version": "1.0.0",
        "receipt_type": DIAGNOSTIC_RECEIPT_TYPE,
        "status": DIAGNOSTIC_PASS_STATUS if valid else DIAGNOSTIC_FAIL_STATUS,
        "decision": "CURRENT_BLUE_SHADOW_CONTROL_PLANE_DIAGNOSTIC_PASS" if valid else "CURRENT_BLUE_SHADOW_CONTROL_PLANE_DIAGNOSTIC_IDENTIFIED_GAPS",
        "observed_on": observed_date,
        "diagnostic_complete": True,
        "control_plane_valid": valid,
        "stages": stages,
        "failure_codes": failure_codes,
        "observed": {
            "shadow_container_count": 1 if facts["exactly_one_shadow"] else 0,
            "core_container_count": 0 if facts["core_container_absent"] else 1,
            "active_slot": "blue" if facts["current_release_blue"] else "NOT_BLUE",
            "candidate_running": facts["running_shadow_candidate_image"],
            "connector_config_regular_file": connector_config_regular_file,
            "connector_hostname_configured": None if not connector_config_regular_file else not connector_has_no_hostname,
        },
        "source_boundary": dict(_object(contract["source_boundary"], "source_boundary")),
        "claim_boundary": contract["claim_boundary"],
        "review_status_before_diagnostic": result["status"],
    }


def observe_host(contract_path: Path, observed_on: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ShadowPostPromotionReviewError("host observation must run as root")
    contract = load_contract(contract_path)
    facts = collect_review_facts(contract, observed_on)
    return build_receipt(contract, facts, observed_on)


def diagnose_host(contract_path: Path, observed_on: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ShadowPostPromotionReviewError("host diagnostic must run as root")
    contract = load_contract(contract_path)
    expected = _object(contract["expected"], "review expected")
    facts = collect_review_facts(contract, observed_on)
    connector_config_regular_file = _is_regular_file(Path(str(expected["connector_config_path"])))
    return build_diagnostic_receipt(
        contract,
        facts,
        observed_on,
        connector_config_regular_file=connector_config_regular_file,
    )


def _failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        observed_date = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_BLUE_SHADOW_REVIEW_INPUT_OR_EXECUTION_FAIL_CLOSED",
        "observed_on": observed_date,
        "review_valid": False,
        "checks": [],
        "failure_codes": ["POST_PROMOTION_CONTROL_PLANE_REVIEW_FAILED"],
        "error_type": type(error).__name__,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "real_time_soak_waited": False,
    }


def _diagnostic_failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        observed_date = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": DIAGNOSTIC_RECEIPT_TYPE,
        "status": DIAGNOSTIC_FAIL_STATUS,
        "decision": "CURRENT_BLUE_SHADOW_CONTROL_PLANE_DIAGNOSTIC_FAILED_CLOSED",
        "observed_on": observed_date,
        "diagnostic_complete": False,
        "control_plane_valid": False,
        "stages": [],
        "failure_codes": ["POST_PROMOTION_CONTROL_PLANE_DIAGNOSTIC_FAILED"],
        "error_type": type(error).__name__,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = diagnose_host(args.contract, args.observed_on) if args.diagnose else observe_host(args.contract, args.observed_on)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowPostPromotionReviewError, ValueError) as exc:
        receipt = _diagnostic_failure_receipt(exc, args.observed_on) if args.diagnose else _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    expected_status = DIAGNOSTIC_PASS_STATUS if args.diagnose else PASS_STATUS
    return 0 if receipt["status"] == expected_status else 1


if __name__ == "__main__":
    raise SystemExit(main())
