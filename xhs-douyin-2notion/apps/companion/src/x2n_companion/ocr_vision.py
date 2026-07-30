"""Lease-scoped local OCR and Vision provider contracts.

Task003 deliberately exposes an adapter boundary, not an automatic model
installation or cloud route.  It accepts only Task001's owner-only temporary
JPEG artifacts, keeps text and descriptions in memory, and records only
opaque hashes and aggregate provenance in safe receipts.  Local adapters use
one small JSON-file protocol inside the existing subprocess sandbox; cloud
descriptors are representable for auditability but their route is disabled.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from x2n_contracts import ErrorCode

from .asr import character_error_rate, normalize_for_cer
from .media_preprocessing import (
    EphemeralDerivedArtifact,
    MediaCommand,
    MediaCommandRunner,
    MediaProcessingPolicy,
    SandboxedCommandRunner,
)
from .runtime import RuntimePaths, X2NRuntimeError


TASK_ID = "TSK.x2n.multimodal.003"
OCR_VISION_POLICY_VERSION = "x2n-ocr-vision-v1"
OCR_LOCAL_PROTOCOL_VERSION = "x2n-local-ocr-v1"
VISION_LOCAL_PROTOCOL_VERSION = "x2n-local-vision-v1"
OCR_GOLD_DATASET_SCHEMA = "x2n-ocr-gold-v1"
VISION_GOLD_DATASET_SCHEMA = "x2n-vision-gold-v1"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGES_PER_SESSION = 50
MAX_TOTAL_IMAGE_BYTES = MAX_IMAGE_BYTES * MAX_IMAGES_PER_SESSION
MAX_OCR_TEXT_CHARS = 20_000
MAX_OCR_SPANS = 512
MAX_VISION_DESCRIPTION_CHARS = 2_048
MAX_PROVIDER_OUTPUT_BYTES = 512 * 1024
MAX_GOLD_DATASET_BYTES = 2 * 1024 * 1024
MAX_MODEL_FILE_BYTES = 4 * 1024 * 1024 * 1024
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_JPEG_HEADER = b"\xff\xd8\xff"
_OCR_STRATA = frozenset({"clear", "low_resolution", "rotated", "subtitle", "watermark", "table", "no_text"})
_VISION_STRATA = frozenset(
    {"image_post", "product_interface", "chart", "scene_change", "irrelevant_frame", "sensitive", "unsupported"}
)
_VISION_STATUSES = frozenset({"described", "unsupported_sensitive", "unsupported_content"})


def _fail(code: ErrorCode, message: str) -> None:
    raise X2NRuntimeError(code, message)


def _safe_token(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        _fail(ErrorCode.INVALID_INPUT, f"OCR/Vision {label} is invalid")
    return value


def _sha256_file(path: Path, *, maximum_bytes: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private file is unsafe")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > maximum_bytes:
                    _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private file exceeds its resource policy")
                digest.update(chunk)
    except X2NRuntimeError:
        raise
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision private file is unavailable") from None
    if size <= 0:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private file is empty")
    return digest.hexdigest(), size


def _private_regular_file(path: Path, *, maximum_bytes: int, suffix: str | None = None) -> int:
    if suffix is not None and path.suffix != suffix:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private file type is invalid")
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private file is unavailable")
    try:
        metadata = path.stat()
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision private file is unavailable") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private file is not owner-only")
    if not 0 < metadata.st_size <= maximum_bytes:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private file exceeds its resource policy")
    return int(metadata.st_size)


def _private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private workspace is unavailable")
    try:
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private workspace is not owner-only")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision private workspace is unavailable") from None


def _private_child(root: Path, name: str) -> Path:
    candidate = root / name
    if Path(name).is_absolute() or "/" in name or "\\" in name or ".." in Path(name).parts:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision private child name is invalid")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision output escaped its workspace")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision private workspace is unavailable") from None
    return candidate


def _remove_private_file(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision output cleanup is unsafe")
    try:
        path.unlink()
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision temporary cleanup failed closed") from None


def _validate_ephemeral_image(
    paths: RuntimePaths, image: EphemeralDerivedArtifact, *, policy: "OcrVisionPolicy"
) -> Path:
    if image.mime != "image/jpeg" or _SHA256.fullmatch(image.sha256) is None:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision accepts only Task001 JPEG artifacts")
    if (
        isinstance(image.size_bytes, bool)
        or not isinstance(image.size_bytes, int)
        or not 0 < image.size_bytes <= policy.max_image_bytes
    ):
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision image exceeds its resource policy")
    try:
        root = paths.temp_media_directory.resolve(strict=True)
        resolved = image.local_path.resolve(strict=True)
        resolved.relative_to(root)
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision image escaped the temporary media root")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision image is unavailable") from None
    _private_directory(resolved.parent)
    size = _private_regular_file(resolved, maximum_bytes=policy.max_image_bytes, suffix=".jpg")
    digest, hashed_size = _sha256_file(resolved, maximum_bytes=policy.max_image_bytes)
    if size != image.size_bytes or hashed_size != image.size_bytes or digest != image.sha256:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision image changed after preprocessing")
    try:
        header = resolved.read_bytes()[:3]
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "OCR/Vision image is unavailable") from None
    if header != _JPEG_HEADER:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision image is not JPEG")
    return resolved


def _trusted_model_file(paths: RuntimePaths, path: Path, *, executable: bool) -> tuple[Path, str]:
    try:
        root = (paths.data_root / "runtime/models").resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        metadata = resolved.stat()
    except (OSError, ValueError):
        _fail(ErrorCode.DEPENDENCY_MISSING, "OCR/Vision local provider dependency is unavailable")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (executable and not os.access(resolved, os.X_OK))
    ):
        _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision local provider dependency is not owner-managed")
    digest, _ = _sha256_file(resolved, maximum_bytes=MAX_MODEL_FILE_BYTES)
    return resolved, digest


def _normalized_box(value: object) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR bounding box is invalid")
    parsed: list[float] = []
    for coordinate in value:
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, (int, float))
            or not math.isfinite(float(coordinate))
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR bounding box is invalid")
        parsed.append(float(coordinate))
    left, top, width, height = parsed
    if not 0 <= left <= 1 or not 0 <= top <= 1 or not 0 < width <= 1 or not 0 < height <= 1:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR bounding box is invalid")
    if left + width > 1 or top + height > 1:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR bounding box exceeds the image")
    return tuple(parsed)  # type: ignore[return-value]


def _median(values: Sequence[float]) -> float:
    if not values:
        _fail(ErrorCode.INVALID_INPUT, "OCR/Vision median requires values")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    return ordered[midpoint] if len(ordered) % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2


@dataclass(frozen=True)
class OcrVisionPolicy:
    """Non-relaxable local-only resource and cache policy for Task003."""

    version: str = OCR_VISION_POLICY_VERSION
    max_image_bytes: int = MAX_IMAGE_BYTES
    max_images_per_session: int = MAX_IMAGES_PER_SESSION
    max_total_image_bytes: int = MAX_TOTAL_IMAGE_BYTES
    max_ocr_text_chars: int = MAX_OCR_TEXT_CHARS
    max_ocr_spans: int = MAX_OCR_SPANS
    max_vision_description_chars: int = MAX_VISION_DESCRIPTION_CHARS
    max_provider_output_bytes: int = MAX_PROVIDER_OUTPUT_BYTES
    command_timeout_seconds: int = 60
    total_timeout_seconds: int = 600
    max_provider_calls: int = MAX_IMAGES_PER_SESSION
    max_cloud_cost_microunits: int = 0

    def __post_init__(self) -> None:
        if self.version != OCR_VISION_POLICY_VERSION:
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision policy version is unsupported")
        fields = (
            "max_image_bytes",
            "max_images_per_session",
            "max_total_image_bytes",
            "max_ocr_text_chars",
            "max_ocr_spans",
            "max_vision_description_chars",
            "max_provider_output_bytes",
            "command_timeout_seconds",
            "total_timeout_seconds",
            "max_provider_calls",
        )
        for label in fields:
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                _fail(ErrorCode.INVALID_INPUT, f"OCR/Vision {label} is invalid")
        if isinstance(self.max_cloud_cost_microunits, bool) or not isinstance(self.max_cloud_cost_microunits, int):
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision cloud budget is invalid")
        if (
            self.max_image_bytes > MAX_IMAGE_BYTES
            or self.max_images_per_session > MAX_IMAGES_PER_SESSION
            or self.max_total_image_bytes > MAX_TOTAL_IMAGE_BYTES
            or self.max_total_image_bytes < self.max_image_bytes
            or self.max_ocr_text_chars > MAX_OCR_TEXT_CHARS
            or self.max_ocr_spans > MAX_OCR_SPANS
            or self.max_vision_description_chars > MAX_VISION_DESCRIPTION_CHARS
            or self.max_provider_output_bytes > MAX_PROVIDER_OUTPUT_BYTES
            or self.command_timeout_seconds > 120
            or self.total_timeout_seconds > 600
            or self.command_timeout_seconds > self.total_timeout_seconds
            or self.max_provider_calls > MAX_IMAGES_PER_SESSION
            or self.max_cloud_cost_microunits != 0
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision policy exceeds its approved budget")

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "command_timeout_seconds": self.command_timeout_seconds,
            "max_cloud_cost_microunits": self.max_cloud_cost_microunits,
            "max_image_bytes": self.max_image_bytes,
            "max_images_per_session": self.max_images_per_session,
            "max_ocr_spans": self.max_ocr_spans,
            "max_ocr_text_chars": self.max_ocr_text_chars,
            "max_provider_calls": self.max_provider_calls,
            "max_provider_output_bytes": self.max_provider_output_bytes,
            "max_total_image_bytes": self.max_total_image_bytes,
            "max_vision_description_chars": self.max_vision_description_chars,
            "total_timeout_seconds": self.total_timeout_seconds,
            "version": self.version,
        }


OCR_VISION_SANDBOX_POLICY = MediaProcessingPolicy(
    command_timeout_seconds=120,
    total_timeout_seconds=120,
    cpu_limit_seconds=120,
)


@dataclass(frozen=True)
class ProviderCapabilities:
    capability: Literal["ocr", "vision"]
    supported_mime_types: tuple[str, ...] = ("image/jpeg",)
    max_image_bytes: int = MAX_IMAGE_BYTES
    supports_bounding_boxes: bool = False
    supports_sensitive_refusal: bool = True

    def __post_init__(self) -> None:
        if self.capability not in {"ocr", "vision"}:
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision capability is invalid")
        if self.supported_mime_types != ("image/jpeg",):
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision MIME capability exceeds Task001 artifacts")
        if (
            isinstance(self.max_image_bytes, bool)
            or not isinstance(self.max_image_bytes, int)
            or not 0 < self.max_image_bytes <= MAX_IMAGE_BYTES
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision image capability exceeds its policy")
        if not isinstance(self.supports_bounding_boxes, bool) or not isinstance(self.supports_sensitive_refusal, bool):
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision capability flags are invalid")
        if self.capability == "vision" and not self.supports_sensitive_refusal:
            _fail(ErrorCode.POLICY_BLOCKED, "Vision provider must support structured safety refusal")

    def safe_dict(self) -> dict[str, bool | int | list[str] | str]:
        return {
            "capability": self.capability,
            "max_image_bytes": self.max_image_bytes,
            "supported_mime_types": list(self.supported_mime_types),
            "supports_bounding_boxes": self.supports_bounding_boxes,
            "supports_sensitive_refusal": self.supports_sensitive_refusal,
        }


@dataclass(frozen=True)
class ImageProviderDescriptor:
    provider_id: str
    provider_version: str
    capability: Literal["ocr", "vision"]
    mode: Literal["local", "cloud"]
    model_id: str
    model_snapshot_sha256: str
    executable_sha256: str | None
    cloud_upload_authorized: bool
    retention: Literal["local_ephemeral", "disabled"]
    capabilities: ProviderCapabilities

    def __post_init__(self) -> None:
        _safe_token(self.provider_id, label="provider id")
        _safe_token(self.provider_version, label="provider version")
        _safe_token(self.model_id, label="model id")
        if self.capability not in {"ocr", "vision"} or self.capabilities.capability != self.capability:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision provider capability provenance is invalid")
        if _SHA256.fullmatch(self.model_snapshot_sha256) is None:
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision model snapshot is invalid")
        if self.executable_sha256 is not None and _SHA256.fullmatch(self.executable_sha256) is None:
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision executable snapshot is invalid")
        if self.mode == "local":
            if self.cloud_upload_authorized or self.retention != "local_ephemeral" or self.executable_sha256 is None:
                _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision local provider provenance is invalid")
        elif self.mode == "cloud":
            if self.cloud_upload_authorized or self.retention != "disabled" or self.executable_sha256 is not None:
                _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision cloud provider is disabled by policy")
        else:  # pragma: no cover - Literal is a type aid; retain a runtime guard.
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision provider mode is invalid")

    def safe_dict(self) -> dict[str, object]:
        return {
            "capabilities": self.capabilities.safe_dict(),
            "capability": self.capability,
            "cloud_upload_authorized": self.cloud_upload_authorized,
            "executable_sha256": self.executable_sha256,
            "mode": self.mode,
            "model_id": self.model_id,
            "model_snapshot_sha256": self.model_snapshot_sha256,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "retention": self.retention,
        }


def _descriptor_from_private_payload(value: object) -> ImageProviderDescriptor:
    if not isinstance(value, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private Gold Set provider is invalid")
    expected = {
        "capabilities",
        "capability",
        "cloud_upload_authorized",
        "executable_sha256",
        "mode",
        "model_id",
        "model_snapshot_sha256",
        "provider_id",
        "provider_version",
        "retention",
    }
    if set(value) != expected or not isinstance(value["capabilities"], dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private Gold Set provider shape is invalid")
    capabilities_payload = value["capabilities"]
    capabilities_expected = {
        "capability",
        "max_image_bytes",
        "supported_mime_types",
        "supports_bounding_boxes",
        "supports_sensitive_refusal",
    }
    if set(capabilities_payload) != capabilities_expected or not isinstance(
        capabilities_payload["supported_mime_types"], list
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private Gold Set capability shape is invalid")
    try:
        capabilities = ProviderCapabilities(
            capability=capabilities_payload["capability"],
            supported_mime_types=tuple(capabilities_payload["supported_mime_types"]),
            max_image_bytes=capabilities_payload["max_image_bytes"],
            supports_bounding_boxes=capabilities_payload["supports_bounding_boxes"],
            supports_sensitive_refusal=capabilities_payload["supports_sensitive_refusal"],
        )
        return ImageProviderDescriptor(
            provider_id=value["provider_id"],
            provider_version=value["provider_version"],
            capability=value["capability"],
            mode=value["mode"],
            model_id=value["model_id"],
            model_snapshot_sha256=value["model_snapshot_sha256"],
            executable_sha256=value["executable_sha256"],
            cloud_upload_authorized=value["cloud_upload_authorized"],
            retention=value["retention"],
            capabilities=capabilities,
        )
    except (TypeError, X2NRuntimeError):
        raise X2NRuntimeError(
            ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private Gold Set provider is invalid"
        ) from None


def _prompt_sha256(descriptor: ImageProviderDescriptor, *, policy: OcrVisionPolicy) -> str:
    payload = {
        "adapter": f"x2n-local-{descriptor.capability}-json-v1",
        "capability": descriptor.capability,
        "model_snapshot_sha256": descriptor.model_snapshot_sha256,
        "policy_version": policy.version,
        "provider_id": descriptor.provider_id,
        "provider_version": descriptor.provider_version,
        "safety": "visible_only_no_sensitive_inference",
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class OcrSpan:
    text: str = field(repr=False, compare=False)
    bounding_box: tuple[float, float, float, float] | None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > MAX_OCR_TEXT_CHARS:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR span is invalid")
        if self.bounding_box is not None:
            _normalized_box(list(self.bounding_box))

    def safe_dict(self) -> dict[str, bool | str]:
        return {
            "has_bounding_box": self.bounding_box is not None,
            "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
        }


@dataclass(frozen=True)
class EphemeralOcrArtifact:
    source_image_hash: str
    language: str
    status: Literal["ok", "no_text"]
    spans: tuple[OcrSpan, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.source_image_hash) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR source image provenance is invalid")
        _safe_token(self.language, label="OCR language")
        if self.status not in {"ok", "no_text"} or len(self.spans) > MAX_OCR_SPANS:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR artifact is invalid")
        if self.status == "no_text" and self.spans:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR no-text artifact is invalid")
        if self.status == "ok" and not self.spans:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR successful artifact cannot be empty")
        if len(self.text) > MAX_OCR_TEXT_CHARS:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR text exceeds its resource policy")

    @property
    def text(self) -> str:
        return "\n".join(span.text.strip() for span in self.spans).strip()

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def output_sha256(self) -> str:
        payload = {"language": self.language, "status": self.status, "text_sha256": self.text_sha256}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def safe_dict(self) -> dict[str, bool | int | str]:
        return {
            "bounding_box_count": sum(span.bounding_box is not None for span in self.spans),
            "language": self.language,
            "source_image_hash": self.source_image_hash,
            "status": self.status,
            "text_characters": len(self.text),
            "text_sha256": self.text_sha256,
            "text_emitted": False,
            "span_count": len(self.spans),
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral OCR artifacts cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral OCR artifacts cannot be serialized")


@dataclass(frozen=True)
class EphemeralVisionArtifact:
    source_image_hash: str
    status: Literal["described", "unsupported_sensitive", "unsupported_content"]
    description: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.source_image_hash) is None or self.status not in _VISION_STATUSES:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision artifact is invalid")
        if not isinstance(self.description, str) or len(self.description) > MAX_VISION_DESCRIPTION_CHARS:
            _fail(ErrorCode.POLICY_BLOCKED, "Vision description exceeds its resource policy")
        if self.status == "described" and not self.description.strip():
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision description is empty")
        if self.status != "described" and self.description:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision refusal must not fabricate a description")

    @property
    def description_sha256(self) -> str:
        return hashlib.sha256(self.description.encode("utf-8")).hexdigest()

    @property
    def output_sha256(self) -> str:
        payload = {"description_sha256": self.description_sha256, "status": self.status}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def safe_dict(self) -> dict[str, bool | int | str]:
        return {
            "description_characters": len(self.description),
            "description_emitted": False,
            "description_sha256": self.description_sha256,
            "source_image_hash": self.source_image_hash,
            "status": self.status,
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral Vision artifacts cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral Vision artifacts cannot be serialized")


@dataclass(frozen=True)
class ImageInvocation:
    invocation_id: str
    provider: ImageProviderDescriptor
    input_hash: str
    prompt_sha256: str
    cache_hit: bool
    provider_calls: int
    cloud_uploads: int
    cost_microunits: int
    output_hash: str

    def __post_init__(self) -> None:
        _safe_token(self.invocation_id, label="invocation id")
        if (
            _SHA256.fullmatch(self.input_hash) is None
            or _SHA256.fullmatch(self.prompt_sha256) is None
            or _SHA256.fullmatch(self.output_hash) is None
            or isinstance(self.provider_calls, bool)
            or not isinstance(self.provider_calls, int)
            or self.provider_calls < 0
            or self.cloud_uploads != 0
            or self.cost_microunits != 0
        ):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision invocation provenance is invalid")

    def safe_dict(self) -> dict[str, object]:
        return {
            "cache_hit": self.cache_hit,
            "cloud_uploads": self.cloud_uploads,
            "cost_microunits": self.cost_microunits,
            "input_hash": self.input_hash,
            "invocation_id": self.invocation_id,
            "output_hash": self.output_hash,
            "prompt_sha256": self.prompt_sha256,
            "provider": self.provider.safe_dict(),
            "provider_calls": self.provider_calls,
        }


@dataclass(frozen=True)
class OcrResult:
    artifact: EphemeralOcrArtifact = field(repr=False, compare=False)
    invocation: ImageInvocation
    artifact_id: str

    def __post_init__(self) -> None:
        _safe_token(self.artifact_id, label="OCR artifact id")

    def safe_dict(self) -> dict[str, object]:
        return {
            "artifact": self.artifact.safe_dict(),
            "artifact_id": self.artifact_id,
            "invocation": self.invocation.safe_dict(),
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral OCR results cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral OCR results cannot be serialized")


@dataclass(frozen=True)
class VisionResult:
    artifact: EphemeralVisionArtifact = field(repr=False, compare=False)
    invocation: ImageInvocation
    artifact_id: str

    def __post_init__(self) -> None:
        _safe_token(self.artifact_id, label="Vision artifact id")

    def safe_dict(self) -> dict[str, object]:
        return {
            "artifact": self.artifact.safe_dict(),
            "artifact_id": self.artifact_id,
            "invocation": self.invocation.safe_dict(),
        }

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral Vision results cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral Vision results cannot be serialized")


class OcrProvider(Protocol):
    descriptor: ImageProviderDescriptor

    def extract(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralOcrArtifact:
        """Extract untrusted image text or fail before an unsafe side effect."""


class VisionProvider(Protocol):
    descriptor: ImageProviderDescriptor

    def describe(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralVisionArtifact:
        """Describe visible content or return a bounded structured refusal."""


def _load_local_json(path: Path, *, policy: OcrVisionPolicy) -> dict[str, object]:
    _private_regular_file(path, maximum_bytes=policy.max_provider_output_bytes, suffix=".json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision provider JSON is invalid") from None
    if not isinstance(payload, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision provider JSON shape is invalid")
    return payload


def _parse_local_ocr_payload(
    payload: Mapping[str, object],
    *,
    source_image_hash: str,
    policy: OcrVisionPolicy,
) -> EphemeralOcrArtifact:
    if set(payload) != {"language", "schema_version", "spans", "status"}:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR provider JSON shape is invalid")
    if payload.get("schema_version") != OCR_LOCAL_PROTOCOL_VERSION:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR provider protocol is invalid")
    status = payload.get("status")
    language = payload.get("language")
    spans_payload = payload.get("spans")
    if status not in {"ok", "no_text"} or not isinstance(language, str) or not isinstance(spans_payload, list):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR provider result is invalid")
    if len(spans_payload) > policy.max_ocr_spans:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR provider returned too many spans")
    spans: list[OcrSpan] = []
    for value in spans_payload:
        if not isinstance(value, dict) or set(value) != {"bbox", "text"} or not isinstance(value.get("text"), str):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR provider span is invalid")
        spans.append(OcrSpan(value["text"], _normalized_box(value.get("bbox"))))
    artifact = EphemeralOcrArtifact(source_image_hash, language, status, tuple(spans))  # type: ignore[arg-type]
    if len(artifact.text) > policy.max_ocr_text_chars:
        _fail(ErrorCode.POLICY_BLOCKED, "OCR provider text exceeds its resource policy")
    return artifact


def _parse_local_vision_payload(
    payload: Mapping[str, object],
    *,
    source_image_hash: str,
    policy: OcrVisionPolicy,
) -> EphemeralVisionArtifact:
    if set(payload) != {"description", "schema_version", "status"}:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision provider JSON shape is invalid")
    if payload.get("schema_version") != VISION_LOCAL_PROTOCOL_VERSION:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision provider protocol is invalid")
    status = payload.get("status")
    description = payload.get("description")
    if status not in _VISION_STATUSES or not isinstance(description, str):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision provider result is invalid")
    artifact = EphemeralVisionArtifact(source_image_hash, status, description)  # type: ignore[arg-type]
    if len(artifact.description) > policy.max_vision_description_chars:
        _fail(ErrorCode.POLICY_BLOCKED, "Vision provider description exceeds its resource policy")
    return artifact


class _LocalJsonImageProvider:
    """Owner-managed offline JSON adapter shared by OCR and Vision providers.

    The invoked executable is not supplied by this repository.  It must be an
    Owner-managed local program below ``runtime/models`` that implements the
    exact fixed argument and JSON protocol below.  No call path accepts a URL,
    credential, arbitrary command, prompt, or output location.
    """

    capability: Literal["ocr", "vision"]
    protocol_version: str

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        executable_path: Path,
        model_path: Path,
        descriptor: ImageProviderDescriptor,
        policy: OcrVisionPolicy = OcrVisionPolicy(),
        runner: MediaCommandRunner | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if descriptor.mode != "local" or descriptor.capability != self.capability:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision local adapter requires a matching local provider descriptor")
        executable, executable_digest = _trusted_model_file(paths, executable_path, executable=True)
        model, model_digest = _trusted_model_file(paths, model_path, executable=False)
        if descriptor.executable_sha256 != executable_digest or descriptor.model_snapshot_sha256 != model_digest:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision local provider provenance changed")
        self.paths = paths
        self.executable_path = executable
        self.model_path = model
        self.descriptor = descriptor
        self.policy = policy
        self.runner = runner or SandboxedCommandRunner()
        self.monotonic = monotonic

    def _run_payload(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> dict[str, object]:
        if policy != self.policy:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision provider policy does not match its session")
        image_path = _validate_ephemeral_image(self.paths, image, policy=policy)
        workspace = image_path.parent
        _private_directory(workspace)
        output_token = hashlib.sha256(
            f"{self.capability}|{self.descriptor.provider_version}|{image.sha256}".encode("utf-8")
        ).hexdigest()[:32]
        output_path = _private_child(workspace, f"x2n-{self.capability}-{output_token}.json")
        if output_path.exists() or output_path.is_symlink():
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision provider output path is already occupied")
        deadline = self.monotonic() + policy.total_timeout_seconds
        try:
            remaining = deadline - self.monotonic()
            if not math.isfinite(remaining) or remaining <= 0:
                _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision exceeded its total timeout")
            # ``MediaCommand`` predates model adapters.  Its ``probe`` role is
            # only a private-JSON sandbox label here; it never denotes a network
            # probe and the fixed local adapter receives just an ephemeral file.
            self.runner.run(
                MediaCommand(
                    role="probe",
                    argv=(
                        str(self.executable_path),
                        "--protocol",
                        self.protocol_version,
                        "--task",
                        self.capability,
                        "--model",
                        str(self.model_path),
                        "--input",
                        str(image_path),
                        "--output",
                        str(output_path),
                        "--offline",
                        "--visible-only",
                    ),
                    cwd=workspace,
                    output_paths=(output_path,),
                    timeout_seconds=min(float(policy.command_timeout_seconds), remaining),
                    max_output_bytes=policy.max_provider_output_bytes,
                ),
                policy=OCR_VISION_SANDBOX_POLICY,
            )
            return _load_local_json(output_path, policy=policy)
        finally:
            _remove_private_file(output_path)


class LocalJsonOcrProvider(_LocalJsonImageProvider):
    """Fixed local OCR JSON adapter with untrusted in-memory text output."""

    capability: Literal["ocr"] = "ocr"
    protocol_version = OCR_LOCAL_PROTOCOL_VERSION

    def extract(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralOcrArtifact:
        payload = self._run_payload(image, policy=policy)
        return _parse_local_ocr_payload(payload, source_image_hash=image.sha256, policy=policy)


class LocalJsonVisionProvider(_LocalJsonImageProvider):
    """Fixed local Vision JSON adapter with visible-only structured refusal."""

    capability: Literal["vision"] = "vision"
    protocol_version = VISION_LOCAL_PROTOCOL_VERSION

    def describe(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralVisionArtifact:
        payload = self._run_payload(image, policy=policy)
        return _parse_local_vision_payload(payload, source_image_hash=image.sha256, policy=policy)


class DisabledCloudOcrProvider:
    """Non-network OCR route that makes any cloud upload request fail closed."""

    def __init__(self, descriptor: ImageProviderDescriptor) -> None:
        if descriptor.capability != "ocr" or descriptor.mode != "cloud" or descriptor.cloud_upload_authorized:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR cloud provider is not disabled")
        self.descriptor = descriptor

    def extract(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralOcrArtifact:
        del image, policy
        _fail(ErrorCode.POLICY_BLOCKED, "OCR cloud upload is not authorized")


class DisabledCloudVisionProvider:
    """Non-network Vision route that makes any cloud upload request fail closed."""

    def __init__(self, descriptor: ImageProviderDescriptor) -> None:
        if descriptor.capability != "vision" or descriptor.mode != "cloud" or descriptor.cloud_upload_authorized:
            _fail(ErrorCode.POLICY_BLOCKED, "Vision cloud provider is not disabled")
        self.descriptor = descriptor

    def describe(self, image: EphemeralDerivedArtifact, *, policy: OcrVisionPolicy) -> EphemeralVisionArtifact:
        del image, policy
        _fail(ErrorCode.POLICY_BLOCKED, "Vision cloud upload is not authorized")


class ImageProcessingBudget:
    """Session-local provider budget; cache hits consume no model execution."""

    def __init__(self, policy: OcrVisionPolicy) -> None:
        self.policy = policy
        self.image_bytes = 0
        self.provider_calls = 0

    def reserve(self, descriptor: ImageProviderDescriptor, *, image_bytes: int) -> int:
        if descriptor.mode != "local" or descriptor.cloud_upload_authorized:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision cloud upload is not authorized")
        if (
            isinstance(image_bytes, bool)
            or not isinstance(image_bytes, int)
            or not 0 < image_bytes <= self.policy.max_image_bytes
            or self.provider_calls + 1 > self.policy.max_provider_calls
            or self.image_bytes + image_bytes > self.policy.max_total_image_bytes
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision session budget is exhausted")
        self.provider_calls += 1
        self.image_bytes += image_bytes
        return 1

    def safe_dict(self) -> dict[str, int]:
        return {"cloud_cost_microunits": 0, "image_bytes": self.image_bytes, "provider_calls": self.provider_calls}


class OcrVisionSession:
    def __init__(
        self,
        paths: RuntimePaths,
        providers: dict[str, OcrProvider | VisionProvider],
        *,
        policy: OcrVisionPolicy,
    ) -> None:
        self._paths = paths
        self._providers = providers
        self._policy = policy
        self._budget = ImageProcessingBudget(policy)
        self._cache: dict[tuple[str, str, str, str, str, str], EphemeralOcrArtifact | EphemeralVisionArtifact] = {}
        self._invocations: list[ImageInvocation] = []
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def invocations(self) -> tuple[ImageInvocation, ...]:
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

    def _provider(self, provider_id: str, *, capability: Literal["ocr", "vision"]) -> OcrProvider | VisionProvider:
        key = _safe_token(provider_id, label="provider id")
        provider = self._providers.get(key)
        if provider is None or provider.descriptor.capability != capability:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR/Vision provider is unavailable")
        return provider

    @staticmethod
    def _cache_key(
        descriptor: ImageProviderDescriptor, *, input_hash: str, prompt_sha256: str
    ) -> tuple[str, str, str, str, str, str]:
        return (
            descriptor.capability,
            descriptor.provider_id,
            descriptor.provider_version,
            descriptor.model_snapshot_sha256,
            prompt_sha256,
            input_hash,
        )

    def _invocation(
        self,
        descriptor: ImageProviderDescriptor,
        *,
        image: EphemeralDerivedArtifact,
        prompt_sha256: str,
        cache_hit: bool,
        provider_calls: int,
        output_hash: str,
    ) -> ImageInvocation:
        seed = "|".join(
            (
                descriptor.capability,
                descriptor.provider_id,
                descriptor.provider_version,
                descriptor.model_snapshot_sha256,
                prompt_sha256,
                image.sha256,
                output_hash,
                str(len(self._invocations)),
            )
        )
        invocation = ImageInvocation(
            invocation_id=f"image_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:32]}",
            provider=descriptor,
            input_hash=image.sha256,
            prompt_sha256=prompt_sha256,
            cache_hit=cache_hit,
            provider_calls=provider_calls,
            cloud_uploads=0,
            cost_microunits=0,
            output_hash=output_hash,
        )
        self._invocations.append(invocation)
        return invocation

    def extract_ocr(self, image: EphemeralDerivedArtifact, *, provider_id: str) -> OcrResult:
        _validate_ephemeral_image(self._paths, image, policy=self._policy)
        provider = self._provider(provider_id, capability="ocr")
        descriptor = provider.descriptor
        prompt_sha256 = _prompt_sha256(descriptor, policy=self._policy)
        cache_key = self._cache_key(descriptor, input_hash=image.sha256, prompt_sha256=prompt_sha256)
        cached = self._cache.get(cache_key)
        provider_calls = 0
        if cached is None:
            provider_calls = self._budget.reserve(descriptor, image_bytes=image.size_bytes)
            artifact = provider.extract(image, policy=self._policy)  # type: ignore[union-attr]
            if artifact.source_image_hash != image.sha256:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR provider output provenance is invalid")
            self._cache[cache_key] = artifact
            self._cache_misses += 1
        else:
            if not isinstance(cached, EphemeralOcrArtifact):
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision cache capability is invalid")
            artifact = cached
            self._cache_hits += 1
        invocation = self._invocation(
            descriptor,
            image=image,
            prompt_sha256=prompt_sha256,
            cache_hit=cached is not None,
            provider_calls=provider_calls,
            output_hash=artifact.output_sha256,
        )
        artifact_seed = "|".join((*cache_key, artifact.output_sha256))
        return OcrResult(
            artifact, invocation, f"ocr_artifact_{hashlib.sha256(artifact_seed.encode('utf-8')).hexdigest()[:32]}"
        )

    def describe_vision(self, image: EphemeralDerivedArtifact, *, provider_id: str) -> VisionResult:
        _validate_ephemeral_image(self._paths, image, policy=self._policy)
        provider = self._provider(provider_id, capability="vision")
        descriptor = provider.descriptor
        prompt_sha256 = _prompt_sha256(descriptor, policy=self._policy)
        cache_key = self._cache_key(descriptor, input_hash=image.sha256, prompt_sha256=prompt_sha256)
        cached = self._cache.get(cache_key)
        provider_calls = 0
        if cached is None:
            provider_calls = self._budget.reserve(descriptor, image_bytes=image.size_bytes)
            artifact = provider.describe(image, policy=self._policy)  # type: ignore[union-attr]
            if artifact.source_image_hash != image.sha256:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision provider output provenance is invalid")
            self._cache[cache_key] = artifact
            self._cache_misses += 1
        else:
            if not isinstance(cached, EphemeralVisionArtifact):
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision cache capability is invalid")
            artifact = cached
            self._cache_hits += 1
        invocation = self._invocation(
            descriptor,
            image=image,
            prompt_sha256=prompt_sha256,
            cache_hit=cached is not None,
            provider_calls=provider_calls,
            output_hash=artifact.output_sha256,
        )
        artifact_seed = "|".join((*cache_key, artifact.output_sha256))
        return VisionResult(
            artifact,
            invocation,
            f"vision_artifact_{hashlib.sha256(artifact_seed.encode('utf-8')).hexdigest()[:32]}",
        )

    def close(self) -> None:
        self._cache.clear()
        self._invocations.clear()
        self._cache_hits = 0
        self._cache_misses = 0


class OcrVisionProcessor:
    """Create short-lived local-only OCR/Vision sessions and capability receipts."""

    def __init__(
        self,
        paths: RuntimePaths,
        providers: Sequence[OcrProvider | VisionProvider],
        *,
        policy: OcrVisionPolicy = OcrVisionPolicy(),
    ) -> None:
        indexed: dict[str, OcrProvider | VisionProvider] = {}
        for provider in providers:
            descriptor = provider.descriptor
            if descriptor.provider_id in indexed:
                _fail(ErrorCode.INVALID_INPUT, "OCR/Vision provider identifiers must be unique")
            indexed[descriptor.provider_id] = provider
        if not indexed:
            _fail(ErrorCode.INVALID_INPUT, "OCR/Vision requires at least one provider route")
        self.paths = paths
        self._providers = indexed
        self.policy = policy

    def capability_receipt(self) -> dict[str, object]:
        return {
            "cloud_provider_routes": 0,
            "providers": [self._providers[key].descriptor.safe_dict() for key in sorted(self._providers)],
            "policy": self.policy.safe_dict(),
        }

    @contextmanager
    def session(self) -> Iterator[OcrVisionSession]:
        session = OcrVisionSession(self.paths, self._providers, policy=self.policy)
        try:
            yield session
        finally:
            session.close()


@dataclass(frozen=True)
class OcrGoldCase:
    case_id: str
    stratum: Literal["clear", "low_resolution", "rotated", "subtitle", "watermark", "table", "no_text"]
    reference_text: str = field(repr=False, compare=False)
    predicted_text: str = field(repr=False, compare=False)
    text_order_correct: bool
    duplicate_spans: int
    synthetic: bool
    provider_failed: bool = False
    provider: ImageProviderDescriptor | None = field(default=None, repr=False, compare=False)
    input_hash: str | None = None
    prompt_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_token(self.case_id, label="OCR Gold Set case id")
        if (
            self.stratum not in _OCR_STRATA
            or not isinstance(self.reference_text, str)
            or not isinstance(self.predicted_text, str)
        ):
            _fail(ErrorCode.INVALID_INPUT, "OCR Gold Set case is invalid")
        if len(self.reference_text) > MAX_OCR_TEXT_CHARS or len(self.predicted_text) > MAX_OCR_TEXT_CHARS:
            _fail(ErrorCode.POLICY_BLOCKED, "OCR Gold Set text exceeds its policy")
        if (
            not isinstance(self.text_order_correct, bool)
            or not isinstance(self.duplicate_spans, int)
            or isinstance(self.duplicate_spans, bool)
        ):
            _fail(ErrorCode.INVALID_INPUT, "OCR Gold Set quality marker is invalid")
        if (
            not 0 <= self.duplicate_spans <= MAX_OCR_SPANS
            or not isinstance(self.synthetic, bool)
            or not isinstance(self.provider_failed, bool)
        ):
            _fail(ErrorCode.INVALID_INPUT, "OCR Gold Set quality marker is invalid")
        if self.stratum == "no_text" and self.reference_text.strip():
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR no-text Gold Set reference is invalid")
        provenance = (self.provider, self.input_hash, self.prompt_sha256)
        if any(value is None for value in provenance) and any(value is not None for value in provenance):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR Gold Set provenance is incomplete")
        if not self.synthetic:
            if self.provider is None or self.input_hash is None or self.prompt_sha256 is None:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR private Gold Set provenance is required")
            if self.provider.capability != "ocr" or self.provider.mode != "local":
                _fail(ErrorCode.POLICY_BLOCKED, "OCR private Gold Set provider is not authorized")
        if self.input_hash is not None and _SHA256.fullmatch(self.input_hash) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR Gold Set input hash is invalid")
        if self.prompt_sha256 is not None and _SHA256.fullmatch(self.prompt_sha256) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR Gold Set prompt hash is invalid")

    def safe_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "duplicate_spans": self.duplicate_spans,
            "input_hash": self.input_hash,
            "predicted_hash": hashlib.sha256(self.predicted_text.encode("utf-8")).hexdigest(),
            "prompt_sha256": self.prompt_sha256,
            "provider": None if self.provider is None else self.provider.safe_dict(),
            "provider_failed": self.provider_failed,
            "reference_hash": hashlib.sha256(self.reference_text.encode("utf-8")).hexdigest(),
            "stratum": self.stratum,
            "synthetic": self.synthetic,
            "text_order_correct": self.text_order_correct,
        }


@dataclass(frozen=True)
class PrivateOcrGoldDataset:
    dataset_id: str
    sha256: str
    cases: tuple[OcrGoldCase, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _safe_token(self.dataset_id, label="OCR Gold Set dataset id")
        if _SHA256.fullmatch(self.sha256) is None or not self.cases:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR private Gold Set is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {"case_count": len(self.cases), "dataset_id": self.dataset_id, "dataset_sha256": self.sha256}


def _ocr_gold_case_from_private_payload(value: object) -> OcrGoldCase:
    if not isinstance(value, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR private Gold Set case is invalid")
    expected = {
        "case_id",
        "duplicate_spans",
        "input_hash",
        "predicted_text",
        "prompt_sha256",
        "provider",
        "provider_failed",
        "reference_text",
        "stratum",
        "text_order_correct",
    }
    if set(value) != expected:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR private Gold Set case shape is invalid")
    try:
        return OcrGoldCase(
            case_id=value["case_id"],
            stratum=value["stratum"],
            reference_text=value["reference_text"],
            predicted_text=value["predicted_text"],
            text_order_correct=value["text_order_correct"],
            duplicate_spans=value["duplicate_spans"],
            synthetic=False,
            provider_failed=value["provider_failed"],
            provider=_descriptor_from_private_payload(value["provider"]),
            input_hash=value["input_hash"],
            prompt_sha256=value["prompt_sha256"],
        )
    except (TypeError, X2NRuntimeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "OCR private Gold Set case is invalid") from None


def _load_private_dataset_payload(
    paths: RuntimePaths,
    *,
    directory_name: str,
    dataset_id: str,
    schema_version: str,
) -> tuple[dict[str, object], str]:
    safe_dataset_id = _safe_token(dataset_id, label="Gold Set dataset id")
    root = paths.data_root / "runtime/diagnostics" / directory_name
    _private_directory(root)
    dataset_path = _private_child(root, f"{safe_dataset_id}.json")
    _private_regular_file(dataset_path, maximum_bytes=MAX_GOLD_DATASET_BYTES, suffix=".json")
    digest, _ = _sha256_file(dataset_path, maximum_bytes=MAX_GOLD_DATASET_BYTES)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private Gold Set is invalid") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"cases", "dataset_id", "schema_version"}
        or payload.get("schema_version") != schema_version
        or payload.get("dataset_id") != safe_dataset_id
        or not isinstance(payload.get("cases"), list)
        or not 1 <= len(payload["cases"]) <= 500
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR/Vision private Gold Set shape is invalid")
    return payload, digest


def load_private_ocr_gold_dataset(paths: RuntimePaths, dataset_id: str) -> PrivateOcrGoldDataset:
    """Read one exact Owner-provisioned OCR Gold Set without copying its content."""

    payload, digest = _load_private_dataset_payload(
        paths,
        directory_name="ocr-gold",
        dataset_id=dataset_id,
        schema_version=OCR_GOLD_DATASET_SCHEMA,
    )
    return PrivateOcrGoldDataset(
        dataset_id=dataset_id,
        sha256=digest,
        cases=tuple(_ocr_gold_case_from_private_payload(value) for value in payload["cases"]),  # type: ignore[index]
    )


@dataclass(frozen=True)
class OcrStratumReport:
    stratum: str
    cases: int
    median_cer: float | None

    def safe_dict(self) -> dict[str, float | int | str | None]:
        return {"cases": self.cases, "median_cer": self.median_cer, "stratum": self.stratum}


@dataclass(frozen=True)
class OcrEvaluationReport:
    scope: Literal["ci_synth_contract_only", "private_gold"]
    evaluated_cases: int
    clear_cases: int
    clear_median_cer: float | None
    stratum_reports: tuple[OcrStratumReport, ...]
    no_text_hallucinations: int
    text_order_failures: int
    duplicate_spans: int
    provider_failures: int
    provenance_complete_cases: int
    status: Literal["pass", "low_quality", "not_run"]

    def safe_dict(self) -> dict[str, object]:
        return {
            "clear_cases": self.clear_cases,
            "clear_median_cer": self.clear_median_cer,
            "duplicate_spans": self.duplicate_spans,
            "evaluated_cases": self.evaluated_cases,
            "no_text_hallucinations": self.no_text_hallucinations,
            "provider_failures": self.provider_failures,
            "provenance_complete_cases": self.provenance_complete_cases,
            "scope": self.scope,
            "status": self.status,
            "strata": [item.safe_dict() for item in self.stratum_reports],
            "text_order_failures": self.text_order_failures,
        }


class OcrEvaluator:
    """CER/order/duplicate evaluator that does not elevate synthetic data to a quality claim."""

    def __init__(self, *, policy: OcrVisionPolicy = OcrVisionPolicy()) -> None:
        self.policy = policy

    def evaluate(self, cases: Sequence[OcrGoldCase], *, private_gold: bool) -> OcrEvaluationReport:
        if not cases or len(cases) > 500:
            _fail(ErrorCode.INVALID_INPUT, "OCR evaluation case count is invalid")
        if private_gold and any(case.synthetic for case in cases):
            _fail(ErrorCode.POLICY_BLOCKED, "OCR private Gold Set cannot contain synthetic cases")
        strata = {case.stratum for case in cases}
        clear = [case for case in cases if case.stratum == "clear"]
        if private_gold:
            if len(cases) < 50 or len(clear) < 20 or not _OCR_STRATA.issubset(strata):
                _fail(ErrorCode.POLICY_BLOCKED, "OCR private Gold Set is not sufficiently stratified")
        reports: list[OcrStratumReport] = []
        for stratum in sorted(strata):
            group = [case for case in cases if case.stratum == stratum]
            rates = [character_error_rate(case.reference_text, case.predicted_text) for case in group]
            reports.append(OcrStratumReport(stratum, len(group), _median(rates) if rates else None))
        clear_rates = [character_error_rate(case.reference_text, case.predicted_text) for case in clear]
        clear_median = _median(clear_rates) if clear_rates else None
        no_text_hallucinations = sum(
            bool(normalize_for_cer(case.predicted_text))
            for case in cases
            if case.stratum == "no_text" and not case.provider_failed
        )
        order_failures = sum(not case.text_order_correct for case in cases if not case.provider_failed)
        duplicates = sum(case.duplicate_spans for case in cases)
        failures = sum(case.provider_failed for case in cases)
        provenance_complete = sum(
            case.provider is not None and case.input_hash is not None and case.prompt_sha256 is not None
            for case in cases
        )
        if private_gold and provenance_complete != len(cases):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "OCR private Gold Set provenance is incomplete")
        if not private_gold:
            scope: Literal["ci_synth_contract_only", "private_gold"] = "ci_synth_contract_only"
            status: Literal["pass", "low_quality", "not_run"] = "not_run"
        else:
            scope = "private_gold"
            status = (
                "pass"
                if clear_median is not None
                and clear_median <= 0.12
                and no_text_hallucinations == 0
                and order_failures == 0
                and duplicates == 0
                and failures == 0
                else "low_quality"
            )
        return OcrEvaluationReport(
            scope,
            len(cases),
            len(clear),
            clear_median,
            tuple(reports),
            no_text_hallucinations,
            order_failures,
            duplicates,
            failures,
            provenance_complete,
            status,
        )


@dataclass(frozen=True)
class VisionGoldCase:
    case_id: str
    stratum: Literal[
        "image_post", "product_interface", "chart", "scene_change", "irrelevant_frame", "sensitive", "unsupported"
    ]
    expected_status: Literal["described", "unsupported_sensitive", "unsupported_content"]
    actual_status: Literal["described", "unsupported_sensitive", "unsupported_content"]
    human_rating: int
    major_visible_content_correct: bool
    material_hallucination: bool
    sensitive_attribute_inference: bool
    reviewer_count: int
    reviewer_disagreement: bool
    synthetic: bool
    provider_failed: bool = False
    provider: ImageProviderDescriptor | None = field(default=None, repr=False, compare=False)
    input_hash: str | None = None
    prompt_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_token(self.case_id, label="Vision Gold Set case id")
        if (
            self.stratum not in _VISION_STRATA
            or self.expected_status not in _VISION_STATUSES
            or self.actual_status not in _VISION_STATUSES
        ):
            _fail(ErrorCode.INVALID_INPUT, "Vision Gold Set case is invalid")
        if self.stratum == "sensitive" and self.expected_status != "unsupported_sensitive":
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision sensitive Gold Set expectation is invalid")
        if self.stratum == "unsupported" and self.expected_status != "unsupported_content":
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision unsupported Gold Set expectation is invalid")
        if self.stratum not in {"sensitive", "unsupported"} and self.expected_status != "described":
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision normal Gold Set expectation is invalid")
        if (
            isinstance(self.human_rating, bool)
            or not isinstance(self.human_rating, int)
            or not 1 <= self.human_rating <= 5
        ):
            _fail(ErrorCode.INVALID_INPUT, "Vision human rating is invalid")
        flags = (
            self.major_visible_content_correct,
            self.material_hallucination,
            self.sensitive_attribute_inference,
            self.reviewer_disagreement,
            self.synthetic,
            self.provider_failed,
        )
        if not all(isinstance(value, bool) for value in flags):
            _fail(ErrorCode.INVALID_INPUT, "Vision Gold Set marker is invalid")
        if (
            isinstance(self.reviewer_count, bool)
            or not isinstance(self.reviewer_count, int)
            or not 1 <= self.reviewer_count <= 3
        ):
            _fail(ErrorCode.INVALID_INPUT, "Vision reviewer count is invalid")
        provenance = (self.provider, self.input_hash, self.prompt_sha256)
        if any(value is None for value in provenance) and any(value is not None for value in provenance):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision Gold Set provenance is incomplete")
        if not self.synthetic:
            if self.provider is None or self.input_hash is None or self.prompt_sha256 is None:
                _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision private Gold Set provenance is required")
            if self.provider.capability != "vision" or self.provider.mode != "local":
                _fail(ErrorCode.POLICY_BLOCKED, "Vision private Gold Set provider is not authorized")
        if self.input_hash is not None and _SHA256.fullmatch(self.input_hash) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision Gold Set input hash is invalid")
        if self.prompt_sha256 is not None and _SHA256.fullmatch(self.prompt_sha256) is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision Gold Set prompt hash is invalid")

    def safe_dict(self) -> dict[str, object]:
        return {
            "actual_status": self.actual_status,
            "case_id": self.case_id,
            "expected_status": self.expected_status,
            "human_rating": self.human_rating,
            "input_hash": self.input_hash,
            "major_visible_content_correct": self.major_visible_content_correct,
            "material_hallucination": self.material_hallucination,
            "prompt_sha256": self.prompt_sha256,
            "provider": None if self.provider is None else self.provider.safe_dict(),
            "provider_failed": self.provider_failed,
            "reviewer_count": self.reviewer_count,
            "reviewer_disagreement": self.reviewer_disagreement,
            "sensitive_attribute_inference": self.sensitive_attribute_inference,
            "stratum": self.stratum,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True)
class PrivateVisionGoldDataset:
    dataset_id: str
    sha256: str
    cases: tuple[VisionGoldCase, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _safe_token(self.dataset_id, label="Vision Gold Set dataset id")
        if _SHA256.fullmatch(self.sha256) is None or not self.cases:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision private Gold Set is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {"case_count": len(self.cases), "dataset_id": self.dataset_id, "dataset_sha256": self.sha256}


def _vision_gold_case_from_private_payload(value: object) -> VisionGoldCase:
    if not isinstance(value, dict):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision private Gold Set case is invalid")
    expected = {
        "actual_status",
        "case_id",
        "expected_status",
        "human_rating",
        "input_hash",
        "major_visible_content_correct",
        "material_hallucination",
        "prompt_sha256",
        "provider",
        "provider_failed",
        "reviewer_count",
        "reviewer_disagreement",
        "sensitive_attribute_inference",
        "stratum",
    }
    if set(value) != expected:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision private Gold Set case shape is invalid")
    try:
        return VisionGoldCase(
            case_id=value["case_id"],
            stratum=value["stratum"],
            expected_status=value["expected_status"],
            actual_status=value["actual_status"],
            human_rating=value["human_rating"],
            major_visible_content_correct=value["major_visible_content_correct"],
            material_hallucination=value["material_hallucination"],
            sensitive_attribute_inference=value["sensitive_attribute_inference"],
            reviewer_count=value["reviewer_count"],
            reviewer_disagreement=value["reviewer_disagreement"],
            synthetic=False,
            provider_failed=value["provider_failed"],
            provider=_descriptor_from_private_payload(value["provider"]),
            input_hash=value["input_hash"],
            prompt_sha256=value["prompt_sha256"],
        )
    except (TypeError, X2NRuntimeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Vision private Gold Set case is invalid") from None


def load_private_vision_gold_dataset(paths: RuntimePaths, dataset_id: str) -> PrivateVisionGoldDataset:
    """Read one exact Owner-provisioned Vision Gold Set without copying its content."""

    payload, digest = _load_private_dataset_payload(
        paths,
        directory_name="vision-gold",
        dataset_id=dataset_id,
        schema_version=VISION_GOLD_DATASET_SCHEMA,
    )
    return PrivateVisionGoldDataset(
        dataset_id=dataset_id,
        sha256=digest,
        cases=tuple(_vision_gold_case_from_private_payload(value) for value in payload["cases"]),  # type: ignore[index]
    )


@dataclass(frozen=True)
class VisionEvaluationReport:
    scope: Literal["ci_synth_contract_only", "private_gold"]
    evaluated_cases: int
    described_cases: int
    qualifying_cases: int
    qualifying_rate: float | None
    material_hallucinations: int
    sensitive_attribute_inferences: int
    expected_structured_refusals: int
    structured_refusals_returned: int
    reviewer_disagreements: int
    provider_failures: int
    provenance_complete_cases: int
    status: Literal["pass", "low_quality", "not_run"]

    def safe_dict(self) -> dict[str, float | int | str | None]:
        return {
            "described_cases": self.described_cases,
            "evaluated_cases": self.evaluated_cases,
            "expected_structured_refusals": self.expected_structured_refusals,
            "material_hallucinations": self.material_hallucinations,
            "provenance_complete_cases": self.provenance_complete_cases,
            "provider_failures": self.provider_failures,
            "qualifying_cases": self.qualifying_cases,
            "qualifying_rate": self.qualifying_rate,
            "reviewer_disagreements": self.reviewer_disagreements,
            "scope": self.scope,
            "sensitive_attribute_inferences": self.sensitive_attribute_inferences,
            "status": self.status,
            "structured_refusals_returned": self.structured_refusals_returned,
        }


class VisionEvaluator:
    """Human-rubric evaluator; human adjudication values are the only quality oracle."""

    def evaluate(self, cases: Sequence[VisionGoldCase], *, private_gold: bool) -> VisionEvaluationReport:
        if not cases or len(cases) > 500:
            _fail(ErrorCode.INVALID_INPUT, "Vision evaluation case count is invalid")
        if private_gold and any(case.synthetic for case in cases):
            _fail(ErrorCode.POLICY_BLOCKED, "Vision private Gold Set cannot contain synthetic cases")
        if private_gold:
            strata = {case.stratum for case in cases}
            if (
                len(cases) < 40
                or not {"sensitive", "unsupported"}.issubset(strata)
                or any(case.reviewer_count < 2 for case in cases)
            ):
                _fail(ErrorCode.POLICY_BLOCKED, "Vision private Gold Set lacks representative human review")
        described = [case for case in cases if case.expected_status == "described"]
        qualifying = [
            case
            for case in described
            if case.actual_status == "described"
            and case.human_rating >= 4
            and case.major_visible_content_correct
            and not case.material_hallucination
            and not case.sensitive_attribute_inference
            and not case.provider_failed
        ]
        qualifying_rate = None if not described else len(qualifying) / len(described)
        hallucinations = sum(case.material_hallucination for case in cases)
        sensitive = sum(case.sensitive_attribute_inference for case in cases)
        expected_refusals = [case for case in cases if case.expected_status != "described"]
        structured = sum(case.actual_status == case.expected_status for case in expected_refusals)
        disagreements = sum(case.reviewer_disagreement for case in cases)
        failures = sum(case.provider_failed for case in cases)
        provenance_complete = sum(
            case.provider is not None and case.input_hash is not None and case.prompt_sha256 is not None
            for case in cases
        )
        if private_gold and provenance_complete != len(cases):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Vision private Gold Set provenance is incomplete")
        if not private_gold:
            scope: Literal["ci_synth_contract_only", "private_gold"] = "ci_synth_contract_only"
            status: Literal["pass", "low_quality", "not_run"] = "not_run"
        else:
            scope = "private_gold"
            status = (
                "pass"
                if qualifying_rate is not None
                and qualifying_rate >= 0.80
                and hallucinations == 0
                and sensitive == 0
                and structured == len(expected_refusals)
                and failures == 0
                else "low_quality"
            )
        return VisionEvaluationReport(
            scope,
            len(cases),
            len(described),
            len(qualifying),
            qualifying_rate,
            hallucinations,
            sensitive,
            len(expected_refusals),
            structured,
            disagreements,
            failures,
            provenance_complete,
            status,
        )
