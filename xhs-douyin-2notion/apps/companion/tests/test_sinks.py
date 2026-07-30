from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
import unittest
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

from x2n_contracts import (
    Classification,
    ErrorCode,
    TaxonomyCategory,
    canonical_json_sha256,
)
from x2n_contracts.models import CaptureCurrentPayload

from x2n_companion.canonical_store import CanonicalProjection, CanonicalStore
from x2n_companion.markdown_sink import (
    MARKDOWN_RENDERER_VERSION,
    TRANSITION_AFTER_ATOMIC_REPLACE,
    TRANSITION_BEFORE_ATOMIC_REPLACE,
    MarkdownSink,
    parse_frontmatter,
    render_markdown,
)
from x2n_companion.media_safety import scan_persisted_scopes
from x2n_companion.notion_sink import (
    NOTION_MAX_CHILD_BLOCKS_PER_REQUEST,
    NOTION_MAX_RICH_TEXT_CHARS,
    NOTION_PLATFORM_VIEW_VALUES,
    NOTION_SINK_SCHEMA_VERSION,
    NOTION_SYNC_STATUS_FAILED,
    NOTION_SYNC_STATUS_SYNCED,
    TRANSITION_AFTER_NOTION_SUCCESS,
    NotionMockServer,
    NotionSchemaConflict,
    NotionSinkWorker,
    NotionTransportError,
    RateLimitedNotionClient,
    RequestRateGate,
    build_notion_projection,
)
from x2n_companion.orchestrator import CurrentPageOrchestrator, _plan
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError
from x2n_companion.sink_projection import ProjectionText, build_sink_projection


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLATFORMS = ("xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao")


class InjectedKill(RuntimeError):
    pass


class FakeClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 7, 22, 10, 0, 0, tzinfo=timezone.utc)
        self.monotonic_value = 0.0

    def monotonic(self) -> float:
        return self.monotonic_value

    def sleep(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall = datetime.fromtimestamp(self.wall.timestamp() + seconds, tz=timezone.utc)

    def advance(self, seconds: float) -> None:
        self.sleep(seconds)

    def iso(self) -> str:
        return self.wall.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def set_iso(self, value: str) -> None:
        self.wall = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _content_id(platform: str, index: int) -> str:
    return f"990000000{index:010d}" if platform == "taobao" else f"synthetic-{platform}-{index:05d}"


def _page_url(platform: str, content_id: str) -> str:
    return {
        "bilibili": f"https://www.bilibili.com/video/{content_id}",
        "douyin": f"https://www.douyin.com/video/{content_id}",
        "kuaishou": f"https://www.kuaishou.com/short-video/{content_id}",
        "taobao": "https://item.taobao.com/item.htm",
        "weibo": f"https://www.weibo.com/detail/{content_id}",
        "xiaohongshu": f"https://www.xiaohongshu.com/explore/{content_id}",
    }[platform]


def _payload(index: int, *, title_suffix: str = "") -> CaptureCurrentPayload:
    platform = PLATFORMS[index % len(PLATFORMS)]
    content_id = _content_id(platform, index)
    return CaptureCurrentPayload.model_validate_json(
        json.dumps(
            {
                "auto_scroll": False,
                "category_id": None,
                "change_account_state": False,
                "page_context": {
                    "content_id": content_id,
                    "content_type": "image_gallery" if platform == "taobao" else "video",
                    "title": f"Synthetic sink title {index}{title_suffix}",
                },
                "page_url": _page_url(platform, content_id),
                "platform": platform,
                "relation": "saved_current",
                "user_gesture": True,
            },
            ensure_ascii=False,
        )
    )


def _model(model: Any, value: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(value, ensure_ascii=False))


class SinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-s005-sinks-")
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
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def capture(self, index: int, *, variant: str = "base", title_suffix: str = "") -> str:
        payload = _payload(index, title_suffix=title_suffix)
        request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-s005:{variant}:{index}"))
        orchestrator = CurrentPageOrchestrator(self.store, clock=self.clock.iso)
        receipt = orchestrator.execute(
            payload,
            request_id=request_id,
            payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
        )
        self.assertEqual(receipt.state, "succeeded")
        return f"{payload.platform.value}:{payload.page_context.content_id}"

    def seed_rebuild_canonical(self, count: int) -> None:
        """Load a real, validated Canonical fixture in one SQLite transaction for 10k rebuild tests."""

        observed_at = self.clock.iso()
        with self.store._transaction() as connection:
            for index in range(count):
                payload = _payload(index)
                request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-s005:rebuild-seed:{index}"))
                payload_hash = canonical_json_sha256(payload.model_dump(mode="json", by_alias=True))
                content, relation, observation, _, _ = _plan(
                    payload,
                    request_id=request_id,
                    payload_hash=payload_hash,
                    observed_at=observed_at,
                )
                self.store._upsert_content(connection, content, observed_at)
                self.store._upsert_relation(connection, relation, content.platform.value, observed_at)
                self.store._append_observation(connection, observation, observed_at)

    def projection(self, index: int, *, text: ProjectionText | None = None) -> Any:
        key = self.capture(index)
        return build_sink_projection(self.store.projection_snapshot(key), text)

    def notion(
        self,
        *,
        category_page_refs: Mapping[str, str] | None = None,
    ) -> tuple[NotionMockServer, NotionSinkWorker]:
        server = NotionMockServer(monotonic=self.clock.monotonic)
        gate = RequestRateGate(monotonic=self.clock.monotonic, sleeper=self.clock.sleep)
        client = RateLimitedNotionClient(server, gate)
        return server, NotionSinkWorker(self.store, client, category_page_refs=category_page_refs)

    @staticmethod
    def _owner_category(*, category_id: str, slug: str, name: str, version: int) -> TaxonomyCategory:
        return _model(
            TaxonomyCategory,
            {
                "aliases": [],
                "category_id": category_id,
                "created_by": "owner",
                "description": f"Synthetic {name} category",
                "enabled": True,
                "level": 1,
                "name": name,
                "negative_examples": [],
                "positive_examples": [],
                "priority": 1,
                "schema_version": "1.0",
                "slug": slug,
                "version": version,
            },
        )

    @staticmethod
    def _reclassified_projection(
        projection: Any,
        *,
        category: TaxonomyCategory,
        revision: int,
    ) -> Any:
        classification = _model(
            Classification,
            {
                "calibration_bucket": "owner",
                "candidate_ranking": [{"calibrated_score": 1.0, "category_id": str(category.category_id)}],
                "classification_id": f"class_s005_rebuild_{revision:04d}",
                "confidence_raw": 1.0,
                "content_key": projection.canonical.content.content_key,
                "created_at": f"2026-07-22T10:{revision:02d}:00Z",
                "decision_mode": "human",
                "evidence_artifact_ids": [
                    projection.canonical.artifacts[0].artifact_id
                    if projection.canonical.artifacts
                    else "art_s005_rebuild_evidence"
                ],
                "explanation_private_ref": None,
                "primary_category_id": str(category.category_id),
                "review_status": "owner_confirmed",
                "schema_version": "1.0",
                "supersedes_classification_id": None,
                "tags": ["owner"],
                "taxonomy_version": category.version,
            },
        )
        canonical = CanonicalProjection(
            content=projection.canonical.content,
            relations=projection.canonical.relations,
            observation=projection.canonical.observation,
            artifacts=projection.canonical.artifacts,
            classification=classification,
            category=category,
        )
        return build_sink_projection(canonical, projection.text)

    def test_six_platform_markdown_frontmatter_paths_index_and_cdn_scan(self) -> None:
        sink = MarkdownSink(self.store)
        projections = []
        for index in range(6):
            projection = self.projection(
                index,
                text=ProjectionText(summary=f"Synthetic summary {index}", transcript=f"Synthetic transcript {index}"),
            )
            projections.append(projection)
            delivery = sink.deliver(projection, now=self.clock.iso())
            self.assertEqual(delivery.state, "delivered")
            path = sink.content_path(projection)
            self.assertEqual(
                path.relative_to(self.paths.data_root).as_posix(),
                f"runtime/library/content/{PLATFORMS[index]}/{_content_id(PLATFORMS[index], index)}.md",
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            yaml_header = path.read_text(encoding="utf-8").split("---", 2)[1]
            # JSON is a strict YAML 1.2 subset and keeps this package test dependency-free.
            independent = {
                key: json.loads(raw) for key, raw in (line.split(": ", 1) for line in yaml_header.strip().splitlines())
            }
            self.assertEqual(independent["content_key"], frontmatter["content_key"])
            self.assertEqual(frontmatter["content_key"], projection.canonical.content.content_key)
            self.assertEqual(frontmatter["projection_hash"], projection.desired_projection_hash)
            self.assertIn("## Provenance", body)
        sink.seed_unclassified_index(projections)
        self.assertEqual(sink.validate_unclassified_links(), 6)
        scan = scan_persisted_scopes(self.paths, ["markdown"])
        self.assertEqual((scan.status, scan.total_findings), ("PASS", 0))

    def test_long_text_special_characters_are_deterministic_and_second_delivery_is_noop(self) -> None:
        projection = self.projection(
            0,
            text=ProjectionText(
                original_text='特殊字符 --- # []() "quotes"\nsecond line',
                transcript="语音" * 8_192,
                ocr="图文" * 4_096,
                summary="Summary with : colon and {json-like} text",
            ),
        )
        rendered = render_markdown(projection)
        self.assertEqual(rendered, render_markdown(projection))
        frontmatter, body = parse_frontmatter(rendered)
        self.assertEqual(frontmatter["schema_version"], "1.0.0")
        self.assertIn("语音" * 200, body)
        sink = MarkdownSink(self.store)
        first = sink.deliver(projection, now=self.clock.iso())
        path = sink.content_path(projection)
        before = path.read_bytes()
        before_mtime = path.stat().st_mtime_ns
        second = sink.deliver(projection, now=self.clock.iso())
        self.assertEqual(second.disposition.value, "unchanged")
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), (before, before_mtime))
        self.assertEqual(first.output_hash, second.output_hash)

    def test_title_and_owner_category_change_never_change_canonical_path(self) -> None:
        projection = self.projection(1)
        title_only = CanonicalProjection(
            content=projection.canonical.content.model_copy(update={"title": "Title-only change"}),
            relations=projection.canonical.relations,
            observation=projection.canonical.observation,
            artifacts=projection.canonical.artifacts,
            classification=projection.canonical.classification,
            category=projection.canonical.category,
        )
        title_projection = build_sink_projection(title_only)
        sink = MarkdownSink(self.store)
        self.assertEqual(sink.content_path(projection), sink.content_path(title_projection))
        self.assertNotEqual(projection.desired_projection_hash, title_projection.desired_projection_hash)
        category = _model(
            TaxonomyCategory,
            {
                "aliases": [],
                "category_id": "11111111-1111-4111-8111-111111111111",
                "created_by": "owner",
                "description": "Owner category",
                "enabled": True,
                "level": 1,
                "name": "Owner Category",
                "negative_examples": [],
                "positive_examples": [],
                "priority": 1,
                "schema_version": "1.0",
                "slug": "owner-category",
                "version": 1,
            },
        )
        classification = _model(
            Classification,
            {
                "calibration_bucket": "owner",
                "candidate_ranking": [{"calibrated_score": 1.0, "category_id": str(category.category_id)}],
                "classification_id": "class_s005_owner0001",
                "confidence_raw": 1.0,
                "content_key": projection.canonical.content.content_key,
                "created_at": "2026-07-22T10:01:00Z",
                "decision_mode": "human",
                "evidence_artifact_ids": [projection.canonical.artifacts[0].artifact_id],
                "explanation_private_ref": None,
                "primary_category_id": str(category.category_id),
                "review_status": "owner_confirmed",
                "schema_version": "1.0",
                "supersedes_classification_id": None,
                "tags": ["owner"],
                "taxonomy_version": 1,
            },
        )
        changed = CanonicalProjection(
            content=projection.canonical.content.model_copy(update={"title": "Completely changed title"}),
            relations=projection.canonical.relations,
            observation=projection.canonical.observation,
            artifacts=projection.canonical.artifacts,
            classification=classification,
            category=category,
        )
        changed_projection = build_sink_projection(changed)
        self.assertEqual(sink.content_path(projection), sink.content_path(changed_projection))
        self.assertNotEqual(projection.desired_projection_hash, changed_projection.desired_projection_hash)
        category_page_ref = "22222222-2222-4222-8222-222222222222"
        server, worker = self.notion(category_page_refs={str(category.category_id): category_page_ref})
        delivered = worker.process(changed_projection, now=self.clock.iso())
        self.assertEqual(delivered.state, "delivered")
        page = next(iter(server.pages.values()))
        self.assertEqual(page.properties["Category"]["relation"], [{"id": category_page_ref}])

    def test_projection_snapshot_stays_on_one_wal_read_transaction(self) -> None:
        content_key = self.capture(6)
        original = self.store.projection_snapshot(content_key)
        original_open = self.store._open
        interleaved = False

        def write_new_canonical_version() -> None:
            nonlocal interleaved
            interleaved = True
            self.clock.advance(1)
            payload = _payload(6, title_suffix=" interleaved")
            CurrentPageOrchestrator(self.store, clock=self.clock.iso).execute(
                payload,
                request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-s005:interleaved:6")),
                payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
            )

        class InterleavingConnection:
            def __init__(self, connection: Any) -> None:
                self.connection = connection

            def __getattr__(self, name: str) -> Any:
                return getattr(self.connection, name)

            def execute(self, statement: str, *args: Any) -> Any:
                if not interleaved and "SELECT payload_json FROM content" in " ".join(statement.split()):
                    # Pin the explicit read transaction before a concurrent WAL commit.
                    self.connection.execute("SELECT COUNT(*) FROM content").fetchone()
                    write_new_canonical_version()
                return self.connection.execute(statement, *args)

        def open_interleaved(*, writable: bool = True) -> Any:
            connection = original_open(writable=writable)
            return connection if writable else InterleavingConnection(connection)

        with mock.patch.object(self.store, "_open", side_effect=open_interleaved):
            snapshot = self.store.projection_snapshot(content_key)
        self.assertTrue(interleaved)
        self.assertEqual(snapshot.content.title, original.content.title)
        self.assertEqual(snapshot.observation.observation_id, original.observation.observation_id)
        latest = self.store.projection_snapshot(content_key)
        self.assertNotEqual(latest.content.title, original.content.title)
        self.assertNotEqual(latest.observation.observation_id, original.observation.observation_id)

    def test_atomic_kills_leave_old_or_complete_file_and_replay_receipts(self) -> None:
        sink = MarkdownSink(self.store)
        original = self.projection(2, text=ProjectionText(summary="old"))
        sink.deliver(original, now=self.clock.iso())
        path = sink.content_path(original)
        old = path.read_bytes()
        self.clock.advance(1)
        payload = _payload(2, title_suffix=" changed")
        orchestrator = CurrentPageOrchestrator(self.store, clock=self.clock.iso)
        orchestrator.execute(
            payload,
            request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-s005:changed:2")),
            payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
        )
        changed = build_sink_projection(
            self.store.projection_snapshot(original.canonical.content.content_key),
            ProjectionText(summary="new"),
        )

        def before(transition: str) -> None:
            if transition == TRANSITION_BEFORE_ATOMIC_REPLACE:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            sink.deliver(changed, now=self.clock.iso(), transition_hook=before)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(list(path.parent.glob(".*.tmp-*")), [])
        self.clock.advance(61)

        def after(transition: str) -> None:
            if transition == TRANSITION_AFTER_ATOMIC_REPLACE:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            sink.deliver(changed, now=self.clock.iso(), transition_hook=after)
        self.assertNotEqual(path.read_bytes(), old)
        self.clock.advance(61)
        replay = sink.deliver(changed, now=self.clock.iso())
        self.assertEqual(replay.state, "delivered")
        self.assertEqual(self.store.counts()["sink_receipt"], 2)

    def test_rebuild_is_atomic_per_file_and_repairs_category_index_after_kill(self) -> None:
        sink = MarkdownSink(self.store)
        original = self.projection(0, text=ProjectionText(summary="old rebuild summary"))
        first = sink.rebuild([original])
        original_path = sink.content_path(original)
        old = original_path.read_bytes()
        self.assertEqual((first.manifest.content_count, first.checked_links), (1, 1))

        self.clock.advance(1)
        payload = _payload(0, title_suffix=" rebuild changed")
        CurrentPageOrchestrator(self.store, clock=self.clock.iso).execute(
            payload,
            request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-s005:rebuild-kill:0")),
            payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
        )
        changed = build_sink_projection(
            self.store.projection_snapshot(original.canonical.content.content_key),
            ProjectionText(summary="new rebuild summary"),
        )
        self.assertEqual(sink.content_path(changed), original_path)

        def before(transition: str) -> None:
            if transition == TRANSITION_BEFORE_ATOMIC_REPLACE:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            sink.rebuild([changed], transition_hook=before)
        self.assertEqual(original_path.read_bytes(), old)
        self.assertEqual(list(original_path.parent.glob(".*.tmp-*")), [])

        def after(transition: str) -> None:
            if transition == TRANSITION_AFTER_ATOMIC_REPLACE:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            sink.rebuild([changed], transition_hook=after)
        self.assertEqual(original_path.read_bytes(), render_markdown(changed).encode("utf-8"))
        repaired = sink.rebuild([changed])
        self.assertEqual((repaired.checked_links, repaired.manifest.content_count), (1, 1))
        self.assertEqual(sink.validate_category_links(), 1)

    @mock.patch("x2n_companion.markdown_sink.os.fsync")
    def test_ten_thousand_canonical_rebuild_is_deterministic_and_category_only_reclassifies(
        self,
        _fsync: Any,
    ) -> None:
        self.seed_rebuild_canonical(10_000)
        sink = MarkdownSink(self.store)
        canonical_counts = self.store.counts()
        first = sink.rebuild_from_canonical(build_sink_projection)
        self.assertEqual(first.manifest.content_count, 10_000)
        self.assertEqual((first.manifest.category_index_count, first.checked_links), (1, 10_000))
        self.assertEqual(first.content_writes, 10_000)
        self.assertEqual(first.removed_content_files, 0)
        self.assertEqual(self.store.counts(), canonical_counts)
        self.assertEqual(sink.library_manifest(), first.manifest)

        library = self.paths.data_root / "runtime/library"
        shutil.rmtree(library)
        restored = sink.rebuild_from_canonical(build_sink_projection)
        self.assertEqual(restored.manifest, first.manifest)
        self.assertEqual((restored.manifest.content_count, restored.checked_links), (10_000, 10_000))
        second = sink.rebuild_from_canonical(build_sink_projection)
        self.assertEqual(second.manifest, first.manifest)
        self.assertEqual(
            (
                second.content_writes,
                second.category_index_writes,
                second.removed_content_files,
                second.removed_category_indexes,
            ),
            (0, 0, 0, 0),
        )

        projections = [build_sink_projection(snapshot) for snapshot in self.store.projection_snapshots()]
        original_path = sink.content_path(projections[0])
        research = self._owner_category(
            category_id="11111111-1111-4111-8111-111111111111",
            slug="owner-research",
            name="Owner Research",
            version=1,
        )
        categorized = list(projections)
        categorized[0] = self._reclassified_projection(categorized[0], category=research, revision=1)
        category_result = sink.rebuild(categorized)
        self.assertEqual(sink.content_path(categorized[0]), original_path)
        self.assertEqual((category_result.manifest.content_count, category_result.checked_links), (10_000, 10_000))
        research_index = library / "categories/owner-research/INDEX.md"
        self.assertTrue(research_index.is_file())

        renamed = self._owner_category(
            category_id=str(research.category_id),
            slug="owner-research",
            name="Owner Research Renamed",
            version=2,
        )
        renamed_projections = list(categorized)
        renamed_projections[0] = self._reclassified_projection(renamed_projections[0], category=renamed, revision=2)
        renamed_result = sink.rebuild(renamed_projections)
        self.assertEqual(sink.content_path(renamed_projections[0]), original_path)
        self.assertEqual(renamed_result.manifest.content_count, 10_000)
        self.assertIn("# Owner Research Renamed", research_index.read_text(encoding="utf-8"))

        merged = self._owner_category(
            category_id="22222222-2222-4222-8222-222222222222",
            slug="owner-library",
            name="Owner Library",
            version=1,
        )
        merged_projections = list(renamed_projections)
        merged_projections[0] = self._reclassified_projection(merged_projections[0], category=merged, revision=3)
        merged_result = sink.rebuild(merged_projections)
        self.assertEqual(sink.content_path(merged_projections[0]), original_path)
        self.assertEqual((merged_result.manifest.content_count, merged_result.checked_links), (10_000, 10_000))
        self.assertFalse(research_index.exists())
        library_index = library / "categories/owner-library/INDEX.md"
        index_frontmatter, _ = parse_frontmatter(library_index.read_text(encoding="utf-8"))
        self.assertEqual(index_frontmatter["renderer_version"], MARKDOWN_RENDERER_VERSION)
        content_frontmatter, _ = parse_frontmatter(original_path.read_text(encoding="utf-8"))
        self.assertEqual(content_frontmatter["renderer_version"], MARKDOWN_RENDERER_VERSION)
        self.assertEqual(
            len(list((library / "content").glob("*/*.md"))),
            10_000,
        )
        self.assertEqual(len(list((library / "categories").glob("*/*.md"))), 2)
        self.assertEqual(sink.validate_category_links(), 10_000)

    def test_projection_rejects_prohibited_private_text(self) -> None:
        key = self.capture(3)
        snapshot = self.store.projection_snapshot(key)
        for value in (
            "https:" + "//example." + "xhs" + "cdn.com/private.jpg",
            "Authorization: " + "Bear" + "er synthetic",
            "file:///private/example.txt",
            "secret" + "_" + "abcdefghijklmnopqrstuvwxyz",
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                build_sink_projection(snapshot, ProjectionText(summary=value))
            self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
            unsafe_canonical = CanonicalProjection(
                content=snapshot.content.model_copy(update={"title": value}),
                relations=snapshot.relations,
                observation=snapshot.observation,
                artifacts=snapshot.artifacts,
                classification=snapshot.classification,
                category=snapshot.category,
            )
            with self.assertRaises(X2NRuntimeError) as canonical_blocked:
                build_sink_projection(unsafe_canonical)
            self.assertEqual(canonical_blocked.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_markdown_refuses_a_symlink_target_without_touching_its_referent(self) -> None:
        projection = self.projection(5)
        sink = MarkdownSink(self.store)
        target = sink.content_path(projection)
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("do not touch", encoding="utf-8")
        os.symlink(outside, target)
        with self.assertRaises(X2NRuntimeError) as blocked:
            sink.deliver(projection, now=self.clock.iso())
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(outside.read_text(encoding="utf-8"), "do not touch")

    def test_notion_additive_schema_upsert_user_fields_and_projection_hash_noop(self) -> None:
        projection = self.projection(4, text=ProjectionText(summary="first summary"))
        server, worker = self.notion()
        first = worker.process(projection, now=self.clock.iso())
        self.assertEqual((first.state, first.remote_write), ("delivered", "create"))
        self.assertEqual((server.page_create_count, len(server.pages)), (1, 1))
        self.assertIn("Owner Notes", server.schemas["items"])
        self.assertIn("Owner Notes", server.schemas["categories"])
        self.assertIn("X2N Schema Version", server.schemas["items"])
        self.assertIn("X2N Schema Version", server.schemas["categories"])
        self.assertIn("Sync Status", server.schemas["items"])
        page_ref, page = next(iter(server.pages.items()))
        custom = dict(page.properties)
        custom["Owner Manual"] = {"rich_text": _rich_text_for_test("keep me"), "type": "rich_text"}
        server.pages[page_ref] = dataclasses.replace(page, properties=custom)
        timeline = len(server.timeline)
        second = worker.process(projection, now=self.clock.iso())
        self.assertEqual((second.state, second.remote_write), ("delivered", "none"))
        self.assertEqual(len(server.timeline), timeline)

        self.clock.advance(1)
        payload = _payload(4, title_suffix=" changed")
        CurrentPageOrchestrator(self.store, clock=self.clock.iso).execute(
            payload,
            request_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-s005:notion-changed:4")),
            payload_hash=canonical_json_sha256(payload.model_dump(mode="json", by_alias=True)),
        )
        changed = build_sink_projection(
            self.store.projection_snapshot(projection.canonical.content.content_key),
            ProjectionText(summary="second summary"),
        )
        update = worker.process(changed, now=self.clock.iso())
        self.assertEqual((update.state, update.remote_write), ("delivered", "update"))
        self.assertEqual((server.page_create_count, server.page_update_count, len(server.pages)), (1, 1, 1))
        self.assertIn("Owner Manual", server.pages[page_ref].properties)
        self.assertEqual(
            server.pages[page_ref].properties["X2N Schema Version"]["rich_text"][0]["text"]["content"],
            NOTION_SINK_SCHEMA_VERSION,
        )
        self.assertEqual(
            server.pages[page_ref].properties["Sync Status"]["select"]["name"],
            NOTION_SYNC_STATUS_SYNCED,
        )
        self.assertEqual(self.store.counts()["notion_mapping"], 1)

    def test_notion_long_text_is_exactly_chunked_into_bounded_child_batches(self) -> None:
        long_summary = "synthetic paragraph " * 12_000
        projection = self.projection(0, text=ProjectionText(summary=long_summary))
        notion = build_notion_projection(projection)
        self.assertGreater(len(notion.children), NOTION_MAX_CHILD_BLOCKS_PER_REQUEST)
        self.assertEqual(len(notion.child_batches), 2)
        self.assertTrue(all(len(batch) <= NOTION_MAX_CHILD_BLOCKS_PER_REQUEST for batch in notion.child_batches))
        summary_start = next(
            index
            for index, block in enumerate(notion.children)
            if block.get("heading_2", {}).get("rich_text", [{}])[0].get("text", {}).get("content") == "Summary"
        )
        provenance_start = next(
            index
            for index, block in enumerate(notion.children)
            if block.get("heading_2", {}).get("rich_text", [{}])[0].get("text", {}).get("content") == "Provenance"
        )
        fragments = [
            str(block["paragraph"]["rich_text"][0]["text"]["content"])
            for block in notion.children[summary_start + 1 : provenance_start]
        ]
        self.assertEqual("".join(fragments), long_summary)
        self.assertTrue(all(len(fragment) <= NOTION_MAX_RICH_TEXT_CHARS for fragment in fragments))

        server, worker = self.notion()
        delivered = worker.process(projection, now=self.clock.iso())
        self.assertEqual((delivered.state, delivered.remote_write), ("delivered", "create"))
        self.assertEqual((server.page_create_count, server.page_append_count), (1, 1))
        page = next(iter(server.pages.values()))
        self.assertEqual(page.children, notion.children)
        self.assertEqual(page.output_hash, notion.output_hash())

        recovery_projection = self.projection(1, text=ProjectionText(summary=long_summary))
        recovery_notion = build_notion_projection(recovery_projection)
        recovery_server, recovery_worker = self.notion()
        recovery_server.queue_fault(
            "append_page_children",
            NotionTransportError(status=529, code="service_overload", retry_after_seconds=1),
        )
        pending = recovery_worker.process(recovery_projection, now=self.clock.iso())
        self.assertEqual(pending.state, "pending")
        partial = next(iter(recovery_server.pages.values()))
        self.assertEqual(len(partial.children), NOTION_MAX_CHILD_BLOCKS_PER_REQUEST)
        self.assertIsNone(self.store.notion_mapping(recovery_projection.canonical.content.content_key))
        retry_state = self.store.outbox_state(pending.event_id)
        assert retry_state is not None
        self.clock.set_iso(retry_state.not_before)
        recovered = recovery_worker.process(recovery_projection, now=retry_state.not_before)
        self.assertEqual((recovered.state, recovered.remote_write), ("delivered", "update"))
        self.assertEqual((recovery_server.page_create_count, recovery_server.page_update_count), (1, 1))
        self.assertEqual((len(recovery_server.pages), recovery_server.page_append_count), (1, 1))
        recovered_page = next(iter(recovery_server.pages.values()))
        self.assertEqual(recovered_page.children, recovery_notion.children)
        self.assertEqual(recovered_page.output_hash, recovery_notion.output_hash())

    def test_notion_views_are_idempotent_and_never_overwrite_a_conflict(self) -> None:
        server, worker = self.notion()
        first = worker.reconcile_views()
        self.assertEqual(first.capability, "SUPPORTED")
        self.assertEqual((server.view_create_count, len(server.views)), (14, 14))
        self.assertEqual({item.state for item in first.deliveries}, {"created"})
        names = {item.name for item in server.views.values()}
        self.assertEqual(
            names,
            {
                "X2N · Default Table",
                "X2N · Category Gallery",
                "X2N · Favorites",
                "X2N · Likes Inbox",
                "X2N · Needs Review",
                "X2N · Processing Failed",
                "X2N · Recent",
                "X2N · Categories",
                *(f"X2N · Platform · {platform.title()}" for platform in NOTION_PLATFORM_VIEW_VALUES),
            },
        )
        favorites = next(item for item in server.views.values() if item.name == "X2N · Favorites")
        self.assertEqual(favorites.filter, {"property": "Relations", "multi_select": {"contains": "favorited"}})
        category_gallery = next(item for item in server.views.values() if item.name == "X2N · Category Gallery")
        self.assertEqual(category_gallery.view_type, "gallery")
        self.assertEqual(category_gallery.filter, {"property": "Category", "relation": {"is_not_empty": True}})
        self.assertEqual(category_gallery.configuration, {"type": "gallery"})
        needs_review = next(item for item in server.views.values() if item.name == "X2N · Needs Review")
        self.assertEqual(
            needs_review.filter,
            {"property": "Review Status", "select": {"equals": ["unclassified", "suggested"]}},
        )
        processing_failed = next(item for item in server.views.values() if item.name == "X2N · Processing Failed")
        self.assertEqual(
            processing_failed.filter,
            {"property": "Sync Status", "select": {"equals": NOTION_SYNC_STATUS_FAILED}},
        )
        categories = next(item for item in server.views.values() if item.name == "X2N · Categories")
        self.assertEqual(categories.data_source_id, server.categories_data_source_id)
        self.assertEqual(categories.view_type, "gallery")
        for platform in NOTION_PLATFORM_VIEW_VALUES:
            platform_view = next(
                item for item in server.views.values() if item.name == f"X2N · Platform · {platform.title()}"
            )
            self.assertEqual(platform_view.filter, {"property": "Platform", "select": {"equals": platform}})
        second = worker.reconcile_views()
        self.assertEqual(second.capability, "SUPPORTED")
        self.assertEqual((server.view_create_count, len(server.views)), (14, 14))
        self.assertEqual({item.state for item in second.deliveries}, {"unchanged"})

        server.views[favorites.view_ref] = dataclasses.replace(favorites, sorts=())
        with self.assertRaises(NotionSchemaConflict):
            worker.reconcile_views()
        self.assertEqual((server.view_create_count, len(server.views)), (14, 14))

    def test_notion_view_capability_unavailable_returns_documented_fallback(self) -> None:
        server, worker = self.notion()
        server.queue_fault("list_views", NotionTransportError(status=404, code="object_not_found"))
        result = worker.reconcile_views()
        self.assertEqual(result.capability, "FALLBACK_DOCUMENTED")
        self.assertEqual(result.fallback_reason, "notion_object_not_found")
        self.assertEqual(result.deliveries, ())
        self.assertEqual((server.view_create_count, len(server.views)), (0, 0))

    def test_notion_request_timeline_is_serialized_at_two_per_second(self) -> None:
        projection = self.projection(5)
        server, worker = self.notion()
        worker.process(projection, now=self.clock.iso())
        times = [float(item["time"]) for item in server.timeline]
        self.assertGreaterEqual(len(times), 5)
        self.assertTrue(all(current - previous >= 0.5 for previous, current in zip(times, times[1:])))
        for invalid_rate in (True, 0, 3):
            with self.assertRaises(X2NRuntimeError):
                RequestRateGate(
                    requests_per_second=invalid_rate,
                    monotonic=self.clock.monotonic,
                    sleeper=self.clock.sleep,
                )
        for invalid_status in (99, 600):
            with self.assertRaises(ValueError):
                NotionTransportError(status=invalid_status, code="invalid")
        for invalid_code in ("Author" + "ization: private", "A" * 65):
            with self.assertRaises(ValueError):
                NotionTransportError(status=500, code=invalid_code)
        for invalid_attempts in (True, 0, 5):
            with self.assertRaises(X2NRuntimeError):
                NotionSinkWorker(self.store, worker.client, max_attempts=invalid_attempts)

    def test_429_and_529_respect_retry_after_without_losing_outbox(self) -> None:
        projection = self.projection(0)
        server, worker = self.notion()
        server.queue_fault(
            "retrieve_schema:categories",
            NotionTransportError(status=429, code="rate_limited", retry_after_seconds=7),
        )
        first = worker.process(projection, now=self.clock.iso())
        self.assertEqual(first.state, "pending")
        state = self.store.outbox_state(first.event_id)
        assert state is not None
        first_not_before = state.not_before
        self.assertGreaterEqual(first_not_before, "2026-07-22T10:00:07Z")
        server.queue_fault(
            "retrieve_schema:categories",
            NotionTransportError(status=529, code="service_overload", retry_after_seconds=11),
        )
        self.clock.set_iso(first_not_before)
        second = worker.process(projection, now=self.clock.iso())
        self.assertEqual(second.state, "pending")
        state = self.store.outbox_state(first.event_id)
        assert state is not None
        self.assertGreaterEqual(state.not_before, "2026-07-22T10:00:18Z")
        self.clock.set_iso(state.not_before)
        final = worker.process(projection, now=self.clock.iso())
        self.assertEqual(final.state, "delivered")
        self.assertEqual((server.page_create_count, len(server.pages)), (1, 1))

    def test_timeout_and_reset_reach_bounded_dead_letter(self) -> None:
        projection = self.projection(1)
        server, worker = self.notion()
        for error in (TimeoutError(), ConnectionResetError(), TimeoutError(), ConnectionResetError()):
            server.queue_fault("retrieve_schema:categories", error)
        result = worker.process(projection, now=self.clock.iso())
        for _ in range(3):
            state = self.store.outbox_state(result.event_id)
            assert state is not None
            self.clock.set_iso(state.not_before)
            result = worker.process(projection, now=self.clock.iso())
        self.assertEqual((result.state, result.attempt_count), ("dead_letter", 4))
        self.assertEqual(len(server.pages), 0)
        state = self.store.outbox_state(result.event_id)
        assert state is not None
        self.assertEqual(state.last_error_code, "notion_connectionreseterror")

    def test_success_before_receipt_kill_reconciles_one_existing_page(self) -> None:
        projection = self.projection(2)
        server, worker = self.notion()

        def kill(transition: str) -> None:
            if transition == TRANSITION_AFTER_NOTION_SUCCESS:
                raise InjectedKill(transition)

        with self.assertRaises(InjectedKill):
            worker.process(projection, now=self.clock.iso(), transition_hook=kill)
        self.assertEqual((server.page_create_count, len(server.pages)), (1, 1))
        self.assertIsNone(self.store.notion_mapping(projection.canonical.content.content_key))
        self.assertEqual(self.store.counts()["sink_receipt"], 0)
        self.clock.advance(61)
        recovered = worker.reconcile(projection, now=self.clock.iso())
        self.assertEqual((recovered.state, recovered.remote_write), ("delivered", "none"))
        self.assertEqual((server.page_create_count, server.page_update_count, len(server.pages)), (1, 0, 1))
        self.assertIsNotNone(self.store.notion_mapping(projection.canonical.content.content_key))
        self.assertEqual(self.store.counts()["sink_receipt"], 1)

    def test_one_hour_notion_outage_does_not_block_canonical_or_markdown(self) -> None:
        projection = self.projection(3, text=ProjectionText(summary="local survives"))
        markdown = MarkdownSink(self.store)
        markdown_delivery = markdown.deliver(projection, now=self.clock.iso())
        self.assertEqual(markdown_delivery.state, "delivered")
        server, worker = self.notion()
        server.queue_fault(
            "retrieve_schema:categories",
            NotionTransportError(status=529, code="service_overload", retry_after_seconds=3_600),
        )
        pending = worker.process(projection, now=self.clock.iso())
        self.assertEqual(pending.state, "pending")
        self.assertTrue(self.store.content_exists(projection.canonical.content.content_key))
        self.assertTrue(markdown.content_path(projection).is_file())
        state = self.store.outbox_state(pending.event_id)
        assert state is not None
        self.assertGreaterEqual(state.not_before, "2026-07-22T11:00:00Z")
        self.clock.set_iso(state.not_before)
        delivered = worker.process(projection, now=self.clock.iso())
        self.assertEqual(delivered.state, "delivered")

    def test_schema_conflict_dead_letters_without_mutating_user_schema(self) -> None:
        projection = self.projection(4)
        server, worker = self.notion()
        server.schemas["items"]["Name"] = {"id": "name", "name": "Name", "number": {}, "type": "number"}
        before = json.loads(json.dumps(server.schemas, sort_keys=True))
        result = worker.process(projection, now=self.clock.iso())
        self.assertEqual(result.state, "dead_letter")
        self.assertEqual(server.schemas, before)
        self.assertIn("Owner Notes", server.schemas["items"])
        self.assertEqual(len(server.pages), 0)

    def test_duplicate_remote_pages_fail_closed_without_mapping(self) -> None:
        projection = self.projection(5)
        server, worker = self.notion()
        notion_projection = build_notion_projection(projection)
        server.create_page(notion_projection)
        server.create_page(notion_projection)
        result = worker.process(projection, now=self.clock.iso())
        self.assertEqual(result.state, "dead_letter")
        self.assertEqual(len(server.pages), 2)
        self.assertIsNone(self.store.notion_mapping(projection.canonical.content.content_key))

    def test_long_notion_queue_can_process_exact_events_in_reverse_order(self) -> None:
        projections = [self.projection(index) for index in range(12)]
        server, worker = self.notion()
        for projection in reversed(projections):
            result = worker.process(projection, now=self.clock.iso())
            self.assertEqual(result.state, "delivered")
        self.assertEqual((len(server.pages), server.page_create_count), (12, 12))
        self.assertEqual(self.store.counts()["notion_mapping"], 12)

    def test_unclassified_notion_relation_is_empty_and_payload_has_no_media_blocks(self) -> None:
        projection = self.projection(0, text=ProjectionText(summary="plain text only"))
        notion = build_notion_projection(projection)
        self.assertEqual(notion.properties["Category"]["relation"], [])
        rendered = json.dumps({"properties": notion.properties, "children": notion.children}, sort_keys=True)
        self.assertNotIn('"external"', rendered)
        self.assertNotIn('"file"', rendered)


def _rich_text_for_test(value: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": value}}]


if __name__ == "__main__":
    unittest.main()
