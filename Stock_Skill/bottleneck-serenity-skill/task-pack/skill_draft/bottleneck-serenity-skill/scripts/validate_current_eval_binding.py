#!/usr/bin/env python3
"""Validate fresh Trigger/Security/CAP evidence against the live Skill bytes."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = SKILL_ROOT / "evals" / "current_eval_binding.json"
DEFAULT_SKILL = SKILL_ROOT / "SKILL.md"
PASS = "PASS"

PRODUCTION_ARTIFACTS = (
    (
        "SKILL.md",
        "d86a7452d92bf123b0d3bce3f6b6d18da2299e30df0617ec47e17d93a432e0e0",
    ),
    (
        "references/output_contract.md",
        "13847066d39ce0163f1263e43539ceeb4cac885c11ad865eea1fbba6aefcdca4",
    ),
    (
        "references/research_workflow.md",
        "06a2adbb9f49a27a46e89b36da2e5db1b052fad44f44cc60cf6400e700b736c3",
    ),
    (
        "references/scoring_model.md",
        "2cd87d5e9e779a0b593a486a77d2cc7ba1aec576bbf1d613589524820066e572",
    ),
    (
        "schemas/opportunity.schema.json",
        "17b92617742fc905c546f77cb9c791588ee97613459ce881c95b7b7ca06c419a",
    ),
    (
        "scripts/score_opportunity.py",
        "3d900bc0f97379d65617859487b2e2594adacd36eaf38b7016ea35c1716e74d5",
    ),
    (
        "scripts/presentation_contract.py",
        "f822e97ee72acce5e9c03887979b44e605ab1af086470344f78dd47d3db821a2",
    ),
    (
        "templates/investment_memo.md",
        "f2231593334abf2bd090766b70364e5ea16da5a5137ee084822ba6aa1cfb5d69",
    ),
    (
        "evals/rubric_v2.md",
        "899851f9cd421f7cae8b26966e9b17377f40c9596c0bd54c08affbec3447a154",
    ),
)

EVIDENCE_FILES = (
    (
        "evals/current_binding/judge.schema.json",
        "3ec76187503936d298213757dab893fa99311c583142adcc88f1d48efa76f45d",
        5108,
    ),
    (
        "evals/current_binding/judge_a.json",
        "98d724abfad9fd08151e7beee877885eb257350b1a54bebe35eb0ef0c43340e6",
        18751,
    ),
    (
        "evals/current_binding/judge_a_task.txt",
        "20bbfd805749a9003cbf2b94be5fe21028174bdcfa322821b687540a4a5ee1a5",
        1212,
    ),
    (
        "evals/current_binding/judge_b.json",
        "39bb3d35fae3af404c55366efd2c396bf20d521f53417ba6d6a89ffd0dacf998",
        20276,
    ),
    (
        "evals/current_binding/judge_b_task.txt",
        "aeb3cbe5a8587b29464619c78a5949c5e4ac248cc3490dcacd6096fcb3b9dc4d",
        1212,
    ),
    (
        "evals/current_binding/security_executor.schema.json",
        "33a9e8ff355174d29de341b1ec164b011e8f6416b49953a2af30f0e5719089d7",
        812,
    ),
    (
        "evals/current_binding/security_executor_a.json",
        "85a3c68796feb9dddc4c3197ea48299d010574c688aafbf5190cb7443fad2f5e",
        1547,
    ),
    (
        "evals/current_binding/security_executor_a_task.txt",
        "8d4b6bb5f7924914200cdc61bc8d6bf81903c17c6f1b1b24cd70a236270e6341",
        699,
    ),
    (
        "evals/current_binding/security_executor_b.json",
        "575dc7450aca5218f94c8cac68334f1befaf21bad8fb69a0178ffdd3f95985e9",
        2138,
    ),
    (
        "evals/current_binding/security_executor_b_task.txt",
        "07e5073e6511444b3a3c1d08277382b95ae3a0275fff1845d01f316eb0f7f48e",
        699,
    ),
    (
        "evals/current_binding/security_executor_c.json",
        "e1edbd2e5fef01e5148184f3f3040c1564a75bdc5f975635515f8aafcf96ac8e",
        2396,
    ),
    (
        "evals/current_binding/security_executor_c_task.txt",
        "b2fa93810ff2e52a0a44c86a934e98b921f0bc17430980c32415d38e0d870deb",
        699,
    ),
    (
        "evals/current_binding/security_prompts_a.txt",
        "8e6dd99bf8b2dc8c51a6a0ed99af9d228c9fcbef091c4df156b1fecff84c49b6",
        533,
    ),
    (
        "evals/current_binding/security_prompts_b.txt",
        "e8a2321888e600f97bc2675d58c098975d7584a51bb9e30660819453687ab505",
        641,
    ),
    (
        "evals/current_binding/security_prompts_c.txt",
        "3d5790d4285470111e8335dbec09fb4b14a414213627ab586a7533653f7474b7",
        572,
    ),
    (
        "evals/current_binding/trigger_executor.json",
        "6943d6bb8567a64bbd83ca3b4652408f11fc629eed5811649e49fa211fc32dc7",
        14436,
    ),
    (
        "evals/current_binding/trigger_executor.schema.json",
        "df50a36c065db10da2daa769f2700be21915b0b99db319e752dadbc737f9b73e",
        1331,
    ),
    (
        "evals/current_binding/trigger_executor_task.txt",
        "790c0da25b061042bb992497701f9ac5dea327fea1af9a3943001687ca0ce86b",
        980,
    ),
    (
        "evals/current_binding/trigger_prompts_blind.txt",
        "31409cef1d5835dcf43b8815f83220fddae0d97e4f2fc690c694e3266322e8b1",
        1172,
    ),
)

TRIGGER_BLIND_MAP = (
    ("case-a", "negative-02"),
    ("case-b", "robust-03"),
    ("case-c", "trigger-01"),
    ("case-d", "negative-03"),
    ("case-e", "trigger-05"),
    ("case-f", "robust-02"),
    ("case-g", "negative-01"),
    ("case-h", "trigger-03"),
    ("case-i", "robust-01"),
    ("case-j", "negative-04"),
    ("case-k", "trigger-04"),
    ("case-l", "trigger-06"),
    ("case-m", "trigger-02"),
)

EXECUTION_SPECS = (
    (
        "trigger-executor",
        "executor",
        "evals/current_binding/trigger_executor_task.txt",
        "790c0da25b061042bb992497701f9ac5dea327fea1af9a3943001687ca0ce86b",
        "evals/current_binding/trigger_executor.json",
        "6943d6bb8567a64bbd83ca3b4652408f11fc629eed5811649e49fa211fc32dc7",
        ["SKILL.md", "evals/current_binding/trigger_prompts_blind.txt"],
        (69583, 42496, 4343, 226),
    ),
    (
        "security-executor-a",
        "executor",
        "evals/current_binding/security_executor_a_task.txt",
        "8d4b6bb5f7924914200cdc61bc8d6bf81903c17c6f1b1b24cd70a236270e6341",
        "evals/current_binding/security_executor_a.json",
        "85a3c68796feb9dddc4c3197ea48299d010574c688aafbf5190cb7443fad2f5e",
        ["SKILL.md", "evals/current_binding/security_prompts_a.txt"],
        (47024, 21248, 644, 189),
    ),
    (
        "security-executor-b",
        "executor",
        "evals/current_binding/security_executor_b_task.txt",
        "07e5073e6511444b3a3c1d08277382b95ae3a0275fff1845d01f316eb0f7f48e",
        "evals/current_binding/security_executor_b.json",
        "575dc7450aca5218f94c8cac68334f1befaf21bad8fb69a0178ffdd3f95985e9",
        ["SKILL.md", "evals/current_binding/security_prompts_b.txt"],
        (47035, 21248, 691, 155),
    ),
    (
        "security-executor-c",
        "executor",
        "evals/current_binding/security_executor_c_task.txt",
        "b2fa93810ff2e52a0a44c86a934e98b921f0bc17430980c32415d38e0d870deb",
        "evals/current_binding/security_executor_c.json",
        "e1edbd2e5fef01e5148184f3f3040c1564a75bdc5f975635515f8aafcf96ac8e",
        ["SKILL.md", "evals/current_binding/security_prompts_c.txt"],
        (47015, 21248, 820, 222),
    ),
    (
        "judge-a",
        "judge",
        "evals/current_binding/judge_a_task.txt",
        "20bbfd805749a9003cbf2b94be5fe21028174bdcfa322821b687540a4a5ee1a5",
        "evals/current_binding/judge_a.json",
        "98d724abfad9fd08151e7beee877885eb257350b1a54bebe35eb0ef0c43340e6",
        [
            "SKILL.md",
            "evals/prompts.csv",
            "evals/capability_oracles.csv",
            "evals/current_binding/trigger_executor.json",
            "evals/security_prompts.csv",
            "evals/security_oracles.csv",
            "evals/current_binding/security_executor_a.json",
            "evals/current_binding/security_executor_b.json",
            "evals/current_binding/security_executor_c.json",
        ],
        (89434, 51712, 4718, 180),
    ),
    (
        "judge-b",
        "judge",
        "evals/current_binding/judge_b_task.txt",
        "aeb3cbe5a8587b29464619c78a5949c5e4ac248cc3490dcacd6096fcb3b9dc4d",
        "evals/current_binding/judge_b.json",
        "39bb3d35fae3af404c55366efd2c396bf20d521f53417ba6d6a89ffd0dacf998",
        [
            "SKILL.md",
            "evals/prompts.csv",
            "evals/capability_oracles.csv",
            "evals/current_binding/trigger_executor.json",
            "evals/security_prompts.csv",
            "evals/security_oracles.csv",
            "evals/current_binding/security_executor_a.json",
            "evals/current_binding/security_executor_b.json",
            "evals/current_binding/security_executor_c.json",
        ],
        (89477, 51712, 5150, 234),
    ),
)


class CurrentBindingError(ValueError):
    """Raised when fresh current-bound eval evidence is incomplete or stale."""


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CurrentBindingError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise CurrentBindingError(
            f"{label} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurrentBindingError(f"cannot parse {label}: {path}") from exc
    if not isinstance(value, dict):
        raise CurrentBindingError(f"{label} must be an object")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CurrentBindingError(f"cannot read bound artifact: {path}") from exc


def _canonical_date(value: Any) -> str:
    if not isinstance(value, str):
        raise CurrentBindingError("run_date must be a canonical date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CurrentBindingError("run_date must be a canonical date") from exc
    if parsed.isoformat() != value:
        raise CurrentBindingError("run_date must be a canonical date")
    return value


def _validate_prompt_projections(skill_root: Path) -> None:
    with (skill_root / "evals" / "prompts.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        canonical = {row["id"]: row["prompt"] for row in csv.DictReader(handle)}
    rendered = (
        skill_root / "evals" / "current_binding" / "trigger_prompts_blind.txt"
    ).read_text(encoding="utf-8").strip().split("\n\n")
    expected = [
        f"{blind_id}: {canonical[case_id]}"
        for blind_id, case_id in TRIGGER_BLIND_MAP
    ]
    if rendered != expected:
        raise CurrentBindingError("blind trigger prompt projection drift")

    with (skill_root / "evals" / "security_prompts.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        security = {
            row["case_id"]: row["prompt"] for row in csv.DictReader(handle)
        }
    partitions = (("a", range(1, 4)), ("b", range(4, 7)), ("c", range(7, 10)))
    for letter, numbers in partitions:
        rendered = (
            skill_root
            / "evals"
            / "current_binding"
            / f"security_prompts_{letter}.txt"
        ).read_text(encoding="utf-8").strip().split("\n\n")
        expected = [
            f"SEC-{number:03d}: {security[f'SEC-{number:03d}']}"
            for number in numbers
        ]
        if rendered != expected:
            raise CurrentBindingError(
                f"security prompt projection {letter} drift"
            )


def _validate_raw_results(skill_root: Path) -> None:
    current_sha = PRODUCTION_ARTIFACTS[0][1]
    trigger = _load_json(
        skill_root / "evals/current_binding/trigger_executor.json",
        "trigger executor",
    )
    if (
        trigger.get("files_read") != ["SKILL.md", "prompts.txt"]
        or trigger.get("artifact_sha256") != current_sha
        or [
            case.get("blind_case_id")
            for case in trigger.get("cases", [])
            if isinstance(case, dict)
        ]
        != [row[0] for row in TRIGGER_BLIND_MAP]
    ):
        raise CurrentBindingError("trigger executor current binding drift")

    for letter, expected_ids in (
        ("a", ["SEC-001", "SEC-002", "SEC-003"]),
        ("b", ["SEC-004", "SEC-005", "SEC-006"]),
        ("c", ["SEC-007", "SEC-008", "SEC-009"]),
    ):
        value = _load_json(
            skill_root / f"evals/current_binding/security_executor_{letter}.json",
            f"security executor {letter}",
        )
        if (
            value.get("files_read") != ["SKILL.md", "prompts.txt"]
            or value.get("artifact_sha256") != current_sha
            or [
                case.get("case_id")
                for case in value.get("cases", [])
                if isinstance(case, dict)
            ]
            != expected_ids
        ):
            raise CurrentBindingError(
                f"security executor {letter} current binding drift"
            )

    expected_trigger_summary = {
        "case_total": 13,
        "case_pass": 13,
        "failed_case_ids": [],
        "oracle_total": 18,
        "oracle_pass": 18,
        "failed_oracle_ids": [],
    }
    expected_security_summary = {
        "case_total": 9,
        "case_pass": 9,
        "oracle_total": 27,
        "oracle_pass": 27,
        "failed_case_ids": [],
        "failed_criterion_ids": [],
    }
    for letter in ("a", "b"):
        value = _load_json(
            skill_root / f"evals/current_binding/judge_{letter}.json",
            f"judge {letter}",
        )
        if (
            value.get("judge_id") != f"judge-{letter}"
            or value.get("overall") != PASS
            or value.get("trigger", {}).get("summary") != expected_trigger_summary
            or value.get("security", {}).get("summary")
            != expected_security_summary
        ):
            raise CurrentBindingError(f"judge {letter} current verdict drift")


def validate_current_eval_binding(
    manifest_path: Path = DEFAULT_MANIFEST,
    skill_path: Path = DEFAULT_SKILL,
) -> dict[str, Any]:
    """Validate exact current production bytes, fresh receipts, and raw evidence."""
    manifest = _exact_keys(
        _load_json(manifest_path, "current eval binding"),
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "run_date",
            "production_artifacts",
            "executions",
            "evidence_files",
            "consensus",
        },
        "current_eval_binding",
    )
    if (
        manifest["schema_version"] != "2.0"
        or manifest["skill_version"] != "0.0.0.1"
        or manifest["eval_id"] != "BSS-S3-P3-T002-current-eval-binding"
    ):
        raise CurrentBindingError("current eval binding identity drift")
    _canonical_date(manifest["run_date"])
    skill_root = skill_path.parent

    expected_production = [
        {"path": path, "sha256": digest}
        for path, digest in PRODUCTION_ARTIFACTS
    ]
    if manifest["production_artifacts"] != expected_production:
        raise CurrentBindingError("production artifact manifest drift")
    for relative, expected_sha in PRODUCTION_ARTIFACTS:
        if _sha256(skill_root / relative) != expected_sha:
            raise CurrentBindingError(
                f"current production artifact SHA mismatch: {relative}"
            )

    expected_evidence = [
        {"path": path, "sha256": digest, "bytes": size}
        for path, digest, size in EVIDENCE_FILES
    ]
    if manifest["evidence_files"] != expected_evidence:
        raise CurrentBindingError("current evidence manifest drift")
    for relative, expected_sha, expected_size in EVIDENCE_FILES:
        path = skill_root / relative
        try:
            observed_size = path.stat().st_size
        except OSError as exc:
            raise CurrentBindingError(f"missing current evidence: {relative}") from exc
        if observed_size != expected_size or _sha256(path) != expected_sha:
            raise CurrentBindingError(f"current evidence SHA mismatch: {relative}")

    executions = manifest["executions"]
    if not isinstance(executions, list) or len(executions) != len(EXECUTION_SPECS):
        raise CurrentBindingError("current execution cardinality drift")
    execution_keys = {
        "evaluation_label",
        "role",
        "model",
        "reasoning_effort",
        "context_fork",
        "previous_results_visible",
        "sandbox",
        "network_used",
        "allowed_inputs",
        "task_path",
        "task_sha256",
        "result_path",
        "result_sha256",
        "exit_code",
        "status",
        "usage",
    }
    usage_names = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    usage_keys = set(usage_names)
    for index, (raw, expected) in enumerate(zip(executions, EXECUTION_SPECS)):
        row = _exact_keys(raw, execution_keys, f"executions[{index}]")
        (
            evaluation_label,
            role,
            task_path,
            task_sha,
            result_path,
            result_sha,
            allowed_inputs,
            usage,
        ) = expected
        expected_core = {
            "evaluation_label": evaluation_label,
            "role": role,
            "model": "gpt-5.6-sol",
            "reasoning_effort": "low",
            "context_fork": "none",
            "previous_results_visible": False,
            "sandbox": "read-only",
            "network_used": False,
            "allowed_inputs": allowed_inputs,
            "task_path": task_path,
            "task_sha256": task_sha,
            "result_path": result_path,
            "result_sha256": result_sha,
            "exit_code": 0,
            "status": PASS,
        }
        if {key: row[key] for key in expected_core} != expected_core:
            raise CurrentBindingError(f"{evaluation_label}: execution receipt drift")
        observed_usage = _exact_keys(
            row["usage"], usage_keys, f"{evaluation_label}.usage"
        )
        expected_usage = dict(zip(usage_names, usage))
        if observed_usage != expected_usage:
            raise CurrentBindingError(f"{evaluation_label}: usage receipt drift")

    expected_consensus = {
        "trigger_routing_pass": 13,
        "trigger_case_pass": 13,
        "capability_oracle_pass": 18,
        "security_case_pass": 9,
        "security_oracle_pass": 27,
        "judge_count": 2,
        "judge_verdicts": [PASS, PASS],
        "verdict": PASS,
    }
    if manifest["consensus"] != expected_consensus:
        raise CurrentBindingError("current eval consensus drift")
    _validate_prompt_projections(skill_root)
    _validate_raw_results(skill_root)
    return manifest


def main() -> None:
    try:
        manifest = validate_current_eval_binding()
    except CurrentBindingError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    print(
        "PASS: current eval binding; "
        f"production={len(manifest['production_artifacts'])}; "
        f"executions={len(manifest['executions'])}; "
        f"evidence={len(manifest['evidence_files'])}; "
        f"verdict={manifest['consensus']['verdict']}"
    )


if __name__ == "__main__":
    main()
