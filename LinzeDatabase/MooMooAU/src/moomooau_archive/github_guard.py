"""Repository-ID anchored GitHub App authentication and endpoint guard."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import cast
from urllib.parse import parse_qsl, quote, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .adapters import is_age_envelope
from .http_boundary import HttpRequest, HttpResponse, HttpTransport
from .secret_values import SecretBytes, SecretText

GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_UPLOAD_ORIGIN = "https://uploads.github.com"
GITHUB_API_VERSION = "2026-03-10"
PRIVATE_NAMESPACE = "MooMooAU/"
LIVE_RELEASE_TAG = "moomooau-live"
LIVE_ASSET_NAME = "timeline-latest.png.age"
TIMELINE_STATE_PATH = "MooMooAU/State/timeline-current.json.age"
GMAIL_SYNC_STATE_PATH = "MooMooAU/State/gmail-sync-current.json.age"
CONTENT_APPEND_MESSAGE = "moomooau: append encrypted object"
CONTENT_POINTER_MESSAGE = "moomooau: replace encrypted processed current pointer"
CONTENT_TIMELINE_STATE_MESSAGE = "moomooau: replace encrypted timeline current state"
CONTENT_GMAIL_SYNC_STATE_MESSAGE = "moomooau: replace encrypted gmail sync state"
CONTENTS_MAX_BYTES = 100 * 1024 * 1024
_LOCATOR_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_PROCESSED_CURRENT_PATH = re.compile(r"^MooMooAU/State/processed-current/[0-9a-f]{64}\.json\.age$")


class GitHubBoundaryError(RuntimeError):
    pass


class InstallationTokenFailureClass(StrEnum):
    """Closed, public-safe classes for the GitHub App token boundary."""

    UNCLASSIFIED = "UNCLASSIFIED"
    LOCAL_BOUNDARY_REJECTED = "LOCAL_BOUNDARY_REJECTED"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"
    AUTHENTICATION_REJECTED = "AUTHENTICATION_REJECTED"
    AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
    INSTALLATION_NOT_FOUND = "INSTALLATION_NOT_FOUND"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    REMOTE_SERVICE_FAILED = "REMOTE_SERVICE_FAILED"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    RESPONSE_SCOPE_REJECTED = "RESPONSE_SCOPE_REJECTED"


class GitHubInstallationTokenError(GitHubBoundaryError):
    """A fixed token failure class without response text, URL, or identifier."""

    def __init__(self, failure_class: InstallationTokenFailureClass) -> None:
        if not isinstance(failure_class, InstallationTokenFailureClass):
            raise TypeError("installation token failure class is invalid")
        super().__init__("installation token operation failed")
        self.failure_class = failure_class


class GitHubOperation(StrEnum):
    REPOSITORY_RESOLVE = "repository.resolve"
    INSTALLATION_TOKEN = "installation.token"
    CONTENT_READ = "contents.read"
    CONTENT_WRITE = "contents.write"
    RELEASE_READ = "release.read"
    RELEASE_CREATE = "release.create"
    RELEASE_ASSETS_LIST = "release.assets.list"
    RELEASE_ASSET_READ = "release.asset.read"
    RELEASE_ASSET_UPLOAD = "release.asset.upload"
    RELEASE_ASSET_DELETE = "release.asset.delete"


@dataclass(frozen=True, slots=True, repr=False)
class TargetRepositoryConfig:
    repository_id: int
    installation_id: int
    namespace: str = PRIVATE_NAMESPACE

    def __post_init__(self) -> None:
        if (
            type(self.repository_id) is not int
            or self.repository_id <= 0
            or type(self.installation_id) is not int
            or self.installation_id <= 0
            or self.namespace != PRIVATE_NAMESPACE
        ):
            raise GitHubBoundaryError("target repository configuration is invalid")

    def __repr__(self) -> str:
        return "TargetRepositoryConfig(repository_id=<protected>, installation_id=<protected>)"


@dataclass(frozen=True, slots=True, repr=False)
class RepositoryLocator:
    repository_id: int
    owner: str
    name: str

    def __post_init__(self) -> None:
        if (
            type(self.repository_id) is not int
            or self.repository_id <= 0
            or _LOCATOR_SEGMENT.fullmatch(self.owner) is None
            or _LOCATOR_SEGMENT.fullmatch(self.name) is None
        ):
            raise GitHubBoundaryError("resolved repository locator is invalid")

    def __repr__(self) -> str:
        return "RepositoryLocator(repository_id=<protected>, current_name=<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class InstallationToken:
    value: SecretText
    expires_at: datetime

    def __repr__(self) -> str:
        return f"InstallationToken(value=<redacted>, expires_at={self.expires_at.isoformat()!r})"

    def destroy(self) -> None:
        self.value.destroy()


@dataclass(frozen=True, slots=True)
class GitHubGuardMetrics:
    allowed_calls: int
    blocked_calls: int
    cross_repository_network_calls: int


class GitHubAppJwtSigner:
    """Create a maximum ten-minute RS256 GitHub App JWT in memory."""

    def __init__(self, app_id: int, private_key: SecretBytes) -> None:
        if type(app_id) is not int or app_id <= 0:
            raise GitHubBoundaryError("GitHub App ID is invalid")
        self._app_id = app_id
        self._private_key = private_key

    def sign(self, now: datetime) -> SecretText:
        current = _require_utc(now)
        try:
            key = serialization.load_pem_private_key(self._private_key.reveal(), password=None)
        except (TypeError, ValueError) as exc:
            raise GitHubBoundaryError("GitHub App key is invalid") from exc
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise GitHubBoundaryError("GitHub App key must be RSA")
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "exp": int((current + timedelta(minutes=9)).timestamp()),
            "iat": int((current - timedelta(seconds=60)).timestamp()),
            "iss": str(self._app_id),
        }
        signing_input = b".".join((_b64_json(header), _b64_json(claims)))
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return SecretText((signing_input + b"." + _b64(signature)).decode("ascii"))


class GitHubEndpointGuard:
    """Allow only the target repository's Contents and fixed live Release surfaces."""

    def __init__(self, transport: HttpTransport, config: TargetRepositoryConfig) -> None:
        self._transport = transport
        self._config = config
        self._locator: RepositoryLocator | None = None
        self._allowed_calls = 0
        self._blocked_calls = 0

    @property
    def metrics(self) -> GitHubGuardMetrics:
        return GitHubGuardMetrics(self._allowed_calls, self._blocked_calls, 0)

    def bind_repository(self, locator: RepositoryLocator) -> None:
        if locator.repository_id != self._config.repository_id:
            raise GitHubBoundaryError("resolved repository ID does not match protected target")
        self._locator = locator

    def send(self, request: HttpRequest) -> HttpResponse:
        try:
            self._validate(request)
        except GitHubBoundaryError:
            self._blocked_calls += 1
            raise
        self._allowed_calls += 1
        return self._transport.send(request)

    def _validate(self, request: HttpRequest) -> GitHubOperation:
        try:
            parsed = urlsplit(request.url)
            port = parsed.port
        except ValueError as exc:
            raise GitHubBoundaryError("GitHub URL is invalid") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"api.github.com", "uploads.github.com"}
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise GitHubBoundaryError("GitHub authority is not allowed")
        self._validate_headers(request.headers)
        try:
            query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise GitHubBoundaryError("GitHub query is invalid") from exc

        resolve_path = f"/repositories/{self._config.repository_id}"
        if (
            parsed.hostname == "api.github.com"
            and request.method == "GET"
            and parsed.path == resolve_path
        ):
            self._require_empty(request, query)
            return GitHubOperation.REPOSITORY_RESOLVE

        token_path = f"/app/installations/{self._config.installation_id}/access_tokens"
        if (
            parsed.hostname == "api.github.com"
            and request.method == "POST"
            and parsed.path == token_path
        ):
            if query:
                raise GitHubBoundaryError("installation token query is not allowed")
            self._validate_token_body(request.body)
            return GitHubOperation.INSTALLATION_TOKEN

        if self._locator is None:
            raise GitHubBoundaryError(
                "repository name must be resolved from the protected ID first"
            )
        owner = self._locator.owner
        name = self._locator.name
        repository_prefix = f"/repos/{owner}/{name}"

        content_prefix = repository_prefix + "/contents/"
        if parsed.hostname == "api.github.com" and parsed.path.startswith(content_prefix):
            relative = parsed.path.removeprefix(content_prefix)
            self._validate_private_path(relative)
            if request.method == "GET":
                if request.body is not None or any(
                    key != "ref" or not value for key, value in query
                ):
                    raise GitHubBoundaryError("Contents read request is invalid")
                return GitHubOperation.CONTENT_READ
            if request.method == "PUT" and request.body:
                if query:
                    raise GitHubBoundaryError("Contents write query is not allowed")
                self._validate_content_write_body(relative, request.body)
                return GitHubOperation.CONTENT_WRITE
            raise GitHubBoundaryError("Contents operation is not allowed")

        fixed_release_path = repository_prefix + f"/releases/tags/{LIVE_RELEASE_TAG}"
        if (
            parsed.hostname == "api.github.com"
            and request.method == "GET"
            and parsed.path == fixed_release_path
        ):
            self._require_empty(request, query)
            return GitHubOperation.RELEASE_READ

        releases_path = repository_prefix + "/releases"
        if (
            parsed.hostname == "api.github.com"
            and request.method == "POST"
            and parsed.path == releases_path
        ):
            if query:
                raise GitHubBoundaryError("Release create query is not allowed")
            self._validate_release_body(request.body)
            return GitHubOperation.RELEASE_CREATE

        assets_list = re.fullmatch(re.escape(releases_path) + r"/([1-9][0-9]*)/assets", parsed.path)
        if parsed.hostname == "api.github.com" and request.method == "GET" and assets_list:
            self._require_empty(request, query)
            return GitHubOperation.RELEASE_ASSETS_LIST

        asset_delete = re.fullmatch(
            re.escape(repository_prefix) + r"/releases/assets/([1-9][0-9]*)", parsed.path
        )
        if parsed.hostname == "api.github.com" and request.method == "GET" and asset_delete:
            self._require_empty(request, query)
            return GitHubOperation.RELEASE_ASSET_READ
        if parsed.hostname == "api.github.com" and request.method == "DELETE" and asset_delete:
            self._require_empty(request, query)
            return GitHubOperation.RELEASE_ASSET_DELETE

        asset_upload = re.fullmatch(
            re.escape(releases_path) + r"/([1-9][0-9]*)/assets", parsed.path
        )
        if parsed.hostname == "uploads.github.com" and request.method == "POST" and asset_upload:
            if query != [("name", LIVE_ASSET_NAME)] or request.body is None:
                raise GitHubBoundaryError("Release Asset upload is not the fixed live asset")
            if not is_age_envelope(request.body):
                raise GitHubBoundaryError("Release Asset upload is not an age envelope")
            return GitHubOperation.RELEASE_ASSET_UPLOAD

        raise GitHubBoundaryError("GitHub endpoint is not allowlisted")

    @staticmethod
    def _validate_headers(headers: tuple[tuple[str, str], ...]) -> None:
        allowed = {"accept", "authorization", "content-type", "user-agent", "x-github-api-version"}
        seen: set[str] = set()
        for name, value in headers:
            lowered = name.casefold()
            if (
                lowered not in allowed
                or lowered in seen
                or "\r" in name
                or "\n" in name
                or "\r" in value
                or "\n" in value
            ):
                raise GitHubBoundaryError("GitHub header is not allowed")
            seen.add(lowered)

    @staticmethod
    def _require_empty(request: HttpRequest, query: list[tuple[str, str]]) -> None:
        if query or request.body is not None:
            raise GitHubBoundaryError("GitHub read request must not include query or body")

    def _validate_token_body(self, body: bytes | None) -> None:
        payload = _decode_object(body)
        expected = {
            "permissions": {"contents": "write", "metadata": "read"},
            "repository_ids": [self._config.repository_id],
        }
        if payload != expected:
            raise GitHubBoundaryError("installation token scope is broader than the target")

    @staticmethod
    def _validate_content_write_body(relative: str, body: bytes) -> None:
        if not relative.endswith(".age"):
            raise GitHubBoundaryError("persistent private content must be age encrypted")
        if len(body) > 4 * ((CONTENTS_MAX_BYTES + 2) // 3) + 4096:
            raise GitHubBoundaryError("Contents write body exceeds the safe limit")
        payload = _decode_object(body)
        if _PROCESSED_CURRENT_PATH.fullmatch(relative) is not None:
            if (
                set(payload)
                not in (
                    {"content", "message"},
                    {"content", "message", "sha"},
                )
                or payload.get("message") != CONTENT_POINTER_MESSAGE
            ):
                raise GitHubBoundaryError("processed current pointer write is not strict CAS")
            revision = payload.get("sha")
            if revision is not None and (
                not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None
            ):
                raise GitHubBoundaryError("processed current pointer revision is invalid")
        elif relative == TIMELINE_STATE_PATH:
            if (
                set(payload) not in ({"content", "message"}, {"content", "message", "sha"})
                or payload.get("message") != CONTENT_TIMELINE_STATE_MESSAGE
            ):
                raise GitHubBoundaryError("Timeline current state write is not strict CAS")
            revision = payload.get("sha")
            if revision is not None and (
                not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None
            ):
                raise GitHubBoundaryError("Timeline current state revision is invalid")
        elif relative == GMAIL_SYNC_STATE_PATH:
            if (
                set(payload) not in ({"content", "message"}, {"content", "message", "sha"})
                or payload.get("message") != CONTENT_GMAIL_SYNC_STATE_MESSAGE
            ):
                raise GitHubBoundaryError("Gmail sync state write is not strict CAS")
            revision = payload.get("sha")
            if revision is not None and (
                not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None
            ):
                raise GitHubBoundaryError("Gmail sync state revision is invalid")
        elif (
            set(payload) != {"content", "message"}
            or payload.get("message") != CONTENT_APPEND_MESSAGE
        ):
            raise GitHubBoundaryError("Contents write body is not append-only")
        encoded = payload.get("content")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((CONTENTS_MAX_BYTES + 2) // 3):
            raise GitHubBoundaryError("Contents write payload exceeds the safe limit")
        try:
            ciphertext = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GitHubBoundaryError("Contents write payload is not valid base64") from exc
        if len(ciphertext) > CONTENTS_MAX_BYTES or not is_age_envelope(ciphertext):
            raise GitHubBoundaryError("Contents write payload is not an age envelope")

    @staticmethod
    def _validate_release_body(body: bytes | None) -> None:
        payload = _decode_object(body)
        expected = {
            "draft": False,
            "name": LIVE_RELEASE_TAG,
            "prerelease": False,
            "tag_name": LIVE_RELEASE_TAG,
        }
        if payload != expected:
            raise GitHubBoundaryError("Release creation is not the fixed live Release")

    @staticmethod
    def _validate_private_path(relative: str) -> None:
        if (
            not relative.startswith(PRIVATE_NAMESPACE)
            or re.fullmatch(r"[A-Za-z0-9._/-]+", relative) is None
            or "%" in relative
            or "//" in relative
            or any(segment in {"", ".", ".."} for segment in relative.split("/"))
        ):
            raise GitHubBoundaryError("private repository path is outside MooMooAU namespace")


class RepositoryResolver:
    def __init__(self, guard: GitHubEndpointGuard, config: TargetRepositoryConfig) -> None:
        self._guard = guard
        self._config = config

    def resolve(self, token: InstallationToken) -> RepositoryLocator:
        response = self._guard.send(
            HttpRequest(
                "GET",
                GITHUB_API_ORIGIN + f"/repositories/{self._config.repository_id}",
                headers=(
                    ("Accept", "application/vnd.github+json"),
                    ("Authorization", "Bearer " + token.value.reveal()),
                    ("X-GitHub-Api-Version", GITHUB_API_VERSION),
                ),
            )
        )
        if response.status != 200:
            raise GitHubBoundaryError("target repository resolution failed")
        payload = _decode_object(response.body)
        full_name = payload.get("full_name")
        if (
            payload.get("id") != self._config.repository_id
            or payload.get("private") is not True
            or not isinstance(full_name, str)
            or full_name.count("/") != 1
        ):
            raise GitHubBoundaryError("target repository identity response is invalid")
        owner, name = full_name.split("/", 1)
        locator = RepositoryLocator(self._config.repository_id, owner, name)
        self._guard.bind_repository(locator)
        return locator


class GitHubInstallationTokenClient:
    def __init__(
        self,
        guard: GitHubEndpointGuard,
        config: TargetRepositoryConfig,
        signer: GitHubAppJwtSigner,
    ) -> None:
        self._guard = guard
        self._config = config
        self._signer = signer

    def mint(self, now: datetime) -> InstallationToken:
        current = _require_utc(now)
        app_jwt = self._signer.sign(current)
        body = _canonical_json(
            {
                "permissions": {"contents": "write", "metadata": "read"},
                "repository_ids": [self._config.repository_id],
            }
        )
        try:
            request = HttpRequest(
                "POST",
                GITHUB_API_ORIGIN
                + f"/app/installations/{self._config.installation_id}/access_tokens",
                headers=(
                    ("Accept", "application/vnd.github+json"),
                    ("Authorization", "Bearer " + app_jwt.reveal()),
                    ("X-GitHub-Api-Version", GITHUB_API_VERSION),
                ),
                body=body,
            )
            try:
                response = self._guard.send(request)
            except GitHubBoundaryError as exc:
                raise GitHubInstallationTokenError(
                    InstallationTokenFailureClass.LOCAL_BOUNDARY_REJECTED
                ) from exc
            except Exception as exc:
                raise GitHubInstallationTokenError(
                    InstallationTokenFailureClass.TRANSPORT_FAILED
                ) from exc
        finally:
            app_jwt.destroy()
        if response.status != 201:
            failure_class = {
                400: InstallationTokenFailureClass.REQUEST_REJECTED,
                401: InstallationTokenFailureClass.AUTHENTICATION_REJECTED,
                403: InstallationTokenFailureClass.AUTHORIZATION_REJECTED,
                404: InstallationTokenFailureClass.INSTALLATION_NOT_FOUND,
                422: InstallationTokenFailureClass.REQUEST_REJECTED,
            }.get(response.status, InstallationTokenFailureClass.REMOTE_SERVICE_FAILED)
            raise GitHubInstallationTokenError(failure_class)
        try:
            payload = _decode_object(response.body)
            token = payload.get("token")
            expires_at = _parse_utc(payload.get("expires_at"))
        except (GitHubBoundaryError, TypeError, ValueError) as exc:
            raise GitHubInstallationTokenError(
                InstallationTokenFailureClass.RESPONSE_INVALID
            ) from exc
        repositories = payload.get("repositories")
        permissions = payload.get("permissions")
        repository_ids = (
            [item.get("id") for item in repositories if isinstance(item, dict)]
            if isinstance(repositories, list)
            else []
        )
        if (
            not isinstance(token, str)
            or not token
            or repository_ids != [self._config.repository_id]
            or not isinstance(repositories, list)
            or len(repositories) != 1
            or permissions != {"contents": "write", "metadata": "read"}
            or not timedelta(0) < expires_at - current <= timedelta(hours=1)
        ):
            raise GitHubInstallationTokenError(
                InstallationTokenFailureClass.RESPONSE_SCOPE_REJECTED
            )
        return InstallationToken(SecretText(token), expires_at)


def content_url(locator: RepositoryLocator, relative_path: str) -> str:
    GitHubEndpointGuard._validate_private_path(relative_path)
    encoded = "/".join(quote(segment, safe="") for segment in relative_path.split("/"))
    return GITHUB_API_ORIGIN + f"/repos/{locator.owner}/{locator.name}/contents/{encoded}"


def _decode_object(body: bytes | None) -> dict[str, object]:
    if body is None:
        raise GitHubBoundaryError("GitHub JSON body is required")
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubBoundaryError("GitHub JSON body is invalid") from exc
    if not isinstance(value, dict):
        raise GitHubBoundaryError("GitHub JSON body must be an object")
    return cast(dict[str, object], value)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")


def _b64_json(value: object) -> bytes:
    return _b64(_canonical_json(value))


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise GitHubBoundaryError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise GitHubBoundaryError("installation token expiry is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitHubBoundaryError("installation token expiry is invalid") from exc
    return _require_utc(parsed)
