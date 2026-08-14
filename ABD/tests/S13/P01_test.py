from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.chinese_workbench import (
    ChineseWorkbenchError,
    build_local_push_payload,
    build_workbench_model,
    evaluate_contract,
    perform_rollback_drill,
    render_visible_text,
    render_workbench_html,
    validate_candidate_preflight,
    validate_ui_fixture,
    verify_existing_phase_evidence,
    write_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
UI_FIXTURE = json.loads((ROOT / "ui_fixtures.json").read_text(encoding="utf-8"))
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S13_P01.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _canonical_hash(value: object) -> str:
    return hashlib.sha256((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")).hexdigest()


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S13-P01"
    assert result["next"] == "S13/P02_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 12
    assert result["external_effect_boundary"]["external_push_sent"] is False
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False


def test_frozen_fixture_has_exactly_three_safe_views_and_one_primary_slot() -> None:
    normalized = validate_ui_fixture(UI_FIXTURE)
    assert [view["view_id"] for view in normalized["views"]] == FIXTURE["expected_view_ids"]
    assert normalized["default_view_id"] == FIXTURE["expected_default_view_id"]
    assert all(view["synthetic_test_only"] is True for view in normalized["views"])
    assert all(view["primary_card"]["action_count"] == 1 for view in normalized["views"])
    assert all(view["primary_card"]["action_enabled"] is False for view in normalized["views"])


def test_default_model_contains_all_required_chinese_panels() -> None:
    model = build_workbench_model(UI_FIXTURE)
    assert [panel["title_zh"] for panel in model["panels"]] == FIXTURE["expected_panel_order"]
    assert model["mode"] == "NO_RECOMMENDATION"
    assert model["primary_card"]["headline_zh"] == "当前不建议"
    assert model["claim_boundary"]["order_submission_enabled"] is False
    assert model["claim_boundary"]["production_deployed_or_activated"] is False


def test_local_push_payload_is_deterministic_and_never_delivers_externally() -> None:
    payloads = [build_local_push_payload(UI_FIXTURE) for _ in range(3)]
    assert payloads == [FIXTURE["expected_default_push_payload"]] * 3
    assert len({_canonical_hash(payload) for payload in payloads}) == 1
    assert payloads[0]["external_delivery_performed"] is False
    assert payloads[0]["order_submission_enabled"] is False


def test_html_renderer_has_chinese_semantics_and_no_external_endpoint() -> None:
    model = build_workbench_model(UI_FIXTURE)
    rendered = render_workbench_html(model)
    visible = render_visible_text(model)
    assert '<html lang="zh-CN">' in rendered
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in rendered
    assert all(label in visible for label in ["当前建议", "覆盖", "风险", "目标", "系统健康"])
    assert "<script" not in rendered
    assert "http://" not in rendered
    assert "https://" not in rendered


def test_push_service_only_builds_the_local_payload() -> None:
    source = (ROOT / "push_service.py").read_text(encoding="utf-8")
    payload = build_local_push_payload(UI_FIXTURE)
    assert payload == FIXTURE["expected_default_push_payload"]
    assert payload["delivery_mode"] == "LOCAL_RENDER_ONLY_NO_EXTERNAL_PUSH"
    assert payload["primary_action_enabled"] is False
    assert "build_local_push_payload" in source


def test_core_sources_have_no_network_soak_or_order_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "asyncio", "time", "random", "os"}
    for relative in ("abd_acceptance/chinese_workbench.py", "push_service.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not imports.intersection(prohibited)
        assert "sleep(" not in source
        assert "submit_order" not in source
        assert "retry_order" not in source
        assert "http://" not in source
        assert "https://" not in source


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture.update({"input_mode": "NETWORK"}),
        lambda fixture: fixture["claim_boundary"].update({"external_push_sent": True}),
        lambda fixture: fixture["views"][0]["primary_card"].update({"action_count": 2}),
        lambda fixture: fixture["views"][0]["primary_card"].update({"action_enabled": True}),
    ],
)
def test_unsafe_or_ambiguous_fixture_variants_fail_closed(mutate) -> None:
    fixture = deepcopy(UI_FIXTURE)
    mutate(fixture)
    with pytest.raises(ChineseWorkbenchError):
        validate_ui_fixture(fixture)


def test_candidate_fails_closed_when_static_workbench_loses_required_panel(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    page = clone / "webapp/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("系统健康", "状态"), encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S13P01-STATIC-CHINESE-WORKBENCH-SEMANTICS" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_does_not_change_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "ui:chinese_workbench_local_push"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_signing_replaces_only_the_p01_jsonl_row_and_replays(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    index_path = clone / "machine/evidence/evidence_index.jsonl"
    rows = index_path.read_text(encoding="utf-8").splitlines()
    planned_index = next(index for index, line in enumerate(rows) if json.loads(line).get("id") == "INDEX-AC-S13-P01")
    cases = "".join(
        '<testcase classname="tests.S13.P01_test" name="signer_fixture_%d" time="0.000" />' % index
        for index in range(12)
    )
    report_path = clone / "machine/evidence/S13/P01/pytest.xml"
    report_path.write_text('<?xml version="1.0" encoding="utf-8"?><testsuite tests="12" failures="0" errors="0" skipped="0">%s</testsuite>' % cases, encoding="utf-8")
    scan_path = clone / "machine/evidence/S13/P01/paid_dependency_scan.txt"
    scan_path.write_text(
        "STATUS: PASS\nMAX_INCREMENTAL_CASH_AUD: 0.00\nPAID_OR_UNKNOWN_DEPENDENCIES: 0\nEXTERNAL_NETWORK_ACCESS_PERFORMED: false\nEXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false\n",
        encoding="utf-8",
    )
    before = index_path.read_text(encoding="utf-8").splitlines()
    result = write_phase_evidence(clone, clone / "machine/evidence")
    after = index_path.read_text(encoding="utf-8").splitlines()
    changed = [index for index, (left, right) in enumerate(zip(before, after)) if left != right]
    assert result["status"] == "PASS"
    assert changed == [planned_index]
    assert json.loads(after[planned_index])["kind"] == "PHASE_EVIDENCE"
    assert verify_existing_phase_evidence(clone)["status"] == "PASS"


def test_acceptance_cli_is_wired_to_the_exact_contract_after_integration() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S13-P01": write_chinese_workbench_phase_evidence' in source
    assert '"AC-S13-P01": verify_chinese_workbench_phase_evidence' in source
    with pytest.raises((ChineseWorkbenchError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
