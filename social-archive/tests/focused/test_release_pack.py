import hashlib
import importlib.util
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from social_archive.models import CaptureRequest


def _load_script(root: Path):
    spec = importlib.util.spec_from_file_location("github_release_backup_test_module", root / "scripts/github_release_backup.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _encrypted(artifact: dict, tmp_path: Path):
    cipher = tmp_path / "shared.age"
    cipher.write_bytes(b"same-age-ciphertext")
    return SimpleNamespace(
        original_sha256=artifact["sha256"],
        cipher_sha256=hashlib.sha256(cipher.read_bytes()).hexdigest(),
        original_byte_size=artifact["byte_size"],
        cipher_byte_size=cipher.stat().st_size,
        path=cipher,
        media_type=artifact["media_type"],
        algorithm="age-x25519",
    )


def _configured(settings):
    return replace(
        settings,
        age_recipient="age1testrecipient",
        github_archive_repository="LinzeColin/Private-Database",
    )


def _set_settings(monkeypatch, module, settings):
    monkeypatch.setattr(module, "Settings", SimpleNamespace(from_env=lambda: settings))


def _enable_github_token(monkeypatch, module):
    monkeypatch.setattr(module, "read_secret", lambda _path: "fixture-gh-token")


def test_release_part_limit_constant_is_under_two_gib():
    root = Path(__file__).resolve().parents[2]
    module = _load_script(root)
    assert module.MAX_PART < 2 * 1024**3


@pytest.mark.parametrize(
    "metadata",
    [
        {"nameWithOwner": "LinzeColin/Private-Database", "isPrivate": False},
        {"nameWithOwner": "someone-else/Private-Database", "isPrivate": True},
        [],
    ],
)
def test_private_repository_check_rejects_public_wrong_or_malformed_metadata(monkeypatch, metadata):
    module = _load_script(Path(__file__).resolve().parents[2])
    monkeypatch.setattr(module, "run", lambda _argv: json.dumps(metadata))
    with pytest.raises(RuntimeError, match="私有归档仓"):
        module.verify_private_repository("LinzeColin/Private-Database")


def test_draft_release_check_rejects_published_or_malformed_metadata(monkeypatch):
    module = _load_script(Path(__file__).resolve().parents[2])
    for metadata in ({"isDraft": False}, {}, []):
        monkeypatch.setattr(module, "run", lambda _argv, response=metadata: json.dumps(response))
        with pytest.raises(RuntimeError, match="Draft"):
            module.verify_draft_release("LinzeColin/Private-Database", "test-tag")


def test_upload_fails_closed_without_recipient_before_runtime_initialization(monkeypatch, tmp_path, capsys):
    root = Path(__file__).resolve().parents[2]
    module = _load_script(root)
    data_root = tmp_path / "blocked-runtime"
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data_root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data_root / "runtime/social-archive.sqlite3"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(data_root / "staging"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(data_root / "private-database"))
    monkeypatch.delenv("SOCIAL_ARCHIVE_AGE_RECIPIENT", raising=False)
    monkeypatch.setattr(sys, "argv", ["github_release_backup.py", "--upload"])

    assert module.main() == 3
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_ENVIRONMENT"
    assert not data_root.exists()


def test_public_repository_is_rejected_before_runtime_or_release(monkeypatch, settings, tmp_path, capsys):
    module = _load_script(Path(__file__).resolve().parents[2])
    data_root = tmp_path / "public-repository-runtime"
    blocked_settings = replace(
        _configured(settings),
        data_root=data_root,
        runtime_db=data_root / "runtime/social-archive.sqlite3",
        staging_root=data_root / "staging",
        private_database_root=data_root / "private-database",
        watch_root=data_root / "import",
        export_root=data_root / "exports",
        cli_output_root=data_root / "vendor-output/cli",
    )
    _set_settings(monkeypatch, module, blocked_settings)
    _enable_github_token(monkeypatch, module)
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        assert argv[:3] == ["gh", "repo", "view"]
        return json.dumps({"nameWithOwner": "LinzeColin/Private-Database", "isPrivate": False})

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/gh")
    monkeypatch.setattr(sys, "argv", ["github_release_backup.py", "--upload"])

    assert module.main() == 3
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_ENVIRONMENT"
    assert calls == [["gh", "repo", "view", "LinzeColin/Private-Database", "--json", "nameWithOwner,isPrivate"]]
    assert not data_root.exists()


def test_mismatched_r2_or_oci_cipher_is_rejected_before_draft_release(service, store, settings, monkeypatch, tmp_path, capsys):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/github-mismatch", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    encrypted = _encrypted(artifact, tmp_path)
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="r2", object_key="r2://object",
        status="verified", verified_sha256="a" * 64,
        original_sha256=artifact["sha256"], encryption="age-x25519",
    )
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="oci", object_key="oci://object",
        status="verified", verified_sha256=encrypted.cipher_sha256,
        original_sha256=artifact["sha256"], encryption="age-x25519",
    )
    module = _load_script(Path(__file__).resolve().parents[2])
    _set_settings(monkeypatch, module, _configured(settings))
    _enable_github_token(monkeypatch, module)

    class FakeEncryptor:
        def __init__(self, **_kwargs):
            pass

        def encrypt(self, _object):
            return encrypted

    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if argv[:3] == ["gh", "repo", "view"]:
            return json.dumps({"nameWithOwner": "LinzeColin/Private-Database", "isPrivate": True})
        raise AssertionError("密文不一致时不得创建、上传或下载 GitHub Release")

    monkeypatch.setattr(module, "AgeEncryptor", FakeEncryptor)
    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/gh")
    monkeypatch.setattr(sys, "argv", ["github_release_backup.py", "--upload"])

    assert module.main() == 4
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "DEGRADED"
    assert report["rejected_object_count"] == 1
    assert calls == [["gh", "repo", "view", "LinzeColin/Private-Database", "--json", "nameWithOwner,isPrivate"]]
    github = store.get_object_replica(artifact["id"], "github")
    assert github and github["status"] == "failed" and github["last_error_code"] == "R2_CIPHER_SHA_MISMATCH"


@pytest.mark.parametrize(
    ("store_id", "field", "value", "expected"),
    [
        ("r2", "status", "failed", "R2_REPLICA_NOT_VERIFIED"),
        ("r2", "original_sha256", "0" * 64, "R2_ORIGINAL_SHA_MISMATCH"),
        ("oci", "encryption", "other-algorithm", "OCI_ENCRYPTION_MISMATCH"),
        ("oci", "verified_sha256", "f" * 64, "OCI_CIPHER_SHA_MISMATCH"),
    ],
)
def test_prior_receipt_gate_requires_each_r2_oci_receipt_field(service, store, tmp_path, store_id, field, value, expected):
    response = service.capture(CaptureRequest(
        platform="generic-web", url=f"https://www.wikipedia.org/github-prior-{expected}", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    encrypted = _encrypted(artifact, tmp_path)
    for candidate_store_id in ("r2", "oci"):
        receipt = {
            "artifact_id": artifact["id"],
            "store_id": candidate_store_id,
            "object_key": f"{candidate_store_id}://object",
            "status": "verified",
            "verified_sha256": encrypted.cipher_sha256,
            "original_sha256": artifact["sha256"],
            "encryption": "age-x25519",
        }
        if candidate_store_id == store_id:
            receipt[field] = value
        store.upsert_object_replica(**receipt)
    module = _load_script(Path(__file__).resolve().parents[2])

    assert module.required_prior_receipt_error(store, artifact["id"], encrypted) == expected


def test_private_draft_release_upload_and_readback_reuses_r2_oci_cipher(service, store, settings, monkeypatch, tmp_path, capsys):
    response = service.capture(CaptureRequest(
        platform="generic-web", url="https://www.wikipedia.org/github-match", requested_levels=["L0", "L1"],
    ))
    artifact = store.get_content(response.content_id)["artifacts"][0]
    encrypted = _encrypted(artifact, tmp_path)
    for store_id in ("r2", "oci"):
        store.upsert_object_replica(
            artifact_id=artifact["id"], store_id=store_id, object_key=f"{store_id}://object",
            status="verified", verified_sha256=encrypted.cipher_sha256,
            original_sha256=artifact["sha256"], encryption="age-x25519",
        )
    store.upsert_object_replica(
        artifact_id=artifact["id"], store_id="github",
        object_key="gh-release://LinzeColin/Social-Archive-Vault/deleted#objects/fixture.age",
        status="failed", verified_sha256=encrypted.cipher_sha256,
        original_sha256=artifact["sha256"], encryption="age-x25519",
        last_error_code="GITHUB_REPOSITORY_OBSOLETE",
    )
    with store.connection() as con:
        con.execute("UPDATE artifact SET status='complete' WHERE id=?", (artifact["id"],))
    module = _load_script(Path(__file__).resolve().parents[2])
    _set_settings(monkeypatch, module, _configured(settings))
    _enable_github_token(monkeypatch, module)

    class FakeEncryptor:
        def __init__(self, **_kwargs):
            pass

        def encrypt(self, _object):
            return encrypted

    remote_assets = tmp_path / "remote-assets"
    remote_assets.mkdir()
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if argv[:3] == ["gh", "repo", "view"]:
            return json.dumps({"nameWithOwner": "LinzeColin/Private-Database", "isPrivate": True})
        if argv[:3] == ["gh", "release", "create"]:
            assert "--draft" in argv
            return ""
        if argv[:3] == ["gh", "release", "view"]:
            return json.dumps({"isDraft": True})
        if argv[:3] == ["gh", "release", "upload"]:
            for asset in argv[4:argv.index("--repo")]:
                shutil.copyfile(asset, remote_assets / Path(asset).name)
            return ""
        if argv[:3] == ["gh", "release", "download"]:
            destination = Path(argv[argv.index("--dir") + 1])
            destination.mkdir(parents=True, exist_ok=True)
            for asset in remote_assets.iterdir():
                shutil.copyfile(asset, destination / asset.name)
            return ""
        raise AssertionError(f"unexpected gh command: {argv}")

    monkeypatch.setattr(module, "AgeEncryptor", FakeEncryptor)
    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/gh")
    monkeypatch.setattr(sys, "argv", ["github_release_backup.py", "--upload"])

    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["completion"]["all_three_verified"] == 1
    assert any(command[:3] == ["gh", "release", "create"] and "--draft" in command for command in calls)
    assert any(command[:3] == ["gh", "release", "upload"] for command in calls)
    assert any(command[:3] == ["gh", "release", "download"] for command in calls)
    github = store.get_object_replica(artifact["id"], "github")
    assert github and github["status"] == "verified" and github["verified_sha256"] == encrypted.cipher_sha256
    assert store.get_content(response.content_id)["artifacts"][0]["status"] == "complete"


def test_upload_requires_configured_github_token_before_runtime_or_provider_calls(monkeypatch, settings, tmp_path, capsys):
    module = _load_script(Path(__file__).resolve().parents[2])
    data_root = tmp_path / "missing-token-runtime"
    blocked_settings = replace(
        _configured(settings),
        data_root=data_root,
        runtime_db=data_root / "runtime/social-archive.sqlite3",
        staging_root=data_root / "staging",
        private_database_root=data_root / "private-database",
        watch_root=data_root / "import",
        export_root=data_root / "exports",
        cli_output_root=data_root / "vendor-output/cli",
        github_token_file=str(tmp_path / "missing-gh-token"),
    )
    _set_settings(monkeypatch, module, blocked_settings)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/gh")
    monkeypatch.setattr(module, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不得调用 gh")))
    monkeypatch.setattr(sys, "argv", ["github_release_backup.py", "--upload"])

    assert module.main() == 3
    assert json.loads(capsys.readouterr().out)["message"] == "缺少 GitHub 私有归档 token 文件"
    assert not data_root.exists()


def test_downloaded_pack_rejects_tampered_cipher_part(tmp_path):
    module = _load_script(Path(__file__).resolve().parents[2])
    cipher = tmp_path / "cipher.age"
    cipher.write_bytes(b"original-cipher")
    encrypted = SimpleNamespace(
        original_sha256="a" * 64,
        cipher_sha256=hashlib.sha256(cipher.read_bytes()).hexdigest(),
        cipher_byte_size=cipher.stat().st_size,
        path=cipher,
        algorithm="age-x25519",
    )
    parts, _manifest_path, manifest = module.create_release_pack([({"id": "artifact-1"}, encrypted)], tmp_path / "pack", "test")
    download = tmp_path / "download"
    download.mkdir()
    for part in parts:
        shutil.copyfile(part, download / part.name)
    (download / parts[0].name).write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="资产回读失败"):
        module.verify_downloaded_pack(download, manifest)
