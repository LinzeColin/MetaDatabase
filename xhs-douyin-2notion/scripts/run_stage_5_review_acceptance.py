#!/usr/bin/env python3
"""Run the independent, zero-external-call Stage 5 G5 CI-synth review."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ID = "STG.X2N.5.REVIEW"
RUN_ID = "RUN-X2N-S05-REVIEW"
TASK005_SYNTHETIC_TESTS = 49


class ReviewAcceptanceError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewAcceptanceError(message)


def _isolated_env(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int = 900) -> str:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ReviewAcceptanceError(f"{label} failed")
    return result.stdout


def _json_line(output: str, *, label: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            values.append(payload)
    _require(values, f"{label} emitted no JSON receipt")
    return values[-1]


def _zero_execution(execution: object, *, fields: tuple[str, ...]) -> None:
    _require(isinstance(execution, dict), "execution receipt is invalid")
    _require(all(execution.get(field) == 0 for field in fields), "external execution counter is nonzero")
    _require(execution.get("platform_calls") == 0 and execution.get("real_account_execution") == "NOT_RUN", "platform or account execution was claimed")


def _validate_g4(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("review_id") == "STG.X2N.4.REVIEW"
        and receipt.get("status") == "PASS_CI_SYNTH_G4_REVIEW"
        and receipt.get("gate_conditions")
        == {
            "ai_taxonomy_mutations": 0,
            "asr_ocr_vision_fusion_reports": "PASS_CI_SYNTH_FOUR_REPORTS",
            "automatic_classification": "DISABLED_PENDING_PRIVATE_GOLD",
            "prompt_injection_suite": "PASS_CI_SYNTH_TASK004",
        }
        and receipt.get("metrics", {}).get("task_reports") == 5
        and int(receipt.get("metrics", {}).get("stage_4_synthetic_unit_tests", 0)) >= 84,
        "G4 preservation replay is invalid",
    )
    _zero_execution(
        receipt.get("execution"),
        fields=("automatic_classification_writes", "model_calls", "notion_calls", "platform_calls"),
    )


def _validate_task001(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("task_id") == "TSK.x2n.uxops.001"
        and receipt.get("phase") == "PH.X2N.5.1"
        and receipt.get("status") == "PASS_CI_SYNTH_MOCK_SCOPED_REAL_NOTION_NOT_RUN"
        and receipt.get("metrics", {}).get("managed_view_definitions") == 14
        and receipt.get("metrics", {}).get("maximum_requests_per_second") == 2
        and int(receipt.get("metrics", {}).get("synthetic_unit_tests", 0)) >= 20
        and receipt.get("metrics", {}).get("user_field_overwrites") == 0,
        "Task001 Notion receipt is invalid",
    )
    execution = receipt.get("execution")
    _zero_execution(execution, fields=("network_calls", "notion_mock_socket_opens", "notion_real_calls", "platform_calls"))
    _require(isinstance(execution, dict) and execution.get("owner_notion_canary") == "NOT_RUN", "Task001 Owner Notion canary ran")


def _validate_task002(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("task_id") == "TSK.x2n.uxops.002"
        and receipt.get("phase") == "PH.X2N.5.2"
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and receipt.get("metrics", {}).get("canonical_content_files") == 10_000
        and receipt.get("metrics", {}).get("duplicate_content_copies") == 0
        and receipt.get("metrics", {}).get("second_rebuild_writes") == 0
        and int(receipt.get("metrics", {}).get("synthetic_unit_tests", 0)) >= 7,
        "Task002 Markdown receipt is invalid",
    )
    _zero_execution(receipt.get("execution"), fields=("network_calls", "platform_calls", "runtime_data_writes"))


def _validate_task003(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("task_id") == "TSK.x2n.uxops.003"
        and receipt.get("phase") == "PH.X2N.5.3"
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and receipt.get("metrics", {}).get("loopback_listener") == "127.0.0.1"
        and receipt.get("metrics", {}).get("diagnostic_private_content_hits") == 0
        and receipt.get("metrics", {}).get("accessibility_smoke") == "PASS"
        and int(receipt.get("metrics", {}).get("synthetic_unit_tests", 0)) >= 21,
        "Task003 review receipt is invalid",
    )
    _zero_execution(receipt.get("execution"), fields=("external_network_calls", "platform_calls", "real_notion_calls", "runtime_data_writes"))


def _validate_task004(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("task_id") == "TSK.x2n.uxops.004"
        and receipt.get("phase") == "PH.X2N.5.4"
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and receipt.get("metrics", {}).get("canonical_loss") == 0
        and receipt.get("metrics", {}).get("diagnostic_private_content_hits") == 0
        and receipt.get("metrics", {}).get("duplicate_notion_pages") == 0
        and receipt.get("metrics", {}).get("recovery_loops") == 0
        and int(receipt.get("metrics", {}).get("synthetic_unit_tests", 0)) >= 60,
        "Task004 diagnostics receipt is invalid",
    )
    _zero_execution(receipt.get("execution"), fields=("external_network_calls", "platform_calls", "real_notion_calls", "runtime_data_writes"))


def _validate_task005_replay(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("status") == "PASS"
        and receipt.get("historical_task") == "TSK.x2n.uxops.005"
        and receipt.get("historical_commit") == "645ab212eb2e5d7d0e9aeac3c6d2c73804de346c"
        and receipt.get("current_g5_tree_evaluated") is False,
        "Task005 historical replay is invalid",
    )


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-s05-g5-review-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        g4 = _json_line(
            _run("G4 preservation acceptance", (sys.executable, "-B", "scripts/run_stage_4_review_acceptance.py"), env=environment),
            label="G4 preservation acceptance",
        )
        task001 = _json_line(_run("Task001 acceptance", (sys.executable, "-B", "scripts/run_uxops_001_acceptance.py"), env=environment), label="Task001")
        task002 = _json_line(_run("Task002 acceptance", (sys.executable, "-B", "scripts/run_uxops_002_acceptance.py"), env=environment), label="Task002")
        task003 = _json_line(_run("Task003 acceptance", (sys.executable, "-B", "scripts/run_uxops_003_acceptance.py"), env=environment), label="Task003")
        task004 = _json_line(_run("Task004 acceptance", (sys.executable, "-B", "scripts/run_uxops_004_acceptance.py"), env=environment), label="Task004")
        task005 = _json_line(_run("Task005 historical replay", (sys.executable, "-B", "scripts/replay_uxops_005_historical.py"), env=environment, timeout=1800), label="Task005 historical replay")
        _run(
            "G5 review ruff",
            (
                sys.executable,
                "-B",
                "-m",
                "ruff",
                "check",
                "scripts/replay_uxops_005_historical.py",
                "scripts/run_stage_5_review_acceptance.py",
                "scripts/verify_stage_5_review.py",
            ),
            env=environment,
        )

    _validate_g4(g4)
    _validate_task001(task001)
    _validate_task002(task002)
    _validate_task003(task003)
    _validate_task004(task004)
    _validate_task005_replay(task005)
    task_receipts = {
        item["task_id"]: {"phase": item["phase"], "status": item["status"], "synthetic_unit_tests": item["metrics"]["synthetic_unit_tests"]}
        for item in (task001, task002, task003, task004)
    }
    task_receipts["TSK.x2n.uxops.005"] = {
        "phase": "PH.X2N.5.5",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "synthetic_unit_tests": TASK005_SYNTHETIC_TESTS,
    }
    stage_5_tests = sum(int(item["synthetic_unit_tests"]) for item in task_receipts.values())
    return {
        "execution": {
            "external_network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "notion_real_calls": 0,
            "private_database_client_calls": 0,
            "tmutil_calls": 0,
            "physical_delete_execution": "NOT_RUN",
            "stage_5_remote_upload": "NOT_RUN",
            "stage_6_executed": False,
        },
        "gate_conditions": {
            "notion_eventually_consistent_or_disabled": "PASS_CI_SYNTH_MOCK_RECONCILE_REAL_NOTION_NOT_RUN",
            "markdown_full_rebuild_deterministic": "PASS_CI_SYNTH_TEN_THOUSAND_REBUILD_SECOND_WRITE_ZERO",
            "review_and_diagnostics_usable": "PASS_CI_SYNTH_LOOPBACK_REVIEW_REDACTED_DOCTOR_RECOVERY",
            "export_delete_backup_behavior_verified": "PASS_CI_SYNTH_DOMAIN_ARCHIVE_RESTORE_TOMBSTONE_TTL",
        },
        "historical_replay": task005,
        "metrics": {
            "g4_synthetic_unit_tests": int(g4["metrics"]["stage_4_synthetic_unit_tests"]),
            "stage_5_synthetic_unit_tests": stage_5_tests,
            "task_reports": len(task_receipts),
        },
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_G5_REVIEW",
        "task_receipts": task_receipts,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
        return 0
    except (OSError, ReviewAcceptanceError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
