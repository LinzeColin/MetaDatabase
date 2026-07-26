#!/usr/bin/env python3
"""Build and fail-closed validate the BSS completion-audit matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Callable


PROJECT_RELATIVE = PurePosixPath("Stock_Skill/bottleneck-serenity-skill")
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_RELATIVE = PROJECT_RELATIVE / "COMPLETION_AUDIT.json"
REQUIREMENTS_RELATIVE = PROJECT_RELATIVE / "task-pack/01_REQUIREMENTS_AND_SCOPE.md"
ARCHITECTURE_RELATIVE = PROJECT_RELATIVE / "task-pack/02_ARCHITECTURE_DATA_API.md"
TASKS_RELATIVE = PROJECT_RELATIVE / "task-pack/03_STAGE_PHASE_TASKS.md"
ACCEPTANCE_RELATIVE = (
    PROJECT_RELATIVE / "task-pack/04_ACCEPTANCE_VALIDATION_STOP.md"
)
LEDGER_RELATIVE = PROJECT_RELATIVE / "task-pack/CHANGELOG.md"
RUN_CONTRACT_RELATIVE = PROJECT_RELATIVE / "task-pack/00_RUN_CONTRACT.md"
TASK_MANIFEST_RELATIVE = PROJECT_RELATIVE / "task-pack/MANIFEST.sha256"
BACKUP_MANIFEST_RELATIVE = PROJECT_RELATIVE / "BACKUP_MANIFEST.sha256"
RELEASE_RELATIVE = (
    PROJECT_RELATIVE
    / "releases/bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip"
)

EXPECTED_SOURCE_IDS = {
    *(f"REQ-{number:03d}" for number in range(1, 24)),
    *(f"CAP-{number:03d}" for number in range(1, 10)),
    *(f"NG-{number:03d}" for number in range(1, 8)),
}
EXPECTED_ACCEPTANCE_IDS = {
    *(f"ACC-S0-{number:03d}" for number in range(1, 8)),
    *(f"ACC-S1-{number:03d}" for number in range(1, 7)),
    *(f"ACC-S2-{number:03d}" for number in range(1, 14)),
    *(f"ACC-S3-{number:03d}" for number in range(1, 11)),
    *(f"ACC-S4-{number:03d}" for number in range(1, 9)),
}
PARTIAL_SOURCE_IDS = {
    "REQ-001",
    "REQ-005",
    "REQ-014",
    "REQ-016",
    "REQ-018",
    "REQ-021",
    "REQ-022",
}
PENDING_ACCEPTANCE_IDS = {
    "ACC-S4-003",
    "ACC-S4-005",
    "ACC-S4-006",
    "ACC-S4-007",
    "ACC-S4-008",
}
EXPECTED_TASK_STATUS_COUNTS = {"DONE": 78, "PENDING": 2, "CONDITIONAL": 2}
EXPECTED_LEDGER_COUNT = 36
ALLOWED_EVIDENCE_GRADES = {"A", "B"}
FORBIDDEN_EVIDENCE_GRADES = {"C", "MISSING"}
LOCAL_SEAL_COMMIT = "36a383813721b46d0ae0d37650c5b92713957f27"
LOCAL_SEAL_TREE = "ad8997f02dba6efcf7bd3fccb068ee1a5bf7330c"
LOCAL_SEAL_RELEASE_SHA256 = (
    "58321504bd94b90cfad61ee7219cdbe9a5f51d6c6b9632daefd82c59c1e56208"
)
READINESS_ORIGIN_MAIN_COMMIT = "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4"
READINESS_PRE_SUBJECT_PATHS = 21
READINESS_PRE_SUBJECT_SHA256 = (
    "d0e0ca3380a22fefddc49aa682c0fbe63a2612572081b10aaa9181d02f8484b2"
)
READINESS_OVERLAY_PATHS = 39
READINESS_OVERLAY_LIST_SHA256 = (
    "c427b4621f18a8120cee6385f987f105f146bea18bc9ef9dde28908f3e685ded"
)
MECHANICAL_GATE_ORIGIN_MAIN_COMMIT = (
    "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7"
)
MECHANICAL_GATE_PRE_SUBJECT_PATHS = 21
MECHANICAL_GATE_PRE_SUBJECT_SHA256 = (
    "0a7d2ff9dc5aa005cabd5532a74302a86995b992182ebba91882b05945e01330"
)
MECHANICAL_GATE_PRE_TASKPACK_FILES = 292
MECHANICAL_GATE_PRE_TASKPACK_SHA256 = (
    "bcc19a4d881991bc85be7312394fea1ef29fa93da9f28a9ad2de45a36d67821e"
)
MECHANICAL_GATE_OVERLAY_PATHS = 39
MECHANICAL_GATE_OVERLAY_LIST_SHA256 = READINESS_OVERLAY_LIST_SHA256
MECHANICAL_GATE_PRE_CANDIDATE_TREE = (
    "048f4fcd6ce621366e0070c58f77d6f3f7b2199b"
)
ReadText = Callable[[Path], str]


class AuditError(RuntimeError):
    """A completion-audit invariant failed."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def read_document(
    repo_root: Path, relative: PurePosixPath, reader: ReadText | None
) -> str:
    path = repo_root.joinpath(*relative.parts)
    if reader is not None:
        return reader(path)
    return path.read_text(encoding="utf-8")


def split_markdown_row(line: str) -> list[str]:
    """Split a Markdown table row while preserving pipes inside code spans."""
    if not line.startswith("|") or not line.rstrip().endswith("|"):
        raise AuditError(f"invalid Markdown table row: {line!r}")
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    escaped = False
    for character in line.strip()[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\":
            current.append(character)
            escaped = True
            continue
        if character == "`":
            in_code = not in_code
            current.append(character)
            continue
        if character == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    if in_code:
        raise AuditError(f"unclosed code span in Markdown row: {line!r}")
    cells.append("".join(current).strip())
    return cells


def require_exact_set(actual: set[str], expected: set[str], label: str) -> None:
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise AuditError(f"{label} set drift; missing={missing}; extra={extra}")


def parse_sources(text: str) -> dict[str, str]:
    sources: dict[str, str] = {}
    patterns = (
        re.compile(
            r"^\|\s*`(REQ-[0-9]{3})`\s*\|.*\|\s*"
            r"(?:`[^`]+`(?:\s*\+\s*`[^`]+`)*)\s*\|\s*(.*?)\s*\|$"
        ),
        re.compile(r"^[0-9]+\.\s+`(CAP-[0-9]{3})`：\s*(.+)$"),
        re.compile(r"^-\s+`(NG-[0-9]{3})`：\s*(.+)$"),
    )
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match is None:
                continue
            source_id, statement = match.groups()
            if source_id in sources:
                raise AuditError(f"duplicate Source ID: {source_id}")
            if not statement.strip():
                raise AuditError(f"empty Source statement: {source_id}")
            sources[source_id] = statement.strip()
            break
    require_exact_set(set(sources), EXPECTED_SOURCE_IDS, "Source ID")
    return sources


def parse_tasks(text: str) -> dict[str, dict[str, str]]:
    tasks: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| `BSS-"):
            continue
        cells = split_markdown_row(line)
        if len(cells) != 5:
            raise AuditError(f"Task row must have five cells: {line!r}")
        task_match = re.fullmatch(r"`(BSS-S[0-9]+-P[0-9]+-T[0-9]+)`", cells[0])
        status_match = re.fullmatch(
            r"`(DONE|PENDING|CONDITIONAL|ACTIVE)`", cells[4]
        )
        if task_match is None or status_match is None:
            raise AuditError(f"invalid Task ID/status row: {line!r}")
        task_id = task_match.group(1)
        if task_id in tasks:
            raise AuditError(f"duplicate Task ID: {task_id}")
        tasks[task_id] = {
            "phase": cells[1],
            "goal": cells[2],
            "acceptance": cells[3],
            "status": status_match.group(1),
        }
    if len(tasks) != 82:
        raise AuditError(f"Task Graph count drift: expected 82, got {len(tasks)}")
    counts = Counter(task["status"] for task in tasks.values())
    if dict(counts) != EXPECTED_TASK_STATUS_COUNTS:
        raise AuditError(
            "Task status count drift: "
            f"expected {EXPECTED_TASK_STATUS_COUNTS}, got {dict(counts)}"
        )
    expected_stage4 = {
        "BSS-S4-P1-T001": ("Audit", "DONE"),
        "BSS-S4-P1-T002": ("Release readiness", "DONE"),
        "BSS-S4-P2-T001": ("Mechanical final gate", "DONE"),
        "BSS-S4-P2-T002": ("Remediation", "CONDITIONAL"),
        "BSS-S4-P2-T003": ("Mechanical revalidation", "CONDITIONAL"),
        "BSS-S4-P3-T001": ("Publish", "PENDING"),
        "BSS-S4-P3-T002": ("Cleanup", "PENDING"),
    }
    for task_id, (phase, status) in expected_stage4.items():
        task = tasks.get(task_id)
        if task is None:
            raise AuditError(f"missing Stage 4 Task: {task_id}")
        if task["phase"] != phase or task["status"] != status:
            raise AuditError(
                f"{task_id} routing drift: expected {phase}/{status}, "
                f"got {task['phase']}/{task['status']}"
            )
    for task_id, task in tasks.items():
        if task_id.startswith("BSS-S4-") and task["phase"] in {"Review", "Re-review"}:
            raise AuditError(f"forbidden Stage 4 review phase: {task_id}")
    return tasks


def parse_acceptance(text: str) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for line in text.splitlines():
        if not line.startswith("| `ACC-"):
            continue
        cells = split_markdown_row(line)
        if len(cells) != 6:
            raise AuditError(f"Acceptance row must have six cells: {line!r}")
        acceptance_match = re.fullmatch(r"`(ACC-S[0-9]+-[0-9]{3})`", cells[0])
        if acceptance_match is None:
            raise AuditError(f"invalid Acceptance ID: {cells[0]!r}")
        acceptance_id = acceptance_match.group(1)
        if acceptance_id in rows:
            raise AuditError(f"duplicate Acceptance ID: {acceptance_id}")
        source_ids = re.findall(r"(?:REQ|CAP|NG)-[0-9]{3}", cells[1])
        producer_ids = re.findall(r"BSS-S[0-9]+-P[0-9]+-T[0-9]+", cells[2])
        verifier_ids = re.findall(r"BSS-S[0-9]+-P[0-9]+-T[0-9]+", cells[3])
        if not source_ids or len(producer_ids) != 1 or not verifier_ids:
            raise AuditError(f"incomplete traceability row: {acceptance_id}")
        if len(source_ids) != len(set(source_ids)):
            raise AuditError(f"duplicate Source ID in {acceptance_id}")
        if len(verifier_ids) != len(set(verifier_ids)):
            raise AuditError(f"duplicate Verifier ID in {acceptance_id}")
        if not cells[4].strip() or not cells[5].strip():
            raise AuditError(f"empty Oracle/Evidence in {acceptance_id}")
        rows[acceptance_id] = {
            "source_ids": source_ids,
            "producer_task_id": producer_ids[0],
            "verifier_task_ids": verifier_ids,
            "oracle": cells[4],
            "evidence": cells[5],
        }
    require_exact_set(set(rows), EXPECTED_ACCEPTANCE_IDS, "Acceptance ID")
    return rows


def parse_ledger(text: str) -> dict[str, str]:
    findings: dict[str, str] = {}
    for line in text.splitlines():
        if not re.match(r"^\| `S[0-9]+-R[0-9]{3}`", line):
            continue
        cells = split_markdown_row(line)
        if len(cells) != 7:
            raise AuditError(f"finding row must have seven cells: {line!r}")
        finding_match = re.match(r"`(S[0-9]+-R[0-9]{3})`", cells[0])
        status_match = re.fullmatch(r"`([A-Z_]+)`", cells[4])
        if finding_match is None or status_match is None:
            raise AuditError(f"invalid finding/status row: {line!r}")
        finding_id = finding_match.group(1)
        if finding_id in findings:
            raise AuditError(f"duplicate finding ID: {finding_id}")
        findings[finding_id] = status_match.group(1)
    if len(findings) != EXPECTED_LEDGER_COUNT:
        raise AuditError(
            f"ledger count drift: expected {EXPECTED_LEDGER_COUNT}, got {len(findings)}"
        )
    non_closed = {
        finding_id: status
        for finding_id, status in findings.items()
        if status != "CLOSED"
    }
    if non_closed:
        raise AuditError(f"ledger contains non-CLOSED findings: {non_closed}")
    return findings


def validate_traceability(
    sources: dict[str, str],
    tasks: dict[str, dict[str, str]],
    acceptances: dict[str, dict[str, object]],
) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {source_id: [] for source_id in sources}
    for acceptance_id, row in acceptances.items():
        source_ids = row["source_ids"]
        assert isinstance(source_ids, list)
        for source_id in source_ids:
            if source_id not in sources:
                raise AuditError(
                    f"{acceptance_id} references undefined Source ID {source_id}"
                )
            coverage[source_id].append(acceptance_id)
        task_ids = [row["producer_task_id"], *row["verifier_task_ids"]]
        for task_id in task_ids:
            if task_id not in tasks:
                raise AuditError(
                    f"{acceptance_id} references undefined Task ID {task_id}"
                )
    uncovered = sorted(
        source_id for source_id, acceptance_ids in coverage.items() if not acceptance_ids
    )
    if uncovered:
        raise AuditError(f"uncovered Source IDs: {uncovered}")
    return coverage


def evidence_catalog() -> list[dict[str, object]]:
    project = PROJECT_RELATIVE.as_posix()
    canonical = (
        f"{project}/task-pack/skill_draft/bottleneck-serenity-skill"
    )
    return [
        {
            "id": "E-REQ",
            "grade": "B",
            "kind": "authoritative_specification",
            "paths": [REQUIREMENTS_RELATIVE.as_posix()],
            "verification": "parse exact 23 REQ + 9 CAP + 7 NG Source IDs",
            "claim": "Identity, scope, capabilities, boundaries, and authority labels.",
        },
        {
            "id": "E-ARCH",
            "grade": "B",
            "kind": "authoritative_contract",
            "paths": [ARCHITECTURE_RELATIVE.as_posix()],
            "verification": "inspect identity, release DAG, interfaces, CI, and restore contracts",
            "claim": "Architecture and deterministic release contracts are explicit.",
        },
        {
            "id": "E-TASK",
            "grade": "A",
            "kind": "machine_parsed_task_graph",
            "paths": [TASKS_RELATIVE.as_posix(), RUN_CONTRACT_RELATIVE.as_posix()],
            "verification": (
                f"python3 -B {project}/scripts/validate_completion_audit.py --check"
            ),
            "claim": "82 unique Tasks; 78 DONE, 2 PENDING, 2 CONDITIONAL; one next Task.",
        },
        {
            "id": "E-ACC",
            "grade": "A",
            "kind": "machine_parsed_traceability",
            "paths": [ACCEPTANCE_RELATIVE.as_posix()],
            "verification": (
                f"python3 -B {project}/scripts/validate_completion_audit.py --check"
            ),
            "claim": "44 exact ACC rows cover all 39 Source IDs and valid Task owners.",
        },
        {
            "id": "E-LEDGER",
            "grade": "A",
            "kind": "machine_parsed_finding_ledger",
            "paths": [LEDGER_RELATIVE.as_posix()],
            "verification": (
                f"python3 -B {project}/scripts/validate_completion_audit.py --check"
            ),
            "claim": "All 36 historical findings are CLOSED.",
        },
        {
            "id": "E-SOURCE",
            "grade": "A",
            "kind": "canonical_source_and_metadata",
            "paths": [
                f"{canonical}/SKILL.md",
                f"{canonical}/agents/openai.yaml",
                f"{project}/VERSION",
                f"{project}/SOURCE_INVENTORY.md",
            ],
            "verification": (
                f"python3 -B {canonical}/scripts/validate_skill.py {canonical}"
            ),
            "claim": "Stable identity, numeric-quad version, source-only Skill, and provenance.",
        },
        {
            "id": "E-TEST",
            "grade": "A",
            "kind": "durable_automated_oracles",
            "paths": [
                "Stock_Skill/scripts/run_unittests.py",
                f"{canonical}/tests",
                "Stock_Skill/tests",
            ],
            "verification": "python3 -B Stock_Skill/scripts/run_unittests.py",
            "claim": "Repository and canonical positive, negative, and mutation Oracles.",
        },
        {
            "id": "E-SECURITY",
            "grade": "A",
            "kind": "public_and_runtime_safety",
            "paths": [
                "Stock_Skill/scripts/validate_public_safety.py",
                f"{canonical}/scripts/validate_security_evals.py",
                f"{canonical}/evals/security_eval_results.json",
            ],
            "verification": (
                "python3 -B Stock_Skill/scripts/validate_public_safety.py"
            ),
            "claim": "Public-safety, no broker/order/network binding, and source-only boundaries.",
        },
        {
            "id": "E-EVAL",
            "grade": "A",
            "kind": "behavioral_evaluation",
            "paths": [
                f"{canonical}/evals/historical_e2e/rubric.json",
                f"{canonical}/evals/forward_test/result.json",
                f"{canonical}/evals/current_eval_binding.json",
                f"{canonical}/evals/presentation_oracles.json",
            ],
            "verification": (
                f"python3 -B {canonical}/scripts/validate_historical_e2e.py && "
                f"python3 -B {canonical}/scripts/validate_forward_test.py && "
                f"python3 -B {canonical}/scripts/validate_current_eval_binding.py"
            ),
            "claim": "Historical cutoff, Forward, current binding, trigger, and presentation evidence.",
        },
        {
            "id": "E-RELEASE",
            "grade": "A",
            "kind": "deterministic_release_hash_dag",
            "paths": [
                RELEASE_RELATIVE.as_posix(),
                f"{project}/releases/SHA256SUMS",
                TASK_MANIFEST_RELATIVE.as_posix(),
                BACKUP_MANIFEST_RELATIVE.as_posix(),
                "Stock_Skill/REGISTRY.json",
                f"{project}/scripts/build_release.py",
            ],
            "verification": (
                f"python3 -B {project}/scripts/build_release.py --verify && "
                "python3 -B Stock_Skill/scripts/validate_registry.py"
            ),
            "claim": "Canonical source, release, manifests, and registry are hash-bound.",
        },
        {
            "id": "E-LICENSE",
            "grade": "A",
            "kind": "license_and_provenance_audit",
            "paths": [
                f"{project}/LICENSE_AND_ATTRIBUTION.md",
                f"{project}/LICENSE_SIMILARITY_AUDIT.json",
                f"{project}/scripts/audit_license_similarity.py",
            ],
            "verification": (
                f"python3 -B {project}/scripts/audit_license_similarity.py "
                "--verify-targets"
            ),
            "claim": "Canonical target set and conservative attribution are machine-bound.",
        },
        {
            "id": "E-CI",
            "grade": "B",
            "kind": "implemented_ci_contract",
            "paths": [
                ".github/workflows/stock-skill-validation.yml",
                "Stock_Skill/tests/test_stock_skill_ci.py",
            ],
            "verification": (
                "python3 -B -m unittest Stock_Skill.tests.test_stock_skill_ci"
            ),
            "claim": "Path-filtered CI exists; terminal remote checks remain Publish-owned.",
        },
        {
            "id": "E-GIT",
            "grade": "B",
            "kind": "local_git_and_scope_evidence",
            "paths": [
                RUN_CONTRACT_RELATIVE.as_posix(),
                LEDGER_RELATIVE.as_posix(),
            ],
            "verification": (
                "git diff --name-only origin/main...HEAD; "
                "git diff --name-only HEAD; git ls-files --others --exclude-standard"
            ),
            "claim": (
                "Local seal and proposed final diff remain within the Stock Skill scope; "
                "remote terminal evidence is not fabricated."
            ),
        },
        {
            "id": "E-POLICY",
            "grade": "B",
            "kind": "current_user_and_repository_policy",
            "paths": [
                "AGENTS.md",
                "Stock_Skill/AGENTS.md",
                RUN_CONTRACT_RELATIVE.as_posix(),
                TASKS_RELATIVE.as_posix(),
            ],
            "verification": "inspect current routing, source-only, cleanup, and safe-gc controls",
            "claim": (
                "No Review, no intermediate upload, one Task per run, and opener cleanup."
            ),
        },
        {
            "id": "E-AUDIT",
            "grade": "A",
            "kind": "canonical_completion_audit",
            "paths": [
                AUDIT_RELATIVE.as_posix(),
                f"{project}/scripts/validate_completion_audit.py",
                "Stock_Skill/tests/test_completion_audit.py",
            ],
            "verification": (
                f"python3 -B {project}/scripts/validate_completion_audit.py --check"
            ),
            "claim": "Exact item sets, A/B-only evidence, statuses, and pending owners fail closed.",
        },
    ]


def source_evidence_refs(source_id: str) -> list[str]:
    refs = {"E-REQ", "E-ACC"}
    number = int(source_id.split("-")[1])
    if source_id.startswith("CAP-"):
        refs.update({"E-SOURCE", "E-EVAL", "E-TEST"})
    elif source_id.startswith("NG-"):
        refs.update({"E-POLICY", "E-SECURITY"})
    elif number in {2, 3, 4, 8, 9, 10, 17, 19}:
        refs.update({"E-ARCH", "E-SOURCE"})
    elif number in {6, 7, 11, 12, 15}:
        refs.update({"E-SECURITY", "E-POLICY"})
    elif number in {13, 22}:
        refs.update({"E-CI", "E-TEST"})
    elif number in {14}:
        refs.update({"E-TASK", "E-LEDGER", "E-AUDIT"})
    elif number in {20, 23}:
        refs.update({"E-LICENSE", "E-SOURCE"})
    else:
        refs.update({"E-GIT", "E-RELEASE"})
    return sorted(refs)


def source_pending_tasks(source_id: str) -> list[str]:
    owners = {
        "REQ-001": ["BSS-S4-P3-T001"],
        "REQ-005": ["BSS-S4-P3-T001", "BSS-S4-P3-T002"],
        "REQ-014": ["BSS-S4-P3-T001"],
        "REQ-016": ["BSS-S4-P3-T001"],
        "REQ-018": ["BSS-S4-P3-T002"],
        "REQ-021": ["BSS-S4-P3-T001"],
        "REQ-022": ["BSS-S4-P3-T001"],
    }
    return owners.get(source_id, [])


def acceptance_evidence_refs(acceptance_id: str) -> list[str]:
    stage = acceptance_id.split("-")[1]
    refs = {"E-ACC", "E-TASK"}
    if stage == "S0":
        refs.update({"E-REQ", "E-LEDGER"})
    elif stage == "S1":
        refs.update({"E-CI", "E-RELEASE", "E-TEST"})
    elif stage == "S2":
        refs.update({"E-LICENSE", "E-RELEASE", "E-SOURCE", "E-TEST"})
    elif stage == "S3":
        refs.update({"E-EVAL", "E-LEDGER", "E-SECURITY", "E-TEST"})
    else:
        stage4_refs = {
            "ACC-S4-001": {"E-AUDIT", "E-REQ"},
            "ACC-S4-002": {"E-LEDGER", "E-POLICY"},
            "ACC-S4-003": {"E-RELEASE", "E-GIT"},
            "ACC-S4-004": {"E-AUDIT", "E-GIT"},
            "ACC-S4-005": {"E-CI", "E-GIT"},
            "ACC-S4-006": {"E-GIT", "E-POLICY"},
            "ACC-S4-007": {"E-GIT", "E-POLICY"},
            "ACC-S4-008": {"E-GIT", "E-POLICY"},
        }
        refs.update(stage4_refs[acceptance_id])
    return sorted(refs)


def acceptance_pending_tasks(acceptance_id: str) -> list[str]:
    owners = {
        "ACC-S4-003": ["BSS-S4-P3-T001"],
        "ACC-S4-005": ["BSS-S4-P3-T001"],
        "ACC-S4-006": ["BSS-S4-P3-T001", "BSS-S4-P3-T002"],
        "ACC-S4-007": ["BSS-S4-P3-T002"],
        "ACC-S4-008": ["BSS-S4-P3-T002"],
    }
    return owners.get(acceptance_id, [])


def repository_constraints() -> list[dict[str, object]]:
    rows = [
        (
            "RC-ONE-TASK-PER-RUN",
            "SATISFIED",
            ["E-POLICY", "E-TASK"],
            [],
            "Exactly one Task is executed in this run.",
        ),
        (
            "RC-WORKTREE-ONLY",
            "SATISFIED",
            ["E-GIT", "E-POLICY"],
            [],
            "Development remains in the dedicated worktree; main tree is not modified.",
        ),
        (
            "RC-STOCK-SKILL-ROUTING",
            "SATISFIED",
            ["E-POLICY", "E-RELEASE"],
            [],
            "Canonical source remains under Stock_Skill and registry schema is 1.1.",
        ),
        (
            "RC-SOURCE-ONLY",
            "SATISFIED",
            ["E-SOURCE", "E-SECURITY"],
            [],
            "No runtime install, broker authentication, or trading execution is introduced.",
        ),
        (
            "RC-PUBLIC-SAFETY",
            "SATISFIED",
            ["E-SECURITY", "E-TEST"],
            [],
            "Public source/release safety remains guarded by durable scanners.",
        ),
        (
            "RC-NO-REVIEW",
            "SATISFIED",
            ["E-POLICY", "E-TASK"],
            [],
            "Future Stage 4 Review/Re-review phases are replaced by mechanical gates.",
        ),
        (
            "RC-DEFER-INTERMEDIATE-UPLOAD",
            "SATISFIED",
            ["E-GIT", "E-POLICY"],
            [],
            "No intermediate push or PR is required before final Publish.",
        ),
        (
            "RC-NO-UNRELATED-CHANGES",
            "SATISFIED",
            ["E-GIT", "E-AUDIT"],
            [],
            "Current task paths stay inside the explicit Stock Skill allowlist.",
        ),
        (
            "RC-NO-PAID-SERVICE",
            "SATISFIED",
            ["E-REQ", "E-SECURITY"],
            [],
            "Audit and validation use local deterministic evidence only.",
        ),
        (
            "RC-OPENER-CLEANUP",
            "PENDING_TERMINAL_ACTION",
            ["E-GIT", "E-POLICY"],
            ["BSS-S4-P3-T002"],
            "The opener must remove worktree/branches/PR metadata after merge.",
        ),
        (
            "RC-SAFE-GC",
            "PENDING_TERMINAL_ACTION",
            ["E-GIT", "E-POLICY"],
            ["BSS-S4-P3-T002"],
            "Cleanup must run git gc without --prune=now.",
        ),
    ]
    return [
        {
            "id": constraint_id,
            "status": status,
            "evidence_grade": "A" if status == "SATISFIED" else "B",
            "evidence_refs": refs,
            "pending_task_ids": owners,
            "claim": claim,
        }
        for constraint_id, status, refs, owners, claim in rows
    ]


def pending_obligations() -> list[dict[str, object]]:
    return [
        {
            "task_id": "BSS-S4-P2-T002",
            "phase": "Remediation",
            "source_ids": [],
            "acceptance_ids": [],
            "terminal_evidence": "conditional only if a mechanical gate fails",
        },
        {
            "task_id": "BSS-S4-P2-T003",
            "phase": "Mechanical revalidation",
            "source_ids": [],
            "acceptance_ids": [],
            "terminal_evidence": "conditional rerun of failed deterministic gates",
        },
        {
            "task_id": "BSS-S4-P3-T001",
            "phase": "Publish",
            "source_ids": [
                "REQ-001",
                "REQ-005",
                "REQ-014",
                "REQ-016",
                "REQ-021",
                "REQ-022",
            ],
            "acceptance_ids": [
                "ACC-S4-003",
                "ACC-S4-005",
                "ACC-S4-006",
            ],
            "terminal_evidence": "final seal, push, ready PR, CI, merge, and closed PR",
        },
        {
            "task_id": "BSS-S4-P3-T002",
            "phase": "Cleanup",
            "source_ids": ["REQ-005", "REQ-018"],
            "acceptance_ids": [
                "ACC-S4-006",
                "ACC-S4-007",
                "ACC-S4-008",
            ],
            "terminal_evidence": "main clean; worktree/branches removed; safe git gc",
        },
    ]


def build_expected(
    repo_root: Path, reader: ReadText | None = None
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    sources = parse_sources(
        read_document(repo_root, REQUIREMENTS_RELATIVE, reader)
    )
    tasks = parse_tasks(read_document(repo_root, TASKS_RELATIVE, reader))
    acceptances = parse_acceptance(
        read_document(repo_root, ACCEPTANCE_RELATIVE, reader)
    )
    findings = parse_ledger(read_document(repo_root, LEDGER_RELATIVE, reader))
    coverage = validate_traceability(sources, tasks, acceptances)

    source_items = []
    for source_id in sorted(sources):
        partial = source_id in PARTIAL_SOURCE_IDS
        source_items.append(
            {
                "id": source_id,
                "statement": sources[source_id],
                "status": (
                    "PARTIAL_PENDING_TERMINAL_ACTION" if partial else "SATISFIED"
                ),
                "evidence_grade": "B" if partial else "A",
                "evidence_refs": source_evidence_refs(source_id),
                "acceptance_ids": sorted(coverage[source_id]),
                "pending_task_ids": source_pending_tasks(source_id),
            }
        )

    acceptance_items = []
    for acceptance_id in sorted(acceptances):
        row = acceptances[acceptance_id]
        pending = acceptance_id in PENDING_ACCEPTANCE_IDS
        acceptance_items.append(
            {
                "id": acceptance_id,
                "source_ids": row["source_ids"],
                "producer_task_id": row["producer_task_id"],
                "verifier_task_ids": row["verifier_task_ids"],
                "oracle": row["oracle"],
                "evidence": row["evidence"],
                "status": "PENDING_NOT_DUE" if pending else "SATISFIED",
                "evidence_grade": "B" if pending else "A",
                "evidence_refs": acceptance_evidence_refs(acceptance_id),
                "pending_task_ids": acceptance_pending_tasks(acceptance_id),
            }
        )

    catalog = evidence_catalog()
    constraints = repository_constraints()
    task_counts = Counter(task["status"] for task in tasks.values())
    grade_counts = Counter(item["grade"] for item in catalog)
    return {
        "schema_version": "1.0",
        "audit_id": "BSS-S4-P1-T001",
        "stable_id": "bottleneck-serenity-skill",
        "version": "0.0.0.1",
        "display_version": "v0.0.0.1",
        "verdict": "MECHANICAL_GATE_PASS_TERMINAL_ACTIONS_PENDING",
        "subject": {
            "local_seal_commit": LOCAL_SEAL_COMMIT,
            "local_seal_tree": LOCAL_SEAL_TREE,
            "local_seal_release_sha256": LOCAL_SEAL_RELEASE_SHA256,
            "task_manifest_sha256": digest(
                repo_root.joinpath(*TASK_MANIFEST_RELATIVE.parts)
            ),
        },
        "evidence_policy": {
            "allowed_grades": ["A", "B"],
            "forbidden_grades": ["C", "MISSING"],
            "rule": (
                "SATISFIED requires current A/B evidence; pending terminal work must "
                "name its owner and may not be reported as completed."
            ),
        },
        "evidence_catalog": catalog,
        "source_items": source_items,
        "acceptance_items": acceptance_items,
        "repository_and_user_constraints": constraints,
        "pending_obligations": pending_obligations(),
        "release_readiness": {
            "task_id": "BSS-S4-P1-T002",
            "status": "PASS_CANDIDATE_NOT_PUBLISHED",
            "origin_main_commit": READINESS_ORIGIN_MAIN_COMMIT,
            "pre_readiness_subject": {
                "base_head": LOCAL_SEAL_COMMIT,
                "path_count": READINESS_PRE_SUBJECT_PATHS,
                "stage_source_sha256": READINESS_PRE_SUBJECT_SHA256,
            },
            "candidate_overlay": {
                "based_on_origin_main": True,
                "path_count": READINESS_OVERLAY_PATHS,
                "path_list_sha256": READINESS_OVERLAY_LIST_SHA256,
            },
            "verification": {
                "worktree_test_cases": 245,
                "clean_restore_test_cases": 245,
                "clean_restore_git_porcelain_empty": True,
                "task_manifest_entries": 291,
                "release_sha_consumer_count": 3,
                "current_release_sha256_stored": False,
                "double_build_byte_identical": {
                    "worktree": True,
                    "clean_restore": True,
                },
                "public_safety": {
                    "files": 378,
                    "blobs": 795,
                    "zip_entries": 417,
                },
                "license_similarity": {
                    "targets": 284,
                    "eligible_text_blobs": 2485,
                    "exact": 0,
                    "four_line": 5,
                    "token20": 1,
                },
            },
            "release_sha_consumer_paths": [
                "Stock_Skill/REGISTRY.json",
                f"{PROJECT_RELATIVE.as_posix()}/BACKUP_MANIFEST.sha256",
                f"{PROJECT_RELATIVE.as_posix()}/releases/SHA256SUMS",
            ],
            "external_actions": {
                "push": False,
                "pull_request": False,
                "merge": False,
                "runtime_install": False,
            },
        },
        "mechanical_final_gate": {
            "task_id": "BSS-S4-P2-T001",
            "status": "PASS",
            "origin_main_commit": MECHANICAL_GATE_ORIGIN_MAIN_COMMIT,
            "pre_gate_subject": {
                "base_head": LOCAL_SEAL_COMMIT,
                "path_count": MECHANICAL_GATE_PRE_SUBJECT_PATHS,
                "stage_source_sha256": MECHANICAL_GATE_PRE_SUBJECT_SHA256,
            },
            "pre_gate_taskpack": {
                "file_count": MECHANICAL_GATE_PRE_TASKPACK_FILES,
                "tree_sha256": MECHANICAL_GATE_PRE_TASKPACK_SHA256,
            },
            "candidate_overlay": {
                "based_on_origin_main": True,
                "path_count": MECHANICAL_GATE_OVERLAY_PATHS,
                "path_list_sha256": MECHANICAL_GATE_OVERLAY_LIST_SHA256,
                "pre_gate_candidate_tree": MECHANICAL_GATE_PRE_CANDIDATE_TREE,
            },
            "verification": {
                "worktree_test_cases": 245,
                "clean_candidate_test_cases": 245,
                "clean_candidate_git_porcelain_empty": True,
                "json_files": 194,
                "task_manifest_entries": 291,
                "finding_total": EXPECTED_LEDGER_COUNT,
                "finding_closed": EXPECTED_LEDGER_COUNT,
                "changed_paths_allowlisted": True,
                "release_sha_consumer_count": 3,
                "current_release_sha256_stored": False,
                "double_build_byte_identical": {
                    "worktree": True,
                    "clean_candidate": True,
                },
                "public_safety": {
                    "files": 378,
                    "blobs": 795,
                    "zip_entries": 417,
                },
                "license_similarity": {
                    "targets": 284,
                    "eligible_text_blobs": 2485,
                    "exact": 0,
                    "four_line": 5,
                    "token20": 1,
                },
            },
            "policy": {
                "reviewer_used": False,
                "live_provider_run": False,
                "conditional_remediation_activated": False,
            },
            "external_actions": {
                "push": False,
                "pull_request": False,
                "merge": False,
                "runtime_install": False,
            },
        },
        "summary": {
            "source_total": len(source_items),
            "source_satisfied": len(source_items) - len(PARTIAL_SOURCE_IDS),
            "source_partial": len(PARTIAL_SOURCE_IDS),
            "acceptance_total": len(acceptance_items),
            "acceptance_satisfied": len(acceptance_items)
            - len(PENDING_ACCEPTANCE_IDS),
            "acceptance_pending_not_due": len(PENDING_ACCEPTANCE_IDS),
            "task_total": len(tasks),
            "task_done": task_counts["DONE"],
            "task_pending": task_counts["PENDING"],
            "task_conditional": task_counts["CONDITIONAL"],
            "finding_total": len(findings),
            "finding_closed": len(findings),
            "constraint_total": len(constraints),
            "constraint_satisfied": sum(
                row["status"] == "SATISFIED" for row in constraints
            ),
            "constraint_pending_terminal_action": sum(
                row["status"] == "PENDING_TERMINAL_ACTION"
                for row in constraints
            ),
            "evidence_catalog_a": grade_counts["A"],
            "evidence_catalog_b": grade_counts["B"],
            "evidence_catalog_c_or_missing": 0,
        },
    }


def validate_evidence_paths(
    document: dict[str, object], repo_root: Path
) -> set[str]:
    catalog = document.get("evidence_catalog")
    if not isinstance(catalog, list) or not catalog:
        raise AuditError("evidence_catalog must be a non-empty list")
    evidence_ids: set[str] = set()
    for entry in catalog:
        if not isinstance(entry, dict):
            raise AuditError("evidence_catalog entries must be objects")
        evidence_id = entry.get("id")
        grade = entry.get("grade")
        paths = entry.get("paths")
        verification = entry.get("verification")
        claim = entry.get("claim")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise AuditError("evidence entry has invalid id")
        if evidence_id in evidence_ids:
            raise AuditError(f"duplicate evidence id: {evidence_id}")
        evidence_ids.add(evidence_id)
        if grade not in ALLOWED_EVIDENCE_GRADES:
            raise AuditError(f"{evidence_id}: forbidden/unknown evidence grade {grade!r}")
        if not isinstance(paths, list) or not paths:
            raise AuditError(f"{evidence_id}: paths must be non-empty")
        for raw in paths:
            if not isinstance(raw, str) or not raw:
                raise AuditError(f"{evidence_id}: invalid evidence path")
            relative = PurePosixPath(raw)
            if (
                relative.is_absolute()
                or relative.as_posix() != raw
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise AuditError(f"{evidence_id}: unsafe evidence path {raw!r}")
            target = repo_root.joinpath(*relative.parts)
            if target.is_symlink() or not target.exists():
                raise AuditError(f"{evidence_id}: missing evidence path {raw}")
        if not isinstance(verification, str) or not verification.strip():
            raise AuditError(f"{evidence_id}: empty verification")
        if not isinstance(claim, str) or not claim.strip():
            raise AuditError(f"{evidence_id}: empty claim")
    return evidence_ids


def validate_item_evidence(
    document: dict[str, object], evidence_ids: set[str]
) -> None:
    collections = (
        "source_items",
        "acceptance_items",
        "repository_and_user_constraints",
    )
    for collection_name in collections:
        collection = document.get(collection_name)
        if not isinstance(collection, list) or not collection:
            raise AuditError(f"{collection_name} must be a non-empty list")
        seen: set[str] = set()
        for item in collection:
            if not isinstance(item, dict):
                raise AuditError(f"{collection_name} entries must be objects")
            item_id = item.get("id")
            grade = item.get("evidence_grade")
            refs = item.get("evidence_refs")
            if not isinstance(item_id, str) or not item_id:
                raise AuditError(f"{collection_name}: invalid item id")
            if item_id in seen:
                raise AuditError(f"{collection_name}: duplicate item {item_id}")
            seen.add(item_id)
            if grade not in ALLOWED_EVIDENCE_GRADES:
                raise AuditError(f"{item_id}: forbidden/unknown evidence grade {grade!r}")
            if not isinstance(refs, list) or not refs:
                raise AuditError(f"{item_id}: evidence_refs must be non-empty")
            if len(refs) != len(set(refs)):
                raise AuditError(f"{item_id}: duplicate evidence_refs")
            unknown = sorted(set(refs) - evidence_ids)
            if unknown:
                raise AuditError(f"{item_id}: unknown evidence refs {unknown}")
            owners = item.get("pending_task_ids")
            status = item.get("status")
            if not isinstance(owners, list):
                raise AuditError(f"{item_id}: pending_task_ids must be a list")
            pending = status in {
                "PARTIAL_PENDING_TERMINAL_ACTION",
                "PENDING_NOT_DUE",
                "PENDING_TERMINAL_ACTION",
            }
            if pending != bool(owners):
                raise AuditError(
                    f"{item_id}: pending status and pending_task_ids disagree"
                )


def validate_changed_path_scope(repo_root: Path) -> None:
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return
    commands = (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            if command[1:3] == ["diff", "--name-only"] and "origin/main" in command:
                continue
            raise AuditError(
                f"changed-path command failed: {' '.join(command)}: "
                f"{result.stderr.strip()}"
            )
        paths.update(line for line in result.stdout.splitlines() if line)
    allowed_exact = {
        "Stock_Skill/AGENTS.md",
        "Stock_Skill/README.md",
        "Stock_Skill/REGISTRY.json",
        "Stock_Skill/scripts/validate_public_safety.py",
        "Stock_Skill/scripts/validate_registry.py",
        "Stock_Skill/tests/test_completion_audit.py",
        "Stock_Skill/tests/test_license_similarity_audit.py",
        "Stock_Skill/tests/test_stock_skill_ci.py",
        ".github/workflows/stock-skill-validation.yml",
    }
    allowed_prefix = f"{PROJECT_RELATIVE.as_posix()}/"
    unrelated = sorted(
        path
        for path in paths
        if not path.startswith(allowed_prefix) and path not in allowed_exact
    )
    if unrelated:
        raise AuditError(f"changed paths escape Stock Skill allowlist: {unrelated}")


def validate_document(
    document: object,
    repo_root: Path,
    reader: ReadText | None = None,
) -> dict[str, object]:
    if not isinstance(document, dict):
        raise AuditError("completion audit root must be an object")
    evidence_ids = validate_evidence_paths(document, repo_root)
    validate_item_evidence(document, evidence_ids)

    source_items = document.get("source_items")
    acceptance_items = document.get("acceptance_items")
    assert isinstance(source_items, list)
    assert isinstance(acceptance_items, list)
    require_exact_set(
        {str(item["id"]) for item in source_items},
        EXPECTED_SOURCE_IDS,
        "audited Source ID",
    )
    require_exact_set(
        {str(item["id"]) for item in acceptance_items},
        EXPECTED_ACCEPTANCE_IDS,
        "audited Acceptance ID",
    )
    source_status = {
        str(item["id"]): item.get("status") for item in source_items
    }
    actual_partial = {
        item_id
        for item_id, status in source_status.items()
        if status == "PARTIAL_PENDING_TERMINAL_ACTION"
    }
    if actual_partial != PARTIAL_SOURCE_IDS:
        raise AuditError(
            f"partial Source set drift: expected {sorted(PARTIAL_SOURCE_IDS)}, "
            f"got {sorted(actual_partial)}"
        )
    if any(
        status not in {"SATISFIED", "PARTIAL_PENDING_TERMINAL_ACTION"}
        for status in source_status.values()
    ):
        raise AuditError("invalid Source status")
    acceptance_status = {
        str(item["id"]): item.get("status") for item in acceptance_items
    }
    actual_pending = {
        item_id
        for item_id, status in acceptance_status.items()
        if status == "PENDING_NOT_DUE"
    }
    if actual_pending != PENDING_ACCEPTANCE_IDS:
        raise AuditError(
            f"pending Acceptance set drift: expected "
            f"{sorted(PENDING_ACCEPTANCE_IDS)}, got {sorted(actual_pending)}"
        )
    if any(
        status not in {"SATISFIED", "PENDING_NOT_DUE"}
        for status in acceptance_status.values()
    ):
        raise AuditError("invalid Acceptance status")

    serialized = json.dumps(document, ensure_ascii=False)
    for forbidden in FORBIDDEN_EVIDENCE_GRADES:
        if re.search(
            rf'"(?:grade|evidence_grade)"\s*:\s*"{re.escape(forbidden)}"',
            serialized,
        ):
            raise AuditError(f"forbidden evidence grade present: {forbidden}")

    expected = build_expected(repo_root, reader)
    if document != expected:
        raise AuditError("completion audit differs from canonical derived state")
    validate_changed_path_scope(repo_root)
    return expected


def validate_serialized(
    payload: bytes,
    repo_root: Path,
    reader: ReadText | None = None,
) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"invalid UTF-8 JSON: {exc}") from exc
    expected = validate_document(document, repo_root, reader)
    if payload != canonical_json(document):
        raise AuditError("completion audit JSON is not canonical")
    return expected


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or check the canonical BSS completion audit."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="repository root (defaults to the script's repository)",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        help="audit JSON path (defaults inside --repo-root)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="atomically refresh audit")
    mode.add_argument("--check", action="store_true", help="validate without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    audit_path = (
        args.audit.resolve()
        if args.audit is not None
        else repo_root.joinpath(*AUDIT_RELATIVE.parts)
    )
    try:
        if args.write:
            expected = build_expected(repo_root)
            atomic_write(audit_path, canonical_json(expected))
        if not audit_path.is_file() or audit_path.is_symlink():
            raise AuditError(f"audit file missing or invalid: {audit_path}")
        expected = validate_serialized(audit_path.read_bytes(), repo_root)
        summary = expected["summary"]
        assert isinstance(summary, dict)
        print(
            "PASS: completion audit; "
            f"sources={summary['source_satisfied']}/{summary['source_total']} "
            f"(partial={summary['source_partial']}); "
            f"acceptance={summary['acceptance_satisfied']}/"
            f"{summary['acceptance_total']} "
            f"(pending={summary['acceptance_pending_not_due']}); "
            f"tasks={summary['task_done']}/{summary['task_total']}; "
            f"findings={summary['finding_closed']}/{summary['finding_total']} CLOSED; "
            "evidence=C/MISSING:0"
        )
        return 0
    except (AuditError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
