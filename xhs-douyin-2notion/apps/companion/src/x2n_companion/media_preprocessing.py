"""Bounded, lease-scoped FFmpeg/FFprobe media preprocessing.

This module is intentionally not an ingestion API.  It receives an already
validated :class:`~x2n_companion.media_safety.MediaLeaseHandle`, creates only
ephemeral audio/frame artifacts below that lease's private workspace, and
removes them before control returns to the caller.  The public-safe result
contains opaque hashes and counts only; artifact paths are intentionally
non-serializable and are usable only inside the processing context.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import signal
import stat
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from x2n_contracts import ErrorCode

from .canonical_store import CanonicalStore, MediaLeaseRecord
from .media_safety import MediaLeaseHandle, derived_media_workspace
from .runtime import RuntimePaths, X2NRuntimeError

try:
    import resource
except ImportError:  # pragma: no cover - Windows must fail closed before spawn.
    resource = None  # type: ignore[assignment]


TASK_ID = "TSK.x2n.multimodal.001"
RESOURCE_POLICY_VERSION = "x2n-media-preprocess-v1"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_DURATION_SECONDS = 2 * 60 * 60
MAX_KEYFRAMES = 50
MAX_DIMENSION = 8_192
MAX_DECODED_PIXELS = 16_777_216
MAX_DERIVATIVE_BYTES = 96 * 1024 * 1024
MAX_PROBE_BYTES = 64 * 1024
_PERCEPTUAL_HASH_BYTES = 64
_DERIVED_SUFFIXES = frozenset({".jpg", ".m4a", ".raw", ".json"})


def _fail(code: ErrorCode, message: str) -> None:
    raise X2NRuntimeError(code, message)


def _finite_number(value: object, *, label: str, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, f"Media {label} is invalid")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, f"Media {label} is invalid")
    if not math.isfinite(parsed) or parsed < 0:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, f"Media {label} is invalid")
    return parsed


def _safe_positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, f"Media {label} is invalid")
    return value


def _sha256_file(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.POLICY_BLOCKED, "Temporary media source is unsafe")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    _fail(ErrorCode.POLICY_BLOCKED, "Temporary media exceeds the processor byte policy")
                digest.update(chunk)
    except X2NRuntimeError:
        raise
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media source is unavailable") from None
    if size == 0:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Temporary media source is empty")
    return digest.hexdigest(), size


def _owned_regular_file(path: Path, *, maximum_bytes: int, suffix: str | None = None) -> int:
    if suffix is not None and path.suffix != suffix:
        _fail(ErrorCode.POLICY_BLOCKED, "Media processor output path is invalid")
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media processor output is unavailable")
    try:
        metadata = path.stat()
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media processor output is unavailable") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail(ErrorCode.POLICY_BLOCKED, "Media processor output is not owner-only")
    if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
        _fail(ErrorCode.POLICY_BLOCKED, "Media processor output exceeds its resource policy")
    return int(metadata.st_size)


def _private_child(root: Path, name: str) -> Path:
    candidate = root / name
    if Path(name).is_absolute() or "/" in name or "\\" in name or ".." in Path(name).parts:
        _fail(ErrorCode.POLICY_BLOCKED, "Media processor output name is invalid")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "Media processor output escaped its workspace")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media processor workspace is unavailable") from None
    return candidate


@dataclass(frozen=True)
class MediaProcessingPolicy:
    """Hard limits for one lease-scoped preprocessing transaction."""

    version: str = RESOURCE_POLICY_VERSION
    max_input_bytes: int = MAX_SOURCE_BYTES
    max_duration_seconds: int = MAX_DURATION_SECONDS
    max_width: int = MAX_DIMENSION
    max_height: int = MAX_DIMENSION
    max_decoded_pixels: int = MAX_DECODED_PIXELS
    max_keyframes: int = MAX_KEYFRAMES
    sample_interval_seconds: int = 144
    max_audio_bytes: int = 32 * 1024 * 1024
    max_frame_bytes: int = 2 * 1024 * 1024
    max_derivative_bytes: int = MAX_DERIVATIVE_BYTES
    max_probe_bytes: int = MAX_PROBE_BYTES
    command_timeout_seconds: int = 20
    total_timeout_seconds: int = 120
    cpu_limit_seconds: int = 120
    max_memory_bytes: int = 768 * 1024 * 1024
    max_open_files: int = 32
    near_duplicate_hamming_distance: int = 8

    def __post_init__(self) -> None:
        if self.version != RESOURCE_POLICY_VERSION:
            _fail(ErrorCode.INVALID_INPUT, "Media processor policy version is unsupported")
        positive = (
            "max_input_bytes",
            "max_duration_seconds",
            "max_width",
            "max_height",
            "max_decoded_pixels",
            "max_keyframes",
            "sample_interval_seconds",
            "max_audio_bytes",
            "max_frame_bytes",
            "max_derivative_bytes",
            "max_probe_bytes",
            "command_timeout_seconds",
            "total_timeout_seconds",
            "cpu_limit_seconds",
            "max_memory_bytes",
            "max_open_files",
        )
        for label in positive:
            _safe_positive_int(getattr(self, label), label=label)
        if (
            self.max_input_bytes > MAX_SOURCE_BYTES
            or self.max_duration_seconds > MAX_DURATION_SECONDS
            or self.max_width > MAX_DIMENSION
            or self.max_height > MAX_DIMENSION
            or self.max_decoded_pixels > MAX_DECODED_PIXELS
            or self.max_keyframes > MAX_KEYFRAMES
            or self.max_derivative_bytes > MAX_DERIVATIVE_BYTES
            or self.max_probe_bytes > MAX_PROBE_BYTES
            or self.command_timeout_seconds > self.total_timeout_seconds
            or self.cpu_limit_seconds > self.total_timeout_seconds
            or self.max_open_files > 64
            or self.max_memory_bytes > 1024 * 1024 * 1024
            or self.max_audio_bytes > self.max_derivative_bytes
            or self.max_frame_bytes > self.max_derivative_bytes
            or not 0 <= self.near_duplicate_hamming_distance <= 16
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "Media processor policy exceeds its approved budget")

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "command_timeout_seconds": self.command_timeout_seconds,
            "cpu_limit_seconds": self.cpu_limit_seconds,
            "max_audio_bytes": self.max_audio_bytes,
            "max_decoded_pixels": self.max_decoded_pixels,
            "max_derivative_bytes": self.max_derivative_bytes,
            "max_frame_bytes": self.max_frame_bytes,
            "max_input_bytes": self.max_input_bytes,
            "max_keyframes": self.max_keyframes,
            "max_memory_bytes": self.max_memory_bytes,
            "max_probe_bytes": self.max_probe_bytes,
            "max_duration_seconds": self.max_duration_seconds,
            "near_duplicate_hamming_distance": self.near_duplicate_hamming_distance,
            "sample_interval_seconds": self.sample_interval_seconds,
            "total_timeout_seconds": self.total_timeout_seconds,
            "version": self.version,
        }


@dataclass(frozen=True)
class MediaCommand:
    """Fully code-derived subprocess request; paths never enter a safe receipt."""

    role: Literal["probe", "audio", "frame"]
    argv: tuple[str, ...] = field(repr=False)
    cwd: Path = field(repr=False)
    stdout_path: Path | None = field(default=None, repr=False)
    output_paths: tuple[Path, ...] = field(default=(), repr=False)
    timeout_seconds: float = 1.0
    max_output_bytes: int = 1


class MediaCommandRunner(Protocol):
    def run(self, command: MediaCommand, *, policy: MediaProcessingPolicy) -> None:
        """Run a code-derived media command or raise a stable safe error."""


def _sandbox_preexec(policy: MediaProcessingPolicy, *, output_limit: int) -> Callable[[], None]:
    """Build a POSIX child hook; unavailable kernel limits fail closed before spawn."""

    required = ("RLIMIT_CPU", "RLIMIT_FSIZE", "RLIMIT_NOFILE")
    if resource is None or os.name != "posix" or any(not hasattr(resource, name) for name in required):
        _fail(ErrorCode.POLICY_BLOCKED, "Media processor sandbox is unavailable")

    def apply_limits() -> None:
        try:
            os.umask(0o077)
            resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_limit_seconds, policy.cpu_limit_seconds + 1))
            resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit, output_limit))
            resource.setrlimit(resource.RLIMIT_NOFILE, (policy.max_open_files, policy.max_open_files))
        except (OSError, ValueError):
            os._exit(127)

    return apply_limits


def _open_stdout(path: Path) -> int:
    if path.is_symlink() or path.exists():
        _fail(ErrorCode.POLICY_BLOCKED, "Media probe output already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media probe output is unavailable") from None
    return descriptor


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


class SandboxedCommandRunner:
    """Run FFmpeg tools without a shell, inherited secrets, logs, or loose limits."""

    def run(self, command: MediaCommand, *, policy: MediaProcessingPolicy) -> None:
        if (
            not command.argv
            or not Path(command.argv[0]).is_absolute()
            or any(not isinstance(value, str) or not value or "\x00" in value for value in command.argv)
            or not command.cwd.is_absolute()
            or command.cwd.is_symlink()
            or not command.cwd.is_dir()
            or not 0 < command.timeout_seconds <= policy.command_timeout_seconds
            or not 0 < command.max_output_bytes <= policy.max_derivative_bytes
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "Media processor command is outside its policy")
        stdout_descriptor: int | None = None
        stdout: int | object = subprocess.DEVNULL
        try:
            if command.stdout_path is not None:
                stdout_descriptor = _open_stdout(command.stdout_path)
                stdout = stdout_descriptor
            process = subprocess.Popen(
                command.argv,
                cwd=command.cwd,
                env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
                preexec_fn=_sandbox_preexec(policy, output_limit=command.max_output_bytes),
            )
        except X2NRuntimeError:
            raise
        except OSError:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Media processor dependency is unavailable") from None
        finally:
            if stdout_descriptor is not None:
                try:
                    os.close(stdout_descriptor)
                except OSError:
                    pass
        try:
            return_code = process.wait(timeout=command.timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _fail(ErrorCode.POLICY_BLOCKED, "Media processor did not terminate after its timeout")
            _fail(ErrorCode.POLICY_BLOCKED, "Media processor exceeded its timeout")
        if return_code != 0:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media processor rejected the temporary media")
        produced = 0
        for path in (*(() if command.stdout_path is None else (command.stdout_path,)), *command.output_paths):
            produced += _owned_regular_file(path, maximum_bytes=command.max_output_bytes)
        if produced > command.max_output_bytes:
            _fail(ErrorCode.POLICY_BLOCKED, "Media processor exceeded its output budget")


def _trusted_executable(path: Path) -> Path:
    if not path.is_absolute():
        _fail(ErrorCode.DEPENDENCY_MISSING, "Media processor executable is unavailable")
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError:
        raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Media processor executable is unavailable") from None
    if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        _fail(ErrorCode.DEPENDENCY_MISSING, "Media processor executable is unavailable")
    return resolved


@dataclass(frozen=True)
class MediaToolchain:
    """Only an exact local FFmpeg/FFprobe pair may receive a lease file."""

    ffmpeg_path: Path
    ffprobe_path: Path
    runner: MediaCommandRunner = field(default_factory=SandboxedCommandRunner, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ffmpeg_path", _trusted_executable(self.ffmpeg_path))
        object.__setattr__(self, "ffprobe_path", _trusted_executable(self.ffprobe_path))

    @classmethod
    def discover(cls, *, runner: MediaCommandRunner | None = None) -> "MediaToolchain":
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            _fail(ErrorCode.DEPENDENCY_MISSING, "FFmpeg and FFprobe are required for media preprocessing")
        return cls(Path(ffmpeg), Path(ffprobe), runner or SandboxedCommandRunner())

    def probe(
        self,
        source: Path,
        workspace: Path,
        *,
        timeout_seconds: float,
        policy: MediaProcessingPolicy,
    ) -> Path:
        output = _private_child(workspace, "probe.json")
        self.runner.run(
            MediaCommand(
                role="probe",
                argv=(
                    str(self.ffprobe_path),
                    "-v",
                    "error",
                    "-max_alloc",
                    str(policy.max_memory_bytes),
                    "-show_entries",
                    "format=duration:stream=codec_type,width,height,duration",
                    "-of",
                    "json",
                    str(source),
                ),
                cwd=workspace,
                stdout_path=output,
                timeout_seconds=timeout_seconds,
                max_output_bytes=policy.max_probe_bytes,
            ),
            policy=policy,
        )
        return output

    def extract_audio(
        self,
        source: Path,
        workspace: Path,
        *,
        timeout_seconds: float,
        policy: MediaProcessingPolicy,
    ) -> Path:
        output = _private_child(workspace, "audio.m4a")
        self.runner.run(
            MediaCommand(
                role="audio",
                argv=(
                    str(self.ffmpeg_path),
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-max_alloc",
                    str(policy.max_memory_bytes),
                    "-threads",
                    "1",
                    "-n",
                    "-i",
                    str(source),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "64k",
                    str(output),
                ),
                cwd=workspace,
                output_paths=(output,),
                timeout_seconds=timeout_seconds,
                max_output_bytes=policy.max_audio_bytes,
            ),
            policy=policy,
        )
        return output

    def extract_frame(
        self,
        source: Path,
        workspace: Path,
        *,
        index: int,
        timestamp_seconds: float,
        source_kind: Literal["audio", "image", "video"],
        timeout_seconds: float,
        policy: MediaProcessingPolicy,
    ) -> tuple[Path, Path]:
        if not 0 <= index < policy.max_keyframes or not math.isfinite(timestamp_seconds) or timestamp_seconds < 0:
            _fail(ErrorCode.POLICY_BLOCKED, "Media frame request is outside its policy")
        frame = _private_child(workspace, f"frame-{index:02d}.jpg")
        fingerprint = _private_child(workspace, f"frame-{index:02d}.raw")
        input_arguments: tuple[str, ...]
        if source_kind == "video":
            # Input-side seeking is keyframe-oriented in FFmpeg while retaining
            # a usable representative frame for short-GOP and sparse-keyframe
            # inputs.  Explicit ``-skip_frame nokey`` would make such inputs
            # fail closed despite otherwise valid bounded media.
            input_arguments = ("-ss", f"{timestamp_seconds:.3f}", "-i", str(source))
        elif source_kind == "image":
            input_arguments = ("-i", str(source))
        else:
            _fail(ErrorCode.POLICY_BLOCKED, "Audio-only media does not have representative frames")
        self.runner.run(
            MediaCommand(
                role="frame",
                argv=(
                    str(self.ffmpeg_path),
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-max_alloc",
                    str(policy.max_memory_bytes),
                    "-threads",
                    "1",
                    "-n",
                    *input_arguments,
                    "-filter_complex",
                    "[0:v:0]split=2[frame][fingerprint];"
                    "[frame]scale='min(1280,iw)':-2[frame_scaled];"
                    "[fingerprint]scale=8:8:flags=area,format=gray[fingerprint_gray]",
                    "-map",
                    "[frame_scaled]",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "5",
                    str(frame),
                    "-map",
                    "[fingerprint_gray]",
                    "-frames:v",
                    "1",
                    "-f",
                    "rawvideo",
                    str(fingerprint),
                ),
                cwd=workspace,
                output_paths=(frame, fingerprint),
                timeout_seconds=timeout_seconds,
                max_output_bytes=policy.max_frame_bytes + _PERCEPTUAL_HASH_BYTES,
            ),
            policy=policy,
        )
        return frame, fingerprint


@dataclass(frozen=True)
class MediaProbe:
    source_kind: Literal["audio", "image", "video"]
    duration_seconds: float | None
    audio_streams: int
    video_streams: int
    width: int | None
    height: int | None

    def safe_dict(self) -> dict[str, int | float | str | None]:
        return {
            "audio_streams": self.audio_streams,
            "duration_seconds": self.duration_seconds,
            "height": self.height,
            "source_kind": self.source_kind,
            "video_streams": self.video_streams,
            "width": self.width,
        }


@dataclass(frozen=True)
class EphemeralDerivedArtifact:
    """Private artifact valid only while ``MediaPreprocessor.process`` is open."""

    sha256: str
    mime: str
    size_bytes: int
    local_path: Path = field(repr=False, compare=False)

    def safe_dict(self) -> dict[str, int | str | bool]:
        return {
            "local_path_emitted": False,
            "mime": self.mime,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral media artifacts cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral media artifacts cannot be serialized")


@dataclass(frozen=True)
class FrameArtifact(EphemeralDerivedArtifact):
    timestamp_ms: int
    perceptual_hash: str

    def safe_dict(self) -> dict[str, int | str | bool]:
        return {
            **super().safe_dict(),
            "perceptual_hash": self.perceptual_hash,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass(frozen=True)
class FrameCandidate:
    artifact: FrameArtifact
    perceptual_hash_value: int = field(repr=False)


@dataclass(frozen=True)
class MediaPreprocessResult:
    lease_id: str
    source_hash: str
    probe: MediaProbe
    audio: EphemeralDerivedArtifact | None
    frames: tuple[FrameArtifact, ...]
    candidate_frame_count: int
    duplicates_dropped: int
    policy_version: str = RESOURCE_POLICY_VERSION

    def safe_dict(self) -> dict[str, object]:
        return {
            "audio": None if self.audio is None else self.audio.safe_dict(),
            "candidate_frame_count": self.candidate_frame_count,
            "duplicates_dropped": self.duplicates_dropped,
            "frames": [item.safe_dict() for item in self.frames],
            "lease_id": self.lease_id,
            "local_paths_emitted": False,
            "policy_version": self.policy_version,
            "probe": self.probe.safe_dict(),
            "source_hash": self.source_hash,
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral media preprocessing results cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral media preprocessing results cannot be serialized")


def _parse_probe(path: Path, *, mime: str, policy: MediaProcessingPolicy) -> MediaProbe:
    _owned_regular_file(path, maximum_bytes=policy.max_probe_bytes, suffix=".json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe output is invalid") from None
    if not isinstance(payload, dict) or set(payload) != {"format", "programs", "stream_groups", "streams"}:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe output shape is invalid")
    format_value = payload.get("format")
    programs = payload.get("programs")
    stream_groups = payload.get("stream_groups")
    streams = payload.get("streams")
    if (
        not isinstance(format_value, dict)
        or set(format_value) - {"duration"}
        or programs != []
        or stream_groups != []
        or not isinstance(streams, list)
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe output shape is invalid")
    if not 1 <= len(streams) <= 8:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe stream count is invalid")
    duration = _finite_number(format_value.get("duration"), label="duration", allow_none=True)
    video_streams = audio_streams = 0
    width: int | None = None
    height: int | None = None
    stream_durations: list[float] = []
    for stream in streams:
        if not isinstance(stream, dict) or set(stream) - {"codec_type", "width", "height", "duration"}:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe stream is invalid")
        kind = stream.get("codec_type")
        if kind == "video":
            video_streams += 1
            stream_width = _safe_positive_int(stream.get("width"), label="width")
            stream_height = _safe_positive_int(stream.get("height"), label="height")
            if stream_width > policy.max_width or stream_height > policy.max_height:
                _fail(ErrorCode.POLICY_BLOCKED, "Media dimensions exceed the processor policy")
            if stream_width * stream_height > policy.max_decoded_pixels:
                _fail(ErrorCode.POLICY_BLOCKED, "Media decoded pixels exceed the processor policy")
            width = max(width or 0, stream_width)
            height = max(height or 0, stream_height)
        elif kind == "audio":
            audio_streams += 1
        else:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe stream kind is unsupported")
        stream_duration = _finite_number(stream.get("duration"), label="stream duration", allow_none=True)
        if stream_duration is not None:
            stream_durations.append(stream_duration)
    if duration is None and stream_durations:
        duration = max(stream_durations)
    if duration is not None and duration > policy.max_duration_seconds:
        _fail(ErrorCode.POLICY_BLOCKED, "Media duration exceeds the processor policy")
    if mime.startswith("image/"):
        if video_streams != 1 or audio_streams != 0:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media MIME does not match the probe result")
        source_kind: Literal["audio", "image", "video"] = "image"
    elif mime.startswith("video/"):
        if video_streams < 1 or duration is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media MIME does not match the probe result")
        source_kind = "video"
    elif mime.startswith("audio/"):
        if video_streams != 0 or audio_streams < 1 or duration is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media MIME does not match the probe result")
        source_kind = "audio"
    else:
        _fail(ErrorCode.POLICY_BLOCKED, "Media MIME is unsupported for preprocessing")
    return MediaProbe(source_kind, duration, audio_streams, video_streams, width, height)


def select_representative_timestamps(
    duration_seconds: float | None,
    *,
    policy: MediaProcessingPolicy = MediaProcessingPolicy(),
) -> tuple[float, ...]:
    """Return deterministic interior samples, bounded at 50 even for 120 minutes."""

    if duration_seconds is None:
        return (0.0,)
    duration = _finite_number(duration_seconds, label="duration")
    assert duration is not None
    if duration > policy.max_duration_seconds:
        _fail(ErrorCode.POLICY_BLOCKED, "Media duration exceeds the processor policy")
    if duration == 0:
        return (0.0,)
    count = min(policy.max_keyframes, max(1, math.ceil(duration / policy.sample_interval_seconds)))
    return tuple((duration * (index + 0.5)) / count for index in range(count))


def _perceptual_hash(raw: bytes) -> int:
    if len(raw) != _PERCEPTUAL_HASH_BYTES:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media frame fingerprint is invalid")
    mean = sum(raw) / len(raw)
    value = 0
    for index, channel in enumerate(raw):
        if channel >= mean:
            value |= 1 << index
    return value


def deduplicate_frame_candidates(
    candidates: Sequence[FrameCandidate],
    *,
    policy: MediaProcessingPolicy = MediaProcessingPolicy(),
) -> tuple[tuple[FrameArtifact, ...], tuple[FrameArtifact, ...]]:
    """Perform bounded near-duplicate filtering with a stable first-frame rule."""

    if len(candidates) > policy.max_keyframes:
        _fail(ErrorCode.POLICY_BLOCKED, "Media frame candidate count exceeds the processor policy")
    retained: list[FrameCandidate] = []
    dropped: list[FrameArtifact] = []
    # Nine disjoint bit bands guarantee that a pair differing by <=8 bits shares
    # at least one band.  The hard 50-frame cap also prevents a pathological
    # candidate list from causing unbounded comparisons.
    buckets: dict[tuple[int, int], list[int]] = {}
    band_widths = (7, 7, 7, 7, 7, 7, 7, 7, 8)
    for candidate in candidates:
        if not 0 <= candidate.perceptual_hash_value < 1 << 64:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media frame fingerprint is invalid")
        offset = 0
        previous_indexes: set[int] = set()
        for band_index, width in enumerate(band_widths):
            value = (candidate.perceptual_hash_value >> offset) & ((1 << width) - 1)
            previous_indexes.update(buckets.get((band_index, value), ()))
            offset += width
        is_duplicate = any(
            (candidate.perceptual_hash_value ^ retained[index].perceptual_hash_value).bit_count()
            <= policy.near_duplicate_hamming_distance
            for index in sorted(previous_indexes)
        )
        if is_duplicate:
            dropped.append(candidate.artifact)
            continue
        retained_index = len(retained)
        retained.append(candidate)
        offset = 0
        for band_index, width in enumerate(band_widths):
            value = (candidate.perceptual_hash_value >> offset) & ((1 << width) - 1)
            buckets.setdefault((band_index, value), []).append(retained_index)
            offset += width
    return tuple(item.artifact for item in retained), tuple(dropped)


class MediaPreprocessor:
    """Transform one validated lease while preserving the text-only fallback."""

    def __init__(
        self,
        paths: RuntimePaths,
        store: CanonicalStore,
        *,
        toolchain: MediaToolchain | None = None,
        policy: MediaProcessingPolicy = MediaProcessingPolicy(),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if store.paths != paths:
            _fail(ErrorCode.POLICY_BLOCKED, "Media Store and Runtime roots do not match")
        self.paths = paths
        self.store = store
        self.toolchain = toolchain or MediaToolchain.discover()
        self.policy = policy
        self.monotonic = monotonic

    def _record_for(self, lease: MediaLeaseHandle) -> MediaLeaseRecord:
        record = self.store.get_media_lease(lease.lease_id)
        if record is None or record.status != "processing":
            _fail(ErrorCode.POLICY_BLOCKED, "Media preprocessing requires an active lease")
        try:
            expected = self.paths.temp_media_directory / record.local_relative_path
            if lease.local_path.resolve(strict=True) != expected.resolve(strict=True):
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media lease path invariant failed")
        except X2NRuntimeError:
            raise
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media source is unavailable") from None
        if (
            record.content_hash != lease.content_hash
            or record.mime != lease.mime
            or record.size_bytes != lease.size_bytes
            or record.duration_seconds != lease.duration_seconds
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media lease metadata invariant failed")
        return record

    def _remaining_timeout(self, deadline: float) -> float:
        remaining = deadline - self.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            _fail(ErrorCode.POLICY_BLOCKED, "Media preprocessing exceeded its total timeout")
        return min(float(self.policy.command_timeout_seconds), remaining)

    def _validate_source(self, lease: MediaLeaseHandle) -> None:
        if lease.size_bytes <= 0 or lease.size_bytes > self.policy.max_input_bytes:
            _fail(ErrorCode.POLICY_BLOCKED, "Temporary media exceeds the processor byte policy")
        try:
            metadata = lease.local_path.stat()
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media source is unavailable") from None
        if (
            lease.local_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "Temporary media source is not owner-only")
        digest, size = _sha256_file(lease.local_path, maximum_bytes=self.policy.max_input_bytes)
        if digest != lease.content_hash or size != lease.size_bytes:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Temporary media source changed after acquisition")

    def _validate_probe_against_lease(self, probe: MediaProbe, lease: MediaLeaseHandle) -> None:
        if lease.duration_seconds is None or probe.duration_seconds is None:
            return
        tolerance = max(1.0, lease.duration_seconds * 0.05)
        if abs(lease.duration_seconds - probe.duration_seconds) > tolerance:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media probe duration conflicts with the lease")

    @staticmethod
    def _frame_candidate(
        path: Path, fingerprint_path: Path, *, timestamp_seconds: float, policy: MediaProcessingPolicy
    ) -> FrameCandidate:
        size = _owned_regular_file(path, maximum_bytes=policy.max_frame_bytes, suffix=".jpg")
        _owned_regular_file(fingerprint_path, maximum_bytes=_PERCEPTUAL_HASH_BYTES, suffix=".raw")
        try:
            header = path.read_bytes()[:3]
            raw_fingerprint = fingerprint_path.read_bytes()
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media frame output is unavailable") from None
        if header != b"\xff\xd8\xff":
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media frame output is not JPEG")
        perceptual_hash = _perceptual_hash(raw_fingerprint)
        artifact = FrameArtifact(
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            mime="image/jpeg",
            size_bytes=size,
            local_path=path,
            timestamp_ms=round(timestamp_seconds * 1000),
            perceptual_hash=f"{perceptual_hash:016x}",
        )
        return FrameCandidate(artifact, perceptual_hash)

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            if path.is_symlink() or not path.is_file():
                _fail(ErrorCode.POLICY_BLOCKED, "Media processor output became unsafe")
            path.unlink()
        except X2NRuntimeError:
            raise
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media processor cleanup failed closed") from None

    @contextmanager
    def process(self, lease: MediaLeaseHandle) -> Iterator[MediaPreprocessResult]:
        """Yield ephemeral audio/frames; always remove derivatives on exit or error."""

        record = self._record_for(lease)
        self._validate_source(lease)
        deadline = self.monotonic() + self.policy.total_timeout_seconds
        with derived_media_workspace(self.paths, record) as workspace:
            probe_path = self.toolchain.probe(
                lease.local_path,
                workspace,
                timeout_seconds=self._remaining_timeout(deadline),
                policy=self.policy,
            )
            probe = _parse_probe(probe_path, mime=lease.mime, policy=self.policy)
            self._validate_probe_against_lease(probe, lease)
            audio: EphemeralDerivedArtifact | None = None
            if probe.audio_streams:
                audio_path = self.toolchain.extract_audio(
                    lease.local_path,
                    workspace,
                    timeout_seconds=self._remaining_timeout(deadline),
                    policy=self.policy,
                )
                audio_size = _owned_regular_file(audio_path, maximum_bytes=self.policy.max_audio_bytes, suffix=".m4a")
                audio = EphemeralDerivedArtifact(
                    sha256=hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                    mime="audio/mp4",
                    size_bytes=audio_size,
                    local_path=audio_path,
                )
            candidates: list[FrameCandidate] = []
            if probe.source_kind != "audio":
                for index, timestamp in enumerate(
                    select_representative_timestamps(probe.duration_seconds, policy=self.policy)
                ):
                    frame_path, fingerprint_path = self.toolchain.extract_frame(
                        lease.local_path,
                        workspace,
                        index=index,
                        timestamp_seconds=timestamp,
                        source_kind=probe.source_kind,
                        timeout_seconds=self._remaining_timeout(deadline),
                        policy=self.policy,
                    )
                    candidate = self._frame_candidate(
                        frame_path,
                        fingerprint_path,
                        timestamp_seconds=timestamp,
                        policy=self.policy,
                    )
                    self._unlink(fingerprint_path)
                    candidates.append(candidate)
            frames, dropped = deduplicate_frame_candidates(candidates, policy=self.policy)
            for artifact in dropped:
                self._unlink(artifact.local_path)
            total_derivative_bytes = sum(frame.size_bytes for frame in frames) + (audio.size_bytes if audio else 0)
            if total_derivative_bytes > self.policy.max_derivative_bytes:
                _fail(ErrorCode.POLICY_BLOCKED, "Media derivatives exceed the processor budget")
            result = MediaPreprocessResult(
                lease_id=lease.lease_id,
                source_hash=lease.content_hash,
                probe=probe,
                audio=audio,
                frames=frames,
                candidate_frame_count=len(candidates),
                duplicates_dropped=len(dropped),
            )
            yield result
