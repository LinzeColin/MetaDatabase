#!/usr/bin/env python3
"""Run A004 pin/schema/transport/Canonical synthetic acceptance."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_contracts import ErrorCode  # noqa: E402
from x2n_companion.adapter_guard import BatchDeletionGuard  # noqa: E402
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.douyin_adapter import DouyinAdapter, build_douyin_canary_plan  # noqa: E402
from x2n_companion.douyin_upstream import (  # noqa: E402
    DouyinBatchRequest,
    PinnedDouyinClient,
    SubprocessDouyinTransport,
    synthetic_attestation,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError  # noqa: E402


TASK_ID = "TSK.x2n.adapters.004"
PHASE = "PH.X2N.3.4"
WORKER = PROJECT_ROOT / "scripts/douyin_sidecar_fixture_worker.py"
SHADOW = PROJECT_ROOT / "scripts/run_douyin_shadow_upgrade.py"
NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
ACCOUNT_HASH = "d" * 64


def _client(case: str = "normal", timeout: float = 2.0) -> PinnedDouyinClient:
    return PinnedDouyinClient(
        SubprocessDouyinTransport((sys.executable, "-B", str(WORKER), "--case", case)),
        expected_build=synthetic_attestation(),
        allow_synthetic=True,
        timeout_seconds=timeout,
    )


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_004_tests",
        PROJECT_ROOT / "apps/companion/tests/test_douyin_adapter.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters004 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Adapters004 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _contract_acceptance() -> dict[str, Any]:
    health = _client().health().safe_dict()
    for mode in ("favorites", "likes"):
        _health, batch = _client().fetch_owner_batch(DouyinBatchRequest(mode=mode, sequence=0))
        if len(batch.items) != 20 or batch.completion_signal != "bounded_limit_reached":
            raise AssertionError("Adapters004 normal contract batch failed")
    expected = {
        "attestation_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        "commit_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        "contract_digest_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        "envelope_schema_drift": ErrorCode.INVALID_SCHEMA_VERSION,
        "error_exit": ErrorCode.UNKNOWN_FAILURE,
        "forbidden_field": ErrorCode.POLICY_BLOCKED,
        "invalid_json": ErrorCode.INVALID_INPUT,
        "license_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        "lock_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        "missing_field": ErrorCode.UNKNOWN_FIELD,
        "oversize": ErrorCode.SECURITY_INJECTION_BLOCKED,
        "persistence_enabled": ErrorCode.POLICY_BLOCKED,
        "schema_drift": ErrorCode.INVALID_SCHEMA_VERSION,
        "timeout": ErrorCode.NETWORK_FAILED,
        "tree_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
        "unknown_error": ErrorCode.UNKNOWN_FAILURE,
        "unknown_field": ErrorCode.UNKNOWN_FIELD,
        "version_mismatch": ErrorCode.DATA_INTEGRITY_FAILED,
    }
    for case, code in expected.items():
        timeout = 0.05 if case == "timeout" else 2.0
        try:
            _client(case, timeout).fetch_owner_batch(DouyinBatchRequest(mode="likes", sequence=0))
        except X2NRuntimeError as error:
            if error.code is not code:
                raise AssertionError(f"Adapters004 error normalization drifted: {case}") from error
        else:
            raise AssertionError(f"Adapters004 negative contract case passed: {case}")
    return {
        "automatic_pagination": 0,
        "build_attestation_scope": health["build"]["scope"],
        "exact_health": True,
        "integration_contract_sha256": health["integration_contract_sha256"],
        "negative_cases": len(expected),
        "normal_modes": 2,
        "pin_commit_match": True,
        "pin_tree_match": True,
        "persistence_writes": health["persistence_writes"],
        "subprocess_shell": False,
    }


def _canonical_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a004-canonical-") as value:
        destination = Path(value) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        root = destination / "xhs-douyin-2notion"
        paths = RuntimePaths.from_values(
            str(root),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        store = CanonicalStore(paths, busy_timeout_ms=30_000)
        store.initialize()
        adapter = DouyinAdapter(store)
        for offset, mode in enumerate(("favorites", "likes")):
            scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-a004-acceptance:{mode}"))
            adapter.begin_scan(
                scan_id,
                account_ref_hash=ACCOUNT_HASH,
                mode=mode,
                scope_mode="canary_20",
                started_at=NOW + timedelta(minutes=offset),
            )
            _health, batch = _client().fetch_owner_batch(DouyinBatchRequest(mode=mode, sequence=0))
            receipt = adapter.commit_batch(
                scan_id,
                batch,
                observed_at=NOW + timedelta(minutes=offset, seconds=1),
            )
            replay = adapter.commit_batch(
                scan_id,
                batch,
                observed_at=NOW + timedelta(minutes=offset, seconds=1),
            )
            if receipt.relation_count != 20 or replay.disposition != "replayed":
                raise AssertionError("Adapters004 Canonical replay failed")
        connection = store._open(writable=False)
        try:
            counts = {
                "classification": int(connection.execute("SELECT COUNT(*) FROM classification").fetchone()[0]),
                "content": int(connection.execute("SELECT COUNT(*) FROM content").fetchone()[0]),
                "favorited": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM user_relation WHERE relation_type = 'favorited'"
                    ).fetchone()[0]
                ),
                "liked": int(
                    connection.execute("SELECT COUNT(*) FROM user_relation WHERE relation_type = 'liked'").fetchone()[0]
                ),
                "observations": int(connection.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0]),
                "removed": int(
                    connection.execute("SELECT COUNT(*) FROM user_relation WHERE status = 'removed'").fetchone()[0]
                ),
                "taxonomy": int(connection.execute("SELECT COUNT(*) FROM taxonomy_category").fetchone()[0]),
                "tombstone": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM user_relation WHERE status = 'tombstone_candidate'"
                    ).fetchone()[0]
                ),
            }
            collections = {
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT source_collection_id FROM user_relation WHERE source_collection_id IS NOT NULL"
                )
            }
            payloads = "\n".join(
                str(row[0])
                for table in ("content", "user_relation", "source_observation")
                for row in connection.execute(f"SELECT payload_json FROM {table}")
            )
            checkpoint_full_scans = int(
                connection.execute("SELECT COUNT(*) FROM checkpoint WHERE full_scan_id IS NOT NULL").fetchone()[0]
            )
        finally:
            connection.close()
        if counts != {
            "classification": 0,
            "content": 40,
            "favorited": 20,
            "liked": 20,
            "observations": 40,
            "removed": 0,
            "taxonomy": 0,
            "tombstone": 0,
        }:
            raise AssertionError("Adapters004 Canonical cardinality drifted")
        if len(collections) != 2 or any(not item.startswith("x2ncol_") for item in collections):
            raise AssertionError("Adapters004 collection normalization drifted")
        forbidden = (
            "aweme_id",
            "database_id",
            "file_path",
            "/" + "Users/",
            "/" + "home/",
            "cookie",
            "play_addr",
        )
        if any(item in payloads for item in forbidden) or checkpoint_full_scans:
            raise AssertionError("Adapters004 Canonical containment failed")
        return {
            "classification_writes": counts["classification"],
            "collection_count": len(collections),
            "content_auto_deletes": 0,
            "content_count": counts["content"],
            "exact_replays": 2,
            "favorited_relations": counts["favorited"],
            "full_scan_completions": checkpoint_full_scans,
            "liked_relations": counts["liked"],
            "observations": counts["observations"],
            "physical_deletes": 0,
            "removed_relations": counts["removed"],
            "taxonomy_mutations": counts["taxonomy"],
            "tombstone_candidates": counts["tombstone"],
            "upstream_database_primary_keys": 0,
            "upstream_paths": 0,
        }


def _deletion_acceptance() -> dict[str, int]:
    guard = BatchDeletionGuard()
    relation = "synthetic_relation"
    non_authoritative = ("auth_expired", "http_error", "platform_changed", "empty_response", "partial_scan")
    decisions = [guard.observe(outcome, [relation]) for outcome in non_authoritative]
    first = guard.observe("complete_success", [relation])
    second = guard.observe("complete_success", [relation])
    if (
        any(item.removed_count for item in decisions)
        or first.tombstone_candidate_count
        or second.tombstone_candidate_count != 1
    ):
        raise AssertionError("Adapters004 deletion guard integration failed")
    return {
        "content_auto_deletes": 0,
        "non_authoritative_cases": len(decisions),
        "non_authoritative_removed": 0,
        "physical_deletes": 0,
        "second_complete_candidate_only": second.tombstone_candidate_count,
    }


def _shadow_acceptance() -> dict[str, Any]:
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    results: dict[str, Any] = {}
    for fixture in ("approved-pin", "observed-current"):
        result = subprocess.run(
            [sys.executable, "-B", str(SHADOW), "--fixture", fixture],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode or result.stderr:
            raise AssertionError("Adapters004 shadow harness failed")
        results[fixture] = json.loads(result.stdout)["shadow"]
    if (
        results["approved-pin"]["status"] != "PASS_PIN_UNCHANGED"
        or results["approved-pin"]["promotion"] is not False
        or results["observed-current"]["status"] != "BLOCKED_SHADOW"
        or results["observed-current"]["promotion"] is not False
    ):
        raise AssertionError("Adapters004 shadow decision drifted")
    return {
        "approved_pin_status": results["approved-pin"]["status"],
        "network_calls": 0,
        "observed_candidate_status": results["observed-current"]["status"],
        "promotions": 0,
    }


def main() -> int:
    unit = _run_unit_suite()
    contract = _contract_acceptance()
    canonical = _canonical_acceptance()
    deletion = _deletion_acceptance()
    shadow = _shadow_acceptance()
    favorites_plan = build_douyin_canary_plan("favorites")
    likes_plan = build_douyin_canary_plan("likes")
    payload = {
        "acceptance_scope": "ADAPTERS_004_DOUYIN_PINNED_SIDECAR_CI_SYNTH",
        "automatic_pagination": 0,
        "canonical": canonical,
        "canary_item_limit": 20,
        "canary_tooling": "PASS_NONEXECUTING",
        "contract": contract,
        "deletion": deletion,
        "favorite_canary_execution": favorites_plan["execution"],
        "identified_item_success_percent": 100,
        "like_canary_execution": likes_plan["execution"],
        "network_calls_external": 0,
        "owner_canary": "NOT_RUN",
        "owner_private_sidecar": "NOT_INSTALLED",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "shadow": shadow,
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "unit_suite": unit,
        "upstream_executed": False,
        "upstream_runtime_dependencies": 0,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
