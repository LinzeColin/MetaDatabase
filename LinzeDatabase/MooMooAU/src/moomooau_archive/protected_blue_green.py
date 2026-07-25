"""Protected cloud-only composition for one Stage 7 T0704 Blue-Green run.

The bootstrap reuses the exact T0703 protected Environment and private-repository binding.  It
performs one full metadata reconciliation, selects the sole verified Trash source backed by an
existing encrypted Processed current pointer, recovers that source's Raw, compares incumbent and
candidate parser versions, appends/re-recovers only the candidate shadow, and publishes exactly
one recoverable encrypted latest Timeline.  It has no Gmail mutation, current-pointer promotion,
schedule, GA, local persistence or plaintext output path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import quote

from .age_stream import OfficialAgeStream
from .attachment_inspector import AttachmentInspector
from .auth import SecretSource, load_gmail_oauth_credential
from .blue_green_runtime import (
    BlueGreenTimelineRunner,
    BlueGreenTimelineRunResult,
    RemoteCurrentProcessedPointerSource,
)
from .canary_runtime import ExistingProcessedReconciliationMatcher
from .canonical_raw import CanonicalRawFetcher
from .capacity import CapacityPolicy, CapacitySnapshot
from .document_parser import ParserActivation
from .github_guard import (
    GITHUB_API_ORIGIN,
    GITHUB_API_VERSION,
    LIVE_ASSET_NAME,
    LIVE_RELEASE_TAG,
    GitHubAppJwtSigner,
    GitHubEndpointGuard,
    GitHubInstallationTokenClient,
    InstallationToken,
    RepositoryLocator,
    RepositoryResolver,
)
from .gmail_discovery import (
    FullMailboxDiscoverer,
    GmailReadClient,
    MessageMetadataUnverifiable,
    MinimalMessage,
)
from .gmail_guard import GmailEndpointGuard
from .http_boundary import HttpRequest, HttpResponse, HttpTransport
from .m3 import M3State
from .oauth import GmailAccessToken, GmailBearerTransport, GmailOAuthTokenClient
from .operation_gate import OperationalGate
from .processed_commit import (
    GitHubProcessedCiphertextStore,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
)
from .processed_models import ClassificationActivation
from .production_adapters import OfficialAgeCrypto, RemoteFirstImportTimestampSource
from .protected_beta import (
    AGE_IDENTITY_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    _load_base64_key,
    _load_secret_bytes,
    _ProtectedIdentityFile,
    _read_secret,
    _verify_identity_recipient,
)
from .protected_m3 import (
    M3_SECRET_NAMES,
    ProtectedM3Config,
    _load_classification_registry,
    _load_config,
    _load_parser_registry,
    _load_sender_registry,
)
from .raw_commit import GitHubAppendOnlyCiphertextStore, OpaqueIdFactory, RawCommitPlanner
from .release_control import PhaseObservation
from .remote_recovery_gate import (
    OfficialAgeDecryptor,
    RemoteRecoveryGate,
    RepositoryCiphertextReader,
)
from .secret_values import SecretBytes
from .sender_registry import (
    MessageVerification,
    RegistryActivation,
    SenderDecision,
    SenderRegistry,
    SenderVerifier,
    VerificationPhase,
)
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
    TimelineSnapshotRecoveryProof,
)

BLUE_GREEN_SECRET_NAMES = M3_SECRET_NAMES
INCUMBENT_PARSER_VERSION = "1.0.0"
CANDIDATE_PARSER_VERSION = "2.0.0"
MAXIMUM_VERIFIED_SOURCE_READS = 1

_MAX_PRIVATE_KEY_BYTES = 32 * 1024
_MAX_IDENTITY_BYTES = 4096
_MAX_CAPACITY_RESPONSE_BYTES = 32 * 1024 * 1024
_MAX_CAPACITY_TREE_ENTRIES = 100_000
_SAFE_DEFAULT_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")


class ProtectedBlueGreenBootstrapError(RuntimeError):
    """A protected T0704 prerequisite failed without exposing a protected value."""


class _LiveRepositoryCapacityProbe:
    """Refresh bounded capacity facts without granting a write endpoint."""

    def __init__(
        self,
        guard: GitHubEndpointGuard,
        locator: RepositoryLocator,
        token: InstallationToken,
    ) -> None:
        self._guard = guard
        self._locator = locator
        self._token = token

    def observe(self, prior: ProtectedM3Config) -> CapacitySnapshot:
        previous = prior.capacity.observed_snapshot
        limits = prior.capacity.limits
        if previous is None or limits is None:
            raise ProtectedBlueGreenBootstrapError(
                "protected capacity continuity context is unavailable"
            )
        metadata = self._repository_metadata()
        size_kib = _non_negative_integer(metadata, "size")
        default_branch = _required_capacity_string(metadata, "default_branch")
        if _SAFE_DEFAULT_BRANCH.fullmatch(default_branch) is None or any(
            part in {"", ".", ".."} for part in default_branch.split("/")
        ):
            raise ProtectedBlueGreenBootstrapError("protected capacity default branch is invalid")
        full_name = metadata.get("full_name")
        if (
            metadata.get("id") != self._locator.repository_id
            or metadata.get("private") is not True
            or full_name != f"{self._locator.owner}/{self._locator.name}"
        ):
            raise ProtectedBlueGreenBootstrapError("protected capacity repository identity differs")

        tree = self._tree(default_branch)
        entries = tree.get("tree")
        if (
            tree.get("truncated") is not False
            or not isinstance(entries, list)
            or len(entries) > _MAX_CAPACITY_TREE_ENTRIES
        ):
            raise ProtectedBlueGreenBootstrapError(
                "protected capacity tree is incomplete or unbounded"
            )
        largest_blob = 0
        tree_bytes = 0
        for entry in entries:
            if not isinstance(entry, dict):
                raise ProtectedBlueGreenBootstrapError("protected capacity tree entry is invalid")
            entry_value = cast(dict[str, object], entry)
            path = _required_capacity_string(entry_value, "path")
            if any(part == ".gitattributes" for part in path.split("/")):
                raise ProtectedBlueGreenBootstrapError(
                    "protected capacity cannot prove zero new LFS usage"
                )
            if entry_value.get("type") != "blob":
                continue
            size = _non_negative_integer(entry_value, "size")
            largest_blob = max(largest_blob, size)
            tree_bytes += size

        # GitHub reports repository size in KiB and refreshes it asynchronously.  One extra
        # KiB plus the current-tree sum makes rounding/lag conservative before prospective
        # mutation demand is applied by OperationalGate.
        repository_bytes = max((size_kib + 1) * 1024, tree_bytes)
        return CapacitySnapshot(
            git_repository_bytes=repository_bytes,
            lfs_storage_bytes=previous.lfs_storage_bytes,
            largest_git_object_bytes=max(
                previous.largest_git_object_bytes,
                largest_blob,
            ),
            largest_lfs_object_bytes=previous.largest_lfs_object_bytes,
            live_release_asset_bytes=self._live_release_asset_bytes(),
        )

    def _repository_metadata(self) -> dict[str, object]:
        response = self._guard.send(
            HttpRequest(
                "GET",
                GITHUB_API_ORIGIN + f"/repositories/{self._locator.repository_id}",
                headers=self._headers(),
            )
        )
        if response.status != 200:
            raise ProtectedBlueGreenBootstrapError(
                "protected capacity repository metadata is unavailable"
            )
        return _capacity_object(response)

    def _tree(self, default_branch: str) -> dict[str, object]:
        encoded_ref = quote(default_branch, safe="")
        url = (
            GITHUB_API_ORIGIN
            + f"/repos/{self._locator.owner}/{self._locator.name}"
            + f"/git/trees/{encoded_ref}?recursive=1"
        )
        response = self._guard.send(HttpRequest("GET", url, headers=self._headers()))
        if response.status != 200:
            raise ProtectedBlueGreenBootstrapError(
                "protected capacity tree observation is unavailable"
            )
        return _capacity_object(response)

    def _live_release_asset_bytes(self) -> int:
        release_response = self._guard.send(
            HttpRequest(
                "GET",
                GITHUB_API_ORIGIN
                + f"/repos/{self._locator.owner}/{self._locator.name}"
                + f"/releases/tags/{LIVE_RELEASE_TAG}",
                headers=self._headers(),
            )
        )
        if release_response.status == 404:
            return 0
        if release_response.status != 200:
            raise ProtectedBlueGreenBootstrapError("protected capacity live Release is unavailable")
        release = _capacity_object(release_response)
        release_id = _positive_integer(release, "id")
        if (
            release.get("tag_name") != LIVE_RELEASE_TAG
            or release.get("draft") is not False
            or release.get("prerelease") is not False
        ):
            raise ProtectedBlueGreenBootstrapError(
                "protected capacity live Release identity differs"
            )
        assets_response = self._guard.send(
            HttpRequest(
                "GET",
                GITHUB_API_ORIGIN
                + f"/repos/{self._locator.owner}/{self._locator.name}"
                + f"/releases/{release_id}/assets",
                headers=self._headers(),
            )
        )
        assets = _capacity_list(assets_response, expected_status=200)
        if len(assets) > 1:
            raise ProtectedBlueGreenBootstrapError(
                "protected capacity observed multiple live Timeline assets"
            )
        if not assets:
            return 0
        asset = assets[0]
        if asset.get("name") != LIVE_ASSET_NAME or asset.get("state") != "uploaded":
            raise ProtectedBlueGreenBootstrapError("protected capacity live Timeline asset differs")
        return _non_negative_integer(asset, "size")

    def _headers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Accept", "application/vnd.github+json"),
            ("Authorization", "Bearer " + self._token.value.reveal()),
            ("X-GitHub-Api-Version", GITHUB_API_VERSION),
        )


@dataclass(frozen=True, slots=True)
class ProtectedBlueGreenRunResult:
    """Aggregate-only result for one exact protected T0704 execution."""

    mechanism: BlueGreenTimelineRunResult
    full_reconcile_runs: int
    full_reconcile_difference: int
    selected_sources: int
    gmail_mutations: int
    current_pointer_mutations: int
    timeline_snapshot_fact_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.mechanism, BlueGreenTimelineRunResult)
            or self.full_reconcile_runs != 1
            or self.full_reconcile_difference != 0
            or self.selected_sources != 1
            or self.gmail_mutations != 0
            or self.current_pointer_mutations != 0
            or self.timeline_snapshot_fact_count < 1
            or not self.mechanism.ready_for_protected_promotion
            or self.mechanism.unresolved_comparison_differences != 0
            or self.mechanism.final_live_timeline_assets != 1
        ):
            raise ProtectedBlueGreenBootstrapError(
                "protected Blue-Green result is not evidence-complete"
            )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.protected-blue-green-public.v1",
            "status": "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL",
            "phase": self.mechanism.phase.value,
            "provenance": "PROTECTED_GITHUB_ACTIONS",
            "observed_runs": 1,
            "selected_verified_source_bucket": "ONE",
            "processed_recoveries": self.mechanism.candidate_processed_recoveries,
            "parser_comparisons": self.mechanism.parser_comparisons,
            "timeline_snapshot_recoveries": self.mechanism.timeline_snapshot_recoveries,
            "timeline_publish_attempts": self.mechanism.timeline_publish_attempts,
            "full_reconcile_runs": self.full_reconcile_runs,
            "full_reconcile_difference": self.full_reconcile_difference,
            "unresolved_comparison_differences": (self.mechanism.unresolved_comparison_differences),
            "gmail_mutations": 0,
            "current_pointer_mutations": 0,
            "minimum_live_timeline_assets": 1,
            "maximum_live_timeline_assets": 1,
            "fixed_calendar_wait_days": 0,
            "candidate_shadow_only": True,
            "incumbent_current_retained": True,
            "exact_mailbox_counts_disclosed": False,
            "production_health_claimed": False,
            "final_acceptance_claimed": False,
        }


@dataclass(slots=True, repr=False)
class ProtectedBlueGreenRuntime:
    """Single-use T0704 runtime owning every destructible protected resource."""

    _gmail: GmailReadClient
    _sender_registry: SenderRegistry
    _verifier: SenderVerifier
    _raw_fetcher: CanonicalRawFetcher
    _inspector: AttachmentInspector
    _raw_planner: RawCommitPlanner
    _raw_recovery: RemoteRecoveryGate
    _source_matcher: ExistingProcessedReconciliationMatcher
    _first_import: RemoteFirstImportTimestampSource
    _runner: BlueGreenTimelineRunner
    _config: ProtectedM3Config
    _predecessors: tuple[PhaseObservation, ...]
    _clock: Callable[[], datetime]
    _gmail_token: GmailAccessToken
    _installation_token: InstallationToken
    _opaque_key: SecretBytes
    _identity: _ProtectedIdentityFile
    _closed: bool = False
    _run_started: bool = False

    def __repr__(self) -> str:
        return (
            "ProtectedBlueGreenRuntime(phase='BLUE_GREEN', resources=<protected>, "
            f"closed={self._closed}, run_started={self._run_started})"
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def run(self) -> ProtectedBlueGreenRunResult:
        if self._closed or self._run_started:
            raise ProtectedBlueGreenBootstrapError(
                "protected Blue-Green runtime is closed or already used"
            )
        self._run_started = True
        try:
            discovery = FullMailboxDiscoverer(self._gmail).scan()
            matches: list[tuple[MinimalMessage, MessageVerification]] = []
            requested_headers = self._sender_registry.requested_header_names
            for ref in discovery.refs:
                try:
                    message = self._gmail.get_metadata(
                        ref.message_id,
                        header_names=requested_headers,
                    )
                except MessageMetadataUnverifiable:
                    continue
                verification = self._verifier.verify_message(
                    message,
                    self._sender_registry,
                    phase=VerificationPhase.PRE_RAW,
                )
                if (
                    verification.decision is SenderDecision.VERIFIED
                    and "TRASH" in message.label_ids
                    and self._source_matcher.has_preexisting_current(ref.message_id)
                ):
                    matches.append((message, verification))
            if len(matches) != 1:
                raise ProtectedBlueGreenBootstrapError(
                    "protected Blue-Green source is not exactly one verified current match"
                )
            message, verification = matches[0]
            permit = verification.raw_fetch_permit
            if permit is None:
                raise ProtectedBlueGreenBootstrapError(
                    "protected Blue-Green source has no Raw permit"
                )
            canonical = self._raw_fetcher.fetch(permit, self._sender_registry)
            attachments = self._inspector.inspect(canonical)
            raw_plan = self._raw_planner.plan(
                canonical,
                attachments,
                key_epoch=self._config.key_epoch,
            )
            raw_proof = self._raw_recovery.verify_raw_only(
                canonical,
                verification,
                raw_plan,
            )
            observed_at = _require_utc(self._clock())
            imported_at = self._first_import.resolve(
                raw_plan.opaque_message_id,
                observed_at,
            )
            historical_labels = self._first_import.resolve_label_state(
                raw_plan.opaque_message_id,
                observed_at,
            )
            if historical_labels is None:
                raise ProtectedBlueGreenBootstrapError(
                    "protected Blue-Green historical source state is unavailable"
                )
            mechanism, snapshot = self._runner.run(
                canonical,
                verification,
                raw_plan,
                raw_proof,
                incumbent_parser_version=INCUMBENT_PARSER_VERSION,
                candidate_parser_version=CANDIDATE_PARSER_VERSION,
                key_epoch=self._config.key_epoch,
                imported_at_utc=imported_at,
                observed_at_utc=observed_at,
                observed_days=0,
                label_state_override=historical_labels,
                m3_state=M3State.ALREADY_TRASHED,
                independent_activity_evidence=None,
                market_session_expected=None,
                sla_exceeded=None,
                predecessor_observations=self._predecessors,
                beta_message_budget=self._config.beta_message_budget,
            )
            return _result(mechanism, snapshot)
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
            raise ProtectedBlueGreenBootstrapError(
                "protected Blue-Green resource cleanup failed"
            ) from cleanup_failure


class ProtectedBlueGreenBootstrap:
    """Assemble exactly one protected T0704 runner from the existing eight inputs."""

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
            raise ProtectedBlueGreenBootstrapError("synthetic ephemeral-root flag is invalid")
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
    ) -> Iterator[ProtectedBlueGreenRuntime]:
        now = _require_utc(self._clock())
        with ExitStack() as resources:
            try:
                config = _load_config(
                    self._secret_source,
                    now,
                    allow_stale_capacity_for_live_refresh=True,
                )
                sender_registry = _load_sender_registry(self._secret_source)
                classification_registry = _load_classification_registry(self._secret_source)
                parser_registry = _load_parser_registry(self._secret_source)
            except Exception as exc:
                raise ProtectedBlueGreenBootstrapError(
                    "protected Blue-Green configuration is invalid"
                ) from exc
            active_processing = (
                classification_registry.activation is ClassificationActivation.ACTIVE
                and parser_registry.activation is ParserActivation.ACTIVE
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
                raise ProtectedBlueGreenBootstrapError(
                    "protected Blue-Green registries are incompatible"
                )

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
                raise ProtectedBlueGreenBootstrapError(
                    "protected GitHub App private key is invalid"
                ) from exc
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
                temporary_prefix="moomooau-protected-blue-green-",
            )
            resources.callback(identity.close)
            identity_secret.destroy()
            _verify_identity_recipient(self._age, config.age_recipient, identity)

            github_guard = GitHubEndpointGuard(
                self._github_transport,
                config.target_repository,
            )
            installation_token = GitHubInstallationTokenClient(
                github_guard,
                config.target_repository,
                signer,
            ).mint(now)
            resources.callback(installation_token.destroy)
            github_private_key.destroy()
            locator = RepositoryResolver(
                github_guard,
                config.target_repository,
            ).resolve(installation_token)
            limits = config.capacity.limits
            if limits is None:
                raise ProtectedBlueGreenBootstrapError("protected capacity limits are unavailable")
            live_capacity = _LiveRepositoryCapacityProbe(
                github_guard,
                locator,
                installation_token,
            ).observe(config)
            config = replace(
                config,
                capacity=CapacityPolicy().evaluate(live_capacity, limits),
                capacity_observed_at_utc=now,
            )

            # No Gmail credential exchange or application read is allowed until the stale
            # config snapshot has been replaced by this run's bounded repository observation.
            gmail_credential = load_gmail_oauth_credential(self._secret_source)
            resources.callback(gmail_credential.destroy)
            gmail_token = GmailOAuthTokenClient(self._oauth_transport).exchange(
                gmail_credential,
                now_utc=now,
            )
            resources.callback(gmail_token.destroy)
            gmail_credential.destroy()

            gmail_guard = GmailEndpointGuard(
                GmailBearerTransport(
                    self._gmail_transport,
                    gmail_token,
                    clock=self._clock,
                )
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
            recovery = RemoteRecoveryGate(
                RepositoryCiphertextReader(raw_store, processed_store),
                decryptor,
            )
            processed_planner = ProcessedCommitPlanner(self._age, config.age_recipient)
            current_source = RemoteCurrentProcessedPointerSource(
                processed_store,
                decryptor,
            )
            opaque_ids = OpaqueIdFactory(opaque_key)
            verifier = SenderVerifier()
            runner = BlueGreenTimelineRunner(
                classification_registry,
                parser_registry,
                current_source,
                processed_planner,
                ProcessedCommitSaga(processed_store),
                recovery,
                TimelineSnapshotPlanner(self._age, config.age_recipient),
                TimelineSnapshotCommitSaga(processed_store),
                TimelineSnapshotRecoveryGate(processed_store, decryptor),
                SingleLatestTimelinePublisher(
                    DeterministicTimelineRenderer(),
                    OfficialAgeCrypto(self._age, config.age_recipient, decryptor),
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
                OperationalGate(config.capacity),
            )
            runtime = ProtectedBlueGreenRuntime(
                gmail,
                sender_registry,
                verifier,
                CanonicalRawFetcher(gmail_guard, verifier),
                AttachmentInspector(),
                RawCommitPlanner(self._age, config.age_recipient, opaque_ids),
                recovery,
                ExistingProcessedReconciliationMatcher(opaque_ids, processed_store),
                RemoteFirstImportTimestampSource(processed_store, decryptor),
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


def _result(
    mechanism: BlueGreenTimelineRunResult,
    snapshot: TimelineSnapshotRecoveryProof,
) -> ProtectedBlueGreenRunResult:
    return ProtectedBlueGreenRunResult(
        mechanism=mechanism,
        full_reconcile_runs=1,
        full_reconcile_difference=0,
        selected_sources=1,
        gmail_mutations=0,
        current_pointer_mutations=mechanism.current_pointer_mutations,
        timeline_snapshot_fact_count=len(snapshot.facts),
    )


def _require_utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ProtectedBlueGreenBootstrapError("protected Blue-Green timestamp must be UTC")
    return value.astimezone(UTC)


def _capacity_json(response: HttpResponse, *, expected_status: int) -> object:
    if (
        response.status != expected_status
        or not response.body
        or len(response.body) > _MAX_CAPACITY_RESPONSE_BYTES
    ):
        raise ProtectedBlueGreenBootstrapError(
            "protected capacity response is unavailable or unbounded"
        )
    try:
        return json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedBlueGreenBootstrapError("protected capacity response is invalid") from exc


def _capacity_object(response: HttpResponse) -> dict[str, object]:
    value = _capacity_json(response, expected_status=200)
    if not isinstance(value, dict):
        raise ProtectedBlueGreenBootstrapError("protected capacity response must be an object")
    return cast(dict[str, object], value)


def _capacity_list(
    response: HttpResponse,
    *,
    expected_status: int,
) -> list[dict[str, object]]:
    value = _capacity_json(response, expected_status=expected_status)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ProtectedBlueGreenBootstrapError("protected capacity response must be an object list")
    return [cast(dict[str, object], item) for item in value]


def _required_capacity_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item or len(item.encode("utf-8")) > 1024:
        raise ProtectedBlueGreenBootstrapError("protected capacity string field is invalid")
    return item


def _non_negative_integer(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or not 0 <= item < 2**63:
        raise ProtectedBlueGreenBootstrapError("protected capacity integer field is invalid")
    return item


def _positive_integer(value: dict[str, object], key: str) -> int:
    item = _non_negative_integer(value, key)
    if item == 0:
        raise ProtectedBlueGreenBootstrapError("protected capacity positive field is invalid")
    return item
