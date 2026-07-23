from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from typing import cast
from urllib.parse import parse_qs
from urllib.request import Request

import pytest
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
from moomooau_archive.gmail_guard import GmailEndpointGuard, list_messages_request
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
from moomooau_archive.release_control import (
    FeatureFlags,
    GateStatus,
    ObservationProvenance,
    ReleasePhase,
    Stage7ReleaseGate,
)
from moomooau_archive.secret_values import SecretText


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
