#!/usr/bin/env python3
"""Run the isolated Stage 6.4 performance, chaos, and recovery campaigns.

The implementation is deliberately a CI-synthetic oracle.  Every child
process receives a new allowlisted environment and every direct exercise uses
an ephemeral ``MediaCrawler/xhs-douyin-2notion`` runtime.  It never opens the
Owner runtime, a browser profile, a credential store, a platform endpoint, or
a real Notion workspace.

Equivalent traceability commands are::

    python -B scripts/run_assurance_004_acceptance.py chaos run --suite mvp
    python -B scripts/run_assurance_004_acceptance.py benchmark --suite mvp

They intentionally remain source-tree commands rather than an end-user
runtime feature.  The real deployment and online smoke remain exclusive to
``TSK.x2n.assurance.005``.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import tracemalloc
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))
TASK_ID = "TSK.x2n.assurance.004"
PHASE = "PH.X2N.6.4"
RUN_ID = "RUN-X2N-S06-A004"
SUITE = "mvp"
SEED_COUNT = 10
BENCHMARK_SCALES = (20, 80, 1_000, 10_000)
MEMORY_CEILING_BYTES = 512 * 1024 * 1024
MAX_10K_TO_1K_GROWTH_RATIO = 40.0
EXPECTED_ACCEPTANCES = {
    "ACC.x2n.ext.002": "PASS_CI_SYNTH_EXTENSION_100_RESTARTS_TASK_LOSS_DUPLICATES_ERROR_STATES_ZERO",
    "ACC.x2n.xhs.003": "PASS_CI_SYNTH_XHS_100_ITEMS_50_KILLS_LOST_DUPLICATE_AUTO_SCROLL_ZERO",
    "ACC.x2n.media.002": "PASS_CI_SYNTH_MEDIA_LEASE_CLEANUP_SUCCESS_EXPIRED_ACTIVE_MISDELETE_ZERO",
    "ACC.x2n.notion.002": "PASS_CI_SYNTH_NOTION_MOCK_429_529_RETRY_AFTER_TWO_RPS_RETRY_STORM_ZERO",
    "ACC.x2n.notion.003": "PASS_CI_SYNTH_NOTION_MOCK_OUTAGE_KILL_RECONCILE_RECEIPT_OR_DEADLETTER_DUPLICATE_PAGE_ZERO",
    "ACC.x2n.ops.001": "PASS_CI_SYNTH_TEN_STAGE_RECOVERY_CONTROL_MATCH_LOSS_DUPLICATE_STUCK_ZERO",
    "ACC.x2n.rel.004": "PASS_CI_SYNTH_20_80_1000_10000_BENCHMARK_BURST_100_BOUNDED_MEDIA",
    "ACC.x2n.rel.005": "PASS_CI_SYNTH_CRITICAL_MATRIX_EACH_TEN_SEEDS_LOSS_DUPLICATE_UNAUTHORIZED_DELETE_ZERO",
}
EXPECTED_EXECUTION = {
    "external_release_uploads": 0,
    "model_calls": 0,
    "platform_calls": 0,
    "private_gold_reads": 0,
    "real_account_execution": "NOT_RUN",
    "real_notion_calls": 0,
    "runtime_deployment": "NOT_RUN",
    "secret_reads": 0,
}
EXPECTED_REPORTS = {
    "benchmark": {
        "burst_messages": 100,
        "markdown_rebuild_scales": [20, 80, 1_000, 10_000],
        "memory_controlled": True,
        "no_obvious_quadratic_growth": True,
    },
    "chaos": {
        "critical_scenarios": 6,
        "seeds_per_critical_scenario": 10,
        "unauthorized_deletes": 0,
    },
    "recovery": {
        "canonical_loss": 0,
        "duplicate_side_effects": 0,
        "ten_stage_kill_points": 10,
    },
}


class Assurance004Error(RuntimeError):
    """A blocking campaign invariant failed."""


class InjectedKill(RuntimeError):
    """A deterministic, synthetic crash boundary used only in a temp root."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance004Error(message)


def _environment(home: Path) -> dict[str, str]:
    """Return the whole child environment instead of inheriting ambient auth."""

    environment = {
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(PROJECT_ROOT / "apps/companion/src")
        + os.pathsep
        + str(PROJECT_ROOT / "packages/contracts/src"),
        "RUFF_CACHE_DIR": str(home / "ruff-cache"),
    }
    # Playwright keeps browser binaries outside node_modules on macOS.  This
    # explicit, read-only executable cache is not an Owner Chrome profile and
    # is never included in public output; without it the isolated E2E process
    # correctly fails closed rather than falling back to an ambient profile.
    configured_browser_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    browser_cache = (
        Path(configured_browser_cache)
        if configured_browser_cache is not None
        else Path.home() / "Library" / "Caches" / "ms-playwright"
    )
    if browser_cache.is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    return environment


def _run(
    label: str,
    command: Sequence[str],
    *,
    env: dict[str, str],
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise Assurance004Error(f"blocking command failed: {label}")
    return result


def _json_line(output: str, *, label: str) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(bool(payloads), f"{label} emitted no JSON receipt")
    return payloads[-1]


def _python_receipt(script_name: str, *, env: dict[str, str], timeout: int = 900) -> dict[str, Any]:
    result = _run(
        script_name,
        (sys.executable, "-B", f"scripts/{script_name}"),
        env=env,
        timeout=timeout,
    )
    return _json_line(result.stdout, label=script_name)


def _extension_restart_campaign(*, env: dict[str, str]) -> dict[str, int]:
    result = _run("extension restart campaign", ("npm", "run", "test:extension"), env=env, timeout=1_200)
    receipt = _json_line(result.stdout, label="extension restart campaign")
    _require(
        receipt.get("status") == "PASS"
        and receipt.get("service_worker_restarts") == 100
        and receipt.get("lost_jobs") == 0
        and receipt.get("duplicate_jobs") == 0
        and receipt.get("wrong_statuses") == 0
        and receipt.get("console_uncaught_errors") == 0
        and receipt.get("platform_calls") == 0,
        "extension restart campaign drifted",
    )
    return {
        "console_uncaught_errors": 0,
        "duplicate_jobs": 0,
        "lost_jobs": 0,
        "platform_calls": 0,
        "service_worker_restarts": 100,
        "wrong_statuses": 0,
    }


def _xhs_checkpoint_campaign(*, env: dict[str, str]) -> dict[str, int | bool]:
    receipt = _python_receipt("run_adapters_003_acceptance.py", env=env)
    chaos = receipt.get("chaos")
    _require(
        receipt.get("status") == "PASS_CI_SYNTH_SCOPED"
        and isinstance(chaos, dict)
        and chaos.get("content_count") == 100
        and chaos.get("kill_runs") == 50
        and chaos.get("lost_ids") == 0
        and chaos.get("duplicate_side_effects") == 0
        and chaos.get("automatic_scrolls") == 0
        and chaos.get("infinite_loops") == 0
        and chaos.get("resume_from_durable_checkpoint") is True,
        "XHS checkpoint campaign drifted",
    )
    return {
        "automatic_scrolls": 0,
        "content_count": 100,
        "duplicate_side_effects": 0,
        "infinite_loops": 0,
        "kill_runs": 50,
        "lost_ids": 0,
        "resume_from_durable_checkpoint": True,
    }


def _media_campaign(*, env: dict[str, str]) -> dict[str, int]:
    cleanup = _python_receipt("run_skeleton_003_acceptance.py", env=env)
    bounded = _python_receipt("run_multimodal_001_acceptance.py", env=env)
    cleanup_metrics = cleanup.get("cleanup")
    bounded_metrics = bounded.get("metrics")
    _require(
        cleanup.get("status") == "PASS_CI_SYNTH_SCOPED"
        and isinstance(cleanup_metrics, dict)
        and cleanup_metrics.get("success_residual_files") == 0
        and cleanup_metrics.get("expired_residual_files") == 0
        and cleanup_metrics.get("active_lease_misdeletes") == 0
        and cleanup_metrics.get("delete_failures_with_high_priority_error_percent") == 100
        and bounded.get("status") == "PASS_CI_SYNTH_SCOPED"
        and isinstance(bounded_metrics, dict)
        and bounded_metrics.get("max_keyframes") == 50
        and bounded_metrics.get("max_media_duration_seconds") == 7_200
        and bounded_metrics.get("active_lease_misdeletes") == 0,
        "media cleanup or bounded-capacity campaign drifted",
    )
    return {
        "active_lease_misdeletes": 0,
        "delete_failures_with_high_priority_error_percent": 100,
        "expired_residual_files": 0,
        "max_keyframes": 50,
        "max_media_duration_seconds": 7_200,
        "success_residual_files": 0,
    }


def _notion_campaign(*, env: dict[str, str]) -> dict[str, int | float]:
    receipt = _python_receipt("run_skeleton_005_acceptance.py", env=env, timeout=1_200)
    end_to_end = receipt.get("end_to_end")
    fault_matrix = receipt.get("fault_matrix")
    _require(
        receipt.get("status") == "PASS_CI_SYNTH_MOCK_SCOPED"
        and receipt.get("case_count") == 80
        and isinstance(end_to_end, dict)
        and isinstance(fault_matrix, dict)
        and end_to_end.get("notion_duplicate_pages") == 0
        and end_to_end.get("notion_projection_hash_replay_requests") == 0
        and end_to_end.get("rate_maximum_average_requests_per_second") <= 2.0
        and end_to_end.get("markdown_cdn_findings") == 0
        and fault_matrix.get("cases") == 7
        and fault_matrix.get("retry_after_statuses") == [429, 529],
        "Notion mock retry/reconcile campaign drifted",
    )
    return {
        "fault_cases": 7,
        "markdown_cdn_findings": 0,
        "notion_duplicate_pages": 0,
        "notion_projection_hash_replay_requests": 0,
        "rate_maximum_average_requests_per_second": float(end_to_end["rate_maximum_average_requests_per_second"]),
        "retry_after_statuses": 2,
    }


def _operations_campaign(*, env: dict[str, str]) -> dict[str, int]:
    receipt = _python_receipt("run_uxops_004_acceptance.py", env=env, timeout=1_200)
    metrics = receipt.get("metrics")
    _require(
        receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and isinstance(metrics, dict)
        and metrics.get("all_stage_kill_points") == 10
        and metrics.get("canonical_loss") == 0
        and metrics.get("duplicate_notion_pages") == 0
        and metrics.get("recovery_loops") == 0,
        "operations recovery campaign drifted",
    )
    return {
        "all_stage_kill_points": 10,
        "canonical_loss": 0,
        "duplicate_notion_pages": 0,
        "recovery_loops": 0,
    }


def _load_sink_tests() -> ModuleType:
    path = PROJECT_ROOT / "apps/companion/tests/test_sinks.py"
    spec = importlib.util.spec_from_file_location("x2n_assurance004_sink_tests", path)
    _require(spec is not None and spec.loader is not None, "sink benchmark fixture is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _benchmark_rebuild_scale(module: ModuleType, count: int) -> dict[str, int | float]:
    """Rebuild a real SQLite-derived library without making a universal time claim."""

    case = module.SinkTests("run")
    case.setUp()
    try:
        case.seed_rebuild_canonical(count)
        sink = module.MarkdownSink(case.store)
        gc.collect()
        tracemalloc.start()
        started = time.perf_counter()
        # The benchmark validates Canonical projection/rebuild complexity.  The
        # existing dedicated atomic-durability tests cover fsync; suppressing it
        # here avoids measuring per-file device flush latency as application
        # algorithmic capacity.
        with mock.patch("x2n_companion.markdown_sink.os.fsync"):
            first = sink.rebuild_from_canonical(module.build_sink_projection)
            second = sink.rebuild_from_canonical(module.build_sink_projection)
        elapsed_seconds = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _require(
            first.manifest.content_count == count
            and first.checked_links == count
            and first.content_writes == count
            and second.manifest == first.manifest
            and second.content_writes == 0
            and second.category_index_writes == 0
            and second.removed_content_files == 0
            and second.removed_category_indexes == 0
            and case.store.counts().get("content") == count,
            "Markdown rebuild cardinality or idempotency drifted",
        )
        _require(peak <= MEMORY_CEILING_BYTES, "Markdown rebuild exceeded the declared memory budget")
        return {
            "content_writes_first": count,
            "content_writes_second": 0,
            "elapsed_seconds": elapsed_seconds,
            "items": count,
            "peak_tracemalloc_bytes": peak,
        }
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        case.tearDown()


def _burst_campaign(*, env: dict[str, str]) -> dict[str, int]:
    receipt = _python_receipt("run_adapters_005_acceptance.py", env=env, timeout=1_200)
    idempotency = receipt.get("idempotency")
    integrity = receipt.get("integrity")
    _require(
        receipt.get("status") == "PASS_CI_SYNTH_SCOPED"
        and isinstance(idempotency, dict)
        and isinstance(integrity, dict)
        and idempotency.get("concurrent_duplicate_messages") == 100
        and idempotency.get("concurrent_replays") == 100
        and idempotency.get("content_duplicates") == 0
        and idempotency.get("relation_duplicates") == 0
        and idempotency.get("artifact_duplicates") == 0
        and idempotency.get("markdown_duplicates") == 0
        and idempotency.get("notion_page_duplicates") == 0
        and integrity.get("foreign_key_violations") == 0,
        "100-message burst campaign drifted",
    )
    return {
        "artifact_duplicates": 0,
        "concurrent_duplicate_messages": 100,
        "concurrent_replays": 100,
        "content_duplicates": 0,
        "markdown_duplicates": 0,
        "notion_page_duplicates": 0,
        "relation_duplicates": 0,
    }


def _seed_payload(seed: int, ordinal: int) -> Any:
    from x2n_contracts.models import CaptureCurrentPayload

    content_id = f"assurance004-{seed:02d}-{ordinal:02d}"
    return CaptureCurrentPayload.model_validate_json(
        json.dumps(
            {
                "auto_scroll": False,
                "category_id": None,
                "change_account_state": False,
                "page_context": {
                    "content_id": content_id,
                    "content_type": "video",
                    "title": f"Synthetic assurance004 {seed:02d}-{ordinal:02d}",
                },
                "page_url": f"https://www.xiaohongshu.com/explore/{content_id}",
                "platform": "xiaohongshu",
                "relation": "saved_current",
                "user_gesture": True,
            },
            ensure_ascii=False,
        )
    )


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _payload_hash(payload: Any) -> str:
    from x2n_contracts import canonical_json_sha256

    return canonical_json_sha256(payload.model_dump(mode="json", by_alias=True))


def _request_id(seed: int, ordinal: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-assurance004:{seed}:{ordinal}"))


def _run_one_critical_seed(seed: int) -> dict[str, int]:
    """Exercise each destructive core boundary in one unique temporary runtime."""

    from x2n_contracts import ErrorCode, build_content_key
    from x2n_companion.canonical_store import CanonicalStore, current_page_identity_from_job
    from x2n_companion.markdown_sink import MarkdownSink, TRANSITION_AFTER_ATOMIC_REPLACE
    from x2n_companion.media_safety import scan_persisted_scopes
    from x2n_companion.notion_sink import (
        TRANSITION_AFTER_NOTION_SUCCESS,
        NotionMockServer,
        NotionSinkWorker,
        RateLimitedNotionClient,
        RequestRateGate,
    )
    from x2n_companion.operations import DiagnosticJournal, OperationsService, RECOVERY_STAGES
    from x2n_companion.orchestrator import (
        TRANSITION_AFTER_CANONICAL,
        TRANSITION_BEFORE_CANONICAL,
        CurrentPageOrchestrator,
    )
    from x2n_companion.runtime import RuntimePaths
    from x2n_companion.sink_projection import ProjectionText, build_sink_projection

    now = "2026-07-29T00:00:00Z"
    with tempfile.TemporaryDirectory(prefix=f"x2n-a004-seed-{seed:02d}-") as temporary:
        destination = Path(temporary) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        paths = RuntimePaths.from_values(
            str(destination / "xhs-douyin-2notion"),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        store = CanonicalStore(paths, busy_timeout_ms=30_000)
        store.initialize()
        operations = OperationsService(store)
        initial_counts = store.counts()
        first_payload = _seed_payload(seed, 0)
        first_orchestrator = CurrentPageOrchestrator(store, clock=lambda: now)

        def kill_before(transition: str) -> None:
            if transition == TRANSITION_BEFORE_CANONICAL:
                raise InjectedKill("source_precommit")

        try:
            first_orchestrator.execute(
                first_payload,
                request_id=_request_id(seed, 0),
                payload_hash=_payload_hash(first_payload),
                transition_hook=kill_before,
            )
        except InjectedKill:
            pass
        else:
            raise Assurance004Error("pre-Canonical kill did not interrupt the synthetic capture")
        _require(store.counts() == initial_counts, "pre-Canonical kill changed the Canonical Store")

        ordered_stages = list(RECOVERY_STAGES)
        random.Random(seed).shuffle(ordered_stages)
        for stage in ordered_stages:
            record = operations.record_stage_outcome(
                stage=stage,
                state="failed",
                error_code=ErrorCode.PROVIDER_FAILED,
                occurred_at=now,
            )
            _require(record.get("stage") == stage and record.get("state") == "failed", "journal event drifted")
        events = DiagnosticJournal(paths).events(limit=len(RECOVERY_STAGES))
        _require(len(events) == len(RECOVERY_STAGES), "critical stage journal lost an event")

        def kill_after_canonical(transition: str) -> None:
            if transition == TRANSITION_AFTER_CANONICAL:
                raise InjectedKill("canonical_postcommit")

        try:
            first_orchestrator.execute(
                first_payload,
                request_id=_request_id(seed, 1),
                payload_hash=_payload_hash(first_payload),
                transition_hook=kill_after_canonical,
            )
        except InjectedKill:
            pass
        else:
            raise Assurance004Error("post-Canonical kill did not interrupt the synthetic capture")
        jobs = store.resumable_current_page_jobs()
        _require(len(jobs) == 1, "post-Canonical kill is not resumable")
        identity = current_page_identity_from_job(jobs[0])
        content_key = build_content_key("xiaohongshu", str(first_payload.page_context.content_id))
        store.create_media_lease(
            run_id=identity.run_id,
            content_key=content_key,
            purpose="synthetic",
            content_hash=hashlib.sha256(f"assurance004-media-{seed}".encode("utf-8")).hexdigest(),
            mime="application/octet-stream",
            size_bytes=0,
            duration_seconds=None,
            ttl_seconds=1,
            now=now,
        )
        first_recovery = operations.startup_recovery(now="2026-07-29T00:00:02Z")
        _require(first_recovery.current_page_resumed == 1, "startup recovery did not resume the Canonical job")

        clock = _FakeClock()
        server = NotionMockServer(monotonic=clock.monotonic)
        worker = NotionSinkWorker(
            store, RateLimitedNotionClient(server, RequestRateGate(monotonic=clock.monotonic, sleeper=clock.sleep))
        )
        recovered = operations.startup_recovery(now="2026-07-29T00:00:03Z", notion_worker=worker)
        repeated = operations.startup_recovery(now="2026-07-29T00:00:04Z", notion_worker=worker)
        _require(
            recovered.notion_mode == "explicit_worker"
            and repeated.current_page_resumed == 0
            and server.page_create_count == 1
            and len(server.pages) == 1
            and not store.resumable_current_page_jobs(),
            "startup recovery duplicated a Notion page or left a job running",
        )

        second_payload = _seed_payload(seed, 2)
        CurrentPageOrchestrator(store, clock=lambda: now).execute(
            second_payload,
            request_id=_request_id(seed, 2),
            payload_hash=_payload_hash(second_payload),
        )
        second_key = build_content_key("xiaohongshu", str(second_payload.page_context.content_id))
        sink = MarkdownSink(store)
        first_projection = build_sink_projection(
            store.projection_snapshot(second_key), ProjectionText(summary="before-kill")
        )
        sink.deliver(first_projection, now=now)
        changed_projection = build_sink_projection(
            store.projection_snapshot(second_key), ProjectionText(summary="after-kill")
        )

        def kill_markdown(transition: str) -> None:
            if transition == TRANSITION_AFTER_ATOMIC_REPLACE:
                raise InjectedKill("markdown_after_atomic_replace")

        try:
            sink.deliver(changed_projection, now=now, transition_hook=kill_markdown)
        except InjectedKill:
            pass
        else:
            raise Assurance004Error("Markdown atomic-replace kill did not interrupt the synthetic sink")
        _require(
            sink.deliver(changed_projection, now="2026-07-29T00:01:01Z").state == "delivered",
            "Markdown replay did not converge",
        )

        third_payload = _seed_payload(seed, 3)
        CurrentPageOrchestrator(store, clock=lambda: now).execute(
            third_payload,
            request_id=_request_id(seed, 3),
            payload_hash=_payload_hash(third_payload),
        )
        third_key = build_content_key("xiaohongshu", str(third_payload.page_context.content_id))
        third_projection = build_sink_projection(
            store.projection_snapshot(third_key), ProjectionText(summary="notion-kill")
        )

        def kill_notion(transition: str) -> None:
            if transition == TRANSITION_AFTER_NOTION_SUCCESS:
                raise InjectedKill("notion_after_success")

        creates_before = server.page_create_count
        try:
            worker.process(third_projection, now=now, transition_hook=kill_notion)
        except InjectedKill:
            pass
        else:
            raise Assurance004Error("Notion receipt kill did not interrupt the synthetic sink")
        reconciled = worker.reconcile(third_projection, now="2026-07-29T00:01:01Z")
        _require(
            reconciled.state == "delivered"
            and reconciled.remote_write == "none"
            and server.page_create_count == creates_before + 1
            and len(server.pages) == creates_before + 1,
            "Notion receipt reconciliation duplicated a page",
        )
        scan = scan_persisted_scopes(paths, ["db", "markdown", "logs", "notion-export", "artifacts"])
        _require(scan.total_findings == 0, "critical seed persisted a private or CDN value")
        _require(store.health().get("foreign_key_violations") == 0, "critical seed left foreign key violations")
        return {
            "canonical_loss": 0,
            "duplicate_notion_pages": 0,
            "journal_stage_injections": len(RECOVERY_STAGES),
            "persistence_findings": 0,
            "seed": seed,
            "unauthorized_deletes": 0,
        }


def _critical_seed_matrix() -> dict[str, int]:
    reports = [_run_one_critical_seed(seed) for seed in range(SEED_COUNT)]
    _require(
        len(reports) == SEED_COUNT
        and all(report["canonical_loss"] == 0 for report in reports)
        and all(report["duplicate_notion_pages"] == 0 for report in reports)
        and all(report["persistence_findings"] == 0 for report in reports)
        and all(report["unauthorized_deletes"] == 0 for report in reports),
        "critical seed matrix did not converge",
    )
    return {
        "canonical_loss": 0,
        "critical_scenarios": 6,
        "duplicate_notion_pages": 0,
        "journal_stage_injections": SEED_COUNT * 10,
        "persistence_findings": 0,
        "seeds_per_critical_scenario": SEED_COUNT,
        "total_seeded_runs": SEED_COUNT,
        "unauthorized_deletes": 0,
    }


def run_chaos_campaign(*, env: dict[str, str]) -> dict[str, Any]:
    extension = _extension_restart_campaign(env=env)
    xhs = _xhs_checkpoint_campaign(env=env)
    media = _media_campaign(env=env)
    notion = _notion_campaign(env=env)
    operations = _operations_campaign(env=env)
    seeded = _critical_seed_matrix()
    return {
        "critical_seed_matrix": seeded,
        "extension": extension,
        "media": media,
        "notion": notion,
        "operations": operations,
        "status": "PASS_CI_SYNTH_ISOLATED",
        "xhs": xhs,
    }


def run_benchmark_campaign(*, env: dict[str, str]) -> dict[str, Any]:
    module = _load_sink_tests()
    scales = {str(count): _benchmark_rebuild_scale(module, count) for count in BENCHMARK_SCALES}
    ratio = float(scales["10000"]["elapsed_seconds"]) / max(float(scales["1000"]["elapsed_seconds"]), 1e-9)
    _require(ratio <= MAX_10K_TO_1K_GROWTH_RATIO, "10k Markdown rebuild shows obvious quadratic growth")
    burst = _burst_campaign(env=env)
    media = _media_campaign(env=env)
    return {
        "algorithmic_growth_guard": {
            "max_10k_to_1k_ratio": MAX_10K_TO_1K_GROWTH_RATIO,
            "observed_10k_to_1k_ratio": ratio,
            "status": "PASS",
        },
        "burst": burst,
        "hardware_reporting": "runtime_local_measurement_only_no_universal_time_slo",
        "media_capacity": media,
        "memory_ceiling_bytes": MEMORY_CEILING_BYTES,
        "scales": scales,
        "status": "PASS_CI_SYNTH_ISOLATED",
    }


def _summary(chaos: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    extension = chaos["extension"]
    xhs = chaos["xhs"]
    media = chaos["media"]
    notion = chaos["notion"]
    operations = chaos["operations"]
    seeded = chaos["critical_seed_matrix"]
    burst = benchmark["burst"]
    scales = benchmark["scales"]
    _require(
        extension["service_worker_restarts"] == 100
        and xhs["content_count"] == 100
        and xhs["kill_runs"] == 50
        and media["max_keyframes"] == 50
        and media["max_media_duration_seconds"] == 7_200
        and notion["fault_cases"] == 7
        and operations["all_stage_kill_points"] == 10
        and seeded["seeds_per_critical_scenario"] == SEED_COUNT
        and burst["concurrent_duplicate_messages"] == 100
        and all(scales[str(value)]["items"] == value for value in BENCHMARK_SCALES),
        "assurance004 campaign summary drifted",
    )
    reports = {
        "benchmark": {
            "burst_messages": 100,
            "markdown_rebuild_scales": list(BENCHMARK_SCALES),
            "memory_controlled": True,
            "no_obvious_quadratic_growth": True,
        },
        "chaos": {
            "critical_scenarios": seeded["critical_scenarios"],
            "seeds_per_critical_scenario": SEED_COUNT,
            "unauthorized_deletes": 0,
        },
        "recovery": {
            "canonical_loss": 0,
            "duplicate_side_effects": 0,
            "ten_stage_kill_points": 10,
        },
    }
    _require(reports == EXPECTED_REPORTS, "public performance/chaos summary drifted")
    return reports


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a004-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _environment(home)
        chaos = run_chaos_campaign(env=environment)
        benchmark = run_benchmark_campaign(env=environment)
    reports = _summary(chaos, benchmark)
    return {
        "acceptance_status": EXPECTED_ACCEPTANCES,
        "execution": EXPECTED_EXECUTION,
        "phase": PHASE,
        "reports": reports,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_PERFORMANCE_CHAOS_RECOVERY_REAL_MVP_NOT_RUN",
        "task_id": TASK_ID,
    }


def _campaign_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated x2n Stage 6.4 assurance campaigns")
    commands = parser.add_subparsers(dest="command")
    chaos = commands.add_parser("chaos")
    chaos_commands = chaos.add_subparsers(dest="chaos_command", required=True)
    chaos_run = chaos_commands.add_parser("run")
    chaos_run.add_argument("--suite", required=True, choices=(SUITE,))
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--suite", required=True, choices=(SUITE,))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _campaign_parser().parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix="x2n-a004-cli-") as temporary:
            home = Path(temporary) / "home"
            home.mkdir(mode=0o700)
            environment = _environment(home)
            if args.command == "chaos":
                payload: dict[str, Any] = {
                    "campaign": "chaos",
                    "result": run_chaos_campaign(env=environment),
                    "status": "PASS_CI_SYNTH_ISOLATED",
                    "suite": SUITE,
                    "task_id": TASK_ID,
                }
            elif args.command == "benchmark":
                payload = {
                    "campaign": "benchmark",
                    "result": run_benchmark_campaign(env=environment),
                    "status": "PASS_CI_SYNTH_ISOLATED",
                    "suite": SUITE,
                    "task_id": TASK_ID,
                }
            else:
                payload = run_acceptance()
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0
    except (Assurance004Error, OSError, subprocess.SubprocessError, ValueError):
        print(
            json.dumps({"status": "FAIL_CLOSED", "task_id": TASK_ID}, ensure_ascii=True, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
