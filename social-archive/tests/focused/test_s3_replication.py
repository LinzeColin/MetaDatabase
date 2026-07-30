import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from social_archive.storage import S3ReplicaStore


def test_s3_replica_key_is_content_addressed():
    store = object.__new__(S3ReplicaStore)
    store.prefix = "primary-objects"
    digest = "a" * 64
    assert store.object_key(digest) == "primary-objects/sha256/aa/aa/" + digest + ".age"


def test_s3_replica_uses_configured_region_and_path_style(monkeypatch):
    captured = {}

    def client(*_args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=client))
    S3ReplicaStore(
        store_id="oci",
        endpoint_url="https://fixture.compat.objectstorage.example",
        bucket="fixture",
        access_key_id="access",
        secret_access_key="secret",
        prefix="primary-objects",
        region_name="ap-singapore-1",
        addressing_style="path",
        s3_compatibility="oci",
    )
    assert captured["region_name"] == "ap-singapore-1"
    assert captured["config"].s3 == {"addressing_style": "path", "payload_signing_enabled": False}
    assert captured["config"].request_checksum_calculation == "when_required"
    assert captured["config"].response_checksum_validation == "when_required"


def test_s3_replica_uploads_only_ciphertext_and_verifies_metadata(tmp_path: Path):
    cipher = tmp_path / "object.age"
    cipher.write_bytes(b"cipher")
    import hashlib
    cipher_sha = hashlib.sha256(b"cipher").hexdigest()
    original_sha = "b" * 64

    class Client:
        def upload_file(self, filename, bucket, key, ExtraArgs):
            assert Path(filename) == cipher
            assert key.endswith(f"{original_sha}.age")
            self.metadata = ExtraArgs["Metadata"]
        def head_object(self, Bucket, Key):
            return {"Metadata": self.metadata, "ETag": '"etag"'}

    store = object.__new__(S3ReplicaStore)
    store.store_id = "r2"
    store.bucket = "private"
    store.prefix = "primary-objects"
    store.client = Client()
    obj = SimpleNamespace(
        original_sha256=original_sha, cipher_sha256=cipher_sha,
        original_byte_size=4, cipher_byte_size=6, path=cipher,
        media_type="application/octet-stream", algorithm="age-x25519",
    )
    key, etag = store.put_encrypted(obj)
    assert key.endswith(".age")
    assert etag == "etag"


def test_s3_replica_readback_verifies_cipher_sha256(tmp_path: Path):
    cipher = b"cipher"
    import hashlib
    expected = hashlib.sha256(cipher).hexdigest()

    class Client:
        def download_file(self, bucket, key, filename):
            assert bucket == "private"
            assert key.endswith(".age")
            Path(filename).write_bytes(cipher)

    store = object.__new__(S3ReplicaStore)
    store.store_id = "r2"
    store.bucket = "private"
    store.client = Client()
    target = tmp_path / "readback.age"
    store.download_verified("primary-objects/object.age", target, expected)
    assert target.read_bytes() == cipher


def test_s3_replica_rejects_mismatched_cipher_readback(tmp_path: Path):
    class Client:
        def download_file(self, _bucket, _key, filename):
            Path(filename).write_bytes(b"wrong-cipher")

    store = object.__new__(S3ReplicaStore)
    store.store_id = "r2"
    store.bucket = "private"
    store.client = Client()
    target = tmp_path / "readback.age"
    with pytest.raises(RuntimeError, match="回读哈希不一致"):
        store.download_verified("primary-objects/object.age", target, "a" * 64)
    assert not target.exists()
    assert not list(tmp_path.glob("*.download"))


def _load_probe(root: Path):
    spec = importlib.util.spec_from_file_location("probe_object_store_test_module", root / "scripts/probe_object_store.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_probe_cli_accepts_taskpack_canary_flag_and_fails_closed_without_recipient(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[2]
    module = _load_probe(root)
    for name in (
        "SOCIAL_ARCHIVE_AGE_RECIPIENT",
        "SOCIAL_ARCHIVE_R2_ENDPOINT",
        "SOCIAL_ARCHIVE_R2_BUCKET",
        "SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE",
        "SOCIAL_ARCHIVE_R2_SECRET_ACCESS_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["probe_object_store.py", "--store", "r2", "--encrypted-canary"])
    assert module.main() == 3
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_ENVIRONMENT"


def test_probe_cli_requires_explicit_canary_confirmation(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[2]
    module = _load_probe(root)
    monkeypatch.setattr(sys, "argv", ["probe_object_store.py", "--store", "r2"])
    assert module.main() == 3
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_USER_CONFIRMATION"
