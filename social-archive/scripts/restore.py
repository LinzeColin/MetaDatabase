from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from social_archive.config import Settings
from social_archive.recovery import (
    SECRET_PATH_FALLBACKS,
    RecoveryBundleError,
    load_recovery_bundle,
    resolve_secret_path,
)
from social_archive.storage import create_s3_client
from social_archive.utils import read_secret, sha256_file


def safe_members(tf: tarfile.TarFile):
    for member in tf.getmembers():
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise ValueError(f"不安全的归档成员：{member.name}")
        yield member


def _latest_manifest(settings: Settings) -> Path | None:
    manifests = sorted((settings.data_root / "backups/private-database").glob("*/manifest.json"), reverse=True)
    return manifests[0] if manifests else None


def _decrypt(ciphertext: Path, identity: str, output: Path) -> None:
    binary = shutil.which("age")
    if not binary:
        raise RuntimeError("缺少 age 命令")
    result = subprocess.run([binary, "-d", "-i", identity, "-o", str(output), str(ciphertext)], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "age 解密失败")[-1000:])


def _s3_config(store_id: str) -> dict[str, str] | None:
    prefix = f"SOCIAL_ARCHIVE_{store_id.upper()}"
    endpoint = os.getenv(f"{prefix}_ENDPOINT", "").strip()
    bucket = os.getenv(f"{prefix}_BUCKET", "").strip()
    # 主机上这几个路径指的是容器里的挂载点，见 recovery.resolve_secret_path。
    access = read_secret(resolve_secret_path(os.getenv(f"{prefix}_ACCESS_KEY_ID_FILE")))
    secret = read_secret(resolve_secret_path(os.getenv(f"{prefix}_SECRET_ACCESS_KEY_FILE")))
    region_name = os.getenv(f"{prefix}_REGION", "auto").strip() or "auto"
    addressing_style = os.getenv(f"{prefix}_ADDRESSING_STYLE", "path").strip() or "path"
    s3_compatibility = os.getenv(f"{prefix}_S3_COMPATIBILITY", "aws").strip().lower() or "aws"
    if not all((endpoint, bucket, access, secret)):
        return None
    if addressing_style not in {"auto", "path", "virtual"}:
        return None
    if s3_compatibility not in {"aws", "oci"}:
        return None
    return {
        "endpoint": endpoint,
        "bucket": bucket,
        "access": access or "",
        "secret": secret or "",
        "region_name": region_name,
        "addressing_style": addressing_style,
        "s3_compatibility": s3_compatibility,
    }


def _s3_client(config: dict[str, str]):
    return create_s3_client(
        endpoint_url=config["endpoint"],
        access_key_id=config["access"],
        secret_access_key=config["secret"],
        region_name=config.get("region_name", "auto"),
        addressing_style=config.get("addressing_style", "path"),
        s3_compatibility=config.get("s3_compatibility", "aws"),
    )


def _latest_remote_descriptor(config: dict[str, str]) -> dict[str, object]:
    client = _s3_client(config)
    response = client.list_objects_v2(Bucket=config["bucket"], Prefix="backups/private-database/")
    keys = sorted(
        str(item.get("Key") or "")
        for item in response.get("Contents") or []
        if str(item.get("Key") or "").endswith("/recovery.json")
    )
    if not keys:
        raise RecoveryBundleError("远端没有可用恢复描述符")
    response = client.get_object(Bucket=config["bucket"], Key=keys[-1])
    try:
        descriptor = json.loads(response["Body"].read().decode("utf-8"))
    except (KeyError, AttributeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise RecoveryBundleError("远端恢复描述符不可解析") from exc
    if not isinstance(descriptor, dict) or descriptor.get("schema_version") != "1.0" or descriptor.get("kind") != "social_archive.private_database_recovery_descriptor":
        raise RecoveryBundleError("远端恢复描述符类型错误")
    return descriptor


def _download_remote_ciphertext(config: dict[str, str], remote_key: str, expected_sha256: str, target: Path) -> None:
    client = _s3_client(config)
    temporary = target.with_name(f".{target.name}.download")
    try:
        client.download_file(config["bucket"], remote_key, str(temporary))
        if not temporary.is_file() or sha256_file(temporary) != expected_sha256:
            raise RecoveryBundleError("远端备份密文回读哈希不一致")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _validated_manifest(manifest: object, *, require_local_ciphertext: bool) -> tuple[dict[str, object], Path | None, str, str, str | None]:
    if not isinstance(manifest, dict):
        raise RecoveryBundleError("备份 manifest 必须是 JSON 对象")
    original_sha = str(manifest.get("original_sha256") or "")
    cipher_sha = str(manifest.get("cipher_sha256") or "")
    if len(original_sha) != 64 or len(cipher_sha) != 64 or manifest.get("encryption") != "age-x25519":
        raise RecoveryBundleError("备份 manifest 缺少有效 age 哈希或算法")
    try:
        bytes.fromhex(original_sha)
        bytes.fromhex(cipher_sha)
    except ValueError as exc:
        raise RecoveryBundleError("备份 manifest 哈希格式无效") from exc
    receipts = manifest.get("receipts")
    if not isinstance(receipts, dict):
        raise RecoveryBundleError("备份 manifest 缺少 R2/OCI 收据")
    for store_id in ("r2", "oci"):
        receipt = receipts.get(store_id)
        if not isinstance(receipt, dict) or receipt.get("status") != "verified":
            raise RecoveryBundleError(f"备份 {store_id} 收据未验证")
        if (
            receipt.get("original_sha256") != original_sha
            or receipt.get("cipher_sha256") != cipher_sha
            or receipt.get("encryption") != "age-x25519"
        ):
            raise RecoveryBundleError(f"备份 {store_id} 收据与密文不一致")
    raw_ciphertext = manifest.get("ciphertext")
    ciphertext = Path(raw_ciphertext) if isinstance(raw_ciphertext, str) and raw_ciphertext else None
    remote_key = manifest.get("remote_key")
    if require_local_ciphertext and ciphertext is None:
        raise RecoveryBundleError("备份 manifest 缺少本地密文路径")
    if not require_local_ciphertext and (not isinstance(remote_key, str) or not remote_key):
        raise RecoveryBundleError("备份 manifest 缺少远端密文键")
    return manifest, ciphertext, original_sha, cipher_sha, str(remote_key) if isinstance(remote_key, str) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or restore an age-encrypted Private-Database backup")
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--target")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--from-store", choices=("r2", "oci"), help="从该冷备副本读取最新 recovery.json 与密文")
    args = parser.parse_args()
    settings = Settings.from_env()
    config: dict[str, str] | None = None
    manifest_path: Path | None = None
    try:
        if args.from_store:
            config = _s3_config(args.from_store)
            if config is None:
                print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": f"缺少 {args.from_store.upper()} 恢复读取配置"}, ensure_ascii=False))
                return 3
            if args.manifest:
                manifest_path = Path(args.manifest).resolve()
                if not manifest_path.is_file():
                    print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "没有可用备份 manifest"}, ensure_ascii=False))
                    return 3
                raw_manifest: object = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                raw_manifest = _latest_remote_descriptor(config)
        else:
            manifest_path = Path(args.manifest).resolve() if args.manifest else _latest_manifest(settings)
            if not manifest_path or not manifest_path.is_file():
                print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "没有可用备份 manifest"}, ensure_ascii=False))
                return 3
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest, ciphertext, original_sha, cipher_sha, remote_key = _validated_manifest(
            raw_manifest, require_local_ciphertext=not bool(args.from_store)
        )
    except (OSError, ValueError, json.JSONDecodeError, RecoveryBundleError, PermissionError) as exc:
        print(json.dumps({"status": "FAIL", "error_code": "RECOVERY_MANIFEST_INVALID", "message": str(exc)}, ensure_ascii=False))
        return 1
    if ciphertext is not None and (not ciphertext.is_file() or ciphertext.is_symlink() or sha256_file(ciphertext) != cipher_sha):
        print(json.dumps({"status": "FAIL", "message": "备份密文缺失或哈希不一致"}, ensure_ascii=False))
        return 1
    identity = resolve_secret_path(
        settings.age_identity_file or os.getenv("SOCIAL_ARCHIVE_AGE_IDENTITY_FILE"))
    if args.dry_run:
        print(json.dumps({"status": "READY",
                          # 从远端读的时候 manifest_path 是 None，原来直接 str() 出来
                          # 就是字符串 "None"——**演练报告上最不该含糊的就是
                          # 「你正要恢复的是哪一份」**。真恢复那条路（第 248 行）
                          # 早就写对了，是这条演练路没跟上。
                          "manifest": str(manifest_path) if manifest_path else "remote:latest",
                          "source_store": args.from_store,
                          "cipher_sha256": cipher_sha,
                          # **改成看文件在不在，不是看配了没配。**
                          # 原来只判 bool(identity)：`.env` 里配着一个容器里的路径，
                          # 主机上那个文件根本不存在，而 --dry-run 照样报
                          # identity_configured=true——**演练说准备好了，真恢复时才发现没有**。
                          "identity_configured": bool(identity and Path(identity).is_file()),
                          "secret_path_fallbacks": list(SECRET_PATH_FALLBACKS)},
                         ensure_ascii=False))
        return 0
    if not identity or not Path(identity).is_file():
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT",
                          "message": "恢复节点缺少 SOCIAL_ARCHIVE_AGE_IDENTITY_FILE",
                          "secret_path_fallbacks": list(SECRET_PATH_FALLBACKS)},
                         ensure_ascii=False))
        return 3

    target = Path(args.target).resolve() if args.target else settings.data_root / "restore" / original_sha[:12]
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        print(json.dumps({"status": "FAIL", "message": "恢复目标必须为空目录"}, ensure_ascii=False))
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="social-archive-restore-") as temp:
            plain = Path(temp) / "private-database.tar.gz"
            if args.from_store:
                assert config is not None and remote_key is not None
                ciphertext = Path(temp) / "remote.age"
                try:
                    _download_remote_ciphertext(config, remote_key, cipher_sha, ciphertext)
                except Exception:  # noqa: BLE001 - external object-store boundary
                    print(json.dumps({"status": "FAIL", "error_code": "RECOVERY_REMOTE_CIPHER_UNAVAILABLE"}, ensure_ascii=False))
                    return 1
            assert ciphertext is not None
            _decrypt(ciphertext, identity, plain)
            if sha256_file(plain) != original_sha:
                print(json.dumps({"status": "FAIL", "message": "解密后的原始哈希不一致"}, ensure_ascii=False))
                return 1
            with tarfile.open(plain, "r:gz") as tf:
                members = list(safe_members(tf))
                extracted = Path(temp) / "extracted"
                extracted.mkdir()
                tf.extractall(extracted, members=members, filter="data")
            try:
                facts = load_recovery_bundle(extracted)
            except RecoveryBundleError as exc:
                print(json.dumps({"status": "FAIL", "error_code": "RECOVERY_BUNDLE_INVALID", "message": str(exc)}, ensure_ascii=False))
                return 1
            if not args.verify_only:
                target.mkdir(parents=True, exist_ok=True)
                for item in extracted.iterdir():
                    shutil.copy2(item, target / item.name)
    except (OSError, RuntimeError, ValueError, tarfile.TarError) as exc:
        print(json.dumps({"status": "FAIL", "error_code": "RECOVERY_DECRYPT_OR_ARCHIVE_FAILED", "message": str(exc)}, ensure_ascii=False))
        return 1
    result = {"status": "PASS", "mode": "verify_only" if args.verify_only else "restore", "manifest": str(manifest_path) if manifest_path else "remote:latest", "original_sha256": original_sha, "fact_count": len(facts), "source_store": args.from_store}
    if not args.verify_only:
        result["target"] = str(target)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
