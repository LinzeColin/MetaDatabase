from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT_ROOT / "machine/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_delivery_status as delivery_status  # noqa: E402
import build_governance_facts as governance_facts  # noqa: E402
import build_package_manifest as package_manifest  # noqa: E402
import validate_assurance_reviews as assurance_reviews  # noqa: E402
import validate_package as package_validation  # noqa: E402
from build_delivery_status import (  # noqa: E402
    _select_transition_state,
    _validate_stage6_evidence_transition,
)
from capture_candidate_gates import _sanitized_tool_versions  # noqa: E402
from validate_assurance_reviews import (  # noqa: E402
    BASELINE_COMMIT,
    EXPECTED_COMMAND_IDS,
    POST_REVIEW_AUTHORITY_PATHS,
    _validate_git_subject,
    _validate_post_review_authorities,
    evaluate_assurance_reviews,
)
from validate_evidence import (  # noqa: E402
    S6_EVIDENCE_SCHEMAS,
    STAGE6_CANDIDATE_RECEIPT_PATH,
    STAGE6_TASK_COMMAND_IDS,
    validate_stage6_candidate_bundle,
    validate_stage6_receipt_anchor,
)
from validate_package import _validate_provenance  # noqa: E402
from validate_stage6_secret_scan import (  # noqa: E402
    _structured_receipt_failures,
    _structured_review_failures,
)
from validate_stage6_secret_scan import (  # noqa: E402
    validate as validate_stage6_secret_scan,
)

from machine.acceptance import evidence as acceptance_evidence  # noqa: E402

CANDIDATE = "a" * 40
CANDIDATE_TREE = "b" * 40
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _write_pretty_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(root: Path, relative: str) -> dict[str, str]:
    return {"path": relative, "sha256": _sha256(root / relative)}


def _reply(request_hash: str, resolved_ids: set[str], reviewer: str) -> dict[str, Any]:
    return {
        "schema_version": "moomooau.independent-review-reply.v2",
        "target": {
            "baseline_commit": BASELINE_COMMIT,
            "candidate_commit": CANDIDATE,
            "candidate_tree": CANDIDATE_TREE,
            "request_sha256": request_hash,
        },
        "review_mode": "READ_ONLY_INDEPENDENT",
        "verdict": "PASS",
        "dimensions": [
            {
                "id": dimension,
                "status": "PASS",
                "evidence_refs": ["synthetic fixture"],
                "rationale": "The synthetic validator fixture closes this dimension.",
            }
            for dimension in ("SCOPE", "EVIDENCE_QUALITY", "FAILURE_HONESTY", "ROLLBACK")
        ],
        "findings": [
            {
                "id": finding_id,
                "severity": "BLOCKING",
                "status": "RESOLVED",
                "finding": "The initial adverse finding is closed in the validator fixture.",
                "evidence_refs": ["synthetic fixture"],
                "resolution_ref": "synthetic fixture remediation",
            }
            for finding_id in sorted(resolved_ids)
        ],
        "limitations": ["Synthetic validator fixture only; no protected or production claim."],
        "sensitive_data_observed": False,
        "production_or_protected_claimed": False,
        "summary": f"PASS for the synthetic {reviewer} provenance validator fixture.",
    }


def _build_valid_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "MooMooAU"
    schemas = root / "machine/stages/S6/schemas"
    shutil.copytree(PROJECT_ROOT / "machine/stages/S6/schemas", schemas)
    review_root = root / "machine/stages/S6/reviews"
    source_review_root = PROJECT_ROOT / "machine/stages/S6/reviews/rmd05"
    (review_root / "rmd05/initial").mkdir(parents=True)
    (review_root / "rmd05/rereview1").mkdir(parents=True)
    (review_root / "rmd05/final").mkdir(parents=True)
    (review_root / "rmd05/rereview3").mkdir(parents=True)
    (review_root / "rmd05/final2").mkdir(parents=True)
    (review_root / "rmd05/rereview5").mkdir(parents=True)
    (review_root / "rmd05/final3").mkdir(parents=True)
    (review_root / "rmd05/final4").mkdir(parents=True)
    (review_root / "rmd05/final5").mkdir(parents=True)
    (review_root / "rmd05/final6").mkdir(parents=True)
    (review_root / "rmd05/final7").mkdir(parents=True)
    (review_root / "rmd05/final8").mkdir(parents=True)
    (review_root / "rmd05/final9").mkdir(parents=True)
    (review_root / "rmd05/final10").mkdir(parents=True)
    (review_root / "rmd05/final11").mkdir(parents=True)
    (review_root / "rmd05/final12").mkdir(parents=True)
    (review_root / "rmd05/final13").mkdir(parents=True)
    (review_root / "rmd05/final14").mkdir(parents=True)
    for relative in (
        "request.md",
        "rereview-request.md",
        "rereview2-request.md",
        "rereview3-request.md",
        "rereview4-request.md",
        "rereview5-request.md",
        "rereview6-request.md",
        "rereview7-request.md",
        "rereview8-request.md",
        "rereview9-request.md",
        "rereview10-request.md",
        "rereview11-request.md",
        "rereview12-request.md",
        "rereview13-request.md",
        "rereview14-request.md",
        "rereview15-request.md",
        "rereview16-request.md",
        "execution-receipt.json",
        "execution-receipt2.json",
        "execution-receipt3.json",
        "execution-receipt4.json",
        "execution-receipt5.json",
        "execution-receipt6.json",
        "execution-receipt7.json",
        "execution-receipt8.json",
        "execution-receipt9.json",
        "execution-receipt10.json",
        "execution-receipt11.json",
        "execution-receipt12.json",
        "execution-receipt13.json",
        "execution-receipt14.json",
        "execution-receipt15.json",
        "execution-receipt16.json",
    ):
        shutil.copy2(source_review_root / relative, review_root / f"rmd05/{relative}")
    for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
        shutil.copy2(
            source_review_root / f"initial/{family}.reply.json",
            review_root / f"rmd05/initial/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"rereview1/{family}.reply.json",
            review_root / f"rmd05/rereview1/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final/{family}.reply.json",
            review_root / f"rmd05/final/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"rereview3/{family}.reply.json",
            review_root / f"rmd05/rereview3/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final2/{family}.reply.json",
            review_root / f"rmd05/final2/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"rereview5/{family}.reply.json",
            review_root / f"rmd05/rereview5/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final3/{family}.reply.json",
            review_root / f"rmd05/final3/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final4/{family}.reply.json",
            review_root / f"rmd05/final4/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final5/{family}.reply.json",
            review_root / f"rmd05/final5/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final6/{family}.reply.json",
            review_root / f"rmd05/final6/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final7/{family}.reply.json",
            review_root / f"rmd05/final7/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final8/{family}.reply.json",
            review_root / f"rmd05/final8/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final9/{family}.reply.json",
            review_root / f"rmd05/final9/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final10/{family}.reply.json",
            review_root / f"rmd05/final10/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final11/{family}.reply.json",
            review_root / f"rmd05/final11/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final12/{family}.reply.json",
            review_root / f"rmd05/final12/{family}.reply.json",
        )
        shutil.copy2(
            source_review_root / f"final13/{family}.reply.json",
            review_root / f"rmd05/final13/{family}.reply.json",
        )

    output = "candidate-bound synthetic gate PASS\n"
    receipt = {
        "schema_version": "moomooau.candidate-execution-receipt.v1",
        "receipt_id": "S6-RMD05-CANDIDATE-GATES",
        "subject": {
            "repository": "MetaDatabase",
            "project_path": "LinzeDatabase/MooMooAU",
            "baseline_commit": BASELINE_COMMIT,
            "candidate_commit": CANDIDATE,
            "candidate_tree": CANDIDATE_TREE,
            "clean_detached_checkout": True,
        },
        "scope": "LOCAL_SYNTHETIC_ONLY",
        "environment": {
            "platform": "synthetic-test-platform",
            "python": "3.12.13",
            "dependency_lock_path": "requirements/stage6.lock",
            "dependency_lock_sha256": "c" * 64,
            "governance_commit": "d" * 40,
            "python_executable_sha256": "e" * 64,
        },
        "commands": [
            {
                "id": command_id,
                "working_directory": "LinzeDatabase/MooMooAU",
                "argv": ["synthetic", command_id],
                "tool_versions": {"synthetic": "1.0"},
                "exit_code": 0,
                "raw_stdout_bytes": len(output.encode()),
                "raw_stderr_bytes": 0,
                "raw_stdout_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "raw_stderr_sha256": EMPTY_SHA256,
                "sanitized_stdout": output,
                "sanitized_stderr": "",
                "sanitized_stdout_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "sanitized_stderr_sha256": EMPTY_SHA256,
                "result_summary": "Synthetic command passed without external effects.",
            }
            for command_id in sorted(EXPECTED_COMMAND_IDS)
        ],
        "raw_logs_retained": False,
        "sensitive_data_observed": False,
        "production_or_protected_executed": False,
        "remote_service_writes": 0,
        "ephemeral_local_outputs_removed": True,
    }
    receipt_path = review_root / "rmd05/execution-receipt17.json"
    _write_json(receipt_path, receipt)
    receipt_artifact = _artifact(root, "machine/stages/S6/reviews/rmd05/execution-receipt17.json")
    adverse_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt.json",
    )

    superseded_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt2.json",
    )
    superseded_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview2-request.md",
    )

    transition_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt3.json",
    )
    transition_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview3-request.md",
    )
    integration_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt4.json",
    )
    integration_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview4-request.md",
    )
    evidence_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt5.json",
    )
    evidence_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview5-request.md",
    )
    anchor_adverse_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt6.json",
    )
    anchor_adverse_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview6-request.md",
    )
    governance_superseded_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt7.json",
    )
    governance_superseded_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview7-request.md",
    )
    materialization_adverse_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt8.json",
    )
    materialization_adverse_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview8-request.md",
    )
    closure_path_superseded_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt9.json",
    )
    closure_path_superseded_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview9-request.md",
    )
    final_rejected_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt10.json",
    )
    final_rejected_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview10-request.md",
    )
    authority_adverse_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt11.json",
    )
    authority_adverse_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview11-request.md",
    )
    authority_materialization_adverse_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt12.json",
    )
    authority_materialization_adverse_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview12-request.md",
    )
    public_closure_adverse_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt13.json",
    )
    public_closure_adverse_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview13-request.md",
    )
    governance_materialization_superseded_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt14.json",
    )
    governance_materialization_superseded_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview14-request.md",
    )
    secret_scan_materialization_superseded_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt15.json",
    )
    secret_scan_materialization_superseded_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview15-request.md",
    )
    assurance_cli_import_superseded_receipt_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/execution-receipt16.json",
    )
    assurance_cli_import_superseded_request_artifact = _artifact(
        root,
        "machine/stages/S6/reviews/rmd05/rereview16-request.md",
    )

    rereview_request = review_root / "rmd05/rereview17-request.md"
    rereview_request.write_text(
        f"Candidate commit: `{CANDIDATE}`\nCandidate tree: `{CANDIDATE_TREE}`\n",
        encoding="utf-8",
    )
    rereview_request_artifact = _artifact(
        root, "machine/stages/S6/reviews/rmd05/rereview17-request.md"
    )
    initial_request = _artifact(root, "machine/stages/S6/reviews/rmd05/request.md")
    adverse_request = _artifact(root, "machine/stages/S6/reviews/rmd05/rereview-request.md")

    identities = {
        "gpt-5.6-sol": ("SOL", "sol"),
        "gpt-5.6-terra": ("TERRA", "terra"),
    }
    for family, (review_suffix, task_suffix) in identities.items():
        initial_relative = f"machine/stages/S6/reviews/rmd05/initial/{family}.reply.json"
        initial_reply = json.loads((root / initial_relative).read_text(encoding="utf-8"))
        initial_ids = {item["id"] for item in initial_reply["findings"]}
        adverse_relative = f"machine/stages/S6/reviews/rmd05/rereview1/{family}.reply.json"
        adverse_reply = json.loads((root / adverse_relative).read_text(encoding="utf-8"))
        adverse_open_ids = {
            item["id"] for item in adverse_reply["findings"] if item["status"] == "OPEN"
        }
        superseded_relative = f"machine/stages/S6/reviews/rmd05/final/{family}.reply.json"
        superseded_reply = json.loads((root / superseded_relative).read_text(encoding="utf-8"))
        transition_relative = f"machine/stages/S6/reviews/rmd05/rereview3/{family}.reply.json"
        transition_reply = json.loads((root / transition_relative).read_text(encoding="utf-8"))
        integration_relative = f"machine/stages/S6/reviews/rmd05/final2/{family}.reply.json"
        integration_reply = json.loads((root / integration_relative).read_text(encoding="utf-8"))
        evidence_relative = f"machine/stages/S6/reviews/rmd05/rereview5/{family}.reply.json"
        evidence_reply = json.loads((root / evidence_relative).read_text(encoding="utf-8"))
        anchor_adverse_relative = f"machine/stages/S6/reviews/rmd05/final3/{family}.reply.json"
        anchor_adverse_reply = json.loads(
            (root / anchor_adverse_relative).read_text(encoding="utf-8")
        )
        governance_superseded_relative = (
            f"machine/stages/S6/reviews/rmd05/final4/{family}.reply.json"
        )
        governance_superseded_reply = json.loads(
            (root / governance_superseded_relative).read_text(encoding="utf-8")
        )
        materialization_adverse_relative = (
            f"machine/stages/S6/reviews/rmd05/final5/{family}.reply.json"
        )
        materialization_adverse_reply = json.loads(
            (root / materialization_adverse_relative).read_text(encoding="utf-8")
        )
        closure_path_superseded_relative = (
            f"machine/stages/S6/reviews/rmd05/final6/{family}.reply.json"
        )
        closure_path_superseded_reply = json.loads(
            (root / closure_path_superseded_relative).read_text(encoding="utf-8")
        )
        final_rejected_relative = f"machine/stages/S6/reviews/rmd05/final7/{family}.reply.json"
        final_rejected_reply = json.loads(
            (root / final_rejected_relative).read_text(encoding="utf-8")
        )
        authority_adverse_relative = f"machine/stages/S6/reviews/rmd05/final8/{family}.reply.json"
        authority_adverse_reply = json.loads(
            (root / authority_adverse_relative).read_text(encoding="utf-8")
        )
        authority_materialization_adverse_relative = (
            f"machine/stages/S6/reviews/rmd05/final9/{family}.reply.json"
        )
        authority_materialization_adverse_reply = json.loads(
            (root / authority_materialization_adverse_relative).read_text(encoding="utf-8")
        )
        public_closure_adverse_relative = (
            f"machine/stages/S6/reviews/rmd05/final10/{family}.reply.json"
        )
        public_closure_adverse_reply = json.loads(
            (root / public_closure_adverse_relative).read_text(encoding="utf-8")
        )
        governance_materialization_superseded_relative = (
            f"machine/stages/S6/reviews/rmd05/final11/{family}.reply.json"
        )
        governance_materialization_superseded_reply = json.loads(
            (root / governance_materialization_superseded_relative).read_text(encoding="utf-8")
        )
        secret_scan_materialization_superseded_relative = (
            f"machine/stages/S6/reviews/rmd05/final12/{family}.reply.json"
        )
        secret_scan_materialization_superseded_reply = json.loads(
            (root / secret_scan_materialization_superseded_relative).read_text(encoding="utf-8")
        )
        assurance_cli_import_superseded_relative = (
            f"machine/stages/S6/reviews/rmd05/final13/{family}.reply.json"
        )
        assurance_cli_import_superseded_reply = json.loads(
            (root / assurance_cli_import_superseded_relative).read_text(encoding="utf-8")
        )
        final_relative = f"machine/stages/S6/reviews/rmd05/final14/{family}.reply.json"
        _write_json(
            root / final_relative,
            _reply(
                rereview_request_artifact["sha256"],
                initial_ids
                | adverse_open_ids
                | {item["id"] for item in superseded_reply["findings"]}
                | {item["id"] for item in transition_reply["findings"]}
                | {item["id"] for item in integration_reply["findings"]}
                | {item["id"] for item in evidence_reply["findings"]}
                | {item["id"] for item in anchor_adverse_reply["findings"]}
                | {item["id"] for item in governance_superseded_reply["findings"]}
                | {item["id"] for item in materialization_adverse_reply["findings"]}
                | {item["id"] for item in closure_path_superseded_reply["findings"]}
                | {item["id"] for item in final_rejected_reply["findings"]}
                | {item["id"] for item in authority_adverse_reply["findings"]}
                | {item["id"] for item in authority_materialization_adverse_reply["findings"]}
                | {item["id"] for item in public_closure_adverse_reply["findings"]}
                | {item["id"] for item in governance_materialization_superseded_reply["findings"]}
                | {item["id"] for item in secret_scan_materialization_superseded_reply["findings"]}
                | {item["id"] for item in assurance_cli_import_superseded_reply["findings"]}
                | {
                    "RMD05-CLOSURE-002",
                    "RMD05-CLOSURE-003",
                    "RMD05-CLOSURE-004",
                    "RMD05-CLOSURE-005",
                    "RMD05-CLOSURE-006",
                    "RMD05-CLOSURE-007",
                    "RMD05-CLOSURE-008",
                    "RMD05-CLOSURE-009",
                    "RMD05-CLOSURE-010",
                    "RMD05-CLOSURE-011",
                    "RMD05-CLOSURE-012",
                },
                family,
            ),
        )
        record = {
            "schema_version": "moomooau.independent-review-provenance.v2",
            "review_id": f"S6-RMD05-GPT56{review_suffix}",
            "stage_id": "S6",
            "model_family": family,
            "review_mode": "READ_ONLY_INDEPENDENT",
            "subject": {
                "baseline_commit": BASELINE_COMMIT,
                "candidate_commit": CANDIDATE,
                "candidate_tree": CANDIDATE_TREE,
            },
            "execution_receipt": receipt_artifact,
            "attempts": [
                {
                    "phase": "INITIAL",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_review",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": initial_request,
                    "reply": {
                        **_artifact(root, initial_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "verdict": "FAIL",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": adverse_request,
                    "reply": {
                        **_artifact(root, adverse_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": adverse_receipt_artifact,
                    "verdict": "FAIL",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview2",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": superseded_request_artifact,
                    "reply": {
                        **_artifact(root, superseded_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": superseded_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_TRANSITION_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview3",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": transition_request_artifact,
                    "reply": {
                        **_artifact(root, transition_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": transition_receipt_artifact,
                    "verdict": "FAIL",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_OUTPUT_INTEGRATION_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview4",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": integration_request_artifact,
                    "reply": {
                        **_artifact(root, integration_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": integration_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_EVIDENCE_COUPLING_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview5",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": evidence_request_artifact,
                    "reply": {
                        **_artifact(root, evidence_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": evidence_receipt_artifact,
                    "verdict": evidence_reply["verdict"],
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_RECEIPT_ANCHOR_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview6",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": anchor_adverse_request_artifact,
                    "reply": {
                        **_artifact(root, anchor_adverse_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": anchor_adverse_receipt_artifact,
                    "verdict": anchor_adverse_reply["verdict"],
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_GOVERNANCE_FACTS_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview7",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": governance_superseded_request_artifact,
                    "reply": {
                        **_artifact(root, governance_superseded_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": governance_superseded_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_OUTPUT_MATERIALIZATION_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview8",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": materialization_adverse_request_artifact,
                    "reply": {
                        **_artifact(root, materialization_adverse_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": materialization_adverse_receipt_artifact,
                    "verdict": materialization_adverse_reply["verdict"],
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_CLOSURE_PATH_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview9",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": closure_path_superseded_request_artifact,
                    "reply": {
                        **_artifact(root, closure_path_superseded_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": closure_path_superseded_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_FINAL_REJECTED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview10",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": final_rejected_request_artifact,
                    "reply": {
                        **_artifact(root, final_rejected_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": final_rejected_receipt_artifact,
                    "verdict": "FAIL",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_AUTHORITY_DRIFT_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview11",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": authority_adverse_request_artifact,
                    "reply": {
                        **_artifact(root, authority_adverse_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": authority_adverse_receipt_artifact,
                    "verdict": authority_adverse_reply["verdict"],
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_AUTHORITY_MATERIALIZATION_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview12",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": authority_materialization_adverse_request_artifact,
                    "reply": {
                        **_artifact(root, authority_materialization_adverse_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": authority_materialization_adverse_receipt_artifact,
                    "verdict": authority_materialization_adverse_reply["verdict"],
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_PUBLIC_CLOSURE_ADVERSE",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview13",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": public_closure_adverse_request_artifact,
                    "reply": {
                        **_artifact(root, public_closure_adverse_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": public_closure_adverse_receipt_artifact,
                    "verdict": public_closure_adverse_reply["verdict"],
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_GOVERNANCE_MATERIALIZATION_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview14",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": governance_materialization_superseded_request_artifact,
                    "reply": {
                        **_artifact(root, governance_materialization_superseded_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": governance_materialization_superseded_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_SECRET_SCAN_MATERIALIZATION_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview15",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": secret_scan_materialization_superseded_request_artifact,
                    "reply": {
                        **_artifact(root, secret_scan_materialization_superseded_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": secret_scan_materialization_superseded_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_ASSURANCE_CLI_IMPORT_SUPERSEDED",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview16",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": assurance_cli_import_superseded_request_artifact,
                    "reply": {
                        **_artifact(root, assurance_cli_import_superseded_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": assurance_cli_import_superseded_receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
                {
                    "phase": "REREVIEW_FINAL",
                    "platform_task_id": f"/root/rmd05_{task_suffix}_rereview17",
                    "invocation_tool": "collaboration.spawn_agent",
                    "requested_model": family,
                    "fork_turns": "none",
                    "inherited_thread_context": False,
                    "request": rereview_request_artifact,
                    "reply": {
                        **_artifact(root, final_relative),
                        "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
                    },
                    "execution_receipt": receipt_artifact,
                    "verdict": "PASS",
                    "receipt_scope": "CODEX_THREAD_AUDIT_LOG",
                    "repository_only_proves_platform_execution": False,
                },
            ],
            "closure_status": "PASS",
            "provenance_limitations": [
                "Repository hashes and task IDs require the retained Codex thread audit log."
            ],
        }
        _write_json(review_root / f"{family}.json", record)
    return root


def _build_stage6_candidate_evidence_bundle(tmp_path: Path) -> Path:
    root = _build_valid_bundle(tmp_path)
    for relative in (
        "machine/contracts/acceptance_contract.json",
        "machine/contracts/publication_safety.json",
        "machine/contracts/task_graph.json",
        "machine/stages/S6/contracts/stage6_acceptance_contract.json",
    ):
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    receipt_path = root / STAGE6_CANDIDATE_RECEIPT_PATH
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_hash = _sha256(receipt_path)
    subject = receipt["subject"]
    for task_id, command_ids in STAGE6_TASK_COMMAND_IDS.items():
        source = PROJECT_ROOT / f"evidence/tasks/{task_id}.json"
        record = json.loads(source.read_text(encoding="utf-8"))
        record["schema_version"] = "moomooau.stage6-evidence.v2"
        record["candidate_commit"] = subject["candidate_commit"]
        record["candidate_tree"] = subject["candidate_tree"]
        record["execution_binding"] = {
            "path": STAGE6_CANDIDATE_RECEIPT_PATH.as_posix(),
            "sha256": receipt_hash,
            "command_ids": sorted(command_ids),
        }
        _write_json(root / f"evidence/tasks/{task_id}.json", record)

    aggregate = json.loads(
        (PROJECT_ROOT / "evidence/stage6/latest.json").read_text(encoding="utf-8")
    )
    aggregate["schema_version"] = "moomooau.stage6-verification.v2"
    aggregate["candidate_commit"] = subject["candidate_commit"]
    aggregate["candidate_tree"] = subject["candidate_tree"]
    aggregate["execution_receipt"] = {
        "path": STAGE6_CANDIDATE_RECEIPT_PATH.as_posix(),
        "sha256": receipt_hash,
    }
    aggregate["local_gate_command_ids"] = [item["id"] for item in receipt["commands"]]
    _write_json(root / "evidence/stage6/latest.json", aggregate)
    return root


def _assert_blocked(root: Path, mutate: Callable[[Path], None]) -> None:
    mutate(root)
    result = evaluate_assurance_reviews(root, root.parent, verify_git=False)
    assert result["status"] == "BLOCKED"
    assert result["errors"]


def test_rmd05_valid_candidate_hash_task_and_reply_chain_passes_without_git_fixture(
    tmp_path: Path,
) -> None:
    root = _build_valid_bundle(tmp_path)
    result = evaluate_assurance_reviews(root, root.parent, verify_git=False)
    assert result["status"] == "PASS"
    assert result["review_records"] == 2
    assert result["distinct_model_families"] == 2
    assert result["distinct_platform_tasks"] == 36
    assert result["preserved_adverse_rereviews"] == 2
    assert result["preserved_superseded_pass_reviews"] == 2
    assert result["preserved_transition_adverse_reviews"] == 2
    assert result["preserved_integration_superseded_pass_reviews"] == 2
    assert result["preserved_evidence_coupling_reviews"] == 2
    assert result["preserved_receipt_anchor_reviews"] == 2
    assert result["preserved_governance_facts_superseded_reviews"] == 2
    assert result["preserved_output_materialization_adverse_reviews"] == 2
    assert result["preserved_closure_path_superseded_reviews"] == 2
    assert result["preserved_final_rejected_reviews"] == 2
    assert result["preserved_authority_drift_adverse_reviews"] == 2
    assert result["preserved_authority_materialization_adverse_reviews"] == 2
    assert result["preserved_public_closure_adverse_reviews"] == 2
    assert result["preserved_governance_materialization_superseded_reviews"] == 2
    assert result["preserved_secret_scan_materialization_superseded_reviews"] == 2
    assert result["platform_audit_log_required"] is True


def test_rmd05_materialized_mixed_history_is_honestly_blocked_but_integral(
    tmp_path: Path,
) -> None:
    root = _build_valid_bundle(tmp_path)
    for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
        path = root / f"machine/stages/S6/reviews/{family}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        assurance_cli_import_superseded = record["attempts"][16]
        reply = json.loads(
            (root / assurance_cli_import_superseded["reply"]["path"]).read_text(encoding="utf-8")
        )
        record["subject"] = {
            "baseline_commit": BASELINE_COMMIT,
            "candidate_commit": reply["target"]["candidate_commit"],
            "candidate_tree": reply["target"]["candidate_tree"],
        }
        record["execution_receipt"] = assurance_cli_import_superseded["execution_receipt"]
        record["attempts"] = record["attempts"][:17]
        record["closure_status"] = "BLOCKED"
        _write_json(path, record)

    result = evaluate_assurance_reviews(root, root.parent, verify_git=False)
    assert result["status"] == "BLOCKED"
    assert result["history_integrity"] == "PASS"
    assert result["pending_final_review"] is True
    assert result["errors"] == []


def test_rmd05_reply_tamper_is_rejected(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        path = target / "machine/stages/S6/reviews/rmd05/final/gpt-5.6-sol.reply.json"
        path.write_bytes(path.read_bytes() + b" ")

    _assert_blocked(root, mutate)


def test_rmd05_adverse_rereview_tamper_is_rejected(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        path = target / "machine/stages/S6/reviews/rmd05/rereview1/gpt-5.6-sol.reply.json"
        path.write_bytes(path.read_bytes() + b" ")

    _assert_blocked(root, mutate)


def test_rmd05_task_id_or_model_record_confusion_is_rejected(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        path = target / "machine/stages/S6/reviews/gpt-5.6-terra.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["attempts"][17]["platform_task_id"] = "/root/rmd05_sol_rereview17"
        _write_json(path, record)

    _assert_blocked(root, mutate)


def test_rmd05_stale_candidate_binding_is_rejected(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        path = target / "machine/stages/S6/reviews/gpt-5.6-sol.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["subject"]["candidate_tree"] = "e" * 40
        _write_json(path, record)

    _assert_blocked(root, mutate)


def test_rmd05_open_rereview_finding_is_rejected_even_with_updated_hash(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        reply_path = target / "machine/stages/S6/reviews/rmd05/final14/gpt-5.6-terra.reply.json"
        reply = json.loads(reply_path.read_text(encoding="utf-8"))
        reply["verdict"] = "FAIL"
        reply["findings"][0]["status"] = "OPEN"
        reply["findings"][0]["required_fix"] = "Keep the finding open."
        reply["findings"][0].pop("resolution_ref")
        _write_json(reply_path, reply)
        record_path = target / "machine/stages/S6/reviews/gpt-5.6-terra.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["attempts"][17]["reply"]["sha256"] = _sha256(reply_path)
        record["attempts"][17]["verdict"] = "FAIL"
        _write_json(record_path, record)

    _assert_blocked(root, mutate)


def test_rmd05_execution_output_digest_tamper_is_rejected(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        receipt_path = target / "machine/stages/S6/reviews/rmd05/execution-receipt17.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["commands"][0]["sanitized_stdout"] = "tampered\n"
        _write_json(receipt_path, receipt)
        digest = _sha256(receipt_path)
        for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
            record_path = target / f"machine/stages/S6/reviews/{family}.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["execution_receipt"]["sha256"] = digest
            record["attempts"][17]["execution_receipt"]["sha256"] = digest
            _write_json(record_path, record)

    _assert_blocked(root, mutate)


def test_rmd05_tool_versions_replace_local_paths() -> None:
    locked_environment = "/private/tmp/rmd05-venv"
    versions = {"build": f"build 1.5.0 ({locked_environment}/lib/python3.12/site-packages/build)"}

    sanitized = _sanitized_tool_versions(
        versions,
        ("build",),
        ((locked_environment, "${LOCKED_ENV}"),),
    )

    assert sanitized == {"build": "build 1.5.0 (${LOCKED_ENV}/lib/python3.12/site-packages/build)"}
    assert "/private/tmp/" not in sanitized["build"]


def test_rmd05_receipt_tool_version_local_path_is_rejected(tmp_path: Path) -> None:
    root = _build_valid_bundle(tmp_path)

    def mutate(target: Path) -> None:
        receipt_path = target / "machine/stages/S6/reviews/rmd05/execution-receipt17.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        local_path = "/" + "Users/example/private/venv"
        receipt["commands"][0]["tool_versions"] = {"synthetic": f"1.0 ({local_path})"}
        _write_json(receipt_path, receipt)
        digest = _sha256(receipt_path)
        for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
            record_path = target / f"machine/stages/S6/reviews/{family}.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["execution_receipt"]["sha256"] = digest
            record["attempts"][17]["execution_receipt"]["sha256"] = digest
            _write_json(record_path, record)

    _assert_blocked(root, mutate)


def _git_run(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _git_commit_all(repository: Path, message: str) -> str:
    _git_run(repository, "add", "-A")
    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "-m",
        message,
    )
    return _git_run(repository, "rev-parse", "HEAD")


def _copy_public_closure_candidate(root: Path) -> None:
    source_repository = PROJECT_ROOT.parents[1]
    project_prefix = "LinzeDatabase/MooMooAU"
    completed = subprocess.run(
        ["git", "-C", str(source_repository), "ls-files", "-z", "--", project_prefix],
        check=True,
        capture_output=True,
    )
    repository_paths = [
        Path(item.decode("utf-8")) for item in completed.stdout.split(b"\0") if item
    ]
    for repository_path in repository_paths:
        source = source_repository / repository_path
        relative = repository_path.relative_to(project_prefix)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for workflow_relative in (
        ".github/workflows/moomooau-stage3-ci.yml",
        ".github/workflows/moomooau-stage4-ci.yml",
        ".github/workflows/moomooau-stage5-ci.yml",
        ".github/workflows/moomooau-stage6-ci.yml",
        ".github/workflows/moomooau-production.yml",
    ):
        source = source_repository / workflow_relative
        target = root.parents[1] / workflow_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for artifact_relative in (
        "machine/stages/S6/reviews/rmd05/execution-receipt13.json",
        "machine/stages/S6/reviews/rmd05/rereview13-request.md",
        "machine/stages/S6/reviews/rmd05/final10/gpt-5.6-sol.reply.json",
        "machine/stages/S6/reviews/rmd05/final10/gpt-5.6-terra.reply.json",
        "machine/stages/S6/reviews/rmd05/execution-receipt14.json",
        "machine/stages/S6/reviews/rmd05/rereview14-request.md",
        "machine/stages/S6/reviews/rmd05/final11/gpt-5.6-sol.reply.json",
        "machine/stages/S6/reviews/rmd05/final11/gpt-5.6-terra.reply.json",
        "machine/stages/S6/reviews/rmd05/execution-receipt15.json",
        "machine/stages/S6/reviews/rmd05/rereview15-request.md",
        "machine/stages/S6/reviews/rmd05/final12/gpt-5.6-sol.reply.json",
        "machine/stages/S6/reviews/rmd05/final12/gpt-5.6-terra.reply.json",
        "machine/stages/S6/reviews/rmd05/execution-receipt16.json",
        "machine/stages/S6/reviews/rmd05/rereview16-request.md",
        "machine/stages/S6/reviews/rmd05/final13/gpt-5.6-sol.reply.json",
        "machine/stages/S6/reviews/rmd05/final13/gpt-5.6-terra.reply.json",
    ):
        source = PROJECT_ROOT / artifact_relative
        target = root / artifact_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _materialize_stage6_v2(
    root: Path,
    *,
    candidate_commit: str,
    candidate_tree: str,
    receipt_sha256: str,
) -> None:
    for task_id, command_ids in STAGE6_TASK_COMMAND_IDS.items():
        path = root / f"evidence/tasks/{task_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["schema_version"] = "moomooau.stage6-evidence.v2"
        record["candidate_commit"] = candidate_commit
        record["candidate_tree"] = candidate_tree
        record["execution_binding"] = {
            "path": STAGE6_CANDIDATE_RECEIPT_PATH.as_posix(),
            "sha256": receipt_sha256,
            "command_ids": sorted(command_ids),
        }
        _write_json(path, record)

    aggregate_path = root / "evidence/stage6/latest.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["schema_version"] = "moomooau.stage6-verification.v2"
    aggregate["candidate_commit"] = candidate_commit
    aggregate["candidate_tree"] = candidate_tree
    aggregate["execution_receipt"] = {
        "path": STAGE6_CANDIDATE_RECEIPT_PATH.as_posix(),
        "sha256": receipt_sha256,
    }
    receipt = json.loads((root / STAGE6_CANDIDATE_RECEIPT_PATH).read_text(encoding="utf-8"))
    aggregate["local_gate_command_ids"] = [item["id"] for item in receipt["commands"]]
    _write_json(aggregate_path, aggregate)


def _write_acceptance_bundle(
    root: Path,
    *,
    observed_at_utc: str,
    remediation_base_commit: str,
) -> None:
    bundle = acceptance_evidence.build_bundle(
        root,
        observed_at_utc=observed_at_utc,
        remediation_base_commit=remediation_base_commit,
    )
    for relative, rendered in bundle.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def _materialize_governance_documents(root: Path) -> None:
    replacements = {
        "文档/00_我在哪.md": (
            ("| 版本 | `1.0.4` |", "| 版本 | `1.0.5` |"),
            (
                "`RMD-05 保证来源链闭包进行中`",
                "`RMD-05 保证来源链已关闭；下一项 RMD-06`",
            ),
            (
                "| RMD-05_ASSURANCE_PROVENANCE_PENDING | 独立保证来源链尚未补齐 |",
                "| RMD-06_PROTECTED_ACCEPTANCE_PENDING | 受保护验收与观察尚未执行 |",
            ),
        ),
        "文档/03_口径字典.md": (("由 v1.0.4 原样继承", "由 v1.0.5 原样继承"),),
        "文档/05_执行与验收.md": (
            (
                "整体复审修复 · RMD-05 保证来源链闭包 · 仅完成 RMD-05",
                "整体复审修复 · RMD-05 保证来源链闭包 · RMD-05 已关闭；下一轮仅进入 RMD-06",
            ),
        ),
        "文档/06_运维手册.md": (
            (
                "|---|---|---|\n| 1.0.4 |",
                "|---|---|---|\n"
                "| 1.0.5 | 2026-07-22 | 以候选绑定执行回执、十八次不可变尝试链和两个模型家族的"
                "独立通过关闭 RMD-05；受保护验证、生产与发布仍关闭。 |\n| 1.0.4 |",
            ),
        ),
    }
    for relative, pairs in replacements.items():
        path = root / relative
        if _sha256(path) == assurance_reviews.GOVERNANCE_DOCUMENT_AUTHORITY_SHA256[relative]:
            continue
        rendered = path.read_text(encoding="utf-8")
        for old, new in pairs:
            assert old in rendered
            rendered = rendered.replace(old, new)
        path.write_text(rendered, encoding="utf-8")
    for relative, expected in assurance_reviews.GOVERNANCE_DOCUMENT_AUTHORITY_SHA256.items():
        assert _sha256(root / relative) == expected


def _write_closed_authorities(root: Path) -> None:
    _write_pretty_json(
        root / package_validation.PROVENANCE_PATH,
        package_validation.build_provenance(),
    )
    _write_pretty_json(
        root / delivery_status.STATUS_PATH,
        delivery_status.build_status(root, assurance_result={"status": "PASS"}),
    )
    for name, value in governance_facts.build_facts(root).items():
        _write_pretty_json(root / "machine/facts" / name, value)
    _materialize_governance_documents(root)
    _write_pretty_json(
        root / package_manifest.MANIFEST_PATH,
        package_manifest.build_manifest(root),
    )


def _build_public_closure_git_fixture(tmp_path: Path) -> dict[str, Path | str]:
    source_repository = PROJECT_ROOT.parents[1]
    repository = tmp_path / "repository"
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(source_repository),
            str(repository),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    branch = "refs/heads/rmd05-public-closure-fixture"
    _git_run(repository, "symbolic-ref", "HEAD", branch)
    _git_run(repository, "update-ref", branch, BASELINE_COMMIT)
    _git_run(repository, "read-tree", "--empty")

    root = repository / "LinzeDatabase/MooMooAU"
    _copy_public_closure_candidate(root)
    seed_commit = _git_commit_all(repository, "synthetic public closure seed")

    frozen_observed_at = "2026-07-22T00:00:00Z"
    _write_acceptance_bundle(
        root,
        observed_at_utc=frozen_observed_at,
        remediation_base_commit=seed_commit,
    )
    execution_candidate = _git_commit_all(repository, "synthetic execution candidate")
    candidate_tree = _git_run(repository, "rev-parse", f"{execution_candidate}^{{tree}}")

    template_root = _build_valid_bundle(tmp_path / "template")
    receipt_relative = STAGE6_CANDIDATE_RECEIPT_PATH.as_posix()
    receipt = json.loads((template_root / receipt_relative).read_text(encoding="utf-8"))
    receipt["subject"]["candidate_commit"] = execution_candidate
    receipt["subject"]["candidate_tree"] = candidate_tree
    _write_json(root / receipt_relative, receipt)
    receipt_artifact = _artifact(root, receipt_relative)

    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "anchor synthetic execution receipt",
        "-m",
        f"MooMooAU-Execution-Candidate: {execution_candidate}\n"
        f"MooMooAU-Execution-Receipt-SHA256: {receipt_artifact['sha256']}",
    )
    review_anchor = _git_run(repository, "rev-parse", "HEAD")
    assert _git_run(repository, "rev-parse", "HEAD^{tree}") == candidate_tree

    request_relative = "machine/stages/S6/reviews/rmd05/rereview17-request.md"
    request_path = root / request_relative
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        f"Candidate commit: `{review_anchor}`\nCandidate tree: `{candidate_tree}`\n",
        encoding="utf-8",
    )
    request_artifact = _artifact(root, request_relative)

    for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
        reply_relative = f"machine/stages/S6/reviews/rmd05/final14/{family}.reply.json"
        reply = json.loads((template_root / reply_relative).read_text(encoding="utf-8"))
        reply["target"]["candidate_commit"] = review_anchor
        reply["target"]["candidate_tree"] = candidate_tree
        reply["target"]["request_sha256"] = request_artifact["sha256"]
        _write_json(root / reply_relative, reply)
        reply_artifact = _artifact(root, reply_relative)

        record_relative = f"machine/stages/S6/reviews/{family}.json"
        record = json.loads((template_root / record_relative).read_text(encoding="utf-8"))
        record["subject"]["candidate_commit"] = review_anchor
        record["subject"]["candidate_tree"] = candidate_tree
        record["execution_receipt"] = receipt_artifact
        final_attempt = record["attempts"][17]
        final_attempt["request"] = request_artifact
        final_attempt["reply"] = {
            **reply_artifact,
            "normalization": "UTF8_JSON_SINGLE_TRAILING_LF",
        }
        final_attempt["execution_receipt"] = receipt_artifact
        _write_json(root / record_relative, record)

    _materialize_stage6_v2(
        root,
        candidate_commit=execution_candidate,
        candidate_tree=candidate_tree,
        receipt_sha256=receipt_artifact["sha256"],
    )
    _write_acceptance_bundle(
        root,
        observed_at_utc=frozen_observed_at,
        remediation_base_commit=seed_commit,
    )
    _write_closed_authorities(root)
    final_commit = _git_commit_all(repository, "materialize deterministic closure authorities")
    assert _git_run(repository, "status", "--porcelain") == ""
    return {
        "repository": repository,
        "root": root,
        "seed_commit": seed_commit,
        "execution_candidate": execution_candidate,
        "candidate_tree": candidate_tree,
        "review_anchor": review_anchor,
        "final_commit": final_commit,
    }


def _clone_public_closure_fixture(source: Path, target: Path) -> tuple[Path, Path]:
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", str(source), str(target)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return target, target / "LinzeDatabase/MooMooAU"


def test_rmd05_public_closure_is_preserved_as_the_immutable_v105_predecessor() -> None:
    predecessor = PROJECT_ROOT / package_manifest.PREDECESSOR_MANIFEST_PATH
    assert predecessor.is_file() and not predecessor.is_symlink()
    assert _sha256(predecessor) == package_manifest.PREDECESSOR_MANIFEST_SHA256
    result = evaluate_assurance_reviews(
        PROJECT_ROOT,
        PROJECT_ROOT.parents[1],
        verify_git=False,
        verify_anchor=True,
    )
    assert result["status"] == "PASS", result["errors"]
    assert result["errors"] == []
    assert len(POST_REVIEW_AUTHORITY_PATHS) == 67
    secret_result = validate_stage6_secret_scan(PROJECT_ROOT)
    assert secret_result["status"] == "PASS", secret_result


def test_rmd05_immutable_predecessor_digest_rejects_byte_drift(
    tmp_path: Path,
) -> None:
    predecessor = PROJECT_ROOT / package_manifest.PREDECESSOR_MANIFEST_PATH
    drifted = tmp_path / predecessor.name
    drifted.write_bytes(predecessor.read_bytes() + b"\n")
    assert _sha256(drifted) != package_manifest.PREDECESSOR_MANIFEST_SHA256


def test_rmd05_historical_authority_set_keeps_exact_v105_paths() -> None:
    assert (
        "LinzeDatabase/MooMooAU/taskpack/PACKAGE_MANIFEST.v1.0.5.json"
        in POST_REVIEW_AUTHORITY_PATHS
    )
    assert (
        "LinzeDatabase/MooMooAU/taskpack/SOURCE_PROVENANCE.v1.0.5.json"
        in POST_REVIEW_AUTHORITY_PATHS
    )
    assert not any("v1.0.6" in path for path in POST_REVIEW_AUTHORITY_PATHS)


def test_rmd05_candidate_bound_stage6_bundle_remains_integral() -> None:
    assert validate_stage6_candidate_bundle(PROJECT_ROOT, PROJECT_ROOT.parents[1]) == []


def test_rmd05_git_anchor_rejects_synchronized_receipt_bundle_replacement(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git_run(repository, "init", "--quiet")
    seed = repository / "seed.txt"
    seed.write_text("executed candidate tree\n", encoding="utf-8")
    _git_run(repository, "add", "seed.txt")
    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "-m",
        "execution candidate",
    )
    execution_candidate = _git_run(repository, "rev-parse", "HEAD")
    candidate_tree = _git_run(repository, "rev-parse", "HEAD^{tree}")

    root = _build_stage6_candidate_evidence_bundle(repository / "fixture")
    receipt_path = root / STAGE6_CANDIDATE_RECEIPT_PATH
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["subject"]["candidate_commit"] = execution_candidate
    receipt["subject"]["candidate_tree"] = candidate_tree
    _write_json(receipt_path, receipt)
    receipt_hash = _sha256(receipt_path)
    for task_id in STAGE6_TASK_COMMAND_IDS:
        path = root / f"evidence/tasks/{task_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["candidate_commit"] = execution_candidate
        record["candidate_tree"] = candidate_tree
        record["execution_binding"]["sha256"] = receipt_hash
        _write_json(path, record)
    aggregate_path = root / "evidence/stage6/latest.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["candidate_commit"] = execution_candidate
    aggregate["candidate_tree"] = candidate_tree
    aggregate["execution_receipt"]["sha256"] = receipt_hash
    _write_json(aggregate_path, aggregate)

    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "anchor receipt",
        "-m",
        f"MooMooAU-Execution-Candidate: {execution_candidate}\n"
        f"MooMooAU-Execution-Receipt-SHA256: {receipt_hash}",
    )
    review_candidate = _git_run(repository, "rev-parse", "HEAD")
    for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
        path = root / f"machine/stages/S6/reviews/{family}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["subject"]["candidate_commit"] = review_candidate
        record["subject"]["candidate_tree"] = candidate_tree
        record["execution_receipt"]["sha256"] = receipt_hash
        record["attempts"][17]["execution_receipt"]["sha256"] = receipt_hash
        _write_json(path, record)

    anchored_execution, anchor_errors = validate_stage6_receipt_anchor(
        root,
        repository,
        review_candidate,
        candidate_tree,
    )
    assert anchored_execution == execution_candidate
    assert anchor_errors == []
    assert validate_stage6_candidate_bundle(root, repository) == []

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["commands"][0]["result_summary"] = "Synchronized replacement remains local."
    _write_json(receipt_path, receipt)
    replacement_hash = _sha256(receipt_path)
    for task_id in STAGE6_TASK_COMMAND_IDS:
        path = root / f"evidence/tasks/{task_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["execution_binding"]["sha256"] = replacement_hash
        _write_json(path, record)
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["execution_receipt"]["sha256"] = replacement_hash
    _write_json(aggregate_path, aggregate)
    for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
        path = root / f"machine/stages/S6/reviews/{family}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["execution_receipt"]["sha256"] = replacement_hash
        record["attempts"][17]["execution_receipt"]["sha256"] = replacement_hash
        _write_json(path, record)

    assert "Stage 6 receipt anchor digest trailer differs from the exact receipt" in (
        validate_stage6_candidate_bundle(root, repository)
    )


def test_rmd05_post_review_effect_surface_drift_is_rejected(tmp_path: Path) -> None:
    cases = (
        (".github/workflows/moomooau-production.yml", True),
        ("LinzeDatabase/MooMooAU/machine/tools/capture_candidate_gates.py", True),
        ("LinzeDatabase/MooMooAU/machine/tools/build_delivery_status.py", True),
        ("LinzeDatabase/MooMooAU/machine/tools/build_governance_facts.py", True),
        ("LinzeDatabase/MooMooAU/machine/tools/build_package_manifest.py", True),
        ("LinzeDatabase/MooMooAU/machine/tools/validate_delivery_status.py", True),
        ("LinzeDatabase/MooMooAU/machine/tools/validate_package.py", True),
        ("LinzeDatabase/MooMooAU/machine/acceptance/evidence.py", True),
        ("LinzeDatabase/MooMooAU/machine/acceptance/build_evidence.py", True),
        (
            "LinzeDatabase/MooMooAU/machine/acceptance/schemas/acceptance-summary-v1.schema.json",
            True,
        ),
        ("LinzeDatabase/MooMooAU/machine/contracts/delivery_status_model.json", True),
        ("LinzeDatabase/MooMooAU/machine/status/latest.json", True),
        ("LinzeDatabase/MooMooAU/evidence/stage6/latest.json", True),
        ("LinzeDatabase/MooMooAU/evidence/tasks/T0601.json", True),
        ("LinzeDatabase/MooMooAU/taskpack/PACKAGE_MANIFEST.v1.0.5.json", True),
        ("LinzeDatabase/MooMooAU/taskpack/SOURCE_PROVENANCE.v1.0.5.json", True),
        ("LinzeDatabase/MooMooAU/machine/facts/status.json", True),
        ("LinzeDatabase/MooMooAU/machine/facts/metrics.json", True),
        ("LinzeDatabase/MooMooAU/evidence/acceptance/unexpected.json", True),
        ("LinzeDatabase/MooMooAU/README.md", False),
    )
    drift_error = (
        "reviewed effect, workflow, dependency, test or assurance surface changed after review"
    )
    for index, (relative, should_block) in enumerate(cases):
        repository = tmp_path / f"repository-{index}"
        repository.mkdir()
        _git_run(repository, "init", "--quiet")
        seed = repository / "seed.txt"
        seed.write_text("candidate\n", encoding="utf-8")
        _git_run(repository, "add", "seed.txt")
        _git_run(
            repository,
            "-c",
            "user.name=RMD05 Test",
            "-c",
            "user.email=rmd05.invalid",
            "commit",
            "--quiet",
            "-m",
            "candidate",
        )
        candidate = _git_run(repository, "rev-parse", "HEAD")
        candidate_tree = _git_run(repository, "rev-parse", "HEAD^{tree}")
        changed = repository / relative
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text("post-review change\n", encoding="utf-8")
        _git_run(repository, "add", relative)
        _git_run(
            repository,
            "-c",
            "user.name=RMD05 Test",
            "-c",
            "user.email=rmd05.invalid",
            "commit",
            "--quiet",
            "-m",
            "post-review",
        )

        errors: list[str] = []
        _validate_git_subject(repository, candidate, candidate_tree, errors)

        assert (drift_error in errors) is should_block


def test_rmd05_final_authority_allowance_rejects_every_nonexact_descendant_path(
    tmp_path: Path,
) -> None:
    drift_error = (
        "reviewed effect, workflow, dependency, test or assurance surface changed after review"
    )
    cases = (
        "LinzeDatabase/MooMooAU/machine/acceptance/evidence.py",
        "LinzeDatabase/MooMooAU/machine/acceptance/build_evidence.py",
        "LinzeDatabase/MooMooAU/machine/acceptance/schemas/acceptance-evidence-v1.schema.json",
        "LinzeDatabase/MooMooAU/machine/facts/metrics.json",
        "LinzeDatabase/MooMooAU/machine/facts/unexpected.json",
        "LinzeDatabase/MooMooAU/evidence/acceptance/unexpected.json",
        "LinzeDatabase/MooMooAU/evidence/acceptance/oracles/AC-001-forged.json",
    )
    for index, relative in enumerate(cases):
        repository = tmp_path / f"allowance-repository-{index}"
        repository.mkdir()
        _git_run(repository, "init", "--quiet")
        seed = repository / "seed.txt"
        seed.write_text("candidate\n", encoding="utf-8")
        _git_run(repository, "add", "seed.txt")
        _git_run(
            repository,
            "-c",
            "user.name=RMD05 Test",
            "-c",
            "user.email=rmd05.invalid",
            "commit",
            "--quiet",
            "-m",
            "candidate",
        )
        candidate = _git_run(repository, "rev-parse", "HEAD")
        candidate_tree = _git_run(repository, "rev-parse", "HEAD^{tree}")
        changed = repository / relative
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text("post-review bypass\n", encoding="utf-8")
        _git_run(repository, "add", relative)
        _git_run(
            repository,
            "-c",
            "user.name=RMD05 Test",
            "-c",
            "user.email=rmd05.invalid",
            "commit",
            "--quiet",
            "-m",
            "post-review bypass",
        )

        errors: list[str] = []
        authorities = _validate_git_subject(
            repository,
            candidate,
            candidate_tree,
            errors,
            allow_post_review_authorities=True,
        )

        assert authorities == []
        assert drift_error in errors


def test_rmd05_final_authority_allowance_contains_only_exact_builder_outputs(
    tmp_path: Path,
) -> None:
    status_path = "LinzeDatabase/MooMooAU/machine/status/latest.json"
    assert status_path in POST_REVIEW_AUTHORITY_PATHS
    assert "LinzeDatabase/MooMooAU/machine/facts/status.json" in POST_REVIEW_AUTHORITY_PATHS
    assert "LinzeDatabase/MooMooAU/machine/facts/metrics.json" not in POST_REVIEW_AUTHORITY_PATHS
    assert (
        "LinzeDatabase/MooMooAU/evidence/acceptance/AC-001-zero-collateral.json"
        in POST_REVIEW_AUTHORITY_PATHS
    )
    assert (
        "LinzeDatabase/MooMooAU/evidence/acceptance/unexpected.json"
        not in POST_REVIEW_AUTHORITY_PATHS
    )

    repository = tmp_path / "exact-authority-repository"
    repository.mkdir()
    _git_run(repository, "init", "--quiet")
    seed = repository / "seed.txt"
    seed.write_text("candidate\n", encoding="utf-8")
    _git_run(repository, "add", "seed.txt")
    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "-m",
        "candidate",
    )
    candidate = _git_run(repository, "rev-parse", "HEAD")
    candidate_tree = _git_run(repository, "rev-parse", "HEAD^{tree}")
    status = repository / status_path
    status.parent.mkdir(parents=True)
    status.write_text("{}\n", encoding="utf-8")
    _git_run(repository, "add", status_path)
    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "-m",
        "exact authority",
    )

    errors: list[str] = []
    authorities = _validate_git_subject(
        repository,
        candidate,
        candidate_tree,
        errors,
        allow_post_review_authorities=True,
    )

    assert authorities == [status_path]
    assert (
        "reviewed effect, workflow, dependency, test or assurance surface changed after review"
        not in errors
    )


def test_rmd05_post_review_authorities_require_exact_deterministic_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "MooMooAU"
    expected_status = {"status": "closed"}
    expected_facts = {"status.json": {"status": "closed"}}
    expected_manifest = {"manifest": "canonical"}
    (root / "machine/status").mkdir(parents=True)
    (root / "machine/status/latest.json").write_text(
        json.dumps(expected_status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    facts_path = root / "machine/facts/status.json"
    facts_path.parent.mkdir(parents=True)
    facts_path.write_text(
        json.dumps(expected_facts["status.json"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    provenance = {"source": "closed"}
    (root / "taskpack").mkdir(parents=True)
    (root / "taskpack/SOURCE_PROVENANCE.v1.0.5.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "taskpack/PACKAGE_MANIFEST.v1.0.5.json").write_text(
        json.dumps(expected_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(assurance_reviews, "validate_stage6_candidate_bundle", lambda *_: [])
    monkeypatch.setattr(assurance_reviews, "GOVERNANCE_DOCUMENT_AUTHORITY_SHA256", {})
    monkeypatch.setattr(acceptance_evidence, "validate_bundle", lambda *_: [])
    monkeypatch.setattr(delivery_status, "build_status", lambda *_args, **_kwargs: expected_status)
    monkeypatch.setattr(governance_facts, "build_facts", lambda *_: expected_facts)
    monkeypatch.setattr(package_manifest, "build_manifest", lambda *_: expected_manifest)
    monkeypatch.setattr(
        package_manifest,
        "MANIFEST_PATH",
        Path("taskpack/PACKAGE_MANIFEST.v1.0.5.json"),
    )
    monkeypatch.setattr(
        package_validation,
        "PROVENANCE_PATH",
        Path("taskpack/SOURCE_PROVENANCE.v1.0.5.json"),
    )
    monkeypatch.setattr(
        package_validation,
        "_validate_provenance",
        lambda _root, _failures: None,
    )
    monkeypatch.setattr(package_validation, "build_provenance", lambda: provenance)

    errors: list[str] = []
    _validate_post_review_authorities(root, tmp_path, ["authority"], errors)
    assert errors == []

    failure_cases = (
        (
            assurance_reviews,
            "validate_stage6_candidate_bundle",
            lambda *_: ["drift"],
            "post-review Stage 6 evidence authority differs from its exact receipt binding",
        ),
        (
            acceptance_evidence,
            "validate_bundle",
            lambda *_: ["drift"],
            "post-review Acceptance evidence authority differs from deterministic evidence",
        ),
        (
            delivery_status,
            "build_status",
            lambda *_args, **_kwargs: {"status": "tampered"},
            "post-review delivery status authority differs from deterministic evidence",
        ),
        (
            governance_facts,
            "build_facts",
            lambda *_: {"status.json": {"status": "tampered"}},
            "post-review governance facts differ from deterministic evidence",
        ),
        (
            package_validation,
            "_validate_provenance",
            lambda _root, failures: failures.append("drift"),
            "post-review source-provenance authority differs from the closed protocol",
        ),
        (
            package_manifest,
            "build_manifest",
            lambda *_: {"manifest": "tampered"},
            "post-review package authority differs from the canonical package selection",
        ),
    )
    for module, name, replacement, expected_error in failure_cases:
        with monkeypatch.context() as scoped:
            scoped.setattr(module, name, replacement)
            errors = []
            _validate_post_review_authorities(root, tmp_path, ["authority"], errors)
            assert expected_error in errors


def test_rmd05_authority_delta_equals_the_exact_deterministic_builder_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    root = repository / "MooMooAU"
    root.mkdir(parents=True)
    _git_run(repository, "init", "--quiet")
    seed = repository / "seed.txt"
    seed.write_text("candidate\n", encoding="utf-8")
    _write_json(
        root / "evidence/acceptance/latest.json",
        {
            "observed_at_utc": "2026-07-22T00:00:00Z",
            "remediation_base_commit": "0" * 40,
        },
    )
    _git_run(repository, "add", "seed.txt", "MooMooAU/evidence/acceptance/latest.json")
    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "-m",
        "candidate",
    )
    candidate = _git_run(repository, "rev-parse", "HEAD")

    stage6_relatives = {
        "evidence/stage6/latest.json",
        *(f"evidence/tasks/T060{index}.json" for index in range(1, 9)),
    }
    expected_status = {"status": "closed"}
    expected_facts = {"status.json": {"status": "closed"}}
    expected_provenance = {"source": "closed"}
    expected_manifest = {"manifest": "canonical"}
    for relative in sorted(stage6_relatives):
        _write_json(root / relative, {"authority": relative})
    for relative, value in (
        ("machine/status/latest.json", expected_status),
        ("machine/facts/status.json", expected_facts["status.json"]),
        ("taskpack/SOURCE_PROVENANCE.v1.0.5.json", expected_provenance),
        ("taskpack/PACKAGE_MANIFEST.v1.0.5.json", expected_manifest),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    _git_run(repository, "add", "MooMooAU")
    _git_run(
        repository,
        "-c",
        "user.name=RMD05 Test",
        "-c",
        "user.email=rmd05.invalid",
        "commit",
        "--quiet",
        "-m",
        "materialized authorities",
    )
    authority_paths = _git_run(
        repository,
        "diff",
        "--name-only",
        f"{candidate}..HEAD",
        "--",
    ).splitlines()
    expected_relatives = stage6_relatives | {
        "machine/status/latest.json",
        "machine/facts/status.json",
        "taskpack/SOURCE_PROVENANCE.v1.0.5.json",
        "taskpack/PACKAGE_MANIFEST.v1.0.5.json",
    }

    monkeypatch.setattr(assurance_reviews, "validate_stage6_candidate_bundle", lambda *_: [])
    monkeypatch.setattr(assurance_reviews, "GOVERNANCE_DOCUMENT_AUTHORITY_SHA256", {})
    monkeypatch.setattr(acceptance_evidence, "validate_bundle", lambda *_: [])
    monkeypatch.setattr(acceptance_evidence, "build_bundle", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(delivery_status, "build_status", lambda *_args, **_kwargs: expected_status)
    monkeypatch.setattr(governance_facts, "build_facts", lambda *_: expected_facts)
    monkeypatch.setattr(package_validation, "_validate_provenance", lambda *_: None)
    monkeypatch.setattr(package_validation, "build_provenance", lambda: expected_provenance)
    monkeypatch.setattr(package_manifest, "build_manifest", lambda *_: expected_manifest)
    monkeypatch.setattr(
        package_manifest,
        "MANIFEST_PATH",
        Path("taskpack/PACKAGE_MANIFEST.v1.0.5.json"),
    )
    monkeypatch.setattr(
        package_validation,
        "PROVENANCE_PATH",
        Path("taskpack/SOURCE_PROVENANCE.v1.0.5.json"),
    )
    monkeypatch.setattr(
        assurance_reviews,
        "POST_REVIEW_AUTHORITY_RELATIVE_PATHS",
        frozenset(expected_relatives),
    )

    errors: list[str] = []
    _validate_post_review_authorities(
        root,
        repository,
        authority_paths,
        errors,
        candidate_commit=candidate,
    )
    assert errors == []

    errors = []
    _validate_post_review_authorities(
        root,
        repository,
        authority_paths[:-1],
        errors,
        candidate_commit=candidate,
    )
    assert "post-review authority path delta differs from exact deterministic materialization" in (
        errors
    )


def test_rmd05_structured_receipt_secret_patterns_are_blocked(tmp_path: Path) -> None:
    sensitive_sample = "AGE-" + "SECRET-KEY-1" + "q" * 32
    for name in (
        "execution-receipt.json",
        "execution-receipt2.json",
        "execution-receipt3.json",
        "execution-receipt4.json",
        "execution-receipt5.json",
        "execution-receipt6.json",
        "execution-receipt7.json",
        "execution-receipt8.json",
        "execution-receipt9.json",
        "execution-receipt10.json",
        "execution-receipt11.json",
        "execution-receipt12.json",
        "execution-receipt13.json",
        "execution-receipt14.json",
        "execution-receipt15.json",
        "execution-receipt16.json",
        "execution-receipt17.json",
    ):
        receipt = tmp_path / f"machine/stages/S6/reviews/rmd05/{name}"
        _write_json(receipt, {"digest": "a" * 64})
        assert _structured_receipt_failures(tmp_path) == []

        _write_json(receipt, {"digest": "a" * 64, "sample": sensitive_sample})
        assert _structured_receipt_failures(tmp_path) == [
            f"structured receipt contains a sensitive pattern: "
            f"machine/stages/S6/reviews/rmd05/{name}"
        ]
        receipt.unlink()


def test_rmd05_structured_review_hashes_are_not_secrets_but_age_keys_are_blocked(
    tmp_path: Path,
) -> None:
    sensitive_sample = "AGE-" + "SECRET-KEY-1" + "q" * 32
    for family in ("gpt-5.6-sol", "gpt-5.6-terra"):
        provenance = tmp_path / f"machine/stages/S6/reviews/{family}.json"
        _write_json(provenance, {"sha256": "a" * 64})
        assert _structured_review_failures(tmp_path) == []

        _write_json(provenance, {"sha256": "a" * 64, "sample": sensitive_sample})
        assert _structured_review_failures(tmp_path) == [
            "structured review provenance contains a sensitive pattern: "
            f"machine/stages/S6/reviews/{family}.json"
        ]
        provenance.unlink()


def test_rmd05_shared_evidence_validator_supports_preclosure_and_candidate_bound_stage6() -> None:
    assert S6_EVIDENCE_SCHEMAS == {
        "moomooau.stage6-evidence.v1": Path(
            "machine/stages/S6/schemas/stage6-evidence-v1.schema.json"
        ),
        "moomooau.stage6-evidence.v2": Path(
            "machine/stages/S6/schemas/stage6-evidence-v2.schema.json"
        ),
    }


def test_rmd05_stage6_validator_reuses_shared_task_command_bindings() -> None:
    validator_source = (PROJECT_ROOT / "machine/stages/S6/tools/validate_stage6.py").read_text(
        encoding="utf-8"
    )

    assert "STAGE6_TASK_COMMAND_IDS[task_id]" in validator_source
    assert "expected_task_commands =" not in validator_source


def test_rmd05_stage6_review_input_help_matches_the_rejected_history() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "machine/stages/S6/tools/validate_stage6.py"),
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    normalized_help = " ".join(completed.stdout.split())
    assert "seventeen-attempt superseded history" in normalized_help
    assert "fifteen-attempt superseded history" not in normalized_help
    assert "fourteen-attempt rejected history" not in normalized_help
    assert "thirteen-attempt rejected history" not in normalized_help
    assert "twelve-attempt rejected history" not in normalized_help
    assert "eleven-attempt rejected history" not in normalized_help
    assert "nine-attempt history" not in normalized_help


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    (
        ("dependency_credential_kind", "GITHUB_APP"),
        ("production_secret_reads_authorized", 1),
    ),
)
def test_rmd06_package_provenance_rejects_dependency_auth_scope_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    wrong_value: object,
) -> None:
    provenance = package_validation.build_provenance()
    path = tmp_path / "SOURCE_PROVENANCE.v1.0.7.json"
    monkeypatch.setattr(package_validation, "PROVENANCE_PATH", path)
    _write_json(path, provenance)
    failures: list[str] = []
    _validate_provenance(PROJECT_ROOT, failures)
    assert failures == []

    provenance["semantic_delta"][field] = wrong_value
    _write_json(path, provenance)
    failures = []
    _validate_provenance(PROJECT_ROOT, failures)
    assert failures == [
        "v1.0.7 provenance differs from the exact deterministic authority",
        "v1.0.7 semantic delta is incomplete or overstated",
    ]


def test_rmd05_closed_state_requires_the_complete_stage6_v2_bundle(tmp_path: Path) -> None:
    root = _build_stage6_candidate_evidence_bundle(tmp_path)
    records = {
        task_id: json.loads((root / f"evidence/tasks/{task_id}.json").read_text(encoding="utf-8"))
        for task_id in STAGE6_TASK_COMMAND_IDS
    }

    assert validate_stage6_candidate_bundle(root) == []
    _validate_stage6_evidence_transition(root, {"package_version": "1.0.5"}, records)

    v1_records = copy.deepcopy(records)
    for record in v1_records.values():
        record["schema_version"] = "moomooau.stage6-evidence.v1"
        record.pop("candidate_commit")
        record.pop("candidate_tree")
        record.pop("execution_binding")
    _validate_stage6_evidence_transition(PROJECT_ROOT, {"package_version": "1.0.4"}, v1_records)
    with pytest.raises(ValueError, match="requires Stage 6 v2 evidence"):
        _validate_stage6_evidence_transition(
            PROJECT_ROOT,
            {"package_version": "1.0.5"},
            v1_records,
        )


@pytest.mark.parametrize(
    "mutation",
    ("missing_aggregate", "stale_receipt_hash", "crossed_candidate"),
)
def test_rmd05_stage6_candidate_bundle_rejects_crossed_or_incomplete_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = _build_stage6_candidate_evidence_bundle(tmp_path)
    if mutation == "missing_aggregate":
        (root / "evidence/stage6/latest.json").unlink()
    else:
        path = root / "evidence/tasks/T0601.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "stale_receipt_hash":
            record["execution_binding"]["sha256"] = "f" * 64
        else:
            record["candidate_commit"] = "e" * 40
        _write_json(path, record)

    assert validate_stage6_candidate_bundle(root)


def test_rmd06_delivery_status_schema_couples_v104_to_v106_transition() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads(
        (PROJECT_ROOT / "schemas/delivery-status-v1.schema.json").read_text(encoding="utf-8")
    )
    current = json.loads((PROJECT_ROOT / "machine/status/latest.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(current))

    preclosure = copy.deepcopy(current)
    preclosure["package_version"] = "1.0.4"
    preclosure["resolved_review_findings"] = [
        "REV-P0-002",
        "REV-P0-003",
        "REV-P1-004",
        "REV-P2-007",
    ]
    preclosure["blockers"] = [
        "FORMAL_TASKS_INCOMPLETE",
        "PROTECTED_ORACLES_NOT_RUN",
        "FINAL_ACCEPTANCE_BLOCKED",
        "PRODUCTION_WORKFLOW_NOT_RUN",
        "RMD-05_ASSURANCE_PROVENANCE_PENDING",
        "FINAL_CLEAN_SNAPSHOT_AND_PUBLICATION_WITHHELD",
    ]
    preclosure["next_action"] = (
        "Finalize RMD-05 assurance provenance; keep protected Oracles, production execution and "
        "publication blocked."
    )
    assert not list(validator.iter_errors(preclosure))

    crossed_ready_facts = copy.deepcopy(current)
    crossed_ready_facts["package_version"] = "1.0.4"
    assert list(validator.iter_errors(crossed_ready_facts))

    crossed_preclosure_facts = copy.deepcopy(preclosure)
    crossed_preclosure_facts["package_version"] = "1.0.6"
    assert list(validator.iter_errors(crossed_preclosure_facts))

    unsupported = copy.deepcopy(current)
    unsupported["package_version"] = "1.0.5"
    assert list(validator.iter_errors(unsupported))


def test_rmd05_delivery_status_builder_fails_closed_until_assurance_passes() -> None:
    model = json.loads(
        (PROJECT_ROOT / "machine/contracts/delivery_status_model.json").read_text(encoding="utf-8")
    )

    assert _select_transition_state(model, {"status": "BLOCKED"}, None) == (
        "PRE_CLOSURE",
        model["states"]["PRE_CLOSURE"],
    )
    assert _select_transition_state(model, {"status": "UNKNOWN"}, None) == (
        "PRE_CLOSURE",
        model["states"]["PRE_CLOSURE"],
    )
    assert _select_transition_state(model, {"status": "PASS"}, None) == (
        "DEPENDENCY_AUTH_READY",
        model["states"]["DEPENDENCY_AUTH_READY"],
    )
    failed_receipt = {
        "claims": {
            "t0702_complete": False,
            "s7ac_002_passed": False,
        }
    }
    assert _select_transition_state(model, {"status": "PASS"}, failed_receipt) == (
        "PROTECTED_BETA_ATTEMPT_FAILED",
        model["states"]["PROTECTED_BETA_ATTEMPT_FAILED"],
    )
    passed_receipt = {
        "claims": {
            "t0702_complete": True,
            "s7ac_002_passed": True,
        }
    }
    assert _select_transition_state(model, {"status": "PASS"}, passed_receipt) == (
        "PROTECTED_BETA_PASS_SCOPE_STOP",
        model["states"]["PROTECTED_BETA_PASS_SCOPE_STOP"],
    )
