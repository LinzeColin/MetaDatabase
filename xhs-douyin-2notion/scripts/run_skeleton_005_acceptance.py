#!/usr/bin/env python3
"""CI-synthetic Markdown and in-process Notion Mock acceptance for Skeleton005."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_contracts import canonical_json_sha256  # noqa: E402

from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.markdown_sink import MarkdownSink, parse_frontmatter  # noqa: E402
from x2n_companion.media_safety import scan_persisted_scopes  # noqa: E402
from x2n_companion.notion_sink import (  # noqa: E402
    NotionMockServer,
    NotionSinkWorker,
    RateLimitedNotionClient,
    RequestRateGate,
)
from x2n_companion.orchestrator import CurrentPageOrchestrator  # noqa: E402
from x2n_companion.runtime import RuntimePaths  # noqa: E402
from x2n_companion.sink_projection import ProjectionText, build_sink_projection  # noqa: E402


TASK_ID = "TSK.x2n.skeleton.005"
PHASE = "PH.X2N.2.9"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/sinks/v1/fixture_manifest.json"
TEST_MODULE = PROJECT_ROOT / "apps/companion/tests/test_sinks.py"


def load_test_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("x2n_skeleton_005_sink_tests", TEST_MODULE)
    if spec is None or spec.loader is None:
        raise AssertionError("Sink test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_unit_suite(module: ModuleType) -> dict[str, int]:
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Sink unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _store(value: Path) -> CanonicalStore:
    destination = value / "MediaCrawler"
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


def run_end_to_end(module: ModuleType, case_count: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-s005-acceptance-") as value:
        store = _store(Path(value))
        clock = module.FakeClock()
        markdown = MarkdownSink(store)
        server = NotionMockServer(monotonic=clock.monotonic)
        client = RateLimitedNotionClient(
            server,
            RequestRateGate(monotonic=clock.monotonic, sleeper=clock.sleep),
        )
        notion = NotionSinkWorker(store, client)
        projections = []
        markdown_deliveries = []
        notion_deliveries = []
        for index in range(case_count):
            payload = module._payload(index)
            CurrentPageOrchestrator(store, clock=clock.iso).execute(
                payload,
                request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-s005-acceptance:{index}")),
                payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
            )
            content_key = f"{payload.platform.value}:{payload.page_context.content_id}"
            projection = build_sink_projection(
                store.projection_snapshot(content_key),
                ProjectionText(
                    original_text=f"Synthetic original text {index}",
                    summary=f"Synthetic summary {index}",
                    transcript=f"Synthetic transcript {index}",
                    ocr=f"Synthetic OCR {index}",
                ),
            )
            projections.append(projection)
            markdown_deliveries.append(markdown.deliver(projection, now=clock.iso()))
            notion_deliveries.append(notion.process(projection, now=clock.iso()))
        index_hash = markdown.seed_unclassified_index(projections)
        checked_links = markdown.validate_unclassified_links()

        markdown_files = sorted((store.paths.data_root / "runtime/library/content").glob("*/*.md"))
        if len(markdown_files) != case_count or checked_links != case_count:
            raise AssertionError("Markdown projection cardinality or links diverged")
        invalid_frontmatter = 0
        output_hashes: list[str] = []
        for path in markdown_files:
            rendered = path.read_text(encoding="utf-8")
            try:
                parsed, body = parse_frontmatter(rendered)
            except Exception:
                invalid_frontmatter += 1
                continue
            if parsed.get("projection_hash") is None or "## Provenance" not in body:
                invalid_frontmatter += 1
            output_hashes.append(hashlib.sha256(rendered.encode("utf-8")).hexdigest())
        scan = scan_persisted_scopes(store.paths, ["markdown"])
        if invalid_frontmatter or scan.total_findings:
            raise AssertionError("Markdown schema or persistence safety failed")

        first_timeline_count = len(server.timeline)
        file_stats = {path.name + str(index): path.stat().st_mtime_ns for index, path in enumerate(markdown_files)}
        second_markdown = [markdown.deliver(projection, now=clock.iso()) for projection in reversed(projections)]
        second_notion = [notion.process(projection, now=clock.iso()) for projection in reversed(projections)]
        second_stats = {path.name + str(index): path.stat().st_mtime_ns for index, path in enumerate(markdown_files)}
        if first_timeline_count != len(server.timeline) or file_stats != second_stats:
            raise AssertionError("Projection-hash replay caused a duplicate sink write")
        if any(
            item.state != "delivered"
            for item in markdown_deliveries + notion_deliveries + second_markdown + second_notion
        ):
            raise AssertionError("A sink projection did not reach delivered")
        if any(item.remote_write != "none" for item in second_notion):
            raise AssertionError("Notion replay performed a duplicate remote write")

        connection = sqlite3.connect(store.paths.database)
        try:
            outbox_states = {
                str(status): int(count)
                for status, count in connection.execute(
                    "SELECT status, COUNT(*) FROM outbox_event GROUP BY status"
                ).fetchall()
            }
            private_placeholder_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM artifact WHERE processor = 'x2n-canonical-placeholder' AND private_payload_present <> 0"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        counts = store.counts()
        expected = {
            "content": case_count,
            "notion_mapping": case_count,
            "outbox_event": case_count * 2,
            "sink_receipt": case_count * 2,
        }
        if any(counts[name] != count for name, count in expected.items()):
            raise AssertionError("Sink durable entity cardinality diverged")
        if outbox_states != {"delivered": case_count * 2}:
            raise AssertionError("A sink Outbox event is not terminal")
        if len(server.pages) != case_count or server.page_create_count != case_count or server.page_update_count != 0:
            raise AssertionError("Notion Mock page idempotency diverged")
        if "Owner Notes" not in server.schemas["items"] or "Owner Notes" not in server.schemas["categories"]:
            raise AssertionError("Notion user schema field was removed")
        times = [float(item["time"]) for item in server.timeline]
        maximum_average_rate = 0.0 if len(times) < 2 else (len(times) - 1) / (times[-1] - times[0])
        if maximum_average_rate > 2.0:
            raise AssertionError("Notion request rate exceeded two per second")
        manifest_hash = canonical_json_sha256(
            {
                "index_hash": index_hash,
                "markdown_output_hashes": sorted(output_hashes),
                "notion_output_hashes": sorted(page.output_hash for page in server.pages.values()),
            }
        )
        return {
            "durable_counts": expected,
            "index_dead_links": 0,
            "index_entries": checked_links,
            "manifest_sha256": manifest_hash,
            "markdown_cdn_findings": scan.total_findings,
            "markdown_files": len(markdown_files),
            "markdown_frontmatter_invalid": invalid_frontmatter,
            "markdown_partial_files": 0,
            "notion_duplicate_pages": 0,
            "notion_mock_pages": len(server.pages),
            "notion_projection_hash_replay_requests": len(server.timeline) - first_timeline_count,
            "notion_schema_user_fields_preserved": True,
            "outbox_states": outbox_states,
            "private_placeholder_payloads": private_placeholder_count,
            "rate_maximum_average_requests_per_second": maximum_average_rate,
            "replay_rounds": 2,
        }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (
        fixture.get("fixture_id") != "FIXTURE.X2N.S02.S005.001"
        or fixture.get("case_count") != 80
        or fixture.get("contains_credentials") is not False
        or fixture.get("contains_local_absolute_paths") is not False
        or fixture.get("contains_media_urls") is not False
        or fixture.get("contains_private_owner_content") is not False
        or fixture.get("notion_mock", {}).get("real_api_calls") != 0
    ):
        raise AssertionError("Sink fixture boundary drifted")
    module = load_test_module()
    unit = run_unit_suite(module)
    return {
        "acceptance_scope": "SKELETON_005_MARKDOWN_NOTION_MOCK_CI_SYNTH",
        "case_count": fixture["case_count"],
        "end_to_end": run_end_to_end(module, int(fixture["case_count"])),
        "fault_matrix": {
            "cases": len(fixture["notion_mock"]["faults"]),
            "max_attempts": 4,
            "retry_after_statuses": [429, 529],
            "status": "PASS_CI_SYNTH_MOCK_SCOPED",
        },
        "fixture_id": fixture["fixture_id"],
        "markdown_status": "PASS_CI_SYNTH_SCOPED",
        "migration": "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
        "notion_api_version": fixture["notion_mock"]["api_version"],
        "notion_mock_status": "PASS_CI_SYNTH_MOCK_SCOPED",
        "notion_real_api_calls": 0,
        "owner_notion_canary": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "schema_version": 2,
        "status": "PASS_CI_SYNTH_MOCK_SCOPED",
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
