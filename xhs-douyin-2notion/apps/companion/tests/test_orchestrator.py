from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest import mock

from x2n_contracts import ErrorCode, canonical_json_sha256
from x2n_contracts.models import CaptureCurrentPayload

from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.native_host import DEVELOPMENT_EXTENSION_ORIGIN, dispatch_wire
from x2n_companion.orchestrator import (
    TRANSITION_AFTER_CANONICAL,
    TRANSITION_AFTER_COMPLETE,
    TRANSITION_BEFORE_CANONICAL,
    CurrentPageOrchestrator,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLATFORMS = ("xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao")


class InjectedKill(RuntimeError):
    pass


def _content_id(platform: str, index: int) -> str:
    if platform == "taobao":
        return f"9900000000000{index:06d}"
    return f"synthetic-{platform}-{index:05d}"


def _page_url(platform: str, content_id: str) -> str:
    values = {
        "bilibili": f"https://www.bilibili.com/video/{content_id}",
        "douyin": f"https://www.douyin.com/video/{content_id}",
        "kuaishou": f"https://www.kuaishou.com/short-video/{content_id}",
        "taobao": "https://item.taobao.com/item.htm",
        "weibo": f"https://www.weibo.com/detail/{content_id}",
        "xiaohongshu": f"https://www.xiaohongshu.com/explore/{content_id}",
    }
    return values[platform]


def _payload(index: int, *, title_suffix: str = "") -> CaptureCurrentPayload:
    platform = PLATFORMS[index % len(PLATFORMS)]
    content_id = _content_id(platform, index)
    title = None if index % 7 == 0 else f"Synthetic title {index}{title_suffix}"
    value = {
        "auto_scroll": False,
        "category_id": None,
        "change_account_state": False,
        "page_context": {
            "content_id": content_id,
            "content_type": "image_gallery" if platform == "taobao" else "video",
            "title": title,
        },
        "page_url": _page_url(platform, content_id),
        "platform": platform,
        "relation": "saved_current",
        "user_gesture": True,
    }
    return CaptureCurrentPayload.model_validate_json(json.dumps(value, ensure_ascii=False))


def _request_id(index: int, *, variant: str = "base") -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-s004:{variant}:{index}"))


def _wire(action: str, payload: dict[str, Any], *, request_id: str) -> bytes:
    value = {
        "action": action,
        "payload": payload,
        "payload_hash": canonical_json_sha256(payload),
        "request_id": request_id,
        "schema_version": "1.0",
        "sent_at": "2026-07-22T00:00:00Z",
    }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-s004-orchestrator-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths, busy_timeout_ms=30_000)
        self.store.initialize()
        self.orchestrator = CurrentPageOrchestrator(self.store, clock=lambda: "2026-07-22T00:00:00Z")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _execute(
        self,
        index: int,
        *,
        variant: str = "base",
        transition_hook: Any = None,
        title_suffix: str = "",
    ) -> Any:
        payload = _payload(index, title_suffix=title_suffix)
        payload_hash = canonical_json_sha256(payload.model_dump(mode="json", by_alias=True))
        return self.orchestrator.execute(
            payload,
            request_id=_request_id(index, variant=variant),
            payload_hash=payload_hash,
            transition_hook=transition_hook,
        )

    def test_six_platform_state_machine_and_receipts_are_redacted(self) -> None:
        receipts = [self._execute(index) for index in range(6)]
        self.assertEqual({receipt.state for receipt in receipts}, {"succeeded"})
        self.assertEqual({receipt.disposition.value for receipt in receipts}, {"new_request"})
        counts = self.store.counts()
        for table in ("artifact", "checkpoint", "content", "request_ledger", "run_record", "source_observation", "user_relation"):
            self.assertEqual(counts[table], 6, table)
        for index, receipt in enumerate(receipts):
            safe = receipt.safe_dict()
            rendered = json.dumps(safe, ensure_ascii=False, sort_keys=True)
            self.assertEqual(safe["state"], "succeeded")
            self.assertEqual(safe["entity_counts"]["artifact_placeholder"], 1)
            self.assertEqual(set(safe["downstream"].values()), {"DOWNSTREAM_NOT_RUN"})
            self.assertNotIn("https://", rendered)
            self.assertNotIn(_content_id(PLATFORMS[index], index), rendered)
            self.assertNotIn(str(self.root), rendered)

    def test_eighty_inputs_replayed_twice_have_no_duplicate_entities(self) -> None:
        first = [self._execute(index) for index in range(80)]
        second = [self._execute(index) for index in range(80)]
        self.assertEqual(sum(item.disposition.value == "new_request" for item in first), 80)
        self.assertEqual(sum(item.disposition.value == "return_existing_job" for item in second), 80)
        self.assertEqual([item.job_id for item in first], [item.job_id for item in second])
        counts = self.store.counts()
        for table in ("artifact", "checkpoint", "content", "request_ledger", "run_record", "source_observation", "user_relation"):
            self.assertEqual(counts[table], 80, table)
        self.assertEqual(self.store.health()["status"], "healthy")

    def test_one_hundred_concurrent_duplicates_create_one_complete_graph(self) -> None:
        def execute(_: int) -> Any:
            return self._execute(3)

        with ThreadPoolExecutor(max_workers=12) as executor:
            receipts = list(executor.map(execute, range(100)))
        self.assertEqual(len({item.job_id for item in receipts}), 1)
        self.assertEqual(sum(item.disposition.value == "new_request" for item in receipts), 1)
        self.assertEqual(sum(item.disposition.value == "return_existing_job" for item in receipts), 99)
        self.assertEqual({item.state for item in receipts}, {"succeeded"})
        counts = self.store.counts()
        for table in ("artifact", "checkpoint", "content", "request_ledger", "run_record", "source_observation", "user_relation"):
            self.assertEqual(counts[table], 1, table)

    def test_kill_before_canonical_commit_leaves_no_partial_graph(self) -> None:
        def kill(transition: str) -> None:
            if transition == TRANSITION_BEFORE_CANONICAL:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            self._execute(1, transition_hook=kill)
        counts = self.store.counts()
        for table in ("artifact", "checkpoint", "content", "request_ledger", "run_record", "source_observation", "user_relation"):
            self.assertEqual(counts[table], 0, table)
        self.assertEqual(self._execute(1).state, "succeeded")

    def test_kill_inside_canonical_transaction_rolls_back_every_row(self) -> None:
        with (
            mock.patch.object(self.store, "_append_observation", side_effect=InjectedKill("inside_transaction")),
            self.assertRaises(InjectedKill),
        ):
            self._execute(2)
        counts = self.store.counts()
        for table in ("artifact", "checkpoint", "content", "request_ledger", "run_record", "source_observation", "user_relation"):
            self.assertEqual(counts[table], 0, table)
        self.assertEqual(self._execute(2).state, "succeeded")

    def test_kill_after_canonical_commit_resumes_without_payload(self) -> None:
        def kill(transition: str) -> None:
            if transition == TRANSITION_AFTER_CANONICAL:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            self._execute(4, transition_hook=kill)
        jobs = self.store.resumable_current_page_jobs()
        self.assertEqual(len(jobs), 1)
        running = self.store.current_page_receipt(jobs[0])
        self.assertEqual((running.state, running.transition), ("running", "canonical_committed"))
        resumed = self.orchestrator.resume(jobs[0])
        self.assertEqual((resumed.state, resumed.transition), ("succeeded", "artifact_placeholder_committed"))
        self.assertEqual(self.store.resumable_current_page_jobs(), ())

    def test_kill_after_completion_replay_returns_existing_complete_job(self) -> None:
        def kill(transition: str) -> None:
            if transition == TRANSITION_AFTER_COMPLETE:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            self._execute(5, transition_hook=kill)
        replay = self._execute(5)
        self.assertEqual(replay.state, "succeeded")
        self.assertEqual(replay.disposition.value, "return_existing_job")
        self.assertEqual(self.store.counts()["artifact"], 1)

    def test_get_job_resumes_a_canonical_committed_run(self) -> None:
        def kill(transition: str) -> None:
            if transition == TRANSITION_AFTER_CANONICAL:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            self._execute(0, transition_hook=kill)
        job_id = self.store.resumable_current_page_jobs()[0]
        response = dispatch_wire(
            _wire("get_job", {"job_id": job_id}, request_id=str(uuid.uuid4())),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertTrue(response.accepted)
        self.assertEqual(response.status.value, "completed")
        self.assertEqual(str(response.job_id), job_id)

    def test_provenance_trace_links_every_scoped_entity(self) -> None:
        receipt = self._execute(3)
        connection = sqlite3.connect(self.paths.database)
        connection.row_factory = sqlite3.Row
        try:
            observation = connection.execute(
                "SELECT observation_id, content_key, adapter_name, adapter_version, run_id FROM source_observation"
            ).fetchone()
            relation = connection.execute("SELECT relation_key, content_key FROM user_relation").fetchone()
            artifact = connection.execute("SELECT artifact_id, content_key, private_payload_present FROM artifact").fetchone()
            run = connection.execute("SELECT run_id, state FROM run_record").fetchone()
            classification_count = int(connection.execute("SELECT COUNT(*) FROM classification").fetchone()[0])
            outbox_count = int(connection.execute("SELECT COUNT(*) FROM outbox_event").fetchone()[0])
            sink_count = int(connection.execute("SELECT COUNT(*) FROM sink_receipt").fetchone()[0])
        finally:
            connection.close()
        self.assertEqual(observation["run_id"], run["run_id"])
        self.assertEqual(observation["content_key"], relation["content_key"])
        self.assertEqual(observation["content_key"], artifact["content_key"])
        self.assertEqual(run["state"], "succeeded")
        self.assertEqual(artifact["private_payload_present"], 0)
        self.assertEqual(
            receipt.content_ref_sha256,
            hashlib.sha256(str(observation["content_key"]).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            receipt.relation_ref_sha256,
            hashlib.sha256(str(relation["relation_key"]).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            receipt.observation_ref_sha256,
            hashlib.sha256(str(observation["observation_id"]).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            receipt.artifact_ref_sha256,
            hashlib.sha256(str(artifact["artifact_id"]).encode("utf-8")).hexdigest(),
        )
        self.assertEqual((classification_count, outbox_count, sink_count), (0, 0, 0))

    def test_new_observation_updates_content_relation_and_appends_evidence(self) -> None:
        first = self._execute(1)
        second_orchestrator = CurrentPageOrchestrator(self.store, clock=lambda: "2026-07-22T00:00:01Z")
        payload = _payload(1, title_suffix=" changed")
        second = second_orchestrator.execute(
            payload,
            request_id=_request_id(1, variant="changed"),
            payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
        )
        self.assertNotEqual(first.job_id, second.job_id)
        connection = sqlite3.connect(self.paths.database)
        try:
            version = int(connection.execute("SELECT record_version FROM content").fetchone()[0])
            artifact_sequences = [row[0] for row in connection.execute(
                "SELECT artifact_sequence FROM artifact ORDER BY artifact_sequence"
            ).fetchall()]
        finally:
            connection.close()
        self.assertEqual(version, 2)
        self.assertEqual(artifact_sequences, [1, 2])
        counts = self.store.counts()
        self.assertEqual(counts["content"], 1)
        self.assertEqual(counts["user_relation"], 1)
        self.assertEqual(counts["source_observation"], 2)
        self.assertEqual(counts["artifact"], 2)

    def test_category_and_mismatched_page_identity_fail_closed_without_writes(self) -> None:
        category = _payload(1).model_dump(mode="json")
        category["category_id"] = str(uuid.uuid4())
        category_payload = CaptureCurrentPayload.model_validate_json(json.dumps(category))
        with self.assertRaises(X2NRuntimeError) as blocked:
            self.orchestrator.execute(
                category_payload,
                request_id=_request_id(1),
                payload_hash=canonical_json_sha256(category),
            )
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

        mismatched = _payload(2).model_dump(mode="json")
        mismatched["page_context"]["content_id"] = "synthetic-bilibili-mismatch"
        mismatch_payload = CaptureCurrentPayload.model_validate_json(json.dumps(mismatched))
        with self.assertRaises(X2NRuntimeError) as invalid:
            self.orchestrator.execute(
                mismatch_payload,
                request_id=_request_id(2),
                payload_hash=canonical_json_sha256(mismatched),
            )
        self.assertEqual(invalid.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        self.assertEqual(self.store.counts()["request_ledger"], 0)


if __name__ == "__main__":
    unittest.main()
