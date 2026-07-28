"""Lease-scoped ASR with local-first execution and an explicit cloud kill switch.

This module deliberately keeps audio and transcript text ephemeral.  It accepts
the short-lived audio handle produced by ``media_preprocessing`` and returns a
non-serializable transcript while the caller still owns that media-processing
context.  The public-safe receipt contains hashes, provenance and aggregates
only.  It never reads credentials, invokes a network client, persists a media
URL, or writes transcript text to SQLite.

The concrete local adapter follows the documented ``whisper.cpp`` CLI shape:
``whisper-cli -m MODEL -f AUDIO -oj -of OUTPUT_BASE``.  The executable and
model must already exist below the private runtime model directory; this Task
does not download, install, update or execute a model automatically.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
import unicodedata
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from x2n_contracts import ErrorCode

from .media_preprocessing import (
    EphemeralDerivedArtifact,
    MediaCommand,
    MediaProcessingPolicy,
    MediaToolchain,
)
from .runtime import RuntimePaths, X2NRuntimeError


TASK_ID = "TSK.x2n.multimodal.002"
ASR_POLICY_VERSION = "x2n-asr-v1"
MAX_AUDIO_SECONDS = 2 * 60 * 60
MAX_CHUNK_SECONDS = 5 * 60
MAX_CHUNKS = MAX_AUDIO_SECONDS // MAX_CHUNK_SECONDS
MAX_WAV_CHUNK_BYTES = 16 * 1024 * 1024
MAX_NORMALIZED_AUDIO_BYTES = 256 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 20_000
MAX_TRANSCRIPT_JSON_BYTES = 2 * 1024 * 1024
# Evaluation deliberately works on bounded reference snippets, rather than a
# whole two-hour transcript.  Exact edit-distance evaluation is quadratic, so
# accepting arbitrarily long text here would turn a quality gate into a local
# denial-of-service surface.
MAX_CER_CHARS = 4_096
MAX_ASR_TOTAL_SECONDS = 30 * 60
MAX_GOLD_DATASET_BYTES = 2 * 1024 * 1024
ASR_GOLD_DATASET_SCHEMA = "x2n-asr-gold-v1"
_ASR_AUDIO_MIME = "audio/mp4"
_LOCAL_MODE = "local"
_CLOUD_MODE = "cloud"
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _fail(code: ErrorCode, message: str) -> None:
    raise X2NRuntimeError(code, message)


def _safe_token(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        _fail(ErrorCode.INVALID_INPUT, f"ASR {label} is invalid")
    return value


def _prompt_sha256(descriptor: "AsrProviderDescriptor", *, language: str, policy: "AsrPolicy") -> str:
    """Fingerprint the fixed local invocation contract without exposing text."""

    payload = {
        "adapter": "whispercpp-cli-v1",
        "language": language,
        "model_snapshot_sha256": descriptor.model_snapshot_sha256,
        "policy_version": policy.version,
        "provider_id": descriptor.provider_id,
        "provider_version": descriptor.provider_version,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private input is unsafe")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    _fail(ErrorCode.POLICY_BLOCKED, "ASR private input exceeds its resource policy")
                digest.update(chunk)
    except X2NRuntimeError:
        raise
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "ASR private input is unavailable") from None
    if size <= 0:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private input is empty")
    return digest.hexdigest(), size


def _private_regular_file(path: Path, *, maximum_bytes: int, suffix: str | None = None) -> int:
    if suffix is not None and path.suffix != suffix:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private file type is invalid")
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private output is unavailable")
    try:
        metadata = path.stat()
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "ASR private output is unavailable") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private output is not owner-only")
    if not 0 < metadata.st_size <= maximum_bytes:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private output exceeds its resource policy")
    return int(metadata.st_size)


def _private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private workspace is unavailable")
    try:
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR private workspace is not owner-only")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "ASR private workspace is unavailable") from None


def _private_child(root: Path, name: str) -> Path:
    candidate = root / name
    if Path(name).is_absolute() or "/" in name or "\\" in name or ".." in Path(name).parts:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private child name is invalid")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR private output escaped its workspace")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "ASR private workspace is unavailable") from None
    return candidate


def _remove_private_tree(path: Path) -> None:
    """Delete only a just-created workspace without traversing symlinks."""

    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        _fail(ErrorCode.POLICY_BLOCKED, "ASR cleanup workspace is unsafe")
    try:
        children = tuple(path.iterdir())
        for child in children:
            if child.is_symlink():
                child.unlink()
            elif child.is_dir():
                _remove_private_tree(child)
            elif child.is_file():
                child.unlink()
            else:
                _fail(ErrorCode.POLICY_BLOCKED, "ASR cleanup workspace contains an unsafe entry")
        path.rmdir()
    except X2NRuntimeError:
        raise
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "ASR temporary cleanup failed closed") from None


@dataclass(frozen=True)
class AsrPolicy:
    """Non-relaxable resource, cache and cloud policy for one ASR session."""

    version: str = ASR_POLICY_VERSION
    max_audio_seconds: int = MAX_AUDIO_SECONDS
    chunk_seconds: int = MAX_CHUNK_SECONDS
    max_chunks: int = MAX_CHUNKS
    max_wav_chunk_bytes: int = MAX_WAV_CHUNK_BYTES
    max_normalized_audio_bytes: int = MAX_NORMALIZED_AUDIO_BYTES
    max_transcript_chars: int = MAX_TRANSCRIPT_CHARS
    max_transcript_json_bytes: int = MAX_TRANSCRIPT_JSON_BYTES
    max_cer_chars: int = MAX_CER_CHARS
    command_timeout_seconds: int = 120
    total_timeout_seconds: int = MAX_ASR_TOTAL_SECONDS
    max_invocations: int = MAX_CHUNKS
    max_cloud_cost_microunits: int = 0

    def __post_init__(self) -> None:
        if self.version != ASR_POLICY_VERSION:
            _fail(ErrorCode.INVALID_INPUT, "ASR policy version is unsupported")
        fields = (
            "max_audio_seconds",
            "chunk_seconds",
            "max_chunks",
            "max_wav_chunk_bytes",
            "max_normalized_audio_bytes",
            "max_transcript_chars",
            "max_transcript_json_bytes",
            "max_cer_chars",
            "command_timeout_seconds",
            "total_timeout_seconds",
            "max_invocations",
        )
        for label in fields:
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                _fail(ErrorCode.INVALID_INPUT, f"ASR {label} is invalid")
        if isinstance(self.max_cloud_cost_microunits, bool) or not isinstance(self.max_cloud_cost_microunits, int):
            _fail(ErrorCode.INVALID_INPUT, "ASR cloud budget is invalid")
        if (
            self.max_audio_seconds > MAX_AUDIO_SECONDS
            or not 30 <= self.chunk_seconds <= MAX_CHUNK_SECONDS
            or self.max_chunks > MAX_CHUNKS
            or self.chunk_seconds * self.max_chunks < self.max_audio_seconds
            or self.max_wav_chunk_bytes > MAX_WAV_CHUNK_BYTES
            or self.max_normalized_audio_bytes > MAX_NORMALIZED_AUDIO_BYTES
            or self.max_transcript_chars > MAX_TRANSCRIPT_CHARS
            or self.max_transcript_json_bytes > MAX_TRANSCRIPT_JSON_BYTES
            or self.max_cer_chars > MAX_CER_CHARS
            or self.command_timeout_seconds > 120
            or self.total_timeout_seconds > MAX_ASR_TOTAL_SECONDS
            or self.command_timeout_seconds > self.total_timeout_seconds
            or self.max_invocations > MAX_CHUNKS
            or self.max_cloud_cost_microunits != 0
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "ASR policy exceeds its approved budget")

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "chunk_seconds": self.chunk_seconds,
            "command_timeout_seconds": self.command_timeout_seconds,
            "max_audio_seconds": self.max_audio_seconds,
            "max_chunks": self.max_chunks,
            "max_cloud_cost_microunits": self.max_cloud_cost_microunits,
            "max_invocations": self.max_invocations,
            "max_normalized_audio_bytes": self.max_normalized_audio_bytes,
            "max_transcript_chars": self.max_transcript_chars,
            "max_wav_chunk_bytes": self.max_wav_chunk_bytes,
            "total_timeout_seconds": self.total_timeout_seconds,
            "version": self.version,
        }


ASR_SANDBOX_POLICY = MediaProcessingPolicy(
    command_timeout_seconds=120,
    total_timeout_seconds=120,
    cpu_limit_seconds=120,
)


@dataclass(frozen=True)
class AsrProviderDescriptor:
    provider_id: str
    provider_version: str
    mode: Literal["local", "cloud"]
    model_id: str
    model_snapshot_sha256: str
    executable_sha256: str | None
    cloud_upload_authorized: bool
    retention: Literal["local_ephemeral", "disabled"]

    def __post_init__(self) -> None:
        _safe_token(self.provider_id, label="provider id")
        _safe_token(self.provider_version, label="provider version")
        _safe_token(self.model_id, label="model id")
        if _SHA256.fullmatch(self.model_snapshot_sha256) is None:
            _fail(ErrorCode.INVALID_INPUT, "ASR model snapshot is invalid")
        if self.executable_sha256 is not None and _SHA256.fullmatch(self.executable_sha256) is None:
            _fail(ErrorCode.INVALID_INPUT, "ASR executable snapshot is invalid")
        if self.mode == _LOCAL_MODE:
            if self.cloud_upload_authorized or self.retention != "local_ephemeral" or self.executable_sha256 is None:
                _fail(ErrorCode.POLICY_BLOCKED, "ASR local provider provenance is invalid")
        elif self.mode == _CLOUD_MODE:
            if self.cloud_upload_authorized or self.retention != "disabled":
                _fail(ErrorCode.POLICY_BLOCKED, "ASR cloud provider is disabled by policy")
        else:  # pragma: no cover - Literal is a type aid; retain a runtime guard.
            _fail(ErrorCode.INVALID_INPUT, "ASR provider mode is invalid")

    def safe_dict(self) -> dict[str, bool | str | None]:
        return {
            "cloud_upload_authorized": self.cloud_upload_authorized,
            "executable_sha256": self.executable_sha256,
            "mode": self.mode,
            "model_id": self.model_id,
            "model_snapshot_sha256": self.model_snapshot_sha256,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "retention": self.retention,
        }


@dataclass(frozen=True)
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.start_ms, bool)
            or isinstance(self.end_ms, bool)
            or not isinstance(self.start_ms, int)
            or not isinstance(self.end_ms, int)
            or not 0 <= self.start_ms <= self.end_ms
            or not isinstance(self.text, str)
            or not self.text.strip()
            or len(self.text) > MAX_TRANSCRIPT_CHARS
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR segment is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "end_ms": self.end_ms,
            "start_ms": self.start_ms,
            "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
        }


@dataclass(frozen=True)
class EphemeralTranscript:
    """Private result valid only while its ASR session remains open."""

    segments: tuple[AsrSegment, ...] = field(repr=False, compare=False)
    language: str
    input_hash: str

    def __post_init__(self) -> None:
        _safe_token(self.language, label="language")
        if _SHA256.fullmatch(self.input_hash) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR transcript input hash is invalid")
        if len(self.text) > MAX_TRANSCRIPT_CHARS:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR transcript exceeds the text policy")

    @property
    def text(self) -> str:
        return "\n".join(item.text.strip() for item in self.segments).strip()

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def safe_dict(self) -> dict[str, bool | int | str]:
        return {
            "input_hash": self.input_hash,
            "language": self.language,
            "local_text_emitted": False,
            "segment_count": len(self.segments),
            "text_characters": len(self.text),
            "text_sha256": self.text_sha256,
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral ASR transcripts cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral ASR transcripts cannot be serialized")


@dataclass(frozen=True)
class AsrInvocation:
    invocation_id: str
    provider: AsrProviderDescriptor
    input_hash: str
    language: str
    prompt_sha256: str
    audio_seconds: float
    cache_hit: bool
    provider_calls: int
    cloud_uploads: int
    cost_microunits: int
    transcript_hash: str

    def __post_init__(self) -> None:
        _safe_token(self.invocation_id, label="invocation id")
        _safe_token(self.language, label="language")
        if (
            _SHA256.fullmatch(self.input_hash) is None
            or _SHA256.fullmatch(self.prompt_sha256) is None
            or _SHA256.fullmatch(self.transcript_hash) is None
            or not math.isfinite(self.audio_seconds)
            or not 0 <= self.audio_seconds <= MAX_AUDIO_SECONDS
            or isinstance(self.provider_calls, bool)
            or not isinstance(self.provider_calls, int)
            or self.provider_calls < 0
            or self.cloud_uploads != 0
            or self.cost_microunits != 0
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR invocation provenance is invalid")

    def safe_dict(self) -> dict[str, bool | float | int | str | dict[str, bool | str | None]]:
        return {
            "audio_seconds": self.audio_seconds,
            "cache_hit": self.cache_hit,
            "cloud_uploads": self.cloud_uploads,
            "cost_microunits": self.cost_microunits,
            "input_hash": self.input_hash,
            "invocation_id": self.invocation_id,
            "language": self.language,
            "prompt_sha256": self.prompt_sha256,
            "provider": self.provider.safe_dict(),
            "provider_calls": self.provider_calls,
            "transcript_hash": self.transcript_hash,
        }


@dataclass(frozen=True)
class AsrResult:
    transcript: EphemeralTranscript = field(repr=False, compare=False)
    invocation: AsrInvocation
    artifact_id: str

    def __post_init__(self) -> None:
        _safe_token(self.artifact_id, label="artifact id")

    def safe_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "invocation": self.invocation.safe_dict(),
            "transcript": self.transcript.safe_dict(),
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral ASR results cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral ASR results cannot be serialized")


class AsrProvider(Protocol):
    descriptor: AsrProviderDescriptor

    def transcribe(
        self,
        audio: EphemeralDerivedArtifact,
        *,
        audio_seconds: float,
        language: str,
        policy: AsrPolicy,
    ) -> EphemeralTranscript:
        """Return an in-memory transcript or fail before an unsafe side effect."""


@dataclass(frozen=True)
class _AsrAudioChunk:
    path: Path = field(repr=False)
    index: int
    offset_ms: int
    duration_seconds: float


class AsrAudioNormalizer:
    """Convert Task001's ephemeral M4A into bounded, temporary PCM WAV chunks."""

    def __init__(self, toolchain: MediaToolchain, *, policy: AsrPolicy = AsrPolicy()) -> None:
        self.toolchain = toolchain
        self.policy = policy

    @contextmanager
    def chunks(
        self,
        audio: EphemeralDerivedArtifact,
        *,
        audio_seconds: float,
        deadline: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> Iterator[tuple[_AsrAudioChunk, ...]]:
        if audio.mime != _ASR_AUDIO_MIME:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR accepts only the Task001 ephemeral audio format")
        if not math.isfinite(audio_seconds) or not 0 < audio_seconds <= self.policy.max_audio_seconds:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR audio duration exceeds its policy")
        _private_regular_file(audio.local_path, maximum_bytes=32 * 1024 * 1024, suffix=".m4a")
        source_hash, source_size = _sha256_file(audio.local_path, maximum_bytes=32 * 1024 * 1024)
        if source_hash != audio.sha256 or source_size != audio.size_bytes:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR source audio changed after preprocessing")
        root = audio.local_path.parent
        _private_directory(root)
        workspace = _private_child(root, f"asr-{audio.sha256[:32]}")
        if workspace.exists() or workspace.is_symlink():
            _fail(ErrorCode.POLICY_BLOCKED, "ASR temporary workspace already exists")
        try:
            workspace.mkdir(mode=0o700)
            workspace.chmod(0o700)
            count = math.ceil(audio_seconds / self.policy.chunk_seconds)
            if not 1 <= count <= self.policy.max_chunks:
                _fail(ErrorCode.POLICY_BLOCKED, "ASR chunk count exceeds its policy")
            chunks: list[_AsrAudioChunk] = []
            normalized_bytes = 0
            for index in range(count):
                remaining = deadline - monotonic()
                if not math.isfinite(remaining) or remaining <= 0:
                    _fail(ErrorCode.POLICY_BLOCKED, "ASR exceeded its total timeout")
                offset = index * self.policy.chunk_seconds
                duration = min(float(self.policy.chunk_seconds), audio_seconds - offset)
                output = _private_child(workspace, f"chunk-{index:02d}.wav")
                self.toolchain.runner.run(
                    MediaCommand(
                        role="audio",
                        argv=(
                            str(self.toolchain.ffmpeg_path),
                            "-nostdin",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-max_alloc",
                            str(ASR_SANDBOX_POLICY.max_memory_bytes),
                            "-threads",
                            "1",
                            "-n",
                            "-ss",
                            f"{offset:.3f}",
                            "-t",
                            f"{duration:.3f}",
                            "-i",
                            str(audio.local_path),
                            "-map",
                            "0:a:0",
                            "-ac",
                            "1",
                            "-ar",
                            "16000",
                            "-c:a",
                            "pcm_s16le",
                            "-f",
                            "wav",
                            str(output),
                        ),
                        cwd=workspace,
                        output_paths=(output,),
                        timeout_seconds=min(float(self.policy.command_timeout_seconds), remaining),
                        max_output_bytes=self.policy.max_wav_chunk_bytes,
                    ),
                    policy=ASR_SANDBOX_POLICY,
                )
                normalized_bytes += _private_regular_file(
                    output,
                    maximum_bytes=self.policy.max_wav_chunk_bytes,
                    suffix=".wav",
                )
                if normalized_bytes > self.policy.max_normalized_audio_bytes:
                    _fail(ErrorCode.POLICY_BLOCKED, "ASR normalized audio exceeds its resource policy")
                chunks.append(_AsrAudioChunk(output, index, round(offset * 1000), duration))
            yield tuple(chunks)
        finally:
            _remove_private_tree(workspace)


def _trusted_model_file(paths: RuntimePaths, path: Path, *, executable: bool) -> tuple[Path, str]:
    try:
        root = (paths.data_root / "runtime/models").resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        metadata = resolved.stat()
    except (OSError, ValueError):
        _fail(ErrorCode.DEPENDENCY_MISSING, "ASR local provider dependency is unavailable")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (executable and not os.access(resolved, os.X_OK))
    ):
        _fail(ErrorCode.POLICY_BLOCKED, "ASR local provider dependency is not owner-managed")
    digest, _ = _sha256_file(resolved, maximum_bytes=4 * 1024 * 1024 * 1024)
    return resolved, digest


def _parse_nonnegative_ms(value: object, *, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return fallback
    parsed = round(float(value))
    return parsed if parsed >= 0 else fallback


def _parse_whisper_json(
    path: Path,
    *,
    chunk: _AsrAudioChunk,
    input_hash: str,
    language: str,
    policy: AsrPolicy,
) -> tuple[AsrSegment, ...]:
    _private_regular_file(path, maximum_bytes=policy.max_transcript_json_bytes, suffix=".json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "ASR provider JSON is invalid") from None
    if not isinstance(payload, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR provider JSON shape is invalid")
    result = payload.get("result", payload)
    if not isinstance(result, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR provider result is invalid")
    rows = result.get("transcription")
    if not isinstance(rows, list) or len(rows) > policy.max_chunks * 256:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR provider transcription is invalid")
    segments: list[AsrSegment] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR provider segment is invalid")
        text = row["text"].strip()
        if not text:
            continue
        offsets = row.get("offsets")
        start = end = None
        if isinstance(offsets, dict):
            start = _parse_nonnegative_ms(offsets.get("from"), fallback=0)
            end = _parse_nonnegative_ms(offsets.get("to"), fallback=start)
        start_ms = chunk.offset_ms + (start if start is not None else round(index * chunk.duration_seconds * 1000))
        end_ms = chunk.offset_ms + (end if end is not None else round((index + 1) * chunk.duration_seconds * 1000))
        end_ms = max(start_ms, min(end_ms, chunk.offset_ms + round(chunk.duration_seconds * 1000)))
        segments.append(AsrSegment(start_ms, end_ms, text))
    transcript = EphemeralTranscript(tuple(segments), language=language, input_hash=input_hash)
    return transcript.segments


class WhisperCppLocalProvider:
    """Owner-managed local ``whisper-cli`` adapter; no model installation or network path."""

    def __init__(
        self,
        paths: RuntimePaths,
        toolchain: MediaToolchain,
        *,
        executable_path: Path,
        model_path: Path,
        descriptor: AsrProviderDescriptor,
        policy: AsrPolicy = AsrPolicy(),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if descriptor.mode != _LOCAL_MODE:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR local adapter requires a local provider descriptor")
        executable, executable_digest = _trusted_model_file(paths, executable_path, executable=True)
        model, model_digest = _trusted_model_file(paths, model_path, executable=False)
        if descriptor.executable_sha256 != executable_digest or descriptor.model_snapshot_sha256 != model_digest:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR local provider provenance changed")
        self.paths = paths
        self.toolchain = toolchain
        self.executable_path = executable
        self.model_path = model
        self.descriptor = descriptor
        self.policy = policy
        self.monotonic = monotonic
        self.normalizer = AsrAudioNormalizer(toolchain, policy=policy)

    def _transcribe_chunk(
        self,
        chunk: _AsrAudioChunk,
        *,
        input_hash: str,
        language: str,
        workspace: Path,
        deadline: float,
    ) -> tuple[AsrSegment, ...]:
        remaining = deadline - self.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR exceeded its total timeout")
        output_base = _private_child(workspace, f"transcript-{chunk.index:02d}")
        output_json = output_base.with_suffix(".json")
        self.toolchain.runner.run(
            MediaCommand(
                role="probe",
                argv=(
                    str(self.executable_path),
                    "-m",
                    str(self.model_path),
                    "-f",
                    str(chunk.path),
                    "-l",
                    language,
                    "-oj",
                    "-of",
                    str(output_base),
                    "-np",
                    "-nt",
                    "-ng",
                    "-t",
                    "1",
                ),
                cwd=workspace,
                output_paths=(output_json,),
                timeout_seconds=min(float(self.policy.command_timeout_seconds), remaining),
                max_output_bytes=self.policy.max_transcript_json_bytes,
            ),
            policy=ASR_SANDBOX_POLICY,
        )
        return _parse_whisper_json(
            output_json,
            chunk=chunk,
            input_hash=input_hash,
            language=language,
            policy=self.policy,
        )

    def transcribe(
        self,
        audio: EphemeralDerivedArtifact,
        *,
        audio_seconds: float,
        language: str,
        policy: AsrPolicy,
    ) -> EphemeralTranscript:
        if policy != self.policy:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR provider policy does not match its session")
        deadline = self.monotonic() + policy.total_timeout_seconds
        segments: list[AsrSegment] = []
        with self.normalizer.chunks(
            audio,
            audio_seconds=audio_seconds,
            deadline=deadline,
            monotonic=self.monotonic,
        ) as chunks:
            workspace = chunks[0].path.parent if chunks else None
            if workspace is None:  # pragma: no cover - normalizer rejects zero duration.
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR audio produced no chunks")
            for chunk in chunks:
                segments.extend(
                    self._transcribe_chunk(
                        chunk,
                        input_hash=audio.sha256,
                        language=language,
                        workspace=workspace,
                        deadline=deadline,
                    )
                )
        return EphemeralTranscript(tuple(segments), language=language, input_hash=audio.sha256)


class DisabledCloudAsrProvider:
    """A non-network provider that makes any cloud upload attempt fail closed."""

    def __init__(self, descriptor: AsrProviderDescriptor) -> None:
        if descriptor.mode != _CLOUD_MODE or descriptor.cloud_upload_authorized:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR cloud provider is not disabled")
        self.descriptor = descriptor

    def transcribe(
        self,
        audio: EphemeralDerivedArtifact,
        *,
        audio_seconds: float,
        language: str,
        policy: AsrPolicy,
    ) -> EphemeralTranscript:
        del audio, audio_seconds, language, policy
        _fail(ErrorCode.POLICY_BLOCKED, "ASR cloud upload is not authorized")


@dataclass(frozen=True)
class AsrGoldCase:
    """Private evaluation input; tests may use synthetic text but never real audio."""

    case_id: str
    stratum: Literal["clear_mandarin", "noise", "music", "dialect", "mixed_language", "no_speech"]
    reference_text: str = field(repr=False, compare=False)
    predicted_text: str = field(repr=False, compare=False)
    synthetic: bool
    provider_failed: bool = False
    provider: AsrProviderDescriptor | None = field(default=None, repr=False, compare=False)
    input_hash: str | None = None
    prompt_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_token(self.case_id, label="Gold Set case id")
        if self.stratum not in {"clear_mandarin", "noise", "music", "dialect", "mixed_language", "no_speech"}:
            _fail(ErrorCode.INVALID_INPUT, "ASR Gold Set stratum is invalid")
        if not isinstance(self.reference_text, str) or not isinstance(self.predicted_text, str):
            _fail(ErrorCode.INVALID_INPUT, "ASR Gold Set text is invalid")
        if len(self.reference_text) > MAX_CER_CHARS or len(self.predicted_text) > MAX_CER_CHARS:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR Gold Set text exceeds its policy")
        if self.stratum == "no_speech" and self.reference_text.strip():
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR no-speech Gold Set reference is invalid")
        if not isinstance(self.synthetic, bool):
            _fail(ErrorCode.INVALID_INPUT, "ASR Gold Set synthetic flag is invalid")
        if not isinstance(self.provider_failed, bool):
            _fail(ErrorCode.INVALID_INPUT, "ASR Gold Set failure flag is invalid")
        provenance = (self.provider, self.input_hash, self.prompt_sha256)
        if any(value is None for value in provenance) and any(value is not None for value in provenance):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR Gold Set provenance is incomplete")
        if not self.synthetic:
            if self.provider is None or self.input_hash is None or self.prompt_sha256 is None:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set provenance is required")
            if self.provider.mode != _LOCAL_MODE:
                _fail(ErrorCode.POLICY_BLOCKED, "ASR private Gold Set provider is not authorized")
        if self.input_hash is not None and _SHA256.fullmatch(self.input_hash) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR Gold Set input hash is invalid")
        if self.prompt_sha256 is not None and _SHA256.fullmatch(self.prompt_sha256) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR Gold Set prompt hash is invalid")

    def safe_dict(self) -> dict[str, bool | int | str | dict[str, bool | str | None] | None]:
        return {
            "case_id": self.case_id,
            "input_hash": self.input_hash,
            "predicted_hash": hashlib.sha256(self.predicted_text.encode("utf-8")).hexdigest(),
            "prompt_sha256": self.prompt_sha256,
            "provider": None if self.provider is None else self.provider.safe_dict(),
            "reference_hash": hashlib.sha256(self.reference_text.encode("utf-8")).hexdigest(),
            "provider_failed": self.provider_failed,
            "stratum": self.stratum,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True)
class PrivateAsrGoldDataset:
    """Read-only, owner-provisioned Gold Set held solely in private runtime."""

    dataset_id: str
    sha256: str
    cases: tuple[AsrGoldCase, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _safe_token(self.dataset_id, label="Gold Set dataset id")
        if _SHA256.fullmatch(self.sha256) is None or not self.cases:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {"case_count": len(self.cases), "dataset_id": self.dataset_id, "dataset_sha256": self.sha256}


def _gold_case_from_private_payload(value: object) -> AsrGoldCase:
    if not isinstance(value, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set case is invalid")
    expected = {
        "case_id",
        "input_hash",
        "predicted_text",
        "prompt_sha256",
        "provider",
        "provider_failed",
        "reference_text",
        "stratum",
    }
    if set(value) != expected or not isinstance(value["provider"], dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set case shape is invalid")
    provider_payload = value["provider"]
    provider_fields = {
        "cloud_upload_authorized",
        "executable_sha256",
        "mode",
        "model_id",
        "model_snapshot_sha256",
        "provider_id",
        "provider_version",
        "retention",
    }
    if set(provider_payload) != provider_fields:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set provider shape is invalid")
    try:
        provider = AsrProviderDescriptor(**provider_payload)
    except (TypeError, X2NRuntimeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set provider is invalid") from None
    try:
        return AsrGoldCase(
            case_id=value["case_id"],
            stratum=value["stratum"],
            reference_text=value["reference_text"],
            predicted_text=value["predicted_text"],
            synthetic=False,
            provider_failed=value["provider_failed"],
            provider=provider,
            input_hash=value["input_hash"],
            prompt_sha256=value["prompt_sha256"],
        )
    except X2NRuntimeError:
        raise
    except (TypeError, ValueError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set case is invalid") from None


def load_private_asr_gold_dataset(paths: RuntimePaths, dataset_id: str) -> PrivateAsrGoldDataset:
    """Read one exact owner-provisioned evaluation file without copying it elsewhere."""

    safe_dataset_id = _safe_token(dataset_id, label="Gold Set dataset id")
    root = paths.data_root / "runtime/diagnostics/asr-gold"
    _private_directory(root)
    dataset_path = _private_child(root, f"{safe_dataset_id}.json")
    _private_regular_file(dataset_path, maximum_bytes=MAX_GOLD_DATASET_BYTES, suffix=".json")
    digest, _ = _sha256_file(dataset_path, maximum_bytes=MAX_GOLD_DATASET_BYTES)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set is invalid") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"cases", "dataset_id", "schema_version"}
        or payload["schema_version"] != ASR_GOLD_DATASET_SCHEMA
        or payload["dataset_id"] != safe_dataset_id
        or not isinstance(payload["cases"], list)
        or not 1 <= len(payload["cases"]) <= 500
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set shape is invalid")
    return PrivateAsrGoldDataset(
        dataset_id=safe_dataset_id,
        sha256=digest,
        cases=tuple(_gold_case_from_private_payload(item) for item in payload["cases"]),
    )


def normalize_for_cer(value: str) -> str:
    """Use a documented, deterministic character-level CER normalization."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def _edit_distance(reference: Sequence[str], predicted: Sequence[str], *, maximum_units: int, label: str) -> int:
    if len(reference) > maximum_units or len(predicted) > maximum_units:
        _fail(ErrorCode.POLICY_BLOCKED, f"ASR {label} input exceeds its policy")
    # Swap only the working rows, never the caller's denominator.  This keeps
    # memory linear in the shorter input while preserving a reference-based
    # error rate.
    rows, columns = reference, predicted
    if len(columns) > len(rows):
        rows, columns = columns, rows
    previous = list(range(len(columns) + 1))
    for index, reference_character in enumerate(rows, start=1):
        current = [index]
        for candidate_index, predicted_character in enumerate(columns, start=1):
            current.append(
                min(
                    previous[candidate_index] + 1,
                    current[candidate_index - 1] + 1,
                    previous[candidate_index - 1] + (reference_character != predicted_character),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, predicted: str, *, maximum_chars: int = MAX_CER_CHARS) -> float:
    if len(reference) > maximum_chars or len(predicted) > maximum_chars:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR CER input exceeds its policy")
    reference_value = normalize_for_cer(reference)
    predicted_value = normalize_for_cer(predicted)
    if not reference_value:
        return 0.0 if not predicted_value else 1.0
    return _edit_distance(
        reference_value,
        predicted_value,
        maximum_units=maximum_chars,
        label="CER",
    ) / len(reference_value)


def _word_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: list[str] = []
    word: list[str] = []
    for character in normalized:
        if "\u4e00" <= character <= "\u9fff":
            if word:
                tokens.append("".join(word))
                word = []
            tokens.append(character)
        elif character.isalnum():
            word.append(character)
        elif word:
            tokens.append("".join(word))
            word = []
    if word:
        tokens.append("".join(word))
    return tuple(tokens)


def word_error_rate(reference: str, predicted: str, *, maximum_chars: int = MAX_CER_CHARS) -> float:
    if len(reference) > maximum_chars or len(predicted) > maximum_chars:
        _fail(ErrorCode.POLICY_BLOCKED, "ASR WER input exceeds its policy")
    reference_tokens = _word_tokens(reference)
    predicted_tokens = _word_tokens(predicted)
    if not reference_tokens:
        return 0.0 if not predicted_tokens else 1.0
    return _edit_distance(
        reference_tokens,
        predicted_tokens,
        maximum_units=maximum_chars,
        label="WER",
    ) / len(reference_tokens)


def _median(values: Sequence[float]) -> float:
    if not values:
        _fail(ErrorCode.INVALID_INPUT, "ASR median requires values")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


@dataclass(frozen=True)
class AsrEvaluationReport:
    scope: Literal["ci_synth_contract_only", "private_gold"]
    clear_mandarin_cases: int
    clear_mandarin_median_cer: float | None
    clear_mandarin_median_wer: float | None
    no_speech_hallucinations: int
    omission_cases: int
    provider_failures: int
    provenance_complete_cases: int
    status: Literal["pass", "low_quality", "not_run"]
    evaluated_cases: int

    def safe_dict(self) -> dict[str, float | int | str | None]:
        return {
            "clear_mandarin_cases": self.clear_mandarin_cases,
            "clear_mandarin_median_cer": self.clear_mandarin_median_cer,
            "clear_mandarin_median_wer": self.clear_mandarin_median_wer,
            "evaluated_cases": self.evaluated_cases,
            "no_speech_hallucinations": self.no_speech_hallucinations,
            "omission_cases": self.omission_cases,
            "provider_failures": self.provider_failures,
            "provenance_complete_cases": self.provenance_complete_cases,
            "scope": self.scope,
            "status": self.status,
        }


class AsrEvaluator:
    """CER/no-speech evaluator that refuses to turn synthetic results into a quality claim."""

    def __init__(self, *, policy: AsrPolicy = AsrPolicy()) -> None:
        self.policy = policy

    def evaluate(self, cases: Sequence[AsrGoldCase], *, private_gold: bool) -> AsrEvaluationReport:
        if not cases:
            _fail(ErrorCode.INVALID_INPUT, "ASR evaluation requires at least one case")
        if len(cases) > 500:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR evaluation case count exceeds its policy")
        if private_gold and any(case.synthetic for case in cases):
            _fail(ErrorCode.POLICY_BLOCKED, "ASR private Gold Set cannot contain synthetic cases")
        clear = [case for case in cases if case.stratum == "clear_mandarin"]
        if private_gold and len(clear) < 20:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR private Gold Set requires at least 20 clear Mandarin cases")
        required_strata = {"clear_mandarin", "noise", "music", "dialect", "mixed_language", "no_speech"}
        present_strata = {case.stratum for case in cases}
        if private_gold and not required_strata.issubset(present_strata):
            _fail(ErrorCode.POLICY_BLOCKED, "ASR private Gold Set is not stratified")
        cer_rates = [
            character_error_rate(case.reference_text, case.predicted_text, maximum_chars=self.policy.max_cer_chars)
            for case in clear
        ]
        wer_rates = [word_error_rate(case.reference_text, case.predicted_text, maximum_chars=self.policy.max_cer_chars) for case in clear]
        median_cer = None if not cer_rates else _median(cer_rates)
        median_wer = None if not wer_rates else _median(wer_rates)
        hallucinations = sum(
            bool(normalize_for_cer(case.predicted_text))
            for case in cases
            if case.stratum == "no_speech" and not case.provider_failed
        )
        omissions = sum(
            bool(normalize_for_cer(case.reference_text)) and not bool(normalize_for_cer(case.predicted_text))
            for case in cases
        )
        failures = sum(case.provider_failed for case in cases)
        provenance_complete = sum(
            case.provider is not None and case.input_hash is not None and case.prompt_sha256 is not None for case in cases
        )
        if private_gold and provenance_complete != len(cases):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR private Gold Set provenance is incomplete")
        if not private_gold:
            status: Literal["pass", "low_quality", "not_run"] = "not_run"
            scope: Literal["ci_synth_contract_only", "private_gold"] = "ci_synth_contract_only"
        else:
            status = (
                "pass"
                if median_cer is not None and median_cer <= 0.15 and hallucinations == 0 and failures == 0
                else "low_quality"
            )
            scope = "private_gold"
        return AsrEvaluationReport(
            scope,
            len(clear),
            median_cer,
            median_wer,
            hallucinations,
            omissions,
            failures,
            provenance_complete,
            status,
            len(cases),
        )


class AsrBudget:
    """Session-local budget; cache hits consume no additional provider invocation."""

    def __init__(self, policy: AsrPolicy) -> None:
        self.policy = policy
        self.invocations = 0
        self.audio_seconds = 0.0

    def reserve(self, provider: AsrProviderDescriptor, *, audio_seconds: float) -> int:
        if provider.mode == _CLOUD_MODE:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR cloud upload is not authorized")
        if not math.isfinite(audio_seconds) or not 0 < audio_seconds <= self.policy.max_audio_seconds:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR audio duration exceeds its policy")
        provider_calls = math.ceil(audio_seconds / self.policy.chunk_seconds)
        if (
            provider_calls > self.policy.max_chunks
            or self.invocations + provider_calls > self.policy.max_invocations
            or self.audio_seconds + audio_seconds > self.policy.max_audio_seconds
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "ASR session budget is exhausted")
        self.invocations += provider_calls
        self.audio_seconds += audio_seconds
        return provider_calls

    def safe_dict(self) -> dict[str, float | int]:
        return {"audio_seconds": self.audio_seconds, "cloud_cost_microunits": 0, "invocations": self.invocations}


class AsrSession:
    def __init__(self, providers: dict[str, AsrProvider], *, policy: AsrPolicy) -> None:
        self._providers = providers
        self._policy = policy
        self._budget = AsrBudget(policy)
        self._cache: dict[tuple[str, str, str, str, str, str, int], EphemeralTranscript] = {}
        self._invocations: list[AsrInvocation] = []
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def invocations(self) -> tuple[AsrInvocation, ...]:
        return tuple(self._invocations)

    def safe_ledger(self) -> dict[str, object]:
        return {
            "budget": self._budget.safe_dict(),
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cloud_uploads": 0,
            "invocations": [item.safe_dict() for item in self._invocations],
        }

    def transcribe(
        self,
        audio: EphemeralDerivedArtifact,
        *,
        audio_seconds: float,
        language: str = "zh",
        provider_id: str,
    ) -> AsrResult:
        _safe_token(language, label="language")
        provider_key = _safe_token(provider_id, label="provider id")
        if not math.isfinite(audio_seconds) or not 0 < audio_seconds <= self._policy.max_audio_seconds:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR audio duration exceeds its policy")
        if _SHA256.fullmatch(audio.sha256) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR audio artifact hash is invalid")
        provider = self._providers.get(provider_key)
        if provider is None:
            _fail(ErrorCode.POLICY_BLOCKED, "ASR provider is unavailable")
        descriptor = provider.descriptor
        prompt_sha256 = _prompt_sha256(descriptor, language=language, policy=self._policy)
        cache_key = (
            descriptor.provider_id,
            descriptor.provider_version,
            descriptor.model_snapshot_sha256,
            language,
            prompt_sha256,
            audio.sha256,
            round(audio_seconds * 1000),
        )
        transcript = self._cache.get(cache_key)
        cache_hit = transcript is not None
        provider_calls = 0
        if transcript is None:
            provider_calls = self._budget.reserve(descriptor, audio_seconds=audio_seconds)
            transcript = provider.transcribe(audio, audio_seconds=audio_seconds, language=language, policy=self._policy)
            if transcript.input_hash != audio.sha256 or transcript.language != language:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "ASR provider transcript provenance is invalid")
            self._cache[cache_key] = transcript
            self._cache_misses += 1
        else:
            self._cache_hits += 1
        cache_tokens = tuple(str(value) for value in cache_key)
        invocation_seed = "|".join((*cache_tokens, transcript.text_sha256, str(len(self._invocations))))
        artifact_seed = "|".join((*cache_tokens, transcript.text_sha256))
        invocation = AsrInvocation(
            invocation_id=f"asr_{hashlib.sha256(invocation_seed.encode('utf-8')).hexdigest()[:32]}",
            provider=descriptor,
            input_hash=audio.sha256,
            language=language,
            prompt_sha256=prompt_sha256,
            audio_seconds=audio_seconds,
            cache_hit=cache_hit,
            provider_calls=provider_calls,
            cloud_uploads=0,
            cost_microunits=0,
            transcript_hash=transcript.text_sha256,
        )
        self._invocations.append(invocation)
        artifact_id = f"asr_artifact_{hashlib.sha256(artifact_seed.encode('utf-8')).hexdigest()[:32]}"
        return AsrResult(transcript, invocation, artifact_id)

    def close(self) -> None:
        self._cache.clear()
        self._invocations.clear()
        self._cache_hits = 0
        self._cache_misses = 0


class AsrProcessor:
    """Create short-lived ASR sessions; callers cannot enable cloud by configuration."""

    def __init__(self, providers: Sequence[AsrProvider], *, policy: AsrPolicy = AsrPolicy()) -> None:
        indexed: dict[str, AsrProvider] = {}
        for provider in providers:
            descriptor = provider.descriptor
            if descriptor.provider_id in indexed:
                _fail(ErrorCode.INVALID_INPUT, "ASR provider identifiers must be unique")
            indexed[descriptor.provider_id] = provider
        if not indexed:
            _fail(ErrorCode.INVALID_INPUT, "ASR requires at least one provider route")
        self._providers = indexed
        self.policy = policy

    @contextmanager
    def session(self) -> Iterator[AsrSession]:
        session = AsrSession(self._providers, policy=self.policy)
        try:
            yield session
        finally:
            session.close()
