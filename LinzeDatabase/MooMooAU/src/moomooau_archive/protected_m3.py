"""Fail-closed protected bootstrap for one Stage 7 M3 Budget-1 Canary.

The bootstrap is intentionally narrower than the GA production composition: it has no
schedule, checkpoint, Blue-Green or Timeline dependency.  It assembles one single-use
``M3CanaryRunner`` from exact protected inputs after the caller has independently established
the protected Beta predecessor.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .age_stream import OfficialAgeStream
from .attachment_inspector import AttachmentInspector
from .auth import GMAIL_OAUTH_SECRET_NAME, SecretSource, load_gmail_oauth_credential
from .canary_runtime import CurrentProcessedPlanFactory, M3CanaryRunner, M3CanaryRunResult
from .canonical_raw import CanonicalRawFetcher
from .capacity import CapacityAssessment, CapacityLimits, CapacityPolicy, CapacitySnapshot
from .document_parser import ParserActivation, ParserProfileRegistry
from .github_guard import (
    GitHubAppJwtSigner,
    GitHubEndpointGuard,
    GitHubInstallationTokenClient,
    InstallationToken,
    RepositoryResolver,
    TargetRepositoryConfig,
)
from .gmail_discovery import GmailReadClient
from .gmail_guard import GmailEndpointGuard
from .http_boundary import HttpTransport
from .m3 import ExactMessageTrashExecutor, GmailLabelConfirmationClient
from .oauth import GmailAccessToken, GmailBearerTransport, GmailOAuthTokenClient
from .operation_gate import OperationalGate
from .processed_commit import (
    GitHubProcessedCiphertextStore,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
)
from .processed_models import ClassificationActivation, ClassificationRegistry
from .production_adapters import RemoteFirstImportTimestampSource
from .protected_beta import (
    AGE_IDENTITY_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    _load_base64_key,
    _load_secret_bytes,
    _ProtectedIdentityFile,
    _read_secret,
    _verify_identity_recipient,
)
from .raw_commit import (
    GitHubAppendOnlyCiphertextStore,
    OpaqueIdFactory,
    RawCommitPlanner,
    RawCommitSaga,
)
from .release_control import PhaseObservation, ReleasePhase, Stage7ReleaseGate
from .remote_recovery_gate import (
    OfficialAgeDecryptor,
    RemoteRecoveryGate,
    RepositoryCiphertextReader,
)
from .secret_values import SecretBytes
from .sender_registry import RegistryActivation, SenderRegistry, SenderVerifier

M3_CONFIG_SECRET_NAME = "MOOMOOAU_M3_CONFIG"  # pragma: allowlist secret
CLASSIFICATION_REGISTRY_SECRET_NAME = (  # pragma: allowlist secret
    "MOOMOOAU_CLASSIFICATION_REGISTRY"
)
PARSER_REGISTRY_SECRET_NAME = "MOOMOOAU_PARSER_REGISTRY"  # pragma: allowlist secret

M3_SECRET_NAMES = (
    M3_CONFIG_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    CLASSIFICATION_REGISTRY_SECRET_NAME,
    PARSER_REGISTRY_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    AGE_IDENTITY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    GMAIL_OAUTH_SECRET_NAME,
)

_CONFIG_SCHEMA = "moomooau.protected-m3-config.v1"
_AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]{58}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_REGISTRY_BYTES = 4 * 1024 * 1024
_MAX_PRIVATE_KEY_BYTES = 32 * 1024
_MAX_IDENTITY_BYTES = 4096
_CAPACITY_MAX_AGE = timedelta(hours=24)
_MAXIMUM_VERIFIED_CANDIDATES = 1


class ProtectedM3BootstrapError(RuntimeError):
    """A protected M3 prerequisite failed without exposing a protected value."""


@dataclass(frozen=True, slots=True, repr=False)
class ProtectedM3Config:
    """Strict configuration for one M3 run with a fixed candidate and mutation budget of one."""

    app_id: int
    target_repository: TargetRepositoryConfig
    age_recipient: str
    key_epoch: str
    parser_current_version: str
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
            or _SEMVER.fullmatch(self.parser_current_version) is None
            or self.beta_message_budget != 1
            or not isinstance(self.capacity, CapacityAssessment)
            or not self.capacity.write_allowed
            or not _is_utc(self.capacity_observed_at_utc)
        ):
            raise ProtectedM3BootstrapError("protected M3 configuration is invalid")

    def __repr__(self) -> str:
        return (
            "ProtectedM3Config(phase='M3_CANARY', values=<protected>, "
            f"capacity_state={self.capacity.state.value!r})"
        )


@dataclass(slots=True, repr=False)
class ProtectedM3Runtime:
    """Single-use M3 runner owning every destructible protected resource."""

    _runner: M3CanaryRunner
    _config: ProtectedM3Config
    _predecessor_observations: tuple[PhaseObservation, ...]
    _clock: Callable[[], datetime]
    _gmail_token: GmailAccessToken
    _installation_token: InstallationToken
    _opaque_key: SecretBytes
    _identity: _ProtectedIdentityFile
    _closed: bool = False
    _run_started: bool = False

    def __repr__(self) -> str:
        return (
            "ProtectedM3Runtime(phase='M3_CANARY', resources=<protected>, "
            f"closed={self._closed}, run_started={self._run_started})"
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def run(self) -> M3CanaryRunResult:
        if self._closed or self._run_started:
            raise ProtectedM3BootstrapError("protected M3 runtime is closed or already used")
        self._run_started = True
        try:
            return self._runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=_MAXIMUM_VERIFIED_CANDIDATES,
                key_epoch=self._config.key_epoch,
                parser_current_version=self._config.parser_current_version,
                observed_at_utc=_require_utc(self._clock()),
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
            raise ProtectedM3BootstrapError(
                "protected M3 resource cleanup failed"
            ) from cleanup_failure


class ProtectedM3Bootstrap:
    """Assemble exactly one protected M3 runner without Timeline or GA reachability."""

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
    ) -> None:
        if type(allow_synthetic_ephemeral_root) is not bool:
            raise ProtectedM3BootstrapError("synthetic ephemeral-root flag is invalid")
        self._secret_source = secret_source
        self._oauth_transport = oauth_transport
        self._gmail_transport = gmail_transport
        self._github_transport = github_transport
        self._approved_tmpfs_root = approved_tmpfs_root
        self._age = age or OfficialAgeStream()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._allow_synthetic_ephemeral_root = allow_synthetic_ephemeral_root

    @contextmanager
    def open(
        self,
        *,
        predecessor_observations: tuple[PhaseObservation, ...],
    ) -> Iterator[ProtectedM3Runtime]:
        now = _require_utc(self._clock())
        with ExitStack() as resources:
            config = _load_config(self._secret_source, now)
            promotion = Stage7ReleaseGate().evaluate_promotion(
                ReleasePhase.M3_CANARY,
                predecessor_observations,
                beta_message_budget=config.beta_message_budget,
                parser_current_version=config.parser_current_version,
            )
            if not promotion.ready:
                raise ProtectedM3BootstrapError("protected M3 predecessor gate is blocked")

            sender_registry = _load_sender_registry(self._secret_source)
            classification_registry = _load_classification_registry(self._secret_source)
            parser_registry = _load_parser_registry(self._secret_source)
            if (
                sender_registry.activation is not RegistryActivation.ACTIVE
                or classification_registry.activation is not ClassificationActivation.ACTIVE
                or parser_registry.activation is not ParserActivation.ACTIVE
                or not any(
                    profile.parser_version == config.parser_current_version
                    for profile in parser_registry.profiles
                )
            ):
                raise ProtectedM3BootstrapError("protected M3 registries are not active")

            github_private_key = _load_secret_bytes(
                self._secret_source,
                GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
                maximum_bytes=_MAX_PRIVATE_KEY_BYTES,
            )
            resources.callback(github_private_key.destroy)
            signer = GitHubAppJwtSigner(config.app_id, github_private_key)
            try:
                jwt_probe = signer.sign(now)
            except Exception as exc:
                raise ProtectedM3BootstrapError("GitHub App private key is invalid") from exc
            jwt_probe.destroy()

            opaque_key = _load_base64_key(self._secret_source)
            resources.callback(opaque_key.destroy)
            identity_secret = _read_secret(
                self._secret_source,
                AGE_IDENTITY_SECRET_NAME,
                maximum_bytes=_MAX_IDENTITY_BYTES,
            )
            resources.callback(identity_secret.destroy)
            identity = _ProtectedIdentityFile(
                self._approved_tmpfs_root,
                identity_secret.reveal().encode("ascii"),
                allow_synthetic_ephemeral_root=self._allow_synthetic_ephemeral_root,
                temporary_prefix="moomooau-protected-m3-",
            )
            resources.callback(identity.close)
            identity_secret.destroy()
            _verify_identity_recipient(self._age, config.age_recipient, identity)

            gmail_credential = load_gmail_oauth_credential(self._secret_source)
            resources.callback(gmail_credential.destroy)
            gmail_token = GmailOAuthTokenClient(self._oauth_transport).exchange(
                gmail_credential,
                now_utc=now,
            )
            resources.callback(gmail_token.destroy)
            gmail_credential.destroy()

            github_guard = GitHubEndpointGuard(self._github_transport, config.target_repository)
            installation_token = GitHubInstallationTokenClient(
                github_guard,
                config.target_repository,
                signer,
            ).mint(now)
            resources.callback(installation_token.destroy)
            github_private_key.destroy()
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
            processed_store = GitHubProcessedCiphertextStore(
                github_guard,
                locator,
                installation_token,
            )
            decryptor = OfficialAgeDecryptor(
                self._age,
                identity.path,
                allowed_tmpfs_roots=identity.allowed_roots,
            )
            processed_planner = ProcessedCommitPlanner(self._age, config.age_recipient)
            runner = M3CanaryRunner(
                gmail,
                sender_registry,
                verifier,
                CanonicalRawFetcher(gmail_guard, verifier),
                AttachmentInspector(),
                RawCommitPlanner(
                    self._age,
                    config.age_recipient,
                    OpaqueIdFactory(opaque_key),
                ),
                RawCommitSaga(raw_store),
                classification_registry,
                parser_registry,
                CurrentProcessedPlanFactory(
                    processed_store,
                    decryptor,
                    processed_planner,
                ),
                ProcessedCommitSaga(processed_store),
                RemoteRecoveryGate(
                    RepositoryCiphertextReader(raw_store, processed_store),
                    decryptor,
                ),
                ExactMessageTrashExecutor(
                    gmail_guard,
                    GmailLabelConfirmationClient(gmail_guard),
                ),
                RemoteFirstImportTimestampSource(processed_store, decryptor),
                OperationalGate(config.capacity),
            )
            runtime = ProtectedM3Runtime(
                runner,
                config,
                predecessor_observations,
                self._clock,
                gmail_token,
                installation_token,
                opaque_key,
                identity,
            )
            resources.callback(runtime.close)
            yield runtime


def _load_config(source: SecretSource, now: datetime) -> ProtectedM3Config:
    encoded = _read_secret(source, M3_CONFIG_SECRET_NAME, maximum_bytes=_MAX_CONFIG_BYTES)
    try:
        try:
            parsed = json.loads(encoded.reveal())
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProtectedM3BootstrapError("protected M3 config is not valid JSON") from exc
    finally:
        encoded.destroy()
    required = {
        "schema_version",
        "phase",
        "key_epoch",
        "age_recipient",
        "parser_current_version",
        "beta_message_budget",
        "github",
        "capacity",
    }
    if (
        not isinstance(parsed, dict)
        or set(parsed) != required
        or parsed.get("schema_version") != _CONFIG_SCHEMA
        or parsed.get("phase") != ReleasePhase.M3_CANARY.value
        or parsed.get("beta_message_budget") != 1
    ):
        raise ProtectedM3BootstrapError("protected M3 config schema is invalid")
    value = cast(dict[str, object], parsed)
    github = _required_object(value, "github")
    if set(github) != {"app_id", "installation_id", "repository_id"}:
        raise ProtectedM3BootstrapError("protected M3 GitHub config schema is invalid")
    capacity = _required_object(value, "capacity")
    assessment, observed_at = _parse_capacity(capacity, now)
    return ProtectedM3Config(
        app_id=_required_positive_int(github, "app_id"),
        target_repository=TargetRepositoryConfig(
            repository_id=_required_positive_int(github, "repository_id"),
            installation_id=_required_positive_int(github, "installation_id"),
        ),
        age_recipient=_required_string(value, "age_recipient"),
        key_epoch=_required_string(value, "key_epoch"),
        parser_current_version=_required_string(value, "parser_current_version"),
        beta_message_budget=1,
        capacity=assessment,
        capacity_observed_at_utc=observed_at,
    )


def _parse_capacity(
    value: dict[str, object],
    now: datetime,
) -> tuple[CapacityAssessment, datetime]:
    if set(value) != {"observed_at_utc", "limits", "snapshot"}:
        raise ProtectedM3BootstrapError("protected M3 capacity config schema is invalid")
    limits_value = _required_object(value, "limits")
    snapshot_value = _required_object(value, "snapshot")
    if set(limits_value) != {"lfs_storage_budget_bytes", "lfs_object_maximum_bytes"}:
        raise ProtectedM3BootstrapError("protected M3 capacity limits schema is invalid")
    if set(snapshot_value) != {
        "git_repository_bytes",
        "lfs_storage_bytes",
        "largest_git_object_bytes",
        "largest_lfs_object_bytes",
        "live_release_asset_bytes",
    }:
        raise ProtectedM3BootstrapError("protected M3 capacity snapshot schema is invalid")
    observed_at = _parse_utc(value.get("observed_at_utc"))
    if observed_at > now or now - observed_at > _CAPACITY_MAX_AGE:
        raise ProtectedM3BootstrapError("protected M3 capacity observation is absent or stale")
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
        git_repository_bytes=_required_non_negative_int(
            snapshot_value,
            "git_repository_bytes",
        ),
        lfs_storage_bytes=_required_non_negative_int(snapshot_value, "lfs_storage_bytes"),
        largest_git_object_bytes=_required_non_negative_int(
            snapshot_value,
            "largest_git_object_bytes",
        ),
        largest_lfs_object_bytes=_required_non_negative_int(
            snapshot_value,
            "largest_lfs_object_bytes",
        ),
        live_release_asset_bytes=_required_non_negative_int(
            snapshot_value,
            "live_release_asset_bytes",
        ),
    )
    return CapacityPolicy().evaluate(snapshot, limits), observed_at


def _load_sender_registry(source: SecretSource) -> SenderRegistry:
    encoded = _read_secret(source, SENDER_REGISTRY_SECRET_NAME, maximum_bytes=_MAX_REGISTRY_BYTES)
    try:
        return SenderRegistry.from_json(encoded.reveal().encode("utf-8"))
    finally:
        encoded.destroy()


def _load_classification_registry(source: SecretSource) -> ClassificationRegistry:
    encoded = _read_secret(
        source,
        CLASSIFICATION_REGISTRY_SECRET_NAME,
        maximum_bytes=_MAX_REGISTRY_BYTES,
    )
    try:
        return ClassificationRegistry.from_json(encoded.reveal().encode("utf-8"))
    finally:
        encoded.destroy()


def _load_parser_registry(source: SecretSource) -> ParserProfileRegistry:
    encoded = _read_secret(
        source,
        PARSER_REGISTRY_SECRET_NAME,
        maximum_bytes=_MAX_REGISTRY_BYTES,
    )
    try:
        return ParserProfileRegistry.from_json(encoded.reveal().encode("utf-8"))
    finally:
        encoded.destroy()


def _required_object(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtectedM3BootstrapError("protected M3 object field is invalid")
    return cast(dict[str, object], item)


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ProtectedM3BootstrapError("protected M3 string field is invalid")
    return item


def _required_positive_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item <= 0:
        raise ProtectedM3BootstrapError("protected M3 positive integer field is invalid")
    return item


def _required_non_negative_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item < 0:
        raise ProtectedM3BootstrapError("protected M3 counter field is invalid")
    return item


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtectedM3BootstrapError("protected M3 timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProtectedM3BootstrapError("protected M3 timestamp is invalid") from exc
    return _require_utc(parsed)


def _require_utc(value: datetime) -> datetime:
    if not _is_utc(value):
        raise ProtectedM3BootstrapError("protected M3 timestamp must be UTC")
    return value.astimezone(UTC)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)
