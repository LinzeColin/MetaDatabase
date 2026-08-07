from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
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


_S3_CONFIG = {"endpoint": "https://fixture", "bucket": "private", "access_key_id": "a",
              "secret_access_key": "s", "region_name": "auto", "addressing_style": "path",
              "s3_compatibility": "aws"}


def _fake_s3(module, monkeypatch, *, metadata, cipher=b"", missing=False):
    class FakeClient:
        def head_object(self, **_kwargs):
            if missing:
                raise RuntimeError("NoSuchKey")
            return {"Metadata": dict(metadata), "ContentLength": len(cipher)}

        def download_file(self, _bucket, _key, target):
            Path(target).write_bytes(cipher)

    monkeypatch.setattr(module, "create_s3_client", lambda **_kwargs: FakeClient())


def test_s3_recovery_refuses_an_object_whose_metadata_disagrees(monkeypatch, tmp_path):
    """**上面那条判据的名字承诺了它没做的事。**（2026-08-07）

    `test_s3_recovery_requires_metadata_and_cipher_hash` 只跑了顺利那一条路。
    把 `raise RecoveryFailure("S3_METADATA_MISMATCH", …)` 整句删掉，
    全套 1227 条照样全绿——**而那一句是「远端这个对象是不是收据说的那个」
    的唯一检查**，它拦的是还原出一个错的或被换过的对象。
    """
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)
    _fake_s3(module, monkeypatch, cipher=cipher, metadata={
        "original-sha256": descriptor["original_sha256"],
        "cipher-sha256": "d" * 64,                     # ← 远端说的密文哈希不是收据里那个
        "encryption": "age-x25519",
    })
    with pytest.raises(module.RecoveryFailure, match="元数据"):
        module.download_s3_ciphertext(descriptor, store_id="r2", config=_S3_CONFIG,
                                      target=tmp_path / "r2.age")
    assert not (tmp_path / "r2.age").exists(), "校验没过却已经写下了文件"


def test_s3_recovery_refuses_an_object_that_is_not_age_encrypted(monkeypatch, tmp_path):
    """**「加密存三份」里的「加密」也得当真。**"""
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)
    _fake_s3(module, monkeypatch, cipher=cipher, metadata={
        "original-sha256": descriptor["original_sha256"],
        "cipher-sha256": descriptor["cipher_sha256"],
        "encryption": "none",
    })
    with pytest.raises(module.RecoveryFailure, match="元数据"):
        module.download_s3_ciphertext(descriptor, store_id="r2", config=_S3_CONFIG,
                                      target=tmp_path / "r2.age")


def test_s3_recovery_refuses_a_download_whose_bytes_do_not_match(monkeypatch, tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)
    _fake_s3(module, monkeypatch, cipher=cipher + b"tampered", metadata={
        "original-sha256": descriptor["original_sha256"],
        "cipher-sha256": descriptor["cipher_sha256"],
        "encryption": "age-x25519",
    })
    with pytest.raises(module.RecoveryFailure, match="密文回读哈希"):
        module.download_s3_ciphertext(descriptor, store_id="r2", config=_S3_CONFIG,
                                      target=tmp_path / "r2.age")
    assert not (tmp_path / "r2.age").exists()


def test_presence_only_answers_without_the_age_key(monkeypatch):
    """**「东西还在吗」不该需要私钥。**（2026-08-07）

    `object_replica` 里那三行 `verified` 是**写入当时**的记录，不代表对象
    今天还在。而在这个之前，唯一的核对入口（--verify-only）整条被 age 私钥
    挡着——于是说明书那句「加密存三份」在生产上没有任何办法当场核实。
    """
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)
    _fake_s3(module, monkeypatch, cipher=cipher, metadata={
        "original-sha256": descriptor["original_sha256"],
        "cipher-sha256": descriptor["cipher_sha256"],
        "encryption": "age-x25519",
    })
    found = module.presence_s3(descriptor, store_id="r2", config=_S3_CONFIG)
    assert found["byte_size"] == len(cipher)
    assert found["encryption"] == "age-x25519"


def test_presence_only_says_so_when_the_object_is_gone(monkeypatch):
    """**副本被清空过一次**（2026-08-04 的 R2），这一条就是为那种情况写的。"""
    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, _cipher = _descriptor(module)
    _fake_s3(module, monkeypatch, missing=True, metadata={})
    with pytest.raises(module.RecoveryFailure, match="找不到这个对象"):
        module.presence_s3(descriptor, store_id="r2", config=_S3_CONFIG)


def test_presence_only_actually_runs_as_a_command(monkeypatch, tmp_path, capsys):
    """**判据要经过被保证的那条路。**（2026-08-07）

    上面几条直接调 `presence_s3`，从没走过 `main()`——于是 `--presence-only`
    漏在「恢复写入必须指定新的空目录」那道闸外面：编译绿、单测绿，
    **而工具在生产上第一次真跑，三个存储全报 RECOVERY_TARGET_MISSING**。

    这个仓记着这一条（「检查不经过被保证之物」），我又栽了一次。
    所以这条判据按**命令行**跑，不按函数跑。
    """
    import json as _json

    module = _load_script(Path(__file__).resolve().parents[2])
    descriptor, _plain, cipher = _descriptor(module)
    _fake_s3(module, monkeypatch, cipher=cipher, metadata={
        "original-sha256": descriptor["original_sha256"],
        "cipher-sha256": descriptor["cipher_sha256"],
        "encryption": "age-x25519",
    })
    monkeypatch.setattr(module, "load_runtime_descriptor", lambda *_a, **_k: descriptor)
    monkeypatch.setattr(module, "_s3_config", lambda _store: dict(_S3_CONFIG))
    monkeypatch.setattr(
        sys, "argv",
        ["restore_object.py", "--artifact-id", descriptor["artifact_id"],
         "--from-store", "r2", "--presence-only"])

    code = module.main()
    printed = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0, printed
    assert printed["status"] == "PASS", printed
    assert printed["mode"] == "presence_only"
    assert printed["found"]["byte_size"] == len(cipher)
    # **不许把「还在」说成「能还原」。**
    assert "--verify-only" in printed["what_this_does_not_prove_zh"]


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
