"""Fail-closed Stage 7 release phases and protected-observation gates.

This module deliberately does not perform network operations or grant credentials.  It turns
phase observations into a deterministic decision which a separately protected GitHub
Environment may consume.  ``provenance`` is an evidence field, not cryptographic attestation;
the report never grants credentials, and the protected workflow must independently establish
where an observation came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class ReleaseControlError(RuntimeError):
    """A release configuration or observation is structurally unsafe."""


class ReleasePhase(StrEnum):
    ALPHA = "ALPHA"
    BETA_RAW_ONLY = "BETA_RAW_ONLY"
    M3_CANARY = "M3_CANARY"
    BLUE_GREEN = "BLUE_GREEN"
    GA = "GA"


class ObservationProvenance(StrEnum):
    LOCAL_SYNTHETIC = "LOCAL_SYNTHETIC"
    PROTECTED_GITHUB_ACTIONS = "PROTECTED_GITHUB_ACTIONS"


class GateStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class FeatureFlags:
    """The complete production flag set for one phase.

    ``mutation_budget_per_run`` is always explicit.  In particular, GA has no guessed default:
    the deployment owner must provision a positive bounded value after capacity evidence exists.
    """

    discovery_enabled: bool
    raw_archive_enabled: bool
    processing_enabled: bool
    m3_enabled: bool
    timeline_enabled: bool
    public_evidence_enabled: bool
    full_reconcile_enabled: bool
    mutation_budget_per_run: int
    parser_current_version: str | None

    def __post_init__(self) -> None:
        boolean_values = (
            self.discovery_enabled,
            self.raw_archive_enabled,
            self.processing_enabled,
            self.m3_enabled,
            self.timeline_enabled,
            self.public_evidence_enabled,
            self.full_reconcile_enabled,
        )
        if any(type(value) is not bool for value in boolean_values):
            raise ReleaseControlError("feature flags must be booleans")
        if type(self.mutation_budget_per_run) is not int or self.mutation_budget_per_run < 0:
            raise ReleaseControlError("mutation budget must be a non-negative integer")
        if self.m3_enabled != (self.mutation_budget_per_run > 0):
            raise ReleaseControlError("M3 and its positive mutation budget must change together")
        if self.processing_enabled != (self.parser_current_version is not None):
            raise ReleaseControlError("processing and its parser version must change together")
        if self.timeline_enabled and not self.processing_enabled:
            raise ReleaseControlError("Timeline requires Processed data")
        if self.m3_enabled and not self.raw_archive_enabled:
            raise ReleaseControlError("M3 requires Raw archive recovery")

    @classmethod
    def for_phase(
        cls,
        phase: ReleasePhase,
        *,
        parser_current_version: str | None = None,
        ga_mutation_budget_per_run: int | None = None,
    ) -> FeatureFlags:
        if phase is ReleasePhase.ALPHA:
            return cls(False, False, False, False, False, False, False, 0, None)
        if phase is ReleasePhase.BETA_RAW_ONLY:
            return cls(True, True, False, False, False, True, True, 0, None)
        if phase is ReleasePhase.M3_CANARY:
            if not _valid_parser_version(parser_current_version):
                raise ReleaseControlError("M3 Canary requires an explicit current parser version")
            return cls(
                True,
                True,
                True,
                True,
                False,
                True,
                True,
                1,
                parser_current_version,
            )
        if phase is ReleasePhase.BLUE_GREEN:
            if not _valid_parser_version(parser_current_version):
                raise ReleaseControlError("Blue-Green requires an explicit current parser version")
            return cls(
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                1,
                parser_current_version,
            )
        if phase is ReleasePhase.GA:
            if (
                not _valid_parser_version(parser_current_version)
                or type(ga_mutation_budget_per_run) is not int
                or ga_mutation_budget_per_run <= 0
            ):
                raise ReleaseControlError(
                    "GA requires an explicit parser and positive bounded mutation budget"
                )
            return cls(
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                ga_mutation_budget_per_run,
                parser_current_version,
            )
        raise ReleaseControlError("unknown release phase")

    def to_public_dict(self) -> dict[str, bool | int | str]:
        return {
            "discovery_enabled": self.discovery_enabled,
            "raw_archive_enabled": self.raw_archive_enabled,
            "processing_enabled": self.processing_enabled,
            "m3_enabled": self.m3_enabled,
            "timeline_enabled": self.timeline_enabled,
            "public_evidence_enabled": self.public_evidence_enabled,
            "full_reconcile_enabled": self.full_reconcile_enabled,
            "mutation_budget_per_run": self.mutation_budget_per_run,
            "parser_current_version": self.parser_current_version or "none",
        }


@dataclass(frozen=True, slots=True, repr=False)
class PhaseObservation:
    """Aggregate-only observation; no message, repository or account identifiers are accepted."""

    phase: ReleasePhase
    provenance: ObservationProvenance
    started_at_utc: datetime
    ended_at_utc: datetime
    observed_runs: int
    scheduled_0430_runs: int
    verified_messages: int
    source_mutations: int
    mutation_budget_max: int
    recovery_attempts: int
    recovery_successes: int
    processed_messages: int
    parser_blue_green_comparisons: int
    timeline_publish_attempts: int
    full_reconcile_runs: int
    collateral_mutations: int
    public_sensitive_findings: int
    logical_duplicates: int
    full_reconcile_difference: int
    minimum_live_timeline_assets: int
    maximum_live_timeline_assets: int
    unresolved_failures: int

    def __post_init__(self) -> None:
        if not isinstance(self.phase, ReleasePhase) or not isinstance(
            self.provenance, ObservationProvenance
        ):
            raise ReleaseControlError("observation phase or provenance is invalid")
        if not _is_utc(self.started_at_utc) or not _is_utc(self.ended_at_utc):
            raise ReleaseControlError("observation timestamps must be timezone-aware UTC")
        if self.ended_at_utc < self.started_at_utc:
            raise ReleaseControlError("observation window cannot run backwards")
        counters = (
            self.observed_runs,
            self.scheduled_0430_runs,
            self.verified_messages,
            self.source_mutations,
            self.mutation_budget_max,
            self.recovery_attempts,
            self.recovery_successes,
            self.processed_messages,
            self.parser_blue_green_comparisons,
            self.timeline_publish_attempts,
            self.full_reconcile_runs,
            self.collateral_mutations,
            self.public_sensitive_findings,
            self.logical_duplicates,
            self.full_reconcile_difference,
            self.minimum_live_timeline_assets,
            self.maximum_live_timeline_assets,
            self.unresolved_failures,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise ReleaseControlError("observation counters must be non-negative integers")
        if self.scheduled_0430_runs > self.observed_runs:
            raise ReleaseControlError("scheduled run count exceeds observed runs")
        if self.recovery_successes > self.recovery_attempts:
            raise ReleaseControlError("recovery successes exceed attempts")
        if self.processed_messages > self.verified_messages:
            raise ReleaseControlError("Processed messages exceed verified messages")
        if self.parser_blue_green_comparisons > self.processed_messages:
            raise ReleaseControlError("Parser comparisons exceed Processed messages")
        if self.timeline_publish_attempts > self.observed_runs:
            raise ReleaseControlError("Timeline attempts exceed observed runs")
        if self.full_reconcile_runs > self.observed_runs:
            raise ReleaseControlError("Full Reconcile count exceeds observed runs")
        if self.source_mutations > self.verified_messages:
            raise ReleaseControlError("source mutations exceed verified messages")
        if self.source_mutations > self.observed_runs * self.mutation_budget_max:
            raise ReleaseControlError("source mutations exceed the per-run budget")
        if self.minimum_live_timeline_assets > self.maximum_live_timeline_assets:
            raise ReleaseControlError("Timeline asset bounds are inverted")

    def __repr__(self) -> str:
        return (
            f"PhaseObservation(phase={self.phase.value!r}, "
            f"provenance={self.provenance.value!r}, window_days={self.window_days}, "
            f"runs={self.observed_runs}, private_values=<redacted>)"
        )

    @property
    def window_days(self) -> int:
        return (self.ended_at_utc - self.started_at_utc).days


@dataclass(frozen=True, slots=True)
class ReleaseGateReport:
    target_phase: ReleasePhase
    status: GateStatus
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status is GateStatus.READY

    def to_public_dict(self) -> dict[str, object]:
        return {
            "target_phase": self.target_phase.value,
            "status": self.status.value,
            "reason_codes": list(self.reasons),
        }


class Stage7ReleaseGate:
    """Evaluate the frozen Alpha -> Beta -> M3 -> Blue-Green -> GA chain."""

    _PREDECESSORS = {
        ReleasePhase.ALPHA: (),
        ReleasePhase.BETA_RAW_ONLY: (ReleasePhase.ALPHA,),
        ReleasePhase.M3_CANARY: (ReleasePhase.ALPHA, ReleasePhase.BETA_RAW_ONLY),
        ReleasePhase.BLUE_GREEN: (
            ReleasePhase.ALPHA,
            ReleasePhase.BETA_RAW_ONLY,
            ReleasePhase.M3_CANARY,
        ),
        ReleasePhase.GA: (
            ReleasePhase.ALPHA,
            ReleasePhase.BETA_RAW_ONLY,
            ReleasePhase.M3_CANARY,
            ReleasePhase.BLUE_GREEN,
        ),
    }

    def evaluate_promotion(
        self,
        target_phase: ReleasePhase,
        observations: tuple[PhaseObservation, ...],
        *,
        beta_message_budget: int | None = None,
        parser_current_version: str | None = None,
        ga_mutation_budget_per_run: int | None = None,
        ga_capacity_authorized: bool | None = None,
    ) -> ReleaseGateReport:
        if not isinstance(target_phase, ReleasePhase):
            raise ReleaseControlError("target release phase is invalid")
        reasons: list[str] = []
        by_phase: dict[ReleasePhase, PhaseObservation] = {}
        for observation in observations:
            if observation.phase in by_phase:
                reasons.append("DUPLICATE_PHASE_OBSERVATION")
            by_phase[observation.phase] = observation

        if target_phase is not ReleasePhase.ALPHA:
            for phase in self._PREDECESSORS[target_phase]:
                predecessor_observation = by_phase.get(phase)
                if predecessor_observation is None:
                    reasons.append(f"{phase.value}_OBSERVATION_MISSING")
                    continue
                reasons.extend(
                    self._phase_reasons(
                        predecessor_observation,
                        beta_message_budget=beta_message_budget,
                        ga_mutation_budget_per_run=ga_mutation_budget_per_run,
                    )
                )

        try:
            FeatureFlags.for_phase(
                target_phase,
                parser_current_version=parser_current_version,
                ga_mutation_budget_per_run=ga_mutation_budget_per_run,
            )
        except ReleaseControlError:
            reasons.append("TARGET_FEATURE_CONFIGURATION_INCOMPLETE")
        if target_phase is ReleasePhase.GA and ga_capacity_authorized is not True:
            reasons.append("GA_CAPACITY_AUTHORIZATION_MISSING")
        deduplicated = tuple(dict.fromkeys(reasons))
        return ReleaseGateReport(
            target_phase=target_phase,
            status=GateStatus.READY if not deduplicated else GateStatus.BLOCKED,
            reasons=deduplicated,
        )

    def evaluate_stage_completion(
        self,
        observations: tuple[PhaseObservation, ...],
        *,
        beta_message_budget: int | None,
        parser_current_version: str | None,
        ga_mutation_budget_per_run: int | None,
        ga_capacity_authorized: bool | None,
    ) -> ReleaseGateReport:
        promotion = self.evaluate_promotion(
            ReleasePhase.GA,
            observations,
            beta_message_budget=beta_message_budget,
            parser_current_version=parser_current_version,
            ga_mutation_budget_per_run=ga_mutation_budget_per_run,
            ga_capacity_authorized=ga_capacity_authorized,
        )
        reasons = list(promotion.reasons)
        ga_observation = next(
            (item for item in observations if item.phase is ReleasePhase.GA),
            None,
        )
        if ga_observation is None:
            reasons.append("GA_PROTECTED_OBSERVATION_MISSING")
        else:
            reasons.extend(
                self._phase_reasons(
                    ga_observation,
                    beta_message_budget=beta_message_budget,
                    ga_mutation_budget_per_run=ga_mutation_budget_per_run,
                )
            )
        deduplicated = tuple(dict.fromkeys(reasons))
        return ReleaseGateReport(
            target_phase=ReleasePhase.GA,
            status=GateStatus.READY if not deduplicated else GateStatus.BLOCKED,
            reasons=deduplicated,
        )

    @staticmethod
    def _phase_reasons(
        observation: PhaseObservation,
        *,
        beta_message_budget: int | None,
        ga_mutation_budget_per_run: int | None = None,
    ) -> list[str]:
        reasons: list[str] = []
        common_zero = (
            observation.collateral_mutations,
            observation.public_sensitive_findings,
            observation.logical_duplicates,
            observation.full_reconcile_difference,
            observation.unresolved_failures,
        )
        if any(common_zero):
            reasons.append(f"{observation.phase.value}_ZERO_ERROR_ORACLE_FAILED")
        if observation.observed_runs < 1:
            reasons.append(f"{observation.phase.value}_NO_OBSERVED_RUN")

        if observation.phase is ReleasePhase.ALPHA:
            if observation.provenance is not ObservationProvenance.LOCAL_SYNTHETIC:
                reasons.append("ALPHA_NOT_SYNTHETIC")
            if any(
                (
                    observation.verified_messages,
                    observation.source_mutations,
                    observation.recovery_attempts,
                    observation.recovery_successes,
                    observation.processed_messages,
                    observation.parser_blue_green_comparisons,
                    observation.timeline_publish_attempts,
                    observation.full_reconcile_runs,
                    observation.minimum_live_timeline_assets,
                    observation.maximum_live_timeline_assets,
                )
            ):
                reasons.append("ALPHA_PRODUCTION_EFFECT_OBSERVED")
            return reasons

        if observation.provenance is not ObservationProvenance.PROTECTED_GITHUB_ACTIONS:
            reasons.append(f"{observation.phase.value}_PROTECTED_ORACLE_NOT_RUN")

        if observation.phase is ReleasePhase.BETA_RAW_ONLY:
            if type(beta_message_budget) is not int or beta_message_budget <= 0:
                reasons.append("BETA_MESSAGE_BUDGET_UNKNOWN")
            elif not 1 <= observation.verified_messages <= beta_message_budget:
                reasons.append("BETA_VERIFIED_MESSAGE_BUDGET_NOT_SATISFIED")
            if any(
                (
                    observation.source_mutations,
                    observation.mutation_budget_max,
                    observation.processed_messages,
                    observation.parser_blue_green_comparisons,
                    observation.timeline_publish_attempts,
                    observation.minimum_live_timeline_assets,
                    observation.maximum_live_timeline_assets,
                )
            ):
                reasons.append("BETA_RAW_ONLY_BOUNDARY_VIOLATED")
            if (
                observation.recovery_attempts != observation.verified_messages
                or observation.recovery_successes != observation.recovery_attempts
            ):
                reasons.append("BETA_RAW_RECOVERY_NOT_ONE_HUNDRED_PERCENT")
            return reasons

        if observation.phase is ReleasePhase.M3_CANARY:
            if observation.ended_at_utc - observation.started_at_utc < timedelta(days=7):
                reasons.append("M3_SEVEN_DAY_WINDOW_INCOMPLETE")
            if observation.scheduled_0430_runs < 7:
                reasons.append("M3_DAILY_RUN_EVIDENCE_INCOMPLETE")
            if observation.mutation_budget_max != 1:
                reasons.append("M3_MUTATION_BUDGET_NOT_ONE")
            if observation.source_mutations < 1:
                reasons.append("M3_NO_CONFIRMED_SOURCE_MUTATION")
            if observation.processed_messages < 1:
                reasons.append("M3_NO_PROCESSED_OR_SAFE_DEFERRED_MESSAGE")
            if (
                observation.recovery_attempts
                < max(observation.source_mutations, observation.processed_messages)
                or observation.recovery_successes != observation.recovery_attempts
            ):
                reasons.append("M3_RECOVERY_NOT_ONE_HUNDRED_PERCENT")
            if any(
                (
                    observation.parser_blue_green_comparisons,
                    observation.timeline_publish_attempts,
                    observation.minimum_live_timeline_assets,
                    observation.maximum_live_timeline_assets,
                )
            ):
                reasons.append("M3_TIMELINE_OR_BLUE_GREEN_BOUNDARY_VIOLATED")
            return reasons

        if observation.phase is ReleasePhase.BLUE_GREEN:
            if observation.ended_at_utc - observation.started_at_utc < timedelta(days=14):
                reasons.append("BLUE_GREEN_FOURTEEN_DAY_WINDOW_INCOMPLETE")
            if observation.scheduled_0430_runs < 14:
                reasons.append("BLUE_GREEN_DAILY_RUN_EVIDENCE_INCOMPLETE")
            if observation.mutation_budget_max != 1:
                reasons.append("BLUE_GREEN_MUTATION_BUDGET_NOT_ONE")
            if observation.processed_messages < 1:
                reasons.append("BLUE_GREEN_NO_PROCESSED_MESSAGE_OBSERVED")
            if observation.parser_blue_green_comparisons < 1:
                reasons.append("BLUE_GREEN_NO_PARSER_COMPARISON_OBSERVED")
            if observation.timeline_publish_attempts < 1:
                reasons.append("BLUE_GREEN_NO_TIMELINE_PUBLISH_OBSERVED")
            if observation.full_reconcile_runs < 1:
                reasons.append("BLUE_GREEN_FULL_RECONCILIATION_NOT_OBSERVED")
            if (
                observation.recovery_attempts
                < max(observation.source_mutations, observation.processed_messages)
                or observation.recovery_successes != observation.recovery_attempts
            ):
                reasons.append("BLUE_GREEN_RECOVERY_NOT_ONE_HUNDRED_PERCENT")
            if (
                observation.minimum_live_timeline_assets != 1
                or observation.maximum_live_timeline_assets != 1
            ):
                reasons.append("BLUE_GREEN_EXACTLY_ONE_LIVE_TIMELINE_FAILED")
            return reasons

        # ReleasePhase is closed; only GA remains after the four branches above.
        if observation.scheduled_0430_runs < 1:
            reasons.append("GA_0430_SCHEDULE_NOT_OBSERVED")
        if observation.verified_messages < 1:
            reasons.append("GA_NO_VERIFIED_MESSAGE_OBSERVED")
        if observation.processed_messages < 1:
            reasons.append("GA_NO_PROCESSED_MESSAGE_OBSERVED")
        if observation.timeline_publish_attempts < 1:
            reasons.append("GA_NO_TIMELINE_PUBLISH_OBSERVED")
        if observation.full_reconcile_runs < 1:
            reasons.append("GA_FULL_RECONCILIATION_NOT_OBSERVED")
        if (
            type(ga_mutation_budget_per_run) is not int
            or ga_mutation_budget_per_run <= 0
            or observation.mutation_budget_max != ga_mutation_budget_per_run
        ):
            reasons.append("GA_MUTATION_BUDGET_OBSERVATION_MISMATCH")
        if (
            observation.recovery_attempts
            < max(observation.source_mutations, observation.processed_messages)
            or observation.recovery_successes != observation.recovery_attempts
        ):
            reasons.append("GA_RECOVERY_NOT_ONE_HUNDRED_PERCENT")
        if (
            observation.minimum_live_timeline_assets != 1
            or observation.maximum_live_timeline_assets != 1
        ):
            reasons.append("GA_EXACTLY_ONE_LIVE_TIMELINE_FAILED")
        return reasons


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _valid_parser_version(value: str | None) -> bool:
    return value is not None and re.fullmatch(r"[1-9][0-9]*\.[0-9]+\.[0-9]+", value) is not None
