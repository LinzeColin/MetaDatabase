"""Fail-closed protected bootstrap for the Stage 7 Raw-only Beta runtime.

This module deliberately has no environment discovery and no production entry point.  A
protected GitHub-hosted workflow must inject the exact Secret source, bounded transports and
approved tmpfs root.  Opening the runtime validates every local prerequisite before exchanging
credentials or issuing a repository request, and closing it destroys all owned ephemeral state.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .age_stream import OfficialAgeStream
from .attachment_inspector import AttachmentInspector
from .auth import SecretSource, load_gmail_oauth_credential
from .canary_runtime import CanaryRunResult, RawOnlyCanaryRunner
from .canonical_raw import CanonicalRawFetcher
from .capacity import (
    CapacityAssessment,
    CapacityLimits,
    CapacityPolicy,
    CapacitySnapshot,
)
from .github_guard import (
    GitHubAppJwtSigner,
    GitHubEndpointGuard,
    GitHubInstallationTokenClient,
    GitHubInstallationTokenError,
    InstallationToken,
    RepositoryResolver,
    TargetRepositoryConfig,
)
from .gmail_discovery import GmailReadClient
from .gmail_guard import GmailEndpointGuard
from .http_boundary import HttpTransport
from .oauth import GmailAccessToken, GmailBearerTransport, GmailOAuthTokenClient
from .operation_gate import OperationalGate
from .protected_beta_diagnostics import (
    ProtectedBetaDiagnostics,
    ProtectedBetaFailurePhase,
)
from .raw_commit import (
    GitHubAppendOnlyCiphertextStore,
    OpaqueIdFactory,
    RawCommitPlanner,
    RawCommitSaga,
)
from .release_control import PhaseObservation, ReleasePhase, Stage7ReleaseGate
from .remote_recovery_gate import OfficialAgeDecryptor, RemoteRecoveryGate
from .secret_values import SecretBytes, SecretText
from .sender_registry import RegistryActivation, SenderRegistry, SenderVerifier

BETA_CONFIG_SECRET_NAME = "MOOMOOAU_BETA_CONFIG"  # pragma: allowlist secret
SENDER_REGISTRY_SECRET_NAME = "MOOMOOAU_SENDER_REGISTRY"  # pragma: allowlist secret
GITHUB_APP_PRIVATE_KEY_SECRET_NAME = (  # pragma: allowlist secret
    "MOOMOOAU_GITHUB_APP_PRIVATE_KEY"
)
AGE_IDENTITY_SECRET_NAME = "MOOMOOAU_AGE_IDENTITY"  # pragma: allowlist secret
OPAQUE_ID_KEY_SECRET_NAME = "MOOMOOAU_OPAQUE_ID_KEY"  # pragma: allowlist secret

_CONFIG_SCHEMA = "moomooau.protected-beta-config.v1"
_AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]{58}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_REGISTRY_BYTES = 1024 * 1024
_MAX_PRIVATE_KEY_BYTES = 32 * 1024
_MAX_IDENTITY_BYTES = 4096
_MAX_OPAQUE_KEY_TEXT_BYTES = 1024
_CAPACITY_MAX_AGE = timedelta(hours=24)
_IDENTITY_PROBE = b"MooMooAU protected age identity binding probe v1"


class ProtectedBetaBootstrapError(RuntimeError):
    """A protected Beta prerequisite failed without exposing a protected value."""


@dataclass(frozen=True, slots=True, repr=False)
class ProtectedBetaConfig:
    """Strict protected configuration for one bounded Raw-only Beta execution."""

    app_id: int
    target_repository: TargetRepositoryConfig
    age_recipient: str
    key_epoch: str
    beta_message_budget: int
    capacity: CapacityAssessment
    capacity_observed_at_utc: datetime

    def __post_init__(self) -> None:
        if (
            type(self.app_id) is not int
            or self.app_id <= 0
            or not isinstance(self.target_repository, TargetRepositoryConfig)
            or _AGE_RECIPIENT.fullmatch(self.age_recipient) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or type(self.beta_message_budget) is not int
            or self.beta_message_budget <= 0
            or not isinstance(self.capacity, CapacityAssessment)
            or not _is_utc(self.capacity_observed_at_utc)
        ):
            raise ProtectedBetaBootstrapError("protected Beta configuration is invalid")
        if not self.capacity.write_allowed:
            raise ProtectedBetaBootstrapError("protected capacity does not authorize Beta writes")

    def __repr__(self) -> str:
        return (
            "ProtectedBetaConfig(phase='BETA_RAW_ONLY', values=<protected>, "
            f"capacity_state={self.capacity.state.value!r})"
        )


class _ProtectedIdentityFile:
    """Materialize one age identity only under an explicitly approved ephemeral root."""

    def __init__(
        self,
        root: Path,
        identity: bytes,
        *,
        allow_synthetic_ephemeral_root: bool,
        temporary_prefix: str = "moomooau-protected-beta-",
    ) -> None:
        if (
            not identity
            or len(identity) > _MAX_IDENTITY_BYTES
            or identity.count(b"AGE-SECRET-KEY-") != 1
            or root.is_symlink()
            or re.fullmatch(r"[a-z0-9-]{8,64}-", temporary_prefix) is None
        ):
            raise ProtectedBetaBootstrapError("protected age identity input is invalid")
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as exc:
            raise ProtectedBetaBootstrapError("approved ephemeral root is unavailable") from exc
        if not resolved_root.is_dir():
            raise ProtectedBetaBootstrapError("approved ephemeral root is not a directory")
        if not allow_synthetic_ephemeral_root and not _is_linux_dev_shm_tmpfs(resolved_root):
            raise ProtectedBetaBootstrapError("protected identity root is not verified tmpfs")
        self._root = resolved_root
        self._temporary = tempfile.TemporaryDirectory(
            prefix=temporary_prefix,
            dir=resolved_root,
        )
        self.path = Path(self._temporary.name) / "identity.agekey"
        self._closed = False
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(identity)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException as exc:
            try:
                self.close()
            except BaseException as cleanup_exc:
                raise cleanup_exc from exc
            raise

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return (self._root,)

    def close(self) -> None:
        if self._closed:
            return
        cleanup_error: OSError | None = None
        try:
            if self.path.exists() and not self.path.is_symlink():
                flags = os.O_WRONLY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(self.path, flags)
                try:
                    remaining = os.fstat(descriptor).st_size
                    zeroes = b"\x00" * min(remaining, 4096)
                    while remaining:
                        written = os.write(descriptor, zeroes[: min(remaining, len(zeroes))])
                        if written <= 0:
                            raise OSError("identity zeroing did not make progress")
                        remaining -= written
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                self.path.unlink()
        except OSError as exc:
            cleanup_error = exc
        finally:
            self._temporary.cleanup()
            self._closed = True
        if cleanup_error is not None:
            raise ProtectedBetaBootstrapError(
                "protected age identity cleanup failed"
            ) from cleanup_error


@dataclass(slots=True, repr=False)
class ProtectedBetaRuntime:
    """Single-use Beta runner with owned, destructible protected resources."""

    _runner: RawOnlyCanaryRunner
    _config: ProtectedBetaConfig
    _predecessor_observations: tuple[PhaseObservation, ...]
    _gmail_token: GmailAccessToken
    _installation_token: InstallationToken
    _opaque_key: SecretBytes
    _identity: _ProtectedIdentityFile
    _diagnostics: ProtectedBetaDiagnostics
    _closed: bool = False
    _run_started: bool = False

    def __repr__(self) -> str:
        return (
            "ProtectedBetaRuntime(phase='BETA_RAW_ONLY', resources=<protected>, "
            f"closed={self._closed}, run_started={self._run_started})"
        )

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def beta_message_budget(self) -> int:
        return self._config.beta_message_budget

    def run(self) -> CanaryRunResult:
        if self._closed or self._run_started:
            raise ProtectedBetaBootstrapError("protected Beta runtime is closed or already used")
        self._run_started = True
        try:
            return self._runner.run(
                ReleasePhase.BETA_RAW_ONLY,
                maximum_verified_candidates=self._config.beta_message_budget,
                key_epoch=self._config.key_epoch,
                predecessor_observations=self._predecessor_observations,
                beta_message_budget=self._config.beta_message_budget,
            )
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        cleanup_failure: BaseException | None = None
        for action in (
            self._gmail_token.destroy,
            self._installation_token.destroy,
            self._opaque_key.destroy,
            self._identity.close,
        ):
            try:
                action()
            except BaseException as exc:
                cleanup_failure = cleanup_failure or exc
        self._closed = True
        if cleanup_failure is not None:
            self._diagnostics.enter(ProtectedBetaFailurePhase.RESOURCE_CLEANUP)
            raise ProtectedBetaBootstrapError(
                "protected Beta resource cleanup failed"
            ) from cleanup_failure


class ProtectedBetaBootstrap:
    """Assemble one production-capable Raw-only runner from exact protected inputs."""

    def __init__(
        self,
        secret_source: SecretSource,
        *,
        oauth_transport: HttpTransport,
        gmail_transport: HttpTransport,
        github_transport: HttpTransport,
        approved_tmpfs_root: Path = Path("/dev/shm"),
        age: OfficialAgeStream | None = None,
        clock: Callable[[], datetime] | None = None,
        allow_synthetic_ephemeral_root: bool = False,
        diagnostics: ProtectedBetaDiagnostics | None = None,
    ) -> None:
        if type(allow_synthetic_ephemeral_root) is not bool:
            raise ProtectedBetaBootstrapError("synthetic ephemeral-root flag is invalid")
        self._secret_source = secret_source
        self._oauth_transport = oauth_transport
        self._gmail_transport = gmail_transport
        self._github_transport = github_transport
        self._approved_tmpfs_root = approved_tmpfs_root
        self._age = age or OfficialAgeStream()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._allow_synthetic_ephemeral_root = allow_synthetic_ephemeral_root
        self._diagnostics = diagnostics or ProtectedBetaDiagnostics()

    @contextmanager
    def open(
        self,
        *,
        predecessor_observations: tuple[PhaseObservation, ...],
    ) -> Iterator[ProtectedBetaRuntime]:
        now = _require_utc(self._clock())
        with ExitStack() as resources:
            self._diagnostics.enter(ProtectedBetaFailurePhase.CONFIG_CAPACITY)
            config = _load_config(self._secret_source, now)
            promotion = Stage7ReleaseGate().evaluate_promotion(
                ReleasePhase.BETA_RAW_ONLY,
                predecessor_observations,
                beta_message_budget=config.beta_message_budget,
            )
            if not promotion.ready:
                raise ProtectedBetaBootstrapError("protected Alpha predecessor gate is blocked")

            self._diagnostics.enter(ProtectedBetaFailurePhase.SENDER_REGISTRY)
            sender_registry = _load_sender_registry(self._secret_source)
            if sender_registry.activation is not RegistryActivation.ACTIVE:
                raise ProtectedBetaBootstrapError("protected sender registry is not active")

            self._diagnostics.enter(ProtectedBetaFailurePhase.GITHUB_APP_KEY)
            github_private_key = _load_secret_bytes(
                self._secret_source,
                GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
                maximum_bytes=_MAX_PRIVATE_KEY_BYTES,
            )
            _register_cleanup(resources, github_private_key.destroy, self._diagnostics)
            github_signer = GitHubAppJwtSigner(config.app_id, github_private_key)
            try:
                local_jwt_probe = github_signer.sign(now)
            except Exception as exc:
                raise ProtectedBetaBootstrapError("GitHub App private key is invalid") from exc
            _destroy_now(local_jwt_probe.destroy, self._diagnostics)

            self._diagnostics.enter(ProtectedBetaFailurePhase.AGE_IDENTITY)
            opaque_key = _load_base64_key(self._secret_source)
            _register_cleanup(resources, opaque_key.destroy, self._diagnostics)
            identity_secret = _read_secret(
                self._secret_source,
                AGE_IDENTITY_SECRET_NAME,
                maximum_bytes=_MAX_IDENTITY_BYTES,
            )
            _register_cleanup(resources, identity_secret.destroy, self._diagnostics)
            identity = _ProtectedIdentityFile(
                self._approved_tmpfs_root,
                identity_secret.reveal().encode("ascii"),
                allow_synthetic_ephemeral_root=self._allow_synthetic_ephemeral_root,
            )
            _register_cleanup(resources, identity.close, self._diagnostics)
            _destroy_now(identity_secret.destroy, self._diagnostics)
            _verify_identity_recipient(self._age, config.age_recipient, identity)

            self._diagnostics.enter(ProtectedBetaFailurePhase.GMAIL_OAUTH)
            gmail_credential = load_gmail_oauth_credential(self._secret_source)
            _register_cleanup(resources, gmail_credential.destroy, self._diagnostics)
            gmail_token = GmailOAuthTokenClient(self._oauth_transport).exchange(
                gmail_credential,
                now_utc=now,
            )
            _register_cleanup(resources, gmail_token.destroy, self._diagnostics)
            _destroy_now(gmail_credential.destroy, self._diagnostics)

            self._diagnostics.enter(ProtectedBetaFailurePhase.GITHUB_APP_TOKEN)
            github_guard = GitHubEndpointGuard(self._github_transport, config.target_repository)
            try:
                installation_token = GitHubInstallationTokenClient(
                    github_guard,
                    config.target_repository,
                    github_signer,
                ).mint(now)
            except GitHubInstallationTokenError as exc:
                self._diagnostics.enter_installation_token_failure(exc.failure_class)
                raise ProtectedBetaBootstrapError(
                    "GitHub App installation token is unavailable"
                ) from exc
            _register_cleanup(resources, installation_token.destroy, self._diagnostics)
            _destroy_now(github_private_key.destroy, self._diagnostics)
            self._diagnostics.enter(ProtectedBetaFailurePhase.REPOSITORY_RESOLUTION)
            locator = RepositoryResolver(github_guard, config.target_repository).resolve(
                installation_token
            )

            gmail_guard = GmailEndpointGuard(
                GmailBearerTransport(self._gmail_transport, gmail_token, clock=self._clock)
            )
            gmail = GmailReadClient(gmail_guard)
            verifier = SenderVerifier()
            raw_store = GitHubAppendOnlyCiphertextStore(
                github_guard,
                locator,
                installation_token,
            )
            runner = RawOnlyCanaryRunner(
                gmail,
                sender_registry,
                verifier,
                CanonicalRawFetcher(gmail_guard, verifier),
                AttachmentInspector(),
                RawCommitPlanner(self._age, config.age_recipient, OpaqueIdFactory(opaque_key)),
                RawCommitSaga(raw_store),
                RemoteRecoveryGate(
                    raw_store,
                    OfficialAgeDecryptor(
                        self._age,
                        identity.path,
                        allowed_tmpfs_roots=identity.allowed_roots,
                    ),
                ),
                OperationalGate(config.capacity),
                diagnostics=self._diagnostics,
            )
            runtime = ProtectedBetaRuntime(
                runner,
                config,
                predecessor_observations,
                gmail_token,
                installation_token,
                opaque_key,
                identity,
                self._diagnostics,
            )
            _register_cleanup(resources, runtime.close, self._diagnostics)
            yield runtime


def _register_cleanup(
    resources: ExitStack,
    action: Callable[[], None],
    diagnostics: ProtectedBetaDiagnostics,
) -> None:
    def guarded_cleanup() -> None:
        try:
            action()
        except BaseException:
            diagnostics.enter(ProtectedBetaFailurePhase.RESOURCE_CLEANUP)
            raise

    resources.callback(guarded_cleanup)


def _destroy_now(
    action: Callable[[], None],
    diagnostics: ProtectedBetaDiagnostics,
) -> None:
    try:
        action()
    except BaseException:
        diagnostics.enter(ProtectedBetaFailurePhase.RESOURCE_CLEANUP)
        raise


def _load_config(source: SecretSource, now: datetime) -> ProtectedBetaConfig:
    encoded = _read_secret(source, BETA_CONFIG_SECRET_NAME, maximum_bytes=_MAX_CONFIG_BYTES)
    try:
        try:
            parsed = json.loads(encoded.reveal())
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProtectedBetaBootstrapError("protected Beta config is not valid JSON") from exc
    finally:
        encoded.destroy()
    if not isinstance(parsed, dict):
        raise ProtectedBetaBootstrapError("protected Beta config must be an object")
    value = cast(dict[str, object], parsed)
    required = {
        "schema_version",
        "phase",
        "beta_message_budget",
        "key_epoch",
        "age_recipient",
        "github",
        "capacity",
    }
    if (
        set(value) != required
        or value.get("schema_version") != _CONFIG_SCHEMA
        or value.get("phase") != ReleasePhase.BETA_RAW_ONLY.value
    ):
        raise ProtectedBetaBootstrapError("protected Beta config schema is invalid")
    github = _required_object(value, "github")
    if set(github) != {"app_id", "installation_id", "repository_id"}:
        raise ProtectedBetaBootstrapError("protected GitHub config schema is invalid")
    capacity = _required_object(value, "capacity")
    if set(capacity) != {"observed_at_utc", "limits", "snapshot"}:
        raise ProtectedBetaBootstrapError("protected capacity config schema is invalid")
    limits_value = _required_object(capacity, "limits")
    if set(limits_value) != {"lfs_storage_budget_bytes", "lfs_object_maximum_bytes"}:
        raise ProtectedBetaBootstrapError("protected capacity limits schema is invalid")
    snapshot_value = _required_object(capacity, "snapshot")
    snapshot_fields = {
        "git_repository_bytes",
        "lfs_storage_bytes",
        "largest_git_object_bytes",
        "largest_lfs_object_bytes",
        "live_release_asset_bytes",
    }
    if set(snapshot_value) != snapshot_fields:
        raise ProtectedBetaBootstrapError("protected capacity snapshot schema is invalid")
    observed_at = _parse_utc(capacity.get("observed_at_utc"))
    if observed_at > now or now - observed_at > _CAPACITY_MAX_AGE:
        raise ProtectedBetaBootstrapError("protected capacity observation is absent or stale")
    limits = CapacityLimits(
        lfs_storage_budget_bytes=_required_positive_int(
            limits_value,
            "lfs_storage_budget_bytes",
        ),
        lfs_object_maximum_bytes=_required_positive_int(
            limits_value,
            "lfs_object_maximum_bytes",
        ),
    )
    snapshot = CapacitySnapshot(
        git_repository_bytes=_required_non_negative_int(snapshot_value, "git_repository_bytes"),
        lfs_storage_bytes=_required_non_negative_int(snapshot_value, "lfs_storage_bytes"),
        largest_git_object_bytes=_required_non_negative_int(
            snapshot_value, "largest_git_object_bytes"
        ),
        largest_lfs_object_bytes=_required_non_negative_int(
            snapshot_value, "largest_lfs_object_bytes"
        ),
        live_release_asset_bytes=_required_non_negative_int(
            snapshot_value, "live_release_asset_bytes"
        ),
    )
    return ProtectedBetaConfig(
        app_id=_required_positive_int(github, "app_id"),
        target_repository=TargetRepositoryConfig(
            repository_id=_required_positive_int(github, "repository_id"),
            installation_id=_required_positive_int(github, "installation_id"),
        ),
        age_recipient=_required_string(value, "age_recipient"),
        key_epoch=_required_string(value, "key_epoch"),
        beta_message_budget=_required_positive_int(value, "beta_message_budget"),
        capacity=CapacityPolicy().evaluate(snapshot, limits),
        capacity_observed_at_utc=observed_at,
    )


def _load_sender_registry(source: SecretSource) -> SenderRegistry:
    encoded = _read_secret(
        source,
        SENDER_REGISTRY_SECRET_NAME,
        maximum_bytes=_MAX_REGISTRY_BYTES,
    )
    try:
        return SenderRegistry.from_json(encoded.reveal().encode("utf-8"))
    finally:
        encoded.destroy()


def _load_secret_bytes(
    source: SecretSource,
    name: str,
    *,
    maximum_bytes: int,
) -> SecretBytes:
    encoded = _read_secret(source, name, maximum_bytes=maximum_bytes)
    try:
        return SecretBytes(encoded.reveal().encode("utf-8"))
    finally:
        encoded.destroy()


def _load_base64_key(source: SecretSource) -> SecretBytes:
    encoded = _read_secret(
        source,
        OPAQUE_ID_KEY_SECRET_NAME,
        maximum_bytes=_MAX_OPAQUE_KEY_TEXT_BYTES,
    )
    try:
        try:
            value = base64.b64decode(encoded.reveal(), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProtectedBetaBootstrapError("opaque ID key encoding is invalid") from exc
    finally:
        encoded.destroy()
    if len(value) != 32:
        raise ProtectedBetaBootstrapError("opaque ID key length is invalid")
    return SecretBytes(value)


def _read_secret(source: SecretSource, name: str, *, maximum_bytes: int) -> SecretText:
    value: SecretText | None = None
    try:
        candidate = source.read(name)
        if not isinstance(candidate, SecretText):
            raise TypeError("protected Secret source returned an invalid wrapper")
        value = candidate
        revealed = value.reveal()
    except Exception as exc:
        if value is not None:
            value.destroy()
        raise ProtectedBetaBootstrapError("required protected Secret is unavailable") from exc
    if len(revealed.encode("utf-8")) > maximum_bytes:
        value.destroy()
        raise ProtectedBetaBootstrapError("required protected Secret exceeds its byte contract")
    return value


def _verify_identity_recipient(
    age: OfficialAgeStream,
    recipient: str,
    identity: _ProtectedIdentityFile,
) -> None:
    ciphertext = io.BytesIO()
    recovered = io.BytesIO()
    try:
        age.encrypt_stream(recipient, io.BytesIO(_IDENTITY_PROBE), ciphertext)
        age.decrypt_stream(
            identity.path,
            io.BytesIO(ciphertext.getvalue()),
            recovered,
            allowed_tmpfs_roots=identity.allowed_roots,
        )
    except Exception as exc:
        raise ProtectedBetaBootstrapError("age identity and recipient are not bound") from exc
    if recovered.getvalue() != _IDENTITY_PROBE:
        raise ProtectedBetaBootstrapError("age identity binding probe differs")


def _required_object(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtectedBetaBootstrapError("protected Beta object field is invalid")
    return cast(dict[str, object], item)


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ProtectedBetaBootstrapError("protected Beta string field is invalid")
    return item


def _required_positive_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item <= 0:
        raise ProtectedBetaBootstrapError("protected Beta positive integer field is invalid")
    return item


def _required_non_negative_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item < 0:
        raise ProtectedBetaBootstrapError("protected Beta counter field is invalid")
    return item


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtectedBetaBootstrapError("protected timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProtectedBetaBootstrapError("protected timestamp is invalid") from exc
    return _require_utc(parsed)


def _require_utc(value: datetime) -> datetime:
    if not _is_utc(value):
        raise ProtectedBetaBootstrapError("protected bootstrap timestamp must be UTC")
    return value.astimezone(UTC)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _is_linux_dev_shm_tmpfs(root: Path) -> bool:
    try:
        dev_shm = Path("/dev/shm").resolve(strict=True)
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError:
        return False
    if not root.is_relative_to(dev_shm):
        return False
    for line in mountinfo.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or not right_fields:
            continue
        if left_fields[4] == "/dev/shm" and right_fields[0] == "tmpfs":
            return True
    return False
