#!/usr/bin/env python3
"""Render extension pages in Chromium with deterministic Chrome/API mocks.

This validates real browser rendering and interaction without claiming that an
unpacked extension was installed. The production Chrome policy in the current
runner blocks unpacked-extension loading, so that remains an environment-bound
Build Agent canary.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"
EVIDENCE = Path(__file__).resolve().parents[5] / "14_EVIDENCE/browser/EXTENSION_UI_MOCK_ACCEPTANCE.json"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        return


@contextmanager
def server() -> Iterator[str]:
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(EXT), **kwargs)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def mock_script(base_url: str) -> str:
    data = {
        "accounts": [
            {
                "id": "acc-xhs-1",
                "platform": "xiaohongshu",
                "external_account_id": "browser-session:xiaohongshu",
                "display_name": "小红书账号",
                "connection_state": "connected",
                "content_count": 1284,
                "last_sync_at": "2026-08-02T10:20:00Z",
            }
        ],
        "runs": [
            {
                "id": "run-1",
                "source_account_id": "acc-xhs-1",
                "platform": "xiaohongshu",
                "mode": "first_full",
                "status": "completed",
                "discovered_count": 1284,
                "imported_count": 1284,
                "updated_at": "2026-08-02T10:20:00Z",
            }
        ],
        "destinations": [
            {"destination_id": "social_archive", "state": "connected", "last_message_zh": "主档案可用"},
            {"destination_id": "markdown", "state": "connected", "last_message_zh": "Markdown 自动写入已开启"},
            {"destination_id": "notion", "state": "needs_user_action", "next_action_zh": "连接 Notion"},
            {"destination_id": "obsidian", "state": "needs_user_action", "next_action_zh": "连接 Obsidian"},
            {"destination_id": "github", "state": "connected", "last_message_zh": "GitHub Private 已连接"},
        ],
    }
    return f"""
(() => {{
  const base = {json.dumps(base_url)};
  const stored = {{
    endpoint: 'https://social-archive-api.linzezhang.com',
    libraryUrl: 'https://social-archive.linzezhang.com',
    destinationIds: ['social_archive','markdown','github'],
    relationType: 'saved', collectionKey: '', showFloatingButton: true,
    onboardingComplete: true, token: 'mock-token'
  }};
  const accounts = {json.dumps(data['accounts'], ensure_ascii=False)};
  const runs = {json.dumps(data['runs'], ensure_ascii=False)};
  const destinations = {json.dumps(data['destinations'], ensure_ascii=False)};
  const event = () => ({{ addListener() {{}}, removeListener() {{}} }});
  globalThis.chrome = {{
    runtime: {{
      getURL: path => `${{base}}/${{path}}`,
      getManifest: () => ({{ version: '0.0.0.6' }}),
      openOptionsPage: async () => true,
      sendMessage: async message => {{
        if (message?.type === 'SA_GET_PENDING_CONNECTIONS') return {{ ok:true, items:{{}} }};
        if (message?.type === 'SA_SYNC_ALL_ACCOUNTS') return {{ ok:true, queuedCount:1, message:'已加入后台同步队列' }};
        if (message?.type === 'SA_SYNC_ACCOUNT') return {{ ok:true, state:'queued', message:'同步已加入后台队列' }};
        if (message?.type === 'SA_ACCOUNT_CONNECT') return {{ ok:true, state:'authorizing', message:'登录页已打开' }};
        return {{ ok:true }};
      }},
      onMessage: event(), onConnect: event()
    }},
    storage: {{ local: {{
      get: async defaults => {{
        if (typeof defaults === 'string') return {{ [defaults]: stored[defaults] }};
        if (Array.isArray(defaults)) return Object.fromEntries(defaults.map(key => [key, stored[key]]));
        return {{ ...(defaults || {{}}), ...stored }};
      }},
      set: async patch => Object.assign(stored, patch),
      remove: async key => delete stored[key]
    }} }},
    tabs: {{
      query: async () => [{{ id:1, windowId:1, status:'complete', url:'https://www.xiaohongshu.com/explore/abc123', title:'示例小红书笔记' }}],
      create: async options => ({{ id:2, ...options }}),
      get: async id => ({{ id, windowId:1, status:'complete', url:'https://www.xiaohongshu.com/explore/abc123' }}),
      update: async (id, options) => ({{ id, ...options }}),
      sendMessage: async () => ({{ ok:true, loggedIn:true, items:[], completeness:'complete' }}),
      onUpdated: event()
    }},
    permissions: {{ contains: async () => true, request: async () => true, remove: async () => true, onAdded: event() }},
    scripting: {{ executeScript: async () => [] }},
    action: {{ setBadgeText: async () => true, setBadgeBackgroundColor: async () => true }},
    sidePanel: {{ open: async () => true, setPanelBehavior: async () => true }},
    alarms: {{ create: async () => true, get: async () => null, onAlarm: event() }},
    bookmarks: {{ getTree: async () => [], onCreated:event(), onChanged:event(), onMoved:event(), onRemoved:event() }},
    contextMenus: {{ removeAll: async () => true, create: () => true, onClicked:event() }},
    commands: {{ onCommand:event() }}
  }};
  const nativeFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = async (input, options = {{}}) => {{
    const url = String(typeof input === 'string' ? input : input.url);
    const response = payload => new Response(JSON.stringify(payload), {{ status:200, headers:{{'Content-Type':'application/json'}} }});
    if (url.endsWith('/runtime-config.json')) return response({{ endpoint:'https://social-archive-api.linzezhang.com', library_url:'https://social-archive.linzezhang.com', managed:true }});
    if (url.includes('/v1/accounts')) return response({{ items:accounts }});
    if (url.includes('/v1/sync-runs')) return response({{ items:runs }});
    if (url.includes('/v1/extension/bootstrap')) return response({{ destinations }});
    if (url.includes('/v1/destinations')) return response({{ items:destinations }});
    if (url.startsWith(base)) return nativeFetch(input, options);
    return response({{ ok:true }});
  }};
}})();
"""


def run() -> dict:
    results = []
    errors = []
    blocked_reason = None
    try:
        with server() as base_url, sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
            try:
                for page_name, checks, click_selector in (
                    ("options.html", ["连接一次账号", "立即同步全部账号", "小红书", "Chrome 书签"], "#syncAll"),
                    ("popup.html", ["账号收藏镜像", "同步全部已连接账号", "备用：保存当前页面"], "#primarySync"),
                    ("sidepanel.html", ["同步进度", "需要处理", "连接账号"], "#syncAll"),
                ):
                    page = browser.new_page(viewport={"width": 1100, "height": 900})
                    page.on("pageerror", lambda exc, name=page_name: errors.append({"page": name, "kind": "pageerror", "message": str(exc)}))
                    page.on("console", lambda msg, name=page_name: errors.append({"page": name, "kind": "console", "message": msg.text}) if msg.type == "error" else None)
                    page.add_init_script(mock_script(base_url))
                    page.goto(f"{base_url}/{page_name}", wait_until="networkidle")
                    body = page.locator("body").inner_text()
                    missing = [text for text in checks if text not in body]
                    if missing:
                        errors.append({"page": page_name, "kind": "missing_copy", "message": ",".join(missing)})
                    page.locator(click_selector).click()
                    page.wait_for_timeout(150)
                    results.append({"page": page_name, "checks": checks, "clicked": click_selector, "missing": missing})
                    page.close()
            finally:
                browser.close()
    except Exception as exc:
        message = str(exc)
        if "ERR_BLOCKED_BY_ADMINISTRATOR" in message:
            blocked_reason = "当前执行环境的 Chromium 管理策略阻止所有页面导航与未打包扩展加载"
        else:
            errors.append({"page": "runner", "kind": "exception", "message": message})
    payload = {
        "status": "NOT_RUN_POLICY_BLOCKED" if blocked_reason else ("PASS" if not errors else "FAIL"),
        "scope": "mocked_browser_render_and_interaction_only",
        "real_unpacked_extension_install": "NOT_RUN_POLICY_BLOCKED",
        "blocked_reason_zh": blocked_reason,
        "results": results,
        "errors": errors,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] in {"PASS", "NOT_RUN_POLICY_BLOCKED"} else 1)
