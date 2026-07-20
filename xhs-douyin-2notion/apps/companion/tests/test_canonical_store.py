from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from x2n_contracts import (
    Artifact,
    CanonicalContent,
    Classification,
    DuplicateDisposition,
    ErrorCode,
    SinkReceipt,
    SourceObservation,
    TaxonomyCategory,
    UserRelation,
    build_artifact_key,
    build_content_key,
    build_relation_key,
    build_sink_key,
)

from x2n_companion.canonical_store import CanonicalStore, WriteDisposition
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLATFORMS = ("xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao")
RELATIONS = ("liked", "favorited", "saved_current")
HOSTS = {
    "xiaohongshu": "www.xiaohongshu.com",
    "douyin": "www.douyin.com",
    "bilibili": "www.bilibili.com",
    "kuaishou": "www.kuaishou.com",
    "weibo": "www.weibo.com",
    "taobao": "item.taobao.com",
}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _model(model: Any, payload: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(payload, ensure_ascii=False))


def synthetic_content(index: int, *, record_version: int = 1, title_suffix: str = "") -> CanonicalContent:
    platform = PLATFORMS[index % len(PLATFORMS)]
    content_id = f"synthetic-{index:05d}"
    return _model(
        CanonicalContent,
        {
            "schema_version": "1.0",
            "content_key": build_content_key(platform, content_id),
            "platform": platform,
            "platform_content_id": content_id,
            "canonical_source_url": f"https://{HOSTS[platform]}/content/{content_id}",
            "content_type": "video" if index % 2 else "image_gallery",
            "title": f"Synthetic title {index}{title_suffix}",
            "description": f"Synthetic public-safe placeholder {index}",
            "author_name": f"Synthetic author {index % 7}",
            "author_platform_id": f"synthetic-author-{index % 7}",
            "published_at": "2026-07-20T00:00:00Z",
            "content_hash": _sha(f"content:{index}:{record_version}:{title_suffix}"),
            "first_observed_at": "2026-07-20T00:01:00Z",
            "last_observed_at": "2026-07-20T00:02:00Z",
            "record_version": record_version,
            "status": "active",
        },
    )


def synthetic_relation(content: CanonicalContent, index: int) -> UserRelation:
    relation_type = RELATIONS[index % len(RELATIONS)]
    account_hash = _sha(f"synthetic-account:{content.platform.value}")
    collection_id = f"collection-{index % 5}" if relation_type == "favorited" else None
    return _model(
        UserRelation,
        {
            "schema_version": "1.0",
            "relation_key": build_relation_key(
                account_hash,
                content.content_key,
                relation_type,
                collection_id,
            ),
            "account_ref_hash": account_hash,
            "content_key": content.content_key,
            "relation_type": relation_type,
            "source_collection_id": collection_id,
            "source_collection_name_private": "Synthetic collection" if collection_id else None,
            "first_seen_at": "2026-07-20T00:01:00Z",
            "last_seen_at": "2026-07-20T00:02:00Z",
            "status": "active",
            "confirmed_by": "scan",
            "scan_receipt_id": f"receipt_scan{index:05d}",
        },
    )


def synthetic_observation(content: CanonicalContent, index: int) -> SourceObservation:
    return _model(
        SourceObservation,
        {
            "schema_version": "1.0",
            "observation_id": f"obs_synthetic{index:05d}",
            "content_key": content.content_key,
            "adapter_name": "synthetic-adapter",
            "adapter_version": "1.0.0",
            "source_method": "current_page",
            "observed_at": "2026-07-20T00:01:00Z",
            "raw_text_hash": _sha(f"raw:{index}"),
            "normalized_fields": ["platform_content_id", "canonical_source_url", "content_type"],
            "field_provenance": [
                {"field": "platform_content_id", "source": "dom", "status": "present", "confidence": 1.0},
                {"field": "canonical_source_url", "source": "derived", "status": "present", "confidence": 1.0},
                {"field": "content_type", "source": "dom", "status": "present", "confidence": 1.0},
            ],
            "completeness": 1.0,
            "warning_codes": [],
            "ephemeral_media_ref_ids": [],
            "run_id": f"run_synthetic{index:05d}",
        },
    )


def synthetic_artifact(content: CanonicalContent, index: int) -> Artifact:
    input_hash = _sha(f"artifact-input:{index}")
    processor_version = "proc-1.0"
    return _model(
        Artifact,
        {
            "schema_version": "1.0",
            "artifact_id": f"art_synthetic{index:05d}",
            "artifact_key": build_artifact_key(content.content_key, "ocr", input_hash, processor_version),
            "content_key": content.content_key,
            "artifact_type": "ocr",
            "input_hash": input_hash,
            "processor": "synthetic-ocr",
            "processor_version": processor_version,
            "model_provider": None,
            "model_name": None,
            "model_snapshot": None,
            "prompt_version": None,
            "language": "zh-CN",
            "quality": {"grade": "high", "metric_name": "cer", "metric_value": 0.01},
            "private_payload_present": True,
            "private_payload_ref": f"prv_artifact{index:05d}",
            "private_payload_hash": _sha(f"artifact-payload:{index}"),
            "append_only": True,
            "artifact_sequence": 1,
            "created_at": "2026-07-20T00:03:00Z",
            "supersedes_artifact_id": None,
        },
    )


class CanonicalStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-f003-test-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _ingest(self, index: int) -> dict[str, Any]:
        content = synthetic_content(index)
        return self.store.ingest_bundle(
            content,
            relation=synthetic_relation(content, index),
            observations=(synthetic_observation(content, index),),
            artifacts=(synthetic_artifact(content, index),),
        )

    def test_runtime_root_is_exact_owner_namespace_and_owner_only(self) -> None:
        self.assertEqual(self.paths.data_root.parent, self.paths.download_destination)
        self.assertEqual(stat.S_IMODE(self.paths.data_root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.paths.marker.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.paths.database.stat().st_mode), 0o600)
        with self.assertRaises(X2NRuntimeError) as mismatch:
            RuntimePaths.from_values(
                str(self.destination / "wrong-project"),
                str(self.destination),
                repository_root=PROJECT_ROOT,
                create=True,
            )
        self.assertEqual(mismatch.exception.code, ErrorCode.POLICY_BLOCKED)
        with self.assertRaises(X2NRuntimeError):
            RuntimePaths.from_values(
                str(self.root),
                str(self.destination),
                repository_root=Path(self.temporary.name),
                create=False,
            )
        marker = json.loads(self.paths.marker.read_text(encoding="utf-8"))
        marker["product_execution_authorized"] = True
        self.paths.marker.write_text(json.dumps(marker), encoding="utf-8")
        self.paths.marker.chmod(0o600)
        with self.assertRaises(X2NRuntimeError) as unauthorized:
            RuntimePaths.from_values(
                str(self.root),
                str(self.destination),
                repository_root=PROJECT_ROOT,
                create=False,
            )
        self.assertEqual(unauthorized.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_schema_wal_foreign_keys_and_integrity_are_enforced(self) -> None:
        health = self.store.health()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["schema_version"], 2)
        self.assertEqual(health["foreign_key_check"], "ok")
        self.assertEqual(health["foreign_key_violations"], 0)
        snapshot = self.store.snapshot_schema()
        names = {item["name"] for item in snapshot["objects"]}
        self.assertTrue({"content", "user_relation", "artifact", "outbox_event", "media_lease"} <= names)
        connection = sqlite3.connect(self.paths.database)
        try:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO classification_artifact(classification_id, artifact_id) VALUES ('missing', 'missing')"
                )
        finally:
            connection.close()

    def test_eighty_items_are_idempotent_across_two_runs(self) -> None:
        first = [self._ingest(index) for index in range(80)]
        first_digest = self.store.logical_digest()
        second = [self._ingest(index) for index in range(80)]
        self.assertTrue(all(item["content"] == "inserted" for item in first))
        self.assertTrue(all(item["content"] == "unchanged" for item in second))
        self.assertEqual(self.store.logical_digest(), first_digest)
        counts = self.store.counts()
        self.assertEqual(counts["content"], 80)
        self.assertEqual(counts["user_relation"], 80)
        self.assertEqual(counts["source_observation"], 80)
        self.assertEqual(counts["artifact"], 80)

    def test_one_hundred_concurrent_duplicates_create_one_record_set(self) -> None:
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(lambda _: self._ingest(700), range(100)))
        self.assertEqual(sum(item["content"] == "inserted" for item in results), 1)
        self.assertEqual(sum(item["content"] == "unchanged" for item in results), 99)
        counts = self.store.counts()
        self.assertEqual(counts["content"], 1)
        self.assertEqual(counts["user_relation"], 1)
        self.assertEqual(counts["source_observation"], 1)
        self.assertEqual(counts["artifact"], 1)

    def test_conflicting_content_and_artifact_versions_fail_closed(self) -> None:
        self._ingest(1)
        with self.assertRaises(X2NRuntimeError) as content_error:
            self.store.ingest_bundle(synthetic_content(1, title_suffix=" conflict"))
        self.assertEqual(content_error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        content = synthetic_content(1)
        artifact = synthetic_artifact(content, 1)
        conflicting = artifact.model_copy(update={"artifact_id": "art_conflict001"})
        with self.assertRaises(X2NRuntimeError) as artifact_error:
            self.store.ingest_bundle(content, artifacts=(conflicting,))
        self.assertEqual(artifact_error.exception.code, ErrorCode.ARTIFACT_VERSION_CONFLICT)

    def test_append_only_and_physical_delete_triggers_block_raw_mutation(self) -> None:
        self._ingest(2)
        connection = sqlite3.connect(self.paths.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE artifact SET processor = 'changed' WHERE artifact_id = 'art_synthetic00002'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM content WHERE content_key = ?", (synthetic_content(2).content_key,))
        finally:
            connection.close()

    def test_owner_taxonomy_and_classification_are_fk_bound_and_append_only(self) -> None:
        content = synthetic_content(3)
        artifact = synthetic_artifact(content, 3)
        self.store.ingest_bundle(content, artifacts=(artifact,))
        category = _model(
            TaxonomyCategory,
            {
                "schema_version": "1.0",
                "category_id": "11111111-1111-4111-8111-111111111111",
                "name": "Synthetic category",
                "slug": "synthetic-category",
                "description": "Owner-created synthetic top-level category.",
                "aliases": [],
                "positive_examples": [],
                "negative_examples": [],
                "priority": 1,
                "enabled": True,
                "version": 1,
                "level": 1,
                "created_by": "owner",
            },
        )
        self.assertEqual(self.store.put_taxonomy_category(category), WriteDisposition.INSERTED)
        classification = _model(
            Classification,
            {
                "schema_version": "1.0",
                "classification_id": "class_synthetic00003",
                "content_key": content.content_key,
                "taxonomy_version": 1,
                "primary_category_id": str(category.category_id),
                "tags": ["synthetic"],
                "candidate_ranking": [{"category_id": str(category.category_id), "calibrated_score": 1.0}],
                "decision_mode": "human",
                "confidence_raw": 1.0,
                "calibration_bucket": "owner",
                "evidence_artifact_ids": [artifact.artifact_id],
                "explanation_private_ref": None,
                "review_status": "owner_confirmed",
                "created_at": "2026-07-20T00:04:00Z",
                "supersedes_classification_id": None,
            },
        )
        self.assertEqual(self.store.append_classification(classification), WriteDisposition.INSERTED)
        self.assertEqual(self.store.append_classification(classification), WriteDisposition.UNCHANGED)
        connection = sqlite3.connect(self.paths.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE taxonomy_category SET created_by = 'ai'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM classification")
        finally:
            connection.close()

    def test_request_ledger_returns_existing_job_and_rejects_conflict(self) -> None:
        payload_hash = _sha("request-payload")
        first = self.store.record_request("request-001", payload_hash, "job-001")
        second = self.store.record_request("request-001", payload_hash, "ignored-job")
        self.assertEqual(first, (DuplicateDisposition.NEW_REQUEST, "job-001"))
        self.assertEqual(second, (DuplicateDisposition.RETURN_EXISTING_JOB, "job-001"))
        with self.assertRaises(X2NRuntimeError) as conflict:
            self.store.record_request("request-001", _sha("different"), "job-002")
        self.assertEqual(conflict.exception.code, ErrorCode.NATIVE_DUPLICATE_REQUEST)

    def test_outbox_is_idempotent_leased_and_receipted_atomically(self) -> None:
        content = synthetic_content(4)
        self.store.ingest_bundle(content)
        projection = _sha("projection")
        first = self.store.enqueue_outbox(
            sink="markdown",
            content_key=content.content_key,
            desired_projection_hash=projection,
            sink_schema_version="1.0",
            now="2026-07-20T00:05:00Z",
        )
        second = self.store.enqueue_outbox(
            sink="markdown",
            content_key=content.content_key,
            desired_projection_hash=projection,
            sink_schema_version="1.0",
            now="2026-07-20T00:05:00Z",
        )
        self.assertEqual(first[0], WriteDisposition.INSERTED)
        self.assertEqual(second, (WriteDisposition.UNCHANGED, first[1]))
        claim = self.store.claim_outbox(worker_id="worker-001", now="2026-07-20T00:06:00Z")
        self.assertIsNotNone(claim)
        assert claim is not None
        receipt = _model(
            SinkReceipt,
            {
                "schema_version": "1.0",
                "receipt_id": "receipt_markdown004",
                "sink_key": build_sink_key("markdown", content.content_key, "1.0"),
                "sink": "markdown",
                "content_key": content.content_key,
                "sink_schema_version": "1.0",
                "desired_projection_hash": projection,
                "output_hash": _sha("markdown-output"),
                "sink_object_ref": "sinkref_markdown004",
                "external_ref_hash": None,
                "status": "verified",
                "delivered_at": "2026-07-20T00:07:00Z",
                "run_id": "run_sink004",
            },
        )
        self.assertEqual(self.store.complete_outbox(claim, receipt), WriteDisposition.INSERTED)
        self.assertIsNone(self.store.claim_outbox(worker_id="worker-001", now="2026-07-20T00:08:00Z"))
        counts = self.store.counts()
        self.assertEqual(counts["outbox_event"], 1)
        self.assertEqual(counts["sink_receipt"], 1)

    def test_expired_outbox_and_media_leases_are_recoverable_without_deleting_content(self) -> None:
        content = synthetic_content(5)
        self.store.ingest_bundle(content)
        self.store.enqueue_outbox(
            sink="notion",
            content_key=content.content_key,
            desired_projection_hash=_sha("notion-projection"),
            sink_schema_version="1.0",
            now="2026-07-20T00:00:00Z",
        )
        self.store.claim_outbox(worker_id="worker-lease", now="2026-07-20T00:00:00Z", lease_seconds=1)
        self.store.create_media_lease(
            run_id="run_media005",
            content_key=content.content_key,
            purpose="synthetic",
            content_hash=_sha("media-placeholder"),
            mime="application/octet-stream",
            size_bytes=0,
            duration_seconds=None,
            ttl_seconds=1,
            now="2026-07-20T00:00:00Z",
        )
        before = self.store.recovery_plan(now="2026-07-20T00:00:02Z")
        self.assertEqual(before.expired_outbox_leases, 1)
        self.assertEqual(before.expired_media_leases, 1)
        after = self.store.apply_recovery(now="2026-07-20T00:00:02Z")
        self.assertEqual(after.expired_outbox_leases, 0)
        self.assertEqual(after.expired_media_leases, 0)
        self.assertEqual(self.store.counts()["content"], 1)

    def test_migration_downgrade_requires_verified_backup_and_restore_recovers_all_rows(self) -> None:
        for index in range(20):
            self._ingest(index)
        self.store.enqueue_outbox(
            sink="markdown",
            content_key=synthetic_content(0).content_key,
            desired_projection_hash=_sha("projection-before-downgrade"),
            sink_schema_version="1.0",
        )
        before_digest = self.store.logical_digest()
        before_counts = self.store.counts()
        receipt = self.store.downgrade_with_backup(1)
        self.assertEqual(self.store.health()["schema_version"], 1)
        self.store.restore(receipt.backup_id, expected_sha256=receipt.database_sha256)
        self.assertEqual(self.store.health()["schema_version"], 2)
        self.assertEqual(self.store.counts(), before_counts)
        self.assertEqual(self.store.logical_digest(), before_digest)

    def test_backup_hash_fault_is_rejected_without_mutating_live_store(self) -> None:
        self._ingest(6)
        before = self.store.logical_digest()
        receipt = self.store.backup(label="fault")
        backup_path = self.paths.backups_directory / f"canonical-{receipt.backup_id}.sqlite"
        with backup_path.open("ab") as handle:
            handle.write(b"fault")
        with self.assertRaises(X2NRuntimeError) as error:
            self.store.restore(receipt.backup_id, expected_sha256=receipt.database_sha256)
        self.assertEqual(error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        self.assertEqual(self.store.logical_digest(), before)

    def test_ten_thousand_record_backup_restore_has_zero_loss(self) -> None:
        result = self.store.ingest_contents(synthetic_content(index + 10_000) for index in range(10_000))
        self.assertEqual(result, {"inserted": 10_000, "updated": 0, "unchanged": 0})
        before_digest = self.store.logical_digest()
        receipt = self.store.backup(label="scale")
        self.assertEqual(receipt.table_counts["content"], 10_000)
        self.store.ingest_bundle(synthetic_content(10_000, record_version=2, title_suffix=" revised"))
        self.assertNotEqual(self.store.logical_digest(), before_digest)
        self.store.restore(receipt.backup_id, expected_sha256=receipt.database_sha256)
        self.assertEqual(self.store.counts()["content"], 10_000)
        self.assertEqual(self.store.logical_digest(), before_digest)
        self.assertEqual(self.store.health()["integrity_check"], "ok")


if __name__ == "__main__":
    unittest.main()
