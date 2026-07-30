from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from social_archive.recovery import RecoveryBundleError


def _load_script(root: Path):
    spec = importlib.util.spec_from_file_location("recovery_restore_test_module", root / "scripts/restore.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _descriptor(cipher_sha: str) -> dict:
    receipt = {
        "status": "verified",
        "object_key": "backups/private-database/fixture/object.age",
        "original_sha256": "a" * 64,
        "cipher_sha256": cipher_sha,
        "encryption": "age-x25519",
    }
    return {
        "schema_version": "1.0",
        "kind": "social_archive.private_database_recovery_descriptor",
        "remote_key": receipt["object_key"],
        "original_sha256": receipt["original_sha256"],
        "cipher_sha256": cipher_sha,
        "encryption": "age-x25519",
        "receipts": {"r2": receipt, "oci": dict(receipt)},
    }


def test_remote_descriptor_selects_latest_and_downloads_only_verified_cipher(monkeypatch, tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    ciphertext = b"fixture remote age ciphertext"
    cipher_sha = hashlib.sha256(ciphertext).hexdigest()
    descriptor = _descriptor(cipher_sha)

    class Body:
        def read(self):
            return json.dumps(descriptor).encode("utf-8")

    class FakeClient:
        def list_objects_v2(self, **_kwargs):
            return {"Contents": [{"Key": "backups/private-database/20260730/recovery.json"}]}

        def get_object(self, **_kwargs):
            return {"Body": Body()}

        def download_file(self, _bucket, key, target):
            assert key == descriptor["remote_key"]
            Path(target).write_bytes(ciphertext)

    monkeypatch.setattr(module, "_s3_client", lambda _config: FakeClient())
    config = {"endpoint": "https://fixture", "bucket": "fixture", "access": "a", "secret": "b"}
    selected = module._latest_remote_descriptor(config)
    _manifest, _ciphertext, _original_sha, returned_sha, remote_key = module._validated_manifest(
        selected, require_local_ciphertext=False
    )
    assert returned_sha == cipher_sha and remote_key == descriptor["remote_key"]
    target = tmp_path / "cipher.age"
    module._download_remote_ciphertext(config, remote_key, returned_sha, target)
    assert target.read_bytes() == ciphertext


def test_remote_restore_rejects_descriptor_with_missing_receipt():
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor = _descriptor("b" * 64)
    descriptor["receipts"].pop("oci")
    with pytest.raises(RecoveryBundleError, match="oci"):
        module._validated_manifest(descriptor, require_local_ciphertext=False)
