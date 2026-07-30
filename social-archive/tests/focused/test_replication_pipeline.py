import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from social_archive.models import CaptureRequest


def _load_script(root: Path):
    spec = importlib.util.spec_from_file_location("replicate_objects_test_module", root / "scripts/replicate_objects.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_oci_queue_requires_verified_r2(service, store, settings):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/r", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    assert store.list_artifacts_for_replication("oci", requires_verified_store="r2") == []
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="r2", object_key="primary-objects/x.age",
        status="verified", verified_sha256="c" * 64, original_sha256=artifact["sha256"], encryption="age-x25519",
    )
    rows = store.list_artifacts_for_replication("oci", requires_verified_store="r2")
    assert [row["id"] for row in rows] == [artifact["id"]]


def test_replication_script_records_cipher_readback(service, store, settings, monkeypatch, tmp_path):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/s", requested_levels=["L0", "L1"],
    ))
    root = Path(__file__).resolve().parents[2]
    module = _load_script(root)

    class FakeEncrypted:
        original_sha256 = "a" * 64
        cipher_sha256 = "b" * 64
        algorithm = "age-x25519"
        path = tmp_path / "cipher.age"
        path.write_bytes(b"cipher")

    class FakeEncryptor:
        def __init__(self, **kwargs):
            pass
        def encrypt(self, obj):
            value = FakeEncrypted()
            value.original_sha256 = obj.sha256
            return value

    class FakeRemote:
        def __init__(self, **config):
            self.store_id = config["store_id"]
        def object_key(self, digest):
            return f"primary-objects/sha256/{digest}.age"
        def put_encrypted(self, obj):
            return self.object_key(obj.original_sha256), "etag"
        def download_verified(self, key, target, expected):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"cipher")

    monkeypatch.setattr(module, "AgeEncryptor", FakeEncryptor)
    monkeypatch.setattr(module, "S3ReplicaStore", FakeRemote)
    monkeypatch.setattr(module, "_store_config", lambda store_id: ({
        "store_id": store_id, "endpoint_url": "https://storage.invalid.local", "bucket": "b",
        "access_key_id": "a", "secret_access_key": "s", "prefix": "primary-objects",
    }, None))
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(settings.data_root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(settings.runtime_db))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(settings.staging_root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(settings.private_database_root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_AGE_RECIPIENT", "age1test")
    monkeypatch.setattr(sys, "argv", ["replicate_objects.py", "--store", "r2"])
    assert module.main() == 0
    summary = store.replica_summary()
    assert any(row["store_id"] == "r2" and row["status"] == "verified" for row in summary)


def test_oci_replication_rejects_r2_cipher_mismatch_before_remote_call(service, store, monkeypatch, tmp_path):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/oci-mismatch", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="r2", object_key="primary-objects/r2.age",
        status="verified", verified_sha256="a" * 64, original_sha256=artifact["sha256"], encryption="age-x25519",
    )
    module = _load_script(Path(__file__).resolve().parents[2])
    cipher = tmp_path / "cipher.age"
    cipher.write_bytes(b"cipher")
    encrypted = SimpleNamespace(
        original_sha256=artifact["sha256"], cipher_sha256="b" * 64,
        original_byte_size=artifact["byte_size"], cipher_byte_size=cipher.stat().st_size,
        path=cipher, media_type=artifact["media_type"], algorithm="age-x25519",
    )

    class Encryptor:
        def encrypt(self, _obj):
            return encrypted

    class Remote:
        store_id = "oci"

        def object_key(self, digest):
            return f"primary-objects/{digest}.age"

        def put_encrypted(self, _obj):
            raise AssertionError("R2 密文 receipt 不一致时不得调用 OCI")

    result = module._replicate_one(
        store, Remote(), Encryptor(), artifact, readback_root=tmp_path / "readback", dry_run=False,
    )
    assert result == {"artifact_id": artifact["id"], "status": "FAILED", "error_code": "R2_CIPHER_SHA_MISMATCH"}
    oci = store.get_object_replica(artifact["id"], "oci")
    assert oci and oci["status"] == "failed" and oci["last_error_code"] == "R2_CIPHER_SHA_MISMATCH"


def test_oci_replication_requires_and_reuses_identical_r2_cipher(service, store, monkeypatch, tmp_path):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/oci-match", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    module = _load_script(Path(__file__).resolve().parents[2])
    cipher = tmp_path / "cipher.age"
    cipher.write_bytes(b"cipher")
    cipher_sha = "b" * 64
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="r2", object_key="primary-objects/r2.age",
        status="verified", verified_sha256=cipher_sha, original_sha256=artifact["sha256"], encryption="age-x25519",
    )
    encrypted = SimpleNamespace(
        original_sha256=artifact["sha256"], cipher_sha256=cipher_sha,
        original_byte_size=artifact["byte_size"], cipher_byte_size=cipher.stat().st_size,
        path=cipher, media_type=artifact["media_type"], algorithm="age-x25519",
    )

    class Encryptor:
        def encrypt(self, _obj):
            return encrypted

    class Remote:
        store_id = "oci"

        def __init__(self):
            self.uploads = []

        def object_key(self, digest):
            return f"primary-objects/{digest}.age"

        def put_encrypted(self, obj):
            self.uploads.append(obj.cipher_sha256)
            return self.object_key(obj.original_sha256), "oci-etag"

        def download_verified(self, _key, target, expected):
            assert expected == cipher_sha
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"cipher")

    remote = Remote()
    result = module._replicate_one(
        store, remote, Encryptor(), artifact, readback_root=tmp_path / "readback", dry_run=False,
    )
    assert result["status"] == "PASS"
    assert remote.uploads == [cipher_sha]
    oci = store.get_object_replica(artifact["id"], "oci")
    assert oci and oci["status"] == "verified" and oci["verified_sha256"] == cipher_sha


def test_replication_once_flag_fails_closed_before_runtime_initialization(monkeypatch, tmp_path, capsys):
    root = Path(__file__).resolve().parents[2]
    module = _load_script(root)
    data_root = tmp_path / "runtime"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data_root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data_root / "runtime.db"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(data_root / "staging"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(data_root / "private"))
    monkeypatch.delenv("SOCIAL_ARCHIVE_AGE_RECIPIENT", raising=False)
    monkeypatch.setattr(sys, "argv", ["replicate_objects.py", "--once"])
    assert module.main() == 3
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_ENVIRONMENT"
    assert not data_root.exists()
