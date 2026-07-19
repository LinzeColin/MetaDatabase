from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple


CONTRACT_ID = "AC-S00-P01"
REQUIREMENT_ID = "REQ-S00-P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
PINNED_CANONICAL_SHA256 = "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385"
PINNED_GOAL_SHA256 = "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5"
PINNED_ROADMAP_SHA256 = "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
PINNED_TASKPACK_ARCHIVE_SHA256 = "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"

CANONICAL_PATH = Path("machine/facts/canonical_facts.json")
CONFLICT_PATH = Path("machine/facts/canonical_conflicts.json")
HASH_LOCK_PATH = Path("machine/facts/canonical_facts.sha256")
JUNIT_PATH = Path("machine/evidence/S00/P01/pytest.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")


class DuplicateKeyError(ValueError):
    """Raised when JSON contains an ambiguous duplicate object key."""


def _reject_duplicate_keys(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def strict_json_load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_reject_duplicate_keys,
    )


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:  # fail closed and preserve the exact parse failure
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    rendered = path.as_posix()
    marker = "/machine/"
    portable = "machine/" + rendered.split(marker, 1)[1] if marker in rendered else path.name
    _add(checks, check_id, True, portable)
    return value


def _duplicates_in_scalar_lists(value: Any, pointer: str = "") -> List[str]:
    duplicates: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            duplicates.extend(_duplicates_in_scalar_lists(child, pointer + "/" + key))
    elif isinstance(value, list):
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in value):
            rendered = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
            if len(rendered) != len(set(rendered)):
                duplicates.append(pointer or "/")
        for index, child in enumerate(value):
            duplicates.extend(_duplicates_in_scalar_lists(child, pointer + "/" + str(index)))
    return duplicates


def _read_hash_lock(path: Path) -> Tuple[str, str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("hash lock must contain exactly one non-empty line")
    match = re.fullmatch(r"([0-9a-f]{64})\s{2}(.+)", lines[0])
    if not match:
        raise ValueError("hash lock must use '<sha256><two spaces><path>'")
    return match.group(1), match.group(2)


def _cross_source_checks(root: Path, canonical: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        version_text = (root / "VERSION").read_text(encoding="utf-8").strip()
    except Exception as exc:
        _add(checks, "FACT-CROSS-SOURCE", False, "VERSION: %s: %s" % (type(exc).__name__, exc))
        return

    params = _safe_load(root / "machine/facts/parameters.json", checks, "SOURCE-PARAMETERS-PARSE")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "SOURCE-COSTS-PARSE")
    release = _safe_load(root / "machine/evidence/release_manifest.json", checks, "SOURCE-RELEASE-PARSE")

    if params is None or costs is None or release is None:
        _add(checks, "FACT-CROSS-SOURCE", False, "one or more source files did not parse")
        return

    try:
        comparisons = {
            "VERSION": version_text == canonical["product"]["version"],
            "parameters.monthly_return": params["target_30pct"]["monthly_return"]
            == canonical["product"]["monthly_target_return"],
            "costs.incremental_budget": costs["incremental_cash_budget"]["likely"]
            == canonical["product"]["incremental_cash_budget_aud"],
            "release.version": release["version"] == canonical["product"]["version"],
            "release.initial_bankroll": release["financial"]["initial_bankroll_aud"]
            == canonical["product"]["initial_bankroll_aud"],
            "release.return_not_guaranteed": release["financial"]["return_guaranteed"] is False,
            "refresh.more_than_24h": params["coverage_and_freshness"]["refresh_seconds"]["more_than_24h"]
            == canonical["scheduling"]["event_more_than_24h_refresh_seconds"],
        }
    except (KeyError, TypeError) as exc:
        _add(checks, "FACT-CROSS-SOURCE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    failures = sorted(key for key, passed in comparisons.items() if not passed)
    _add(checks, "FACT-CROSS-SOURCE", not failures, failures or sorted(comparisons))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites: Iterable[ET.Element]
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = root.findall("testsuite")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(float(suite.attrib.get(key, "0")))
    return totals


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "FACTS_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "scope_statement": "No conflicts in evaluated scope; external unprovided drafts and time-varying provider facts are not asserted.",
        "release_status": "NOT_READY",
        "stage_status": "S00_IN_PROGRESS",
        "next": "S00/P02_READY_NOT_STARTED" if status == "PASS" else "S00/P02_BLOCKED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, Any] = {}

    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("canonical_facts.json")
        if ".git" not in path.parts and "__pycache__" not in path.parts
    )
    expected_candidates = [CANONICAL_PATH.as_posix()]
    _add(checks, "FACT-SINGLE-SOURCE", candidates == expected_candidates, candidates)

    canonical_path = root / CANONICAL_PATH
    canonical = _safe_load(canonical_path, checks, "FACT-STRICT-JSON")
    if not isinstance(canonical, dict):
        _add(checks, "FACT-OBJECT", False, "canonical facts are not a parsed JSON object")
        return _build_result(checks, hashes)

    canonical_hash = sha256_file(canonical_path)
    hashes[CANONICAL_PATH.as_posix()] = canonical_hash
    required_top_level = {
        "schema_version",
        "product",
        "scope",
        "runtime",
        "scheduling",
        "email",
        "truth_and_evidence",
        "authorization",
    }
    missing = sorted(required_top_level - set(canonical))
    _add(checks, "FACT-REQUIRED-TOP-LEVEL", not missing, missing or sorted(required_top_level))

    try:
        product = canonical["product"]
        exact_values = {
            "product.id": product["id"] == "ABD",
            "product.version": product["version"] == VERSION,
            "product.initial_bankroll_aud": product["initial_bankroll_aud"] == "300.00",
            "product.incremental_cash_budget_aud": product["incremental_cash_budget_aud"] == "0.00",
            "product.monthly_target_return": product["monthly_target_return"] == "0.30",
            "scope.analysis_only": canonical["scope"]["product_role"] == "ANALYSIS_AND_ADVICE_ONLY",
            "scope.no_order_module": canonical["scope"]["order_submission_module_present"] is False,
            "truth.actual_return_needs_evidence": canonical["truth_and_evidence"]["actual_return_requires_verified_execution_evidence"] is True,
        }
        exact_failures = sorted(key for key, passed in exact_values.items() if not passed)
        _add(checks, "FACT-BASELINE-VALUES", not exact_failures, exact_failures or sorted(exact_values))
    except (KeyError, TypeError) as exc:
        _add(checks, "FACT-BASELINE-VALUES", False, "%s: %s" % (type(exc).__name__, exc))

    duplicate_arrays = _duplicates_in_scalar_lists(canonical)
    _add(checks, "FACT-UNIQUE-SCALAR-LISTS", not duplicate_arrays, duplicate_arrays or "none")
    _add(
        checks,
        "FACT-PINNED-HASH",
        canonical_hash == PINNED_CANONICAL_SHA256,
        {"expected": PINNED_CANONICAL_SHA256, "actual": canonical_hash},
    )

    try:
        locked_hash, locked_path = _read_hash_lock(root / HASH_LOCK_PATH)
        lock_ok = locked_hash == canonical_hash and locked_path == CANONICAL_PATH.as_posix()
        _add(
            checks,
            "FACT-HASH-LOCK",
            lock_ok,
            {"locked_hash": locked_hash, "locked_path": locked_path, "actual_hash": canonical_hash},
        )
    except Exception as exc:
        _add(checks, "FACT-HASH-LOCK", False, "%s: %s" % (type(exc).__name__, exc))

    conflicts = _safe_load(root / CONFLICT_PATH, checks, "CONFLICT-STRICT-JSON")
    if isinstance(conflicts, dict):
        raw_entries = conflicts.get("conflicts", [])
        entries = raw_entries if isinstance(raw_entries, list) else []
        entries_are_objects = all(isinstance(entry, dict) for entry in entries)
        unresolved = [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("status") != "RESOLVED"
        ]
        ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
        declared_count = conflicts.get("unresolved_conflict_count")
        conflict_ok = (
            isinstance(raw_entries, list)
            and entries_are_objects
            and len(ids) == len(set(ids))
            and not unresolved
            and declared_count == 0
            and conflicts.get("status") == "NO_CONFLICTS_IN_EVALUATED_SCOPE"
            and conflicts.get("canonical_facts_sha256") == canonical_hash
            and conflicts.get("product_version") == VERSION
        )
        _add(
            checks,
            "CONFLICT-NONE-UNRESOLVED",
            conflict_ok,
            {
                "entries": len(entries) if isinstance(entries, list) else None,
                "unresolved": len(unresolved),
                "declared": declared_count,
                "status": conflicts.get("status"),
            },
        )

        source_errors: List[Dict[str, Any]] = []
        raw_sources = conflicts.get("evaluated_sources", [])
        sources = raw_sources if isinstance(raw_sources, list) else []
        if not isinstance(raw_sources, list):
            source_errors.append({"reason": "evaluated_sources is not an array"})
        for source in sources:
            if not isinstance(source, dict):
                source_errors.append({"reason": "evaluated source is not an object"})
                continue
            expected = source.get("sha256")
            if expected is None:
                continue
            if source.get("id") == "INPUT-TASKPACK-ARCHIVE" and expected != PINNED_TASKPACK_ARCHIVE_SHA256:
                source_errors.append({"id": source.get("id"), "reason": "archive hash changed"})
            if not source.get("available_in_project"):
                continue
            artifact = root / source["artifact"]
            if not artifact.is_file():
                source_errors.append({"id": source.get("id"), "reason": "artifact missing"})
                continue
            actual = sha256_file(artifact)
            if actual != expected:
                source_errors.append(
                    {"id": source.get("id"), "expected": expected, "actual": actual}
                )
        _add(checks, "CONFLICT-SOURCE-HASHES", not source_errors, source_errors or "all match")
        _add(
            checks,
            "CONFLICT-SCOPE-DISCLOSED",
            bool(conflicts.get("unevaluated_scope")),
            conflicts.get("unevaluated_scope", []),
        )
    else:
        _add(checks, "CONFLICT-NONE-UNRESOLVED", False, "conflict report unavailable")

    _cross_source_checks(root, canonical, checks)
    for check_id, relative, expected in [
        ("SOURCE-PINNED-GOAL", Path("PURSUE_GOAL_PROMPT.txt"), PINNED_GOAL_SHA256),
        ("SOURCE-PINNED-ROADMAP", Path("machine/evidence/roadmap_stage_phase.md"), PINNED_ROADMAP_SHA256),
    ]:
        try:
            actual = sha256_file(root / relative)
            _add(checks, check_id, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    if require_external_reports:
        try:
            junit = _junit_summary(root / JUNIT_PATH)
            junit_ok = junit["tests"] >= 10 and junit["failures"] == 0 and junit["errors"] == 0
            _add(checks, "TEST-JUNIT-PASS", junit_ok, junit)
            hashes[JUNIT_PATH.as_posix()] = sha256_file(root / JUNIT_PATH)
        except Exception as exc:
            _add(checks, "TEST-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))

        pack_report = _safe_load(root / PACK_REPORT_PATH, checks, "PACK-REPORT-PARSE")
        pack_ok = isinstance(pack_report, dict) and pack_report.get("status") == "PASS"
        _add(
            checks,
            "PACK-VALIDATION-PASS",
            pack_ok,
            pack_report.get("status") if isinstance(pack_report, dict) else "unavailable",
        )
        if (root / PACK_REPORT_PATH).is_file():
            hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)

    return _build_result(checks, hashes)


def _code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    source = root / CANONICAL_PATH
    expected_hash = sha256_file(source)
    with tempfile.TemporaryDirectory(prefix="abd-s00-p01-rollback-") as directory:
        directory_path = Path(directory)
        signed = directory_path / "signed.json"
        active = directory_path / "active.json"
        shutil.copyfile(str(source), str(signed))
        shutil.copyfile(str(signed), str(active))
        active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
        corrupted_hash = sha256_file(active)
        shutil.copyfile(str(signed), str(active))
        restored_hash = sha256_file(active)
    status = "PASS" if corrupted_hash != expected_hash and restored_hash == expected_hash else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_SNAPSHOT_RESTORE",
        "status": status,
        "signed_sha256": expected_hash,
        "corrupted_sha256": corrupted_hash,
        "restored_sha256": restored_hash,
        "production_state_changed": False,
        "note": "No prior deployed ABD artifact exists; this deterministically proves restore from the frozen signed bytes without touching production.",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        CANONICAL_PATH,
        CONFLICT_PATH,
        HASH_LOCK_PATH,
        Path("VERSION"),
        Path("PURSUE_GOAL_PROMPT.txt"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/evidence/roadmap_stage_phase.md"),
    ]
    hashes: Dict[str, str] = {}
    for path in paths:
        candidate = root / path
        hashes[path.as_posix()] = sha256_file(candidate) if candidate.is_file() else "MISSING"
    return hashes


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S00-P01-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
        }
    if rollback["status"] != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["next"] = "S00/P02_BLOCKED"

    rollback_bytes = _json_bytes(rollback)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "task_ids": ["T-S00-P01-01", "T-S00-P01-02", "T-S00-P01-03"],
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "pass_gate": "全部事实唯一、无冲突、版本为0.0.0.1。",
        "validation": result,
        "hashes": {
            "inputs": _input_hashes(root),
            "parameters": _input_hashes(root).get("machine/facts/parameters.json", "MISSING"),
            "code": _code_hash(root),
            "model": None,
            "model_not_applicable_reason": "S00/P01 freezes facts and has no model artifact.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
                "result_source": PACK_REPORT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q tests/S00/P01_test.py --junitxml=machine/evidence/S00/P01/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S00-P01 --evidence machine/evidence",
                "exit_code": 0 if result["status"] == "PASS" else 1,
            },
        ],
        "rollback": {
            "artifact": "machine/evidence/EVD-S00-P01_rollback.json",
            "status": rollback["status"],
        },
        "non_guarantee": "30% monthly compounding remains an unverified falsifiable target, never a random-return guarantee.",
        "explicit_unknowns": [
            "External unprovided historical drafts were not evaluated.",
            "Current provider, regulatory, account, OVH, Cloudflare, Gmail and TAB runtime state was not verified in S00/P01.",
            "No production deployment, real order or actual-return evidence exists in this phase."
        ],
        "release_status": "NOT_READY",
        "stage_status": "S00_IN_PROGRESS",
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
    path = root / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    matches = 0
    for row in rows:
        if row.get("id") == "INDEX-AC-S00-P01":
            matches += 1
            row["status"] = status
            row["actual_artifact"] = "machine/evidence/EVD-S00-P01.json"
            row["artifact_sha256"] = evidence_hash
            row["verified_at"] = FIXED_CLOCK
            row["next"] = "S00/P02_READY_NOT_STARTED" if status == "PASS" else "S00/P02_BLOCKED"
    if matches != 1:
        raise ValueError("expected exactly one INDEX-AC-S00-P01 row, found %d" % matches)
    data = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
    )
    _atomic_write(path, data)


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence directory must be inside the ABD project root") from exc

    evidence, rollback = build_evidence(root, require_external_reports=True)
    rollback_path = evidence_dir / "EVD-S00-P01_rollback.json"
    evidence_path = evidence_dir / "EVD-S00-P01.json"
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
