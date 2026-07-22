from __future__ import annotations

import hashlib
import json
import os
import pickle
import stat
import tempfile
import time
import unittest
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest import mock

from x2n_contracts import CanonicalContent, ErrorCode, build_content_key
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.media_safety import (
    MAX_MEDIA_LEASE_SECONDS,
    CdnScanReport,
    EphemeralMediaSource,
    MediaInspector,
    MediaLeaseCleaner,
    MediaLeaseManager,
    MediaLimits,
    MediaMetadata,
    MediaResponse,
    ValidatedMediaTarget,
    canonicalize_persistable_page_url,
    download_media,
    scan_persisted_scopes,
    validate_media_target,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError
from x2n_companion import runtime_cli


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GLOBAL_IP = "93.184.216.34"
HOSTS = {
    "xiaohongshu": "asset.xhscdn.com",
    "douyin": "asset.douyinvod.com",
    "bilibili": "asset.bilivideo.com",
    "kuaishou": "asset.kscdn.com",
    "weibo": "asset.sinaimg.cn",
    "taobao": "asset.alicdn.com",
}


def _url(host: str, path: str = "/media.bin", query: str = "") -> str:
    return "https:" + "//" + host + path + (f"?{query}" if query else "")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content() -> CanonicalContent:
    content_id = "synthetic-media-001"
    return CanonicalContent.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "content_key": build_content_key("xiaohongshu", content_id),
                "platform": "xiaohongshu",
                "platform_content_id": content_id,
                "canonical_source_url": _url("www.xiaohongshu.com", f"/explore/{content_id}"),
                "content_type": "image_gallery",
                "title": "Synthetic media lease",
                "description": "Public-safe synthetic content",
                "author_name": "Synthetic author",
                "author_platform_id": "synthetic-author",
                "published_at": "2026-07-22T00:00:00Z",
                "content_hash": _sha("synthetic-content"),
                "first_observed_at": "2026-07-22T00:00:01Z",
                "last_observed_at": "2026-07-22T00:00:02Z",
                "record_version": 1,
                "status": "active",
            }
        )
    )


class FakeResponse:
    def __init__(self, status: int, headers: Mapping[str, str], chunks: Iterable[bytes]) -> None:
        self.status = status
        self.headers = headers
        self._chunks = tuple(chunks)
        self.closed = False

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
        del chunk_size
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class FakeTransport:
    def __init__(self, *responses: MediaResponse) -> None:
        self.responses = list(responses)
        self.targets: list[ValidatedMediaTarget] = []

    def request(self, target: ValidatedMediaTarget, *, timeout_seconds: float) -> MediaResponse:
        self.targets.append(target)
        if timeout_seconds <= 0 or not self.responses:
            raise RuntimeError("synthetic transport exhausted")
        return self.responses.pop(0)


class FakeInspector:
    def __init__(self, metadata: MediaMetadata | None = None, *, fail: bool = False) -> None:
        self.metadata = metadata or MediaMetadata(width=16, height=16, decoded_pixels=256)
        self.fail = fail
        self.calls = 0

    def inspect(self, path: Path, *, mime: str, timeout_seconds: float) -> MediaMetadata:
        self.calls += 1
        if self.fail or not path.is_file() or mime != "image/jpeg" or timeout_seconds <= 0:
            raise RuntimeError("synthetic inspection failure")
        return self.metadata


def _resolver(hostname: str, port: int) -> Sequence[str]:
    if not hostname or port != 443:
        raise RuntimeError("unexpected synthetic resolution")
    return (GLOBAL_IP,)


def _jpeg(size: int = 32) -> bytes:
    return b"\xff\xd8\xff" + b"S" * max(0, size - 5) + b"\xff\xd9"


class MediaSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-s003-test-")
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
        self.content = _content()
        self.store.ingest_bundle(self.content)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _source(self, *, platform: str = "xiaohongshu", query: str = "sign=synthetic") -> EphemeralMediaSource:
        return EphemeralMediaSource(
            platform=platform,
            raw_url=_url(HOSTS[platform], query=query),
            source_ref_id=f"source-{platform}",
        )

    @staticmethod
    def _response(body: bytes | None = None, **headers: str) -> FakeResponse:
        value = body or _jpeg()
        merged = {"Content-Type": "image/jpeg", "Content-Length": str(len(value)), **headers}
        return FakeResponse(200, merged, (value,))

    def _manager(
        self,
        *,
        response: FakeResponse | None = None,
        inspector: MediaInspector | None = None,
        delete_file: Any = None,
        limits: MediaLimits = MediaLimits(),
    ) -> MediaLeaseManager:
        return MediaLeaseManager(
            self.paths,
            self.store,
            resolver=_resolver,
            transport=FakeTransport(response or self._response()),
            inspector=inspector or FakeInspector(),
            delete_file=delete_file,
            limits=limits,
        )

    def test_ephemeral_source_repr_safe_dict_and_pickle_never_emit_url(self) -> None:
        source = self._source()
        rendered = repr(source) + json.dumps(source.safe_dict(), sort_keys=True)
        self.assertNotIn(HOSTS["xiaohongshu"], rendered)
        self.assertNotIn("sign=", rendered)
        self.assertIn("<redacted>", rendered)
        with self.assertRaises(TypeError):
            pickle.dumps(source)

    def test_page_url_canonicalizer_strips_query_and_fragment(self) -> None:
        raw = _url("www.xiaohongshu.com", "/explore/synthetic", "x=1") + "#fragment"
        self.assertEqual(
            canonicalize_persistable_page_url(raw, "xiaohongshu"),
            _url("www.xiaohongshu.com", "/explore/synthetic"),
        )
        for rejected in (
            _url(HOSTS["xiaohongshu"]),
            "http:" + "//www.xiaohongshu.com/explore/1",
            _url("www.xiaohongshu.com", "/a/%252e%252e/b"),
            "https:" + "//user@www.xiaohongshu.com/explore/1",
        ):
            with self.subTest(rejected=rejected), self.assertRaises(X2NRuntimeError) as error:
                canonicalize_persistable_page_url(rejected, "xiaohongshu")
            self.assertEqual(error.exception.code, ErrorCode.URL_REJECTED)

    def test_exact_suffix_allowlist_supports_six_platforms(self) -> None:
        for platform, host in HOSTS.items():
            with self.subTest(platform=platform):
                target = validate_media_target(_url(host), platform=platform, resolver=_resolver)
                self.assertEqual(target.platform, platform)
                self.assertEqual(target.pinned_ip, GLOBAL_IP)
                self.assertNotIn("media.bin", repr(target))

    def test_authority_scheme_path_and_lookalike_inputs_fail_closed(self) -> None:
        values = (
            "http:" + "//" + HOSTS["xiaohongshu"] + "/media.bin",
            "https:" + "//user@" + HOSTS["xiaohongshu"] + "/media.bin",
            "https:" + "//" + HOSTS["xiaohongshu"] + ":444/media.bin",
            _url("xhscdn.com.attacker.example"),
            _url("evilxhscdn.com"),
            _url(HOSTS["xiaohongshu"], "/%252e%252e/private"),
            _url(HOSTS["xiaohongshu"]) + "#fragment",
            "file:" + "///etc/passwd",
            "data:" + "//text/plain,private",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(X2NRuntimeError) as error:
                validate_media_target(value, platform="xiaohongshu", resolver=_resolver)
            self.assertEqual(error.exception.code, ErrorCode.URL_REJECTED)

    def test_private_reserved_and_mapped_dns_answers_fail_closed(self) -> None:
        addresses = (
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "224.0.0.1",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "fc00::1",
            "::ffff:127.0.0.1",
        )
        for address in addresses:
            with self.subTest(address=address), self.assertRaises(X2NRuntimeError) as error:
                validate_media_target(
                    _url(HOSTS["xiaohongshu"]),
                    platform="xiaohongshu",
                    resolver=lambda _host, _port, answer=address: (answer,),
                )
            self.assertEqual(error.exception.code, ErrorCode.URL_REJECTED)
        with self.assertRaises(X2NRuntimeError):
            validate_media_target(
                _url(HOSTS["xiaohongshu"]),
                platform="xiaohongshu",
                resolver=lambda _host, _port: (GLOBAL_IP, "127.0.0.1"),
            )

    def test_redirect_is_revalidated_and_dns_rebind_is_blocked(self) -> None:
        redirect = FakeResponse(302, {"Location": _url(HOSTS["xiaohongshu"], "/second")}, ())
        final = self._response()
        transport = FakeTransport(redirect, final)
        calls = 0

        def rebinding(_host: str, _port: int) -> Sequence[str]:
            nonlocal calls
            calls += 1
            return (GLOBAL_IP,) if calls == 1 else ("127.0.0.1",)

        destination = self.paths.temp_media_directory / "redirect" / "media_test.bin"
        with self.assertRaises(X2NRuntimeError) as error:
            download_media(
                self._source(),
                paths=self.paths,
                destination=destination,
                resolver=rebinding,
                transport=transport,
                inspector=FakeInspector(),
            )
        self.assertEqual(error.exception.code, ErrorCode.URL_REJECTED)
        self.assertEqual(calls, 2)
        self.assertTrue(redirect.closed)
        self.assertFalse(destination.exists())

    def test_valid_download_is_ip_pinned_owner_only_and_bounded(self) -> None:
        response = self._response()
        transport = FakeTransport(response)
        destination = self.paths.temp_media_directory / "download" / "media_test.bin"
        downloaded = download_media(
            self._source(),
            paths=self.paths,
            destination=destination,
            resolver=_resolver,
            transport=transport,
            inspector=FakeInspector(),
        )
        self.assertEqual(downloaded.content_hash, hashlib.sha256(_jpeg()).hexdigest())
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(transport.targets[0].pinned_ip, GLOBAL_IP)
        self.assertEqual(transport.targets[0].request_target, "/media.bin?sign=synthetic")
        self.assertNotIn("sign=", repr(transport.targets[0]))
        self.assertTrue(response.closed)

    def test_download_rejects_oversize_stream_and_removes_partial_file(self) -> None:
        body = _jpeg(40)
        response = FakeResponse(200, {"Content-Type": "image/jpeg"}, (body[:20], body[20:]))
        destination = self.paths.temp_media_directory / "oversize" / "media_test.bin"
        with self.assertRaises(X2NRuntimeError) as error:
            download_media(
                self._source(),
                paths=self.paths,
                destination=destination,
                resolver=_resolver,
                transport=FakeTransport(response),
                inspector=FakeInspector(),
                limits=MediaLimits(max_bytes=32),
            )
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertFalse(destination.exists())
        self.assertFalse(destination.with_suffix(".bin.part").exists())

        collision = self.paths.temp_media_directory / "collision" / "media_test.bin"
        collision.parent.mkdir(mode=0o700)
        preexisting_partial = collision.with_suffix(".bin.part")
        preexisting_partial.write_bytes(b"preexisting-owner-data")
        preexisting_partial.chmod(0o600)
        collision_response = self._response()
        with self.assertRaises(X2NRuntimeError) as collision_error:
            download_media(
                self._source(),
                paths=self.paths,
                destination=collision,
                resolver=_resolver,
                transport=FakeTransport(collision_response),
                inspector=FakeInspector(),
            )
        self.assertEqual(collision_error.exception.code, ErrorCode.STORAGE_FAILED)
        self.assertEqual(preexisting_partial.read_bytes(), b"preexisting-owner-data")
        self.assertTrue(collision_response.closed)

    def test_download_deadline_and_prestream_rejection_close_response(self) -> None:
        deadline_response = self._response()
        destination = self.paths.temp_media_directory / "deadline" / "media_test.bin"
        ticks = iter((0.0, 0.0, 61.0))
        with self.assertRaises(X2NRuntimeError) as deadline:
            download_media(
                self._source(),
                paths=self.paths,
                destination=destination,
                resolver=_resolver,
                transport=FakeTransport(deadline_response),
                inspector=FakeInspector(),
                monotonic=lambda: next(ticks),
            )
        self.assertEqual(deadline.exception.code, ErrorCode.NETWORK_FAILED)
        self.assertTrue(deadline_response.closed)
        self.assertFalse(destination.exists())

        rejected_response = FakeResponse(500, {}, ())
        with self.assertRaises(X2NRuntimeError) as rejected:
            download_media(
                self._source(),
                paths=self.paths,
                destination=self.paths.temp_media_directory / "rejected" / "media_test.bin",
                resolver=_resolver,
                transport=FakeTransport(rejected_response),
                inspector=FakeInspector(),
            )
        self.assertEqual(rejected.exception.code, ErrorCode.NETWORK_FAILED)
        self.assertTrue(rejected_response.closed)

    def test_download_rejects_fake_mime_corruption_encoding_and_length(self) -> None:
        cases = (
            FakeResponse(200, {"Content-Type": "image/png", "Content-Length": "5"}, (b"plain",)),
            FakeResponse(200, {"Content-Type": "text/html", "Content-Length": "5"}, (b"plain",)),
            FakeResponse(200, {"Content-Type": "image/jpeg", "Content-Encoding": "gzip"}, (_jpeg(),)),
            FakeResponse(200, {"Content-Type": "image/jpeg", "Content-Length": "999"}, (_jpeg(),)),
        )
        for index, response in enumerate(cases):
            destination = self.paths.temp_media_directory / f"bad-{index}" / "media_test.bin"
            with self.subTest(index=index), self.assertRaises(X2NRuntimeError):
                download_media(
                    self._source(),
                    paths=self.paths,
                    destination=destination,
                    resolver=_resolver,
                    transport=FakeTransport(response),
                    inspector=FakeInspector(),
                )
            self.assertFalse(destination.exists())

    def test_inspector_resource_limits_and_failure_remove_promoted_file(self) -> None:
        inspectors = (
            FakeInspector(MediaMetadata(duration_seconds=7_201.0)),
            FakeInspector(MediaMetadata(duration_seconds=float("nan"))),
            FakeInspector(MediaMetadata(width=20_000, height=20_000, decoded_pixels=400_000_000)),
            FakeInspector(fail=True),
        )
        for index, inspector in enumerate(inspectors):
            destination = self.paths.temp_media_directory / f"inspect-{index}" / "media_test.bin"
            with self.subTest(index=index), self.assertRaises(X2NRuntimeError):
                download_media(
                    self._source(),
                    paths=self.paths,
                    destination=destination,
                    resolver=_resolver,
                    transport=FakeTransport(self._response()),
                    inspector=inspector,
                )
            self.assertFalse(destination.exists())

    def test_successful_lease_is_registered_without_url_and_deleted_immediately(self) -> None:
        manager = self._manager()
        with manager.lease(
            self._source(),
            run_id="run-media-success",
            content_key=self.content.content_key,
            purpose="ocr-input",
            ttl_seconds=60,
            now="2026-07-22T00:00:00Z",
        ) as handle:
            self.assertTrue(handle.local_path.is_file())
            safe = json.dumps(handle.safe_dict(), sort_keys=True)
            self.assertNotIn(HOSTS["xiaohongshu"], safe)
            lease_id = handle.lease_id
            processing = self.store.get_media_lease(lease_id)
            assert processing is not None
            self.assertEqual(processing.status, "processing")
            self.assertEqual(processing.content_hash, hashlib.sha256(_jpeg()).hexdigest())
        self.assertIsNotNone(handle.cleanup_report)
        self.assertEqual(handle.cleanup_report.status, "PASS")
        self.assertFalse(handle.local_path.exists())
        record = self.store.get_media_lease(lease_id)
        assert record is not None
        self.assertEqual(record.status, "deleted")
        self.assertNotIn(HOSTS["xiaohongshu"], json.dumps(record.safe_dict(), sort_keys=True))

    def test_processing_exception_still_deletes_media(self) -> None:
        manager = self._manager()
        with self.assertRaisesRegex(RuntimeError, "synthetic processing"):
            with manager.lease(
                self._source(),
                run_id="run-media-failure",
                content_key=self.content.content_key,
                purpose="ocr-input",
                ttl_seconds=60,
            ) as handle:
                raise RuntimeError("synthetic processing")
        self.assertFalse(handle.local_path.exists())
        self.assertEqual(self.store.get_media_lease(handle.lease_id).status, "deleted")  # type: ignore[union-attr]

    def test_lease_rejects_cross_platform_source_before_transport(self) -> None:
        manager = self._manager()
        with self.assertRaises(X2NRuntimeError) as error:
            with manager.lease(
                self._source(platform="douyin"),
                run_id="run-cross-platform",
                content_key=self.content.content_key,
                purpose="ocr-input",
                ttl_seconds=60,
            ):
                self.fail("cross-platform media lease must not be yielded")
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_cleanup_failure_is_high_priority_and_retryable(self) -> None:
        def deny_delete(_path: Path) -> None:
            raise PermissionError("synthetic deny")

        manager = self._manager(delete_file=deny_delete)
        with self.assertRaises(X2NRuntimeError) as error:
            with manager.lease(
                self._source(),
                run_id="run-media-cleanup-error",
                content_key=self.content.content_key,
                purpose="ocr-input",
                ttl_seconds=60,
            ) as handle:
                self.assertTrue(handle.local_path.exists())
        self.assertEqual(error.exception.code, ErrorCode.STORAGE_FAILED)
        record = self.store.get_media_lease(handle.lease_id)
        assert record is not None
        self.assertEqual(record.status, "cleanup_pending")
        self.assertEqual(record.cleanup_error_code, ErrorCode.STORAGE_FAILED.value)
        report = MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-22T00:00:00Z")
        self.assertEqual(report.status, "PASS")
        self.assertFalse(handle.local_path.exists())

        def fail_before_yield(lease_id: str, **_metadata: object) -> None:
            record = self.store.get_media_lease(lease_id)
            assert record is not None
            part = self.paths.temp_media_directory / (record.local_relative_path + ".part")
            part.write_bytes(b"synthetic-partial")
            part.chmod(0o600)
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Synthetic finalization failure")

        pre_yield_manager = self._manager(delete_file=deny_delete)
        with mock.patch.object(self.store, "finalize_media_lease", side_effect=fail_before_yield):
            with self.assertRaises(X2NRuntimeError) as pre_yield_error:
                with pre_yield_manager.lease(
                    self._source(),
                    run_id="run-media-pre-yield-error",
                    content_key=self.content.content_key,
                    purpose="ocr-input",
                    ttl_seconds=60,
                    now="2026-07-22T00:00:00Z",
                ):
                    self.fail("failed finalization must not yield a private media path")
        self.assertEqual(pre_yield_error.exception.code, ErrorCode.STORAGE_FAILED)
        pending = [
            item for item in self.store.list_media_leases() if item.run_id == "run-media-pre-yield-error"
        ]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].status, "cleanup_pending")
        retry = MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-22T00:00:00Z")
        self.assertEqual(retry.deleted_files, 2)
        self.assertEqual(self.store.get_media_lease(pending[0].lease_id).status, "deleted")  # type: ignore[union-attr]

    def test_cleaner_deletes_expired_but_not_unexpired_active_lease(self) -> None:
        with self.assertRaises(X2NRuntimeError) as invalid_identity:
            self.store.create_media_lease(
                run_id="run-invalid-identity",
                content_key=self.content.content_key,
                purpose="synthetic",
                content_hash=_sha("invalid"),
                mime="image/jpeg",
                size_bytes=1,
                duration_seconds=None,
                ttl_seconds=1,
                now="2026-07-22T00:00:00Z",
                lease_id="media_not-a-random-identity",
            )
        self.assertEqual(invalid_identity.exception.code, ErrorCode.INVALID_INPUT)
        with self.assertRaises(X2NRuntimeError) as invalid_time:
            MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-22T00:00:00+00:00")
        self.assertEqual(invalid_time.exception.code, ErrorCode.INVALID_INPUT)

        active_id = self.store.create_media_lease(
            run_id="run-active",
            content_key=self.content.content_key,
            purpose="synthetic",
            content_hash=_sha("active"),
            mime="image/jpeg",
            size_bytes=1,
            duration_seconds=None,
            ttl_seconds=MAX_MEDIA_LEASE_SECONDS,
            now="2026-07-22T00:00:00Z",
        )
        expired_id = self.store.create_media_lease(
            run_id="run-expired",
            content_key=self.content.content_key,
            purpose="synthetic",
            content_hash=_sha("expired"),
            mime="image/jpeg",
            size_bytes=1,
            duration_seconds=None,
            ttl_seconds=1,
            now="2026-07-22T00:00:00Z",
        )
        for lease_id in (active_id, expired_id):
            record = self.store.get_media_lease(lease_id)
            assert record is not None
            path = self.paths.temp_media_directory / record.local_relative_path
            path.parent.mkdir(mode=0o700)
            path.write_bytes(b"x")
            path.chmod(0o600)
        report = MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-22T00:00:02Z")
        self.assertEqual(report.active_lease_misdeletes, 0)
        self.assertEqual(report.deleted_files, 1)
        active = self.store.get_media_lease(active_id)
        expired = self.store.get_media_lease(expired_id)
        assert active is not None and expired is not None
        self.assertTrue((self.paths.temp_media_directory / active.local_relative_path).exists())
        self.assertEqual(active.status, "active")
        self.assertEqual(expired.status, "deleted")

    def test_cleaner_records_every_delete_failure_as_high_priority(self) -> None:
        lease_id = self.store.create_media_lease(
            run_id="run-cleaner-deny",
            content_key=self.content.content_key,
            purpose="synthetic",
            content_hash=_sha("deny"),
            mime="image/jpeg",
            size_bytes=1,
            duration_seconds=None,
            ttl_seconds=1,
            now="2026-07-22T00:00:00Z",
        )
        record = self.store.get_media_lease(lease_id)
        assert record is not None
        path = self.paths.temp_media_directory / record.local_relative_path
        path.parent.mkdir(mode=0o700)
        path.write_bytes(b"x")
        path.chmod(0o600)
        report = MediaLeaseCleaner(
            self.paths,
            self.store,
            delete_file=lambda _path: (_ for _ in ()).throw(PermissionError("synthetic")),
        ).run(now="2026-07-22T00:00:02Z")
        self.assertEqual(report.high_priority_errors, 1)
        self.assertEqual(report.status, "FAIL_CLOSED")
        self.assertEqual(self.store.get_media_lease(lease_id).status, "cleanup_pending")  # type: ignore[union-attr]

    def test_cleaner_removes_old_orphan_but_preserves_recent_orphan(self) -> None:
        directory = self.paths.temp_media_directory / "run-orphan"
        directory.mkdir(mode=0o700)
        old = directory / "media_old.bin.part"
        recent = directory / "media_recent.bin.part"
        old.write_bytes(b"old")
        recent.write_bytes(b"recent")
        old.chmod(0o600)
        recent.chmod(0o600)
        old_epoch = datetime_epoch("2026-07-20T00:00:00Z")
        os.utime(old, (old_epoch, old_epoch))
        report = MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-22T00:00:00Z")
        self.assertEqual(report.orphan_files_deleted, 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_lifecycle_lock_prevents_cleaner_race_with_active_context(self) -> None:
        manager = self._manager()
        cleaner = MediaLeaseCleaner(self.paths, self.store)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with manager.lease(
                self._source(),
                run_id="run-race",
                content_key=self.content.content_key,
                purpose="ocr-input",
                ttl_seconds=1,
                now="2026-07-22T00:00:00Z",
            ) as handle:
                future = executor.submit(cleaner.run, now="2026-07-22T00:00:02Z")
                time.sleep(0.05)
                self.assertFalse(future.done())
                self.assertTrue(handle.local_path.exists())
            report = future.result(timeout=2)
        self.assertEqual(report.active_lease_misdeletes, 0)
        self.assertFalse(handle.local_path.exists())

    def test_scanner_is_clean_then_detects_all_persistence_classes_without_values(self) -> None:
        clean = scan_persisted_scopes(
            self.paths,
            ("db", "markdown", "logs", "notion-export", "artifacts"),
        )
        self.assertIsInstance(clean, CdnScanReport)
        self.assertEqual(clean.status, "PASS")
        log = self.paths.data_root / "runtime/logs/synthetic.log"
        log.write_text(
            _url(HOSTS["xiaohongshu"], query="xsec_" + "token=synthetic")
            + "\n"
            + _url("www.xiaohongshu.com", "/explore/1", "tracking_id=synthetic"),
            encoding="utf-8",
        )
        log.chmod(0o600)
        report = scan_persisted_scopes(self.paths, ("logs",))
        self.assertEqual(report.status, "FAIL_CLOSED")
        self.assertGreaterEqual(report.findings["platform_media_url"], 1)
        self.assertGreaterEqual(report.findings["sensitive_query"], 2)
        self.assertGreaterEqual(report.findings["canonical_query_or_fragment"], 1)
        rendered = json.dumps(report.safe_dict(), sort_keys=True)
        self.assertNotIn(HOSTS["xiaohongshu"], rendered)
        self.assertNotIn(str(self.paths.data_root), rendered)

    def test_scanner_detects_chunk_boundary_and_rejects_arbitrary_scope_or_symlink(self) -> None:
        log = self.paths.data_root / "runtime/logs/boundary.log"
        payload = b"A" * (1024 * 1024 - 10) + _url(HOSTS["douyin"]).encode("ascii")
        log.write_bytes(payload)
        log.chmod(0o600)
        report = scan_persisted_scopes(self.paths, ("logs",))
        self.assertGreaterEqual(report.findings["platform_media_url"], 1)
        for scopes in (("logs", "logs"), ("/tmp",), ()):
            with self.subTest(scopes=scopes), self.assertRaises(X2NRuntimeError):
                scan_persisted_scopes(self.paths, scopes)
        target = self.paths.data_root / "runtime/logs-target"
        target.mkdir(mode=0o700)
        link = self.paths.data_root / "runtime/logs/link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(X2NRuntimeError) as error:
            scan_persisted_scopes(self.paths, ("logs",))
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_cdn_zero_cli_accepts_only_fixed_logical_scopes(self) -> None:
        args = runtime_cli.build_parser().parse_args(
            ["verify", "cdn-zero", "--scopes", "db,markdown,logs,notion-export,artifacts"]
        )
        with mock.patch.dict(
            os.environ,
            {
                "X2N_DATA_ROOT": str(self.paths.data_root),
                "X2N_DOWNLOAD_DESTINATION": str(self.paths.download_destination),
            },
            clear=False,
        ):
            payload = runtime_cli.run(args)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["task_id"], "TSK.x2n.skeleton.003")
        self.assertFalse(payload["private_path_emitted"])

    def test_errors_do_not_include_source_url_or_exception_cause(self) -> None:
        raw = _url(HOSTS["xiaohongshu"], query="sign=must-not-leak")
        with self.assertRaises(X2NRuntimeError) as caught:
            validate_media_target(
                raw,
                platform="xiaohongshu",
                resolver=lambda _host, _port: (_ for _ in ()).throw(RuntimeError(raw)),
            )
        self.assertNotIn("must-not-leak", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)


def datetime_epoch(value: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").timestamp()


if __name__ == "__main__":
    unittest.main()
