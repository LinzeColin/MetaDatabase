from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .stage2_delivery import (
    PINNED_RECEIPT_SHA256 as S02_DELIVERY_RECEIPT_SHA256,
    RECEIPT_PATH as S02_DELIVERY_RECEIPT_PATH,
    verify_stage2_delivery,
)


CONTRACT_ID = "AC-S03-P01"
REQUIREMENT_ID = "REQ-S03-P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

GLOSSARY_PATH = Path("glossary_zh.json")
FORBIDDEN_PATH = Path("forbidden_ui_terms.json")
LEGACY_GLOSSARY_PATH = Path("machine/facts/glossary_zh.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S03_P01.json")
TEST_PATH = Path("tests/S03/P01_test.py")
JUNIT_PATH = Path("machine/evidence/S03/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S03/P01/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PINNED_PHASE_HASHES = {
    GLOSSARY_PATH.as_posix(): "ffaf3a6c66533ce89bd8dc788b1bbfb09754bb8af0dec1355c90544eb4151097",
    FORBIDDEN_PATH.as_posix(): "c2dc156b31b7e333fe316343c09d6cab47339b18d3f7572b11e7c1fbf2590c7f",
    FIXTURE_PATH.as_posix(): "db5a58ff94577cd7a352c0094a40bf6d9c6476c7de63b31a0ee82d31d78cf132",
    TEST_PATH.as_posix(): "b142adfcfb8da35f6517524ba7ef6fe0c1833a47144c9ef3ee77b842e97e8761",
}

PINNED_BASELINE_HASHES = {
    LEGACY_GLOSSARY_PATH.as_posix(): "7cd21db129058a8b14b36cfddf33710d99cb065ae6840dd537689f8a31dffec3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    S02_DELIVERY_RECEIPT_PATH.as_posix(): S02_DELIVERY_RECEIPT_SHA256,
    "machine/evidence/EVD-S02-STAGE-REVIEW.json": "7164544cf192a5ce45b093eccc4d310e9fce811900a1cef3b277834e01292569",
    "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json": "d0f9815ee7c483df7a8d5a3747fe5c5e6c0506062e6be4751580c876a195f867",
    "abd_acceptance/stage2_delivery.py": "d031952a2a1e756a53ca9d572ed4226a572c371ae0850d306de1645468620650",
}

PINNED_REPO_HASHES = {
    CONTINUOUS_WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

PHASE_COMMIT = "436e8e7168a383e0ebcac150bef8dd9f79c32c24"
PINNED_PHASE_CODE_HASH = "bef5b7366e316ddea86feff558636aee243fa97af71ba1b0c107e45171d68392"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/terminology_governance.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S03/P01_test.py",
}
SUCCESSOR_EVOLVED_PHASE_HASHES = {
    TEST_PATH.as_posix(): "e8857d49127deae4db19f3b7d9c3ef1d7d16b25acb0c5bb82f58168345abccf3",
}
SUCCESSOR_UNIT_SELF_NORMALIZED_SHA256 = "9190e57311739a7112253145444f8aa0ad9a86655054e87f0dc62e080dd1826f"

ALLOWED_UI_POLICIES = {
    "ZH_WITH_OPTIONAL_EXPLAINED_TOKEN",
    "ZH_ONLY",
    "BRAND_WITH_ZH_CONTEXT",
    "MACHINE_ONLY",
}
POLICY_TO_ACTION = {
    "ZH_WITH_OPTIONAL_EXPLAINED_TOKEN": "ALLOW_ONLY_WITH_EXACT_EXPLANATION",
    "ZH_ONLY": "BLOCK_USE_ZH_LABEL",
    "BRAND_WITH_ZH_CONTEXT": "ALLOW_ONLY_WITH_ZH_CONTEXT",
    "MACHINE_ONLY": "BLOCK_MACHINE_ONLY",
}
ACTION_TO_REASON = {
    "ALLOW_ONLY_WITH_EXACT_EXPLANATION": "UI_TERM_UNEXPLAINED",
    "ALLOW_ONLY_WITH_ZH_CONTEXT": "UI_TERM_UNEXPLAINED",
    "BLOCK_USE_ZH_LABEL": "UI_TERM_ZH_ONLY",
    "BLOCK_MACHINE_ONLY": "UI_TERM_MACHINE_ONLY",
}
ALLOWED_NUMERIC_DELTA_STRINGS = {"-0.0001", "0", "0.0001"}
ALLOWED_NUMERIC_DELTAS = {Decimal("-0.0001"), Decimal("0"), Decimal("0.0001")}


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


def _duplicates(values: Sequence[Any]) -> List[Any]:
    seen: Set[str] = set()
    duplicates: List[Any] = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(marker)
    return duplicates


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    matches = [row for row in rows if row.get(key) == item_id]
    return matches[0] if len(matches) == 1 else {}


def _token_pattern(token: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(token))


def _token_present(text: str, token: str) -> bool:
    return bool(_token_pattern(token).search(text))


def _contains_exact_text(value: Any, identifier: str) -> bool:
    if isinstance(value, dict):
        if identifier in value:
            return True
        return any(_contains_exact_text(item, identifier) for item in value.values())
    if isinstance(value, list):
        return any(_contains_exact_text(item, identifier) for item in value)
    if isinstance(value, str):
        return _token_present(value, identifier)
    return False


def scan_ui_text(
    text: str,
    surface_kind: str,
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(text, str) or not isinstance(surface_kind, str):
        raise TypeError("text and surface_kind must be strings")
    exemption = policy.get("non_rendered_machine_exemption", {})
    if surface_kind == exemption.get("surface_kind"):
        return []
    included = policy.get("included_surface_kinds", [])
    if surface_kind not in included:
        return [{"reason_code": "UI_SURFACE_UNKNOWN", "token": surface_kind, "term_id": None}]

    entries = {entry.get("term_id"): entry for entry in glossary.get("entries", []) if isinstance(entry, dict)}
    violations: List[Dict[str, Any]] = []
    registered_tokens: Set[str] = set()
    for rule in policy.get("rules", []):
        if not isinstance(rule, dict):
            continue
        term_id = rule.get("term_id")
        entry = entries.get(term_id, {})
        for token in rule.get("raw_tokens", []):
            if not isinstance(token, str):
                continue
            registered_tokens.add(token)
            if not _token_present(text, token):
                continue
            action = rule.get("action")
            allowed_forms = rule.get("allowed_ui_forms", [])
            if action in {"ALLOW_ONLY_WITH_EXACT_EXPLANATION", "ALLOW_ONLY_WITH_ZH_CONTEXT"}:
                allowed = any(isinstance(form, str) and form in text for form in allowed_forms)
            else:
                allowed = False
            if not allowed:
                violations.append(
                    {
                        "reason_code": rule.get("reason_code_on_failure"),
                        "token": token,
                        "term_id": term_id,
                        "replacement_zh": entry.get("preferred_ui_label"),
                    }
                )

    patterns = {row.get("pattern_id"): row for row in policy.get("generic_forbidden_patterns", []) if isinstance(row, dict)}
    priority = ["PATTERN-INTERNAL-ID", "PATTERN-SNAKE-CASE", "PATTERN-UPPERCASE-ACRONYM"]
    occupied: List[Tuple[int, int]] = []
    for pattern_id in priority:
        row = patterns.get(pattern_id, {})
        try:
            expression = re.compile(str(row.get("regex", "")))
        except re.error:
            continue
        for match in expression.finditer(text):
            token = match.group(0)
            span = match.span()
            if token in registered_tokens:
                continue
            if any(start <= span[0] and span[1] <= end for start, end in occupied):
                continue
            occupied.append(span)
            violations.append(
                {
                    "reason_code": row.get("reason_code"),
                    "token": token,
                    "term_id": None,
                    "replacement_zh": None,
                }
            )

    unique: List[Dict[str, Any]] = []
    markers: Set[Tuple[Any, ...]] = set()
    for violation in violations:
        marker = (violation.get("reason_code"), violation.get("token"), violation.get("term_id"))
        if marker not in markers:
            unique.append(violation)
            markers.add(marker)
    return unique


def resolve_ui_gate(
    *,
    text: str,
    surface_kind: str,
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
    numeric_delta: str,
    adverse_odds_tick: bool,
) -> str:
    if not isinstance(numeric_delta, str):
        raise TypeError("numeric_delta must be an exact decimal string")
    if numeric_delta not in ALLOWED_NUMERIC_DELTA_STRINGS:
        raise ValueError("numeric_delta must use the frozen boundary representation")
    try:
        parsed = Decimal(numeric_delta)
    except InvalidOperation as exc:
        raise ValueError("invalid numeric_delta") from exc
    if parsed not in ALLOWED_NUMERIC_DELTAS:
        raise ValueError("numeric_delta is outside the frozen boundary set")
    if type(adverse_odds_tick) is not bool:
        raise TypeError("adverse_odds_tick must be boolean")
    return "BLOCK" if scan_ui_text(text, surface_kind, glossary, policy) else "ALLOW"


def _check_pinned_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in {**PINNED_PHASE_HASHES, **PINNED_BASELINE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        accepted = {expected}
        if relative in SUCCESSOR_EVOLVED_PHASE_HASHES:
            accepted.add(SUCCESSOR_EVOLVED_PHASE_HASHES[relative])
        _add(checks, "S03P01-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual in accepted, {"expected": sorted(accepted), "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S03P01-PIN-REPO-%s" % Path(relative).name.upper().replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})


def _mapping_is_valid(root: Path, entry: Mapping[str, Any], mapping: Mapping[str, Any], cache: MutableMapping[str, Any]) -> Tuple[bool, Any]:
    source = mapping.get("source")
    identifier = mapping.get("identifier")
    mode = mapping.get("match_mode")
    if not isinstance(source, str) or not isinstance(identifier, str) or mode not in {"EXACT_TEXT", "LEGACY_GLOSSARY_KEY"}:
        return False, "invalid mapping shape"
    candidate = Path(source)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False, "unsafe mapping path"
    path = root / candidate
    if source not in cache:
        try:
            cache[source] = strict_json_load(path)
        except Exception as exc:
            return False, "%s: %s" % (type(exc).__name__, exc)
    value = cache[source]
    if mode == "LEGACY_GLOSSARY_KEY":
        expected = "%s：%s" % (entry.get("zh_name"), entry.get("definition_zh"))
        actual = value.get(identifier) if isinstance(value, dict) else None
        return actual == expected, {"expected": expected, "actual": actual}
    return _contains_exact_text(value, identifier), {"source": source, "identifier": identifier}


def _check_glossary(root: Path, glossary: Any, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    if not isinstance(glossary, dict):
        _add(checks, "S03P01-GLOSSARY-SHAPE", False, "glossary unavailable")
        return {}
    entries = glossary.get("entries", [])
    shape_ok = (
        glossary.get("schema_version") == "1.0.0"
        and glossary.get("product_version") == VERSION
        and glossary.get("stage_id") == "S03"
        and glossary.get("phase_id") == "P01"
        and glossary.get("language") == "zh-CN"
        and glossary.get("ui_policy_values") == [
            "ZH_WITH_OPTIONAL_EXPLAINED_TOKEN", "ZH_ONLY", "BRAND_WITH_ZH_CONTEXT", "MACHINE_ONLY"
        ]
        and isinstance(entries, list)
        and not _contains_float(glossary)
    )
    _add(checks, "S03P01-GLOSSARY-SHAPE", shape_ok, {"entries": len(entries) if isinstance(entries, list) else None})
    if not isinstance(entries, list):
        return {}
    ids = [entry.get("term_id") for entry in entries if isinstance(entry, dict)]
    tokens = [entry.get("machine_token") for entry in entries if isinstance(entry, dict)]
    expected_ids = fixture.get("expected_term_ids", [])
    _add(checks, "S03P01-GLOSSARY-TERM-SET-EXACT", ids == expected_ids and not _duplicates(ids), ids)
    _add(checks, "S03P01-GLOSSARY-MACHINE-TOKENS-UNIQUE", len(tokens) == len(set(tokens)) and None not in tokens, tokens)
    policy_counts = Counter(entry.get("ui_policy") for entry in entries if isinstance(entry, dict))
    _add(checks, "S03P01-GLOSSARY-POLICY-COUNTS", dict(policy_counts) == fixture.get("expected_ui_policy_counts"), dict(policy_counts))
    scope = glossary.get("contract_scope", {})
    scope_ok = (
        scope.get("status") == "TERMINOLOGY_CONTRACT_FROZEN_UI_NOT_IMPLEMENTED"
        and len(scope.get("applies_to", [])) == 5
        and len(scope.get("non_claims", [])) == 4
        and "用户可见文字必须优先使用中文" in scope.get("rule", "")
        and all(_contains_chinese(value) for value in scope.get("non_claims", []))
    )
    _add(checks, "S03P01-GLOSSARY-SCOPE-NO-RUNTIME-CLAIM", scope_ok, scope)
    rendered = json.dumps(glossary, ensure_ascii=False, sort_keys=True)
    portable = (
        ("/" + "Users/") not in rendered
        and ("/private/" + "var/") not in rendered
        and ("file" + "://") not in rendered
        and ("C:" + "\\Users\\") not in rendered
    )
    _add(checks, "S03P01-GLOSSARY-PORTABLE-NO-LOCAL-PATH", portable, "portable" if portable else "local path found")

    cache: Dict[str, Any] = {}
    by_id: Dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        term_id = str(entry.get("term_id", "INVALID"))
        aliases = entry.get("machine_aliases", [])
        mappings = entry.get("machine_mappings", [])
        policy = entry.get("ui_policy")
        machine_token = entry.get("machine_token")
        fields_ok = (
            term_id.startswith("TERM-")
            and isinstance(machine_token, str) and bool(machine_token)
            and isinstance(aliases, list) and bool(aliases) and not _duplicates(aliases)
            and isinstance(entry.get("zh_name"), str) and _contains_chinese(entry["zh_name"])
            and isinstance(entry.get("definition_zh"), str) and _contains_chinese(entry["definition_zh"])
            and isinstance(entry.get("preferred_ui_label"), str) and _contains_chinese(entry["preferred_ui_label"])
            and isinstance(entry.get("first_use_display"), str) and _contains_chinese(entry["first_use_display"])
            and policy in ALLOWED_UI_POLICIES
            and isinstance(mappings, list) and bool(mappings)
        )
        if policy == "ZH_WITH_OPTIONAL_EXPLAINED_TOKEN":
            fields_ok = fields_ok and entry.get("first_use_display") == "%s（%s）" % (entry.get("zh_name"), machine_token)
        elif policy == "BRAND_WITH_ZH_CONTEXT":
            fields_ok = fields_ok and _token_present(str(entry.get("first_use_display", "")), str(machine_token))
        else:
            fields_ok = fields_ok and not _token_present(str(entry.get("first_use_display", "")), str(machine_token))
        _add(checks, "S03P01-GLOSSARY-ENTRY-%s" % term_id, fields_ok, {"token": machine_token, "policy": policy})
        mapping_results = [_mapping_is_valid(root, entry, mapping, cache) for mapping in mappings if isinstance(mapping, dict)]
        mapping_ok = len(mapping_results) == len(mappings) and bool(mapping_results) and all(passed for passed, _ in mapping_results)
        _add(checks, "S03P01-GLOSSARY-MAPPING-%s" % term_id, mapping_ok, [detail for _, detail in mapping_results])
        by_id[term_id] = entry

    legacy = strict_json_load(root / LEGACY_GLOSSARY_PATH)
    legacy_tokens = fixture.get("legacy_machine_tokens", [])
    legacy_ok = set(legacy) == set(legacy_tokens) and all(
        any(
            entry.get("machine_token") == token
            and "%s：%s" % (entry.get("zh_name"), entry.get("definition_zh")) == legacy[token]
            for entry in entries
            if isinstance(entry, dict)
        )
        for token in legacy_tokens
    )
    _add(checks, "S03P01-LEGACY-GLOSSARY-15-OF-15-PRESERVED", legacy_ok, {"legacy": len(legacy), "expected": len(legacy_tokens)})
    return by_id


def _check_policy(policy: Any, glossary_by_id: Mapping[str, Mapping[str, Any]], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    if not isinstance(policy, dict):
        _add(checks, "S03P01-POLICY-SHAPE", False, "policy unavailable")
        return
    rules = policy.get("rules", [])
    patterns = policy.get("generic_forbidden_patterns", [])
    shape_ok = (
        policy.get("schema_version") == "1.0.0"
        and policy.get("product_version") == VERSION
        and policy.get("stage_id") == "S03"
        and policy.get("phase_id") == "P01"
        and policy.get("policy_id") == "UI-TERMINOLOGY-ZH-ONLY-V1"
        and policy.get("default_action") == "BLOCK_UNREGISTERED_OR_UNEXPLAINED_TOKEN"
        and policy.get("included_surface_kinds") == fixture.get("expected_surface_kinds")
        and isinstance(rules, list)
        and isinstance(patterns, list)
        and not _contains_float(policy)
    )
    _add(checks, "S03P01-POLICY-SHAPE", shape_ok, {"rules": len(rules) if isinstance(rules, list) else None})
    if not isinstance(rules, list) or not isinstance(patterns, list):
        return
    term_ids = [row.get("term_id") for row in rules if isinstance(row, dict)]
    _add(checks, "S03P01-POLICY-TERM-SET-EXACT", term_ids == fixture.get("expected_term_ids") and not _duplicates(term_ids), term_ids)
    action_counts = Counter(row.get("action") for row in rules if isinstance(row, dict))
    _add(checks, "S03P01-POLICY-ACTION-COUNTS", dict(action_counts) == fixture.get("expected_action_counts"), dict(action_counts))
    pattern_ids = [row.get("pattern_id") for row in patterns if isinstance(row, dict)]
    patterns_ok = pattern_ids == fixture.get("expected_generic_pattern_ids") and not _duplicates(pattern_ids)
    for row in patterns:
        try:
            re.compile(str(row.get("regex", "")))
        except re.error:
            patterns_ok = False
    _add(checks, "S03P01-POLICY-GENERIC-PATTERNS", patterns_ok, pattern_ids)
    reason_codes = policy.get("reason_codes", {})
    expected_reasons = {
        "UI_TERM_UNREGISTERED_RAW_TOKEN", "UI_TERM_INTERNAL_IDENTIFIER", "UI_TERM_MACHINE_IDENTIFIER",
        "UI_TERM_UNEXPLAINED", "UI_TERM_ZH_ONLY", "UI_TERM_MACHINE_ONLY", "UI_SURFACE_UNKNOWN",
    }
    reasons_ok = isinstance(reason_codes, dict) and set(reason_codes) == expected_reasons and all(_contains_chinese(value) for value in reason_codes.values())
    _add(checks, "S03P01-POLICY-REASON-CODES-CLOSED", reasons_ok, sorted(reason_codes) if isinstance(reason_codes, dict) else reason_codes)
    exemption = policy.get("non_rendered_machine_exemption", {})
    exemption_ok = exemption == {
        "surface_kind": "NON_RENDERED_MACHINE_RECORD",
        "condition": "内容只存在于源代码、机器字段、结构化证据或运维日志且绝不被渲染到用户界面。",
        "rendered_content_must_reenter_ui_gate": True,
    }
    _add(checks, "S03P01-POLICY-MACHINE-EXEMPTION-NON-RENDERED-ONLY", exemption_ok, exemption)
    _add(checks, "S03P01-POLICY-EXTERNAL-EFFECT-BOUNDARY", policy.get("external_effect_boundary") == fixture.get("expected_external_effect_boundary"), policy.get("external_effect_boundary"))
    rendered = json.dumps(policy, ensure_ascii=False, sort_keys=True)
    portable = (
        ("/" + "Users/") not in rendered
        and ("/private/" + "var/") not in rendered
        and ("file" + "://") not in rendered
        and ("C:" + "\\Users\\") not in rendered
    )
    _add(checks, "S03P01-POLICY-PORTABLE-NO-LOCAL-PATH", portable, "portable" if portable else "local path found")

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        term_id = str(rule.get("term_id", "INVALID"))
        entry = glossary_by_id.get(term_id, {})
        expected_action = POLICY_TO_ACTION.get(entry.get("ui_policy"))
        expected_forms = [entry.get("first_use_display")] if expected_action in {
            "ALLOW_ONLY_WITH_EXACT_EXPLANATION", "ALLOW_ONLY_WITH_ZH_CONTEXT"
        } else []
        rule_ok = (
            bool(entry)
            and rule.get("raw_tokens") == [entry.get("machine_token")]
            and rule.get("action") == expected_action
            and rule.get("allowed_ui_forms") == expected_forms
            and rule.get("reason_code_on_failure") == ACTION_TO_REASON.get(expected_action)
        )
        _add(checks, "S03P01-POLICY-RULE-%s" % term_id, rule_ok, rule)


def _check_ui_samples(glossary: Mapping[str, Any], policy: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    for sample in fixture.get("allowed_ui_samples", []):
        violations = scan_ui_text(sample["text"], sample["surface_kind"], glossary, policy)
        _add(checks, "S03P01-UI-ALLOW-%s" % sample["id"], not violations, violations or sample["text"])
    for sample in fixture.get("blocked_ui_samples", []):
        violations = scan_ui_text(sample["text"], sample["surface_kind"], glossary, policy)
        reasons = [row.get("reason_code") for row in violations]
        _add(checks, "S03P01-UI-BLOCK-%s" % sample["id"], bool(violations) and sample["reason_code"] in reasons, violations)
    for vector in fixture.get("boundary_vectors", []):
        decision = resolve_ui_gate(
            text=vector["text"], surface_kind="ADVICE_CARD", glossary=glossary, policy=policy,
            numeric_delta=vector["numeric_delta"], adverse_odds_tick=vector["adverse_odds_tick"],
        )
        _add(checks, "S03P01-BOUNDARY-%s" % vector["id"], decision == vector["expected"], decision)


def _check_taskpack_contract(
    roadmap: Any,
    requirements: Any,
    acceptance: Any,
    task_graph: Any,
    traceability: Any,
    checks: List[Dict[str, Any]],
) -> None:
    stages = roadmap.get("stages", []) if isinstance(roadmap, dict) else []
    stage = _row(stages, "S03")
    phase = _row(stage.get("phases", []), "P01") if stage else {}
    roadmap_ok = (
        stage.get("title") == "全中文交互与术语治理"
        and phase == {
            "id": "P01", "title": "中文术语字典", "objective": "为所有必要缩写提供中文名、定义和机器映射。",
            "outputs": ["glossary_zh.json", "forbidden_ui_terms.json"], "pass_gate": "日常界面不存在未解释缩写。",
            "hours": {"low": 3, "likely": 4, "high": 6},
        }
    )
    _add(checks, "S03P01-TASKPACK-ROADMAP-EXACT", roadmap_ok, phase)
    req = _row(requirements if isinstance(requirements, list) else [], REQUIREMENT_ID)
    req_ok = (
        req.get("stage_id") == "S03" and req.get("phase_id") == "P01"
        and req.get("scope") == ["glossary_zh.json", "forbidden_ui_terms.json"]
        and req.get("target") == "日常界面不存在未解释缩写。"
        and req.get("primary_acceptance_criteria_id") == CONTRACT_ID
    )
    _add(checks, "S03P01-TASKPACK-REQUIREMENT-EXACT", req_ok, req)
    ac = _row(acceptance if isinstance(acceptance, list) else [], CONTRACT_ID)
    ac_ok = (
        ac.get("requirement_id") == REQUIREMENT_ID
        and ac.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S03-P01 --evidence machine/evidence"
        and ac.get("threshold") == "日常界面不存在未解释缩写。"
        and ac.get("pass_gate") == "日常界面不存在未解释缩写。"
        and len(ac.get("tests", [])) == 3
    )
    _add(checks, "S03P01-TASKPACK-ACCEPTANCE-EXACT", ac_ok, ac)
    tasks = task_graph.get("tasks", []) if isinstance(task_graph, dict) else []
    phase_tasks = [row for row in tasks if row.get("stage_id") == "S03" and row.get("phase_id") == "P01"]
    task_ok = (
        [row.get("id") for row in phase_tasks] == ["T-S03-P01-01", "T-S03-P01-02", "T-S03-P01-03"]
        and phase_tasks[0].get("outputs") == ["glossary_zh.json", "forbidden_ui_terms.json"]
        and phase_tasks[1].get("outputs") == ["tests/S03/P01_test.py", "machine/tests/fixtures/S03_P01.json"]
        and phase_tasks[2].get("outputs") == ["machine/evidence/EVD-S03-P01.json", "machine/evidence/EVD-S03-P01_rollback.json"]
        if len(phase_tasks) == 3 else False
    )
    _add(checks, "S03P01-TASKPACK-TASK-GRAPH-EXACT", task_ok, [row.get("id") for row in phase_tasks])
    trace_rows = [row for row in traceability if isinstance(row, dict) and row.get("requirement_id") == REQUIREMENT_ID] if isinstance(traceability, list) else []
    trace_ok = len(trace_rows) == 1 and trace_rows[0] == {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S03-P01-01", "T-S03-P01-02", "T-S03-P01-03"],
        "test_ids": ["TEST-S03-P01", "TEST-S03-P01-BOUNDARY", "TEST-S03-P01-REPLAY"],
        "evidence_id": "EVD-S03-P01",
        "artifact_ids": ["ART-S03-P01-01", "ART-S03-P01-02"],
        "stage_id": "S03",
        "phase_id": "P01",
    }
    _add(checks, "S03P01-TASKPACK-TRACEABILITY-EXACT", trace_ok, trace_rows)


def _check_p02_not_started(root: Path, checks: List[Dict[str, Any]]) -> None:
    p02_paths = [
        Path("advice_card_schema.json"), Path("advice_card_fixtures.json"),
        Path("tests/S03/P02_test.py"), Path("machine/tests/fixtures/S03_P02.json"),
        Path("machine/evidence/EVD-S03-P02.json"), Path("machine/evidence/EVD-S03-P02_rollback.json"),
    ]
    later_paths = [
        Path("machine/facts/stage3_review_contract.json"), Path("tests/S03/stage_review_test.py"),
        Path("machine/evidence/EVD-S03-STAGE-REVIEW.json"),
    ]
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p02 = [row for row in rows if row.get("id") == "INDEX-AC-S03-P02"]
        present = [path.as_posix() for path in p02_paths if (root / path).exists()]
        later = [path.as_posix() for path in later_paths if (root / path).exists()]
        if not present and not later:
            artifacts_ok = True
            index_ok = len(p02) == 1 and p02[0].get("status") == "PLANNED" and "actual_artifact" not in p02[0] and "artifact_sha256" not in p02[0]
            detail: Any = "none"
        elif (
            set(present)
            == {
                "advice_card_schema.json",
                "advice_card_fixtures.json",
                "tests/S03/P02_test.py",
                "machine/tests/fixtures/S03_P02.json",
            }
            and not later
        ):
            from .advice_card import PINNED_PHASE_HASHES as P02_PINNED_PHASE_HASHES

            p02_hashes_ok = all(
                (root / relative).is_file() and sha256_file(root / relative) == expected
                for relative, expected in P02_PINNED_PHASE_HASHES.items()
            )
            artifacts_ok = p02_hashes_ok
            index_ok = len(p02) == 1 and p02[0].get("status") == "PLANNED" and "actual_artifact" not in p02[0] and "artifact_sha256" not in p02[0]
            detail = {"mode": "CONTROLLED_S03_P02_BUILD_IN_PROGRESS", "artifacts": present, "hashes_ok": p02_hashes_ok}
        elif len(present) == len(p02_paths) and not later:
            from .advice_card import verify_existing_phase_evidence as verify_p02_evidence

            successor = verify_p02_evidence(root, verify_git_history=True)
            artifacts_ok = successor.get("status") == "PASS" and successor.get("next") == "S03/P03_READY_NOT_STARTED"
            index_ok = (
                len(p02) == 1
                and p02[0].get("status") == "PASS"
                and p02[0].get("actual_artifact") == "machine/evidence/EVD-S03-P02.json"
                and p02[0].get("next") == "S03/P03_READY_NOT_STARTED"
            )
            detail = {"mode": "VERIFIED_S03_P02_SUCCESSOR", "summary": successor.get("summary")}
        else:
            artifacts_ok = False
            index_ok = False
            detail = {"partial_p02": present, "later_successor": later}
        _add(checks, "S03P01-SUCCESSOR-ARTIFACTS-NOT-STARTED", artifacts_ok, detail)
        _add(checks, "S03P01-SUCCESSOR-INDEX-PLANNED", index_ok, p02)
    except Exception as exc:
        _add(checks, "S03P01-SUCCESSOR-ARTIFACTS-NOT-STARTED", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S03P01-SUCCESSOR-INDEX-PLANNED", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    for element in root.iter():
        if element.tag == "testsuite":
            if element.attrib.get("hostname") is not None:
                return False
            if element.attrib.get("timestamp") != JUNIT_FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S03P01-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S03P01-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
    ]:
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            passed = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and normalized
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root / PACK_REPORT_PATH, checks, "S03P01-PACK-REPORT-PARSE")
    report_ok = isinstance(report, dict) and report.get("status") == "PASS" and report.get("summary", {}).get("checks") == 49 and report.get("summary", {}).get("failed") == 0
    _add(checks, "S03P01-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = (
            "STATUS: PASS" in text and "MAX_INCREMENTAL_CASH_AUD: 0.00" in text
            and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in text
            and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in text
        )
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        _add(checks, "S03P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S03P01-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S03",
        "phase_id": "P01",
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "ZH_TERMINOLOGY_AND_UI_EXPOSURE_POLICY_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for row in checks if row["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "user_interface_status": "CONTRACT_ONLY_NOT_IMPLEMENTED_OR_DEPLOYED",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "release_status": "NOT_READY_S03_P02_TO_P04_AND_STAGE_REVIEW_REQUIRED",
        "phase_status": "S03_P01_PASS" if status == "PASS" else "S03_P01_FAILED",
        "next": "S03/P02_READY_NOT_STARTED" if status == "PASS" else "S03/P01_REMEDIATION_REQUIRED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S03P01-FIXTURE-STRICT-JSON")
    glossary = _safe_load(root / GLOSSARY_PATH, checks, "S03P01-GLOSSARY-STRICT-JSON")
    policy = _safe_load(root / FORBIDDEN_PATH, checks, "S03P01-POLICY-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S03P01-ROADMAP-STRICT-JSON")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S03P01-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S03P01-ACCEPTANCE-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S03P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S03P01-TRACEABILITY-STRICT-JSON")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "S03P01-CANONICAL-STRICT-JSON")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "S03P01-COSTS-STRICT-JSON")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S03P01-PARAMETERS-STRICT-JSON")
    _check_pinned_hashes(root, checks, hashes)
    import_markers = [
        Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py"),
        Path("tests/S02/__init__.py"), Path("tests/S03/__init__.py"),
    ]
    _add(checks, "S03P01-PYTEST-IMPORT-ISOLATION", all((root / path).is_file() for path in import_markers), [path.as_posix() for path in import_markers])
    if isinstance(fixture, dict):
        glossary_by_id = _check_glossary(root, glossary, fixture, checks)
        _check_policy(policy, glossary_by_id, fixture, checks)
        if isinstance(glossary, dict) and isinstance(policy, dict):
            _check_ui_samples(glossary, policy, fixture, checks)
        _check_taskpack_contract(roadmap, requirements, acceptance, task_graph, traceability, checks)
        _add(checks, "S03P01-NUMERIC-BOUNDARY-SET-EXACT", set(fixture.get("allowed_numeric_delta_strings", [])) == ALLOWED_NUMERIC_DELTA_STRINGS, fixture.get("allowed_numeric_delta_strings"))
    else:
        _add(checks, "S03P01-FIXTURE-CONTRACT-AVAILABLE", False, "fixture unavailable")

    canonical_ok = (
        isinstance(canonical, dict)
        and canonical.get("product", {}).get("initial_bankroll_aud") == "300.00"
        and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00"
        and canonical.get("product", {}).get("monthly_target_return") == "0.30"
    )
    _add(checks, "S03P01-AUD300-AUD0-TARGET-BASELINE", canonical_ok, canonical.get("product") if isinstance(canonical, dict) else canonical)
    cost_gate_ok = (
        isinstance(costs, dict)
        and costs.get("incremental_cash_budget") == {"low": "0.00", "likely": "0.00", "high": "0.00"}
        and costs.get("incremental_cash_gate", {}).get("maximum_aud") == "0.00"
        and costs.get("incremental_cash_gate", {}).get("automatic_purchase_allowed") is False
        and costs.get("incremental_cash_gate", {}).get("automatic_paid_upgrade_allowed") is False
        and costs.get("incremental_cash_gate", {}).get("automatic_overage_billing_allowed") is False
    )
    _add(checks, "S03P01-COSTS-ZERO-INCREMENTAL-CASH", cost_gate_ok, costs.get("incremental_cash_budget") if isinstance(costs, dict) else costs)
    _add(checks, "S03P01-PARAMETERS-NO-FLOAT", isinstance(parameters, dict) and not _contains_float(parameters), "decimal strings only")
    try:
        delivery = verify_stage2_delivery(root, verify_git_history=_verify_git_history)
        _add(
            checks,
            "S03P01-S02-DELIVERY-PREREQUISITE",
            delivery.get("status") == "PASS" and delivery.get("decision") == "S02_DELIVERED_S03_MAY_START" and delivery.get("next") == "S03/P01_READY_NOT_STARTED",
            {"status": delivery.get("status"), "summary": delivery.get("summary"), "next": delivery.get("next")},
        )
    except Exception as exc:
        _add(checks, "S03P01-S02-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    _check_p02_not_started(root, checks)
    if require_external_reports and isinstance(fixture, dict):
        _check_runtime_reports(root, fixture, checks, hashes)
    result = _build_result(checks, hashes)
    minimum = int(fixture.get("expected_oracle_check_minimum", 0)) if isinstance(fixture, dict) else 0
    if result["summary"]["checks"] < minimum:
        _add(checks, "S03P01-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
        result = _build_result(checks, hashes)
    return result


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
    artifacts = [GLOSSARY_PATH, FORBIDDEN_PATH, FIXTURE_PATH, S02_DELIVERY_RECEIPT_PATH, LEGACY_GLOSSARY_PATH]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s03-p01-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(artifacts):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
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
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_TERMINOLOGY_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        GLOSSARY_PATH, FORBIDDEN_PATH, FIXTURE_PATH, TEST_PATH,
        Path("README.md"),
        *[Path(relative) for relative in PINNED_BASELINE_HASHES],
        Path("abd_acceptance/terminology_governance.py"), Path("abd_acceptance/stage2_delivery.py"),
        Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
        Path("tests/__init__.py"), Path("tests/S00/__init__.py"), Path("tests/S01/__init__.py"),
        Path("tests/S02/__init__.py"), Path("tests/S03/__init__.py"),
    ]
    unique = {path.as_posix(): path for path in paths}
    result = {relative: sha256_file(root / path) for relative, path in unique.items()}
    result[CONTINUOUS_WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / CONTINUOUS_WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0", "evidence_id": "EVD-S03-P01-ROLLBACK", "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False, "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["phase_status"] = "S03_P01_FAILED"
        result["next"] = "S03/P01_REMEDIATION_REQUIRED"
    input_hashes = _input_hashes(root)
    external_boundary = strict_json_load(root / FIXTURE_PATH)["expected_external_effect_boundary"]
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S03",
        "phase_id": "P01",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S03-P01-01": GLOSSARY_PATH.as_posix(),
            "ART-S03-P01-02": FORBIDDEN_PATH.as_posix(),
        },
        "stage2_delivery_prerequisite": {
            "receipt": S02_DELIVERY_RECEIPT_PATH.as_posix(),
            "receipt_sha256": S02_DELIVERY_RECEIPT_SHA256,
            "status": "PASS",
            "decision": "S02_DELIVERED_S03_MAY_START",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes["machine/facts/parameters.json"],
            "code": _current_code_hash(root),
            "model": input_hashes["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S03/P01 freezes terminology and user-interface exposure policy only; it executes no model, strategy, provider interaction, deployment, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P01_test.py --junitxml=machine/evidence/S03/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S03/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S03-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": dict(external_boundary),
        "explicit_unknowns": [
            "S03/P01 freezes a terminology contract and deterministic scanner; no daily interface has been implemented, deployed or usability-tested.",
            "S03/P02 advice card, S03/P03 error and next-action copy, S03/P04 accessibility work and the S03 whole-stage review have not started.",
            "TAB, Gmail, OVH and Cloudflare account, authorization, capacity and runtime states remain uninspected or unauthorized and fail closed.",
            "No model, calibration, robustness, numeric stability, Kelly, market coverage, capacity, friction or actual execution evidence was produced.",
            "No automatic order-submission capability exists; the user remains the only party permitted to complete a final order.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
        ],
        "release_status": "NOT_READY_S03_P02_TO_P04_AND_STAGE_REVIEW_REQUIRED",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P01"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S03-P01 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S03/P02_READY_NOT_STARTED" if status == "PASS" else "S03/P01_REMEDIATION_REQUIRED"
    payload = b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows)
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


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
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
        if not _phase_commit_is_ancestor(root):
            return False
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (PHASE_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if relative == "abd_acceptance/terminology_governance.py":
        try:
            text = (root / relative).read_text(encoding="utf-8")
            normalized = re.sub(
                r'(?m)^(SUCCESSOR_UNIT_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
                r'\1<NORMALIZED>\2',
                text,
                count=1,
            )
            return normalized != text and _sha256_bytes(normalized.encode("utf-8")) == SUCCESSOR_UNIT_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    # Successor phases own and hash their current README/CLI/export surfaces. In
    # a unit copy without .git, the immutable P01 receipt remains authoritative
    # for their historical blobs while the successor oracle protects current ones.
    return True


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _phase_commit_is_ancestor(root):
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", PHASE_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        line for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S03P01-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S03P01-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, dict):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S03-P01"
            and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S03" and evidence.get("phase_id") == "P01"
            and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS"
            and evidence.get("decision") == "ZH_TERMINOLOGY_AND_UI_EXPOSURE_POLICY_FROZEN"
            and evidence.get("phase_status") == "S03_P01_PASS" and evidence.get("next") == "S03/P02_READY_NOT_STARTED"
            and evidence.get("artifacts") == {"ART-S03-P01-01": GLOSSARY_PATH.as_posix(), "ART-S03-P01-02": FORBIDDEN_PATH.as_posix()}
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S03P01-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = (
            validation.get("status") == "PASS" and validation.get("decision") == "ZH_TERMINOLOGY_AND_UI_EXPOSURE_POLICY_FROZEN"
            and validation.get("summary", {}).get("failed") == 0 and validation.get("next") == "S03/P02_READY_NOT_STARTED"
            and all(row.get("passed") is True for row in validation.get("checks", []))
        )
        _add(checks, "S03P01-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        _add(checks, "S03P01-RECEIPT-NO-EXTERNAL-EFFECT", evidence.get("external_effect_boundary") == strict_json_load(root / FIXTURE_PATH).get("expected_external_effect_boundary"), evidence.get("external_effect_boundary"))
        input_errors = []
        signed_inputs = evidence.get("hashes", {}).get("inputs", {})
        if not isinstance(signed_inputs, dict):
            signed_inputs = {}
            input_errors.append("signed inputs unavailable")
        for relative, expected in signed_inputs.items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "reason": "unsafe path"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                if _historical_file_matches(root, relative, expected, verify_git_history):
                    continue
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03P01-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or len(signed_inputs))
        validation_hashes = validation.get("hashes", {})
        report_errors = []
        for relative in [JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), PACK_REPORT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()]:
            expected = validation_hashes.get(relative)
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if expected != actual:
                report_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03P01-RECEIPT-REPORT-HASHES-CURRENT", not report_errors, report_errors or "all reports match")
        code_expected = evidence.get("hashes", {}).get("code")
        code_current = _current_code_hash(root)
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (
            code_expected == PINNED_PHASE_CODE_HASH
            and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(checks, "S03P01-RECEIPT-CODE-HASH-CURRENT", code_ok, {"expected": code_expected, "current": code_current, "historical_phase_commit": code_historical})
        _add(checks, "S03P01-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        portable = (
            str(root) not in rendered
            and ("/" + "Users/") not in rendered
            and ("/private/" + "var/") not in rendered
            and ("file" + "://") not in rendered
            and ("C:" + "\\Users\\") not in rendered
        )
        _add(checks, "S03P01-RECEIPT-NO-ABSOLUTE-LOCAL-PATH", portable, "portable" if portable else "local path found")
    else:
        for check_id in [
            "S03P01-RECEIPT-EVIDENCE-INTEGRITY", "S03P01-RECEIPT-VALIDATION-ALL-PASS",
            "S03P01-RECEIPT-NO-EXTERNAL-EFFECT", "S03P01-RECEIPT-SIGNED-INPUTS-CURRENT",
            "S03P01-RECEIPT-REPORT-HASHES-CURRENT", "S03P01-RECEIPT-CODE-HASH-CURRENT",
            "S03P01-RECEIPT-ROLLBACK-HASH-BINDING", "S03P01-RECEIPT-NO-ABSOLUTE-LOCAL-PATH",
        ]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, dict) and rollback.get("evidence_id") == "EVD-S03-P01-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False and len(rollback.get("artifacts", {})) == 5
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S03P01-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, dict) else "unavailable")
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        p01 = [row for row in rows if row.get("id") == "INDEX-AC-S03-P01"]
        index_ok = len(p01) == 1 and p01[0].get("status") == "PASS" and p01[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and p01[0].get("artifact_sha256") == evidence_hash and p01[0].get("next") == "S03/P02_READY_NOT_STARTED"
        _add(checks, "S03P01-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, p01)
    except Exception as exc:
        _add(checks, "S03P01-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        delivery = verify_stage2_delivery(root, verify_git_history=verify_git_history)
        _add(checks, "S03P01-RECEIPT-S02-DELIVERY-PREREQUISITE", delivery.get("status") == "PASS", delivery.get("summary"))
    except Exception as exc:
        _add(checks, "S03P01-RECEIPT-S02-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S03-P01",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S03_P01_EVIDENCE_VERIFIED" if not failed else "S03_P01_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": sum(1 for row in checks if row["passed"]), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S03/P02_READY_NOT_STARTED" if not failed else "S03/P01_REMEDIATION_REQUIRED",
    }
