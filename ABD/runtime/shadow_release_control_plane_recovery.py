#!/usr/bin/env python3
"""Recover one non-secret blue/green control plane from a safe ABD shadow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY"
FAIL_STATUS = "FAIL_SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY"
RECEIPT_TYPE = "ABD_POST_FREEZE_SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY"
SLOT_IDS = ("blue", "green")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ShadowControlPlaneRecoveryError(ValueError):
    """Raised when a recovery input would weaken the shadow-only boundary."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ShadowControlPlaneRecoveryError("%s must be an object" % name)
    return value


def _sha256_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ShadowControlPlaneRecoveryError("%s must be a lowercase sha256" % name)
    return value


def _image_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ShadowControlPlaneRecoveryError("%s must be a sha256 image id" % name)
    _sha256_value(value[7:], name)
    return value


def _image_reference(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("local/abd-runtime@sha256:"):
        raise ShadowControlPlaneRecoveryError("%s must be an ABD digest reference" % name)
    _image_id(value.rsplit("@", 1)[-1], name)
    return value


def _absolute_path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\n" in value or "\x00" in value:
        raise ShadowControlPlaneRecoveryError("%s must be a newline-free absolute path" % name)
    return value


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), "control-plane recovery contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowControlPlaneRecoveryError("control-plane recovery contract is unreadable") from exc


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "contract_id",
        "product_version",
        "status",
        "expected_image_reference",
        "expected_image_id",
        "expected_compose_sha256",
        "source_boundary",
        "canonical_layout",
        "required_running_shadow",
        "rollback",
    }
    if set(contract) != required:
        raise ShadowControlPlaneRecoveryError("control-plane recovery contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise ShadowControlPlaneRecoveryError("control-plane recovery schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-SHADOW-CANONICAL-CONTROL-PLANE-001":
        raise ShadowControlPlaneRecoveryError("control-plane recovery contract id is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise ShadowControlPlaneRecoveryError("control-plane recovery product version is not exact")
    if contract.get("status") != "ONE_SHOT_HOST_LOOPBACK_CANONICAL_CONTROL_PLANE_RECOVERY_ONLY":
        raise ShadowControlPlaneRecoveryError("control-plane recovery must remain one-shot and loopback-only")
    reference = _image_reference(contract.get("expected_image_reference"), "expected_image_reference")
    image_id = _image_id(contract.get("expected_image_id"), "expected_image_id")
    if reference.rsplit("@", 1)[-1] != image_id:
        raise ShadowControlPlaneRecoveryError("expected image reference and id disagree")
    _sha256_value(contract.get("expected_compose_sha256"), "expected_compose_sha256")
    if _object(contract.get("source_boundary"), "source_boundary") != {
        "live_shadow_docker_metadata_read": True,
        "nonsecret_runtime_config_read": True,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise ShadowControlPlaneRecoveryError("source boundary is not exact")
    layout = _object(contract.get("canonical_layout"), "canonical_layout")
    if set(layout) != {
        "release_root",
        "slots",
        "current_release_symlink",
        "active_slot",
        "atomic_switch_method",
        "canonical_config_path",
        "canonical_state_path",
    }:
        raise ShadowControlPlaneRecoveryError("canonical layout field set is not exact")
    if layout.get("release_root") != "/opt/abd/releases" or layout.get("current_release_symlink") != "/opt/abd/current":
        raise ShadowControlPlaneRecoveryError("canonical release paths are not exact")
    if layout.get("active_slot") != "blue" or layout.get("atomic_switch_method") != "CREATE_SIBLING_SYMLINK_THEN_RENAME":
        raise ShadowControlPlaneRecoveryError("canonical active slot or switch method is not exact")
    if layout.get("canonical_config_path") != "/etc/abd/config.json" or layout.get("canonical_state_path") != "/var/lib/abd":
        raise ShadowControlPlaneRecoveryError("canonical config or state path is not exact")
    expected_slots = [
        {
            "id": "blue",
            "release_path": "/opt/abd/releases/blue",
            "runtime_env_path": "/etc/abd/slots/blue.env",
            "log_path": "/var/log/abd/blue",
            "bind_port": 8081,
            "project_name": "abd-shadow-blue",
        },
        {
            "id": "green",
            "release_path": "/opt/abd/releases/green",
            "runtime_env_path": "/etc/abd/slots/green.env",
            "log_path": "/var/log/abd/green",
            "bind_port": 8082,
            "project_name": "abd-shadow-green",
        },
    ]
    if layout.get("slots") != expected_slots:
        raise ShadowControlPlaneRecoveryError("canonical slots are not exact")
    shadow = _object(contract.get("required_running_shadow"), "required_running_shadow")
    if set(shadow) != {
        "shadow_label",
        "core_label",
        "shadow_container_count",
        "core_container_count",
        "user",
        "entrypoint",
        "working_dir",
        "memory_limit_bytes",
        "memory_swap_limit_bytes",
        "cpu_nano_cpus",
        "pids_limit",
        "loopback_port",
        "safe_status",
    }:
        raise ShadowControlPlaneRecoveryError("running shadow field set is not exact")
    if shadow != {
        "shadow_label": "com.linze.abd.runtime-role=candidate-shadow",
        "core_label": "com.linze.abd.phase=S04-P01",
        "shadow_container_count": 1,
        "core_container_count": 0,
        "user": "10001:10001",
        "entrypoint": ["python3", "-m", "abd_runtime.server"],
        "working_dir": "/app",
        "memory_limit_bytes": 536870912,
        "memory_swap_limit_bytes": 536870912,
        "cpu_nano_cpus": 250000000,
        "pids_limit": 128,
        "loopback_port": "127.0.0.1:8081",
        "safe_status": {
            "service": "ABD",
            "version": "0.0.0.1",
            "mode": "SHADOW_READ_ONLY",
            "decision": "NO_RECOMMENDATION_NO_ORDER",
            "ready": True,
            "recommendation_enabled": False,
            "order_submission_enabled": False,
            "market_or_account_connected": False,
            "gmail_or_tab_connected": False,
        },
    }:
        raise ShadowControlPlaneRecoveryError("running shadow contract is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "preserve_original_shadow_until_all_checks_pass": True,
        "restore_original_current_symlink_on_failure": True,
        "remove_only_resources_created_by_this_run_on_failure": True,
        "old_shadow_removal_after_success_only": True,
    }:
        raise ShadowControlPlaneRecoveryError("rollback contract is not exact")


def slot_for(contract: Mapping[str, Any], slot_id: str) -> Mapping[str, Any]:
    validate_contract(contract)
    for slot in _object(contract["canonical_layout"], "canonical_layout")["slots"]:
        if isinstance(slot, dict) and slot.get("id") == slot_id:
            return _object(slot, "slot")
    raise ShadowControlPlaneRecoveryError("unknown canonical slot")


def render_slot_env(contract: Mapping[str, Any], slot_id: str, secret_source: str) -> bytes:
    validate_contract(contract)
    slot = slot_for(contract, slot_id)
    secret = _absolute_path(secret_source, "runtime secret source")
    lines = [
        "ABD_IMAGE=" + str(contract["expected_image_reference"]),
        "ABD_RUNTIME_UID_GID=10001:10001",
        "ABD_CONFIG_FILE=" + str(contract["canonical_layout"]["canonical_config_path"]),
        "ABD_STATE_DIR=" + str(contract["canonical_layout"]["canonical_state_path"]),
        "ABD_SHADOW_LOG_DIR=" + str(slot["log_path"]),
        "ABD_RUNTIME_SECRET_FILE=" + secret,
        "ABD_SHADOW_BIND_PORT=" + str(slot["bind_port"]),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_release_manifest(
    contract: Mapping[str, Any],
    slot_id: str,
    *,
    config_sha256: str,
    slot_env_sha256: str,
) -> dict[str, Any]:
    validate_contract(contract)
    slot = slot_for(contract, slot_id)
    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_SHADOW_CANONICAL_SLOT_MANIFEST",
        "release_id": slot_id,
        "product_version": contract["product_version"],
        "image_reference": contract["expected_image_reference"],
        "image_id": contract["expected_image_id"],
        "compose_sha256": contract["expected_compose_sha256"],
        "config_sha256": _sha256_value(config_sha256, "config_sha256"),
        "slot_env_sha256": _sha256_value(slot_env_sha256, "slot_env_sha256"),
        "runtime_mode": "SHADOW_READ_ONLY",
        "loopback_port": "127.0.0.1:%d" % int(slot["bind_port"]),
        "state_access": "READ_ONLY",
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
    }


def evaluate_control_plane_facts(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    required = {
        "canonical_config_safe",
        "slot_files_exact",
        "current_symlink_blue",
        "shadow_project_blue",
        "shadow_count_exact",
        "core_count_zero",
        "image_attestation_pass",
    }
    if set(facts) != required or not all(isinstance(value, bool) for value in facts.values()):
        raise ShadowControlPlaneRecoveryError("control-plane facts must be exact booleans")
    checks = [
        {"id": "CANONICAL_CONFIG_SAFE", "passed": facts["canonical_config_safe"]},
        {"id": "BLUE_GREEN_SLOT_FILES_EXACT", "passed": facts["slot_files_exact"]},
        {"id": "CURRENT_RELEASE_SYMLINK_BLUE", "passed": facts["current_symlink_blue"]},
        {"id": "BLUE_SHADOW_COMPOSE_PROJECT_EXACT", "passed": facts["shadow_project_blue"]},
        {"id": "EXACTLY_ONE_SHADOW_CONTAINER", "passed": facts["shadow_count_exact"]},
        {"id": "CORE_RUNTIME_ABSENT", "passed": facts["core_count_zero"]},
        {"id": "IMAGE_AND_DUAL_ENDPOINT_ATTESTATION_PASS", "passed": facts["image_attestation_pass"]},
    ]
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if not failures else FAIL_STATUS,
        "decision": "SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY_PASS" if not failures else "SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY_FAIL_CLOSED",
        "recovery_valid": not failures,
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
        observation_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowControlPlaneRecoveryError("observed date is invalid") from exc
    if not isinstance(readiness_attempts, int) or not 1 <= readiness_attempts <= 3:
        raise ShadowControlPlaneRecoveryError("readiness attempts must be in [1, 3]")
    result = evaluate_control_plane_facts(contract, facts)
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": observation_date,
        "contract_sha256": _sha256_value(contract_sha256, "contract_sha256"),
        "validator_sha256": _sha256_value(validator_sha256, "validator_sha256"),
        "recovery_valid": result["recovery_valid"],
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "observed": result["observed"],
        "readiness_attempts": readiness_attempts,
        "source_boundary": dict(_object(contract["source_boundary"], "source_boundary")),
    }


def _run(arguments: Sequence[str]) -> str:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _line_values(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _docker_inspect(identifier: str) -> Mapping[str, Any]:
    try:
        value = json.loads(_run(("docker", "inspect", identifier)))
    except (json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise ShadowControlPlaneRecoveryError("Docker inspect is unavailable") from exc
    if not isinstance(value, list) or len(value) != 1:
        raise ShadowControlPlaneRecoveryError("Docker inspect result is malformed")
    return _object(value[0], "Docker inspect result")


def _mounts_by_destination(container: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    mounts = container.get("Mounts")
    if not isinstance(mounts, list):
        raise ShadowControlPlaneRecoveryError("Docker mounts are malformed")
    result: dict[str, Mapping[str, Any]] = {}
    for mount in mounts:
        item = _object(mount, "Docker mount")
        destination = item.get("Destination")
        if not isinstance(destination, str) or destination in result:
            raise ShadowControlPlaneRecoveryError("Docker mount destination is malformed")
        result[destination] = item
    return result


def _safe_config(path: Path) -> bool:
    try:
        value = _object(json.loads(path.read_text(encoding="utf-8")), "runtime config")
        runtime = _object(value.get("runtime"), "runtime config runtime")
        network = _object(value.get("network"), "runtime config network")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowControlPlaneRecoveryError):
        return False
    return (
        value.get("product_version") == "0.0.0.1"
        and value.get("activation_requested") is False
        and runtime.get("order_submission_enabled") is False
        and network.get("public_business_inbound_enabled") is False
    )


def _slot_path(contract: Mapping[str, Any], slot_id: str, key: str) -> Path:
    value = slot_for(contract, slot_id).get(key)
    return Path(_absolute_path(value, "slot " + key))


def _atomic_write(path: Path, data: bytes, mode: int, uid: int, gid: int) -> None:
    temporary = path.with_name(path.name + ".next-control-plane")
    if os.path.lexists(temporary):
        raise ShadowControlPlaneRecoveryError("recovery temporary path already exists")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.chown(temporary, uid, gid)
        os.replace(temporary, path)
    except Exception:
        if os.path.lexists(temporary):
            os.unlink(temporary)
        raise


def _make_directory(path: Path, mode: int, uid: int, gid: int) -> None:
    path.mkdir(mode=mode)
    os.chmod(path, mode)
    os.chown(path, uid, gid)


def _attest_image_identity(observed_on: str) -> bool:
    attester = Path("/usr/local/lib/abd/shadow_runtime_image_identity_attestation.py")
    contract = Path("/usr/local/lib/abd/shadow_runtime_image_identity_attestation_contract.json")
    if not attester.is_file() or not contract.is_file() or attester.is_symlink() or contract.is_symlink():
        return False
    completed = subprocess.run(
        (str(attester), "--contract", str(contract), "--observed-on", observed_on),
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        value = _object(json.loads(completed.stdout), "image attestation receipt")
    except (json.JSONDecodeError, ShadowControlPlaneRecoveryError):
        return False
    checks = value.get("checks")
    return (
        completed.returncode == 0
        and value.get("status") == "PASS_SHADOW_IMAGE_IDENTITY_ATTESTATION"
        and value.get("attestation_valid") is True
        and isinstance(checks, list)
        and bool(checks)
        and all(isinstance(check, dict) and check.get("passed") is True for check in checks)
    )


def _attest_with_bounded_readiness(observed_on: str) -> int:
    for attempt in range(1, 4):
        if _attest_image_identity(observed_on):
            return attempt
        if attempt < 3:
            time.sleep(1)
    raise ShadowControlPlaneRecoveryError("shadow image identity attestation did not become ready")


def _container_name(container: Mapping[str, Any]) -> str:
    value = container.get("Name")
    if not isinstance(value, str):
        raise ShadowControlPlaneRecoveryError("shadow container name is malformed")
    name = value.removeprefix("/")
    if not CONTAINER_NAME_RE.fullmatch(name):
        raise ShadowControlPlaneRecoveryError("shadow container name is unsafe")
    return name


def _assert_preconditions(
    contract: Mapping[str, Any], compose_source: Path, observed_on: str
) -> tuple[Mapping[str, Any], str, Path, Path]:
    validate_contract(contract)
    if not compose_source.is_file() or compose_source.is_symlink():
        raise ShadowControlPlaneRecoveryError("compose source must be a regular file")
    if _sha256(compose_source.read_bytes()) != contract["expected_compose_sha256"]:
        raise ShadowControlPlaneRecoveryError("compose source hash is not exact")
    shadow = _object(contract["required_running_shadow"], "required_running_shadow")
    shadow_ids = _line_values(_run(("docker", "ps", "-q", "--filter", "label=" + str(shadow["shadow_label"]))))
    core_ids = _line_values(_run(("docker", "ps", "-q", "--filter", "label=" + str(shadow["core_label"]))))
    if len(shadow_ids) != shadow["shadow_container_count"] or len(core_ids) != shadow["core_container_count"]:
        raise ShadowControlPlaneRecoveryError("running container counts are not exact")
    container = _docker_inspect(shadow_ids[0])
    config = _object(container.get("Config"), "shadow config")
    host = _object(container.get("HostConfig"), "shadow host config")
    if config.get("User") != shadow["user"] or config.get("Entrypoint") != shadow["entrypoint"] or config.get("WorkingDir") != shadow["working_dir"]:
        raise ShadowControlPlaneRecoveryError("running shadow identity is not exact")
    if host.get("Memory") != shadow["memory_limit_bytes"] or host.get("MemorySwap") != shadow["memory_swap_limit_bytes"] or host.get("NanoCpus") != shadow["cpu_nano_cpus"] or host.get("PidsLimit") != shadow["pids_limit"]:
        raise ShadowControlPlaneRecoveryError("running shadow resources are not exact")
    if host.get("PortBindings") != {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8081"}]}:
        raise ShadowControlPlaneRecoveryError("running shadow port binding is not exact")
    image_id = _image_id(container.get("Image"), "running image id")
    if image_id != contract["expected_image_id"]:
        raise ShadowControlPlaneRecoveryError("running image id is not exact")
    repo_digests = json.loads(_run(("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id)))
    if repo_digests != [contract["expected_image_reference"]]:
        raise ShadowControlPlaneRecoveryError("running image digest reference is not exact")
    mounts = _mounts_by_destination(container)
    expected_destinations = {"/etc/abd/config.json", "/var/lib/abd", "/var/log/abd", "/run/secrets/abd_runtime"}
    if set(mounts) != expected_destinations:
        raise ShadowControlPlaneRecoveryError("running shadow mount set is not exact")
    config_path = Path(str(contract["canonical_layout"]["canonical_config_path"]))
    state_path = Path(str(contract["canonical_layout"]["canonical_state_path"]))
    if mounts["/etc/abd/config.json"].get("Source") != str(config_path) or mounts["/var/lib/abd"].get("Source") != str(state_path):
        raise ShadowControlPlaneRecoveryError("running shadow canonical mounts are not exact")
    if mounts["/etc/abd/config.json"].get("RW") is not False or mounts["/var/lib/abd"].get("RW") is not False or mounts["/run/secrets/abd_runtime"].get("RW") is not False or mounts["/var/log/abd"].get("RW") is not True:
        raise ShadowControlPlaneRecoveryError("running shadow mount permissions are not exact")
    secret_source = _absolute_path(mounts["/run/secrets/abd_runtime"].get("Source"), "runtime secret source")
    if not secret_source.startswith("/etc/abd/secrets/") or not Path(secret_source).is_file() or Path(secret_source).is_symlink():
        raise ShadowControlPlaneRecoveryError("runtime secret source is not an existing canonical file")
    log_source = _absolute_path(mounts["/var/log/abd"].get("Source"), "shadow log source")
    if not log_source.startswith("/var/log/abd/") or log_source in {"/var/log/abd/blue", "/var/log/abd/green"} or not Path(log_source).is_dir() or Path(log_source).is_symlink():
        raise ShadowControlPlaneRecoveryError("shadow log source is not an existing non-slot canonical directory")
    if not config_path.is_file() or config_path.is_symlink() or not state_path.is_dir() or state_path.is_symlink() or not _safe_config(config_path):
        raise ShadowControlPlaneRecoveryError("canonical non-secret config or state is not safe")
    if _mode(config_path) != 0o640 or config_path.stat().st_gid != 10001:
        raise ShadowControlPlaneRecoveryError("canonical config permissions are not exact")
    layout = _object(contract["canonical_layout"], "canonical_layout")
    current = Path(str(layout["current_release_symlink"]))
    release_root = Path(str(layout["release_root"]))
    if not current.is_symlink() or not release_root.is_dir():
        raise ShadowControlPlaneRecoveryError("existing current release pointer is unavailable")
    current_target = Path(os.path.realpath(current))
    if not current_target.is_dir() or current_target.parent != release_root or current_target.name in SLOT_IDS:
        raise ShadowControlPlaneRecoveryError("existing current release pointer is not a recoverable non-slot release")
    current_compose = current_target / "infra/compose.yml"
    if not current_compose.is_file() or _sha256(current_compose.read_bytes()) != contract["expected_compose_sha256"]:
        raise ShadowControlPlaneRecoveryError("existing current release compose is not exact")
    slots_dir = Path("/etc/abd/slots")
    if os.path.lexists(slots_dir):
        raise ShadowControlPlaneRecoveryError("canonical slot env directory already exists")
    for slot_id in SLOT_IDS:
        if os.path.lexists(_slot_path(contract, slot_id, "release_path")) or os.path.lexists(_slot_path(contract, slot_id, "log_path")):
            raise ShadowControlPlaneRecoveryError("canonical slot resources already exist")
        project_name = str(slot_for(contract, slot_id)["project_name"])
        project_ids = _line_values(
            _run(("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project_name))
        )
        if project_ids:
            raise ShadowControlPlaneRecoveryError("canonical slot compose project already exists")
    if not _attest_image_identity(observed_on):
        raise ShadowControlPlaneRecoveryError("existing shadow image identity attestation does not pass")
    return container, secret_source, current, current_target


def _write_slot_resources(contract: Mapping[str, Any], compose_source: Path, secret_source: str) -> None:
    config_path = Path(str(contract["canonical_layout"]["canonical_config_path"]))
    config_sha256 = _sha256(config_path.read_bytes())
    slots_dir = Path("/etc/abd/slots")
    _make_directory(slots_dir, 0o750, 0, 0)
    for slot_id in SLOT_IDS:
        slot = slot_for(contract, slot_id)
        release_path = Path(str(slot["release_path"]))
        infra_path = release_path / "infra"
        _make_directory(release_path, 0o750, 0, 0)
        _make_directory(infra_path, 0o750, 0, 0)
        _make_directory(Path(str(slot["log_path"])), 0o750, 10001, 10001)
        env_bytes = render_slot_env(contract, slot_id, secret_source)
        _atomic_write(Path(str(slot["runtime_env_path"])), env_bytes, 0o600, 0, 0)
        _atomic_write(infra_path / "compose.yml", compose_source.read_bytes(), 0o644, 0, 0)
        manifest = build_release_manifest(
            contract,
            slot_id,
            config_sha256=config_sha256,
            slot_env_sha256=_sha256(env_bytes),
        )
        _atomic_write(release_path / "release_manifest.json", _json_bytes(manifest), 0o644, 0, 0)


def _remove_created_slot_resources(contract: Mapping[str, Any]) -> None:
    for slot_id in SLOT_IDS:
        release = _slot_path(contract, slot_id, "release_path")
        log_path = _slot_path(contract, slot_id, "log_path")
        if release.exists() and not release.is_symlink():
            shutil.rmtree(release)
        if log_path.exists() and not log_path.is_symlink():
            shutil.rmtree(log_path)
    slots_dir = Path("/etc/abd/slots")
    if slots_dir.exists() and not slots_dir.is_symlink():
        shutil.rmtree(slots_dir)


def _atomic_current_switch(current: Path, target: Path, suffix: str) -> None:
    candidate = current.with_name(current.name + "." + suffix)
    if os.path.lexists(candidate):
        raise ShadowControlPlaneRecoveryError("current release sibling link already exists")
    os.symlink(str(target), candidate)
    os.replace(candidate, current)


def _path_has_exact_metadata(path: Path, *, kind: str, mode: int, uid: int, gid: int) -> bool:
    try:
        if path.is_symlink():
            return False
        if kind == "file" and not path.is_file():
            return False
        if kind == "directory" and not path.is_dir():
            return False
        details = path.stat()
    except OSError:
        return False
    return stat.S_IMODE(details.st_mode) == mode and details.st_uid == uid and details.st_gid == gid


def _slot_env_bytes(contract: Mapping[str, Any], slot_id: str, env_path: Path) -> bytes | None:
    if not _path_has_exact_metadata(env_path, kind="file", mode=0o600, uid=0, gid=0):
        return None
    try:
        env_bytes = env_path.read_bytes()
        lines = env_bytes.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    secret_lines = [line for line in lines if line.startswith("ABD_RUNTIME_SECRET_FILE=")]
    if len(secret_lines) != 1:
        return None
    try:
        secret_source = _absolute_path(secret_lines[0].split("=", 1)[1], "slot runtime secret source")
    except ShadowControlPlaneRecoveryError:
        return None
    secret_path = Path(secret_source)
    if not secret_source.startswith("/etc/abd/secrets/") or not secret_path.is_file() or secret_path.is_symlink():
        return None
    expected = render_slot_env(contract, slot_id, secret_source)
    return env_bytes if env_bytes == expected else None


def _canonical_facts(contract: Mapping[str, Any], image_attestation_pass: bool) -> dict[str, bool]:
    layout = _object(contract["canonical_layout"], "canonical_layout")
    config_path = Path(str(layout["canonical_config_path"]))
    config_safe = config_path.is_file() and not config_path.is_symlink() and _mode(config_path) == 0o640 and config_path.stat().st_gid == 10001 and _safe_config(config_path)
    slot_files_exact = True
    config_sha256 = _sha256(config_path.read_bytes()) if config_safe else ""
    for slot_id in SLOT_IDS:
        slot = slot_for(contract, slot_id)
        release_path = Path(str(slot["release_path"]))
        env_path = Path(str(slot["runtime_env_path"]))
        log_path = Path(str(slot["log_path"]))
        infra_path = release_path / "infra"
        compose_path = release_path / "infra/compose.yml"
        manifest_path = release_path / "release_manifest.json"
        env_bytes = _slot_env_bytes(contract, slot_id, env_path)
        if (
            not _path_has_exact_metadata(release_path, kind="directory", mode=0o750, uid=0, gid=0)
            or not _path_has_exact_metadata(infra_path, kind="directory", mode=0o750, uid=0, gid=0)
            or not _path_has_exact_metadata(log_path, kind="directory", mode=0o750, uid=10001, gid=10001)
            or not _path_has_exact_metadata(compose_path, kind="file", mode=0o644, uid=0, gid=0)
            or not _path_has_exact_metadata(manifest_path, kind="file", mode=0o644, uid=0, gid=0)
            or env_bytes is None
            or _sha256(compose_path.read_bytes()) != contract["expected_compose_sha256"]
        ):
            slot_files_exact = False
            continue
        try:
            manifest = _object(json.loads(manifest_path.read_text(encoding="utf-8")), "slot manifest")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowControlPlaneRecoveryError):
            slot_files_exact = False
            continue
        expected_manifest = build_release_manifest(contract, slot_id, config_sha256=config_sha256, slot_env_sha256=_sha256(env_bytes))
        if manifest != expected_manifest:
            slot_files_exact = False
    current = Path(str(layout["current_release_symlink"]))
    current_blue = current.is_symlink() and Path(os.path.realpath(current)) == _slot_path(contract, "blue", "release_path")
    shadow = _object(contract["required_running_shadow"], "required_running_shadow")
    shadow_ids = _line_values(_run(("docker", "ps", "-q", "--filter", "label=" + str(shadow["shadow_label"]))))
    core_ids = _line_values(_run(("docker", "ps", "-q", "--filter", "label=" + str(shadow["core_label"]))))
    project_blue = False
    if len(shadow_ids) == 1:
        labels = json.loads(_run(("docker", "inspect", "--format", "{{json .Config.Labels}}", shadow_ids[0])))
        project_blue = isinstance(labels, dict) and labels.get("com.docker.compose.project") == "abd-shadow-blue"
    return {
        "canonical_config_safe": config_safe,
        "slot_files_exact": slot_files_exact,
        "current_symlink_blue": current_blue,
        "shadow_project_blue": project_blue,
        "shadow_count_exact": len(shadow_ids) == 1,
        "core_count_zero": len(core_ids) == 0,
        "image_attestation_pass": image_attestation_pass,
    }


def _remove_new_blue_project(contract: Mapping[str, Any]) -> None:
    blue = slot_for(contract, "blue")
    compose_path = Path(str(blue["release_path"])) / "infra/compose.yml"
    env_path = Path(str(blue["runtime_env_path"]))
    if compose_path.is_file() and env_path.is_file():
        subprocess.run(
            (
                "docker",
                "compose",
                "--project-name",
                str(blue["project_name"]),
                "--env-file",
                str(env_path),
                "--file",
                str(compose_path),
                "--profile",
                "shadow",
                "down",
                "--remove-orphans",
            ),
            check=False,
            capture_output=True,
            text=True,
        )
    try:
        identifiers = _line_values(
            _run((
                "docker",
                "ps",
                "-aq",
                "--filter",
                "label=com.docker.compose.project=" + str(blue["project_name"]),
            ))
        )
    except (subprocess.SubprocessError, ShadowControlPlaneRecoveryError):
        identifiers = ()
    for identifier in identifiers:
        subprocess.run(("docker", "rm", "-f", identifier), check=False, capture_output=True, text=True)


def recover_host(contract_path: Path, compose_source: Path, observed_on: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise ShadowControlPlaneRecoveryError("host recovery must run as root")
    contract_bytes = contract_path.read_bytes()
    contract = load_contract(contract_path)
    validate_contract(contract)
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowControlPlaneRecoveryError("observed date is invalid") from exc
    container, secret_source, current, old_target = _assert_preconditions(contract, compose_source, observed_date)
    original_name = _container_name(container)
    rollback_name = original_name + ".shadow-control-plane-rollback"
    if not CONTAINER_NAME_RE.fullmatch(rollback_name) or subprocess.run(("docker", "inspect", rollback_name), capture_output=True).returncode == 0:
        raise ShadowControlPlaneRecoveryError("rollback container name is unavailable")
    old_renamed = False
    current_switched = False
    created_slots = False
    try:
        created_slots = True
        _write_slot_resources(contract, compose_source, secret_source)
        _run(("docker", "rename", str(container.get("Id")), rollback_name))
        old_renamed = True
        _run(("docker", "stop", "--time", "2", rollback_name))
        blue = slot_for(contract, "blue")
        _run(
            (
                "docker",
                "compose",
                "--project-name",
                str(blue["project_name"]),
                "--env-file",
                str(blue["runtime_env_path"]),
                "--file",
                str(Path(str(blue["release_path"])) / "infra/compose.yml"),
                "--profile",
                "shadow",
                "up",
                "--detach",
                "--force-recreate",
                "--no-deps",
                "abd-shadow",
            )
        )
        readiness_attempts = _attest_with_bounded_readiness(observed_date)
        _atomic_current_switch(current, Path(str(blue["release_path"])), "next-shadow-control-plane")
        current_switched = True
        facts = _canonical_facts(contract, image_attestation_pass=True)
        receipt = build_receipt(
            contract,
            facts,
            observed_on=observed_date,
            contract_sha256=_sha256(contract_bytes),
            validator_sha256=_sha256(Path(__file__).read_bytes()),
            readiness_attempts=readiness_attempts,
        )
        if receipt["status"] != PASS_STATUS:
            raise ShadowControlPlaneRecoveryError("canonical control-plane facts did not pass")
        _run(("docker", "rm", rollback_name))
        return receipt
    except Exception:
        if current_switched:
            try:
                _atomic_current_switch(current, old_target, "restore-shadow-control-plane")
            except Exception:
                pass
        if created_slots:
            _remove_new_blue_project(contract)
        if old_renamed:
            subprocess.run(("docker", "start", rollback_name), check=False, capture_output=True)
            subprocess.run(("docker", "rename", rollback_name, original_name), check=False, capture_output=True)
        if created_slots:
            _remove_created_slot_resources(contract)
        raise


def _failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        observed = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        observed = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY_INPUT_OR_EXECUTION_FAIL_CLOSED",
        "observed_on": observed,
        "recovery_valid": False,
        "checks": [],
        "failure_codes": ["SHADOW_CANONICAL_CONTROL_PLANE_RECOVERY_FAILED"],
        "error_type": type(error).__name__,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--compose-source", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = recover_host(args.contract, args.compose_source, args.observed_on)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, subprocess.SubprocessError, ShadowControlPlaneRecoveryError, ValueError) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
