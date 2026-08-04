"""Validation and rebuild helpers for encrypted Private-Database recovery bundles.

The cold backup is deliberately a projection of already-delivered, fully
replicated facts.  It is not a second local Private-Database checkout.  These
helpers make that boundary executable: an incomplete three-replica fact is
rejected before a new Runtime SQLite projection is created.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .db import RuntimeStore
from .private_facts import PRIVATE_DATABASE_FACT_SCHEMA, fact_sha256
from .utils import sha256_bytes


class RecoveryBundleError(ValueError):
    """The recovery fixture is malformed or cannot prove durable completeness."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecoveryBundleError(message)


def _regular_file(path: Path, message: str) -> None:
    _require(path.is_file() and not path.is_symlink(), message)


def _hex_digest(value: object, message: str) -> str:
    raw = str(value or "")
    _require(len(raw) == 64, message)
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise RecoveryBundleError(message) from exc
    return raw


def _validate_complete_fact(fact: Any) -> dict[str, Any]:
    _require(isinstance(fact, dict), "恢复事实必须是 JSON 对象")
    _require(fact.get("schema_version") == PRIVATE_DATABASE_FACT_SCHEMA, "恢复事实 schema 不兼容")
    _require(fact.get("kind") == "social_archive.completed_content", "恢复事实类型错误")
    content = fact.get("content")
    _require(isinstance(content, dict), "恢复事实缺少 content")
    content_id = str(content.get("id") or "")
    _require(bool(content_id), "恢复事实缺少 content.id")
    _require(bool(str(content.get("platform") or "")), "恢复事实缺少 platform")
    _require(bool(str(content.get("canonical_url") or "")), "恢复事实缺少 canonical_url")

    relations = fact.get("relations")
    artifacts = fact.get("artifacts")
    replicas = fact.get("object_replicas")
    _require(isinstance(relations, list), "恢复事实 relations 必须是列表")
    _require(isinstance(artifacts, list) and artifacts, "恢复事实必须至少包含一个对象")
    _require(isinstance(replicas, list), "恢复事实 object_replicas 必须是列表")

    artifact_ids: set[str] = set()
    artifact_sha: dict[str, str] = {}
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "恢复对象必须是 JSON 对象")
        artifact_id = str(artifact.get("id") or "")
        _require(bool(artifact_id) and artifact_id not in artifact_ids, "恢复对象 ID 缺失或重复")
        _require(str(artifact.get("content_id") or "") == content_id, "恢复对象 content_id 不一致")
        _require(str(artifact.get("status") or "") == "complete", "恢复对象不是完成态")
        artifact_ids.add(artifact_id)
        artifact_sha[artifact_id] = _hex_digest(artifact.get("sha256"), "恢复对象 SHA-256 无效")

    seen_receipts: set[tuple[str, str]] = set()
    per_artifact: dict[str, dict[str, dict[str, Any]]] = {artifact_id: {} for artifact_id in artifact_ids}
    for receipt in replicas:
        _require(isinstance(receipt, dict), "恢复副本收据必须是 JSON 对象")
        artifact_id = str(receipt.get("artifact_id") or "")
        store_id = str(receipt.get("store_id") or "")
        key = (artifact_id, store_id)
        _require(artifact_id in artifact_ids and store_id in {"r2", "oci", "github"}, "恢复副本收据引用无效")
        _require(key not in seen_receipts, "恢复副本收据重复")
        _require(str(receipt.get("status") or "") == "verified", "恢复副本尚未验证")
        _require(str(receipt.get("original_sha256") or "") == artifact_sha[artifact_id], "恢复副本原始 SHA 不一致")
        _require(str(receipt.get("encryption") or "") == "age-x25519", "恢复副本加密算法不一致")
        _hex_digest(receipt.get("verified_sha256"), "恢复副本密文 SHA-256 无效")
        seen_receipts.add(key)
        per_artifact[artifact_id][store_id] = receipt

    for artifact_id, receipt_map in per_artifact.items():
        _require(set(receipt_map) == {"r2", "oci", "github"}, f"恢复对象 {artifact_id} 缺少三副本收据")
        cipher_hashes = {str(item.get("verified_sha256")) for item in receipt_map.values()}
        _require(len(cipher_hashes) == 1, f"恢复对象 {artifact_id} 三副本密文不一致")
    return fact


def load_recovery_bundle(root: Path) -> list[dict[str, Any]]:
    """Load a deterministic backup bundle and reject any weakened receipt chain."""
    root = root.resolve()
    snapshot_path = root / "snapshot.json"
    facts_path = root / "facts.ndjson"
    _regular_file(snapshot_path, "恢复包缺少安全的 snapshot.json")
    _regular_file(facts_path, "恢复包缺少安全的 facts.ndjson")
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RecoveryBundleError("恢复包 snapshot.json 不可解析") from exc
    _require(isinstance(snapshot, dict), "恢复包 snapshot.json 必须是对象")
    _require(snapshot.get("schema_version") == "1.0", "恢复包 schema 不兼容")
    _require(snapshot.get("kind") == "social_archive.private_database_recovery_bundle", "恢复包类型错误")

    try:
        lines = facts_path.read_bytes().splitlines()
        facts = [_validate_complete_fact(json.loads(line.decode("utf-8"))) for line in lines]
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, RecoveryBundleError):
            raise
        raise RecoveryBundleError("恢复包 facts.ndjson 不可解析") from exc
    _require(bool(facts), "恢复包不得为空")
    content_ids = [str(fact["content"]["id"]) for fact in facts]
    _require(content_ids == sorted(content_ids) and len(set(content_ids)) == len(content_ids), "恢复事实顺序或 ID 不确定")
    digests = [fact_sha256(fact) for fact in facts]
    expected_digests = snapshot.get("fact_sha256s")
    _require(isinstance(expected_digests, list) and expected_digests == digests, "恢复事实哈希列表不一致")
    _require(snapshot.get("fact_count") == len(facts), "恢复事实数量不一致")
    expected_bundle_hash = sha256_bytes(b"".join(bytes.fromhex(digest) for digest in digests))
    _require(snapshot.get("facts_sha256") == expected_bundle_hash, "恢复事实汇总哈希不一致")
    return facts


def rebuild_runtime_projection(recovery_root: Path, target: Path) -> dict[str, int]:
    """Build a fresh Runtime SQLite projection without overwriting an existing DB.

    Jobs, leases and destination export receipts are intentionally not recreated:
    they are operational projections rather than Private-Database authority.
    """
    facts = load_recovery_bundle(recovery_root)
    target = target.resolve()
    _require(not target.exists(), "重建目标已存在；拒绝覆盖现有 Runtime SQLite")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.rebuild")
    _require(not temporary.exists(), "恢复临时目标已存在；拒绝覆盖")
    store = RuntimeStore(temporary)
    content_count = relation_count = artifact_count = replica_count = 0
    try:
        store.initialize()
        with store.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            for fact in facts:
                content = fact["content"]
                content_id = str(content["id"])
                relations = fact["relations"]
                for relation in relations:
                    _require(isinstance(relation, dict), "恢复关系必须是 JSON 对象")
                    source_account_id = relation.get("source_account_id")
                    if source_account_id:
                        relation_time = str(relation.get("first_observed_at") or content.get("first_observed_at") or "")
                        _require(bool(relation_time), "恢复关系缺少时间")
                        con.execute(
                            """INSERT OR IGNORE INTO source_account(
                                 id,platform,external_account_id,display_name,auth_ref,created_at,updated_at
                               ) VALUES(?,?,?,?,?,?,?)""",
                            (str(source_account_id), str(content["platform"]), None, None, None, relation_time, relation_time),
                        )
                con.execute(
                    """INSERT INTO content(
                         id,platform,external_content_id,canonical_url,content_type,title,author_name,published_at,
                         first_observed_at,last_observed_at,availability,metadata_json
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        content_id,
                        str(content["platform"]),
                        content.get("external_content_id"),
                        str(content["canonical_url"]),
                        str(content.get("content_type") or "unknown"),
                        content.get("title"),
                        content.get("author_name"),
                        content.get("published_at"),
                        str(content.get("first_observed_at") or ""),
                        str(content.get("last_observed_at") or ""),
                        str(content.get("availability") or "observed"),
                        json.dumps(content.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
                    ),
                )
                content_count += 1
                tags: list[str] = []
                for relation in relations:
                    relation_id = str(relation.get("id") or "")
                    _require(bool(relation_id), "恢复关系缺少 ID")
                    _require(str(relation.get("content_id") or "") == content_id, "恢复关系 content_id 不一致")
                    collection_key = str(relation.get("collection_key") or "")
                    if collection_key:
                        tags.append(collection_key)
                    con.execute(
                        """INSERT INTO user_relation(
                             id,source_account_id,content_id,relation_type,collection_key,status,
                             first_observed_at,last_observed_at,missing_complete_scan_count,closed_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            relation_id,
                            relation.get("source_account_id"),
                            content_id,
                            str(relation.get("relation_type") or "saved"),
                            collection_key,
                            str(relation.get("status") or "active"),
                            str(relation.get("first_observed_at") or ""),
                            str(relation.get("last_observed_at") or ""),
                            int(relation.get("missing_complete_scan_count") or 0),
                            relation.get("closed_at"),
                        ),
                    )
                    relation_count += 1
                con.execute(
                    "INSERT INTO content_fts(content_id,title,author_name,body,tags) VALUES(?,?,?,?,?)",
                    (content_id, str(content.get("title") or ""), str(content.get("author_name") or ""), str(fact.get("body") or ""), " ".join(sorted(set(tags)))),
                )
                for artifact in fact["artifacts"]:
                    con.execute(
                        """INSERT INTO artifact(
                             id,content_id,archive_level,artifact_type,sha256,byte_size,media_type,local_path,created_at,status
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            str(artifact["id"]), content_id, str(artifact.get("archive_level") or "L1"),
                            str(artifact.get("artifact_type") or "recovered"), str(artifact["sha256"]),
                            int(artifact.get("byte_size") or 0), artifact.get("media_type"), None,
                            str(artifact.get("created_at") or content.get("last_observed_at") or ""), "complete",
                        ),
                    )
                    artifact_count += 1
                for receipt in fact["object_replicas"]:
                    con.execute(
                        """INSERT INTO object_replica(
                             id,artifact_id,store_id,object_key,status,etag,verified_sha256,original_sha256,encryption,updated_at,last_error_code
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            str(receipt.get("id") or f"recovered-{receipt['artifact_id']}-{receipt['store_id']}"),
                            str(receipt["artifact_id"]), str(receipt["store_id"]), str(receipt.get("object_key") or ""),
                            "verified", receipt.get("etag"), str(receipt["verified_sha256"]), str(receipt["original_sha256"]),
                            "age-x25519", str(receipt.get("updated_at") or ""), receipt.get("last_error_code"),
                        ),
                    )
                    replica_count += 1
            con.execute("COMMIT")
        # RuntimeStore enables WAL for normal operation.  Checkpoint before the
        # atomic replace so the rebuilt projection is a single portable SQLite
        # file rather than a main DB that still depends on a sibling -wal file.
        with store.connection() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        os.replace(temporary, target)
    except Exception:
        for candidate in (temporary, temporary.with_name(f"{temporary.name}-wal"), temporary.with_name(f"{temporary.name}-shm")):
            candidate.unlink(missing_ok=True)
        raise
    for candidate in (temporary.with_name(f"{temporary.name}-wal"), temporary.with_name(f"{temporary.name}-shm")):
        candidate.unlink(missing_ok=True)
    return {
        "content_count": content_count,
        "relation_count": relation_count,
        "artifact_count": artifact_count,
        "replica_count": replica_count,
    }


# ---- 恢复节点上的密钥路径 -------------------------------------------------
#
# **恢复是出事那天才跑的东西，那一天不能再去现场试路径。**
#
# 2026-08-05 实测：`.env` 里那几个 *_FILE 指的是 /run/secrets/… ——那是**容器里**
# 的挂载点，主机上根本不存在。于是在主机上照着运维手册跑
# `bash scripts/restore.sh --latest --dry-run`，拿到的是
# 「缺少 R2 恢复读取配置」；而那两个密钥就在主机的 runtime/secrets/ 下。
#
# 兜底的边界卡死：**只找同名文件、只在这一个目录下找**，两处都没有就照旧失败。
# 绝不猜别的名字——密钥这种东西「找个像的顶上」是最坏的行为，
# 它会把一份错的凭据当成对的用下去，而错误要到很久以后才显形。
SECRET_FALLBACK_DIR = Path(__file__).resolve().parents[2] / "runtime/secrets"
SECRET_PATH_FALLBACKS: list[str] = []


def resolve_secret_path(configured: str | None) -> str | None:
    """配置指的路径不在，就去恢复节点的 runtime/secrets/ 找同名文件。

    用过就记一笔到 `SECRET_PATH_FALLBACKS`——**静默兜底比不兜底更坏**：
    它会让人以为配置本来就是对的，换一台机器照抄配置又撞同一堵墙。
    """
    if not configured:
        return configured
    if Path(configured).is_file():
        return configured
    candidate = SECRET_FALLBACK_DIR / Path(configured).name
    if candidate.is_file():
        SECRET_PATH_FALLBACKS.append(f"{configured} → {candidate}")
        return str(candidate)
    return configured
