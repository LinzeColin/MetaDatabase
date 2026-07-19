from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .delivery import verify_stage0_delivery


CONTRACT_ID = "AC-S01-P02"
REQUIREMENT_ID = "REQ-S01-P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

FAQ_PATH = Path("customer_faq.md")
REGISTER_PATH = Path("assumption_register.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S01_P02.json")
JUNIT_PATH = Path("machine/evidence/S01/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S01/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S01-P01_rollback.json")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

P01_COMMIT = "7c52659e2f6de6ebfff6d3079ba0a29cf542867e"
P01_EVIDENCE_SHA256 = "41ecd4c590adda8cfe357bc73c6d49571a464ba65672330bd3592f2f69b9209e"
P01_ROLLBACK_SHA256 = "18e51cb3bc5a06274e70c624855d990362a4fbe5ed75fbaedf219b8def29db55"

PINNED_SOURCE_HASHES = {
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/authorization_matrix.json": "f7cf34a3d60e37365c3090fac75f40e0b390ec211976393e7148d597a2f4affe",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/decision_prerequisites.json": "e9b54b985aff11faceaa7a2d6e6db42e070c96c0a8286a348ff767bc62921ccc",
    "machine/facts/degraded_mode_contract.json": "823a92ee03a468aaa1df6a4706aa0f1af3472b7f9c96c530877578f2f072d02f",
    "machine/facts/email_ingestion.json": "7d40a142a482b5179aa6bb11fa0694fa5576a770f0b2a5af751615da3dea53cd",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/security_assurance.json": "03543d4356f3718047293329d6b4e7cc3c14735b521e47f03079ff101f3205dd",
    "machine/facts/sources.json": "387df5c4cf54fcad59072c46ee7bbcd67f13e66adf2f5ccf9b115b71182784d8",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    P01_EVIDENCE_PATH.as_posix(): P01_EVIDENCE_SHA256,
}

PINNED_PHASE_HASHES = {
    FAQ_PATH.as_posix(): "c004e375b0924564e1453885da5e7c286e15cc1924103524097fc4c58af22cb3",
    REGISTER_PATH.as_posix(): "b51e164e16fcf4c3cbd0708565583f91f7b5bf08f6a325d65a288872b03d9426",
    FIXTURE_PATH.as_posix(): "f9f1183b9635c86c862e88f4f6fd26ac33dade5a10dd5c907cfc7a48fece9ccb",
}

PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

P01_SIGNED_ARTIFACT_HASHES = {
    "customer_press_release.md": "8cd88a4d4cd0dc6fe4735f8c0400fdd05ccab001afdbe9a09aec57a683f950ab",
    "customer_outcomes.json": "54ea272e26be24f88dc7344b4b2ea9d3268a488622214bc1790fe229d791b28d",
    "machine/tests/fixtures/S01_P01.json": "824e848b8d259ea1d29f6a10a9df38d1f1fbefeb0ab1c774da94fa27af0c8a96",
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


def _duplicates(values: Sequence[Any]) -> bool:
    rendered = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
    return len(rendered) != len(set(rendered))


def _find_by_id(rows: Any, item_id: str) -> Any:
    if not isinstance(rows, list):
        return None
    matching = [row for row in rows if isinstance(row, dict) and row.get("id") == item_id]
    return matching[0] if len(matching) == 1 else None


def resolve_zero_budget_default(value: str | None) -> str:
    if value is None:
        return "BLOCK_INCREMENTAL_CASH_COST_UNKNOWN"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "FAIL_INVALID_COST_DATA"
    if not amount.is_finite() or amount < 0:
        return "FAIL_INVALID_COST_DATA"
    if amount > 0:
        return "BLOCK_INCREMENTAL_CASH_BUDGET_EXCEEDED"
    return "CONTINUE_ZERO_INCREMENTAL_CASH_PATH"


def resolve_mail_default(**gates: bool) -> str:
    expected = (
        "consent_active",
        "raw_eml_saved",
        "all_attachments_saved",
        "hash_manifest_committed",
        "malware_scan_passed",
        "parser_result_recorded",
        "local_restore_readback_passed",
    )
    if set(gates) != set(expected) or any(type(gates.get(name)) is not bool for name in expected):
        return "DISABLE_GMAIL_KEEP_MESSAGE"
    if gates["consent_active"] is not True:
        return "DISABLE_GMAIL_KEEP_MESSAGE"
    if all(gates[name] is True for name in expected):
        return "TRASH_AFTER_VERIFIED_ARCHIVE"
    return "KEEP_OR_QUARANTINE_DO_NOT_TRASH"


def resolve_recommendation_default(*, evidence_complete: bool, fresh: bool, stable: bool, risk_passed: bool) -> str:
    gates = (evidence_complete, fresh, stable, risk_passed)
    return "RECOMMENDATION" if all(value is True for value in gates) else "NO_RECOMMENDATION"


def _single_source_check(root: Path, relative: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(relative.name)
        if not {".git", ".venv", ".pytest_cache", "__pycache__"}.intersection(path.parts)
    )
    _add(checks, "S01P02-SINGLE-%s" % relative.stem.upper(), candidates == [relative.as_posix()], candidates)


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in {**PINNED_SOURCE_HASHES, **PINNED_PHASE_HASHES}.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S01P02-HASH-%s" % Path(relative).stem.upper(),
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S01P02-HASH-%s" % Path(relative).stem.upper(), False, str(exc))
    for relative, expected in PINNED_REPO_HASHES.items():
        try:
            actual = sha256_file(root.parent / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S01P02-HASH-%s" % Path(relative).stem.upper(),
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S01P02-HASH-%s" % Path(relative).stem.upper(), False, str(exc))


def _check_continuous_workflow(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        text = (root.parent / CONTINUOUS_WORKFLOW_PATH).read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S01P02-CONTINUOUS-CI", False, str(exc))
        return
    action_refs = re.findall(r"^\s*-\s+uses:\s+[^@\s]+@([^\s#]+)", text, flags=re.MULTILINE)
    expected_refs = {
        "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "ece7cb06caefa5fff74198d8649806c4678c61a1",
        "11f9893b081a58869d3b5fccaea48c9e9e46f990",
    }
    workflow_ok = (
        "name: ABD continuous validation" in text
        and "runs-on: ubuntu-latest" in text
        and "working-directory: ABD" in text
        and len(action_refs) == 3
        and set(action_refs) == expected_refs
        and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
        and 'version: "0.11.28"' in text
        and 'python-version: "3.12"' in text
        and "uv sync --frozen --group dev" in text
        and re.search(r"^\s*run:\s+uv run --frozen --python 3\.12 python -m pytest -q\s*$", text, re.MULTILINE)
        is not None
        and "--verify-existing STAGE-REVIEW-S00" in text
        and "python machine/tools/validate_pack.py" in text
        and "python machine/tools/update_artifact_manifest.py" in text
        and "shasum -a 256 -c machine/evidence/SHA256SUMS" in text
        and "git diff --exit-code" in text
        and ("$" + "{{ secrets.") not in text
    )
    _add(checks, "S01P02-CONTINUOUS-CI", workflow_ok, action_refs)


def _check_taskpack_contract(
    roadmap: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        stages = [row for row in roadmap.get("stages", []) if row.get("id") == "S01"]
        phases = [row for row in stages[0].get("phases", []) if row.get("id") == "P02"] if len(stages) == 1 else []
        phase = phases[0] if len(phases) == 1 else {}
        roadmap_ok = (
            phase.get("title") == "客户常见问题"
            and phase.get("objective") == "回答30%目标、无保证、零预算、全范围、邮件归档、故障和隐私问题。"
            and phase.get("outputs") == [FAQ_PATH.as_posix(), REGISTER_PATH.as_posix()]
            and phase.get("pass_gate") == "关键疑问均有明确默认与证据。"
            and phase.get("hours") == {"low": 3, "likely": 4, "high": 6}
        )
    except Exception as exc:
        phase = {"error": "%s: %s" % (type(exc).__name__, exc)}
        roadmap_ok = False
    _add(checks, "S01P02-ROADMAP-EXACT", roadmap_ok, phase)

    requirement = _find_by_id(list(requirements), REQUIREMENT_ID)
    requirement_ok = isinstance(requirement, dict) and (
        requirement.get("stage_id") == "S01"
        and requirement.get("phase_id") == "P02"
        and requirement.get("value") == "回答30%目标、无保证、零预算、全范围、邮件归档、故障和隐私问题。"
        and requirement.get("scope") == [FAQ_PATH.as_posix(), REGISTER_PATH.as_posix()]
        and requirement.get("target") == "关键疑问均有明确默认与证据。"
        and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        and requirement.get("owner_input_required_during_development") is False
        and requirement.get("non_goals") == [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
    )
    _add(checks, "S01P02-REQUIREMENT-EXACT", requirement_ok, requirement)

    contract = _find_by_id(list(acceptance), CONTRACT_ID)
    contract_ok = isinstance(contract, dict) and (
        contract.get("requirement_id") == REQUIREMENT_ID
        and contract.get("oracle", {}).get("type") == "EXECUTABLE"
        and contract.get("oracle", {}).get("command")
        == "python -m abd_acceptance --contract AC-S01-P02 --evidence machine/evidence"
        and contract.get("pass_gate") == "关键疑问均有明确默认与证据。"
        and [row.get("id") for row in contract.get("tests", [])]
        == ["TEST-S01-P02", "TEST-S01-P02-BOUNDARY", "TEST-S01-P02-REPLAY"]
        and "新增现金支出将超过A$0" in contract.get("stop_condition", [])
    )
    _add(checks, "S01P02-ACCEPTANCE-CONTRACT-EXACT", contract_ok, contract)

    tasks = [
        row
        for row in task_graph.get("tasks", [])
        if isinstance(row, dict) and str(row.get("id", "")).startswith("T-S01-P02-")
    ]
    expected_ids = ["T-S01-P02-01", "T-S01-P02-02", "T-S01-P02-03"]
    tasks_ok = (
        [row.get("id") for row in tasks] == expected_ids
        and [row.get("depends_on") for row in tasks]
        == [["T-S01-P01-03"], ["T-S01-P02-01"], ["T-S01-P02-02"]]
        and all(row.get("auto_advance_on_pass") is True for row in tasks)
        and all(row.get("owner_input_required") is False for row in tasks)
        and tasks[0].get("outputs") == [FAQ_PATH.as_posix(), REGISTER_PATH.as_posix()]
        and tasks[1].get("outputs") == ["tests/S01/P02_test.py", FIXTURE_PATH.as_posix()]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
    )
    _add(checks, "S01P02-TASK-CHAIN-EXACT", tasks_ok, [row.get("id") for row in tasks])

    trace = next(
        (row for row in traceability if isinstance(row, dict) and row.get("requirement_id") == REQUIREMENT_ID),
        None,
    )
    trace_ok = isinstance(trace, dict) and (
        trace.get("acceptance_criteria_id") == CONTRACT_ID
        and trace.get("task_ids") == expected_ids
        and trace.get("test_ids") == ["TEST-S01-P02", "TEST-S01-P02-BOUNDARY", "TEST-S01-P02-REPLAY"]
        and trace.get("evidence_id") == "EVD-S01-P02"
        and trace.get("artifact_ids") == ["ART-S01-P02-01", "ART-S01-P02-02"]
    )
    _add(checks, "S01P02-TRACEABILITY-EXACT", trace_ok, trace)


def _parse_faq(text: str) -> Tuple[str, Dict[str, str], str]:
    lines = text.splitlines()
    h1 = [line[2:].strip() for line in lines if line.startswith("# ")]
    if len(h1) != 1:
        raise ValueError("FAQ must contain exactly one level-one heading")
    questions: Dict[str, str] = {}
    boundary = ""
    current: str | None = None
    buffer: List[str] = []
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                payload = "\n".join(buffer).strip()
                if current == "当前交付边界":
                    boundary = payload
                else:
                    questions[current] = payload
            current = line[3:].strip()
            if current in questions or (current == "当前交付边界" and boundary):
                raise ValueError("duplicate FAQ section: %s" % current)
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        payload = "\n".join(buffer).strip()
        if current == "当前交付边界":
            boundary = payload
        else:
            questions[current] = payload
    return h1[0], questions, boundary


def _check_faq(text: str, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, str]:
    try:
        title, question_sections, boundary = _parse_faq(text)
        question_ids = [heading.split("｜", 1)[0] for heading in question_sections]
        expected_ids = fixture.get("expected_question_ids", [])
        labels = fixture.get("required_faq_labels", [])
        sections_ok = (
            title == "ABD 客户常见问题（目标合同稿）"
            and question_ids == expected_ids
            and all("｜" in heading for heading in question_sections)
            and all(payload for payload in question_sections.values())
            and all(payload.count("**%s：**" % label) == 1 for payload in question_sections.values() for label in labels)
            and bool(boundary)
            and text.count(str(fixture.get("required_faq_preamble"))) == 1
            and "```" not in text
            and "http://" not in text
            and "https://" not in text
        )
        detail = {"question_ids": question_ids, "boundary": bool(boundary)}
    except Exception as exc:
        question_sections = {}
        sections_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01P02-FAQ-STRUCTURE", sections_ok, detail)

    chinese_count = sum("\u4e00" <= character <= "\u9fff" for character in text)
    language_ok = (
        chinese_count >= int(fixture.get("minimum_chinese_characters", 0))
        and len(text) <= int(fixture.get("maximum_total_characters", 0))
    )
    _add(
        checks,
        "S01P02-FAQ-CUSTOMER-LANGUAGE",
        language_ok,
        {"chinese_characters": chinese_count, "total_characters": len(text)},
    )

    missing = [term for term in fixture.get("required_customer_concepts", []) if term not in text]
    _add(checks, "S01P02-FAQ-REQUIRED-CONCEPTS", not missing, missing or "all present")

    claim_text = "\n".join(question_sections.values()) if question_sections else text
    false_claims = [term for term in fixture.get("forbidden_current_claims", []) if term in claim_text]
    false_pattern = re.compile(r"(?:现已|目前已)(?:上线|部署|连接|覆盖)|(?:已经|现已|将)(?:确保|保证)(?:收益|盈利|本金增长)")
    false_claims.extend(match.group(0) for match in false_pattern.finditer(claim_text))
    _add(checks, "S01P02-FAQ-NO-FALSE-CURRENT-CLAIMS", not false_claims, false_claims or "none")

    default_and_evidence_ok = True
    per_question = {}
    for heading, payload in question_sections.items():
        question_id = heading.split("｜", 1)[0]
        required_paths = fixture.get("required_source_paths_by_question", {}).get(question_id, [])
        missing_paths = [path for path in required_paths if path not in payload]
        per_question[question_id] = missing_paths
        if missing_paths or "**默认：**" not in payload or "**证据：**" not in payload:
            default_and_evidence_ok = False
    _add(checks, "S01P02-FAQ-DEFAULT-AND-EVIDENCE-PER-QUESTION", default_and_evidence_ok, per_question)
    return question_sections


def _json_pointer(value: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("invalid JSON pointer: %r" % pointer)
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit():
                raise KeyError(token)
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(token)
    return current


def _check_register(
    root: Path,
    register: Mapping[str, Any],
    fixture: Mapping[str, Any],
    source_documents: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    top_ok = (
        register.get("schema_version") == "1.0.0"
        and register.get("artifact_id") == "ART-S01-P02-02"
        and register.get("requirement_id") == REQUIREMENT_ID
        and register.get("acceptance_contract_id") == CONTRACT_ID
        and register.get("product_version") == VERSION
        and register.get("fixed_at") == FIXED_CLOCK
        and register.get("status") == "WORKING_BACKWARDS_ASSUMPTIONS_NOT_PRODUCTION_PROOF"
        and register.get("next_on_acceptance_pass") == "S01/P03_READY_NOT_STARTED"
    )
    _add(checks, "S01P02-REGISTER-TOP-LEVEL", top_ok, register.get("status"))

    try:
        actual_bindings = {relative: sha256_file(root / relative) for relative in PINNED_SOURCE_HASHES}
        bindings_ok = register.get("source_bindings") == PINNED_SOURCE_HASHES and actual_bindings == PINNED_SOURCE_HASHES
    except Exception as exc:
        bindings_ok = False
        actual_bindings = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(
        checks,
        "S01P02-REGISTER-SOURCE-BINDINGS",
        bindings_ok,
        {"declared": register.get("source_bindings"), "actual": actual_bindings},
    )

    question_ids = fixture.get("expected_question_ids", [])
    required_ids_ok = register.get("required_question_ids") == question_ids
    _add(checks, "S01P02-REGISTER-REQUIRED-QUESTIONS", required_ids_ok, register.get("required_question_ids"))

    assumptions = register.get("assumptions", [])
    rows_are_objects = isinstance(assumptions, list) and all(isinstance(row, dict) for row in assumptions)
    assumption_ids = [row.get("id") for row in assumptions] if rows_are_objects else []
    row_questions = [row.get("question_id") for row in assumptions] if rows_are_objects else []
    topics = [row.get("topic") for row in assumptions] if rows_are_objects else []
    defaults = [row.get("safe_default") for row in assumptions] if rows_are_objects else []
    rows_ok = (
        rows_are_objects
        and assumption_ids == fixture.get("expected_assumption_ids")
        and row_questions == question_ids
        and topics == fixture.get("expected_topics")
        and defaults == fixture.get("expected_safe_defaults")
        and not _duplicates(assumption_ids)
        and not _duplicates(row_questions)
        and all(row.get("statement") and row.get("current_status") and row.get("evidence_class") for row in assumptions)
        and all(row.get("disconfirming_evidence") and row.get("proof_required") for row in assumptions)
        and all(row.get("external_state_observed_in_phase") is False for row in assumptions)
    )
    _add(checks, "S01P02-REGISTER-ONE-ROW-PER-QUESTION", rows_ok, assumption_ids)

    evidence_ok = rows_are_objects
    evidence_detail: Dict[str, Any] = {}
    for row in assumptions if rows_are_objects else []:
        question_id = row.get("question_id")
        evidence = row.get("evidence", [])
        required_paths = fixture.get("required_source_paths_by_question", {}).get(question_id, [])
        actual_paths = [item.get("source_path") for item in evidence if isinstance(item, dict)] if isinstance(evidence, list) else []
        row_ok = isinstance(evidence, list) and len(evidence) == len(actual_paths) and set(actual_paths) == set(required_paths)
        pointer_failures = []
        if row_ok:
            for item in evidence:
                source_path = item.get("source_path")
                pointers = item.get("json_pointers")
                if not item.get("supports") or not isinstance(pointers, list) or not pointers:
                    pointer_failures.append("%s:missing-metadata" % source_path)
                    continue
                document = source_documents.get(source_path)
                if document is None:
                    pointer_failures.append("%s:missing-document" % source_path)
                    continue
                for pointer in pointers:
                    try:
                        _json_pointer(document, pointer)
                    except Exception as exc:
                        pointer_failures.append("%s%s:%s" % (source_path, pointer, type(exc).__name__))
        row_ok = row_ok and not pointer_failures
        evidence_detail[str(question_id)] = {"paths": actual_paths, "pointer_failures": pointer_failures}
        evidence_ok = evidence_ok and row_ok
    _add(checks, "S01P02-REGISTER-EVIDENCE-POINTERS-RESOLVE", evidence_ok, evidence_detail)

    by_topic = {row.get("topic"): row for row in assumptions if isinstance(row, dict)}
    try:
        target_ok = (
            by_topic["MONTHLY_TARGET"]["current_status"] == "UNVERIFIED_FALSIFIABLE_TARGET"
            and "6个完整自然月" in by_topic["MONTHLY_TARGET"]["disconfirming_evidence"]
            and "12个完整自然月" in by_topic["MONTHLY_TARGET"]["proof_required"]
        )
        guarantee_ok = (
            by_topic["NO_RETURN_GUARANTEE"]["current_status"] == "NO_GUARANTEE_RETURN_UNVERIFIED"
            and by_topic["NO_RETURN_GUARANTEE"]["safe_default"] == "NO_RECOMMENDATION_AND_NO_RETURN_CLAIM"
        )
        budget_ok = (
            by_topic["ZERO_INCREMENTAL_CASH"]["safe_default"] == "BLOCK_POSITIVE_OR_UNKNOWN_INCREMENTAL_COST"
            and "EXTERNAL_BILLING_UNVERIFIED" in by_topic["ZERO_INCREMENTAL_CASH"]["current_status"]
        )
        coverage_ok = (
            by_topic["ALL_OBSERVABLE_MARKETS"]["current_status"] == "SCOPE_CONTRACT_ONLY_COVERAGE_UNVERIFIED"
            and "NEVER_SILENT_DROP" in by_topic["ALL_OBSERVABLE_MARKETS"]["safe_default"]
        )
        mail_ok = (
            by_topic["MAIL_ARCHIVE"]["current_status"] == "GMAIL_NOT_CONNECTED_NOT_IMPLEMENTED_NOT_READY"
            and "KEEP_OR_QUARANTINE" in by_topic["MAIL_ARCHIVE"]["safe_default"]
        )
        failure_ok = (
            by_topic["FAILURE_AND_DEGRADED_OPERATION"]["safe_default"] == "AUTO_ROLLBACK_OR_NO_RECOMMENDATION"
            and "RUNTIME_UNVERIFIED" in by_topic["FAILURE_AND_DEGRADED_OPERATION"]["current_status"]
        )
        privacy_ok = (
            by_topic["PRIVACY_AND_SECRETS"]["current_status"] == "NO_EXTERNAL_ACCOUNT_OR_SECRET_OBSERVED_IN_PHASE"
            and "DENY_DISABLE_ISOLATE" in by_topic["PRIVACY_AND_SECRETS"]["safe_default"]
        )
    except (KeyError, TypeError):
        target_ok = guarantee_ok = budget_ok = coverage_ok = mail_ok = failure_ok = privacy_ok = False
    _add(checks, "S01P02-REGISTER-TARGET-DEFAULT", target_ok, by_topic.get("MONTHLY_TARGET"))
    _add(checks, "S01P02-REGISTER-NO-GUARANTEE-DEFAULT", guarantee_ok, by_topic.get("NO_RETURN_GUARANTEE"))
    _add(checks, "S01P02-REGISTER-ZERO-BUDGET-DEFAULT", budget_ok, by_topic.get("ZERO_INCREMENTAL_CASH"))
    _add(checks, "S01P02-REGISTER-COVERAGE-DEFAULT", coverage_ok, by_topic.get("ALL_OBSERVABLE_MARKETS"))
    _add(checks, "S01P02-REGISTER-MAIL-DEFAULT", mail_ok, by_topic.get("MAIL_ARCHIVE"))
    _add(checks, "S01P02-REGISTER-FAILURE-DEFAULT", failure_ok, by_topic.get("FAILURE_AND_DEGRADED_OPERATION"))
    _add(checks, "S01P02-REGISTER-PRIVACY-DEFAULT", privacy_ok, by_topic.get("PRIVACY_AND_SECRETS"))

    boundaries_ok = register.get("claim_boundaries") == fixture.get("expected_claim_boundaries")
    _add(checks, "S01P02-REGISTER-CLAIM-BOUNDARIES", boundaries_ok, register.get("claim_boundaries"))


def _check_cross_document(
    question_sections: Mapping[str, str],
    register: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    headings_by_id = {heading.split("｜", 1)[0]: payload for heading, payload in question_sections.items()}
    assumptions = register.get("assumptions", [])
    by_question = {
        row.get("question_id"): row
        for row in assumptions
        if isinstance(assumptions, list) and isinstance(row, dict)
    } if isinstance(assumptions, list) else {}
    expected = fixture.get("expected_question_ids", [])
    cross_ok = list(headings_by_id) == expected and list(by_question) == expected
    detail = {}
    for question_id in expected:
        payload = headings_by_id.get(question_id, "")
        row = by_question.get(question_id, {})
        paths = [item.get("source_path") for item in row.get("evidence", []) if isinstance(item, dict)]
        row_ok = bool(payload) and row.get("safe_default") and all(path in payload for path in paths)
        detail[question_id] = row_ok
        cross_ok = cross_ok and bool(row_ok)
    _add(checks, "S01P02-FAQ-REGISTER-CONSISTENCY", cross_ok, detail)


def _verify_p01_prerequisite(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    verify_git_history: bool,
) -> None:
    evidence = _safe_load(root / P01_EVIDENCE_PATH, checks, "S01P02-P01-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / P01_ROLLBACK_PATH, checks, "S01P02-P01-ROLLBACK-STRICT-JSON")
    if not isinstance(evidence, dict) or not isinstance(rollback, dict):
        _add(checks, "S01P02-P01-IMMUTABLE-RECEIPT", False, "receipt unavailable")
        return
    try:
        evidence_hash = sha256_file(root / P01_EVIDENCE_PATH)
        rollback_hash = sha256_file(root / P01_ROLLBACK_PATH)
        hashes[P01_EVIDENCE_PATH.as_posix()] = evidence_hash
        hashes[P01_ROLLBACK_PATH.as_posix()] = rollback_hash
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        integrity_ok = decision_hash == _sha256_bytes(_json_bytes(unsigned))
        receipt_ok = (
            evidence_hash == P01_EVIDENCE_SHA256
            and rollback_hash == P01_ROLLBACK_SHA256
            and evidence.get("evidence_id") == "EVD-S01-P01"
            and evidence.get("contract_id") == "AC-S01-P01"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "CUSTOMER_OUTCOME_CONTRACT_FROZEN"
            and evidence.get("phase_status") == "S01_P01_PASS"
            and evidence.get("next") == "S01/P02_READY_NOT_STARTED"
            and evidence.get("artifacts")
            == {"ART-S01-P01-01": "customer_press_release.md", "ART-S01-P01-02": "customer_outcomes.json"}
            and evidence.get("hashes", {}).get("rollback_evidence") == P01_ROLLBACK_SHA256
            and evidence.get("external_effect_boundary", {}).get("github_upload_performed") is False
            and evidence.get("external_effect_boundary", {}).get("incremental_cash_spent_aud") == "0.00"
            and evidence.get("external_effect_boundary", {}).get("real_order_capability_present") is False
            and evidence.get("external_effect_boundary", {}).get("return_guaranteed") is False
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and integrity_ok
        )
    except Exception as exc:
        receipt_ok = False
        evidence_hash = rollback_hash = "unavailable"
        integrity_ok = False
        _add(checks, "S01P02-P01-RECEIPT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _add(
        checks,
        "S01P02-P01-IMMUTABLE-RECEIPT",
        receipt_ok,
        {"evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "decision_integrity": integrity_ok},
    )

    signed_inputs = evidence.get("hashes", {}).get("inputs", {})
    artifact_ok = isinstance(signed_inputs, dict)
    artifact_detail = {}
    for relative, expected in P01_SIGNED_ARTIFACT_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
        signed = signed_inputs.get(relative) if isinstance(signed_inputs, dict) else None
        row_ok = actual == expected and signed == expected
        artifact_detail[relative] = {"expected": expected, "signed": signed, "actual": actual}
        artifact_ok = artifact_ok and row_ok
    _add(checks, "S01P02-P01-SIGNED-ARTIFACTS", artifact_ok, artifact_detail)

    try:
        rows = [
            json.loads(line)
            for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
            if line
        ]
        p01_rows = [row for row in rows if row.get("id") == "INDEX-AC-S01-P01"]
        index_ok = (
            len(p01_rows) == 1
            and p01_rows[0].get("status") == "PASS"
            and p01_rows[0].get("artifact_sha256") == P01_EVIDENCE_SHA256
            and p01_rows[0].get("actual_artifact") == P01_EVIDENCE_PATH.as_posix()
            and p01_rows[0].get("next") == "S01/P02_READY_NOT_STARTED"
        )
    except Exception as exc:
        p01_rows = []
        index_ok = False
        _add(checks, "S01P02-P01-INDEX-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _add(checks, "S01P02-P01-EVIDENCE-INDEX", index_ok, p01_rows)

    stage0 = verify_stage0_delivery(root, verify_git_history=verify_git_history)
    _add(
        checks,
        "S01P02-STAGE0-DELIVERY-CHAIN",
        stage0.get("status") == "PASS" and stage0.get("next") == "S01/P01_READY_NOT_STARTED",
        stage0.get("summary"),
    )
    hashes.update(stage0.get("hashes", {}))

    if verify_git_history:
        try:
            resolved = subprocess.run(
                ["git", "-C", str(root.parent), "rev-parse", "%s^{commit}" % P01_COMMIT],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            ancestor = subprocess.run(
                ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", P01_COMMIT, "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            git_ok = resolved.returncode == 0 and resolved.stdout.strip() == P01_COMMIT and ancestor.returncode == 0
            git_detail = {"resolved": resolved.stdout.strip(), "ancestor_exit": ancestor.returncode}
        except Exception as exc:
            git_ok = False
            git_detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S01P02-P01-GIT-ANCESTRY", git_ok, git_detail)
    else:
        _add(
            checks,
            "S01P02-TEST-ONLY-PARTIAL-GIT-PROFILE",
            False,
            "Mutation clones skip Git ancestry; final evidence never does.",
        )


def _check_frozen_semantics(
    canonical: Mapping[str, Any],
    parameters: Mapping[str, Any],
    costs: Mapping[str, Any],
    email: Mapping[str, Any],
    prerequisites: Mapping[str, Any],
    degraded: Mapping[str, Any],
    release: Mapping[str, Any],
    security: Mapping[str, Any],
    authorization: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    product = canonical.get("product", {})
    target = parameters.get("target_30pct", {})
    risk = parameters.get("risk", {})
    target_ok = (
        product.get("target_curve") == "B_n = 300 * (1.3 ** n)"
        and product.get("monthly_target_return") == "0.30"
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and target.get("shadow_min_days") == 90
        and target.get("shadow_min_independent_equivalent_signals") == 1000
        and len(target.get("falsification_gate", [])) == 3
        and len(target.get("verification_gate", [])) == 4
        and risk.get("target_shortfall_may_relax_gate") is False
        and risk.get("chase_loss_prohibited") is True
    )
    _add(checks, "S01P02-FACT-TARGET-NO-GUARANTEE", target_ok, target)

    cost_semantics = costs.get("cost_semantics", {})
    cost_gate = costs.get("incremental_cash_gate", {})
    budget_ok = (
        product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and cost_semantics.get("total_system_cost_is_zero") is False
        and "不是开发或基础设施预算" in cost_semantics.get("bankroll_principal", "")
        and cost_gate.get("maximum_aud") == "0.00"
        and cost_gate.get("positive_boundary_aud") == "0.0001"
        and cost_gate.get("positive_or_unknown_action") == "BLOCK_AND_EMIT_INCREMENTAL_CASH_BUDGET_EXCEEDED"
        and cost_gate.get("automatic_purchase_allowed") is False
        and cost_gate.get("automatic_paid_upgrade_allowed") is False
        and cost_gate.get("automatic_overage_billing_allowed") is False
    )
    _add(checks, "S01P02-FACT-ZERO-BUDGET-SEMANTICS", budget_ok, cost_gate)

    scope = canonical.get("scope", {})
    truth = canonical.get("truth_and_evidence", {})
    source_policy = costs.get("future_source_admission_policy", {})
    coverage_ok = (
        scope.get("discovery_scope") == "ALL_OBSERVABLE_MARKETS"
        and scope.get("recommendation_scope") == "EVIDENCE_GATED"
        and truth.get("silent_coverage_gap_target") == 0
        and source_policy.get("observable_market_coverage_goal_preserved") is True
        and source_policy.get("unknown_cost_or_terms_action") == "DO_NOT_ADMIT_SOURCE_MARK_COVERAGE_GAP"
        and source_policy.get("coverage_gap_behavior")
        == "DISCOVERED_BUT_NOT_RECOMMENDABLE_OR_UNOBSERVABLE_NOT_SILENTLY_DROPPED"
        and parameters.get("numeric_determinism", {}).get("unstable_action") == "NO_RECOMMENDATION"
    )
    _add(checks, "S01P02-FACT-COVERAGE-AND-SAFE-DEFAULT", coverage_ok, source_policy)

    current = prerequisites.get("current_phase_observation", {})
    trash = email.get("trash_gate", {})
    mail_ok = (
        current.get("gmail_authorization_status") == "NOT_REQUESTED"
        and current.get("gmail_capability_status") == "UNVERIFIED"
        and current.get("gmail_readiness_status") == "NOT_READY"
        and current.get("gmail_module_enabled") is False
        and current.get("gmail_external_api_call_performed") is False
        and current.get("token_received_or_stored") is False
        and degraded.get("current_state") == "CONSENT_NOT_REQUESTED"
        and trash.get("all_required") is True
        and trash.get("conditions") == parameters.get("email", {}).get("trash_only_after")
        and trash.get("permanent_delete") is False
        and trash.get("unknown_sender") == "KEEP"
    )
    _add(checks, "S01P02-FACT-GMAIL-NOT-CONNECTED-SAFE-ARCHIVE", mail_ok, current)

    runtime = canonical.get("runtime", {})
    failure_ok = (
        runtime.get("single_host_zero_downtime_guaranteed") is False
        and len(release.get("auto_rollback_on", [])) == 7
        and "账本或证据完整性失败" in release.get("auto_rollback_on", [])
        and prerequisites.get("semantics", {}).get("unknown_external_state_default")
        == "DISABLE_AFFECTED_EXTERNAL_MODULE_CONTINUE_SAFE_CORE"
    )
    _add(checks, "S01P02-FACT-FAILURE-ROLLBACK", failure_ok, release.get("auto_rollback_on"))

    consent = degraded.get("consent_receipt_contract", {})
    methods = degraded.get("method_policy", {})
    privacy_ok = (
        "外部内容一律不可信" in security.get("design_controls", [])
        and "秘密使用操作系统密钥库或加密文件" in security.get("design_controls", [])
        and consent.get("secret_material_present_must_equal") is False
        and set(consent.get("forbidden_fields", []))
        == {
            "authorization_code",
            "access_token",
            "refresh_token",
            "client_secret",
            "token_value",
            "email_address",
            "account_id",
            "authorization_url",
        }
        and "users.messages.send" in methods.get("always_denied", [])
        and "users.messages.delete" in methods.get("always_denied", [])
        and "NO_SECRET_OR_ACCOUNT_DATA_IN_DURABLE_EVIDENCE"
        in source_policy.get("admission_requirements", [])
    )
    _add(checks, "S01P02-FACT-PRIVACY-AND-SECRETS", privacy_ok, consent)

    actions = {
        row.get("id"): row
        for row in authorization.get("actions", [])
        if isinstance(row, dict)
    } if isinstance(authorization.get("actions"), list) else {}
    boundary = degraded.get("s00_p04_execution_boundary", {})
    external_ok = (
        scope.get("order_submission_module_present") is False
        and actions.get("REAL_ORDER_SUBMISSION", {}).get("authorization") == "PROHIBITED"
        and actions.get("REAL_ORDER_SUBMISSION", {}).get("capability_status") == "MODULE_MUST_NOT_EXIST"
        and boundary.get("external_product_or_account_network_access") is False
        and boundary.get("token_received_or_stored") is False
        and boundary.get("gmail_api_called") is False
        and boundary.get("email_moved_or_deleted") is False
    )
    _add(checks, "S01P02-NO-EXTERNAL-EFFECTS-OR-ORDER", external_ok, boundary)


def _check_p03_not_started(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        rows = [
            json.loads(line)
            for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
            if line
        ]
        p03 = [row for row in rows if row.get("id") == "INDEX-AC-S01-P03"]
        future_evidence = sorted((root / "machine/evidence").glob("EVD-S01-P0[3-4]*.json"))
        future_outputs = [
            root / "requirements.json",
            root / "scope_boundary.json",
            root / "business_flows.json",
            root / "metrics.json",
            root / "economics.json",
            root / "kill_criteria.json",
        ]
        progression_ok = (
            len(p03) == 1
            and p03[0].get("status") == "PLANNED"
            and not future_evidence
            and not any(path.exists() for path in future_outputs)
        )
        detail = {
            "p03_status": p03[0].get("status") if len(p03) == 1 else "INVALID",
            "evidence": [path.name for path in future_evidence],
            "outputs": [path.name for path in future_outputs if path.exists()],
        }
    except Exception as exc:
        progression_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01P02-P03-NOT-STARTED", progression_ok, detail)


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites: Iterable[ET.Element] = [root] if root.tag == "testsuite" else root.findall("testsuite")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(float(suite.attrib.get(key, "0")))
    return totals


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    for element in root.iter():
        if element.tag == "testsuite":
            if element.attrib.get("hostname") is not None:
                return False
            if element.attrib.get("timestamp") != FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(
    root: Path,
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    reports = [
        ("S01P02-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("targeted_test_minimum", 0))),
        ("S01P02-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("full_regression_test_minimum", 0))),
    ]
    for check_id, relative, minimum in reports:
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            passed = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and normalized
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S01P02-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "S01P02-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)

    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = (
            "STATUS: PASS" in scan_text
            and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan_text
            and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
            and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in scan_text
        )
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        _add(checks, "S01P02-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S01P02-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P02",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "FAQ_AND_ASSUMPTIONS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "release_status": "NOT_READY",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "phase_status": "S01_P02_PASS" if status == "PASS" else "S01_P02_FAILED",
        "next": "S01/P03_READY_NOT_STARTED" if status == "PASS" else "S01/P02_REMEDIATION_REQUIRED",
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

    for path in (FAQ_PATH, REGISTER_PATH, FIXTURE_PATH):
        _single_source_check(root, path, checks)

    fixture = _safe_load(root / FIXTURE_PATH, checks, "S01P02-FIXTURE-STRICT-JSON")
    register = _safe_load(root / REGISTER_PATH, checks, "S01P02-REGISTER-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S01P02-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S01P02-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S01P02-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S01P02-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S01P02-TRACEABILITY-STRICT-JSON")
    source_paths = [relative for relative in PINNED_SOURCE_HASHES if relative != P01_EVIDENCE_PATH.as_posix()]
    source_documents = {
        relative: _safe_load(root / relative, checks, "S01P02-SOURCE-%s-STRICT-JSON" % Path(relative).stem.upper())
        for relative in source_paths
    }
    try:
        faq_text = (root / FAQ_PATH).read_text(encoding="utf-8")
        _add(checks, "S01P02-FAQ-UTF8", True, FAQ_PATH.as_posix())
    except Exception as exc:
        faq_text = ""
        _add(checks, "S01P02-FAQ-UTF8", False, "%s: %s" % (type(exc).__name__, exc))

    _check_pinned_hashes(root, checks, hashes)
    _check_continuous_workflow(root, checks)
    import_isolation_ok = all((root / path).is_file() for path in [Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py")])
    _add(checks, "S01P02-PYTEST-IMPORT-ISOLATION", import_isolation_ok, "package markers")

    dictionaries = [fixture, register, roadmap, task_graph]
    arrays = [requirements, acceptance, traceability]
    if (
        not all(isinstance(value, dict) for value in dictionaries)
        or not all(isinstance(value, list) for value in arrays)
        or not all(value is not None for value in source_documents.values())
    ):
        _add(checks, "S01P02-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S01P02-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    try:
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
    except Exception as exc:
        _add(checks, "S01P02-TASKPACK-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        question_sections = _check_faq(faq_text, fixture, checks)
    except Exception as exc:
        question_sections = {}
        _add(checks, "S01P02-FAQ-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_register(root, register, fixture, source_documents, checks)
    except Exception as exc:
        _add(checks, "S01P02-REGISTER-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        _check_cross_document(question_sections, register, fixture, checks)
    except Exception as exc:
        _add(checks, "S01P02-CROSS-DOCUMENT-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))

    _verify_p01_prerequisite(root, checks, hashes, _verify_git_history)

    try:
        _check_frozen_semantics(
            source_documents["machine/facts/canonical_facts.json"],
            source_documents["machine/facts/parameters.json"],
            source_documents["machine/facts/costs.json"],
            source_documents["machine/facts/email_ingestion.json"],
            source_documents["machine/facts/decision_prerequisites.json"],
            source_documents["machine/facts/degraded_mode_contract.json"],
            source_documents["machine/facts/release_policy.json"],
            source_documents["machine/facts/security_assurance.json"],
            source_documents["machine/facts/authorization_matrix.json"],
            checks,
        )
    except Exception as exc:
        _add(checks, "S01P02-FROZEN-SEMANTICS-EVALUATION-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    _check_p03_not_started(root, checks)
    if require_external_reports:
        _check_runtime_reports(root, fixture, checks, hashes)
    return _build_result(checks, hashes)


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = [
        (FAQ_PATH.as_posix(), root / FAQ_PATH),
        (REGISTER_PATH.as_posix(), root / REGISTER_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        (P01_EVIDENCE_PATH.as_posix(), root / P01_EVIDENCE_PATH),
        (P01_ROLLBACK_PATH.as_posix(), root / P01_ROLLBACK_PATH),
        (CONTINUOUS_WORKFLOW_PATH.as_posix(), root.parent / CONTINUOUS_WORKFLOW_PATH),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s01-p02-rollback-") as directory:
        temporary = Path(directory)
        for index, (label, source) in enumerate(artifacts):
            expected_hash = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted_hash = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored_hash = sha256_file(active)
            results[label] = {
                "status": "PASS" if corrupted_hash != expected_hash and restored_hash == expected_hash else "FAIL",
                "signed_sha256": expected_hash,
                "corrupted_sha256": corrupted_hash,
                "restored_sha256": restored_hash,
            }
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_FAQ_CONTRACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        FAQ_PATH,
        REGISTER_PATH,
        FIXTURE_PATH,
        P01_EVIDENCE_PATH,
        P01_ROLLBACK_PATH,
        *[Path(relative) for relative in PINNED_SOURCE_HASHES if relative != P01_EVIDENCE_PATH.as_posix()],
        Path("tests/S01/P02_test.py"),
        Path("abd_acceptance/customer_faq.py"),
        Path("abd_acceptance/delivery.py"),
        Path("tests/__init__.py"),
        Path("tests/S00/__init__.py"),
        Path("tests/S01/__init__.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[CONTINUOUS_WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / CONTINUOUS_WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S01-P02-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
            "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["phase_status"] = "S01_P02_FAILED"
        result["next"] = "S01/P02_REMEDIATION_REQUIRED"

    input_hashes = _input_hashes(root)
    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S01",
        "phase_id": "P02",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S01-P02-01": FAQ_PATH.as_posix(),
            "ART-S01-P02-02": REGISTER_PATH.as_posix(),
        },
        "p01_prerequisite": {
            "evidence": P01_EVIDENCE_PATH.as_posix(),
            "sha256": P01_EVIDENCE_SHA256,
            "commit": P01_COMMIT,
            "status": "PASS",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": None,
            "model_not_applicable_reason": "S01/P02 freezes customer questions and assumptions; no prediction model is implemented or evaluated in this phase.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing STAGE-REVIEW-S00",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S01/P02_test.py --junitxml=machine/evidence/S01/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S01/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S01-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {
            "artifact": ROLLBACK_EVIDENCE_PATH.as_posix(),
            "status": rollback.get("status"),
        },
        "external_effect_boundary": {
            "github_upload_performed": False,
            "external_account_or_api_accessed": False,
            "secret_provisioned": False,
            "incremental_cash_spent_aud": "0.00",
            "production_deployment_claimed": False,
            "all_market_coverage_claimed": False,
            "gmail_connected_claimed": False,
            "real_order_capability_present": False,
            "return_or_guarantee_claimed": False,
        },
        "explicit_unknowns": [
            "The 30% monthly target remains unverified and is not guaranteed.",
            "OVH, Cloudflare, Gmail, betting accounts, source freshness and all-market production coverage remain unverified.",
            "No external account, secret, real email, order, deployment or actual return was observed in this phase.",
        ],
        "release_status": "NOT_READY",
        "phase_status": result["phase_status"],
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
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S01-P02"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S01-P02 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S01/P03_READY_NOT_STARTED" if status == "PASS" else "S01/P02_REMEDIATION_REQUIRED"
    payload = b"".join(
        (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows
    )
    _atomic_write(path, payload)


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
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
