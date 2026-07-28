"""Task005 durable lifecycle for the private x2n Canonical Store.

The module deliberately keeps two truths separate: SQLite is the active logical
truth, while only a verified, domain-bound Private-MetaDatabase archive makes a
snapshot durable.  Production client calls are digest-pinned and command
allowlisted; CI supplies a fake transport and never touches authentication or
the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform as os_platform
import re
import sqlite3
import stat
import subprocess
import sys
import tarfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from x2n_contracts import ErrorCode

from .canonical_store import CanonicalStore
from .markdown_sink import MarkdownSink
from .migrations import current_version
from .runtime import REQUIRED_DIRECTORIES, RuntimePaths, X2NRuntimeError, _atomic_private_json
from .sink_projection import build_sink_projection


TASK_ID = "TSK.x2n.uxops.005"
PRIVATE_AREA = "Private-MetaDatabase"
PRIVATE_DOMAIN = "xhs-douyin-2notion"
PRIVATE_CLIENT_ENV = "X2N_PRIVATE_DB_CLIENT"
TRUSTED_PRIVATE_CLIENT_SHA256 = "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa"
ARCHIVE_FORMAT = "x2n-private-archive-v1"
RESTORE_MANIFEST_FORMAT = "x2n-private-restore-manifest-v1"
ENVELOPE_FORMAT = "x2n-private-chunk-envelope-v1"
ARCHIVE_CHUNK_MAX_BYTES = 90 * 1024 * 1024
LIFECYCLE_DELETE_CONFIRMATION = "APPLY_LOCAL_LIFECYCLE_DELETE"
RUNTIME_WIPE_REQUEST_CONFIRMATION = "REQUEST_ACTIVE_RUNTIME_WIPE"
RUNTIME_WIPE_CONFIRMATION = "WIPE_VERIFIED_ACTIVE_RUNTIME"
PRIVATE_EXPORT_CONFIRMATION = "EXPORT_VERIFIED_PRIVATE_METADATABASE_ARCHIVE"
PRIVATE_RESTORE_CONFIRMATION = "RESTORE_LATEST_VERIFIED_PRIVATE_METADATABASE_ARCHIVE"
TIME_MACHINE_CONFIRMATION = "EXCLUDE_ENTIRE_X2N_DATA_ROOT_FROM_TIME_MACHINE"
_OPAQUE_NAME = re.compile(r"^x2n-[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_OBJECT_PATH = re.compile(r"^objects/[0-9a-f]{2}/[0-9a-f]{64}_x2n-[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_MANIFEST_NAME = re.compile(r"^x2n-lifecycle-manifest-[0-9a-f]{32}\.json$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SQLITE_HEADER = b"SQLite format 3\x00"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except (AttributeError, ValueError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle timestamp is invalid") from None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, f"{label} is invalid")
    return value


def _require_opaque_name(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _OPAQUE_NAME.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, f"{label} must be opaque")
    return value


def _expected_object_path(sha256: str, opaque_name: str) -> str:
    _require_sha256(sha256, label="object_sha256")
    _require_opaque_name(opaque_name, label="object_name")
    return f"objects/{sha256[:2]}/{sha256}_{opaque_name}"


def _private_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle private file is unsafe")


def _private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle private directory is unsafe")


def _write_private_bytes(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle output already exists")
    _private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle private output is unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _remove_private_tree(root: Path) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _private_directory(root)
    for child in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
        if child.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle temporary tree contains a symbolic link")
        if child.is_dir():
            _remove_private_tree(child)
        elif child.is_file():
            _private_regular_file(child)
            child.unlink()
        else:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle temporary tree contains an unsafe entry")
    root.rmdir()


@dataclass(frozen=True)
class LifecycleTtlPolicy:
    workspace_seconds: int = 60 * 60

    def __post_init__(self) -> None:
        if not 60 <= self.workspace_seconds <= 7 * 24 * 60 * 60:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle workspace TTL is invalid")


@dataclass(frozen=True)
class PrivateObject:
    object_sha256: str
    object_path: str
    opaque_name: str
    size_bytes: int

    def __post_init__(self) -> None:
        _require_sha256(self.object_sha256, label="private_object_sha256")
        _require_opaque_name(self.opaque_name, label="private_object_name")
        if self.object_path != _expected_object_path(self.object_sha256, self.opaque_name):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private object path is invalid")
        if not isinstance(self.size_bytes, int) or self.size_bytes < 1 or self.size_bytes > ARCHIVE_CHUNK_MAX_BYTES:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private object size is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {"object_sha256": self.object_sha256, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class ArchiveChunk:
    index: int
    total: int
    payload_sha256: str
    payload_size_bytes: int
    private_object: PrivateObject

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or not isinstance(self.total, int) or not 0 <= self.index < self.total:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive chunk index is invalid")
        _require_sha256(self.payload_sha256, label="archive_chunk_payload_sha256")
        if not isinstance(self.payload_size_bytes, int) or not 1 <= self.payload_size_bytes <= ARCHIVE_CHUNK_MAX_BYTES:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive chunk size is invalid")

    def safe_dict(self) -> dict[str, int | str]:
        return {
            "index": self.index,
            "object_sha256": self.private_object.object_sha256,
            "payload_sha256": self.payload_sha256,
            "payload_size_bytes": self.payload_size_bytes,
            "total": self.total,
        }


@dataclass(frozen=True)
class RestoreManifest:
    archive_sha256: str
    archive_size_bytes: int
    chunks: tuple[ArchiveChunk, ...]
    created_at: str
    database_sha256: str
    deletion_epoch: int
    jsonl_sha256: str
    logical_sha256: str
    schema_version: int
    snapshot_id: str
    tombstones: tuple[dict[str, int | str], ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.archive_sha256, "archive_sha256"),
            (self.database_sha256, "database_sha256"),
            (self.jsonl_sha256, "jsonl_sha256"),
            (self.logical_sha256, "logical_sha256"),
        ):
            _require_sha256(value, label=label)
        if not isinstance(self.archive_size_bytes, int) or self.archive_size_bytes < 1:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive size is invalid")
        if not isinstance(self.deletion_epoch, int) or self.deletion_epoch < 0:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive deletion epoch is invalid")
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive schema version is invalid")
        if not re.fullmatch(r"snapshot_[0-9a-f]{32}", self.snapshot_id):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive snapshot identity is invalid")
        _parse_timestamp(self.created_at)
        if not self.chunks or tuple(chunk.index for chunk in self.chunks) != tuple(range(len(self.chunks))):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive chunk sequence is invalid")
        if any(chunk.total != len(self.chunks) for chunk in self.chunks):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive chunk count is invalid")
        prior_epoch = 0
        for tombstone in self.tombstones:
            if not isinstance(tombstone, Mapping):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive tombstone is invalid")
            kind = tombstone.get("target_kind")
            epoch = tombstone.get("deletion_epoch")
            if kind not in {"content", "relation", "sink", "runtime"} or not isinstance(epoch, int) or epoch < 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive tombstone is invalid")
            _require_sha256(tombstone.get("target_key_sha256"), label="archive_tombstone_target_sha256")
            if epoch <= prior_epoch or epoch > self.deletion_epoch:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive tombstone epoch is invalid")
            prior_epoch = epoch

    @property
    def opaque_name(self) -> str:
        return f"x2n-lifecycle-manifest-{self.snapshot_id.removeprefix('snapshot_')}.json"

    def payload(self) -> dict[str, Any]:
        return {
            "archive": {"sha256": self.archive_sha256, "size_bytes": self.archive_size_bytes},
            "chunks": [
                {
                    "index": chunk.index,
                    "object_path": chunk.private_object.object_path,
                    "object_sha256": chunk.private_object.object_sha256,
                    "opaque_name": chunk.private_object.opaque_name,
                    "object_size_bytes": chunk.private_object.size_bytes,
                    "payload_sha256": chunk.payload_sha256,
                    "payload_size_bytes": chunk.payload_size_bytes,
                    "total": chunk.total,
                }
                for chunk in self.chunks
            ],
            "created_at": self.created_at,
            "database": {
                "logical_sha256": self.logical_sha256,
                "sha256": self.database_sha256,
                "schema_version": self.schema_version,
            },
            "deletion_epoch": self.deletion_epoch,
            "domain": PRIVATE_DOMAIN,
            "format": RESTORE_MANIFEST_FORMAT,
            "jsonl_sha256": self.jsonl_sha256,
            "snapshot_id": self.snapshot_id,
            "tombstones": [dict(item) for item in self.tombstones],
        }

    def to_bytes(self) -> bytes:
        return (json.dumps(self.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")

    @property
    def sha256(self) -> str:
        return _sha256_bytes(self.to_bytes())

    def safe_dict(self) -> dict[str, Any]:
        return {
            "archive_sha256": self.archive_sha256,
            "archive_size_bytes": self.archive_size_bytes,
            "chunk_count": len(self.chunks),
            "deletion_epoch": self.deletion_epoch,
            "logical_sha256": self.logical_sha256,
            "manifest_sha256": self.sha256,
            "schema_version": self.schema_version,
            "tombstone_count": len(self.tombstones),
        }

    @classmethod
    def from_bytes(cls, value: bytes) -> "RestoreManifest":
        try:
            raw = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest is invalid") from None
        if not isinstance(raw, Mapping) or raw.get("format") != RESTORE_MANIFEST_FORMAT or raw.get("domain") != PRIVATE_DOMAIN:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest identity is invalid")
        archive = raw.get("archive")
        database = raw.get("database")
        chunks_value = raw.get("chunks")
        tombstones = raw.get("tombstones")
        if not isinstance(archive, Mapping) or not isinstance(database, Mapping) or not isinstance(chunks_value, list):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest fields are invalid")
        chunks: list[ArchiveChunk] = []
        for value_item in chunks_value:
            if not isinstance(value_item, Mapping):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest chunk is invalid")
            object_sha = _require_sha256(value_item.get("object_sha256"), label="manifest_object_sha256")
            opaque_name = _require_opaque_name(value_item.get("opaque_name"), label="manifest_object_name")
            object_path = value_item.get("object_path")
            if not isinstance(object_path, str):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest object path is invalid")
            chunks.append(
                ArchiveChunk(
                    index=value_item.get("index"),
                    total=value_item.get("total"),
                    payload_sha256=_require_sha256(value_item.get("payload_sha256"), label="manifest_payload_sha256"),
                    payload_size_bytes=value_item.get("payload_size_bytes"),
                    private_object=PrivateObject(
                        object_sha256=object_sha,
                        object_path=object_path,
                        opaque_name=opaque_name,
                        size_bytes=value_item.get("object_size_bytes"),
                    ),
                )
            )
        if not isinstance(tombstones, list) or any(not isinstance(item, Mapping) for item in tombstones):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest tombstones are invalid")
        normalized_tombstones: list[dict[str, int | str]] = []
        for item in tombstones:
            assert isinstance(item, Mapping)
            kind = item.get("target_kind")
            target_hash = item.get("target_key_sha256")
            epoch = item.get("deletion_epoch")
            if kind not in {"content", "relation", "sink", "runtime"} or not isinstance(epoch, int):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore manifest tombstone is invalid")
            normalized_tombstones.append(
                {
                    "deletion_epoch": epoch,
                    "target_key_sha256": _require_sha256(target_hash, label="tombstone_target_sha256"),
                    "target_kind": str(kind),
                }
            )
        return cls(
            archive_sha256=_require_sha256(archive.get("sha256"), label="manifest_archive_sha256"),
            archive_size_bytes=archive.get("size_bytes"),
            chunks=tuple(chunks),
            created_at=raw.get("created_at"),
            database_sha256=_require_sha256(database.get("sha256"), label="manifest_database_sha256"),
            deletion_epoch=raw.get("deletion_epoch"),
            jsonl_sha256=_require_sha256(raw.get("jsonl_sha256"), label="manifest_jsonl_sha256"),
            logical_sha256=_require_sha256(database.get("logical_sha256"), label="manifest_logical_sha256"),
            schema_version=database.get("schema_version"),
            snapshot_id=raw.get("snapshot_id"),
            tombstones=tuple(normalized_tombstones),
        )


@dataclass(frozen=True)
class PreparedArchive:
    archive_path: Path
    chunks: tuple[ArchiveChunk, ...]
    manifest: RestoreManifest
    manifest_object: PrivateObject
    manifest_path: Path
    snapshot_path: Path
    workspace: Path


class PrivateDbTransport(Protocol):
    """Minimal, command-limited transport used by lifecycle orchestration."""

    def ingest(self, local: Path, *, opaque_name: str, batch: str) -> PrivateObject: ...

    def get(self, object_path: str, output: Path) -> None: ...

    def list(self) -> None: ...

    def verify(self) -> None: ...

    def attestation(self) -> dict[str, Any]: ...


class DigestPinnedPrivateDbClient:
    """Production-only command adapter for the approved client surface.

    It never receives a token value or writes auth configuration.  `gh` may use
    an Owner's existing session internally, but only the pinned client process
    can reach that session.
    """

    def __init__(self, client_path: Path) -> None:
        candidate = client_path.expanduser()
        if candidate.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Approved Private-Database client is unsafe")
        try:
            self._client_path = candidate.resolve(strict=True)
        except OSError:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Approved Private-Database client is unavailable") from None
        if self._client_path.is_symlink() or not self._client_path.is_file():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Approved Private-Database client is unsafe")
        if _sha256_file(self._client_path) != TRUSTED_PRIVATE_CLIENT_SHA256:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Approved Private-Database client digest changed")
        self._actions: list[str] = []

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "DigestPinnedPrivateDbClient":
        values = os.environ if env is None else env
        raw = values.get(PRIVATE_CLIENT_ENV)
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Approved Private-Database client is not configured")
        return cls(Path(raw))

    @staticmethod
    def _environment() -> dict[str, str]:
        home = os.environ.get("HOME")
        path = os.environ.get("PATH")
        if not home or not path:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Private client execution environment is unavailable")
        return {
            "HOME": home,
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": path,
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def _invoke(self, action: str, arguments: Sequence[str]) -> None:
        if action not in {"ingest", "get", "list", "verify"}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Private client command is outside the allowlist")
        command = (sys.executable, str(self._client_path), action, PRIVATE_AREA, *arguments)
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment(),
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError):
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Approved Private-Database client failed closed") from None
        if result.returncode != 0:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Approved Private-Database client rejected lifecycle transfer")
        self._actions.append(action)

    def ingest(self, local: Path, *, opaque_name: str, batch: str) -> PrivateObject:
        opaque = _require_opaque_name(opaque_name, label="archive_object_name")
        if local.name != opaque or local.is_symlink() or not local.is_file():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle archive input is unsafe")
        _private_regular_file(local)
        size = local.stat().st_size
        if size < 1 or size > ARCHIVE_CHUNK_MAX_BYTES:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle archive object exceeds the size policy")
        try:
            with local.open("rb") as handle:
                if handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Raw SQLite cannot enter Private-MetaDatabase")
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle archive input is unavailable") from None
        if not re.fullmatch(r"snapshot_[0-9a-f]{32}", batch):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle batch identity is invalid")
        payload_sha = _sha256_file(local)
        self._invoke("ingest", (str(local), "--domain", PRIVATE_DOMAIN, "--batch", batch))
        return PrivateObject(
            object_sha256=payload_sha,
            object_path=_expected_object_path(payload_sha, opaque),
            opaque_name=opaque,
            size_bytes=size,
        )

    def get(self, object_path: str, output: Path) -> None:
        if object_path != "manifest.jsonl" and _OBJECT_PATH.fullmatch(object_path) is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Private client object path is outside lifecycle policy")
        if output.exists() or output.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle get output already exists")
        _private_directory(output.parent)
        self._invoke("get", (object_path, str(output)))
        _private_regular_file(output)

    def list(self) -> None:
        self._invoke("list", ("objects",))

    def verify(self) -> None:
        self._invoke("verify", ())

    def attestation(self) -> dict[str, Any]:
        return {
            "authenticated_session": "private_db_client_only",
            "auth_mutations": 0,
            "client_digest_verified": True,
            "command_allowlist": ["get", "ingest", "list", "verify"],
            "commands_invoked": dict((action, self._actions.count(action)) for action in sorted(set(self._actions))),
            "token_value_contact": 0,
        }


def _lifecycle_root(paths: RuntimePaths) -> Path:
    root = paths.data_root / "runtime/lifecycle"
    try:
        root.relative_to(paths.data_root)
    except ValueError:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle workspace escaped Private Runtime") from None
    _private_directory(root)
    return root


def _new_workspace(paths: RuntimePaths, *, snapshot_id: str, ttl: LifecycleTtlPolicy, now: str) -> Path:
    _parse_timestamp(now)
    root = _lifecycle_root(paths)
    workspace = root / snapshot_id
    if workspace.exists() or workspace.is_symlink():
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle workspace identity already exists")
    try:
        workspace.mkdir(mode=0o700)
        workspace.chmod(0o700)
    except OSError:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle workspace is unavailable") from None
    expires_at = (_parse_timestamp(now) + timedelta(seconds=ttl.workspace_seconds)).replace(microsecond=0)
    _atomic_private_json(
        workspace / "workspace.json",
        {
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
        },
    )
    return workspace


def _export_jsonl(database: Path, output: Path) -> str:
    if database.is_symlink() or not database.is_file():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle archive snapshot is unavailable")
    uri = f"file:{quote(str(database))}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle archive snapshot cannot be opened") from None
    payload = bytearray()
    try:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if not columns:
                continue
            ordering = ", ".join(f'"{column}"' for column in columns)
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY {ordering}'):
                rendered = json.dumps(
                    {"row": dict(row), "table": table},
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                payload.extend(rendered.encode("utf-8"))
                payload.extend(b"\n")
    except sqlite3.Error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle JSONL export failed") from None
    finally:
        connection.close()
    _write_private_bytes(output, bytes(payload))
    return _sha256_bytes(bytes(payload))


def _write_archive(*, output: Path, snapshot: Path, jsonl: Path, metadata: Mapping[str, Any]) -> str:
    for path in (snapshot, jsonl):
        _private_regular_file(path)
    if output.exists() or output.is_symlink():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle archive output already exists")
    _private_directory(output.parent)
    metadata_payload = (json.dumps(dict(metadata), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            with tarfile.open(fileobj=handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, path in (("canonical.sqlite", snapshot), ("canonical.jsonl", jsonl)):
                    info = tarfile.TarInfo(name)
                    info.size = path.stat().st_size
                    info.mode = 0o600
                    info.mtime = 0
                    with path.open("rb") as source:
                        archive.addfile(info, source)
                info = tarfile.TarInfo("archive.json")
                info.size = len(metadata_payload)
                info.mode = 0o600
                info.mtime = 0
                archive.addfile(info, fileobj=_BytesReader(metadata_payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        output.chmod(0o600)
    except (OSError, tarfile.TarError):
        raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle archive packaging failed") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
    _private_regular_file(output)
    return _sha256_file(output)


class _BytesReader:
    """Small `tarfile.addfile` reader without holding a real temporary file."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    def read(self, count: int = -1) -> bytes:
        if count < 0:
            count = len(self._payload) - self._offset
        result = self._payload[self._offset : self._offset + count]
        self._offset += len(result)
        return result


def _chunk_archive(archive: Path, *, workspace: Path, snapshot_id: str) -> tuple[ArchiveChunk, ...]:
    _private_regular_file(archive)
    archive_sha = _sha256_file(archive)
    size = archive.stat().st_size
    # The Private-Database object limit applies to the complete opaque envelope,
    # not merely to its archive payload.  A deliberately conservative allowance
    # keeps every stored object below 90 MiB even if fields grow slightly.
    payload_limit = ARCHIVE_CHUNK_MAX_BYTES - 4096
    total = (size + payload_limit - 1) // payload_limit
    if total < 1:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive is empty")
    chunks: list[ArchiveChunk] = []
    with archive.open("rb") as handle:
        for index in range(total):
            payload = handle.read(payload_limit)
            if not payload:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive chunk is missing")
            payload_sha = _sha256_bytes(payload)
            opaque_name = f"x2n-archive-{archive_sha[:16]}-{index:04d}.bin"
            envelope_header = {
                "archive_sha256": archive_sha,
                "domain": PRIVATE_DOMAIN,
                "format": ENVELOPE_FORMAT,
                "index": index,
                "payload_sha256": payload_sha,
                "payload_size_bytes": len(payload),
                "snapshot_id": snapshot_id,
                "total": total,
            }
            envelope = (
                json.dumps(envelope_header, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                + b"\n"
                + payload
            )
            if len(envelope) > ARCHIVE_CHUNK_MAX_BYTES:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive chunk exceeds policy limit")
            output = workspace / opaque_name
            _write_private_bytes(output, envelope)
            object_sha = _sha256_bytes(envelope)
            chunks.append(
                ArchiveChunk(
                    index=index,
                    total=total,
                    payload_sha256=payload_sha,
                    payload_size_bytes=len(payload),
                    private_object=PrivateObject(
                        object_sha256=object_sha,
                        object_path=_expected_object_path(object_sha, opaque_name),
                        opaque_name=opaque_name,
                        size_bytes=len(envelope),
                    ),
                )
            )
        if handle.read(1):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive chunking is invalid")
    return tuple(chunks)


def _decode_chunk_envelope(value: bytes, expected: ArchiveChunk, *, manifest: RestoreManifest) -> bytes:
    header_bytes, separator, payload = value.partition(b"\n")
    if not separator:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive envelope is invalid")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive envelope is invalid") from None
    if not isinstance(header, Mapping) or (
        header.get("format") != ENVELOPE_FORMAT
        or header.get("domain") != PRIVATE_DOMAIN
        or header.get("archive_sha256") != manifest.archive_sha256
        or header.get("snapshot_id") != manifest.snapshot_id
        or header.get("index") != expected.index
        or header.get("total") != expected.total
        or header.get("payload_sha256") != expected.payload_sha256
        or header.get("payload_size_bytes") != expected.payload_size_bytes
        or len(payload) != expected.payload_size_bytes
        or _sha256_bytes(payload) != expected.payload_sha256
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive envelope diverged")
    return payload


def _domain_manifest_records(payload: bytes) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for raw_line in payload.splitlines():
        try:
            item = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # A malformed foreign row must not couple another domain into x2n's
            # outcome. Expected x2n rows will still be absent and fail closed.
            continue
        if not isinstance(item, Mapping) or item.get("domain") != PRIVATE_DOMAIN:
            continue
        object_path = item.get("object_path")
        sha256 = item.get("sha256")
        original_name = item.get("original_name")
        if not isinstance(object_path, str) or not isinstance(sha256, str) or not isinstance(original_name, str):
            continue
        if _OBJECT_PATH.fullmatch(object_path) is None or _SHA256.fullmatch(sha256) is None:
            continue
        records[object_path] = {"object_path": object_path, "original_name": original_name, "sha256": sha256}
    return records


def _load_private_manifest(client: PrivateDbTransport, *, workspace: Path) -> dict[str, dict[str, Any]]:
    output = workspace / "get-manifest.jsonl"
    try:
        client.get("manifest.jsonl", output)
        _private_regular_file(output)
        return _domain_manifest_records(output.read_bytes())
    finally:
        if output.exists() or output.is_symlink():
            _private_regular_file(output)
            output.unlink()


def _validate_expected_objects(records: Mapping[str, Mapping[str, Any]], objects: Sequence[PrivateObject]) -> None:
    for expected in objects:
        row = records.get(expected.object_path)
        if row is None or row.get("sha256") != expected.object_sha256 or row.get("original_name") != expected.opaque_name:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private-MetaDatabase exact-domain manifest is incomplete")


@dataclass(frozen=True)
class ExtractedArchive:
    archive_path: Path
    jsonl_path: Path
    snapshot_path: Path


def _extract_archive(archive_path: Path, *, workspace: Path, manifest: RestoreManifest) -> ExtractedArchive:
    _private_regular_file(archive_path)
    expected_names = {"archive.json", "canonical.jsonl", "canonical.sqlite"}
    extracted: dict[str, Path] = {}
    try:
        with tarfile.open(archive_path, "r") as archive:
            members = archive.getmembers()
            if {member.name for member in members} != expected_names:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive member set is invalid")
            for member in members:
                if not member.isfile() or member.issym() or member.islnk() or member.name not in expected_names:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle archive member is unsafe")
                source = archive.extractfile(member)
                if source is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive member is unavailable")
                payload = source.read()
                output = workspace / f"restored-{member.name}"
                _write_private_bytes(output, payload)
                extracted[member.name] = output
    except X2NRuntimeError:
        raise
    except (OSError, tarfile.TarError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive extraction failed") from None
    metadata_path = extracted["archive.json"]
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive metadata is invalid") from None
    if not isinstance(metadata, Mapping) or (
        metadata.get("format") != ARCHIVE_FORMAT
        or metadata.get("domain") != PRIVATE_DOMAIN
        or metadata.get("database_sha256") != manifest.database_sha256
        or metadata.get("jsonl_sha256") != manifest.jsonl_sha256
        or metadata.get("logical_sha256") != manifest.logical_sha256
        or metadata.get("schema_version") != manifest.schema_version
        or metadata.get("snapshot_id") != manifest.snapshot_id
        or metadata.get("deletion_epoch") != manifest.deletion_epoch
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive metadata is invalid")
    snapshot = extracted["canonical.sqlite"]
    jsonl = extracted["canonical.jsonl"]
    if _sha256_file(snapshot) != manifest.database_sha256 or _sha256_file(jsonl) != manifest.jsonl_sha256:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive payload hash is invalid")
    return ExtractedArchive(archive_path=archive_path, jsonl_path=jsonl, snapshot_path=snapshot)


def _verify_archived_database(snapshot: Path, manifest: RestoreManifest) -> None:
    uri = f"file:{quote(str(snapshot))}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archived SQLite cannot be opened") from None
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower()
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0]).lower()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if quick != "ok" or integrity != "ok" or violations:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archived SQLite integrity is invalid")
        if current_version(connection) != manifest.schema_version:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archived SQLite schema is invalid")
        if CanonicalStore._logical_digest(connection) != manifest.logical_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archived SQLite logical digest is invalid")
        state = connection.execute("SELECT deletion_epoch FROM lifecycle_state WHERE state_id = 1").fetchone()
        if state is None or int(state["deletion_epoch"]) != manifest.deletion_epoch:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archived SQLite deletion epoch is invalid")
    finally:
        connection.close()


class LifecycleService:
    """Owner-local lifecycle operations; external transfers are explicit only."""

    def __init__(self, store: CanonicalStore, *, ttl: LifecycleTtlPolicy | None = None) -> None:
        self.store = store
        self.paths = store.paths
        self.ttl = ttl or LifecycleTtlPolicy()

    def status(self) -> dict[str, Any]:
        active = self.paths.database.is_file() and not self.paths.database.is_symlink()
        state: dict[str, Any]
        if active:
            state = self.store.lifecycle_state().safe_dict()
        else:
            state = {
                "deletion_epoch": "UNKNOWN_ACTIVE_STORE_MISSING",
                "durability_state": "durability_pending",
                "latest_manifest_sha256": None,
                "updated_at": "UNKNOWN_ACTIVE_STORE_MISSING",
            }
        return {
            "active_sqlite": "available" if active else "missing_durability_pending_recovery",
            "durability": state,
            "durable_destination": PRIVATE_AREA,
            "durable_domain": PRIVATE_DOMAIN,
            "durable_hard_erase": "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED",
            "private_client": "not_invoked",
            "time_machine": "not_run_owner_confirmation_required",
        }

    def delete_preview(self, *, target_kind: str, target_key_private: str) -> dict[str, Any]:
        return self.store.lifecycle_delete_preview(target_kind=target_kind, target_key_private=target_key_private)

    def confirm_delete(
        self,
        *,
        target_kind: str,
        target_key_private: str,
        confirmation: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        if confirmation != LIFECYCLE_DELETE_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle deletion requires explicit confirmation")
        tombstone = self.store.record_owner_tombstone(
            target_kind=target_kind,
            target_key_private=target_key_private,
            now=now,
        )
        markdown = {"category_index_writes": 0, "content_writes": 0, "removed_category_indexes": 0, "removed_content_files": 0}
        if target_kind in {"content", "relation", "sink"}:
            rebuild = MarkdownSink(self.store).rebuild_from_canonical(build_sink_projection)
            markdown = {
                "category_index_writes": rebuild.category_index_writes,
                "content_writes": rebuild.content_writes,
                "removed_category_indexes": rebuild.removed_category_indexes,
                "removed_content_files": rebuild.removed_content_files,
            }
        return {
            "durability": self.store.lifecycle_state().safe_dict(),
            "durable_hard_erase": "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED",
            "markdown": markdown,
            "tombstone": tombstone.safe_dict(),
        }

    def request_runtime_wipe(self, *, confirmation: str, now: str | None = None) -> dict[str, Any]:
        if confirmation != RUNTIME_WIPE_REQUEST_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Runtime wipe request requires explicit confirmation")
        tombstone = self.store.record_owner_tombstone(
            target_kind="runtime",
            target_key_private="active_runtime",
            now=now,
        )
        return {"durability": self.store.lifecycle_state().safe_dict(), "tombstone": tombstone.safe_dict()}

    def apply_verified_runtime_wipe(self, *, confirmation: str) -> dict[str, Any]:
        if confirmation != RUNTIME_WIPE_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Runtime wipe requires explicit confirmation")
        state = self.store.lifecycle_state()
        runtime_tombstones = [item for item in self.store.lifecycle_tombstones() if item.target_kind == "runtime"]
        if state.durability_state != "durability_verified" or not runtime_tombstones:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Runtime wipe requires a verified latest tombstone manifest")
        deleted = 0
        with self.store._file_lock(exclusive=True):
            for path in (self.paths.database, Path(f"{self.paths.database}-wal"), Path(f"{self.paths.database}-shm")):
                if not path.exists() and not path.is_symlink():
                    continue
                _private_regular_file(path)
                path.unlink()
                deleted += 1
            library = self.paths.data_root / "runtime/library"
            _private_directory(library)
            for child in sorted(library.iterdir(), key=lambda item: item.name, reverse=True):
                if child.is_symlink():
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Derived library contains a symbolic link")
                if child.is_dir():
                    _remove_private_tree(child)
                elif child.is_file():
                    _private_regular_file(child)
                    child.unlink()
                else:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Derived library contains an unsafe entry")
                deleted += 1
        return {
            "active_sqlite": "removed_local_only",
            "durable_hard_erase": "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED",
            "local_entries_removed": deleted,
            "restore_requires": "latest_verified_manifest_only",
        }

    def _prepare(self, *, now: str | None = None) -> PreparedArchive:
        created_at = now or _utc_now()
        self.store.mark_durability_pending(now=created_at)
        receipt = self.store.backup(label="lifecycle")
        verified = self.store.verify_backup(receipt.backup_id, expected_sha256=receipt.database_sha256)
        snapshot_path = self.paths.backups_directory / f"canonical-{receipt.backup_id}.sqlite"
        snapshot_id = f"snapshot_{uuid.uuid4().hex}"
        workspace = _new_workspace(self.paths, snapshot_id=snapshot_id, ttl=self.ttl, now=created_at)
        try:
            jsonl_path = workspace / "canonical.jsonl"
            jsonl_sha = _export_jsonl(snapshot_path, jsonl_path)
            lifecycle = self.store.lifecycle_state()
            tombstones = tuple(item.safe_dict() for item in self.store.lifecycle_tombstones())
            archive_path = workspace / "x2n-archive.bundle"
            archive_sha = _write_archive(
                output=archive_path,
                snapshot=snapshot_path,
                jsonl=jsonl_path,
                metadata={
                    "database_sha256": verified.database_sha256,
                    "deletion_epoch": lifecycle.deletion_epoch,
                    "domain": PRIVATE_DOMAIN,
                    "format": ARCHIVE_FORMAT,
                    "jsonl_sha256": jsonl_sha,
                    "logical_sha256": verified.logical_sha256,
                    "schema_version": verified.schema_version,
                    "snapshot_id": snapshot_id,
                },
            )
            chunks = _chunk_archive(archive_path, workspace=workspace, snapshot_id=snapshot_id)
            manifest = RestoreManifest(
                archive_sha256=archive_sha,
                archive_size_bytes=archive_path.stat().st_size,
                chunks=chunks,
                created_at=created_at,
                database_sha256=verified.database_sha256,
                deletion_epoch=lifecycle.deletion_epoch,
                jsonl_sha256=jsonl_sha,
                logical_sha256=verified.logical_sha256,
                schema_version=verified.schema_version,
                snapshot_id=snapshot_id,
                tombstones=tombstones,
            )
            manifest_path = workspace / manifest.opaque_name
            manifest_payload = manifest.to_bytes()
            _write_private_bytes(manifest_path, manifest_payload)
            manifest_object = PrivateObject(
                object_sha256=_sha256_bytes(manifest_payload),
                object_path=_expected_object_path(_sha256_bytes(manifest_payload), manifest.opaque_name),
                opaque_name=manifest.opaque_name,
                size_bytes=len(manifest_payload),
            )
            return PreparedArchive(
                archive_path=archive_path,
                chunks=chunks,
                manifest=manifest,
                manifest_object=manifest_object,
                manifest_path=manifest_path,
                snapshot_path=snapshot_path,
                workspace=workspace,
            )
        except BaseException:
            _remove_private_tree(workspace)
            raise

    def _download_and_extract(
        self,
        manifest: RestoreManifest,
        client: PrivateDbTransport,
        *,
        workspace: Path,
        manifest_object: PrivateObject | None,
    ) -> ExtractedArchive:
        records = _load_private_manifest(client, workspace=workspace)
        expected = [chunk.private_object for chunk in manifest.chunks]
        if manifest_object is not None:
            expected.append(manifest_object)
        _validate_expected_objects(records, expected)
        archive_path = workspace / "reassembled.archive"
        try:
            descriptor = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as destination:
                for chunk in manifest.chunks:
                    output = workspace / f"get-{chunk.index:04d}.bin"
                    try:
                        client.get(chunk.private_object.object_path, output)
                        _private_regular_file(output)
                        envelope = output.read_bytes()
                        if (
                            len(envelope) != chunk.private_object.size_bytes
                            or _sha256_bytes(envelope) != chunk.private_object.object_sha256
                        ):
                            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Downloaded archive object hash is invalid")
                        destination.write(_decode_chunk_envelope(envelope, chunk, manifest=manifest))
                    finally:
                        if output.exists() or output.is_symlink():
                            _private_regular_file(output)
                            output.unlink()
                destination.flush()
                os.fsync(destination.fileno())
            archive_path.chmod(0o600)
        except X2NRuntimeError:
            raise
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Lifecycle archive reassembly failed") from None
        if _sha256_file(archive_path) != manifest.archive_sha256 or archive_path.stat().st_size != manifest.archive_size_bytes:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle archive reassembly hash is invalid")
        extracted = _extract_archive(archive_path, workspace=workspace, manifest=manifest)
        _verify_archived_database(extracted.snapshot_path, manifest)
        return extracted

    def export_and_verify(self, client: PrivateDbTransport, *, now: str | None = None) -> dict[str, Any]:
        prepared = self._prepare(now=now)
        try:
            transferred: list[PrivateObject] = []
            for chunk in prepared.chunks:
                local = prepared.workspace / chunk.private_object.opaque_name
                object_receipt = client.ingest(local, opaque_name=chunk.private_object.opaque_name, batch=prepared.manifest.snapshot_id)
                if object_receipt != chunk.private_object:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private archive object receipt diverged")
                transferred.append(object_receipt)
            manifest_receipt = client.ingest(
                prepared.manifest_path,
                opaque_name=prepared.manifest_object.opaque_name,
                batch=prepared.manifest.snapshot_id,
            )
            if manifest_receipt != prepared.manifest_object:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private restore manifest receipt diverged")
            client.list()
            client.verify()
            self._download_and_extract(
                prepared.manifest,
                client,
                workspace=prepared.workspace,
                manifest_object=prepared.manifest_object,
            )
            state = self.store.mark_durability_verified(prepared.manifest.sha256, now=now)
            return {
                "archive": prepared.manifest.safe_dict(),
                "attestation": client.attestation(),
                "durability": state.safe_dict(),
                "execution": {
                    "platform_calls": 0,
                    "real_account_execution": "NOT_RUN",
                    "real_notion_calls": 0,
                    "token_value_contact": 0,
                },
                "transferred_object_count": len(transferred) + 1,
            }
        finally:
            _remove_private_tree(prepared.workspace)

    def _discover_latest_manifest(self, client: PrivateDbTransport, *, workspace: Path) -> tuple[RestoreManifest, PrivateObject]:
        records = _load_private_manifest(client, workspace=workspace)
        candidates: list[tuple[RestoreManifest, PrivateObject]] = []
        for object_path, row in records.items():
            opaque_name = row.get("original_name")
            sha = row.get("sha256")
            if not isinstance(opaque_name, str) or _MANIFEST_NAME.fullmatch(opaque_name) is None or not isinstance(sha, str):
                continue
            object_receipt = PrivateObject(
                object_sha256=_require_sha256(sha, label="manifest_object_sha256"),
                object_path=object_path,
                opaque_name=opaque_name,
                size_bytes=1,
            )
            output = workspace / f"discover-{len(candidates):04d}.json"
            try:
                client.get(object_path, output)
                _private_regular_file(output)
                payload = output.read_bytes()
                if _sha256_bytes(payload) != object_receipt.object_sha256:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Latest restore manifest hash is invalid")
                manifest = RestoreManifest.from_bytes(payload)
                if manifest.opaque_name != opaque_name:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Latest restore manifest identity is invalid")
                candidates.append((manifest, object_receipt))
            finally:
                if output.exists() or output.is_symlink():
                    _private_regular_file(output)
                    output.unlink()
        if not candidates:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "No exact-domain restore manifest is available")
        return max(candidates, key=lambda item: (item[0].deletion_epoch, item[0].created_at, item[0].snapshot_id))

    def restore_latest(self, client: PrivateDbTransport, *, confirmation: str) -> dict[str, Any]:
        if confirmation != PRIVATE_RESTORE_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Lifecycle restore requires explicit confirmation")
        snapshot_id = f"snapshot_{uuid.uuid4().hex}"
        workspace = _new_workspace(self.paths, snapshot_id=snapshot_id, ttl=self.ttl, now=_utc_now())
        try:
            manifest, manifest_object = self._discover_latest_manifest(client, workspace=workspace)
            extracted = self._download_and_extract(
                manifest,
                client,
                workspace=workspace,
                manifest_object=manifest_object,
            )
            receipt = self.store.restore_archival_snapshot(
                extracted.snapshot_path,
                expected_database_sha256=manifest.database_sha256,
                expected_logical_sha256=manifest.logical_sha256,
                expected_schema_version=manifest.schema_version,
                expected_deletion_epoch=manifest.deletion_epoch,
            )
            state = self.store.mark_durability_verified(manifest.sha256)
            return {"archive": manifest.safe_dict(), "durability": state.safe_dict(), "restore": receipt.safe_dict()}
        finally:
            _remove_private_tree(workspace)

    def recovery_plan(self) -> dict[str, Any]:
        if self.paths.database.is_file() and not self.paths.database.is_symlink():
            return {"action": "none", "durability": self.store.lifecycle_state().safe_dict(), "state": "active_sqlite_present"}
        return {
            "action": "restore_latest_requires_explicit_confirmation",
            "durability": "durability_pending",
            "state": "active_sqlite_missing",
        }

    def cleanup_expired_workspaces(self, *, now: str | None = None) -> dict[str, int]:
        observed_at = _parse_timestamp(now or _utc_now())
        root = _lifecycle_root(self.paths)
        deleted = blocked = 0
        for candidate in sorted(root.iterdir(), key=lambda item: item.name):
            if candidate.is_symlink() or not candidate.is_dir() or not re.fullmatch(r"snapshot_[0-9a-f]{32}", candidate.name):
                blocked += 1
                continue
            marker = candidate / "workspace.json"
            try:
                _private_regular_file(marker)
                payload = json.loads(marker.read_text(encoding="utf-8"))
                if not isinstance(payload, Mapping) or payload.get("snapshot_id") != candidate.name:
                    raise ValueError("workspace identity")
                expires_at = _parse_timestamp(str(payload.get("expires_at")))
            except (OSError, ValueError, json.JSONDecodeError, X2NRuntimeError):
                blocked += 1
                continue
            if expires_at <= observed_at:
                _remove_private_tree(candidate)
                deleted += 1
        return {"expired_workspaces_deleted": deleted, "unsafe_workspaces_blocked": blocked}

    def time_machine_plan(self) -> dict[str, Any]:
        return {
            "action": "tmutil_addexclusion_entire_x2n_data_root",
            "confirmation_required": TIME_MACHINE_CONFIRMATION,
            "local_backup_is_durability": False,
            "status": "not_run",
        }

    def apply_time_machine_exclusion(
        self,
        *,
        confirmation: str,
        system_name: Callable[[], str] = os_platform.system,
        runner: Callable[[Sequence[str]], tuple[int, bytes]] | None = None,
    ) -> dict[str, Any]:
        if confirmation != TIME_MACHINE_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Time Machine exclusion requires explicit confirmation")
        if system_name() != "Darwin":
            return {"local_backup_is_durability": False, "status": "UNSUPPORTED_OS_FAIL_CLOSED"}
        invoke = runner or self._tmutil_runner
        code, _ = invoke(("/usr/bin/tmutil", "addexclusion", str(self.paths.data_root)))
        if code != 0:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Time Machine exclusion failed closed")
        targets = (self.paths.data_root, *(self.paths.data_root / item for item in REQUIRED_DIRECTORIES))
        for target in targets:
            code, output = invoke(("/usr/bin/tmutil", "isexcluded", str(target)))
            if code != 0 or b"[Excluded]" not in output:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Time Machine exclusion verification failed")
        return {
            "excluded_required_subpaths": len(REQUIRED_DIRECTORIES),
            "local_backup_is_durability": False,
            "status": "PASS_OWNER_CONFIRMED_WHOLE_ROOT_EXCLUSION",
        }

    @staticmethod
    def _tmutil_runner(command: Sequence[str]) -> tuple[int, bytes]:
        try:
            result = subprocess.run(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return 1, b""
        return result.returncode, result.stdout
