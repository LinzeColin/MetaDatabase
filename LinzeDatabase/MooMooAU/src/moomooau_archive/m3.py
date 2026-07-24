"""Exact-message M3 mutation with double verification, budget and Trash confirmation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from .gmail_discovery import MinimalMessage
from .gmail_guard import GmailEndpointGuard, get_message_request, trash_message_request
from .remote_recovery_gate import MessageRecoveryProof, RecoveryScope
from .sender_registry import MessageVerification, double_verification_matches

_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class M3Error(RuntimeError):
    """M3 precondition or response failed without exposing a Gmail identifier."""


class MutationPhase(StrEnum):
    ALPHA = "ALPHA"
    BETA = "BETA"
    CANARY = "CANARY"
    STABLE = "STABLE"


class M3State(StrEnum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE = "ELIGIBLE"
    TRASHED = "TRASHED"
    ALREADY_TRASHED = "ALREADY_TRASHED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class MutationBudget:
    phase: MutationPhase
    maximum_calls: int
    consumed_calls: int = 0

    def __post_init__(self) -> None:
        expected = {
            MutationPhase.ALPHA: 0,
            MutationPhase.BETA: 0,
            MutationPhase.CANARY: 1,
        }
        if (
            type(self.maximum_calls) is not int
            or self.maximum_calls < 0
            or type(self.consumed_calls) is not int
            or not 0 <= self.consumed_calls <= self.maximum_calls
            or (self.phase in expected and self.maximum_calls != expected[self.phase])
            or (self.phase is MutationPhase.STABLE and self.maximum_calls <= 0)
        ):
            raise M3Error("mutation budget is invalid for the release phase")

    @classmethod
    def for_phase(
        cls,
        phase: MutationPhase,
        *,
        stable_maximum_calls: int | None = None,
    ) -> MutationBudget:
        if phase is MutationPhase.STABLE:
            if stable_maximum_calls is None:
                raise M3Error("stable mutation budget requires an explicit bound")
            return cls(phase, stable_maximum_calls)
        limits = {
            MutationPhase.ALPHA: 0,
            MutationPhase.BETA: 0,
            MutationPhase.CANARY: 1,
        }
        return cls(phase, limits[phase])

    def consume(self) -> None:
        if self.consumed_calls >= self.maximum_calls:
            raise M3Error("mutation budget is exhausted")
        self.consumed_calls += 1


@dataclass(frozen=True, slots=True)
class LabelConfirmation:
    label_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.label_ids != tuple(sorted(self.label_ids))
            or len(self.label_ids) != len(set(self.label_ids))
            or any(_ID.fullmatch(value) is None for value in self.label_ids)
        ):
            raise M3Error("Gmail label confirmation is invalid")


class LabelConfirmationReader(Protocol):
    def confirm(self, message_id: str) -> LabelConfirmation: ...


class GmailLabelConfirmationClient:
    """Fetch only minimal message labels after a Trash mutation."""

    def __init__(self, guard: GmailEndpointGuard) -> None:
        self._guard = guard

    def confirm(self, message_id: str) -> LabelConfirmation:
        response = self._guard.send(get_message_request(message_id, message_format="minimal"))
        if response.status != 200 or len(response.body) > 1024 * 1024:
            raise M3Error("messages.get minimal confirmation failed")
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise M3Error("messages.get minimal confirmation is invalid") from exc
        if not isinstance(value, dict):
            raise M3Error("messages.get minimal confirmation is invalid")
        payload = cast(dict[str, object], value)
        labels = payload.get("labelIds")
        if (
            payload.get("id") != message_id
            or not isinstance(labels, list)
            or not all(isinstance(item, str) for item in labels)
            or any(key in payload for key in ("raw", "snippet"))
        ):
            raise M3Error("messages.get minimal confirmation identity is invalid")
        return LabelConfirmation(tuple(sorted(cast(list[str], labels))))


@dataclass(frozen=True, slots=True)
class M3Result:
    state: M3State
    mutation_calls: int
    trash_confirmed: bool
    reason_code: str

    def __post_init__(self) -> None:
        successful = self.state in {M3State.TRASHED, M3State.ALREADY_TRASHED}
        if (
            type(self.mutation_calls) is not int
            or self.mutation_calls not in {0, 1}
            or successful != self.trash_confirmed
            or not self.reason_code
            or (self.state is M3State.ALREADY_TRASHED and self.mutation_calls != 0)
            or (self.state is M3State.TRASHED and self.mutation_calls != 1)
        ):
            raise M3Error("M3 result is internally inconsistent")


class ExactMessageTrashExecutor:
    """Perform at most one exact ``users.messages.trash`` call in this attempt."""

    def __init__(
        self,
        guard: GmailEndpointGuard,
        confirmation_reader: LabelConfirmationReader,
    ) -> None:
        self._guard = guard
        self._confirmation_reader = confirmation_reader

    def execute(
        self,
        message: MinimalMessage,
        first_verification: MessageVerification,
        second_verification: MessageVerification,
        recovery_proof: MessageRecoveryProof,
        budget: MutationBudget,
    ) -> M3Result:
        self._validate_binding(
            message,
            first_verification,
            second_verification,
            recovery_proof,
        )
        if "TRASH" in message.label_ids:
            return M3Result(M3State.ALREADY_TRASHED, 0, True, "PRECHECK_ALREADY_TRASHED")

        budget.consume()
        try:
            response = self._guard.send(trash_message_request(message.ref.message_id))
        except Exception:
            return M3Result(M3State.UNKNOWN, 1, False, "TRASH_CALL_OUTCOME_UNKNOWN")
        if response.status != 200:
            return M3Result(M3State.UNKNOWN, 1, False, "TRASH_RESPONSE_NOT_SUCCESS")
        try:
            confirmation = self._confirmation_reader.confirm(message.ref.message_id)
        except Exception:
            return M3Result(M3State.UNKNOWN, 1, False, "TRASH_CONFIRMATION_UNAVAILABLE")
        if "TRASH" not in confirmation.label_ids:
            return M3Result(M3State.FAILED, 1, False, "TRASH_LABEL_NOT_CONFIRMED")
        return M3Result(M3State.TRASHED, 1, True, "EXACT_MESSAGE_TRASH_CONFIRMED")

    def reconcile_already_trashed(
        self,
        message: MinimalMessage,
        first_verification: MessageVerification,
        second_verification: MessageVerification,
        recovery_proof: MessageRecoveryProof,
    ) -> M3Result:
        """Confirm a prior unknown outcome without issuing any Gmail mutation request."""

        self._validate_binding(
            message,
            first_verification,
            second_verification,
            recovery_proof,
        )
        if "TRASH" not in message.label_ids:
            raise M3Error("zero-mutation reconciliation requires the source in Trash")
        return M3Result(
            M3State.ALREADY_TRASHED,
            0,
            True,
            "PRIOR_UNKNOWN_MUTATION_RECONCILED",
        )

    @staticmethod
    def _validate_binding(
        message: MinimalMessage,
        first_verification: MessageVerification,
        second_verification: MessageVerification,
        recovery_proof: MessageRecoveryProof,
    ) -> None:
        if (
            not double_verification_matches(first_verification, second_verification)
            or message.ref.message_id != second_verification.message_id
            or message.internal_date_ms != second_verification.internal_date_ms
            or recovery_proof.message_id != second_verification.message_id
            or recovery_proof.internal_date_ms != second_verification.internal_date_ms
            or recovery_proof.verification_digest != second_verification.verification_digest
            or recovery_proof.recovery_scope is not RecoveryScope.RAW_AND_PROCESSED
        ):
            raise M3Error("M3 proof and double verification are not bound")
        if "SENT" in message.label_ids or "DRAFT" in message.label_ids:
            raise M3Error("outbound message cannot enter M3")
