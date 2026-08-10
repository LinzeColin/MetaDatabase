from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from shadow_runtime_provenance import (
    PASS_STATUS,
    ShadowRuntimeProvenanceError,
    build_receipt,
    validate_contract,
    validate_oci_archive,
    verify_source_archive,
)


def _contract() -> dict[str, object]:
    return json.loads((RUNTIME / "shadow_runtime_provenance_contract.json").read_text(encoding="utf-8"))


def _tar_bytes(entries: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, content in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(content))
    return stream.getvalue()


def _oci_archive(tmp_path: Path, *, user: str = "10001:10001") -> tuple[Path, str, str]:
    labels = {
        "org.opencontainers.image.title": "ABD observation runtime",
        "org.opencontainers.image.version": "0.0.0.1",
        "org.opencontainers.image.description": "Non-trading, non-recommendation ABD runtime control plane",
    }
    config = json.dumps(
        {
            "architecture": "amd64",
            "os": "linux",
            "config": {
                "WorkingDir": "/app",
                "User": user,
                "Entrypoint": ["python3", "-m", "abd_runtime.server"],
                "Labels": labels,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    layer = b"synthetic-layer"
    config_digest = hashlib.sha256(config).hexdigest()
    layer_digest = hashlib.sha256(layer).hexdigest()
    manifest = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": "sha256:" + config_digest,
                "size": len(config),
            },
            "layers": [
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar",
                    "digest": "sha256:" + layer_digest,
                    "size": len(layer),
                }
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_digest = hashlib.sha256(manifest).hexdigest()
    index = json.dumps(
        {
            "schemaVersion": 2,
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": "sha256:" + manifest_digest,
                    "size": len(manifest),
                    "platform": {"architecture": "amd64", "os": "linux"},
                }
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload = _tar_bytes(
        {
            "oci-layout": b'{"imageLayoutVersion":"1.0.0"}',
            "index.json": index,
            "blobs/sha256/" + config_digest: config,
            "blobs/sha256/" + layer_digest: layer,
            "blobs/sha256/" + manifest_digest: manifest,
        }
    )
    path = tmp_path / "candidate.oci.tar"
    path.write_bytes(payload)
    return path, "sha256:" + manifest_digest, "sha256:" + config_digest


def test_contract_is_exact_and_pins_the_nonrunning_candidate_boundary() -> None:
    contract = _contract()

    validate_contract(contract)

    assert contract["build"] == {
        "platform": "linux/amd64",
        "base_image_reference": "docker.io/library/python:3.12-alpine@sha256:aa679aa4eed6eb56c1dc6ad3f1b98b7d2d788fd961596779d188fdedad97fb38",
        "base_image_must_already_be_cached": True,
        "pull_allowed": False,
        "network_mode": "none",
        "oci_output_required": True,
        "candidate_loaded_into_docker_store": False,
        "candidate_started": False,
    }
    assert contract["source_boundary"]["external_network_accessed"] is False
    assert contract["source_boundary"]["running_shadow_replaced"] is False


def test_contract_mutation_fails_closed() -> None:
    contract = _contract()
    contract["build"] = {"network_mode": "host"}

    with pytest.raises(ShadowRuntimeProvenanceError):
        validate_contract(contract)


def test_pinned_git_source_archive_is_exactly_verified(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar"
    with archive.open("wb") as output:
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                "b7df8bee5bc91987970ce51d540c68f3fc324f36",
                "--",
                "ABD/runtime/Dockerfile",
                "ABD/runtime/build_oci.sh",
                "ABD/runtime/abd_runtime",
            ],
            cwd=ROOT.parent,
            check=True,
            stdout=output,
        )

    source = verify_source_archive(_contract(), archive)

    assert source["source_commit"] == "b7df8bee5bc91987970ce51d540c68f3fc324f36"
    assert source["source_archive_bytes"] == 20480
    assert source["source_file_count"] == 5
    assert set(source["members"]) == {
        "ABD/runtime/Dockerfile",
        "ABD/runtime/build_oci.sh",
        "ABD/runtime/abd_runtime/__init__.py",
        "ABD/runtime/abd_runtime/observation_evidence.py",
        "ABD/runtime/abd_runtime/server.py",
    }


def test_oci_candidate_layout_and_runtime_config_are_verified(tmp_path: Path) -> None:
    archive, manifest_digest, config_digest = _oci_archive(tmp_path)

    candidate = validate_oci_archive(_contract(), archive)

    assert candidate["candidate_manifest_digest"] == manifest_digest
    assert candidate["candidate_image_id"] == config_digest
    assert candidate["candidate_architecture"] == "amd64"
    assert candidate["candidate_os"] == "linux"
    assert candidate["candidate_layer_count"] == 1


def test_oci_candidate_runtime_mutation_fails_closed(tmp_path: Path) -> None:
    archive, _, _ = _oci_archive(tmp_path, user="0:0")

    with pytest.raises(ShadowRuntimeProvenanceError):
        validate_oci_archive(_contract(), archive)


def test_candidate_receipt_is_redacted_and_never_claims_a_running_image(tmp_path: Path) -> None:
    archive, manifest_digest, config_digest = _oci_archive(tmp_path)
    candidate = validate_oci_archive(_contract(), archive)
    source = {
        "source_commit": "b7df8bee5bc91987970ce51d540c68f3fc324f36",
        "source_archive_sha256": "7ad7b97aeaaec84b747dc3002a849851cba7625fa7e300dd1015ff83d023d6d6",
        "source_archive_bytes": 20480,
        "source_file_count": 5,
        "members": {},
    }

    receipt = build_receipt(
        _contract(),
        source,
        candidate,
        observed_on="2026-08-10",
        contract_sha256="a" * 64,
        validator_sha256="b" * 64,
    )

    assert receipt["status"] == PASS_STATUS
    assert receipt["candidate"]["manifest_digest"] == manifest_digest
    assert receipt["candidate"]["image_id"] == config_digest
    assert receipt["candidate"]["loaded_into_docker_store"] is False
    assert receipt["candidate"]["started"] is False
    assert receipt["source_boundary"]["runtime_secret_content_read"] is False
    assert receipt["source_boundary"]["external_network_accessed"] is False
    assert receipt["source_boundary"]["real_time_soak_waited"] is False


def test_provenance_builder_has_only_nonrunning_no_network_capabilities() -> None:
    source = (RUNTIME / "shadow_runtime_provenance.py").read_text(encoding="utf-8")

    assert '"docker", "image", "inspect"' in source
    assert '"docker", "buildx", "version"' in source
    for forbidden in ("requests", "urllib", "docker load", "docker run", "docker compose", "systemctl", "time.sleep"):
        assert forbidden not in source
    assert "candidate_loaded_into_docker_store\": False" in source
    assert "running_shadow_replaced\": False" in source
    assert "external_network_accessed\": False" in source
