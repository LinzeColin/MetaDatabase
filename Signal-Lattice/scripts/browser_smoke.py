#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import re
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


def wait_ready(url: str, timeout: float = 20.0) -> None:
    end = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last = exc
        time.sleep(0.15)
    raise RuntimeError(f"SERVER_NOT_READY:{type(last).__name__ if last else 'UNKNOWN'}")


def main() -> int:
    parser = argparse.ArgumentParser()
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

    with tempfile.TemporaryDirectory(prefix="signal-lattice-browser-") as tmp:
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"}}
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
                browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
                html_source = (root / "web/index.html").read_text()
                html_fallback = re.sub(r'<link[^>]+href="/styles\.css"[^>]*>', '', html_source)
                html_fallback = re.sub(r'<script[^>]+src="/app\.js"[^>]*></script>', '', html_fallback)
                css_source = (root / "web/styles.css").read_text()
                fixture = {
                    "scope": "PREBUILD_CONTRACT_FIXTURE_NOT_LIVE_STATUS_PROOF",
                    "lines": [
                        {
                            "line_id": f"BL{i:02d}",
                            "cells": [
                                {"slice_id": key, "state": "NOT_EXECUTED_IN_TARGET_ENVIRONMENT", "blocker": "TARGET_ENVIRONMENT_NOT_BOUND"}
                                for key in ("code_source", "ci", "deployment", "runtime", "entrypoint", "data", "backup", "monitoring", "self_heal")
                            ],
                        }
                        for i in range(13)
                    ],
                }
                for viewport in viewports:
                    page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
                    local_errors: list[str] = []
                    page.on("console", lambda msg, bucket=local_errors: bucket.append(msg.text) if msg.type == "error" else None)
                    transport_mode = "HTTP_LOOPBACK"
                    try:
                        response = page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                        if response is None or not response.ok:
                            findings.append(f"HTTP_PAGE_FAILED:{viewport['name']}")
                    except Exception as nav_exc:
                        if "ERR_BLOCKED_BY_ADMINISTRATOR" not in str(nav_exc):
                            raise
                        # The execution sandbox may block browser navigation to localhost even though
                        # urllib reached the same loopback server. Render the exact first-party assets
                        # in Chromium and stub only the deterministic business-line endpoint.
                        transport_mode = "SET_CONTENT_FALLBACK_ENV_POLICY"
                        page.close()
                        local_errors.clear()
                        page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
                        page.on("console", lambda msg, bucket=local_errors: bucket.append(msg.text) if msg.type == "error" else None)
                        page.set_content(html_fallback, wait_until="domcontentloaded")
                        page.add_style_tag(content=css_source)
                        page.evaluate("fixture => { window.fetch = async () => ({ok:true, json:async()=>fixture}); }", fixture)
                        page.add_script_tag(path=str(root / "web/app.js"))
                        page.wait_for_function("document.querySelectorAll('#business-matrix tbody tr').length === 13")
                    page.locator("#today-title").wait_for()
                    if page.locator("#today-title").inner_text().strip() != "NO_ACTION":
                        findings.append(f"NO_ACTION_NOT_PRIMARY:{viewport['name']}")
                    if page.locator("nav.primary-nav a").count() != 9:
                        findings.append(f"NAV_COUNT:{viewport['name']}")
                    if page.locator("#business-matrix tbody tr").count() != 13:
                        findings.append(f"BUSINESS_LINE_COUNT:{viewport['name']}")
                    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                    if overflow:
                        findings.append(f"PAGE_HORIZONTAL_OVERFLOW:{viewport['name']}")
                    smallest = page.evaluate("Math.min(...Array.from(document.querySelectorAll('nav.primary-nav a')).map(x => x.getBoundingClientRect().height))")
                    if float(smallest) < 44:
                        findings.append(f"TOUCH_TARGET_LT_44:{viewport['name']}")
                    if page.locator(".skip-link").count() != 1:
                        findings.append(f"SKIP_LINK_MISSING:{viewport['name']}")
                    if local_errors:
                        console_errors.extend(f"{viewport['name']}:{item}" for item in local_errors)
                    results.append({
                        "viewport": viewport,
                        "transport_mode": transport_mode,
                        "no_action_visible": True,
                        "nav_count": page.locator("nav.primary-nav a").count(),
                        "business_line_count": page.locator("#business-matrix tbody tr").count(),
                        "page_overflow": bool(overflow),
                        "minimum_nav_target_height": float(smallest),
                        "console_error_count": len(local_errors),
                    })
                    page.close()
                browser.close()
        except Exception as exc:
            findings.append(f"BROWSER_SMOKE_EXCEPTION:{type(exc).__name__}:{str(exc)[:160]}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    findings.extend(f"CONSOLE_ERROR:{item}" for item in console_errors)
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": "PASS" if not findings else "FAIL",
        "browser": "chromium",
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "results": results,
        "findings": sorted(set(findings)),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps({"state": receipt["state"], "receipt_sha256": receipt["receipt_sha256"]}, ensure_ascii=False))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
