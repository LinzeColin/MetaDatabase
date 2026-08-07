from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from social_archive.config import Settings
from social_archive.storage import create_s3_client
from social_archive.recovery import SECRET_PATH_FALLBACKS, resolve_secret_path
from social_archive.utils import read_secret, sha256_file


REQUIRED_STORES = ("r2", "oci", "github")


class RecoveryBlocked(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RecoveryFailure(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _sha256(value: object, *, field: str) -> str:
    raw = str(value or "")
    if len(raw) != 64:
        raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", f"{field} 不是 SHA-256")
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", f"{field} 不是 SHA-256") from exc
    return raw.lower()


def _validated_descriptor(artifact: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    artifact_id = str(artifact.get("id") or "")
    original_sha256 = _sha256(artifact.get("sha256"), field="artifact.sha256")
    if not artifact_id or str(artifact.get("status") or "") != "complete":
        raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", "恢复对象不是完成态")

    by_store: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", "恢复副本收据类型错误")
        store_id = str(receipt.get("store_id") or "")
        if store_id not in REQUIRED_STORES or store_id in by_store:
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", "恢复副本收据缺失、重复或目标非法")
        if str(receipt.get("artifact_id") or "") != artifact_id:
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", "恢复副本收据引用错误")
        if str(receipt.get("status") or "") != "verified":
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", f"{store_id} 副本尚未验证")
        if str(receipt.get("original_sha256") or "").lower() != original_sha256:
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", f"{store_id} 明文哈希收据不一致")
        if str(receipt.get("encryption") or "") != "age-x25519":
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", f"{store_id} 加密算法收据不一致")
        object_key = str(receipt.get("object_key") or "")
        if not object_key:
            raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", f"{store_id} 缺少对象键")
        by_store[store_id] = {
            "artifact_id": artifact_id,
            "store_id": store_id,
            "object_key": object_key,
            "cipher_sha256": _sha256(receipt.get("verified_sha256"), field=f"{store_id}.verified_sha256"),
            "original_sha256": original_sha256,
            "encryption": "age-x25519",
        }

    if set(by_store) != set(REQUIRED_STORES):
        raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", "恢复对象缺少三副本收据")
    cipher_hashes = {receipt["cipher_sha256"] for receipt in by_store.values()}
    if len(cipher_hashes) != 1:
        raise RecoveryFailure("RECOVERY_RECEIPT_INVALID", "三副本密文哈希不一致")
    return {
        "artifact_id": artifact_id,
        "original_sha256": original_sha256,
        "cipher_sha256": next(iter(cipher_hashes)),
        "encryption": "age-x25519",
        "replicas": by_store,
    }


def load_runtime_descriptor(runtime_db: Path, artifact_id: str) -> dict[str, Any]:
    """Read exactly one artifact receipt chain through an SQLite read-only URI."""
    if not artifact_id:
        raise RecoveryBlocked("ARTIFACT_ID_MISSING", "必须指定 artifact ID")
    if not runtime_db.is_file() or runtime_db.is_symlink():
        raise RecoveryBlocked("RUNTIME_DB_UNAVAILABLE", "恢复来源 Runtime SQLite 不可用")
    try:
        uri = runtime_db.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            artifact = connection.execute(
                "SELECT id,sha256,status FROM artifact WHERE id=?", (artifact_id,)
            ).fetchone()
            receipts = connection.execute(
                """SELECT artifact_id,store_id,object_key,status,verified_sha256,
                          original_sha256,encryption
                     FROM object_replica WHERE artifact_id=? ORDER BY store_id""",
                (artifact_id,),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise RecoveryFailure("RUNTIME_RECEIPT_READ_FAILED", "无法读取恢复对象收据") from exc
    if artifact is None:
        raise RecoveryBlocked("ARTIFACT_NOT_FOUND", "指定对象不存在于 Runtime 收据")
    return _validated_descriptor(dict(artifact), [dict(row) for row in receipts])




def _s3_config(store_id: str) -> dict[str, str]:
    prefix = f"SOCIAL_ARCHIVE_{store_id.upper()}"
    endpoint = os.getenv(f"{prefix}_ENDPOINT", "").strip()
    bucket = os.getenv(f"{prefix}_BUCKET", "").strip()
    access_key_id = read_secret(resolve_secret_path(os.getenv(f"{prefix}_ACCESS_KEY_ID_FILE")))
    secret_access_key = read_secret(resolve_secret_path(os.getenv(f"{prefix}_SECRET_ACCESS_KEY_FILE")))
    region_name = os.getenv(f"{prefix}_REGION", "auto").strip() or "auto"
    addressing_style = os.getenv(f"{prefix}_ADDRESSING_STYLE", "path").strip() or "path"
    s3_compatibility = os.getenv(f"{prefix}_S3_COMPATIBILITY", "aws").strip().lower() or "aws"
    if not all((endpoint, bucket, access_key_id, secret_access_key)):
        raise RecoveryBlocked("OBJECT_STORE_CONFIG_MISSING", f"缺少 {store_id.upper()} 恢复读取配置")
    if addressing_style not in {"auto", "path", "virtual"} or s3_compatibility not in {"aws", "oci"}:
        raise RecoveryBlocked("OBJECT_STORE_CONFIG_INVALID", f"{store_id.upper()} 恢复读取配置非法")
    return {
        "endpoint": endpoint,
        "bucket": bucket,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "region_name": region_name,
        "addressing_style": addressing_style,
        "s3_compatibility": s3_compatibility,
    }


def _canonical_s3_key(original_sha256: str) -> str:
    return f"primary-objects/sha256/{original_sha256[:2]}/{original_sha256[2:4]}/{original_sha256}.age"


def _s3_head(descriptor: dict[str, Any], *, store_id: str, config: dict[str, str]):
    """HEAD 一次并校验元数据。**不下载、不解密。**

    抽出来是因为「东西还在不在」和「东西能不能还原」是两个问题，
    而后者需要 age 私钥。2026-08-07 想在生产上确认「加密存三份」是否
    仍然成立，发现**唯一的核对入口整条都被私钥挡着**——而
    `object_replica` 里那三行 `verified` 是**写入当时**的记录，
    不代表对象今天还在（这个仓已经因为「记录说 verified」栽过）。
    """
    receipt = descriptor["replicas"][store_id]
    expected_key = _canonical_s3_key(descriptor["original_sha256"])
    if receipt["object_key"] != expected_key:
        raise RecoveryFailure("S3_RECEIPT_KEY_MISMATCH", f"{store_id.upper()} 对象键不符合内容寻址合同")
    client = create_s3_client(
        endpoint_url=config["endpoint"],
        access_key_id=config["access_key_id"],
        secret_access_key=config["secret_access_key"],
        region_name=config["region_name"],
        addressing_style=config["addressing_style"],
        s3_compatibility=config["s3_compatibility"],
    )
    head = client.head_object(Bucket=config["bucket"], Key=expected_key)
    metadata = {str(key).lower(): str(value) for key, value in (head.get("Metadata") or {}).items()}
    if (
        metadata.get("original-sha256", "").lower() != descriptor["original_sha256"]
        or metadata.get("cipher-sha256", "").lower() != descriptor["cipher_sha256"]
        or metadata.get("encryption") != "age-x25519"
    ):
        raise RecoveryFailure("S3_METADATA_MISMATCH", f"{store_id.upper()} 远端元数据与收据不一致")
    return client, expected_key, head


def presence_s3(descriptor: dict[str, Any], *, store_id: str, config: dict[str, str]) -> dict[str, Any]:
    try:
        _client, key, head = _s3_head(descriptor, store_id=store_id, config=config)
    except RecoveryFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - 不泄漏供应商诊断或凭据
        raise RecoveryFailure("S3_OBJECT_MISSING", f"{store_id.upper()} 上找不到这个对象") from exc
    return {"object_key": key, "byte_size": int(head.get("ContentLength") or 0),
            "encryption": "age-x25519"}


def presence_github(descriptor: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    repository = str(settings.github_archive_repository or "").strip()
    if not repository:
        raise RecoveryBlocked("GITHUB_REPOSITORY_MISSING", "缺少 GitHub Vault 仓配置")
    repository, tag, member = _github_receipt_location(descriptor, repository)
    if not shutil.which("gh"):
        raise RecoveryBlocked("GH_BINARY_MISSING", "缺少 gh CLI，无法读取 GitHub Vault")
    environment = _github_environment(settings.github_token_file)
    try:
        release = json.loads(_run_gh(
            ["gh", "release", "view", tag, "--repo", repository, "--json", "isDraft,assets"],
            env=environment))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RecoveryFailure("GITHUB_RELEASE_READ_FAILED", "GitHub Vault Draft 状态不可验证") from exc
    if not isinstance(release, dict) or release.get("isDraft") is not True:
        raise RecoveryFailure("GITHUB_RELEASE_NOT_DRAFT", "GitHub 恢复副本不是 Draft Release")
    assets = [str(item.get("name") or "") for item in (release.get("assets") or [])]
    if not assets:
        raise RecoveryFailure("GITHUB_ASSET_MISSING", "这个 Draft Release 上一个附件都没有")
    return {"release_tag": tag, "asset_count": len(assets), "member": member}


def download_s3_ciphertext(
    descriptor: dict[str, Any],
    *,
    store_id: str,
    config: dict[str, str],
    target: Path,
) -> None:
    try:
        client, expected_key, head = _s3_head(descriptor, store_id=store_id, config=config)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.download")
        try:
            client.download_file(config["bucket"], expected_key, str(temporary))
            if not temporary.is_file() or sha256_file(temporary) != descriptor["cipher_sha256"]:
                raise RecoveryFailure("S3_CIPHER_HASH_MISMATCH", f"{store_id.upper()} 密文回读哈希不一致")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    except RecoveryFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - do not expose provider diagnostics or credentials
        raise RecoveryFailure("S3_CIPHER_DOWNLOAD_FAILED", f"{store_id.upper()} 密文恢复读取失败") from exc


def _github_environment(token_file: str | None) -> dict[str, str]:
    token = read_secret(token_file)
    if not token:
        raise RecoveryBlocked("GITHUB_TOKEN_MISSING", "缺少 GitHub Vault 专用恢复 token")
    environment = dict(os.environ)
    environment.pop("GITHUB_TOKEN", None)
    environment["GH_TOKEN"] = token
    return environment


def _run_gh(argv: list[str], *, env: dict[str, str]) -> str:
    completed = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
    if completed.returncode:
        raise RecoveryFailure("GITHUB_RELEASE_READ_FAILED", "GitHub Private Draft Release 读取失败")
    return completed.stdout


def _github_receipt_location(descriptor: dict[str, Any], configured_repository: str) -> tuple[str, str, str]:
    raw = str(descriptor["replicas"]["github"]["object_key"])
    parsed = urlsplit(raw)
    segments = [segment for segment in parsed.path.split("/") if segment]
    expected_member = f"objects/{descriptor['original_sha256']}.age"
    if (
        parsed.scheme != "gh-release"
        or not parsed.netloc
        or len(segments) < 2
        or not parsed.fragment == expected_member
    ):
        raise RecoveryFailure("GITHUB_RECEIPT_INVALID", "GitHub 副本收据格式非法")
    repository = f"{parsed.netloc}/{segments[0]}"
    tag = "/".join(segments[1:])
    if repository != configured_repository:
        raise RecoveryFailure("GITHUB_RECEIPT_REPOSITORY_MISMATCH", "GitHub 副本收据不属于配置的 Vault")
    return repository, tag, expected_member


def _simple_asset_name(value: object) -> str:
    name = str(value or "")
    if not name or Path(name).name != name or name in {".", ".."}:
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 资产名称非法")
    return name


def _release_manifest(download_dir: Path, descriptor: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = sorted(
        path for path in download_dir.iterdir()
        if path.is_file() and not path.is_symlink() and path.name.endswith(".manifest.json")
    )
    if len(candidates) != 1:
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 缺少唯一对象包清单")
    try:
        manifest = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象包清单不可解析") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "2.0" or manifest.get("encryption") != "age-x25519":
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象包清单类型错误")
    _sha256(manifest.get("pack_sha256"), field="github.pack_sha256")
    parts = manifest.get("pack_parts")
    objects = manifest.get("objects")
    if not isinstance(parts, list) or not parts or not isinstance(objects, list) or not objects:
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象包清单不完整")
    if any(not isinstance(item, dict) for item in objects):
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象清单包含非法项目")
    selected = [
        item for item in objects
        if isinstance(item, dict) and str(item.get("original_sha256") or "").lower() == descriptor["original_sha256"]
    ]
    if len(selected) != 1:
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 不包含目标对象")
    item = selected[0]
    if (
        _sha256(item.get("cipher_sha256"), field="github.object.cipher_sha256") != descriptor["cipher_sha256"]
        or item.get("encryption") != "age-x25519"
        or item.get("path") != f"objects/{descriptor['original_sha256']}.age"
    ):
        raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 目标对象与收据不一致")
    return manifest, list(objects)


def extract_verified_github_ciphertext(download_dir: Path, descriptor: dict[str, Any], target: Path) -> None:
    """Verify every listed release asset, then extract only the requested cipher."""
    manifest, objects = _release_manifest(download_dir, descriptor)
    raw_parts = manifest["pack_parts"]
    assert isinstance(raw_parts, list)
    part_names: set[str] = set()
    parts: list[Path] = []
    for item in raw_parts:
        if not isinstance(item, dict):
            raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 分片清单非法")
        name = _simple_asset_name(item.get("name"))
        if name in part_names:
            raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 分片重复")
        part_names.add(name)
        expected_sha = _sha256(item.get("sha256"), field="github.part.sha256")
        path = download_dir / name
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected_sha:
            raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 分片回读哈希不一致")
        if int(item.get("byte_size") or -1) != path.stat().st_size:
            raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 分片大小不一致")
        parts.append(path)

    assembled = download_dir / ".assembled.tar"
    try:
        with assembled.open("wb") as output:
            for part in parts:
                with part.open("rb") as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        if sha256_file(assembled) != _sha256(manifest.get("pack_sha256"), field="github.pack_sha256"):
            raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象包哈希不一致")
        expected_members: dict[str, dict[str, Any]] = {}
        for item in objects:
            path = str(item.get("path") or "")
            original = _sha256(item.get("original_sha256"), field="github.object.original_sha256")
            expected_path = f"objects/{original}.age"
            if path != expected_path:
                raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象路径非法")
            if item.get("encryption") != "age-x25519":
                raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象加密算法错误")
            cipher = _sha256(item.get("cipher_sha256"), field="github.object.cipher_sha256")
            # **同一条路径出现两次，不一定是坏的。**
            #
            # 对象是按内容寻址的（路径 = objects/{原文 sha256}.age），所以
            # **两个制品只要字节相同，就必然指向同一条路径**。清单里保留两条
            # 记录是对的：它记的是「哪个 artifact 对应哪个对象」，
            # 而多对一是这套设计的正常结果。
            #
            # 原来这里一见重复就整包判废。2026-08-04 实测：
            # 20260804T060736Z 那个包 500 个对象里有 **3 组**这样的重复，
            # 于是**整包 500 个对象一个都恢复不了**——而三份副本在库里
            # 全都登记着 verified。
            #
            # 真正该拦的是「同一条路径下挂着两份**不同**的内容」，那才是坏了。
            previous = expected_members.get(path)
            if previous is not None:
                if previous.get("cipher_sha256") != cipher:
                    raise RecoveryFailure(
                        "GITHUB_PACK_INVALID", "GitHub Release 同一路径下有两份不同的密文"
                    )
                continue
            expected_members[path] = item
        with tarfile.open(assembled, "r") as archive:
            members = {member.name: member for member in archive.getmembers()}
            if set(members) != set(expected_members):
                raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象包成员不一致")
            for name, item in expected_members.items():
                member = members[name]
                if not member.isfile():
                    raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象包包含非普通对象")
                handle = archive.extractfile(member)
                if handle is None:
                    raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象不可读取")
                digest = hashlib.sha256()
                with handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != _sha256(item.get("cipher_sha256"), field="github.object.cipher_sha256"):
                    raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 对象密文哈希不一致")
            selected_name = f"objects/{descriptor['original_sha256']}.age"
            handle = archive.extractfile(members[selected_name])
            if handle is None:
                raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 目标对象不可读取")
            with handle, target.open("wb") as output:
                shutil.copyfileobj(handle, output, length=1024 * 1024)
        if sha256_file(target) != descriptor["cipher_sha256"]:
            raise RecoveryFailure("GITHUB_PACK_INVALID", "GitHub Release 目标密文哈希不一致")
    finally:
        assembled.unlink(missing_ok=True)


def download_github_ciphertext(descriptor: dict[str, Any], *, settings: Settings, target: Path) -> None:
    repository = str(settings.github_archive_repository or "").strip()
    if not repository:
        raise RecoveryBlocked("GITHUB_REPOSITORY_MISSING", "缺少 GitHub Vault 仓配置")
    repository, tag, _member = _github_receipt_location(descriptor, repository)
    if not shutil.which("gh"):
        raise RecoveryBlocked("GH_BINARY_MISSING", "缺少 gh CLI，无法读取 GitHub Vault")
    environment = _github_environment(settings.github_token_file)
    try:
        repo = json.loads(_run_gh(["gh", "repo", "view", repository, "--json", "nameWithOwner,isPrivate"], env=environment))
        release = json.loads(_run_gh(["gh", "release", "view", tag, "--repo", repository, "--json", "isDraft"], env=environment))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RecoveryFailure("GITHUB_RELEASE_READ_FAILED", "GitHub Vault 身份或 Draft 状态不可验证") from exc
    if not isinstance(repo, dict) or repo.get("nameWithOwner") != repository or repo.get("isPrivate") is not True:
        raise RecoveryFailure("GITHUB_REPOSITORY_INVALID", "GitHub Vault 身份错误或不是私有仓")
    if not isinstance(release, dict) or release.get("isDraft") is not True:
        raise RecoveryFailure("GITHUB_RELEASE_NOT_DRAFT", "GitHub 恢复副本不是 Draft Release")
    with tempfile.TemporaryDirectory(prefix="social-archive-github-restore-") as temporary:
        download_dir = Path(temporary)
        _run_gh(["gh", "release", "download", tag, "--repo", repository, "--dir", str(download_dir)], env=environment)
        extract_verified_github_ciphertext(download_dir, descriptor, target)


def _validated_target(raw_target: str, settings: Settings) -> Path:
    candidate = Path(raw_target).expanduser()
    if candidate.is_symlink():
        raise RecoveryFailure("RECOVERY_TARGET_INVALID", "恢复目标不能是符号链接")
    target = candidate.resolve()
    if target == target.parent:
        raise RecoveryFailure("RECOVERY_TARGET_INVALID", "恢复目标不能是根目录")
    protected = (settings.data_root, settings.staging_root, settings.runtime_db.parent, settings.private_database_root)
    for root in protected:
        try:
            target.relative_to(root.resolve())
        except ValueError:
            continue
        raise RecoveryFailure("RECOVERY_TARGET_INVALID", "恢复目标不能落入运行数据面")
    if target.exists() and (not target.is_dir() or target.is_symlink() or any(target.iterdir())):
        raise RecoveryFailure("RECOVERY_TARGET_INVALID", "恢复目标必须是新的空目录")
    return target


def decrypt_and_verify(ciphertext: Path, *, identity: str, descriptor: dict[str, Any], plaintext: Path) -> None:
    binary = shutil.which("age")
    if not binary:
        raise RecoveryBlocked("AGE_BINARY_MISSING", "缺少 age 命令")
    identity_path = Path(identity)
    if not identity_path.is_file():
        raise RecoveryBlocked("AGE_IDENTITY_MISSING", "恢复节点缺少 age identity")
    completed = subprocess.run(
        [binary, "-d", "-i", str(identity_path), "-o", str(plaintext), str(ciphertext)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RecoveryFailure("AGE_DECRYPT_FAILED", "age 解密失败")
    if not plaintext.is_file() or sha256_file(plaintext) != descriptor["original_sha256"]:
        raise RecoveryFailure("PLAINTEXT_HASH_MISMATCH", "恢复对象明文哈希不一致")


def _write_plaintext(plaintext: Path, target: Path, descriptor: dict[str, Any]) -> None:
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target, 0o700)
    output = target / f"{descriptor['original_sha256']}.bin"
    temporary = target / f".{output.name}.restore"
    try:
        with plaintext.open("rb") as source, temporary.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o600)
        if sha256_file(temporary) != descriptor["original_sha256"]:
            raise RecoveryFailure("PLAINTEXT_HASH_MISMATCH", "恢复对象写入后明文哈希不一致")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover one verified age-encrypted object from R2, OCI, or GitHub Private Draft")
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--from-store", required=True, choices=REQUIRED_STORES)
    parser.add_argument("--target")
    parser.add_argument("--runtime-db")
    parser.add_argument("--verify-only", action="store_true")
    # **「还在不在」不需要私钥。**（2026-08-07）
    # verify-only 是「下载并解密还原一遍」，那当然要私钥；而灾难恢复的第一问
    # 是「东西还在吗」，它该能在任何一台机器上问得出来。原先这条路整个被
    # 私钥挡着，于是「加密存三份」这句承诺在生产上**没有任何办法当场核实**。
    parser.add_argument("--presence-only", action="store_true",
                        help="只确认副本还在（HEAD / 列附件），不下载、不解密、不需要 age 私钥")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        runtime_db = Path(args.runtime_db).expanduser().resolve() if args.runtime_db else settings.runtime_db
        descriptor = load_runtime_descriptor(runtime_db, args.artifact_id)
        target = _validated_target(args.target, settings) if args.target else None
        if not args.verify_only and target is None:
            raise RecoveryBlocked("RECOVERY_TARGET_MISSING", "恢复写入必须指定新的空目录")
        identity = resolve_secret_path(
            settings.age_identity_file or os.getenv("SOCIAL_ARCHIVE_AGE_IDENTITY_FILE"))
        if args.dry_run:
            if args.from_store in {"r2", "oci"}:
                _s3_config(args.from_store)
            else:
                _github_receipt_location(descriptor, str(settings.github_archive_repository or "").strip())
                _github_environment(settings.github_token_file)
            print(json.dumps({
                "status": "READY", "source_store": args.from_store,
                "artifact_id": descriptor["artifact_id"],
                "original_sha256": descriptor["original_sha256"],
                "cipher_sha256": descriptor["cipher_sha256"],
                "identity_configured": bool(identity and Path(identity).is_file()),
            }, ensure_ascii=False))
            return 0
        if args.presence_only:
            if args.from_store in {"r2", "oci"}:
                found = presence_s3(descriptor, store_id=args.from_store,
                                    config=_s3_config(args.from_store))
            else:
                found = presence_github(descriptor, settings=settings)
            print(json.dumps({
                "status": "PASS", "mode": "presence_only",
                "source_store": args.from_store,
                "artifact_id": descriptor["artifact_id"],
                "found": found,
                "what_this_does_not_prove_zh": (
                    "只证明**副本还在、远端元数据对得上**。能不能真的还原出原文"
                    "要 --verify-only（那一档需要 age 私钥）。"),
            }, ensure_ascii=False))
            return 0
        if not identity:
            raise RecoveryBlocked("AGE_IDENTITY_MISSING", "恢复节点缺少 age identity")
        with tempfile.TemporaryDirectory(prefix="social-archive-object-restore-") as temporary:
            temporary_root = Path(temporary)
            ciphertext = temporary_root / "object.age"
            plaintext = temporary_root / "object.plain"
            if args.from_store in {"r2", "oci"}:
                download_s3_ciphertext(descriptor, store_id=args.from_store, config=_s3_config(args.from_store), target=ciphertext)
            else:
                download_github_ciphertext(descriptor, settings=settings, target=ciphertext)
            decrypt_and_verify(ciphertext, identity=identity, descriptor=descriptor, plaintext=plaintext)
            if not args.verify_only:
                assert target is not None
                _write_plaintext(plaintext, target, descriptor)
        print(json.dumps({
            "status": "PASS",
            "mode": "verify_only" if args.verify_only else "restore",
            "source_store": args.from_store,
            "artifact_id": descriptor["artifact_id"],
            "original_sha256": descriptor["original_sha256"],
            "cipher_sha256": descriptor["cipher_sha256"],
            "target_written": not args.verify_only,
            # 兜底用过就说出来。**静默兜底比不兜底更坏**——它会让人以为
            # 配置本来就是对的，下一台机器上照抄配置又撞同一堵墙。
            "secret_path_fallbacks": list(SECRET_PATH_FALLBACKS),
        }, ensure_ascii=False))
        return 0
    except RecoveryBlocked as exc:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "error_code": exc.code,
                          "message": exc.message,
                          "secret_path_fallbacks": list(SECRET_PATH_FALLBACKS)}, ensure_ascii=False))
        return 3
    except RecoveryFailure as exc:
        print(json.dumps({"status": "FAIL", "error_code": exc.code, "message": exc.message}, ensure_ascii=False))
        return 1
    except Exception:  # noqa: BLE001 - command output must never disclose provider diagnostics or secret paths
        print(json.dumps({"status": "FAIL", "error_code": "RECOVERY_UNEXPECTED_FAILURE", "message": "恢复过程发生未预期错误"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
