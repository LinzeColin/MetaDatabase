from __future__ import annotations

import ast
import copy
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .terminology_governance import scan_ui_text


CONTRACT_ID = "AC-S13-P01"
REQUIREMENT_ID = "REQ-S13-P01"
STAGE_ID = "S13"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"

UI_FIXTURES_PATH = Path("ui_fixtures.json")
WEBAPP_PATH = Path("webapp/index.html")
WEBAPP_STYLE_PATH = Path("webapp/app.css")
PUSH_SERVICE_PATH = Path("push_service.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S13_P01.json")
TEST_PATH = Path("tests/S13/P01_test.py")
GLOSSARY_PATH = Path("glossary_zh.json")
FORBIDDEN_PATH = Path("forbidden_ui_terms.json")
JUNIT_PATH = Path("machine/evidence/S13/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S13/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

_PREDECESSORS = (
    Path("machine/evidence/EVD-S03-P04.json"),
    Path("machine/evidence/EVD-S11-P04.json"),
    Path("machine/evidence/EVD-S12-P04.json"),
)
_FACT_PATHS = (
    Path("machine/facts/canonical_facts.json"),
    Path("machine/facts/parameters.json"),
    Path("machine/facts/requirements.json"),
    Path("machine/facts/acceptance_contracts.json"),
    Path("machine/facts/task_graph.json"),
    Path("machine/facts/traceability_matrix.json"),
    Path("machine/facts/roadmap.json"),
)
_BOUNDARY = {
    "external_network_accessed": False,
    "external_push_sent": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_account_accessed": False,
    "real_time_soak_waited": False,
}
_PANEL_ORDER = ("覆盖", "风险", "目标", "系统健康")


class ChineseWorkbenchError(ValueError):
    """Raised when the Chinese workbench contract cannot be replayed safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, relative.as_posix())
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ChineseWorkbenchError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ChineseWorkbenchError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise ChineseWorkbenchError("blank evidence-index row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ChineseWorkbenchError("evidence-index row %d is not an object" % number)
        rows.append(value)
    return rows


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _contains_chinese(value: Any) -> bool:
    return isinstance(value, str) and re.search(r"[\u3400-\u9fff]", value) is not None


def _ui_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or not _contains_chinese(value):
        raise ChineseWorkbenchError("%s must be a non-empty Chinese visible string" % field)
    return value


def _validate_panel(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"level", "status_zh", "detail_zh"}:
        raise ChineseWorkbenchError("%s has an invalid panel shape" % field)
    level = value.get("level")
    if level not in {"GREEN", "AMBER", "RED", "GREY"}:
        raise ChineseWorkbenchError("%s level is not closed" % field)
    return {
        "level": level,
        "status_zh": _ui_string(value.get("status_zh"), "%s.status_zh" % field),
        "detail_zh": _ui_string(value.get("detail_zh"), "%s.detail_zh" % field),
    }


def _validate_primary_card(value: Any, field: str) -> Dict[str, Any]:
    expected = {
        "headline_zh",
        "detail_zh",
        "owner_action_zh",
        "action_count",
        "action_enabled",
        "action_label_zh",
        "evidence_refs",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ChineseWorkbenchError("%s has an invalid primary-card shape" % field)
    if value.get("action_count") != 1 or type(value.get("action_count")) is not int:
        raise ChineseWorkbenchError("%s must preserve exactly one primary action slot" % field)
    if value.get("action_enabled") is not False:
        raise ChineseWorkbenchError("%s must not enable an external action in this phase" % field)
    refs = value.get("evidence_refs")
    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
        raise ChineseWorkbenchError("%s evidence references must be unique and non-empty" % field)
    if not all(isinstance(item, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{2,127}", item) for item in refs):
        raise ChineseWorkbenchError("%s contains an invalid evidence reference" % field)
    return {
        "headline_zh": _ui_string(value.get("headline_zh"), "%s.headline_zh" % field),
        "detail_zh": _ui_string(value.get("detail_zh"), "%s.detail_zh" % field),
        "owner_action_zh": _ui_string(value.get("owner_action_zh"), "%s.owner_action_zh" % field),
        "action_count": 1,
        "action_enabled": False,
        "action_label_zh": _ui_string(value.get("action_label_zh"), "%s.action_label_zh" % field),
        "evidence_refs": list(refs),
    }


def _validate_push(value: Any, field: str) -> Dict[str, Any]:
    expected = {"title_zh", "body_zh", "delivery_mode", "external_delivery_performed"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ChineseWorkbenchError("%s has an invalid push shape" % field)
    if value.get("delivery_mode") != "LOCAL_RENDER_ONLY_NO_EXTERNAL_PUSH":
        raise ChineseWorkbenchError("%s delivery mode must stay local" % field)
    if value.get("external_delivery_performed") is not False:
        raise ChineseWorkbenchError("%s must not report an external delivery" % field)
    return {
        "title_zh": _ui_string(value.get("title_zh"), "%s.title_zh" % field),
        "body_zh": _ui_string(value.get("body_zh"), "%s.body_zh" % field),
        "delivery_mode": "LOCAL_RENDER_ONLY_NO_EXTERNAL_PUSH",
        "external_delivery_performed": False,
    }


def validate_ui_fixture(value: Any) -> Dict[str, Any]:
    expected = {
        "schema_version",
        "fixture_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "claim_boundary",
        "default_view_id",
        "views",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ChineseWorkbenchError("ui fixture keys are not closed")
    if value.get("schema_version") != "1.0.0" or value.get("product_version") != VERSION:
        raise ChineseWorkbenchError("ui fixture version is not frozen")
    if not isinstance(value.get("fixture_id"), str) or not value["fixture_id"].startswith("FIX-S13-P01-"):
        raise ChineseWorkbenchError("ui fixture id is invalid")
    if value.get("fixed_clock") != FIXED_CLOCK:
        raise ChineseWorkbenchError("ui fixture clock is not frozen")
    if value.get("input_mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT":
        raise ChineseWorkbenchError("ui fixture input mode is not safe")
    if value.get("claim_boundary") != _BOUNDARY:
        raise ChineseWorkbenchError("ui fixture claim boundary differs from the phase boundary")
    if _contains_float(value):
        raise ChineseWorkbenchError("ui fixture must not contain binary floats")
    views = value.get("views")
    if not isinstance(views, list) or len(views) != 3:
        raise ChineseWorkbenchError("ui fixture must contain exactly three deterministic views")
    seen: set[str] = set()
    normalized: list[Dict[str, Any]] = []
    for index, item in enumerate(views):
        fields = {"view_id", "mode", "synthetic_test_only", "primary_card", "coverage", "risk", "target", "system_health", "push"}
        if not isinstance(item, Mapping) or set(item) != fields:
            raise ChineseWorkbenchError("view %d keys are not closed" % index)
        view_id = item.get("view_id")
        if not isinstance(view_id, str) or not re.fullmatch(r"S13-P01-[A-Z0-9-]{3,64}", view_id) or view_id in seen:
            raise ChineseWorkbenchError("view %d id is invalid or duplicated" % index)
        seen.add(view_id)
        if item.get("mode") not in {"NO_RECOMMENDATION", "SYNTHETIC_PREVIEW", "DEGRADED"}:
            raise ChineseWorkbenchError("view %s mode is not closed" % view_id)
        if item.get("synthetic_test_only") is not True:
            raise ChineseWorkbenchError("view %s must be marked synthetic_test_only" % view_id)
        normalized.append(
            {
                "view_id": view_id,
                "mode": item["mode"],
                "synthetic_test_only": True,
                "primary_card": _validate_primary_card(item.get("primary_card"), "view[%s].primary_card" % view_id),
                "coverage": _validate_panel(item.get("coverage"), "view[%s].coverage" % view_id),
                "risk": _validate_panel(item.get("risk"), "view[%s].risk" % view_id),
                "target": _validate_panel(item.get("target"), "view[%s].target" % view_id),
                "system_health": _validate_panel(item.get("system_health"), "view[%s].system_health" % view_id),
                "push": _validate_push(item.get("push"), "view[%s].push" % view_id),
            }
        )
    if value.get("default_view_id") not in seen:
        raise ChineseWorkbenchError("default view is missing")
    return {
        "schema_version": "1.0.0",
        "fixture_id": value["fixture_id"],
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "claim_boundary": dict(_BOUNDARY),
        "default_view_id": value["default_view_id"],
        "views": normalized,
    }


def _view_by_id(validated: Mapping[str, Any], view_id: str | None = None) -> Mapping[str, Any]:
    selected = view_id if view_id is not None else validated["default_view_id"]
    matches = [item for item in validated["views"] if item["view_id"] == selected]
    if len(matches) != 1:
        raise ChineseWorkbenchError("requested view does not exist")
    return matches[0]


def build_workbench_model(value: Any, *, view_id: str | None = None) -> Dict[str, Any]:
    validated = validate_ui_fixture(value)
    selected = _view_by_id(validated, view_id)
    panels = [
        {"title_zh": "覆盖", **selected["coverage"]},
        {"title_zh": "风险", **selected["risk"]},
        {"title_zh": "目标", **selected["target"]},
        {"title_zh": "系统健康", **selected["system_health"]},
    ]
    return {
        "schema_version": "1.0.0",
        "view_id": selected["view_id"],
        "mode": selected["mode"],
        "synthetic_test_only": True,
        "fixed_clock": validated["fixed_clock"],
        "primary_card": dict(selected["primary_card"]),
        "panels": panels,
        "push": dict(selected["push"]),
        "claim_boundary": dict(_BOUNDARY),
    }


def build_local_push_payload(value: Any, *, view_id: str | None = None) -> Dict[str, Any]:
    model = build_workbench_model(value, view_id=view_id)
    push = model["push"]
    return {
        "schema_version": "1.0.0",
        "view_id": model["view_id"],
        "delivery_mode": push["delivery_mode"],
        "delivery_state_zh": "外部推送未启用",
        "title_zh": push["title_zh"],
        "body_zh": push["body_zh"],
        "primary_action_enabled": False,
        "external_delivery_performed": False,
        "order_submission_enabled": False,
        "synthetic_test_only": True,
    }


def render_workbench_html(model: Mapping[str, Any]) -> str:
    if not isinstance(model, Mapping) or model.get("claim_boundary") != _BOUNDARY:
        raise ChineseWorkbenchError("workbench model must preserve the claim boundary")
    primary = model.get("primary_card")
    panels = model.get("panels")
    if not isinstance(primary, Mapping) or not isinstance(panels, list) or [item.get("title_zh") for item in panels if isinstance(item, Mapping)] != list(_PANEL_ORDER):
        raise ChineseWorkbenchError("workbench model structure is invalid")
    esc = lambda item: html.escape(str(item), quote=True)
    panel_html = "".join(
        "<section class=\"panel level-%s\" aria-labelledby=\"panel-%d\">"
        "<h2 id=\"panel-%d\">%s</h2><p class=\"status\">%s</p><p>%s</p></section>"
        % (
            esc(panel["level"]).lower(),
            index,
            index,
            esc(panel["title_zh"]),
            esc(panel["status_zh"]),
            esc(panel["detail_zh"]),
        )
        for index, panel in enumerate(panels, start=1)
    )
    return """<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>全天候投注决策辅助系统中文工作台</title>
  <link rel=\"stylesheet\" href=\"app.css\">
</head>
<body>
  <main class=\"workbench\" aria-labelledby=\"page-title\">
    <header class=\"masthead\">
      <p class=\"eyebrow\">冻结合成验收界面</p>
      <h1 id=\"page-title\">全天候投注决策辅助系统中文工作台</h1>
      <p>当前页面只展示本地确定性状态，不连接真实账户、不发送外部推送，也不提交订单。</p>
    </header>
    <section class=\"primary-card\" aria-labelledby=\"current-advice\">
      <h2 id=\"current-advice\">当前建议</h2>
      <p class=\"headline\">%s</p>
      <p>%s</p>
      <p><strong>你需要做的事情：</strong>%s</p>
      <p class=\"action-disabled\" aria-live=\"polite\">%s</p>
    </section>
    <section class=\"panel-grid\" aria-label=\"覆盖、风险、目标和系统健康\">%s</section>
    <footer>状态来源：冻结测试夹具；外部访问与生产部署均未验证。</footer>
  </main>
</body>
</html>
""" % (
        esc(primary["headline_zh"]),
        esc(primary["detail_zh"]),
        esc(primary["owner_action_zh"]),
        esc(primary["action_label_zh"]),
        panel_html,
    )


def render_visible_text(model: Mapping[str, Any]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", render_workbench_html(model))).strip()


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S13P01-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S13P01-CONTRACTS-PARSE")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S13P01-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S13P01-TRACEABILITY-PARSE")
    roadmap = _safe_load(root, Path("machine/facts/roadmap.json"), checks, "S13P01-ROADMAP-PARSE")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(graph, Mapping) or not isinstance(traceability, list) or not isinstance(roadmap, Mapping):
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [item for item in graph.get("tasks", []) if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        stages = [item for item in roadmap.get("stages", []) if isinstance(item, Mapping) and item.get("id") == STAGE_ID]
        phase = next((item for item in stages[0].get("phases", []) if item.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
        expected_scope = ["webapp", "push_service.py", "ui_fixtures.json"]
        expected_tasks = ["T-S13-P01-01", "T-S13-P01-02", "T-S13-P01-03"]
        task_outputs = {output for task in tasks for output in task.get("outputs", [])}
        exact = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "手机/电脑任意地点可访问，界面中文。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == {
                "type": "EXECUTABLE",
                "command": "python -m abd_acceptance --contract AC-S13-P01 --evidence machine/evidence",
                "rule": "手机/电脑任意地点可访问，界面中文。",
            }
            and contract.get("pass_gate") == requirement.get("target")
            and phase.get("outputs") == expected_scope
            and phase.get("pass_gate") == requirement.get("target")
        )
        _add(checks, "S13P01-TASKPACK-EXACT", exact, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == expected_tasks
            and tasks[0].get("depends_on") == ["T-S03-P04-03", "T-S11-P04-03", "T-S12-P04-03"]
            and tasks[1].get("depends_on") == ["T-S13-P01-01"]
            and tasks[2].get("depends_on") == ["T-S13-P01-02"]
            and all(item in task_outputs for item in expected_scope + [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(), EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()])
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == expected_tasks
            and trace.get("test_ids") == ["TEST-S13-P01", "TEST-S13-P01-BOUNDARY", "TEST-S13-P01-REPLAY"]
            and trace.get("evidence_id") == "EVD-S13-P01"
            and trace.get("artifact_ids") == ["ART-S13-P01-01", "ART-S13-P01-02", "ART-S13-P01-03"]
        )
        _add(checks, "S13P01-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S13P01-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected = {
        _PREDECESSORS[0]: "AC-S03-P04",
        _PREDECESSORS[1]: "AC-S11-P04",
        _PREDECESSORS[2]: "AC-S12-P04",
    }
    for relative, contract_id in expected.items():
        evidence = _safe_load(root, relative, checks, "S13P01-PREDECESSOR-%s-PARSE" % contract_id)
        try:
            hashes[relative.as_posix()] = sha256_file(root / relative)
        except Exception:
            hashes[relative.as_posix()] = "MISSING"
        passed = isinstance(evidence, Mapping) and evidence.get("contract_id") == contract_id and evidence.get("status") == "PASS"
        _add(checks, "S13P01-PREDECESSOR-%s-SIGNED" % contract_id, passed, evidence.get("status") if isinstance(evidence, Mapping) else evidence)


def _check_chinese_ui(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    glossary = _safe_load(root, GLOSSARY_PATH, checks, "S13P01-GLOSSARY-PARSE")
    policy = _safe_load(root, FORBIDDEN_PATH, checks, "S13P01-FORBIDDEN-TERMS-PARSE")
    if not isinstance(glossary, Mapping) or not isinstance(policy, Mapping):
        return
    texts: list[str] = []
    for view in fixture["views"]:
        primary = view["primary_card"]
        texts.extend([primary["headline_zh"], primary["detail_zh"], primary["owner_action_zh"], primary["action_label_zh"]])
        for name in ("coverage", "risk", "target", "system_health"):
            panel = view[name]
            texts.extend([panel["status_zh"], panel["detail_zh"]])
        texts.extend([view["push"]["title_zh"], view["push"]["body_zh"]])
    violations = [
        {"text": text, "violations": scan_ui_text(text, "ADVICE_CARD", glossary, policy)}
        for text in texts
        if scan_ui_text(text, "ADVICE_CARD", glossary, policy)
    ]
    _add(checks, "S13P01-ALL-VISIBLE-FIXTURE-TEXT-PASSES-CHINESE-GATE", not violations, violations)


def _check_runtime(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S13P01-FIXTURE-PARSE")
    ui_fixture = _safe_load(root, UI_FIXTURES_PATH, checks, "S13P01-UI-FIXTURE-PARSE")
    if not isinstance(fixture, Mapping) or not isinstance(ui_fixture, Mapping):
        return
    try:
        normalized = validate_ui_fixture(ui_fixture)
        model = build_workbench_model(normalized)
        payload = build_local_push_payload(normalized)
        expected_ids = fixture.get("expected_view_ids")
        contract_ok = (
            fixture.get("schema_version") == "1.0.0"
            and fixture.get("fixture_id") == "FIX-S13-P01-WORKBENCH"
            and fixture.get("ui_fixture_path") == UI_FIXTURES_PATH.as_posix()
            and fixture.get("expected_default_view_id") == normalized["default_view_id"]
            and expected_ids == [view["view_id"] for view in normalized["views"]]
            and fixture.get("expected_panel_order") == list(_PANEL_ORDER)
            and fixture.get("expected_default_push_payload") == payload
            and model["claim_boundary"] == _BOUNDARY
        )
        _add(checks, "S13P01-FROZEN-UI-AND-PUSH-REPLAY-EXACT", contract_ok, {"view_ids": expected_ids, "default": normalized["default_view_id"]})
        _check_chinese_ui(root, normalized, checks)
        static_html = (root / WEBAPP_PATH).read_text(encoding="utf-8")
        static_css = (root / WEBAPP_STYLE_PATH).read_text(encoding="utf-8")
        visible = render_visible_text(model)
        protocol_literals = ("http" + "://", "https" + "://")
        html_ok = (
            '<html lang="zh-CN">' in static_html
            and 'name="viewport" content="width=device-width, initial-scale=1"' in static_html
            and 'href="app.css"' in static_html
            and all(token in static_html for token in ["当前建议", "覆盖", "风险", "目标", "系统健康", model["primary_card"]["headline_zh"]])
            and all(token in visible for token in ["当前建议", "覆盖", "风险", "目标", "系统健康"])
            and all(item not in static_html for item in protocol_literals)
        )
        _add(checks, "S13P01-STATIC-CHINESE-WORKBENCH-SEMANTICS", html_ok, WEBAPP_PATH.as_posix())
        css_ok = (
            "@media (max-width: 720px)" in static_css
            and "@media (min-width: 721px)" in static_css
            and ".panel-grid" in static_css
            and ":focus-visible" in static_css
            and all(item not in static_css for item in protocol_literals)
        )
        _add(checks, "S13P01-MOBILE-DESKTOP-LOCAL-LAYOUT-CONTRACT", css_ok, WEBAPP_STYLE_PATH.as_posix())
        push_source = (root / PUSH_SERVICE_PATH).read_text(encoding="utf-8")
        push_ok = (
            payload.get("delivery_mode") == "LOCAL_RENDER_ONLY_NO_EXTERNAL_PUSH"
            and payload.get("external_delivery_performed") is False
            and payload.get("order_submission_enabled") is False
            and "build_local_push_payload" in push_source
        )
        _add(checks, "S13P01-LOCAL-PUSH-PAYLOAD-ONLY-NO-EXTERNAL-DELIVERY", push_ok, payload)
        for relative in (UI_FIXTURES_PATH, WEBAPP_PATH, WEBAPP_STYLE_PATH, PUSH_SERVICE_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/chinese_workbench.py")):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except Exception as exc:
        _add(checks, "S13P01-WORKBENCH-RUNNER", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtp" + "lib", "asyncio", "time", "random", "os"}
    prohibited_literals = {
        "sleep" + "(",
        "submit" + "_order",
        "retry" + "_order",
        "http" + "://",
        "https" + "://",
        "web" + "hook",
        "smtp" + "lib",
    }
    failures: list[Any] = []
    for relative in (Path("abd_acceptance/chinese_workbench.py"), PUSH_SERVICE_PATH):
        try:
            source = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as exc:
            failures.append({"path": relative.as_posix(), "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        prohibited = sorted(imports.intersection(prohibited_imports))
        literals = sorted(item for item in prohibited_literals if item in source)
        if prohibited or literals:
            failures.append({"path": relative.as_posix(), "imports": prohibited, "literals": literals})
    _add(checks, "S13P01-STATIC-NO-NETWORK-SOAK-ORDER-OR-EXTERNAL-PUSH", not failures, failures or "static boundary intact")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        scan = scan_dependency_budget(root)
        passed = scan.get("status") == "PASS" and scan.get("summary", {}).get("paid_or_unknown_dependencies") == 0
        _add(checks, "S13P01-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", passed, scan.get("summary"))
    except Exception as exc:
        _add(checks, "S13P01-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    }


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        cases = list(ET.parse(root / JUNIT_PATH).getroot().iter("testcase"))
        passed = summary["tests"] >= 12 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and all(case.attrib.get("time") == "0.000" for case in cases)
        _add(checks, "S13P01-TARGETED-JUNIT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S13P01-TARGETED-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S13P01-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S13P01-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S13P01-TASKPACK-REPORT-PARSE")
    _add(checks, "S13P01-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "CHINESE_WORKBENCH_AND_LOCAL_PUSH_CONTRACT_READY_PLATFORM_VALIDATION_AND_POST_ADVICE_EVIDENCE_REQUIRED" if passed else "S13/P01_BLOCKED",
        "next": "S13/P02_READY_NOT_STARTED" if passed else "S13/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "external_effect_boundary": dict(_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack_trace(root, checks)
    _check_predecessors(root, checks, hashes)
    _check_runtime(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in (UI_FIXTURES_PATH, WEBAPP_PATH, WEBAPP_STYLE_PATH, PUSH_SERVICE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_CHINESE_WORKBENCH_AND_LOCAL_PUSH_RESTORE_SIGNED_S03_S11_S12_PREDECESSORS_KEEP_ALL_EVIDENCE",
        "feature_flag_id": "ui:chinese_workbench_local_push",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [Path("abd_acceptance/chinese_workbench.py"), PUSH_SERVICE_PATH, UI_FIXTURES_PATH, WEBAPP_PATH, WEBAPP_STYLE_PATH, FIXTURE_PATH, TEST_PATH, GLOSSARY_PATH, FORBIDDEN_PATH, *_FACT_PATHS, *_PREDECESSORS]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "hashes": {
            "code": sha256_file(root / Path("abd_acceptance/chinese_workbench.py")),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S13/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S13/P01_test.py --junitxml=machine/evidence/S13/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S13/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S13-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"view_count": 3, "real_time_wait_performed": False},
        "external_effect_boundary": dict(_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S13_P01_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED",
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    if len(raw_lines) != len(rows):
        raise ChineseWorkbenchError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-AC-S13-P01",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S13/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = sum(row.get("id") == replacement["id"] for row in rows)
    if matches != 1:
        raise ChineseWorkbenchError("S13/P01 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ChineseWorkbenchError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ChineseWorkbenchError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/P02_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise ChineseWorkbenchError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "CHINESE_WORKBENCH_AND_LOCAL_PUSH_CONTRACT_READY_PLATFORM_VALIDATION_AND_POST_ADVICE_EVIDENCE_REQUIRED"
        and evidence.get("next") == "S13/P02_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == "ui:chinese_workbench_local_push"
        and rollback.get("external_state_changed") is False
    )
    if not valid:
        raise ChineseWorkbenchError("existing S13/P01 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/P02_READY_NOT_STARTED",
    }
