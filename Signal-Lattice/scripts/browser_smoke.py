#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def chromium_executable() -> str:
    configured = os.environ.get("SIGNAL_LATTICE_BROWSER_EXECUTABLE", "").strip()
    candidates = [
        configured,
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    for command in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        discovered = shutil.which(command)
        if discovered:
            return discovered
    raise RuntimeError("CHROMIUM_EXECUTABLE_NOT_FOUND")


def wait_ready(url: str, timeout: float = 20.0) -> None:
    end = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic only
            last = exc
        time.sleep(0.15)
    raise RuntimeError(f"SERVER_NOT_READY:{type(last).__name__ if last else 'UNKNOWN'}")


def _business_fixture(root: Path) -> dict[str, Any]:
    configured = json.loads((root / "config/business_lines.json").read_text(encoding="utf-8"))
    lines = configured.get("lines", [])
    slices = ("code_source", "ci", "deployment", "runtime", "entrypoint", "data", "backup", "monitoring", "self_heal")
    return {
        "scope": "PREBUILD_CONTRACT_FIXTURE_NOT_LIVE_STATUS_PROOF",
        "lines": [
            {
                "line_id": str(row["line_id"]),
                "cells": [
                    {
                        "slice_id": key,
                        "state": "NOT_EXECUTED_IN_TARGET_ENVIRONMENT",
                        "blocker": "TARGET_ENVIRONMENT_NOT_BOUND",
                        "next_action": "BIND_TARGET_ENVIRONMENT",
                        "measured": False,
                    }
                    for key in slices
                ],
            }
            for row in lines
        ],
    }


def _status_fixture() -> dict[str, Any]:
    # An empty prebuild shell must visibly fail closed as SYSTEM_BLOCKED. This is not
    # a valid investment recommendation and must never be accepted as a public release.
    return {
        "state": "DEGRADED",
        "minute_cycle": {
            "cycle_id": "prebuild-browser-fixture",
            "scheduled_for": "2026-07-31T00:00:00+00:00",
            "completed_at": None,
            "state": "FAILED",
            "recommendation": {
                "action": "SYSTEM_BLOCKED",
                "symbol": None,
                "market": None,
                "message": "预构建环境没有真实市场数据和完整 Skill 运行收据。",
                "reasons": ["PREBUILD_FIXTURE_NOT_LIVE_PROOF"],
                "valid_until": "2026-07-31T00:01:00+00:00",
                "next_cycle_at": "2026-07-31T00:01:00+00:00",
                "full_cycle_completed": False,
                "active_skill_count": 0,
                "completed_skill_count": 0,
                "failed_skill_count": 0,
                "candidate_symbol_count": 0,
                "evidence_refs": [],
                "per_symbol": [],
                "skill_judgements": [],
            },
        },
    }


def wait_for_empty_pipeline(page: Any, expected_line_count: int) -> None:
    page.wait_for_function(
        """expectedLineCount => {
            const title = document.querySelector('#decision-title');
            const skills = document.querySelector('#skill-list .empty-state');
            const candidates = document.querySelector('#candidate-list .empty-state');
            const rows = document.querySelectorAll('#business-matrix tbody tr');
            return title && title.dataset.action === 'SYSTEM_BLOCKED'
                && title.textContent.trim() === '系统未就绪'
                && skills && candidates && rows.length === expectedLineCount;
        }""",
        arg=expected_line_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Signal Lattice 北极星中文桌面与移动页面。")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    port = free_port()
    findings: list[str] = []
    console_errors: list[str] = []
    viewports = [
        {"name": "desktop", "width": 1440, "height": 1000},
        {"name": "mobile", "width": 390, "height": 844},
    ]
    results: list[dict[str, Any]] = []
    business_fixture = _business_fixture(root)
    status_fixture = _status_fixture()
    expected_line_count = len(business_fixture["lines"])

    with tempfile.TemporaryDirectory(prefix="signal-lattice-browser-") as tmp:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {
                "PYTHONHOME", "PYTHONPATH", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "GOOGLE_API_KEY", "GEMINI_API_KEY",
            }
        }
        env.update({
            "PYTHONPATH": str(root / "src"),
            "SIGNAL_LATTICE_STATE_DIR": str(Path(tmp) / "state"),
            "SIGNAL_LATTICE_ARTIFACT_DIR": str(Path(tmp) / "artifacts"),
            "SIGNAL_LATTICE_WEB_DIR": str(root / "web"),
            "SIGNAL_LATTICE_HOST": "127.0.0.1",
            "SIGNAL_LATTICE_PORT": str(port),
            "PYTHONHASHSEED": "0",
        })
        process = subprocess.Popen(
            [os.sys.executable, "-m", "signal_lattice.cli", "serve"],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            wait_ready(f"http://127.0.0.1:{port}/health/ready")
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=chromium_executable(),
                    args=["--no-sandbox"],
                )
                html_source = (root / "web/index.html").read_text(encoding="utf-8")
                html_fallback = re.sub(r'<link[^>]+href="/styles\.css"[^>]*>', "", html_source)
                html_fallback = re.sub(r'<script[^>]+src="/app\.js"[^>]*></script>', "", html_fallback)
                css_source = (root / "web/styles.css").read_text(encoding="utf-8")

                for viewport in viewports:
                    page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
                    local_errors: list[str] = []
                    page.on("console", lambda msg, bucket=local_errors: bucket.append(msg.text) if msg.type == "error" else None)
                    transport_mode = "HTTP_LOOPBACK"
                    try:
                        response = page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                        if response is None or not response.ok:
                            findings.append(f"HTTP_PAGE_FAILED:{viewport['name']}")
                        wait_for_empty_pipeline(page, expected_line_count)
                    except Exception as nav_exc:
                        if "ERR_BLOCKED_BY_ADMINISTRATOR" not in str(nav_exc):
                            raise
                        # Some execution sandboxes block browser navigation to loopback while urllib
                        # can still reach it. Render the exact first-party assets and stub only the
                        # deterministic API fixtures; no production result is claimed by this path.
                        transport_mode = "SET_CONTENT_FALLBACK_ENV_POLICY"
                        page.close()
                        local_errors.clear()
                        page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
                        page.on("console", lambda msg, bucket=local_errors: bucket.append(msg.text) if msg.type == "error" else None)
                        page.set_content(html_fallback, wait_until="domcontentloaded")
                        page.add_style_tag(content=css_source)
                        fixtures = {
                            "/api/v1/system/status": status_fixture,
                            "/api/v1/business-lines": business_fixture,
                        }
                        page.evaluate(
                            "fixtures => { window.fetch = async (path) => { const key = new URL(String(path), 'https://local.invalid').pathname; const body = fixtures[key] || {}; return {ok: Boolean(fixtures[key]), status: fixtures[key] ? 200 : 404, json: async () => body}; }; }",
                            fixtures,
                        )
                        page.add_script_tag(path=str(root / "web/app.js"))
                        wait_for_empty_pipeline(page, expected_line_count)

                    title = page.locator("#decision-title")
                    title.wait_for()
                    action = title.get_attribute("data-action") or ""
                    title_text = title.inner_text().strip()
                    if action != "SYSTEM_BLOCKED":
                        findings.append(f"EMPTY_PIPELINE_NOT_SYSTEM_BLOCKED:{viewport['name']}:{action}")
                    if title_text != "系统未就绪":
                        findings.append(f"SYSTEM_BLOCKED_LABEL_MISMATCH:{viewport['name']}:{title_text}")
                    if page.locator("nav.primary-nav a").count() != 9:
                        findings.append(f"NAV_COUNT:{viewport['name']}")
                    if page.locator("#business-matrix tbody tr").count() != expected_line_count:
                        findings.append(f"BUSINESS_LINE_COUNT:{viewport['name']}")
                    if page.locator("#skill-list .empty-state").count() != 1:
                        findings.append(f"EMPTY_SKILL_STATE_NOT_EXPLICIT:{viewport['name']}")
                    if page.locator("#candidate-list .empty-state").count() != 1:
                        findings.append(f"EMPTY_CANDIDATE_STATE_NOT_EXPLICIT:{viewport['name']}")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
                    )
                    if overflow:
                        findings.append(f"PAGE_HORIZONTAL_OVERFLOW:{viewport['name']}")
                    smallest = page.evaluate(
                        "Math.min(...Array.from(document.querySelectorAll('nav.primary-nav a')).map(x => x.getBoundingClientRect().height))"
                    )
                    if float(smallest) < 44:
                        findings.append(f"TOUCH_TARGET_LT_44:{viewport['name']}")
                    if page.locator(".skip-link").count() != 1:
                        findings.append(f"SKIP_LINK_MISSING:{viewport['name']}")
                    if local_errors:
                        console_errors.extend(f"{viewport['name']}:{item}" for item in local_errors)
                    results.append({
                        "viewport": viewport,
                        "transport_mode": transport_mode,
                        "empty_pipeline_action": action,
                        "decision_title": title_text,
                        "nav_count": page.locator("nav.primary-nav a").count(),
                        "business_line_count": page.locator("#business-matrix tbody tr").count(),
                        "expected_business_line_count": expected_line_count,
                        "page_overflow": bool(overflow),
                        "minimum_nav_target_height": float(smallest),
                        "console_error_count": len(local_errors),
                    })
                    page.close()
                browser.close()
        except Exception as exc:
            findings.append(f"BROWSER_SMOKE_EXCEPTION:{type(exc).__name__}:{str(exc)[:240]}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    findings.extend(f"CONSOLE_ERROR:{item}" for item in console_errors)
    receipt: dict[str, Any] = {
        "schema_version": "2.0.0",
        "state": "PASS" if not findings else "FAIL",
        "browser": "chromium",
        "scope": "NORTH_STAR_UI_EMPTY_PIPELINE_FAIL_CLOSED_DESKTOP_AND_MOBILE",
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "results": results,
        "findings": sorted(set(findings)),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": receipt["state"], "receipt_sha256": receipt["receipt_sha256"]}, ensure_ascii=False))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
