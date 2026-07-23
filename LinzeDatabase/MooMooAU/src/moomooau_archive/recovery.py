"""Fail-closed recovery-key ceremony with pluggable protected delivery ports."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .secret_values import SecretBytes

RECOVERY_FILENAME = "MooMooAU-Recovery-Key.agekey"
_PUBLIC_RECIPIENT = re.compile(r"^age1[0-9a-z]{58}$")
_PUBLIC_KEY_LINE = re.compile(rb"^# public key: (age1[0-9a-z]{58})$", re.MULTILINE)


class RecoveryCeremonyError(RuntimeError):
    pass


class RecoveryState(StrEnum):
    AWAITING_OWNER = "AWAITING_OWNER"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, repr=False)
class GeneratedAgeIdentity:
    recipient: str
    identity: SecretBytes

    def __repr__(self) -> str:
        return f"GeneratedAgeIdentity(recipient={self.recipient!r}, identity=<redacted>)"

    def destroy(self) -> None:
        self.identity.destroy()


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryPreparation:
    ceremony_id: str
    recipient: str
    delivery_id: str
    state: RecoveryState = RecoveryState.AWAITING_OWNER

    def __repr__(self) -> str:
        return (
            "RecoveryPreparation(ceremony_id=<opaque>, recipient="
            f"{self.recipient!r}, delivery_id=<opaque>, state={self.state.value!r})"
        )


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    state: RecoveryState
    delivery_claims: int
    recovery_verified: bool
    m3_eligible: bool
    failure_code: str | None


class AgeIdentityGenerator:
    """Generate an age identity to stdout; no identity file is created."""

    def __init__(self, keygen_binary: str | None = None) -> None:
        resolved = keygen_binary or shutil.which("age-keygen")
        if resolved is None:
            raise RecoveryCeremonyError("official age-keygen binary is required")
        self._keygen_binary = resolved

    def generate(self) -> GeneratedAgeIdentity:
        completed = subprocess.run(
            [self._keygen_binary],
            check=False,
            capture_output=True,
        )
        if (
            completed.returncode != 0
            or not completed.stdout
            or completed.stdout.count(b"AGE-SECRET-KEY-") != 1
        ):
            raise RecoveryCeremonyError("age identity generation failed with redacted diagnostics")
        match = _PUBLIC_KEY_LINE.search(completed.stdout)
        if match is None:
            raise RecoveryCeremonyError("age identity generation returned no public recipient")
        recipient = match.group(1).decode("ascii")
        if _PUBLIC_RECIPIENT.fullmatch(recipient) is None:
            raise RecoveryCeremonyError("age public recipient is invalid")
        return GeneratedAgeIdentity(recipient, SecretBytes(completed.stdout))


class ProtectedSecretInstaller(Protocol):
    def install(self, identity: bytes) -> str: ...

    def revoke(self, installation_receipt: str) -> None: ...

    def verify_recovery(self, recipient: str) -> bool: ...


class OneTimeRecoveryHandoff(Protocol):
    def publish_once(self, filename: str, identity: bytes) -> str: ...

    def claim_count(self, delivery_id: str) -> int: ...

    def is_available(self, delivery_id: str) -> bool: ...

    def revoke(self, delivery_id: str) -> None: ...


class RecoveryCeremony:
    """Coordinate generation, protected Secret injection, one-time claim and recovery proof."""

    def __init__(
        self,
        generator: AgeIdentityGenerator,
        installer: ProtectedSecretInstaller,
        handoff: OneTimeRecoveryHandoff,
    ) -> None:
        self._generator = generator
        self._installer = installer
        self._handoff = handoff
        self._pending: RecoveryPreparation | None = None
        self._installation_receipt: str | None = None

    def start(self) -> RecoveryPreparation:
        if self._pending is not None:
            raise RecoveryCeremonyError("a recovery ceremony is already pending")
        generated = self._generator.generate()
        installation_receipt: str | None = None
        delivery_id: str | None = None
        try:
            installation_receipt = self._installer.install(generated.identity.reveal())
            if not installation_receipt:
                raise RecoveryCeremonyError("protected Secret installation returned no receipt")
            delivery_id = self._handoff.publish_once(
                RECOVERY_FILENAME,
                generated.identity.reveal(),
            )
            if not delivery_id:
                raise RecoveryCeremonyError("one-time recovery delivery returned no receipt")
        except BaseException:
            if delivery_id:
                self._handoff.revoke(delivery_id)
            if installation_receipt:
                self._installer.revoke(installation_receipt)
            raise
        finally:
            generated.destroy()
        preparation = RecoveryPreparation(
            ceremony_id=uuid.uuid4().hex,
            recipient=generated.recipient,
            delivery_id=delivery_id,
        )
        self._pending = preparation
        self._installation_receipt = installation_receipt
        return preparation

    def complete(self, preparation: RecoveryPreparation) -> RecoveryOutcome:
        if self._pending is None or preparation != self._pending:
            raise RecoveryCeremonyError("recovery ceremony receipt does not match the pending run")
        claims = self._handoff.claim_count(preparation.delivery_id)
        if claims == 0:
            return RecoveryOutcome(
                state=RecoveryState.AWAITING_OWNER,
                delivery_claims=claims,
                recovery_verified=False,
                m3_eligible=False,
                failure_code="OWNER_CONFIRMATION_NOT_READY",
            )
        if claims != 1:
            self._revoke_pending(preparation)
            return RecoveryOutcome(
                state=RecoveryState.FAILED,
                delivery_claims=claims,
                recovery_verified=False,
                m3_eligible=False,
                failure_code="ONE_TIME_DELIVERY_NOT_EXACTLY_ONCE",
            )
        if self._handoff.is_available(preparation.delivery_id):
            self._revoke_pending(preparation)
            return RecoveryOutcome(
                state=RecoveryState.FAILED,
                delivery_claims=claims,
                recovery_verified=False,
                m3_eligible=False,
                failure_code="ONE_TIME_DELIVERY_STILL_AVAILABLE",
            )
        recovered = self._installer.verify_recovery(preparation.recipient)
        if not recovered:
            self._revoke_pending(preparation)
            return RecoveryOutcome(
                state=RecoveryState.FAILED,
                delivery_claims=claims,
                recovery_verified=False,
                m3_eligible=False,
                failure_code="RECOVERY_PROBE_FAILED",
            )
        self._handoff.revoke(preparation.delivery_id)
        self._pending = None
        self._installation_receipt = None
        return RecoveryOutcome(
            state=RecoveryState.VERIFIED,
            delivery_claims=claims,
            recovery_verified=True,
            m3_eligible=True,
            failure_code=None,
        )

    def _revoke_pending(self, preparation: RecoveryPreparation) -> None:
        self._handoff.revoke(preparation.delivery_id)
        if self._installation_receipt is not None:
            self._installer.revoke(self._installation_receipt)
        self._pending = None
        self._installation_receipt = None
