"""Unique fail-closed production composition root for MooMooAU Archive.

The module binds the 04:30 Sydney planner, protected Gmail/GitHub credentials, official age,
encrypted remote state and the full GA runner.  Importing it has no side effects.  The CLI has
an offline contract-only mode and one explicit protected execution mode; there is no implicit
fallback, local state or broad environment discovery.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .age_stream import OfficialAgeStream
from .attachment_inspector import AttachmentInspector
from .auth import GMAIL_OAUTH_SECRET_NAME, SecretSource, load_gmail_oauth_credential
from .blue_green_runtime import RemoteCurrentProcessedPointerSource
from .canary_runtime import CurrentProcessedPlanFactory
from .canonical_raw import CanonicalRawFetcher
from .capacity import CapacityAssessment, CapacityLimits, CapacityPolicy, CapacitySnapshot
from .document_parser import ParserActivation, ParserProfileRegistry
from .ga_runtime import GAFullPipelineOutcome, GAFullPipelineRunner
from .github_guard import (
    GitHubAppJwtSigner,
    GitHubEndpointGuard,
    GitHubInstallationTokenClient,
    InstallationToken,
    RepositoryResolver,
    TargetRepositoryConfig,
)
from .gmail_discovery import FullMailboxDiscoverer, GmailReadClient, GmailReconciler
from .gmail_guard import GmailEndpointGuard
from .gmail_sync_checkpoint import EncryptedGmailSyncCheckpoint, GitHubGmailSyncStateStore
from .http_boundary import HttpTransport
from .http_transport import StdlibHttpsTransport
from .m3 import ExactMessageTrashExecutor, GmailLabelConfirmationClient
from .oauth import GmailAccessToken, GmailBearerTransport, GmailOAuthTokenClient
from .operation_gate import OperationalGate, SensitiveOperation
from .processed_commit import (
    GitHubProcessedCiphertextStore,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
)
from .processed_models import ClassificationActivation, ClassificationRegistry
from .production_adapters import OfficialAgeCrypto, RemoteFirstImportTimestampSource
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
from .release_control import (
    ObservationProvenance,
    PhaseObservation,
    ReleasePhase,
    Stage7ReleaseGate,
)
from .remote_recovery_gate import (
    OfficialAgeDecryptor,
    RemoteRecoveryGate,
    RepositoryCiphertextReader,
)
from .run_schedule import RunPlanner, RunTrigger, ScheduledRunPlan
from .secret_values import SecretBytes, SecretText
from .sender_registry import RegistryActivation, SenderRegistry, SenderVerifier
from .timeline_publish import (
    GitHubTimelineReleaseRemote,
    GitHubTimelineStateStore,
    SingleLatestTimelinePublisher,
)
from .timeline_render import DeterministicTimelineRenderer
from .timeline_snapshot import (
    TimelineSnapshotCommitSaga,
    TimelineSnapshotPlanner,
    TimelineSnapshotRecoveryGate,
)

PRODUCTION_CONFIG_SECRET_NAME = "MOOMOOAU_PRODUCTION_CONFIG"  # pragma: allowlist secret
CLASSIFICATION_REGISTRY_SECRET_NAME = (  # pragma: allowlist secret
    "MOOMOOAU_CLASSIFICATION_REGISTRY"
)
PARSER_REGISTRY_SECRET_NAME = "MOOMOOAU_PARSER_REGISTRY"  # pragma: allowlist secret

PRODUCTION_SECRET_NAMES = (
    PRODUCTION_CONFIG_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    CLASSIFICATION_REGISTRY_SECRET_NAME,
    PARSER_REGISTRY_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    AGE_IDENTITY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    GMAIL_OAUTH_SECRET_NAME,
)

_CONFIG_SCHEMA = "moomooau.production-config.v1"
_AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]{58}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_MAX_CONFIG_BYTES = 512 * 1024
_MAX_REGISTRY_BYTES = 4 * 1024 * 1024
_MAX_PRIVATE_KEY_BYTES = 32 * 1024
_MAX_IDENTITY_BYTES = 4096
_CAPACITY_MAX_AGE = timedelta(hours=24)
_PREDECESSOR_PHASES = (
    ReleasePhase.ALPHA,
    ReleasePhase.BETA_RAW_ONLY,
    ReleasePhase.M3_CANARY,
    ReleasePhase.BLUE_GREEN,
)
_OBSERVATION_COUNTERS = (
    "observed_runs",
    "scheduled_0430_runs",
    "verified_messages",
    "source_mutations",
    "mutation_budget_max",
    "recovery_attempts",
    "recovery_successes",
    "processed_messages",
    "parser_blue_green_comparisons",
    "timeline_publish_attempts",
    "full_reconcile_runs",
    "collateral_mutations",
    "public_sensitive_findings",
    "logical_duplicates",
    "full_reconcile_difference",
    "minimum_live_timeline_assets",
    "maximum_live_timeline_assets",
    "unresolved_failures",
)


class ProductionBootstrapError(RuntimeError):
    """A production prerequisite failed without exposing a protected value."""


class ExactEnvironmentSecretSource:
    """Read only the eight explicitly allowlisted workflow environment values."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    def read(self, name: str) -> SecretText:
        if name not in PRODUCTION_SECRET_NAMES:
            raise ProductionBootstrapError("protected Secret name is not allowlisted")
        value = self._environment.get(name)
        if not isinstance(value, str) or not value:
            raise ProductionBootstrapError("required protected Secret is unavailable")
        return SecretText(value)


@dataclass(frozen=True, slots=True, repr=False)
class ProductionConfig:
    app_id: int
    target_repository: TargetRepositoryConfig
    age_recipient: str
    key_epoch: str
    parser_current_version: str
    beta_message_budget: int
    ga_mutation_budget_per_run: int
    capacity: CapacityAssessment
    capacity_observed_at_utc: datetime
    predecessor_observations: tuple[PhaseObservation, ...]

    def __post_init__(self) -> None:
        if (
            type(self.app_id) is not int
            or self.app_id <= 0
            or not isinstance(self.target_repository, TargetRepositoryConfig)
            or _AGE_RECIPIENT.fullmatch(self.age_recipient) is None
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or _SEMVER.fullmatch(self.parser_current_version) is None
            or type(self.beta_message_budget) is not int
            or self.beta_message_budget <= 0
            or type(self.ga_mutation_budget_per_run) is not int
            or self.ga_mutation_budget_per_run <= 0
            or not isinstance(self.capacity, CapacityAssessment)
            or not self.capacity.write_allowed
            or not _is_utc(self.capacity_observed_at_utc)
            or tuple(item.phase for item in self.predecessor_observations) != _PREDECESSOR_PHASES
        ):
            raise ProductionBootstrapError("production configuration is invalid")

    def __repr__(self) -> str:
        return (
            "ProductionConfig(phase='GA', values=<protected>, "
            f"capacity_state={self.capacity.state.value!r})"
        )


@dataclass(frozen=True, slots=True)
class ProductionExecutionResult:
    plan: ScheduledRunPlan
    outcome: GAFullPipelineOutcome

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.production-execution-public.v1",
            "status": "GA_MECHANISM_COMPLETED_NOT_FINAL",
            "schedule": self.plan.to_public_dict(),
            "pipeline": self.outcome.result.to_public_dict(),
            "production_health_claimed": False,
        }


@dataclass(slots=True, repr=False)
class ProductionRuntime:
    """Single-use runtime owning every destructible protected resource."""

    _runner: GAFullPipelineRunner
    _sync_checkpoint: EncryptedGmailSyncCheckpoint
    _operational_gate: OperationalGate
    _config: ProductionConfig
    _clock: Callable[[], datetime]
    _gmail_token: GmailAccessToken
    _installation_token: InstallationToken
    _opaque_key: SecretBytes
    _identity: _ProtectedIdentityFile
    _closed: bool = False
    _run_started: bool = False

    def __repr__(self) -> str:
        return (
            "ProductionRuntime(phase='GA', resources=<protected>, "
            f"closed={self._closed}, run_started={self._run_started})"
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def run(self, trigger: RunTrigger) -> ProductionExecutionResult:
        if self._closed or self._run_started or not isinstance(trigger, RunTrigger):
            raise ProductionBootstrapError("production runtime is closed or already used")
        self._run_started = True
        try:
            now = _require_utc(self._clock())
            self._operational_gate.authorize(SensitiveOperation.PRODUCTION_RUN)
            recovered = self._operational_gate.execute(
                SensitiveOperation.REMOTE_READ,
                self._sync_checkpoint.recover,
            )
            last_success = (
                recovered.checkpoint.last_successful_run_date_sydney
                if recovered is not None
                else None
            )
            plan = RunPlanner().plan(
                trigger,
                started_at_utc=now,
                last_successful_run_date_sydney=last_success,
            )
            outcome = self._runner.run(
                plan,
                key_epoch=self._config.key_epoch,
                parser_current_version=self._config.parser_current_version,
                predecessor_observations=self._config.predecessor_observations,
                beta_message_budget=self._config.beta_message_budget,
                ga_mutation_budget_per_run=self._config.ga_mutation_budget_per_run,
                ga_capacity_authorized=self._config.capacity.write_allowed,
            )
            if (
                outcome.sync_checkpoint.checkpoint.checkpoint.last_successful_run_date_sydney
                != plan.run_date_sydney
            ):
                raise ProductionBootstrapError("production scheduling watermark did not commit")
            return ProductionExecutionResult(plan, outcome)
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
            raise ProductionBootstrapError(
                "production protected-resource cleanup failed"
            ) from cleanup_failure


class ProductionBootstrap:
    """Assemble the unique production-capable GA runner from exact protected inputs."""

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
            raise ProductionBootstrapError("synthetic ephemeral-root flag is invalid")
        self._secret_source = secret_source
        self._oauth_transport = oauth_transport
        self._gmail_transport = gmail_transport
        self._github_transport = github_transport
        self._approved_tmpfs_root = approved_tmpfs_root
        self._age = age or OfficialAgeStream()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._allow_synthetic_ephemeral_root = allow_synthetic_ephemeral_root

    @contextmanager
    def open(self) -> Iterator[ProductionRuntime]:
        now = _require_utc(self._clock())
        with ExitStack() as resources:
            config = _load_config(self._secret_source, now)
            promotion = Stage7ReleaseGate().evaluate_promotion(
                ReleasePhase.GA,
                config.predecessor_observations,
                beta_message_budget=config.beta_message_budget,
                parser_current_version=config.parser_current_version,
                ga_mutation_budget_per_run=config.ga_mutation_budget_per_run,
                ga_capacity_authorized=config.capacity.write_allowed,
            )
            if not promotion.ready:
                raise ProductionBootstrapError("protected GA predecessor gate is blocked")

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
                raise ProductionBootstrapError("protected production registries are not active")

            github_private_key = _load_secret_bytes(
                self._secret_source,
                GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
                maximum_bytes=_MAX_PRIVATE_KEY_BYTES,
            )
            resources.callback(github_private_key.destroy)
            signer = GitHubAppJwtSigner(config.app_id, github_private_key)
            try:
                local_jwt_probe = signer.sign(now)
            except Exception as exc:
                raise ProductionBootstrapError("GitHub App private key is invalid") from exc
            local_jwt_probe.destroy()

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
                temporary_prefix="moomooau-protected-production-",
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
            crypto = OfficialAgeCrypto(self._age, config.age_recipient, decryptor)
            checkpoint = EncryptedGmailSyncCheckpoint(
                GitHubGmailSyncStateStore(github_guard, locator, installation_token),
                crypto,
            )
            reader = RepositoryCiphertextReader(raw_store, processed_store)
            operational_gate = OperationalGate(config.capacity)
            processed_planner = ProcessedCommitPlanner(self._age, config.age_recipient)
            current_source = RemoteCurrentProcessedPointerSource(processed_store, decryptor)
            sender_verifier = SenderVerifier()
            runner = GAFullPipelineRunner(
                gmail,
                GmailReconciler(gmail, FullMailboxDiscoverer(gmail)),
                checkpoint,
                sender_registry,
                sender_verifier,
                CanonicalRawFetcher(gmail_guard, sender_verifier),
                AttachmentInspector(),
                RawCommitPlanner(
                    self._age,
                    config.age_recipient,
                    OpaqueIdFactory(opaque_key),
                ),
                RawCommitSaga(raw_store),
                classification_registry,
                parser_registry,
                CurrentProcessedPlanFactory(processed_store, decryptor, processed_planner),
                ProcessedCommitSaga(processed_store),
                RemoteRecoveryGate(reader, decryptor),
                ExactMessageTrashExecutor(
                    gmail_guard,
                    GmailLabelConfirmationClient(gmail_guard),
                ),
                RemoteFirstImportTimestampSource(processed_store, decryptor),
                current_source,
                TimelineSnapshotPlanner(self._age, config.age_recipient),
                TimelineSnapshotCommitSaga(processed_store),
                TimelineSnapshotRecoveryGate(processed_store, decryptor),
                SingleLatestTimelinePublisher(
                    DeterministicTimelineRenderer(),
                    crypto,
                    GitHubTimelineReleaseRemote(
                        github_guard,
                        locator,
                        installation_token,
                    ),
                    GitHubTimelineStateStore(
                        github_guard,
                        locator,
                        installation_token,
                    ),
                ),
                operational_gate,
            )
            runtime = ProductionRuntime(
                runner,
                checkpoint,
                operational_gate,
                config,
                self._clock,
                gmail_token,
                installation_token,
                opaque_key,
                identity,
            )
            resources.callback(runtime.close)
            yield runtime


def composition_contract() -> dict[str, object]:
    """Return the static offline composition descriptor without reading Secrets."""

    return {
        "schema_version": "moomooau.production-composition-public.v1",
        "status": "CONTRACT_ONLY_NO_EXECUTION",
        "entrypoint": "python -m moomooau_archive.production --execute-protected",
        "schedule": {"cron": "30 4 * * *", "timezone": "Australia/Sydney"},
        "secret_names": list(PRODUCTION_SECRET_NAMES),
        "components": [
            "RunPlanner",
            "EncryptedGmailSyncCheckpoint",
            "GmailReconciler",
            "GAFullPipelineRunner",
            "RemoteRecoveryGate",
            "ExactMessageTrashExecutor",
            "SingleLatestTimelinePublisher",
        ],
        "real_gmail_calls": 0,
        "private_repository_calls": 0,
        "protected_oracles_executed": 0,
        "production_workflow_runs": 0,
        "production_health_claimed": False,
    }


def _load_config(source: SecretSource, now: datetime) -> ProductionConfig:
    encoded = _read_secret(source, PRODUCTION_CONFIG_SECRET_NAME, maximum_bytes=_MAX_CONFIG_BYTES)
    try:
        try:
            parsed = json.loads(encoded.reveal())
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProductionBootstrapError("production config is not valid JSON") from exc
    finally:
        encoded.destroy()
    required = {
        "schema_version",
        "phase",
        "key_epoch",
        "age_recipient",
        "parser_current_version",
        "beta_message_budget",
        "ga_mutation_budget_per_run",
        "github",
        "capacity",
        "predecessor_observations",
    }
    if (
        not isinstance(parsed, dict)
        or set(parsed) != required
        or parsed.get("schema_version") != _CONFIG_SCHEMA
        or parsed.get("phase") != ReleasePhase.GA.value
    ):
        raise ProductionBootstrapError("production config schema is invalid")
    value = cast(dict[str, object], parsed)
    github = _required_object(value, "github")
    if set(github) != {"app_id", "installation_id", "repository_id"}:
        raise ProductionBootstrapError("production GitHub config schema is invalid")
    capacity = _required_object(value, "capacity")
    assessment, observed_at = _parse_capacity(capacity, now)
    raw_observations = value.get("predecessor_observations")
    if not isinstance(raw_observations, list):
        raise ProductionBootstrapError("production predecessor observations are invalid")
    observations = tuple(_parse_observation(item) for item in raw_observations)
    return ProductionConfig(
        app_id=_required_positive_int(github, "app_id"),
        target_repository=TargetRepositoryConfig(
            repository_id=_required_positive_int(github, "repository_id"),
            installation_id=_required_positive_int(github, "installation_id"),
        ),
        age_recipient=_required_string(value, "age_recipient"),
        key_epoch=_required_string(value, "key_epoch"),
        parser_current_version=_required_string(value, "parser_current_version"),
        beta_message_budget=_required_positive_int(value, "beta_message_budget"),
        ga_mutation_budget_per_run=_required_positive_int(
            value,
            "ga_mutation_budget_per_run",
        ),
        capacity=assessment,
        capacity_observed_at_utc=observed_at,
        predecessor_observations=observations,
    )


def _parse_capacity(
    value: dict[str, object],
    now: datetime,
) -> tuple[CapacityAssessment, datetime]:
    if set(value) != {"observed_at_utc", "limits", "snapshot"}:
        raise ProductionBootstrapError("production capacity config schema is invalid")
    limits_value = _required_object(value, "limits")
    snapshot_value = _required_object(value, "snapshot")
    if set(limits_value) != {"lfs_storage_budget_bytes", "lfs_object_maximum_bytes"}:
        raise ProductionBootstrapError("production capacity limits schema is invalid")
    if set(snapshot_value) != {
        "git_repository_bytes",
        "lfs_storage_bytes",
        "largest_git_object_bytes",
        "largest_lfs_object_bytes",
        "live_release_asset_bytes",
    }:
        raise ProductionBootstrapError("production capacity snapshot schema is invalid")
    observed_at = _parse_utc(value.get("observed_at_utc"))
    if observed_at > now or now - observed_at > _CAPACITY_MAX_AGE:
        raise ProductionBootstrapError("production capacity observation is absent or stale")
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


def _parse_observation(raw: object) -> PhaseObservation:
    required = {
        "phase",
        "provenance",
        "started_at_utc",
        "ended_at_utc",
        *_OBSERVATION_COUNTERS,
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ProductionBootstrapError("production predecessor observation schema is invalid")
    value = cast(dict[str, object], raw)
    try:
        return PhaseObservation(
            phase=ReleasePhase(_required_string(value, "phase")),
            provenance=ObservationProvenance(_required_string(value, "provenance")),
            started_at_utc=_parse_utc(value.get("started_at_utc")),
            ended_at_utc=_parse_utc(value.get("ended_at_utc")),
            **{name: _required_non_negative_int(value, name) for name in _OBSERVATION_COUNTERS},
        )
    except ValueError as exc:
        raise ProductionBootstrapError("production predecessor enum is invalid") from exc


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
        raise ProductionBootstrapError("production object field is invalid")
    return cast(dict[str, object], item)


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ProductionBootstrapError("production string field is invalid")
    return item


def _required_positive_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item <= 0:
        raise ProductionBootstrapError("production positive integer field is invalid")
    return item


def _required_non_negative_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item < 0:
        raise ProductionBootstrapError("production counter field is invalid")
    return item


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProductionBootstrapError("production timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProductionBootstrapError("production timestamp is invalid") from exc
    return _require_utc(parsed)


def _require_utc(value: datetime) -> datetime:
    if not _is_utc(value):
        raise ProductionBootstrapError("production timestamp must be UTC")
    return value.astimezone(UTC)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract-only", action="store_true")
    mode.add_argument("--execute-protected", action="store_true")
    parser.add_argument("--event-name", choices=[item.value for item in RunTrigger])
    args = parser.parse_args(argv)
    if args.contract_only:
        if args.event_name is not None:
            parser.error("--event-name is only valid with --execute-protected")
        print(json.dumps(composition_contract(), sort_keys=True, separators=(",", ":")))
        return 0
    if args.event_name is None:
        parser.error("--event-name is required with --execute-protected")
    transport = StdlibHttpsTransport()
    try:
        bootstrap = ProductionBootstrap(
            ExactEnvironmentSecretSource(os.environ),
            oauth_transport=transport,
            gmail_transport=transport,
            github_transport=transport,
        )
        with bootstrap.open() as runtime:
            result = runtime.run(RunTrigger(args.event_name))
        print(json.dumps(result.to_public_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema_version": "moomooau.production-execution-public.v1",
                    "status": "BLOCKED",
                    "reason_code": "PROTECTED_PRODUCTION_RUN_FAILED",
                    "production_health_claimed": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
