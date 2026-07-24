from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode

from x2n_companion.adapter_guard import AdapterExecutionGate
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.douyin_adapter import (
    DouyinAdapter,
    DouyinBatchCoordinator,
    build_douyin_canary_plan,
)
from x2n_companion.douyin_upstream import (
    BATCH_SCHEMA,
    DouyinBatchRequest,
    LoopbackRestDouyinTransport,
    PinnedDouyinClient,
    SubprocessDouyinTransport,
    decode_response,
    evaluate_shadow_candidate,
    parse_batch,
    synthetic_attestation,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError
from x2n_companion import runtime_cli


PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER = PROJECT_ROOT / "scripts/douyin_sidecar_fixture_worker.py"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "d" * 64


class InjectedKill(BaseException):
    pass


WORKER_SPEC = importlib.util.spec_from_file_location("douyin_sidecar_fixture_worker", WORKER)
assert WORKER_SPEC and WORKER_SPEC.loader
WORKER_MODULE = importlib.util.module_from_spec(WORKER_SPEC)
sys.modules[WORKER_SPEC.name] = WORKER_MODULE
WORKER_SPEC.loader.exec_module(WORKER_MODULE)


def _scan_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters004:{label}"))


def _client(case: str = "normal", *, timeout: float = 2.0, extra: tuple[str, ...] = ()) -> PinnedDouyinClient:
    transport = SubprocessDouyinTransport((sys.executable, "-B", str(WORKER), "--case", case, *extra))
    return PinnedDouyinClient(
        transport,
        expected_build=synthetic_attestation(),
        allow_synthetic=True,
        timeout_seconds=timeout,
    )


class _FixtureHandler(BaseHTTPRequestHandler):
    case = "normal"

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        if self.case == "http_503":
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        response = WORKER_MODULE.response_for(request, self.case)
        payload = json.dumps(response, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *args: Any) -> None:
        return


class DouyinAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-adapters004-")
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

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _rows(self, sql: str, values: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        connection = self.store._open(writable=False)
        try:
            return connection.execute(sql, values).fetchall()
        finally:
            connection.close()

    def _batch(self, mode: str, case: str = "normal", sequence: int = 0):
        request = DouyinBatchRequest(mode=mode, sequence=sequence)  # type: ignore[arg-type]
        _health, batch = _client(case).fetch_owner_batch(request)
        return batch

    def test_health_attests_exact_pin_protocol_storage_and_synthetic_scope(self) -> None:
        health = _client().health()
        safe = health.safe_dict()
        self.assertEqual(safe["upstream_version"], "2.0.0")
        self.assertEqual(safe["persistence_writes"], 0)
        self.assertEqual(safe["build"]["scope"], "ci_synthetic")
        with self.assertRaises(X2NRuntimeError) as blocked:
            PinnedDouyinClient(
                SubprocessDouyinTransport((sys.executable, "-B", str(WORKER))),
                expected_build=synthetic_attestation(),
            )
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_subprocess_normal_likes_and_favorites_are_strict_and_bounded(self) -> None:
        for mode in ("likes", "favorites"):
            with self.subTest(mode=mode):
                request = DouyinBatchRequest(mode=mode, sequence=0)  # type: ignore[arg-type]
                _health, batch = _client().fetch_owner_batch(request)
                self.assertEqual(batch.mode, mode)
                self.assertEqual(len(batch.items), 20)
                self.assertEqual(batch.completion_signal, "bounded_limit_reached")
                self.assertTrue(all(item.collection is None for item in batch.items) if mode == "likes" else True)
                if mode == "favorites":
                    self.assertEqual(len({item.collection.key for item in batch.items if item.collection}), 2)

    def test_schema_pin_and_recursive_safety_failures_block(self) -> None:
        cases = {
            "attestation_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
            "commit_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
            "contract_digest_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
            "envelope_schema_drift": ErrorCode.INVALID_SCHEMA_VERSION,
            "forbidden_field": ErrorCode.POLICY_BLOCKED,
            "license_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
            "lock_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
            "missing_field": ErrorCode.UNKNOWN_FIELD,
            "persistence_enabled": ErrorCode.POLICY_BLOCKED,
            "schema_drift": ErrorCode.INVALID_SCHEMA_VERSION,
            "tree_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
            "unknown_field": ErrorCode.UNKNOWN_FIELD,
            "version_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        }
        for case, expected in cases.items():
            with self.subTest(case=case):
                with self.assertRaises(X2NRuntimeError) as blocked:
                    _client(case).fetch_owner_batch(DouyinBatchRequest(mode="likes", sequence=0))
                self.assertEqual(blocked.exception.code, expected)

    def test_error_exit_timeout_oversize_invalid_json_and_unknown_error_normalize(self) -> None:
        cases = {
            "error_exit": ErrorCode.UNKNOWN_FAILURE,
            "invalid_json": ErrorCode.INVALID_INPUT,
            "oversize": ErrorCode.SECURITY_INJECTION_BLOCKED,
            "timeout": ErrorCode.NETWORK_FAILED,
            "unknown_error": ErrorCode.UNKNOWN_FAILURE,
        }
        for case, expected in cases.items():
            with self.subTest(case=case):
                timeout = 0.05 if case == "timeout" else 2.0
                with self.assertRaises(X2NRuntimeError) as blocked:
                    _client(case, timeout=timeout).fetch_owner_batch(DouyinBatchRequest(mode="likes", sequence=0))
                self.assertEqual(blocked.exception.code, expected)
                self.assertNotIn(str(self.root), str(blocked.exception))

    def test_no_shell_command_or_payload_injection(self) -> None:
        marker = Path(self.temporary.name) / "must-not-exist"
        argument = f";touch {marker}"
        request = DouyinBatchRequest(mode="likes", sequence=0)
        _health, batch = _client(extra=("--sentinel-argument", argument)).fetch_owner_batch(request)
        self.assertEqual(len(batch.items), 20)
        self.assertFalse(marker.exists())
        with self.assertRaises(X2NRuntimeError) as blocked:
            SubprocessDouyinTransport((sys.executable, "bad\nargument"))
        self.assertEqual(blocked.exception.code, ErrorCode.SECURITY_INJECTION_BLOCKED)

    def test_duplicate_json_and_url_or_local_path_values_are_rejected(self) -> None:
        with self.assertRaises(X2NRuntimeError) as duplicate:
            decode_response(b'{"schema_version":"1","schema_version":"2"}')
        self.assertEqual(duplicate.exception.code, ErrorCode.UNKNOWN_FIELD)
        for payload in (
            b'{"title":"https://example.invalid/value"}',
            b'{"title":"' + b"/" + b'home/example/private"}',
            b'{"cover_url":"redacted"}',
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(X2NRuntimeError) as blocked:
                    decode_response(payload)
                self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_boolean_numeric_schema_drift_and_corrupt_cursor_fail_closed(self) -> None:
        request = DouyinBatchRequest(mode="likes", sequence=0, max_items=1)
        envelope = WORKER_MODULE.response_for(request.wire(), "normal")
        for field, value in (("sequence", False), ("max_items", True)):
            with self.subTest(field=field):
                batch = dict(envelope["batch"])
                batch[field] = value
                with self.assertRaises(X2NRuntimeError) as blocked:
                    parse_batch(batch, request=request)
                self.assertEqual(blocked.exception.code, ErrorCode.INVALID_INPUT)

        cursor = DouyinAdapter._initial_cursor("likes", "owner_bounded")
        for field in ("next_sequence", "error_evidence_count"):
            with self.subTest(cursor_field=field):
                corrupt = dict(cursor)
                corrupt[field] = False
                with self.assertRaises(X2NRuntimeError) as blocked:
                    DouyinAdapter._cursor(json.dumps(corrupt))
                self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_scan_graph_state_mismatch_fails_closed(self) -> None:
        adapter = DouyinAdapter(self.store)
        scan_id = _scan_id("graph-state-mismatch")
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            mode="likes",
            scope_mode="owner_bounded",
            started_at=NOW,
        )
        with self.store._transaction() as connection:
            connection.execute(
                "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id LIKE 'run_dy_%'",
                ((NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),),
            )
        for operation in (
            lambda: adapter.begin_scan(
                scan_id,
                account_ref_hash=ACCOUNT_HASH,
                mode="likes",
                scope_mode="owner_bounded",
                started_at=NOW,
            ),
            lambda: adapter.commit_batch(
                scan_id,
                self._batch("likes"),
                observed_at=NOW + timedelta(seconds=2),
            ),
            lambda: adapter.checkpoint(scan_id),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(X2NRuntimeError) as blocked:
                    operation()
                self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_loopback_rest_contract_and_error_mapping(self) -> None:
        for case, expected in (
            ("normal", None),
            ("schema_drift", ErrorCode.INVALID_SCHEMA_VERSION),
            ("http_503", ErrorCode.NETWORK_FAILED),
        ):
            with self.subTest(case=case):
                handler = type("CaseHandler", (_FixtureHandler,), {"case": case})
                server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    client = PinnedDouyinClient(
                        LoopbackRestDouyinTransport(server.server_port),
                        expected_build=synthetic_attestation(),
                        allow_synthetic=True,
                        timeout_seconds=2.0,
                    )
                    if expected is None:
                        _health, batch = client.fetch_owner_batch(DouyinBatchRequest(mode="favorites", sequence=0))
                        self.assertEqual(len(batch.items), 20)
                    else:
                        with self.assertRaises(X2NRuntimeError) as blocked:
                            client.fetch_owner_batch(DouyinBatchRequest(mode="favorites", sequence=0))
                        self.assertEqual(blocked.exception.code, expected)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_twenty_favorites_map_to_two_hashed_collections(self) -> None:
        adapter = DouyinAdapter(self.store)
        scan_id = _scan_id("favorites-20")
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            mode="favorites",
            scope_mode="canary_20",
            started_at=NOW,
        )
        batch = self._batch("favorites")
        receipt = adapter.commit_batch(scan_id, batch, observed_at=NOW + timedelta(seconds=1))
        replay = adapter.commit_batch(scan_id, batch, observed_at=NOW + timedelta(seconds=1))
        self.assertEqual(receipt.checkpoint_state, "complete")
        self.assertEqual(replay.disposition, "replayed")
        self.assertEqual(receipt.relation_count, 20)
        self.assertEqual(receipt.observation_count, 20)
        self.assertEqual(len(self._rows("SELECT * FROM content")), 20)
        relations = self._rows("SELECT relation_type, source_collection_id, status FROM user_relation")
        self.assertEqual({row["relation_type"] for row in relations}, {"favorited"})
        self.assertEqual(len({row["source_collection_id"] for row in relations}), 2)
        self.assertTrue(all(str(row["source_collection_id"]).startswith("x2ncol_") for row in relations))
        self.assertEqual({row["status"] for row in relations}, {"active"})

    def test_twenty_likes_map_without_collection_or_classification(self) -> None:
        adapter = DouyinAdapter(self.store)
        scan_id = _scan_id("likes-20")
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            mode="likes",
            scope_mode="canary_20",
            started_at=NOW,
        )
        receipt = adapter.commit_batch(scan_id, self._batch("likes"), observed_at=NOW + timedelta(seconds=1))
        self.assertEqual(receipt.relation_count, 20)
        relations = self._rows("SELECT relation_type, source_collection_id, status FROM user_relation")
        self.assertEqual({row["relation_type"] for row in relations}, {"liked"})
        self.assertEqual({row["source_collection_id"] for row in relations}, {None})
        self.assertEqual({row["status"] for row in relations}, {"active"})
        self.assertEqual(len(self._rows("SELECT * FROM classification")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM taxonomy_category")), 0)

    def test_injected_kill_rolls_back_batch_checkpoint_and_run_atomically(self) -> None:
        scan_id = _scan_id("fault-rollback")
        stable = DouyinAdapter(self.store)
        stable.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            mode="likes",
            scope_mode="canary_20",
            started_at=NOW,
        )

        def kill(label: str) -> None:
            if label == "before_checkpoint":
                raise InjectedKill()

        with self.assertRaises(InjectedKill):
            DouyinAdapter(self.store, fault_injector=kill).commit_batch(
                scan_id,
                self._batch("likes"),
                observed_at=NOW + timedelta(seconds=1),
            )
        checkpoint = stable.checkpoint(scan_id)
        self.assertEqual(checkpoint.next_sequence, 0)
        self.assertEqual(checkpoint.observed_unique_items, 0)
        self.assertEqual(self.store.counts()["content"], 0)
        self.assertEqual(self.store.counts()["user_relation"], 0)
        self.assertEqual(self.store.counts()["source_observation"], 0)
        self.assertEqual(self._rows("SELECT state FROM run_record")[0]["state"], "running")

        batch = self._batch("likes")
        recovered = stable.commit_batch(scan_id, batch, observed_at=NOW + timedelta(seconds=1))
        replay = stable.commit_batch(scan_id, batch, observed_at=NOW + timedelta(seconds=1))
        self.assertEqual(recovered.checkpoint_state, "complete")
        self.assertEqual(replay.disposition, "replayed")
        self.assertEqual(recovered.observed_unique_items, 20)

    def test_partial_and_empty_batches_never_advance_remove_or_full_scan(self) -> None:
        adapter = DouyinAdapter(self.store)
        empty_scan = _scan_id("empty")
        adapter.begin_scan(
            empty_scan,
            account_ref_hash=ACCOUNT_HASH,
            mode="likes",
            scope_mode="owner_bounded",
            started_at=NOW,
        )
        empty = adapter.commit_batch(
            empty_scan,
            self._batch("likes", "empty_unverified"),
            observed_at=NOW + timedelta(seconds=1),
        )
        self.assertEqual(empty.next_sequence, 0)
        self.assertEqual(empty.checkpoint_state, "active")
        self.assertEqual(len(self._rows("SELECT * FROM user_relation")), 0)

        partial_scan = _scan_id("partial")
        adapter.begin_scan(
            partial_scan,
            account_ref_hash=ACCOUNT_HASH,
            mode="favorites",
            scope_mode="owner_bounded",
            started_at=NOW,
        )
        partial = adapter.commit_batch(
            partial_scan,
            self._batch("favorites", "partial"),
            observed_at=NOW + timedelta(seconds=1),
        )
        self.assertEqual(partial.next_sequence, 0)
        self.assertEqual(partial.checkpoint_state, "active")
        self.assertEqual(partial.relation_count, 19)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'removed'")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'tombstone_candidate'")), 0)
        checkpoints = self._rows("SELECT full_scan_id FROM checkpoint")
        self.assertTrue(all(row["full_scan_id"] is None for row in checkpoints))

    def test_guarded_coordinator_performs_one_owner_batch_without_retry(self) -> None:
        adapter = DouyinAdapter(self.store)
        scan_id = _scan_id("coordinator")
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            mode="likes",
            scope_mode="canary_20",
            started_at=NOW,
        )
        coordinator = DouyinBatchCoordinator(
            adapter,
            _client(),
            AdapterExecutionGate(self.paths),
        )
        receipt = coordinator.apply_owner_action(
            scan_id,
            DouyinBatchRequest(mode="likes", sequence=0),
            observed_at=NOW + timedelta(seconds=1),
            monotonic_batch_time=100.0,
            monotonic_observation_time=101.0,
        )
        self.assertEqual(receipt.relation_count, 20)
        self.assertEqual(receipt.checkpoint_state, "complete")

    def test_nonexecuting_canary_plans_and_fixed_limit(self) -> None:
        for mode in ("favorites", "likes"):
            plan = build_douyin_canary_plan(mode)  # type: ignore[arg-type]
            self.assertEqual(plan["execution"], "NOT_RUN")
            self.assertFalse(plan["production_enabled"])
            self.assertFalse(plan["automatic_pagination"])
            self.assertEqual(plan["max_items"], 20)
        with self.assertRaises(X2NRuntimeError) as blocked:
            build_douyin_canary_plan("likes", 21)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_cli_only_emits_nonexecuting_douyin_canary_plan(self) -> None:
        args = runtime_cli.build_parser().parse_args(
            ["douyin", "canary-plan", "--mode", "favorites", "--max-items", "20"]
        )
        receipt = runtime_cli.run(args)
        self.assertEqual(receipt["task_id"], "TSK.x2n.adapters.004")
        self.assertEqual(receipt["plan"]["execution"], "NOT_RUN")
        self.assertFalse(receipt["plan"]["production_enabled"])
        self.assertEqual(receipt["real_account_execution"], "NOT_RUN")

    def test_shadow_candidate_never_promotes_changed_upstream(self) -> None:
        base = {
            "commit": "ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7",
            "critical_files_match": True,
            "license": "MIT",
            "protocol_version": "1.0.0",
            "resolved_lock_sha256": "1" * 64,
            "sbom_sha256": "2" * 64,
            "transitive_licenses_compatible": True,
            "tree": "ff7774b618f269fcdc750e17dc63612f159b6b46",
            "version": "2.0.0",
        }
        unchanged = evaluate_shadow_candidate(base).safe_dict()
        self.assertEqual(unchanged["status"], "PASS_PIN_UNCHANGED")
        self.assertFalse(unchanged["promotion"])
        changed = dict(base)
        changed.update(
            {
                "commit": "2e373df6fe474368804909f337fd26ee5139ce5d",
                "critical_files_match": False,
                "tree": "faa5b5c700b1eb39a2318cb8867f4ac8898c6fbf",
            }
        )
        decision = evaluate_shadow_candidate(changed).safe_dict()
        self.assertEqual(decision["status"], "BLOCKED_SHADOW")
        self.assertFalse(decision["promotion"])
        self.assertIn("commit_changed", decision["reason_codes"])

    def test_batch_schema_constant_is_exact(self) -> None:
        self.assertEqual(BATCH_SCHEMA, "x2n-douyin-sidecar-batch-1.0")


if __name__ == "__main__":
    unittest.main()
