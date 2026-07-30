#!/usr/bin/env python3
"""Run the independent, zero-external-call Stage 4 G4 CI-synth review."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ID = "STG.X2N.4.REVIEW"
RUN_ID = "RUN-X2N-S04-REVIEW"
RUNNERS = (
    ("TSK.x2n.multimodal.001", "PH.X2N.4.1", "PASS_CI_SYNTH_SCOPED", "run_multimodal_001_acceptance.py"),
    (
        "TSK.x2n.multimodal.002",
        "PH.X2N.4.2",
        "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
        "run_multimodal_002_acceptance.py",
    ),
    (
        "TSK.x2n.multimodal.003",
        "PH.X2N.4.3",
        "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
        "run_multimodal_003_acceptance.py",
    ),
    (
        "TSK.x2n.multimodal.004",
        "PH.X2N.4.4",
        "PASS_CI_SYNTH_SCOPED_FUSION_MODEL_NOT_RUN",
        "run_multimodal_004_acceptance.py",
    ),
    (
        "TSK.x2n.multimodal.005",
        "PH.X2N.4.5",
        "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
        "run_multimodal_005_acceptance.py",
    ),
)


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
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run(label: str, command: Sequence[str], *, env: dict[str, str]) -> str:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=360,
    )
    if result.returncode != 0:
        raise ReviewAcceptanceError(f"{label} failed")
    return result.stdout


def _receipt(output: str, *, task_id: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            values.append(payload)
    _require(values, f"{task_id} emitted no receipt")
    return values[-1]


def _zero_execution(receipt: dict[str, Any], *fields: str) -> None:
    execution = receipt.get("execution", {})
    _require(isinstance(execution, dict), "execution receipt is invalid")
    _require(all(execution.get(field) == 0 for field in fields), "external execution counter is nonzero")
    _require(
        execution.get("platform_calls") == 0
        and execution.get("notion_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN",
        "platform, Notion, or account execution was claimed",
    )


def _validate_task001(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("metrics", {}).get("synthetic_unit_tests", 0) >= 32
        and receipt.get("metrics", {}).get("active_lease_misdeletes") == 0
        and receipt.get("policy", {}).get("raw_media_persistence") == 0
        and receipt.get("policy", {}).get("raw_media_url_persistence") == 0,
        "Task001 bounded-media report is invalid",
    )
    _zero_execution(receipt, "model_calls")


def _validate_task002(receipt: dict[str, Any]) -> None:
    _require(
        receipt.get("metrics", {}).get("synthetic_unit_tests", 0) >= 9
        and receipt.get("metrics", {}).get("same_input_duplicate_provider_calls") == 0
        and receipt.get("policy", {}).get("cloud_provider") == "DISABLED"
        and receipt.get("execution", {}).get("private_gold_evaluation") == "NOT_RUN",
        "Task002 ASR report is invalid",
    )
    _zero_execution(receipt, "cloud_uploads", "model_calls")


def _validate_task003(receipt: dict[str, Any]) -> None:
    execution = receipt.get("execution", {})
    _require(
        receipt.get("metrics", {}).get("synthetic_unit_tests", 0) >= 9
        and receipt.get("metrics", {}).get("same_input_duplicate_provider_calls") == 0
        and receipt.get("metrics", {}).get("url_uploads") == 0
        and receipt.get("policy", {}).get("cloud_provider") == "DISABLED"
        and execution.get("private_gold_ocr_evaluation") == "NOT_RUN"
        and execution.get("private_gold_vision_evaluation") == "NOT_RUN",
        "Task003 OCR/Vision report is invalid",
    )
    _zero_execution(receipt, "cloud_uploads", "model_calls")


def _validate_task004(receipt: dict[str, Any]) -> None:
    execution = receipt.get("execution", {})
    _require(
        receipt.get("metrics", {}).get("synthetic_unit_tests", 0) >= 12
        and receipt.get("metrics", {}).get("same_input_duplicate_model_calls") == 0
        and receipt.get("policy", {}).get("top_level_category_mutations") == 0
        and receipt.get("policy", {}).get("raw_media_url_persisted") is False,
        "Task004 fusion or prompt-injection report is invalid",
    )
    _zero_execution(
        receipt,
        "cloud_uploads",
        "config_writes",
        "file_reads",
        "model_calls",
        "network_calls",
        "secret_reads",
        "tool_calls",
    )
    _require(execution.get("owner_profile_login") == "NOT_RUN", "Task004 accessed an Owner profile")


def _validate_task005(receipt: dict[str, Any]) -> None:
    execution = receipt.get("execution", {})
    _require(
        receipt.get("metrics", {}).get("synthetic_unit_tests", 0) >= 22
        and receipt.get("metrics", {}).get("automatic_classification_writes") == 0
        and receipt.get("policy", {}).get("auto_classify") == "DISABLED_PENDING_PRIVATE_GOLD"
        and receipt.get("policy", {}).get("taxonomy_actor") == "OWNER_ONLY"
        and receipt.get("policy", {}).get("top_level_category_ai_mutations") == 0
        and execution.get("owner_private_gold_evaluation") == "NOT_RUN",
        "Task005 taxonomy and automatic-classification report is invalid",
    )
    _zero_execution(receipt, "ai_top_level_category_mutations", "cloud_uploads", "model_calls", "network_calls")


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-s04-g4-review-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        environment = _isolated_env(home)
        receipts: dict[str, dict[str, Any]] = {}
        for task_id, phase, status, script in RUNNERS:
            receipt = _receipt(
                _run(task_id, (sys.executable, "-B", str(PROJECT_ROOT / "scripts" / script)), env=environment),
                task_id=task_id,
            )
            _require(
                receipt.get("task_id") == task_id and receipt.get("phase") == phase and receipt.get("status") == status,
                f"{task_id} identity or status drifted",
            )
            receipts[task_id] = receipt

    _validate_task001(receipts["TSK.x2n.multimodal.001"])
    _validate_task002(receipts["TSK.x2n.multimodal.002"])
    _validate_task003(receipts["TSK.x2n.multimodal.003"])
    _validate_task004(receipts["TSK.x2n.multimodal.004"])
    _validate_task005(receipts["TSK.x2n.multimodal.005"])
    total_tests = sum(int(receipt["metrics"]["synthetic_unit_tests"]) for receipt in receipts.values())
    return {
        "execution": {
            "automatic_classification_writes": 0,
            "model_calls": 0,
            "notion_calls": 0,
            "platform_calls": 0,
            "private_gold_evaluation": "NOT_RUN",
            "real_account_execution": "NOT_RUN",
            "stage_4_remote_upload": "NOT_RUN",
        },
        "gate_conditions": {
            "ai_taxonomy_mutations": 0,
            "asr_ocr_vision_fusion_reports": "PASS_CI_SYNTH_FOUR_REPORTS",
            "automatic_classification": "DISABLED_PENDING_PRIVATE_GOLD",
            "prompt_injection_suite": "PASS_CI_SYNTH_TASK004",
        },
        "metrics": {
            "prompt_injection_synthetic_tests": int(
                receipts["TSK.x2n.multimodal.004"]["metrics"]["synthetic_unit_tests"]
            ),
            "stage_4_synthetic_unit_tests": total_tests,
            "task_reports": len(receipts),
        },
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_G4_REVIEW",
        "task_receipts": {
            task_id: {
                "phase": receipt["phase"],
                "status": receipt["status"],
                "synthetic_unit_tests": receipt["metrics"]["synthetic_unit_tests"],
            }
            for task_id, receipt in receipts.items()
        },
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
        return 0
    except (OSError, ReviewAcceptanceError, subprocess.SubprocessError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
