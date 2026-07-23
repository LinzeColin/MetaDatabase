from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from stage6_support import public_document

from moomooau_archive.model_boundary import (
    AutoAction,
    BoundaryDecision,
    CodexAutoMonitor,
    CodexDevelopmentBoundary,
    DevelopmentInputKind,
    PublicHealthObservation,
    RequestedCapability,
)
from moomooau_archive.public_inventory import PublicRunState
from moomooau_archive.publication_saga import PrivateFirstPublicationSaga

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTO_NOW = datetime(2026, 7, 20, 4, 30, tzinfo=UTC)


def _auto_observation(state: PublicRunState) -> PublicHealthObservation:
    return PublicHealthObservation(
        public_document(state),
        "LinzeDatabase/MooMooAU/evidence/ops/latest.json",
        AUTO_NOW,
    )


def test_t0605_system_card_keeps_every_real_data_plane_component_model_free() -> None:
    card = json.loads(
        (PROJECT_ROOT / "machine/stages/S6/model/codex-system-card.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert card["schema_version"] == "moomooau.codex-system-card.v1"
    assert card["model_surfaces"] == ["DEVELOPMENT_THREAD", "PUBLIC_HEALTH_MONITOR"]
    assert set(card["allowed_development_inputs"]) == {
        "FROZEN_TASKPACK",
        "PUBLIC_CODE",
        "SYNTHETIC_FIXTURE",
        "PUBLIC_EVIDENCE",
    }
    assert set(card["denied_inputs"]) == {"REAL_EMAIL", "PRIVATE_OBJECT", "SECRET"}
    assert card["data_plane_model_calls"] == 0
    assert set(card["data_plane_components"]) == {
        "GMAIL_DISCOVERY",
        "FULL_FETCH",
        "VERIFICATION",
        "RAW",
        "PROCESSED",
        "AGE",
        "PRIVATE_COMMIT",
        "REMOTE_RECOVERY",
        "M3",
        "TIMELINE",
    }
    assert card["monitor_contract"] == {
        "input": "STRICT_PUBLIC_INVENTORY_ONLY",
        "healthy_action": "NONE",
        "abnormal_action": "UPDATE_SINGLE_OPS_ISSUE",
        "maximum_issue_updates": 1,
        "production_trigger_allowed": False,
        "data_plane_dependency": False,
    }


def test_t0605_all_capability_and_red_team_policy_evals_pass() -> None:
    catalog = json.loads(
        (PROJECT_ROOT / "machine/stages/S6/model/model-evals.v1.json").read_text(encoding="utf-8")
    )
    cases = catalog["cases"]
    assert [item["id"] for item in cases] == [
        "EV-01",
        "EV-02",
        "EV-03",
        "EV-04",
        "EV-05",
        "EV-06",
        "SR-01",
        "SR-02",
        "SR-03",
        "SR-04",
        "SR-05",
        "SR-06",
        "SR-07",
        "SR-08",
    ]
    boundary = CodexDevelopmentBoundary()
    observed = [boundary.decide(RequestedCapability(item["capability"])).value for item in cases]
    assert observed == [item["expected"] for item in cases]
    assert observed.count(BoundaryDecision.DENY.value) == 12
    assert observed.count(BoundaryDecision.ALLOW.value) == 2


def test_t0605_runtime_has_no_model_dispatch_port_and_private_inputs_are_denied() -> None:
    boundary = CodexDevelopmentBoundary()
    for kind in (
        DevelopmentInputKind.REAL_EMAIL,
        DevelopmentInputKind.PRIVATE_OBJECT,
        DevelopmentInputKind.SECRET,
    ):
        assert boundary.authorize_input(kind) is BoundaryDecision.DENY
    for kind in (
        DevelopmentInputKind.FROZEN_TASKPACK,
        DevelopmentInputKind.PUBLIC_CODE,
        DevelopmentInputKind.SYNTHETIC_FIXTURE,
        DevelopmentInputKind.PUBLIC_EVIDENCE,
    ):
        assert boundary.authorize_input(kind) is BoundaryDecision.ALLOW
    runtime = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "src/moomooau_archive").glob("*.py")
    )
    assert "ModelPort" not in runtime
    assert "def dispatch(" not in runtime
    assert "def invoke(" not in runtime


def test_t0605_auto_reads_only_strict_public_health_and_is_not_a_data_plane_dependency() -> None:
    monitor = CodexAutoMonitor()
    healthy = monitor.plan(_auto_observation(PublicRunState.HEALTHY), now_utc=AUTO_NOW)
    assert healthy.action is AutoAction.NONE
    assert healthy.issue_updates == 0
    for state in (
        PublicRunState.DEGRADED_RAW_ONLY,
        PublicRunState.WAITING_PASSWORD,
        PublicRunState.M3_FAILED,
        PublicRunState.TIMELINE_FAILED,
        PublicRunState.FAILED,
        PublicRunState.NOT_RUN,
    ):
        plan = monitor.plan(_auto_observation(state), now_utc=AUTO_NOW)
        assert plan.action is AutoAction.UPDATE_SINGLE_OPS_ISSUE
        assert plan.issue_updates == 1

    disabled = monitor.plan(
        _auto_observation(PublicRunState.FAILED),
        now_utc=AUTO_NOW,
        enabled=False,
    )
    assert disabled.action is AutoAction.DISABLED
    assert disabled.issue_updates == 0
    saga = PrivateFirstPublicationSaga()
    saga.record_private(committed=True, recovery_verified=True)
    assert saga.snapshot.m3_authorized
