from __future__ import annotations

import json
from pathlib import Path

from stage7_support import phase_observation

from moomooau_archive.release_control import (
    FeatureFlags,
    GateStatus,
    ReleasePhase,
    Stage7ReleaseGate,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_t0701_alpha_has_every_production_flag_off() -> None:
    flags = FeatureFlags.for_phase(ReleasePhase.ALPHA)
    assert flags.to_public_dict() == {
        "discovery_enabled": False,
        "raw_archive_enabled": False,
        "processing_enabled": False,
        "m3_enabled": False,
        "timeline_enabled": False,
        "public_evidence_enabled": False,
        "full_reconcile_enabled": False,
        "mutation_budget_per_run": 0,
        "parser_current_version": "none",
    }
    report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.BETA_RAW_ONLY,
        (phase_observation(ReleasePhase.ALPHA),),
        beta_message_budget=1,
    )
    assert report.status is GateStatus.READY


def test_t0701_stage7_contract_catalog_is_closed_and_not_final() -> None:
    contract = json.loads(
        (PROJECT_ROOT / "machine/stages/S7/contracts/stage7_acceptance_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["id"] for item in contract["acceptance_contracts"]] == [
        f"S7AC-00{index}" for index in range(1, 9)
    ]
    assert [item["task_id"] for item in contract["acceptance_contracts"]] == [
        f"T070{index}" for index in range(1, 9)
    ]
    assert contract["overall_status"] == "BLOCKED_T0702_PASS_SCOPE_STOP"
    assert contract["final_acceptances_passed"] == 0


def test_t0701_remote_alpha_receipt_is_passed_without_production_claim() -> None:
    record = json.loads((PROJECT_ROOT / "evidence/tasks/T0701.json").read_text(encoding="utf-8"))
    assert record["production_oracles"] == [
        {
            "id": "REMOTE_ALPHA_NO_SECRET_PREFLIGHT",
            "status": "PASS",
            "reason": (
                "The same-tree no-Secret Alpha job completed successfully on the exact merged "
                "main commit before the protected Beta job began."
            ),
        }
    ]
    assert record["record_status"] == "READY"
    assert all(item["status"] != "PASS" for item in record["linked_final_acceptance"])
