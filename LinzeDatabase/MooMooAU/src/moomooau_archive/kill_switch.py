"""Machine-enforced response plans for the ten frozen Kill Criteria."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

_GATE_ID = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,63}$")


class KillSwitchError(RuntimeError):
    pass


class KillId(StrEnum):
    KILL_001 = "KILL-001"
    KILL_002 = "KILL-002"
    KILL_003 = "KILL-003"
    KILL_004 = "KILL-004"
    KILL_005 = "KILL-005"
    KILL_006 = "KILL-006"
    KILL_007 = "KILL-007"
    KILL_008 = "KILL-008"
    KILL_009 = "KILL-009"
    KILL_010 = "KILL-010"


@dataclass(frozen=True, slots=True)
class KillImpact:
    kill_id: KillId
    production_enabled: bool
    raw_enabled: bool
    processed_enabled: bool
    m3_enabled: bool
    timeline_enabled: bool
    model_enabled: bool
    backfill_enabled: bool
    reason_code: str


class KillTransitionAction(StrEnum):
    TRIGGER = "TRIGGER"
    RECOVER = "RECOVER"


@dataclass(frozen=True, slots=True)
class KillTransition:
    sequence: int
    action: KillTransitionAction
    kill_id: KillId
    reason_code: str
    required_resume_gates: tuple[str, ...]
    observed_passing_gates: tuple[str, ...]


_IMPACTS = {
    KillId.KILL_001: (False, False, False, False, False, False, False, "ZERO_COLLATERAL_BREACH"),
    KillId.KILL_002: (False, False, False, False, False, False, False, "PUBLIC_LEAK"),
    KillId.KILL_003: (False, False, False, False, False, True, False, "RAW_RECOVERY_MISMATCH"),
    KillId.KILL_004: (False, False, False, False, False, True, False, "FORBIDDEN_GMAIL_MUTATION"),
    KillId.KILL_005: (False, False, False, False, False, True, False, "RECOVERY_KEY_FAILURE"),
    KillId.KILL_006: (True, True, True, True, True, False, True, "MODEL_DATA_BOUNDARY_BREACH"),
    KillId.KILL_007: (False, False, False, False, False, True, False, "CAPACITY_RED"),
    KillId.KILL_008: (True, True, False, False, False, True, False, "UNEXPLAINED_RECONCILE_GAP"),
    KillId.KILL_009: (True, True, False, False, False, True, False, "PARSER_SILENT_ERROR"),
    KillId.KILL_010: (True, True, False, True, False, True, False, "COST_EXCEEDS_BENEFIT"),
}

_RESUME_GATES = {
    KillId.KILL_001: frozenset({"AC-001", "AC-004", "AC-006"}),
    KillId.KILL_002: frozenset({"AC-011", "AC-012", "AC-016", "AC-022"}),
    KillId.KILL_003: frozenset({"AC-007", "AC-013", "AC-027"}),
    KillId.KILL_004: frozenset({"AC-006", "AC-018", "SECURITY_REVIEW"}),
    KillId.KILL_005: frozenset({"AC-012", "AC-032"}),
    KillId.KILL_006: frozenset({"AC-020", "AC-024", "AC-033"}),
    KillId.KILL_007: frozenset({"CAPACITY_PLAN_APPROVED", "SINGLE_REPOSITORY_PROVEN"}),
    KillId.KILL_008: frozenset({"AC-003", "AC-025"}),
    KillId.KILL_009: frozenset({"GOLDEN", "BLUE_GREEN", "ORACLE"}),
    KillId.KILL_010: frozenset({"BENEFIT_OVER_COST"}),
}


class KillSwitch:
    def __init__(self) -> None:
        self._active: KillImpact | None = None
        self._transitions: list[KillTransition] = []

    @property
    def active_impact(self) -> KillImpact | None:
        return self._active

    @property
    def transitions(self) -> tuple[KillTransition, ...]:
        return tuple(self._transitions)

    def trigger(self, kill_id: KillId) -> KillImpact:
        if self._active is not None:
            if self._active.kill_id is kill_id:
                return self._active
            raise KillSwitchError("a different Kill Criterion is already active")
        values = _IMPACTS[kill_id]
        self._active = KillImpact(kill_id, *values)
        self._append_transition(KillTransitionAction.TRIGGER, kill_id, frozenset())
        return self._active

    def required_resume_gates(self, kill_id: KillId) -> frozenset[str]:
        return _RESUME_GATES[kill_id]

    def recovery_authorized(self, kill_id: KillId, passing_gates: frozenset[str]) -> bool:
        if any(_GATE_ID.fullmatch(value) is None for value in passing_gates):
            raise KillSwitchError("resume gate identity is invalid")
        return _RESUME_GATES[kill_id] == passing_gates

    def recover(self, passing_gates: frozenset[str]) -> bool:
        if self._active is None:
            raise KillSwitchError("no Kill Criterion is active")
        kill_id = self._active.kill_id
        if not self.recovery_authorized(kill_id, passing_gates):
            return False
        self._append_transition(KillTransitionAction.RECOVER, kill_id, passing_gates)
        self._active = None
        return True

    def canonical_audit_bytes(self) -> bytes:
        payload = {
            "schema_version": "moomooau.kill-audit.v1",
            "active_kill_id": self._active.kill_id.value if self._active is not None else None,
            "transitions": [
                {
                    "sequence": item.sequence,
                    "action": item.action.value,
                    "kill_id": item.kill_id.value,
                    "reason_code": item.reason_code,
                    "required_resume_gates": list(item.required_resume_gates),
                    "observed_passing_gates": list(item.observed_passing_gates),
                }
                for item in self._transitions
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")

    def _append_transition(
        self,
        action: KillTransitionAction,
        kill_id: KillId,
        passing_gates: frozenset[str],
    ) -> None:
        self._transitions.append(
            KillTransition(
                sequence=len(self._transitions) + 1,
                action=action,
                kill_id=kill_id,
                reason_code=_IMPACTS[kill_id][-1],
                required_resume_gates=tuple(sorted(_RESUME_GATES[kill_id])),
                observed_passing_gates=tuple(sorted(passing_gates)),
            )
        )
