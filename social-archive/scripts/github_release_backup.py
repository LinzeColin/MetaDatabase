from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.encryption import AgeEncryptor, EncryptedObject
from social_archive.storage import StoredObject
from social_archive.utils import read_secret, sha256_file, utcnow

MAX_PART = 1800 * 1024 * 1024


def run(argv: Sequence[str], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(list(argv), text=True, capture_output=True, check=False, env=env)
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "命令失败")[-2000:])
    return completed.stdout


def github_cli_environment(token_file: str | None) -> dict[str, str] | None:
    """Build a scoped gh environment from the configured secret file only."""
    token = read_secret(token_file)
    if not token:
        return None
    environment = dict(os.environ)
    environment["GH_TOKEN"] = token
    return environment


def _repository_name_is_valid(repository: str) -> bool:
    owner_and_name = repository.split("/")
    return len(owner_and_name) == 2 and all(part and part == part.strip() for part in owner_and_name)


def verify_private_repository(repository: str, *, env: dict[str, str] | None = None) -> None:
    """Fail closed before any draft or asset can be created in a wrong repository."""
    try:
        metadata = json.loads(run([
            "gh", "repo", "view", repository, "--json", "nameWithOwner,isPrivate",
        ], env=env))
    except (RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("无法验证 GitHub 私有归档仓") from exc
    if not isinstance(metadata, dict) or metadata.get("nameWithOwner") != repository or metadata.get("isPrivate") is not True:
        raise RuntimeError("GitHub 私有归档仓身份错误或不是私有仓")


def verify_draft_release(repository: str, tag: str, *, env: dict[str, str] | None = None) -> None:
    """Require the just-created Release to remain a draft before asset upload."""
    try:
        metadata = json.loads(run([
            "gh", "release", "view", tag, "--repo", repository, "--json", "isDraft",
        ], env=env))
    except (RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("无法验证 GitHub Draft Release") from exc
    if not isinstance(metadata, dict) or metadata.get("isDraft") is not True:
        raise RuntimeError("GitHub Release 不是 Draft，已拒绝上传")


def _replica_receipt_error(
    store: RuntimeStore,
    artifact_id: str,
    store_id: str,
    encrypted: EncryptedObject,
) -> str | None:
    receipt = store.get_object_replica(artifact_id, store_id)
    prefix = store_id.upper()
    if not receipt:
        return f"{prefix}_REPLICA_MISSING"
    if receipt.get("status") != "verified":
        return f"{prefix}_REPLICA_NOT_VERIFIED"
    if receipt.get("original_sha256") != encrypted.original_sha256:
        return f"{prefix}_ORIGINAL_SHA_MISMATCH"
    if receipt.get("encryption") != encrypted.algorithm:
        return f"{prefix}_ENCRYPTION_MISMATCH"
    if receipt.get("verified_sha256") != encrypted.cipher_sha256:
        return f"{prefix}_CIPHER_SHA_MISMATCH"
    return None


def required_prior_receipt_error(
    store: RuntimeStore,
    artifact_id: str,
    encrypted: EncryptedObject,
) -> str | None:
    """GitHub may only receive the exact age ciphertext already verified twice."""
    for store_id in ("r2", "oci"):
        error = _replica_receipt_error(store, artifact_id, store_id, encrypted)
        if error:
            return error
    return None


def split_file(path: Path) -> list[Path]:
    if path.stat().st_size <= MAX_PART:
        return [path]
    parts: list[Path] = []
    with path.open("rb") as source:
        index = 0
        while True:
            chunk = source.read(MAX_PART)
            if not chunk:
                break
            part = path.with_name(f"{path.name}.part-{index:04d}")
            part.write_bytes(chunk)
            parts.append(part)
            index += 1
    path.unlink()
    return parts


def join_parts(parts: list[Path], target: Path) -> None:
    with target.open("wb") as output:
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def create_release_pack(objects: list[tuple[dict[str, Any], EncryptedObject]], outdir: Path, stamp: str) -> tuple[list[Path], Path, dict[str, Any]]:
    outdir.mkdir(parents=True, exist_ok=True)
    pack = outdir / f"social-archive-objects-{stamp}.tar"
    object_manifest = []
    with tarfile.open(pack, "w") as archive:
        for row, encrypted in sorted(objects, key=lambda item: item[1].original_sha256):
            arcname = f"objects/{encrypted.original_sha256}.age"
            archive.add(encrypted.path, arcname=arcname, recursive=False)
            object_manifest.append({
                "artifact_id": row["id"],
                "original_sha256": encrypted.original_sha256,
                "cipher_sha256": encrypted.cipher_sha256,
                "cipher_byte_size": encrypted.cipher_byte_size,
                "path": arcname,
                "encryption": encrypted.algorithm,
            })
    pack_sha = sha256_file(pack)
    parts = split_file(pack)
    manifest = {
        "schema_version": "2.0",
        "created_at": utcnow(),
        "encryption": "age-x25519",
        "pack_sha256": pack_sha,
        "pack_parts": [{"name": item.name, "sha256": sha256_file(item), "byte_size": item.stat().st_size} for item in parts],
        "objects": object_manifest,
    }
    manifest_path = outdir / f"social-archive-objects-{stamp}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return parts, manifest_path, manifest


def verify_downloaded_pack(download_dir: Path, manifest: dict[str, Any]) -> None:
    parts = [download_dir / item["name"] for item in manifest["pack_parts"]]
    for path, expected in zip(parts, manifest["pack_parts"], strict=True):
        if not path.is_file() or sha256_file(path) != expected["sha256"]:
            raise RuntimeError(f"GitHub Release 资产回读失败：{expected['name']}")
    assembled = download_dir / "assembled.tar"
    if len(parts) == 1:
        shutil.copyfile(parts[0], assembled)
    else:
        join_parts(parts, assembled)
    if sha256_file(assembled) != manifest["pack_sha256"]:
        raise RuntimeError("GitHub Release 合并包哈希不一致")
    with tarfile.open(assembled, "r") as archive:
        members = {member.name: member for member in archive.getmembers()}
        for item in manifest["objects"]:
            member = members.get(item["path"])
            if not member or not member.isfile():
                raise RuntimeError(f"GitHub Release 缺少密文：{item['path']}")
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError(f"无法读取密文：{item['path']}")
            import hashlib
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            if digest.hexdigest() != item["cipher_sha256"]:
                raise RuntimeError(f"GitHub Release 密文哈希不一致：{item['path']}")


def _record_failed_github_replica(
    store: RuntimeStore,
    row: dict[str, Any],
    *,
    error_code: str,
    encrypted: EncryptedObject | None = None,
) -> None:
    store.upsert_object_replica(
        artifact_id=row["id"],
        store_id="github",
        object_key=(
            f"gh-release://blocked#objects/{encrypted.original_sha256}.age"
            if encrypted is not None
            else "unavailable"
        ),
        status="failed",
        verified_sha256=encrypted.cipher_sha256 if encrypted is not None else None,
        original_sha256=encrypted.original_sha256 if encrypted is not None else None,
        encryption=encrypted.algorithm if encrypted is not None else None,
        last_error_code=error_code,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.getenv("SOCIAL_ARCHIVE_GITHUB_ARCHIVE_REPOSITORY"))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    repository = (args.repository or settings.github_archive_repository or "").strip()
    if not settings.age_recipient:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 SOCIAL_ARCHIVE_AGE_RECIPIENT；禁止明文备份"}, ensure_ascii=False))
        return 3
    if not _repository_name_is_valid(repository):
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 GitHub 私有归档仓库"}, ensure_ascii=False))
        return 3
    github_env: dict[str, str] | None = None
    if args.upload:
        if not shutil.which("gh"):
            print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 gh CLI"}, ensure_ascii=False))
            return 3
        github_env = github_cli_environment(settings.github_token_file)
        if github_env is None:
            print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 GitHub 私有归档 token 文件"}, ensure_ascii=False))
            return 3
        try:
            verify_private_repository(repository, env=github_env)
        except RuntimeError:
            print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "GitHub 私有归档仓验证失败"}, ensure_ascii=False))
            return 3

    settings.ensure_directories()
    store = RuntimeStore(settings.runtime_db)
    store.initialize()

    rows = store.list_artifacts_for_replication("github", limit=max(1, min(args.limit, 5000)), requires_verified_store="oci")
    if not rows:
        print(json.dumps({"status": "PASS", "message": "没有待复制对象", "object_count": 0}, ensure_ascii=False))
        return 0
    encryptor = AgeEncryptor(recipient=settings.age_recipient, root=settings.staging_root / "encrypted")
    encrypted_rows: list[tuple[dict[str, Any], EncryptedObject]] = []
    rejected = 0
    for row in rows:
        source = Path(str(row.get("local_path") or ""))
        if not source.is_file() or source.is_symlink():
            _record_failed_github_replica(store, row, error_code="LOCAL_OBJECT_MISSING")
            rejected += 1
            continue
        try:
            encrypted = encryptor.encrypt(StoredObject(str(row["sha256"]), int(row["byte_size"]), source, row.get("media_type")))
        except Exception as exc:  # noqa: BLE001 - boundary emits a bounded receipt
            _record_failed_github_replica(store, row, error_code=exc.__class__.__name__)
            rejected += 1
            continue
        prerequisite_error = required_prior_receipt_error(store, row["id"], encrypted)
        if prerequisite_error:
            _record_failed_github_replica(store, row, error_code=prerequisite_error, encrypted=encrypted)
            rejected += 1
            continue
        encrypted_rows.append((row, encrypted))
    if not encrypted_rows:
        print(json.dumps({"status": "DEGRADED", "message": "待复制对象未通过三副本一致性门", "rejected_object_count": rejected}, ensure_ascii=False))
        return 4

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    outdir = settings.data_root / "github-release-packs" / stamp
    parts, manifest_path, manifest = create_release_pack(encrypted_rows, outdir, stamp)
    report: dict[str, Any] = {
        "status": "READY" if not args.upload else "CHECKING",
        "repository": repository,
        "object_count": len(encrypted_rows),
        "manifest": str(manifest_path),
        "part_count": len(parts),
        "pack_sha256": manifest["pack_sha256"],
        "rejected_object_count": rejected,
    }
    if args.dry_run and not args.upload:
        print(json.dumps(report, ensure_ascii=False))
        return 0
    if not args.upload:
        print(json.dumps(report, ensure_ascii=False))
        return 0
    tag = f"social-archive-backup-{stamp}"
    assets = [str(manifest_path), *[str(path) for path in parts]]
    try:
        run(["gh", "release", "create", tag, "--repo", repository, "--draft", "--title", tag, "--notes", "Social Archive age-encrypted object backup"], env=github_env)
        verify_draft_release(repository, tag, env=github_env)
        run(["gh", "release", "upload", tag, *assets, "--repo", repository], env=github_env)
        with tempfile.TemporaryDirectory(prefix="social-archive-gh-readback-") as tmp:
            download_dir = Path(tmp)
            run(["gh", "release", "download", tag, "--repo", repository, "--dir", str(download_dir)], env=github_env)
            downloaded_manifest_path = download_dir / manifest_path.name
            if not downloaded_manifest_path.is_file() or sha256_file(downloaded_manifest_path) != sha256_file(manifest_path):
                raise RuntimeError("GitHub Release manifest 回读哈希不一致")
            downloaded_manifest = json.loads(downloaded_manifest_path.read_text(encoding="utf-8"))
            if downloaded_manifest != manifest:
                raise RuntimeError("GitHub Release manifest 内容不一致")
            verify_downloaded_pack(download_dir, manifest)
    except Exception as exc:  # noqa: BLE001 - preserve retryable failed receipts without publishing success
        for row, encrypted in encrypted_rows:
            _record_failed_github_replica(store, row, error_code=exc.__class__.__name__, encrypted=encrypted)
        report.update({"status": "DEGRADED", "message": "GitHub Draft Release 上传或回读失败", "error_code": exc.__class__.__name__})
        print(json.dumps(report, ensure_ascii=False))
        return 4

    for row, encrypted in encrypted_rows:
        store.upsert_object_replica(
            artifact_id=row["id"], store_id="github",
            object_key=f"gh-release://{repository}/{tag}#objects/{encrypted.original_sha256}.age",
            status="verified", verified_sha256=encrypted.cipher_sha256,
            original_sha256=encrypted.original_sha256, encryption=encrypted.algorithm,
        )
    report.update({
        "status": "PASS" if rejected == 0 else "DEGRADED",
        "tag": tag,
        "completion": store.replication_completion(),
    })
    print(json.dumps(report, ensure_ascii=False))
    return 0 if rejected == 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
