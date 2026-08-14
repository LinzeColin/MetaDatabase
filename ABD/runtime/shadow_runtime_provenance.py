#!/usr/bin/env python3
"""Build and attest one non-running ABD shadow OCI candidate from a pinned source tar."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping


PASS_STATUS = "PASS_SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE"
FAIL_STATUS = "FAIL_SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE"
RECEIPT_TYPE = "ABD_POST_FREEZE_SHADOW_SOURCE_TO_OCI_CANDIDATE"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OCI_BLOB_RE = re.compile(r"^blobs/sha256/([0-9a-f]{64})$")


class ShadowRuntimeProvenanceError(ValueError):
    """Raised when the pinned source-to-OCI candidate boundary is malformed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ShadowRuntimeProvenanceError("%s must be an object" % name)
    return value


def _sha256_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ShadowRuntimeProvenanceError("%s must be a lowercase sha256" % name)
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ShadowRuntimeProvenanceError("%s must be a sha256 digest" % name)
    _sha256_value(value[7:], name)
    return value


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ShadowRuntimeProvenanceError("%s must be a positive integer" % name)
    return value


def _source_files() -> list[dict[str, object]]:
    return [
        {
            "path": "ABD/runtime/Dockerfile",
            "sha256": "070ecdcbcc793688fd0705023727b792e15a0990df10d98f26c2c924eadbd4fa",
            "bytes": 651,
        },
        {
            "path": "ABD/runtime/abd_runtime/__init__.py",
            "sha256": "c51bef940aa5d988af7d7ab25377eaaa53250f1713708b4e302be4ad608c2155",
            "bytes": 365,
        },
        {
            "path": "ABD/runtime/abd_runtime/observation_evidence.py",
            "sha256": "095035ab3f8e38da84cf253e634a9e98d3852413b2b8f8f558fe60b0ff09d317",
            "bytes": 2181,
        },
        {
            "path": "ABD/runtime/abd_runtime/server.py",
            "sha256": "38e8afc40650a1eee8cd7596dd8575ed0221114058620ec75b98ba0dcf184d73",
            "bytes": 7647,
        },
        {
            "path": "ABD/runtime/build_oci.sh",
            "sha256": "749569f373742b5ee02aec7b3ce4307d14c9e2359651817e82755e42f17f3a0f",
            "bytes": 1271,
        },
    ]


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), "shadow runtime provenance contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowRuntimeProvenanceError("shadow runtime provenance contract is unreadable") from exc


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "contract_id",
        "product_version",
        "status",
        "source_snapshot",
        "build",
        "expected_oci_runtime_config",
        "evidence",
        "source_boundary",
        "rollback",
    }
    if set(contract) != required:
        raise ShadowRuntimeProvenanceError("shadow runtime provenance contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise ShadowRuntimeProvenanceError("shadow runtime provenance schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-SHADOW-SOURCE-TO-OCI-001":
        raise ShadowRuntimeProvenanceError("shadow runtime provenance contract id is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise ShadowRuntimeProvenanceError("shadow runtime provenance product version is not exact")
    if contract.get("status") != "ONE_SHOT_NONRUNNING_SOURCE_TO_OCI_CANDIDATE_ONLY":
        raise ShadowRuntimeProvenanceError("shadow runtime provenance must remain a non-running candidate")
    source_snapshot = _object(contract.get("source_snapshot"), "source_snapshot")
    if source_snapshot != {
        "git_commit": "b7df8bee5bc91987970ce51d540c68f3fc324f36",
        "archive_format": "GIT_ARCHIVE_TAR",
        "archive_sha256": "7ad7b97aeaaec84b747dc3002a849851cba7625fa7e300dd1015ff83d023d6d6",
        "archive_bytes": 20480,
        "files": _source_files(),
    }:
        raise ShadowRuntimeProvenanceError("source snapshot is not exact")
    build = _object(contract.get("build"), "build")
    if build != {
        "platform": "linux/amd64",
        "base_image_reference": "docker.io/library/python:3.12-alpine@sha256:aa679aa4eed6eb56c1dc6ad3f1b98b7d2d788fd961596779d188fdedad97fb38",
        "base_image_must_already_be_cached": True,
        "pull_allowed": False,
        "network_mode": "none",
        "oci_output_required": True,
        "candidate_loaded_into_docker_store": False,
        "candidate_started": False,
    }:
        raise ShadowRuntimeProvenanceError("build boundary is not exact")
    config = _object(contract.get("expected_oci_runtime_config"), "expected_oci_runtime_config")
    if config != {
        "architecture": "amd64",
        "os": "linux",
        "working_dir": "/app",
        "user": "10001:10001",
        "entrypoint": ["python3", "-m", "abd_runtime.server"],
        "labels": {
            "org.opencontainers.image.title": "ABD observation runtime",
            "org.opencontainers.image.version": "0.0.0.1",
            "org.opencontainers.image.description": "Non-trading, non-recommendation ABD runtime control plane",
        },
    }:
        raise ShadowRuntimeProvenanceError("OCI runtime config contract is not exact")
    if _object(contract.get("evidence"), "evidence") != {
        "archive_source_tar": True,
        "archive_oci_tar": True,
        "archive_redacted_receipt": True,
        "private_database_area": "Private-MetaDatabase",
        "readback_sha256_required": True,
    }:
        raise ShadowRuntimeProvenanceError("evidence boundary is not exact")
    if _object(contract.get("source_boundary"), "source_boundary") != {
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "cloudflare_changed": False,
        "core_runtime_started": False,
        "running_shadow_replaced": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise ShadowRuntimeProvenanceError("source boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "on_failure": "REMOVE_ONLY_THIS_RUNS_NONRUNNING_BUILD_DIRECTORY_AND_OCI_OUTPUT",
        "keep_existing_running_shadow_unchanged": True,
        "keep_current_release_symlink_unchanged": True,
        "do_not_load_or_start_candidate": True,
    }:
        raise ShadowRuntimeProvenanceError("rollback boundary is not exact")


def _member_bytes(archive: tarfile.TarFile) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for member in archive.getmembers():
        name = member.name
        if not name or name.startswith("/") or ".." in Path(name).parts:
            raise ShadowRuntimeProvenanceError("archive member path is unsafe")
        if member.isdir():
            continue
        if not member.isfile() or name in files:
            raise ShadowRuntimeProvenanceError("archive member type is not accepted")
        source = archive.extractfile(member)
        if source is None:
            raise ShadowRuntimeProvenanceError("archive member is unreadable")
        files[name] = source.read()
    return files


def verify_source_archive(contract: Mapping[str, Any], source_archive: Path) -> dict[str, Any]:
    """Validate the exact, non-secret source tar before extraction or build."""

    validate_contract(contract)
    if not source_archive.is_file() or source_archive.is_symlink():
        raise ShadowRuntimeProvenanceError("source archive must be a regular file")
    try:
        raw = source_archive.read_bytes()
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
        members = _member_bytes(archive)
    except (OSError, tarfile.TarError) as exc:
        raise ShadowRuntimeProvenanceError("source archive is unreadable") from exc
    source = _object(contract["source_snapshot"], "source_snapshot")
    if len(raw) != source["archive_bytes"] or _sha256(raw) != source["archive_sha256"]:
        raise ShadowRuntimeProvenanceError("source archive identity is not exact")
    expected = {str(item["path"]): item for item in source["files"]}
    if set(members) != set(expected):
        raise ShadowRuntimeProvenanceError("source archive file set is not exact")
    for path, item in expected.items():
        data = members[path]
        if len(data) != item["bytes"] or _sha256(data) != item["sha256"]:
            raise ShadowRuntimeProvenanceError("source archive file hash is not exact")
    return {
        "source_commit": source["git_commit"],
        "source_archive_sha256": source["archive_sha256"],
        "source_archive_bytes": source["archive_bytes"],
        "source_file_count": len(expected),
        "members": members,
    }


def _blob_bytes(members: Mapping[str, bytes], digest: str, size: object, name: str) -> bytes:
    value = _digest(digest, name)
    expected_size = _positive_int(size, name + " size")
    path = "blobs/sha256/" + value[7:]
    data = members.get(path)
    if data is None or len(data) != expected_size or _sha256(data) != value[7:]:
        raise ShadowRuntimeProvenanceError(name + " blob identity is not exact")
    return data


def validate_oci_archive(contract: Mapping[str, Any], oci_archive: Path) -> dict[str, Any]:
    """Validate one un-loaded OCI candidate against the runtime-image contract."""

    validate_contract(contract)
    if not oci_archive.is_file() or oci_archive.is_symlink():
        raise ShadowRuntimeProvenanceError("OCI archive must be a regular file")
    try:
        raw = oci_archive.read_bytes()
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
        members = _member_bytes(archive)
    except (OSError, tarfile.TarError) as exc:
        raise ShadowRuntimeProvenanceError("OCI archive is unreadable") from exc
    if set(name for name in members if name.startswith("blobs/")) != {
        name for name in members if OCI_BLOB_RE.fullmatch(name)
    }:
        raise ShadowRuntimeProvenanceError("OCI archive contains a malformed blob path")
    try:
        layout = _object(json.loads(members["oci-layout"]), "OCI layout")
        index = _object(json.loads(members["index.json"]), "OCI index")
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, ShadowRuntimeProvenanceError) as exc:
        raise ShadowRuntimeProvenanceError("OCI layout or index is malformed") from exc
    if layout != {"imageLayoutVersion": "1.0.0"}:
        raise ShadowRuntimeProvenanceError("OCI layout version is not exact")
    manifests = index.get("manifests")
    if index.get("schemaVersion") != 2 or not isinstance(manifests, list) or len(manifests) != 1:
        raise ShadowRuntimeProvenanceError("OCI index must contain one manifest")
    descriptor = _object(manifests[0], "OCI manifest descriptor")
    if descriptor.get("mediaType") != "application/vnd.oci.image.manifest.v1+json":
        raise ShadowRuntimeProvenanceError("OCI manifest media type is not exact")
    platform = _object(descriptor.get("platform"), "OCI platform")
    if platform != {"architecture": "amd64", "os": "linux"}:
        raise ShadowRuntimeProvenanceError("OCI platform is not exact")
    manifest_raw = _blob_bytes(members, descriptor.get("digest"), descriptor.get("size"), "OCI manifest")
    try:
        manifest = _object(json.loads(manifest_raw), "OCI manifest")
    except (UnicodeDecodeError, json.JSONDecodeError, ShadowRuntimeProvenanceError) as exc:
        raise ShadowRuntimeProvenanceError("OCI manifest is malformed") from exc
    if manifest.get("schemaVersion") != 2 or manifest.get("mediaType") != "application/vnd.oci.image.manifest.v1+json":
        raise ShadowRuntimeProvenanceError("OCI manifest shape is not exact")
    config_descriptor = _object(manifest.get("config"), "OCI config descriptor")
    if config_descriptor.get("mediaType") != "application/vnd.oci.image.config.v1+json":
        raise ShadowRuntimeProvenanceError("OCI config media type is not exact")
    config_raw = _blob_bytes(members, config_descriptor.get("digest"), config_descriptor.get("size"), "OCI config")
    try:
        image_config = _object(json.loads(config_raw), "OCI image config")
        runtime_config = _object(image_config.get("config"), "OCI runtime config")
        labels = _object(runtime_config.get("Labels"), "OCI runtime labels")
    except (UnicodeDecodeError, json.JSONDecodeError, ShadowRuntimeProvenanceError) as exc:
        raise ShadowRuntimeProvenanceError("OCI image config is malformed") from exc
    expected = _object(contract["expected_oci_runtime_config"], "expected_oci_runtime_config")
    if (
        image_config.get("architecture") != expected["architecture"]
        or image_config.get("os") != expected["os"]
        or runtime_config.get("WorkingDir") != expected["working_dir"]
        or runtime_config.get("User") != expected["user"]
        or runtime_config.get("Entrypoint") != expected["entrypoint"]
        or {key: labels.get(key) for key in expected["labels"]} != expected["labels"]
    ):
        raise ShadowRuntimeProvenanceError("OCI runtime configuration is not exact")
    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ShadowRuntimeProvenanceError("OCI manifest must contain layers")
    for layer in layers:
        item = _object(layer, "OCI layer descriptor")
        _blob_bytes(members, item.get("digest"), item.get("size"), "OCI layer")
    return {
        "oci_archive_sha256": _sha256(raw),
        "oci_archive_bytes": len(raw),
        "candidate_manifest_digest": descriptor["digest"],
        "candidate_image_id": config_descriptor["digest"],
        "candidate_architecture": image_config["architecture"],
        "candidate_os": image_config["os"],
        "candidate_layer_count": len(layers),
    }


def build_receipt(
    contract: Mapping[str, Any],
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    observed_on: str,
    contract_sha256: str,
    validator_sha256: str,
) -> dict[str, Any]:
    validate_contract(contract)
    try:
        observation_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowRuntimeProvenanceError("observed date is invalid") from exc
    required_source = {"source_commit", "source_archive_sha256", "source_archive_bytes", "source_file_count", "members"}
    required_candidate = {
        "oci_archive_sha256",
        "oci_archive_bytes",
        "candidate_manifest_digest",
        "candidate_image_id",
        "candidate_architecture",
        "candidate_os",
        "candidate_layer_count",
    }
    if set(source) != required_source or set(candidate) != required_candidate:
        raise ShadowRuntimeProvenanceError("receipt input shape is not exact")
    if not isinstance(source["source_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", source["source_commit"]):
        raise ShadowRuntimeProvenanceError("receipt source commit is malformed")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": PASS_STATUS,
        "decision": "SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE_PASS_NOT_LOADED_OR_STARTED",
        "observed_on": observation_date,
        "contract_sha256": _sha256_value(contract_sha256, "contract_sha256"),
        "validator_sha256": _sha256_value(validator_sha256, "validator_sha256"),
        "source": {
            "git_commit": source["source_commit"],
            "archive_sha256": _sha256_value(source["source_archive_sha256"], "source archive sha256"),
            "archive_bytes": _positive_int(source["source_archive_bytes"], "source archive bytes"),
            "file_count": _positive_int(source["source_file_count"], "source file count"),
        },
        "candidate": {
            "oci_archive_sha256": _sha256_value(candidate["oci_archive_sha256"], "OCI archive sha256"),
            "oci_archive_bytes": _positive_int(candidate["oci_archive_bytes"], "OCI archive bytes"),
            "manifest_digest": _digest(candidate["candidate_manifest_digest"], "candidate manifest digest"),
            "image_id": _digest(candidate["candidate_image_id"], "candidate image id"),
            "architecture": candidate["candidate_architecture"],
            "os": candidate["candidate_os"],
            "layer_count": _positive_int(candidate["candidate_layer_count"], "candidate layer count"),
            "loaded_into_docker_store": False,
            "started": False,
        },
        "checks": [
            {"id": "SOURCE_ARCHIVE_IDENTITY_EXACT", "passed": True},
            {"id": "SOURCE_ARCHIVE_FILE_SET_AND_HASHES_EXACT", "passed": True},
            {"id": "PINNED_BASE_IMAGE_CACHED", "passed": True},
            {"id": "DOCKER_BUILDX_AVAILABLE", "passed": True},
            {"id": "OCI_LAYOUT_AND_PLATFORM_EXACT", "passed": True},
            {"id": "OCI_RUNTIME_CONFIG_EXACT", "passed": True},
            {"id": "CANDIDATE_NOT_LOADED_OR_STARTED", "passed": True},
        ],
        "source_boundary": dict(_object(contract["source_boundary"], "source_boundary")),
    }


def _run(arguments: tuple[str, ...], *, env: Mapping[str, str] | None = None) -> None:
    subprocess.run(arguments, check=True, capture_output=True, text=True, env=dict(env) if env is not None else None)


def _extract_source(members: Mapping[str, bytes], destination: Path) -> None:
    destination.mkdir(mode=0o700)
    for relative, data in members.items():
        target = destination / relative
        if destination not in target.resolve().parents:
            raise ShadowRuntimeProvenanceError("source archive extraction path is unsafe")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(target, 0o700 if target.name == "build_oci.sh" else 0o600)


def build_candidate(contract_path: Path, source_archive: Path, work_dir: Path, observed_on: str) -> dict[str, Any]:
    """Build an OCI tar only; never load, start, or replace a runtime image."""

    if os.geteuid() != 0:
        raise ShadowRuntimeProvenanceError("candidate build must run as root")
    contract_bytes = contract_path.read_bytes()
    contract = load_contract(contract_path)
    validate_contract(contract)
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise ShadowRuntimeProvenanceError("observed date is invalid") from exc
    source = verify_source_archive(contract, source_archive)
    if work_dir.exists() or work_dir.is_symlink() or work_dir.parent == work_dir:
        raise ShadowRuntimeProvenanceError("candidate work directory must be absent")
    output = work_dir / "candidate.oci.tar"
    created = False
    try:
        _run(("docker", "image", "inspect", str(contract["build"]["base_image_reference"])))
        _run(("docker", "buildx", "version"))
        work_dir.mkdir(mode=0o700)
        created = True
        extraction = work_dir / "source"
        _extract_source(source["members"], extraction)
        build_env = {
            "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
            "HOME": "/root",
            "ABD_TARGET_PLATFORM": "linux/amd64",
        }
        _run(("sh", str(extraction / "ABD/runtime/build_oci.sh"), str(output)), env=build_env)
        candidate = validate_oci_archive(contract, output)
        return build_receipt(
            contract,
            source,
            candidate,
            observed_on=observed_date,
            contract_sha256=_sha256(contract_bytes),
            validator_sha256=_sha256(Path(__file__).read_bytes()),
        )
    except Exception:
        if created and work_dir.exists() and not work_dir.is_symlink():
            shutil.rmtree(work_dir)
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
        "decision": "SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE_FAIL_CLOSED",
        "observed_on": observed,
        "candidate_valid": False,
        "checks": [],
        "failure_codes": ["SHADOW_RUNTIME_SOURCE_TO_OCI_CANDIDATE_FAILED"],
        "error_type": type(error).__name__,
        "runtime_secret_content_read": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_candidate(args.contract, args.source_archive, args.work_dir, args.observed_on)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, subprocess.SubprocessError, tarfile.TarError, ShadowRuntimeProvenanceError, ValueError) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
