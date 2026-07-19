from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from urllib.parse import urlparse

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S00-P03"
REQUIREMENT_ID = "REQ-S00-P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

COSTS_PATH = Path("machine/facts/costs.json")
LOCK_PATH = Path("machine/facts/dependency_budget.lock")
FIXTURE_PATH = Path("machine/tests/fixtures/S00_P03.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S00-P02.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
JUNIT_PATH = Path("machine/evidence/S00/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S00/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

PINNED_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    P02_EVIDENCE_PATH.as_posix(): "6bd925ae31a61bd10759faf36e29a241822884163a2add4a84fad263ea5b558b",
    COSTS_PATH.as_posix(): "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    LOCK_PATH.as_posix(): "4904a86b7561456edef9f5e4c9da3e8fa5562a83892f224e58ea3a7511e66b06",
    FIXTURE_PATH.as_posix(): "c9b280e5c1658de78f7d2f0c2fff1166cff3ef265279b16e2526b76b21242601",
    "pyproject.toml": "ed30542952d445085e1f7724872bda1b697898f90576bf9bd65fd3191719bb72",
    "uv.lock": "982a3044aabd62584d76cddcbd9dfcfe761482a5e60248ad5e299c18fd2ad9cf",
}

REQUIRED_COST_SOURCE_HOSTS = {
    "Cloudflare": {"www.cloudflare.com", "developers.cloudflare.com"},
    "GitHub": {"docs.github.com"},
    "Google": {"developers.google.com"},
    "OVHcloud": {"www.ovhcloud.com"},
    "Python Package Index": {"pypi.org"},
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _portable(path: Path) -> str:
    rendered = path.as_posix()
    for marker in ("/machine/", "/abd_acceptance/", "/tests/"):
        if marker in rendered:
            return marker.strip("/").split("/")[0] + "/" + rendered.split(marker, 1)[1]
    return path.name


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


def _safe_toml(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


def _single_source_check(root: Path, expected: Path, checks: List[Dict[str, Any]]) -> None:
    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob(expected.name)
        if not {".git", ".venv", "__pycache__"}.intersection(path.parts)
    )
    _add(checks, "SOURCE-SINGLE-%s" % expected.stem.upper(), candidates == [expected.as_posix()], candidates)


def _load_evidence_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / "machine/evidence/evidence_index.jsonl")
        .read_text(encoding="utf-8-sig")
        .splitlines()
        if line
    ]


def _check_p02_prerequisite(root: Path, checks: List[Dict[str, Any]]) -> None:
    p02 = _safe_load(root / P02_EVIDENCE_PATH, checks, "PREREQ-P02-EVIDENCE-PARSE")
    if not isinstance(p02, dict):
        _add(checks, "PREREQ-P02-PASS", False, "P02 evidence unavailable")
        return
    try:
        rows = _load_evidence_index(root)
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S00-P02"]
        actual_hash = sha256_file(root / P02_EVIDENCE_PATH)
        index_ok = (
            len(matching) == 1
            and matching[0].get("status") == "PASS"
            and matching[0].get("artifact_sha256") == actual_hash
        )
    except Exception as exc:
        _add(checks, "PREREQ-P02-PASS", False, "evidence index: %s: %s" % (type(exc).__name__, exc))
        return
    p02_ok = (
        p02.get("status") == "PASS"
        and p02.get("contract_id") == "AC-S00-P02"
        and p02.get("next") == "S00/P03_READY_NOT_STARTED"
        and actual_hash == PINNED_HASHES[P02_EVIDENCE_PATH.as_posix()]
        and index_ok
    )
    _add(
        checks,
        "PREREQ-P02-PASS",
        p02_ok,
        {
            "status": p02.get("status"),
            "next": p02.get("next"),
            "artifact_hash_matches": actual_hash == PINNED_HASHES[P02_EVIDENCE_PATH.as_posix()],
            "index_hash_matches": index_ok,
        },
    )


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in PINNED_HASHES.items():
        path = root / relative
        try:
            actual = sha256_file(path)
        except Exception as exc:
            _add(checks, "HASH-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "HASH-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _decimal_is(value: Any, expected: str) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+\.\d{2,4}", value):
        return False
    try:
        return Decimal(value) == Decimal(expected)
    except InvalidOperation:
        return False


def _check_costs(costs: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        budget = costs["incremental_cash_budget"]
        gate = costs["incremental_cash_gate"]
        budget_ok = (
            all(budget.get(position) == "0.00" for position in ("low", "likely", "high"))
            and gate.get("maximum_aud") == "0.00"
            and gate.get("comparison") == "ACTUAL_INCREMENTAL_CASH_COST_MUST_EQUAL_ZERO"
            and gate.get("positive_boundary_aud") == "0.0001"
            and gate.get("negative_boundary_aud") == "-0.0001"
            and gate.get("automatic_purchase_allowed") is False
            and gate.get("automatic_paid_upgrade_allowed") is False
            and gate.get("automatic_overage_billing_allowed") is False
            and gate.get("cash_commitments_created_in_s00_p03") == []
            and gate.get("external_billing_accounts_inspected_in_s00_p03") is False
        )
        _add(checks, "COST-INCREMENTAL-CASH-EXACT-ZERO", budget_ok, {"budget": budget, "gate": gate})
    except (KeyError, TypeError) as exc:
        _add(checks, "COST-INCREMENTAL-CASH-EXACT-ZERO", False, "%s: %s" % (type(exc).__name__, exc))

    semantics = costs.get("cost_semantics", {})
    semantics_ok = (
        isinstance(semantics, dict)
        and semantics.get("total_system_cost_is_zero") is False
        and "新增现金" in str(semantics.get("zero_budget_claim_scope", ""))
        and "现有资源" in str(semantics.get("zero_budget_claim_scope", ""))
        and "A$300" in str(semantics.get("bankroll_principal", ""))
        and "经济价值" in str(semantics.get("opportunity_cost", ""))
    )
    _add(checks, "COST-SEMANTICS-NO-ZERO-TOTAL-CLAIM", semantics_ok, semantics)

    resources = costs.get("resource_costs")
    if not isinstance(resources, list) or not all(isinstance(item, dict) for item in resources):
        _add(checks, "COST-RESOURCES-STRUCTURE", False, "resource_costs must be an array of objects")
        return
    ids = [item.get("id") for item in resources]
    expected_ids = fixture.get("required_resource_ids", [])
    structure_ok = len(ids) == len(set(ids)) and sorted(ids) == sorted(expected_ids)
    _add(checks, "COST-RESOURCES-STRUCTURE", structure_ok, {"ids": ids, "expected": expected_ids})

    required_failure_actions = set(fixture.get("required_provider_failure_actions", []))
    resource_errors: List[Dict[str, Any]] = []
    for item in resources:
        if not _decimal_is(item.get("incremental_cash_cost_aud"), "0.00"):
            resource_errors.append({"id": item.get("id"), "reason": "nonzero_or_invalid_incremental_cash"})
        if not str(item.get("incremental_cash_cost_status", "")).startswith("FROZEN_ZERO_"):
            resource_errors.append({"id": item.get("id"), "reason": "unknown_incremental_cost_status"})
        if item.get("purchase_required") is not False:
            resource_errors.append({"id": item.get("id"), "reason": "purchase_required"})
        if item.get("paid_tier_allowed") is not False:
            resource_errors.append({"id": item.get("id"), "reason": "paid_tier_allowed"})
        if item.get("automatic_overage_allowed") is not False:
            resource_errors.append({"id": item.get("id"), "reason": "overage_allowed"})
        if item.get("on_unavailable_or_limit") not in required_failure_actions:
            resource_errors.append({"id": item.get("id"), "reason": "unsafe_or_unknown_failure_action"})
        if item.get("id") != "RES-OSS-PINNED" and str(item.get("capability_status", "")).startswith("VERIFIED"):
            resource_errors.append({"id": item.get("id"), "reason": "external_capability_claimed_verified"})
    _add(checks, "COST-RESOURCES-ZERO-AND-FAIL-CLOSED", not resource_errors, resource_errors or "all resources safe")

    expected_critical = sorted(fixture.get("critical_resource_ids", []))
    actual_critical = sorted(item["id"] for item in resources if item.get("critical_path") is True)
    by_id = {item["id"]: item for item in resources if item.get("id")}
    critical_ok = (
        actual_critical == expected_critical
        and by_id.get("RES-GMAIL-EXISTING-OPTIONAL", {}).get("critical_path") is False
        and by_id.get("RES-GMAIL-EXISTING-OPTIONAL", {}).get("on_unavailable_or_limit")
        == "DISABLE_GMAIL_MODULE_CONTINUE_CORE"
        and by_id.get("RES-OVH-EXISTING-VPS1", {}).get("existing_recurring_cash_cost_aud")
        == "UNKNOWN_ACCOUNT_SPECIFIC"
        and by_id.get("RES-OVH-EXISTING-VPS1", {}).get("public_reference_is_account_invoice") is False
    )
    _add(
        checks,
        "COST-CRITICAL-PATH-AND-EXISTING-COST-DISCLOSED",
        critical_ok,
        {"critical": actual_critical, "expected": expected_critical},
    )

    admission = costs.get("future_source_admission_policy", {})
    admission_ok = (
        admission.get("observable_market_coverage_goal_preserved") is True
        and admission.get("paid_odds_api_required") is False
        and admission.get("free_endpoint_single_point_allowed") is False
        and admission.get("paid_source_action") == "BLOCK_WITH_INCREMENTAL_CASH_BUDGET_EXCEEDED"
        and admission.get("unknown_cost_or_terms_action") == "DO_NOT_ADMIT_SOURCE_MARK_COVERAGE_GAP"
    )
    _add(checks, "COST-FUTURE-SOURCE-ADMISSION", admission_ok, admission)

    effort = costs.get("development_effort_hours", {})
    opportunity_errors = []
    for row in costs.get("opportunity_cost_sensitivity", []):
        if not isinstance(row, dict):
            opportunity_errors.append("non-object")
            continue
        for position in ("low", "likely", "high"):
            if row.get(position) != row.get("hourly_value", 0) * effort.get(position, -1):
                opportunity_errors.append({"hourly": row.get("hourly_value"), "position": position})
    _add(checks, "COST-OPPORTUNITY-COST-DISCLOSED", not opportunity_errors, opportunity_errors or "all arithmetic matches")

    benefit = costs.get("benefit_model", {})
    benefit_ok = (
        benefit.get("target_curve") == "300*1.3^n"
        and benefit.get("return_guaranteed") is False
        and "不是收益承诺" in str(benefit.get("warning", ""))
    )
    _add(checks, "COST-RETURN-NOT-GUARANTEED", benefit_ok, benefit)

    sources = costs.get("official_cost_sources")
    source_errors: List[Any] = []
    source_ids = set()
    if not isinstance(sources, list):
        source_errors.append("official_cost_sources must be an array")
        sources = []
    for source in sources:
        if not isinstance(source, dict):
            source_errors.append("source is not an object")
            continue
        source_id = source.get("id")
        if source_id in source_ids:
            source_errors.append({"id": source_id, "reason": "duplicate"})
        source_ids.add(source_id)
        publisher = source.get("publisher")
        host = urlparse(str(source.get("url", ""))).hostname
        if host not in REQUIRED_COST_SOURCE_HOSTS.get(publisher, set()):
            source_errors.append({"id": source_id, "reason": "non_first_party_host", "host": host})
        if source.get("retrieved_at") != "2026-07-19" or source.get("time_varying") is not True:
            source_errors.append({"id": source_id, "reason": "freshness_metadata"})
        if not source.get("verified_claim"):
            source_errors.append({"id": source_id, "reason": "missing_claim"})
    allowed_non_source = {"BASELINE-OWNER-DECLARATION"}
    referenced = {
        source_id
        for item in resources
        for source_id in item.get("source_ids", [])
        if source_id not in allowed_non_source
    }
    missing_references = sorted(referenced - source_ids)
    if missing_references:
        source_errors.append({"missing_references": missing_references})
    freshness = costs.get("freshness_policy", {})
    if (
        freshness.get("official_terms_are_snapshot_not_permanent_fact") is not True
        or "ANY_EXTERNAL_DEPLOYMENT" not in freshness.get("reverify_before", [])
        or freshness.get("on_stale_or_changed") != "FAIL_CLOSED_OR_DEGRADE_WITHOUT_PAID_SUBSTITUTION"
    ):
        source_errors.append("unsafe freshness policy")
    _add(checks, "COST-FIRST-PARTY-SOURCES-AND-FRESHNESS", not source_errors, source_errors or sorted(source_ids))


def _check_lock(
    root: Path,
    lock: Mapping[str, Any],
    costs: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    policy = lock.get("budget_policy", {})
    policy_ok = (
        policy.get("maximum_incremental_cash_cost_aud") == "0.00"
        and policy.get("actual_incremental_cash_cost_aud") == "0.00"
        and policy.get("paid_dependency_allowed") is False
        and policy.get("unknown_cost_dependency_allowed") is False
        and policy.get("automatic_purchase_allowed") is False
        and policy.get("automatic_paid_upgrade_allowed") is False
        and policy.get("automatic_overage_allowed") is False
        and policy.get("existing_resource_total_cost_claimed_zero") is False
        and policy.get("paid_data_api_in_critical_path") is False
    )
    _add(checks, "LOCK-BUDGET-POLICY", policy_ok, policy)

    authority_errors = []
    for authority in lock.get("authority", {}).values():
        if not isinstance(authority, dict):
            authority_errors.append("authority is not an object")
            continue
        path = root / str(authority.get("path", ""))
        if not path.is_file():
            authority_errors.append({"path": authority.get("path"), "reason": "missing"})
            continue
        actual = sha256_file(path)
        if actual != authority.get("sha256"):
            authority_errors.append({"path": authority.get("path"), "expected": authority.get("sha256"), "actual": actual})
    _add(checks, "LOCK-AUTHORITY-HASHES", not authority_errors, authority_errors or "all match")

    cost_resources = {
        item.get("id"): item
        for item in costs.get("resource_costs", [])
        if isinstance(item, dict) and item.get("id")
    }
    providers = lock.get("providers")
    provider_errors: List[Any] = []
    if not isinstance(providers, list):
        provider_errors.append("providers must be an array")
        providers = []
    provider_ids = [item.get("resource_id") for item in providers if isinstance(item, dict)]
    if len(provider_ids) != len(set(provider_ids)) or sorted(provider_ids) != sorted(fixture.get("required_resource_ids", [])):
        provider_errors.append({"provider_ids": provider_ids})
    for provider in providers:
        if not isinstance(provider, dict):
            provider_errors.append("provider is not an object")
            continue
        resource = cost_resources.get(provider.get("resource_id"), {})
        aligned_fields = (
            "critical_path",
            "incremental_cash_cost_aud",
            "incremental_cash_cost_status",
            "paid_tier_allowed",
            "automatic_overage_allowed",
        )
        for field in aligned_fields:
            if provider.get(field) != resource.get(field):
                provider_errors.append({"id": provider.get("resource_id"), "field": field})
        if provider.get("incremental_cash_cost_aud") != "0.00":
            provider_errors.append({"id": provider.get("resource_id"), "reason": "nonzero_cash"})
        if provider.get("paid_tier_allowed") is not False or provider.get("automatic_overage_allowed") is not False:
            provider_errors.append({"id": provider.get("resource_id"), "reason": "paid_or_overage"})
        if provider.get("on_failure") != resource.get("on_unavailable_or_limit"):
            provider_errors.append({"id": provider.get("resource_id"), "reason": "failure_action_drift"})
    _add(checks, "LOCK-PROVIDERS-ALIGN-COSTS", not provider_errors, provider_errors or "all align")

    critical = lock.get("critical_path")
    critical_errors: List[Any] = []
    if not isinstance(critical, list):
        critical_errors.append("critical_path must be an array")
        critical = []
    ordered = sorted(critical, key=lambda item: item.get("order", 0) if isinstance(item, dict) else 0)
    resource_ids = [item.get("resource_id") for item in ordered if isinstance(item, dict)]
    if resource_ids != [
        "RES-OSS-PINNED",
        "RES-OVH-EXISTING-VPS1",
        "RES-CLOUDFLARE-ZERO-TRUST-FREE",
        "RES-GITHUB-EXISTING",
    ]:
        critical_errors.append({"ordered_resources": resource_ids})
    for item in ordered:
        if item.get("paid_or_approval_bound_dependency") is not False:
            critical_errors.append({"id": item.get("resource_id"), "reason": "paid_or_approval_bound"})
    _add(checks, "LOCK-CRITICAL-PATH-NO-PAID-INTERFACE", not critical_errors, critical_errors or resource_ids)

    python_env = lock.get("python_environment", {})
    packages = python_env.get("registry_packages")
    package_errors: List[Any] = []
    if not isinstance(packages, list):
        package_errors.append("registry_packages must be an array")
        packages = []
    names = [item.get("name") for item in packages if isinstance(item, dict)]
    approved = set(python_env.get("approved_license_expressions", []))
    if len(names) != len(set(names)) or len(names) != fixture.get("expected_registry_package_count"):
        package_errors.append({"package_names": names})
    for package in packages:
        if not isinstance(package, dict):
            package_errors.append("package is not an object")
            continue
        if package.get("license_spdx") not in approved:
            package_errors.append({"name": package.get("name"), "reason": "unapproved_or_unknown_license"})
        source = str(package.get("source", ""))
        if urlparse(source).hostname != "pypi.org" or not package.get("version"):
            package_errors.append({"name": package.get("name"), "reason": "untrusted_source_or_unpinned"})
        if not str(package.get("scope", "")).startswith("DEV_"):
            package_errors.append({"name": package.get("name"), "reason": "unexpected_scope"})
    _add(checks, "LOCK-OPEN-SOURCE-PACKAGE-ALLOWLIST", not package_errors, package_errors or sorted(names))

    freshness = lock.get("freshness", {})
    future = lock.get("future_dependency_admission", {})
    freshness_ok = (
        freshness.get("official_cost_snapshot_date") == "2026-07-19"
        and "EXTERNAL_DEPLOYMENT" in freshness.get("reverify_before", [])
        and freshness.get("stale_snapshot_action") == "FAIL_CLOSED_OR_DEGRADE_WITHOUT_PAID_SUBSTITUTION"
        and future.get("must_update_lock") is True
        and future.get("must_regenerate_scan") is True
        and future.get("must_reverify_current_first_party_cost_and_terms") is True
        and future.get("must_keep_incremental_cash_cost_aud") == "0.00"
        and future.get("paid_or_unknown_dependency_action") == "BLOCK_NOT_AUTO_APPROVE"
    )
    _add(checks, "LOCK-FUTURE-ADMISSION-AND-FRESHNESS", freshness_ok, {"freshness": freshness, "future": future})


def _excluded(path: Path, root: Path, excluded_parts: Sequence[str]) -> bool:
    relative = path.relative_to(root)
    return bool(set(relative.parts).intersection(excluded_parts))


def _discover_manifests(root: Path, patterns: Sequence[str], excluded_parts: Sequence[str]) -> List[str]:
    found = set()
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.is_file() and not _excluded(path, root, excluded_parts):
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


def _glob_files(root: Path, patterns: Sequence[str], excluded_parts: Sequence[str]) -> List[Path]:
    found = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and not _excluded(path, root, excluded_parts):
                found.add(path)
    return sorted(found, key=lambda path: path.relative_to(root).as_posix())


def _audit_imports(
    root: Path,
    paths: Sequence[Path],
    import_mapping: Mapping[str, str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[Dict[str, Any]] = []
    audited: List[str] = []
    allowed_third_party = set(import_mapping)
    allowed_local = {"abd_acceptance", "machine"}
    stdlib = set(sys.stdlib_module_names)
    for path in paths:
        relative = path.relative_to(root).as_posix()
        audited.append(relative)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except Exception as exc:
            errors.append({"path": relative, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".", 1)[0])
        unknown = sorted(roots - stdlib - allowed_local - allowed_third_party)
        if unknown:
            errors.append({"path": relative, "unknown_import_roots": unknown})
    return errors, audited


def _audit_prohibited_literals(
    root: Path,
    paths: Sequence[Path],
    identifiers: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    prohibited_roots = [str(value).lower() for value in identifiers.get("import_roots", [])]
    prohibited_hosts = [str(value).lower() for value in identifiers.get("hostnames", [])]
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except Exception as exc:
            errors.append({"path": relative, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        matches = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value.lower()
            matches.update(host for host in prohibited_hosts if host in value)
            for root_name in prohibited_roots:
                if re.search(r"(?<![a-z0-9_])%s(?![a-z0-9_])" % re.escape(root_name), value):
                    matches.add(root_name)
        if matches:
            errors.append({"path": relative, "prohibited_literals": sorted(matches)})
    return errors


def scan_dependency_budget(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    try:
        lock = strict_json_load(root / LOCK_PATH)
    except Exception as exc:
        _add(checks, "SCAN-LOCK-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return _build_scan_result(checks, [], [], [], [])
    _add(checks, "SCAN-LOCK-PARSE", isinstance(lock, dict), LOCK_PATH.as_posix())
    if not isinstance(lock, dict):
        return _build_scan_result(checks, [], [], [], [])

    scan_policy = lock.get("scan_policy", {})
    excluded_parts = scan_policy.get("excluded_path_parts", [])
    manifests = _discover_manifests(
        root,
        scan_policy.get("dependency_manifest_patterns", []),
        excluded_parts,
    )
    expected_manifests = sorted(scan_policy.get("expected_dependency_manifests", []))
    _add(checks, "SCAN-MANIFEST-SET", manifests == expected_manifests, {"actual": manifests, "expected": expected_manifests})

    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        uv_lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    except Exception as exc:
        _add(checks, "SCAN-TOML-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return _build_scan_result(checks, manifests, [], [], [])
    _add(checks, "SCAN-TOML-PARSE", True, ["pyproject.toml", "uv.lock"])

    python_env = lock.get("python_environment", {})
    runtime_direct = pyproject.get("project", {}).get("dependencies", [])
    dev_direct = pyproject.get("dependency-groups", {}).get("dev", [])
    direct_ok = (
        runtime_direct == python_env.get("runtime_direct_dependencies")
        and dev_direct == python_env.get("dev_direct_dependencies")
    )
    _add(
        checks,
        "SCAN-DIRECT-DEPENDENCIES",
        direct_ok,
        {"runtime": runtime_direct, "dev": dev_direct},
    )

    uv_packages = uv_lock.get("package", [])
    actual_registry: Dict[str, str] = {}
    local_packages: Dict[str, str] = {}
    source_errors: List[Any] = []
    for package in uv_packages:
        if not isinstance(package, dict):
            source_errors.append("uv package is not an object")
            continue
        name = package.get("name")
        version = package.get("version")
        source = package.get("source", {})
        if source.get("virtual") == ".":
            local_packages[name] = version
        elif source.get("registry") == "https://pypi.org/simple":
            actual_registry[name] = version
        else:
            source_errors.append({"name": name, "source": source})

    allowed_registry = {
        package.get("name"): package.get("version")
        for package in python_env.get("registry_packages", [])
        if isinstance(package, dict)
    }
    allowed_local = {
        package.get("name"): package.get("version")
        for package in python_env.get("local_packages", [])
        if isinstance(package, dict)
    }
    package_ok = not source_errors and actual_registry == allowed_registry and local_packages == allowed_local
    _add(
        checks,
        "SCAN-LOCKED-PACKAGE-ALLOWLIST",
        package_ok,
        {
            "registry_count": len(actual_registry),
            "unclassified_or_source_errors": source_errors,
            "unexpected": sorted(set(actual_registry) - set(allowed_registry)),
            "missing": sorted(set(allowed_registry) - set(actual_registry)),
            "version_drift": sorted(
                name for name in set(actual_registry).intersection(allowed_registry) if actual_registry[name] != allowed_registry[name]
            ),
        },
    )

    approved = set(python_env.get("approved_license_expressions", []))
    license_errors = [
        package.get("name")
        for package in python_env.get("registry_packages", [])
        if not isinstance(package, dict)
        or not package.get("license_spdx")
        or package.get("license_spdx") not in approved
    ]
    _add(checks, "SCAN-LICENSES-CLASSIFIED", not license_errors, license_errors or sorted(approved))

    import_paths = _glob_files(root, scan_policy.get("import_audit_globs", []), excluded_parts)
    import_errors, audited_python_files = _audit_imports(
        root,
        import_paths,
        python_env.get("import_to_distribution", {}),
    )
    _add(checks, "SCAN-IMPORTS-CLASSIFIED", not import_errors, import_errors or {"files": len(audited_python_files)})

    literal_paths = _glob_files(root, scan_policy.get("production_literal_audit_globs", []), excluded_parts)
    literal_errors = _audit_prohibited_literals(
        root,
        literal_paths,
        lock.get("prohibited_runtime_identifiers", {}),
    )
    _add(checks, "SCAN-NO-PROHIBITED-RUNTIME-IDENTIFIERS", not literal_errors, literal_errors or {"files": len(literal_paths)})

    providers = lock.get("providers", [])
    paid_or_unknown = [
        provider.get("resource_id")
        for provider in providers
        if not isinstance(provider, dict)
        or provider.get("incremental_cash_cost_aud") != "0.00"
        or provider.get("paid_tier_allowed") is not False
        or provider.get("automatic_overage_allowed") is not False
        or not str(provider.get("incremental_cash_cost_status", "")).startswith("FROZEN_ZERO_")
    ]
    critical_paid_or_approval = [
        item.get("resource_id")
        for item in lock.get("critical_path", [])
        if not isinstance(item, dict) or item.get("paid_or_approval_bound_dependency") is not False
    ]
    _add(checks, "SCAN-PROVIDER-COSTS-EXACT-ZERO", not paid_or_unknown, paid_or_unknown or "all providers frozen zero")
    _add(
        checks,
        "SCAN-CRITICAL-PATH-NO-PAID-OR-APPROVAL-BOUND-INTERFACE",
        not critical_paid_or_approval,
        critical_paid_or_approval or "none",
    )

    return _build_scan_result(
        checks,
        manifests,
        sorted(actual_registry.items()),
        sorted((provider.get("resource_id"), provider.get("critical_path")) for provider in providers if isinstance(provider, dict)),
        audited_python_files,
    )


def _build_scan_result(
    checks: List[Dict[str, Any]],
    manifests: Sequence[str],
    packages: Sequence[Tuple[str, str]],
    providers: Sequence[Tuple[str, Any]],
    audited_python_files: Sequence[str],
) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "scan_id": "ABD-S00-P03-PAID-DEPENDENCY-SCAN",
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS" if not failed else "FAIL",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
            "dependency_manifests": len(manifests),
            "runtime_direct_dependencies": 0,
            "locked_registry_packages": len(packages),
            "providers": len(providers),
            "paid_or_unknown_dependencies": 0 if not failed else None,
        },
        "checks": checks,
        "manifests": list(manifests),
        "packages": [{"name": name, "version": version} for name, version in packages],
        "providers": [{"resource_id": resource_id, "critical_path": critical} for resource_id, critical in providers],
        "audited_python_files": list(audited_python_files),
        "external_network_access_performed": False,
        "external_account_or_billing_access_performed": False,
    }


def render_scan_report(scan: Mapping[str, Any]) -> str:
    summary = scan.get("summary", {})
    lines = [
        "ABD S00/P03 PAID DEPENDENCY SCAN",
        "STATUS: %s" % scan.get("status", "FAIL"),
        "FIXED_CLOCK: %s" % scan.get("fixed_clock", FIXED_CLOCK),
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "DEPENDENCY_MANIFESTS: %s" % summary.get("dependency_manifests", 0),
        "RUNTIME_DIRECT_DEPENDENCIES: %s" % summary.get("runtime_direct_dependencies", 0),
        "LOCKED_REGISTRY_PACKAGES: %s" % summary.get("locked_registry_packages", 0),
        "PAID_OR_UNKNOWN_DEPENDENCIES: %s" % (0 if scan.get("status") == "PASS" else "UNKNOWN_OR_NONZERO"),
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        "",
        "MANIFESTS",
    ]
    lines.extend("- %s" % path for path in scan.get("manifests", []))
    lines.extend(["", "PACKAGES"])
    lines.extend("- %s==%s" % (package["name"], package["version"]) for package in scan.get("packages", []))
    lines.extend(["", "PROVIDERS"])
    lines.extend(
        "- %s critical_path=%s incremental_cash_aud=0.00"
        % (provider["resource_id"], str(bool(provider["critical_path"])).lower())
        for provider in scan.get("providers", [])
    )
    lines.extend(["", "CHECKS"])
    lines.extend(
        "- %s %s" % ("PASS" if check.get("passed") else "FAIL", check.get("id"))
        for check in scan.get("checks", [])
    )
    lines.extend(
        [
            "",
            "BOUNDARY",
            "- Existing resource and opportunity costs are disclosed separately; this report proves only incremental cash cost A$0 for declared dependencies.",
            "- External capability, account plan, quota headroom, deployment, market coverage and returns are not verified by this scan.",
            "- Any new, paid, unknown-cost, unclassified or approval-bound critical dependency fails closed.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_scan_report(root: Path, output: Path) -> Dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError("scan output must be inside the ABD project root") from exc
    scan = scan_dependency_budget(root)
    report = render_scan_report(scan)
    _atomic_write(output, report.encode("utf-8"))
    return {
        "status": scan["status"],
        "output": output.relative_to(root).as_posix(),
        "sha256": sha256_file(output),
        "failed_check_ids": scan["summary"]["failed_check_ids"],
    }


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
    scan: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    for check_id, path, minimum in [
        ("TEST-P03-JUNIT-PASS", JUNIT_PATH, 20),
        ("TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, 50),
    ]:
        try:
            summary = _junit_summary(root / path)
            normalized = _junit_is_normalized(root / path)
            ok = (
                summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and normalized
            )
            _add(checks, check_id, ok, {**summary, "normalized": normalized, "minimum": minimum})
            hashes[path.as_posix()] = sha256_file(root / path)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    pack = _safe_load(root / PACK_REPORT_PATH, checks, "PACK-REPORT-PARSE")
    pack_ok = isinstance(pack, dict) and pack.get("status") == "PASS"
    _add(checks, "PACK-VALIDATION-PASS", pack_ok, pack.get("status") if isinstance(pack, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)

    expected_report = render_scan_report(scan)
    try:
        actual_report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        report_ok = actual_report == expected_report and scan.get("status") == "PASS"
        _add(
            checks,
            "SCAN-REPORT-DETERMINISTIC-PASS",
            report_ok,
            {
                "status": scan.get("status"),
                "exact_match": actual_report == expected_report,
                "path": SCAN_REPORT_PATH.as_posix(),
            },
        )
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "SCAN-REPORT-DETERMINISTIC-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _check_no_sensitive_or_local_data(artifacts: Sequence[Mapping[str, Any]], checks: List[Dict[str, Any]]) -> None:
    rendered = json.dumps(list(artifacts), ensure_ascii=False, sort_keys=True)
    patterns = {
        "absolute_user_path": r"/" + r"Users/",
        "private_key": r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        "github_token": r"ghp_[0-9A-Za-z]{20,}",
        "google_api_key": r"AIza[0-9A-Za-z_-]{20,}",
    }
    matches = [name for name, pattern in patterns.items() if re.search(pattern, rendered)]
    _add(checks, "SECURITY-NO-SECRET-OR-LOCAL-PATH", not matches, matches or "none")


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
        "decision": "ZERO_BUDGET_DEPENDENCIES_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "release_status": "NOT_READY",
        "stage_status": "S00_IN_PROGRESS",
        "next": "S00/P04_READY_NOT_STARTED" if status == "PASS" else "S00/P04_BLOCKED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}

    _check_p02_prerequisite(root, checks)
    for expected in (COSTS_PATH, LOCK_PATH):
        _single_source_check(root, expected, checks)

    costs = _safe_load(root / COSTS_PATH, checks, "INPUT-COSTS-PARSE")
    lock = _safe_load(root / LOCK_PATH, checks, "INPUT-DEPENDENCY-LOCK-PARSE")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "INPUT-FIXTURE-PARSE")
    _safe_toml(root / "pyproject.toml", checks, "INPUT-PYPROJECT-PARSE")
    _safe_toml(root / "uv.lock", checks, "INPUT-UV-LOCK-PARSE")
    _check_pinned_hashes(root, checks, hashes)

    if not isinstance(costs, dict) or not isinstance(lock, dict) or not isinstance(fixture, dict):
        _add(checks, "INPUTS-ALL-OBJECTS", False, "one or more required JSON inputs are unavailable")
        return _build_result(checks, hashes)
    _add(checks, "INPUTS-ALL-OBJECTS", True, "all parsed")

    version_ok = (
        costs.get("product_version") == VERSION
        and costs.get("phase") == "S00/P03"
        and lock.get("product_version") == VERSION
        and lock.get("phase") == "S00/P03"
        and fixture.get("contract_id") == CONTRACT_ID
    )
    _add(checks, "BUDGET-VERSION-AND-PHASE", version_ok, {"costs": costs.get("product_version"), "lock": lock.get("product_version")})

    _check_costs(costs, fixture, checks)
    _check_lock(root, lock, costs, fixture, checks)

    scan = scan_dependency_budget(root)
    for scan_check in scan.get("checks", []):
        _add(
            checks,
            scan_check.get("id", "SCAN-UNKNOWN"),
            bool(scan_check.get("passed")),
            scan_check.get("detail"),
        )
    _add(
        checks,
        "DEPENDENCY-SCAN-PASS",
        scan.get("status") == "PASS",
        scan.get("summary", {}),
    )

    _check_no_sensitive_or_local_data([costs, lock, scan], checks)
    if require_external_reports:
        _check_runtime_reports(root, scan, checks, hashes)
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
    artifacts = (COSTS_PATH, LOCK_PATH, SCAN_REPORT_PATH)
    results: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s00-p03-rollback-") as directory:
        directory_path = Path(directory)
        for index, relative in enumerate(artifacts):
            source = root / relative
            expected_hash = sha256_file(source)
            signed = directory_path / ("signed-%d" % index)
            active = directory_path / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted_hash = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored_hash = sha256_file(active)
            item_status = "PASS" if corrupted_hash != expected_hash and restored_hash == expected_hash else "FAIL"
            results[relative.as_posix()] = {
                "status": item_status,
                "signed_sha256": expected_hash,
                "corrupted_sha256": corrupted_hash,
                "restored_sha256": restored_hash,
            }
    status = "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_BUDGET_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        Path("machine/facts/canonical_facts.json"),
        P02_EVIDENCE_PATH,
        COSTS_PATH,
        LOCK_PATH,
        SCAN_REPORT_PATH,
        FIXTURE_PATH,
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
    ]
    return {
        path.as_posix(): sha256_file(root / path) if (root / path).is_file() else "MISSING"
        for path in paths
    }


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S00-P03-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["next"] = "S00/P04_BLOCKED"

    rollback_bytes = _json_bytes(rollback)
    input_hashes = _input_hashes(root)
    scan = scan_dependency_budget(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "task_ids": ["T-S00-P03-01", "T-S00-P03-02", "T-S00-P03-03"],
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "pass_gate": "新增现金支出为A$0；付费接口不在关键路径。",
        "validation": result,
        "dependency_scan": {
            "artifact": SCAN_REPORT_PATH.as_posix(),
            "status": scan.get("status"),
            "summary": scan.get("summary"),
        },
        "cost_boundary": {
            "incremental_cash_budget_aud": "0.00",
            "existing_resource_total_cost_claimed_zero": False,
            "opportunity_cost_disclosed": True,
            "bankroll_is_operating_budget": False,
            "external_billing_accounts_inspected": False,
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes.get("machine/facts/parameters.json", "MISSING"),
            "code": _code_hash(root),
            "model": None,
            "model_not_applicable_reason": "S00/P03 freezes costs and dependencies and has no model artifact.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
                "result_source": SCAN_REPORT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
                "result_source": PACK_REPORT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q tests/S00/P03_test.py --junitxml=machine/evidence/S00/P03/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P03/pytest.xml",
                "result_source": JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S00/P03/full_regression.xml",
                "result_source": FULL_JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/P03/full_regression.xml",
                "result_source": FULL_JUNIT_PATH.as_posix(),
            },
            {
                "command": "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S00-P03 --evidence machine/evidence",
                "exit_code": 0 if result["status"] == "PASS" else 1,
            },
        ],
        "rollback": {
            "artifact": "machine/evidence/EVD-S00-P03_rollback.json",
            "status": rollback.get("status"),
        },
        "non_guarantee": "A$300*1.3^n remains an unverified falsifiable target, never a random-return guarantee.",
        "explicit_unknowns": [
            "Existing OVH and account-specific recurring costs were not inspected and are not claimed to be zero.",
            "OVH, Cloudflare, GitHub and Gmail credentials, quotas, billing settings and runtime capability remain unverified.",
            "Current official free-tier facts are a 2026-07-19 snapshot and must be reverified before external enablement.",
            "No external deployment, account change, email action, real order or cash spend occurred in S00/P03.",
            "P04 external-consent degraded mode and the rest of Stage 0 remain unrun.",
        ],
        "release_status": "NOT_READY",
        "stage_status": "S00_IN_PROGRESS",
        "next": result["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    path = root / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    matches = 0
    for row in rows:
        if row.get("id") == "INDEX-AC-S00-P03":
            matches += 1
            row["status"] = status
            row["actual_artifact"] = "machine/evidence/EVD-S00-P03.json"
            row["artifact_sha256"] = evidence_hash
            row["verified_at"] = FIXED_CLOCK
            row["next"] = "S00/P04_READY_NOT_STARTED" if status == "PASS" else "S00/P04_BLOCKED"
    if matches != 1:
        raise ValueError("expected exactly one INDEX-AC-S00-P03 row, found %d" % matches)
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
    rollback_path = evidence_dir / "EVD-S00-P03_rollback.json"
    evidence_path = evidence_dir / "EVD-S00-P03.json"
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
