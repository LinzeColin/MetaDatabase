"""Fail-closed media URL, temporary lease, cleanup, and persistence scanner.

Raw source URLs are deliberately confined to local variables and the
non-serializable ``EphemeralMediaSource``.  Public receipts contain only
opaque identifiers, counts, hashes, stable codes, and policy versions.
"""

from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import math
import os
import re
import sqlite3
import stat
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote, urljoin, urlsplit

from x2n_contracts import ErrorCode
from x2n_contracts.base import validate_canonical_page_url

from .canonical_store import CanonicalStore, MEDIA_LEASE_ID, MEDIA_TIMESTAMP, MediaLeaseRecord
from .runtime import RuntimePaths, X2NRuntimeError


TASK_ID = "TSK.x2n.skeleton.003"
PATTERN_SET_VERSION = "x2n-media-zero-v1"
MAX_MEDIA_LEASE_SECONDS = 24 * 60 * 60
_MAX_URL_BYTES = 2_048
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SENSITIVE_QUERY_KEYS = (
    "xsec_token",
    "xsec_source",
    "signature",
    "sign",
    "auth_key",
    "expires",
    "tracking_id",
    "track_id",
)

# Exact host/suffix policy.  A marker occurring elsewhere in a hostname does
# not grant access.
PLATFORM_CDN_SUFFIXES: dict[str, tuple[str, ...]] = {
    "xiaohongshu": ("xhscdn.com",),
    "douyin": ("douyinvod.com", "byteimg.com", "pstatp.com"),
    "bilibili": ("bilivideo.com", "hdslb.com"),
    "kuaishou": ("kscdn.com", "yximgs.com"),
    "weibo": ("sinaimg.cn",),
    "taobao": ("alicdn.com", "tbcdn.cn"),
}

_MEDIA_HOST_MARKERS = tuple(
    sorted({suffix.split(".", 1)[0] for suffixes in PLATFORM_CDN_SUFFIXES.values() for suffix in suffixes})
)
_CDN_URL_PATTERN = re.compile(
    rb"https?://[^\s<>\"']{0,2048}(?:" + b"|".join(re.escape(item.encode("ascii")) for item in _MEDIA_HOST_MARKERS) + rb")[^\s<>\"']*",
    flags=re.IGNORECASE,
)
_SENSITIVE_QUERY_PATTERN = re.compile(
    rb"(?:[?&]|\b)(?:" + b"|".join(re.escape(item.encode("ascii")) for item in _SENSITIVE_QUERY_KEYS) + rb")=",
    flags=re.IGNORECASE,
)
_CANONICAL_QUERY_PATTERN = re.compile(
    rb"https?://(?:[a-z0-9-]+\.)?(?:xiaohongshu\.com|douyin\.com|bilibili\.com|kuaishou\.com|weibo\.com|taobao\.com)/[^\s<>\"']*[?#]",
    flags=re.IGNORECASE,
)
_SCAN_PATTERNS = {
    "canonical_query_or_fragment": _CANONICAL_QUERY_PATTERN,
    "platform_media_url": _CDN_URL_PATTERN,
    "sensitive_query": _SENSITIVE_QUERY_PATTERN,
}


def _fail(code: ErrorCode, message: str) -> None:
    raise X2NRuntimeError(code, message)


def _safe_token(value: str, *, label: str) -> str:
    if _SAFE_TOKEN.fullmatch(value) is None:
        _fail(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    return value


def _decoded_path_is_safe(path: str) -> bool:
    decoded = path
    for _ in range(3):
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    if "\\" in decoded or "\x00" in decoded or any(ord(character) < 0x20 for character in decoded):
        return False
    return not any(segment in {".", ".."} for segment in decoded.split("/"))


def canonicalize_persistable_page_url(raw_url: str, platform: str) -> str:
    """Strip query/fragment and return a strict, persistable canonical page URL."""

    if not isinstance(raw_url, str) or len(raw_url.encode("utf-8", errors="ignore")) > _MAX_URL_BYTES:
        _fail(ErrorCode.URL_REJECTED, "Content page address was rejected")
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except (TypeError, ValueError):
        _fail(ErrorCode.URL_REJECTED, "Content page address was rejected")
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not path.startswith("/")
        or not _decoded_path_is_safe(path)
    ):
        _fail(ErrorCode.URL_REJECTED, "Content page address was rejected")
    candidate = f"https://{host}{path}"
    try:
        return validate_canonical_page_url(candidate, platform)
    except ValueError:
        _fail(ErrorCode.URL_REJECTED, "Content page address was rejected")


class EphemeralMediaSource:
    """Process-memory-only media input whose representation is always redacted."""

    __slots__ = ("__platform", "__raw_url", "__source_ref_id")

    def __init__(self, *, platform: str, raw_url: str, source_ref_id: str) -> None:
        if platform not in PLATFORM_CDN_SUFFIXES:
            _fail(ErrorCode.INVALID_INPUT, "Media platform is unsupported")
        _safe_token(source_ref_id, label="source_ref_id")
        if not isinstance(raw_url, str) or not raw_url:
            _fail(ErrorCode.INVALID_INPUT, "Ephemeral media source is invalid")
        self.__platform = platform
        self.__raw_url = raw_url
        self.__source_ref_id = source_ref_id

    @property
    def platform(self) -> str:
        return self.__platform

    @property
    def source_ref_id(self) -> str:
        return self.__source_ref_id

    def _url_for_single_process_use(self) -> str:
        return self.__raw_url

    def safe_dict(self) -> dict[str, str | bool]:
        return {
            "platform": self.__platform,
            "raw_url_present": True,
            "source_ref_id": self.__source_ref_id,
            "url_persistable": False,
        }

    def __repr__(self) -> str:
        return f"EphemeralMediaSource(platform={self.__platform!r}, source_ref_id={self.__source_ref_id!r}, raw_url=<redacted>)"

    def __str__(self) -> str:
        return repr(self)

    def __getstate__(self) -> None:
        raise TypeError("Ephemeral media sources cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Ephemeral media sources cannot be serialized")


class ValidatedMediaTarget:
    """Transport input pinned to the address validated by the URL firewall."""

    __slots__ = ("__hostname", "__path", "__pinned_ip", "__platform", "__port", "__query")

    def __init__(
        self,
        *,
        platform: str,
        hostname: str,
        pinned_ip: str,
        port: int = 443,
        path: str = "/",
        query: str = "",
    ) -> None:
        self.__platform = platform
        self.__hostname = hostname
        self.__pinned_ip = pinned_ip
        self.__port = port
        self.__path = path
        self.__query = query

    @property
    def platform(self) -> str:
        return self.__platform

    @property
    def hostname(self) -> str:
        return self.__hostname

    @property
    def pinned_ip(self) -> str:
        return self.__pinned_ip

    @property
    def port(self) -> int:
        return self.__port

    @property
    def request_target(self) -> str:
        return self.__path + (f"?{self.__query}" if self.__query else "")

    def safe_dict(self) -> dict[str, str | int | bool]:
        return {
            "hostname_allowlisted": True,
            "ip_class": "global",
            "platform": self.__platform,
            "port": self.__port,
            "request_target_redacted": True,
            "tls_hostname": self.__hostname,
        }

    def __repr__(self) -> str:
        return (
            f"ValidatedMediaTarget(platform={self.__platform!r}, hostname={self.__hostname!r}, "
            f"pinned_ip={self.__pinned_ip!r}, port={self.__port!r}, request_target=<redacted>)"
        )

    def __getstate__(self) -> None:
        raise TypeError("Validated media targets cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        del protocol
        raise TypeError("Validated media targets cannot be serialized")


class MediaResponse(Protocol):
    status: int
    headers: Mapping[str, str]

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]: ...

    def close(self) -> None: ...


class MediaTransport(Protocol):
    def request(self, target: ValidatedMediaTarget, *, timeout_seconds: float) -> MediaResponse: ...


class MediaInspector(Protocol):
    def inspect(self, path: Path, *, mime: str, timeout_seconds: float) -> "MediaMetadata": ...


Resolver = Callable[[str, int], Sequence[str]]


@dataclass(frozen=True)
class MediaLimits:
    max_bytes: int = 64 * 1024 * 1024
    max_duration_seconds: float = 7_200.0
    max_width: int = 16_384
    max_height: int = 16_384
    max_decoded_pixels: int = 100_000_000
    max_redirects: int = 3
    deadline_seconds: float = 60.0
    stream_chunk_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        if (
            self.max_bytes < 1
            or self.max_duration_seconds <= 0
            or self.max_width < 1
            or self.max_height < 1
            or self.max_decoded_pixels < 1
            or not 0 <= self.max_redirects <= 10
            or self.deadline_seconds <= 0
            or not 1 <= self.stream_chunk_bytes <= 4 * 1024 * 1024
        ):
            _fail(ErrorCode.INVALID_INPUT, "Media limits are invalid")


@dataclass(frozen=True)
class MediaMetadata:
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    decoded_pixels: int | None = None


@dataclass(frozen=True)
class DownloadedMedia:
    content_hash: str
    mime: str
    size_bytes: int
    metadata: MediaMetadata
    local_path: Path = field(repr=False)

    def safe_dict(self) -> dict[str, str | int | float | None | bool]:
        return {
            "content_hash": self.content_hash,
            "duration_seconds": self.metadata.duration_seconds,
            "local_path_emitted": False,
            "mime": self.mime,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class CleanupReport:
    examined_leases: int
    deleted_files: int
    missing_files: int
    orphan_files_deleted: int
    active_lease_misdeletes: int
    high_priority_errors: int

    @property
    def status(self) -> str:
        return "PASS" if self.high_priority_errors == 0 and self.active_lease_misdeletes == 0 else "FAIL_CLOSED"

    def safe_dict(self) -> dict[str, str | int | bool]:
        return {
            "active_lease_misdeletes": self.active_lease_misdeletes,
            "deleted_files": self.deleted_files,
            "examined_leases": self.examined_leases,
            "high_priority_errors": self.high_priority_errors,
            "missing_files": self.missing_files,
            "orphan_files_deleted": self.orphan_files_deleted,
            "private_path_emitted": False,
            "status": self.status,
        }


@dataclass
class MediaLeaseHandle:
    lease_id: str
    source_ref_id: str
    content_hash: str
    mime: str
    size_bytes: int
    duration_seconds: float | None
    local_path: Path = field(repr=False)
    cleanup_report: CleanupReport | None = field(default=None, repr=False)

    def safe_dict(self) -> dict[str, str | int | float | None | bool]:
        return {
            "content_hash": self.content_hash,
            "duration_seconds": self.duration_seconds,
            "lease_id": self.lease_id,
            "local_path_emitted": False,
            "mime": self.mime,
            "raw_url_persisted": False,
            "size_bytes": self.size_bytes,
            "source_ref_id": self.source_ref_id,
        }


@dataclass(frozen=True)
class CdnScanReport:
    scopes: tuple[str, ...]
    scanned_files: int
    scanned_bytes: int
    findings: dict[str, int]
    canonical_rows_checked: int

    @property
    def total_findings(self) -> int:
        return sum(self.findings.values())

    @property
    def status(self) -> str:
        return "PASS" if self.total_findings == 0 else "FAIL_CLOSED"

    def safe_dict(self) -> dict[str, object]:
        return {
            "canonical_rows_checked": self.canonical_rows_checked,
            "findings": dict(sorted(self.findings.items())),
            "matched_values_emitted": False,
            "pattern_set_version": PATTERN_SET_VERSION,
            "private_path_emitted": False,
            "scanned_bytes": self.scanned_bytes,
            "scanned_files": self.scanned_files,
            "scopes": list(self.scopes),
            "status": self.status,
            "total_findings": self.total_findings,
        }


def _allowlisted_host(platform: str, hostname: str) -> bool:
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in PLATFORM_CDN_SUFFIXES[platform])


def _global_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if not isinstance(value, str) or "%" in value:
        _fail(ErrorCode.URL_REJECTED, "Media target address was rejected")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _fail(ErrorCode.URL_REJECTED, "Media target address was rejected")
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        _fail(ErrorCode.URL_REJECTED, "Media target address was rejected")
    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        _fail(ErrorCode.URL_REJECTED, "Media target address was rejected")
    return address


def validate_media_target(raw_url: str, *, platform: str, resolver: Resolver) -> ValidatedMediaTarget:
    """Validate authority/path and pin a globally routable DNS result."""

    if platform not in PLATFORM_CDN_SUFFIXES:
        _fail(ErrorCode.INVALID_INPUT, "Media platform is unsupported")
    if not isinstance(raw_url, str) or len(raw_url.encode("utf-8", errors="ignore")) > _MAX_URL_BYTES:
        _fail(ErrorCode.URL_REJECTED, "Media source address was rejected")
    if "\\" in raw_url or "\x00" in raw_url or any(ord(character) < 0x20 for character in raw_url):
        _fail(ErrorCode.URL_REJECTED, "Media source address was rejected")
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except (TypeError, ValueError):
        _fail(ErrorCode.URL_REJECTED, "Media source address was rejected")
    hostname = (parsed.hostname or "").lower()
    try:
        hostname.encode("ascii")
    except UnicodeEncodeError:
        _fail(ErrorCode.URL_REJECTED, "Media source address was rejected")
    if (
        parsed.scheme != "https"
        or not hostname
        or hostname.endswith(".")
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
        or not parsed.path.startswith("/")
        or not _decoded_path_is_safe(parsed.path)
        or not _allowlisted_host(platform, hostname)
    ):
        _fail(ErrorCode.URL_REJECTED, "Media source address was rejected")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        _fail(ErrorCode.URL_REJECTED, "Media source address was rejected")
    try:
        resolved = tuple(resolver(hostname, 443))
    except Exception:
        raise X2NRuntimeError(ErrorCode.NETWORK_FAILED, "Media target resolution failed closed") from None
    if not resolved or len(resolved) > 32:
        _fail(ErrorCode.URL_REJECTED, "Media target address was rejected")
    addresses = {_global_ip(value) for value in resolved}
    pinned = sorted(addresses, key=lambda item: (item.version, int(item)))[0]
    return ValidatedMediaTarget(
        platform=platform,
        hostname=hostname,
        pinned_ip=str(pinned),
        path=parsed.path,
        query=parsed.query,
    )


def _headers(value: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    try:
        items = value.items()
    except AttributeError:
        _fail(ErrorCode.NETWORK_FAILED, "Media response headers were rejected")
    for key, item in items:
        if not isinstance(key, str) or not isinstance(item, str) or "\r" in item or "\n" in item:
            _fail(ErrorCode.NETWORK_FAILED, "Media response headers were rejected")
        normalized[key.lower()] = item.strip()
    return normalized


def _close_response(response: MediaResponse) -> None:
    try:
        response.close()
    except Exception:
        # A close failure must never expose transport internals or mask the
        # stable fail-closed error already being handled.
        pass


def _unlink_ephemeral(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media cleanup failed closed") from None


def _declared_mime(headers: Mapping[str, str]) -> str:
    encoding = headers.get("content-encoding", "identity").lower()
    if encoding not in {"", "identity"}:
        _fail(ErrorCode.POLICY_BLOCKED, "Encoded media responses are not accepted")
    mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    allowed = {
        "audio/mp4",
        "audio/mpeg",
        "image/jpeg",
        "image/png",
        "image/webp",
        "video/mp4",
        "video/webm",
    }
    if mime not in allowed:
        _fail(ErrorCode.POLICY_BLOCKED, "Media MIME is not allowlisted")
    return mime


def _declared_length(headers: Mapping[str, str], *, maximum: int) -> int | None:
    raw = headers.get("content-length")
    if raw is None:
        return None
    if re.fullmatch(r"[0-9]{1,20}", raw) is None:
        _fail(ErrorCode.NETWORK_FAILED, "Media length header was rejected")
    value = int(raw)
    if value > maximum:
        _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the byte limit")
    return value


def _sniffed_mimes(header: bytes) -> frozenset[str]:
    if header.startswith(b"\xff\xd8\xff"):
        return frozenset({"image/jpeg"})
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return frozenset({"image/png"})
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return frozenset({"image/webp"})
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return frozenset({"audio/mp4", "video/mp4"})
    if header.startswith(b"\x1aE\xdf\xa3"):
        return frozenset({"video/webm"})
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        return frozenset({"audio/mpeg"})
    return frozenset()


def _validate_metadata(metadata: MediaMetadata, limits: MediaLimits) -> None:
    numeric = (metadata.duration_seconds, metadata.width, metadata.height, metadata.decoded_pixels)
    if any(
        value is not None
        and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        )
        for value in numeric
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media metadata was rejected")
    if any(
        value is not None and not isinstance(value, int)
        for value in (metadata.width, metadata.height, metadata.decoded_pixels)
    ):
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media dimensions were rejected")
    if metadata.duration_seconds is not None and metadata.duration_seconds > limits.max_duration_seconds:
        _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the duration limit")
    if metadata.width is not None and metadata.width > limits.max_width:
        _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the dimension limit")
    if metadata.height is not None and metadata.height > limits.max_height:
        _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the dimension limit")
    if metadata.decoded_pixels is not None and metadata.decoded_pixels > limits.max_decoded_pixels:
        _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the decoded-pixel limit")
    if metadata.width is not None and metadata.height is not None:
        if metadata.width * metadata.height > limits.max_decoded_pixels:
            _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the decoded-pixel limit")


def download_media(
    source: EphemeralMediaSource,
    *,
    paths: RuntimePaths,
    destination: Path,
    resolver: Resolver,
    transport: MediaTransport,
    inspector: MediaInspector,
    limits: MediaLimits = MediaLimits(),
    monotonic: Callable[[], float] = time.monotonic,
) -> DownloadedMedia:
    """Stream a validated source into a caller-derived owner-only path."""

    try:
        destination.resolve(strict=False).relative_to(paths.temp_media_directory.resolve(strict=True))
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "Temporary media target escaped its private root")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media root is unavailable") from None
    current_url = source._url_for_single_process_use()
    response: MediaResponse | None = None
    headers: dict[str, str] = {}
    mime = ""
    started = monotonic()
    for redirect_count in range(limits.max_redirects + 1):
        target = validate_media_target(current_url, platform=source.platform, resolver=resolver)
        request_timeout = limits.deadline_seconds - (monotonic() - started)
        if request_timeout <= 0:
            _fail(ErrorCode.NETWORK_FAILED, "Media download deadline was exceeded")
        try:
            response = transport.request(target, timeout_seconds=request_timeout)
        except X2NRuntimeError:
            raise
        except Exception:
            raise X2NRuntimeError(ErrorCode.NETWORK_FAILED, "Media transport failed closed") from None
        redirect_url: str | None = None
        try:
            headers = _headers(response.headers)
            if response.status in _REDIRECT_STATUSES:
                location = headers.get("location")
                if not location or redirect_count >= limits.max_redirects:
                    _fail(ErrorCode.URL_REJECTED, "Media redirect was rejected")
                redirect_url = urljoin(current_url, location)
            elif response.status != 200:
                _fail(ErrorCode.NETWORK_FAILED, "Media response status was rejected")
            else:
                mime = _declared_mime(headers)
        except X2NRuntimeError:
            _close_response(response)
            response = None
            raise
        except Exception:
            _close_response(response)
            response = None
            raise X2NRuntimeError(ErrorCode.NETWORK_FAILED, "Media response was rejected") from None
        if redirect_url is not None:
            _close_response(response)
            response = None
            current_url = redirect_url
            continue
        break
    if response is None or not mime:
        _fail(ErrorCode.NETWORK_FAILED, "Media response was unavailable")

    try:
        declared_length = _declared_length(headers, maximum=limits.max_bytes)
    except X2NRuntimeError:
        _close_response(response)
        raise
    try:
        destination.parent.mkdir(mode=0o700, parents=False, exist_ok=True)
    except OSError:
        _close_response(response)
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media directory is unavailable") from None
    try:
        if destination.parent.is_symlink() or stat.S_IMODE(destination.parent.stat().st_mode) != 0o700:
            _fail(ErrorCode.POLICY_BLOCKED, "Temporary media directory is not owner-only")
        if destination.exists() or destination.is_symlink():
            _fail(ErrorCode.POLICY_BLOCKED, "Temporary media target already exists")
    except X2NRuntimeError:
        _close_response(response)
        raise
    except OSError:
        _close_response(response)
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media target is unavailable") from None
    partial = destination.with_suffix(destination.suffix + ".part")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    partial_created = False
    promoted = False
    completed = False
    digest = hashlib.sha256()
    size_bytes = 0
    header = bytearray()
    try:
        try:
            descriptor = os.open(partial, flags, 0o600)
            partial_created = True
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media file creation failed closed") from None
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            try:
                chunks = response.iter_bytes(limits.stream_chunk_bytes)
                for chunk in chunks:
                    if monotonic() - started > limits.deadline_seconds:
                        _fail(ErrorCode.NETWORK_FAILED, "Media download deadline was exceeded")
                    if not isinstance(chunk, bytes):
                        _fail(ErrorCode.NETWORK_FAILED, "Media stream yielded an invalid chunk")
                    if not chunk:
                        continue
                    if size_bytes + len(chunk) > limits.max_bytes:
                        _fail(ErrorCode.POLICY_BLOCKED, "Media exceeds the byte limit")
                    if len(header) < 64:
                        header.extend(chunk[: 64 - len(header)])
                    handle.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                if monotonic() - started > limits.deadline_seconds:
                    _fail(ErrorCode.NETWORK_FAILED, "Media download deadline was exceeded")
                handle.flush()
                os.fsync(handle.fileno())
            except X2NRuntimeError:
                raise
            except OSError:
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media write failed closed") from None
            except Exception:
                raise X2NRuntimeError(ErrorCode.NETWORK_FAILED, "Media stream failed closed") from None
        if size_bytes == 0 or (declared_length is not None and declared_length != size_bytes):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media response length did not match its body")
        if mime not in _sniffed_mimes(bytes(header)):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media MIME did not match its content")
        try:
            os.link(partial, destination, follow_symlinks=False)
            promoted = True
            _unlink_ephemeral(partial)
            partial_created = False
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media promotion failed closed") from None
        try:
            destination.chmod(0o600)
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media permissions failed closed") from None
        inspection_timeout = limits.deadline_seconds - (monotonic() - started)
        if inspection_timeout <= 0:
            _fail(ErrorCode.NETWORK_FAILED, "Media download deadline was exceeded")
        try:
            metadata = inspector.inspect(destination, mime=mime, timeout_seconds=inspection_timeout)
        except X2NRuntimeError:
            raise
        except Exception:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Media inspection failed closed") from None
        if not isinstance(metadata, MediaMetadata):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media inspection returned an invalid result")
        _validate_metadata(metadata, limits)
        result = DownloadedMedia(
            content_hash=digest.hexdigest(),
            mime=mime,
            size_bytes=size_bytes,
            metadata=metadata,
            local_path=destination,
        )
        completed = True
        return result
    finally:
        _close_response(response)
        cleanup_failed = False
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                cleanup_failed = True
        if partial_created:
            try:
                _unlink_ephemeral(partial)
            except X2NRuntimeError:
                cleanup_failed = True
        if promoted and not completed:
            try:
                _unlink_ephemeral(destination)
            except X2NRuntimeError:
                cleanup_failed = True
        if cleanup_failed:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media cleanup failed closed") from None


@contextmanager
def _media_lifecycle_lock(paths: RuntimePaths, *, exclusive: bool) -> Iterator[None]:
    directory = paths.temp_media_directory
    try:
        if directory.is_symlink() or not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
            _fail(ErrorCode.POLICY_BLOCKED, "Temporary media root is not owner-only")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media root is unavailable") from None
    lock_path = directory / ".media-lifecycle.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media lifecycle lock is unavailable") from None
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
    except OSError:
        os.close(descriptor)
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media lifecycle lock is unavailable") from None
    try:
        yield
    finally:
        cleanup_failed = False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            cleanup_failed = True
        try:
            os.close(descriptor)
        except OSError:
            cleanup_failed = True
        if cleanup_failed:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Media lifecycle unlock failed closed") from None


def _lease_path(paths: RuntimePaths, record: MediaLeaseRecord) -> Path:
    _safe_token(record.run_id, label="run_id")
    if MEDIA_LEASE_ID.fullmatch(record.lease_id) is None:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media lease identity invariant failed")
    expected = f"{record.run_id}/{record.lease_id}.bin"
    if record.local_relative_path != expected:
        _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media lease path invariant failed")
    candidate = paths.temp_media_directory / record.local_relative_path
    try:
        candidate.resolve(strict=False).relative_to(paths.temp_media_directory.resolve(strict=True))
    except ValueError:
        _fail(ErrorCode.POLICY_BLOCKED, "Media lease escaped its temporary root")
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media root is unavailable") from None
    return candidate


def _delete_lease_files(
    paths: RuntimePaths,
    record: MediaLeaseRecord,
    delete_file: Callable[[Path], None],
) -> tuple[int, int, int]:
    path = _lease_path(paths, record)
    deleted = 0
    found = False
    try:
        for candidate in (path, path.with_suffix(path.suffix + ".part")):
            if candidate.is_symlink():
                _fail(ErrorCode.POLICY_BLOCKED, "Temporary media file became a symbolic link")
            if candidate.exists():
                found = True
                delete_file(candidate)
                deleted += 1
        return deleted, 0 if found else 1, 0
    except Exception:
        return deleted, 0, 1


class MediaLeaseManager:
    """Acquire a bounded media file and delete it at context completion."""

    def __init__(
        self,
        paths: RuntimePaths,
        store: CanonicalStore,
        *,
        resolver: Resolver,
        transport: MediaTransport,
        inspector: MediaInspector,
        limits: MediaLimits = MediaLimits(),
        delete_file: Callable[[Path], None] | None = None,
    ) -> None:
        if store.paths != paths:
            _fail(ErrorCode.POLICY_BLOCKED, "Media Store and Runtime roots do not match")
        self.paths = paths
        self.store = store
        self.resolver = resolver
        self.transport = transport
        self.inspector = inspector
        self.limits = limits
        self.delete_file = delete_file or (lambda path: path.unlink())

    def _delete_registered(self, record: MediaLeaseRecord) -> CleanupReport:
        path = _lease_path(self.paths, record)
        deleted, missing, errors = _delete_lease_files(self.paths, record, self.delete_file)
        try:
            self.store.record_media_cleanup(
                record.lease_id,
                deleted=errors == 0,
                error_code=ErrorCode.STORAGE_FAILED.value if errors else None,
            )
        except Exception:
            errors = 1
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return CleanupReport(1, deleted, missing, 0, 0, errors)

    @contextmanager
    def lease(
        self,
        source: EphemeralMediaSource,
        *,
        run_id: str,
        content_key: str,
        purpose: str,
        ttl_seconds: int = MAX_MEDIA_LEASE_SECONDS,
        now: str | None = None,
    ) -> Iterator[MediaLeaseHandle]:
        _safe_token(run_id, label="run_id")
        _safe_token(purpose, label="purpose")
        if not 1 <= ttl_seconds <= MAX_MEDIA_LEASE_SECONDS:
            _fail(ErrorCode.POLICY_BLOCKED, "Media lease exceeds the retention policy")
        content_platform = self.store.content_platform(content_key)
        if content_platform is None:
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical content must exist before media acquisition")
        if content_platform != source.platform:
            _fail(ErrorCode.POLICY_BLOCKED, "Media source platform does not match canonical content")
        lease_id = f"media_{uuid.uuid4().hex}"
        handle: MediaLeaseHandle | None = None
        with _media_lifecycle_lock(self.paths, exclusive=False):
            run_directory = self.paths.temp_media_directory / run_id
            try:
                if run_directory.exists():
                    if run_directory.is_symlink() or not run_directory.is_dir():
                        _fail(ErrorCode.POLICY_BLOCKED, "Temporary media run directory is invalid")
                    if stat.S_IMODE(run_directory.stat().st_mode) != 0o700:
                        _fail(ErrorCode.POLICY_BLOCKED, "Temporary media run directory is not owner-only")
                else:
                    run_directory.mkdir(mode=0o700)
            except OSError:
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media run directory is unavailable") from None
            destination = run_directory / f"{lease_id}.bin"
            observed_at = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            self.store.reserve_media_lease(
                run_id=run_id,
                content_key=content_key,
                purpose=purpose,
                ttl_seconds=ttl_seconds,
                now=observed_at,
                lease_id=lease_id,
            )
            try:
                downloaded = download_media(
                    source,
                    paths=self.paths,
                    destination=destination,
                    resolver=self.resolver,
                    transport=self.transport,
                    inspector=self.inspector,
                    limits=self.limits,
                )
                self.store.finalize_media_lease(
                    lease_id,
                    content_hash=downloaded.content_hash,
                    mime=downloaded.mime,
                    size_bytes=downloaded.size_bytes,
                    duration_seconds=downloaded.metadata.duration_seconds,
                )
                handle = MediaLeaseHandle(
                    lease_id=lease_id,
                    source_ref_id=source.source_ref_id,
                    content_hash=downloaded.content_hash,
                    mime=downloaded.mime,
                    size_bytes=downloaded.size_bytes,
                    duration_seconds=downloaded.metadata.duration_seconds,
                    local_path=destination,
                )
            except BaseException:
                record = self.store.get_media_lease(lease_id)
                if record is None:
                    _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Reserved media lease disappeared during acquisition")
                report = self._delete_registered(record)
                if report.high_priority_errors:
                    raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Temporary media cleanup failed closed") from None
                raise
            try:
                assert handle is not None
                yield handle
            except BaseException:
                record = self.store.get_media_lease(lease_id)
                if record is not None:
                    handle.cleanup_report = self._delete_registered(record)
                raise
            else:
                record = self.store.get_media_lease(lease_id)
                if record is None:
                    _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Media lease disappeared during processing")
                handle.cleanup_report = self._delete_registered(record)
                if handle.cleanup_report.high_priority_errors:
                    _fail(ErrorCode.STORAGE_FAILED, "Temporary media cleanup failed closed")


class MediaLeaseCleaner:
    """Exclusive, idempotent cleanup for expired leases and 24-hour orphans."""

    def __init__(
        self,
        paths: RuntimePaths,
        store: CanonicalStore,
        *,
        delete_file: Callable[[Path], None] | None = None,
    ) -> None:
        if store.paths != paths:
            _fail(ErrorCode.POLICY_BLOCKED, "Media Store and Runtime roots do not match")
        self.paths = paths
        self.store = store
        self.delete_file = delete_file or (lambda path: path.unlink())

    def _delete_candidate(self, record: MediaLeaseRecord) -> tuple[int, int, int]:
        path = _lease_path(self.paths, record)
        deleted, missing, error = _delete_lease_files(self.paths, record, self.delete_file)
        try:
            self.store.record_media_cleanup(
                record.lease_id,
                deleted=error == 0,
                error_code=ErrorCode.STORAGE_FAILED.value if error else None,
            )
            try:
                path.parent.rmdir()
            except OSError:
                pass
            return deleted, missing, error
        except Exception:
            return deleted, missing, 1

    def _delete_old_orphans(self, *, cutoff_epoch: float, registered: set[str]) -> tuple[int, int]:
        deleted = 0
        errors = 0
        root = self.paths.temp_media_directory

        def record_walk_error(_error: OSError) -> None:
            nonlocal errors
            errors += 1

        for current, directory_names, file_names in os.walk(
            root,
            topdown=True,
            onerror=record_walk_error,
            followlinks=False,
        ):
            current_path = Path(current)
            safe_directories: list[str] = []
            for name in directory_names:
                candidate = current_path / name
                if candidate.is_symlink():
                    errors += 1
                else:
                    safe_directories.append(name)
            directory_names[:] = safe_directories
            for name in file_names:
                candidate = current_path / name
                if candidate == root / ".media-lifecycle.lock":
                    continue
                try:
                    relative = candidate.relative_to(root).as_posix()
                    if relative in registered:
                        continue
                    if candidate.is_symlink() or not candidate.is_file():
                        errors += 1
                        continue
                    if not (name.endswith(".bin") or name.endswith(".bin.part")):
                        errors += 1
                        continue
                    if candidate.stat().st_mtime > cutoff_epoch:
                        continue
                    self.delete_file(candidate)
                    deleted += 1
                except OSError:
                    errors += 1
        for current, directory_names, _ in os.walk(
            root,
            topdown=False,
            onerror=record_walk_error,
            followlinks=False,
        ):
            current_path = Path(current)
            if current_path == root:
                continue
            for name in directory_names:
                candidate = current_path / name
                if not candidate.is_symlink():
                    try:
                        candidate.rmdir()
                    except OSError:
                        pass
        return deleted, errors

    def run(self, *, now: str | None = None) -> CleanupReport:
        observed_at = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if not isinstance(observed_at, str) or MEDIA_TIMESTAMP.fullmatch(observed_at) is None:
            _fail(ErrorCode.INVALID_INPUT, "Cleanup time is invalid")
        try:
            parsed_now = datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            _fail(ErrorCode.INVALID_INPUT, "Cleanup time is invalid")
        with _media_lifecycle_lock(self.paths, exclusive=True):
            candidates = self.store.media_cleanup_candidates(now=observed_at)
            all_records = self.store.list_media_leases()
            registered = {
                relative_path
                for record in all_records
                if record.status != "deleted"
                for relative_path in (
                    record.local_relative_path,
                    record.local_relative_path + ".part",
                )
            }
            deleted = missing = errors = 0
            for record in candidates:
                one_deleted, one_missing, one_error = self._delete_candidate(record)
                deleted += one_deleted
                missing += one_missing
                errors += one_error
            orphan_deleted, orphan_errors = self._delete_old_orphans(
                cutoff_epoch=(parsed_now - timedelta(seconds=MAX_MEDIA_LEASE_SECONDS)).timestamp(),
                registered=registered,
            )
            errors += orphan_errors
        return CleanupReport(
            examined_leases=len(candidates),
            deleted_files=deleted,
            missing_files=missing,
            orphan_files_deleted=orphan_deleted,
            active_lease_misdeletes=0,
            high_priority_errors=errors,
        )


_SCOPE_RELATIVE_DIRECTORIES: dict[str, tuple[str, ...]] = {
    "artifacts": ("runtime/checkpoints", "runtime/models"),
    "db": ("runtime/canonical",),
    "logs": ("runtime/logs", "runtime/diagnostics"),
    "markdown": ("runtime/library",),
    "notion-export": ("runtime/provider_cache",),
}


def _scan_file(path: Path) -> tuple[int, dict[str, int]]:
    if path.is_symlink() or not path.is_file():
        _fail(ErrorCode.POLICY_BLOCKED, "Persistence scanner encountered an unsafe file")
    findings = {name: 0 for name in _SCAN_PATTERNS}
    scanned = 0
    overlap = b""
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                scanned += len(chunk)
                combined = overlap + chunk
                boundary = len(overlap)
                for name, pattern in _SCAN_PATTERNS.items():
                    findings[name] += sum(1 for match in pattern.finditer(combined) if match.end() > boundary)
                overlap = combined[-4096:]
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Persistence scanner could not read a sink") from None
    return scanned, findings


def _scope_files(paths: RuntimePaths, scope: str) -> Iterator[Path]:
    for relative in _SCOPE_RELATIVE_DIRECTORIES[scope]:
        root = paths.data_root / relative
        if root.is_symlink() or not root.is_dir():
            _fail(ErrorCode.POLICY_BLOCKED, "Persistence scanner scope is invalid")
        def fail_walk(_error: OSError) -> None:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Persistence scanner could not traverse a sink") from None

        for current, directory_names, file_names in os.walk(
            root,
            topdown=True,
            onerror=fail_walk,
            followlinks=False,
        ):
            current_path = Path(current)
            for name in directory_names:
                if (current_path / name).is_symlink():
                    _fail(ErrorCode.POLICY_BLOCKED, "Persistence scanner refuses symbolic links")
            for name in sorted(file_names):
                yield current_path / name


def _canonical_query_rows(database: Path) -> tuple[int, int]:
    if not database.exists():
        return 0, 0
    try:
        connection = sqlite3.connect(f"file:{quote(str(database))}?mode=ro", uri=True)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'content'"
            ).fetchone()
            if table is None:
                return 0, 0
            rows = connection.execute("SELECT canonical_source_url FROM content").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical URL scan failed closed") from None
    findings = 0
    for (value,) in rows:
        try:
            parsed = urlsplit(str(value))
        except ValueError:
            findings += 1
            continue
        if parsed.query or parsed.fragment:
            findings += 1
    return len(rows), findings


def scan_persisted_scopes(paths: RuntimePaths, scopes: Sequence[str]) -> CdnScanReport:
    """Scan fixed logical sinks without accepting caller-controlled paths."""

    normalized = tuple(sorted(set(scopes)))
    if not normalized or len(normalized) != len(scopes) or any(scope not in _SCOPE_RELATIVE_DIRECTORIES for scope in normalized):
        _fail(ErrorCode.INVALID_INPUT, "Persistence scanner scopes are invalid")
    findings = {name: 0 for name in _SCAN_PATTERNS}
    scanned_files = 0
    scanned_bytes = 0
    seen: set[Path] = set()
    for scope in normalized:
        for path in _scope_files(paths, scope):
            try:
                resolved = path.resolve(strict=False)
            except OSError:
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Persistence scanner could not resolve a sink") from None
            if resolved in seen:
                continue
            seen.add(resolved)
            byte_count, file_findings = _scan_file(path)
            scanned_files += 1
            scanned_bytes += byte_count
            for name, count in file_findings.items():
                findings[name] += count
    canonical_rows = 0
    if "db" in normalized:
        canonical_rows, canonical_findings = _canonical_query_rows(paths.database)
        findings["canonical_query_or_fragment"] += canonical_findings
    return CdnScanReport(
        scopes=normalized,
        scanned_files=scanned_files,
        scanned_bytes=scanned_bytes,
        findings=findings,
        canonical_rows_checked=canonical_rows,
    )
