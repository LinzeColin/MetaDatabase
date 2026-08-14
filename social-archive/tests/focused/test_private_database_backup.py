from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from social_archive.encryption import EncryptedObject
from social_archive.models import CaptureRequest
from social_archive.private_facts import PRIVATE_DATABASE_EVENT, completed_content_facts


def _load_script(root: Path):
    spec = importlib.util.spec_from_file_location("private_database_backup_test_module", root / "scripts/backup.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _set_settings(monkeypatch, module, settings):
    monkeypatch.setattr(module, "Settings", SimpleNamespace(from_env=lambda: settings))


def _delivered_complete_fact(service, store):
    response = service.capture(CaptureRequest(
        platform="generic-web",
        url="https://www.wikipedia.org/private-backup",
        relation_type="saved",
        requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for store_id in ("r2", "oci", "github"):
        store.upsert_object_replica(
            artifact_id=artifact["id"],
            store_id=store_id,
            object_key=f"{store_id}://private-backup",
            status="verified",
            verified_sha256="e" * 64,
            original_sha256=artifact["sha256"],
            encryption="age-x25519",
        )
    fact = completed_content_facts(store)[0]
    event = store.ensure_outbox_event(
        event_type=PRIVATE_DATABASE_EVENT,
        aggregate_id=response.content_id,
        payload=fact,
    )
    store.mark_outbox_delivered(event["id"])
    return fact


def _configured(settings):
    return replace(settings, age_recipient="age1testrecipient")


def _fake_encryptor(tmp_path):
    class FakeEncryptor:
        def __init__(self, *, recipient, root, **_kwargs):
            assert recipient == "age1testrecipient"
            self.root = root
            self.root.mkdir(parents=True, exist_ok=True)

        @property
        def recipient_fingerprint(self):
            return "fixture-recipient"

        def encrypt(self, obj):
            path = self.root / "fixture.age"
            path.write_bytes(b"fixture-age-cipher:" + obj.path.read_bytes())
            return EncryptedObject(
                original_sha256=obj.sha256,
                cipher_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                original_byte_size=obj.byte_size,
                cipher_byte_size=path.stat().st_size,
                path=path,
                media_type=obj.media_type,
            )

    return FakeEncryptor


def test_backup_remote_receipt_binds_original_cipher_and_algorithm(monkeypatch, tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    cipher = tmp_path / "bundle.age"
    cipher.write_bytes(b"fixture ciphertext")
    encrypted = EncryptedObject(
        original_sha256="a" * 64,
        cipher_sha256=hashlib.sha256(cipher.read_bytes()).hexdigest(),
        original_byte_size=17,
        cipher_byte_size=cipher.stat().st_size,
        path=cipher,
        media_type="application/gzip",
    )
    uploaded: dict[str, object] = {}

    class FakeClient:
        def upload_file(self, source, bucket, key, ExtraArgs):
            uploaded.update({
                "bytes": Path(source).read_bytes(),
                "bucket": bucket,
                "key": key,
                "metadata": ExtraArgs["Metadata"],
                "storage_class": ExtraArgs["StorageClass"],
            })

        def head_object(self, **_kwargs):
            return {"Metadata": uploaded["metadata"], "ETag": '"fixture-etag"'}

        def download_file(self, _bucket, _key, target):
            Path(target).write_bytes(uploaded["bytes"])

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: FakeClient()))
    result = module._upload_and_verify(
        {"endpoint": "https://fixture", "bucket": "fixture", "access": "a", "secret": "b"},
        cipher,
        "backups/private-database/fixture.age",
        encrypted,
        tmp_path / "readback" / "cipher.age",
    )

    assert uploaded["metadata"] == {
        "original-sha256": encrypted.original_sha256,
        "cipher-sha256": encrypted.cipher_sha256,
        "encryption": "age-x25519",
    }
    assert uploaded["storage_class"] == "STANDARD"
    assert result["status"] == "verified"
    assert result["cipher_sha256"] == encrypted.cipher_sha256
    assert not list((tmp_path / "readback").glob("*"))


def test_recovery_descriptor_is_hash_verified_and_contains_no_fact_payload(monkeypatch):
    module = _load_script(Path(__file__).resolve().parents[2])
    uploaded: dict[str, object] = {}

    class Body:
        def read(self):
            return uploaded["body"]

    class FakeClient:
        def put_object(self, **kwargs):
            uploaded.update({
                "body": kwargs["Body"],
                "metadata": kwargs["Metadata"],
                "key": kwargs["Key"],
                "storage_class": kwargs["StorageClass"],
            })

        def head_object(self, **_kwargs):
            return {"Metadata": uploaded["metadata"]}

        def get_object(self, **_kwargs):
            return {"Body": Body()}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *_args, **_kwargs: FakeClient()))
    descriptor = {
        "schema_version": "1.0",
        "kind": "social_archive.private_database_recovery_descriptor",
        "remote_key": "backups/private-database/fixture/object.age",
        "original_sha256": "a" * 64,
        "cipher_sha256": "b" * 64,
        "encryption": "age-x25519",
        "fact_count": 1,
        "receipts": {},
    }
    result = module._upload_recovery_descriptor_and_verify(
        {"endpoint": "https://fixture", "bucket": "fixture", "access": "a", "secret": "b"},
        descriptor,
        "backups/private-database/fixture/recovery.json",
    )

    payload = json.loads(uploaded["body"])
    assert result["status"] == "verified"
    assert uploaded["key"].endswith("/recovery.json")
    assert uploaded["storage_class"] == "STANDARD"
    assert "facts" not in payload and "body" not in payload and "ciphertext" not in payload


def test_backup_missing_recipient_fails_before_runtime_or_local_private_copy(monkeypatch, settings, tmp_path, capsys):
    module = _load_script(Path(__file__).resolve().parents[2])
    data_root = tmp_path / "blocked-runtime"
    blocked_settings = replace(
        settings,
        data_root=data_root,
        runtime_db=data_root / "runtime/social-archive.sqlite3",
        staging_root=data_root / "staging",
        private_database_root=data_root / "private-database",
        watch_root=data_root / "import",
        export_root=data_root / "exports",
        cli_output_root=data_root / "vendor-output/cli",
        age_recipient=None,
    )
    _set_settings(monkeypatch, module, blocked_settings)
    monkeypatch.setattr(sys, "argv", ["backup.py", "--once"])

    assert module.main() == 3
    report = json.loads(capsys.readouterr().out)
    assert report["error_code"] == "AGE_RECIPIENT_MISSING"
    assert not data_root.exists()
    assert not blocked_settings.private_database_root.exists()


def test_backup_uses_only_api_delivered_facts_and_mirrors_r2_then_oci(monkeypatch, service, store, settings, tmp_path, capsys):
    fact = _delivered_complete_fact(service, store)
    module = _load_script(Path(__file__).resolve().parents[2])
    _set_settings(monkeypatch, module, _configured(settings))
    monkeypatch.setattr(module, "AgeEncryptor", _fake_encryptor(tmp_path))
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fixture/age")
    monkeypatch.setattr(module, "_s3_config", lambda store_id: {"id": store_id, "endpoint": "https://fixture", "bucket": "fixture", "access": "a", "secret": "b"})
    calls: list[tuple[str, str, str]] = []
    descriptor_calls: list[tuple[str, str, dict]] = []

    def fake_upload(config, ciphertext, key, encrypted, _readback):
        calls.append((config["id"], key, encrypted.cipher_sha256))
        assert ciphertext.is_file()
        assert key.startswith("backups/private-database/")
        return {
            "status": "verified",
            "object_key": key,
            "original_sha256": encrypted.original_sha256,
            "cipher_sha256": encrypted.cipher_sha256,
            "encryption": encrypted.algorithm,
        }

    monkeypatch.setattr(module, "_upload_and_verify", fake_upload)

    def fake_descriptor(config, descriptor, key):
        descriptor_calls.append((config["id"], key, descriptor))
        assert "facts" not in descriptor and "ciphertext" not in descriptor
        return {"status": "verified", "object_key": key, "sha256": "d" * 64}

    monkeypatch.setattr(module, "_upload_recovery_descriptor_and_verify", fake_descriptor)
    output = tmp_path / "cold-backup"
    monkeypatch.setattr(sys, "argv", ["backup.py", "--once", "--output", str(output)])

    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert [item[0] for item in calls] == ["r2", "oci"]
    assert calls[0][1:] == calls[1][1:]
    assert [item[0] for item in descriptor_calls] == ["r2", "oci"]
    assert descriptor_calls[0][1] == descriptor_calls[1][1] == calls[0][1].rsplit("/", 1)[0] + "/recovery.json"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "Private-Database API-synchronized canonical facts"
    assert manifest["fact_count"] == 1
    assert manifest["fact_sha256s"]
    assert manifest["recovery_descriptor"]["receipts"]["r2"]["status"] == "verified"
    assert fact["content"]["id"]
    assert not settings.private_database_root.exists()


def test_r2_failure_still_attempts_the_offsite_copy_without_claiming_a_cold_backup(monkeypatch, service, store, settings, tmp_path, capsys):
    _delivered_complete_fact(service, store)
    module = _load_script(Path(__file__).resolve().parents[2])
    _set_settings(monkeypatch, module, _configured(settings))
    monkeypatch.setattr(module, "AgeEncryptor", _fake_encryptor(tmp_path))
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fixture/age")
    monkeypatch.setattr(module, "_s3_config", lambda store_id: {"id": store_id, "endpoint": "https://fixture", "bucket": "fixture", "access": "a", "secret": "b"})
    calls: list[str] = []

    def fail_r2_only(config, *_args):
        calls.append(config["id"])
        if config["id"] == "r2":
            raise RuntimeError("r2 unavailable")
        return {"status": "verified", "object_key": "fixture", "cipher_sha256": "fixture"}

    monkeypatch.setattr(module, "_upload_and_verify", fail_r2_only)
    output = tmp_path / "r2-failure"
    monkeypatch.setattr(sys, "argv", ["backup.py", "--once", "--output", str(output)])

    assert module.main() == 4
    report = json.loads(capsys.readouterr().out)
    # Not claiming a cold backup is the job of the overall verdict, not of
    # skipping the upload. Chaining them meant an R2 outage took the offsite
    # copy from two copies to zero, precisely when it is most needed. The
    # frozen v0.0.0.6 pack iterates both stores independently.
    assert report["status"] == "DEGRADED"
    assert calls == ["r2", "oci"], "the offsite copy must be attempted even when the primary fails"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["receipts"]["r2"]["status"] == "failed"
    assert manifest["receipts"]["oci"]["status"] == "verified"


def test_backup_refuses_completed_but_not_api_acknowledged_facts(monkeypatch, service, store, settings, capsys):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/not-yet-synced", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for store_id in ("r2", "oci", "github"):
        store.upsert_object_replica(
            artifact_id=artifact["id"], store_id=store_id, object_key=f"{store_id}://not-synced",
            status="verified", verified_sha256="f" * 64, original_sha256=artifact["sha256"], encryption="age-x25519",
        )
    module = _load_script(Path(__file__).resolve().parents[2])
    _set_settings(monkeypatch, module, _configured(settings))
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fixture/age")
    monkeypatch.setattr(module, "_s3_config", lambda _store_id: {"endpoint": "https://fixture", "bucket": "fixture", "access": "a", "secret": "b"})
    monkeypatch.setattr(sys, "argv", ["backup.py", "--once"])

    assert module.main() == 3
    report = json.loads(capsys.readouterr().out)
    assert report["error_code"] == "PRIVATE_DATABASE_SYNC_PREREQUISITE"
