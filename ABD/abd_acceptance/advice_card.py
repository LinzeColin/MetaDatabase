from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .terminology_governance import (
    FIXED_CLOCK as P01_FIXED_CLOCK,
    PINNED_PHASE_HASHES as P01_PINNED_PHASE_HASHES,
    scan_ui_text,
    verify_existing_phase_evidence as verify_p01_evidence,
)


CONTRACT_ID = "AC-S03-P02"
REQUIREMENT_ID = "REQ-S03-P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T09:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SCHEMA_PATH = Path("advice_card_schema.json")
FIXTURES_PATH = Path("advice_card_fixtures.json")
ORACLE_FIXTURE_PATH = Path("machine/tests/fixtures/S03_P02.json")
TEST_PATH = Path("tests/S03/P02_test.py")
GLOSSARY_PATH = Path("glossary_zh.json")
FORBIDDEN_PATH = Path("forbidden_ui_terms.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
MODEL_CARD_PATH = Path("machine/facts/model_system_card.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S03-P01_rollback.json")
JUNIT_PATH = Path("machine/evidence/S03/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S03/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S03-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CONTINUOUS_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PINNED_PHASE_HASHES = {
    SCHEMA_PATH.as_posix(): "213f1f467d3421f56382f8de247842d23b3ece1ce726e83af13269caa6febc9a",
    FIXTURES_PATH.as_posix(): "2f9a5f892eebf01dfbdf91e3c14c96ee59005cd801f169460514d8c4e5476eb5",
    ORACLE_FIXTURE_PATH.as_posix(): "26bdaef3a2335204e5acaecb4e7ed8a91959c649c42aed637192e089efc8978d",
    TEST_PATH.as_posix(): "04463326c983d22d53093609429c8ced6589445cb4cde40702f34ce3b33a54f0",
}
PINNED_BASELINE_HASHES = {
    GLOSSARY_PATH.as_posix(): P01_PINNED_PHASE_HASHES[GLOSSARY_PATH.as_posix()],
    FORBIDDEN_PATH.as_posix(): P01_PINNED_PHASE_HASHES[FORBIDDEN_PATH.as_posix()],
    P01_EVIDENCE_PATH.as_posix(): "cc128b7e0b3552d7633239971250c357320f7a3edbbb9782ee23e1dc8a922d25",
    P01_ROLLBACK_PATH.as_posix(): "4ebf1284026f1aacb5c9b37c193b814fd34f586f7befb93742e2b4231db5183e",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    PARAMETERS_PATH.as_posix(): "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    MODEL_CARD_PATH.as_posix(): "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "tests/S03/P01_test.py": "172fd4792995132b92e812205d9f92a9cada9dc9331d6fec63e2157cb71e0aa2",
}

PHASE_COMMIT = "b21f7a49f1d2f17c772cc6c1bd55e1add410cda2"
PINNED_PHASE_CODE_HASH = "0a92aae3fb6801c312aaf453808d71adbba31b8518f9da02aa2ca320dabfdb2e"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/advice_card.py",
    "abd_acceptance/terminology_governance.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "tests/S03/P02_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES = {
    "README.md": "cdeb85233247f078f9b8d7380e182a6eb905bde133ac05246231a559c2cbe8ef",
    "abd_acceptance/terminology_governance.py": "d51ae252e7d28addfa7097a2f4ccb5ba2f017ec0745a0eee4e0971fd744beded",
    "abd_acceptance/__main__.py": "6f1d82c21751c665a8b33b93178fc98db8a7545a095141c9c63811be1871d2f9",
    "abd_acceptance/__init__.py": "dd43b55546ecbb245bc4b97a201563454f20766666bbaf37a3741f89375e594b",
    "tests/S03/P02_test.py": "04463326c983d22d53093609429c8ced6589445cb4cde40702f34ce3b33a54f0",
}
SUCCESSOR_EVOLVED_PHASE_HASHES = {
    TEST_PATH.as_posix(): "04463326c983d22d53093609429c8ced6589445cb4cde40702f34ce3b33a54f0",
}

STRUCTURAL_SELF_NORMALIZED_SHA256 = "ab733b14dacfa058c1e5910a9f37e9d5ff36cc8b0209118d22b11dd0b4e62ffe"

DISPLAY_ORDER = ["status", "action", "countdown", "reasons", "evidence", "invalidation", "safety"]
PRIMARY_ANSWER_KEYS = ["what_zh", "where_zh", "amount_zh", "minimum_odds_zh"]
ALLOWED_NUMERIC_DELTA_STRINGS = {"-0.0001", "0", "0.0001"}
REQUIRED_RECOMMENDATION_GATES = [
    "identity_passed",
    "quote_fresh",
    "evidence_gate_passed",
    "risk_gate_passed",
    "stability_gate_passed",
    "action_channel_verified",
    "provider_contract_passed",
]
ODDS_PATTERN = re.compile(r"^[1-9][0-9]*\.[0-9]{6}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SYDNEY_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\+10:00|\+11:00)$"
)
INVALIDATION_CONDITIONS_ZH = [
    "当前赔率低于最低可接受赔率",
    "赛事、盘口、选择或结算规则与卡片不一致",
    "倒计时结束或报价过期",
    "证据、来源、模型、稳定性或风险门不再通过",
    "平台页面无法核对或动作通道不明确",
]


class CardContractError(ValueError):
    """Raised when an upstream card input is malformed and cannot be trusted."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


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
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not SYDNEY_TIMESTAMP_PATTERN.fullmatch(value):
        raise CardContractError("%s must be an explicit Australia/Sydney offset timestamp" % field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CardContractError("%s is not a valid timestamp" % field) from exc
    if parsed.utcoffset() not in {timedelta(hours=10), timedelta(hours=11)}:
        raise CardContractError("%s has an unsupported Sydney offset" % field)
    return parsed


def _parse_odds(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not ODDS_PATTERN.fullmatch(value):
        raise CardContractError("%s must be a six-decimal string" % field)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CardContractError("%s is not a decimal" % field) from exc
    if parsed <= Decimal("1.000000"):
        raise CardContractError("%s must be greater than 1.000000" % field)
    return parsed


def _validate_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise CardContractError("%s must be a lowercase SHA-256" % field)
    return value


def _validate_ui_string(
    value: Any,
    field: str,
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    if not isinstance(value, str) or not value.strip() or not _contains_chinese(value):
        raise CardContractError("%s must be a non-empty Chinese user-visible string" % field)
    violations = scan_ui_text(value, "ADVICE_CARD", glossary, policy)
    if violations:
        raise CardContractError("%s violates the frozen Chinese UI gate: %s" % (field, violations))
    return value


def _validate_reasons(
    value: Any,
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise CardContractError("reasons must contain one to three rows")
    output: List[Dict[str, Any]] = []
    seen = set()
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != {"code", "title_zh", "detail_zh", "evidence_refs"}:
            raise CardContractError("reason %d has an invalid shape" % index)
        code = row.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", code):
            raise CardContractError("reason %d has an invalid machine code" % index)
        if code in seen:
            raise CardContractError("reason codes must be unique")
        seen.add(code)
        title = _validate_ui_string(row.get("title_zh"), "reason.title_zh", glossary, policy)
        detail = _validate_ui_string(row.get("detail_zh"), "reason.detail_zh", glossary, policy)
        refs = row.get("evidence_refs")
        if not isinstance(refs, list) or not refs or len(refs) > 8 or len(refs) != len(set(refs)):
            raise CardContractError("reason evidence_refs must be one to eight unique machine references")
        if not all(isinstance(ref, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{2,127}", ref) for ref in refs):
            raise CardContractError("reason evidence_refs contain an invalid reference")
        output.append({"code": code, "title_zh": title, "detail_zh": detail, "evidence_refs": list(refs)})
    return output


def _validate_input(
    decision: Mapping[str, Any],
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(decision, Mapping):
        raise CardContractError("decision must be a mapping")
    required = {
        "vector_id", "synthetic_test_only", "sydney_date", "generated_at", "expires_at",
        "candidate_status", "platform_zh", "event_zh", "market_zh", "selection_zh",
        "stake_cents", "observed_odds_decimal", "minimum_odds_decimal",
        "numeric_boundary_delta", "stability_action_flip", "adverse_odds_tick_action_flip",
        "evidence_status", "evidence_reference_count", "gates", "reasons",
    }
    missing = sorted(required - set(decision))
    extra = sorted(set(decision) - required)
    if missing or extra:
        raise CardContractError("decision keys mismatch: missing=%s extra=%s" % (missing, extra))
    if not isinstance(decision["vector_id"], str) or not decision["vector_id"]:
        raise CardContractError("vector_id must be a non-empty string")
    if decision["synthetic_test_only"] is not True:
        raise CardContractError("P02 fixtures must be explicitly synthetic_test_only")
    generated = _parse_timestamp(decision["generated_at"], "generated_at")
    expires = _parse_timestamp(decision["expires_at"], "expires_at")
    if not isinstance(decision["sydney_date"], str) or decision["sydney_date"] != generated.date().isoformat():
        raise CardContractError("sydney_date must equal the generated Sydney date")
    status = decision["candidate_status"]
    if status not in {"RECOMMENDATION", "NO_RECOMMENDATION"}:
        raise CardContractError("candidate_status is not closed")
    delta = decision["numeric_boundary_delta"]
    if not isinstance(delta, str) or delta not in ALLOWED_NUMERIC_DELTA_STRINGS:
        raise CardContractError("numeric_boundary_delta must use -0.0001, 0 or 0.0001")
    for field in ["stability_action_flip", "adverse_odds_tick_action_flip"]:
        if type(decision[field]) is not bool:
            raise CardContractError("%s must be boolean" % field)
    evidence_status = decision["evidence_status"]
    if evidence_status not in {"COMPLETE", "INCOMPLETE", "UNVERIFIED"}:
        raise CardContractError("evidence_status is not closed")
    reference_count = decision["evidence_reference_count"]
    if type(reference_count) is not int or reference_count < 0:
        raise CardContractError("evidence_reference_count must be a non-negative integer")
    gates = decision["gates"]
    if not isinstance(gates, dict) or list(gates) != REQUIRED_RECOMMENDATION_GATES:
        raise CardContractError("gates must contain the frozen ordered gate set")
    if not all(type(gates[key]) is bool for key in REQUIRED_RECOMMENDATION_GATES):
        raise CardContractError("all gates must be booleans")
    reasons = _validate_reasons(decision["reasons"], glossary, policy)

    output = dict(decision)
    output["generated_datetime"] = generated
    output["expires_datetime"] = expires
    output["reasons"] = reasons
    if status == "RECOMMENDATION":
        for field in ["platform_zh", "event_zh", "market_zh", "selection_zh"]:
            output[field] = _validate_ui_string(decision[field], field, glossary, policy)
        stake = decision["stake_cents"]
        if type(stake) is not int or stake <= 0:
            raise CardContractError("recommendation stake_cents must be a positive integer")
        output["observed_odds"] = _parse_odds(decision["observed_odds_decimal"], "observed_odds_decimal")
        output["minimum_odds"] = _parse_odds(decision["minimum_odds_decimal"], "minimum_odds_decimal")
        if evidence_status != "COMPLETE":
            raise CardContractError("a recommendation candidate requires COMPLETE evidence")
    else:
        if any(decision[field] is not None for field in ["platform_zh", "event_zh", "market_zh", "selection_zh", "observed_odds_decimal", "minimum_odds_decimal"]):
            raise CardContractError("no-recommendation input must not carry actionable fields")
        if decision["stake_cents"] != 0 or type(decision["stake_cents"]) is not int:
            raise CardContractError("no-recommendation input stake must be integer zero")
        output["observed_odds"] = None
        output["minimum_odds"] = None
    return output


def _countdown(generated: datetime, expires: datetime, palette: Mapping[str, Any]) -> Dict[str, Any]:
    seconds = max(0, int((expires - generated).total_seconds()))
    if seconds == 0:
        state = "EXPIRED"
        display = "已失效，请勿下单"
    elif seconds <= 60:
        state = "EXPIRING"
        display = "剩余%d秒" % seconds
    else:
        state = "ACTIVE"
        minutes, remainder = divmod(seconds, 60)
        display = "剩余%d分%d秒" % (minutes, remainder) if remainder else "剩余%d分钟" % minutes
    colors = palette[state]
    return {
        "state": state,
        "seconds_remaining": seconds,
        "expires_at": expires.isoformat(),
        "display_zh": display,
        "color": {"background": colors["background"], "foreground": colors["foreground"]},
    }


def _downgrade_reason(validated: Mapping[str, Any]) -> Dict[str, Any]:
    if validated["expires_datetime"] <= validated["generated_datetime"]:
        return {
            "code": "ADVICE_EXPIRED",
            "title_zh": "建议已失效",
            "detail_zh": "倒计时已经结束，当前卡片不得再用于下单。",
            "evidence_refs": ["CARD:COUNTDOWN"],
        }
    if validated.get("observed_odds") is not None and validated.get("minimum_odds") is not None and validated["observed_odds"] < validated["minimum_odds"]:
        return {
            "code": "CURRENT_ODDS_BELOW_MINIMUM",
            "title_zh": "当前赔率不足",
            "detail_zh": "当前赔率低于最低可接受赔率，因此本卡自动改为不建议。",
            "evidence_refs": ["CARD:ODDS-BOUNDARY"],
        }
    if validated["stability_action_flip"] or validated["adverse_odds_tick_action_flip"]:
        return {
            "code": "STABILITY_ACTION_FLIP",
            "title_zh": "轻微变化会改变动作",
            "detail_zh": "不利边界或赔率跳动会改变动作，因此本卡自动改为不建议。",
            "evidence_refs": ["CARD:STABILITY-BOUNDARY"],
        }
    failed = [name for name in REQUIRED_RECOMMENDATION_GATES if validated["gates"][name] is not True]
    if failed:
        return {
            "code": "UPSTREAM_GATE_FAILED",
            "title_zh": "上游安全门未通过",
            "detail_zh": "至少一个证据、时效、来源、稳定性或风险门未通过。",
            "evidence_refs": ["CARD:GATE:%s" % failed[0].upper().replace("_", "-")],
        }
    return {
        "code": "NO_QUALIFIED_OPPORTUNITY",
        "title_zh": "当前不建议",
        "detail_zh": "当前没有同时通过全部证据、时效、稳定性和风险门的机会。",
        "evidence_refs": ["CARD:NO-QUALIFIED-OPPORTUNITY"],
    }


def _artifact_hash(card: Mapping[str, Any]) -> str:
    unsigned = copy.deepcopy(dict(card))
    unsigned.get("provenance", {}).pop("artifact_sha256", None)
    return _canonical_sha256(unsigned)


def build_advice_card(
    decision: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
    parameters_sha256: str,
    model_sha256: str,
) -> Dict[str, Any]:
    validated = _validate_input(decision, glossary, policy)
    _validate_hash(parameters_sha256, "parameters_sha256")
    _validate_hash(model_sha256, "model_sha256")
    display = schema.get("x-abd-display-contract", {})
    status_palette = display.get("status_palette", {})
    countdown_palette = display.get("countdown_palette", {})
    if set(status_palette) != {"RECOMMENDATION", "NO_RECOMMENDATION"} or set(countdown_palette) != {"ACTIVE", "EXPIRING", "EXPIRED"}:
        raise CardContractError("schema palette is not closed")

    all_gates = all(validated["gates"].values())
    not_expired = validated["expires_datetime"] > validated["generated_datetime"]
    odds_pass = (
        validated.get("observed_odds") is not None
        and validated.get("minimum_odds") is not None
        and validated["observed_odds"] >= validated["minimum_odds"]
    )
    stable = not validated["stability_action_flip"] and not validated["adverse_odds_tick_action_flip"]
    recommendation = (
        validated["candidate_status"] == "RECOMMENDATION"
        and all_gates
        and not_expired
        and odds_pass
        and stable
    )
    status = "RECOMMENDATION" if recommendation else "NO_RECOMMENDATION"
    palette = status_palette[status]
    countdown = _countdown(validated["generated_datetime"], validated["expires_datetime"], countdown_palette)
    input_sha = _canonical_sha256(decision)

    if recommendation:
        action = {
            "action_type": "OWNER_FINAL_ORDER_ONLY",
            "platform_zh": validated["platform_zh"],
            "event_zh": validated["event_zh"],
            "market_zh": validated["market_zh"],
            "selection_zh": validated["selection_zh"],
            "stake_cents": validated["stake_cents"],
            "stake_display_zh": "A$%d.%02d" % divmod(validated["stake_cents"], 100),
            "observed_odds_decimal": decision["observed_odds_decimal"],
            "observed_odds_display_zh": "当前赔率%s" % decision["observed_odds_decimal"],
            "minimum_odds_decimal": decision["minimum_odds_decimal"],
            "minimum_odds_display_zh": "最低可接受赔率%s" % decision["minimum_odds_decimal"],
            "user_instruction_zh": "请在指定平台页面核对赛事、盘口、选择、赔率和倒计时；全部一致后，由你自行决定是否完成最终下单。",
        }
        headline = "今天有一个建议"
        summary = "先核对平台、选择、金额和最低赔率，再由你自行决定是否下单。"
        reasons = validated["reasons"]
        evidence_status = "COMPLETE"
    else:
        action = {
            "action_type": "NO_ACTION",
            "platform_zh": None,
            "event_zh": None,
            "market_zh": None,
            "selection_zh": None,
            "stake_cents": 0,
            "stake_display_zh": "A$0.00",
            "observed_odds_decimal": None,
            "observed_odds_display_zh": "不适用",
            "minimum_odds_decimal": None,
            "minimum_odds_display_zh": "不适用",
            "user_instruction_zh": "无需下单；等待下一次自动更新。",
        }
        headline = "今天不建议下单"
        summary = "当前没有同时通过全部安全门的机会，你无需前往任何平台。"
        reasons = validated["reasons"] if validated["candidate_status"] == "NO_RECOMMENDATION" else [_downgrade_reason(validated)]
        evidence_status = validated["evidence_status"] if validated["evidence_status"] != "COMPLETE" else "INCOMPLETE"

    evidence_labels = {"COMPLETE": "证据已通过", "INCOMPLETE": "证据不足", "UNVERIFIED": "证据未验证"}
    card: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "card_id": "CARD-%s-%s" % (validated["sydney_date"], input_sha[:12]),
        "sydney_date": validated["sydney_date"],
        "timezone": "Australia/Sydney",
        "generated_at": validated["generated_datetime"].isoformat(),
        "status": status,
        "status_label_zh": palette["label_zh"],
        "status_symbol": palette["symbol"],
        "status_color": {"background": palette["background"], "foreground": palette["foreground"]},
        "headline_zh": headline,
        "summary_zh": summary,
        "display_order": list(DISPLAY_ORDER),
        "action": action,
        "countdown": countdown,
        "reasons": reasons,
        "evidence": {
            "status": evidence_status,
            "label_zh": evidence_labels[evidence_status],
            "checked_at": validated["generated_datetime"].isoformat(),
            "reference_count": validated["evidence_reference_count"],
        },
        "invalidation": {
            "conditions_zh": list(INVALIDATION_CONDITIONS_ZH),
            "behavior_zh": "任一条件出现立即作废并停止下单。",
        },
        "safety": {
            "auto_order_enabled": False,
            "owner_final_action_required": True,
            "guaranteed_return": False,
            "target_shortfall_may_relax_gate": False,
            "boundary_zh": "系统只提供分析建议；最终下单只能由用户自行决定并完成，月度30%目标未验证且不保证。",
        },
        "provenance": {
            "input_sha256": input_sha,
            "parameters_sha256": parameters_sha256,
            "model_sha256": model_sha256,
            "artifact_sha256": "0" * 64,
        },
    }
    card["provenance"]["artifact_sha256"] = _artifact_hash(card)
    return card


def safe_build_advice_card(
    decision: Any,
    *,
    schema: Mapping[str, Any],
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
    parameters_sha256: str,
    model_sha256: str,
) -> Dict[str, Any]:
    try:
        return build_advice_card(
            decision,
            schema=schema,
            glossary=glossary,
            policy=policy,
            parameters_sha256=parameters_sha256,
            model_sha256=model_sha256,
        )
    except Exception:
        try:
            source_sha = _canonical_sha256(decision)
        except Exception:
            source_sha = _sha256_bytes(repr(decision).encode("utf-8"))
        generated_text = decision.get("generated_at") if isinstance(decision, Mapping) else None
        date_text = decision.get("sydney_date") if isinstance(decision, Mapping) else None
        try:
            generated = _parse_timestamp(generated_text, "generated_at")
            sydney_date = generated.date().isoformat()
        except CardContractError:
            generated = _parse_timestamp(FIXED_CLOCK, "fixed_clock")
            sydney_date = generated.date().isoformat()
        if not isinstance(date_text, str) or date_text != sydney_date:
            date_text = sydney_date
        fallback = {
            "vector_id": "FAIL-CLOSED-MALFORMED-INPUT",
            "synthetic_test_only": True,
            "sydney_date": date_text,
            "generated_at": generated.isoformat(),
            "expires_at": (generated + timedelta(seconds=60)).isoformat(),
            "candidate_status": "NO_RECOMMENDATION",
            "platform_zh": None,
            "event_zh": None,
            "market_zh": None,
            "selection_zh": None,
            "stake_cents": 0,
            "observed_odds_decimal": None,
            "minimum_odds_decimal": None,
            "numeric_boundary_delta": "0",
            "stability_action_flip": False,
            "adverse_odds_tick_action_flip": False,
            "evidence_status": "UNVERIFIED",
            "evidence_reference_count": 1,
            "gates": {key: False for key in REQUIRED_RECOMMENDATION_GATES},
            "reasons": [
                {
                    "code": "CARD_INPUT_INVALID",
                    "title_zh": "卡片输入无效",
                    "detail_zh": "输入缺失、类型错误或包含未解释机器文字，已自动改为不建议。",
                    "evidence_refs": ["CARD:INPUT-VALIDATION"],
                }
            ],
        }
        card = build_advice_card(
            fallback,
            schema=schema,
            glossary=glossary,
            policy=policy,
            parameters_sha256=parameters_sha256,
            model_sha256=model_sha256,
        )
        card["provenance"]["input_sha256"] = source_sha
        card["card_id"] = "CARD-%s-%s" % (card["sydney_date"], source_sha[:12])
        card["provenance"]["artifact_sha256"] = _artifact_hash(card)
        return card


def render_visible_text(card: Mapping[str, Any], schema: Mapping[str, Any]) -> str:
    labels = schema.get("x-abd-display-contract", {}).get("section_labels_zh", {})
    action = card.get("action", {})
    visible = [
        labels.get("status", "结论"), card.get("status_label_zh"), card.get("headline_zh"), card.get("summary_zh"),
        labels.get("action", "行动"), action.get("platform_zh"), action.get("event_zh"), action.get("market_zh"),
        action.get("selection_zh"), action.get("stake_display_zh"), action.get("observed_odds_display_zh"),
        action.get("minimum_odds_display_zh"), action.get("user_instruction_zh"), labels.get("countdown", "剩余时间"),
        card.get("countdown", {}).get("display_zh"), labels.get("reasons", "主要理由"),
    ]
    for reason in card.get("reasons", []):
        if isinstance(reason, Mapping):
            visible.extend([reason.get("title_zh"), reason.get("detail_zh")])
    visible.extend([
        labels.get("evidence", "证据状态"), card.get("evidence", {}).get("label_zh"),
        labels.get("invalidation", "必须取消的情况"),
    ])
    visible.extend(card.get("invalidation", {}).get("conditions_zh", []))
    visible.extend([
        card.get("invalidation", {}).get("behavior_zh"), labels.get("safety", "安全边界"),
        card.get("safety", {}).get("boundary_zh"),
    ])
    return "\n".join(str(item) for item in visible if isinstance(item, str) and item)


def extract_primary_answers(card: Mapping[str, Any]) -> Dict[str, str]:
    action = card.get("action", {})
    if card.get("status") == "RECOMMENDATION":
        return {
            "what_zh": "%s｜%s｜%s" % (action.get("event_zh"), action.get("market_zh"), action.get("selection_zh")),
            "where_zh": str(action.get("platform_zh")),
            "amount_zh": str(action.get("stake_display_zh")),
            "minimum_odds_zh": str(action.get("minimum_odds_display_zh")),
        }
    return {
        "what_zh": "不下单",
        "where_zh": "无需前往平台",
        "amount_zh": "A$0.00",
        "minimum_odds_zh": "不适用",
    }


def validate_daily_card_set(cards: Any) -> List[str]:
    if not isinstance(cards, list):
        return ["daily card collection must be a list"]
    errors: List[str] = []
    counts: Dict[str, int] = {}
    for card in cards:
        if not isinstance(card, Mapping):
            errors.append("daily card row must be an object")
            continue
        date = card.get("sydney_date")
        counts[str(date)] = counts.get(str(date), 0) + 1
    duplicates = {date: count for date, count in counts.items() if count != 1}
    if duplicates:
        errors.append("each Sydney date must contain exactly one card: %s" % duplicates)
    return errors


def validate_card(
    card: Any,
    *,
    schema: Mapping[str, Any],
    glossary: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors.extend(
            "%s: %s" % ("/".join(str(part) for part in error.absolute_path) or "$", error.message)
            for error in sorted(validator.iter_errors(card), key=lambda row: list(row.absolute_path))
        )
    except Exception as exc:
        return ["schema validation unavailable: %s: %s" % (type(exc).__name__, exc)]
    if not isinstance(card, Mapping):
        return errors or ["card must be an object"]
    if card.get("display_order") != DISPLAY_ORDER:
        errors.append("display_order does not match the frozen scan path")
    status = card.get("status")
    action = card.get("action", {})
    if status == "RECOMMENDATION":
        if not all(action.get(field) for field in ["platform_zh", "event_zh", "market_zh", "selection_zh", "minimum_odds_decimal"]):
            errors.append("recommendation is missing a primary answer")
        try:
            if _parse_odds(action.get("observed_odds_decimal"), "observed") < _parse_odds(action.get("minimum_odds_decimal"), "minimum"):
                errors.append("recommendation observed odds are below minimum")
        except CardContractError as exc:
            errors.append(str(exc))
        stake = action.get("stake_cents")
        if type(stake) is not int or stake <= 0:
            errors.append("recommendation stake is not a positive integer")
        elif action.get("stake_display_zh") != "A$%d.%02d" % divmod(stake, 100):
            errors.append("stake display does not match integer cents")
        if card.get("evidence", {}).get("status") != "COMPLETE":
            errors.append("recommendation evidence is not complete")
    elif status == "NO_RECOMMENDATION":
        if action.get("action_type") != "NO_ACTION" or action.get("stake_cents") != 0:
            errors.append("no-recommendation card carries an action")
    else:
        errors.append("status is not closed")
    safety = card.get("safety", {})
    if safety.get("auto_order_enabled") is not False or safety.get("owner_final_action_required") is not True:
        errors.append("owner-only final action boundary is broken")
    if safety.get("guaranteed_return") is not False or safety.get("target_shortfall_may_relax_gate") is not False:
        errors.append("return or target safety boundary is broken")
    countdown = card.get("countdown", {})
    try:
        generated = _parse_timestamp(card.get("generated_at"), "generated_at")
        expires = _parse_timestamp(countdown.get("expires_at"), "expires_at")
        seconds = max(0, int((expires - generated).total_seconds()))
        state = "EXPIRED" if seconds == 0 else "EXPIRING" if seconds <= 60 else "ACTIVE"
        if countdown.get("seconds_remaining") != seconds or countdown.get("state") != state:
            errors.append("countdown is not derived from the frozen timestamps")
        if state == "EXPIRED" and status != "NO_RECOMMENDATION":
            errors.append("expired card still recommends")
    except CardContractError as exc:
        errors.append(str(exc))
    provenance = card.get("provenance", {})
    if provenance.get("artifact_sha256") != _artifact_hash(card):
        errors.append("artifact hash does not bind the rendered card")
    input_sha = provenance.get("input_sha256")
    expected_card_id = "CARD-%s-%s" % (card.get("sydney_date"), str(input_sha)[:12])
    if card.get("card_id") != expected_card_id:
        errors.append("card_id does not bind the Sydney date and input hash")
    answers = extract_primary_answers(card)
    if list(answers) != PRIMARY_ANSWER_KEYS or any(not value for value in answers.values()):
        errors.append("the four primary answers are not directly extractable")
    if card.get("invalidation", {}).get("conditions_zh") != INVALIDATION_CONDITIONS_ZH:
        errors.append("invalidation conditions are not the frozen exact set")
    visible = render_visible_text(card, schema)
    violations = scan_ui_text(visible, "ADVICE_CARD", glossary, policy)
    if violations:
        errors.append("visible text violates the Chinese terminology gate: %s" % violations)
    return errors


def _hex_to_rgb(value: str) -> Tuple[float, float, float]:
    return tuple(int(value[index:index + 2], 16) / 255.0 for index in (1, 3, 5))  # type: ignore[return-value]


def _relative_luminance(value: str) -> float:
    channels = []
    for channel in _hex_to_rgb(value):
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(background: str, foreground: str) -> float:
    light, dark = sorted([_relative_luminance(background), _relative_luminance(foreground)], reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _pack_report_passes(report: Any) -> bool:
    if not isinstance(report, Mapping):
        return False
    summary = report.get("summary", {})
    return (
        isinstance(summary, Mapping)
        and report.get("status") == "PASS"
        and summary.get("checks") == 49
        and summary.get("passed") == 49
        and summary.get("failed") == 0
    )


def _paid_dependency_scan_passes(scan_text: Any) -> bool:
    if not isinstance(scan_text, str):
        return False
    required_lines = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    return required_lines.issubset(set(scan_text.splitlines()))


def _set_path(value: MutableMapping[str, Any], dotted: str, replacement: Any) -> None:
    parts = dotted.split(".")
    current: MutableMapping[str, Any] = value
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, MutableMapping):
            raise CardContractError("mutation path is not an object: %s" % dotted)
        current = nested
    current[parts[-1]] = replacement


def _merge_input(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in overrides.items():
        if key == "gates" and isinstance(value, Mapping):
            merged["gates"].update(value)
        else:
            merged[key] = value
    return merged


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    graph = strict_json_load(root / "machine/facts/task_graph.json")
    traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
    req = next((row for row in requirements if row.get("id") == REQUIREMENT_ID), {})
    _add(
        checks,
        "S03P02-TASKPACK-REQUIREMENT-EXACT",
        req.get("scope") == [SCHEMA_PATH.as_posix(), FIXTURES_PATH.as_posix()]
        and req.get("target") == "用户10秒内知道做什么、在哪做、金额和最低赔率。"
        and req.get("primary_acceptance_criteria_id") == CONTRACT_ID
        and req.get("owner_input_required_during_development") is False,
        req,
    )
    ac = next((row for row in contracts if row.get("id") == CONTRACT_ID), {})
    _add(
        checks,
        "S03P02-TASKPACK-ACCEPTANCE-EXACT",
        ac.get("requirement_id") == REQUIREMENT_ID
        and ac.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S03-P02 --evidence machine/evidence"
        and ac.get("threshold") == "用户10秒内知道做什么、在哪做、金额和最低赔率。"
        and ac.get("pass_gate") == "用户10秒内知道做什么、在哪做、金额和最低赔率。"
        and len(ac.get("tests", [])) == 3,
        ac,
    )
    tasks = [row for row in graph.get("tasks", []) if row.get("stage_id") == "S03" and row.get("phase_id") == "P02"]
    task_ok = (
        len(tasks) == 3
        and [row.get("id") for row in tasks] == ["T-S03-P02-01", "T-S03-P02-02", "T-S03-P02-03"]
        and tasks[0].get("outputs") == [SCHEMA_PATH.as_posix(), FIXTURES_PATH.as_posix()]
        and tasks[1].get("outputs") == [TEST_PATH.as_posix(), ORACLE_FIXTURE_PATH.as_posix()]
        and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
        and tasks[0].get("depends_on") == ["T-S03-P01-03"]
    )
    _add(checks, "S03P02-TASKPACK-TASK-GRAPH-EXACT", task_ok, [row.get("id") for row in tasks])
    trace = [row for row in traceability if row.get("requirement_id") == REQUIREMENT_ID]
    trace_ok = len(trace) == 1 and trace[0] == {
        "requirement_id": REQUIREMENT_ID,
        "acceptance_criteria_id": CONTRACT_ID,
        "task_ids": ["T-S03-P02-01", "T-S03-P02-02", "T-S03-P02-03"],
        "test_ids": ["TEST-S03-P02", "TEST-S03-P02-BOUNDARY", "TEST-S03-P02-REPLAY"],
        "evidence_id": "EVD-S03-P02",
        "artifact_ids": ["ART-S03-P02-01", "ART-S03-P02-02"],
        "stage_id": "S03",
        "phase_id": "P02",
    }
    _add(checks, "S03P02-TASKPACK-TRACEABILITY-EXACT", trace_ok, trace)


def _check_p03_not_started(
    root: Path,
    checks: List[Dict[str, Any]],
    *,
    verify_git_history: bool,
) -> None:
    core = [
        Path("reason_codes_zh.json"),
        Path("next_action_matrix.json"),
        Path("tests/S03/P03_test.py"),
        Path("machine/tests/fixtures/S03_P03.json"),
    ]
    receipts = [
        Path("machine/evidence/EVD-S03-P03.json"),
        Path("machine/evidence/EVD-S03-P03_rollback.json"),
    ]
    later = [
        Path("machine/facts/stage3_review_contract.json"),
        Path("machine/evidence/S03/STAGE_REVIEW/findings.json"),
        Path("machine/tests/fixtures/S03_STAGE_REVIEW.json"),
        Path("tests/S03/stage_review_test.py"),
        Path("machine/evidence/EVD-S03-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S03-STAGE-REVIEW_rollback.json"),
    ]
    present_core = [path for path in core if (root / path).is_file()]
    present_receipts = [path for path in receipts if (root / path).is_file()]
    present_later = [path for path in later if (root / path).exists()]
    stage_progression: Mapping[str, Any] = {"status": "READY_NOT_STARTED"}
    if present_later:
        try:
            from .usability_accessibility import _stage_review_progression

            stage_progression = _stage_review_progression(root)
        except Exception as exc:
            stage_progression = {"status": "INVALID", "error": "%s: %s" % (type(exc).__name__, exc)}
    stage_progression_ok = stage_progression.get("status") in {"CONTROLLED_CANDIDATE", "SIGNED_REVIEW_PASS"}
    mode = "INVALID_PARTIAL_OR_LATER_SUCCESSOR"
    artifacts_ok = False
    successor: Any = None
    if not present_core and not present_receipts and not present_later:
        mode = "P03_NOT_STARTED"
        artifacts_ok = True
    elif len(present_core) == len(core) and not present_receipts and not present_later:
        from .reason_next_action import PINNED_PHASE_HASHES as P03_PINNED_PHASE_HASHES

        actual = {path.as_posix(): sha256_file(root / path) for path in core}
        artifacts_ok = actual == P03_PINNED_PHASE_HASHES
        mode = "P03_CONTROLLED_BUILD" if artifacts_ok else "P03_CONTROLLED_BUILD_HASH_MISMATCH"
        successor = actual
    elif len(present_core) == len(core) and len(present_receipts) == len(receipts) and (not present_later or stage_progression_ok):
        from .reason_next_action import (
            verify_existing_phase_evidence as verify_p03_evidence,
        )

        receipt = verify_p03_evidence(root, verify_git_history=verify_git_history)
        successor = {"receipt": receipt, "stage_progression": stage_progression}
        artifacts_ok = (
            receipt.get("status") == "PASS"
            and receipt.get("next") == "S03/P04_READY_NOT_STARTED"
        )
        if artifacts_ok:
            mode = "P03_SIGNED_DELIVERY_WITH_STAGE_REVIEW" if present_later else "P03_SIGNED_DELIVERY"
        else:
            mode = "P03_SIGNED_DELIVERY_INVALID"
    _add(
        checks,
        "S03P02-SUCCESSOR-ARTIFACTS-NOT-STARTED",
        artifacts_ok,
        {
            "mode": mode,
            "core": [path.as_posix() for path in present_core],
            "receipts": [path.as_posix() for path in present_receipts],
            "later": [path.as_posix() for path in present_later],
            "successor": successor,
        },
    )
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P03"]
        if mode in {"P03_SIGNED_DELIVERY", "P03_SIGNED_DELIVERY_WITH_STAGE_REVIEW"}:
            ok = (
                len(matching) == 1
                and matching[0].get("status") == "PASS"
                and matching[0].get("actual_artifact") == "machine/evidence/EVD-S03-P03.json"
                and matching[0].get("next") == "S03/P04_READY_NOT_STARTED"
            )
        else:
            ok = (
                artifacts_ok
                and len(matching) == 1
                and matching[0].get("status") == "PLANNED"
                and "actual_artifact" not in matching[0]
                and "artifact_sha256" not in matching[0]
            )
        _add(checks, "S03P02-SUCCESSOR-INDEX-PLANNED", ok, matching)
    except Exception as exc:
        _add(checks, "S03P02-SUCCESSOR-INDEX-PLANNED", False, "%s: %s" % (type(exc).__name__, exc))


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/advice_card.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r'\1<NORMALIZED>\2',
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    passed = len(checks) - len(failed)
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "ADVICE_CARD_INFORMATION_CONTRACT_FROZEN" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "phase_status": "S03_P02_PASS" if status == "PASS" else "S03_P02_FAILED",
        "user_interface_status": "SCHEMA_AND_DETERMINISTIC_PRESENTATION_MODEL_ONLY_NOT_DEPLOYED",
        "human_ten_second_usability_status": "STRUCTURAL_INFORMATION_GATE_PASS_HUMAN_TIMING_DEFERRED_TO_S03_P04" if status == "PASS" else "UNVERIFIED",
        "production_status": "NOT_DEPLOYED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "release_status": "NOT_READY_S03_P03_P04_AND_STAGE_REVIEW_REQUIRED",
        "summary": {"checks": len(checks), "passed": passed, "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "next": "S03/P03_READY_NOT_STARTED" if status == "PASS" else "S03/P02_REMEDIATION_REQUIRED",
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
    schema = _safe_load(root / SCHEMA_PATH, checks, "S03P02-SCHEMA-STRICT-JSON")
    fixtures = _safe_load(root / FIXTURES_PATH, checks, "S03P02-FIXTURES-STRICT-JSON")
    oracle_fixture = _safe_load(root / ORACLE_FIXTURE_PATH, checks, "S03P02-ORACLE-FIXTURE-STRICT-JSON")
    glossary = _safe_load(root / GLOSSARY_PATH, checks, "S03P02-GLOSSARY-STRICT-JSON")
    policy = _safe_load(root / FORBIDDEN_PATH, checks, "S03P02-POLICY-STRICT-JSON")
    parameters = _safe_load(root / PARAMETERS_PATH, checks, "S03P02-PARAMETERS-STRICT-JSON")
    model_card = _safe_load(root / MODEL_CARD_PATH, checks, "S03P02-MODEL-CARD-STRICT-JSON")
    for relative, expected in {**PINNED_BASELINE_HASHES, **PINNED_PHASE_HASHES}.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S03P02-HASH-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})
    self_hash = _structural_self_hash(root)
    hashes["abd_acceptance/advice_card.py#normalized"] = self_hash
    _add(checks, "S03P02-ORACLE-SELF-INTEGRITY", self_hash == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": self_hash})
    _add(checks, "S03P02-NO-BINARY-FLOAT-IN-AUTHORITATIVE-FACTS", isinstance(parameters, dict) and not _contains_float(parameters), "parameters use exact strings/integers")

    if all(isinstance(item, dict) for item in [schema, fixtures, oracle_fixture, glossary, policy, parameters, model_card]):
        try:
            from jsonschema import Draft202012Validator

            Draft202012Validator.check_schema(schema)
            schema_ok = True
            schema_detail: Any = "Draft 2020-12 schema valid"
        except Exception as exc:
            schema_ok = False
            schema_detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S03P02-JSON-SCHEMA-META-VALID", schema_ok, schema_detail)
        contract = schema.get("x-abd-contract", {})
        display = schema.get("x-abd-display-contract", {})
        _add(checks, "S03P02-CONTRACT-IDENTITY-EXACT", contract.get("product_version") == VERSION and contract.get("stage_id") == "S03" and contract.get("phase_id") == "P02" and contract.get("contract_id") == CONTRACT_ID and contract.get("requirement_id") == REQUIREMENT_ID, contract)
        _add(checks, "S03P02-DAILY-UNIQUE-SYDNEY-CONTRACT", contract.get("timezone") == "Australia/Sydney" and contract.get("daily_card_limit") == 1, contract)
        questions = contract.get("primary_questions", [])
        _add(checks, "S03P02-PRIMARY-QUESTIONS-EXACT", [row.get("id") for row in questions] == fixtures.get("expected_primary_question_ids") and len({row.get("answer_pointer") for row in questions}) == 4, questions)
        gate = contract.get("ten_second_information_gate", {})
        _add(checks, "S03P02-STRUCTURAL-TEN-SECOND-GATE-HONEST", gate.get("type") == "STRUCTURAL_SCAN_PATH_PROXY" and gate.get("maximum_primary_answers") == 4 and gate.get("primary_section") == "action" and gate.get("primary_section_position") == 2 and gate.get("human_timing_validation") == "DEFERRED_TO_S03_P04" and "不声称真人" in gate.get("claim_boundary_zh", ""), gate)
        _add(checks, "S03P02-NON-CLAIMS-EXPLICIT", len(contract.get("non_claims", [])) == 4 and any("没有验证或保证月度30%" in row for row in contract.get("non_claims", [])), contract.get("non_claims"))
        _add(checks, "S03P02-DISPLAY-ORDER-EXACT", display.get("section_order") == fixtures.get("expected_display_order") == DISPLAY_ORDER and schema.get("properties", {}).get("display_order", {}).get("const") == DISPLAY_ORDER, display.get("section_order"))
        _add(checks, "S03P02-COLOR-NOT-SOLE-SIGNAL", display.get("color_is_only_signal") is False and len(display.get("required_redundant_signals", [])) == 3, display)
        _add(checks, "S03P02-STATUS-PALETTE-EXACT", display.get("status_palette") == fixtures.get("expected_status_palette"), display.get("status_palette"))
        _add(checks, "S03P02-COUNTDOWN-PALETTE-EXACT", display.get("countdown_palette") == fixtures.get("expected_countdown_palette"), display.get("countdown_palette"))
        for group_name in ["status_palette", "countdown_palette"]:
            for name, colors in display.get(group_name, {}).items():
                ratio = contrast_ratio(colors.get("background", "#000000"), colors.get("foreground", "#000000"))
                _add(checks, "S03P02-CONTRAST-%s-%s" % (group_name.upper(), name), ratio >= 4.5, {"ratio": "%.3f" % ratio, "minimum": "4.5"})
        _add(checks, "S03P02-ROOT-ADDITIONAL-PROPERTIES-CLOSED", schema.get("additionalProperties") is False, schema.get("additionalProperties"))
        required = schema.get("required", [])
        _add(checks, "S03P02-ROOT-FIELDS-FROZEN", len(required) == 19 and len(required) == len(set(required)) and set(required) == set(schema.get("properties", {})), required)
        _add(checks, "S03P02-INVALIDATION-EXACT", fixtures.get("expected_invalidation_conditions_zh") == INVALIDATION_CONDITIONS_ZH, fixtures.get("expected_invalidation_conditions_zh"))
        _add(checks, "S03P02-GATES-EXACT", fixtures.get("required_recommendation_gates") == REQUIRED_RECOMMENDATION_GATES, fixtures.get("required_recommendation_gates"))
        _add(checks, "S03P02-DELTA-REPRESENTATIONS-EXACT", set(fixtures.get("allowed_numeric_delta_strings", [])) == ALLOWED_NUMERIC_DELTA_STRINGS, fixtures.get("allowed_numeric_delta_strings"))
        _check_taskpack(root, checks)
        try:
            p01 = verify_p01_evidence(root, verify_git_history=_verify_git_history)
            _add(checks, "S03P02-P01-DELIVERY-PREREQUISITE", p01.get("status") == "PASS" and p01.get("decision") == "S03_P01_EVIDENCE_VERIFIED" and p01.get("next") == "S03/P02_READY_NOT_STARTED", {"status": p01.get("status"), "summary": p01.get("summary"), "next": p01.get("next")})
        except Exception as exc:
            _add(checks, "S03P02-P01-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))

        parameters_sha = sha256_file(root / PARAMETERS_PATH)
        model_sha = sha256_file(root / MODEL_CARD_PATH)
        base = fixtures.get("base_recommendation_input", {})
        no_base = fixtures.get("base_no_recommendation_input", {})
        try:
            recommendation = build_advice_card(base, schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
            recommendation_errors = validate_card(recommendation, schema=schema, glossary=glossary, policy=policy)
            replay = build_advice_card(copy.deepcopy(base), schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
            answers = extract_primary_answers(recommendation)
            _add(checks, "S03P02-BASE-RECOMMENDATION-VALID", not recommendation_errors, recommendation_errors or recommendation["card_id"])
            _add(checks, "S03P02-BASE-RECOMMENDATION-STATUS", recommendation.get("status") == "RECOMMENDATION", recommendation.get("status"))
            _add(checks, "S03P02-BASE-FOUR-ANSWERS-EXTRACTABLE", list(answers) == fixtures.get("expected_primary_answer_keys") and all(answers.values()), answers)
            _add(checks, "S03P02-BASE-DETERMINISTIC-REPLAY", recommendation == replay and _canonical_sha256(recommendation) == _canonical_sha256(replay), recommendation.get("provenance"))
            _add(checks, "S03P02-BASE-OWNER-ONLY", recommendation.get("safety", {}).get("auto_order_enabled") is False and recommendation.get("safety", {}).get("owner_final_action_required") is True, recommendation.get("safety"))
            _add(checks, "S03P02-BASE-NO-RETURN-GUARANTEE", recommendation.get("safety", {}).get("guaranteed_return") is False and recommendation.get("safety", {}).get("target_shortfall_may_relax_gate") is False, recommendation.get("safety"))
            visible = render_visible_text(recommendation, schema)
            _add(checks, "S03P02-BASE-CHINESE-UI-GATE", scan_ui_text(visible, "ADVICE_CARD", glossary, policy) == [], visible)
            _add(checks, "S03P02-BASE-ONE-CARD-PER-DATE", validate_daily_card_set([recommendation]) == [], recommendation["sydney_date"])
            _add(checks, "S03P02-DUPLICATE-DAILY-CARD-REJECTED", bool(validate_daily_card_set([recommendation, replay])), "duplicate rejected")
        except Exception as exc:
            recommendation = {}
            for check_id in ["S03P02-BASE-RECOMMENDATION-VALID", "S03P02-BASE-RECOMMENDATION-STATUS", "S03P02-BASE-FOUR-ANSWERS-EXTRACTABLE", "S03P02-BASE-DETERMINISTIC-REPLAY", "S03P02-BASE-OWNER-ONLY", "S03P02-BASE-NO-RETURN-GUARANTEE", "S03P02-BASE-CHINESE-UI-GATE", "S03P02-BASE-ONE-CARD-PER-DATE", "S03P02-DUPLICATE-DAILY-CARD-REJECTED"]:
                _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            no_card = build_advice_card(no_base, schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
            no_errors = validate_card(no_card, schema=schema, glossary=glossary, policy=policy)
            no_answers = extract_primary_answers(no_card)
            _add(checks, "S03P02-BASE-NO-RECOMMENDATION-VALID", not no_errors, no_errors or no_card["card_id"])
            _add(checks, "S03P02-BASE-NO-RECOMMENDATION-STATUS", no_card.get("status") == "NO_RECOMMENDATION" and no_card.get("action", {}).get("action_type") == "NO_ACTION", no_card.get("action"))
            _add(checks, "S03P02-BASE-NO-RECOMMENDATION-FOUR-ANSWERS", no_answers == {"what_zh": "不下单", "where_zh": "无需前往平台", "amount_zh": "A$0.00", "minimum_odds_zh": "不适用"}, no_answers)
        except Exception as exc:
            for check_id in ["S03P02-BASE-NO-RECOMMENDATION-VALID", "S03P02-BASE-NO-RECOMMENDATION-STATUS", "S03P02-BASE-NO-RECOMMENDATION-FOUR-ANSWERS"]:
                _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

        for vector in fixtures.get("boundary_vectors", []):
            vector_id = vector.get("id", "UNKNOWN")
            try:
                candidate = _merge_input(base, vector.get("overrides", {}))
                candidate["vector_id"] = "BOUNDARY-%s" % vector_id
                card = build_advice_card(candidate, schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
                errors = validate_card(card, schema=schema, glossary=glossary, policy=policy)
                replay = build_advice_card(copy.deepcopy(candidate), schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
                _add(checks, "S03P02-BOUNDARY-%s-STATUS" % vector_id, card.get("status") == vector.get("expected_status"), card.get("status"))
                _add(checks, "S03P02-BOUNDARY-%s-COUNTDOWN" % vector_id, card.get("countdown", {}).get("state") == vector.get("expected_countdown_state"), card.get("countdown"))
                _add(checks, "S03P02-BOUNDARY-%s-VALID" % vector_id, not errors, errors or card.get("card_id"))
                _add(checks, "S03P02-BOUNDARY-%s-REPLAY" % vector_id, card == replay, card.get("provenance"))
                _add(checks, "S03P02-BOUNDARY-%s-NO-AUTO-ORDER" % vector_id, card.get("safety", {}).get("auto_order_enabled") is False, card.get("safety"))
            except Exception as exc:
                for suffix in ["STATUS", "COUNTDOWN", "VALID", "REPLAY", "NO-AUTO-ORDER"]:
                    _add(checks, "S03P02-BOUNDARY-%s-%s" % (vector_id, suffix), False, "%s: %s" % (type(exc).__name__, exc))

        for vector in fixtures.get("gate_failure_vectors", []):
            vector_id = vector.get("id", "UNKNOWN")
            candidate = copy.deepcopy(base)
            candidate["vector_id"] = "GATE-%s" % vector_id
            if vector.get("gate") in candidate.get("gates", {}):
                candidate["gates"][vector["gate"]] = False
            try:
                card = build_advice_card(candidate, schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
                errors = validate_card(card, schema=schema, glossary=glossary, policy=policy)
                _add(checks, "S03P02-GATE-%s-DOWNGRADES" % vector_id, card.get("status") == "NO_RECOMMENDATION", card.get("status"))
                _add(checks, "S03P02-GATE-%s-NO-ACTION" % vector_id, card.get("action", {}).get("action_type") == "NO_ACTION" and card.get("action", {}).get("stake_cents") == 0, card.get("action"))
                _add(checks, "S03P02-GATE-%s-VALID" % vector_id, not errors, errors or card.get("card_id"))
            except Exception as exc:
                for suffix in ["DOWNGRADES", "NO-ACTION", "VALID"]:
                    _add(checks, "S03P02-GATE-%s-%s" % (vector_id, suffix), False, "%s: %s" % (type(exc).__name__, exc))

        for vector in fixtures.get("malformed_input_vectors", []):
            vector_id = vector.get("id", "UNKNOWN")
            candidate = copy.deepcopy(base)
            candidate["vector_id"] = "MALFORMED-%s" % vector_id
            candidate[vector.get("path")] = vector.get("replacement")
            try:
                build_advice_card(candidate, schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
                strict_rejected = False
                strict_detail: Any = "unexpectedly accepted"
            except Exception as exc:
                strict_rejected = True
                strict_detail = "%s: %s" % (type(exc).__name__, exc)
            safe = safe_build_advice_card(candidate, schema=schema, glossary=glossary, policy=policy, parameters_sha256=parameters_sha, model_sha256=model_sha)
            safe_errors = validate_card(safe, schema=schema, glossary=glossary, policy=policy)
            _add(checks, "S03P02-MALFORMED-%s-STRICT-REJECT" % vector_id, strict_rejected, strict_detail)
            _add(checks, "S03P02-MALFORMED-%s-FAIL-CLOSED" % vector_id, safe.get("status") == "NO_RECOMMENDATION" and safe.get("action", {}).get("action_type") == "NO_ACTION", safe.get("action"))
            _add(checks, "S03P02-MALFORMED-%s-SAFE-CARD-VALID" % vector_id, not safe_errors, safe_errors or safe.get("card_id"))

        if recommendation:
            for vector in fixtures.get("invalid_rendered_card_mutations", []):
                vector_id = vector.get("id", "UNKNOWN")
                mutated = copy.deepcopy(recommendation)
                try:
                    _set_path(mutated, vector.get("path"), vector.get("replacement"))
                    errors = validate_card(mutated, schema=schema, glossary=glossary, policy=policy)
                    _add(checks, "S03P02-RENDERED-MUTATION-%s-REJECTED" % vector_id, bool(errors), errors)
                except Exception as exc:
                    _add(checks, "S03P02-RENDERED-MUTATION-%s-REJECTED" % vector_id, False, "%s: %s" % (type(exc).__name__, exc))
        _check_p03_not_started(root, checks, verify_git_history=_verify_git_history)
    else:
        _add(checks, "S03P02-CORE-ARTIFACTS-AVAILABLE", False, "one or more core artifacts unavailable")

    if require_external_reports and isinstance(fixtures, dict):
        for path, check_id, minimum_key in [
            (JUNIT_PATH, "S03P02-TARGETED-JUNIT", "minimum_targeted_pytest_cases"),
            (FULL_JUNIT_PATH, "S03P02-FULL-JUNIT", "minimum_full_pytest_cases"),
        ]:
            try:
                summary = _junit_summary(root / path)
                hashes[path.as_posix()] = sha256_file(root / path)
                _add(checks, check_id, summary["tests"] >= int(fixtures.get(minimum_key, 0)) and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0, summary)
            except Exception as exc:
                _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            report = strict_json_load(root / PACK_REPORT_PATH)
            hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
            _add(checks, "S03P02-PACK-REPORT", _pack_report_passes(report), report)
        except Exception as exc:
            _add(checks, "S03P02-PACK-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
        try:
            scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
            hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
            _add(checks, "S03P02-PAID-DEPENDENCY-SCAN", _paid_dependency_scan_passes(scan_text), scan_text.strip())
        except Exception as exc:
            _add(checks, "S03P02-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))

    result = _build_result(checks, hashes)
    minimum = int(fixtures.get("expected_oracle_check_minimum", 0)) if isinstance(fixtures, dict) else 0
    if result["summary"]["checks"] < minimum:
        _add(checks, "S03P02-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
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
    artifacts = [SCHEMA_PATH, FIXTURES_PATH, ORACLE_FIXTURE_PATH, P01_EVIDENCE_PATH, GLOSSARY_PATH]
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s03-p02-rollback-") as directory:
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
        "evidence_id": "EVD-S03-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_ADVICE_CARD_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        SCHEMA_PATH, FIXTURES_PATH, ORACLE_FIXTURE_PATH, TEST_PATH, GLOSSARY_PATH, FORBIDDEN_PATH,
        PARAMETERS_PATH, MODEL_CARD_PATH, P01_EVIDENCE_PATH, P01_ROLLBACK_PATH,
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"), Path("README.md"),
        Path("abd_acceptance/advice_card.py"), Path("abd_acceptance/terminology_governance.py"),
        Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
        Path("tests/__init__.py"), Path("tests/S03/__init__.py"),
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
            "schema_version": "1.0.0", "evidence_id": "EVD-S03-P02-ROLLBACK", "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False, "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "BLOCKED_FAIL_CLOSED"
        result["phase_status"] = "S03_P02_FAILED"
        result["next"] = "S03/P02_REMEDIATION_REQUIRED"
    input_hashes = _input_hashes(root)
    external_boundary = strict_json_load(root / ORACLE_FIXTURE_PATH)["expected_external_effect_boundary"]
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S03-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": "S03",
        "phase_id": "P02",
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "validation": result,
        "artifacts": {
            "ART-S03-P02-01": SCHEMA_PATH.as_posix(),
            "ART-S03-P02-02": FIXTURES_PATH.as_posix(),
        },
        "p01_delivery_prerequisite": {
            "evidence": P01_EVIDENCE_PATH.as_posix(),
            "evidence_sha256": PINNED_BASELINE_HASHES[P01_EVIDENCE_PATH.as_posix()],
            "rollback_sha256": PINNED_BASELINE_HASHES[P01_ROLLBACK_PATH.as_posix()],
            "fixed_clock": P01_FIXED_CLOCK,
            "status": "PASS",
            "decision": "S03_P01_EVIDENCE_VERIFIED",
        },
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes[PARAMETERS_PATH.as_posix()],
            "code": _current_code_hash(root),
            "model": input_hashes[MODEL_CARD_PATH.as_posix()],
            "model_not_executed_reason": "S03/P02 freezes a card schema and deterministic presentation model using synthetic fixtures; it executes no prediction model, provider interaction, deployment, order or return evaluation.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py --junitxml=machine/evidence/S03/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S03/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S03-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "external_effect_boundary": dict(external_boundary),
        "explicit_unknowns": [
            "S03/P02 freezes a machine schema and deterministic presentation model; no web, mobile, notification or browser interface has been implemented or deployed.",
            "The structural four-answer scan path is not a human ten-second timing study; human usability, accessibility and device validation remain S03/P04 work.",
            "S03/P03 full Chinese reason-code and unique-next-action matrix, S03/P04 accessibility work and the S03 whole-stage review have not started.",
            "All recommendation fixtures are synthetic contract vectors; no market, provider, account, quote, model, stake or order was selected or executed.",
            "TAB, Gmail, OVH and Cloudflare account, authorization, capacity and runtime states remain uninspected or unauthorized and fail closed.",
            "The 30% monthly compounding target remains falsifiable, unverified and not guaranteed; target shortfall cannot relax any gate.",
        ],
        "release_status": "NOT_READY_S03_P03_P04_AND_STAGE_REVIEW_REQUIRED",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P02"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-AC-S03-P02 row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S03/P03_READY_NOT_STARTED" if status == "PASS" else "S03/P02_REMEDIATION_REQUIRED"
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
    if relative == "abd_acceptance/advice_card.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    evolved = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return (
        evolved is not None
        and (root / relative).is_file()
        and sha256_file(root / relative) == evolved
    )


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
        line
        for line in listing.stdout.splitlines()
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
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S03P02-RECEIPT-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S03P02-RECEIPT-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, dict):
        unsigned = dict(evidence)
        decision_hash = unsigned.pop("decision_sha256", None)
        shape_ok = (
            evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S03-P02"
            and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == "S03" and evidence.get("phase_id") == "P02"
            and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS"
            and evidence.get("decision") == "ADVICE_CARD_INFORMATION_CONTRACT_FROZEN"
            and evidence.get("phase_status") == "S03_P02_PASS" and evidence.get("next") == "S03/P03_READY_NOT_STARTED"
            and evidence.get("artifacts") == {"ART-S03-P02-01": SCHEMA_PATH.as_posix(), "ART-S03-P02-02": FIXTURES_PATH.as_posix()}
            and decision_hash == _sha256_bytes(_json_bytes(unsigned))
        )
        _add(checks, "S03P02-RECEIPT-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = validation.get("status") == "PASS" and validation.get("decision") == "ADVICE_CARD_INFORMATION_CONTRACT_FROZEN" and validation.get("summary", {}).get("failed") == 0 and validation.get("next") == "S03/P03_READY_NOT_STARTED" and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S03P02-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        boundary = strict_json_load(root / ORACLE_FIXTURE_PATH).get("expected_external_effect_boundary")
        _add(checks, "S03P02-RECEIPT-NO-EXTERNAL-EFFECT", evidence.get("external_effect_boundary") == boundary, evidence.get("external_effect_boundary"))
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
        _add(checks, "S03P02-RECEIPT-SIGNED-INPUTS-CURRENT", not input_errors, input_errors or len(signed_inputs))
        reports = []
        validation_hashes = validation.get("hashes", {})
        for relative in [JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), PACK_REPORT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()]:
            expected = validation_hashes.get(relative)
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if expected != actual:
                reports.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S03P02-RECEIPT-REPORT-HASHES-CURRENT", not reports, reports or "all reports match")
        code_expected = evidence.get("hashes", {}).get("code")
        code_current = _current_code_hash(root)
        code_historical = _historical_code_hash(root, verify_git_history) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (
            code_expected == PINNED_PHASE_CODE_HASH
            and code_historical in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(
            checks,
            "S03P02-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {
                "expected": code_expected,
                "current": code_current,
                "historical_phase_commit": code_historical,
            },
        )
        _add(checks, "S03P02-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        portable = str(root) not in rendered and ("/" + "Users/") not in rendered and ("/private/" + "var/") not in rendered and ("file" + "://") not in rendered and ("C:" + "\\Users\\") not in rendered
        _add(checks, "S03P02-RECEIPT-NO-ABSOLUTE-LOCAL-PATH", portable, "portable" if portable else "local path found")
    else:
        for check_id in ["S03P02-RECEIPT-EVIDENCE-INTEGRITY", "S03P02-RECEIPT-VALIDATION-ALL-PASS", "S03P02-RECEIPT-NO-EXTERNAL-EFFECT", "S03P02-RECEIPT-SIGNED-INPUTS-CURRENT", "S03P02-RECEIPT-REPORT-HASHES-CURRENT", "S03P02-RECEIPT-CODE-HASH-CURRENT", "S03P02-RECEIPT-ROLLBACK-HASH-BINDING", "S03P02-RECEIPT-NO-ABSOLUTE-LOCAL-PATH"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, dict) and rollback.get("evidence_id") == "EVD-S03-P02-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and len(rollback.get("artifacts", {})) == 5 and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S03P02-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, dict) else "unavailable")
    try:
        rows = [json.loads(line) for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines() if line]
        matching = [row for row in rows if row.get("id") == "INDEX-AC-S03-P02"]
        index_ok = len(matching) == 1 and matching[0].get("status") == "PASS" and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and matching[0].get("artifact_sha256") == evidence_hash and matching[0].get("next") == "S03/P03_READY_NOT_STARTED"
        _add(checks, "S03P02-RECEIPT-EVIDENCE-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S03P02-RECEIPT-EVIDENCE-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        p01 = verify_p01_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S03P02-RECEIPT-P01-PREREQUISITE", p01.get("status") == "PASS", p01.get("summary"))
    except Exception as exc:
        _add(checks, "S03P02-RECEIPT-P01-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": "PHASE-DELIVERY-S03-P02",
        "status": "PASS" if not failed else "FAIL",
        "decision": "S03_P02_EVIDENCE_VERIFIED" if not failed else "S03_P02_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": sum(1 for row in checks if row["passed"]), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S03/P03_READY_NOT_STARTED" if not failed else "S03/P02_REMEDIATION_REQUIRED",
    }
