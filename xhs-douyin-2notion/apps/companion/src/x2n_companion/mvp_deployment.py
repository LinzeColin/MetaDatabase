"""Blue-green local packaging and online smoke for the direct owner MVP.

The deployer has no network/platform adapter.  It stages public code into the
private Runtime before it changes a release pointer, delegates the Native Host
install to its transaction-safe installer, and only then switches the staged
artifact.  The post-switch smoke combines a local Native Host health frame
with the Side Panel's recorded Native Messaging handshake.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode, canonical_json_sha256

from .mvp_release import MvpReleaseController, RELEASE_VERSION, owner_input_contract_sha256
from .native_host import DEVELOPMENT_EXTENSION_ORIGIN, HOST_NAME
from .native_host_installer import (
    INSTALL_CONFIRMATION,
    UNINSTALL_CONFIRMATION,
    create_plan,
    execute_plan,
    verify_release_installation,
)
from .runtime import RuntimePaths, X2NRuntimeError, _atomic_private_json


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEPLOY_CONFIRMATION = "DEPLOY_X2N_OWNER_MVP_V0_0_0_1"
ONLINE_SMOKE_CONFIRMATION = "ONLINE_SMOKE_X2N_OWNER_MVP_V0_0_0_1"
PREARM_HOST_CONFIRMATION = "INSTALL_X2N_PREARM_SIDEPANEL_HOST"
_EXTENSION_RELEASE_IDENTITY = "release_identity.json"
_PREARM_MANIFEST = "prearm_manifest.json"
_PREARM_ARTIFACT_KIND = "owner_prearm_sidepanel"
_SOURCE_TREES = (
    (PROJECT_ROOT / "apps/extension", "extension"),
    (PROJECT_ROOT / "apps/companion/src/x2n_companion", "companion/x2n_companion"),
    (PROJECT_ROOT / "packages/contracts/src/x2n_contracts", "contracts/x2n_contracts"),
)


def _private_directory(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release directory is unsafe")
        return
    path.mkdir(mode=0o700)
    path.chmod(0o700)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _directory_digest(path: Path, *, excluded_relative_paths: frozenset[str] = frozenset()) -> str:
    if path.is_symlink() or not path.is_dir():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release source tree is unsafe")
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release source cannot contain symbolic links")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(path).as_posix()
        if relative in excluded_relative_paths:
            continue
        if "__pycache__" in candidate.parts or candidate.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(_sha256_file(candidate).encode("ascii") + b"\n")
    return digest.hexdigest()


def _release_layout(paths: RuntimePaths) -> tuple[Path, Path, Path, Path]:
    install = paths.ensure_private_directory("runtime/install")
    versions = install / "versions"
    _private_directory(versions)
    return install, versions, install / "current", install / "previous"


def _controlled_link(path: Path, *, versions: Path) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_symlink():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release pointer is not a controlled link")
    try:
        target = path.resolve(strict=True)
        target.relative_to(versions.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release pointer escaped its version directory") from error
    if target.parent != versions.resolve(strict=True) or not target.is_dir() or target.is_symlink():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release pointer target is invalid")
    return target.name


def _replace_link(path: Path, *, target_name: str | None) -> None:
    temporary = path.with_name(f".{path.name}.x2n-{uuid.uuid4().hex}")
    try:
        if target_name is None:
            if path.exists() or path.is_symlink():
                path.unlink()
            return
        os.symlink(f"versions/{target_name}", temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _source_manifest() -> dict[str, Any]:
    rows = []
    for source, destination in _SOURCE_TREES:
        if not source.is_dir() or source.is_symlink():
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "MVP release source tree is unavailable")
        if destination == "extension" and (
            (source / _EXTENSION_RELEASE_IDENTITY).exists() or (source / _EXTENSION_RELEASE_IDENTITY).is_symlink()
        ):
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED, "MVP extension source contains a generated release identity"
            )
        rows.append({"destination": destination, "source_digest": _directory_digest(source)})
    artifact_basis = {
        "artifact_kind": "local_owner_mvp",
        "contract_version": "1.0",
        "native_host": HOST_NAME,
        "release_version": RELEASE_VERSION,
        "source_trees": rows,
    }
    artifact_sha256 = canonical_json_sha256(artifact_basis)
    extension_identity = {"artifact_sha256": artifact_sha256, "schema_version": "1.0"}
    return {
        **artifact_basis,
        "artifact_sha256": artifact_sha256,
        "extension_release_identity_sha256": canonical_json_sha256(extension_identity),
    }


def _prearm_source_manifest() -> dict[str, Any]:
    """Build a non-release source identity for the stable pre-arm Side Panel."""

    rows = []
    for source, destination in _SOURCE_TREES:
        if not source.is_dir() or source.is_symlink():
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Pre-arm Side Panel source tree is unavailable")
        if destination == "extension" and (
            (source / _EXTENSION_RELEASE_IDENTITY).exists() or (source / _EXTENSION_RELEASE_IDENTITY).is_symlink()
        ):
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED, "Pre-arm Side Panel source contains a generated release identity"
            )
        rows.append({"destination": destination, "source_digest": _directory_digest(source)})
    artifact_basis = {
        "artifact_kind": _PREARM_ARTIFACT_KIND,
        "contract_version": "1.0",
        "native_host": HOST_NAME,
        "source_trees": rows,
    }
    return {**artifact_basis, "artifact_sha256": canonical_json_sha256(artifact_basis)}


def _prearm_layout(paths: RuntimePaths) -> Path:
    return paths.ensure_private_directory("runtime/prearm/bundles")


def _copy_private_release_tree(source: Path, destination: Path) -> None:
    """Copy a public source tree into owner-only staging without following links."""

    _directory_digest(source)  # validates the complete source surface first
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for candidate in sorted(destination.rglob("*")):
        if candidate.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release staging contains a symbolic link")
        if candidate.is_dir():
            candidate.chmod(0o700)
        elif candidate.is_file():
            candidate.chmod(0o600)
        else:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release staging contains an unsafe entry")
    destination.chmod(0o700)


def _write_extension_release_identity(extension: Path, *, artifact_sha256: str) -> None:
    """Bind the staged Side Panel to the same non-secret artifact identity as the Host."""

    if extension.is_symlink() or not extension.is_dir() or (extension / _EXTENSION_RELEASE_IDENTITY).exists():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP extension release identity destination is unsafe")
    _atomic_private_json(
        extension / _EXTENSION_RELEASE_IDENTITY,
        {"artifact_sha256": artifact_sha256, "schema_version": "1.0"},
    )


def _read_staged_manifest(target: Path) -> dict[str, Any]:
    manifest = target / "release_manifest.json"
    if (
        target.is_symlink()
        or not target.is_dir()
        or stat.S_IMODE(target.stat().st_mode) != 0o700
        or manifest.is_symlink()
        or not manifest.is_file()
        or stat.S_IMODE(manifest.stat().st_mode) != 0o600
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP staged artifact is unsafe")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact manifest is invalid") from error
    expected = {
        "artifact_kind",
        "artifact_sha256",
        "contract_version",
        "extension_release_identity_sha256",
        "native_host",
        "release_version",
        "source_trees",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("artifact_kind") != "local_owner_mvp"
        or value.get("contract_version") != "1.0"
        or value.get("native_host") != HOST_NAME
        or value.get("release_version") != RELEASE_VERSION
        or not isinstance(value.get("source_trees"), list)
        or not isinstance(value.get("artifact_sha256"), str)
        or not isinstance(value.get("extension_release_identity_sha256"), str)
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact manifest is invalid")
    basis = {
        key: item for key, item in value.items() if key not in {"artifact_sha256", "extension_release_identity_sha256"}
    }
    if canonical_json_sha256(basis) != value["artifact_sha256"]:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact digest is invalid")
    expected_destinations = {destination for _source, destination in _SOURCE_TREES}
    rows = value["source_trees"]
    if (
        len(rows) != len(expected_destinations)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"destination", "source_digest"}
            or row["destination"] not in expected_destinations
            or not isinstance(row["source_digest"], str)
            for row in rows
        )
        or {row["destination"] for row in rows} != expected_destinations
        or {entry.name for entry in target.iterdir()}
        != {Path(destination).parts[0] for destination in expected_destinations} | {"release_manifest.json"}
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact members are invalid")
    extension_identity = target / "extension" / _EXTENSION_RELEASE_IDENTITY
    if (
        extension_identity.is_symlink()
        or not extension_identity.is_file()
        or stat.S_IMODE(extension_identity.stat().st_mode) != 0o600
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged Side Panel identity is invalid")
    try:
        identity_value = json.loads(extension_identity.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged Side Panel identity is invalid") from error
    expected_identity = {"artifact_sha256": value["artifact_sha256"], "schema_version": "1.0"}
    if (
        identity_value != expected_identity
        or canonical_json_sha256(identity_value) != value["extension_release_identity_sha256"]
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged Side Panel identity drifted")
    for row in rows:
        excluded = frozenset({_EXTENSION_RELEASE_IDENTITY}) if row["destination"] == "extension" else frozenset()
        if _directory_digest(target / row["destination"], excluded_relative_paths=excluded) != row["source_digest"]:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact content drifted")
    return value


def _read_prearm_manifest(target: Path) -> dict[str, Any]:
    manifest = target / _PREARM_MANIFEST
    if (
        target.is_symlink()
        or not target.is_dir()
        or stat.S_IMODE(target.stat().st_mode) != 0o700
        or manifest.is_symlink()
        or not manifest.is_file()
        or stat.S_IMODE(manifest.stat().st_mode) != 0o600
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Pre-arm Side Panel bundle is unsafe")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel manifest is invalid") from error
    expected = {"artifact_kind", "artifact_sha256", "contract_version", "native_host", "source_trees"}
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("artifact_kind") != _PREARM_ARTIFACT_KIND
        or value.get("contract_version") != "1.0"
        or value.get("native_host") != HOST_NAME
        or not isinstance(value.get("artifact_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["artifact_sha256"]) is None
        or not isinstance(value.get("source_trees"), list)
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel manifest is invalid")
    basis = {key: item for key, item in value.items() if key != "artifact_sha256"}
    if canonical_json_sha256(basis) != value["artifact_sha256"]:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel digest is invalid")
    expected_destinations = {destination for _source, destination in _SOURCE_TREES}
    rows = value["source_trees"]
    if (
        len(rows) != len(expected_destinations)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"destination", "source_digest"}
            or row["destination"] not in expected_destinations
            or not isinstance(row["source_digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", row["source_digest"]) is None
            for row in rows
        )
        or {row["destination"] for row in rows} != expected_destinations
        or {entry.name for entry in target.iterdir()}
        != {Path(destination).parts[0] for destination in expected_destinations} | {_PREARM_MANIFEST}
        or (target / "extension" / _EXTENSION_RELEASE_IDENTITY).exists()
        or (target / "extension" / _EXTENSION_RELEASE_IDENTITY).is_symlink()
    ):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel members are invalid")
    for row in rows:
        if _directory_digest(target / row["destination"]) != row["source_digest"]:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel content drifted")
    return value


@dataclass(frozen=True)
class BlueGreenReceipt:
    artifact_sha256: str
    current_version: str
    previous_version_present: bool

    def safe_dict(self) -> dict[str, Any]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "current_version": self.current_version,
            "paths_emitted": False,
            "previous_version_present": self.previous_version_present,
            "release_version": RELEASE_VERSION,
        }


@dataclass(frozen=True)
class StagedRelease:
    artifact_sha256: str

    def safe_dict(self) -> dict[str, Any]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "paths_emitted": False,
            "release_version": RELEASE_VERSION,
            "staged": True,
        }


@dataclass(frozen=True)
class PrearmSidePanel:
    """Digest-addressed private bundle for the temporary, non-release bridge."""

    artifact_sha256: str

    def safe_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": _PREARM_ARTIFACT_KIND,
            "artifact_sha256": self.artifact_sha256,
            "paths_emitted": False,
            "prearm": True,
            "release_pointer_changed": False,
        }


class MvpDeploymentManager:
    """Stage, install and switch one direct-MVP release atomically enough to roll back."""

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths

    @staticmethod
    def assert_release_source_tagged() -> None:
        """Require the clean, uniquely tagged source identity before a real deploy."""

        owner_input_contract_sha256(verify_source=True)
        status = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain=v1", "--", "."],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if status.returncode != 0 or status.stdout.strip():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP deploy requires a clean release source worktree")
        tags = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "tag", "--points-at", "HEAD"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        release_tags = {line.strip() for line in tags.stdout.splitlines() if line.strip()}
        if tags.returncode != 0 or release_tags != {RELEASE_VERSION}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP deploy requires the unique v0.0.0.1 release tag")

    def stage(self) -> StagedRelease:
        _install, versions, current, previous = _release_layout(self.paths)
        _controlled_link(current, versions=versions)
        _controlled_link(previous, versions=versions)
        target = versions / RELEASE_VERSION
        if target.exists() or target.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Unique MVP release version is already staged")
        staging = versions / f".{RELEASE_VERSION}.x2n-staging-{uuid.uuid4().hex}"
        completed = False
        target_created = False
        try:
            manifest = _source_manifest()
            staging.mkdir(mode=0o700)
            staging.chmod(0o700)
            for source, destination in _SOURCE_TREES:
                _copy_private_release_tree(source, staging / destination)
            for row in manifest["source_trees"]:
                destination = staging / row["destination"]
                if _directory_digest(destination) != row["source_digest"]:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP release staging digest drifted")
            _write_extension_release_identity(staging / "extension", artifact_sha256=manifest["artifact_sha256"])
            _atomic_private_json(staging / "release_manifest.json", manifest)
            _read_staged_manifest(staging)
            os.replace(staging, target)
            target_created = True
            target.chmod(0o700)
            completed = True
            return StagedRelease(artifact_sha256=manifest["artifact_sha256"])
        finally:
            if not completed and (staging.exists() or staging.is_symlink()):
                if staging.is_symlink() or not staging.is_dir():
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release staging became unsafe")
                shutil.rmtree(staging)
            if not completed and target_created and (target.exists() or target.is_symlink()):
                _read_staged_manifest(target)
                shutil.rmtree(target)

    def stage_prearm_sidepanel(self) -> PrearmSidePanel:
        """Create an idempotent owner-private pre-arm bundle without staging a release."""

        manifest = _prearm_source_manifest()
        bundles = _prearm_layout(self.paths)
        target = bundles / manifest["artifact_sha256"]
        if target.exists() or target.is_symlink():
            existing = _read_prearm_manifest(target)
            if existing["artifact_sha256"] != manifest["artifact_sha256"]:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel identity drifted")
            return PrearmSidePanel(artifact_sha256=manifest["artifact_sha256"])
        staging = bundles / f".{manifest['artifact_sha256']}.x2n-staging-{uuid.uuid4().hex}"
        completed = False
        target_created = False
        try:
            staging.mkdir(mode=0o700)
            staging.chmod(0o700)
            for source, destination in _SOURCE_TREES:
                _copy_private_release_tree(source, staging / destination)
            for row in manifest["source_trees"]:
                if _directory_digest(staging / row["destination"]) != row["source_digest"]:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel staging digest drifted")
            _atomic_private_json(staging / _PREARM_MANIFEST, manifest)
            _read_prearm_manifest(staging)
            if _prearm_source_manifest()["artifact_sha256"] != manifest["artifact_sha256"]:
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel source changed during staging"
                )
            os.replace(staging, target)
            target_created = True
            target.chmod(0o700)
            completed = True
            return PrearmSidePanel(artifact_sha256=manifest["artifact_sha256"])
        finally:
            if not completed and (staging.exists() or staging.is_symlink()):
                if staging.is_symlink() or not staging.is_dir():
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Pre-arm Side Panel staging became unsafe")
                shutil.rmtree(staging)
            if not completed and target_created and (target.exists() or target.is_symlink()):
                _read_prearm_manifest(target)
                shutil.rmtree(target)

    def _prearm_target(self, staged: PrearmSidePanel) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", staged.artifact_sha256) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Pre-arm Side Panel identity is invalid")
        target = _prearm_layout(self.paths) / staged.artifact_sha256
        manifest = _read_prearm_manifest(target)
        if manifest["artifact_sha256"] != staged.artifact_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pre-arm Side Panel identity drifted")
        return target

    def prearm_extension_directory(self, staged: PrearmSidePanel) -> Path:
        """Return the verified private extension directory without emitting it publicly."""

        return self._prearm_target(staged) / "extension"

    def prearm_native_host_plan(self, *, browser: str, home: Path, env: Mapping[str, str], staged: PrearmSidePanel):
        """Build the matching temporary Host plan from the same private bundle."""

        target = self._prearm_target(staged)
        return create_plan(
            action="install",
            browser=browser,
            home=home,
            env=env,
            release_source_root=target,
            release_artifact_sha256=staged.artifact_sha256,
        )

    def install_prearm_native_host(
        self,
        *,
        confirmation: str,
        browser: str,
        staged: PrearmSidePanel,
    ) -> dict[str, Any]:
        """Install one owner-confirmed pre-arm Host without creating a release."""

        if confirmation != PREARM_HOST_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Pre-arm Native Host install confirmation is missing")
        plan = self.prearm_native_host_plan(browser=browser, home=Path.home(), env=os.environ, staged=staged)
        if any(
            path.exists() or path.is_symlink() for path in (plan.runtime_path, plan.launcher_path, plan.manifest_path)
        ):
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED,
                "Pre-arm Native Host will not overwrite an existing Host; uninstall the owned bridge first",
            )
        receipt = execute_plan(plan, confirmation=INSTALL_CONFIRMATION)
        if receipt.get("status") != "INSTALLED":
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Pre-arm Native Host installation did not complete")
        binding = verify_release_installation(plan, release_artifact_sha256=staged.artifact_sha256)
        return {
            "native_host_prearm_bound": binding["native_host_release_bound"],
            "native_host_prearm_installed": True,
            "native_host_transaction": "atomic_or_rolled_back",
            "paths_emitted": False,
            "release_pointer_changed": False,
        }

    def switch(self, staged: StagedRelease) -> BlueGreenReceipt:
        _install, versions, current, previous = _release_layout(self.paths)
        old_current = _controlled_link(current, versions=versions)
        old_previous = _controlled_link(previous, versions=versions)
        target = versions / RELEASE_VERSION
        manifest = _read_staged_manifest(target)
        if manifest["artifact_sha256"] != staged.artifact_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact identity drifted")
        if _source_manifest()["artifact_sha256"] != staged.artifact_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP source changed after staging")
        try:
            _replace_link(previous, target_name=old_current)
            _replace_link(current, target_name=RELEASE_VERSION)
        except Exception as error:
            try:
                _replace_link(current, target_name=old_current)
                _replace_link(previous, target_name=old_previous)
            except Exception as recovery_error:
                raise X2NRuntimeError(
                    ErrorCode.POLICY_BLOCKED,
                    "MVP release pointer transaction requires manual recovery",
                ) from recovery_error
            if isinstance(error, X2NRuntimeError):
                raise
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP release pointer switch rolled back") from error
        return BlueGreenReceipt(
            artifact_sha256=staged.artifact_sha256,
            current_version=RELEASE_VERSION,
            previous_version_present=old_current is not None,
        )

    def discard_staged(self) -> None:
        _install, versions, current, previous = _release_layout(self.paths)
        if (
            _controlled_link(current, versions=versions) == RELEASE_VERSION
            or _controlled_link(previous, versions=versions) == RELEASE_VERSION
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Active MVP staged artifact cannot be discarded")
        target = versions / RELEASE_VERSION
        if not target.exists() and not target.is_symlink():
            return
        _read_staged_manifest(target)
        shutil.rmtree(target)

    def stage_and_switch(self) -> BlueGreenReceipt:
        """Compatibility helper for isolated release-pointer tests only."""

        return self.switch(self.stage())

    def rollback_pointer(self) -> dict[str, Any]:
        _install, versions, current, previous = _release_layout(self.paths)
        current_version = _controlled_link(current, versions=versions)
        previous_version = _controlled_link(previous, versions=versions)
        if current_version is None:
            return {
                "current_version": "disabled",
                "paths_emitted": False,
                "release_version": RELEASE_VERSION,
                "rollback_pointer_switched": False,
            }
        if current_version != RELEASE_VERSION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Current staged release cannot be rolled back")
        if previous_version is None:
            _replace_link(current, target_name=None)
            return {
                "current_version": "disabled",
                "paths_emitted": False,
                "release_version": RELEASE_VERSION,
                "rollback_pointer_switched": False,
            }
        try:
            _replace_link(current, target_name=previous_version)
            _replace_link(previous, target_name=RELEASE_VERSION)
        except Exception as error:
            try:
                _replace_link(current, target_name=RELEASE_VERSION)
                _replace_link(previous, target_name=previous_version)
            except Exception as recovery_error:
                raise X2NRuntimeError(
                    ErrorCode.POLICY_BLOCKED,
                    "MVP rollback pointer transaction requires manual recovery",
                ) from recovery_error
            if isinstance(error, X2NRuntimeError):
                raise
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP rollback pointer switch rolled back") from error
        return {
            "current_version": previous_version,
            "paths_emitted": False,
            "release_version": RELEASE_VERSION,
            "rollback_pointer_switched": True,
        }

    def _staged_target(self, staged: StagedRelease) -> Path:
        _install, versions, _current, _previous = _release_layout(self.paths)
        target = versions / RELEASE_VERSION
        manifest = _read_staged_manifest(target)
        if manifest["artifact_sha256"] != staged.artifact_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "MVP staged artifact identity drifted")
        return target

    def install_native_host(self, *, confirmation: str, browser: str, staged: StagedRelease) -> dict[str, Any]:
        if confirmation != DEPLOY_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP deployment confirmation is missing")
        target = self._staged_target(staged)
        plan = create_plan(
            action="install",
            browser=browser,
            home=Path.home(),
            env=os.environ,
            release_source_root=target,
            release_artifact_sha256=staged.artifact_sha256,
        )
        if any(
            path.exists() or path.is_symlink() for path in (plan.runtime_path, plan.launcher_path, plan.manifest_path)
        ):
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED,
                "MVP deploy will not overwrite an existing Native Host; migrate it in a separate owner task",
            )
        receipt = execute_plan(plan, confirmation=INSTALL_CONFIRMATION)
        if receipt.get("status") != "INSTALLED":
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Native Host installation did not complete")
        return {
            "native_host_installed": True,
            "native_host_transaction": "atomic_or_rolled_back",
            "paths_emitted": False,
            **verify_release_installation(plan, release_artifact_sha256=staged.artifact_sha256),
        }

    def verify_native_host_artifact(self, *, browser: str, artifact_sha256: str) -> dict[str, Any]:
        staged = StagedRelease(artifact_sha256=artifact_sha256)
        target = self._staged_target(staged)
        plan = create_plan(
            action="uninstall",
            browser=browser,
            home=Path.home(),
            env={},
            release_source_root=target,
            release_artifact_sha256=artifact_sha256,
        )
        return verify_release_installation(plan, release_artifact_sha256=artifact_sha256)

    def uninstall_native_host(self, *, browser: str | None) -> dict[str, Any]:
        if browser is None:
            return {"native_host_uninstalled": False, "paths_emitted": False, "rollback_target": "disabled"}
        plan = create_plan(action="uninstall", browser=browser, home=Path.home(), env={})
        if not any(
            path.exists() or path.is_symlink() for path in (plan.runtime_path, plan.launcher_path, plan.manifest_path)
        ):
            return {"native_host_uninstalled": False, "paths_emitted": False, "rollback_target": "disabled"}
        receipt = execute_plan(plan, confirmation=UNINSTALL_CONFIRMATION)
        if receipt.get("status") != "UNINSTALLED":
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Native Host rollback did not complete")
        return {"native_host_uninstalled": True, "paths_emitted": False, "rollback_target": "disabled"}

    def deploy(self, *, confirmation: str, browser: str) -> dict[str, Any]:
        """Do not switch `current` unless the fresh Native Host install completed."""

        self.assert_release_source_tagged()
        staged = self.stage()
        installed = False
        switched = False
        try:
            installed_receipt = self.install_native_host(confirmation=confirmation, browser=browser, staged=staged)
            installed = True
            switched_receipt = self.switch(staged)
            switched = True
            return {**staged.safe_dict(), **switched_receipt.safe_dict(), **installed_receipt}
        except Exception as error:
            cleanup_failed = False
            if installed:
                try:
                    self.uninstall_native_host(browser=browser)
                except X2NRuntimeError:
                    cleanup_failed = True
            if switched:
                try:
                    self.rollback_pointer()
                except X2NRuntimeError:
                    cleanup_failed = True
            else:
                try:
                    self.discard_staged()
                except X2NRuntimeError:
                    cleanup_failed = True
            if cleanup_failed:
                raise X2NRuntimeError(
                    ErrorCode.POLICY_BLOCKED, "MVP deployment rollback cleanup is incomplete"
                ) from error
            if isinstance(error, X2NRuntimeError):
                raise
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP deployment transaction failed") from error

    def rollback_deployment(self, *, browser: str | None) -> dict[str, Any]:
        """Disable the installed Host before moving the staged extension pointer."""

        native_host = self.uninstall_native_host(browser=browser)
        pointer = self.rollback_pointer()
        return {"native_host": native_host, "pointer": pointer, "paths_emitted": False}

    def verify_current_artifact(self) -> dict[str, Any]:
        """Verify the active staged artifact is source-only and exactly manifest-bound."""

        _install, versions, current, _previous = _release_layout(self.paths)
        if _controlled_link(current, versions=versions) != RELEASE_VERSION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP staged release is not current")
        target = versions / RELEASE_VERSION
        manifest = _read_staged_manifest(target)
        return {
            "artifact_sha256": manifest["artifact_sha256"],
            "runtime_data_files": 0,
            "source_only_artifact": True,
            "paths_emitted": False,
        }

    def online_smoke(
        self,
        *,
        confirmation: str,
        browser: str,
        controller: MvpReleaseController,
    ) -> dict[str, Any]:
        if confirmation != ONLINE_SMOKE_CONFIRMATION:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP online-smoke confirmation is missing")
        if controller.state["deployment"]["browser"] != browser:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP online-smoke browser differs from deployment")
        artifact = self.verify_current_artifact()
        native_host = self.verify_native_host_artifact(browser=browser, artifact_sha256=artifact["artifact_sha256"])
        browser_handshake = controller.verify_browser_handshake()
        plan = create_plan(action="uninstall", browser=browser, home=Path.home(), env={})
        if not plan.launcher_path.is_file() or plan.launcher_path.is_symlink():
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Installed Native Host launcher is unavailable")
        payload = {"action": "health", "payload": {}}
        payload["payload_hash"] = canonical_json_sha256(payload["payload"])
        payload["request_id"] = str(uuid.uuid4())
        payload["schema_version"] = "1.0"
        payload["sent_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        frame = len(raw).to_bytes(4, byteorder=sys.byteorder, signed=False) + raw
        try:
            result = subprocess.run(
                [str(plan.launcher_path), DEVELOPMENT_EXTENSION_ORIGIN],
                input=frame,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Native Host online smoke could not start") from error
        if result.returncode != 0 or len(result.stdout) < 4:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Native Host online smoke failed")
        size = int.from_bytes(result.stdout[:4], byteorder=sys.byteorder, signed=False)
        if size != len(result.stdout) - 4:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Native Host online smoke response is malformed")
        try:
            response = json.loads(result.stdout[4:].decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise X2NRuntimeError(
                ErrorCode.DATA_INTEGRITY_FAILED, "Native Host online smoke response is invalid"
            ) from error
        if (
            not isinstance(response, Mapping)
            or response.get("accepted") is not True
            or response.get("status") != "completed"
            or response.get("error") is not None
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Native Host online smoke was rejected")
        return {
            "browser_extension_package": "sidepanel_native_handshake",
            **browser_handshake,
            "native_host_health": "PASS",
            **native_host,
            "paths_emitted": False,
            "platform_calls": 0,
            "runtime_online": True,
        }
