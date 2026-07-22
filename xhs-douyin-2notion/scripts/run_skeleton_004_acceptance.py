#!/usr/bin/env python3
"""Run the public-safe Skeleton004 orchestration acceptance matrix."""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_contracts import canonical_json_sha256  # noqa: E402
from x2n_contracts.models import CaptureCurrentPayload  # noqa: E402
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.orchestrator import CurrentPageOrchestrator  # noqa: E402
from x2n_companion.runtime import RuntimePaths  # noqa: E402


TASK_ID = "TSK.x2n.skeleton.004"
PHASE = "PH.X2N.2.8"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/orchestrator/v1/fixture_manifest.json"
PLATFORMS = ("xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao")


def _content_id(platform: str, index: int) -> str:
    return f"9900000000000{index:06d}" if platform == "taobao" else f"synthetic-{platform}-{index:05d}"


def _payload(index: int) -> CaptureCurrentPayload:
    platform = PLATFORMS[index % len(PLATFORMS)]
    content_id = _content_id(platform, index)
    urls = {
        "bilibili": f"https://www.bilibili.com/video/{content_id}",
        "douyin": f"https://www.douyin.com/video/{content_id}",
        "kuaishou": f"https://www.kuaishou.com/short-video/{content_id}",
        "taobao": "https://item.taobao.com/item.htm",
        "weibo": f"https://www.weibo.com/detail/{content_id}",
        "xiaohongshu": f"https://www.xiaohongshu.com/explore/{content_id}",
    }
    return CaptureCurrentPayload.model_validate_json(
        json.dumps(
            {
                "auto_scroll": False,
                "category_id": None,
                "change_account_state": False,
                "page_context": {
                    "content_id": content_id,
                    "content_type": "image_gallery" if platform == "taobao" else "video",
                    "title": None if index % 7 == 0 else f"Synthetic title {index}",
                },
                "page_url": urls[platform],
                "platform": platform,
                "relation": "saved_current",
                "user_gesture": True,
            },
            ensure_ascii=False,
        )
    )


def _request_id(index: int, *, namespace: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-s004:{namespace}:{index}"))


def _execute(orchestrator: CurrentPageOrchestrator, index: int, *, namespace: str) -> Any:
    payload = _payload(index)
    return orchestrator.execute(
        payload,
        request_id=_request_id(index, namespace=namespace),
        payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
    )


def _store(temporary_root: Path) -> CanonicalStore:
    destination = temporary_root / "MediaCrawler"
    destination.mkdir(mode=0o700)
    paths = RuntimePaths.from_values(
        str(destination / "xhs-douyin-2notion"),
        str(destination),
        repository_root=PROJECT_ROOT,
        create=True,
    )
    store = CanonicalStore(paths, busy_timeout_ms=30_000)
    store.initialize()
    return store


def run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_skeleton_004_orchestrator_tests",
        PROJECT_ROOT / "apps/companion/tests/test_orchestrator.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Orchestrator test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Orchestrator unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def run_idempotency(case_count: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-s004-acceptance-idempotency-") as value:
        store = _store(Path(value))
        orchestrator = CurrentPageOrchestrator(store, clock=lambda: "2026-07-22T00:00:00Z")
        first = [_execute(orchestrator, index, namespace="acceptance") for index in range(case_count)]
        second = [_execute(orchestrator, index, namespace="acceptance") for index in range(case_count)]
        counts = store.counts()
        expected_tables = (
            "artifact",
            "checkpoint",
            "content",
            "request_ledger",
            "run_record",
            "source_observation",
            "user_relation",
        )
        if any(counts[table] != case_count for table in expected_tables):
            raise AssertionError("80x2 replay created a duplicate or missing canonical entity")
        if sum(item.disposition.value == "new_request" for item in first) != case_count:
            raise AssertionError("Initial replay round did not create every request")
        if sum(item.disposition.value == "return_existing_job" for item in second) != case_count:
            raise AssertionError("Second replay round did not return every existing Job")
        connection = sqlite3.connect(store.paths.database)
        try:
            broken_traces = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM run_record AS r
                    LEFT JOIN source_observation AS o ON o.run_id = r.run_id
                    LEFT JOIN content AS c ON c.content_key = o.content_key
                    LEFT JOIN user_relation AS u ON u.content_key = c.content_key AND u.relation_type = 'saved_current'
                    LEFT JOIN artifact AS a ON a.content_key = c.content_key
                    WHERE r.run_kind = 'current_page_capture_v1'
                      AND (r.state <> 'succeeded' OR o.observation_id IS NULL OR c.content_key IS NULL
                           OR u.relation_key IS NULL OR a.artifact_id IS NULL)
                    """
                ).fetchone()[0]
            )
            private_placeholders = int(
                connection.execute(
                    "SELECT COUNT(*) FROM artifact WHERE processor = 'x2n-canonical-placeholder' AND private_payload_present <> 0"
                ).fetchone()[0]
            )
            downstream_counts = {
                "classification": int(connection.execute("SELECT COUNT(*) FROM classification").fetchone()[0]),
                "markdown_outbox": int(
                    connection.execute("SELECT COUNT(*) FROM outbox_event WHERE sink = 'markdown'").fetchone()[0]
                ),
                "notion_outbox": int(
                    connection.execute("SELECT COUNT(*) FROM outbox_event WHERE sink = 'notion'").fetchone()[0]
                ),
                "sink_receipt": int(connection.execute("SELECT COUNT(*) FROM sink_receipt").fetchone()[0]),
            }
        finally:
            connection.close()
        if broken_traces or private_placeholders or any(downstream_counts.values()):
            raise AssertionError("Scoped provenance or downstream boundary failed")
        return {
            "broken_provenance_traces": broken_traces,
            "case_count": case_count,
            "duplicate_entities": 0,
            "entity_counts": {table: counts[table] for table in expected_tables},
            "existing_jobs_round_2": case_count,
            "new_jobs_round_1": case_count,
            "private_placeholder_payloads": private_placeholders,
            "replay_rounds": 2,
            "stuck_runs": 0,
        }


def run_concurrency(request_count: int) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="x2n-s004-acceptance-concurrency-") as value:
        store = _store(Path(value))
        orchestrator = CurrentPageOrchestrator(store, clock=lambda: "2026-07-22T00:00:00Z")

        def execute(_: int) -> Any:
            return _execute(orchestrator, 1, namespace="concurrent")

        with ThreadPoolExecutor(max_workers=12) as executor:
            receipts = list(executor.map(execute, range(request_count)))
        job_count = len({item.job_id for item in receipts})
        new_count = sum(item.disposition.value == "new_request" for item in receipts)
        existing_count = sum(item.disposition.value == "return_existing_job" for item in receipts)
        if (job_count, new_count, existing_count) != (1, 1, request_count - 1):
            raise AssertionError("Concurrent duplicate request identity diverged")
        if any(store.counts()[table] != 1 for table in (
            "artifact", "checkpoint", "content", "request_ledger", "run_record", "source_observation", "user_relation"
        )):
            raise AssertionError("Concurrent duplicate created more than one canonical graph")
        return {
            "duplicate_entities": 0,
            "existing_jobs": existing_count,
            "job_count": job_count,
            "new_jobs": new_count,
            "requests": request_count,
        }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (
        fixture.get("fixture_id") != "FIXTURE.X2N.S02.S004.001"
        or fixture.get("case_count") != 80
        or fixture.get("real_accounts") is not False
        or fixture.get("contains_credentials") is not False
        or fixture.get("contains_media_urls") is not False
        or fixture.get("contains_private_content") is not False
        or fixture.get("contains_local_absolute_paths") is not False
    ):
        raise AssertionError("Orchestrator fixture boundary drifted")
    cases = int(fixture["case_count"])
    concurrency = int(fixture["tests"]["concurrent_duplicate_count"])
    unit = run_unit_suite()
    return {
        "acceptance_scope": "SKELETON_004_CANONICAL_ORCHESTRATION_CI_SYNTH",
        "concurrency": run_concurrency(concurrency),
        "downstream": {
            "classification": "DOWNSTREAM_NOT_RUN",
            "markdown": "DOWNSTREAM_NOT_RUN",
            "media_processing": "DOWNSTREAM_NOT_RUN",
            "notion": "DOWNSTREAM_NOT_RUN",
            "renderer": "DOWNSTREAM_NOT_RUN",
        },
        "fixture_id": fixture["fixture_id"],
        "idempotency": run_idempotency(cases),
        "kill_points": {
            "cases": len(fixture["tests"]["kill_points"]),
            "non_replayable_states": 0,
            "status": "PASS_CI_SYNTH_SCOPED",
        },
        "migration": "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
        "notion_calls": 0,
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "schema_version": 2,
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "unit_suite": unit,
    }


def main() -> int:
    try:
        payload = run()
    except Exception as error:
        print(
            json.dumps(
                {"reason": str(error), "status": "FAIL_CLOSED", "task_id": TASK_ID},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
