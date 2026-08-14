#!/usr/bin/env python3
"""Promote one preloaded, source-attested OCI candidate into the ABD blue shadow slot."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from shadow_release_control_plane_recovery import (
    CONTAINER_NAME_RE,
    ShadowControlPlaneRecoveryError,
    _attest_image_identity,
    _atomic_write,
    _canonical_facts,
    _container_name,
    _docker_inspect,
    _image_id,
    _image_reference,
    _json_bytes,
    _line_values,
    _mounts_by_destination,
    _object,
    _path_has_exact_metadata,
    _run,
    _sha256,
    _sha256_value,
    build_release_manifest,
    load_contract as load_release_contract,
    render_slot_env,
    slot_for,
    validate_contract as validate_release_contract,
)
from shadow_runtime_image_identity_attestation import (
    ShadowImageIdentityAttestationError,
    load_contract as load_identity_contract,
    validate_contract as validate_identity_contract,
)


PASS_STATUS = "PASS_SHADOW_SOURCE_PROVENANCE_PROMOTION"
FAIL_STATUS = "FAIL_SHADOW_SOURCE_PROVENANCE_PROMOTION"
RECEIPT_TYPE = "ABD_POST_FREEZE_SHADOW_SOURCE_PROVENANCE_PROMOTION"
SLOT_IDS = ("blue", "green")
HOST_IDENTITY_VALIDATOR = Path("/usr/local/lib/abd/shadow_runtime_image_identity_attestation.py")
HOST_IDENTITY_CONTRACT = Path("/usr/local/lib/abd/shadow_runtime_image_identity_attestation_contract.json")
SAFE_BIND_SOURCE_RE = re.compile(r"^/[A-Za-z0-9_.\-/]+$")


class ShadowSourceProvenancePromotionError(ValueError):
    """Raised when a source-provenance promotion would weaken the shadow boundary."""


class PromotionExecutionError(ShadowSourceProvenancePromotionError):
    """A fail-closed host mutation error with its rollback outcome."""

    def __init__(
        self,
        error_type: str,
        *,
        failure_step: str,
        rollback_attempted: bool,
        rollback_restored: bool,
        diagnostics: Mapping[str, bool],
    ) -> None:
        super().__init__(error_type)
        self.failure_step = failure_step
        self.rollback_attempted = rollback_attempted
        self.rollback_restored = rollback_restored
        self.diagnostics = dict(diagnostics)


FileSnapshot = tuple[bytes, int, int, int]


def _json_object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ShadowSourceProvenancePromotionError("%s must be an object" % name)
    return value


def _exact_string(value: object, expected: str, name: str) -> str:
    if value != expected:
        raise ShadowSourceProvenancePromotionError("%s is not exact" % name)
    return expected


def _digest(value: object, name: str) -> str:
    try:
        return _sha256_value(value, name)
    except ShadowControlPlaneRecoveryError as exc:
        raise ShadowSourceProvenancePromotionError("%s is malformed" % name) from exc


def _image_digest(value: object, name: str) -> str:
    try:
        return _image_id(value, name)
    except ShadowControlPlaneRecoveryError as exc:
        raise ShadowSourceProvenancePromotionError("%s is malformed" % name) from exc


def _image_ref(value: object, name: str) -> str:
    try:
        return _image_reference(value, name)
    except ShadowControlPlaneRecoveryError as exc:
        raise ShadowSourceProvenancePromotionError("%s is malformed" % name) from exc


def _regular_bytes(path: Path, name: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ShadowSourceProvenancePromotionError("%s must be a regular file" % name)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ShadowSourceProvenancePromotionError("%s is unreadable" % name) from exc


def _load_json_bytes(data: bytes, name: str) -> Mapping[str, Any]:
    try:
        return _json_object(json.loads(data), name)
    except (UnicodeDecodeError, json.JSONDecodeError, ShadowSourceProvenancePromotionError) as exc:
        raise ShadowSourceProvenancePromotionError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load_json_bytes(_regular_bytes(path, "promotion contract"), "promotion contract")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "contract_id",
        "product_version",
        "status",
        "source_provenance",
        "candidate",
        "previous",
        "required_contracts",
        "source_boundary",
        "rollback",
    }
    if set(contract) != required:
        raise ShadowSourceProvenancePromotionError("promotion contract field set is not exact")
    _exact_string(contract.get("schema_version"), "1.0.0", "schema_version")
    _exact_string(contract.get("contract_id"), "ABD-POST-FREEZE-SHADOW-SOURCE-PROVENANCE-PROMOTION-001", "contract_id")
    _exact_string(contract.get("product_version"), "0.0.0.1", "product_version")
    _exact_string(
        contract.get("status"),
        "ONE_SHOT_HOST_LOOPBACK_SOURCE_PROVENANCE_BLUE_PROMOTION_ONLY",
        "status",
    )

    source = _json_object(contract.get("source_provenance"), "source_provenance")
    expected_source = {
        "source_commit": "b7df8bee5bc91987970ce51d540c68f3fc324f36",
        "source_archive_sha256": "7ad7b97aeaaec84b747dc3002a849851cba7625fa7e300dd1015ff83d023d6d6",
        "source_to_oci_receipt_sha256": "f6052b31867d35bed665662831aa51f4321c7ef86129fac901190552aca04395",
        "oci_archive_sha256": "2cbfde404f1d21b3241da4f31eb67f44708798c959e62c2213265647c2db332d",
        "oci_manifest_digest": "sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "oci_config_digest": "sha256:e9a3d81370ec722178393f1d153fc8c1540987ec44740aa435603977b1688702",
    }
    if dict(source) != expected_source:
        raise ShadowSourceProvenancePromotionError("source provenance is not exact")
    for key in ("source_archive_sha256", "source_to_oci_receipt_sha256", "oci_archive_sha256"):
        _digest(source[key], key)
    for key in ("oci_manifest_digest", "oci_config_digest"):
        _image_digest(source[key], key)

    candidate = _json_object(contract.get("candidate"), "candidate")
    expected_candidate = {
        "docker_image_id": expected_source["oci_manifest_digest"],
        "image_reference": "local/abd-runtime@" + expected_source["oci_manifest_digest"],
        "image_tag": "local/abd-runtime:0.0.0.1",
        "repo_tags_before_promotion": [],
        "repo_digests_before_promotion": [],
        "architecture": "amd64",
        "os": "linux",
        "labels": {
            "org.opencontainers.image.title": "ABD observation runtime",
            "org.opencontainers.image.version": "0.0.0.1",
            "org.opencontainers.image.description": "Non-trading, non-recommendation ABD runtime control plane",
        },
    }
    if dict(candidate) != expected_candidate:
        raise ShadowSourceProvenancePromotionError("candidate identity is not exact")
    if _image_ref(candidate["image_reference"], "candidate image_reference").rsplit("@", 1)[-1] != _image_digest(
        candidate["docker_image_id"], "candidate docker_image_id"
    ):
        raise ShadowSourceProvenancePromotionError("candidate image reference and id disagree")

    previous = _json_object(contract.get("previous"), "previous")
    expected_previous = {
        "image_id": "sha256:6d51e3e01c2fb7a02460ac9c9eeaf20b8f41f144c4dc795eaae5335b15737ec8",
        "image_reference": "local/abd-runtime@sha256:6d51e3e01c2fb7a02460ac9c9eeaf20b8f41f144c4dc795eaae5335b15737ec8",
        "image_tag": "local/abd-runtime:0.0.0.1",
    }
    if dict(previous) != expected_previous:
        raise ShadowSourceProvenancePromotionError("previous identity is not exact")
    if _image_ref(previous["image_reference"], "previous image_reference").rsplit("@", 1)[-1] != _image_digest(
        previous["image_id"], "previous image_id"
    ):
        raise ShadowSourceProvenancePromotionError("previous image reference and id disagree")

    if _json_object(contract.get("required_contracts"), "required_contracts") != {
        "release_control_plane_contract_id": "ABD-POST-FREEZE-SHADOW-CANONICAL-CONTROL-PLANE-001",
        "identity_attester_contract_id": "ABD-POST-FREEZE-SHADOW-IMAGE-IDENTITY-005",
    }:
        raise ShadowSourceProvenancePromotionError("required contracts are not exact")
    if _json_object(contract.get("source_boundary"), "source_boundary") != {
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "cloudflare_changed": False,
        "core_runtime_started": False,
        "running_shadow_replaced": True,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise ShadowSourceProvenancePromotionError("source boundary is not exact")
    if _json_object(contract.get("rollback"), "rollback") != {
        "preserve_prior_container_until_candidate_attested": True,
        "restore_prior_image_tag_and_identity_contract_on_failure": True,
        "restore_prior_slot_env_and_manifests_on_failure": True,
        "remove_only_candidate_containers_created_by_this_run_on_failure": True,
        "keep_prior_image_after_success_for_manual_rollback": True,
        "remove_prior_container_after_success_only": True,
    }:
        raise ShadowSourceProvenancePromotionError("rollback boundary is not exact")


def _source_receipt_exact(contract: Mapping[str, Any], receipt_path: Path) -> bool:
    source = _json_object(contract["source_provenance"], "source_provenance")
    receipt_bytes = _regular_bytes(receipt_path, "source-to-OCI receipt")
    if _sha256(receipt_bytes) != source["source_to_oci_receipt_sha256"]:
        return False
    receipt = _load_json_bytes(receipt_bytes, "source-to-OCI receipt")
    return (
        receipt.get("schema_version") == "1.0.0"
        and receipt.get("receipt_type") == "ABD_POST_FREEZE_SHADOW_SOURCE_TO_OCI_CANDIDATE"
        and receipt.get("status") == "PASS_SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE"
        and receipt.get("decision") == "SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE_PASS_NOT_LOADED_OR_STARTED"
        and receipt.get("source")
        == {
            "git_commit": source["source_commit"],
            "archive_sha256": source["source_archive_sha256"],
            "archive_bytes": 20480,
            "file_count": 5,
        }
        and receipt.get("candidate")
        == {
            "manifest_digest": source["oci_manifest_digest"],
            "image_id": source["oci_config_digest"],
            "oci_archive_sha256": source["oci_archive_sha256"],
            "oci_archive_bytes": 18043392,
            "architecture": "amd64",
            "os": "linux",
            "layer_count": 7,
            "loaded_into_docker_store": False,
            "started": False,
        }
        and receipt.get("source_boundary")
        == {
            "runtime_secret_content_read": False,
            "external_network_accessed": False,
            "cloudflare_changed": False,
            "core_runtime_started": False,
            "running_shadow_replaced": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        }
    )


def _candidate_archive_exact(contract: Mapping[str, Any], candidate_archive: Path) -> bool:
    source = _json_object(contract["source_provenance"], "source_provenance")
    return _sha256(_regular_bytes(candidate_archive, "OCI candidate archive")) == source["oci_archive_sha256"]


def _docker_image(identifier: str) -> Mapping[str, Any]:
    try:
        value = json.loads(_run(("docker", "image", "inspect", identifier)))
    except (json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise ShadowSourceProvenancePromotionError("Docker image inspect is unavailable") from exc
    if not isinstance(value, list) or len(value) != 1:
        raise ShadowSourceProvenancePromotionError("Docker image inspect result is malformed")
    return _json_object(value[0], "Docker image inspect result")


def _candidate_loaded_untagged_exact(contract: Mapping[str, Any]) -> bool:
    candidate = _json_object(contract["candidate"], "candidate")
    image = _docker_image(str(candidate["docker_image_id"]))
    return (
        image.get("Id") == candidate["docker_image_id"]
        and image.get("RepoTags") == candidate["repo_tags_before_promotion"]
        and image.get("RepoDigests") == candidate["repo_digests_before_promotion"]
        and image.get("Architecture") == candidate["architecture"]
        and image.get("Os") == candidate["os"]
        and image.get("Config") is not None
        and _json_object(image["Config"], "candidate Docker config").get("Labels") == candidate["labels"]
    )


def _prior_release_contract(release_contract: Mapping[str, Any], promotion_contract: Mapping[str, Any]) -> Mapping[str, Any]:
    previous = _json_object(promotion_contract["previous"], "previous")
    prior = copy.deepcopy(dict(release_contract))
    prior["expected_image_reference"] = previous["image_reference"]
    prior["expected_image_id"] = previous["image_id"]
    try:
        validate_release_contract(prior)
    except ShadowControlPlaneRecoveryError as exc:
        raise ShadowSourceProvenancePromotionError("prior release contract is invalid") from exc
    return prior


def _validate_release_contract(release_contract: Mapping[str, Any], promotion_contract: Mapping[str, Any]) -> None:
    try:
        validate_release_contract(release_contract)
    except ShadowControlPlaneRecoveryError as exc:
        raise ShadowSourceProvenancePromotionError("candidate release contract is invalid") from exc
    candidate = _json_object(promotion_contract["candidate"], "candidate")
    required = _json_object(promotion_contract["required_contracts"], "required_contracts")
    if (
        release_contract.get("contract_id") != required["release_control_plane_contract_id"]
        or release_contract.get("product_version") != promotion_contract["product_version"]
        or release_contract.get("expected_image_reference") != candidate["image_reference"]
        or release_contract.get("expected_image_id") != candidate["docker_image_id"]
    ):
        raise ShadowSourceProvenancePromotionError("candidate release contract does not bind the candidate image")


def _validate_identity_inputs(
    promotion_contract: Mapping[str, Any], identity_contract_path: Path, identity_validator_path: Path
) -> bytes:
    candidate = _json_object(promotion_contract["candidate"], "candidate")
    required = _json_object(promotion_contract["required_contracts"], "required_contracts")
    try:
        identity_contract = load_identity_contract(identity_contract_path)
        validate_identity_contract(identity_contract)
    except ShadowImageIdentityAttestationError as exc:
        raise ShadowSourceProvenancePromotionError("candidate identity attestation contract is invalid") from exc
    expected = _json_object(identity_contract.get("expected"), "candidate identity expected")
    if (
        identity_contract.get("contract_id") != required["identity_attester_contract_id"]
        or expected.get("image_reference") != candidate["image_reference"]
        or expected.get("image_id") != candidate["docker_image_id"]
    ):
        raise ShadowSourceProvenancePromotionError("candidate identity attestation does not bind the candidate image")
    staged_validator = _regular_bytes(identity_validator_path, "staged identity attester")
    installed_validator = _regular_bytes(HOST_IDENTITY_VALIDATOR, "installed identity attester")
    if staged_validator != installed_validator:
        raise ShadowSourceProvenancePromotionError("installed identity attester differs from the reviewed staged source")
    return _regular_bytes(identity_contract_path, "candidate identity attestation contract")


def _snapshot(path: Path, *, mode: int, uid: int, gid: int, name: str) -> FileSnapshot:
    if not _path_has_exact_metadata(path, kind="file", mode=mode, uid=uid, gid=gid):
        raise ShadowSourceProvenancePromotionError("%s metadata is not exact" % name)
    return (_regular_bytes(path, name), mode, uid, gid)


def _capture_control_files(release_contract: Mapping[str, Any]) -> dict[Path, FileSnapshot]:
    snapshots: dict[Path, FileSnapshot] = {}
    for slot_id in SLOT_IDS:
        slot = slot_for(release_contract, slot_id)
        env_path = Path(str(slot["runtime_env_path"]))
        manifest_path = Path(str(slot["release_path"])) / "release_manifest.json"
        snapshots[env_path] = _snapshot(env_path, mode=0o600, uid=0, gid=0, name=slot_id + " slot env")
        snapshots[manifest_path] = _snapshot(manifest_path, mode=0o644, uid=0, gid=0, name=slot_id + " release manifest")
    snapshots[HOST_IDENTITY_CONTRACT] = _snapshot(
        HOST_IDENTITY_CONTRACT, mode=0o644, uid=0, gid=0, name="installed identity attestation contract"
    )
    return snapshots


def _secret_source_from_env(env_bytes: bytes, slot_id: str) -> str:
    try:
        lines = env_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ShadowSourceProvenancePromotionError("%s slot environment is not UTF-8" % slot_id) from exc
    matches = [line.split("=", 1)[1] for line in lines if line.startswith("ABD_RUNTIME_SECRET_FILE=")]
    if len(matches) != 1 or not matches[0].startswith("/etc/abd/secrets/") or "\n" in matches[0] or "\x00" in matches[0]:
        raise ShadowSourceProvenancePromotionError("%s slot secret source is not safe" % slot_id)
    source = Path(matches[0])
    if not source.is_file() or source.is_symlink():
        raise ShadowSourceProvenancePromotionError("%s slot secret source is unavailable" % slot_id)
    return matches[0]


def _write_candidate_control_files(
    release_contract: Mapping[str, Any], snapshots: Mapping[Path, FileSnapshot]
) -> None:
    layout = _json_object(release_contract["canonical_layout"], "canonical layout")
    config_path = Path(str(layout["canonical_config_path"]))
    if not config_path.is_file() or config_path.is_symlink():
        raise ShadowSourceProvenancePromotionError("canonical config is unavailable")
    config_sha256 = _sha256(_regular_bytes(config_path, "canonical config"))
    for slot_id in SLOT_IDS:
        slot = slot_for(release_contract, slot_id)
        env_path = Path(str(slot["runtime_env_path"]))
        manifest_path = Path(str(slot["release_path"])) / "release_manifest.json"
        secret_source = _secret_source_from_env(snapshots[env_path][0], slot_id)
        env_bytes = render_slot_env(release_contract, slot_id, secret_source)
        _atomic_write(env_path, env_bytes, 0o600, 0, 0)
        manifest = build_release_manifest(
            release_contract,
            slot_id,
            config_sha256=config_sha256,
            slot_env_sha256=_sha256(env_bytes),
        )
        _atomic_write(manifest_path, _json_bytes(manifest), 0o644, 0, 0)


def _restore_files(snapshots: Mapping[Path, FileSnapshot]) -> None:
    for path in sorted(snapshots, key=lambda item: item.as_posix()):
        data, mode, uid, gid = snapshots[path]
        _atomic_write(path, data, mode, uid, gid)


def _image_is_untagged(image_id: str) -> bool:
    try:
        image = _docker_image(image_id)
    except ShadowSourceProvenancePromotionError:
        return False
    return image.get("RepoTags") in (None, []) and image.get("RepoDigests") in (None, [])


def _network_name(container: Mapping[str, Any]) -> str:
    host = _json_object(container.get("HostConfig"), "prior shadow host config")
    network_settings = _json_object(container.get("NetworkSettings"), "prior shadow network settings")
    networks = _json_object(network_settings.get("Networks"), "prior shadow networks")
    network = host.get("NetworkMode")
    if not isinstance(network, str) or not CONTAINER_NAME_RE.fullmatch(network) or set(networks) != {network}:
        raise ShadowSourceProvenancePromotionError("prior shadow network is not exact")
    return network


def _create_candidate_blue(
    release_contract: Mapping[str, Any], promotion_contract: Mapping[str, Any], state: Mapping[str, Any]
) -> None:
    """Create the new blue container directly so the renamed prior project is never Compose-reconciled away."""

    shadow = _json_object(release_contract["required_running_shadow"], "candidate running shadow")
    blue = slot_for(release_contract, "blue")
    env_path = Path(str(blue["runtime_env_path"]))
    secret_source = _secret_source_from_env(_regular_bytes(env_path, "candidate blue slot env"), "blue")
    config_path = str(_json_object(release_contract["canonical_layout"], "canonical layout")["canonical_config_path"])
    state_path = str(_json_object(release_contract["canonical_layout"], "canonical layout")["canonical_state_path"])
    log_path = str(blue["log_path"])
    if not all(SAFE_BIND_SOURCE_RE.fullmatch(value) for value in (secret_source, config_path, state_path, log_path)):
        raise ShadowSourceProvenancePromotionError("candidate bind source is unsafe")
    candidate = _json_object(promotion_contract["candidate"], "candidate")
    labels = [
        "com.linze.abd.order-submission=disabled",
        "com.linze.abd.phase=S04-STAGE-REVIEW",
        "com.linze.abd.product-version=0.0.0.1",
        "com.linze.abd.runtime-role=candidate-shadow",
        "com.docker.compose.project=" + str(blue["project_name"]),
        "com.docker.compose.service=abd-shadow",
        "com.docker.compose.container-number=1",
        "com.docker.compose.oneoff=False",
    ]
    command: list[str] = ["docker", "create", "--name", str(state["old_name"])]
    for label in labels:
        command.extend(("--label", label))
    command.extend(
        (
            "--user",
            str(shadow["user"]),
            "--read-only",
            "--init",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(shadow["pids_limit"]),
            "--cpus",
            "0.25",
            "--memory",
            "512m",
            "--memory-reservation",
            "128m",
            "--memory-swap",
            "512m",
            "--restart",
            "no",
            "--publish",
            str(shadow["loopback_port"]) + ":8080/tcp",
            "--env",
            "ABD_CONFIG_FILE=/etc/abd/config.json",
            "--env",
            "ABD_ORDER_SUBMISSION_ENABLED=false",
            "--env",
            "ABD_RUNTIME_MODE=SHADOW_READ_ONLY",
            "--env",
            "ABD_RUNTIME_SECRET_FILE=/run/secrets/abd_runtime",
            "--mount",
            "type=bind,src=" + config_path + ",dst=/etc/abd/config.json,readonly",
            "--mount",
            "type=bind,src=" + state_path + ",dst=/var/lib/abd,readonly",
            "--mount",
            "type=bind,src=" + log_path + ",dst=/var/log/abd",
            "--mount",
            "type=bind,src=" + secret_source + ",dst=/run/secrets/abd_runtime,readonly",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=32m",
            "--network",
            str(state["old_network"]),
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=10m",
            "--log-opt",
            "max-file=3",
            str(candidate["image_reference"]),
        )
    )
    _run(tuple(command))
    _run(("docker", "start", str(state["old_name"])))


def _candidate_runtime_shape_exact(release_contract: Mapping[str, Any], *, expected_network: str) -> bool:
    try:
        shadow = _json_object(release_contract["required_running_shadow"], "candidate running shadow")
        shadow_ids = _line_values(_run(("docker", "ps", "-q", "--filter", "label=" + str(shadow["shadow_label"]))))
        if len(shadow_ids) != 1:
            return False
        container = _docker_inspect(shadow_ids[0])
        config = _json_object(container.get("Config"), "candidate shadow config")
        host = _json_object(container.get("HostConfig"), "candidate shadow host config")
        if (
            config.get("User") != shadow["user"]
            or config.get("Entrypoint") != shadow["entrypoint"]
            or config.get("WorkingDir") != shadow["working_dir"]
            or host.get("Memory") != shadow["memory_limit_bytes"]
            or host.get("MemorySwap") != shadow["memory_swap_limit_bytes"]
            or host.get("NanoCpus") != shadow["cpu_nano_cpus"]
            or host.get("PidsLimit") != shadow["pids_limit"]
            or host.get("PortBindings") != {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8081"}]}
            or host.get("NetworkMode") != expected_network
            or host.get("ReadonlyRootfs") is not True
            or host.get("Init") is not True
            or host.get("CapDrop") != ["ALL"]
            or host.get("SecurityOpt") != ["no-new-privileges:true"]
        ):
            return False
        labels = _json_object(config.get("Labels"), "candidate shadow labels")
        blue = slot_for(release_contract, "blue")
        if (
            labels.get("com.linze.abd.order-submission") != "disabled"
            or labels.get("com.linze.abd.phase") != "S04-STAGE-REVIEW"
            or labels.get("com.linze.abd.product-version") != "0.0.0.1"
            or labels.get("com.linze.abd.runtime-role") != "candidate-shadow"
            or labels.get("com.docker.compose.project") != blue["project_name"]
            or labels.get("com.docker.compose.service") != "abd-shadow"
        ):
            return False
        mounts = _mounts_by_destination(container)
        if set(mounts) != {"/etc/abd/config.json", "/var/lib/abd", "/var/log/abd", "/run/secrets/abd_runtime"}:
            return False
        layout = _json_object(release_contract["canonical_layout"], "canonical layout")
        return (
            mounts["/etc/abd/config.json"].get("Source") == layout["canonical_config_path"]
            and mounts["/etc/abd/config.json"].get("RW") is False
            and mounts["/var/lib/abd"].get("Source") == layout["canonical_state_path"]
            and mounts["/var/lib/abd"].get("RW") is False
            and mounts["/var/log/abd"].get("Source") == blue["log_path"]
            and mounts["/var/log/abd"].get("RW") is True
            and isinstance(mounts["/run/secrets/abd_runtime"].get("Source"), str)
            and str(mounts["/run/secrets/abd_runtime"]["Source"]).startswith("/etc/abd/secrets/")
            and mounts["/run/secrets/abd_runtime"].get("RW") is False
        )
    except (ShadowControlPlaneRecoveryError, ShadowSourceProvenancePromotionError, subprocess.SubprocessError):
        return False


def _remove_candidate_project_containers(prior_project_ids: set[str]) -> bool:
    try:
        all_project_ids = set(
            _line_values(_run(("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=abd-shadow-blue")))
        )
    except (ShadowControlPlaneRecoveryError, subprocess.SubprocessError):
        return False
    ok = True
    for identifier in sorted(all_project_ids - prior_project_ids):
        completed = subprocess.run(("docker", "rm", "-f", identifier), check=False, capture_output=True, text=True)
        if completed.returncode != 0 and subprocess.run(("docker", "inspect", identifier), capture_output=True).returncode == 0:
            ok = False
    return ok


def _rollback(state: Mapping[str, Any], *, tag_moved: bool, control_written: bool, project_attempted: bool, old_stopped: bool, old_renamed: bool) -> bool:
    restored = True
    if project_attempted:
        restored = _remove_candidate_project_containers(set(state["prior_project_ids"])) and restored
    try:
        if control_written:
            _restore_files(state["snapshots"])
        if tag_moved:
            _run(("docker", "tag", str(state["old_image_id"]), str(state["previous_image_tag"])))
        if old_stopped:
            completed = subprocess.run(("docker", "start", str(state["rollback_name"])), check=False, capture_output=True, text=True)
            restored = restored and completed.returncode == 0
        if old_renamed:
            completed = subprocess.run(
                ("docker", "rename", str(state["rollback_name"]), str(state["old_name"])),
                check=False,
                capture_output=True,
                text=True,
            )
            restored = restored and completed.returncode == 0
    except (OSError, ShadowControlPlaneRecoveryError, subprocess.SubprocessError):
        restored = False
    return _attest_image_identity(str(state["observed_on"])) and restored


def _preflight(
    promotion_contract: Mapping[str, Any],
    release_contract: Mapping[str, Any],
    *,
    candidate_archive: Path,
    source_receipt: Path,
    identity_contract_path: Path,
    identity_validator_path: Path,
    observed_on: str,
) -> dict[str, Any]:
    validate_contract(promotion_contract)
    _validate_release_contract(release_contract, promotion_contract)
    candidate_identity_contract_bytes = _validate_identity_inputs(
        promotion_contract, identity_contract_path, identity_validator_path
    )
    if not _candidate_archive_exact(promotion_contract, candidate_archive):
        raise ShadowSourceProvenancePromotionError("OCI candidate archive hash is not exact")
    if not _source_receipt_exact(promotion_contract, source_receipt):
        raise ShadowSourceProvenancePromotionError("source-to-OCI receipt is not exact")
    if not _candidate_loaded_untagged_exact(promotion_contract):
        raise ShadowSourceProvenancePromotionError("preloaded candidate image is not exact and untagged")
    if not _attest_image_identity(observed_on):
        raise ShadowSourceProvenancePromotionError("prior image attestation does not pass")

    prior_release_contract = _prior_release_contract(release_contract, promotion_contract)
    facts = _canonical_facts(prior_release_contract, image_attestation_pass=True)
    if not all(facts.values()):
        raise ShadowSourceProvenancePromotionError("prior canonical control plane is not exact")

    shadow = _json_object(prior_release_contract["required_running_shadow"], "prior running shadow")
    shadow_ids = _line_values(_run(("docker", "ps", "-q", "--filter", "label=" + str(shadow["shadow_label"]))))
    if len(shadow_ids) != 1:
        raise ShadowSourceProvenancePromotionError("prior shadow container is not unique")
    old_container_id = shadow_ids[0]
    old_container = _docker_inspect(old_container_id)
    old_image_id = _image_digest(old_container.get("Image"), "prior running image id")
    previous = _json_object(promotion_contract["previous"], "previous")
    if old_image_id != previous["image_id"]:
        raise ShadowSourceProvenancePromotionError("prior running image id is not exact")
    if _run(("docker", "image", "inspect", "--format", "{{.Id}}", str(previous["image_tag"]))) != old_image_id:
        raise ShadowSourceProvenancePromotionError("prior canonical image tag is not exact")
    old_name = _container_name(old_container)
    old_network = _network_name(old_container)
    rollback_name = old_name + ".source-provenance-rollback"
    if not CONTAINER_NAME_RE.fullmatch(rollback_name):
        raise ShadowSourceProvenancePromotionError("rollback container name is unsafe")
    if subprocess.run(("docker", "inspect", rollback_name), capture_output=True).returncode == 0:
        raise ShadowSourceProvenancePromotionError("rollback container name is unavailable")
    prior_project_ids = set(
        _line_values(_run(("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=abd-shadow-blue")))
    )
    if prior_project_ids != {old_container_id}:
        raise ShadowSourceProvenancePromotionError("prior blue compose project resources are not exact")
    snapshots = _capture_control_files(release_contract)
    return {
        "candidate_identity_contract_bytes": candidate_identity_contract_bytes,
        "old_container_id": old_container_id,
        "old_image_id": old_image_id,
        "old_name": old_name,
        "old_network": old_network,
        "rollback_name": rollback_name,
        "prior_project_ids": prior_project_ids,
        "previous_image_tag": previous["image_tag"],
        "snapshots": snapshots,
        "observed_on": observed_on,
    }


def evaluate_promotion_facts(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    required = {
        "source_archive_exact",
        "source_receipt_exact",
        "candidate_archive_exact",
        "candidate_loaded_untagged_precondition",
        "previous_image_attestation_pass",
        "previous_control_plane_exact",
        "candidate_identity_attestation_pass",
        "candidate_runtime_shape_exact",
        "candidate_control_plane_exact",
        "current_release_blue",
        "exactly_one_shadow",
        "core_runtime_absent",
        "prior_container_removed_after_success",
        "prior_image_retained_untagged",
    }
    if set(facts) != required or not all(isinstance(value, bool) for value in facts.values()):
        raise ShadowSourceProvenancePromotionError("promotion facts must be exact booleans")
    checks = [
        {"id": "SOURCE_ARCHIVE_AND_RECEIPT_EXACT", "passed": facts["source_archive_exact"] and facts["source_receipt_exact"]},
        {"id": "OCI_CANDIDATE_ARCHIVE_EXACT", "passed": facts["candidate_archive_exact"]},
        {"id": "CANDIDATE_LOADED_UNTAGGED_PRECONDITION", "passed": facts["candidate_loaded_untagged_precondition"]},
        {"id": "PRIOR_IMAGE_ATTESTATION_PASS", "passed": facts["previous_image_attestation_pass"]},
        {"id": "PRIOR_CONTROL_PLANE_EXACT", "passed": facts["previous_control_plane_exact"]},
        {"id": "CANDIDATE_IMAGE_AND_DUAL_ENDPOINT_ATTESTATION_PASS", "passed": facts["candidate_identity_attestation_pass"]},
        {"id": "CANDIDATE_RUNTIME_SHAPE_EXACT", "passed": facts["candidate_runtime_shape_exact"]},
        {"id": "CANDIDATE_CONTROL_PLANE_EXACT", "passed": facts["candidate_control_plane_exact"]},
        {"id": "CURRENT_RELEASE_REMAINS_BLUE", "passed": facts["current_release_blue"]},
        {"id": "EXACTLY_ONE_SHADOW_CONTAINER", "passed": facts["exactly_one_shadow"]},
        {"id": "CORE_RUNTIME_ABSENT", "passed": facts["core_runtime_absent"]},
        {"id": "PRIOR_CONTAINER_REMOVED_AFTER_SUCCESS", "passed": facts["prior_container_removed_after_success"]},
        {"id": "PRIOR_IMAGE_RETAINED_UNTAGGED", "passed": facts["prior_image_retained_untagged"]},
    ]
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if not failures else FAIL_STATUS,
        "decision": "SHADOW_SOURCE_PROVENANCE_PROMOTION_PASS" if not failures else "SHADOW_SOURCE_PROVENANCE_PROMOTION_FAIL_CLOSED",
        "promotion_valid": not failures,
        "checks": checks,
        "failure_codes": failures,
        "observed": dict(facts),
    }


def build_receipt(
    contract: Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    observed_on: str,
    contract_sha256: str,
    validator_sha256: str,
    readiness_attempts: int,
) -> dict[str, Any]:
    validate_contract(contract)
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowSourceProvenancePromotionError("observed date is invalid") from exc
    if not isinstance(readiness_attempts, int) or not 1 <= readiness_attempts <= 3:
        raise ShadowSourceProvenancePromotionError("readiness attempts must be in [1, 3]")
    result = evaluate_promotion_facts(contract, facts)
    source = _json_object(contract["source_provenance"], "source_provenance")
    candidate = _json_object(contract["candidate"], "candidate")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": observed_date,
        "contract_sha256": _digest(contract_sha256, "contract_sha256"),
        "validator_sha256": _digest(validator_sha256, "validator_sha256"),
        "promotion_valid": result["promotion_valid"],
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "observed": result["observed"],
        "readiness_attempts": readiness_attempts,
        "source_provenance": {
            "source_commit": source["source_commit"],
            "source_archive_sha256": source["source_archive_sha256"],
            "source_to_oci_receipt_sha256": source["source_to_oci_receipt_sha256"],
            "oci_archive_sha256": source["oci_archive_sha256"],
            "oci_manifest_digest": source["oci_manifest_digest"],
            "oci_config_digest": source["oci_config_digest"],
            "docker_image_id": candidate["docker_image_id"],
        },
        "source_boundary": dict(_json_object(contract["source_boundary"], "source_boundary")),
    }


def _bounded_identity_attestation(observed_on: str) -> int:
    for attempt in range(1, 4):
        if _attest_image_identity(observed_on):
            return attempt
        if attempt < 3:
            time.sleep(1)
    raise ShadowSourceProvenancePromotionError("candidate image attestation did not become ready")


def promote_host(
    promotion_contract_path: Path,
    release_contract_path: Path,
    *,
    identity_contract_path: Path,
    identity_validator_path: Path,
    candidate_archive: Path,
    source_receipt: Path,
    observed_on: str,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ShadowSourceProvenancePromotionError("host promotion must run as root")
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowSourceProvenancePromotionError("observed date is invalid") from exc
    promotion_contract_bytes = _regular_bytes(promotion_contract_path, "promotion contract")
    promotion_contract = load_contract(promotion_contract_path)
    release_contract = load_release_contract(release_contract_path)
    state = _preflight(
        promotion_contract,
        release_contract,
        candidate_archive=candidate_archive,
        source_receipt=source_receipt,
        identity_contract_path=identity_contract_path,
        identity_validator_path=identity_validator_path,
        observed_on=observed_date,
    )

    tag_moved = False
    control_written = False
    project_attempted = False
    old_stopped = False
    old_renamed = False
    diagnostics: dict[str, bool] = {}
    mutation_step = "RENAME_PRIOR_CONTAINER"
    try:
        _run(("docker", "rename", str(state["old_container_id"]), str(state["rollback_name"])))
        old_renamed = True
        mutation_step = "STOP_PRIOR_CONTAINER"
        _run(("docker", "stop", "--time", "2", str(state["rollback_name"])))
        old_stopped = True
        candidate = _json_object(promotion_contract["candidate"], "candidate")
        mutation_step = "MOVE_CANONICAL_IMAGE_TAG"
        _run(("docker", "tag", str(candidate["docker_image_id"]), str(candidate["image_tag"])))
        tag_moved = True
        mutation_step = "VERIFY_CANDIDATE_DIGEST_REFERENCE"
        if _docker_image(str(candidate["image_reference"])).get("Id") != candidate["docker_image_id"]:
            raise ShadowSourceProvenancePromotionError("candidate digest reference is unavailable after canonical tag move")
        control_written = True
        mutation_step = "WRITE_CANDIDATE_CONTROL_FILES"
        _write_candidate_control_files(release_contract, state["snapshots"])
        _atomic_write(HOST_IDENTITY_CONTRACT, state["candidate_identity_contract_bytes"], 0o644, 0, 0)
        project_attempted = True
        mutation_step = "CREATE_AND_START_CANDIDATE_BLUE"
        _create_candidate_blue(release_contract, promotion_contract, state)
        mutation_step = "CANDIDATE_BOUNDED_IDENTITY_ATTESTATION"
        readiness_attempts = _bounded_identity_attestation(observed_date)
        mutation_step = "CANDIDATE_CONTROL_PLANE_ATTESTATION"
        candidate_facts = _canonical_facts(release_contract, image_attestation_pass=True)
        candidate_runtime_shape = _candidate_runtime_shape_exact(
            release_contract, expected_network=str(state["old_network"])
        )
        diagnostics = {"candidate_" + key: value for key, value in candidate_facts.items()}
        diagnostics["candidate_runtime_shape_exact"] = candidate_runtime_shape
        facts = {
            "source_archive_exact": True,
            "source_receipt_exact": True,
            "candidate_archive_exact": True,
            "candidate_loaded_untagged_precondition": True,
            "previous_image_attestation_pass": True,
            "previous_control_plane_exact": True,
            "candidate_identity_attestation_pass": True,
            "candidate_runtime_shape_exact": candidate_runtime_shape,
            "candidate_control_plane_exact": all(candidate_facts.values()),
            "current_release_blue": candidate_facts["current_symlink_blue"],
            "exactly_one_shadow": candidate_facts["shadow_count_exact"],
            "core_runtime_absent": candidate_facts["core_count_zero"],
            "prior_container_removed_after_success": True,
            "prior_image_retained_untagged": _image_is_untagged(str(state["old_image_id"])),
        }
        mutation_step = "PREPARE_SUCCESS_RECEIPT"
        receipt = build_receipt(
            promotion_contract,
            facts,
            observed_on=observed_date,
            contract_sha256=_sha256(promotion_contract_bytes),
            validator_sha256=_sha256(Path(__file__).read_bytes()),
            readiness_attempts=readiness_attempts,
        )
        if receipt["status"] != PASS_STATUS or receipt["promotion_valid"] is not True:
            raise ShadowSourceProvenancePromotionError("candidate promotion facts did not pass before prior removal")
        mutation_step = "REMOVE_PRIOR_CONTAINER_AFTER_SUCCESS"
        _run(("docker", "rm", str(state["rollback_name"])))
        return receipt
    except Exception as exc:
        rollback_restored = _rollback(
            state,
            tag_moved=tag_moved,
            control_written=control_written,
            project_attempted=project_attempted,
            old_stopped=old_stopped,
            old_renamed=old_renamed,
        )
        raise PromotionExecutionError(
            type(exc).__name__,
            failure_step=mutation_step,
            rollback_attempted=True,
            rollback_restored=rollback_restored,
            diagnostics=diagnostics,
        ) from exc


def _failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        observed_date = "INVALID"
    rollback_attempted = isinstance(error, PromotionExecutionError) and error.rollback_attempted
    rollback_restored = isinstance(error, PromotionExecutionError) and error.rollback_restored
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "SHADOW_SOURCE_PROVENANCE_PROMOTION_INPUT_OR_EXECUTION_FAIL_CLOSED",
        "observed_on": observed_date,
        "promotion_valid": False,
        "checks": [],
        "failure_codes": ["SHADOW_SOURCE_PROVENANCE_PROMOTION_FAILED"],
        "error_type": type(error).__name__,
        "failure_step": error.failure_step if isinstance(error, PromotionExecutionError) else "PRECONDITION_OR_INPUT",
        "diagnostics": error.diagnostics if isinstance(error, PromotionExecutionError) else {},
        "rollback_attempted": rollback_attempted,
        "rollback_restored": rollback_restored,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--release-contract", type=Path, required=True)
    parser.add_argument("--identity-contract", type=Path, required=True)
    parser.add_argument("--identity-validator", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--source-to-oci-receipt", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = promote_host(
            args.contract,
            args.release_contract,
            identity_contract_path=args.identity_contract,
            identity_validator_path=args.identity_validator,
            candidate_archive=args.candidate_archive,
            source_receipt=args.source_to_oci_receipt,
            observed_on=args.observed_on,
        )
    except Exception as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
