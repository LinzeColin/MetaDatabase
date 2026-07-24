"""Deterministic bounded retry policy for safe, idempotent remote operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import sleep
from typing import TypeVar

from .http_boundary import HttpRequest, HttpResponse

_T = TypeVar("_T")
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RetryError(RuntimeError):
    """A remote operation could not safely complete in this run."""


class RetryExhausted(RetryError):
    """The bounded retry budget was exhausted."""


class RetryDeferred(RetryError):
    """The server requested a delay longer than this run may safely hold."""


class RetryOperation(StrEnum):
    READ = "READ"
    IDEMPOTENT_WRITE = "IDEMPOTENT_WRITE"
    GMAIL_TRASH = "GMAIL_TRASH"


class RetryAction(StrEnum):
    RETURN = "RETURN"
    RETRY = "RETRY"
    DEFER = "DEFER"
    EXHAUSTED = "EXHAUSTED"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    action: RetryAction
    delay_seconds: int
    reason_code: str

    def __post_init__(self) -> None:
        if self.delay_seconds < 0 or not self.reason_code:
            raise RetryError("retry decision is invalid")
        if self.action is not RetryAction.RETRY and self.delay_seconds != 0:
            raise RetryError("non-retry decisions cannot carry a delay")


@dataclass(frozen=True, slots=True)
class BoundedRetryPolicy:
    """Use 1, 2, 4... second waits; never blindly retry Gmail Trash."""

    maximum_attempts: int = 5
    base_delay_seconds: int = 1
    maximum_delay_seconds: int = 60

    def __post_init__(self) -> None:
        if (
            type(self.maximum_attempts) is not int
            or type(self.base_delay_seconds) is not int
            or type(self.maximum_delay_seconds) is not int
            or self.maximum_attempts <= 0
            or self.base_delay_seconds < 1
            or self.maximum_delay_seconds < self.base_delay_seconds
        ):
            raise ValueError("retry limits are invalid")

    def assess(
        self,
        operation: RetryOperation,
        *,
        status: int,
        attempt: int,
        retry_after: str | None = None,
    ) -> RetryDecision:
        if type(status) is not int or not 100 <= status <= 599:
            raise RetryError("HTTP status is invalid")
        if type(attempt) is not int or not 1 <= attempt <= self.maximum_attempts:
            raise RetryError("retry attempt is outside the bounded budget")
        if operation is RetryOperation.GMAIL_TRASH or status not in _RETRYABLE_STATUSES:
            return RetryDecision(RetryAction.RETURN, 0, "NO_AUTOMATIC_RETRY")
        if attempt >= self.maximum_attempts:
            return RetryDecision(RetryAction.EXHAUSTED, 0, "RETRY_BUDGET_EXHAUSTED")
        requested = _retry_after_seconds(retry_after)
        if requested is not None and requested > self.maximum_delay_seconds:
            return RetryDecision(RetryAction.DEFER, 0, "RETRY_AFTER_EXCEEDS_RUN_BUDGET")
        exponential = min(
            self.base_delay_seconds * (2 ** (attempt - 1)),
            self.maximum_delay_seconds,
        )
        delay = max(exponential, requested or 0)
        return RetryDecision(RetryAction.RETRY, delay, "BOUNDED_EXPONENTIAL_BACKOFF")


def send_with_retry(
    send: Callable[[HttpRequest], HttpResponse],
    request: HttpRequest,
    operation: RetryOperation,
    *,
    policy: BoundedRetryPolicy | None = None,
    sleeper: Callable[[int], None] | None = None,
) -> HttpResponse:
    """Execute through an injected transport; cancellation and unknown exceptions propagate."""

    selected = policy or BoundedRetryPolicy()
    wait = sleeper or sleep
    for attempt in range(1, selected.maximum_attempts + 1):
        try:
            response = send(request)
        except (ConnectionError, TimeoutError, OSError) as exc:
            if operation is RetryOperation.GMAIL_TRASH:
                raise RetryDeferred(
                    "Gmail Trash outcome is unknown; reconcile before retry"
                ) from exc
            if attempt >= selected.maximum_attempts:
                raise RetryExhausted("retryable transport failure exhausted the budget") from exc
            wait(
                min(
                    selected.base_delay_seconds * (2 ** (attempt - 1)),
                    selected.maximum_delay_seconds,
                )
            )
            continue
        retry_after = _header(response, "retry-after")
        decision = selected.assess(
            operation,
            status=response.status,
            attempt=attempt,
            retry_after=retry_after,
        )
        if decision.action is RetryAction.RETURN:
            return response
        if decision.action is RetryAction.DEFER:
            raise RetryDeferred("server retry delay exceeds the bounded run budget")
        if decision.action is RetryAction.EXHAUSTED:
            raise RetryExhausted("retryable HTTP response exhausted the budget")
        wait(decision.delay_seconds)
    raise AssertionError("bounded retry loop did not terminate")


def _header(response: HttpResponse, name: str) -> str | None:
    matches = [value for key, value in response.headers if key.casefold() == name.casefold()]
    return matches[0] if len(matches) == 1 else None


def _retry_after_seconds(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdigit():
        return None
    seconds = int(value)
    return seconds if seconds >= 0 else None
