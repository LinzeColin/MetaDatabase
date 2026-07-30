"""Dedicated Browser Profile, session-health and Doctor primitives.

Browser state remains entirely inside the Owner-selected Private Runtime.  The
public API returns logical references and stable enums only; it never reads or
exports Chrome cookies, accepts a caller-selected executable/path/URL, or
automates login and verification challenges.
"""

from __future__ import annotations

import json
import os
import platform as os_platform
import shutil
import stat
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from x2n_contracts import ERROR_SPECS, ErrorCode
from x2n_contracts.models import (
    ErrorContract,
    HealthComponent,
    HealthComponentName,
    HealthReport,
    HealthState,
)

from .runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError, _atomic_private_json


TASK_ID = "TSK.x2n.adapters.001"
PROFILE_LAUNCH_CONFIRMATION = "MANUAL_LOGIN_ONLY_NO_AUTOMATION"
SESSION_CHECKPOINT_NAME = "adapter-session-health.json"
SESSION_TTL_SECONDS = 300
SESSION_FUTURE_SKEW_SECONDS = 30
SessionSignal = Literal[
    "authenticated",
    "login_required",
    "expired",
    "verification_required",
    "platform_changed",
]

SESSION_SIGNALS = {
    "authenticated",
    "login_required",
    "expired",
    "verification_required",
    "platform_changed",
}

KNOWN_CHROME_EXECUTABLES: dict[str, tuple[Path, ...]] = {
    "Darwin": (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ),
    "Linux": (
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
    ),
    "Windows": (
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Session time must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_rfc3339(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health time is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health time is invalid") from error
    return parsed.astimezone(timezone.utc)


def _platform(value: str) -> str:
    if value not in PROFILE_PLATFORMS:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Session platform is unsupported")
    return value


@dataclass(frozen=True)
class ProfileLaunchPlan:
    """Private launch arguments plus a redacted public view."""

    platform: str
    executable: Path
    profile_directory: Path
    argv: tuple[str, ...]

    def safe_dict(self, *, launched: bool) -> dict[str, Any]:
        return {
            "account_state_changed_by_x2n": False,
            "arbitrary_path_accepted": False,
            "arbitrary_url_accepted": False,
            "browser": "chrome",
            "cookie_exported": False,
            "launched": launched,
            "login_automated": False,
            "platform": self.platform,
            "profile_path_emitted": False,
            "profile_ref": f"browser_profile_{self.platform}",
            "remote_debugging_enabled": False,
            "verification_bypass": False,
        }


def _resolve_known_chrome() -> Path:
    candidates = KNOWN_CHROME_EXECUTABLES.get(os_platform.system(), ())
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Supported local Chrome executable is unavailable")


def _start_chrome(argv: Sequence[str]) -> object:
    return subprocess.Popen(
        tuple(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


class ProfileLauncher:
    """Launch one fixed, Runtime-contained Profile without login automation."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        executable_resolver: Callable[[], Path] = _resolve_known_chrome,
        starter: Callable[[Sequence[str]], object] = _start_chrome,
    ) -> None:
        self.paths = paths
        self._executable_resolver = executable_resolver
        self._starter = starter

    def build_plan(self, platform: str) -> ProfileLaunchPlan:
        platform = _platform(platform)
        profile = self.paths.browser_profile_directory(platform)
        executable = self._executable_resolver()
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "Supported local Chrome executable is unavailable")
        argv = (
            str(executable),
            f"--user-data-dir={profile}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--new-window",
            "chrome://newtab/",
        )
        return ProfileLaunchPlan(platform, executable, profile, argv)

    def plan(self, platform: str) -> dict[str, Any]:
        return self.build_plan(platform).safe_dict(launched=False)

    def launch(self, platform: str, *, confirmation: str) -> dict[str, Any]:
        if confirmation != PROFILE_LAUNCH_CONFIRMATION:
            raise X2NRuntimeError(
                ErrorCode.POLICY_BLOCKED, "Profile launch requires explicit manual-login confirmation"
            )
        plan = self.build_plan(platform)
        try:
            self._starter(plan.argv)
        except OSError as error:
            raise X2NRuntimeError(
                ErrorCode.DEPENDENCY_MISSING, "Dedicated Browser Profile could not be opened"
            ) from error
        return plan.safe_dict(launched=True)


@dataclass(frozen=True)
class SessionHealth:
    platform: str
    state: Literal["ok", "blocked"]
    reason: str
    error_code: ErrorCode | None
    safe_action: str | None
    observation_fresh: bool

    def safe_dict(self) -> dict[str, Any]:
        return {
            "cookie_read": False,
            "error_code": None if self.error_code is None else self.error_code.value,
            "observation_fresh": self.observation_fresh,
            "platform": self.platform,
            "profile_path_emitted": False,
            "reason": self.reason,
            "safe_action": self.safe_action,
            "state": self.state,
        }


class SessionHealthStore:
    """Persist only short-lived, credential-free live-probe classifications."""

    def __init__(self, paths: RuntimePaths, *, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        if ttl_seconds < 30 or ttl_seconds > 900:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Session health TTL is outside policy")
        self.paths = paths
        self.ttl_seconds = ttl_seconds
        self.path = paths.checkpoints_directory / SESSION_CHECKPOINT_NAME

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        if self.path.is_symlink() or not self.path.is_file():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Session health checkpoint is unsafe")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(self.path, flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid()
                or metadata.st_size > 65_536
            ):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Session health checkpoint is not owner-only")
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                descriptor = -1
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health checkpoint is invalid") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "sessions"}:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health checkpoint is invalid")
        sessions = payload.get("sessions")
        if payload.get("schema_version") != "1.0" or not isinstance(sessions, dict):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health checkpoint is invalid")
        normalized: dict[str, dict[str, str]] = {}
        for platform, row in sessions.items():
            if platform not in PROFILE_PLATFORMS or not isinstance(row, dict) or set(row) != {"observed_at", "signal"}:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health checkpoint is invalid")
            signal = row.get("signal")
            observed_at = row.get("observed_at")
            if signal not in SESSION_SIGNALS or not isinstance(observed_at, str):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Session health checkpoint is invalid")
            _parse_rfc3339(observed_at)
            normalized[platform] = {"observed_at": observed_at, "signal": signal}
        return normalized

    def record(self, platform: str, signal: SessionSignal, *, observed_at: datetime | None = None) -> SessionHealth:
        platform = _platform(platform)
        if signal not in SESSION_SIGNALS:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Session health signal is unsupported")
        now = _utc_now() if observed_at is None else observed_at
        sessions = self._load()
        sessions[platform] = {"observed_at": _rfc3339(now), "signal": signal}
        _atomic_private_json(self.path, {"schema_version": "1.0", "sessions": sessions})
        return self.evaluate(platform, now=now)

    def evaluate(self, platform: str, *, now: datetime | None = None) -> SessionHealth:
        platform = _platform(platform)
        current = _utc_now() if now is None else now.astimezone(timezone.utc)
        row = self._load().get(platform)
        if row is None:
            return SessionHealth(
                platform,
                "blocked",
                "session_observation_missing",
                ErrorCode.ADAPTER_AUTH_EXPIRED,
                "open_dedicated_profile_and_login_manually",
                False,
            )
        observed = _parse_rfc3339(row["observed_at"])
        age = current - observed
        if age > timedelta(seconds=self.ttl_seconds) or age < -timedelta(seconds=SESSION_FUTURE_SKEW_SECONDS):
            return SessionHealth(
                platform,
                "blocked",
                "session_observation_stale",
                ErrorCode.ADAPTER_AUTH_EXPIRED,
                "open_dedicated_profile_and_login_manually",
                False,
            )
        signal = row["signal"]
        if signal == "authenticated":
            return SessionHealth(platform, "ok", "authenticated_live_probe", None, None, True)
        if signal == "platform_changed":
            return SessionHealth(
                platform,
                "blocked",
                "platform_changed",
                ErrorCode.PLATFORM_CHANGED,
                "disable_platform_and_inspect_synthetic_fixture",
                True,
            )
        actions = {
            "login_required": "open_dedicated_profile_and_login_manually",
            "expired": "open_dedicated_profile_and_login_manually",
            "verification_required": "complete_verification_manually_or_leave_adapter_disabled",
        }
        return SessionHealth(platform, "blocked", signal, ErrorCode.ADAPTER_AUTH_EXPIRED, actions[signal], True)

    def evaluate_all(self, *, now: datetime | None = None) -> tuple[SessionHealth, ...]:
        return tuple(self.evaluate(platform, now=now) for platform in PROFILE_PLATFORMS)


DoctorState = Literal["ok", "degraded", "blocked"]


@dataclass(frozen=True)
class DoctorComponentResult:
    component: HealthComponentName
    state: DoctorState
    error_code: ErrorCode | None
    remediation_action: str
    remediation_command: str | None

    def safe_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.value,
            "error_code": None if self.error_code is None else self.error_code.value,
            "remediation": {
                "action": self.remediation_action,
                "command": self.remediation_command,
            },
            "state": self.state,
        }


@dataclass(frozen=True)
class DoctorProbe:
    extension_reachable: bool
    native_host_registered: bool
    companion_reachable: bool
    canonical_db_state: Literal["ok", "busy", "failed"]
    ffmpeg_available: bool
    provider_configured: bool
    notion_authorized: bool
    chrome_available: bool
    sessions: tuple[SessionHealth, ...]


@dataclass(frozen=True)
class DoctorReport:
    observed_at: str
    overall: DoctorState
    components: tuple[DoctorComponentResult, ...]
    health_contract: HealthReport

    def safe_dict(self) -> dict[str, Any]:
        return {
            "components": [item.safe_dict() for item in self.components],
            "health_contract": self.health_contract.model_dump(mode="json", by_alias=True),
            "noncore_missing_disables_canonical": False,
            "observed_at": self.observed_at,
            "overall": self.overall,
            "private_path_emitted": False,
            "schema_version": "1.0",
            "secret_emitted": False,
            "task_id": TASK_ID,
        }


def _component(
    name: HealthComponentName,
    state: DoctorState,
    code: ErrorCode | None,
    action: str,
    command: str | None,
) -> DoctorComponentResult:
    if (state == "ok") != (code is None):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Doctor component state is inconsistent")
    return DoctorComponentResult(name, state, code, action, command)


def _error_contract(code: ErrorCode, component: str) -> ErrorContract:
    spec = ERROR_SPECS[code]
    return ErrorContract.model_validate(
        {
            "schema_version": "1.0",
            "code": code,
            "class": spec.error_class,
            "retryable": spec.retryable,
            "safe_message": spec.default_safe_message,
            "internal_ref": f"evt_doctor_{component}",
            "data_effect": spec.data_effect,
            "next_action": spec.next_action,
        }
    )


def _health_contract(components: tuple[DoctorComponentResult, ...], observed_at: str) -> HealthReport:
    health_components = []
    for component in components:
        state = {
            "ok": HealthState.HEALTHY,
            "degraded": HealthState.DEGRADED,
            "blocked": HealthState.UNAVAILABLE,
        }[component.state]
        health_components.append(
            HealthComponent(
                component=component.component,
                state=state,
                observed_at=observed_at,
                error=None
                if component.error_code is None
                else _error_contract(component.error_code, component.component.value),
            )
        )
    states = {item.state for item in health_components}
    overall = HealthState.HEALTHY if states == {HealthState.HEALTHY} else HealthState.DEGRADED
    return HealthReport(
        schema_version="1.0",
        report_id=f"health_{uuid.uuid4().hex}",
        observed_at=observed_at,
        overall=overall,
        components=tuple(health_components),
    )


def build_doctor_report(probe: DoctorProbe, *, observed_at: datetime | None = None) -> DoctorReport:
    """Build an eight-component report without serializing any discovered path."""

    timestamp = _rfc3339(_utc_now() if observed_at is None else observed_at)
    components: list[DoctorComponentResult] = [
        _component(
            HealthComponentName.EXTENSION,
            "ok" if probe.extension_reachable else "degraded",
            None if probe.extension_reachable else ErrorCode.DEPENDENCY_MISSING,
            "none" if probe.extension_reachable else "reload_extension",
            None if probe.extension_reachable else "x2n doctor",
        ),
        _component(
            HealthComponentName.NATIVE_HOST,
            "ok" if probe.native_host_registered else "blocked",
            None if probe.native_host_registered else ErrorCode.DEPENDENCY_MISSING,
            "none" if probe.native_host_registered else "plan_native_host_install",
            None if probe.native_host_registered else "x2n-native-host-installer plan --browser chrome",
        ),
        _component(
            HealthComponentName.COMPANION,
            "ok" if probe.companion_reachable else "blocked",
            None if probe.companion_reachable else ErrorCode.UNKNOWN_FAILURE,
            "none" if probe.companion_reachable else "restart_companion",
            None if probe.companion_reachable else "x2n doctor",
        ),
    ]
    db_code = (
        None
        if probe.canonical_db_state == "ok"
        else (ErrorCode.STORAGE_FAILED if probe.canonical_db_state == "busy" else ErrorCode.DATA_INTEGRITY_FAILED)
    )
    components.append(
        _component(
            HealthComponentName.CANONICAL_DB,
            "ok" if db_code is None else "blocked",
            db_code,
            "none" if db_code is None else "release_database_lock_and_retry",
            None if db_code is None else "x2n doctor",
        )
    )
    components.extend(
        (
            _component(
                HealthComponentName.FFMPEG,
                "ok" if probe.ffmpeg_available else "degraded",
                None if probe.ffmpeg_available else ErrorCode.DEPENDENCY_MISSING,
                "none" if probe.ffmpeg_available else "install_ffmpeg",
                None if probe.ffmpeg_available else "ffmpeg -version",
            ),
            _component(
                HealthComponentName.PROVIDER,
                "ok" if probe.provider_configured else "degraded",
                None if probe.provider_configured else ErrorCode.PROVIDER_FAILED,
                "none" if probe.provider_configured else "configure_provider_reference_or_keep_disabled",
                None if probe.provider_configured else "x2n doctor",
            ),
            _component(
                HealthComponentName.NOTION,
                "ok" if probe.notion_authorized else "degraded",
                None if probe.notion_authorized else ErrorCode.PROVIDER_FAILED,
                "none" if probe.notion_authorized else "authorize_notion_or_keep_disabled",
                None if probe.notion_authorized else "x2n doctor",
            ),
        )
    )
    blocked_session = next((item for item in probe.sessions if item.state == "blocked"), None)
    session_platforms = [item.platform for item in probe.sessions]
    session_matrix_complete = (
        len(session_platforms) == len(PROFILE_PLATFORMS)
        and len(set(session_platforms)) == len(PROFILE_PLATFORMS)
        and set(session_platforms) == set(PROFILE_PLATFORMS)
    )
    adapter_ok = probe.chrome_available and session_matrix_complete and blocked_session is None
    adapter_code = (
        None
        if adapter_ok
        else (
            ErrorCode.DEPENDENCY_MISSING
            if not probe.chrome_available
            else ErrorCode.DATA_INTEGRITY_FAILED
            if not session_matrix_complete
            else blocked_session.error_code
            if blocked_session is not None
            else ErrorCode.ADAPTER_AUTH_EXPIRED
        )
    )
    adapter_platform = blocked_session.platform if blocked_session is not None else PROFILE_PLATFORMS[0]
    components.append(
        _component(
            HealthComponentName.ADAPTER,
            "ok" if adapter_ok else "blocked",
            adapter_code,
            "none" if adapter_ok else "open_dedicated_profile_and_login_manually",
            None
            if adapter_ok
            else f"x2n profile launch --platform {adapter_platform} --confirm {PROFILE_LAUNCH_CONFIRMATION}",
        )
    )
    rendered = tuple(components)
    core_names = {
        HealthComponentName.NATIVE_HOST,
        HealthComponentName.COMPANION,
        HealthComponentName.CANONICAL_DB,
    }
    if any(item.state == "blocked" and item.component in core_names for item in rendered):
        overall: DoctorState = "blocked"
    elif any(item.state != "ok" for item in rendered):
        overall = "degraded"
    else:
        overall = "ok"
    return DoctorReport(timestamp, overall, rendered, _health_contract(rendered, timestamp))


def chrome_available() -> bool:
    try:
        _resolve_known_chrome()
    except X2NRuntimeError:
        return False
    return True


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def native_host_registered(home: Path) -> bool:
    """Return only a boolean; user-specific Native Host paths never leave this function."""

    relative = Path("Library/Application Support/Google/Chrome/NativeMessagingHosts/com.linzecolin.x2n.json")
    candidate = home / relative
    return candidate.is_file() and not candidate.is_symlink()


def safe_reference_configured(env: Mapping[str, str], name: str) -> bool:
    """Check a non-secret reference token, never a credential value."""

    value = env.get(name)
    return isinstance(value, str) and value.startswith("keychain:") and 10 < len(value) <= 200
