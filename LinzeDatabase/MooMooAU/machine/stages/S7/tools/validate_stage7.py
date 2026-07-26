#!/usr/bin/env python3
"""Read-only cumulative Stage 7 implementation and protected-oracle validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
STAGE6_TOOLS = PROJECT_ROOT / "machine/stages/S6/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
STAGE7_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage7-ci.yml"
BETA_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-beta.yml"
M3_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-m3.yml"
BLUE_GREEN_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-blue-green.yml"
PATCH_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-patch-lifecycle.yml"
PRODUCTION_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-production.yml"
BASELINE_COMMIT = "be8e196b03dcc475ed6261fbe20593b08bd26bcf"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
GOVERNANCE_PIN = "ebc6c2e4884edc959118cfc56d0e18a86c49460f"  # pragma: allowlist secret
FAILED_BETA_RECEIPT_SHA256 = "1f78a94d3e4019d89dda7aae9ddfc949e280eece03a0ce28829beba7094922c0"
FAILED_T0704_ATTEMPT_LEDGER_SHA256 = (
    "8f541dc5d5aba89c20539c6f28aeab508a93b8e5c800f5b2a3bb01345cea6ee5"  # pragma: allowlist secret
)
FAILED_T0704_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "bf3e2ee4cb6f8d0e1ccb67423dfa615d33b3089f9bfc730f34cd944ee14f8e0c"  # pragma: allowlist secret
)
FAILED_T0705_ATTEMPT_LEDGER_SHA256 = (
    "7249e7c1190b4a4263aa1e72e8232c697ada4ba65afd5280a3ed5c07cfa0b928"  # pragma: allowlist secret
)
FAILED_T0705_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "89779fecb7090722c616ae056318eea3119429f8c5e011830393d9f39aba47eb"  # pragma: allowlist secret
)
FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SHA256 = (
    "497b01fecc89be10f2e80f356cabdd3aecdecee4146b79d4b085655e6d722e7b"  # pragma: allowlist secret
)
FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "71779086ba7ee3210e77894f63b987a5ab9feaac5a56ee422062e49db2f92df9"  # pragma: allowlist secret
)
FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SHA256 = (
    "ed311f5a932c5e0976c70f43df0ebe576a75436981e95ccca413c33eb42a353d"  # pragma: allowlist secret
)
FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "85a8f4448fb1a1f47e01a880685694ddabccc222ee6a554ac65bbc88fbd33cea"  # pragma: allowlist secret
)
FAILED_T0705_POST_PROCESSED_ATTEMPT_LEDGER_SHA256 = (
    "b8dd28f8fba8c05a847433e5a3e44a467ea25003a388c8bbd152d5d019e2383f"  # pragma: allowlist secret
)
FAILED_T0705_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "2cd4af584ca38f45f8760309f5d38c4b7b076d47720aa400255e4875bce21c63"  # pragma: allowlist secret
)
FAILED_T0705_PROCESSED_PLAN_ATTEMPT_LEDGER_SHA256 = (
    "9cebe7c23adf11274c645c5b2d87da7d4b435602b6c8bba2b7b6b24b130546dc"  # pragma: allowlist secret
)
FAILED_T0705_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "1964a88737eaaadbbfc5cc22419730cd59c09d86f187132f21cf2c0b79c157a0"  # pragma: allowlist secret
)
FAILED_T0705_FIRST_IMPORT_ATTEMPT_LEDGER_SHA256 = (
    "9c5b5bedade30d511d0503f0b623a57ff59bca14bd7cf48409f8a6c459879b31"  # pragma: allowlist secret
)
FAILED_T0705_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "d6deff1bc93e92c78e1b3c15771a679bcc5fd6b2a59da216fbbf08a4244be4b3"  # pragma: allowlist secret
)
FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SHA256 = (
    "18d2e1cc29182dea7a94b25d25072d15cbc0ac91b091685faba69bcaa7532066"  # pragma: allowlist secret
)
FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "801e1e44299115958bc838cc6c8e04c45f482a5ee50567345f22ad2295db83d2"  # pragma: allowlist secret
)
FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SHA256 = (
    "092f5a580d905213066a99221f51b9065748dceeb82e48e20b54ed42e82d444f"  # pragma: allowlist secret
)
FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "2945fb030f4154da1d18142f5b239a5b824126010d8dbcc9ae92b7a973f089ab"  # pragma: allowlist secret
)
FAILED_T0705_CANONICAL_BLOB_ATTEMPT_LEDGER_SHA256 = (
    "264cfa33f6e3662485d4abc2b3b69d70ba31fdba4d76b49102c16d7dfaa7e4bd"  # pragma: allowlist secret
)
FAILED_T0705_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "a5449bf6ca1733b5cd01a0cc7873b708bd95bf4dee37ac79550f364c879fd5a8"  # pragma: allowlist secret
)
FAILED_T0705_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SHA256 = (
    "f6e5707059df47549cbb92e58157578c872f53d23e2770b83b03ba50d100173d"  # pragma: allowlist secret
)
FAILED_T0705_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "e6f7c63108ca228475e38c5a3b75223861ef45ba419a11738edfc6505b373514"  # pragma: allowlist secret
)
FAILED_T0705_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SHA256 = (
    "04a1f579c29e384c7db16545f5babf4b5feee63333af53f2fc560ba5728fdbab"  # pragma: allowlist secret
)
FAILED_T0705_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "b927dcae93cb20de48cf2cf53fc50906492683eaf3f51021cca79e1f5b31de24"  # pragma: allowlist secret
)
FAILED_T0705_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SHA256 = (
    "c4b746090050897b8548a0ec07ed162e807477ed5f3e9047c8c185fb083e45eb"  # pragma: allowlist secret
)
FAILED_T0705_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "a3587e687e74aad18fa4d2259484cde1759ed7825d84de10af94f37fbe594654"  # pragma: allowlist secret
)
FAILED_T0705_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SHA256 = (
    "4881b45d1013bc68a8b2f4549b88bc42eb7d9c7d3e2897d76270bb6c83c1efe9"  # pragma: allowlist secret
)
FAILED_T0705_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "bba6e330cee067128c6c14b4dd7333900e1e175beede90fbc93ce390a897782a"  # pragma: allowlist secret
)
FAILED_T0705_RAW_RECOVERY_ATTEMPT_LEDGER_SHA256 = (
    "69dfae428aacfa3f20748472027dc89cf8d625c57bcbeb8cdb7f9315b743fd65"  # pragma: allowlist secret
)
FAILED_T0705_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "b0457d69d11d6be3cff0edd5b3a4db4ff7a5a7c8306b88670111f5f3d801ad51"  # pragma: allowlist secret
)
FAILED_T0705_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SHA256 = (
    "6a05af65bc8f0045bb5c7d4ce511ff643c07fe1b6a1a6c8190962cd4c5ca598b"  # pragma: allowlist secret
)
FAILED_T0705_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_SHA256 = (
    "5cee0e8e3dc695251f487f482457ea91cab5b240eed7be81891b0d23bf4cb4e8"  # pragma: allowlist secret
)
PROTECTED_BETA_ATTEMPT_LEDGER = Path("machine/stages/S7/reviews/t0702/attempt-ledger.json")
PROTECTED_BETA_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-beta-attempt-ledger-v2.schema.json"
)
PROTECTED_M3_ATTEMPT_LEDGER = Path("machine/stages/S7/reviews/t0703/attempt-ledger.json")
PROTECTED_M3_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-m3-attempt-ledger-v1.schema.json"
)
PROTECTED_M3_RECEIPT = Path("machine/stages/S7/reviews/t0703/execution-receipt.json")
PROTECTED_M3_RECEIPT_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-m3-execution-receipt-v1.schema.json"
)
PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER = Path("machine/stages/S7/reviews/t0704/attempt-ledger.json")
PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-blue-green-attempt-ledger-v1.schema.json"
)
PROTECTED_BLUE_GREEN_RECEIPT = Path("machine/stages/S7/reviews/t0704/execution-receipt.json")
PROTECTED_BLUE_GREEN_RECEIPT_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-blue-green-execution-receipt-v1.schema.json"
)
PROTECTED_GA_ATTEMPT_LEDGER = Path("machine/stages/S7/reviews/t0705/attempt-ledger.json")
PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_REPAIR_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/repair-attempt-ledger.json"
)
PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-repair-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/label-replay-attempt-ledger.json"
)
PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-label-replay-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/post-processed-attempt-ledger.json"
)
PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-post-processed-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/processed-plan-attempt-ledger.json"
)
PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-processed-plan-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/first-import-attempt-ledger.json"
)
PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-first-import-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/pointer-fetch-attempt-ledger.json"
)
PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-pointer-fetch-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/pointer-blob-attempt-ledger.json"
)
PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-pointer-blob-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/canonical-blob-attempt-ledger.json"
)
PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-canonical-blob-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/canonical-blob-preflight-attempt-ledger.json"
)
PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-candidate-preflight-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/authority-variable-scope-attempt-ledger.json"
)
PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-authority-context-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/schedule-planning-clock-attempt-ledger.json"
)
PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-schedule-planning-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/authentication-clock-coupling-attempt-ledger.json"
)
PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-authentication-clock-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/raw-recovery-representation-attempt-ledger.json"
)
PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/"
    "protected-ga-raw-recovery-representation-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER = Path(
    "machine/stages/S7/reviews/t0705/trash-confirmation-attempt-ledger.json"
)
PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA = Path(
    "machine/stages/S7/schemas/protected-ga-trash-confirmation-attempt-ledger-v1.schema.json"
)
STAGE7_TASKS = [f"T070{index}" for index in range(1, 9)]
STAGE7_ACCEPTANCES = [f"S7AC-00{index}" for index in range(1, 9)]
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")
EVIDENCE_PATH = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:json|md|py|ya?ml)")
IGNORED_PARTS = {
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}

for import_path in (STAGE6_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_production_composition import validate as validate_composition  # noqa: E402
from validate_publication import scan_tree  # noqa: E402
from validate_stage6 import evaluate_stage6  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_auth,
    validate_governance_dependency_workflow,
    validate_workflow_expression_contexts,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(check_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and not (set(path.parts) & IGNORED_PARTS)
    ]
    paths.extend(
        path
        for path in (
            STAGE7_WORKFLOW,
            BETA_WORKFLOW,
            M3_WORKFLOW,
            BLUE_GREEN_WORKFLOW,
            PATCH_WORKFLOW,
            PRODUCTION_WORKFLOW,
        )
        if path.is_file()
    )
    for path in sorted(set(paths), key=str):
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else path.relative_to(REPOSITORY_ROOT).as_posix()
        )
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _validate_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S7"}
    dependencies = {
        "T0701": ["T0608"],
        "T0702": ["T0701"],
        "T0703": ["T0702"],
        "T0704": ["T0703"],
        "T0705": ["T0704"],
        "T0706": ["T0705"],
        "T0707": ["T0706"],
        "T0708": ["T0707"],
    }
    if set(graph_tasks) != set(STAGE7_TASKS) or any(
        graph_tasks[task_id].get("dependencies") != expected
        for task_id, expected in dependencies.items()
    ):
        errors.append("Stage 7 dependency chain drifts from the frozen task graph")

    local = _load(root / "machine/stages/S7/contracts/stage7_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE7_ACCEPTANCES:
        errors.append("Stage 7 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE7_TASKS:
        errors.append("Stage 7 acceptance-to-task mapping must be one-to-one")
    if (
        local.get("overall_status")
        != "T0705_THIRTEEN_FAILED_HEADS_FROZEN_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED_PENDING"
        or local.get("final_acceptances_passed") != 0
        or "Local implementation preflight" not in local.get("final_acceptance_policy", "")
        or "No fixed calendar observation period or wall-clock 04:30 wait applies"
        not in local.get("final_acceptance_policy", "")
    ):
        errors.append("Stage 7 acceptance policy overstates current completion")
    local_text = json.dumps(local, sort_keys=True)
    if any(
        token in local_text
        for token in (
            "seven M3 Canary days",
            "fourteen Blue-Green days",
            "observation >=7 days",
            "observation >=14 days",
        )
    ):
        errors.append("Stage 7 acceptance policy retains a calendar wait")
    required_fields = {
        "title",
        "environment",
        "input",
        "oracle",
        "threshold",
        "evidence_required",
        "verification",
        "failure_action",
    }
    for item in items:
        task_id = item.get("task_id")
        if (
            task_id not in graph_tasks
            or item.get("linked_final_acceptance_ids") != graph_tasks[task_id]["acceptance_ids"]
        ):
            errors.append("Stage 7 final acceptance links drift from the frozen graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 7 acceptance contract is incomplete")

    run = _load(root / "machine/stages/S7/contracts/run_contract.json")
    prohibitions = run.get("prohibitions", {})
    authorization = run.get("authorization", {})
    effect_budget = run.get("authorized_effect_budget", {})
    if (
        run.get("schema_version") != "moomooau.run-contract.v1"
        or run.get("stage_id") != "S7"
        or run.get("task_id") != "T0705"
        or run.get("baseline_commit")
        != "4b7442bb635ea1e7cf5a814c3c56047aa288d594"  # pragma: allowlist secret
        or run.get("baseline_manifest_sha256")
        != "dbe7e3867c92e5d960bfea2d7e2b9e9e43680751c16fbfb9324e0450a6b1a141"  # pragma: allowlist secret  # noqa: E501
        or not isinstance(prohibitions, dict)
        or any(value != 0 for value in prohibitions.values())
        or authorization.get("purpose")
        != "T0705_PROTECTED_GA_TRASH_CONFIRMATION_RECOVERY_AND_ENABLEMENT_ONLY"
        or authorization.get("original_run_contract_sha256")
        != "1c94dfdce8b5809718e2772d422bb6db773f8b9899ad9e719b0ffda11d0053b9"  # pragma: allowlist secret  # noqa: E501
        or authorization.get("prior_run_contract_sha256")
        != "004f648b027ec68390a864988a537e7064de9224bab738b429c1c093b0ca4722"  # pragma: allowlist secret  # noqa: E501
        or authorization.get("failed_attempt_ledgers_required") != 9
        or authorization.get("first_failed_attempt_ledger_sha256")
        != FAILED_T0705_ATTEMPT_LEDGER_SHA256
        or authorization.get("first_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("second_failed_attempt_ledger_sha256")
        != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SHA256
        or authorization.get("second_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("third_failed_attempt_ledger_sha256")
        != FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SHA256
        or authorization.get("third_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("fourth_failed_attempt_ledger_sha256")
        != FAILED_T0705_POST_PROCESSED_ATTEMPT_LEDGER_SHA256
        or authorization.get("fourth_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("fifth_failed_attempt_ledger_sha256")
        != FAILED_T0705_PROCESSED_PLAN_ATTEMPT_LEDGER_SHA256
        or authorization.get("fifth_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("sixth_failed_attempt_ledger_sha256")
        != FAILED_T0705_FIRST_IMPORT_ATTEMPT_LEDGER_SHA256
        or authorization.get("sixth_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("seventh_failed_attempt_ledger_sha256")
        != FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SHA256
        or authorization.get("seventh_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("eighth_failed_attempt_ledger_sha256")
        != FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SHA256
        or authorization.get("eighth_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("ninth_failed_attempt_ledger_sha256")
        != FAILED_T0705_CANONICAL_BLOB_ATTEMPT_LEDGER_SHA256
        or authorization.get("ninth_failed_attempt_ledger_schema_sha256")
        != FAILED_T0705_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("candidate_preflight_attempt_ledger_sha256")
        != FAILED_T0705_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SHA256
        or authorization.get("candidate_preflight_attempt_ledger_schema_sha256")
        != FAILED_T0705_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("authority_context_attempt_ledger_sha256")
        != FAILED_T0705_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SHA256
        or authorization.get("authority_context_attempt_ledger_schema_sha256")
        != FAILED_T0705_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("schedule_planning_attempt_ledger_sha256")
        != FAILED_T0705_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SHA256
        or authorization.get("schedule_planning_attempt_ledger_schema_sha256")
        != FAILED_T0705_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("authentication_clock_attempt_ledger_sha256")
        != FAILED_T0705_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SHA256
        or authorization.get("authentication_clock_attempt_ledger_schema_sha256")
        != FAILED_T0705_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("raw_recovery_attempt_ledger_sha256")
        != FAILED_T0705_RAW_RECOVERY_ATTEMPT_LEDGER_SHA256
        or authorization.get("raw_recovery_attempt_ledger_schema_sha256")
        != FAILED_T0705_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("trash_confirmation_attempt_ledger_sha256")
        != FAILED_T0705_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SHA256
        or authorization.get("trash_confirmation_attempt_ledger_schema_sha256")
        != FAILED_T0705_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_SHA256
        or authorization.get("failed_workflow_head_shas")
        != [
            "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f",  # pragma: allowlist secret
            "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0",  # pragma: allowlist secret
            "cc7c8af9a40122a61ee2549fb365df813cbd4f16",  # pragma: allowlist secret
            "4c207ad539754166fae6642ff4e6850438d3e2fc",  # pragma: allowlist secret
            "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4",  # pragma: allowlist secret
            "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7",  # pragma: allowlist secret
            "2133673b335a384657c8668b62a1c13055c212cd",  # pragma: allowlist secret
            "8b6faaf9059661edc3153352b8787ddbc4f733f3",  # pragma: allowlist secret
            "6f82e738611e0d2eeeadd2507f738c9e269c91e0",  # pragma: allowlist secret
        ]
        or authorization.get("failed_candidate_preflight_head_shas")
        != [
            "26949ab5031a21b0c515c282c9ef06ff9417e058",  # pragma: allowlist secret
        ]
        or authorization.get("failed_authority_context_head_shas")
        != [
            "9c79b92bcdf8b027727963dfe52bd183a170954c",  # pragma: allowlist secret
        ]
        or authorization.get("failed_schedule_planning_head_shas")
        != [
            "27886f54a30a12ca7992a908e97340d1d8234430",  # pragma: allowlist secret
        ]
        or authorization.get("failed_authentication_clock_head_shas")
        != [
            "c2c057b449fe1cbbd470867c274833242e3f139d",  # pragma: allowlist secret
        ]
        or authorization.get("failed_raw_recovery_head_shas")
        != [
            "0d0b6afd6a0cde606230a3df7378bdd90586de5d",  # pragma: allowlist secret
        ]
        or authorization.get("failed_trash_confirmation_head_shas")
        != [
            "4b7442bb635ea1e7cf5a814c3c56047aa288d594",  # pragma: allowlist secret
        ]
        or authorization.get("failed_head_rerun_allowed") is not False
        or authorization.get("failed_head_redispatch_allowed") is not False
        or authorization.get("t0704_receipt_required") is not True
        or authorization.get("t0704_receipt_sha256")
        != "67a5b0f2860fac8b97d459d79f1ad87172f6ce4e45570bb1a1f4f8dc0731fbf7"  # pragma: allowlist secret  # noqa: E501
        or authorization.get("t0705_authorized") is not True
        or authorization.get("t0706_authorized") is not False
        or authorization.get("controlled_main_delivery_total_limit") != 17
        or authorization.get("controlled_main_deliveries_consumed") != 15
        or authorization.get("controlled_main_deliveries_remaining") != 2
        or authorization.get("ga_rehearsal_dispatches_consumed") != 13
        or authorization.get("ga_candidate_preflight_dispatches_consumed") != 5
        or authorization.get("ga_authority_context_scope_failures_consumed") != 1
        or authorization.get("ga_schedule_planning_clock_failures_consumed") != 1
        or authorization.get("ga_authentication_clock_coupling_failures_consumed") != 1
        or authorization.get("ga_raw_recovery_representation_failures_consumed") != 1
        or authorization.get("ga_trash_confirmation_failures_consumed") != 1
        or authorization.get("ga_metadata_quarantine_repair_dispatches_consumed") != 1
        or authorization.get("ga_label_replay_repair_dispatches_consumed") != 1
        or authorization.get("ga_phase_diagnostic_dispatches_consumed") != 1
        or authorization.get("ga_processed_plan_diagnostic_dispatches_consumed") != 1
        or authorization.get("ga_first_import_diagnostic_dispatches_consumed") != 1
        or authorization.get("ga_exact_pointer_blob_repair_dispatches_consumed") != 1
        or authorization.get("ga_app_repository_scope_activation_dispatches_consumed") != 1
        or authorization.get("ga_canonical_git_blob_recovery_dispatch_limit") != 1
        or authorization.get("ga_deterministic_clock_recovery_dispatch_limit") != 1
        or authorization.get("ga_security_clock_decoupling_recovery_dispatch_limit") != 1
        or authorization.get("ga_raw_canonical_git_blob_recovery_dispatch_limit") != 1
        or authorization.get("ga_trash_confirmation_recovery_dispatch_limit") != 1
        or authorization.get("ga_first_import_diagnostic_rerun_limit") != 0
        or authorization.get("security_clock_mode") != "LIVE_UTC"
        or authorization.get("rehearsal_schedule_clock_mode")
        != "DETERMINISTIC_HISTORICAL_REPLAY_FIXTURE"
        or authorization.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T19:00:00Z"
        or authorization.get("known_data_effect_upper_bound_utc") != "2026-07-26T17:20:17Z"
        or authorization.get("manual_environment_reviewers_required") is not False
        or authorization.get("fixed_calendar_wait_days") != 0
        or authorization.get("final_publication_authorized") is not False
        or effect_budget.get("controlled_main_deliveries_total_maximum") != 17
        or effect_budget.get("controlled_main_deliveries_remaining_maximum") != 2
        or effect_budget.get("protected_environment_secret_names_maximum") != 8
        or effect_budget.get("private_data_repository_creations_maximum") != 0
        or effect_budget.get("github_app_creations_maximum") != 0
        or effect_budget.get("protected_ga_rehearsal_dispatches_total_maximum") != 14
        or effect_budget.get("protected_ga_rehearsal_dispatches_consumed") != 13
        or effect_budget.get("protected_ga_candidate_preflight_dispatches_total_maximum") != 6
        or effect_budget.get("protected_ga_candidate_preflight_dispatches_consumed") != 5
        or effect_budget.get("protected_ga_authority_context_scope_failures_maximum") != 1
        or effect_budget.get("protected_ga_authority_context_scope_failures_consumed") != 1
        or effect_budget.get("protected_ga_schedule_planning_clock_failures_maximum") != 1
        or effect_budget.get("protected_ga_schedule_planning_clock_failures_consumed") != 1
        or effect_budget.get("protected_ga_authentication_clock_coupling_failures_maximum") != 1
        or effect_budget.get("protected_ga_authentication_clock_coupling_failures_consumed") != 1
        or effect_budget.get("protected_ga_raw_recovery_representation_failures_maximum") != 1
        or effect_budget.get("protected_ga_raw_recovery_representation_failures_consumed") != 1
        or effect_budget.get("protected_ga_trash_confirmation_failures_maximum") != 1
        or effect_budget.get("protected_ga_trash_confirmation_failures_consumed") != 1
        or effect_budget.get("protected_ga_metadata_quarantine_repair_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_label_replay_repair_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_phase_diagnostic_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_processed_plan_diagnostic_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_first_import_diagnostic_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_first_import_diagnostic_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_exact_pointer_blob_repair_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_exact_pointer_blob_repair_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_app_repository_scope_activation_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_app_repository_scope_activation_dispatches_consumed")
        != 1
        or effect_budget.get("protected_ga_canonical_git_blob_recovery_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_deterministic_clock_recovery_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_deterministic_clock_recovery_dispatches_consumed") != 1
        or effect_budget.get("protected_ga_security_clock_decoupling_recovery_dispatches_maximum")
        != 1
        or effect_budget.get("protected_ga_raw_canonical_git_blob_recovery_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_trash_confirmation_recovery_dispatches_maximum") != 1
        or effect_budget.get("protected_ga_rehearsal_reruns_maximum") != 0
        or effect_budget.get("failed_head_reruns_maximum") != 0
        or effect_budget.get("failed_head_redispatches_maximum") != 0
        or effect_budget.get("protected_ga_first_import_diagnostic_pipeline_runs_maximum") != 1
        or effect_budget.get("protected_ga_exact_pointer_blob_repair_pipeline_runs_maximum") != 1
        or effect_budget.get("protected_ga_app_repository_scope_activation_pipeline_runs_maximum")
        != 1
        or effect_budget.get("protected_ga_canonical_git_blob_recovery_pipeline_runs_maximum") != 1
        or effect_budget.get("protected_ga_deterministic_clock_recovery_pipeline_runs_maximum") != 1
        or effect_budget.get(
            "protected_ga_security_clock_decoupling_recovery_pipeline_runs_maximum"
        )
        != 1
        or effect_budget.get("protected_ga_raw_canonical_git_blob_recovery_pipeline_runs_maximum")
        != 1
        or effect_budget.get("protected_ga_trash_confirmation_recovery_pipeline_runs_maximum") != 1
        or effect_budget.get("platform_schedule_events_during_rehearsal_maximum") != 0
        or effect_budget.get("gmail_exact_message_trash_mutations_maximum") != 1
        or effect_budget.get("timeline_snapshot_commit_attempts_maximum") != 1
        or effect_budget.get("timeline_state_commits_maximum") != 1
        or effect_budget.get("timeline_publish_attempts_maximum") != 1
        or effect_budget.get("release_asset_uploads_maximum") != 1
        or effect_budget.get("maximum_live_timeline_assets") != 1
        or effect_budget.get("gmail_checkpoint_mutations_maximum") != 1
        or effect_budget.get("production_schedule_enablement_mutations_maximum") != 1
        or effect_budget.get("t0706_runs_maximum") != 0
        or effect_budget.get("recovery_drill_runs_maximum") != 0
        or effect_budget.get("patch_lifecycle_protected_runs_maximum") != 0
        or not run.get("protected_oracles")
        or not any(
            "more than one new protected T0705 Trash-confirmation recovery dispatch" in item
            for item in run.get("non_goals", [])
        )
        or not run.get("rollback")
        or not run.get("stop_conditions")
    ):
        errors.append("Stage 7 T0705 protected GA Run Contract is incomplete")
    blue_green_ledger_path = root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER
    blue_green_schema_path = root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA
    blue_green_ledger = _load(blue_green_ledger_path)
    blue_green_schema = _load(blue_green_schema_path)
    blue_green_attempts = blue_green_ledger.get("attempts", [])
    blue_green_attempt = (
        blue_green_attempts[0]
        if isinstance(blue_green_attempts, list) and len(blue_green_attempts) == 1
        else {}
    )
    if (
        list(
            Draft202012Validator(
                blue_green_schema,
                format_checker=FormatChecker(),
            ).iter_errors(blue_green_ledger)
        )
        or _sha256(blue_green_ledger_path) != FAILED_T0704_ATTEMPT_LEDGER_SHA256
        or _sha256(blue_green_schema_path) != FAILED_T0704_ATTEMPT_LEDGER_SCHEMA_SHA256
        or blue_green_attempt.get("delivery", {}).get("merge_commit_sha")
        != "b3ff184bd9a7f0e66a7fde6cd6656f11dd982177"  # pragma: allowlist secret
        or blue_green_attempt.get("workflow", {}).get("run_attempt") != 1
        or blue_green_attempt.get("workflow", {}).get("reruns") != 0
        or blue_green_attempt.get("effects", {}).get("private_repository_new_commits") != 5
        or blue_green_attempt.get("effects", {}).get("processed_current_path_and_blob_identity")
        is not True
        or blue_green_attempt.get("effects", {}).get("live_timeline_assets_after_dispatch") != 0
        or blue_green_attempt.get("diagnosis", {}).get("high_confidence_defect")
        != "GITHUB_RELEASE_ASSET_302_RECOVERY_NOT_SUPPORTED"
        or blue_green_ledger.get("completion_policy", {}).get("same_head_rerun_allowed")
        is not False
        or blue_green_ledger.get("completion_policy", {}).get("failed_head_redispatch_allowed")
        is not False
        or blue_green_ledger.get("completion_policy", {}).get("t0705_authorized") is not False
    ):
        errors.append("T0704 failed attempt ledger is not exact or frozen")

    repair = _load(root / "machine/stages/S7/contracts/t0702_repair_run_contract.json")
    repair_authority = repair.get("authority", {})
    repair_budget = repair.get("authorized_effect_budget", {})
    failed_receipt = root / "machine/stages/S7/reviews/t0702/execution-receipt-failed-20260723.json"
    if (
        repair.get("schema_version") != "moomooau.run-contract.v1"
        or repair.get("stage_id") != "S7"
        or repair.get("task_id") != "T0702"
        or repair.get("failed_attempt_receipt")
        != "machine/stages/S7/reviews/t0702/execution-receipt-failed-20260723.json"
        or repair.get("failed_attempt_receipt_sha256") != FAILED_BETA_RECEIPT_SHA256
        or not failed_receipt.is_file()
        or _sha256(failed_receipt) != FAILED_BETA_RECEIPT_SHA256
        or repair_authority.get("basis") != "OWNER_PERSISTENT_GOAL_LOCAL_STAGE7_REPAIR"
        or repair_authority.get("local_code_changes_allowed") is not True
        or any(
            repair_authority.get(key) is not False
            for key in (
                "main_delivery_allowed",
                "workflow_dispatch_allowed",
                "protected_secret_reads_allowed",
                "gmail_calls_allowed",
                "private_repository_calls_allowed",
                "m3_allowed",
                "final_publication_allowed",
            )
        )
        or not isinstance(repair_budget, dict)
        or not repair_budget
        or any(value != 0 for value in repair_budget.values())
        or not repair.get("acceptance")
        or not repair.get("stop_conditions")
        or (
            "a second branch push, pull request, main delivery, workflow dispatch or rerun"
            not in repair.get("non_goals", [])
        )
    ):
        errors.append(
            "T0702 diagnostic repair run contract is incomplete or grants remote authority"
        )

    completion = _load(root / "machine/stages/S7/contracts/stage7_completion_run_contract.json")
    completion_authority = completion.get("authority", {})
    completion_policy = completion.get("execution_policy", {})
    if (
        completion.get("schema_version") != "moomooau.run-contract.v1"
        or completion.get("stage_id") != "S7"
        or completion_authority.get("basis")
        != "OWNER_EXPLICIT_STAGE7_COMPLETION_NO_ARTIFICIAL_BLOCKS"
        or any(
            completion_authority.get(key) is not True
            for key in (
                "controlled_main_delivery_allowed",
                "serial_first_attempt_dispatch_allowed",
                "protected_secret_reads_in_github_actions_allowed",
                "gmail_calls_in_protected_runtime_allowed",
                "private_repository_calls_in_protected_runtime_allowed",
                "m3_allowed_after_t0702_pass",
                "blue_green_allowed_after_m3_pass",
                "ga_allowed_after_blue_green_pass",
                "recovery_drill_allowed_after_ga_pass",
                "final_publication_allowed_only_after_full_acceptance_and_review",
            )
        )
        or completion_authority.get("manual_environment_approval_required") is not False
        or completion_policy.get("stage_scope") != "S7_ONLY"
        or completion_policy.get("dispatch_sequence") != "SERIAL_FIRST_ATTEMPT_PER_EXACT_MAIN_SHA"
        or completion_policy.get("workflow_rerun_allowed") is not False
        or completion_policy.get("fixed_calendar_wait_days") != 0
        or completion_policy.get("beta_verified_message_budget_per_attempt") != 1
        or completion_policy.get("beta_gmail_mutation_budget") != 0
        or completion_policy.get("m3_source_mutation_budget_per_run") != 1
        or completion_policy.get("maximum_concurrent_writers") != 1
        or completion_policy.get("remote_recovery_required_before_source_mutation") is not True
        or completion_policy.get("single_live_timeline_required") is not True
        or not completion.get("scope")
        or not completion.get("non_goals")
        or not completion.get("validation")
        or not completion.get("stop_conditions")
    ):
        errors.append("Stage 7 completion authority is missing or violates bounded safety")

    status = _load(root / "machine/stages/S7/contracts/task_status.json")
    task_items = status.get("tasks", [])
    if (
        [item.get("id") for item in task_items] != STAGE7_TASKS
        or any(item.get("status") == "completed" for item in task_items)
        or status.get("stage_status")
        != "T0705_THIRTEEN_FAILED_HEADS_FROZEN_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED_PENDING"
        or status.get("scoped_preflight_task_oracle_file_count") != 8
        or status.get("implementation_completion_status") != "LOCAL_MECHANISMS_READY"
        or status.get("completed_task_count") != 0
        or status.get("protected_oracles_executed") != 5
        or status.get("protected_oracles_passed") != 4
        or status.get("protected_oracles_failed") != 1
        or status.get("protected_workflow_runs") != 33
        or status.get("production_workflow_runs") != 15
        or status.get("final_acceptances_passed") != 0
        or status.get("delivery_status")
        != "CONTROLLED_T0705_TRASH_CONFIRMATION_RECOVERY_CANDIDATE_NOT_FINAL"
        or status.get("ordering_status")
        != (
            "T0705_THIRTEEN_PROTECTED_FAILED_HEADS_FROZEN_TWO_PRE_SECRET_FAILURES_"
            "ONE_TRASH_CONFIRMATION_RECOVERY_ATTEMPT_AUTHORIZED"
        )
        or status.get("diagnostic_repair_status") != "GA_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED"
        or status.get("new_controlled_delivery_authorized") is not True
        or status.get("new_protected_dispatch_authorized") is not True
    ):
        errors.append("Stage 7 task status is not truthfully T0705 authorized-pending")

    semantic = _load(root / "machine/stages/S7/contracts/semantic_gate.json")
    semantic_statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("status")
        != "T0705_THIRTEEN_FAILED_HEADS_FROZEN_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED_PENDING"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or "T0702_PROTECTED_BETA_PASS_NO_RERUN" not in semantic_statuses
        or "T0704_FIRST_ATTEMPT_FAILED_HEAD_FROZEN" not in semantic_statuses
        or "T0704_RELEASE_ASSET_302_RECOVERY_REPAIR_VERIFIED" not in semantic_statuses
        or "T0704_PROTECTED_BLUE_GREEN_PASS_SCOPE_STOP" not in semantic_statuses
        or "T0705_FIRST_ATTEMPT_FAILED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_SAFE_DEFERRED_COMPATIBILITY_REPAIR_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_METADATA_QUARANTINE_REPAIR_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_LABEL_REPLAY_REPAIR_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_CLOSED_PHASE_DIAGNOSTIC_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_CLOSED_PROCESSED_PLAN_DIAGNOSTIC_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_CLOSED_FIRST_IMPORT_DIAGNOSTIC_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_POINTER_BLOB_RECOVERY_REPAIR_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_APP_REPOSITORY_SCOPE_ACTIVATION_RECOVERY_AUTHORIZED" not in semantic_statuses
        or "T0705_CANONICAL_GIT_BLOB_RECOVERY_AUTHORIZED" not in semantic_statuses
        or "T0705_CANONICAL_GIT_BLOB_FORMAT_PREFLIGHT_RECOVERY_AUTHORIZED" not in semantic_statuses
        or "T0705_ONE_SHOT_AUTHORITY_SCOPE_RECOVERY_AUTHORIZED" not in semantic_statuses
        or "T0705_DETERMINISTIC_HISTORICAL_CLOCK_RECOVERY_DELIVERED_HEAD_FROZEN"
        not in semantic_statuses
        or "T0705_SECURITY_CLOCK_DECOUPLING_RECOVERY_DELIVERED_HEAD_FROZEN" not in semantic_statuses
        or "T0705_RAW_CANONICAL_GIT_BLOB_RECOVERY_AUTHORIZED" not in semantic_statuses
        or "T0705_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED" not in semantic_statuses
        or "T0703_FAILED_LINEAGE_FROZEN" not in semantic_statuses
        or "PROTECTED_ZERO_NEW_WRITE_RECONCILIATION_VALIDATED" not in semantic_statuses
        or "T0703_PROTECTED_ZERO_MUTATION_RECONCILIATION_PASS" not in semantic_statuses
        or "RESOLVED_BY_ENCRYPTED_HISTORICAL_LABEL_REPLAY" not in semantic_statuses
        or "RESOLVED_NO_CALENDAR_WAIT" not in semantic_statuses
    ):
        errors.append("Stage 7 semantic gate is incomplete or overstates production evidence")
    return errors


def _validate_source_and_tests(root: Path) -> list[str]:
    errors: list[str] = []
    required_tokens: dict[str, tuple[str, ...]] = {
        "release_control.py": (
            'ALPHA = "ALPHA"',
            'BETA_RAW_ONLY = "BETA_RAW_ONLY"',
            "M3_NO_CONFIRMED_SOURCE_MUTATION",
            "M3_NO_PROCESSED_OR_SAFE_DEFERRED_MESSAGE",
            "BETA_RAW_RECOVERY_NOT_ONE_HUNDRED_PERCENT",
            "BLUE_GREEN_NO_TIMELINE_PUBLISH_OBSERVED",
            "GA_0430_SCHEDULE_NOT_OBSERVED",
            "TARGET_FEATURE_CONFIGURATION_INCOMPLETE",
            "GA_CAPACITY_AUTHORIZATION_MISSING",
            "mutation_budget_per_run",
            "source mutations exceed the per-run budget",
            "BLUE_GREEN_NO_PARSER_COMPARISON_OBSERVED",
            "BLUE_GREEN_FULL_RECONCILIATION_NOT_OBSERVED",
            "GA_NO_PROCESSED_MESSAGE_OBSERVED",
            "GA_NO_TIMELINE_PUBLISH_OBSERVED",
            "evaluate_completed_phase",
        ),
        "processed_commit.py": (
            'CANDIDATE_SHADOW_ONLY = "CANDIDATE_SHADOW_ONLY"',
            "def shadow(",
            '"CANDIDATE_SHADOW_ONLY"',
            "git_blob_url",
            "_fetch_canonical_blob",
            'blob_payload.get("encoding") != "base64"',
            "canonical Git blob SHA mismatch",
        ),
        "http_transport.py": (
            "_NoRedirect",
            "maximum_request_bytes",
            "maximum_response_bytes",
            'parsed.scheme != "https"',
        ),
        "oauth.py": (
            "GOOGLE_TOKEN_ENDPOINT",
            "GMAIL_MODIFY_SCOPE",
            'parsed.hostname != "gmail.googleapis.com"',
            'payload.get("token_type") != "Bearer"',
        ),
        "protected_beta.py": (
            "ProtectedBetaBootstrap",
            "ProtectedBetaRuntime",
            "BETA_CONFIG_SECRET_NAME",
            "SENDER_REGISTRY_SECRET_NAME",
            "GITHUB_APP_PRIVATE_KEY_SECRET_NAME",
            "AGE_IDENTITY_SECRET_NAME",
            "OPAQUE_ID_KEY_SECRET_NAME",
            "Stage7ReleaseGate().evaluate_promotion",
            "RepositoryResolver",
            "GmailOAuthTokenClient",
            "OfficialAgeDecryptor",
            "RawOnlyCanaryRunner",
            "_CAPACITY_MAX_AGE",
            "approved_tmpfs_root",
            "_is_linux_dev_shm_tmpfs",
            "allow_synthetic_ephemeral_root: bool = False",
            "ProtectedBetaFailurePhase.CONFIG_CAPACITY",
            "ProtectedBetaFailurePhase.RESOURCE_CLEANUP",
        ),
        "protected_beta_diagnostics.py": (
            "class ProtectedBetaFailurePhase",
            "FAILURE_TAXONOMY_VERSION",
            "def failure_reason_codes",
            "def public_failure_payload",
            '"exact_root_cause_claimed": False',
            '"production_health_claimed": False',
            '"final_acceptance_claimed": False',
        ),
        "protected_beta_entrypoint.py": (
            "ExactBetaEnvironmentSecretSource",
            "ProtectedGitHubContext",
            "ProtectedBetaExecutionEvidence",
            "CONTROL_REPOSITORY_ID = 1_300_525_906",
            "CONTROL_OWNER_ID = 68_840_188",
            'CONTROL_REF = "refs/heads/main"',
            'PROTECTED_ENVIRONMENT = "moomooau-beta"',
            'RAW_ONLY_CONFIRMATION = "BETA_RAW_ONLY"',
            "runner_environment",
            '"required_actor_id": CONTROL_OWNER_ID',
            '"required_run_attempt": 1',
            "BETA_SECRET_NAMES",
            "alpha_gate_sha256",
            "Stage7ReleaseGate().evaluate_completed_phase",
            "ProtectedBetaFailurePhase.CONTEXT_GATE",
            "ProtectedBetaFailurePhase.ALPHA_BINDING",
            "ProtectedBetaFailurePhase.AGGREGATE_GATE",
            "public_failure_payload(diagnostics)",
            '"m3_executed": False',
            '"production_health_claimed": False',
            '"final_acceptance_claimed": False',
            "--contract-only",
            "--execute-protected",
        ),
        "protected_m3.py": (
            "ProtectedM3Bootstrap",
            "ProtectedM3Runtime",
            "M3_CONFIG_SECRET_NAME",
            "M3_SECRET_NAMES",
            "Stage7ReleaseGate().evaluate_promotion",
            "M3CanaryRunner",
            "RepositoryCiphertextReader",
            "ExactMessageTrashExecutor",
            "ExistingProcessedReconciliationMatcher",
            "RemoteFirstImportTimestampSource",
            "_MAXIMUM_VERIFIED_CANDIDATES = 1",
            'temporary_prefix="moomooau-protected-m3-"',
        ),
        "protected_m3_diagnostics.py": (
            "class ProtectedM3FailurePhase",
            "FAILURE_TAXONOMY_VERSION",
            "def public_failure_payload",
            '"exact_root_cause_claimed": False',
            '"production_health_claimed": False',
            '"final_acceptance_claimed": False',
        ),
        "protected_m3_entrypoint.py": (
            "ExactM3EnvironmentSecretSource",
            "ProtectedM3GitHubContext",
            "ProtectedM3ExecutionEvidence",
            "CONTROL_REPOSITORY_ID = 1_300_525_906",
            "CONTROL_OWNER_ID = 68_840_188",
            'CONTROL_REF = "refs/heads/main"',
            'PROTECTED_ENVIRONMENT = "moomooau-beta"',
            'M3_CONFIRMATION = "M3_RECONCILE_UNKNOWN_MUTATION_ZERO_NEW_WRITES"',
            "beta_receipt_sha256",
            "m3_gate_sha256",
            "_load_prior_attempt_count",
            "_M3_ATTEMPT_LEDGER_PATH",
            "_M3_SUCCESS_RECEIPT_PATH",
            "_m3_authorized",
            "completion_receipt_present",
            "maximum_verified_candidates",
            "Stage7ReleaseGate().evaluate_completed_phase",
            '"maximum_source_mutations": 0',
            '"maximum_cumulative_source_mutations": 1',
            '"maximum_timeline_mutations": 0',
            '"fixed_calendar_wait_days": 0',
            '"same_head_rerun_allowed": False',
            '"production_health_claimed": False',
            '"final_acceptance_claimed": False',
            "--contract-only",
            "--execute-protected",
        ),
        "stage7_ops.py": (
            'RAW = "RAW"',
            'PROCESSED = "PROCESSED"',
            'TIMELINE = "TIMELINE"',
            "HIGH_OR_CRITICAL_FINDING_OPEN",
            "PROTECTED_PATCH_CANARY_NOT_PASSED",
        ),
        "canary_runtime.py": (
            "RawOnlyCanaryRunner",
            "M3CanaryRunner",
            "CurrentProcessedPlanFactory",
            "ExistingProcessedReconciliationMatcher",
            "FullMailboxDiscoverer",
            "VerificationPhase.PRE_RAW",
            "VerificationPhase.PRE_M3",
            "verify_raw_only",
            "SensitiveOperation.RAW_WRITE",
            "SensitiveOperation.PROCESSED_WRITE",
            "SensitiveOperation.M3",
            "MutationBudget.for_phase(MutationPhase.CANARY)",
            "Stage7ReleaseGate().evaluate_promotion",
            "phase is not ReleasePhase.BETA_RAW_ONLY",
            "BETA_RAW_ONLY_COMPLETED_NOT_FINAL",
            "M3_CANARY_RUN_COMPLETED_NOT_FINAL",
            "reconcile_prior_unknown_mutation",
            "reconcile_already_trashed",
            "ProtectedBetaFailurePhase.MAILBOX_DISCOVERY",
            "ProtectedBetaFailurePhase.METADATA_VERIFICATION",
            "ProtectedBetaFailurePhase.RAW_FETCH",
            "ProtectedBetaFailurePhase.RAW_ENCRYPTION_PLAN",
            "ProtectedBetaFailurePhase.RAW_COMMIT",
            "ProtectedBetaFailurePhase.REMOTE_RECOVERY",
        ),
        "remote_recovery_gate.py": (
            'RAW_ONLY = "RAW_ONLY"',
            'RAW_AND_PROCESSED = "RAW_AND_PROCESSED"',
            "RepositoryCiphertextReader",
            "raw_ciphertext_sha256",
            "_validate_processed_manifest",
        ),
        "timeline_event.py": (
            "def from_bytes",
            "allow_nan=False",
            "Timeline Event payload is not canonical",
            '"Australia/Sydney"',
        ),
        "timeline_snapshot.py": (
            "TimelineSnapshotPlanner",
            "TimelineSnapshotCommitSaga",
            "TimelineSnapshotRecoveryGate",
            "moomooau.timeline-snapshot-root.v1",
            "CurrentProcessedPointer.from_bytes",
            "TimelineEvent.from_bytes",
            "recover_root",
        ),
        "timeline_publish.py": (
            "recover_committed_snapshot_root",
            "Timeline Asset exists without a recoverable private snapshot head",
            "committed Timeline snapshot head is not healthy",
        ),
        "blue_green_runtime.py": (
            "BlueGreenTimelineRunner",
            "RemoteCurrentProcessedPointerSource",
            "Stage7ReleaseGate().evaluate_promotion",
            "candidate shadow unexpectedly contains a current pointer",
            "current pointer changed during candidate shadow commit",
            "recover_committed_snapshot_root",
            "SensitiveOperation.TIMELINE_WRITE",
            "self._timeline_publisher.publish",
            '"calendar_wait_required": False',
            '"deterministic_evidence_complete"',
        ),
        "protected_blue_green.py": (
            "ProtectedBlueGreenBootstrap",
            "ProtectedBlueGreenRuntime",
            "_LiveRepositoryCapacityProbe",
            "allow_stale_capacity_for_live_refresh=True",
            "protected capacity tree is incomplete or unbounded",
            "BLUE_GREEN_SECRET_NAMES = M3_SECRET_NAMES",
            "MAXIMUM_VERIFIED_SOURCE_READS = 1",
            "RemoteCurrentProcessedPointerSource",
            "ProtectedBlueGreenRunResult",
            '"candidate_shadow_only": True',
            '"incumbent_current_retained": True',
            '"current_pointer_mutations": 0',
            '"maximum_live_timeline_assets": 1',
            "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL",
        ),
        "protected_blue_green_entrypoint.py": (
            "ProtectedBlueGreenGitHubContext",
            "ProtectedBlueGreenExecutionEvidence",
            "CONTROL_REPOSITORY_ID = 1_300_525_906",
            "CONTROL_OWNER_ID = 68_840_188",
            'CONTROL_REF = "refs/heads/main"',
            'PROTECTED_ENVIRONMENT = "moomooau-beta"',
            'BLUE_GREEN_CONFIRMATION = "BLUE_GREEN_SAME_RECOVERED_RAW_SHADOW_ONLY"',
            "T0704_PROTECTED_BLUE_GREEN_REDIRECT_RECOVERY_ONLY",
            '"candidate_pointer_promotion": False',
            '"current_pointer_mutations": 0',
            '"single_live_timeline_required": True',
            "--contract-only",
            "--execute-protected",
        ),
        "gmail_sync_checkpoint.py": (
            "EncryptedGmailSyncCheckpoint",
            "GitHubGmailSyncStateStore",
            "moomooau.gmail-run-checkpoint.v1",
            "moomooau.gmail-run-checkpoint.v2",
            "last_successful_run_date_sydney",
            "GMAIL_SYNC_STATE_PATH",
            "Gmail sync checkpoint remote recovery differs",
        ),
        "ga_runtime.py": (
            "GAFullPipelineRunner",
            "Stage7ReleaseGate().evaluate_promotion",
            "MutationPhase.STABLE",
            "reconcile_for_run",
            "VerificationPhase.PRE_RAW",
            "VerificationPhase.PRE_M3",
            "verify_raw_only",
            "SensitiveOperation.M3",
            "Full Reconciliation candidate set differs from full truth",
            "self._timeline_publisher.publish",
            "self._sync_checkpoint.commit",
        ),
        "protected_ga_diagnostics.py": (
            "class ProtectedGAFailurePhase",
            "class ProtectedGADiagnostics",
            "FAILURE_TAXONOMY_VERSION",
            "def public_failure_payload",
            '"exact_root_cause_claimed": False',
            '"protected_values_disclosed": False',
        ),
        "production_adapters.py": (
            "OfficialAgeCrypto",
            "RemoteFirstImportTimestampSource",
            "current Processed manifest recovery failed",
            "first-import timestamp is after the observation",
        ),
        "production.py": (
            "ProductionBootstrap",
            "ProductionRuntime",
            "ExactEnvironmentSecretSource",
            "PRODUCTION_SECRET_NAMES",
            "Stage7ReleaseGate().evaluate_promotion",
            "EncryptedGmailSyncCheckpoint",
            "GAFullPipelineRunner",
            "RemoteFirstImportTimestampSource",
            "--contract-only",
            "--execute-protected",
            "production scheduling watermark did not commit",
            '"production_health_claimed": False',
        ),
        "github_guard.py": (
            "GMAIL_SYNC_STATE_PATH",
            "CONTENT_GMAIL_SYNC_STATE_MESSAGE",
            'GIT_TREE_READ = "git.tree.read"',
            'GIT_BLOB_READ = "git.blob.read"',
            "def git_blob_url(",
            "Git tree observation request is not bounded",
            "Gmail sync state write is not strict CAS",
        ),
        "model_boundary.py": (
            "PassiveCodexAutoContract",
            "PublicHealthObservation",
            "LinzeDatabase/MooMooAU/evidence/ops/latest.json",
            "maximum_evidence_age: timedelta = timedelta(hours=48)",
            "PUBLIC_HEALTH_STALE_SINGLE_ISSUE_BUDGET",
            '"workflow_dispatches": 0',
            '"conversation_continuations": 0',
            '"data_plane_dependency": False',
        ),
        "recovery_drill.py": (
            "RecoveryDrillRunner",
            "OWNER_RECOVERY_KEY_FILE",
            "maximum_samples_per_role: int = 1",
            "private_repository_reads_allowed: bool = False",
            "OfficialRecoveryStreamDecryptor",
            '"MooMooAU-Recovery-Key.agekey"',
            'Path("/dev/shm").resolve(strict=True)',
            "plaintext_sink = _DigestSink()",
            "RecoveryDrillSafetyAudit",
            "KillId.KILL_005",
            '"private_repository_writes": 0',
            '"final_stage7_claimed": False',
        ),
        "patch_lifecycle.py": (
            "PatchLifecycleRunContract",
            "PatchLifecycleRunner",
            "PatchChangeSet",
            "OperationsReadinessSnapshot",
            "FREEZE_KEEP_LAST_VERIFIED",
            "READY_FOR_OWNER_APPROVED_PROMOTION",
            "T0707_PROTECTED_PREDECESSOR_NOT_READY",
            "PATCH_PATH_OUTSIDE_MOOMOOAU_SCOPE",
            '"patch_applied": False',
            '"rollback_executions": 0',
            '"stage7_completion_claimed": False',
        ),
    }
    source_root = root / "src/moomooau_archive"
    for name, tokens in required_tokens.items():
        path = source_root / name
        if not path.is_file() or any(
            token not in path.read_text(encoding="utf-8") for token in tokens
        ):
            errors.append(f"Stage 7 source invariant is missing from {name}")
    calendar_gate_tokens = (
        "M3_SEVEN_DAY_WINDOW_INCOMPLETE",
        "BLUE_GREEN_FOURTEEN_DAY_WINDOW_INCOMPLETE",
        "FOURTEEN_DAY_OBSERVATION_INCOMPLETE",
        "M3_DAILY_RUN_EVIDENCE_INCOMPLETE",
        "BLUE_GREEN_DAILY_RUN_EVIDENCE_INCOMPLETE",
    )
    for name in ("release_control.py", "processed_commit.py", "blue_green_runtime.py"):
        text = (source_root / name).read_text(encoding="utf-8")
        if any(token in text for token in calendar_gate_tokens):
            errors.append(f"Stage 7 calendar wait remains active in {name}")
    protected_beta = source_root / "protected_beta.py"
    if protected_beta.is_file() and "os.environ" in protected_beta.read_text(encoding="utf-8"):
        errors.append("protected Beta bootstrap performs implicit environment discovery")
    public_failure_schema = (
        root / "machine/stages/S7/schemas/protected-beta-public-failure-v1.schema.json"
    )
    if not public_failure_schema.is_file() or public_failure_schema.is_symlink():
        errors.append("protected Beta public failure schema is missing or unsafe")
    tests = [root / "tests/tasks" / f"test_{task.casefold()}.py" for task in STAGE7_TASKS]
    if not all(path.is_file() for path in tests):
        errors.append("Stage 7 task tests are incomplete")
    for index, path in enumerate(tests, start=1):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if f"test_t070{index}" not in text:
            errors.append(f"T070{index} test file has no executable task oracle")
    remediation_paths = (
        root / "tests/remediation/test_rmd04.py",
        root / "machine/contracts/production_composition.json",
        root / "schemas/production-composition-v1.schema.json",
        root / "schemas/production-config-v1.schema.json",
        root / "machine/tools/validate_production_composition.py",
    )
    if not all(path.is_file() and not path.is_symlink() for path in remediation_paths):
        errors.append("RMD-04 production composition evidence closure is incomplete")
    runbook = root / "operations/STAGE7_RUNBOOK.md"
    runbook_text = runbook.read_text(encoding="utf-8") if runbook.is_file() else ""
    for token in (
        "T0705_THIRTEEN_FAILED_HEADS_FROZEN_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED_PENDING",
        "不设自然日等待",
        "一次有界受保护运行",
        "04:30 Australia/Sydney",
        "Mutation Budget",
        "Recovery Drill",
        "Patch Lifecycle",
        "High/Critical",
    ):
        if token not in runbook_text:
            errors.append("Stage 7 operations runbook is incomplete")
            break
    return errors


def _action_uses(workflow: str) -> list[str]:
    return re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)


def _validate_workflow(root: Path) -> list[str]:
    if (
        not STAGE7_WORKFLOW.is_file()
        or not BETA_WORKFLOW.is_file()
        or not M3_WORKFLOW.is_file()
        or not BLUE_GREEN_WORKFLOW.is_file()
        or not PATCH_WORKFLOW.is_file()
    ):
        return ["Stage 7 preflight, protected Beta/M3/Blue-Green or Patch workflow is missing"]
    errors: list[str] = []
    text = STAGE7_WORKFLOW.read_text(encoding="utf-8")
    uses = _action_uses(text)
    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    if not uses or any(PINNED_ACTION.fullmatch(item) is None for item in uses):
        errors.append("Stage 7 preflight workflow contains an unpinned Action")
    for item in uses:
        action, digest = item.rsplit("@", 1)
        expected = pins["actions"].get(action, {}).get("commit_sha")
        if digest != expected:
            errors.append("Stage 7 preflight Action drifts from the pin catalog")
    lowered = text.casefold()
    forbidden = (
        "schedule:",
        "workflow_dispatch",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_production_enabled",
    )
    if any(token in lowered for token in forbidden):
        errors.append("Stage 7 preflight workflow adds Secret, persistence or production authority")
    required = (
        "requirements/stage6.lock",
        "--require-hashes",
        "test_t07*.py",
        "validate_stage7.py",
        "ga_runtime.py",
        "production.py",
        "production_adapters.py",
        "protected_m3.py",
        "protected_m3_diagnostics.py",
        "protected_m3_entrypoint.py",
        "protected_blue_green.py",
        "protected_blue_green_entrypoint.py",
        "protected_ga_diagnostics.py",
        "protected_ga_entrypoint.py",
        "gmail_sync_checkpoint.py",
        "model_boundary.py",
        "recovery_drill.py",
        "patch_lifecycle.py",
        "test_rmd04.py",
        "validate_production_composition.py",
        "production_composition.json",
        "production-composition-v1.schema.json",
        "production-config-v1.schema.json",
        "moomooau-production.yml",
        "moomooau-m3.yml",
        "moomooau-blue-green.yml",
        "moomooau-patch-lifecycle.yml",
        "--preflight",
        "persist-credentials: false",
        "LinzeColin/Governance",
        GOVERNANCE_PIN,
        pins["age"]["linux_amd64_archive_sha256"],
    )
    if any(token not in text for token in required):
        errors.append("Stage 7 preflight command closure is incomplete")
    errors.extend(
        validate_governance_dependency_workflow(
            STAGE7_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )
    beta = BETA_WORKFLOW.read_text(encoding="utf-8")
    beta_uses = _action_uses(beta)
    expected_beta_secret_names = {
        "MOOMOOAU_BETA_CONFIG",
        "MOOMOOAU_SENDER_REGISTRY",
        "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
        "MOOMOOAU_AGE_IDENTITY",
        "MOOMOOAU_OPAQUE_ID_KEY",
        "MOOMOOAU_GMAIL_OAUTH",
    }
    actual_beta_secret_names = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", beta))
    try:
        beta_value = yaml.load(beta, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        beta_value = None
    beta_required = (
        "workflow_dispatch:",
        "expected_head_sha:",
        "confirm_raw_only:",
        "permissions:\n  contents: read",
        "group: moomooau-beta-raw-only-single-writer",
        "cancel-in-progress: false",
        "Fail closed on invalid protected dispatch context",
        'test "$GITHUB_REPOSITORY_ID" = "1300525906"',
        'test "$GITHUB_REPOSITORY_OWNER_ID" = "68840188"',
        'test "$GITHUB_ACTOR_ID" = "68840188"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        'test "$RUNNER_ENVIRONMENT" = "github-hosted"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"',
        'test "$RAW_ONLY_CONFIRMATION" = "BETA_RAW_ONLY"',
        "needs: alpha-gate",
        "environment: moomooau-beta",
        "runs-on: ubuntu-24.04",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        "test_t0701.py tests/tasks/test_t0702.py",
        "validate_package.py",
        "validate_delivery_status.py",
        "validate_publication.py",
        "protected_beta_entrypoint",
        "protected_beta_diagnostics.py",
        "canary_runtime.py",
        "tests/stage7_support.py",
        "protected-beta-public-failure-v1.schema.json",
        "--contract-only",
        "--execute-protected",
        "alpha_gate_sha256",
        "moomooau-protected-beta-*",
        "persist-credentials: false",
        pins["age"]["linux_amd64_archive_sha256"],
    )
    beta_forbidden = (
        "schedule:",
        "pull_request:",
        "\n  push:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_production_enabled",
        "python -m moomooau_archive.production",
        "moomooau_classification_registry",
        "moomooau_parser_registry",
        "moomooau_governance_deploy_key",
    )
    beta_workflow_triggers = (
        set(beta_value.get("on", {}))
        if isinstance(beta_value, dict) and isinstance(beta_value.get("on"), dict)
        else set()
    )
    if (
        beta_workflow_triggers != {"workflow_dispatch"}
        or any(token not in beta for token in beta_required)
        or any(token in beta.casefold() for token in beta_forbidden)
        or actual_beta_secret_names != expected_beta_secret_names
        or beta.count("${{ secrets.") != len(expected_beta_secret_names)
        or beta.count('test "$RUNNER_ENVIRONMENT" = "github-hosted"') != 2
        or beta.count(pins["age"]["linux_amd64_archive_sha256"]) != 2
        or len(beta_uses) != 4
        or any(PINNED_ACTION.fullmatch(item) is None for item in beta_uses)
        or any(
            item.rsplit("@", 1)[1]
            != pins["actions"].get(item.rsplit("@", 1)[0], {}).get("commit_sha")
            for item in beta_uses
        )
    ):
        errors.append("protected Beta workflow drifts from the Raw-only execution contract")
    errors.extend(
        validate_workflow_expression_contexts(
            beta_value,
            label=".github/workflows/moomooau-beta.yml",
        )
    )
    errors.extend(
        validate_governance_dependency_auth(
            beta_value,
            label=".github/workflows/moomooau-beta.yml",
            required=False,
        )
    )
    m3 = M3_WORKFLOW.read_text(encoding="utf-8")
    m3_uses = _action_uses(m3)
    expected_m3_secret_names = {
        "MOOMOOAU_BETA_CONFIG",
        "MOOMOOAU_SENDER_REGISTRY",
        "MOOMOOAU_CLASSIFICATION_REGISTRY",
        "MOOMOOAU_PARSER_REGISTRY",
        "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
        "MOOMOOAU_AGE_IDENTITY",
        "MOOMOOAU_OPAQUE_ID_KEY",
        "MOOMOOAU_GMAIL_OAUTH",
    }
    actual_m3_secret_names = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", m3))
    try:
        m3_value = yaml.load(m3, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        m3_value = None
    m3_required = (
        "workflow_dispatch:",
        "expected_head_sha:",
        "confirm_m3:",
        "M3_RECONCILE_UNKNOWN_MUTATION_ZERO_NEW_WRITES",
        "permissions:\n  contents: read",
        "group: moomooau-m3-zero-mutation-reconciliation",
        "cancel-in-progress: false",
        "Fail closed on invalid protected M3 dispatch context",
        'test "$GITHUB_REPOSITORY_ID" = "1300525906"',
        'test "$GITHUB_REPOSITORY_OWNER_ID" = "68840188"',
        'test "$GITHUB_ACTOR_ID" = "68840188"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        'test "$RUNNER_ENVIRONMENT" = "github-hosted"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"',
        'test "$M3_CONFIRMATION" = "M3_RECONCILE_UNKNOWN_MUTATION_ZERO_NEW_WRITES"',
        "needs: m3-authority-gate",
        "environment: moomooau-beta",
        "runs-on: ubuntu-24.04",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        "tests/tasks/test_t0702.py tests/tasks/test_t0703.py",
        "validate_package.py",
        "validate_delivery_status.py",
        "validate_publication.py",
        "protected_m3_entrypoint",
        "protected_m3.py",
        "protected_m3_diagnostics.py",
        "src/moomooau_archive/m3.py",
        "--contract-only",
        "--execute-protected",
        'assert value["m3_authorized"] is True',
        "beta_receipt_sha256",
        "m3_gate_sha256",
        "moomooau-protected-m3-*",
        "persist-credentials: false",
        pins["age"]["linux_amd64_archive_sha256"],
    )
    m3_forbidden = (
        "schedule:",
        "pull_request:",
        "\n  push:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_production_enabled",
        "python -m moomooau_archive.production",
        "python -m moomooau_archive.blue_green_runtime",
        "moomooau_governance_deploy_key",
    )
    m3_workflow_triggers = (
        set(m3_value.get("on", {}))
        if isinstance(m3_value, dict) and isinstance(m3_value.get("on"), dict)
        else set()
    )
    if (
        m3_workflow_triggers != {"workflow_dispatch"}
        or any(token not in m3 for token in m3_required)
        or any(token in m3.casefold() for token in m3_forbidden)
        or actual_m3_secret_names != expected_m3_secret_names
        or m3.count("${{ secrets.") != len(expected_m3_secret_names)
        or m3.count('test "$RUNNER_ENVIRONMENT" = "github-hosted"') != 2
        or m3.count(pins["age"]["linux_amd64_archive_sha256"]) != 2
        or len(m3_uses) != 4
        or any(PINNED_ACTION.fullmatch(item) is None for item in m3_uses)
        or any(
            item.rsplit("@", 1)[1]
            != pins["actions"].get(item.rsplit("@", 1)[0], {}).get("commit_sha")
            for item in m3_uses
        )
    ):
        errors.append("protected M3 workflow drifts from the Budget-1 execution contract")
    errors.extend(
        validate_workflow_expression_contexts(
            m3_value,
            label=".github/workflows/moomooau-m3.yml",
        )
    )
    errors.extend(
        validate_governance_dependency_auth(
            m3_value,
            label=".github/workflows/moomooau-m3.yml",
            required=False,
        )
    )
    blue_green = BLUE_GREEN_WORKFLOW.read_text(encoding="utf-8")
    blue_green_uses = _action_uses(blue_green)
    expected_blue_green_secret_names = {
        "MOOMOOAU_BETA_CONFIG",
        "MOOMOOAU_SENDER_REGISTRY",
        "MOOMOOAU_CLASSIFICATION_REGISTRY",
        "MOOMOOAU_PARSER_REGISTRY",
        "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
        "MOOMOOAU_AGE_IDENTITY",
        "MOOMOOAU_OPAQUE_ID_KEY",
        "MOOMOOAU_GMAIL_OAUTH",
    }
    actual_blue_green_secret_names = set(
        re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", blue_green)
    )
    try:
        blue_green_value = yaml.load(blue_green, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        blue_green_value = None
    blue_green_required = (
        "workflow_dispatch:",
        "expected_head_sha:",
        "confirm_blue_green:",
        "BLUE_GREEN_SAME_RECOVERED_RAW_SHADOW_ONLY",
        "permissions:\n  contents: read",
        "group: moomooau-blue-green-single-writer",
        "cancel-in-progress: false",
        "Fail closed on invalid protected Blue-Green dispatch context",
        'test "$GITHUB_REPOSITORY_ID" = "1300525906"',
        'test "$GITHUB_REPOSITORY_OWNER_ID" = "68840188"',
        'test "$GITHUB_ACTOR_ID" = "68840188"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        'test "$RUNNER_ENVIRONMENT" = "github-hosted"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"',
        "needs: blue-green-authority-gate",
        "environment: moomooau-beta",
        "runs-on: ubuntu-24.04",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        "tests/tasks/test_t0703.py tests/tasks/test_t0704.py",
        "validate_package.py",
        "validate_delivery_status.py",
        "validate_publication.py",
        "protected_blue_green_entrypoint",
        "protected_blue_green.py",
        "--contract-only",
        "--execute-protected",
        'assert value["blue_green_authorized"] is True',
        "m3_receipt_sha256",
        "blue_green_gate_sha256",
        "moomooau-protected-blue-green-*",
        "persist-credentials: false",
        pins["age"]["linux_amd64_archive_sha256"],
    )
    blue_green_forbidden = (
        "schedule:",
        "pull_request:",
        "\n  push:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "python -m moomooau_archive.production",
        "moomooau_governance_deploy_key",
    )
    blue_green_workflow_triggers = (
        set(blue_green_value.get("on", {}))
        if isinstance(blue_green_value, dict) and isinstance(blue_green_value.get("on"), dict)
        else set()
    )
    if (
        blue_green_workflow_triggers != {"workflow_dispatch"}
        or any(token not in blue_green for token in blue_green_required)
        or any(token in blue_green.casefold() for token in blue_green_forbidden)
        or actual_blue_green_secret_names != expected_blue_green_secret_names
        or blue_green.count("${{ secrets.") != len(expected_blue_green_secret_names)
        or blue_green.count('test "$RUNNER_ENVIRONMENT" = "github-hosted"') != 2
        or blue_green.count(pins["age"]["linux_amd64_archive_sha256"]) != 2
        or len(blue_green_uses) != 4
        or any(PINNED_ACTION.fullmatch(item) is None for item in blue_green_uses)
        or any(
            item.rsplit("@", 1)[1]
            != pins["actions"].get(item.rsplit("@", 1)[0], {}).get("commit_sha")
            for item in blue_green_uses
        )
    ):
        errors.append("protected Blue-Green workflow drifts from the T0704 execution contract")
    errors.extend(
        validate_workflow_expression_contexts(
            blue_green_value,
            label=".github/workflows/moomooau-blue-green.yml",
        )
    )
    errors.extend(
        validate_governance_dependency_auth(
            blue_green_value,
            label=".github/workflows/moomooau-blue-green.yml",
            required=False,
        )
    )
    patch_text = PATCH_WORKFLOW.read_text(encoding="utf-8")
    patch_uses = _action_uses(patch_text)
    if not patch_uses or any(PINNED_ACTION.fullmatch(item) is None for item in patch_uses):
        errors.append("Patch Lifecycle workflow contains an unpinned Action")
    for item in patch_uses:
        action, digest = item.rsplit("@", 1)
        expected = pins["actions"].get(action, {}).get("commit_sha")
        if digest != expected:
            errors.append("Patch Lifecycle Action drifts from the pin catalog")
    patch_lowered = patch_text.casefold()
    patch_forbidden = (
        "schedule:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "environment:",
        "moomooau_production_enabled",
    )
    if any(token in patch_lowered for token in patch_forbidden):
        errors.append("Patch Lifecycle policy workflow adds Secret or mutation authority")
    patch_required = (
        "workflow_dispatch:",
        "permissions:\n  contents: read",
        "patch-policy-preflight",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-deps --disable-pip",
        "python -m pytest -q tests/tasks",
        "validate_stage7.py",
        "--preflight",
        "stage7-patch-sbom.cdx.json",
        "patch_lifecycle.py",
        "MOOMOOAU_PATCH_APPLIED:-false",
        "MOOMOOAU_ROLLBACK_EXECUTED:-false",
        "persist-credentials: false",
        "LinzeColin/Governance",
        GOVERNANCE_PIN,
        pins["age"]["linux_amd64_archive_sha256"],
    )
    if any(token not in patch_text for token in patch_required):
        errors.append("Patch Lifecycle policy workflow command closure is incomplete")
    errors.extend(
        validate_governance_dependency_workflow(
            PATCH_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )
    production = (
        PRODUCTION_WORKFLOW.read_text(encoding="utf-8") if PRODUCTION_WORKFLOW.is_file() else ""
    )
    production_uses = _action_uses(production)
    expected_secret_names = {
        "MOOMOOAU_BETA_CONFIG",
        "MOOMOOAU_SENDER_REGISTRY",
        "MOOMOOAU_CLASSIFICATION_REGISTRY",
        "MOOMOOAU_PARSER_REGISTRY",
        "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
        "MOOMOOAU_AGE_IDENTITY",
        "MOOMOOAU_OPAQUE_ID_KEY",
        "MOOMOOAU_GMAIL_OAUTH",
    }
    actual_secret_names = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", production))
    try:
        production_value = yaml.load(production, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        production_value = None
    production_required = (
        'cron: "30 4 * * *"',
        'timezone: "Australia/Sydney"',
        "workflow_dispatch:",
        "expected_head_sha:",
        "confirm_ga:",
        "GA_SCHEDULE_MODE_TRASH_CONFIRMATION_RECOVERY_MUTATION_BUDGET_ONE",
        "permissions:\n  contents: read",
        "group: moomooau-production-single-writer",
        "Fail closed on invalid protected GA dispatch context",
        'test "$GITHUB_REPOSITORY_ID" = "1300525906"',
        'test "$GITHUB_REPOSITORY_OWNER_ID" = "68840188"',
        'test "$GITHUB_ACTOR_ID" = "68840188"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        'test "$RUNNER_ENVIRONMENT" = "github-hosted"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"',
        'test "$GA_AUTHORIZED_HEAD" = "$GITHUB_SHA"',
        'test "$GITHUB_SHA" != "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f"',
        'test "$GITHUB_SHA" != "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0"',
        'test "$GITHUB_SHA" != "cc7c8af9a40122a61ee2549fb365df813cbd4f16"',
        'test "$GITHUB_SHA" != "4c207ad539754166fae6642ff4e6850438d3e2fc"',
        'test "$GITHUB_SHA" != "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4"',
        'test "$GITHUB_SHA" != "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7"',
        'test "$GITHUB_SHA" != "2133673b335a384657c8668b62a1c13055c212cd"',
        'test "$GITHUB_SHA" != "8b6faaf9059661edc3153352b8787ddbc4f733f3"',
        'test "$GITHUB_SHA" != "6f82e738611e0d2eeeadd2507f738c9e269c91e0"',
        'test "$GITHUB_SHA" != "26949ab5031a21b0c515c282c9ef06ff9417e058"',
        'test "$GITHUB_SHA" != "9c79b92bcdf8b027727963dfe52bd183a170954c"',
        'test "$GITHUB_SHA" != "27886f54a30a12ca7992a908e97340d1d8234430"',
        'test "$GITHUB_SHA" != "c2c057b449fe1cbbd470867c274833242e3f139d"',
        'test "$GITHUB_SHA" != "0d0b6afd6a0cde606230a3df7378bdd90586de5d"',
        'test "$GITHUB_SHA" != "4b7442bb635ea1e7cf5a814c3c56047aa288d594"',
        'echo "authorized_head=$GITHUB_SHA" >> "$GITHUB_OUTPUT"',
        "needs: ga-authority-gate",
        "needs.ga-authority-gate.outputs.authorized_head",
        "environment: moomooau-beta",
        "concurrency:",
        "cancel-in-progress: false",
        "runs-on: ubuntu-24.04",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        pins["age"]["linux_amd64_archive_sha256"],
        "tests/tasks/test_t0705.py",
        "tests/tasks/test_t0202.py",
        "tests/tasks/test_t0502.py",
        "validate_package.py",
        "validate_delivery_status.py",
        "validate_publication.py",
        "protected_ga_entrypoint",
        "--contract-only",
        "--execute-protected",
        "blue_green_receipt_sha256",
        "ga_gate_sha256",
        "MOOMOOAU_GA_REHEARSAL_AUTHORIZED_HEAD",
        "MOOMOOAU_PRODUCTION_ENABLED",
        "persist-credentials: false",
    )
    production_forbidden = (
        "self-hosted",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "git push",
        "contents: write",
        "MOOMOOAU_STAGE5_PROTECTED_ORACLE",
        "environment: moomooau-production",
        "python -m moomooau_archive.production",
    )
    production_workflow_triggers = (
        set(production_value.get("on", {}))
        if isinstance(production_value, dict) and isinstance(production_value.get("on"), dict)
        else set()
    )
    if (
        not PRODUCTION_WORKFLOW.is_file()
        or production_workflow_triggers != {"schedule", "workflow_dispatch"}
        or any(token not in production for token in production_required)
        or any(token.casefold() in production.casefold() for token in production_forbidden)
        or actual_secret_names != expected_secret_names
        or production.count("${{ secrets.") != len(expected_secret_names)
        or production.count('test "$RUNNER_ENVIRONMENT" = "github-hosted"') != 2
        or production.count(pins["age"]["linux_amd64_archive_sha256"]) != 2
        or len(production_uses) != 4
        or any(PINNED_ACTION.fullmatch(item) is None for item in production_uses)
        or any(
            item.rsplit("@", 1)[1]
            != pins["actions"].get(item.rsplit("@", 1)[0], {}).get("commit_sha")
            for item in production_uses
        )
    ):
        errors.append("protected production workflow drifts from the T0705 candidate contract")
    errors.extend(
        validate_workflow_expression_contexts(
            production_value,
            label=".github/workflows/moomooau-production.yml",
        )
    )
    errors.extend(
        validate_governance_dependency_auth(
            production_value,
            label=".github/workflows/moomooau-production.yml",
            required=False,
        )
    )
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S7/schemas/stage7-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    receipt_path = root / "machine/stages/S7/reviews/t0702/execution-receipt.json"
    receipt_schema_path = (
        root / "machine/stages/S7/schemas/protected-beta-execution-receipt-v2.schema.json"
    )
    try:
        receipt = _load(receipt_path)
        receipt_schema = _load(receipt_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected Beta execution receipt is missing or unreadable")
        receipt = {}
        receipt_schema = {}
    else:
        receipt_errors = list(
            Draft202012Validator(
                receipt_schema,
                format_checker=FormatChecker(),
            ).iter_errors(receipt)
        )
        if receipt_errors:
            errors.append("protected Beta execution receipt violates its exact schema")
    ledger_path = root / PROTECTED_BETA_ATTEMPT_LEDGER
    ledger_schema_path = root / PROTECTED_BETA_ATTEMPT_LEDGER_SCHEMA
    try:
        ledger = _load(ledger_path)
        ledger_schema = _load(ledger_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected Beta serial attempt ledger is missing or unreadable")
        ledger = {}
        ledger_schema = {}
    else:
        ledger_errors = list(
            Draft202012Validator(
                ledger_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ledger)
        )
        if ledger_errors:
            errors.append("protected Beta serial attempt ledger violates its schema")
        else:
            attempts = ledger.get("attempts", [])
            summary = ledger.get("summary", {})
            expected_prs = (88, 92, 93, 94, 95, 96, None, None, None, 98, 99)
            expected_merge_shas = (
                "3ad418123f840d2d1a8f49f763ffe3e51ae8094e",  # pragma: allowlist secret
                "508939423ce20b35c2c82936acd8f32b9f7c35fc",  # pragma: allowlist secret
                "e702f1ad3fc6b0f9cef0dec7aaf2f1845191b856",  # pragma: allowlist secret
                "e158c9664579460236033bb9b2c8e2b37344c72d",  # pragma: allowlist secret
                "3d0de0bbfcdf7491857df6b9bb15a0544df6574c",  # pragma: allowlist secret
                "07f8cbf4aaa4a47f8306906e4504afc1b2e724b7",  # pragma: allowlist secret
                None,
                None,
                None,
                "12c68bd101b845c1039841392839e52b27db2b85",  # pragma: allowlist secret
                "eaade5f7be7fca678885cc402b463cb0df54cf90",  # pragma: allowlist secret
            )
            expected_head_shas = (
                "3ad418123f840d2d1a8f49f763ffe3e51ae8094e",  # pragma: allowlist secret
                "508939423ce20b35c2c82936acd8f32b9f7c35fc",  # pragma: allowlist secret
                "e702f1ad3fc6b0f9cef0dec7aaf2f1845191b856",  # pragma: allowlist secret
                "e158c9664579460236033bb9b2c8e2b37344c72d",  # pragma: allowlist secret
                "3d0de0bbfcdf7491857df6b9bb15a0544df6574c",  # pragma: allowlist secret
                "07f8cbf4aaa4a47f8306906e4504afc1b2e724b7",  # pragma: allowlist secret
                "5520b1642a74ff2063b3bec20af4f34bd8808532",  # pragma: allowlist secret
                "0d78b9d14142a01f5c73a6a457b7c6f719576167",  # pragma: allowlist secret
                "49e7ca5352380ed44e6f233b89ed5204bc8ce375",  # pragma: allowlist secret
                "12c68bd101b845c1039841392839e52b27db2b85",  # pragma: allowlist secret
                "eaade5f7be7fca678885cc402b463cb0df54cf90",  # pragma: allowlist secret
            )
            expected_runs = (
                29998793639,
                30008562905,
                30010198526,
                30011285627,
                30012211355,
                30016055252,
                30046255364,
                30047441575,
                30048206165,
                30049384268,
                30051063099,
            )
            expected_classes = (
                "NOT_AVAILABLE_IN_HISTORICAL_AGGREGATE",
                "NOT_CLASSIFIED",
                "INSTALLATION_NOT_FOUND",
                "INSTALLATION_DISCOVERY_REJECTED",
                "INSTALLATION_ZERO",
                "INSTALLATION_ZERO",
                "INSTALLATION_SELECTION_REJECTED",
                "REQUEST_REJECTED",
                "RESPONSE_SCOPE_REJECTED",
                "UNCLASSIFIED",
                None,
            )
            expected_failure_phases = (
                "UNDETERMINED_AGGREGATE_ONLY",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "GITHUB_APP_TOKEN",
                "METADATA_VERIFICATION",
                None,
            )
            expected_reason_codes = (
                "PROTECTED_BETA_RUN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_GITHUB_APP_TOKEN_FAILED",
                "PROTECTED_BETA_METADATA_VERIFICATION_FAILED",
                None,
            )
            expected_summary = {
                "controlled_main_deliveries": 8,
                "protected_beta_dispatches": 12,
                "context_rejected_dispatches": 1,
                "protected_workflow_runs": 11,
                "workflow_reruns": 0,
                "alpha_gate_passes": 11,
                "beta_passes": 1,
                "beta_failures": 10,
                "identity_plaintext_cleanup_passes": 11,
                "latest_outcome": "PASS",
                "last_failure_phase": "METADATA_VERIFICATION",
                "last_installation_token_failure_class": "UNCLASSIFIED",
                "raw_archive_successful_runs": 1,
                "gmail_mutations": 0,
                "m3_runs": 0,
                "processed_writes": 0,
                "timeline_writes": 0,
                "scheduled_runs": 0,
                "t0702_complete": True,
                "m3_predecessor_satisfied": True,
                "m3_allowed": False,
                "m3_authority_status": "WITHHELD_BY_CURRENT_OWNER_SCOPE",
                "production_health_claimed": False,
                "final_acceptance_claimed": False,
            }
            failure_objects = [item.get("public_failure") for item in attempts]
            failure_classes = tuple(
                item.get("installation_token_failure_class") if isinstance(item, dict) else None
                for item in failure_objects
            )
            failure_phases = tuple(
                item.get("failure_phase") if isinstance(item, dict) else None
                for item in failure_objects
            )
            reason_codes = tuple(
                item.get("reason_code") if isinstance(item, dict) else None
                for item in failure_objects
            )
            zero_effect_keys = (
                "gmail_mutations",
                "m3_runs",
                "processed_writes",
                "timeline_writes",
                "scheduled_runs",
            )
            if (
                ledger.get("observed_through_utc") != "2026-07-23T22:53:05Z"
                or len(ledger.get("rejected_dispatches", [])) != 1
                or len(attempts) != 11
                or tuple(item.get("sequence") for item in attempts) != tuple(range(1, 12))
                or tuple(item.get("delivery", {}).get("pull_request_number") for item in attempts)
                != expected_prs
                or tuple(item.get("delivery", {}).get("merge_commit_sha") for item in attempts)
                != expected_merge_shas
                or tuple(item.get("workflow_head_sha") for item in attempts) != expected_head_shas
                or tuple(item.get("workflow_run_id") for item in attempts) != expected_runs
                or failure_classes != expected_classes
                or failure_phases != expected_failure_phases
                or reason_codes != expected_reason_codes
                or any(item.get("alpha_gate", {}).get("status") != "PASS" for item in attempts)
                or any(
                    item.get("beta_raw_only", {}).get("status") != "FAILED"
                    for item in attempts[:-1]
                )
                or attempts[-1].get("beta_raw_only", {}).get("status") != "PASS"
                or any(
                    item.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
                    for item in attempts
                )
                or any(
                    item.get("effects", {}).get("raw_ciphertext_commits") != "ZERO"
                    or item.get("effects", {}).get("raw_remote_recovery") != "NOT_RUN"
                    or any(item.get("effects", {}).get(key) != 0 for key in zero_effect_keys)
                    for item in attempts[:-1]
                )
                or attempts[-1].get("effects", {}).get("raw_ciphertext_commits")
                != "NONZERO_WITHIN_CONFIGURED_BUDGET"
                or attempts[-1].get("effects", {}).get("raw_remote_recovery")
                != "ONE_HUNDRED_PERCENT"
                or any(attempts[-1].get("effects", {}).get(key) != 0 for key in zero_effect_keys)
                or summary != expected_summary
            ):
                errors.append("protected Beta serial attempt ledger is not exact or pass closed")

    m3_ledger_path = root / PROTECTED_M3_ATTEMPT_LEDGER
    m3_ledger_schema_path = root / PROTECTED_M3_ATTEMPT_LEDGER_SCHEMA
    try:
        m3_ledger = _load(m3_ledger_path)
        m3_ledger_schema = _load(m3_ledger_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected M3 attempt ledger is missing or unreadable")
        m3_ledger = {}
        m3_ledger_schema = {}
    else:
        m3_ledger_errors = list(
            Draft202012Validator(
                m3_ledger_schema,
                format_checker=FormatChecker(),
            ).iter_errors(m3_ledger)
        )
        if m3_ledger_errors:
            errors.append("protected M3 attempt ledger violates its exact schema")
        else:
            m3_attempts = m3_ledger.get("attempts", [])
            m3_policy = m3_ledger.get("completion_policy", {})
            m3_claims = m3_ledger.get("claims", {})
            first = m3_attempts[0] if len(m3_attempts) == 6 else {}
            second = m3_attempts[1] if len(m3_attempts) == 6 else {}
            third = m3_attempts[2] if len(m3_attempts) == 6 else {}
            fourth = m3_attempts[3] if len(m3_attempts) == 6 else {}
            fifth = m3_attempts[4] if len(m3_attempts) == 6 else {}
            sixth = m3_attempts[5] if len(m3_attempts) == 6 else {}
            if (
                m3_ledger.get("observed_through_utc") != "2026-07-24T08:09:12Z"
                or m3_ledger.get("task_id") != "T0703"
                or len(m3_attempts) != 6
                or [item.get("sequence") for item in m3_attempts] != [1, 2, 3, 4, 5, 6]
                or [item.get("delivery", {}).get("pull_request_number") for item in m3_attempts]
                != [101, 102, 103, 104, 106, 108]
                or [item.get("delivery", {}).get("merge_commit_sha") for item in m3_attempts]
                != [
                    "f747ddcd2e5eab589802a0c545293cd6f275ca71",  # pragma: allowlist secret
                    "9b15c4d5208429125c9ce2680cac4fbb408f65e0",  # pragma: allowlist secret
                    "bc0bfb3bc60a5ad769b286bb7b4bcdfc1ac195e6",  # pragma: allowlist secret
                    "b922219fa80fd0f55e8dd0d100a87ced2a77b2b8",  # pragma: allowlist secret
                    "c860f3880b48b03c3f71ac79e61e278125fb1811",  # pragma: allowlist secret
                    "9ca3b47eaaa75ef2f6e6650b41960d11545ed04e",  # pragma: allowlist secret
                ]
                or [item.get("workflow", {}).get("run_id") for item in m3_attempts]
                != [
                    30060804854,
                    30063841144,
                    30066295809,
                    30068892160,
                    30072484529,
                    30077550182,
                ]
                or any(
                    item.get("workflow", {}).get("workflow_head_sha")
                    != item.get("delivery", {}).get("merge_commit_sha")
                    for item in m3_attempts
                )
                or any(
                    item.get("delivery", {}).get("main_ci_runs_passed") != 10
                    or item.get("delivery", {}).get("main_ci_runs_failed") != 0
                    or item.get("workflow", {}).get("event") != "workflow_dispatch"
                    or item.get("workflow", {}).get("run_attempt") != 1
                    or item.get("workflow", {}).get("reruns") != 0
                    or item.get("jobs", {}).get("authority_gate", {}).get("status") != "PASS"
                    or item.get("jobs", {}).get("m3_budget_one", {}).get("status") != "FAILED"
                    or item.get("jobs", {}).get("identity_plaintext_cleanup", {}).get("status")
                    != "PASS"
                    or item.get("public_failure", {}).get("status") != "BLOCKED"
                    or item.get("public_failure", {}).get("exact_root_cause_claimed") is not False
                    or item.get("effects", {}).get("source_mutations") != 0
                    or item.get("effects", {}).get("timeline_writes") != 0
                    or item.get("effects", {}).get("scheduled_runs") != 0
                    or item.get("effects", {}).get("identity_plaintext_cleanup") != "PASS"
                    for item in m3_attempts
                )
                or any(
                    item.get("effects", {}).get("private_repository_new_commits") != 0
                    or item.get("effects", {}).get("private_repository_head_changed") is not False
                    or item.get("effects", {}).get("raw_ciphertext_creations") != "ZERO_OBSERVED"
                    or item.get("effects", {}).get("processed_writes") != "ZERO_OBSERVED"
                    or item.get("effects", {}).get("processed_current_before_dispatch") != "ZERO"
                    or item.get("effects", {}).get("processed_current_after_dispatch") != "ZERO"
                    or item.get("effects", {}).get("gmail_trash_messages_after_dispatch") != 0
                    or item.get("effects", {}).get("source_mutation_attribution") != "ZERO_OBSERVED"
                    for item in m3_attempts[:4]
                )
                or first.get("public_failure", {}).get("reason_code")
                != "PROTECTED_M3_ENTRYPOINT_FAILED"
                or first.get("diagnosis", {}).get("high_confidence_defect")
                != "M3_METADATA_QUARANTINE_PARITY_GAP"
                or second.get("public_failure", {}).get("reason_code")
                != "PROTECTED_M3_GITHUB_APP_TOKEN_FAILED"
                or second.get("public_failure", {}).get("failure_phase") != "GITHUB_APP_TOKEN"
                or second.get("diagnosis", {}).get("exact_root_cause")
                != "NOT_CLAIMED_FROM_CLOSED_PHASE_ONLY_OUTPUT"
                or second.get("diagnosis", {}).get("high_confidence_defect")
                != "M3_INSTALLATION_TOKEN_FAILURE_CLASS_VISIBILITY_GAP"
                or third.get("public_failure", {}).get("reason_code")
                != "PROTECTED_M3_GITHUB_APP_TOKEN_FAILED"
                or third.get("public_failure", {}).get("failure_phase") != "GITHUB_APP_TOKEN"
                or third.get("public_failure", {}).get("installation_token_failure_class")
                != "RESPONSE_SCOPE_REJECTED"
                or third.get("diagnosis", {}).get("exact_root_cause")
                != "NOT_CLAIMED_FROM_CLOSED_RESPONSE_SCOPE_CLASS"
                or third.get("diagnosis", {}).get("high_confidence_defect")
                != "OPTIONAL_TOKEN_SCOPE_ECHO_AND_SERVER_TIME_VALIDATION_MISMATCH"
                or fourth.get("public_failure", {}).get("reason_code")
                != "PROTECTED_M3_AGGREGATE_GATE_FAILED"
                or fourth.get("public_failure", {}).get("failure_phase") != "AGGREGATE_GATE"
                or fourth.get("public_failure", {}).get("installation_token_failure_class")
                != "UNCLASSIFIED"
                or fourth.get("diagnosis", {}).get("exact_root_cause")
                != "NOT_CLAIMED_FROM_CLOSED_AGGREGATE_PHASE_ONLY_OUTPUT"
                or fourth.get("diagnosis", {}).get("high_confidence_defect")
                != "EMPTY_REGISTRY_QUARANTINE_SAFE_DEFERRED_ORDERING_GAP"
                or fifth.get("public_failure", {}).get("aggregate_failure_class")
                != "MUTATION_FAILED"
                or fifth.get("effects", {}).get("private_repository_new_commits")
                != "NONZERO_NOT_EXACTLY_COUNTED"
                or fifth.get("effects", {}).get("private_repository_head_changed") is not True
                or fifth.get("effects", {}).get("raw_ciphertext_creations") != "ZERO_OBSERVED"
                or fifth.get("effects", {}).get("processed_writes") != "ONE_RECOVERED"
                or fifth.get("effects", {}).get("processed_current_before_dispatch") != "ZERO"
                or fifth.get("effects", {}).get("processed_current_after_dispatch") != "ONE"
                or fifth.get("effects", {}).get("gmail_trash_messages_after_dispatch") != 1
                or fifth.get("effects", {}).get("source_mutation_attribution")
                != "UNCONFIRMED_EXACT_SOURCE"
                or fifth.get("diagnosis", {}).get("exact_root_cause")
                != "NOT_CLAIMED_FROM_CLOSED_MUTATION_FAILURE_CLASS_AND_AGGREGATE_EFFECTS"
                or fifth.get("diagnosis", {}).get("high_confidence_defect")
                != "UNKNOWN_MUTATION_OUTCOME_REQUIRES_ZERO_MUTATION_RECONCILIATION"
                or sixth.get("public_failure", {}).get("reason_code")
                != "PROTECTED_M3_PROCESSED_PLAN_FAILED"
                or sixth.get("public_failure", {}).get("failure_phase") != "PROCESSED_PLAN"
                or sixth.get("public_failure", {}).get("installation_token_failure_class")
                != "UNCLASSIFIED"
                or sixth.get("public_failure", {}).get("aggregate_failure_class") != "UNCLASSIFIED"
                or sixth.get("effects", {}).get("private_repository_new_commits") != 0
                or sixth.get("effects", {}).get("private_repository_head_changed") is not False
                or sixth.get("effects", {}).get("raw_ciphertext_creations") != "ZERO_OBSERVED"
                or sixth.get("effects", {}).get("processed_writes") != "ZERO_OBSERVED"
                or sixth.get("effects", {}).get("processed_current_before_dispatch") != "ONE"
                or sixth.get("effects", {}).get("processed_current_after_dispatch") != "ONE"
                or sixth.get("effects", {}).get("gmail_trash_messages_after_dispatch") != 0
                or sixth.get("effects", {}).get("source_mutation_attribution") != "ZERO_OBSERVED"
                or sixth.get("diagnosis", {}).get("exact_root_cause")
                != "NOT_CLAIMED_FROM_CLOSED_PROCESSED_PLAN_PHASE_ONLY_OUTPUT"
                or sixth.get("diagnosis", {}).get("high_confidence_defect")
                != "M3_HISTORICAL_GMAIL_LABEL_STATE_REPLAY_GAP"
                or m3_policy.get("same_head_rerun_allowed") is not False
                or m3_policy.get("failed_head_redispatch_allowed") is not False
                or m3_policy.get("repaired_exact_main_candidate_dispatch_allowed") is not True
                or m3_policy.get("zero_mutation_reconciliation_dispatch_allowed") is not True
                or m3_policy.get("next_candidate_dispatch_limit") != 1
                or m3_policy.get("t0704_authorized") is not False
                or m3_policy.get("final_publication_authorized") is not False
                or any(value is not False for value in m3_claims.values())
            ):
                errors.append(
                    "protected M3 failed-attempt lineage is not exact or reconciliation-eligible"
                )
    m3_receipt_path = root / PROTECTED_M3_RECEIPT
    m3_receipt_schema_path = root / PROTECTED_M3_RECEIPT_SCHEMA
    try:
        m3_receipt = _load(m3_receipt_path)
        m3_receipt_schema = _load(m3_receipt_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected M3 PASS receipt is missing or unreadable")
        m3_receipt = {}
        m3_receipt_schema = {}
    else:
        m3_receipt_errors = list(
            Draft202012Validator(
                m3_receipt_schema,
                format_checker=FormatChecker(),
            ).iter_errors(m3_receipt)
        )
        control = m3_receipt.get("control", {})
        public = m3_receipt.get("public_result", {})
        verification = m3_receipt.get("independent_post_run_verification", {})
        scope = m3_receipt.get("scope_decision", {})
        claims = m3_receipt.get("claims", {})
        if (
            m3_receipt_errors
            or m3_receipt.get("observed_at_utc") != "2026-07-24T09:20:08Z"
            or control.get("pull_request_number") != 110
            or control.get("merge_commit_sha") != "83fec6161d5cd80c62f3553d6332c0113ef5a514"
            or control.get("workflow_run_id") != 30081901453
            or control.get("workflow_head_sha") != control.get("merge_commit_sha")
            or control.get("workflow_attempt") != 1
            or control.get("reruns") != 0
            or control.get("prior_failed_attempt_ledger_sha256")
            != _sha256(root / PROTECTED_M3_ATTEMPT_LEDGER)
            or any(job.get("status") != "PASS" for job in m3_receipt.get("jobs", {}).values())
            or public.get("status")
            != "PROTECTED_M3_ZERO_MUTATION_RECONCILIATION_COMPLETED_NOT_FINAL"
            or public.get("remote_recovery_one_hundred_percent") is not True
            or public.get("prior_unknown_mutation_reconciled") is not True
            or public.get("current_run_source_mutation_budget") != 0
            or public.get("collateral_mutations") != 0
            or public.get("timeline_publish_attempts") != 0
            or public.get("exact_mailbox_counts_disclosed") is not False
            or verification.get("private_repository_head_unchanged") is not True
            or verification.get("private_repository_tree_unchanged") is not True
            or verification.get("private_repository_path_counts_unchanged") is not True
            or verification.get("gmail_trash_aggregate_delta") != 0
            or verification.get("source_mutations") != 0
            or verification.get("exact_private_locator_disclosed") is not False
            or scope.get("t0703_complete") is not True
            or scope.get("t0704_authorized") is not False
            or scope.get("further_m3_dispatch_allowed") is not False
            or claims.get("s7ac_003_passed") is not True
            or claims.get("stage7_complete") is not False
            or claims.get("final_acceptance") is not False
        ):
            errors.append("protected M3 PASS receipt is not exact or scope-stopped")
    blue_green_receipt_path = root / PROTECTED_BLUE_GREEN_RECEIPT
    blue_green_receipt_schema_path = root / PROTECTED_BLUE_GREEN_RECEIPT_SCHEMA
    try:
        blue_green_receipt = _load(blue_green_receipt_path)
        blue_green_receipt_schema = _load(blue_green_receipt_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected Blue-Green PASS receipt is missing or unreadable")
        blue_green_receipt = {}
        blue_green_receipt_schema = {}
    else:
        blue_green_receipt_errors = list(
            Draft202012Validator(
                blue_green_receipt_schema,
                format_checker=FormatChecker(),
            ).iter_errors(blue_green_receipt)
        )
        control = blue_green_receipt.get("control", {})
        jobs = blue_green_receipt.get("jobs", {})
        public = blue_green_receipt.get("public_result", {})
        verification = blue_green_receipt.get("independent_post_run_verification", {})
        scope = blue_green_receipt.get("scope_decision", {})
        claims = blue_green_receipt.get("claims", {})
        if (
            blue_green_receipt_errors
            or blue_green_receipt.get("observed_at_utc") != "2026-07-25T22:52:22Z"
            or control.get("pull_request_number") != 113
            or control.get("pull_request_head_sha") != "10849a91e4386e9b98575f15bce554c65e890d62"
            or control.get("merge_commit_parent_sha")
            != "b3ff184bd9a7f0e66a7fde6cd6656f11dd982177"  # pragma: allowlist secret
            or control.get("merge_commit_sha") != "65cef09935475ab578d28a61817cc92700d6da04"
            or control.get("workflow_run_id") != 30178201201
            or control.get("workflow_head_sha") != control.get("merge_commit_sha")
            or control.get("workflow_attempt") != 1
            or control.get("dispatches_for_head") != 1
            or control.get("reruns") != 0
            or control.get("prior_failed_attempt_ledger_sha256")
            != _sha256(root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER)
            or control.get("prior_failed_attempt_ledger_schema_sha256")
            != _sha256(root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA)
            or control.get("m3_receipt_sha256") != _sha256(root / PROTECTED_M3_RECEIPT)
            or any(job.get("status") != "PASS" for job in jobs.values())
            or public.get("status") != "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL"
            or public.get("blue_green_gate_status") != "PASS"
            or public.get("observed_runs") != 1
            or public.get("selected_verified_source_bucket") != "ONE"
            or public.get("processed_recoveries") != 1
            or public.get("parser_comparisons") != 1
            or public.get("candidate_shadow_only") is not True
            or public.get("current_pointer_mutations") != 0
            or public.get("incumbent_current_retained") is not True
            or public.get("timeline_snapshot_recoveries") != 1
            or public.get("timeline_publish_attempts") != 1
            or public.get("minimum_live_timeline_assets") != 1
            or public.get("maximum_live_timeline_assets") != 1
            or public.get("full_reconcile_runs") != 1
            or public.get("full_reconcile_difference") != 0
            or public.get("fixed_calendar_wait_days") != 0
            or public.get("gmail_mutations") != 0
            or public.get("unresolved_comparison_differences") != 0
            or public.get("remote_timeline_recovery_one_hundred_percent") is not True
            or public.get("exact_mailbox_counts_disclosed") is not False
            or public.get("protected_values_disclosed") is not False
            or public.get("production_health_claimed") is not False
            or public.get("final_acceptance_claimed") is not False
            or verification.get("private_repository_tree_complete") is not True
            or verification.get("private_repository_tree_truncated") is not False
            or verification.get("moomooau_namespace_new_commits") != 1
            or verification.get("other_namespace_activity_excluded") is not True
            or verification.get("changed_files_in_repair_commit") != 1
            or verification.get("encrypted_timeline_state_writes") != 1
            or verification.get("encrypted_timeline_state_age_envelope") is not True
            or verification.get("raw_tree_unchanged") is not True
            or verification.get("processed_tree_unchanged") is not True
            or verification.get("candidate_processed_shadow_writes") != 0
            or verification.get("timeline_snapshot_writes") != 0
            or verification.get("processed_current_before_dispatch") != "ONE"
            or verification.get("processed_current_after_dispatch") != "ONE"
            or verification.get("processed_current_path_and_blob_identity") is not True
            or verification.get("fixed_release_count") != 1
            or verification.get("live_timeline_assets") != 1
            or verification.get("live_asset_nonempty") is not True
            or verification.get("live_asset_download_bytes") != 11622
            or verification.get("live_asset_age_envelope") is not True
            or verification.get("live_asset_download_recovered") is not True
            or verification.get("protected_asset_decrypt_and_digest_verification") != "PASS"
            or verification.get("independent_asset_decryption_claimed") is not False
            or verification.get("gmail_mutation_independent_remeasurement")
            != "NOT_REQUIRED_REPAIR_CONTRACT_ZERO_MUTATION"
            or verification.get("source_mutations") != 0
            or verification.get("scheduled_runs") != 0
            or verification.get("ga_runs") != 0
            or verification.get("identity_plaintext_cleanup") != "PASS"
            or verification.get("exact_private_locator_disclosed") is not False
            or verification.get("exact_mailbox_counts_disclosed") is not False
            or scope.get("status") != "T0704_COMPLETE_SCOPE_STOP"
            or scope.get("t0704_complete") is not True
            or scope.get("blue_green_predecessor_satisfied") is not True
            or scope.get("t0705_authorized") is not False
            or scope.get("further_blue_green_dispatch_allowed") is not False
            or scope.get("rerun_allowed") is not False
            or scope.get("failed_head_redispatch_allowed") is not False
            or claims.get("t0704_complete") is not True
            or claims.get("s7ac_004_passed") is not True
            or claims.get("t0705_complete") is not False
            or claims.get("production_health") is not False
            or claims.get("final_acceptance") is not False
            or claims.get("stage7_complete") is not False
        ):
            errors.append("protected Blue-Green PASS receipt is not exact or scope-stopped")
    ga_ledger_path = root / PROTECTED_GA_ATTEMPT_LEDGER
    ga_ledger_schema_path = root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_ledger = _load(ga_ledger_path)
        ga_ledger_schema = _load(ga_ledger_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA failed-attempt ledger is missing or unreadable")
        ga_ledger = {}
        ga_ledger_schema = {}
    else:
        ga_ledger_errors = list(
            Draft202012Validator(
                ga_ledger_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_ledger)
        )
        attempts = ga_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        public_failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_ledger.get("completion_policy", {})
        claims = ga_ledger.get("claims", {})
        if (
            ga_ledger_errors
            or _sha256(ga_ledger_path) != FAILED_T0705_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_ledger_schema_path) != FAILED_T0705_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_ledger.get("task_id") != "T0705"
            or delivery.get("pull_request_number") != 115
            or delivery.get("merge_commit_sha") != "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f"
            or delivery.get("terminal_checks") != 39
            or delivery.get("successful_checks") != 22
            or delivery.get("failed_checks") != 11
            or delivery.get("skipped_checks") != 5
            or delivery.get("neutral_checks") != 1
            or workflow.get("run_id") != 30182491342
            or workflow.get("workflow_id") != 318812500
            or workflow.get("event") != "workflow_dispatch"
            or workflow.get("workflow_head_sha") != "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f"
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or public_failure.get("reason_code") != "PROTECTED_GA_FAILED"
            or public_failure.get("exact_root_cause_claimed") is not False
            or public_failure.get("protected_values_disclosed") is not False
            or public_failure.get("platform_schedule_event_claimed") is not False
            or public_failure.get("production_health_claimed") is not False
            or public_failure.get("final_acceptance_claimed") is not False
            or effects.get("private_repository_new_commits") != 0
            or effects.get("raw_path_changes") != 0
            or effects.get("processed_path_changes") != 0
            or effects.get("state_path_changes") != 0
            or effects.get("other_path_changes") != 0
            or effects.get("gmail_checkpoint_exists_after_dispatch") is not False
            or effects.get("timeline_state_exists_after_dispatch") is not True
            or effects.get("live_timeline_assets_before_dispatch") != 1
            or effects.get("live_timeline_assets_after_dispatch") != 1
            or effects.get("canonical_live_timeline_assets_after_dispatch") != 1
            or effects.get("live_timeline_ciphertext_bytes_after_dispatch") != 11622
            or effects.get("gmail_mutation_api_reachable") is not False
            or effects.get("platform_schedule_events") != 0
            or effects.get("identity_plaintext_cleanup") != "PASS"
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or diagnosis.get("observable_failure_boundary")
            != "BEFORE_GMAIL_CREDENTIAL_EXCHANGE_OR_DATA_PLANE_WRITE"
            or diagnosis.get("exact_runtime_exception") != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
            or diagnosis.get("high_confidence_defect")
            != "GA_REJECTED_PAIRED_SAFE_DEFERRED_REGISTRIES"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("new_reviewed_repair_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA failed-attempt ledger is not exact or frozen")
    ga_repair_ledger_path = root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER
    ga_repair_ledger_schema_path = root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_repair_ledger = _load(ga_repair_ledger_path)
        ga_repair_ledger_schema = _load(ga_repair_ledger_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA repair failed-attempt ledger is missing or unreadable")
    else:
        ga_repair_errors = list(
            Draft202012Validator(
                ga_repair_ledger_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_repair_ledger)
        )
        attempts = ga_repair_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        predecessor = ga_repair_ledger.get("predecessor_control", {})
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        effects = attempt.get("effects", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_repair_ledger.get("completion_policy", {})
        claims = ga_repair_ledger.get("claims", {})
        if (
            ga_repair_errors
            or _sha256(ga_repair_ledger_path) != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_repair_ledger_schema_path)
            != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("prior_attempt_ledger_sha256") != FAILED_T0705_ATTEMPT_LEDGER_SHA256
            or predecessor.get("prior_attempt_ledger_schema_sha256")
            != FAILED_T0705_ATTEMPT_LEDGER_SCHEMA_SHA256
            or attempt.get("sequence") != 2
            or delivery.get("pull_request_number") != 116
            or delivery.get("merge_commit_sha") != "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0"
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or delivery.get("terminal_checks") != 23
            or delivery.get("successful_checks") != 23
            or any(
                delivery.get(key) != 0
                for key in ("failed_checks", "skipped_checks", "neutral_checks")
            )
            or workflow.get("run_id") != 30184702520
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or effects.get("private_repository_new_commits_since_dispatch") != 0
            or any(
                effects.get(key) != 0
                for key in (
                    "raw_path_changes",
                    "processed_path_changes",
                    "state_path_changes",
                    "other_path_changes",
                    "platform_schedule_events",
                )
            )
            or effects.get("gmail_checkpoint_exists_after_dispatch") is not False
            or effects.get("timeline_state_exists_after_dispatch") is not True
            or effects.get("live_timeline_assets_after_dispatch") != 1
            or effects.get("live_timeline_ciphertext_bytes_after_dispatch") != 11622
            or effects.get("gmail_mutation_api_reached") is not False
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or diagnosis.get("exact_runtime_exception") != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
            or diagnosis.get("high_confidence_defect")
            != "GA_DID_NOT_QUARANTINE_MESSAGE_METADATA_UNVERIFIABLE"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("new_reviewed_metadata_quarantine_repair_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 2
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA repair failed-attempt ledger is not exact or frozen")
    ga_label_replay_ledger_path = root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER
    ga_label_replay_schema_path = root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_label_replay_ledger = _load(ga_label_replay_ledger_path)
        ga_label_replay_schema = _load(ga_label_replay_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA label-replay failed-attempt ledger is missing or unreadable")
    else:
        ga_label_replay_errors = list(
            Draft202012Validator(
                ga_label_replay_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_label_replay_ledger)
        )
        attempts = ga_label_replay_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        predecessor = ga_label_replay_ledger.get("predecessor_control", {})
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        effects = attempt.get("effects", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_label_replay_ledger.get("completion_policy", {})
        claims = ga_label_replay_ledger.get("claims", {})
        if (
            ga_label_replay_errors
            or _sha256(ga_label_replay_ledger_path)
            != FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_label_replay_schema_path)
            != FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("first_attempt_ledger_sha256") != FAILED_T0705_ATTEMPT_LEDGER_SHA256
            or predecessor.get("first_attempt_ledger_schema_sha256")
            != FAILED_T0705_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("second_attempt_ledger_sha256")
            != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SHA256
            or predecessor.get("second_attempt_ledger_schema_sha256")
            != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SCHEMA_SHA256
            or attempt.get("sequence") != 3
            or delivery.get("pull_request_number") != 117
            or delivery.get("pull_request_head_sha")
            != "aacbf18766e98852cce4733f74b5104b8587ef15"  # pragma: allowlist secret
            or delivery.get("merge_commit_parent_sha")
            != "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha")
            != "cc7c8af9a40122a61ee2549fb365df813cbd4f16"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or delivery.get("terminal_checks") != 40
            or delivery.get("successful_checks") != 35
            or delivery.get("failed_checks") != 0
            or delivery.get("skipped_checks") != 5
            or delivery.get("neutral_checks") != 0
            or workflow.get("run_id") != 30187132406
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or effects.get("private_repository_new_commits_since_dispatch") != 0
            or effects.get("private_repository_path_aggregate_change")
            != "UNCHANGED_BECAUSE_ZERO_NEW_COMMITS"
            or effects.get("gmail_checkpoint_exists_after_dispatch") is not False
            or effects.get("timeline_state_exists_after_dispatch") is not True
            or effects.get("active_moomoo_candidate_outside_trash_after_dispatch") is not True
            or effects.get("gmail_mutation_api_reached") != "NOT_CLAIMED_WITHOUT_PROTECTED_TRACE"
            or effects.get("timeline_release_asset_independent_remeasurement") != "NOT_PERFORMED"
            or effects.get("platform_schedule_events") != 0
            or effects.get("identity_plaintext_cleanup") != "PASS"
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or diagnosis.get("exact_runtime_exception") != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
            or diagnosis.get("high_confidence_defect")
            != "GA_DID_NOT_REPLAY_PERSISTED_FIRST_IMPORT_LABEL_STATE"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("new_reviewed_label_replay_repair_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 3
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA label-replay failed-attempt ledger is not exact or frozen")
    ga_post_processed_ledger_path = root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER
    ga_post_processed_schema_path = root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_post_processed_ledger = _load(ga_post_processed_ledger_path)
        ga_post_processed_schema = _load(ga_post_processed_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA post-Processed failed-attempt ledger is missing or unreadable")
    else:
        ga_post_processed_errors = list(
            Draft202012Validator(
                ga_post_processed_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_post_processed_ledger)
        )
        attempts = ga_post_processed_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        predecessor = ga_post_processed_ledger.get("predecessor_control", {})
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        public_failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_post_processed_ledger.get("completion_policy", {})
        claims = ga_post_processed_ledger.get("claims", {})
        if (
            ga_post_processed_errors
            or _sha256(ga_post_processed_ledger_path)
            != FAILED_T0705_POST_PROCESSED_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_post_processed_schema_path)
            != FAILED_T0705_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("first_attempt_ledger_sha256") != FAILED_T0705_ATTEMPT_LEDGER_SHA256
            or predecessor.get("first_attempt_ledger_schema_sha256")
            != FAILED_T0705_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("second_attempt_ledger_sha256")
            != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SHA256
            or predecessor.get("second_attempt_ledger_schema_sha256")
            != FAILED_T0705_REPAIR_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("third_attempt_ledger_sha256")
            != FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SHA256
            or predecessor.get("third_attempt_ledger_schema_sha256")
            != FAILED_T0705_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_SHA256
            or attempt.get("sequence") != 4
            or delivery.get("pull_request_number") != 118
            or delivery.get("pull_request_head_sha")
            != "5693dbf09c472046530f4ff3bb23ed425deccf34"  # pragma: allowlist secret
            or delivery.get("merge_commit_parent_sha")
            != "cc7c8af9a40122a61ee2549fb365df813cbd4f16"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha")
            != "4c207ad539754166fae6642ff4e6850438d3e2fc"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or delivery.get("terminal_checks") != 23
            or delivery.get("successful_checks") != 23
            or any(
                delivery.get(key) != 0
                for key in ("failed_checks", "skipped_checks", "neutral_checks")
            )
            or workflow.get("run_id") != 30189278592
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or public_failure.get("reason_code") != "PROTECTED_GA_FAILED"
            or public_failure.get("exact_root_cause_claimed") is not False
            or effects.get("private_repository_new_commits_during_attempt") != 6
            or effects.get("private_repository_added_encrypted_paths") != 6
            or effects.get("private_repository_modified_paths") != 0
            or effects.get("private_repository_removed_paths") != 0
            or effects.get("raw_content_paths_added") != 2
            or effects.get("raw_manifest_paths_added") != 1
            or effects.get("processed_content_paths_added") != 1
            or effects.get("processed_manifest_paths_added") != 1
            or effects.get("processed_current_pointer_paths_added") != 1
            or effects.get("timeline_snapshot_or_manifest_paths_changed") != 0
            or effects.get("timeline_state_paths_changed") != 0
            or effects.get("gmail_checkpoint_paths_changed") != 0
            or effects.get("added_paths_with_age_magic") != 6
            or effects.get("added_paths_without_age_magic") != 0
            or effects.get("gmail_checkpoint_exists_after_dispatch") is not False
            or effects.get("timeline_state_exists_after_dispatch") is not True
            or effects.get("live_timeline_assets_after_dispatch") != 1
            or effects.get("active_moomoo_candidate_outside_trash_after_dispatch") is not True
            or effects.get("gmail_mutation_api_reached") != "NOT_CLAIMED_WITHOUT_PROTECTED_TRACE"
            or effects.get("gmail_mutation_independent_remeasurement")
            != "NOT_CLAIMED_WITHOUT_EXACT_PRE_DISPATCH_BASELINE"
            or effects.get("platform_schedule_events") != 0
            or effects.get("identity_plaintext_cleanup") != "PASS"
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or diagnosis.get("observable_failure_boundary")
            != (
                "AFTER_SIX_ENCRYPTED_RAW_PROCESSED_CURRENT_ADDITIONS_"
                "BEFORE_TIMELINE_SNAPSHOT_OR_CHECKPOINT"
            )
            or diagnosis.get("exact_runtime_exception") != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
            or diagnosis.get("exact_root_cause_claimed") is not False
            or diagnosis.get("safe_next_diagnostic") != "CLOSED_ENUM_LAST_ENTERED_GA_PHASE_ONLY"
            or policy.get("new_reviewed_phase_diagnostic_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 4
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append(
                "protected GA post-Processed failed-attempt ledger is not exact or frozen"
            )
    ga_processed_plan_ledger_path = root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER
    ga_processed_plan_schema_path = root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_processed_plan_ledger = _load(ga_processed_plan_ledger_path)
        ga_processed_plan_schema = _load(ga_processed_plan_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA Processed-plan failed-attempt ledger is missing or unreadable")
    else:
        ga_processed_plan_errors = list(
            Draft202012Validator(
                ga_processed_plan_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_processed_plan_ledger)
        )
        attempts = ga_processed_plan_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_processed_plan_ledger.get("completion_policy", {})
        claims = ga_processed_plan_ledger.get("claims", {})
        if (
            ga_processed_plan_errors
            or _sha256(ga_processed_plan_ledger_path)
            != FAILED_T0705_PROCESSED_PLAN_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_processed_plan_schema_path)
            != FAILED_T0705_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_SHA256
            or attempt.get("sequence") != 5
            or delivery.get("pull_request_number") != 119
            or delivery.get("merge_commit_sha")
            != "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or workflow.get("run_id") != 30192270846
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or failure.get("reason_code") != "PROTECTED_GA_PROCESSED_PLAN_FAILED"
            or failure.get("failure_phase") != "PROCESSED_PLAN"
            or failure.get("exact_root_cause_claimed") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "private_repository_new_commits_during_attempt",
                    "private_repository_added_paths",
                    "private_repository_modified_paths",
                    "private_repository_removed_paths",
                    "raw_ciphertext_creations",
                    "processed_immutable_creations",
                    "processed_current_pointer_mutations",
                    "timeline_snapshot_mutations",
                    "timeline_state_mutations",
                    "timeline_publish_attempts",
                    "gmail_checkpoint_mutations",
                    "gmail_source_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("gmail_mutation_api_reached") is not False
            or diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
            or diagnosis.get("exact_root_cause") != "UNKNOWN"
            or diagnosis.get("safe_next_diagnostic") != "CLOSED_ENUM_PROCESSED_PLAN_SUBPHASE_ONLY"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("new_reviewed_processed_plan_subphase_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 5
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append(
                "protected GA Processed-plan failed-attempt ledger is not exact or frozen"
            )
    ga_first_import_ledger_path = root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER
    ga_first_import_schema_path = root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_first_import_ledger = _load(ga_first_import_ledger_path)
        ga_first_import_schema = _load(ga_first_import_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA first-import failed-attempt ledger is missing or unreadable")
    else:
        ga_first_import_errors = list(
            Draft202012Validator(
                ga_first_import_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_first_import_ledger)
        )
        attempts = ga_first_import_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_first_import_ledger.get("completion_policy", {})
        claims = ga_first_import_ledger.get("claims", {})
        if (
            ga_first_import_errors
            or _sha256(ga_first_import_ledger_path)
            != FAILED_T0705_FIRST_IMPORT_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_first_import_schema_path)
            != FAILED_T0705_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_SHA256
            or attempt.get("sequence") != 6
            or delivery.get("pull_request_number") != 120
            or delivery.get("merge_commit_sha")
            != "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or workflow.get("run_id") != 30194651840
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or failure.get("reason_code") != "PROTECTED_GA_FIRST_IMPORT_RECOVERY_FAILED"
            or failure.get("failure_phase") != "FIRST_IMPORT_RECOVERY"
            or failure.get("exact_root_cause_claimed") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "private_repository_new_commits_during_attempt",
                    "private_repository_added_paths",
                    "private_repository_modified_paths",
                    "private_repository_removed_paths",
                    "raw_ciphertext_creations",
                    "processed_immutable_creations",
                    "processed_current_pointer_mutations",
                    "timeline_snapshot_mutations",
                    "timeline_state_mutations",
                    "timeline_publish_attempts",
                    "gmail_checkpoint_mutations",
                    "gmail_source_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("private_repository_head_changed") is not False
            or effects.get("gmail_mutation_api_reached") is not False
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
            or diagnosis.get("exact_root_cause") != "UNKNOWN"
            or diagnosis.get("safe_next_diagnostic")
            != "CLOSED_ENUM_FIRST_IMPORT_RECOVERY_SUBPHASE_ONLY"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("new_reviewed_first_import_subphase_candidate_allowed") is not True
            or policy.get("exact_repair_or_pass_closure_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 2
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 6
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA first-import failed-attempt ledger is not exact or frozen")
    ga_pointer_fetch_ledger_path = root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER
    ga_pointer_fetch_schema_path = root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA
    try:
        ga_pointer_fetch_ledger = _load(ga_pointer_fetch_ledger_path)
        ga_pointer_fetch_schema = _load(ga_pointer_fetch_schema_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("protected GA pointer-fetch failed-attempt ledger is missing or unreadable")
    else:
        ledger_errors = list(
            Draft202012Validator(
                ga_pointer_fetch_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_pointer_fetch_ledger)
        )
        attempts = ga_pointer_fetch_ledger.get("attempts", [])
        attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else {}
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        protocol = attempt.get("protocol_evidence", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_pointer_fetch_ledger.get("completion_policy", {})
        claims = ga_pointer_fetch_ledger.get("claims", {})
        if (
            ledger_errors
            or _sha256(ga_pointer_fetch_ledger_path)
            != FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_pointer_fetch_schema_path)
            != FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_SHA256
            or attempt.get("sequence") != 7
            or delivery.get("pull_request_number") != 122
            or delivery.get("merge_commit_sha")
            != "2133673b335a384657c8668b62a1c13055c212cd"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or workflow.get("run_id") != 30196968135
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or failure.get("reason_code") != "PROTECTED_GA_FIRST_IMPORT_POINTER_FETCH_FAILED"
            or failure.get("failure_phase") != "FIRST_IMPORT_POINTER_FETCH"
            or failure.get("exact_root_cause_claimed") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "private_repository_new_commits_during_attempt",
                    "private_repository_added_paths",
                    "private_repository_modified_paths",
                    "private_repository_removed_paths",
                    "raw_ciphertext_creations",
                    "processed_immutable_creations",
                    "processed_current_pointer_mutations",
                    "timeline_snapshot_mutations",
                    "timeline_state_mutations",
                    "timeline_publish_attempts",
                    "gmail_checkpoint_mutations",
                    "gmail_source_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("private_repository_head_changed") is not False
            or effects.get("gmail_mutation_api_reached") is not False
            or protocol.get("matching_private_repositories") != 1
            or protocol.get("current_pointer_objects") != 2
            or protocol.get("git_tree_blob_objects_valid") != 2
            or protocol.get("git_raw_media_objects_valid") != 2
            or protocol.get("contents_inline_representation_mismatches") != 1
            or protocol.get("canonical_git_blob_sha_bindings_valid") != 2
            or diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
            or diagnosis.get("exact_root_cause") != "UNKNOWN"
            or diagnosis.get("safe_next_repair")
            != "CONTENTS_METADATA_PLUS_EXACT_RAW_MEDIA_WITH_CANONICAL_GIT_BLOB_SHA_BINDING"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("exact_pointer_blob_recovery_repair_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 7
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA pointer-fetch failed-attempt ledger is not exact or frozen")
    ga_pointer_blob_ledger_path = root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER
    ga_pointer_blob_schema_path = root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_pointer_blob_ledger_path.is_file()
        or ga_pointer_blob_ledger_path.is_symlink()
        or not ga_pointer_blob_schema_path.is_file()
        or ga_pointer_blob_schema_path.is_symlink()
    ):
        errors.append("protected GA pointer-blob failed-attempt ledger is missing or unsafe")
    else:
        ga_pointer_blob_ledger = _load(ga_pointer_blob_ledger_path)
        ga_pointer_blob_schema = _load(ga_pointer_blob_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_pointer_blob_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_pointer_blob_ledger)
        )
        predecessor = ga_pointer_blob_ledger.get("predecessor_control", {})
        attempt = ga_pointer_blob_ledger.get("attempts", [{}])[0]
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        transition = attempt.get("external_state_transition", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_pointer_blob_ledger.get("completion_policy", {})
        claims = ga_pointer_blob_ledger.get("claims", {})
        frozen_heads = [
            "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f",  # pragma: allowlist secret
            "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0",  # pragma: allowlist secret
            "cc7c8af9a40122a61ee2549fb365df813cbd4f16",  # pragma: allowlist secret
            "4c207ad539754166fae6642ff4e6850438d3e2fc",  # pragma: allowlist secret
            "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4",  # pragma: allowlist secret
            "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7",  # pragma: allowlist secret
            "2133673b335a384657c8668b62a1c13055c212cd",  # pragma: allowlist secret
            "8b6faaf9059661edc3153352b8787ddbc4f733f3",  # pragma: allowlist secret
        ]
        if (
            ledger_errors
            or _sha256(ga_pointer_blob_ledger_path)
            != FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_pointer_blob_schema_path)
            != FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("prior_run_contract_sha256")
            != "2220fb87d2bd089242254b998786aeae4ddd1d83f62bec26d9140af562a1b07d"  # pragma: allowlist secret  # noqa: E501
            or predecessor.get("seventh_attempt_ledger_sha256")
            != FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SHA256
            or predecessor.get("seventh_attempt_ledger_schema_sha256")
            != FAILED_T0705_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("prior_failed_workflow_head_shas") != frozen_heads[:-1]
            or predecessor.get("prior_failed_head_dispatches_after_freeze") != 0
            or predecessor.get("prior_failed_head_reruns_after_freeze") != 0
            or attempt.get("sequence") != 8
            or delivery.get("pull_request_number") != 123
            or delivery.get("pull_request_head_sha")
            != "9858f9f091363ac21e9ebc4a24ceaa073c180521"  # pragma: allowlist secret
            or delivery.get("merge_commit_parent_sha")
            != "2133673b335a384657c8668b62a1c13055c212cd"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha")
            != "8b6faaf9059661edc3153352b8787ddbc4f733f3"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or delivery.get("terminal_checks") != 40
            or delivery.get("successful_checks") != 35
            or delivery.get("failed_checks") != 0
            or delivery.get("skipped_checks") != 5
            or delivery.get("neutral_checks") != 0
            or workflow.get("run_id") != 30199215335
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or failure.get("reason_code") != "PROTECTED_GA_FIRST_IMPORT_POINTER_FETCH_FAILED"
            or failure.get("failure_phase") != "FIRST_IMPORT_POINTER_FETCH"
            or failure.get("installation_token_failure_class") != "UNCLASSIFIED"
            or failure.get("exact_root_cause_claimed") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "private_repository_new_commits_during_attempt",
                    "private_repository_added_paths",
                    "private_repository_modified_paths",
                    "private_repository_removed_paths",
                    "raw_ciphertext_creations",
                    "processed_immutable_creations",
                    "processed_current_pointer_mutations",
                    "timeline_snapshot_mutations",
                    "timeline_state_mutations",
                    "timeline_publish_attempts",
                    "gmail_checkpoint_mutations",
                    "gmail_source_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("matching_private_repositories") != 1
            or effects.get("private_repository_head_changed") is not False
            or effects.get("gmail_mutation_api_reached") is not False
            or effects.get("identity_plaintext_cleanup") != "PASS"
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or effects.get("protected_environment_secret_names") != 8
            or any(
                effects.get(key) is not False
                for key in (
                    "exact_private_locator_disclosed",
                    "exact_private_path_disclosed",
                    "exact_source_identifier_disclosed",
                    "exact_mailbox_counts_disclosed",
                )
            )
            or transition.get("occurred_after_failed_attempt") is not True
            or transition.get(
                "owner_confirmed_github_app_linked_to_existing_single_private_data_repository"
            )
            is not True
            or transition.get("runtime_installation_repository_scope_verification")
            != "PENDING_NEW_EXACT_HEAD_PROTECTED_ORACLE"
            or transition.get("retroactive_root_cause_attribution") is not False
            or transition.get("new_private_repository_created") is not False
            or transition.get("new_github_app_created") is not False
            or transition.get("private_repository_locator_disclosed") is not False
            or diagnosis.get("observable_failure_boundary")
            != (
                "WITHIN_FIRST_IMPORT_POINTER_FETCH_BEFORE_POINTER_DECRYPT_OR_ANY_NEW_"
                "PROCESSED_WRITE_OR_GMAIL_MUTATION"
            )
            or diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
            or diagnosis.get("exact_root_cause") != "UNKNOWN"
            or diagnosis.get("exact_root_cause_claimed") is not False
            or diagnosis.get("safe_next_action")
            != "NEW_EXACT_HEAD_APP_REPOSITORY_SCOPE_ACTIVATION_RECOVERY_REHEARSAL"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_failed_workflow_head_shas") != frozen_heads
            or policy.get("exact_app_repository_scope_activation_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 8
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA pointer-blob failed-attempt ledger is not exact or frozen")
    ga_canonical_blob_ledger_path = root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER
    ga_canonical_blob_schema_path = root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_canonical_blob_ledger_path.is_file()
        or ga_canonical_blob_ledger_path.is_symlink()
        or not ga_canonical_blob_schema_path.is_file()
        or ga_canonical_blob_schema_path.is_symlink()
    ):
        errors.append("protected GA canonical-blob failed-attempt ledger is missing or unsafe")
    else:
        ga_canonical_blob_ledger = _load(ga_canonical_blob_ledger_path)
        ga_canonical_blob_schema = _load(ga_canonical_blob_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_canonical_blob_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_canonical_blob_ledger)
        )
        predecessor = ga_canonical_blob_ledger.get("predecessor_control", {})
        attempt = ga_canonical_blob_ledger.get("attempts", [{}])[0]
        delivery = attempt.get("delivery", {})
        workflow = attempt.get("workflow", {})
        jobs = attempt.get("jobs", {})
        failure = attempt.get("public_failure", {})
        effects = attempt.get("effects", {})
        scope_activation = attempt.get("scope_activation", {})
        protocol = attempt.get("live_protocol_ab", {})
        diagnosis = attempt.get("diagnosis", {})
        policy = ga_canonical_blob_ledger.get("completion_policy", {})
        claims = ga_canonical_blob_ledger.get("claims", {})
        frozen_heads = [
            "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f",  # pragma: allowlist secret
            "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0",  # pragma: allowlist secret
            "cc7c8af9a40122a61ee2549fb365df813cbd4f16",  # pragma: allowlist secret
            "4c207ad539754166fae6642ff4e6850438d3e2fc",  # pragma: allowlist secret
            "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4",  # pragma: allowlist secret
            "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7",  # pragma: allowlist secret
            "2133673b335a384657c8668b62a1c13055c212cd",  # pragma: allowlist secret
            "8b6faaf9059661edc3153352b8787ddbc4f733f3",  # pragma: allowlist secret
            "6f82e738611e0d2eeeadd2507f738c9e269c91e0",  # pragma: allowlist secret
        ]
        if (
            ledger_errors
            or _sha256(ga_canonical_blob_ledger_path)
            != FAILED_T0705_CANONICAL_BLOB_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_canonical_blob_schema_path)
            != FAILED_T0705_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("prior_run_contract_sha256")
            != "88c19bfb0c95b1ba75d47738899b04f648eb6c53b2bbc0ed217749d72154e0a7"  # pragma: allowlist secret  # noqa: E501
            or predecessor.get("eighth_attempt_ledger_sha256")
            != FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SHA256
            or predecessor.get("eighth_attempt_ledger_schema_sha256")
            != FAILED_T0705_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_SHA256
            or predecessor.get("prior_failed_workflow_head_shas") != frozen_heads[:-1]
            or predecessor.get("prior_failed_head_dispatches_after_freeze") != 0
            or predecessor.get("prior_failed_head_reruns_after_freeze") != 0
            or attempt.get("sequence") != 9
            or delivery.get("pull_request_number") != 126
            or delivery.get("pull_request_head_sha")
            != "f82d9ecd99aa809fd8a27d3323bf7fdffca7bf45"  # pragma: allowlist secret
            or delivery.get("merge_commit_parent_sha")
            != "c3acc31eda47505bf07b9cf7e53cd0391e229f5d"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha")
            != "6f82e738611e0d2eeeadd2507f738c9e269c91e0"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or workflow.get("run_id") != 30201167052
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_gate", {}).get("status") != "PASS"
            or jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
            or jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            or jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
            or failure.get("reason_code") != "PROTECTED_GA_FIRST_IMPORT_POINTER_FETCH_FAILED"
            or failure.get("failure_phase") != "FIRST_IMPORT_POINTER_FETCH"
            or failure.get("exact_root_cause_claimed") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "private_repository_new_commits_during_attempt",
                    "raw_ciphertext_creations",
                    "processed_immutable_creations",
                    "processed_current_pointer_mutations",
                    "timeline_snapshot_mutations",
                    "timeline_state_mutations",
                    "timeline_publish_attempts",
                    "gmail_checkpoint_mutations",
                    "gmail_source_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("matching_private_repositories") != 1
            or effects.get("private_repository_head_changed") is not False
            or effects.get("gmail_mutation_api_reached") is not False
            or effects.get("identity_plaintext_cleanup") != "PASS"
            or effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
            or effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
            or effects.get("protected_environment_secret_names") != 8
            or any(
                effects.get(key) is not False
                for key in (
                    "exact_private_locator_disclosed",
                    "exact_private_path_disclosed",
                    "exact_source_identifier_disclosed",
                    "exact_mailbox_counts_disclosed",
                )
            )
            or scope_activation.get("runtime_exact_installation_repository_scope")
            != "PASS_BEFORE_GMAIL_CREDENTIAL_EXCHANGE"
            or scope_activation.get("new_private_repository_created") is not False
            or scope_activation.get("new_github_app_created") is not False
            or protocol.get("contents_metadata_shape") != "ALL_PASS"
            or protocol.get("contents_raw_media_http_status") != "ALL_200"
            or protocol.get("contents_raw_media_canonical_age_size_sha") != "PARTIAL_ONE_FAILED"
            or protocol.get("git_blob_api_encoding_sha_size_age") != "ALL_PASS"
            or protocol.get("patched_production_adapter_recovery") != "ALL_PASS"
            or diagnosis.get("exact_protected_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
            or diagnosis.get("reproduced_root_cause")
            != "CONTENTS_RAW_MEDIA_RETURNED_NON_CANONICAL_BODY_FOR_ONE_CURRENT_POINTER"
            or diagnosis.get("root_cause_basis")
            != "LIVE_REPRODUCED_SAME_PRODUCTION_ADAPTER_AND_UNCHANGED_REMOTE_HEAD"
            or diagnosis.get("safe_next_action")
            != "NEW_EXACT_HEAD_CANONICAL_GIT_BLOB_RECOVERY_REHEARSAL"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_failed_workflow_head_shas") != frozen_heads
            or policy.get("exact_canonical_git_blob_candidate_allowed") is not True
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("historical_ga_rehearsal_dispatches_consumed") != 9
            or policy.get("historical_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append(
                "protected GA canonical-blob failed-attempt ledger is not exact or frozen"
            )
    ga_preflight_ledger_path = root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER
    ga_preflight_schema_path = root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_preflight_ledger_path.is_file()
        or ga_preflight_ledger_path.is_symlink()
        or not ga_preflight_schema_path.is_file()
        or ga_preflight_schema_path.is_symlink()
    ):
        errors.append("protected GA candidate-preflight ledger is missing or unsafe")
    else:
        ga_preflight_ledger = _load(ga_preflight_ledger_path)
        ga_preflight_schema = _load(ga_preflight_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_preflight_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_preflight_ledger)
        )
        delivery = ga_preflight_ledger.get("delivery", {})
        workflow = ga_preflight_ledger.get("workflow", {})
        jobs = ga_preflight_ledger.get("jobs", {})
        failure = ga_preflight_ledger.get("failure", {})
        effects = ga_preflight_ledger.get("effects", {})
        policy = ga_preflight_ledger.get("completion_policy", {})
        claims = ga_preflight_ledger.get("claims", {})
        preflight_head = "26949ab5031a21b0c515c282c9ef06ff9417e058"  # pragma: allowlist secret
        if (
            ledger_errors
            or _sha256(ga_preflight_ledger_path)
            != FAILED_T0705_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_preflight_schema_path)
            != FAILED_T0705_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_preflight_ledger.get("scope") != "PRE_SECRET_EXACT_MAIN_CANDIDATE_VALIDATION_ONLY"
            or delivery.get("pull_request_number") != 129
            or delivery.get("merge_commit_sha") != preflight_head
            or workflow.get("workflow_head_sha") != preflight_head
            or workflow.get("run_id") != 30203291213
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_context") != "PASS"
            or jobs.get("candidate_validation") != "FAILED"
            or jobs.get("protected_environment") != "SKIPPED"
            or jobs.get("live_schedule_hold") != "SKIPPED"
            or failure.get("phase") != "PRE_SECRET_CANDIDATE_VALIDATION"
            or failure.get("reason_code") != "RUFF_FORMAT_CHECK_REJECTED"
            or failure.get("finding") != "PROCESSED_COMMIT_WOULD_BE_REFORMATTED"
            or failure.get("exact_root_cause_claimed") is not True
            or effects.get("protected_environment_entered") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "protected_secret_names_injected",
                    "gmail_api_calls",
                    "private_repository_calls",
                    "gmail_mutations",
                    "private_repository_mutations",
                    "timeline_mutations",
                    "checkpoint_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("one_shot_authority_variable_after_failure") != "ABSENT"
            or effects.get("production_enablement_variable_after_failure") != "ABSENT"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_candidate_preflight_head_shas") != [preflight_head]
            or policy.get("next_candidate_scope")
            != "FORMAT_ONLY_PLUS_DERIVED_HASH_STATUS_AND_PACKAGE_BINDINGS"
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("protected_ga_rehearsal_dispatches_consumed") != 9
            or policy.get("protected_ga_rehearsal_reruns") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA candidate-preflight ledger is not exact or frozen")
    ga_authority_ledger_path = root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER
    ga_authority_schema_path = root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_authority_ledger_path.is_file()
        or ga_authority_ledger_path.is_symlink()
        or not ga_authority_schema_path.is_file()
        or ga_authority_schema_path.is_symlink()
    ):
        errors.append("protected GA authority-context ledger is missing or unsafe")
    else:
        ga_authority_ledger = _load(ga_authority_ledger_path)
        ga_authority_schema = _load(ga_authority_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_authority_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_authority_ledger)
        )
        delivery = ga_authority_ledger.get("delivery", {})
        workflow = ga_authority_ledger.get("workflow", {})
        jobs = ga_authority_ledger.get("jobs", {})
        failure = ga_authority_ledger.get("failure", {})
        effects = ga_authority_ledger.get("effects", {})
        policy = ga_authority_ledger.get("completion_policy", {})
        claims = ga_authority_ledger.get("claims", {})
        authority_head = "9c79b92bcdf8b027727963dfe52bd183a170954c"  # pragma: allowlist secret
        if (
            ledger_errors
            or _sha256(ga_authority_ledger_path)
            != FAILED_T0705_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_authority_schema_path)
            != FAILED_T0705_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_authority_ledger.get("scope") != "PRE_CHECKOUT_PRE_SECRET_AUTHORITY_CONTEXT_ONLY"
            or delivery.get("pull_request_number") != 130
            or delivery.get("pull_request_head_sha")
            != "ca79b2211ffcda40f13dce068db38aa8143957e4"  # pragma: allowlist secret
            or delivery.get("merge_commit_parent_sha")
            != "26949ab5031a21b0c515c282c9ef06ff9417e058"  # pragma: allowlist secret
            or delivery.get("merge_commit_sha") != authority_head
            or workflow.get("workflow_head_sha") != authority_head
            or workflow.get("run_id") != 30204453383
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_context") != "FAILED"
            or jobs.get("candidate_validation") != "SKIPPED"
            or jobs.get("protected_environment") != "SKIPPED"
            or jobs.get("live_schedule_hold") != "SKIPPED"
            or failure.get("phase") != "PRE_CHECKOUT_AUTHORITY_CONTEXT"
            or failure.get("reason_code") != "ONE_SHOT_AUTHORITY_VARIABLE_SCOPE_MISMATCH"
            or failure.get("finding") != "AUTHORITY_JOB_CANNOT_READ_ENVIRONMENT_SCOPED_VARIABLE"
            or failure.get("exact_root_cause_claimed") is not True
            or effects.get("checkout_started") is not False
            or effects.get("protected_environment_entered") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "protected_secret_names_injected",
                    "gmail_api_calls",
                    "private_repository_calls",
                    "gmail_mutations",
                    "private_repository_mutations",
                    "timeline_mutations",
                    "checkpoint_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("environment_scoped_one_shot_authority_after_cleanup") != "ABSENT"
            or effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
            or effects.get("production_enablement_variable_after_failure") != "ABSENT"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_authority_context_head_shas") != [authority_head]
            or policy.get("next_candidate_scope")
            != "REPOSITORY_SCOPED_ONE_SHOT_AUTHORITY_PLUS_DERIVED_BINDINGS_ONLY"
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("protected_ga_rehearsal_dispatches_consumed") != 9
            or policy.get("protected_ga_rehearsal_reruns") != 0
            or policy.get("protected_environment_entries_for_failed_dispatch") != 0
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or any(value is not False for value in claims.values())
        ):
            errors.append("protected GA authority-context ledger is not exact or frozen")
    ga_schedule_ledger_path = root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER
    ga_schedule_schema_path = root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_schedule_ledger_path.is_file()
        or ga_schedule_ledger_path.is_symlink()
        or not ga_schedule_schema_path.is_file()
        or ga_schedule_schema_path.is_symlink()
    ):
        errors.append("protected GA schedule-planning ledger is missing or unsafe")
    else:
        ga_schedule_ledger = _load(ga_schedule_ledger_path)
        ga_schedule_schema = _load(ga_schedule_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_schedule_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_schedule_ledger)
        )
        workflow = ga_schedule_ledger.get("workflow", {})
        jobs = ga_schedule_ledger.get("jobs", {})
        failure = ga_schedule_ledger.get("failure", {})
        effects = ga_schedule_ledger.get("effects", {})
        policy = ga_schedule_ledger.get("completion_policy", {})
        claims = ga_schedule_ledger.get("claims", {})
        schedule_head = "27886f54a30a12ca7992a908e97340d1d8234430"
        if (
            ledger_errors
            or _sha256(ga_schedule_ledger_path)
            != FAILED_T0705_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_schedule_schema_path)
            != FAILED_T0705_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_schedule_ledger.get("scope")
            != "PROTECTED_ENVIRONMENT_PRE_DATA_PLANE_SCHEDULE_PLANNING_ONLY"
            or workflow.get("workflow_head_sha") != schedule_head
            or workflow.get("run_id") != 30205924236
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_context") != "PASS"
            or jobs.get("candidate_validation") != "PASS"
            or jobs.get("protected_environment") != "FAILED"
            or jobs.get("plaintext_cleanup") != "PASS"
            or failure.get("phase") != "SCHEDULE_PLANNING"
            or failure.get("reason_code") != "PROTECTED_GA_SCHEDULE_PLANNING_FAILED"
            or failure.get("finding") != "WALL_CLOCK_BEFORE_0430_REJECTED_SCHEDULE_REHEARSAL"
            or failure.get("exact_root_cause_claimed") is not True
            or failure.get("taskpack_fake_clock_policy_was_not_applied") is not True
            or effects.get("protected_environment_entered") is not True
            or effects.get("protected_secret_names_injected") != 8
            or effects.get("schedule_checkpoint_recovery") != "PASS"
            or effects.get("private_repository_read_calls") != "NONZERO_WITHIN_CONFIGURED_BUDGET"
            or any(
                effects.get(key) != 0
                for key in (
                    "gmail_api_calls",
                    "verified_full_raw_reads",
                    "gmail_mutations",
                    "private_repository_mutations",
                    "raw_mutations",
                    "processed_mutations",
                    "timeline_mutations",
                    "checkpoint_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("tmpfs_plaintext_cleanup") != "PASS"
            or effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
            or effects.get("production_enablement_variable_after_failure") != "ABSENT"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_schedule_planning_head_shas") != [schedule_head]
            or policy.get("next_candidate_scope")
            != "DETERMINISTIC_HISTORICAL_REPLAY_CLOCK_ONLY_PLUS_DERIVED_BINDINGS"
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("protected_ga_rehearsal_dispatches_consumed") != 10
            or policy.get("protected_ga_rehearsal_reruns") != 0
            or policy.get("real_time_wait_allowed") is not False
            or policy.get("rehearsal_clock_fixture_utc") != "2026-07-26T01:00:00Z"
            or claims.get("candidate_validation_executed") is not True
            or claims.get("protected_ga_data_plane_executed") is not False
            or any(
                claims.get(key) is not False
                for key in (
                    "production_health_claimed",
                    "t0705_pass_claimed",
                    "stage7_complete_claimed",
                    "final_acceptance_claimed",
                    "final_publication_claimed",
                )
            )
        ):
            errors.append("protected GA schedule-planning ledger is not exact or frozen")
    ga_auth_clock_ledger_path = root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER
    ga_auth_clock_schema_path = root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_auth_clock_ledger_path.is_file()
        or ga_auth_clock_ledger_path.is_symlink()
        or not ga_auth_clock_schema_path.is_file()
        or ga_auth_clock_schema_path.is_symlink()
    ):
        errors.append("protected GA authentication-clock ledger is missing or unsafe")
    else:
        ga_auth_clock_ledger = _load(ga_auth_clock_ledger_path)
        ga_auth_clock_schema = _load(ga_auth_clock_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_auth_clock_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_auth_clock_ledger)
        )
        workflow = ga_auth_clock_ledger.get("workflow", {})
        jobs = ga_auth_clock_ledger.get("jobs", {})
        failure = ga_auth_clock_ledger.get("failure", {})
        effects = ga_auth_clock_ledger.get("effects", {})
        policy = ga_auth_clock_ledger.get("completion_policy", {})
        claims = ga_auth_clock_ledger.get("claims", {})
        auth_clock_head = "c2c057b449fe1cbbd470867c274833242e3f139d"
        if (
            ledger_errors
            or _sha256(ga_auth_clock_ledger_path)
            != FAILED_T0705_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_auth_clock_schema_path)
            != FAILED_T0705_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_auth_clock_ledger.get("scope")
            != "PROTECTED_ENVIRONMENT_PRE_REPOSITORY_RESOLUTION_GITHUB_APP_AUTHENTICATION_ONLY"
            or workflow.get("workflow_head_sha") != auth_clock_head
            or workflow.get("run_id") != 30207628898
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_context") != "PASS"
            or jobs.get("candidate_validation") != "PASS"
            or jobs.get("protected_environment") != "FAILED"
            or jobs.get("live_schedule_hold") != "SKIPPED"
            or jobs.get("plaintext_cleanup") != "PASS"
            or failure.get("phase") != "GITHUB_APP_TOKEN"
            or failure.get("reason_code") != "PROTECTED_GA_GITHUB_APP_TOKEN_FAILED"
            or failure.get("installation_token_failure_class") != "AUTHENTICATION_REJECTED"
            or failure.get("finding") != "HISTORICAL_REHEARSAL_CLOCK_REUSED_FOR_SECURITY_JWT"
            or failure.get("public_payload_exact_root_cause_claimed") is not False
            or failure.get("ledger_exact_root_cause_claimed") is not True
            or effects.get("protected_environment_entered") is not True
            or effects.get("protected_secret_names_injected") != 8
            or effects.get("github_app_token_exchange") != "AUTHENTICATION_REJECTED"
            or effects.get("repository_resolution_reached") is not False
            or effects.get("gmail_oauth_exchange_reached") is not False
            or any(
                effects.get(key) != 0
                for key in (
                    "gmail_api_calls",
                    "verified_full_raw_reads",
                    "private_repository_calls",
                    "gmail_mutations",
                    "private_repository_mutations",
                    "raw_mutations",
                    "processed_mutations",
                    "timeline_mutations",
                    "checkpoint_mutations",
                    "platform_schedule_events",
                )
            )
            or effects.get("tmpfs_plaintext_cleanup") != "PASS"
            or effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
            or effects.get("production_enablement_variable_after_failure") != "ABSENT"
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_authentication_clock_head_shas") != [auth_clock_head]
            or policy.get("next_candidate_scope")
            != "SECURITY_AND_SCHEDULE_CLOCK_DECOUPLING_ONLY_PLUS_DERIVED_BINDINGS"
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("protected_ga_rehearsal_dispatches_consumed") != 11
            or policy.get("protected_ga_rehearsal_reruns") != 0
            or policy.get("security_clock_mode") != "LIVE_UTC"
            or policy.get("schedule_clock_mode") != "DETERMINISTIC_HISTORICAL_REPLAY_FIXTURE"
            or policy.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T13:00:00Z"
            or policy.get("known_data_effect_upper_bound_utc") != "2026-07-26T05:44:53Z"
            or policy.get("real_time_wait_allowed") is not False
            or claims.get("candidate_validation_executed") is not True
            or claims.get("protected_ga_data_plane_executed") is not False
            or any(
                claims.get(key) is not False
                for key in (
                    "production_health_claimed",
                    "t0705_pass_claimed",
                    "stage7_complete_claimed",
                    "final_acceptance_claimed",
                    "final_publication_claimed",
                )
            )
        ):
            errors.append("protected GA authentication-clock ledger is not exact or frozen")
    ga_raw_ledger_path = root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER
    ga_raw_schema_path = root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_raw_ledger_path.is_file()
        or ga_raw_ledger_path.is_symlink()
        or not ga_raw_schema_path.is_file()
        or ga_raw_schema_path.is_symlink()
    ):
        errors.append("protected GA Raw-recovery ledger is missing or unsafe")
    else:
        ga_raw_ledger = _load(ga_raw_ledger_path)
        ga_raw_schema = _load(ga_raw_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_raw_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_raw_ledger)
        )
        workflow = ga_raw_ledger.get("workflow", {})
        jobs = ga_raw_ledger.get("jobs", {})
        failure = ga_raw_ledger.get("failure", {})
        effects = ga_raw_ledger.get("effects", {})
        topology = ga_raw_ledger.get("remote_commit_topology", {})
        replay = ga_raw_ledger.get("read_only_representation_ab", {})
        policy = ga_raw_ledger.get("completion_policy", {})
        claims = ga_raw_ledger.get("claims", {})
        raw_head = "0d0b6afd6a0cde606230a3df7378bdd90586de5d"
        if (
            ledger_errors
            or _sha256(ga_raw_ledger_path) != FAILED_T0705_RAW_RECOVERY_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_raw_schema_path) != FAILED_T0705_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_raw_ledger.get("scope")
            != "PROTECTED_ENVIRONMENT_VERIFIED_PIPELINE_RAW_RECOVERY_ONLY"
            or workflow.get("workflow_head_sha") != raw_head
            or workflow.get("run_id") != 30209560542
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or jobs.get("authority_context") != "PASS"
            or jobs.get("candidate_validation") != "PASS"
            or jobs.get("protected_environment") != "FAILED"
            or jobs.get("live_schedule_hold") != "SKIPPED"
            or jobs.get("plaintext_cleanup") != "PASS"
            or failure.get("phase") != "RAW_RECOVERY"
            or failure.get("reason_code") != "PROTECTED_GA_RAW_RECOVERY_FAILED"
            or failure.get("finding")
            != "CONTENTS_RAW_MEDIA_REPRESENTATION_DIFFERS_FROM_CANONICAL_GIT_BLOB"
            or failure.get("public_payload_exact_root_cause_claimed") is not False
            or failure.get("ledger_exact_root_cause_claimed") is not True
            or effects.get("protected_environment_entered") is not True
            or effects.get("protected_secret_names_injected") != 8
            or effects.get("github_app_repository_scope") != "PASS"
            or effects.get("gmail_oauth_exchange") != "PASS"
            or effects.get("first_candidate_full_recovery_before_trash") is not True
            or effects.get("first_candidate_second_verification_before_trash") is not True
            or effects.get("first_candidate_trash_outcome") != "CONFIRMED_OR_ALREADY_TRASHED"
            or effects.get("gmail_exact_message_trash_api_calls_claimed") is not False
            or effects.get("second_candidate_raw_commit_reached") is not True
            or effects.get("second_candidate_raw_recovery_completed") is not False
            or effects.get("timeline_mutations") != 0
            or effects.get("checkpoint_mutations") != 0
            or effects.get("platform_schedule_events") != 0
            or effects.get("tmpfs_plaintext_cleanup") != "PASS"
            or effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
            or effects.get("production_enablement_variable_after_failure") != "ABSENT"
            or topology.get("private_repository_locator_disclosed") is not False
            or topology.get("private_object_paths_disclosed") is not False
            or topology.get("timeline_or_checkpoint_commit_present") is not False
            or replay.get("network_mutations") != 0
            or replay.get("contents_raw_media", {}).get("declared_size_match") is not False
            or replay.get("contents_raw_media", {}).get("canonical_git_blob_sha_match") is not False
            or replay.get("metadata_addressed_git_blob", {}).get("response_sha_match") is not True
            or replay.get("metadata_addressed_git_blob", {}).get("declared_size_match") is not True
            or replay.get("metadata_addressed_git_blob", {}).get("decoded_size_match") is not True
            or replay.get("metadata_addressed_git_blob", {}).get("age_envelope_valid") is not True
            or replay.get("metadata_addressed_git_blob", {}).get("canonical_git_blob_sha_match")
            is not True
            or policy.get("same_head_rerun_allowed") is not False
            or policy.get("failed_head_redispatch_allowed") is not False
            or policy.get("frozen_raw_recovery_head_shas") != [raw_head]
            or policy.get("next_candidate_dispatch_limit") != 1
            or policy.get("protected_ga_rehearsal_dispatches_consumed") != 12
            or policy.get("protected_ga_candidate_preflight_dispatches_consumed") != 5
            or policy.get("protected_ga_rehearsal_reruns") != 0
            or policy.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T19:00:00Z"
            or policy.get("known_data_effect_upper_bound_utc") != "2026-07-26T16:12:21Z"
            or policy.get("real_time_wait_allowed") is not False
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or claims.get("candidate_validation_executed") is not True
            or claims.get("protected_ga_data_plane_executed") is not True
            or claims.get("exact_gmail_mutation_call_count_claimed") is not False
            or any(
                claims.get(key) is not False
                for key in (
                    "production_health_claimed",
                    "t0705_pass_claimed",
                    "stage7_complete_claimed",
                    "final_acceptance_claimed",
                    "final_publication_claimed",
                )
            )
        ):
            errors.append("protected GA Raw-recovery ledger is not exact or frozen")
    ga_trash_ledger_path = root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER
    ga_trash_schema_path = root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA
    if (
        not ga_trash_ledger_path.is_file()
        or ga_trash_ledger_path.is_symlink()
        or not ga_trash_schema_path.is_file()
        or ga_trash_schema_path.is_symlink()
    ):
        errors.append("protected GA Trash-confirmation ledger is missing or unsafe")
    else:
        ga_trash_ledger = _load(ga_trash_ledger_path)
        ga_trash_schema = _load(ga_trash_schema_path)
        ledger_errors = list(
            Draft202012Validator(
                ga_trash_schema,
                format_checker=FormatChecker(),
            ).iter_errors(ga_trash_ledger)
        )
        workflow = ga_trash_ledger.get("workflow", {})
        failure = ga_trash_ledger.get("failure", {})
        effects = ga_trash_ledger.get("effects", {})
        topology = ga_trash_ledger.get("remote_commit_topology", {})
        probe = ga_trash_ledger.get("read_only_gmail_representation_probe", {})
        policy = ga_trash_ledger.get("remediation_contract", {})
        claims = ga_trash_ledger.get("claims", {})
        trash_head = "4b7442bb635ea1e7cf5a814c3c56047aa288d594"
        if (
            ledger_errors
            or _sha256(ga_trash_ledger_path)
            != FAILED_T0705_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SHA256
            or _sha256(ga_trash_schema_path)
            != FAILED_T0705_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_SHA256
            or ga_trash_ledger.get("scope")
            != "PROTECTED_ENVIRONMENT_VERIFIED_PIPELINE_TRASH_CONFIRMATION_ONLY"
            or workflow.get("workflow_head_sha") != trash_head
            or workflow.get("run_id") != 30212089899
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or failure.get("phase") != "TRASH_MUTATION"
            or failure.get("reason_code") != "PROTECTED_GA_TRASH_MUTATION_FAILED"
            or failure.get("public_payload_exact_root_cause_claimed") is not False
            or failure.get("ledger_exact_root_cause_claimed") is not False
            or effects.get("raw_and_processed_remote_recovery_reached_before_failure") is not True
            or effects.get("timeline_mutations") != 0
            or effects.get("checkpoint_mutations") != 0
            or effects.get("tmpfs_plaintext_cleanup") != "PASS"
            or effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
            or effects.get("production_enablement_variable_after_failure") != "ABSENT"
            or topology.get("private_repository_locator_disclosed") is not False
            or topology.get("private_object_paths_disclosed") is not False
            or topology.get("timeline_or_checkpoint_commit_present") is not False
            or probe.get("message_bodies_read") is not False
            or probe.get("message_mutations") != 0
            or probe.get("minimal_response_contains_nonempty_snippet") is not True
            or probe.get("exact_partial_response_required") != "id,labelIds"
            or policy.get("minimal_confirmation_fields") != "id,labelIds"
            or policy.get("uncertain_trash_response_label_reads_maximum") != 1
            or policy.get("trash_mutation_retries_inside_attempt_maximum") != 0
            or policy.get("frozen_trash_confirmation_head_shas") != [trash_head]
            or policy.get("protected_ga_rehearsal_dispatches_consumed") != 13
            or policy.get("protected_ga_candidate_preflight_dispatches_consumed") != 5
            or policy.get("protected_ga_rehearsal_reruns") != 0
            or policy.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T19:00:00Z"
            or policy.get("known_data_effect_upper_bound_utc") != "2026-07-26T17:20:17Z"
            or policy.get("real_time_wait_allowed") is not False
            or policy.get("t0705_complete") is not False
            or policy.get("t0706_authorized") is not False
            or policy.get("final_publication_authorized") is not False
            or claims.get("protected_ga_data_plane_executed") is not True
            or claims.get("exact_protected_failure_root_cause_claimed") is not False
            or claims.get("exact_gmail_mutation_call_count_claimed") is not False
        ):
            errors.append("protected GA Trash-confirmation ledger is not exact or frozen")
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S7"}
    required_blockers = {
        "T0702": {"FINAL_ACCEPTANCE_AND_POST_BETA_STAGE7_PHASES_NOT_RUN"},
        "T0703": {
            "FINAL_ACCEPTANCE_AND_POST_M3_STAGE7_PHASES_NOT_RUN",
        },
        "T0704": {
            "T0705_NOT_AUTHORIZED_IN_CURRENT_RUN",
            "FINAL_ACCEPTANCE_AND_POST_BLUE_GREEN_STAGE7_PHASES_NOT_RUN",
        },
        "T0705": {
            "T0705_THIRTEEN_PROTECTED_FAILED_HEADS_FROZEN",
            "T0705_TRASH_CONFIRMATION_RECOVERY_PENDING",
            "T0705_PROTECTED_RECEIPT_NOT_BOUND",
            "FINAL_ACCEPTANCE_AND_POST_GA_STAGE7_PHASES_NOT_RUN",
        },
        "T0706": {
            "GA_NOT_COMPLETE",
            "CODEX_AUTOMATION_NOT_CREATED",
        },
        "T0707": {
            "CODEX_AUTOMATION_TASK_PREDECESSOR_NOT_COMPLETE",
            "PROTECTED_RECOVERY_SAMPLE_ADAPTERS_NOT_PROVISIONED",
            "OWNER_RECOVERY_KEY_FILE_NOT_PROVIDED",
            "REAL_RECOVERY_KEY_DRILL_NOT_RUN",
        },
        "T0708": {
            "RECOVERY_DRILL_TASK_PREDECESSOR_NOT_COMPLETE",
            "PROTECTED_PATCH_CANDIDATE_NOT_PROVISIONED",
            "PROTECTED_PATCH_CANARY_ADAPTER_NOT_PROVISIONED",
            "PROTECTED_OPERATIONS_NOT_RUN",
        },
    }
    resolved_local_blockers = {
        "T0702": {"PROTECTED_RUNTIME_BOOTSTRAP_NOT_IMPLEMENTED"},
        "T0703": {
            "M3_PROCESSED_CANARY_RUNTIME_NOT_IMPLEMENTED",
            "M3_SEVEN_DAY_WINDOW_NOT_STARTED",
        },
        "T0704": {
            "BLUE_GREEN_AND_TIMELINE_AGGREGATION_RUNTIME_NOT_IMPLEMENTED",
            "BLUE_GREEN_FOURTEEN_DAY_WINDOW_NOT_STARTED",
        },
        "T0705": {"GA_FULL_PIPELINE_ENTRY_NOT_IMPLEMENTED"},
        "T0707": {"PROTECTED_RECOVERY_DRILL_ENTRY_NOT_IMPLEMENTED"},
        "T0708": {"PROTECTED_PATCH_LIFECYCLE_WORKFLOW_NOT_IMPLEMENTED"},
    }
    expected_oracle_status = {
        "T0701": "PASS",
        "T0702": "PASS",
        "T0703": "PASS",
        "T0704": "PASS",
        "T0705": "FAILED",
    }
    for index, task_id in enumerate(STAGE7_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid Stage 7 evidence schema for {task_id}")
            continue
        for check in record["checks"]:
            evidence_ref = check["evidence_ref"]
            matches = EVIDENCE_PATH.findall(evidence_ref)
            if "../" in evidence_ref or not matches:
                errors.append(f"invalid evidence reference for {task_id}")
                continue
            for relative in matches:
                unresolved = root / relative
                resolved = unresolved.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    errors.append(f"evidence reference escapes root for {task_id}")
                    continue
                if unresolved.is_symlink() or not resolved.is_file():
                    errors.append(f"missing or unsafe evidence reference for {task_id}")
        expected_status = "READY" if task_id in {"T0701", "T0702", "T0703", "T0704"} else "BLOCKED"
        if (
            record["stage_acceptance_id"] != f"S7AC-00{index}"
            or record["record_status"] != expected_status
            or any(item["status"] != "PASS" for item in record["checks"])
        ):
            errors.append(f"Stage 7 implementation status mismatch for {task_id}")
        if [item["id"] for item in record["linked_final_acceptance"]] != graph_tasks[task_id][
            "acceptance_ids"
        ] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"}
            for item in record["linked_final_acceptance"]
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        expected_protected_status = expected_oracle_status.get(task_id, "NOT_RUN")
        if any(
            item["status"] != expected_protected_status for item in record["production_oracles"]
        ):
            errors.append(f"production oracle is overstated for {task_id}")
        expected_receipt = (
            "machine/stages/S7/reviews/t0702/execution-receipt.json"
            if task_id in {"T0701", "T0702"}
            else (
                "machine/stages/S7/reviews/t0703/execution-receipt.json"
                if task_id == "T0703"
                else (
                    "machine/stages/S7/reviews/t0704/execution-receipt.json"
                    if task_id == "T0704"
                    else None
                )
            )
        )
        if record.get("protected_execution_receipt") != expected_receipt:
            errors.append(f"protected execution receipt binding differs for {task_id}")
        if (
            not record["blockers"]
            or not required_blockers.get(task_id, set()).issubset(record["blockers"])
            or resolved_local_blockers.get(task_id, set()).intersection(record["blockers"])
            or any(record["prohibition_counters"].values())
        ):
            errors.append(f"Stage 7 blocker or prohibition counters are invalid for {task_id}")

    latest = _load(root / "evidence/stage7/latest.json")
    observation = latest.get("observation", {})
    aggregate_required_blockers = set().union(*required_blockers.values()) - {
        "T0705_NOT_AUTHORIZED_IN_CURRENT_RUN"
    }
    aggregate_resolved_blockers = set().union(*resolved_local_blockers.values())
    not_run = (
        "ga_0430_schedule",
        "codex_automation_created",
        "real_recovery_key_drill",
        "protected_patch_lifecycle",
    )
    if (
        latest.get("stage_id") != "S7"
        or latest.get("status")
        != "T0705_THIRTEEN_FAILED_HEADS_FROZEN_TRASH_CONFIRMATION_RECOVERY_AUTHORIZED_PENDING"
        or latest.get("scoped_preflight")
        != "PASS_CONTROL_BETA_M3_BLUE_GREEN_TIMELINE_GA_CODEX_AUTO_RECOVERY_AND_PATCH_POLICY"
        or latest.get("implementation_completion_status") != "LOCAL_MECHANISMS_READY"
        or latest.get("scope")
        != (
            "LOCAL_PREFLIGHT_WITH_PROTECTED_T0702_T0703_T0704_PASS_RECEIPTS"
            "_THIRTEEN_T0705_FAILED_ATTEMPTS_TWO_PRE_SECRET_FAILURES"
            "_ONE_RAW_RECOVERY_REPRESENTATION_FAILURE_AND_ONE_TRASH_CONFIRMATION_FAILURE"
        )
        or latest.get("mechanism_task_oracle_files_passed") != 8
        or latest.get("task_total") != 8
        or latest.get("completed_task_count") != 0
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 5
        or latest.get("protected_oracles_passed") != 4
        or latest.get("protected_oracles_failed") != 1
        or latest.get("protected_workflow_runs") != 33
        or latest.get("production_workflow_runs") != 15
        or observation.get("alpha_local_synthetic") != "PASS"
        or observation.get("beta_local_bootstrap_mechanism") != "PASS"
        or observation.get("beta_public_safe_failure_diagnostics")
        != "CLOSED_PASS_AFTER_TYPED_METADATA_QUARANTINE"
        or observation.get("m3_local_synthetic_mechanism") != "PASS"
        or observation.get("m3_protected_entrypoint") != "PASS_RECEIPT_BOUND_AUTHORITY_CONSUMED"
        or observation.get("blue_green_timeline_local_mechanism") != "PASS"
        or observation.get("blue_green_protected_entrypoint")
        != "PASS_RECEIPT_BOUND_AUTHORITY_CONSUMED"
        or observation.get("blue_green_deterministic_evidence_run")
        != "PASS_ONE_RECOVERABLE_ENCRYPTED_TIMELINE_ZERO_GMAIL_OR_CURRENT_MUTATION"
        or observation.get("ga_full_pipeline_local_mechanism")
        != "PASS_EXACT_PROTECTED_ENTRYPOINT_READY"
        or observation.get("ga_protected_entrypoint")
        != (
            "THIRTEENTH_PROTECTED_TRASH_MUTATION_FAILURE_FROZEN_"
            "TRASH_CONFIRMATION_RECOVERY_AUTHORIZED"
        )
        or observation.get("codex_auto_local_policy") != "PASS"
        or observation.get("recovery_drill_local_mechanism") != "PASS"
        or observation.get("patch_lifecycle_local_policy") != "PASS"
        or observation.get("alpha_remote_preflight") != "PASS"
        or observation.get("beta_real_raw_only")
        != "PASS_RAW_RECOVERY_100_PERCENT_ZERO_SOURCE_MUTATION"
        or observation.get("m3_deterministic_evidence_run")
        != "PASS_ZERO_MUTATION_RECONCILIATION_RECOVERY_100_PERCENT_ZERO_NEW_EFFECT"
        or any(observation.get(key) != "NOT_RUN" for key in not_run)
        or observation.get("protected_gmail_read_path")
        != "BOUNDED_VERIFIED_CANDIDATE_SCAN_EXACT_COUNTS_NOT_DISCLOSED"
        or observation.get("gmail_mutations") != 1
        or observation.get("verified_full_raw_reads") != "ONE_RECOVERED_WITHIN_CONFIGURED_BUDGET"
        or observation.get("protected_private_repository_path")
        != "NONZERO_AGE_CIPHERTEXT_ONLY_REMOTE_RECOVERY_100_PERCENT"
        or observation.get("protected_secret_injection")
        != "EIGHT_EXACT_NAMES_INJECTED_EXACT_READ_COUNT_NOT_DISCLOSED"
        or observation.get("controlled_main_deliveries") != 32
        or observation.get("private_raw_commits") != "NONZERO_WITHIN_CONFIGURED_BUDGET"
        or observation.get("remote_publications") != 0
        or observation.get("m3_runs") != 1
        or observation.get("processed_writes") != 3
        or observation.get("timeline_writes") != 4
        or observation.get("scheduled_runs") != 0
        or observation.get("maximum_observed_live_timeline_assets") != 1
        or not aggregate_required_blockers.issubset(latest.get("blocking_conditions", []))
        or aggregate_resolved_blockers.intersection(latest.get("blocking_conditions", []))
        or latest.get("delivery_status")
        != "CONTROLLED_T0705_TRASH_CONFIRMATION_RECOVERY_CANDIDATE_NOT_FINAL"
        or latest.get("next_action")
        != (
            "Freeze the Trash-mutation failed head, deliver one exact-main T0705 "
            "content-excluding label-confirmation successor, and execute exactly one new attempt-1 "
            "schedule-mode rehearsal with 2026-07-26T19:00:00Z only for RunPlanner. "
            "Require fields=id,labelIds; after an uncertain Trash response perform at most one "
            "label read and zero mutation retries. "
            "Never rerun or redispatch any "
            "failed head. Set the one-shot repository variable only after merge, delete it after "
            "authority consumption, then after exact protected PASS bind the receipt, enable only "
            "the committed live UTC 04:30 Australia/Sydney schedule and stop before T0706."
        )
    ):
        errors.append("Stage 7 aggregate evidence is not truthfully T0705 authorized-pending")
    return errors


def evaluate_stage7(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    before = _tree_digest(root)
    checks: list[dict[str, str]] = []
    manifest = root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"
    checks.append(
        _check(
            "baseline.manifest_identity",
            _sha256(manifest) == BASELINE_MANIFEST_SHA256,
            "frozen Stage 0 manifest digest matches the verified handoff",
        )
    )
    stage6 = evaluate_stage6(root, governance_root, allow_stage7=True)
    checks.append(
        _check(
            "baseline.cumulative_stage6",
            stage6["status"] == "PASS",
            f"Stage 6 failed checks {len(stage6['failed_check_ids'])}",
        )
    )
    contract_errors = _validate_contracts(root)
    checks.append(
        _check(
            "contracts.stage7_fail_closed_overlay",
            not contract_errors,
            f"Stage 7 contract errors {len(contract_errors)}",
        )
    )
    source_errors = _validate_source_and_tests(root)
    checks.append(
        _check(
            "implementation.release_transport_ops",
            not source_errors,
            f"Stage 7 source or test errors {len(source_errors)}",
        )
    )
    workflow_errors = _validate_workflow(root)
    checks.append(
        _check(
            "security.no_secret_stage7_preflight",
            not workflow_errors,
            f"Stage 7 workflow errors {len(workflow_errors)}",
        )
    )
    composition = validate_composition(root)
    checks.append(
        _check(
            "implementation.production_composition",
            composition["status"] == "PASS",
            f"RMD-04 composition failures {len(composition['failures'])}",
        )
    )
    evidence_errors = _validate_evidence(root)
    checks.append(
        _check(
            "evidence.truthful_protected_outcome",
            not evidence_errors,
            f"Stage 7 evidence errors {len(evidence_errors)}",
        )
    )
    publication = scan_tree(root)
    checks.append(
        _check(
            "security.publication",
            publication["status"] == "PASS",
            f"publication findings {publication['total_matches']}",
        )
    )
    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    scoped_preflight_status = "PASS" if not failed else "BLOCKED"
    implementation_status = "LOCAL_MECHANISMS_READY" if not failed else "BLOCKED"
    latest = _load(root / "evidence/stage7/latest.json")
    latest_observation = latest.get("observation", {})
    protected_blockers = tuple(latest.get("blocking_conditions", []))
    overall_status = str(latest.get("status"))
    return {
        "schema_version": "moomooau.stage7-verification.v1",
        "stage_id": "S7",
        "status": overall_status,
        "scoped_preflight_status": scoped_preflight_status,
        "implementation_status": implementation_status,
        "checks": checks,
        "failed_check_ids": failed,
        "blocking_conditions": list(protected_blockers),
        "signals": {
            "stage7_task_oracle_files": 8,
            "stage7_local_implementation_complete": not failed,
            "stage7_protected_integration_complete": False,
            "stage7_completed_tasks": 0,
            "protected_oracles_executed": latest.get("protected_oracles_executed"),
            "protected_oracles_passed": latest.get("protected_oracles_passed"),
            "protected_oracles_failed": latest.get("protected_oracles_failed"),
            "protected_workflow_runs": latest.get("protected_workflow_runs"),
            "production_workflow_runs": latest.get("production_workflow_runs"),
            "protected_gmail_read_path": latest_observation.get("protected_gmail_read_path"),
            "gmail_mutations": latest_observation.get("gmail_mutations"),
            "verified_full_raw_reads": latest_observation.get("verified_full_raw_reads"),
            "private_raw_commits": latest_observation.get("private_raw_commits"),
            "controlled_main_deliveries": latest_observation.get("controlled_main_deliveries"),
            "remote_publications": 0,
            "final_acceptances_passed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "return success only for the scoped control, protected Beta bootstrap/Raw-only, "
            "local synthetic M3, Blue-Green/Timeline, GA full-pipeline and passive Codex Auto "
            "policy, Recovery Drill and Patch Lifecycle mechanism preflight"
        ),
    )
    args = parser.parse_args()
    result = evaluate_stage7(args.root, args.governance_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.preflight:
        return 0 if result["scoped_preflight_status"] == "PASS" else 1
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
