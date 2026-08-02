from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from social_archive.models import CaptureRequest


def _load_script(root: Path):
    spec = importlib.util.spec_from_file_location("object_recovery_test_module", root / "scripts/restore_object.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _descriptor(module, *, plain: bytes = b"recovery plaintext", cipher: bytes = b"age ciphertext"):
    original_sha = hashlib.sha256(plain).hexdigest()
    cipher_sha = hashlib.sha256(cipher).hexdigest()
    artifact = {"id": "art_canary", "sha256": original_sha, "status": "complete"}
    receipts = [
        {
            "artifact_id": "art_canary",
            "store_id": store_id,
            "object_key": (
                f"gh-release://LinzeColin/Private-Database/social-archive-backup-fixture#objects/{original_sha}.age"
                if store_id == "github"
                else f"primary-objects/sha256/{original_sha[:2]}/{original_sha[2:4]}/{original_sha}.age"
            ),
            "status": "verified",
            "verified_sha256": cipher_sha,
            "original_sha256": original_sha,
            "encryption": "age-x25519",
        }
        for store_id in ("r2", "oci", "github")
    ]
    return module._validated_descriptor(artifact, receipts), plain, cipher


def test_runtime_descriptor_requires_exact_three_receipts(service, store, settings):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/object-recovery-fixture",
        requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    for store_id in ("r2", "oci", "github"):
        store.upsert_object_replica(
            artifact_id=artifact["id"], store_id=store_id,
            object_key=(
                f"gh-release://LinzeColin/Private-Database/fixture#objects/{artifact['sha256']}.age"
                if store_id == "github"
                else f"primary-objects/sha256/{artifact['sha256'][:2]}/{artifact['sha256'][2:4]}/{artifact['sha256']}.age"
            ),
            status="verified", verified_sha256="c" * 64,
            original_sha256=artifact["sha256"], encryption="age-x25519",
        )
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor = module.load_runtime_descriptor(settings.runtime_db, artifact["id"])
    assert descriptor["artifact_id"] == artifact["id"]
    assert descriptor["original_sha256"] == artifact["sha256"]
    assert descriptor["cipher_sha256"] == "c" * 64


def test_descriptor_rejects_mismatched_cipher_receipt(tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, _cipher = _descriptor(module)
    receipts = list(descriptor["replicas"].values())
    receipts[2] = dict(receipts[2], cipher_sha256="d" * 64, verified_sha256="d" * 64)
    with pytest.raises(module.RecoveryFailure, match="密文哈希"):
        module._validated_descriptor(
            {"id": descriptor["artifact_id"], "sha256": descriptor["original_sha256"], "status": "complete"},
            [
                {
                    "artifact_id": row["artifact_id"], "store_id": row["store_id"], "object_key": row["object_key"],
                    "status": "verified", "verified_sha256": row["cipher_sha256"],
                    "original_sha256": row["original_sha256"], "encryption": row["encryption"],
                }
                for row in receipts
            ],
        )


def test_s3_recovery_requires_metadata_and_cipher_hash(monkeypatch, tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)

    class FakeClient:
        def head_object(self, **_kwargs):
            return {"Metadata": {
                "original-sha256": descriptor["original_sha256"],
                "cipher-sha256": descriptor["cipher_sha256"],
                "encryption": "age-x25519",
            }}

        def download_file(self, _bucket, _key, target):
            Path(target).write_bytes(cipher)

    monkeypatch.setattr(module, "create_s3_client", lambda **_kwargs: FakeClient())
    target = tmp_path / "r2.age"
    module.download_s3_ciphertext(
        descriptor, store_id="r2",
        config={"endpoint": "https://fixture", "bucket": "private", "access_key_id": "a", "secret_access_key": "s", "region_name": "auto", "addressing_style": "path", "s3_compatibility": "aws"},
        target=target,
    )
    assert target.read_bytes() == cipher


def test_github_pack_extracts_only_verified_target_ciphertext(tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)
    member = f"objects/{descriptor['original_sha256']}.age"
    pack = tmp_path / "social-archive-objects-fixture.tar"
    source = tmp_path / "cipher.age"
    source.write_bytes(cipher)
    with tarfile.open(pack, "w") as archive:
        archive.add(source, arcname=member, recursive=False)
    manifest = {
        "schema_version": "2.0",
        "encryption": "age-x25519",
        "pack_sha256": hashlib.sha256(pack.read_bytes()).hexdigest(),
        "pack_parts": [{"name": pack.name, "sha256": hashlib.sha256(pack.read_bytes()).hexdigest(), "byte_size": pack.stat().st_size}],
        "objects": [{
            "artifact_id": descriptor["artifact_id"], "original_sha256": descriptor["original_sha256"],
            "cipher_sha256": descriptor["cipher_sha256"], "path": member, "encryption": "age-x25519",
        }],
    }
    (tmp_path / "social-archive-objects-fixture.manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
    target = tmp_path / "downloaded.age"
    module.extract_verified_github_ciphertext(tmp_path, descriptor, target)
    assert target.read_bytes() == cipher


def test_decrypt_and_target_guard_are_hash_checked(tmp_path, settings):
    if not shutil.which("age") or not shutil.which("age-keygen"):
        pytest.skip("age binary is unavailable")
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, plain, _cipher = _descriptor(module)
    identity = tmp_path / "fixture.agekey"
    generated = subprocess.run(["age-keygen", "-o", str(identity)], text=True, capture_output=True, check=True)
    match = re.search(r"Public key:\s*(age1[0-9a-z]+)", generated.stdout + generated.stderr)
    assert match
    ciphertext = tmp_path / "fixture.age"
    plaintext = tmp_path / "fixture.plain"
    subprocess.run(["age", "-r", match.group(1), "-o", str(ciphertext), "-"], input=plain, check=True)
    descriptor["cipher_sha256"] = hashlib.sha256(ciphertext.read_bytes()).hexdigest()
    for receipt in descriptor["replicas"].values():
        receipt["cipher_sha256"] = descriptor["cipher_sha256"]
    module.decrypt_and_verify(ciphertext, identity=str(identity), descriptor=descriptor, plaintext=plaintext)
    assert plaintext.read_bytes() == plain
    with pytest.raises(module.RecoveryFailure, match="运行数据面"):
        module._validated_target(str(settings.data_root / "forbidden"), settings)


def test_systemd_wrapper_is_collected_and_uses_only_store_specific_credentials():
    wrapper = (Path(__file__).resolve().parents[2] / "scripts/restore_object_systemd.sh").read_text(encoding="utf-8")
    assert "systemd-run --wait --collect --pipe" in wrapper
    assert "CREDENTIALS_DIRECTORY" in wrapper
    assert '${args[@]}' not in wrapper
    assert "private_database_token" not in wrapper
    assert "LoadCredential=r2_access_key_id" in wrapper
    assert "LoadCredential=oci_access_key_id" in wrapper
    assert "LoadCredential=github_token" in wrapper
