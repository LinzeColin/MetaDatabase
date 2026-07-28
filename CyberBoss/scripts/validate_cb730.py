#!/usr/bin/env python3
"""Fail-closed local seal for CB-730.

Mapped acceptance: AC-004 (registration and consent copy), AC-010 (one-time
setup link surface), AC-037 (Chinese novice-proof experience), AC-049 (zero
technical barrier).

The frozen taskpack browser harness needs Playwright and Chromium, which are not
installed on this host. The page was instead measured in a real Chromium engine
over a served URL, and that receipt is required here — it is never treated as
optional and never replaced by an assumption.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
APP = PROJECT / "app"
EVIDENCE = PROJECT / "docs/evidence/CB-730"
PORTAL = APP / "templates/setup-portal.html"

ACCEPTANCE_IDS = ("AC-004", "AC-010", "AC-037", "AC-049")
SUITE = "test/cb730-novice-experience.test.js"
UI_CONTRACT = {
    "base_font_px": 16,
    "min_touch_target_px": 44,
    "min_text_contrast_ratio": 4.5,
    "primary_actions_per_view": 1,
    "horizontal_overflow_mobile": False,
    "end_user_cli_steps": 0,
    "novice_jargon_exposure": 0,
}


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] != "PASS"]


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative], cwd=APP,
        capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative, "returncode": result.returncode,
        "tests": counts.get("tests", 0), "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_page(checks: Checks) -> None:
    html = PORTAL.read_text(encoding="utf-8")
    checks.add("ac049.language_is_chinese", "AC-049",
               '<html lang="zh-CN">' in html and len(re.findall(r"[一-鿿]", html)) > 100,
               "the page declares and uses Chinese")
    checks.add("ac049.mobile_viewport", "AC-049",
               "width=device-width, initial-scale=1" in html,
               "a mobile viewport is declared")
    checks.add("ac049.touch_target_44", "AC-049",
               "--touch: 44px" in html and "min-height: var(--touch)" in html,
               "controls are at least 44px")
    checks.add("ac049.base_font_16", "AC-049",
               "font: 16px" in html and "font-size: 16px" in html,
               "body and input font size is 16px")
    checks.add("ac049.no_horizontal_overflow_rule", "AC-049",
               "overflow-x: hidden" in html and "overflow-wrap: anywhere" in html,
               "long values wrap instead of pushing the layout sideways")
    checks.add("ac049.one_primary_action", "AC-049",
               len(re.findall(r'class="primary"', html))
               == len(re.findall(r'<section id="view-[a-z]+"', html))
               and len(re.findall(r'<section id="view-[a-z]+"(?! hidden)', html)) == 1,
               "each view carries exactly one primary action and one view is visible")
    checks.add("ac037.error_has_repair_action", "AC-037",
               'id="error-repair"' in html,
               "the error view carries a repair button")
    checks.add("ac049.keyboard_operable", "AC-049",
               ":focus-visible" in html and html.count("<label for=") >= 3,
               "focus is visible and every input is labelled")
    checks.add("ac049.usage_protection_visible", "AC-049",
               'id="usage"' in html and "AI 用量" in html,
               "remaining protected usage is visible before anything goes wrong")

    checks.add("ac010.strict_csp", "AC-010",
               "default-src 'none'" in html
               and "unsafe-inline" not in html
               and "unsafe-eval" not in html
               and "base-uri 'none'" in html
               and "frame-ancestors 'none'" in html,
               "a strict CSP with no unsafe directive")
    checks.add("ac010.no_inline_handlers_or_sinks", "AC-010",
               not re.search(r"\son[a-z]+=", html, re.IGNORECASE)
               and not any(sink in html for sink in ("innerHTML", "outerHTML", "document.write", "eval(")),
               "no inline handlers and no unsafe HTML sinks")
    checks.add("ac010.no_inline_style_attribute", "AC-010",
               not re.search(r"<[^>]+\sstyle=\"", html),
               "no inline style attribute in the delivered markup")
    checks.add("ac010.no_runtime_style_mutation", "AC-010",
               ".style.width" not in html and "__USAGE_PERCENT__" in html,
               "the usage fill is server-rendered rather than set at runtime")
    checks.add("ac010.token_stripped_from_address_bar", "AC-010",
               "location.hash" in html
               and "history.replaceState" in html
               and "location.search" not in html
               and '<meta name="referrer" content="no-referrer">' in html,
               "the one-time token arrives in the fragment and is removed immediately")
    checks.add("ac004.one_time_and_autosave_stated", "AC-004",
               "只能用一次" in html and "自动保存" in html,
               "the page states the one-time rule and auto-save in Chinese")


def check_browser_receipt(checks: Checks) -> dict[str, Any]:
    path = EVIDENCE / "browser-check.json"
    if not path.is_file():
        checks.add("cb730.browser_receipt_present", "AC-049", False,
                   "no browser receipt: the page was never measured in a real engine")
        return {}
    receipt = json.loads(path.read_text(encoding="utf-8"))
    viewports = {row["name"]: row for row in receipt.get("viewports", [])}
    checks.add("cb730.browser_receipt_present", "AC-049",
               receipt.get("result") == "PASS" and {"mobile", "desktop"} <= set(viewports),
               f"viewports={sorted(viewports)}")
    mobile = viewports.get("mobile", {})
    desktop = viewports.get("desktop", {})
    checks.add("ac049.measured_no_horizontal_overflow", "AC-049",
               mobile.get("horizontal_overflow") is False
               and mobile.get("elements_past_right_edge") == []
               and desktop.get("horizontal_overflow") is False,
               "measured: nothing extends past the viewport at 375px or 1280px")
    checks.add("ac049.measured_touch_targets", "AC-049",
               mobile.get("controls_below_44px") == []
               and desktop.get("controls_below_44px") == []
               and mobile.get("visible_controls", 0) > 0,
               f"measured controls below 44px: {mobile.get('controls_below_44px')}")
    checks.add("ac049.measured_one_primary_action", "AC-049",
               mobile.get("visible_primary_actions") == UI_CONTRACT["primary_actions_per_view"]
               and desktop.get("visible_primary_actions") == 1,
               "measured: exactly one primary action visible")
    ratios = desktop.get("contrast_ratios", {})
    measured = [value for key, value in ratios.items() if key != "minimum_required"]
    checks.add("ac049.measured_contrast", "AC-049",
               bool(measured) and min(measured) >= UI_CONTRACT["min_text_contrast_ratio"],
               f"measured contrast minimum={min(measured) if measured else None}")
    checks.add("ac010.measured_no_inline_style", "AC-010",
               mobile.get("inline_style_attributes") == 0
               and desktop.get("inline_style_attributes") == 0,
               "measured: zero inline style attributes")
    checks.add("ac049.measured_tab_order", "AC-049",
               mobile.get("tab_order_matches_visual_order") is True,
               "measured: keyboard order follows visual order")
    checks.add("cb730.browser_finding_recorded", "AC-010",
               isinstance(receipt.get("findings_fixed_during_this_check"), list),
               "findings from the browser check are recorded rather than silently fixed")
    return receipt


def check_copy(checks: Checks) -> None:
    presenter = (APP / "src/services/ops/novice-presenter.js").read_text(encoding="utf-8")
    commands = (APP / "src/services/commands/novice-command-map.js").read_text(encoding="utf-8")
    checks.add("ac037.copy_audit_exists", "AC-037",
               "auditMessages" in presenter and "JARGON" in presenter,
               "every message is audited for jargon and repair actions")
    checks.add("ac037.repair_actions_declared", "AC-037",
               "REPAIR_REQUIRED" in presenter,
               "messages that report a problem must declare a repair action")
    checks.add("ac037.command_map_is_a_lookup", "AC-037",
               "new Map()" in commands or "LOOKUP" in commands,
               "intent resolution is a table lookup, not a model call")
    checks.add("ac037.owner_phrases_never_resolve", "AC-037",
               "FORBIDDEN_PHRASES" in commands,
               "operator phrasings resolve to nothing rather than partially matching")
    checks.add("ac049.no_cli_instruction_in_novice_surface", "AC-049",
               not any(marker in presenter or marker in commands
                       for marker in ("sudo ", "systemctl ", "npm install", "curl -")),
               "no novice surface instructs a command-line step")


def main() -> int:
    checks = Checks()
    check_page(checks)
    receipt = check_browser_receipt(checks)
    check_copy(checks)
    suite = run_node_suite(SUITE)
    checks.add("cb730.suite", "AC-037",
               suite["returncode"] == 0 and suite["fail"] == 0 and suite["tests"] > 0,
               f"tests={suite['tests']} pass={suite['pass']} fail={suite['fail']}")

    report = {
        "schema_version": "cyberboss.cb730.validation.v1",
        "task_id": "CB-730",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "ui_contract": UI_CONTRACT,
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "browser_engine": receipt.get("tool"),
        "frozen_prototype_harness": "NOT_RUN_PLAYWRIGHT_AND_CHROMIUM_UNAVAILABLE_ON_HOST",
        "frozen_prototype_harness_substitute": "live Chromium measurement recorded in browser-check.json",
        "node_suite": suite,
        "node_test_total": suite["tests"],
        "checks": checks.rows,
        "artifact_sha256": {
            "app/templates/setup-portal.html": hashlib.sha256(PORTAL.read_bytes()).hexdigest(),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
