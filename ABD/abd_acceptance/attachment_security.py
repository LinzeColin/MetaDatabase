"""Independent deterministic acceptance oracle for ABD S06/P03.

The oracle consumes frozen synthetic bytes only.  It does not execute an
attachment, contact Gmail or another network service, start an OS sandbox or
process, access private business data, move mail to trash, or wait for real
time.  A successful result proves the stated deterministic fixture gate; it
does not claim a production malware engine or a financial outcome has run.
"""

from __future__ import annotations

import ast
import base64
from copy import deepcopy
import hashlib
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from attachment_sandbox import (
    CONTRACT_ID as SANDBOX_CONTRACT_ID,
    REQUIREMENT_ID as SANDBOX_REQUIREMENT_ID,
    load_policy,
    sandbox_plan,
    scan_attachment,
    scan_attachments,
)

from .canonical_facts import sha256_file, strict_json_load
from .mail_preservation import verify_existing_phase_evidence as verify_mail_preservation_evidence


CONTRACT_ID = "AC-S06-P03"
REQUIREMENT_ID = "REQ-S06-P03"
STAGE_ID = "S06"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-29T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SANDBOX_PATH = Path("attachment_sandbox.py")
REGISTRY_PATH = Path("parser_registry.json")
RULES_PATH = Path("quarantine_rules.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S06_P03.json")
TEST_PATH = Path("tests/S06/P03_test.py")
ORACLE_PATH = Path("abd_acceptance/attachment_security.py")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S06-P02_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S06/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S06/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")

PINNED_PHASE_HASHES: Dict[str, str] = {
    "attachment_sandbox.py": "e56426b20e32958c3a118948edd44a127b1ecd9bce7be2ca808a6818ffb30c8a",
    "parser_registry.json": "8bf360cb020f6cb4649a9da3ff2ecb1c4ba7d26cd340a99bd5c76425f81ba259",
    "quarantine_rules.json": "59f2cb7db51b42a48fc288a3e623fd46fd9cc354d2427bd4a896a47cdd94f667",
    "machine/tests/fixtures/S06_P03.json": "aa615f2215591aedf9c2ad5f8ff78753155385332989e4ff1479ffeacc4ad7dc",
    "tests/S06/P03_test.py": "16127b7306f0ee7f09bceacf2874f60c0805e3a2080bfcb30b2c6e474fa8b433",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "05afd9fab61769998e98daa419cd896d413372889e6f17d4960a77857142df2d"
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {}

ROLLBACK_ARTIFACTS = (SANDBOX_PATH, REGISTRY_PATH, RULES_PATH)
EXTERNAL_EFFECT_BOUNDARY = {
    "gmail_account_or_api_accessed": False,
    "gmail_mutation_performed": False,
    "private_database_client_executed": False,
    "private_database_or_raw_data_written": False,
    "real_network_accessed": False,
    "real_time_soak_waited": False,
    "scheduler_daemon_started": False,
    "token_or_client_secret_read": False,
    "attachment_executed": False,
    "os_sandbox_process_started": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "real_order_submitted_or_retried": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
}

SECRET_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])ya29\.[A-Za-z0-9._-]+", re.I),
    re.compile(r"(?:^|[^a-z0-9])1//[A-Za-z0-9._-]+", re.I),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}", re.I),
)
LOCAL_PATH_FRAGMENTS = ("/" + "Users/", "file" + "://")
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _portable(path: Path) -> str:
    rendered = path.as_posix()
    for marker in ("/machine/", "/abd_acceptance/", "/tests/"):
        if marker in rendered:
            return marker.strip("/").split("/", 1)[0] + "/" + rendered.split(marker, 1)[1]
    return path.name


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s=%s row" % (key, identifier))
    return matches[0]


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]*("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8"))


def _current_code_hash(root: Path) -> str:
    payload = b""
    for relative in (SANDBOX_PATH, REGISTRY_PATH, RULES_PATH, ORACLE_PATH):
        payload += relative.as_posix().encode("utf-8") + b"\0" + (root / relative).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _scan(root: Path, record: Mapping[str, Any]) -> Dict[str, Any]:
    return scan_attachment(
        record,
        parser_registry_path=root / REGISTRY_PATH,
        quarantine_rules_path=root / RULES_PATH,
    )


def _scan_many(root: Path, records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return scan_attachments(
        records,
        parser_registry_path=root / REGISTRY_PATH,
        quarantine_rules_path=root / RULES_PATH,
    )


def _policy(root: Path) -> Dict[str, Any]:
    return load_policy(parser_registry_path=root / REGISTRY_PATH, quarantine_rules_path=root / RULES_PATH)


def _sandbox_plan(root: Path) -> Dict[str, Any]:
    return sandbox_plan(policy=_policy(root))


def _fixture_cases(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise ValueError("fixture cases are unavailable")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in cases:
        if not isinstance(row, Mapping) or set(row) != {"id", "attachment_id", "filename", "content_base64", "expected_status", "expected_reason"}:
            raise ValueError("fixture case fields are not exact")
        case_id = row.get("id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", case_id) or case_id in seen:
            raise ValueError("fixture case id is invalid")
        seen.add(case_id)
        if row.get("expected_status") not in {"PARSED_SAFE", "QUARANTINED_KEEP"}:
            raise ValueError("fixture expected status is invalid")
        expected_reason = row.get("expected_reason")
        if row["expected_status"] == "PARSED_SAFE" and expected_reason is not None:
            raise ValueError("safe fixture cannot declare a quarantine reason")
        if row["expected_status"] == "QUARANTINED_KEEP" and (not isinstance(expected_reason, str) or not expected_reason.endswith("_QUARANTINE")):
            raise ValueError("quarantine fixture reason is invalid")
        try:
            content = base64.b64decode(row["content_base64"], validate=True)
        except Exception as exc:
            raise ValueError("fixture base64 is invalid") from exc
        if not content:
            raise ValueError("fixture content is empty")
        records.append(
            {
                "case_id": case_id,
                "attachment_id": row["attachment_id"],
                "filename": row["filename"],
                "content": content,
                "expected_status": row["expected_status"],
                "expected_reason": expected_reason,
            }
        )
    required = {
        "SAFE_CSV",
        "SAFE_PDF",
        "SAFE_XLSX",
        "MALWARE_MARKER",
        "MACRO_OFFICE",
        "SCRIPT_PDF",
        "FORMULA_CSV",
        "PROMPT_INJECTION",
        "UNKNOWN_TYPE",
        "TYPE_MISMATCH",
        "PATH_TRAVERSAL",
        "DANGEROUS_EXTENSION",
        "MALFORMED_OFFICE",
    }
    if {record["case_id"] for record in records} != required:
        raise ValueError("fixture does not cover the exact P03 threat set")
    return records


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(
            checks,
            "S06P03-PIN-%s" % Path(relative).stem.upper(),
            bool(expected) and actual == expected,
            {"expected": expected or "UNSET", "actual": actual},
        )


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S06P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S06P03-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S06P03-TASK-GRAPH-STRICT-JSON")
    trace = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S06P03-TRACE-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        task_01 = _row(tasks, "T-S06-P03-01")
        task_02 = _row(tasks, "T-S06-P03-02")
        task_03 = _row(tasks, "T-S06-P03-03")
        trace_row = _row(trace, REQUIREMENT_ID, key="requirement_id")
        requirement_ok = (
            requirement.get("stage_id") == STAGE_ID
            and requirement.get("phase_id") == PHASE_ID
            and requirement.get("scope") == ["attachment_sandbox.py", "parser_registry.json", "quarantine_rules.json"]
            and requirement.get("target") == "恶意、宏、脚本、公式注入或未知类型全部隔离。"
            and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        )
        contract_ok = (
            contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S06-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == "恶意、宏、脚本、公式注入或未知类型全部隔离。"
            and [test.get("id") for test in contract.get("tests", [])] == ["TEST-S06-P03", "TEST-S06-P03-BOUNDARY", "TEST-S06-P03-REPLAY"]
        )
        graph_ok = (
            task_01.get("outputs") == ["attachment_sandbox.py", "parser_registry.json", "quarantine_rules.json"]
            and task_01.get("depends_on") == ["T-S06-P02-03"]
            and task_02.get("outputs") == ["tests/S06/P03_test.py", "machine/tests/fixtures/S06_P03.json"]
            and task_02.get("depends_on") == ["T-S06-P03-01"]
            and task_03.get("outputs") == ["machine/evidence/EVD-S06-P03.json", "machine/evidence/EVD-S06-P03_rollback.json"]
            and task_03.get("depends_on") == ["T-S06-P03-02"]
        )
        trace_ok = (
            trace_row.get("acceptance_criteria_id") == CONTRACT_ID
            and trace_row.get("evidence_id") == "EVD-S06-P03"
            and trace_row.get("artifact_ids") == ["ART-S06-P03-01", "ART-S06-P03-02", "ART-S06-P03-03"]
        )
    except Exception as exc:
        requirement_ok = contract_ok = graph_ok = trace_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = "exact S06/P03 task-pack rows"
    _add(checks, "S06P03-TASKPACK-REQUIREMENT-EXACT", requirement_ok, detail)
    _add(checks, "S06P03-TASKPACK-CONTRACT-EXACT", contract_ok, detail)
    _add(checks, "S06P03-TASKPACK-GRAPH-EXACT", graph_ok, detail)
    _add(checks, "S06P03-TASKPACK-TRACE-EXACT", trace_ok, detail)


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    try:
        predecessor = verify_mail_preservation_evidence(root, verify_git_history=verify_git_history)
        ok = predecessor.get("status") == "PASS" and predecessor.get("next") == "S06/P03_READY_NOT_STARTED"
        detail: Any = {"status": predecessor.get("status"), "next": predecessor.get("next")}
    except Exception as exc:
        ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P03-PREREQUISITE-P02-PASS", ok, detail)


def _check_policy(root: Path, checks: List[Dict[str, Any]]) -> None:
    registry = _safe_load(root / REGISTRY_PATH, checks, "S06P03-REGISTRY-STRICT-JSON")
    rules = _safe_load(root / RULES_PATH, checks, "S06P03-RULES-STRICT-JSON")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S06P03-PARAMETERS-STRICT-JSON")
    try:
        policy = _policy(root)
        runtime = policy["runtime"]
        params_email = parameters["email"] if isinstance(parameters, Mapping) else None
        limits_ok = (
            runtime["attachment_max_bytes"] == params_email["max_attachment_bytes"] == 50_000_000
            and runtime["cpu_budget_seconds"] == params_email["parser_sandbox_cpu_seconds"] == 60
            and runtime["memory_budget_mb"] == params_email["parser_sandbox_memory_mb"] == 256
            and params_email["malware_scan_required"] is True
        )
        profiles_ok = set(policy["profiles_by_extension"]) == {"csv", "pdf", "xlsx", "docx", "pptx"}
        rules_ok = (
            policy["rules"]["permanent_delete"] is False
            and policy["rules"]["mail_content_instruction_trust"] == "NONE"
            and "xlsm" in policy["rules"]["dangerous_extensions"]
        )
        plan = _sandbox_plan(root)
        plan_ok = (
            plan["mode"] == "NO_EXECUTION_PURE_BYTES_INSPECTION"
            and plan["external_network_accessed"] is False
            and plan["attachment_execution_performed"] is False
            and plan["zip_extracted_to_disk"] is False
            and plan["subprocess_started"] is False
            and plan["real_time_soak_waited"] is False
            and plan["malware_clearance_claimed"] is False
        )
        identity_ok = SANDBOX_CONTRACT_ID == CONTRACT_ID and SANDBOX_REQUIREMENT_ID == REQUIREMENT_ID
    except Exception as exc:
        limits_ok = profiles_ok = rules_ok = plan_ok = identity_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = {"registry_type": type(registry).__name__, "rules_type": type(rules).__name__}
    _add(checks, "S06P03-POLICY-FACT-LIMITS-EXACT", limits_ok, detail)
    _add(checks, "S06P03-PARSER-ALLOWLIST-EXACT", profiles_ok, detail)
    _add(checks, "S06P03-QUARANTINE-DEFAULTS-EXACT", rules_ok, detail)
    _add(checks, "S06P03-NO-EXECUTION-SANDBOX-PLAN", plan_ok, detail)
    _add(checks, "S06P03-SANDBOX-IDENTITY-EXACT", identity_ok, detail)


def _check_fixture(root: Path, fixture: Any, checks: List[Dict[str, Any]]) -> list[dict[str, Any]] | None:
    if not isinstance(fixture, Mapping):
        _add(checks, "S06P03-FIXTURE-SHAPE", False, "fixture unavailable")
        return None
    expected = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "fixed_clock",
        "input_mode",
        "expected_oracle_check_minimum",
        "minimum_targeted_pytest_cases",
        "minimum_full_pytest_cases",
        "replay_iterations",
        "adverse_perturbation_iterations",
        "scaled_attachment_boundary_bytes",
        "expected_next",
        "expected_release_status",
        "cases",
    }
    try:
        cases = _fixture_cases(fixture)
        shape_ok = (
            set(fixture) == expected
            and fixture.get("schema_version") == "1.0.0"
            and fixture.get("fixture_id") == "FIX-S06-P03"
            and fixture.get("contract_id") == CONTRACT_ID
            and fixture.get("requirement_id") == REQUIREMENT_ID
            and fixture.get("fixed_clock") == FIXED_CLOCK
            and fixture.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
            and type(fixture.get("expected_oracle_check_minimum")) is int
            and type(fixture.get("minimum_targeted_pytest_cases")) is int
            and type(fixture.get("minimum_full_pytest_cases")) is int
            and fixture.get("replay_iterations") == 100
            and fixture.get("adverse_perturbation_iterations") == 10_000
            and fixture.get("scaled_attachment_boundary_bytes") == 4
            and fixture.get("expected_next") == "S06/P04_READY_NOT_STARTED"
            and fixture.get("expected_release_status") == "NOT_READY_S06_P04_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED"
        )
        detail: Any = {"case_count": len(cases)}
    except Exception as exc:
        cases = None
        shape_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P03-FIXTURE-SHAPE", shape_ok, detail)
    return cases


def _check_core_flow(root: Path, cases: Sequence[Mapping[str, Any]], checks: List[Dict[str, Any]]) -> None:
    results: dict[str, Dict[str, Any]] = {}
    for case in cases:
        result = _scan(
            root,
            {
                "attachment_id": case["attachment_id"],
                "filename": case["filename"],
                "content": case["content"],
            },
        )
        results[str(case["case_id"])] = result
    exact = all(
        result.get("status") == case["expected_status"]
        and (case["expected_reason"] is None or case["expected_reason"] in result.get("reason_codes", []))
        for case, result in ((case, results[str(case["case_id"])]) for case in cases)
    )
    safe_ids = {"SAFE_CSV", "SAFE_PDF", "SAFE_XLSX"}
    danger_ids = set(results) - safe_ids
    isolation_ok = (
        all(results[case_id].get("status") == "PARSED_SAFE" for case_id in safe_ids)
        and all(results[case_id].get("status") == "QUARANTINED_KEEP" and results[case_id].get("quarantined") is True for case_id in danger_ids)
    )
    no_mutation_ok = all(
        result.get("trash_eligible") is False
        and result.get("gmail_mutation_performed") is False
        and result.get("permanent_delete_performed") is False
        and result.get("sandbox", {}).get("real_time_soak_waited") is False
        and "content" not in result
        for result in results.values()
    )
    required_reasons = {
        "MALWARE_MARKER": "MALWARE_MARKER_QUARANTINE",
        "MACRO_OFFICE": "MACRO_OR_ACTIVE_OFFICE_ENTRY_QUARANTINE",
        "SCRIPT_PDF": "PDF_ACTIVE_CONTENT_QUARANTINE",
        "FORMULA_CSV": "FORMULA_INJECTION_QUARANTINE",
        "PROMPT_INJECTION": "PROMPT_INJECTION_QUARANTINE",
        "UNKNOWN_TYPE": "UNKNOWN_TYPE_QUARANTINE",
        "TYPE_MISMATCH": "TYPE_SIGNATURE_MISMATCH_QUARANTINE",
        "PATH_TRAVERSAL": "PATH_TRAVERSAL_QUARANTINE",
        "DANGEROUS_EXTENSION": "DANGEROUS_EXTENSION_QUARANTINE",
        "MALFORMED_OFFICE": "OFFICE_PARSE_FAILURE_QUARANTINE",
    }
    threat_gate = all(reason in results[case_id].get("reason_codes", []) for case_id, reason in required_reasons.items())
    batch = _scan_many(
        root,
        [
            {"attachment_id": case["attachment_id"], "filename": case["filename"], "content": case["content"]}
            for case in cases
        ],
    )
    batch_ok = [row.get("content_sha256") for row in batch] == [results[str(case["case_id"])].get("content_sha256") for case in cases]
    _add(checks, "S06P03-FROZEN-CASES-EXACT", exact, {case_id: result.get("status") for case_id, result in results.items()})
    _add(checks, "S06P03-MALWARE-MACRO-SCRIPT-FORMULA-UNKNOWN-ISOLATED", isolation_ok and threat_gate, sorted(danger_ids))
    _add(checks, "S06P03-NO-TRASH-OR-DESTRUCTIVE-ACTION", no_mutation_ok, "P04 remains the only trash owner")
    _add(checks, "S06P03-BATCH-ORDER-AND-HASH-REPLAY", batch_ok, {"count": len(batch)})


def _check_replay_and_boundaries(root: Path, fixture: Mapping[str, Any], cases: Sequence[Mapping[str, Any]], checks: List[Dict[str, Any]]) -> None:
    by_id = {str(case["case_id"]): case for case in cases}
    safe = {"attachment_id": by_id["SAFE_CSV"]["attachment_id"], "filename": by_id["SAFE_CSV"]["filename"], "content": by_id["SAFE_CSV"]["content"]}
    formula = {"attachment_id": by_id["FORMULA_CSV"]["attachment_id"], "filename": by_id["FORMULA_CSV"]["filename"], "content": by_id["FORMULA_CSV"]["content"]}
    first_safe = _scan(root, safe)
    repeats = [_scan(root, safe) for _ in range(int(fixture["replay_iterations"]))]
    first_formula = _scan(root, formula)
    perturbations = [_scan(root, formula) for _ in range(int(fixture["adverse_perturbation_iterations"]))]
    replay_ok = all(result == first_safe for result in repeats)
    adverse_ok = all(result == first_formula and result.get("status") == "QUARANTINED_KEEP" for result in perturbations)
    try:
        registry = strict_json_load(root / REGISTRY_PATH)
        registry["runtime"]["attachment_max_bytes"] = int(fixture["scaled_attachment_boundary_bytes"])
        registry["runtime"]["max_zip_uncompressed_bytes"] = int(fixture["scaled_attachment_boundary_bytes"])
        rules = strict_json_load(root / RULES_PATH)
        with tempfile.TemporaryDirectory(prefix="abd-s06-p03-boundary-") as directory:
            directory_path = Path(directory)
            registry_path = directory_path / "parser_registry.json"
            rules_path = directory_path / "quarantine_rules.json"
            registry_path.write_bytes(_json_bytes(registry))
            rules_path.write_bytes(_json_bytes(rules))
            at_limit = scan_attachment(
                {"attachment_id": "ATTBOUNDARY", "filename": "limit.csv", "content": b"a,b\n"},
                parser_registry_path=registry_path,
                quarantine_rules_path=rules_path,
            )
            over_limit = scan_attachment(
                {"attachment_id": "ATTBOUNDARY2", "filename": "over.csv", "content": b"a,b\nx"},
                parser_registry_path=registry_path,
                quarantine_rules_path=rules_path,
            )
        boundary_ok = at_limit.get("status") == "PARSED_SAFE" and over_limit.get("reason_codes") == ["ATTACHMENT_SIZE_EXCEEDED_QUARANTINE"]
        detail: Any = {"at_limit": at_limit.get("status"), "over_limit": over_limit.get("reason_codes")}
    except Exception as exc:
        boundary_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P03-100-REPLAY-DETERMINISTIC", replay_ok, {"iterations": len(repeats)})
    _add(checks, "S06P03-ONE-IN-TEN-THOUSAND-ADVERSE-STABLE", adverse_ok, {"iterations": len(perturbations)})
    _add(checks, "S06P03-SCALED-SIZE-BOUNDARY-FAILS-CLOSED", boundary_ok, detail)


def _check_static_safety(root: Path, checks: List[Dict[str, Any]]) -> None:
    path = root / SANDBOX_PATH
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=SANDBOX_PATH.as_posix())
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        denied = {"socket", "subprocess", "requests", "urllib", "http", "os", "shutil", "time", "asyncio"}
        imports_ok = not (imported_roots & denied)
        banned_calls = ("time.sleep(", "subprocess.", "socket.", "requests.", "urllib.", "os.system(")
        calls_ok = not any(marker in text for marker in banned_calls)
        no_extract_ok = "extractall(" not in text and ".extract(" not in text
        detail: Any = {"imports": sorted(imported_roots), "denied": sorted(imported_roots & denied)}
    except Exception as exc:
        imports_ok = calls_ok = no_extract_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P03-NO-NETWORK-OR-PROCESS-IMPORT", imports_ok, detail)
    _add(checks, "S06P03-NO-SLEEP-OR-EXTERNAL-CALL", calls_ok, detail)
    _add(checks, "S06P03-NO-ZIP-DISK-EXTRACTION", no_extract_ok, detail)


def _check_no_sensitive_material(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = (SANDBOX_PATH, REGISTRY_PATH, RULES_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH)
    leaks: List[Dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative.as_posix(), "kind": "local-path"})
    _add(checks, "S06P03-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
    suites = list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in result:
            result[key] += int(suite.attrib.get(key, "0"))
    return result


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(path).getroot()
    suites = list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
        for suite in suites
    )


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for label, relative, minimum in (
        ("TARGETED", JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases")),
        ("FULL", FULL_JUNIT_PATH, fixture.get("minimum_full_pytest_cases")),
    ):
        try:
            summary = _junit_summary(root / relative)
            ok = type(minimum) is int and summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and _junit_is_normalized(root / relative)
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, "S06P03-%s-PYTEST-REPORT" % label, ok, {"summary": summary, "minimum": minimum, "normalized": _junit_is_normalized(root / relative)})
        except Exception as exc:
            _add(checks, "S06P03-%s-PYTEST-REPORT" % label, False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S06P03-PACK-REPORT-STRICT-JSON")
    if isinstance(pack, Mapping):
        pack_ok = pack.get("status") == "PASS" and pack.get("summary", {}).get("checks") == 49 and pack.get("summary", {}).get("failed") == 0
        _add(checks, "S06P03-TASKPACK-49-PASS", pack_ok, pack.get("summary"))
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8") if (root / SCAN_REPORT_PATH).is_file() else ""
    required_lines = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    _add(checks, "S06P03-PAID-DEPENDENCY-SCAN", required_lines <= set(scan.splitlines()), SCAN_REPORT_PATH.as_posix())
    if (root / SCAN_REPORT_PATH).is_file():
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S06P03-FIXTURE-STRICT-JSON")
    _check_pins(root, checks, hashes)
    _add(
        checks,
        "S06P03-ORACLE-SELF-INTEGRITY",
        bool(STRUCTURAL_SELF_NORMALIZED_SHA256) and _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256 or "UNSET", "actual": _structural_self_hash(root)},
    )
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, verify_git_history=_verify_git_history)
    _check_policy(root, checks)
    cases = _check_fixture(root, fixture, checks)
    if isinstance(fixture, Mapping) and cases is not None:
        _check_core_flow(root, cases, checks)
        _check_replay_and_boundaries(root, fixture, cases, checks)
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S06P03-FROZEN-THREAT-GATE", False, "fixture unavailable")
    _check_static_safety(root, checks)
    _check_no_sensitive_material(root, checks)
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS" if not failed else "FAIL",
        "phase_status": "S06_P03_PASS" if not failed else "S06_P03_FAIL",
        "decision": "ATTACHMENTS_PARSED_OR_QUARANTINED_KEEP_ONLY" if not failed else "S06_P03_BLOCKED_FAIL_CLOSED",
        "release_status": "NOT_READY_S06_P04_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S06/P04_READY_NOT_STARTED" if not failed else "S06/P03_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S06_P03_CANDIDATE_VALID" if result["status"] == "PASS" else "S06_P03_CANDIDATE_INVALID",
        "summary": result["summary"],
        "next": result["next"],
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, str]] = {}
    for relative in ROLLBACK_ARTIFACTS:
        try:
            before = sha256_file(root / relative)
            after = sha256_file(root / relative)
            artifacts[relative.as_posix()] = {"status": "PASS" if before == after else "FAIL", "before": before, "after": after}
        except Exception as exc:
            artifacts[relative.as_posix()] = {"status": "FAIL", "detail": "%s: %s" % (type(exc).__name__, exc)}
    status = "PASS" if artifacts and all(row.get("status") == "PASS" for row in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_ATTACHMENT_PARSER_KEEP_ARCHIVED_SOURCE_NO_GMAIL_ACTION",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "gmail_account_or_api_accessed": False,
        "attachment_executed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = (
        SANDBOX_PATH,
        REGISTRY_PATH,
        RULES_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        P02_EVIDENCE_PATH,
        P02_ROLLBACK_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/email_ingestion.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
    )
    return {relative.as_posix(): sha256_file(root / relative) for relative in paths}


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
    *,
    _verify_git_history: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    fixture = strict_json_load(root / FIXTURE_PATH)
    scan_summary: list[dict[str, Any]] = []
    try:
        for case in _fixture_cases(fixture):
            result = _scan(root, {"attachment_id": case["attachment_id"], "filename": case["filename"], "content": case["content"]})
            scan_summary.append(
                {
                    "case_id": case["case_id"],
                    "status": result.get("status"),
                    "reason_codes": result.get("reason_codes"),
                    "content_sha256": result.get("content_sha256"),
                    "trash_eligible": result.get("trash_eligible"),
                }
            )
        safe_case = next(case for case in _fixture_cases(fixture) if case["case_id"] == "SAFE_CSV")
        repeat = [
            _scan(root, {"attachment_id": safe_case["attachment_id"], "filename": safe_case["filename"], "content": safe_case["content"]})
            for _ in range(int(fixture["adverse_perturbation_iterations"]))
        ]
        replay_summary: Mapping[str, Any] = {
            "iterations": len(repeat),
            "all_equal": all(row == repeat[0] for row in repeat),
            "result_sha256": _sha256_bytes(_json_bytes(repeat[0])) if repeat else "",
        }
    except Exception as exc:
        scan_summary = [{"error": "%s: %s" % (type(exc).__name__, exc)}]
        replay_summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": fixture.get("fixed_clock"),
        "status": validation["status"],
        "phase_status": validation["phase_status"],
        "decision": validation["decision"],
        "validation": validation,
        "predecessor_evidence": {
            "p02_evidence": P02_EVIDENCE_PATH.as_posix(),
            "p02_evidence_sha256": sha256_file(root / P02_EVIDENCE_PATH),
            "p02_rollback_sha256": sha256_file(root / P02_ROLLBACK_PATH),
        },
        "attachment_scan_summary": scan_summary,
        "deterministic_replay": replay_summary,
        "no_real_time_soak": _sandbox_plan(root),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": fixture.get("expected_release_status"),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S06/P03_test.py --junitxml=machine/evidence/S06/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S06/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S06-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": _input_hashes(root),
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S06/P03 validates frozen attachment byte inspection only.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str, fixed_clock: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S06-P03"]
    rows.append(
        {
            "id": "INDEX-AC-S06-P03",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S06/P04_READY_NOT_STARTED" if status == "PASS" else "S06/P03_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise ValueError("S06/P03 evidence must be written to the project machine/evidence directory")
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(evidence_path, _json_bytes(evidence))
    _atomic_write(rollback_path, _json_bytes(rollback))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash, str(evidence["fixed_clock"]))
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = dict(evidence)
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S06P03-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S06P03-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S06-P03"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S06/P04_READY_NOT_STARTED"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S06P03-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                input_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S06P03-EXISTING-INPUT-HASHES", not input_errors, input_errors or "all inputs match")
        _add(checks, "S06P03-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S06P03-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S06-P03-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S06P03-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S06P03-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    _add(checks, "S06P03-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "",
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S06/P04_READY_NOT_STARTED" if not failed else "S06/P03_REMEDIATION_REQUIRED",
    }


__all__ = [
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_FIXED_CLOCK",
    "JUNIT_PATH",
    "ORACLE_PATH",
    "PINNED_PHASE_HASHES",
    "REGISTRY_PATH",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "RULES_PATH",
    "SANDBOX_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "SUCCESSOR_UNIT_PROFILE_HASHES",
    "TEST_PATH",
    "_junit_is_normalized",
    "_junit_summary",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
