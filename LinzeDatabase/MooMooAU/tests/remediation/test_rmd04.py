from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from build_delivery_status import build_status
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from stage3_support import registry_payload
from stage4_support import classification_registry_payload, parser_registry_payload
from stage7_support import (
    Stage7GmailTransport,
    SyntheticOAuthTransport,
    TrackingProtectedSecretSource,
    m3_canary_message,
    observations_through,
)
from validate_evidence import PROJECT_ROOT

from moomooau_archive.age_stream import OfficialAgeStream, is_age_envelope
from moomooau_archive.attachment_inspector import AttachmentKind
from moomooau_archive.auth import GMAIL_MODIFY_SCOPE, GMAIL_OAUTH_SECRET_NAME
from moomooau_archive.github_guard import (
    GMAIL_SYNC_STATE_PATH,
    LIVE_ASSET_NAME,
)
from moomooau_archive.gmail_discovery import MessageRef, SyncState
from moomooau_archive.gmail_sync_checkpoint import (
    GmailRunCheckpoint,
    _decode_checkpoint,
    _encode_checkpoint,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.processed_commit import RevisionedCiphertext
from moomooau_archive.processed_models import DocumentClass
from moomooau_archive.production import (
    CLASSIFICATION_REGISTRY_SECRET_NAME,
    PARSER_REGISTRY_SECRET_NAME,
    PRODUCTION_CONFIG_SECRET_NAME,
    ProductionBootstrap,
    ProductionBootstrapError,
    composition_contract,
    main,
)
from moomooau_archive.production_adapters import RemoteFirstImportTimestampSource
from moomooau_archive.protected_beta import (
    AGE_IDENTITY_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
)
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.release_control import PhaseObservation, ReleasePhase
from moomooau_archive.remote_recovery_gate import OfficialAgeDecryptor
from moomooau_archive.run_schedule import RunTrigger

RMD04_MANIFEST_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.4.json")
RMD04_MANIFEST_SHA256 = "24b24ce8bd25b85f6c4dce3f7fbf6c8770b24e88be13f52be1d8d6a87b0c6e15"
RMD04_PREDECESSOR_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.3.json")
RMD04_PREDECESSOR_SHA256 = "301fa1c6f5c46760c4aa3a7092bf0be77ca1a2e974e7b65e8b53dcf90db9925e"
RMD04_CONTROL_PREDECESSOR_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.2.json")
RMD04_CONTROL_PREDECESSOR_SHA256 = (
    "6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3"
)
RMD04_LEGACY_PATH = Path("taskpack/PACKAGE_MANIFEST.v1.0.1.json")
RMD04_LEGACY_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"


class SyntheticProductionGitHubTransport:
    """One private GitHub repository, Contents CAS and fixed Release over synthetic HTTP."""

    def __init__(
        self,
        *,
        repository_id: int,
        installation_id: int,
        now: datetime,
        events: list[str],
    ) -> None:
        self.repository_id = repository_id
        self.installation_id = installation_id
        self.now = now
        self.owner = "synthetic-owner"
        self.name = "synthetic-private-database"
        self.events = events
        self.requests: list[HttpRequest] = []
        self.objects: dict[str, bytes] = {}
        self.revisions: dict[str, str] = {}
        self.write_calls = 0
        self.maximum_assets = 0
        self.release_exists = False
        self.release_id = 701
        self.assets: dict[int, bytes] = {}
        self._next_asset_id = 1

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        parsed = urlsplit(request.url)
        if (
            request.method == "POST"
            and parsed.path == f"/app/installations/{self.installation_id}/access_tokens"
        ):
            return self._json(
                201,
                {
                    "token": "synthetic-production-installation-token",
                    "expires_at": (self.now + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "repositories": [{"id": self.repository_id}],
                    "permissions": {"contents": "write", "metadata": "read"},
                },
            )
        if request.method == "GET" and parsed.path == f"/repositories/{self.repository_id}":
            return self._json(
                200,
                {
                    "id": self.repository_id,
                    "private": True,
                    "full_name": f"{self.owner}/{self.name}",
                },
            )

        prefix = f"/repos/{self.owner}/{self.name}"
        content_prefix = prefix + "/contents/"
        if parsed.path.startswith(content_prefix):
            relative = unquote(parsed.path.removeprefix(content_prefix))
            return self._contents(request, relative)
        if request.method == "GET" and parsed.path == prefix + "/releases/tags/moomooau-live":
            return self._release() if self.release_exists else HttpResponse(404, b"{}")
        if request.method == "POST" and parsed.path == prefix + "/releases":
            if self.release_exists:
                return HttpResponse(422, b"{}")
            self.release_exists = True
            return self._release(status=201)
        if (
            request.method == "GET"
            and parsed.path == prefix + f"/releases/{self.release_id}/assets"
        ):
            return self._json(
                200,
                [self._asset(item_id, value) for item_id, value in sorted(self.assets.items())],
            )
        asset_prefix = prefix + "/releases/assets/"
        if parsed.path.startswith(asset_prefix):
            asset_id = int(parsed.path.removeprefix(asset_prefix))
            if request.method == "GET":
                value = self.assets.get(asset_id)
                if value is not None:
                    self.events.append("github_recovery_read")
                return HttpResponse(404, b"{}") if value is None else HttpResponse(200, value)
            if request.method == "DELETE" and asset_id in self.assets:
                del self.assets[asset_id]
                return HttpResponse(204, b"")
        upload_path = prefix + f"/releases/{self.release_id}/assets"
        if (
            parsed.hostname == "uploads.github.com"
            and request.method == "POST"
            and parsed.path == upload_path
            and request.body is not None
        ):
            asset_id = self._next_asset_id
            self._next_asset_id += 1
            self.assets[asset_id] = bytes(request.body)
            self.maximum_assets = max(self.maximum_assets, len(self.assets))
            return self._json(201, self._asset(asset_id, request.body))
        raise AssertionError("synthetic production GitHub received an unexpected request")

    def _contents(self, request: HttpRequest, relative: str) -> HttpResponse:
        if request.method == "GET":
            value = self.objects.get(relative)
            if value is None:
                return HttpResponse(404, b"{}")
            self.events.append("github_recovery_read")
            accept = dict(request.headers).get("Accept")
            if accept == "application/vnd.github.raw+json":
                return HttpResponse(200, value)
            return self._json(
                200,
                {
                    "content": base64.b64encode(value).decode("ascii"),
                    "encoding": "base64",
                    "sha": self.revisions[relative],
                },
            )
        if request.method != "PUT" or request.body is None:
            raise AssertionError("unexpected synthetic Contents method")
        payload = json.loads(request.body)
        expected = payload.get("sha")
        current = self.revisions.get(relative)
        if current != expected:
            return HttpResponse(409 if expected is not None else 422, b"{}")
        ciphertext = base64.b64decode(payload["content"], validate=True)
        self.write_calls += 1
        revision = hashlib.sha1(
            str(self.write_calls).encode("ascii") + b"\0" + ciphertext,
            usedforsecurity=False,
        ).hexdigest()
        self.objects[relative] = ciphertext
        self.revisions[relative] = revision
        return self._json(200 if current is not None else 201, {"content": {"sha": revision}})

    def _release(self, *, status: int = 200) -> HttpResponse:
        return self._json(
            status,
            {
                "id": self.release_id,
                "tag_name": "moomooau-live",
                "draft": False,
                "prerelease": False,
            },
        )

    @staticmethod
    def _asset(asset_id: int, value: bytes) -> dict[str, object]:
        return {
            "id": asset_id,
            "name": LIVE_ASSET_NAME,
            "state": "uploaded",
            "size": len(value),
        }

    @staticmethod
    def _json(status: int, payload: object) -> HttpResponse:
        return HttpResponse(
            status,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )


class _StoredProcessedView:
    def __init__(self, remote: SyntheticProductionGitHubTransport) -> None:
        self._remote = remote

    def fetch_current(self, relative_path: str) -> RevisionedCiphertext | None:
        value = self._remote.objects.get(relative_path)
        if value is None:
            return None
        return RevisionedCiphertext(value, self._remote.revisions[relative_path])

    def fetch_immutable(self, relative_path: str) -> bytes | None:
        return self._remote.objects.get(relative_path)


@dataclass(frozen=True, slots=True)
class ProductionSyntheticContext:
    bootstrap: ProductionBootstrap
    source: TrackingProtectedSecretSource
    oauth: SyntheticOAuthTransport
    gmail: Stage7GmailTransport
    github: SyntheticProductionGitHubTransport
    now: datetime
    identity: bytes
    tmpfs_root: Path


def _observation_dict(value: PhaseObservation) -> dict[str, object]:
    return {
        "phase": value.phase.value,
        "provenance": value.provenance.value,
        "started_at_utc": value.started_at_utc.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": value.ended_at_utc.isoformat().replace("+00:00", "Z"),
        "observed_runs": value.observed_runs,
        "scheduled_0430_runs": value.scheduled_0430_runs,
        "verified_messages": value.verified_messages,
        "source_mutations": value.source_mutations,
        "mutation_budget_max": value.mutation_budget_max,
        "recovery_attempts": value.recovery_attempts,
        "recovery_successes": value.recovery_successes,
        "processed_messages": value.processed_messages,
        "parser_blue_green_comparisons": value.parser_blue_green_comparisons,
        "timeline_publish_attempts": value.timeline_publish_attempts,
        "full_reconcile_runs": value.full_reconcile_runs,
        "collateral_mutations": value.collateral_mutations,
        "public_sensitive_findings": value.public_sensitive_findings,
        "logical_duplicates": value.logical_duplicates,
        "full_reconcile_difference": value.full_reconcile_difference,
        "minimum_live_timeline_assets": value.minimum_live_timeline_assets,
        "maximum_live_timeline_assets": value.maximum_live_timeline_assets,
        "unresolved_failures": value.unresolved_failures,
    }


@contextmanager
def _production_context(*, block_predecessor: bool = False) -> Iterator[ProductionSyntheticContext]:
    now = datetime(2026, 7, 22, 1, tzinfo=UTC)
    repository_id = 7_200_104
    installation_id = 8_200_104
    app_id = 9_200_104
    events: list[str] = []
    generated = AgeIdentityGenerator().generate()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-rmd04-production-")
    try:
        observations = [
            _observation_dict(item) for item in observations_through(ReleasePhase.BLUE_GREEN)
        ]
        if block_predecessor:
            observations[-1]["unresolved_failures"] = 1
        config = {
            "schema_version": "moomooau.production-config.v1",
            "phase": "GA",
            "key_epoch": "synthetic-epoch-1",
            "age_recipient": generated.recipient,
            "parser_current_version": "1.0.0",
            "beta_message_budget": 1,
            "ga_mutation_budget_per_run": 1,
            "github": {
                "app_id": app_id,
                "installation_id": installation_id,
                "repository_id": repository_id,
            },
            "capacity": {
                "observed_at_utc": now.isoformat().replace("+00:00", "Z"),
                "limits": {
                    "lfs_storage_budget_bytes": 10_000_000,
                    "lfs_object_maximum_bytes": 1_000_000,
                },
                "snapshot": {
                    "git_repository_bytes": 1_000,
                    "lfs_storage_bytes": 1_000,
                    "largest_git_object_bytes": 1_000,
                    "largest_lfs_object_bytes": 1_000,
                    "live_release_asset_bytes": 0,
                },
            },
            "predecessor_observations": observations,
        }
        values = {
            PRODUCTION_CONFIG_SECRET_NAME: json.dumps(
                config,
                sort_keys=True,
                separators=(",", ":"),
            ),
            SENDER_REGISTRY_SECRET_NAME: registry_payload().decode(),
            CLASSIFICATION_REGISTRY_SECRET_NAME: classification_registry_payload(
                ((DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV),)
            ).decode(),
            PARSER_REGISTRY_SECRET_NAME: parser_registry_payload(
                DocumentClass.DAILY_STATEMENT,
                AttachmentKind.CSV,
            ).decode(),
            GITHUB_APP_PRIVATE_KEY_SECRET_NAME: private_key_pem.decode("ascii"),
            AGE_IDENTITY_SECRET_NAME: generated.identity.reveal().decode("ascii"),
            OPAQUE_ID_KEY_SECRET_NAME: base64.b64encode(b"synthetic-protected-opaque-key-1").decode(
                "ascii"
            ),
            GMAIL_OAUTH_SECRET_NAME: json.dumps(
                {
                    "type": "authorized_user",
                    "client_id": "synthetic-production-client",
                    "client_secret": (  # pragma: allowlist secret
                        "synthetic-production-client-secret"
                    ),
                    "refresh_token": "synthetic-production-refresh-token",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "scopes": [GMAIL_MODIFY_SCOPE],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        source = TrackingProtectedSecretSource(values)
        oauth = SyntheticOAuthTransport()
        gmail = Stage7GmailTransport(
            (m3_canary_message("msg-rmd04-production"),),
            events=events,
        )
        github = SyntheticProductionGitHubTransport(
            repository_id=repository_id,
            installation_id=installation_id,
            now=now,
            events=events,
        )
        bootstrap = ProductionBootstrap(
            source,
            oauth_transport=oauth,
            gmail_transport=gmail,
            github_transport=github,
            approved_tmpfs_root=Path(temporary.name),
            clock=lambda: now,
            allow_synthetic_ephemeral_root=True,
        )
        yield ProductionSyntheticContext(
            bootstrap,
            source,
            oauth,
            gmail,
            github,
            now,
            generated.identity.reveal(),
            Path(temporary.name),
        )
    finally:
        generated.destroy()
        temporary.cleanup()


def test_rmd04_contract_only_is_offline_and_requires_explicit_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract = composition_contract()
    assert contract["status"] == "CONTRACT_ONLY_NO_EXECUTION"
    assert contract["schedule"] == {"cron": "30 4 * * *", "timezone": "Australia/Sydney"}
    assert contract["production_health_claimed"] is False
    assert main(["--contract-only"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == contract
    with pytest.raises(SystemExit) as failure:
        main([])
    assert failure.value.code == 2


def test_rmd04_protected_cli_without_exact_secrets_fails_closed_and_redacted(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        PRODUCTION_CONFIG_SECRET_NAME,
        SENDER_REGISTRY_SECRET_NAME,
        CLASSIFICATION_REGISTRY_SECRET_NAME,
        PARSER_REGISTRY_SECRET_NAME,
        GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
        AGE_IDENTITY_SECRET_NAME,
        OPAQUE_ID_KEY_SECRET_NAME,
        GMAIL_OAUTH_SECRET_NAME,
    ):
        monkeypatch.delenv(name, raising=False)
    assert main(["--execute-protected", "--event-name", "schedule"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "moomooau.production-execution-public.v1",
        "status": "BLOCKED",
        "reason_code": "PROTECTED_PRODUCTION_RUN_FAILED",
        "production_health_claimed": False,
    }


def test_rmd04_production_composition_recovers_before_exact_trash_and_keeps_one_asset() -> None:
    with _production_context() as context:
        verification_identity = context.tmpfs_root / "verification.agekey"
        verification_identity.write_bytes(context.identity)
        verification_identity.chmod(0o600)
        with context.bootstrap.open() as runtime:
            result = runtime.run(RunTrigger.SCHEDULE)
            assert runtime.closed is True

        public = result.to_public_dict()
        assert public["production_health_claimed"] is False
        assert result.plan.run_date_sydney.isoformat() == "2026-07-22"
        assert result.outcome.result.verified_candidates == 1
        assert result.outcome.result.processed_complete == 1
        assert result.outcome.result.confirmed_trashed == 1
        assert context.gmail.trashed_ids == ["msg-rmd04-production"]
        assert context.github.maximum_assets == len(context.github.assets) == 1
        assert context.github.events.index("github_recovery_read") < context.github.events.index(
            "trash"
        )
        assert context.github.write_calls > 0
        assert all(is_age_envelope(value) for value in context.github.objects.values())
        assert all(is_age_envelope(value) for value in context.github.assets.values())
        checkpoint_ciphertext = context.github.objects[GMAIL_SYNC_STATE_PATH]
        assert b"msg-rmd04-production" not in checkpoint_ciphertext

        decryptor = OfficialAgeDecryptor(
            OfficialAgeStream(),
            verification_identity,
            allowed_tmpfs_roots=(context.tmpfs_root,),
        )
        checkpoint_plaintext = decryptor.decrypt(checkpoint_ciphertext)
        checkpoint = json.loads(checkpoint_plaintext)
        assert checkpoint["schema_version"] == "moomooau.gmail-run-checkpoint.v2"
        assert checkpoint["last_successful_run_date_sydney"] == "2026-07-22"

        current_paths = [
            path
            for path in context.github.objects
            if path.startswith("MooMooAU/State/processed-current/")
        ]
        assert len(current_paths) == 1
        source_id = current_paths[0].removesuffix(".json.age").rsplit("/", 1)[1]
        imported = RemoteFirstImportTimestampSource(
            _StoredProcessedView(context.github),  # type: ignore[arg-type]
            decryptor,
        ).resolve(source_id, context.now + timedelta(days=1))
        assert imported == context.now
        verification_identity.unlink()
        assert list(context.tmpfs_root.iterdir()) == []
        assert context.source.all_issued_destroyed is True


def test_rmd04_blocked_predecessor_stops_before_any_credential_exchange_or_remote_call() -> None:
    with _production_context(block_predecessor=True) as context:
        with pytest.raises(ProductionBootstrapError, match="predecessor"):
            with context.bootstrap.open():
                pass
        assert context.source.reads == [PRODUCTION_CONFIG_SECRET_NAME]
        assert context.source.all_issued_destroyed is True
        assert context.oauth.requests == []
        assert context.gmail.inner.requests == []
        assert context.github.requests == []
        assert list(context.tmpfs_root.iterdir()) == []


def test_rmd04_checkpoint_reads_legacy_v1_and_writes_canonical_v2_watermark() -> None:
    legacy = json.dumps(
        {
            "schema_version": "moomooau.gmail-run-checkpoint.v1",
            "history_id": "9000",
            "known_refs": [{"message_id": "legacy-message", "thread_id": "legacy-thread"}],
            "pending_verified_refs": [],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    recovered = _decode_checkpoint(legacy)
    assert recovered.last_successful_run_date_sydney is None
    upgraded = GmailRunCheckpoint(
        SyncState("9000", (MessageRef("legacy-message", "legacy-thread"),)),
        (),
        date(2026, 7, 22),
    )
    encoded = json.loads(_encode_checkpoint(upgraded))
    assert encoded["schema_version"] == "moomooau.gmail-run-checkpoint.v2"
    assert encoded["last_successful_run_date_sydney"] == "2026-07-22"


def test_rmd04_status_preserves_composition_closure_through_later_packages() -> None:
    status = json.loads((PROJECT_ROOT / "machine/status/latest.json").read_text(encoding="utf-8"))
    assert status == build_status(PROJECT_ROOT)
    assert tuple(int(part) for part in status["package_version"].split(".")) >= (1, 0, 4)
    assert {
        "REV-P0-002",
        "REV-P0-003",
        "REV-P1-004",
        "REV-P2-007",
    }.issubset(status["resolved_review_findings"])
    assert "RMD-04_PRODUCTION_COMPOSITION_PENDING" not in status["blockers"]
    assert status["dimensions"]["formal_task_completion"]["completed"] == 7
    assert status["dimensions"]["final_acceptance"]["passed"] == 0
    assert status["dimensions"]["production_readiness"]["status"] == "BLOCKED"
    if status["package_version"] == "1.0.6":
        assert status["dimensions"]["protected_oracles"] == {
            "status": "FAILED",
            "declared": 43,
            "executed": 2,
            "passed": 1,
            "failed": 1,
            "not_run": 41,
        }
        assert status["dimensions"]["publication"] == {
            "status": "CONTROLLED_BETA_DELIVERY_NOT_FINAL",
            "controlled_main_deliveries": 6,
            "remote_publications": 0,
        }
    else:
        assert status["dimensions"]["protected_oracles"]["executed"] == 0
        assert status["dimensions"]["publication"]["status"] == "LOCAL_ONLY_NOT_PUBLISHED"


def test_rmd04_v104_package_is_the_immutable_direct_predecessor() -> None:
    manifest_path = PROJECT_ROOT / RMD04_MANIFEST_PATH
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == RMD04_MANIFEST_SHA256
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["package_id"] == "MMAU-ARCHIVE-TP-2026-07-22-V1.0.4"
    assert manifest["version"] == "1.0.4"
    assert manifest["predecessor"] == {
        "path": RMD04_PREDECESSOR_PATH.as_posix(),
        "sha256": RMD04_PREDECESSOR_SHA256,
        "status": "IMMUTABLE_CONTROL_PREDECESSOR",
    }
    assert manifest["control_predecessor"] == {
        "path": RMD04_CONTROL_PREDECESSOR_PATH.as_posix(),
        "sha256": RMD04_CONTROL_PREDECESSOR_SHA256,
        "status": "IMMUTABLE_CONTROL_PREDECESSOR",
    }
    assert manifest["legacy_baseline"] == {
        "path": RMD04_LEGACY_PATH.as_posix(),
        "sha256": RMD04_LEGACY_SHA256,
        "status": "IMMUTABLE_HISTORICAL_ARTIFACT",
    }
    provenance = json.loads(
        (PROJECT_ROOT / "taskpack/SOURCE_PROVENANCE.v1.0.4.json").read_text(encoding="utf-8")
    )
    assert provenance["effective_package"]["manifest"] == RMD04_MANIFEST_PATH.as_posix()
    assert provenance["semantic_delta"]["resolved_review_findings"] == ["REV-P0-002"]
