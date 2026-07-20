"""Fail-closed user-level Native Host installer with a plan-only default."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode

from .native_host import DEVELOPMENT_EXTENSION_ORIGIN, HOST_NAME
from .runtime import DOWNLOAD_ENV, ROOT_ENV, RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
INSTALL_CONFIRMATION = "INSTALL_X2N_NATIVE_HOST"
UNINSTALL_CONFIRMATION = "UNINSTALL_X2N_NATIVE_HOST"
LAUNCHER_MARKER = "# x2n-owned-native-host-v1"
BUNDLE_MARKER_NAME = ".x2n-native-host-owned.json"
RUNTIME_REQUIREMENTS = (
    "annotated-types==0.7.0",
    "pydantic==2.13.4",
    "pydantic-core==2.46.4",
    "typing-extensions==4.16.0",
    "typing-inspection==0.4.2",
)
BROWSER_DIRECTORIES = {
    "chrome": Path("Library/Application Support/Google/Chrome/NativeMessagingHosts"),
    "chrome-for-testing": Path("Library/Application Support/Google/ChromeForTesting/NativeMessagingHosts"),
    "chromium": Path("Library/Application Support/Chromium/NativeMessagingHosts"),
}


@dataclass(frozen=True)
class InstallPlan:
    action: str
    browser: str
    launcher_path: Path
    manifest_path: Path
    runtime_path: Path
    bundle_marker_path: Path
    uv_path: Path | None
    launcher_content: str | None
    manifest_content: str | None

    def safe_summary(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "browser": self.browser,
            "launcher_present": self.launcher_path.is_file(),
            "manifest_present": self.manifest_path.is_file(),
            "runtime_present": self.runtime_path.is_dir(),
            "paths_emitted": False,
            "scope": "user_level_only",
        }


def _known_paths(*, home: Path, browser: str) -> tuple[Path, Path, Path, Path]:
    if browser not in BROWSER_DIRECTORIES:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Browser selection is unsupported")
    host_root = home / "Library/Application Support/x2n/native-host"
    launcher = host_root / "x2n-native-host"
    manifest = home / BROWSER_DIRECTORIES[browser] / f"{HOST_NAME}.json"
    runtime = host_root / "runtime"
    return launcher, manifest, runtime, runtime / BUNDLE_MARKER_NAME


def _launcher_content(*, runtime_python: Path, data_root: str, download_destination: str) -> str:
    command = " ".join(
        shlex.quote(value)
        for value in (
            str(runtime_python),
            "-B",
            "-m",
            "x2n_companion.native_host",
        )
    )
    private_home = runtime_python.parents[2]
    return (
        "#!/bin/sh\n"
        f"{LAUNCHER_MARKER}\n"
        "set -eu\n"
        "exec /usr/bin/env -i "
        f"HOME={shlex.quote(str(private_home))} "
        "LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONNOUSERSITE=1 "
        f"{ROOT_ENV}={shlex.quote(data_root)} "
        f"{DOWNLOAD_ENV}={shlex.quote(download_destination)} "
        f"{command} \"$@\"\n"
    )


def _manifest_content(*, launcher: Path) -> str:
    return json.dumps(
        {
            "allowed_origins": [DEVELOPMENT_EXTENSION_ORIGIN],
            "description": "x2n local companion development host",
            "name": HOST_NAME,
            "path": str(launcher),
            "type": "stdio",
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def create_plan(
    *,
    action: str,
    browser: str,
    home: Path,
    env: Mapping[str, str],
    uv_path: Path | None = None,
) -> InstallPlan:
    if action not in {"plan", "install", "uninstall"}:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Installer action is unsupported")
    launcher, manifest, runtime, bundle_marker = _known_paths(home=home, browser=browser)
    if action == "uninstall":
        return InstallPlan(action, browser, launcher, manifest, runtime, bundle_marker, None, None, None)

    resolved_uv = uv_path or (Path(value) if (value := shutil.which("uv")) else None)
    if (
        resolved_uv is None
        or not resolved_uv.is_absolute()
        or not resolved_uv.is_file()
        or not os.access(resolved_uv, os.X_OK)
    ):
        raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "uv executable is unavailable")
    paths = RuntimePaths.from_environment(env, repository_root=PROJECT_ROOT, create=False)
    launcher_content = _launcher_content(
        runtime_python=runtime / "bin/python",
        data_root=str(paths.data_root),
        download_destination=str(paths.download_destination),
    )
    return InstallPlan(
        action,
        browser,
        launcher,
        manifest,
        runtime,
        bundle_marker,
        resolved_uv,
        launcher_content,
        _manifest_content(launcher=launcher),
    )


def _ensure_directory(path: Path, *, private: bool) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer destination is unsafe")
        return
    path.mkdir(parents=True, mode=0o700 if private else 0o755)
    if private:
        path.chmod(0o700)


def _stage_write(path: Path, content: str, mode: int) -> Path:
    if path.is_symlink():
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses symbolic-link destinations")
    temporary = path.with_name(f".{path.name}.x2n-{uuid.uuid4().hex}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        return temporary
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _atomic_write(path: Path, content: str, mode: int) -> None:
    temporary = _stage_write(path, content, mode)
    try:
        os.replace(temporary, path)
        path.chmod(mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle_receipt(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    expected = {
        "host": HOST_NAME,
        "owner": "x2n-native-host-installer",
        "runtime_requirements": list(RUNTIME_REQUIREMENTS),
        "schema_version": "1.1",
    }
    if not isinstance(value, dict) or any(value.get(key) != expected_value for key, expected_value in expected.items()):
        return None
    if set(value) != set(expected) | {"launcher_sha256", "manifest_sha256"}:
        return None
    if any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(key, ""))) is None for key in ("launcher_sha256", "manifest_sha256")):
        return None
    return value


def _owned_manifest(path: Path, launcher: Path, receipt: Mapping[str, Any]) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        digest_matches = not path.is_symlink() and _file_sha256(path) == receipt.get("manifest_sha256")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return digest_matches and value == {
        "allowed_origins": [DEVELOPMENT_EXTENSION_ORIGIN],
        "description": "x2n local companion development host",
        "name": HOST_NAME,
        "path": str(launcher),
        "type": "stdio",
    }


def _owned_launcher(path: Path, receipt: Mapping[str, Any]) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
        return (
            path.is_file()
            and not path.is_symlink()
            and content.splitlines()[:2] == ["#!/bin/sh", LAUNCHER_MARKER]
            and _file_sha256(path) == receipt.get("launcher_sha256")
        )
    except (OSError, UnicodeDecodeError):
        return False


def _bundle_marker_content(*, launcher_content: str, manifest_content: str) -> str:
    return json.dumps(
        {
            "host": HOST_NAME,
            "launcher_sha256": hashlib.sha256(launcher_content.encode("utf-8")).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_content.encode("utf-8")).hexdigest(),
            "owner": "x2n-native-host-installer",
            "runtime_requirements": list(RUNTIME_REQUIREMENTS),
            "schema_version": "1.1",
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _owned_bundle(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and _bundle_receipt(path) is not None


def _run_provision(command: list[str], *, env: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=120,
    )
    if result.returncode != 0:
        raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Native Host private runtime could not be provisioned")


def _provision_runtime(plan: InstallPlan) -> Path:
    if plan.uv_path is None:
        raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "uv executable is unavailable")
    if plan.launcher_content is None or plan.manifest_content is None:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer payload is incomplete")
    if plan.runtime_path.exists() or plan.runtime_path.is_symlink():
        if (
            plan.runtime_path.is_symlink()
            or not plan.runtime_path.is_dir()
            or not _owned_bundle(plan.bundle_marker_path)
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses to replace an unowned runtime")
    staging_path = plan.runtime_path.with_name(f".{plan.runtime_path.name}.x2n-staging-{uuid.uuid4().hex}")
    cache_path = staging_path.with_name(f"{staging_path.name}-uv-cache")
    completed = False
    environment = {
        "HOME": str(plan.runtime_path.parent),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "UV_CACHE_DIR": str(cache_path),
        "UV_INDEX_URL": "https://pypi.org/simple",
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_NO_CONFIG": "1",
    }
    try:
        _run_provision(
            [str(plan.uv_path), "venv", "--python", sys.executable, str(staging_path)],
            env=environment,
        )
        runtime_python = staging_path / "bin/python"
        requirements_path = staging_path / ".x2n-locked-requirements.txt"
        _run_provision(
            [
                str(plan.uv_path),
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-emit-workspace",
                "--package",
                "x2n-companion",
                "--output-file",
                str(requirements_path),
            ],
            env=environment,
        )
        requirements = requirements_path.read_text(encoding="utf-8")
        locked_requirements = dict(re.findall(r"(?m)^([a-z0-9-]+)==([0-9][^ \\\n]+)", requirements))
        expected_requirements = dict(item.split("==", 1) for item in RUNTIME_REQUIREMENTS)
        if locked_requirements != expected_requirements or requirements.count("--hash=sha256:") < len(locked_requirements):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Native Host locked requirements are incomplete")
        _run_provision(
            [
                str(plan.uv_path),
                "pip",
                "install",
                "--python",
                str(runtime_python),
                "--no-deps",
                "--require-hashes",
                "-r",
                str(requirements_path),
            ],
            env=environment,
        )
        requirements_path.unlink()
        probe = subprocess.run(
            [str(runtime_python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode != 0 or len(probe.stdout.splitlines()) != 1:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Native Host private runtime is invalid")
        site_packages = Path(probe.stdout.strip()).resolve(strict=True)
        try:
            site_packages.relative_to(staging_path.resolve(strict=True))
        except ValueError as error:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Native Host runtime escaped its private bundle") from error
        for package_name, source in (
            ("x2n_companion", PROJECT_ROOT / "apps/companion/src/x2n_companion"),
            ("x2n_contracts", PROJECT_ROOT / "packages/contracts/src/x2n_contracts"),
        ):
            shutil.copytree(
                source,
                site_packages / package_name,
                dirs_exist_ok=False,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        validation = subprocess.run(
            [str(runtime_python), "-B", "-c", "import pydantic, x2n_companion.native_host, x2n_contracts"],
            cwd=staging_path,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        if validation.returncode != 0:
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Native Host private runtime validation failed")
        _atomic_write(
            staging_path / BUNDLE_MARKER_NAME,
            _bundle_marker_content(
                launcher_content=plan.launcher_content,
                manifest_content=plan.manifest_content,
            ),
            0o600,
        )
        completed = True
        return staging_path
    finally:
        if not completed and staging_path.exists():
            if staging_path.is_symlink() or not staging_path.is_dir():
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer staging destination became unsafe")
            shutil.rmtree(staging_path)
        if cache_path.exists():
            if cache_path.is_symlink() or not cache_path.is_dir():
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer cache destination became unsafe")
            shutil.rmtree(cache_path)


def _remove_transaction_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _transaction_residuals(plan: InstallPlan) -> list[Path]:
    destinations = (plan.runtime_path, plan.launcher_path, plan.manifest_path)
    return [
        candidate
        for destination in destinations
        for candidate in destination.parent.glob(f".{destination.name}.x2n-*")
    ]


def _commit_install(plan: InstallPlan, runtime_staging: Path) -> None:
    if plan.launcher_content is None or plan.manifest_content is None:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer payload is incomplete")
    launcher_staging: Path | None = None
    manifest_staging: Path | None = None
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    try:
        launcher_staging = _stage_write(plan.launcher_path, plan.launcher_content, 0o700)
        manifest_staging = _stage_write(plan.manifest_path, plan.manifest_content, 0o600)
        destinations = (plan.runtime_path, plan.launcher_path, plan.manifest_path)
        for destination in destinations:
            if destination.exists() or destination.is_symlink():
                backup = destination.with_name(f".{destination.name}.x2n-backup-{uuid.uuid4().hex}")
                os.replace(destination, backup)
                backups[destination] = backup
        for staging, destination in (
            (runtime_staging, plan.runtime_path),
            (launcher_staging, plan.launcher_path),
            (manifest_staging, plan.manifest_path),
        ):
            os.replace(staging, destination)
            committed.append(destination)
        plan.launcher_path.chmod(0o700)
        plan.manifest_path.chmod(0o600)
    except Exception as error:
        rollback_errors = 0
        for destination in reversed(committed):
            try:
                if destination.exists() or destination.is_symlink():
                    _remove_transaction_path(destination)
            except OSError:
                rollback_errors += 1
        for destination, backup in reversed(tuple(backups.items())):
            try:
                if backup.exists() or backup.is_symlink():
                    os.replace(backup, destination)
            except OSError:
                rollback_errors += 1
        if rollback_errors:
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED,
                "Native Host install transaction requires manual recovery",
            ) from error
        if isinstance(error, X2NRuntimeError):
            raise
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Native Host install transaction rolled back") from error
    else:
        cleanup_errors = 0
        for backup in backups.values():
            try:
                _remove_transaction_path(backup)
            except OSError:
                cleanup_errors += 1
        if cleanup_errors:
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED,
                "Native Host install completed but retired files require manual cleanup",
            )
    finally:
        for staging in (runtime_staging, launcher_staging, manifest_staging):
            if staging is not None and (staging.exists() or staging.is_symlink()):
                _remove_transaction_path(staging)


def execute_plan(plan: InstallPlan, *, confirmation: str | None) -> dict[str, Any]:
    if plan.action == "plan":
        return {**plan.safe_summary(), "status": "PLAN_ONLY"}
    if plan.action == "install":
        if confirmation != INSTALL_CONFIRMATION or plan.launcher_content is None or plan.manifest_content is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Native Host install confirmation is missing")
        _ensure_directory(plan.launcher_path.parent, private=True)
        _ensure_directory(plan.manifest_path.parent, private=False)
        if any(path.is_symlink() for path in (plan.runtime_path, plan.launcher_path, plan.manifest_path)):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses symbolic-link destinations")
        receipt = _bundle_receipt(plan.bundle_marker_path)
        if (plan.runtime_path.exists() or plan.launcher_path.exists() or plan.manifest_path.exists()) and receipt is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses an incomplete or unowned installation")
        if plan.launcher_path.exists() and (
            receipt is None or not _owned_launcher(plan.launcher_path, receipt)
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses to replace an unowned launcher")
        if plan.manifest_path.exists() and (
            receipt is None or not _owned_manifest(plan.manifest_path, plan.launcher_path, receipt)
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses to replace an unowned manifest")
        if _transaction_residuals(plan):
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED,
                "Installer requires review of an interrupted install transaction",
            )
        runtime_staging = _provision_runtime(plan)
        _commit_install(plan, runtime_staging)
        return {**plan.safe_summary(), "status": "INSTALLED"}
    if confirmation != UNINSTALL_CONFIRMATION:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Native Host uninstall confirmation is missing")
    if _transaction_residuals(plan):
        raise X2NRuntimeError(
            ErrorCode.POLICY_BLOCKED,
            "Installer requires review of an interrupted install transaction",
        )
    receipt = _bundle_receipt(plan.bundle_marker_path)
    if (plan.runtime_path.exists() or plan.launcher_path.exists() or plan.manifest_path.exists()) and receipt is None:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses an incomplete or unowned installation")
    if plan.manifest_path.exists() and (
        receipt is None or not _owned_manifest(plan.manifest_path, plan.launcher_path, receipt)
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses to remove an unowned manifest")
    if plan.launcher_path.exists() and (
        receipt is None or not _owned_launcher(plan.launcher_path, receipt)
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses to remove an unowned launcher")
    if (plan.runtime_path.exists() or plan.bundle_marker_path.exists()) and (
        plan.runtime_path.is_symlink() or not _owned_bundle(plan.bundle_marker_path)
    ):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Installer refuses to remove an unowned runtime")
    if plan.manifest_path.exists():
        plan.manifest_path.unlink()
    if plan.launcher_path.exists():
        plan.launcher_path.unlink()
    if plan.runtime_path.exists():
        shutil.rmtree(plan.runtime_path)
    if plan.bundle_marker_path.exists():
        plan.bundle_marker_path.unlink()
    return {**plan.safe_summary(), "status": "UNINSTALLED"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or manage the user-level x2n Native Host")
    parser.add_argument("action", choices=("plan", "install", "uninstall"), nargs="?", default="plan")
    parser.add_argument("--browser", choices=tuple(BROWSER_DIRECTORIES), default="chrome")
    parser.add_argument("--confirm")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = create_plan(
            action=args.action,
            browser=args.browser,
            home=Path.home(),
            env=os.environ,
        )
        result = execute_plan(plan, confirmation=args.confirm)
    except X2NRuntimeError as error:
        result = {
            "code": error.code.value,
            "paths_emitted": False,
            "safe_message": error.safe_message,
            "status": "FAIL_CLOSED",
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
