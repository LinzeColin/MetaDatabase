#!/usr/bin/env python3
"""Validate the pre-registered trigger eval, blind outputs, and CAP oracles."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS = SKILL_ROOT / "evals" / "prompts.csv"
DEFAULT_ORACLES = SKILL_ROOT / "evals" / "capability_oracles.csv"
DEFAULT_RESULTS = SKILL_ROOT / "evals" / "trigger_eval_results.json"
DEFAULT_SKILL = SKILL_ROOT / "SKILL.md"
PROMPT_HEADER = (
    "id",
    "should_trigger",
    "mode",
    "prompt",
    "must_have",
    "must_not_have",
)
ORACLE_HEADER = (
    "oracle_id",
    "capability_id",
    "polarity",
    "case_id",
    "criterion",
    "must_not",
)
EXPECTED_CASES = {
    "trigger-01": (True, "scan"),
    "trigger-02": (True, "deep_dive"),
    "trigger-03": (True, "compare"),
    "trigger-04": (True, "monitor"),
    "trigger-05": (True, "postmortem"),
    "trigger-06": (True, "scan"),
    "negative-01": (False, "none"),
    "negative-02": (False, "none"),
    "negative-03": (False, "none"),
    "negative-04": (False, "none"),
    "robust-01": (True, "scan"),
    "robust-02": (True, "deep_dive"),
    "robust-03": (True, "compare"),
}
EXPECTED_BLIND_MAP = {
    "case-a": "negative-02",
    "case-b": "robust-03",
    "case-c": "trigger-01",
    "case-d": "negative-03",
    "case-e": "trigger-05",
    "case-f": "robust-02",
    "case-g": "negative-01",
    "case-h": "trigger-03",
    "case-i": "robust-01",
    "case-j": "negative-04",
    "case-k": "trigger-04",
    "case-l": "trigger-06",
    "case-m": "trigger-02",
}
ALLOWED_ROUTES = {
    "activate_full_workflow",
    "respond_without_skill",
    "refuse_no_execution",
}
PASS = "PASS"
CURRENT_BINDING_MANIFEST = "current_eval_binding.json"


class TriggerEvalError(ValueError):
    """Raised when trigger-eval evidence violates the frozen contract."""


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TriggerEvalError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise TriggerEvalError(
            f"{label} keys mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _load_csv(path: Path, header: tuple[str, ...], label: str) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
    except OSError as exc:
        raise TriggerEvalError(f"cannot read {label}: {path}") from exc
    if not rows or tuple(rows[0]) != header:
        raise TriggerEvalError(f"{label} header must equal {header}")
    parsed: list[dict[str, str]] = []
    for number, row in enumerate(rows[1:], 2):
        if len(row) != len(header):
            raise TriggerEvalError(
                f"{label}:{number}: expected {len(header)} fields, got {len(row)}"
            )
        for field, value in zip(header, row):
            if value != value.strip() or value.startswith('"') or value.endswith('"'):
                raise TriggerEvalError(
                    f"{label}:{number}:{field}: non-canonical surrounding whitespace/quote"
                )
        parsed.append(dict(zip(header, row)))
    return parsed


def load_prompts(path: Path = DEFAULT_PROMPTS) -> dict[str, dict[str, str]]:
    rows = _load_csv(path, PROMPT_HEADER, "prompts")
    ids = [row["id"] for row in rows]
    if ids != list(EXPECTED_CASES):
        raise TriggerEvalError("prompts must preserve the 13 pre-registered case IDs/order")
    for row in rows:
        case_id = row["id"]
        expected_trigger, expected_mode = EXPECTED_CASES[case_id]
        if row["should_trigger"] != str(expected_trigger).lower():
            raise TriggerEvalError(f"{case_id}: should_trigger drift")
        if row["mode"] != expected_mode:
            raise TriggerEvalError(f"{case_id}: mode drift")
        if not row["prompt"] or not row["must_not_have"]:
            raise TriggerEvalError(f"{case_id}: prompt and must_not_have are required")
        if expected_trigger and not row["must_have"]:
            raise TriggerEvalError(f"{case_id}: positive/robust case needs must_have")
        if case_id == "negative-03" and not row["must_have"]:
            raise TriggerEvalError("negative-03 needs refusal/no-execution evidence")
    return {row["id"]: row for row in rows}


def load_oracles(
    path: Path = DEFAULT_ORACLES,
    prompts: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    prompts = prompts or load_prompts()
    rows = _load_csv(path, ORACLE_HEADER, "capability_oracles")
    expected_ids = [
        f"CAP-{number:03d}-{polarity}"
        for number in range(1, 10)
        for polarity in ("P", "N")
    ]
    ids = [row["oracle_id"] for row in rows]
    if ids != expected_ids:
        raise TriggerEvalError("capability_oracles must contain ordered CAP-001..009 P/N pairs")
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if row["case_id"] not in prompts:
            raise TriggerEvalError(f"{row['oracle_id']}: unknown case_id")
        if row["polarity"] not in {"positive", "negative"}:
            raise TriggerEvalError(f"{row['oracle_id']}: invalid polarity")
        if not row["criterion"] or not row["must_not"]:
            raise TriggerEvalError(f"{row['oracle_id']}: criterion/must_not required")
        counts[(row["capability_id"], row["polarity"])] += 1
    expected_counts = Counter(
        (f"CAP-{number:03d}", polarity)
        for number in range(1, 10)
        for polarity in ("positive", "negative")
    )
    if counts != expected_counts:
        raise TriggerEvalError("each CAP must have exactly one positive and one negative oracle")
    return {row["oracle_id"]: row for row in rows}


def _expected_route(case_id: str) -> str:
    should_trigger, _ = EXPECTED_CASES[case_id]
    if should_trigger:
        return "activate_full_workflow"
    if case_id == "negative-03":
        return "refuse_no_execution"
    return "respond_without_skill"


def _canonical_date(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TriggerEvalError(f"{label} must be a canonical date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise TriggerEvalError(f"{label} must be a canonical date") from exc
    if parsed.isoformat() != value:
        raise TriggerEvalError(f"{label} must be a canonical date")
    return value


def _require_quote(raw_response: str, quote: Any, label: str) -> None:
    if not isinstance(quote, str) or not quote.strip():
        raise TriggerEvalError(f"{label}: evidence quote must be non-empty")
    if quote not in raw_response:
        raise TriggerEvalError(f"{label}: evidence quote is not in raw response")


def validate_current_binding(
    binding_path: Path,
    skill_path: Path,
) -> dict[str, Any]:
    """Validate fresh executions and judges bound to the exact current Skill."""
    validator_path = Path(__file__).with_name("validate_current_eval_binding.py")
    spec = importlib.util.spec_from_file_location(
        "_bss_validate_current_eval_binding",
        validator_path,
    )
    if spec is None or spec.loader is None:
        raise TriggerEvalError("cannot load current eval binding validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.validate_current_eval_binding(binding_path, skill_path)
    except module.CurrentBindingError as exc:
        raise TriggerEvalError(str(exc)) from exc

def validate_results(
    results_path: Path = DEFAULT_RESULTS,
    prompts_path: Path = DEFAULT_PROMPTS,
    oracles_path: Path = DEFAULT_ORACLES,
    skill_path: Path = DEFAULT_SKILL,
) -> dict[str, int]:
    prompts = load_prompts(prompts_path)
    oracles = load_oracles(oracles_path, prompts)
    try:
        result = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TriggerEvalError(f"cannot parse trigger results: {results_path}") from exc
    result = _exact_keys(
        result,
        {
            "schema_version",
            "skill_version",
            "eval_id",
            "run_date",
            "remediation_baseline",
            "adjudication_baseline",
            "pair_overlap_baseline",
            "entity_chain_baseline",
            "oracle_precision_baseline",
            "executor",
            "judges",
            "summary",
        },
        "results",
    )
    if result["schema_version"] != "2.0" or result["skill_version"] != "0.0.0.1":
        raise TriggerEvalError("results schema/skill version mismatch")
    if result["eval_id"] != "BSS-S3-P3-T002-current-trigger-capability":
        raise TriggerEvalError("results eval_id mismatch")
    _canonical_date(result["run_date"], "run_date")

    baseline = _exact_keys(
        result["remediation_baseline"],
        {"artifact_sha256", "routing_pass_count", "routing_total", "failed_cases"},
        "remediation_baseline",
    )
    if baseline["routing_pass_count"] != 12 or baseline["routing_total"] != 13:
        raise TriggerEvalError("baseline must preserve the observed 12/13 result")
    failed = baseline["failed_cases"]
    if not isinstance(failed, list) or len(failed) != 1:
        raise TriggerEvalError("baseline must preserve exactly one failed case")
    failed_case = _exact_keys(
        failed[0],
        {
            "id",
            "blind_case_id",
            "observed_route",
            "expected_route",
            "raw_response",
        },
        "remediation_baseline.failed_cases[0]",
    )
    if (
        failed_case["id"],
        failed_case["blind_case_id"],
        failed_case["observed_route"],
        failed_case["expected_route"],
    ) != (
        "robust-01",
        "case-i",
        "respond_without_skill",
        "activate_full_workflow",
    ):
        raise TriggerEvalError("baseline failed-case identity drift")
    if not isinstance(failed_case["raw_response"], str) or not failed_case["raw_response"]:
        raise TriggerEvalError("baseline raw response is required")

    adjudication = _exact_keys(
        result["adjudication_baseline"],
        {
            "artifact_sha256",
            "routing_pass_count",
            "routing_total",
            "executor_cases",
            "judge_summaries",
            "remediation",
        },
        "adjudication_baseline",
    )
    if adjudication["artifact_sha256"] != (
        "3f45ca6411471776071eec726eeb678ff3f026138c4c16da968aa3f2af689beb"
    ):
        raise TriggerEvalError("adjudication baseline artifact SHA drift")
    if adjudication["routing_pass_count"] != 13 or adjudication["routing_total"] != 13:
        raise TriggerEvalError("adjudication baseline must preserve the observed 13/13 routing")
    adjudication_cases = adjudication["executor_cases"]
    if not isinstance(adjudication_cases, list) or len(adjudication_cases) != 13:
        raise TriggerEvalError("adjudication baseline must preserve 13 raw executor cases")
    if [case.get("id") for case in adjudication_cases if isinstance(case, dict)] != list(
        EXPECTED_CASES
    ):
        raise TriggerEvalError("adjudication baseline case IDs/order drift")
    for index, case in enumerate(adjudication_cases):
        case = _exact_keys(
            case,
            {"id", "blind_case_id", "observed_route", "observed_mode", "raw_response"},
            f"adjudication_baseline.executor_cases[{index}]",
        )
        if not isinstance(case["raw_response"], str) or not case["raw_response"].strip():
            raise TriggerEvalError("adjudication baseline raw response is required")
    expected_judge_summaries = [
        {
            "judge_id": "judge-a",
            "case_pass_count": 9,
            "case_total": 13,
            "failed_case_ids": ["trigger-01", "trigger-02", "trigger-05", "trigger-06"],
            "oracle_pass_count": 12,
            "oracle_total": 18,
            "failed_oracle_ids": [
                "CAP-001-P",
                "CAP-004-N",
                "CAP-005-P",
                "CAP-006-P",
                "CAP-007-P",
                "CAP-009-P",
            ],
        },
        {
            "judge_id": "judge-b",
            "case_pass_count": 9,
            "case_total": 13,
            "failed_case_ids": ["trigger-01", "trigger-02", "trigger-05", "trigger-06"],
            "oracle_pass_count": 11,
            "oracle_total": 18,
            "failed_oracle_ids": [
                "CAP-001-P",
                "CAP-004-P",
                "CAP-004-N",
                "CAP-005-P",
                "CAP-006-P",
                "CAP-007-P",
                "CAP-009-P",
            ],
        },
    ]
    if adjudication["judge_summaries"] != expected_judge_summaries:
        raise TriggerEvalError("adjudication baseline judge summaries drift")
    if not isinstance(adjudication["remediation"], str) or not adjudication[
        "remediation"
    ].strip():
        raise TriggerEvalError("adjudication remediation is required")

    pair_overlap = _exact_keys(
        result["pair_overlap_baseline"],
        {
            "artifact_sha256",
            "routing_pass_count",
            "routing_total",
            "executor_cases",
            "judge_summaries",
            "remediation",
        },
        "pair_overlap_baseline",
    )
    if pair_overlap["artifact_sha256"] != (
        "29064055414fdfdb3aac1abad03c2e10fb106553e9cdcaa0150d8638a39172ad"
    ):
        raise TriggerEvalError("pair-overlap baseline artifact SHA drift")
    if pair_overlap["routing_pass_count"] != 13 or pair_overlap["routing_total"] != 13:
        raise TriggerEvalError("pair-overlap baseline must preserve 13/13 routing")
    pair_cases = pair_overlap["executor_cases"]
    if not isinstance(pair_cases, list) or len(pair_cases) != 13:
        raise TriggerEvalError("pair-overlap baseline must preserve 13 raw executor cases")
    if [case.get("id") for case in pair_cases if isinstance(case, dict)] != list(
        EXPECTED_CASES
    ):
        raise TriggerEvalError("pair-overlap baseline case IDs/order drift")
    for index, case in enumerate(pair_cases):
        case = _exact_keys(
            case,
            {"id", "blind_case_id", "observed_route", "observed_mode", "raw_response"},
            f"pair_overlap_baseline.executor_cases[{index}]",
        )
        if not isinstance(case["raw_response"], str) or not case["raw_response"].strip():
            raise TriggerEvalError("pair-overlap baseline raw response is required")
    expected_pair_judges = [
        {
            "judge_id": judge_id,
            "case_pass_count": 11,
            "case_total": 13,
            "failed_case_ids": ["trigger-03", "robust-03"],
            "oracle_pass_count": 18,
            "oracle_total": 18,
            "failed_oracle_ids": [],
        }
        for judge_id in ("judge-c", "judge-d")
    ]
    if pair_overlap["judge_summaries"] != expected_pair_judges:
        raise TriggerEvalError("pair-overlap baseline judge summaries drift")
    if not isinstance(pair_overlap["remediation"], str) or not pair_overlap[
        "remediation"
    ].strip():
        raise TriggerEvalError("pair-overlap remediation is required")

    entity_chain = _exact_keys(
        result["entity_chain_baseline"],
        {
            "artifact_sha256",
            "routing_pass_count",
            "routing_total",
            "executor_cases",
            "judge_summaries",
            "remediation",
        },
        "entity_chain_baseline",
    )
    if entity_chain["artifact_sha256"] != (
        "05c256ffbf8344f5a18eaeec882836db71291f295b14a6fcd9394258ebc15be7"
    ):
        raise TriggerEvalError("entity-chain baseline artifact SHA drift")
    if entity_chain["routing_pass_count"] != 13 or entity_chain["routing_total"] != 13:
        raise TriggerEvalError("entity-chain baseline must preserve 13/13 routing")
    entity_cases = entity_chain["executor_cases"]
    if not isinstance(entity_cases, list) or len(entity_cases) != 13:
        raise TriggerEvalError("entity-chain baseline must preserve 13 raw executor cases")
    if [case.get("id") for case in entity_cases if isinstance(case, dict)] != list(
        EXPECTED_CASES
    ):
        raise TriggerEvalError("entity-chain baseline case IDs/order drift")
    for index, case in enumerate(entity_cases):
        case = _exact_keys(
            case,
            {"id", "blind_case_id", "observed_route", "observed_mode", "raw_response"},
            f"entity_chain_baseline.executor_cases[{index}]",
        )
        if not isinstance(case["raw_response"], str) or not case["raw_response"].strip():
            raise TriggerEvalError("entity-chain baseline raw response is required")
    expected_entity_judges = [
        {
            "judge_id": judge_id,
            "case_pass_count": 12,
            "case_total": 13,
            "failed_case_ids": ["trigger-06"],
            "oracle_pass_count": 17,
            "oracle_total": 18,
            "failed_oracle_ids": ["CAP-004-N"],
        }
        for judge_id in ("judge-e", "judge-f")
    ]
    if entity_chain["judge_summaries"] != expected_entity_judges:
        raise TriggerEvalError("entity-chain baseline judge summaries drift")
    if not isinstance(entity_chain["remediation"], str) or not entity_chain[
        "remediation"
    ].strip():
        raise TriggerEvalError("entity-chain remediation is required")

    oracle_precision = _exact_keys(
        result["oracle_precision_baseline"],
        {
            "artifact_sha256",
            "routing_pass_count",
            "routing_total",
            "executor_cases",
            "judge_summaries",
            "remediation",
        },
        "oracle_precision_baseline",
    )
    if oracle_precision["artifact_sha256"] != (
        "6595ebe118811020128a5c44594f04db93e067e7ee170886ef543f1724be41c5"
    ):
        raise TriggerEvalError("oracle-precision baseline artifact SHA drift")
    if (
        oracle_precision["routing_pass_count"] != 13
        or oracle_precision["routing_total"] != 13
    ):
        raise TriggerEvalError("oracle-precision baseline must preserve 13/13 routing")
    oracle_cases = oracle_precision["executor_cases"]
    if not isinstance(oracle_cases, list) or len(oracle_cases) != 13:
        raise TriggerEvalError("oracle-precision baseline must preserve 13 raw cases")
    if [case.get("id") for case in oracle_cases if isinstance(case, dict)] != list(
        EXPECTED_CASES
    ):
        raise TriggerEvalError("oracle-precision baseline case IDs/order drift")
    for index, case in enumerate(oracle_cases):
        case = _exact_keys(
            case,
            {"id", "blind_case_id", "observed_route", "observed_mode", "raw_response"},
            f"oracle_precision_baseline.executor_cases[{index}]",
        )
        if not isinstance(case["raw_response"], str) or not case["raw_response"].strip():
            raise TriggerEvalError("oracle-precision baseline raw response is required")
    expected_oracle_judges = [
        {
            "judge_id": "judge-g",
            "case_pass_count": 13,
            "case_total": 13,
            "failed_case_ids": [],
            "oracle_pass_count": 18,
            "oracle_total": 18,
            "failed_oracle_ids": [],
        },
        {
            "judge_id": "judge-h",
            "case_pass_count": 13,
            "case_total": 13,
            "failed_case_ids": [],
            "oracle_pass_count": 16,
            "oracle_total": 18,
            "failed_oracle_ids": ["CAP-006-P", "CAP-007-P"],
        },
    ]
    if oracle_precision["judge_summaries"] != expected_oracle_judges:
        raise TriggerEvalError("oracle-precision baseline judge summaries drift")
    if not isinstance(oracle_precision["remediation"], str) or not oracle_precision[
        "remediation"
    ].strip():
        raise TriggerEvalError("oracle-precision remediation is required")

    executor = _exact_keys(
        result["executor"],
        {
            "executor_id",
            "history_fork",
            "expected_labels_visible",
            "files_read",
            "artifact_sha256",
            "cases",
        },
        "executor",
    )
    if (
        executor["executor_id"] != "current-trigger-executor"
        or executor["history_fork"] != "none"
    ):
        raise TriggerEvalError("executor must be the fresh current-trigger run")
    if executor["expected_labels_visible"] is not False:
        raise TriggerEvalError("executor must not receive expected labels")
    if executor["files_read"] != ["SKILL.md", "prompts.txt"]:
        raise TriggerEvalError(
            "executor file surface must be exactly SKILL.md plus blind prompts"
        )
    binding = validate_current_binding(
        results_path.parent / CURRENT_BINDING_MANIFEST,
        skill_path,
    )
    current_skill_sha = binding["production_artifacts"][0]["sha256"]
    if executor["artifact_sha256"] != current_skill_sha:
        raise TriggerEvalError("executor artifact SHA does not match current Skill")
    raw_trigger_path = (
        skill_path.parent / "evals" / "current_binding" / "trigger_executor.json"
    )
    try:
        raw_trigger = json.loads(raw_trigger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TriggerEvalError("cannot parse current trigger executor evidence") from exc
    expected_current_cases = [
        {"id": EXPECTED_BLIND_MAP[case["blind_case_id"]], **case}
        for case in raw_trigger["cases"]
    ]
    if executor["cases"] != expected_current_cases:
        raise TriggerEvalError("embedded executor cases drift from current raw evidence")
    cases = executor["cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise TriggerEvalError("executor must contain exactly 13 cases")
    case_results: dict[str, dict[str, Any]] = {}
    seen_blind: set[str] = set()
    for index, value in enumerate(cases):
        case = _exact_keys(
            value,
            {"id", "blind_case_id", "observed_route", "observed_mode", "raw_response"},
            f"executor.cases[{index}]",
        )
        case_id = case["id"]
        blind_id = case["blind_case_id"]
        if case_id in case_results or blind_id in seen_blind:
            raise TriggerEvalError("duplicate executor case/blind ID")
        if EXPECTED_BLIND_MAP.get(blind_id) != case_id:
            raise TriggerEvalError(f"{case_id}: blind mapping drift")
        seen_blind.add(blind_id)
        if case["observed_route"] not in ALLOWED_ROUTES:
            raise TriggerEvalError(f"{case_id}: invalid route")
        if case["observed_route"] != _expected_route(case_id):
            raise TriggerEvalError(f"{case_id}: routing verdict mismatch")
        if case["observed_mode"] != EXPECTED_CASES[case_id][1]:
            raise TriggerEvalError(f"{case_id}: mode mismatch")
        raw_response = case["raw_response"]
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise TriggerEvalError(f"{case_id}: raw response is required")
        for forbidden in filter(None, prompts[case_id]["must_not_have"].split("|")):
            if forbidden.casefold() in raw_response.casefold():
                raise TriggerEvalError(f"{case_id}: literal forbidden phrase present: {forbidden}")
        case_results[case_id] = case
    if set(case_results) != set(EXPECTED_CASES):
        raise TriggerEvalError("executor case set mismatch")

    judges = result["judges"]
    if not isinstance(judges, list) or len(judges) != 2:
        raise TriggerEvalError("exactly two independent judges are required")
    expected_current_judges: list[dict[str, Any]] = []
    for letter in ("a", "b"):
        raw_judge_path = (
            skill_path.parent
            / "evals"
            / "current_binding"
            / f"judge_{letter}.json"
        )
        try:
            raw_judge = json.loads(raw_judge_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TriggerEvalError(
                f"cannot parse current judge {letter} evidence"
            ) from exc
        current_case_verdicts = []
        for verdict in raw_judge["trigger"]["case_verdicts"]:
            current_case_verdicts.append(
                {
                    **verdict,
                    "criterion_evidence": {
                        row["criterion"]: row["evidence_quote"]
                        for row in verdict["criterion_evidence"]
                    },
                }
            )
        expected_current_judges.append(
            {
                "judge_id": f"judge-{letter}",
                "history_fork": "none",
                "executor_role_separation": True,
                "case_verdicts": current_case_verdicts,
                "oracle_verdicts": raw_judge["trigger"]["oracle_verdicts"],
            }
        )
    if judges != expected_current_judges:
        raise TriggerEvalError("embedded judges drift from current raw evidence")
    judge_ids: set[str] = set()
    for judge_index, value in enumerate(judges):
        judge = _exact_keys(
            value,
            {
                "judge_id",
                "history_fork",
                "executor_role_separation",
                "case_verdicts",
                "oracle_verdicts",
            },
            f"judges[{judge_index}]",
        )
        judge_id = judge["judge_id"]
        if judge_id not in {"judge-a", "judge-b"} or judge_id in judge_ids:
            raise TriggerEvalError("judges must be unique current judge-a/judge-b")
        judge_ids.add(judge_id)
        if judge["history_fork"] != "none" or judge["executor_role_separation"] is not True:
            raise TriggerEvalError(f"{judge_id}: independence metadata mismatch")

        verdicts = judge["case_verdicts"]
        if not isinstance(verdicts, list) or len(verdicts) != 13:
            raise TriggerEvalError(f"{judge_id}: exactly 13 case verdicts required")
        seen_cases: set[str] = set()
        for verdict_index, value in enumerate(verdicts):
            verdict = _exact_keys(
                value,
                {
                    "id",
                    "routing",
                    "required_content",
                    "forbidden_content",
                    "overall",
                    "criterion_evidence",
                    "rationale",
                },
                f"{judge_id}.case_verdicts[{verdict_index}]",
            )
            case_id = verdict["id"]
            if case_id not in case_results or case_id in seen_cases:
                raise TriggerEvalError(f"{judge_id}: unknown/duplicate case verdict")
            seen_cases.add(case_id)
            if any(verdict[key] != PASS for key in (
                "routing", "required_content", "forbidden_content", "overall"
            )):
                raise TriggerEvalError(f"{judge_id}:{case_id}: non-PASS case verdict")
            if not isinstance(verdict["rationale"], str) or not verdict["rationale"].strip():
                raise TriggerEvalError(f"{judge_id}:{case_id}: rationale required")
            expected_criteria = set(filter(None, prompts[case_id]["must_have"].split("|")))
            evidence = verdict["criterion_evidence"]
            if not isinstance(evidence, dict) or set(evidence) != expected_criteria:
                raise TriggerEvalError(f"{judge_id}:{case_id}: criterion evidence set mismatch")
            for criterion, quote in evidence.items():
                _require_quote(
                    case_results[case_id]["raw_response"],
                    quote,
                    f"{judge_id}:{case_id}:{criterion}",
                )
        if seen_cases != set(EXPECTED_CASES):
            raise TriggerEvalError(f"{judge_id}: case verdict set mismatch")

        oracle_verdicts = judge["oracle_verdicts"]
        if not isinstance(oracle_verdicts, list) or len(oracle_verdicts) != 18:
            raise TriggerEvalError(f"{judge_id}: exactly 18 oracle verdicts required")
        seen_oracles: set[str] = set()
        for oracle_index, value in enumerate(oracle_verdicts):
            verdict = _exact_keys(
                value,
                {"oracle_id", "verdict", "evidence_quote", "rationale"},
                f"{judge_id}.oracle_verdicts[{oracle_index}]",
            )
            oracle_id = verdict["oracle_id"]
            if oracle_id not in oracles or oracle_id in seen_oracles:
                raise TriggerEvalError(f"{judge_id}: unknown/duplicate oracle verdict")
            seen_oracles.add(oracle_id)
            if verdict["verdict"] != PASS:
                raise TriggerEvalError(f"{judge_id}:{oracle_id}: non-PASS oracle verdict")
            if not isinstance(verdict["rationale"], str) or not verdict["rationale"].strip():
                raise TriggerEvalError(f"{judge_id}:{oracle_id}: rationale required")
            linked_case = oracles[oracle_id]["case_id"]
            _require_quote(
                case_results[linked_case]["raw_response"],
                verdict["evidence_quote"],
                f"{judge_id}:{oracle_id}",
            )
        if seen_oracles != set(oracles):
            raise TriggerEvalError(f"{judge_id}: oracle verdict set mismatch")

    summary = _exact_keys(
        result["summary"],
        {
            "case_total",
            "routing_pass",
            "case_pass",
            "oracle_total",
            "oracle_pass",
            "judge_count",
            "guaranteed_alpha_claims",
        },
        "summary",
    )
    expected_summary = {
        "case_total": 13,
        "routing_pass": 13,
        "case_pass": 13,
        "oracle_total": 18,
        "oracle_pass": 18,
        "judge_count": 2,
        "guaranteed_alpha_claims": 0,
    }
    if summary != expected_summary:
        raise TriggerEvalError("summary mismatch")
    serialized = json.dumps(result, ensure_ascii=False)
    posix_user_markers = ("/" + "Users" + "/", "/" + "home" + "/")
    windows_user_pattern = re.compile(
        r"[A-Za-z]:" + re.escape("\\") + "Users" + re.escape("\\")
    )
    if any(marker in serialized for marker in posix_user_markers) or windows_user_pattern.search(
        serialized
    ):
        raise TriggerEvalError("results contain a local user path")
    return expected_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--oracles", type=Path, default=DEFAULT_ORACLES)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    args = parser.parse_args()
    try:
        summary = validate_results(args.results, args.prompts, args.oracles, args.skill)
    except TriggerEvalError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    print(
        "PASS: trigger eval; "
        f"routing={summary['routing_pass']}/{summary['case_total']}; "
        f"cases={summary['case_pass']}/{summary['case_total']}; "
        f"CAP oracles={summary['oracle_pass']}/{summary['oracle_total']}; "
        f"judges={summary['judge_count']}"
    )


if __name__ == "__main__":
    main()
