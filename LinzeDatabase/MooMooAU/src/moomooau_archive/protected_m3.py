"""Fail-closed protected bootstrap for one Stage 7 M3 Budget-1 Canary.

The bootstrap is intentionally narrower than the GA production composition: it has no
schedule, checkpoint, Blue-Green or Timeline dependency.  It assembles one single-use
``M3CanaryRunner`` from exact protected inputs after the caller has independently established
the protected Beta predecessor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .age_stream import OfficialAgeStream
from .attachment_inspector import AttachmentInspector
from .auth import GMAIL_OAUTH_SECRET_NAME, SecretSource, load_gmail_oauth_credential
from .canary_runtime import CurrentProcessedPlanFactory, M3CanaryRunner, M3CanaryRunResult
from .canonical_raw import CanonicalRawFetcher
from .capacity import CapacityAssessment
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
    BETA_CONFIG_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    ProtectedBetaBootstrapError,
    _load_base64_key,
    _load_secret_bytes,
    _ProtectedIdentityFile,
    _read_secret,
    _verify_identity_recipient,
)
from .protected_beta import (
    _load_config as _load_beta_config,
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

# T0703 deliberately reuses the exact protected Beta infrastructure and its already-verified
# private-repository binding.  GitHub Environment Secret values are write-only, so requiring a
# copied M3 config would add a credential-migration path without improving isolation.
M3_CONFIG_SECRET_NAME = BETA_CONFIG_SECRET_NAME
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

_AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]{58}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_MAX_REGISTRY_BYTES = 4 * 1024 * 1024
_MAX_PRIVATE_KEY_BYTES = 32 * 1024
_MAX_IDENTITY_BYTES = 4096
_MAXIMUM_VERIFIED_CANDIDATES = 1
_PARSER_CURRENT_VERSION = "1.0.0"


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
            active_processing = (
                classification_registry.activation is ClassificationActivation.ACTIVE
                and parser_registry.activation is ParserActivation.ACTIVE
                and any(
                    profile.parser_version == config.parser_current_version
                    for profile in parser_registry.profiles
                )
            )
            safe_deferred_processing = (
                classification_registry.activation
                is ClassificationActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
                and parser_registry.activation is ParserActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
                and not classification_registry.rules
                and not parser_registry.profiles
            )
            if sender_registry.activation is not RegistryActivation.ACTIVE or not (
                active_processing or safe_deferred_processing
            ):
                raise ProtectedM3BootstrapError("protected M3 registries are incompatible")

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
    try:
        beta = _load_beta_config(source, now)
    except ProtectedBetaBootstrapError as exc:
        raise ProtectedM3BootstrapError("protected Beta infrastructure config is invalid") from exc
    if beta.beta_message_budget != 1:
        raise ProtectedM3BootstrapError("protected M3 config budget is not one")
    return ProtectedM3Config(
        app_id=beta.app_id,
        target_repository=beta.target_repository,
        age_recipient=beta.age_recipient,
        key_epoch=beta.key_epoch,
        parser_current_version=_PARSER_CURRENT_VERSION,
        beta_message_budget=1,
        capacity=beta.capacity,
        capacity_observed_at_utc=beta.capacity_observed_at_utc,
    )


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


def _require_utc(value: datetime) -> datetime:
    if not _is_utc(value):
        raise ProtectedM3BootstrapError("protected M3 timestamp must be UTC")
    return value.astimezone(UTC)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)
