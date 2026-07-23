from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from stage6_support import public_document

from moomooau_archive.model_boundary import (
    PASSIVE_CODEX_AUTO_CONTRACT,
    AutoAction,
    CodexAutoMonitor,
    ModelBoundaryError,
    PassiveCodexAutoContract,
    PublicHealthObservation,
)
from moomooau_archive.public_inventory import PublicRunState

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 4, 30, tzinfo=UTC)
PUBLIC_PATH = "LinzeDatabase/MooMooAU/evidence/ops/latest.json"


def _observation(
    state: PublicRunState,
    *,
    age: timedelta = timedelta(),
    path: str = PUBLIC_PATH,
) -> PublicHealthObservation:
    return PublicHealthObservation(public_document(state), path, NOW - age)


def test_t0706_auto_contract_has_only_noncritical_public_issue_authority() -> None:
    contract = PASSIVE_CODEX_AUTO_CONTRACT
    assert contract.name == "MooMooAU passive health check"
    assert contract.schedule_frequency == "DAILY"
    assert contract.schedule_target == "04:30"
    assert contract.timezone == "Australia/Sydney"
    assert contract.public_repository == "LinzeColin/MetaDatabase"
    assert contract.public_evidence_path == PUBLIC_PATH
    assert contract.maximum_evidence_age == timedelta(hours=48)
    assert contract.issue_label == "moomooau-ops"
    assert contract.maximum_issue_updates == 1
    assert not any(
        (
            contract.gmail_reads_allowed,
            contract.private_repository_reads_allowed,
            contract.secret_reads_allowed,
            contract.encrypted_data_reads_allowed,
            contract.workflow_dispatches_allowed,
            contract.code_writes_allowed,
            contract.conversation_continuations_allowed,
            contract.data_plane_dependency,
        )
    )
    with pytest.raises(ModelBoundaryError, match="exceeds"):
        PassiveCodexAutoContract(workflow_dispatches_allowed=True)


def test_t0706_auto_is_passive_public_health_only_and_data_plane_independent() -> None:
    monitor = CodexAutoMonitor()
    healthy = monitor.plan(_observation(PublicRunState.HEALTHY), now_utc=NOW)
    assert healthy.action is AutoAction.NONE
    assert healthy.issue_updates == 0

    boundary_fresh = monitor.plan(
        _observation(PublicRunState.HEALTHY, age=timedelta(hours=48)),
        now_utc=NOW,
    )
    assert boundary_fresh.action is AutoAction.NONE

    stale = monitor.plan(
        _observation(PublicRunState.HEALTHY, age=timedelta(hours=48, seconds=1)),
        now_utc=NOW,
    )
    assert stale.action is AutoAction.UPDATE_SINGLE_OPS_ISSUE
    assert stale.issue_updates == 1
    assert stale.reason_code == "PUBLIC_HEALTH_STALE_SINGLE_ISSUE_BUDGET"

    abnormal_stale = monitor.plan(
        _observation(PublicRunState.FAILED, age=timedelta(days=3)),
        now_utc=NOW,
    )
    assert abnormal_stale.reason_code == "PUBLIC_ABNORMAL_AND_STALE_SINGLE_ISSUE_BUDGET"

    abnormal = monitor.plan(_observation(PublicRunState.FAILED), now_utc=NOW)
    assert abnormal.action is AutoAction.UPDATE_SINGLE_OPS_ISSUE
    assert abnormal.issue_updates == 1
    assert abnormal.issue_label == "moomooau-ops"
    assert abnormal.public_evidence_path == PUBLIC_PATH
    assert abnormal.development_thread_prompt is not None
    assert monitor.plan(_observation(PublicRunState.FAILED), now_utc=NOW) == abnormal
    public = abnormal.to_public_dict()
    assert public["public_repository"] == "LinzeColin/MetaDatabase"
    assert public["development_thread_prompt"] == abnormal.development_thread_prompt
    assert public["issue_updates"] == 1
    assert public["workflow_dispatches"] == public["code_writes"] == 0
    assert public["gmail_reads"] == public["private_repository_reads"] == 0
    assert public["secret_reads"] == public["encrypted_data_reads"] == 0
    assert public["conversation_continuations"] == 0
    assert public["data_plane_dependency"] is False

    disabled = monitor.plan(
        _observation(PublicRunState.FAILED, age=timedelta(days=30)),
        now_utc=NOW,
        enabled=False,
    )
    assert disabled.action is AutoAction.DISABLED
    assert disabled.issue_updates == 0


def test_t0706_auto_rejects_nonlatest_path_and_invalid_freshness_metadata() -> None:
    with pytest.raises(ModelBoundaryError, match="outside"):
        _observation(
            PublicRunState.HEALTHY,
            path="LinzeDatabase/MooMooAU/evidence/ops/older.json",
        )
    with pytest.raises(ModelBoundaryError, match="outside"):
        PublicHealthObservation(
            public_document(PublicRunState.HEALTHY),
            PUBLIC_PATH,
            datetime(2026, 7, 22, 4, 30),
        )

    future = PublicHealthObservation(
        public_document(PublicRunState.HEALTHY),
        PUBLIC_PATH,
        NOW + timedelta(seconds=1),
    )
    with pytest.raises(ModelBoundaryError, match="freshness"):
        CodexAutoMonitor().plan(future, now_utc=NOW)


def test_t0706_frozen_setup_prompt_matches_the_executable_passive_contract() -> None:
    prompt = (PROJECT_ROOT / "implementation/CODEX_AUTO_SETUP.txt").read_text(encoding="utf-8")
    responsibilities = (PROJECT_ROOT / "design/CODEX_GITHUB_RESPONSIBILITIES.md").read_text(
        encoding="utf-8"
    )
    required = (
        "MooMooAU passive health check",
        "daily at 04:30 Australia/Sydney",
        "latest completed public MooMooAU health evidence",
        "must not access Gmail",
        "must not trigger GitHub Actions",
        "no older than 48 hours",
        "single GitHub issue labeled moomooau-ops",
        "must remain fully functional when this Automation is disabled or broken",
    )
    assert all(token in prompt for token in required)
    assert "`evidence/ops/latest.json`" in responsibilities
    assert PASSIVE_CODEX_AUTO_CONTRACT.public_evidence_path.endswith("evidence/ops/latest.json")
