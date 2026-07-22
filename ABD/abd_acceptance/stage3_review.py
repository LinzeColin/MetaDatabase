from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .advice_card import (
    DISPLAY_ORDER,
    build_advice_card,
    contrast_ratio,
    evaluate_contract as evaluate_p02,
    extract_primary_answers,
    render_visible_text,
    validate_card,
    verify_existing_phase_evidence as verify_p02,
)
from .canonical_facts import sha256_file, strict_json_load
from .reason_next_action import (
    evaluate_contract as evaluate_p03,
    render_failure_guidance,
    resolve_failure_states,
    validate_resolution,
    verify_existing_phase_evidence as verify_p03,
)
from .stage2_delivery import verify_stage2_delivery
from .terminology_governance import (
    evaluate_contract as evaluate_p01,
    scan_ui_text,
    verify_existing_phase_evidence as verify_p01,
)
from .usability_accessibility import (
    FAILURE_GUIDANCE_ORDER,
    evaluate_contract as evaluate_p04,
    evaluate_timing_gate,
    verify_existing_phase_evidence as verify_p04,
)


CONTRACT_ID = "STAGE-REVIEW-S03"
REVIEW_ID = "ABD-S03-WHOLE-STAGE-REVIEW"
STAGE_ID = "S03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T18:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage3_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S03/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S03_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S03/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S03/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S03/STAGE_REVIEW/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S03-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

STRUCTURAL_SELF_NORMALIZED_SHA256 = "72849001b1165eb96e6f9ad0798d3ef1299849db710181d4a1924624cb62dbdf"
STAGE_REVIEW_COMMIT = "4168321dee17540bdba5763271694f78b33e3c42"
PINNED_STAGE_REVIEW_CODE_HASH = "18431889da80b66a6f6c35375859793bee2d811ce14228cec80f69f880902b93"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "tests/S03/stage_review_test.py",
    "abd_acceptance/stage3_review.py",
    "abd_acceptance/usability_accessibility.py",
    "abd_acceptance/reason_next_action.py",
    "abd_acceptance/advice_card.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "README.md": "d687fc424a8ca00602acaa5627c337db020dd58f114acfa5cfe81b6393b6f881",
    "tests/S03/stage_review_test.py": "4a140a8848b2990873c1e568588336d05d24311ce966ed3ed627ac9d7c3e4b5d",
    "abd_acceptance/usability_accessibility.py": "3a140e2062c1a4bdda7492f0b8240ac6c44840aaf3774695bebe25201101f9aa",
    "abd_acceptance/reason_next_action.py": "8dbcc6640745e75723c24eaea40c0fc6ae83742f5520e17c59884be0fdb419c6",
    "abd_acceptance/advice_card.py": "d8ad7722996915fd4743bcf3039492ff102705e001c5926b14cb009a379f1ff5",
    "abd_acceptance/__main__.py": "e29a648fcb0582c2139593cf0d42670893580d30879412664a5605c3772f93cc",
    "abd_acceptance/__init__.py": "969cc5d7d8c8e187b9bfd6679b7b51a47607ceeee703ddcc71be747957636f8e",
}
PINNED_REVIEW_ARTIFACT_HASHES: Dict[str, str] = {
    CONTRACT_PATH.as_posix(): "9466f63e3f8029cba8b518e828b4d22113bf59ae7fa13b44470509ee8732d241",
    FINDINGS_PATH.as_posix(): "e62242685c6091564c92efc9d05be5b061e382cecfaa46bb39ae780eac072ea9",
    FIXTURE_PATH.as_posix(): "ca816f8e50b63fc38c0c1626351957104ad682a72e13455f7e789aa0f2a141bc",
    TEST_PATH.as_posix(): "f9d55d572526e0e81f144d6ecb5c62e83ce0907f1ce5e1315d8bd4e1aa5ed103",
}
WORKFLOW_SHA256 = "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d"

PHASE_EVALUATORS = {"P01": evaluate_p01, "P02": evaluate_p02, "P03": evaluate_p03, "P04": evaluate_p04}
PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_DECISIONS = {
    "P01": "S03_P01_EVIDENCE_VERIFIED",
    "P02": "S03_P02_EVIDENCE_VERIFIED",
    "P03": "S03_P03_EVIDENCE_VERIFIED",
    "P04": "S03_P04_EVIDENCE_VERIFIED",
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("decision_sha256")
    unsigned = deepcopy(dict(evidence))
    unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and _sha256_bytes(_json_bytes(unsigned)) == expected


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/stage3_review.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r'\1<NORMALIZED>\2',
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _stage_review_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", STAGE_REVIEW_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(
    root: Path,
    relative: str,
    expected_sha256: str,
    verify_git_history: bool,
) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if verify_git_history:
        if not _stage_review_commit_is_ancestor(root):
            return False
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (STAGE_REVIEW_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if relative == "abd_acceptance/stage3_review.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    evolved = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return evolved is not None and (root / relative).is_file() and sha256_file(root / relative) == evolved


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _stage_review_commit_is_ancestor(root):
        return "INVALID_STAGE_REVIEW_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", STAGE_REVIEW_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_STAGE_REVIEW_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        line
        for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (STAGE_REVIEW_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_STAGE_REVIEW_COMMIT_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _load_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
        if line
    ]


def _check_review_pins(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> None:
    for relative, expected in PINNED_REVIEW_ARTIFACT_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(
            checks,
            "S03REVIEW-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"),
            actual == expected or (successor is not None and actual == successor),
            {"expected": expected, "accepted_successor": successor, "actual": actual},
        )
    workflow = root.parent / WORKFLOW_PATH
    actual_workflow = sha256_file(workflow) if workflow.is_file() else "MISSING"
    hashes[WORKFLOW_PATH.as_posix()] = actual_workflow
    _add(checks, "S03REVIEW-WORKFLOW-PIN", actual_workflow == WORKFLOW_SHA256, {"expected": WORKFLOW_SHA256, "actual": actual_workflow})
    self_hash = _structural_self_hash(root)
    hashes["abd_acceptance/stage3_review.py"] = sha256_file(root / "abd_acceptance/stage3_review.py")
    _add(
        checks,
        "S03REVIEW-ORACLE-SELF-INTEGRITY",
        self_hash == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_hash},
    )


def _check_contract_shape(contract: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    scope = contract.get("review_scope", {})
    records = contract.get("phase_records", [])
    record_ids = [row.get("phase_id") for row in records if isinstance(row, Mapping)]
    shape = (
        contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and contract.get("fixed_at") == FIXED_CLOCK
        and scope.get("phase_ids") == fixture.get("expected_phase_ids")
        and scope.get("requirement_ids") == ["REQ-S03-P01", "REQ-S03-P02", "REQ-S03-P03", "REQ-S03-P04"]
        and scope.get("acceptance_contract_ids") == ["AC-S03-P01", "AC-S03-P02", "AC-S03-P03", "AC-S03-P04"]
        and len(scope.get("task_ids", [])) == 12
        and len(set(scope.get("task_ids", []))) == 12
        and record_ids == fixture.get("expected_phase_ids")
        and contract.get("review_findings_path") == FINDINGS_PATH.as_posix()
        and contract.get("release_status_on_pass") == fixture.get("expected_release_status")
        and contract.get("next_on_pass") == fixture.get("expected_next")
        and not _contains_float(contract)
    )
    _add(checks, "S03REVIEW-CONTRACT-SHAPE", shape, {"scope": scope, "records": record_ids})
    source_receipts = contract.get("supplied_source_receipts", [])
    source_ok = (
        len(source_receipts) == 2
        and source_receipts[0].get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and source_receipts[0].get("repository_equivalent") == "machine/evidence/roadmap_stage_phase.md"
        and source_receipts[1].get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and source_receipts[1].get("original_file_count") == 53
        and source_receipts[1].get("repository_equivalent_required") is False
    )
    _add(checks, "S03REVIEW-SUPPLIED-SOURCE-RECEIPTS", source_ok, source_receipts)
    boundary = contract.get("external_effect_boundary", {})
    boundary_ok = (
        boundary.get("incremental_cash_spent_aud") == "0.00"
        and boundary.get("owner_final_order_only") is True
        and all(value is False for key, value in boundary.items() if key not in {"incremental_cash_spent_aud", "owner_final_order_only"})
    )
    _add(checks, "S03REVIEW-EXTERNAL-EFFECT-BOUNDARY", boundary_ok, boundary)
    claim = contract.get("claim_boundary", {})
    claim_ok = claim == fixture.get("expected_claim_boundary") and all(
        value is False
        for key, value in claim.items()
        if key != "ten_second_information_gate_kind"
    )
    _add(checks, "S03REVIEW-HUMAN-TIMING-CLAIM-BOUNDARY", claim_ok, claim)
    _add(
        checks,
        "S03REVIEW-UPLOAD-PRECONDITIONS",
        set(contract.get("upload_preconditions", [])) == {
            "ALL_STAGE_PHASES_PASS",
            "WHOLE_STAGE_REVIEW_PASS",
            "ALL_REVIEW_FINDINGS_RESOLVED",
            "FULL_STAGE_REGRESSION_PASS",
            "PAID_DEPENDENCY_SCAN_PASS",
            "CLEAN_WORKTREE_AFTER_COMMIT",
            "NO_INCREMENTAL_CASH_COST",
        },
        contract.get("upload_preconditions"),
    )


def _check_baseline_hashes(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for section in ["baseline_critical_artifacts", "remediated_artifacts"]:
        values = contract.get(section, {})
        if not isinstance(values, Mapping):
            _add(checks, "S03REVIEW-%s-SHAPE" % section.upper().replace("_", "-"), False, values)
            continue
        for relative, expected in values.items():
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            hashes[str(relative)] = actual
            _add(
                checks,
                "S03REVIEW-BASELINE-%s" % str(relative).upper().replace("/", "-").replace(".", "-"),
                actual == expected,
                {"expected": expected, "actual": actual},
            )


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    found = [row for row in rows if row.get(key) == item_id]
    return found[0] if len(found) == 1 else {}


def _check_taskpack_trace(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    tasks = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    traces = strict_json_load(root / "machine/facts/traceability_matrix.json")
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID]
    expected_outputs = [
        ["glossary_zh.json", "forbidden_ui_terms.json"],
        ["advice_card_schema.json", "advice_card_fixtures.json"],
        ["reason_codes_zh.json", "next_action_matrix.json"],
        ["ux_test_plan.json", "accessibility_report.json"],
    ]
    roadmap_ok = (
        len(stages) == 1
        and stages[0].get("depends_on") == ["S00", "S01"]
        and [row.get("id") for row in stages[0].get("phases", [])] == ["P01", "P02", "P03", "P04"]
        and [row.get("outputs") for row in stages[0].get("phases", [])] == expected_outputs
    )
    _add(checks, "S03REVIEW-ROADMAP-TRACE-EXACT", roadmap_ok, stages)
    for record in contract.get("phase_records", []):
        phase = record.get("phase_id")
        req_id = record.get("requirement_id")
        ac_id = record.get("acceptance_contract_id")
        task_ids = record.get("task_ids")
        req = _row(requirements, str(req_id))
        ac = _row(acceptance, str(ac_id))
        phase_tasks = [row for row in tasks if row.get("stage_id") == STAGE_ID and row.get("phase_id") == phase]
        trace = _row(traces, str(req_id), "requirement_id")
        expected_test_ids = ["TEST-S03-%s" % phase, "TEST-S03-%s-BOUNDARY" % phase, "TEST-S03-%s-REPLAY" % phase]
        ok = (
            req.get("stage_id") == STAGE_ID
            and req.get("phase_id") == phase
            and req.get("primary_acceptance_criteria_id") == ac_id
            and ac.get("requirement_id") == req_id
            and ac.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % ac_id
            and [row.get("id") for row in phase_tasks] == task_ids
            and trace.get("acceptance_criteria_id") == ac_id
            and trace.get("task_ids") == task_ids
            and trace.get("test_ids") == expected_test_ids
            and trace.get("evidence_id") == "EVD-S03-%s" % phase
        )
        _add(checks, "S03REVIEW-%s-TASKPACK-TRACE" % phase, ok, {"requirement": req_id, "acceptance": ac_id, "tasks": task_ids})
    stage_tasks = [row for row in tasks if row.get("stage_id") == STAGE_ID]
    expected_ids = contract.get("review_scope", {}).get("task_ids", [])
    dependency_ok = [row.get("id") for row in stage_tasks] == expected_ids
    for index, row in enumerate(stage_tasks):
        expected_dependency = ["T-S00-P04-03", "T-S01-P04-03"] if index == 0 else [expected_ids[index - 1]]
        dependency_ok = dependency_ok and row.get("depends_on") == expected_dependency
    _add(checks, "S03REVIEW-TASK-CHAIN-EXACT", dependency_ok, [row.get("depends_on") for row in stage_tasks])


def _verify_phase(phase_id: str, root: Path, verify_git_history: bool) -> Dict[str, Any]:
    return PHASE_VERIFIERS[phase_id](root, verify_git_history=verify_git_history)


def _evaluate_phase(phase_id: str, root: Path, verify_git_history: bool) -> Dict[str, Any]:
    return PHASE_EVALUATORS[phase_id](root, False, _verify_git_history=verify_git_history)


def _check_phase_receipts_and_oracles(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    verify_git_history: bool,
) -> None:
    expected_evidence = fixture.get("expected_phase_evidence_sha256", {})
    expected_rollback = fixture.get("expected_phase_rollback_sha256", {})
    for record in contract.get("phase_records", []):
        phase = str(record.get("phase_id"))
        try:
            receipt = _verify_phase(phase, root, verify_git_history)
            receipt_ok = (
                receipt.get("status") == "PASS"
                and receipt.get("decision") == PHASE_DECISIONS[phase]
                and receipt.get("next") == record.get("expected_next")
                and receipt.get("evidence_sha256") == expected_evidence.get(phase) == record.get("evidence_sha256")
                and receipt.get("rollback_sha256") == expected_rollback.get(phase) == record.get("rollback_sha256")
            )
            _add(checks, "S03REVIEW-%s-SIGNED-RECEIPT" % phase, receipt_ok, receipt.get("summary"))
        except Exception as exc:
            _add(checks, "S03REVIEW-%s-SIGNED-RECEIPT" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            current = _evaluate_phase(phase, root, verify_git_history)
            current_ok = current.get("status") == "PASS" and current.get("summary", {}).get("failed") == 0
            _add(checks, "S03REVIEW-%s-CURRENT-ORACLE" % phase, current_ok, current.get("summary"))
        except Exception as exc:
            _add(checks, "S03REVIEW-%s-CURRENT-ORACLE" % phase, False, "%s: %s" % (type(exc).__name__, exc))


def _check_cross_phase_surfaces(root: Path, contract: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    glossary = strict_json_load(root / "glossary_zh.json")
    policy = strict_json_load(root / "forbidden_ui_terms.json")
    schema = strict_json_load(root / "advice_card_schema.json")
    card_fixtures = strict_json_load(root / "advice_card_fixtures.json")
    reasons = strict_json_load(root / "reason_codes_zh.json")
    matrix = strict_json_load(root / "next_action_matrix.json")
    plan = strict_json_load(root / "ux_test_plan.json")
    report = strict_json_load(root / "accessibility_report.json")
    parameters_hash = sha256_file(root / "machine/facts/parameters.json")
    model_hash = sha256_file(root / "machine/facts/model_system_card.json")

    _add(
        checks,
        "S03REVIEW-GLOSSARY-TERM-COUNT",
        len(glossary.get("entries", [])) == fixture.get("expected_glossary_term_count"),
        len(glossary.get("entries", [])),
    )
    display = schema.get("x-abd-display-contract", {})
    palette_rows = list(display.get("status_palette", {}).values()) + list(display.get("countdown_palette", {}).values())
    ratios = [contrast_ratio(row.get("background", ""), row.get("foreground", "")) for row in palette_rows]
    presentation_ok = (
        display.get("section_order") == fixture.get("expected_display_order") == DISPLAY_ORDER
        and display.get("color_is_only_signal") is False
        and display.get("required_redundant_signals") == ["中文状态文字", "状态符号", "明确行动句"]
        and ratios
        and min(ratios) >= 4.5
    )
    _add(checks, "S03REVIEW-ADVICE-PRESENTATION-A11Y", presentation_ok, {"order": display.get("section_order"), "ratios": ratios})

    card_errors: List[Dict[str, Any]] = []
    built_cards: List[Mapping[str, Any]] = []
    for vector_name in ["base_recommendation_input", "base_no_recommendation_input"]:
        try:
            first = build_advice_card(
                card_fixtures[vector_name],
                schema=schema,
                glossary=glossary,
                policy=policy,
                parameters_sha256=parameters_hash,
                model_sha256=model_hash,
            )
            second = build_advice_card(
                deepcopy(card_fixtures[vector_name]),
                schema=schema,
                glossary=glossary,
                policy=policy,
                parameters_sha256=parameters_hash,
                model_sha256=model_hash,
            )
            errors = validate_card(first, schema=schema, glossary=glossary, policy=policy)
            ui_errors = scan_ui_text(render_visible_text(first, schema), "ADVICE_CARD", glossary, policy)
            answers = extract_primary_answers(first)
            if first != second or errors or ui_errors or list(answers) != ["what_zh", "where_zh", "amount_zh", "minimum_odds_zh"]:
                card_errors.append({"vector": vector_name, "errors": errors, "ui_errors": ui_errors, "answers": answers})
            built_cards.append(first)
        except Exception as exc:
            card_errors.append({"vector": vector_name, "error": "%s: %s" % (type(exc).__name__, exc)})
    _add(checks, "S03REVIEW-ADVICE-AND-NO-ADVICE-CHINESE-DETERMINISTIC", not card_errors and len(built_cards) == 2, card_errors or [row.get("status") for row in built_cards])

    reason_rows = reasons.get("reason_codes", [])
    action_rows = matrix.get("actions", [])
    replay_errors: List[Dict[str, Any]] = []
    replay_hashes: List[str] = []
    for row in reason_rows:
        code = row.get("code") if isinstance(row, Mapping) else None
        try:
            first = resolve_failure_states([code], reason_catalog=reasons, next_action_matrix=matrix)
            second = resolve_failure_states([code], reason_catalog=reasons, next_action_matrix=matrix)
            validation_errors = validate_resolution(first, reason_catalog=reasons, next_action_matrix=matrix, glossary=glossary, policy=policy)
            ui_errors = scan_ui_text(render_failure_guidance(first), "USER_ERROR_NEXT_ACTION", glossary, policy)
            if first != second or validation_errors or ui_errors or first.get("considered_count") != 1:
                replay_errors.append({"code": code, "validation": validation_errors, "ui": ui_errors})
            replay_hashes.append(str(first.get("provenance", {}).get("artifact_sha256")))
        except Exception as exc:
            replay_errors.append({"code": code, "error": "%s: %s" % (type(exc).__name__, exc)})
    failure_ok = (
        len(reason_rows) == fixture.get("expected_reason_count")
        and len(action_rows) == fixture.get("expected_action_count")
        and len(replay_hashes) == len(set(replay_hashes)) == fixture.get("expected_reason_count")
        and not replay_errors
    )
    _add(checks, "S03REVIEW-ALL-USER-SURFACES-CHINESE-AND-UNIQUE", failure_ok, replay_errors or {"replayed": len(replay_hashes)})

    integration = plan.get("failure_guidance_integration", {})
    assessment = report.get("failure_guidance_assessment", {})
    failure_order_ok = (
        integration.get("source_contract_id") == "AC-S03-P03"
        and integration.get("declared_reason_count") == fixture.get("expected_reason_count")
        and integration.get("region_order") == fixture.get("expected_failure_guidance_order") == FAILURE_GUIDANCE_ORDER
        and integration.get("keyboard_focus_order") == FAILURE_GUIDANCE_ORDER
        and integration.get("screen_reader_order") == FAILURE_GUIDANCE_ORDER
        and integration.get("machine_code_visible") is False
        and integration.get("exactly_one_next_action_required") is True
        and integration.get("chinese_ui_gate_required") is True
        and integration.get("runtime_status") == "NOT_EXECUTED"
        and assessment.get("deterministically_replayed_reason_count") == fixture.get("expected_reason_count")
        and assessment.get("unique_next_action_gate_status") == "PASS"
        and assessment.get("chinese_ui_gate_status") == "PASS"
        and assessment.get("runtime_status") == "NOT_EXECUTED"
    )
    _add(checks, "S03REVIEW-FAILURE-GUIDANCE-A11Y-BINDING", failure_order_ok, {"integration": integration, "assessment": assessment})

    durations = [row.get("budget_seconds") for row in plan.get("scenario_budgets", [])]
    timing = evaluate_timing_gate(durations)
    expected_timing = fixture.get("expected_budget_summary", {})
    timing_ok = (
        len(durations) == fixture.get("expected_budget_count")
        and len(plan.get("profiles", [])) == fixture.get("expected_profile_count")
        and timing.get("median_seconds") == expected_timing.get("median_seconds")
        and timing.get("p95_seconds") == expected_timing.get("p95_seconds")
        and timing.get("median_max_seconds") == expected_timing.get("median_max_seconds")
        and timing.get("p95_max_seconds") == expected_timing.get("p95_max_seconds")
        and timing.get("status") == "PASS"
    )
    _add(checks, "S03REVIEW-FROZEN-TASK-BUDGET-GATE", timing_ok, timing)
    ten_second = schema.get("x-abd-contract", {}).get("ten_second_information_gate", {})
    claim = contract.get("claim_boundary", {})
    report_claim = report.get("claim_boundary", {})
    claim_ok = (
        ten_second.get("human_timing_validation") == "DEFERRED_TO_S03_P04"
        and claim == fixture.get("expected_claim_boundary")
        and claim.get("ten_second_information_gate_kind") == "STRUCTURAL_INFORMATION_PLACEMENT_ONLY"
        and all(value is False for key, value in claim.items() if key != "ten_second_information_gate_kind")
        and report_claim.get("human_timing_observed") is False
        and report_claim.get("human_usability_conclusion_claimed") is False
        and report_claim.get("production_ui_implemented") is False
        and report_claim.get("production_ui_deployed") is False
        and report_claim.get("real_device_or_browser_run_executed") is False
        and report_claim.get("screen_reader_runtime_run_executed") is False
        and report_claim.get("formal_wcag_conformance_claimed") is False
    )
    _add(checks, "S03REVIEW-TEN-SECOND-NOT-HUMAN-TIMING", claim_ok, {"ten_second": ten_second, "claim": claim, "report": report_claim})
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        regular = evaluate_timing_gate(durations, numeric_boundary_delta=delta, adverse_odds_tick=False)
        adverse = evaluate_timing_gate(durations, numeric_boundary_delta=delta, adverse_odds_tick=True)
        _add(
            checks,
            "S03REVIEW-NUMERIC-ADVERSE-INVARIANT-%s" % str(delta).replace("-", "MINUS").replace(".", "_"),
            regular.get("status") == adverse.get("status") == "PASS"
            and regular.get("median_seconds") == adverse.get("median_seconds")
            and regular.get("p95_seconds") == adverse.get("p95_seconds"),
            {"regular": regular, "adverse": adverse},
        )


def _check_findings(findings: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    rows = findings.get("findings", [])
    ids = [row.get("id") for row in rows if isinstance(row, Mapping)]
    rows_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_at") == FIXED_CLOCK
        and ids == fixture.get("expected_finding_ids")
        and len(ids) == len(set(ids)) == 5
        and all(
            row.get("status") == "RESOLVED_IN_REVIEW_CANDIDATE"
            and row.get("severity") in {"HIGH", "MEDIUM"}
            and isinstance(row.get("verification_gate"), str)
            for row in rows
        )
    )
    _add(checks, "S03REVIEW-FINDINGS-EXACT-RESOLVED", rows_ok, ids)
    summary = findings.get("summary", {})
    _add(
        checks,
        "S03REVIEW-FINDINGS-SUMMARY",
        summary == {"total": 5, "resolved_in_review_candidate": 5, "open": 0, "remote_ci_pending_is_upload_evidence_not_an_open_code_finding": True},
        summary,
    )
    boundary = findings.get("scope_boundaries", {})
    boundary_ok = (
        boundary.get("incremental_cash_spent_aud") == "0.00"
        and all(value is False for key, value in boundary.items() if key != "incremental_cash_spent_aud")
    )
    _add(checks, "S03REVIEW-FINDINGS-SCOPE-BOUNDARY", boundary_ok, boundary)


def _iter_text_files(root: Path) -> Iterable[Path]:
    for relative in [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, Path("README.md")]:
        path = root / relative
        if path.is_file():
            yield path


def _check_predecessor_monotonic_progression(root: Path, checks: List[Dict[str, Any]], verify_git_history: bool) -> None:
    try:
        from .stage2_review import evaluate_contract as evaluate_stage2_review

        result = evaluate_stage2_review(
            root,
            require_external_reports=False,
            _verify_history=verify_git_history,
            _verify_phase_oracles=False,
        )
        matching = [row for row in result.get("checks", []) if row.get("id") == "S02REVIEW-S03-NOT-STARTED"]
        detail = matching[0].get("detail", {}) if len(matching) == 1 else {}
        successor = detail.get("successor", {}) if isinstance(detail, Mapping) else {}
        mode = successor.get("mode") if isinstance(successor, Mapping) else None
        passed = (
            result.get("status") == "PASS"
            and len(matching) == 1
            and matching[0].get("passed") is True
            and mode in {"VERIFIED_S03_P04_SUCCESSOR", "VERIFIED_S03_STAGE_REVIEW_SUCCESSOR"}
        )
        _add(
            checks,
            "S03REVIEW-PREDECESSOR-MONOTONIC-PROGRESSION",
            passed,
            {"stage2_summary": result.get("summary"), "successor_mode": mode, "progression": detail},
        )
    except Exception as exc:
        _add(
            checks,
            "S03REVIEW-PREDECESSOR-MONOTONIC-PROGRESSION",
            False,
            "%s: %s" % (type(exc).__name__, exc),
        )


def _check_safety_and_progression(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], verify_git_history: bool) -> None:
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    product = canonical.get("product", {})
    baseline_ok = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("monthly_target_return") == "0.30"
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and costs.get("incremental_cash_budget", {}).get("low") == "0.00"
        and costs.get("incremental_cash_budget", {}).get("likely") == "0.00"
        and costs.get("incremental_cash_budget", {}).get("high") == "0.00"
    )
    _add(checks, "S03REVIEW-A300-A0-NO-GUARANTEE", baseline_ok, {"product": product, "target": parameters.get("target_30pct"), "cost": costs.get("incremental_cash_budget")})
    try:
        delivery = verify_stage2_delivery(root, verify_git_history=verify_git_history)
        delivery_ok = delivery.get("status") == "PASS" and delivery.get("decision") == "S02_DELIVERED_S03_MAY_START" and delivery.get("next") == "S03/P01_READY_NOT_STARTED"
        _add(checks, "S03REVIEW-S02-DELIVERY-PREREQUISITE", delivery_ok, delivery.get("summary"))
    except Exception as exc:
        _add(checks, "S03REVIEW-S02-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    s04_candidate_paths = [
        Path("infra/compose.yml"),
        Path("infra/config.schema.json"),
        Path("infra/systemd/abd.service"),
        Path("infra/rebuild.sh"),
        Path("tests/S04/P01_test.py"),
        Path("machine/tests/fixtures/S04_P01.json"),
        Path("abd_acceptance/infrastructure_iac.py"),
        Path("abd_acceptance/stage3_delivery.py"),
        Path("machine/evidence/S03/STAGE_REVIEW/github_delivery_receipt.json"),
    ]
    s04_signed_paths = [
        Path("machine/evidence/EVD-S04-P01.json"),
        Path("machine/evidence/EVD-S04-P01_rollback.json"),
    ]
    candidate_present = [path.as_posix() for path in s04_candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in s04_signed_paths if (root / path).exists()]
    rows = _load_index(root)
    s04 = [row for row in rows if row.get("id") == "INDEX-AC-S04-P01"]
    index_planned = (
        len(s04) == 1
        and s04[0].get("status") == "PLANNED"
        and "actual_artifact" not in s04[0]
        and "artifact_sha256" not in s04[0]
    )
    index_signed = (
        len(s04) == 1
        and s04[0].get("status") == "PASS"
        and s04[0].get("actual_artifact") == "machine/evidence/EVD-S04-P01.json"
        and isinstance(s04[0].get("artifact_sha256"), str)
    )
    mode = "INVALID_PARTIAL_S04_P01_SUCCESSOR"
    successor: Dict[str, Any] = {}
    if not candidate_present and not signed_present and index_planned:
        mode = "S04_P01_NOT_STARTED"
        progression_ok = True
    elif len(candidate_present) == len(s04_candidate_paths) and not signed_present and index_planned:
        try:
            from .infrastructure_iac import evaluate_contract as evaluate_s04_p01

            successor = evaluate_s04_p01(
                root,
                require_external_reports=False,
                _verify_git_history=verify_git_history,
            )
            progression_ok = successor.get("status") == "PASS" and successor.get("next") == "S04/P02_READY_NOT_STARTED"
            mode = "VERIFIED_S04_P01_CANDIDATE" if progression_ok else "INVALID_S04_P01_CANDIDATE"
        except Exception as exc:
            progression_ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif len(candidate_present) == len(s04_candidate_paths) and len(signed_present) == len(s04_signed_paths) and index_signed:
        try:
            from .infrastructure_iac import verify_existing_phase_evidence as verify_s04_p01

            successor = verify_s04_p01(root, verify_git_history=verify_git_history)
            progression_ok = successor.get("status") == "PASS" and successor.get("next") == "S04/P02_READY_NOT_STARTED"
            mode = "VERIFIED_S04_P01_SIGNED_SUCCESSOR" if progression_ok else "INVALID_S04_P01_SIGNED_SUCCESSOR"
        except Exception as exc:
            progression_ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        progression_ok = False
    _add(
        checks,
        "S03REVIEW-S04-NOT-STARTED",
        progression_ok,
        {
            "mode": mode,
            "candidate_present": candidate_present,
            "signed_present": signed_present,
            "index": s04,
            "successor_summary": successor.get("summary") if isinstance(successor, Mapping) else successor,
        },
    )
    secret_patterns = [re.compile(pattern) for pattern in [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", r"\bghp_[A-Za-z0-9]{20,}\b", r"\bAKIA[A-Z0-9]{16}\b"]]
    leaks: List[Dict[str, str]] = []
    local_path_fragments = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]
    for path in _iter_text_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in secret_patterns:
            if pattern.search(text):
                leaks.append({"path": path.relative_to(root).as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in local_path_fragments):
            leaks.append({"path": path.relative_to(root).as_posix(), "kind": "absolute-local-path"})
    _add(checks, "S03REVIEW-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    for element in root.iter():
        if element.tag == "testsuite":
            if element.attrib.get("hostname") is not None or element.attrib.get("timestamp") != JUNIT_FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S03REVIEW-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S03REVIEW-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
    ]:
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            hashes[relative.as_posix()] = sha256_file(root / relative)
            passed = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
        summary = report.get("summary", {})
        ok = report.get("status") == "PASS" and summary.get("checks") == 49 and summary.get("passed") == 49 and summary.get("failed") == 0
        _add(checks, "S03REVIEW-TASKPACK-49-PASS", ok, summary)
    except Exception as exc:
        _add(checks, "S03REVIEW-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S03REVIEW-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.strip())
    except Exception as exc:
        _add(checks, "S03REVIEW-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "S03_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S03_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "release_status": "NOT_READY_STAGE_4_TO_19_AND_PRODUCTION_VALIDATION_REQUIRED",
        "human_validation_status": "NOT_EXECUTED",
        "production_status": "NOT_IMPLEMENTED_NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "next": "S03/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S03/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root / CONTRACT_PATH, checks, "S03REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root / FINDINGS_PATH, checks, "S03REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S03REVIEW-FIXTURE-STRICT-JSON")
    _check_review_pins(root, checks, hashes)
    if isinstance(contract, Mapping) and isinstance(findings, Mapping) and isinstance(fixture, Mapping):
        try:
            _check_contract_shape(contract, fixture, checks)
            _check_baseline_hashes(root, contract, checks, hashes)
            _check_taskpack_trace(root, contract, checks)
            _check_phase_receipts_and_oracles(root, contract, fixture, checks, _verify_git_history)
            _check_cross_phase_surfaces(root, contract, fixture, checks)
            _check_findings(findings, fixture, checks)
            _check_safety_and_progression(root, contract, checks, _verify_git_history)
            _check_predecessor_monotonic_progression(root, checks, _verify_git_history)
        except Exception as exc:
            _add(checks, "S03REVIEW-INTERNAL-ERROR", False, "%s: %s" % (type(exc).__name__, exc))
        if require_external_reports:
            _check_runtime_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S03REVIEW-INPUTS-AVAILABLE", False, "contract, findings or fixture unavailable")
    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0)) if isinstance(fixture, Mapping) else 0
    if result["summary"]["checks"] < minimum:
        _add(checks, "S03REVIEW-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
        result = _build_result(checks, hashes)
    return result


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    result = evaluate_contract(root, require_external_reports=False)
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": result["status"],
        "decision": "S03_REVIEW_CANDIDATE_PREFLIGHT_PASS" if result["status"] == "PASS" else "S03_REVIEW_CANDIDATE_INVALID",
        "summary": result["summary"],
        "checks": result["checks"],
        "next": "S03/STAGE_REVIEW_CANDIDATE" if result["status"] == "PASS" else "S03/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = [
        Path("glossary_zh.json"), Path("forbidden_ui_terms.json"),
        Path("advice_card_schema.json"), Path("advice_card_fixtures.json"),
        Path("reason_codes_zh.json"), Path("next_action_matrix.json"),
        Path("ux_test_plan.json"), Path("accessibility_report.json"),
        CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH,
    ]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s03-stage-review-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(artifacts):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%02d" % index)
            active = temporary / ("active-%02d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored = sha256_file(active)
            results[relative.as_posix()] = {
                "status": "PASS" if corrupted != expected and restored == expected else "FAIL",
                "signed_sha256": expected,
                "corrupted_sha256": corrupted,
                "restored_sha256": restored,
            }
    status = "PASS" if len(results) == 12 and all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_STAGE_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH,
        Path("glossary_zh.json"), Path("forbidden_ui_terms.json"),
        Path("advice_card_schema.json"), Path("advice_card_fixtures.json"),
        Path("reason_codes_zh.json"), Path("next_action_matrix.json"),
        Path("ux_test_plan.json"), Path("accessibility_report.json"),
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"), Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"), Path("machine/facts/traceability_matrix.json"),
        Path("machine/evidence/EVD-S03-P01.json"), Path("machine/evidence/EVD-S03-P01_rollback.json"),
        Path("machine/evidence/EVD-S03-P02.json"), Path("machine/evidence/EVD-S03-P02_rollback.json"),
        Path("machine/evidence/EVD-S03-P03.json"), Path("machine/evidence/EVD-S03-P03_rollback.json"),
        Path("machine/evidence/EVD-S03-P04.json"), Path("machine/evidence/EVD-S03-P04_rollback.json"),
        Path("machine/evidence/S02/STAGE_REVIEW/github_delivery_receipt.json"),
        Path("README.md"), Path("abd_acceptance/stage3_review.py"),
        Path("abd_acceptance/usability_accessibility.py"), Path("abd_acceptance/reason_next_action.py"),
        Path("abd_acceptance/advice_card.py"), Path("abd_acceptance/terminology_governance.py"),
        Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0", "evidence_id": "EVD-S03-STAGE-REVIEW-ROLLBACK",
            "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False, "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "S03_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED"
        result["next"] = "S03/STAGE_REVIEW_REMEDIATION_REQUIRED"
    contract = strict_json_load(root / CONTRACT_PATH)
    findings = strict_json_load(root / FINDINGS_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    inputs = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "phase_completion": {
            "phase_ids": fixture["expected_phase_ids"],
            "phase_evidence_status": "PASS",
            "phase_count": 4,
            "task_count": 12,
            "glossary_term_count": 28,
            "reason_count": 49,
            "action_count": 38,
            "accessibility_profile_count": 7,
            "frozen_budget_count": 21,
        },
        "review_findings": findings.get("summary"),
        "claim_boundary": contract.get("claim_boundary"),
        "hashes": {
            "inputs": inputs,
            "parameters": inputs["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S03 whole-stage review replays Chinese presentation contracts offline; it executes no model, provider, human study, browser, screen reader, deployment, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/stage_review_test.py --junitxml=machine/evidence/S03/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S03/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "explicit_unknowns": [
            "The ten-second gate is structural information placement only, not observed human comprehension time.",
            "Frozen task budgets are not participant observations or production telemetry.",
            "No production UI, real device, browser, low-bandwidth network, keyboard journey or screen-reader runtime was implemented or executed.",
            "No formal WCAG conformance or human usability conclusion is claimed.",
            "TAB, Gmail, OVH and Cloudflare account, authorization, capacity and runtime states remain uninspected or unverified and fail closed.",
            "No model, market, quote, stake, account or order was selected or executed.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
            "Remote GitHub CI is not claimed by local review evidence and must be observed after whole-stage upload.",
        ],
        "release_status": fixture["expected_release_status"],
        "stage_status": "S03_WHOLE_STAGE_REVIEW_PASS" if result["status"] == "PASS" else "S03_WHOLE_STAGE_REVIEW_FAILED",
        "next": result["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-S03-STAGE-REVIEW"]
    if len(matching) > 1:
        raise ValueError("duplicate INDEX-S03-STAGE-REVIEW rows")
    if matching:
        row = matching[0]
    else:
        row = {"id": "INDEX-S03-STAGE-REVIEW", "kind": "STAGE_REVIEW_EVIDENCE", "stage_id": STAGE_ID}
        rows.append(row)
    row.update(
        {
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "verified_at": FIXED_CLOCK,
            "next": "S03/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S03/STAGE_REVIEW_REMEDIATION_REQUIRED",
        }
    )
    payload = b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows)
    _atomic_write(path, payload)


def write_stage3_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.relative_to(root).as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def verify_existing_stage_review_evidence(
    root: Path,
    *,
    verify_phase_prerequisites: bool = True,
    verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S03REVIEW-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S03REVIEW-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S03-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S03_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("stage_status") == "S03_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("release_status") == "NOT_READY_STAGE_4_TO_19_AND_PRODUCTION_VALIDATION_REQUIRED"
            and evidence.get("next") == "S03/GITHUB_STAGE_UPLOAD_READY"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S03REVIEW-RECEIPT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        _add(
            checks,
            "S03REVIEW-RECEIPT-VALIDATION-ALL-PASS",
            isinstance(validation, Mapping)
            and validation.get("status") == "PASS"
            and validation.get("summary", {}).get("failed") == 0
            and all(row.get("passed") is True for row in validation.get("checks", [])),
            validation.get("summary") if isinstance(validation, Mapping) else validation,
        )
        input_errors: List[Any] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "reason": "unsafe path"})
                continue
            path = root.parent / candidate if str(relative).startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                if _historical_file_matches(root, relative, expected, verify_git_history):
                    continue
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03REVIEW-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or len(evidence.get("hashes", {}).get("inputs", {})))
        code_expected = evidence.get("hashes", {}).get("code")
        code_current = _current_code_hash(root)
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (
            code_expected == PINNED_STAGE_REVIEW_CODE_HASH
            and code_historical in {PINNED_STAGE_REVIEW_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(
            checks,
            "S03REVIEW-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_current, "historical_stage_review_commit": code_historical},
        )
        _add(checks, "S03REVIEW-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
    else:
        for check_id in ["S03REVIEW-RECEIPT-INTEGRITY", "S03REVIEW-RECEIPT-VALIDATION-ALL-PASS", "S03REVIEW-RECEIPT-SIGNED-INPUTS-CURRENT", "S03REVIEW-RECEIPT-CODE-HASH-CURRENT", "S03REVIEW-RECEIPT-ROLLBACK-HASH-BINDING"]:
            _add(checks, check_id, False, "evidence unavailable")
    fixture = strict_json_load(root / FIXTURE_PATH)
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S03-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and len(rollback.get("artifacts", {})) == fixture.get("expected_rollback_artifact_count")
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S03REVIEW-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-S03-STAGE-REVIEW"]
    index_ok = (
        len(matching) == 1
        and matching[0].get("status") == "PASS"
        and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and matching[0].get("artifact_sha256") == evidence_hash
        and matching[0].get("next") == "S03/GITHUB_STAGE_UPLOAD_READY"
    )
    _add(checks, "S03REVIEW-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    if verify_phase_prerequisites:
        for phase in ["P01", "P02", "P03", "P04"]:
            try:
                result = _verify_phase(phase, root, verify_git_history)
                _add(checks, "S03REVIEW-RECEIPT-%s-PREREQUISITE" % phase, result.get("status") == "PASS", result.get("summary"))
            except Exception as exc:
                _add(checks, "S03REVIEW-RECEIPT-%s-PREREQUISITE" % phase, False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S03_STAGE_REVIEW_EVIDENCE_VERIFIED" if not failed else "S03_STAGE_REVIEW_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S03/GITHUB_STAGE_UPLOAD_READY" if not failed else "S03/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
