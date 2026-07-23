from __future__ import annotations

import hashlib
import io
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from moomooau_archive.age_stream import OfficialAgeStream
from moomooau_archive.kill_switch import KillId, KillSwitch
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.recovery_drill import (
    OfficialRecoveryStreamDecryptor,
    RecoveryDigestSource,
    RecoveryDrillError,
    RecoveryDrillRunContract,
    RecoveryDrillRunner,
    RecoveryDrillSafetyAudit,
    RecoveryDrillSafetySnapshot,
    RecoveryIdentityOrigin,
    RecoverySampleDescriptor,
    RecoverySampleStream,
)
from moomooau_archive.release_control import GateStatus, ObservationProvenance
from moomooau_archive.stage7_ops import (
    RecoveryArtifactRole,
    RecoveryDrillGate,
    RecoveryDrillObservation,
    Stage7OpsError,
)

NOW = datetime(2026, 7, 22, 5, tzinfo=UTC)
ROLE_ORDER = tuple(RecoveryArtifactRole)
ROLE_DIGEST_SOURCE = {
    RecoveryArtifactRole.RAW: RecoveryDigestSource.RAW_MANIFEST,
    RecoveryArtifactRole.PROCESSED: RecoveryDigestSource.PROCESSED_MANIFEST,
    RecoveryArtifactRole.TIMELINE: RecoveryDigestSource.TIMELINE_PRIVATE_STATE,
}
PRIVATE_PLAINTEXTS = {
    RecoveryArtifactRole.RAW: b"synthetic-private-raw-eml",
    RecoveryArtifactRole.PROCESSED: b"synthetic-private-processed-json",
    RecoveryArtifactRole.TIMELINE: b"synthetic-private-timeline-html",
}


class _MemoryRandomSource:
    def __init__(
        self,
        ciphertexts: dict[RecoveryArtifactRole, bytes],
        *,
        mismatch_role: RecoveryArtifactRole | None = None,
    ) -> None:
        self._ciphertexts = ciphertexts
        self._mismatch_role = mismatch_role
        self.calls: list[tuple[RecoveryArtifactRole, bytes]] = []
        self.closed_streams = 0

    @contextmanager
    def open_random(
        self,
        role: RecoveryArtifactRole,
        selection_nonce: bytes,
    ) -> Iterator[RecoverySampleStream]:
        self.calls.append((role, bytes(selection_nonce)))
        plaintext = PRIVATE_PLAINTEXTS[role]
        expected_plaintext = (
            hashlib.sha256(b"synthetic-mismatched-plaintext").hexdigest()
            if role is self._mismatch_role
            else hashlib.sha256(plaintext).hexdigest()
        )
        ciphertext = self._ciphertexts[role]
        descriptor = RecoverySampleDescriptor(
            role=role,
            digest_source=ROLE_DIGEST_SOURCE[role],
            expected_ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            expected_plaintext_sha256=expected_plaintext,
            selection_nonce_sha256=hashlib.sha256(selection_nonce).hexdigest(),
            opaque_sample_id=hashlib.sha256(
                b"synthetic-opaque-sample\x00" + role.value.encode()
            ).hexdigest(),
        )
        stream = io.BytesIO(ciphertext)
        try:
            yield RecoverySampleStream(descriptor, stream)
        finally:
            stream.close()
            self.closed_streams += 1


@dataclass(slots=True)
class _RecoveryContext:
    source: _MemoryRandomSource
    decryptor: OfficialRecoveryStreamDecryptor
    identity_path: Path


class _SafetyAudit:
    def __init__(
        self,
        after: RecoveryDrillSafetySnapshot | None = None,
    ) -> None:
        self._after = after or RecoveryDrillSafetySnapshot(0, 0, 0)
        self.calls = 0

    def snapshot(self) -> RecoveryDrillSafetySnapshot:
        self.calls += 1
        return RecoveryDrillSafetySnapshot(0, 0, 0) if self.calls == 1 else self._after


class _FailingSafetyAudit:
    def __init__(self, fail_on_call: int) -> None:
        self._fail_on_call = fail_on_call
        self.calls = 0

    def snapshot(self) -> RecoveryDrillSafetySnapshot:
        self.calls += 1
        if self.calls == self._fail_on_call:
            raise RuntimeError("synthetic-private-safety-value")
        return RecoveryDrillSafetySnapshot(0, 0, 0)


@contextmanager
def _recovery_context(
    *,
    mismatch_role: RecoveryArtifactRole | None = None,
    wrong_identity: bool = False,
) -> Iterator[_RecoveryContext]:
    encryption_identity = AgeIdentityGenerator().generate()
    decryption_identity = AgeIdentityGenerator().generate() if wrong_identity else None
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-t0707-synthetic-")
    identity_path = Path(temporary.name) / "identity.agekey"
    age = OfficialAgeStream()
    try:
        identity_path.write_bytes((decryption_identity or encryption_identity).identity.reveal())
        identity_path.chmod(0o600)
        ciphertexts: dict[RecoveryArtifactRole, bytes] = {}
        for role in ROLE_ORDER:
            source = io.BytesIO(PRIVATE_PLAINTEXTS[role])
            sink = io.BytesIO()
            age.encrypt_stream(encryption_identity.recipient, source, sink)
            ciphertexts[role] = sink.getvalue()
        yield _RecoveryContext(
            source=_MemoryRandomSource(ciphertexts, mismatch_role=mismatch_role),
            decryptor=OfficialRecoveryStreamDecryptor(
                age,
                identity_path,
                allowed_tmpfs_roots=(Path(temporary.name),),
            ),
            identity_path=identity_path,
        )
    finally:
        encryption_identity.destroy()
        if decryption_identity is not None:
            decryption_identity.destroy()
        temporary.cleanup()


def _contract(
    *,
    provenance: ObservationProvenance = ObservationProvenance.LOCAL_SYNTHETIC,
    predecessor_ready: bool = True,
) -> RecoveryDrillRunContract:
    origin = (
        RecoveryIdentityOrigin.LOCAL_SYNTHETIC
        if provenance is ObservationProvenance.LOCAL_SYNTHETIC
        else RecoveryIdentityOrigin.OWNER_RECOVERY_KEY_FILE
    )
    return RecoveryDrillRunContract(
        run_id="recovery-" + "1" * 32,
        code_commit="a" * 40,
        container_digest="sha256:" + "b" * 64,
        provenance=provenance,
        identity_origin=origin,
        predecessor_ready=predecessor_ready,
        private_repository_reads_allowed=(
            provenance is ObservationProvenance.PROTECTED_GITHUB_ACTIONS
        ),
    )


def _clock() -> Iterator[datetime]:
    yield NOW
    yield NOW + timedelta(seconds=3)


def _runner(
    context: _RecoveryContext,
    kill_switch: KillSwitch,
    *,
    safety_audit: RecoveryDrillSafetyAudit | None = None,
) -> RecoveryDrillRunner:
    ticks = _clock()
    return RecoveryDrillRunner(
        context.source,
        context.decryptor,
        safety_audit or _SafetyAudit(),
        kill_switch,
        clock=lambda: next(ticks),
        nonce_source=lambda size: bytes(range(size)),
    )


def _observation(provenance: ObservationProvenance) -> RecoveryDrillObservation:
    return RecoveryDrillObservation(
        provenance=provenance,
        observed_at_utc=NOW,
        attempted_roles=ROLE_ORDER,
        recovered_roles=ROLE_ORDER,
        digest_mismatches=0,
        identity_disclosures=0,
        persistent_plaintext_objects=0,
        private_values_recorded=0,
    )


def test_t0707_contract_allows_only_one_read_only_sample_per_role() -> None:
    contract = _contract()
    assert contract.predecessor_task_id == "T0706"
    assert contract.maximum_samples_per_role == 1
    assert contract.maximum_total_samples == 3
    assert not contract.private_repository_reads_allowed
    assert not any(
        (
            contract.private_repository_writes_allowed,
            contract.gmail_access_allowed,
            contract.workflow_dispatches_allowed,
            contract.m3_mutations_allowed,
            contract.identity_output_allowed,
            contract.persistent_plaintext_allowed,
        )
    )
    with pytest.raises(RecoveryDrillError, match="frozen boundary"):
        RecoveryDrillRunContract(
            run_id="recovery-" + "1" * 32,
            code_commit="a" * 40,
            container_digest="sha256:" + "b" * 64,
            provenance=ObservationProvenance.LOCAL_SYNTHETIC,
            identity_origin=RecoveryIdentityOrigin.LOCAL_SYNTHETIC,
            predecessor_ready=True,
            private_repository_writes_allowed=True,
        )
    with pytest.raises(RecoveryDrillError, match="frozen boundary"):
        RecoveryDrillRunContract(
            run_id="recovery-" + "1" * 32,
            code_commit="a" * 40,
            container_digest="sha256:" + "b" * 64,
            provenance=ObservationProvenance.LOCAL_SYNTHETIC,
            identity_origin=RecoveryIdentityOrigin.LOCAL_SYNTHETIC,
            predecessor_ready=True,
            private_repository_reads_allowed=True,
        )


def test_t0707_local_three_role_streaming_recovery_is_digest_only_and_not_protected() -> None:
    with _recovery_context() as context:
        kill_switch = KillSwitch()
        result = _runner(context, kill_switch).run(_contract())

        assert result.gate_status is GateStatus.BLOCKED
        assert result.reason_codes == ("PROTECTED_RECOVERY_DRILL_NOT_RUN",)
        assert result.observation.attempted_roles == ROLE_ORDER
        assert result.observation.recovered_roles == ROLE_ORDER
        assert result.observation.digest_mismatches == 0
        assert result.observation.persistent_plaintext_objects == 0
        assert context.source.closed_streams == 3
        assert [role for role, _ in context.source.calls] == list(ROLE_ORDER)
        assert len({nonce for _, nonce in context.source.calls}) == 3
        assert kill_switch.active_impact is None

        public = result.to_public_dict()
        assert public["roles_recovered"] == public["required_roles"] == 3
        assert public["sample_attempt_count"] == 3
        assert public["private_repository_writes"] == public["gmail_calls"] == 0
        assert public["workflow_dispatches"] == public["m3_mutations_during_drill"] == 0
        assert public["persistent_plaintext_objects"] == 0
        assert public["final_stage7_claimed"] is False
        rendered = json.dumps(public, sort_keys=True) + repr(result)
        assert all(value.decode() not in rendered for value in PRIVATE_PLAINTEXTS.values())
        assert all(
            hashlib.sha256(value).hexdigest() not in rendered
            for value in PRIVATE_PLAINTEXTS.values()
        )


def test_t0707_protected_run_requires_owner_key_origin_and_exact_dev_shm_contract() -> None:
    with pytest.raises(RecoveryDrillError, match="frozen boundary"):
        RecoveryDrillRunContract(
            run_id="recovery-" + "1" * 32,
            code_commit="a" * 40,
            container_digest="sha256:" + "b" * 64,
            provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
            identity_origin=RecoveryIdentityOrigin.LOCAL_SYNTHETIC,
            predecessor_ready=True,
        )

    with _recovery_context() as context:
        kill_switch = KillSwitch()
        exact_root_decryptor = OfficialRecoveryStreamDecryptor(
            OfficialAgeStream(), context.identity_path
        )
        assert not exact_root_decryptor.protected_identity_contract
        with pytest.raises(RecoveryDrillError, match="/dev/shm"):
            ticks = _clock()
            RecoveryDrillRunner(
                context.source,
                exact_root_decryptor,
                _SafetyAudit(),
                kill_switch,
                clock=lambda: next(ticks),
                nonce_source=lambda size: bytes(range(size)),
            ).run(
                _contract(provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS),
            )
        assert context.source.calls == []
        assert kill_switch.active_impact is None


def test_t0707_predecessor_failure_has_zero_sample_or_kill_side_effects() -> None:
    with _recovery_context() as context:
        kill_switch = KillSwitch()
        with pytest.raises(RecoveryDrillError, match="predecessor"):
            _runner(context, kill_switch).run(_contract(predecessor_ready=False))
        assert context.source.calls == []
        assert kill_switch.active_impact is None


def test_t0707_digest_mismatch_fails_fast_and_arms_kill_005_with_m3_zero() -> None:
    with _recovery_context(mismatch_role=RecoveryArtifactRole.RAW) as context:
        kill_switch = KillSwitch()
        result = _runner(context, kill_switch).run(_contract())

        assert result.observation.attempted_roles == (RecoveryArtifactRole.RAW,)
        assert result.observation.recovered_roles == ()
        assert result.observation.digest_mismatches == 1
        assert len(context.source.calls) == 1
        assert result.kill_005_triggered
        assert result.kill_005_active
        assert result.to_public_dict()["m3_budget_override"] == 0
        assert set(result.reason_codes) >= {
            "RECOVERY_ARTIFACT_SET_INCOMPLETE",
            "RECOVERY_SUCCESS_NOT_ONE_HUNDRED_PERCENT",
            "RECOVERY_DIGEST_MISMATCH",
        }
        impact = kill_switch.active_impact
        assert impact is not None and impact.kill_id is KillId.KILL_005
        assert not impact.production_enabled and not impact.raw_enabled and not impact.m3_enabled


def test_t0707_wrong_identity_fails_closed_without_exposing_age_diagnostics() -> None:
    with _recovery_context(wrong_identity=True) as context:
        kill_switch = KillSwitch()
        result = _runner(context, kill_switch).run(_contract())

        assert result.observation.attempted_roles == (RecoveryArtifactRole.RAW,)
        assert result.observation.recovered_roles == ()
        assert result.observation.digest_mismatches == 0
        assert result.kill_005_active
        assert "RECOVERY_SUCCESS_NOT_ONE_HUNDRED_PERCENT" in result.reason_codes
        assert "AGE-SECRET-KEY" not in repr(result)


@pytest.mark.parametrize(
    ("after", "counter_name", "reason_code"),
    (
        (
            RecoveryDrillSafetySnapshot(1, 0, 0),
            "identity_disclosures",
            "RECOVERY_IDENTITY_DISCLOSED",
        ),
        (
            RecoveryDrillSafetySnapshot(0, 1, 0),
            "persistent_plaintext_objects",
            "RECOVERY_PLAINTEXT_PERSISTED",
        ),
        (
            RecoveryDrillSafetySnapshot(0, 0, 1),
            "private_values_recorded",
            "RECOVERY_EVIDENCE_CONTAINS_PRIVATE_VALUES",
        ),
    ),
)
def test_t0707_safety_audit_finding_blocks_success_and_arms_kill_005(
    after: RecoveryDrillSafetySnapshot,
    counter_name: str,
    reason_code: str,
) -> None:
    with _recovery_context() as context:
        kill_switch = KillSwitch()
        audit = _SafetyAudit(after)
        result = _runner(context, kill_switch, safety_audit=audit).run(_contract())

        assert result.observation.recovered_roles == ROLE_ORDER
        assert getattr(result.observation, counter_name) == 1
        assert reason_code in result.reason_codes
        assert result.kill_005_triggered and result.kill_005_active
        assert audit.calls == 2


@pytest.mark.parametrize(
    ("fail_on_call", "sample_calls", "kill_005_active"),
    ((1, 0, False), (2, 3, True)),
)
def test_t0707_safety_audit_failure_is_redacted_and_fails_closed(
    fail_on_call: int,
    sample_calls: int,
    kill_005_active: bool,
) -> None:
    with _recovery_context() as context:
        kill_switch = KillSwitch()
        audit = _FailingSafetyAudit(fail_on_call)
        with pytest.raises(RecoveryDrillError, match="safety") as caught:
            _runner(context, kill_switch, safety_audit=audit).run(_contract())

        assert "synthetic-private-safety-value" not in str(caught.value)
        assert caught.value.__suppress_context__
        assert audit.calls == fail_on_call
        assert len(context.source.calls) == sample_calls
        impact = kill_switch.active_impact
        assert (impact is not None and impact.kill_id is KillId.KILL_005) is kill_005_active


def test_t0707_aggregate_gate_is_policy_not_protected_attestation() -> None:
    gate = RecoveryDrillGate()
    assert gate.evaluate(None).reason_codes == ("PROTECTED_RECOVERY_DRILL_NOT_RUN",)
    assert (
        gate.evaluate(_observation(ObservationProvenance.LOCAL_SYNTHETIC)).status
        is GateStatus.BLOCKED
    )
    assert (
        gate.evaluate(_observation(ObservationProvenance.PROTECTED_GITHUB_ACTIONS)).status
        is GateStatus.READY
    )
    with pytest.raises(Stage7OpsError, match="subset"):
        RecoveryDrillObservation(
            provenance=ObservationProvenance.LOCAL_SYNTHETIC,
            observed_at_utc=NOW,
            attempted_roles=(RecoveryArtifactRole.RAW,),
            recovered_roles=(RecoveryArtifactRole.PROCESSED,),
            digest_mismatches=0,
            identity_disclosures=0,
            persistent_plaintext_objects=0,
            private_values_recorded=0,
        )
