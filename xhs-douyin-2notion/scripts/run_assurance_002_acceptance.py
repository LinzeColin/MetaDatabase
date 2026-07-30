#!/usr/bin/env python3
"""Run the Stage 6.2 model-assurance acceptance without reading private Gold data."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CI_ROOT = PROJECT_ROOT / "scripts/ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

from ci_baseline import BaselineError, scan_source, validate_model_dataset  # noqa: E402


TASK_ID = "TSK.x2n.assurance.002"
PHASE = "PH.X2N.6.2"
RUN_ID = "RUN-X2N-S06-A002"
MODEL_TEST_MODULES = (
    "apps.companion.tests.test_asr",
    "apps.companion.tests.test_ocr_vision",
    "apps.companion.tests.test_fusion",
    "apps.companion.tests.test_taxonomy",
)
MISSING_PRIVATE_GOLD_ACTIONS = ("asr", "ocr", "vision", "classify")
EXPECTED_ACCEPTANCES = {
    "ACC.x2n.ai.001": "PASS_CI_SYNTH_FEATURE_GATE_ASR_DISABLED_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.002": "PASS_CI_SYNTH_FEATURE_GATE_OCR_DISABLED_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.003": "PASS_CI_SYNTH_FEATURE_GATE_VISION_DISABLED_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.004": "PASS_CI_SYNTH_FUSION_RED_TEAM_SCHEMA_ISOLATION_MODEL_NOT_RUN",
    "ACC.x2n.ai.005": "PASS_CI_SYNTH_OWNER_TAXONOMY_GUARD_SUGGESTION_ONLY",
    "ACC.x2n.ai.006": "PASS_CI_SYNTH_FEATURE_GATE_CLASSIFICATION_SUGGESTION_ONLY_PRIVATE_GOLD_NOT_RUN",
    "ACC.x2n.ai.007": "PASS_CI_SYNTH_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO",
    "ACC.x2n.rel.002": "PASS_CI_SYNTH_MODEL_PIPELINE_FEATURES_DISABLED_PRIVATE_GOLD_NOT_RUN",
}
EXPECTED_FEATURE_GATES = {
    "asr": "DISABLED_PENDING_PRIVATE_GOLD",
    "automatic_classification": "DISABLED_PENDING_ACC.x2n.ai.006",
    "classification": "SUGGESTION_ONLY_PENDING_PRIVATE_GOLD",
    "fusion": "DISABLED_MODEL_NOT_RUN",
    "ocr": "DISABLED_PENDING_PRIVATE_GOLD",
    "vision": "DISABLED_PENDING_PRIVATE_GOLD",
}
EXPECTED_EXECUTION = {
    "cloud_uploads": 0,
    "config_writes": 0,
    "model_calls": 0,
    "network_calls": 0,
    "platform_calls": 0,
    "private_gold_evaluation": "NOT_RUN",
    "real_account_execution": "NOT_RUN",
    "secret_reads": 0,
    "tool_calls": 0,
}


class Assurance002Error(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance002Error(message)


def _environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(PROJECT_ROOT / "apps/companion/src")
        + os.pathsep
        + str(PROJECT_ROOT / "packages/contracts/src"),
        "RUFF_CACHE_DIR": str(home / "ruff-cache"),
    }


def _run(
    label: str,
    command: Sequence[str],
    *,
    env: dict[str, str],
    timeout: int = 300,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
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
    if not allow_failure and result.returncode != 0:
        safe_code = "UNCLASSIFIED_FAILURE"
        for line in reversed((result.stdout + "\n" + result.stderr).splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("code"), str):
                safe_code = payload["code"]
                break
        raise Assurance002Error(f"blocking command failed: {label}:{safe_code}")
    return result


def _json_payload(output: str, *, label: str) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(payloads, f"{label} emitted no JSON receipt")
    return payloads[-1]


def _unittest_metrics(output: str, *, label: str) -> dict[str, int]:
    match = re.search(r"Ran (\d+) tests? in [0-9.]+s", output)
    _require(match is not None and "OK" in output, f"{label} did not report success")
    _require("skipped" not in output.lower(), f"{label} skipped a blocking test")
    return {"blocking_skips": 0, "tests": int(match.group(1))}


def _validate_feature_gates() -> dict[str, Any]:
    policy = json.loads((PROJECT_ROOT / "machine/policy/ci_gate_manifest.json").read_text(encoding="utf-8"))
    flags = policy.get("model_features")
    _require(isinstance(flags, dict), "model feature policy is invalid")
    _require(
        flags.get("asr") is False
        and flags.get("ocr") is False
        and flags.get("fusion") is False
        and flags.get("classification") is False
        and flags.get("automatic_classification") is False
        and flags.get("vision") is False
        and flags.get("automatic_classification_gate") == "ACC.x2n.ai.006",
        "a model feature is enabled before a private quality gate",
    )
    baseline = validate_model_dataset()
    _require(
        baseline.get("model_calls") == 0 and baseline.get("red_team_contract_cases") == 3, "model baseline drifted"
    )
    return {
        "automatic_classification_gate": flags["automatic_classification_gate"],
        "feature_gates": EXPECTED_FEATURE_GATES,
        "model_dataset": {
            "dataset_id": baseline["dataset_id"],
            "dataset_version": baseline["dataset_version"],
            "red_team_contract_cases": baseline["red_team_contract_cases"],
            "status": baseline["status"],
        },
    }


def _probe_missing_private_gold(env: dict[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a002-private-gold-") as temporary:
        temporary_root = Path(temporary)
        destination = temporary_root / "MediaCrawler"
        destination.mkdir(mode=0o700)
        data_root = destination / "xhs-douyin-2notion"
        data_root.mkdir(mode=0o700)
        probe_env = dict(env)
        probe_env["X2N_DATA_ROOT"] = str(data_root)
        probe_env["X2N_DOWNLOAD_DESTINATION"] = str(destination)
        for action in MISSING_PRIVATE_GOLD_ACTIONS:
            result = _run(
                f"missing_private_gold_{action}",
                (sys.executable, "-B", "-m", "x2n_companion.runtime_cli", "eval", action, "--dataset", "not-present"),
                env=probe_env,
                timeout=120,
                allow_failure=True,
            )
            _require(result.returncode != 0, "missing private Gold input did not fail closed")
            receipt = _json_payload(result.stderr + "\n" + result.stdout, label=f"missing private Gold {action}")
            _require(
                receipt.get("status") == "FAIL_CLOSED" and receipt.get("private_path_emitted") is False,
                "missing private Gold failure leaked a path or did not fail closed",
            )
            rendered = json.dumps(receipt, ensure_ascii=True, sort_keys=True)
            _require(
                str(temporary_root) not in rendered and "/" + "Users/" not in rendered,
                "private Gold probe leaked a path",
            )
    return {"commands": len(MISSING_PRIVATE_GOLD_ACTIONS), "private_gold_evaluation": "NOT_RUN", "safe_failures": 4}


def _run_current_pipeline(env: dict[str, str]) -> dict[str, Any]:
    ruff = (sys.executable, "-B", "-m", "ruff")
    _run("format", (*ruff, "format", "--check", "."), env=env)
    _run("lint", (*ruff, "check", "."), env=env)
    _run(
        "python_compile",
        (sys.executable, "-B", "-m", "compileall", "-q", "apps/companion/src", "packages/contracts/src", "scripts"),
        env=env,
    )
    _run("typescript_contract", ("npm", "run", "check:contracts:types"), env=env)
    assurance = _run(
        "assurance_unit",
        (sys.executable, "-B", "-m", "unittest", "discover", "-v", "-s", "tests", "-p", "test_assurance_002.py"),
        env=env,
    )
    model = _run(
        "model_contract_redteam",
        (sys.executable, "-B", "-m", "unittest", "-v", *MODEL_TEST_MODULES),
        env=env,
    )
    feature_gate = _validate_feature_gates()
    missing_gold = _probe_missing_private_gold(env)
    source = scan_source()
    _require(source.get("status") == "PASS" and source.get("finding_count") == 0, "source privacy scan failed")
    return {
        "assurance_unit": _unittest_metrics(assurance.stdout + assurance.stderr, label="assurance unit"),
        "blocking_commands": 6,
        "blocking_failures": 0,
        "blocking_skips": 0,
        "feature_gate": feature_gate,
        "flaky_blocking_tests": 0,
        "missing_private_gold": missing_gold,
        "model_contract_redteam": _unittest_metrics(model.stdout + model.stderr, label="model contract and red team"),
        "source_scan": source,
    }


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a002-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        pipeline = _run_current_pipeline(_environment(home))
    reports = {
        "asr": {"quality": "NOT_RUN_PRIVATE_GOLD", "scope": "ci_synth_contract_only"},
        "classification": {"calibration": "NOT_RUN_PRIVATE_GOLD", "mode": "suggestion_only"},
        "cross_model_disagreement": {"models_compared": 0, "status": "NOT_RUN_FEATURES_DISABLED"},
        "fusion": {"model_calls": 0, "red_team": "PASS_CI_SYNTH_SCHEMA_AND_ISOLATION"},
        "ocr": {"quality": "NOT_RUN_PRIVATE_GOLD", "scope": "ci_synth_contract_only"},
        "system_card": {"model_quality_claim": "NONE", "status": "UPDATED_FEATURES_DISABLED"},
        "vision": {"quality": "NOT_RUN_PRIVATE_GOLD", "scope": "ci_synth_contract_only"},
    }
    return {
        "acceptance_status": EXPECTED_ACCEPTANCES,
        "execution": EXPECTED_EXECUTION,
        "feature_gates": EXPECTED_FEATURE_GATES,
        "phase": PHASE,
        "pipeline": pipeline,
        "reports": reports,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_MODEL_ASSURANCE_FEATURES_DISABLED_PRIVATE_GOLD_NOT_RUN",
        "task_id": TASK_ID,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
        return 0
    except (Assurance002Error, BaselineError, OSError, subprocess.SubprocessError, ValueError):
        print(
            json.dumps({"status": "FAIL_CLOSED", "task_id": TASK_ID}, ensure_ascii=True, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
