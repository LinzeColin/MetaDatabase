from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from x2n_contracts import (
    CanonicalContent,
    ErrorCode,
    SourceObservation,
    UserRelation,
    build_content_key,
    build_relation_key,
)

from x2n_companion import lifecycle
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.lifecycle import (
    ARCHIVE_CHUNK_MAX_BYTES,
    LIFECYCLE_DELETE_CONFIRMATION,
    PRIVATE_DOMAIN,
    PRIVATE_RESTORE_CONFIRMATION,
    RUNTIME_WIPE_CONFIRMATION,
    RUNTIME_WIPE_REQUEST_CONFIRMATION,
    TIME_MACHINE_CONFIRMATION,
    DigestPinnedPrivateDbClient,
    LifecycleService,
    LifecycleTtlPolicy,
    PrivateObject,
)
from x2n_companion.runtime import REQUIRED_DIRECTORIES, RuntimePaths, X2NRuntimeError
from x2n_companion.runtime_cli import build_parser, run


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = "2026-07-29T00:00:00Z"


def _sha(value: str | bytes) -> str:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _model(model: object, payload: dict[str, object]) -> object:
    return model.model_validate_json(json.dumps(payload, ensure_ascii=False))  # type: ignore[union-attr]


def _content(index: int, *, record_version: int = 1) -> CanonicalContent:
    content_id = f"lifecycle-{index:05d}"
    return _model(
        CanonicalContent,
        {
            "author_name": "Synthetic lifecycle author",
            "author_platform_id": "synthetic-lifecycle-author",
            "canonical_source_url": f"https://www.xiaohongshu.com/explore/{content_id}",
            "content_hash": _sha(f"content:{index}:{record_version}"),
            "content_key": build_content_key("xiaohongshu", content_id),
            "content_type": "video",
            "description": "Synthetic private-runtime lifecycle payload.",
            "first_observed_at": NOW,
            "last_observed_at": NOW,
            "platform": "xiaohongshu",
            "platform_content_id": content_id,
            "published_at": None,
            "record_version": record_version,
            "schema_version": "1.0",
            "status": "active",
            "title": f"Synthetic lifecycle title {index}",
        },
    )  # type: ignore[return-value]


def _relation(content: CanonicalContent, index: int) -> UserRelation:
    account = _sha("synthetic-lifecycle-account")
    return _model(
        UserRelation,
        {
            "account_ref_hash": account,
            "confirmed_by": "scan",
            "content_key": content.content_key,
            "first_seen_at": NOW,
            "last_seen_at": NOW,
            "relation_key": build_relation_key(account, content.content_key, "saved_current"),
            "relation_type": "saved_current",
            "scan_receipt_id": f"receipt_lifecycle{index:05d}",
            "schema_version": "1.0",
            "source_collection_id": None,
            "source_collection_name_private": None,
            "status": "active",
        },
    )  # type: ignore[return-value]


def _observation(content: CanonicalContent, index: int) -> SourceObservation:
    return _model(
        SourceObservation,
        {
            "adapter_name": "synthetic-lifecycle-adapter",
            "adapter_version": "1.0.0",
            "completeness": 1.0,
            "content_key": content.content_key,
            "ephemeral_media_ref_ids": [],
            "field_provenance": [
                {"confidence": 1.0, "field": "platform_content_id", "source": "dom", "status": "present"},
            ],
            "normalized_fields": ["platform_content_id"],
            "observation_id": f"obs_lifecycle{index:05d}",
            "observed_at": NOW,
            "raw_text_hash": _sha(f"raw:{index}"),
            "run_id": f"run_lifecycle{index:05d}",
            "schema_version": "1.0",
            "source_method": "current_page",
            "warning_codes": [],
        },
    )  # type: ignore[return-value]


class FakePrivateDbTransport:
    """In-memory client double; no auth, subprocess, filesystem service, or network."""

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.get_outputs: list[Path] = []
        self.missing: set[str] = set()
        self.objects: dict[str, bytes] = {}
        self.records: list[dict[str, str]] = []

    def add_foreign_missing_object(self) -> None:
        payload_sha = _sha("same-private-payload-in-another-domain")
        self.records.append(
            {
                "domain": "unrelated-project",
                "object_path": f"objects/{payload_sha[:2]}/{payload_sha}_foreign-object.bin",
                "original_name": "foreign-object.bin",
                "sha256": payload_sha,
            }
        )

    def ingest(self, local: Path, *, opaque_name: str, batch: str) -> PrivateObject:
        self.calls["ingest"] += 1
        self._assert_batch(batch)
        self._assert_private_file(local)
        if local.name != opaque_name:
            raise AssertionError("opaque lifecycle name diverged")
        payload = local.read_bytes()
        digest = _sha(payload)
        object_path = f"objects/{digest[:2]}/{digest}_{opaque_name}"
        receipt = PrivateObject(
            object_sha256=digest,
            object_path=object_path,
            opaque_name=opaque_name,
            size_bytes=len(payload),
        )
        self.objects[object_path] = payload
        self.records.append(
            {
                "domain": PRIVATE_DOMAIN,
                "object_path": object_path,
                "original_name": opaque_name,
                "sha256": digest,
            }
        )
        return receipt

    def get(self, object_path: str, output: Path) -> None:
        self.calls["get"] += 1
        self.get_outputs.append(output)
        if object_path == "manifest.jsonl":
            payload = b"".join(
                (json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
                for item in self.records
            )
        elif object_path in self.missing or object_path not in self.objects:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Synthetic Private-MetaDatabase object is absent")
        else:
            payload = self.objects[object_path]
        if output.exists() or output.is_symlink():
            raise AssertionError("lifecycle get output must be new")
        output.write_bytes(payload)
        output.chmod(0o600)

    def list(self) -> None:
        self.calls["list"] += 1

    def verify(self) -> None:
        # Deliberately advisory: a foreign missing object never blocks x2n's
        # own exact-domain manifest verification.
        self.calls["verify"] += 1

    def attestation(self) -> dict[str, object]:
        return {
            "auth_mutations": 0,
            "command_allowlist": ["get", "ingest", "list", "verify"],
            "commands_invoked": dict(sorted(self.calls.items())),
            "token_value_contact": 0,
        }

    @staticmethod
    def _assert_batch(batch: str) -> None:
        if not batch.startswith("snapshot_"):
            raise AssertionError("unexpected lifecycle batch")

    @staticmethod
    def _assert_private_file(path: Path) -> None:
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600:
            raise AssertionError("lifecycle transfer input is not private")


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-lifecycle-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.paths = RuntimePaths.from_values(
            str(self.destination / "xhs-douyin-2notion"),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()
        self.service = LifecycleService(self.store, ttl=LifecycleTtlPolicy(workspace_seconds=60))
        self.transport = FakePrivateDbTransport()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _ingest(self, index: int, *, record_version: int = 1) -> tuple[CanonicalContent, UserRelation]:
        content = _content(index, record_version=record_version)
        relation = _relation(content, index)
        self.store.ingest_bundle(content, relation=relation, observations=(_observation(content, index),))
        return content, relation

    def _remove_active_database(self) -> None:
        for path in (self.paths.database, Path(f"{self.paths.database}-wal"), Path(f"{self.paths.database}-shm")):
            if path.exists() or path.is_symlink():
                path.unlink()

    def _assert_no_workspace_or_get_leak(self) -> None:
        lifecycle_root = self.paths.data_root / "runtime/lifecycle"
        self.assertEqual(list(lifecycle_root.iterdir()), [])
        self.assertTrue(all(not output.exists() for output in self.transport.get_outputs))

    def test_domain_bound_export_verifies_and_restores_after_local_working_loss(self) -> None:
        self._ingest(1)
        self._ingest(2)
        self.transport.add_foreign_missing_object()

        exported = self.service.export_and_verify(self.transport, now=NOW)
        self.assertEqual(exported["durability"]["durability_state"], "durability_verified")
        self.assertEqual(exported["attestation"]["token_value_contact"], 0)
        self.assertEqual(self.transport.calls["verify"], 1)
        self.assertTrue(self.transport.objects)
        self.assertTrue(all(len(payload) <= ARCHIVE_CHUNK_MAX_BYTES for payload in self.transport.objects.values()))
        self._assert_no_workspace_or_get_leak()

        self._remove_active_database()
        self.assertEqual(self.service.status()["active_sqlite"], "missing_durability_pending_recovery")
        restored = self.service.restore_latest(self.transport, confirmation=PRIVATE_RESTORE_CONFIRMATION)
        self.assertEqual(restored["durability"]["durability_state"], "durability_verified")
        self.assertEqual(self.store.counts()["content"], 2)
        self._assert_no_workspace_or_get_leak()

    def test_missing_exact_domain_object_fails_closed_while_foreign_manifest_defects_do_not_leak(self) -> None:
        self._ingest(3)
        self.transport.add_foreign_missing_object()
        self.service.export_and_verify(self.transport, now=NOW)
        archive_path = next(path for path in self.transport.objects if path.endswith(".bin"))
        self.transport.missing.add(archive_path)

        with self.assertRaises(X2NRuntimeError) as blocked:
            self.service.restore_latest(self.transport, confirmation=PRIVATE_RESTORE_CONFIRMATION)
        self.assertEqual(blocked.exception.code, ErrorCode.STORAGE_FAILED)
        self._assert_no_workspace_or_get_leak()

    def test_preview_cancel_relation_and_content_tombstones_do_not_physically_delete_or_resurrect(self) -> None:
        content, relation = self._ingest(4)
        preview = self.service.delete_preview(target_kind="relation", target_key_private=relation.relation_key)
        self.assertEqual((preview["relation_rows"], preview["content_rows"]), (1, 0))
        with self.assertRaises(X2NRuntimeError) as cancelled:
            self.service.confirm_delete(
                target_kind="relation",
                target_key_private=relation.relation_key,
                confirmation="wrong",
                now=NOW,
            )
        self.assertEqual(cancelled.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(self.store.lifecycle_state().deletion_epoch, 0)

        relation_deleted = self.service.confirm_delete(
            target_kind="relation",
            target_key_private=relation.relation_key,
            confirmation=LIFECYCLE_DELETE_CONFIRMATION,
            now=NOW,
        )
        self.assertEqual(relation_deleted["tombstone"]["target_kind"], "relation")
        connection = sqlite3.connect(self.paths.database)
        try:
            relation_state = connection.execute(
                "SELECT status, confirmed_by FROM user_relation WHERE relation_key = ?", (relation.relation_key,)
            ).fetchone()
            content_state = connection.execute(
                "SELECT status FROM content WHERE content_key = ?", (content.content_key,)
            ).fetchone()
            self.assertEqual(relation_state, ("removed", "owner"))
            self.assertEqual(content_state, ("active",))
        finally:
            connection.close()

        content_deleted = self.service.confirm_delete(
            target_kind="content",
            target_key_private=content.content_key,
            confirmation=LIFECYCLE_DELETE_CONFIRMATION,
            now="2026-07-29T00:00:01Z",
        )
        self.assertEqual(content_deleted["durable_hard_erase"], "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED")
        self.assertEqual(self.store.lifecycle_state().deletion_epoch, 2)
        connection = sqlite3.connect(self.paths.database)
        try:
            self.assertEqual(
                connection.execute("SELECT status FROM content WHERE content_key = ?", (content.content_key,)).fetchone(),
                ("deleted_by_user",),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM content WHERE content_key = ?", (content.content_key,))
        finally:
            connection.close()
        replay = self.store.ingest_bundle(
            _content(4, record_version=2),
            relation=_relation(_content(4, record_version=2), 4),
            observations=(_observation(_content(4, record_version=2), 4),),
        )
        self.assertEqual(replay["content"], "unchanged")

    def test_restore_cannot_regress_deletion_epoch_and_verified_runtime_wipe_needs_tombstone_manifest(self) -> None:
        content, _ = self._ingest(5)
        self.service.export_and_verify(self.transport, now=NOW)
        self.service.confirm_delete(
            target_kind="content",
            target_key_private=content.content_key,
            confirmation=LIFECYCLE_DELETE_CONFIRMATION,
            now="2026-07-29T00:00:01Z",
        )
        with self.assertRaises(X2NRuntimeError) as stale:
            self.service.restore_latest(self.transport, confirmation=PRIVATE_RESTORE_CONFIRMATION)
        self.assertEqual(stale.exception.code, ErrorCode.POLICY_BLOCKED)

        self.service.request_runtime_wipe(
            confirmation=RUNTIME_WIPE_REQUEST_CONFIRMATION,
            now="2026-07-29T00:00:02Z",
        )
        self.service.export_and_verify(self.transport, now="2026-07-29T00:00:03Z")
        wiped = self.service.apply_verified_runtime_wipe(confirmation=RUNTIME_WIPE_CONFIRMATION)
        self.assertEqual(wiped["active_sqlite"], "removed_local_only")
        self.assertEqual(self.service.recovery_plan()["action"], "restore_latest_requires_explicit_confirmation")

    def test_ttl_client_rejections_tmutil_contract_and_cli_status_are_safe(self) -> None:
        self._ingest(6)
        prepared = self.service._prepare(now=NOW)
        cleaned = self.service.cleanup_expired_workspaces(now="2026-07-29T00:01:01Z")
        self.assertEqual(cleaned["expired_workspaces_deleted"], 1)
        self.assertFalse(prepared.workspace.exists())

        lifecycle_root = self.paths.data_root / "runtime/lifecycle"
        raw_sqlite = lifecycle_root / "x2n-raw.sqlite.bin"
        raw_sqlite.write_bytes(b"SQLite format 3\x00private")
        raw_sqlite.chmod(0o600)
        client = object.__new__(DigestPinnedPrivateDbClient)
        client._actions = []  # type: ignore[attr-defined]
        with self.assertRaises(X2NRuntimeError) as raw_blocked:
            client.ingest(raw_sqlite, opaque_name=raw_sqlite.name, batch="snapshot_" + "a" * 32)
        self.assertEqual(raw_blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        oversized = lifecycle_root / "x2n-oversized.bin"
        oversized.write_bytes(b"xx")
        oversized.chmod(0o600)
        with mock.patch.object(lifecycle, "ARCHIVE_CHUNK_MAX_BYTES", 1):
            with self.assertRaises(X2NRuntimeError) as size_blocked:
                client.ingest(oversized, opaque_name=oversized.name, batch="snapshot_" + "b" * 32)
        self.assertEqual(size_blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        with self.assertRaises(X2NRuntimeError) as put_blocked:
            client._invoke("put", ())  # type: ignore[attr-defined]
        self.assertEqual(put_blocked.exception.code, ErrorCode.POLICY_BLOCKED)

        self.assertEqual(
            self.service.apply_time_machine_exclusion(
                confirmation=TIME_MACHINE_CONFIRMATION,
                system_name=lambda: "Linux",
            )["status"],
            "UNSUPPORTED_OS_FAIL_CLOSED",
        )
        tmutil_commands: list[tuple[str, ...]] = []

        def fake_tmutil(command: object) -> tuple[int, bytes]:
            rendered = tuple(command)  # type: ignore[arg-type]
            tmutil_commands.append(rendered)
            return (0, b"[Excluded]")

        excluded = self.service.apply_time_machine_exclusion(
            confirmation=TIME_MACHINE_CONFIRMATION,
            system_name=lambda: "Darwin",
            runner=fake_tmutil,
        )
        self.assertEqual(excluded["excluded_required_subpaths"], len(REQUIRED_DIRECTORIES))
        self.assertEqual(len(tmutil_commands), len(REQUIRED_DIRECTORIES) + 2)

        environment = {
            "X2N_DATA_ROOT": str(self.paths.data_root),
            "X2N_DOWNLOAD_DESTINATION": str(self.destination),
        }
        with mock.patch.dict(os.environ, environment):
            status = run(build_parser().parse_args(["lifecycle", "status"]))
            self.assertEqual((status["task_id"], status["status"]), ("TSK.x2n.uxops.005", "PASS"))
            with self.assertRaises(X2NRuntimeError) as cli_blocked:
                run(
                    build_parser().parse_args(
                        ["lifecycle", "delete", "--target-kind", "content", "--target-key", "x", "--confirm", "wrong"]
                    )
                )
        self.assertEqual(cli_blocked.exception.code, ErrorCode.POLICY_BLOCKED)


if __name__ == "__main__":
    unittest.main()
