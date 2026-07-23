from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest
import yaml
from stage3_support import metadata_headers, synthetic_address, synthetic_registry
from stage7_support import (
    canary_context,
    canary_message,
    phase_observation,
    protected_beta_context,
)

from moomooau_archive.age_stream import is_age_envelope
from moomooau_archive.auth import (
    GMAIL_MODIFY_SCOPE,
    GMAIL_OAUTH_SECRET_NAME,
    GmailOAuthCredential,
)
from moomooau_archive.canary_runtime import CanaryRuntimeError
from moomooau_archive.capacity import CapacityAssessment, CapacityState
from moomooau_archive.gmail_discovery import HeaderSnapshot, MessageRef, MinimalMessage
from moomooau_archive.gmail_guard import (
    GmailEndpointGuard,
    get_message_request,
    list_messages_request,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.http_transport import HttpTransportError, StdlibHttpsTransport, _NoRedirect
from moomooau_archive.oauth import (
    GmailBearerTransport,
    GmailOAuthTokenClient,
    OAuthExchangeError,
)
from moomooau_archive.operation_gate import OperationGateError
from moomooau_archive.protected_beta import (
    AGE_IDENTITY_SECRET_NAME,
    BETA_CONFIG_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    ProtectedBetaBootstrap,
    ProtectedBetaBootstrapError,
)
from moomooau_archive.protected_beta_entrypoint import (
    BETA_SECRET_NAMES,
    CONTROL_OWNER_ID,
    CONTROL_REF,
    CONTROL_REPOSITORY_ID,
    CONTROL_WORKFLOW_REF,
    PROTECTED_ENVIRONMENT,
    RAW_ONLY_CONFIRMATION,
    ExactBetaEnvironmentSecretSource,
    ProtectedBetaEntrypointError,
    alpha_gate_sha256,
    execute_protected,
    execution_contract,
)
from moomooau_archive.release_control import (
    FeatureFlags,
    GateStatus,
    ObservationProvenance,
    ReleasePhase,
    Stage7ReleaseGate,
)
from moomooau_archive.secret_values import SecretText
from moomooau_archive.sender_registry import SenderDecision, SenderVerifier, VerificationPhase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]


class RecordingTransport:
    def __init__(self, responses: tuple[HttpResponse, ...]) -> None:
        self.responses = list(responses)
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class FakeUrlResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = body
        self._status = status
        self.closed = False
        self.headers = Message()
        self.headers["Retry-After"] = "1"
        self.headers["Set-Cookie"] = "must-not-cross-boundary"

    def getcode(self) -> int:
        return self._status

    def read(self, amount: int = -1) -> bytes:
        return self._body[:amount]

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, response: FakeUrlResponse) -> None:
        self.response = response
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: float | None = None) -> FakeUrlResponse:
        assert timeout == 30.0
        self.requests.append(request)
        return self.response


def _credential() -> GmailOAuthCredential:
    return GmailOAuthCredential(
        SecretText("synthetic-client"),
        SecretText("synthetic-client-secret"),
        SecretText("synthetic-refresh-token"),
    )


def _protected_github_environment(*, head_sha: str = "a" * 40) -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY_ID": str(CONTROL_REPOSITORY_ID),
        "GITHUB_REPOSITORY_OWNER_ID": str(CONTROL_OWNER_ID),
        "GITHUB_ACTOR_ID": str(CONTROL_OWNER_ID),
        "GITHUB_RUN_ID": "7002001",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": head_sha,
        "GITHUB_REF": CONTROL_REF,
        "GITHUB_WORKFLOW_REF": CONTROL_WORKFLOW_REF,
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MOOMOOAU_PROTECTED_ENVIRONMENT": PROTECTED_ENVIRONMENT,
    }


def test_t0702_beta_is_real_raw_only_and_local_claims_are_rejected() -> None:
    flags = FeatureFlags.for_phase(ReleasePhase.BETA_RAW_ONLY)
    assert flags.discovery_enabled and flags.raw_archive_enabled
    assert not flags.processing_enabled
    assert not flags.m3_enabled and flags.mutation_budget_per_run == 0
    assert not flags.timeline_enabled

    local_beta = phase_observation(
        ReleasePhase.BETA_RAW_ONLY,
        provenance=ObservationProvenance.LOCAL_SYNTHETIC,
    )
    report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.M3_CANARY,
        (phase_observation(ReleasePhase.ALPHA), local_beta),
        beta_message_budget=1,
    )
    assert report.status is GateStatus.BLOCKED
    assert "BETA_RAW_ONLY_PROTECTED_ORACLE_NOT_RUN" in report.reasons

    missing_recovery = phase_observation(
        ReleasePhase.BETA_RAW_ONLY,
        recovery_attempts=0,
        recovery_successes=0,
    )
    recovery_report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.M3_CANARY,
        (phase_observation(ReleasePhase.ALPHA), missing_recovery),
        beta_message_budget=1,
    )
    assert "BETA_RAW_RECOVERY_NOT_ONE_HUNDRED_PERCENT" in recovery_report.reasons

    processed_beta = phase_observation(
        ReleasePhase.BETA_RAW_ONLY,
        processed_messages=1,
    )
    boundary_report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.M3_CANARY,
        (phase_observation(ReleasePhase.ALPHA), processed_beta),
        beta_message_budget=1,
    )
    assert "BETA_RAW_ONLY_BOUNDARY_VIOLATED" in boundary_report.reasons


def test_t0702_exact_oauth_refresh_and_gmail_only_bearer_injection() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    token_payload = json.dumps(
        {
            "access_token": "synthetic-short-token",
            "expires_in": 3600,
            "scope": GMAIL_MODIFY_SCOPE,
            "token_type": "Bearer",
        }
    ).encode()
    oauth_transport = RecordingTransport((HttpResponse(200, token_payload),))
    credential = _credential()
    try:
        token = GmailOAuthTokenClient(oauth_transport).exchange(credential, now_utc=now)
    finally:
        credential.destroy()
    oauth_request = oauth_transport.requests[0]
    assert oauth_request.url == "https://oauth2.googleapis.com/token"
    assert oauth_request.body is not None
    form = parse_qs(oauth_request.body.decode("ascii"), strict_parsing=True)
    assert set(form) == {"client_id", "client_secret", "refresh_token", "grant_type"}
    assert form["grant_type"] == ["refresh_token"]
    assert "synthetic-short-token" not in repr(token)

    gmail_transport = RecordingTransport((HttpResponse(200, b'{"messages":[]}'),))
    bearer = GmailBearerTransport(
        gmail_transport,
        token,
        clock=lambda: now + timedelta(minutes=1),
    )
    GmailEndpointGuard(bearer).send(list_messages_request())
    sent = gmail_transport.requests[0]
    assert ("Authorization", "Bearer synthetic-short-token") in sent.headers
    with pytest.raises(OAuthExchangeError):
        bearer.send(HttpRequest("GET", "https://example.invalid/"))
    token.destroy()


def test_t0702_live_gmail_metadata_shape_excludes_content_and_accepts_rfc8601_dkim_i() -> None:
    request = get_message_request(
        "synthetic-live-shape",
        message_format="metadata",
        metadata_headers=("From", "Subject", "Authentication-Results"),
    )
    query = parse_qs(urlsplit(request.url).query, strict_parsing=True)
    assert query["fields"] == ["id,threadId,labelIds,historyId,internalDate,payload/headers"]

    sender = synthetic_address()
    authentication = (
        "mx.google.com; "
        f"spf=pass smtp.mailfrom={sender}; "
        "dkim=pass header.i=@synthetic.invalid; "
        "dmarc=pass header.from=synthetic.invalid"
    )
    message = MinimalMessage(
        ref=MessageRef("synthetic-live-shape", "thread-synthetic-live-shape"),
        history_id="100",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        headers=HeaderSnapshot(metadata_headers(auth_results=authentication)),
    )
    result = SenderVerifier().verify_message(
        message,
        synthetic_registry(),
        phase=VerificationPhase.PRE_RAW,
    )
    assert result.decision is SenderDecision.VERIFIED
    assert result.raw_fetch_permit is not None


def test_t0702_https_transport_bounds_and_sanitizes_response() -> None:
    response = FakeUrlResponse(b"1234")
    opener = FakeOpener(response)
    transport = StdlibHttpsTransport(maximum_response_bytes=4, opener=opener)
    result = transport.send(HttpRequest("GET", "https://gmail.googleapis.com/example"))
    assert result.status == 200 and result.body == b"1234"
    assert result.headers == (("Retry-After", "1"),)
    assert response.closed
    assert len(opener.requests) == 1

    oversized = FakeUrlResponse(b"12345")
    with pytest.raises(HttpTransportError, match="byte limit"):
        StdlibHttpsTransport(maximum_response_bytes=4, opener=FakeOpener(oversized)).send(
            HttpRequest("GET", "https://gmail.googleapis.com/example")
        )
    assert oversized.closed


def test_t0702_https_transport_rejects_non_tls_before_open() -> None:
    opener = FakeOpener(FakeUrlResponse(b"unused"))
    transport = StdlibHttpsTransport(opener=opener)
    with pytest.raises(HttpTransportError, match="boundary rejected"):
        transport.send(HttpRequest("GET", "http://gmail.googleapis.com/example"))
    assert opener.requests == []


def test_t0702_transport_and_bearer_errors_do_not_chain_private_urls() -> None:
    opener = FakeOpener(FakeUrlResponse(b"unused"))
    transport = StdlibHttpsTransport(opener=opener)
    with pytest.raises(HttpTransportError) as malformed:
        transport.send(HttpRequest("GET", "https://gmail.googleapis.com:private-port/example"))
    assert malformed.value.__cause__ is None
    assert "private-port" not in str(malformed.value)
    with pytest.raises(HttpTransportError, match="header is invalid"):
        transport.send(
            HttpRequest(
                "GET",
                "https://gmail.googleapis.com/example",
                headers=(("X:Invalid", "synthetic"),),
            )
        )
    assert opener.requests == []


def test_t0702_oauth_rejects_non_header_safe_access_token() -> None:
    payload = json.dumps(
        {
            "access_token": "synthetic-token\nnot-a-header",
            "expires_in": 3600,
            "scope": GMAIL_MODIFY_SCOPE,
            "token_type": "Bearer",
        }
    ).encode()
    credential = _credential()
    try:
        with pytest.raises(OAuthExchangeError, match="exact token contract"):
            GmailOAuthTokenClient(RecordingTransport((HttpResponse(200, payload),))).exchange(
                credential,
                now_utc=datetime(2026, 7, 20, tzinfo=UTC),
            )
    finally:
        credential.destroy()


def test_t0702_https_transport_never_follows_redirects() -> None:
    request = Request("https://gmail.googleapis.com/example")
    headers = Message()
    headers["Location"] = "https://example.invalid/redirect"
    redirect = cast(Callable[..., object | None], _NoRedirect().redirect_request)
    assert (
        redirect(
            request,
            BytesIO(),
            302,
            "Found",
            headers,
            "https://example.invalid/redirect",
        )
        is None
    )


def test_t0702_beta_runner_fetches_only_verified_raw_and_recovers_remote() -> None:
    unrelated = canary_message("msg-stage7-unrelated", verified=False)
    verified = canary_message("msg-stage7-verified")
    with canary_context((unrelated, verified)) as context:
        result = context.runner.run(
            ReleasePhase.BETA_RAW_ONLY,
            maximum_verified_candidates=1,
            key_epoch="synthetic-epoch-1",
            predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
            beta_message_budget=1,
        )
        assert context.transport.inner.raw_fetches == [verified.message_id]
        assert result.verified_candidates == 1
        assert result.archived_and_recovered == 1
        assert result.source_mutations == 0
        assert result.maximum_live_timeline_assets == 0
        assert all(is_age_envelope(item) for item in context.store.ciphertexts())
        public = result.to_public_dict()
        assert verified.message_id not in json.dumps(public)
        assert public["processing_enabled"] is False
        assert public["timeline_enabled"] is False


def test_t0702_beta_runner_blocks_unknown_capacity_before_raw_write() -> None:
    message = canary_message("msg-stage7-capacity")
    unknown = CapacityAssessment(
        CapacityState.UNKNOWN,
        False,
        False,
        ("OWNER_LFS_BUDGET_NOT_PROVISIONED",),
    )
    with canary_context((message,), capacity=unknown) as context:
        with pytest.raises(OperationGateError, match="fail-closed capacity"):
            context.runner.run(
                ReleasePhase.BETA_RAW_ONLY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
                beta_message_budget=1,
            )
        assert context.transport.inner.requests == []
        assert context.store.create_calls == 0


def test_t0702_beta_runner_requires_alpha_and_explicit_budget_before_network() -> None:
    message = canary_message("msg-stage7-no-alpha")
    with canary_context((message,)) as context:
        with pytest.raises(CanaryRuntimeError, match="predecessor gate is blocked"):
            context.runner.run(
                ReleasePhase.BETA_RAW_ONLY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                predecessor_observations=(),
                beta_message_budget=1,
            )
        assert context.transport.inner.requests == []
        assert context.store.create_calls == 0

        with pytest.raises(CanaryRuntimeError, match="configuration is invalid"):
            context.runner.run(
                ReleasePhase.BETA_RAW_ONLY,
                maximum_verified_candidates=2,
                key_epoch="synthetic-epoch-1",
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
                beta_message_budget=1,
            )
        assert context.transport.inner.requests == []
        assert context.store.create_calls == 0


def test_t0702_protected_bootstrap_runs_one_raw_only_beta_and_cleans_resources() -> None:
    unrelated = canary_message("msg-stage7-protected-unrelated", verified=False)
    verified = canary_message("msg-stage7-protected-verified")
    with protected_beta_context((unrelated, verified)) as context:
        with context.bootstrap.open(
            predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
        ) as runtime:
            assert not runtime.closed
            assert verified.message_id not in repr(runtime)
            result = runtime.run()
            assert runtime.closed
            assert result.verified_candidates == result.archived_and_recovered == 1
            assert result.source_mutations == 0
            assert result.maximum_live_timeline_assets == 0
            with pytest.raises(ProtectedBetaBootstrapError, match="already used"):
                runtime.run()

        assert runtime.closed
        assert list(context.tmpfs_root.iterdir()) == []
        assert context.source.all_issued_destroyed
        assert context.source.reads == [
            BETA_CONFIG_SECRET_NAME,
            SENDER_REGISTRY_SECRET_NAME,
            GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
            OPAQUE_ID_KEY_SECRET_NAME,
            AGE_IDENTITY_SECRET_NAME,
            GMAIL_OAUTH_SECRET_NAME,
        ]
        assert context.gmail_transport.inner.raw_fetches == [verified.message_id]
        assert context.gmail_transport.trashed_ids == []
        assert context.github_transport.write_calls == 2
        assert all(is_age_envelope(value) for value in context.github_transport.objects.values())
        assert all(
            path.startswith(("MooMooAU/Raw/", "MooMooAU/Manifests/raw/"))
            for path in context.github_transport.objects
        )
        assert len(context.oauth_transport.requests) == 1
        assert all("/releases" not in request.url for request in context.github_transport.requests)


def test_t0702_protected_bootstrap_blocks_before_network_without_alpha_or_registry() -> None:
    with protected_beta_context((canary_message("msg-stage7-protected-no-alpha"),)) as context:
        with pytest.raises(ProtectedBetaBootstrapError, match="Alpha predecessor"):
            with context.bootstrap.open(
                predecessor_observations=(),
            ):
                pytest.fail("blocked protected bootstrap yielded a runtime")
        assert context.source.reads == [BETA_CONFIG_SECRET_NAME]
        assert context.source.all_issued_destroyed
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []
        assert list(context.tmpfs_root.iterdir()) == []

    with protected_beta_context(
        (canary_message("msg-stage7-protected-invalid-github-key"),),
        github_key_valid=False,
    ) as context:
        with pytest.raises(ProtectedBetaBootstrapError, match="private key is invalid"):
            with context.bootstrap.open(
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
            ):
                pytest.fail("invalid GitHub key yielded a runtime")
        assert context.source.all_issued_destroyed
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []
        assert list(context.tmpfs_root.iterdir()) == []

    with protected_beta_context(
        (canary_message("msg-stage7-protected-empty-registry"),),
        sender_active=False,
    ) as context:
        with pytest.raises(ProtectedBetaBootstrapError, match="registry is not active"):
            with context.bootstrap.open(
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
            ):
                pytest.fail("inactive protected registry yielded a runtime")
        assert context.source.reads == [
            BETA_CONFIG_SECRET_NAME,
            SENDER_REGISTRY_SECRET_NAME,
        ]
        assert context.source.all_issued_destroyed
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []
        assert list(context.tmpfs_root.iterdir()) == []


def test_t0702_protected_bootstrap_rejects_stale_capacity_and_identity_drift() -> None:
    with protected_beta_context(
        (canary_message("msg-stage7-protected-stale-capacity"),),
        capacity_age_hours=25,
    ) as context:
        with pytest.raises(ProtectedBetaBootstrapError, match="absent or stale"):
            with context.bootstrap.open(
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
            ):
                pytest.fail("stale protected capacity yielded a runtime")
        assert context.source.reads == [BETA_CONFIG_SECRET_NAME]
        assert context.source.all_issued_destroyed
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []
        assert list(context.tmpfs_root.iterdir()) == []

    with protected_beta_context(
        (canary_message("msg-stage7-protected-wrong-identity"),),
        identity_matches_recipient=False,
    ) as context:
        with pytest.raises(ProtectedBetaBootstrapError, match="not bound"):
            with context.bootstrap.open(
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
            ):
                pytest.fail("mismatched protected age identity yielded a runtime")
        assert context.source.all_issued_destroyed
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []
        assert list(context.tmpfs_root.iterdir()) == []


def test_t0702_protected_bootstrap_requires_verified_tmpfs_by_default() -> None:
    with protected_beta_context(
        (canary_message("msg-stage7-protected-non-tmpfs"),),
    ) as context:
        strict_bootstrap = ProtectedBetaBootstrap(
            context.source,
            oauth_transport=context.oauth_transport,
            gmail_transport=context.gmail_transport,
            github_transport=context.github_transport,
            approved_tmpfs_root=context.tmpfs_root,
            clock=lambda: context.now,
        )
        with pytest.raises(ProtectedBetaBootstrapError, match="not verified tmpfs"):
            with strict_bootstrap.open(
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
            ):
                pytest.fail("non-tmpfs protected identity root yielded a runtime")
        assert context.source.all_issued_destroyed
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []
        assert list(context.tmpfs_root.iterdir()) == []


def test_t0702_entrypoint_contract_is_exact_raw_only_and_non_executing() -> None:
    contract = execution_contract(PROJECT_ROOT)
    assert contract["mode"] == "CONTRACT_ONLY"
    assert contract["required_actor_id"] == CONTROL_OWNER_ID
    assert contract["required_ref"] == "refs/heads/main"
    assert contract["required_workflow_ref"] == CONTROL_WORKFLOW_REF
    assert contract["protected_environment"] == "moomooau-beta"
    assert contract["required_runner_environment"] == "github-hosted"
    assert contract["required_run_attempt"] == 1
    assert contract["required_secret_names"] == list(BETA_SECRET_NAMES)
    assert len(contract["required_secret_names"]) == 6
    assert contract["alpha_gate_sha256"] == alpha_gate_sha256(PROJECT_ROOT)
    assert (
        contract["feature_flags"]
        == FeatureFlags.for_phase(ReleasePhase.BETA_RAW_ONLY).to_public_dict()
    )
    assert contract["maximum_source_mutations"] == 0
    assert contract["maximum_processed_writes"] == 0
    assert contract["maximum_timeline_mutations"] == 0
    assert contract["production_health_claimed"] is False


def test_t0702_entrypoint_secret_source_has_an_exact_six_name_allowlist() -> None:
    values = {name: f"synthetic-{index}" for index, name in enumerate(BETA_SECRET_NAMES)}
    source = ExactBetaEnvironmentSecretSource(values)
    issued = source.read(BETA_CONFIG_SECRET_NAME)
    try:
        assert issued.reveal() == "synthetic-0"
    finally:
        issued.destroy()
    with pytest.raises(ProtectedBetaEntrypointError, match="not allowlisted"):
        source.read("MOOMOOAU_UNDECLARED_SECRET")
    with pytest.raises(ProtectedBetaEntrypointError, match="unavailable"):
        ExactBetaEnvironmentSecretSource({}).read(BETA_CONFIG_SECRET_NAME)


def test_t0702_entrypoint_rejects_non_main_context_before_secret_reads() -> None:
    environment = _protected_github_environment()
    environment["GITHUB_REF"] = "refs/heads/candidate"
    with protected_beta_context((canary_message("msg-stage7-entrypoint-context"),)) as context:
        with pytest.raises(ProtectedBetaEntrypointError, match="context is not allowed"):
            execute_protected(
                environment,
                project_root=PROJECT_ROOT,
                expected_head_sha=environment["GITHUB_SHA"],
                supplied_alpha_gate_sha256=alpha_gate_sha256(PROJECT_ROOT),
                confirmation=RAW_ONLY_CONFIRMATION,
                bootstrap=context.bootstrap,
                clock=lambda: context.now,
            )
        assert context.source.reads == []
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []


def test_t0702_entrypoint_rejects_rerun_before_secret_reads() -> None:
    environment = _protected_github_environment()
    environment["GITHUB_RUN_ATTEMPT"] = "2"
    with protected_beta_context((canary_message("msg-stage7-entrypoint-rerun"),)) as context:
        with pytest.raises(ProtectedBetaEntrypointError, match="context is not allowed"):
            execute_protected(
                environment,
                project_root=PROJECT_ROOT,
                expected_head_sha=environment["GITHUB_SHA"],
                supplied_alpha_gate_sha256=alpha_gate_sha256(PROJECT_ROOT),
                confirmation=RAW_ONLY_CONFIRMATION,
                bootstrap=context.bootstrap,
                clock=lambda: context.now,
            )
        assert context.source.reads == []
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []


def test_t0702_entrypoint_rejects_non_cloud_runner_before_secret_reads() -> None:
    environment = _protected_github_environment()
    environment["RUNNER_ENVIRONMENT"] = "self-hosted"
    with protected_beta_context((canary_message("msg-stage7-entrypoint-runner"),)) as context:
        with pytest.raises(ProtectedBetaEntrypointError, match="context is not allowed"):
            execute_protected(
                environment,
                project_root=PROJECT_ROOT,
                expected_head_sha=environment["GITHUB_SHA"],
                supplied_alpha_gate_sha256=alpha_gate_sha256(PROJECT_ROOT),
                confirmation=RAW_ONLY_CONFIRMATION,
                bootstrap=context.bootstrap,
                clock=lambda: context.now,
            )
        assert context.source.reads == []
        assert context.oauth_transport.requests == []
        assert context.gmail_transport.inner.requests == []
        assert context.github_transport.requests == []


def test_t0702_entrypoint_executes_one_aggregate_only_protected_beta() -> None:
    message = canary_message("msg-stage7-entrypoint-verified")
    environment = _protected_github_environment()
    with protected_beta_context((message,)) as context:
        evidence = execute_protected(
            environment,
            project_root=PROJECT_ROOT,
            expected_head_sha=environment["GITHUB_SHA"],
            supplied_alpha_gate_sha256=alpha_gate_sha256(PROJECT_ROOT),
            confirmation=RAW_ONLY_CONFIRMATION,
            bootstrap=context.bootstrap,
            clock=lambda: context.now,
        )
        rendered = evidence.to_dict()
        assert rendered["status"] == "PROTECTED_BETA_RAW_ONLY_COMPLETED_NOT_FINAL"
        assert rendered["beta_message_budget_configured"] is True
        assert rendered["phase_observation"]["phase"] == "BETA_RAW_ONLY"
        assert rendered["phase_observation"]["provenance"] == "PROTECTED_GITHUB_ACTIONS"
        assert rendered["phase_observation"]["verified_within_configured_budget"] is True
        assert rendered["phase_observation"]["raw_recovery_one_hundred_percent"] is True
        assert rendered["phase_observation"]["exact_mailbox_counts_disclosed"] is False
        assert "beta_message_budget" not in rendered
        assert "verified_messages" not in rendered["phase_observation"]
        assert "recovery_attempts" not in rendered["phase_observation"]
        assert "recovery_successes" not in rendered["phase_observation"]
        assert rendered["boundaries"] == {
            "processing_enabled": False,
            "m3_enabled": False,
            "timeline_enabled": False,
            "gmail_mutations": 0,
            "processed_writes": 0,
            "timeline_mutations": 0,
        }
        assert rendered["beta_gate_status"] == "PASS"
        assert rendered["m3_executed"] is False
        assert rendered["production_health_claimed"] is False
        assert rendered["final_acceptance_claimed"] is False
        assert message.message_id not in json.dumps(rendered)
        assert context.gmail_transport.trashed_ids == []
    assert context.source.all_issued_destroyed


def test_t0702_entrypoint_blocks_zero_recovered_raw_without_claiming_beta() -> None:
    environment = _protected_github_environment()
    unrelated = canary_message("msg-stage7-entrypoint-unrelated", verified=False)
    with protected_beta_context((unrelated,)) as context:
        with pytest.raises(ProtectedBetaEntrypointError, match="recovered no verified Raw"):
            execute_protected(
                environment,
                project_root=PROJECT_ROOT,
                expected_head_sha=environment["GITHUB_SHA"],
                supplied_alpha_gate_sha256=alpha_gate_sha256(PROJECT_ROOT),
                confirmation=RAW_ONLY_CONFIRMATION,
                bootstrap=context.bootstrap,
                clock=lambda: context.now,
            )
        assert context.gmail_transport.trashed_ids == []
        assert context.github_transport.write_calls == 0
    assert context.source.all_issued_destroyed


def test_t0702_protected_workflow_is_manual_main_only_and_exact_six_secret() -> None:
    path = REPOSITORY_ROOT / ".github/workflows/moomooau-beta.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert workflow["on"].keys() == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["group"] == "moomooau-beta-raw-only-single-writer"
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["jobs"]["beta-raw-only"]["needs"] == "alpha-gate"
    assert workflow["jobs"]["beta-raw-only"]["environment"] == "moomooau-beta"
    first_step = workflow["jobs"]["alpha-gate"]["steps"][0]
    assert first_step["name"] == "Fail closed on invalid protected dispatch context"
    assert 'test "$GITHUB_ACTOR_ID" = "68840188"' in first_step["run"]
    assert 'test "$GITHUB_RUN_ATTEMPT" = "1"' in first_step["run"]
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in first_step["run"]
    assert 'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"' in first_step["run"]
    beta_first_step = workflow["jobs"]["beta-raw-only"]["steps"][0]
    assert beta_first_step["name"] == "Fail closed on non-cloud protected runner"
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in beta_first_step["run"]
    assert "if" not in workflow["jobs"]["alpha-gate"]
    assert "if" not in workflow["jobs"]["beta-raw-only"]
    secret_names = re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", text)
    assert len(secret_names) == 6
    assert set(secret_names) == set(BETA_SECRET_NAMES)
    assert text.count("python -m moomooau_archive.protected_beta_entrypoint") == 2
    assert "--contract-only" in text
    assert "--execute-protected" in text
    assert "tests/tasks/test_t0701.py tests/tasks/test_t0702.py" in text
    age_archive_sha256 = "bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377"
    assert text.count(age_archive_sha256) == 2
    assert "refs/heads/main" in text
    assert "moomooau-protected-beta-*" in text
    for forbidden in (
        "schedule:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_archive.production",
    ):
        assert forbidden not in text.casefold()
