from __future__ import annotations

import shutil
import subprocess

import pytest

from moomooau_archive.recovery import (
    RECOVERY_FILENAME,
    AgeIdentityGenerator,
    RecoveryCeremony,
    RecoveryState,
)
from moomooau_archive.secret_values import SecretBytes


class SyntheticSecretInstaller:
    def __init__(self) -> None:
        self.secret: SecretBytes | None = None
        self.revoked = False

    def install(self, identity: bytes) -> str:
        self.secret = SecretBytes(identity)
        return "synthetic-install-receipt"

    def revoke(self, installation_receipt: str) -> None:
        assert installation_receipt == "synthetic-install-receipt"
        self.revoked = True
        if self.secret is not None:
            self.secret.destroy()

    def verify_recovery(self, recipient: str) -> bool:
        assert self.secret is not None
        keygen = shutil.which("age-keygen")
        assert keygen is not None
        completed = subprocess.run(
            [keygen, "-y"],
            input=self.secret.reveal(),
            check=False,
            capture_output=True,
        )
        return completed.returncode == 0 and completed.stdout.decode().strip() == recipient

    def cleanup(self) -> None:
        if self.secret is not None:
            self.secret.destroy()


class SyntheticOneTimeHandoff:
    def __init__(self) -> None:
        self.filename: str | None = None
        self.secret: SecretBytes | None = None
        self.claims = 0

    def publish_once(self, filename: str, identity: bytes) -> str:
        assert self.secret is None
        self.filename = filename
        self.secret = SecretBytes(identity)
        return "synthetic-delivery-receipt"

    def claim_count(self, delivery_id: str) -> int:
        assert delivery_id == "synthetic-delivery-receipt"
        return self.claims

    def is_available(self, delivery_id: str) -> bool:
        assert delivery_id == "synthetic-delivery-receipt"
        return self.secret is not None and not self.secret.destroyed

    def revoke(self, delivery_id: str) -> None:
        assert delivery_id == "synthetic-delivery-receipt"
        if self.secret is not None:
            self.secret.destroy()

    def claim(self) -> bytes:
        if self.claims != 0 or self.secret is None:
            raise RuntimeError("one-time recovery delivery is no longer available")
        self.claims = 1
        delivered = self.secret.reveal()
        self.secret.destroy()
        return delivered

    def cleanup(self) -> None:
        if self.secret is not None:
            self.secret.destroy()


def test_t0206_requires_exactly_one_owner_claim_and_real_key_recovery_proof() -> None:
    installer = SyntheticSecretInstaller()
    handoff = SyntheticOneTimeHandoff()
    ceremony = RecoveryCeremony(AgeIdentityGenerator(), installer, handoff)
    try:
        preparation = ceremony.start()
        assert handoff.filename == RECOVERY_FILENAME
        assert "SECRET-KEY" not in repr(preparation)
        waiting = ceremony.complete(preparation)
        assert waiting.state is RecoveryState.AWAITING_OWNER
        assert not waiting.m3_eligible

        delivered = handoff.claim()
        assert delivered
        assert not handoff.is_available(preparation.delivery_id)
        with pytest.raises(RuntimeError, match="no longer available"):
            handoff.claim()
        outcome = ceremony.complete(preparation)
        assert outcome.state is RecoveryState.VERIFIED
        assert outcome.delivery_claims == 1
        assert outcome.recovery_verified
        assert outcome.m3_eligible
        assert outcome.failure_code is None
    finally:
        installer.cleanup()
        handoff.cleanup()


def test_t0206_revokes_ceremony_if_claimed_content_remains_available() -> None:
    installer = SyntheticSecretInstaller()
    handoff = SyntheticOneTimeHandoff()
    ceremony = RecoveryCeremony(AgeIdentityGenerator(), installer, handoff)
    try:
        preparation = ceremony.start()
        handoff.claims = 1
        outcome = ceremony.complete(preparation)
        assert outcome.state is RecoveryState.FAILED
        assert outcome.failure_code == "ONE_TIME_DELIVERY_STILL_AVAILABLE"
        assert not outcome.m3_eligible
        assert installer.revoked
        assert not handoff.is_available(preparation.delivery_id)
    finally:
        installer.cleanup()
        handoff.cleanup()
