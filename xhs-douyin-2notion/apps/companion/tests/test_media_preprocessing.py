from __future__ import annotations

import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from x2n_contracts import CanonicalContent, ErrorCode, build_content_key
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.media_preprocessing import (
    MAX_KEYFRAMES,
    EphemeralDerivedArtifact,
    FrameArtifact,
    FrameCandidate,
    MediaCommand,
    MediaPreprocessor,
    MediaProcessingPolicy,
    MediaToolchain,
    SandboxedCommandRunner,
    deduplicate_frame_candidates,
    select_representative_timestamps,
)
from x2n_companion.media_safety import (
    MAX_MEDIA_LEASE_SECONDS,
    EphemeralMediaSource,
    MediaLeaseCleaner,
    MediaLeaseManager,
    MediaMetadata,
    MediaResponse,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GLOBAL_IP = "93.184.216.34"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _url(host: str) -> str:
    return "https:" + "//" + host + "/synthetic.bin?signature=synthetic"


def _content() -> CanonicalContent:
    content_id = "synthetic-preprocess-001"
    return CanonicalContent.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "content_key": build_content_key("xiaohongshu", content_id),
                "platform": "xiaohongshu",
                "platform_content_id": content_id,
                "canonical_source_url": "https:" + "//www.xiaohongshu.com/explore/" + content_id,
                "content_type": "video",
                "title": "Synthetic preprocessing",
                "description": "Synthetic-only fixture",
                "author_name": "Synthetic author",
                "author_platform_id": "synthetic-author",
                "published_at": "2026-07-28T00:00:00Z",
                "content_hash": _sha(b"synthetic-preprocess-content"),
                "first_observed_at": "2026-07-28T00:00:01Z",
                "last_observed_at": "2026-07-28T00:00:02Z",
                "record_version": 1,
                "status": "active",
            }
        )
    )


def _mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"synthetic-video" * 16


class FakeResponse:
    def __init__(self, headers: Mapping[str, str], chunks: Iterable[bytes]) -> None:
        self.status = 200
        self.headers = headers
        self._chunks = tuple(chunks)

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
        del chunk_size
        yield from self._chunks

    def close(self) -> None:
        return None


class FakeTransport:
    def __init__(self, response: MediaResponse) -> None:
        self.response = response

    def request(self, _target: object, *, timeout_seconds: float) -> MediaResponse:
        if timeout_seconds <= 0:
            raise RuntimeError("synthetic timeout")
        return self.response


class FakeInspector:
    def __init__(self, *, duration_seconds: float | None) -> None:
        self.duration_seconds = duration_seconds

    def inspect(self, path: Path, *, mime: str, timeout_seconds: float) -> MediaMetadata:
        if not path.is_file() or timeout_seconds <= 0 or mime != "video/mp4":
            raise RuntimeError("synthetic inspection failure")
        return MediaMetadata(duration_seconds=self.duration_seconds, width=16, height=16, decoded_pixels=256)


def _resolver(_hostname: str, port: int) -> Sequence[str]:
    if port != 443:
        raise RuntimeError("unexpected port")
    return (GLOBAL_IP,)


class SyntheticRunner:
    def __init__(self, *, probe_kind: str = "video", fail_role: str | None = None) -> None:
        self.probe_kind = probe_kind
        self.fail_role = fail_role
        self.commands: list[MediaCommand] = []

    @staticmethod
    def _write(path: Path, payload: bytes) -> None:
        path.write_bytes(payload)
        path.chmod(0o600)

    def run(self, command: MediaCommand, *, policy: MediaProcessingPolicy) -> None:
        del policy
        self.commands.append(command)
        if command.role == self.fail_role:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Synthetic processor timeout")
        if command.role == "probe":
            assert command.stdout_path is not None
            if self.probe_kind == "video":
                payload = {
                    "format": {"duration": "7200.0"},
                    "programs": [],
                    "stream_groups": [],
                    "streams": [
                        {"codec_type": "video", "width": 16, "height": 16, "duration": "7200.0"},
                        {"codec_type": "audio", "duration": "7200.0"},
                    ],
                }
            elif self.probe_kind == "image_bomb":
                payload = {
                    "format": {"duration": "7200.0"},
                    "programs": [],
                    "stream_groups": [],
                    "streams": [
                        {"codec_type": "video", "width": 20_000, "height": 20_000, "duration": "7200.0"}
                    ],
                }
            elif self.probe_kind == "malformed":
                self._write(command.stdout_path, b"not-json")
                return
            elif self.probe_kind == "audio":
                payload = {
                    "format": {"duration": "7200.0"},
                    "programs": [],
                    "stream_groups": [],
                    "streams": [{"codec_type": "audio", "duration": "7200.0"}],
                }
            else:
                payload = {
                    "format": {"duration": "1.0"},
                    "programs": [],
                    "stream_groups": [],
                    "streams": [{"codec_type": "video", "width": 16, "height": 16, "duration": "1.0"}],
                }
            self._write(command.stdout_path, json.dumps(payload, sort_keys=True).encode("utf-8"))
            return
        if command.role == "audio":
            self._write(command.output_paths[0], b"synthetic-audio")
            return
        if command.role == "frame":
            self._write(command.output_paths[0], b"\xff\xd8\xff" + b"frame" * 16)
            self._write(command.output_paths[1], b"\x80" * 64)
            return
        raise AssertionError("unexpected media command")


class MediaPreprocessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-m001-test-")
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

    def _manager(self) -> MediaLeaseManager:
        return self._manager_for_payload(_mp4(), duration_seconds=7200.0)

    def _manager_for_payload(self, payload: bytes, *, duration_seconds: float) -> MediaLeaseManager:
        response = FakeResponse(
            {"Content-Type": "video/mp4", "Content-Length": str(len(payload))},
            (payload,),
        )
        return MediaLeaseManager(
            self.paths,
            self.store,
            resolver=_resolver,
            transport=FakeTransport(response),
            inspector=FakeInspector(duration_seconds=duration_seconds),
        )

    @staticmethod
    def _source() -> EphemeralMediaSource:
        return EphemeralMediaSource(
            platform="xiaohongshu",
            raw_url=_url("asset." + "xhscdn.com"),
            source_ref_id="synthetic-media-source",
        )

    @staticmethod
    def _toolchain(runner: SyntheticRunner) -> MediaToolchain:
        executable = Path(sys.executable)
        return MediaToolchain(executable, executable, runner)

    def test_video_budget_dedup_and_ephemeral_cleanup(self) -> None:
        runner = SyntheticRunner()
        processor = MediaPreprocessor(self.paths, self.store, toolchain=self._toolchain(runner))
        manager = self._manager()
        with manager.lease(
            self._source(),
            run_id="run-preprocess-video",
            content_key=self.content.content_key,
            purpose="multimodal-preprocess",
            ttl_seconds=60,
            now="2026-07-28T00:00:00Z",
        ) as handle:
            workspace = handle.local_path.with_name(f"{handle.lease_id}.derived")
            with processor.process(handle) as result:
                self.assertTrue(workspace.is_dir())
                self.assertEqual(result.probe.source_kind, "video")
                self.assertEqual(result.candidate_frame_count, MAX_KEYFRAMES)
                self.assertEqual(len(result.frames), 1)
                self.assertEqual(result.duplicates_dropped, MAX_KEYFRAMES - 1)
                self.assertIsNotNone(result.audio)
                self.assertTrue(result.frames[0].local_path.is_file())
                self.assertTrue(result.audio is not None and result.audio.local_path.is_file())
                rendered = json.dumps(result.safe_dict(), sort_keys=True)
                self.assertNotIn(str(self.paths.data_root), rendered)
                self.assertNotIn("xhscdn", rendered)
                with self.assertRaises(TypeError):
                    pickle.dumps(result)
            self.assertFalse(workspace.exists())
            self.assertTrue(handle.local_path.exists())
        self.assertFalse(handle.local_path.exists())
        self.assertEqual(self.store.get_media_lease(handle.lease_id).status, "deleted")  # type: ignore[union-attr]
        self.assertEqual([command.role for command in runner.commands].count("frame"), MAX_KEYFRAMES)

    def test_false_mime_and_processor_timeout_fail_closed_and_clean(self) -> None:
        for runner in (
            SyntheticRunner(probe_kind="audio"),
            SyntheticRunner(probe_kind="image_bomb"),
            SyntheticRunner(probe_kind="malformed"),
            SyntheticRunner(fail_role="probe"),
        ):
            with self.subTest(runner=runner.probe_kind + str(runner.fail_role)):
                processor = MediaPreprocessor(self.paths, self.store, toolchain=self._toolchain(runner))
                manager = self._manager()
                with self.assertRaises(X2NRuntimeError) as error:
                    with manager.lease(
                        self._source(),
                        run_id="run-preprocess-fail-" + str(len(runner.commands)),
                        content_key=self.content.content_key,
                        purpose="multimodal-preprocess",
                        ttl_seconds=60,
                    ) as handle:
                        workspace = handle.local_path.with_name(f"{handle.lease_id}.derived")
                        with processor.process(handle):
                            self.fail("invalid media processor result must not yield")
                self.assertIn(error.exception.code, {ErrorCode.DATA_INTEGRITY_FAILED, ErrorCode.POLICY_BLOCKED})
                self.assertFalse(handle.local_path.exists())
                self.assertFalse(workspace.exists())

    def test_cleaner_recovers_expired_derived_workspace_without_touching_active_lease(self) -> None:
        expired = self.store.create_media_lease(
            run_id="run-preprocess-expired",
            content_key=self.content.content_key,
            purpose="multimodal-preprocess",
            content_hash=_sha(b"expired"),
            mime="image/jpeg",
            size_bytes=1,
            duration_seconds=None,
            ttl_seconds=1,
            now="2026-07-28T00:00:00Z",
        )
        active = self.store.create_media_lease(
            run_id="run-preprocess-active",
            content_key=self.content.content_key,
            purpose="multimodal-preprocess",
            content_hash=_sha(b"active"),
            mime="image/jpeg",
            size_bytes=1,
            duration_seconds=None,
            ttl_seconds=MAX_MEDIA_LEASE_SECONDS,
            now="2026-07-28T00:00:00Z",
        )
        for lease_id in (expired, active):
            record = self.store.get_media_lease(lease_id)
            assert record is not None
            source = self.paths.temp_media_directory / record.local_relative_path
            source.parent.mkdir(mode=0o700)
            source.write_bytes(b"x")
            source.chmod(0o600)
            workspace = source.with_name(f"{lease_id}.derived")
            workspace.mkdir(mode=0o700)
            frame = workspace / "frame-00.jpg"
            frame.write_bytes(b"\xff\xd8\xffx")
            frame.chmod(0o600)
        report = MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-28T00:00:02Z")
        self.assertEqual(report.active_lease_misdeletes, 0)
        expired_record = self.store.get_media_lease(expired)
        active_record = self.store.get_media_lease(active)
        assert expired_record is not None and active_record is not None
        expired_source = self.paths.temp_media_directory / expired_record.local_relative_path
        active_source = self.paths.temp_media_directory / active_record.local_relative_path
        self.assertEqual(expired_record.status, "deleted")
        self.assertFalse(expired_source.exists())
        self.assertFalse(expired_source.with_name(f"{expired}.derived").exists())
        self.assertEqual(active_record.status, "active")
        self.assertTrue(active_source.exists())
        self.assertTrue(active_source.with_name(f"{active}.derived").exists())

    def test_cleaner_removes_24_hour_orphaned_derived_media(self) -> None:
        workspace = self.paths.temp_media_directory / "run-preprocess-orphan" / ("media_" + "a" * 32 + ".derived")
        workspace.mkdir(mode=0o700, parents=True)
        orphan = workspace / "frame-00.jpg"
        orphan.write_bytes(b"\xff\xd8\xfforphan")
        orphan.chmod(0o600)
        old_epoch = 1_784_332_800  # 2026-07-20T00:00:00Z
        os.utime(orphan, (old_epoch, old_epoch))
        report = MediaLeaseCleaner(self.paths, self.store).run(now="2026-07-28T00:00:00Z")
        self.assertGreaterEqual(report.orphan_files_deleted, 1)
        self.assertFalse(orphan.exists())
        self.assertFalse(workspace.exists())

    def test_lifecycle_lock_prevents_cleaner_race_with_preprocessor_workspace(self) -> None:
        runner = SyntheticRunner()
        processor = MediaPreprocessor(self.paths, self.store, toolchain=self._toolchain(runner))
        manager = self._manager()
        cleaner = MediaLeaseCleaner(self.paths, self.store)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with manager.lease(
                self._source(),
                run_id="run-preprocess-race",
                content_key=self.content.content_key,
                purpose="multimodal-preprocess",
                ttl_seconds=1,
                now="2026-07-28T00:00:00Z",
            ) as handle:
                with processor.process(handle) as result:
                    self.assertEqual(len(result.frames), 1)
                    future = executor.submit(cleaner.run, now="2026-07-28T00:00:02Z")
                    time.sleep(0.05)
                    self.assertFalse(future.done())
                    self.assertTrue(handle.local_path.exists())
                self.assertTrue(handle.local_path.exists())
            report = future.result(timeout=2)
        self.assertEqual(report.active_lease_misdeletes, 0)
        self.assertFalse(handle.local_path.exists())

    def test_120_minute_sampling_and_candidate_cap_are_bounded(self) -> None:
        timestamps = select_representative_timestamps(7200.0)
        self.assertEqual(len(timestamps), MAX_KEYFRAMES)
        self.assertTrue(all(0.0 < value < 7200.0 for value in timestamps))
        artifact = FrameArtifact(
            sha256="a" * 64,
            mime="image/jpeg",
            size_bytes=10,
            local_path=Path("/tmp/synthetic-frame.jpg"),
            timestamp_ms=0,
            perceptual_hash="0" * 16,
        )
        candidates = tuple(FrameCandidate(artifact, 0) for _ in range(MAX_KEYFRAMES))
        retained, dropped = deduplicate_frame_candidates(candidates)
        self.assertEqual(len(retained), 1)
        self.assertEqual(len(dropped), MAX_KEYFRAMES - 1)
        with self.assertRaises(X2NRuntimeError) as error:
            deduplicate_frame_candidates(candidates + (FrameCandidate(artifact, 0),))
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_subprocess_timeout_kills_the_process_group(self) -> None:
        policy = MediaProcessingPolicy(command_timeout_seconds=1, total_timeout_seconds=2, cpu_limit_seconds=2)
        with tempfile.TemporaryDirectory(prefix="x2n-m001-timeout-") as temporary:
            workspace = Path(temporary)
            workspace.chmod(0o700)
            command = MediaCommand(
                role="probe",
                argv=("/bin/sh", "-c", "sleep 5"),
                cwd=workspace,
                timeout_seconds=1,
                max_output_bytes=1024,
            )
            started = time.monotonic()
            with self.assertRaises(X2NRuntimeError) as error:
                SandboxedCommandRunner().run(command, policy=policy)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertLess(time.monotonic() - started, 4.0)

    def test_policy_rejects_a_relaxed_unbounded_configuration(self) -> None:
        with self.assertRaises(X2NRuntimeError) as error:
            MediaProcessingPolicy(max_keyframes=MAX_KEYFRAMES + 1)
        self.assertEqual(error.exception.code, ErrorCode.POLICY_BLOCKED)
        artifact = EphemeralDerivedArtifact("b" * 64, "audio/mp4", 1, Path("/tmp/synthetic-audio.m4a"))
        with self.assertRaises(TypeError):
            pickle.dumps(artifact)

    def test_real_ffmpeg_toolchain_smoke_uses_only_temporary_synthetic_media(self) -> None:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("local FFmpeg/FFprobe capability is unavailable")
        fixture = Path(self.temporary.name) / "synthetic-input.mp4"
        generated = subprocess.run(
            (
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:d=0.5",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=0.5",
                "-shortest",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                "-y",
                str(fixture),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if generated.returncode != 0:
            self.skipTest("local FFmpeg cannot create the bounded synthetic fixture")
        manager = self._manager_for_payload(fixture.read_bytes(), duration_seconds=0.5)
        processor = MediaPreprocessor(self.paths, self.store, toolchain=MediaToolchain.discover())
        with manager.lease(
            self._source(),
            run_id="run-preprocess-real-toolchain",
            content_key=self.content.content_key,
            purpose="multimodal-preprocess",
            ttl_seconds=60,
        ) as handle:
            with processor.process(handle) as result:
                self.assertEqual(result.probe.source_kind, "video")
                self.assertIsNotNone(result.audio)
                self.assertGreaterEqual(len(result.frames), 1)
        self.assertFalse(handle.local_path.exists())


if __name__ == "__main__":
    unittest.main()
