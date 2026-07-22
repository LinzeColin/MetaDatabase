"""Private Runtime root resolution for x2n.

The resolved path is private state.  Public callers receive stable error codes
and aggregate facts only; this module never falls back to an OS default path.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode


PROJECT_NAME = "xhs-douyin-2notion"
ROOT_ENV = "X2N_DATA_ROOT"
DOWNLOAD_ENV = "X2N_DOWNLOAD_DESTINATION"
DOWNLOAD_BASENAME = "MediaCrawler"
MARKER_NAME = ".x2n-root.json"

REQUIRED_DIRECTORIES = (
    "downloads/xiaohongshu/runs",
    "downloads/douyin/runs",
    "downloads/bilibili/runs",
    "downloads/kuaishou/runs",
    "downloads/weibo/runs",
    "downloads/taobao/runs",
    "downloads/external_research/runs",
    "runtime/canonical",
    "runtime/checkpoints",
    "runtime/temp_media",
    "runtime/browser_profiles/xiaohongshu",
    "runtime/browser_profiles/douyin",
    "runtime/browser_profiles/bilibili",
    "runtime/browser_profiles/kuaishou",
    "runtime/browser_profiles/weibo",
    "runtime/browser_profiles/taobao",
    "runtime/library/content",
    "runtime/library/categories",
    "runtime/logs",
    "runtime/diagnostics",
    "runtime/backups",
    "runtime/models",
    "runtime/provider_cache",
)


class X2NRuntimeError(RuntimeError):
    """Fail-closed Runtime error without private path disclosure."""

    def __init__(self, code: ErrorCode, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


def _fail(code: ErrorCode, message: str) -> None:
    raise X2NRuntimeError(code, message)


def _private_mode(path: Path, expected: int, *, label: str) -> None:
    if path.is_symlink():
        _fail(ErrorCode.POLICY_BLOCKED, f"{label} cannot be a symbolic link")
    if stat.S_IMODE(path.stat().st_mode) != expected:
        _fail(ErrorCode.POLICY_BLOCKED, f"{label} must be owner-only")


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _raw_absolute_path(value: str | None, *, label: str) -> Path:
    if value is None or not value or "\x00" in value or value.startswith("~"):
        _fail(ErrorCode.INVALID_INPUT, f"{label} requires an explicit absolute path")
    path = Path(value)
    if not path.is_absolute():
        _fail(ErrorCode.INVALID_INPUT, f"{label} requires an explicit absolute path")
    return path


def _mkdir_private(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime layout conflicts with an existing file")
        _private_mode(path, 0o700, label="Private Runtime directory")
        return
    path.mkdir(mode=0o700)
    path.chmod(0o700)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class RuntimePaths:
    """Validated paths inside the single Owner-selected x2n namespace."""

    data_root: Path
    download_destination: Path
    repository_root: Path

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        repository_root: Path,
        create: bool = False,
    ) -> "RuntimePaths":
        values = os.environ if env is None else env
        return cls.from_values(
            values.get(ROOT_ENV),
            values.get(DOWNLOAD_ENV),
            repository_root=repository_root,
            create=create,
        )

    @classmethod
    def from_values(
        cls,
        data_root: str | None,
        download_destination: str | None,
        *,
        repository_root: Path,
        create: bool = False,
    ) -> "RuntimePaths":
        raw_root = _raw_absolute_path(data_root, label=ROOT_ENV)
        raw_destination = _raw_absolute_path(download_destination, label=DOWNLOAD_ENV)
        if not raw_destination.is_dir():
            _fail(ErrorCode.POLICY_BLOCKED, "Owner download destination is unavailable")
        _private_mode(raw_destination, 0o700, label="Owner download destination")

        destination = raw_destination.resolve(strict=True)
        if destination.name != DOWNLOAD_BASENAME:
            _fail(ErrorCode.POLICY_BLOCKED, "Owner download destination identity does not match policy")
        expected_root = destination / PROJECT_NAME
        if raw_root.resolve(strict=False) != expected_root.resolve(strict=False):
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime is outside the approved project namespace")

        repository = repository_root.resolve(strict=True)
        root = expected_root.resolve(strict=False)
        if root == repository or _contains(root, repository) or _contains(repository, root):
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime must remain outside the repository")

        if root.exists():
            if not root.is_dir():
                _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime root conflicts with an existing file")
            _private_mode(root, 0o700, label="Private Runtime root")
            root = root.resolve(strict=True)
        elif create:
            _mkdir_private(root)
            root = root.resolve(strict=True)
        else:
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime root is unavailable")

        instance = cls(data_root=root, download_destination=destination, repository_root=repository)
        if create:
            instance.initialize_layout()
        else:
            instance.validate_layout()
        return instance

    @property
    def marker(self) -> Path:
        return self.data_root / MARKER_NAME

    @property
    def canonical_directory(self) -> Path:
        return self.data_root / "runtime/canonical"

    @property
    def database(self) -> Path:
        return self.canonical_directory / "canonical.sqlite"

    @property
    def backups_directory(self) -> Path:
        return self.data_root / "runtime/backups"

    @property
    def temp_media_directory(self) -> Path:
        return self.data_root / "runtime/temp_media"

    def _safe_child(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime layout contains an unsafe path")
        resolved = (self.data_root / candidate).resolve(strict=False)
        if not _contains(self.data_root, resolved):
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime path escaped its namespace")
        return resolved

    def initialize_layout(self) -> None:
        _private_mode(self.download_destination, 0o700, label="Owner download destination")
        _private_mode(self.data_root, 0o700, label="Private Runtime root")
        for relative in REQUIRED_DIRECTORIES:
            current = self.data_root
            for part in Path(relative).parts:
                current = current / part
                _mkdir_private(current)
                if not _contains(self.data_root, current.resolve(strict=True)):
                    _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime path escaped its namespace")

        if self.marker.exists():
            self._validate_marker()
        else:
            _atomic_private_json(
                self.marker,
                {
                    "legacy_import": False,
                    "product_execution_authorized": False,
                    "project": PROJECT_NAME,
                    "real_data_state": "stage_1_canonical_store_pending_no_content",
                    "resolved_root": str(self.data_root),
                    "root_ref": ROOT_ENV,
                    "schema_version": "1.0",
                },
            )
        self.validate_layout()

    def _validate_marker(self) -> dict[str, Any]:
        if not self.marker.is_file():
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime marker is unavailable")
        _private_mode(self.marker, 0o600, label="Private Runtime marker")
        try:
            value = json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Private Runtime marker is invalid") from error
        if not isinstance(value, dict):
            _fail(ErrorCode.DATA_INTEGRITY_FAILED, "Private Runtime marker is invalid")
        if (
            value.get("project") != PROJECT_NAME
            or value.get("root_ref") != ROOT_ENV
            or Path(str(value.get("resolved_root", ""))).resolve(strict=False) != self.data_root
            or value.get("legacy_import") is not False
            or value.get("product_execution_authorized") is not False
        ):
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime marker does not match this project")
        return value

    def validate_layout(self) -> None:
        _private_mode(self.download_destination, 0o700, label="Owner download destination")
        _private_mode(self.data_root, 0o700, label="Private Runtime root")
        if self.data_root.parent != self.download_destination:
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime namespace relation changed")
        for relative in REQUIRED_DIRECTORIES:
            directory = self._safe_child(relative)
            if not directory.is_dir():
                _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime layout is incomplete")
            _private_mode(directory, 0o700, label="Private Runtime directory")
        self._validate_marker()

    def mark_store_initialized(self) -> None:
        marker = self._validate_marker()
        allowed_states = {
            "empty_pre_stage_00",
            "stage_0_owner_input_defaults_no_content",
            "stage_1_canonical_store_pending_no_content",
            "stage_1_canonical_store_initialized_no_content",
        }
        if marker.get("real_data_state") not in allowed_states:
            _fail(ErrorCode.POLICY_BLOCKED, "Private Runtime marker state forbids Store initialization")
        marker["real_data_state"] = "stage_1_canonical_store_initialized_no_content"
        marker["product_execution_authorized"] = False
        marker["canonical_store_schema_version"] = 2
        _atomic_private_json(self.marker, marker)

    def ensure_private_file(self, path: Path) -> None:
        resolved = path.resolve(strict=False)
        if not _contains(self.data_root, resolved):
            _fail(ErrorCode.POLICY_BLOCKED, "Runtime file escaped its private namespace")
        if path.exists() and path.is_symlink():
            _fail(ErrorCode.POLICY_BLOCKED, "Runtime file cannot be a symbolic link")
        if path.exists():
            path.chmod(0o600)
