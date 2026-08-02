#!/usr/bin/env python3
"""Fail-closed production account E2E for WeRead Port v0.0.0.1.9.

This suite talks to the real production origin through the same browser, BFF,
account service, SQLite and R2 path used by users. It never prints credentials,
keys, cookies, note bodies or full account identifiers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, sync_playwright

VERSION = "v0.0.0.1.9"
REQUIRED_WEREAD_CAPABILITIES = {
    "/_list", "/shelf/sync", "/user/notebooks", "/book/bookmarklist",
    "/review/list/mine", "/book/info", "/book/getprogress",
    "/book/chapterinfo", "/readdata/detail", "/book/recommend",
}
OAUTH_HOSTS = {
    "google": "accounts.google.com",
    "github": "github.com",
    "notion": "api.notion.com",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def opaque(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def api(page: Page, path: str, *, method: str = "GET", body: Any = None, csrf: str = "", idempotency: str = "") -> dict[str, Any]:
    result = page.evaluate(
        """async ({path, method, body, csrf, idempotency}) => {
          const headers = {Accept: 'application/json'};
          if (body !== null) headers['Content-Type'] = 'application/json';
          if (csrf) headers['X-CSRF-Token'] = csrf;
          if (idempotency) headers['Idempotency-Key'] = idempotency;
          const response = await fetch('/api/platform/v1' + path, {
            method, credentials: 'include', headers,
            body: body === null ? undefined : JSON.stringify(body),
            redirect: 'manual'
          });
          const text = await response.text();
          let payload = {};
          try { payload = text ? JSON.parse(text) : {}; } catch { payload = {nonJson: true}; }
          return {status: response.status, ok: response.ok, payload};
        }""",
        {"path": path, "method": method, "body": body, "csrf": csrf, "idempotency": idempotency},
    )
    return result


def expect(result: dict[str, Any], status: int | set[int], label: str) -> dict[str, Any]:
    accepted = {status} if isinstance(status, int) else status
    if result.get("status") not in accepted:
        code = result.get("payload", {}).get("error", {}).get("code", "UNKNOWN")
        raise AssertionError(f"{label}: HTTP {result.get('status')} code={code}")
    return result.get("payload", {})


def open_origin(context: BrowserContext, url: str) -> Page:
    page = context.new_page()
    page.set_default_timeout(15_000)
    response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    if response is None or response.status >= 500:
        raise AssertionError(f"主页不可用：HTTP {response.status if response else 'NO_RESPONSE'}")
    if page.locator("#retry-service").count():
        detail = page.locator("#platform-main").inner_text()[:240]
        raise AssertionError(f"账户入口 fail-closed：{detail}")
    page.get_by_role("heading", name="一个账户，统一保存、同步和理解你的全部阅读笔记。").wait_for()
    return page


def register_password(page: Page, email: str, password: str, display: str) -> tuple[dict[str, Any], str]:
    payload = expect(api(page, "/auth/register/password", method="POST", body={"email": email, "password": password, "displayName": display}), 200, "密码注册")
    if not payload.get("account", {}).get("id") or not payload.get("csrf"):
        raise AssertionError("密码注册未返回账户或 CSRF")
    return payload["account"], payload["csrf"]


def login_password(page: Page, email: str, password: str) -> tuple[dict[str, Any], str]:
    payload = expect(api(page, "/auth/login/password", method="POST", body={"email": email, "password": password}), 200, "密码登录")
    if not payload.get("account", {}).get("id") or not payload.get("csrf"):
        raise AssertionError("密码登录未返回账户或 CSRF")
    return payload["account"], payload["csrf"]


def logout(page: Page, csrf: str) -> None:
    expect(api(page, "/auth/logout", method="POST", body={}, csrf=csrf), 200, "退出登录")
    expect(api(page, "/session"), 401, "退出后会话失效")


def delete_account(page: Page, csrf: str) -> None:
    expect(api(page, "/account/delete", method="POST", body={}, csrf=csrf), 200, "删除测试账户")


def wait_import(page: Page, job_id: str, *, timeout_seconds: int = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        payload = expect(api(page, f"/imports/jobs/{job_id}"), 200, "读取导入任务")
        last = payload.get("job") or {}
        if last.get("state") == "COMPLETE":
            return last
        if last.get("state") == "FAILED":
            raise AssertionError(f"Obsidian 导入失败：{last.get('errorCode', 'UNKNOWN')}")
        time.sleep(1.0)
    raise AssertionError(f"Obsidian 导入超时，最后状态={last.get('state') if last else 'UNKNOWN'}")


def wait_weread_sync(page: Page, job_id: str, *, timeout_seconds: int = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        payload = expect(api(page, f"/weread/sync/jobs/{job_id}"), 200, "读取微信读书同步任务")
        last = payload.get("job") or {}
        if last.get("state") == "COMPLETE":
            return last
        if last.get("state") == "FAILED":
            raise AssertionError(f"微信读书同步失败：{last.get('errorCode', 'UNKNOWN')}")
        time.sleep(1.0)
    raise AssertionError(f"微信读书同步超时，最后状态={last.get('state') if last else 'UNKNOWN'}")


def oauth_contract(page: Page) -> list[dict[str, Any]]:
    checks = []
    for provider, host in OAUTH_HOSTS.items():
        payload = expect(api(page, f"/oauth/{provider}/start?intent=login"), 200, f"{provider} OAuth 启动")
        value = payload.get("authorizationUrl")
        parsed = urlparse(value or "")
        if parsed.scheme != "https" or parsed.hostname != host:
            raise AssertionError(f"{provider} OAuth 目标不正确")
        query = parsed.query
        if "state=" not in query or "redirect_uri=" not in query:
            raise AssertionError(f"{provider} OAuth 缺少 state 或 callback")
        if provider in {"google", "github"} and "code_challenge=" not in query:
            raise AssertionError(f"{provider} OAuth 缺少 PKCE")
        checks.append({"provider": provider, "authorizationHost": host, "status": "PASS"})
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("WEREAD_PORT_SITE_URL", "https://weread.linzezhang.com"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM_PATH", ""))
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="仅验证账户、存储、隔离、导入、OAuth 与导出删除；不调用微信读书官方 gateway。",
    )
    args = parser.parse_args()
    origin = args.url.rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("生产地址必须是无凭据 HTTPS origin")
    weread_key = os.environ.get("WRP_E2E_WEREAD_KEY", "").strip()
    if not args.core_only and not weread_key:
        raise SystemExit("缺少 WRP_E2E_WEREAD_KEY；真实密钥链路不得跳过")
    domain = os.environ.get("WRP_E2E_EMAIL_DOMAIN", "linzezhang.com").strip().lower()
    if not domain or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for ch in domain):
        raise SystemExit("WRP_E2E_EMAIL_DOMAIN 无效")
    run_id = f"{int(time.time())}-{secrets.token_hex(4)}"
    email_a = f"weread-e2e-a+{run_id}@{domain}"
    email_b = f"weread-e2e-b+{run_id}@{domain}"
    password_a = f"A9!{secrets.token_urlsafe(24)}"
    password_b = f"B9!{secrets.token_urlsafe(24)}"
    note_external = f"production-e2e-{run_id}"
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "suite": "production-account-e2e",
        "scope": "core-account-e2e" if args.core_only else "formal-account-e2e",
        "taskpackVersion": VERSION,
        "origin": origin,
        "startedAt": utc_now(),
        "status": "FAIL",
        "checks": [],
    }
    account_a = account_b = None
    page_a = page_a2 = page_b = None
    csrf_a = csrf_a2 = csrf_b = csrf_current_a = ""
    cleanup_failures: list[str] = []
    chromium_args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if args.chromium:
        chromium_args["executable_path"] = args.chromium
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch(**chromium_args)
            try:
                context_a = browser.new_context(locale="zh-CN")
                page_a = open_origin(context_a, origin)
                account_a, csrf_a = register_password(page_a, email_a, password_a, "生产验收 A")
                report["checks"].append({"id": "register-password", "status": "PASS", "account": opaque(account_a["id"])})
                session = expect(api(page_a, "/session"), 200, "注册后会话")
                csrf_a = session["csrf"]
                logout(page_a, csrf_a)
                account_a_login, csrf_a = login_password(page_a, email_a, password_a)
                if account_a_login["id"] != account_a["id"]:
                    raise AssertionError("密码登录返回了不同账户")
                page_a.reload(wait_until="domcontentloaded")
                session = expect(api(page_a, "/session"), 200, "刷新后会话")
                csrf_a = session["csrf"]
                report["checks"].append({"id": "logout-login-refresh-session", "status": "PASS"})

                note_payload = expect(api(page_a, "/notes", method="POST", csrf=csrf_a, body={"source": "manual", "externalId": note_external, "title": "生产验收笔记", "content": "用于验证服务端长期存储、跨设备同步和租户隔离。", "category": "验收"}), 201, "创建生产验收笔记")
                note = note_payload["note"]
                report["checks"].append({"id": "server-note-create", "status": "PASS", "note": opaque(note["id"])})

                context_a2 = browser.new_context(locale="zh-CN")
                page_a2 = open_origin(context_a2, origin)
                account_a2, csrf_a2 = login_password(page_a2, email_a, password_a)
                if account_a2["id"] != account_a["id"]:
                    raise AssertionError("第二设备登录账户不一致")
                csrf_current_a = csrf_a2
                persisted = expect(api(page_a2, f"/notes/{note['id']}"), 200, "第二设备读取长期笔记")["note"]
                if persisted.get("content") != "用于验证服务端长期存储、跨设备同步和租户隔离。":
                    raise AssertionError("第二设备读取的笔记正文不一致")
                pulled = expect(api(page_a2, "/sync/pull", method="POST", csrf=csrf_a2, body={"cursor": 0, "limit": 500}), 200, "第二设备增量同步")
                if not any(event.get("entityId") == note["id"] for event in pulled.get("events", [])):
                    raise AssertionError("跨设备同步未包含新笔记")
                report["checks"].append({"id": "cross-device-persistence-sync", "status": "PASS"})

                context_b = browser.new_context(locale="zh-CN")
                page_b = open_origin(context_b, origin)
                account_b, csrf_b = register_password(page_b, email_b, password_b, "生产验收 B")
                expect(api(page_b, f"/notes/{note['id']}"), 404, "账户 B 不可读取账户 A 笔记")
                isolated = expect(api(page_b, "/sync/pull", method="POST", csrf=csrf_b, body={"cursor": 0, "limit": 500}), 200, "账户 B 同步隔离")
                if any(event.get("entityId") == note["id"] for event in isolated.get("events", [])):
                    raise AssertionError("跨租户同步泄漏")
                report["checks"].append({"id": "multi-tenant-isolation", "status": "PASS", "accountB": opaque(account_b["id"])})

                obsidian = {"items": [{"name": "新手导入示例.md", "path": "阅读/新手导入示例.md", "content": "# Obsidian 一键导入\n\n真实生产导入验收。"}], "sourceLabel": "生产验收文件", "totalFiles": 1}
                job_payload = expect(api(page_a2, "/imports/obsidian/start", method="POST", csrf=csrf_a2, idempotency=f"obsidian-{run_id}", body={"selection": obsidian}), 202, "Obsidian 一键导入启动")
                job = wait_import(page_a2, job_payload["job"]["id"])
                if int(job.get("progress", {}).get("saved", 0)) < 1:
                    raise AssertionError("Obsidian 导入未保存笔记")
                report["checks"].append({"id": "obsidian-one-click-import", "status": "PASS"})

                oauth_checks = oauth_contract(page_a2)
                report["checks"].extend({"id": f"oauth-start-{item['provider']}", **item} for item in oauth_checks)

                if args.core_only:
                    report["checks"].append({"id": "weread-key-login-wide-sync", "status": "NOT_RUN", "reason": "CORE_ONLY_MODE"})
                else:
                    expect(api(page_a2, "/auth/link/weread", method="POST", csrf=csrf_a2, body={"key": weread_key}), 200, "绑定微信读书密钥")
                    logout(page_a2, csrf_a2)
                    key_login = expect(api(page_a2, "/auth/login/weread", method="POST", body={"key": weread_key}), 200, "微信读书密钥登录")
                    if key_login.get("account", {}).get("id") != account_a["id"]:
                        raise AssertionError("密钥登录未返回绑定账户")
                    csrf_current_a = key_login["csrf"]
                    wide_start = expect(api(page_a2, "/weread/sync", method="POST", csrf=csrf_current_a, idempotency=f"weread-{run_id}", body={"recommendationPages": 3}), 202, "微信读书广范围同步任务启动")
                    wide = wait_weread_sync(page_a2, wide_start["job"]["id"])
                    progress = wide.get("progress") or {}
                    caps = set(progress.get("capabilities") or [])
                    if caps and not REQUIRED_WEREAD_CAPABILITIES.issubset(caps):
                        raise AssertionError("真实微信读书能力范围缺失关键接口")
                    coverage = progress.get("coverage") or {}
                    if coverage.get("legacyTop5CeilingRemoved") is not True or int(coverage.get("detailedBooks") or 0) <= 5:
                        raise AssertionError("真实微信读书读取仍未证明突破 Top 5")
                    report["checks"].append({"id": "weread-key-login-wide-sync", "status": "PASS", "detailedBooks": int(coverage.get("detailedBooks") or 0), "capabilityCount": int(coverage.get("capabilityCount") or 0)})

                dashboard = expect(api(page_a2, "/analytics/dashboard"), 200, "读取画像与行为可视化")["dashboard"]
                if not dashboard.get("summary") or not isinstance(dashboard.get("noteActivityHeatmap"), list) or not isinstance(dashboard.get("recommendations"), list):
                    raise AssertionError("画像、笔记活动或潜在推荐结构缺失")
                if not args.core_only and not isinstance(dashboard.get("officialReading"), dict):
                    raise AssertionError("微信读书官方阅读统计结构缺失")
                report["checks"].append({"id": "profile-behavior-visualization", "status": "PASS", "recommendations": len(dashboard.get("recommendations", []))})

                export = expect(api(page_a2, "/account/export"), 200, "导出账户")
                if not isinstance(export.get("notes"), list):
                    raise AssertionError("账户导出缺少笔记")
                delete_account(page_b, csrf_b)
                account_b = None
                delete_account(page_a2, csrf_current_a)
                account_a = None
                report["checks"].append({"id": "export-delete-cleanup", "status": "PASS"})

                context_b.close(); context_a2.close(); context_a.close()
            finally:
                if account_b is not None:
                    try:
                        if page_b is None or not csrf_b:
                            raise AssertionError("账户 B 缺少可用清理会话")
                        delete_account(page_b, csrf_b)
                        account_b = None
                    except Exception as error:
                        cleanup_failures.append(f"account_b:{type(error).__name__}")
                if account_a is not None:
                    try:
                        cleanup_page = page_a2 or page_a
                        cleanup_csrf = csrf_current_a or csrf_a2 or csrf_a
                        if cleanup_page is None:
                            raise AssertionError("账户 A 缺少可用清理页面")
                        try:
                            if not cleanup_csrf:
                                raise AssertionError("账户 A 缺少可用清理会话")
                            delete_account(cleanup_page, cleanup_csrf)
                        except Exception:
                            _, cleanup_csrf = login_password(cleanup_page, email_a, password_a)
                            delete_account(cleanup_page, cleanup_csrf)
                        account_a = None
                    except Exception as error:
                        cleanup_failures.append(f"account_a:{type(error).__name__}")
                report["cleanup"] = {
                    "status": "FAILED" if cleanup_failures else "PASS",
                    "failures": cleanup_failures,
                }
                browser.close()
        if cleanup_failures:
            raise AssertionError("测试账户清理未完成")
        report["status"] = "PASS"
        report["completedAt"] = utc_now()
        report["passed"] = sum(1 for check in report["checks"] if check.get("status") == "PASS")
        report["notRun"] = sum(1 for check in report["checks"] if check.get("status") == "NOT_RUN")
        report["credentialsPrinted"] = False
        report["userContentPrinted"] = False
        output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        print(output, end="")
        return 0
    except Exception as exc:
        report["completedAt"] = utc_now()
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["credentialsPrinted"] = False
        output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        print(output, end="", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
