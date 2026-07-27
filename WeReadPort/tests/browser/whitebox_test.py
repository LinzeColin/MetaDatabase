#!/usr/bin/env python3
"""目标环境即时浏览器验收：不使用真实密钥，不等待真实时间。"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEREAD_PORT_URL", "http://127.0.0.1:4187")
BASE_HOSTNAME = urlparse(BASE).hostname
OUT = Path(os.environ.get("WEREAD_PORT_EVIDENCE", "/tmp/weread-port-browser-evidence"))
OUT.mkdir(parents=True, exist_ok=True)
CHROMIUM = os.environ.get("CHROMIUM_PATH")
RESULTS: list[dict[str, object]] = []


def check(name: str, condition: bool, detail: object = None) -> None:
    row = {"name": name, "status": "PASS" if condition else "FAIL", "detail": copy.deepcopy(detail)}
    RESULTS.append(row)
    print(f"[{row['status']}] {name}", flush=True)
    if not condition:
        raise AssertionError(f"{name}：{detail}")


FAKE_CLOCK = r"""
(() => {
  let now = 0, nextId = 1;
  const tasks = new Map();
  window.__WEREAD_PORT_TEST_CLOCK__ = {
    advance(ms) {
      now += Number(ms);
      let progressed = true;
      while (progressed) {
        progressed = false;
        const due = [...tasks.entries()].filter(([, task]) => task.at <= now).sort((a, b) => a[1].at - b[1].at);
        if (due.length) {
          const [id, task] = due[0];
          tasks.delete(id);
          task.fn();
          progressed = true;
        }
      }
    },
    pending: () => [...tasks.values()].map(task => task.at - now),
  };
  window.setTimeout = (fn, delay = 0) => {
    const id = nextId++;
    tasks.set(id, { at: now + Number(delay), fn });
    return id;
  };
  window.clearTimeout = id => tasks.delete(id);
})();
"""


def browser_type(playwright):
    kwargs = {"headless": True}
    if CHROMIUM:
        kwargs["executable_path"] = CHROMIUM
        kwargs["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
    return playwright.chromium.launch(**kwargs)


with sync_playwright() as playwright:
    browser = browser_type(playwright)
    for label, viewport in (("桌面", {"width": 1440, "height": 1000}), ("手机", {"width": 390, "height": 844})):
        context = browser.new_context(viewport=viewport, color_scheme="light", accept_downloads=True)
        context.add_init_script(FAKE_CLOCK)
        page = context.new_page()
        external: list[str] = []
        automatic_downloads: list[str] = []
        opened: list[str] = []
        page.on("request", lambda request: external.append(request.url) if urlparse(request.url).hostname != BASE_HOSTNAME and not request.url.startswith("blob:") else None)
        page.on("download", lambda download: automatic_downloads.append(download.suggested_filename))
        page.add_init_script("""
          window.__openedUrls = [];
          window.open = url => { window.__openedUrls.push(String(url)); return null; };
          Object.defineProperty(navigator, 'clipboard', { value: { writeText: async text => { window.__copiedText = String(text); } } });
        """)
        page.goto(BASE, wait_until="networkidle")

        check(f"{label}：页面标题为全中文产品名", "微信读书笔记迁移" in page.title(), page.title())
        check(f"{label}：文档语言为简体中文", page.locator("html").get_attribute("lang") == "zh-CN")
        check(f"{label}：真实微信读书连接是线上主路径", page.locator("#hero-connect").count() == 1 and "primary" in (page.locator("#hero-connect").get_attribute("class") or ""))
        check(f"{label}：演示入口明确降级为体验入口", page.locator("#hero-demo").count() == 1 and "ghost" in (page.locator("#hero-demo").get_attribute("class") or ""))
        dims = page.locator("body").evaluate("e => ({scrollWidth:e.scrollWidth,clientWidth:e.clientWidth})")
        check(f"{label}：无横向溢出", dims["scrollWidth"] <= dims["clientWidth"], dims)
        page.screenshot(path=str(OUT / f"{label}-首页.png"), full_page=True)

        # 生产公开页面和机器状态必须真实可用，且不使用用户密钥探测。
        for route, phrase in (("/privacy/", "我们处理哪些数据"), ("/terms/", "禁止用途"), ("/status/", "系统状态")):
            response = page.goto(BASE.rstrip("/") + route, wait_until="networkidle")
            check(f"{label}：{route} 可访问", response is not None and response.ok, response.status if response else None)
            body_text = page.locator("body").inner_text()
            check(f"{label}：{route} 不是空壳", phrase in body_text, body_text[:200])
            if route == "/status/":
                check(f"{label}：状态页展示业务纵向切片矩阵", all(text in body_text for text in ["端到端白箱治理矩阵", "依赖与耦合", "验收 Oracle"]))
                check(f"{label}：状态页登记七条业务线", page.locator("[data-business-line]").count() == 7, page.locator("[data-business-line]").count())
                status_dims = page.locator("body").evaluate("e => ({scrollWidth:e.scrollWidth,clientWidth:e.clientWidth})")
                check(f"{label}：状态页无页面级横向溢出", status_dims["scrollWidth"] <= status_dims["clientWidth"], status_dims)
        health = page.request.get(BASE.rstrip("/") + "/healthz")
        ready = page.request.get(BASE.rstrip("/") + "/readyz")
        public_status = page.request.get(BASE.rstrip("/") + "/api/status")
        version = page.request.get(BASE.rstrip("/") + "/api/version")
        check(f"{label}：存活端点可用", health.ok and health.json().get("status") == "ALIVE", health.text())
        ready_payload = ready.json() if ready.ok else {}
        check(f"{label}：就绪端点独立可用", ready.ok and ready_payload.get("status") == "READY", ready.text())
        check(f"{label}：业务依赖图通过就绪 Oracle", ready_payload.get("checks", {}).get("businessGovernanceContract", {}).get("ready") is True, ready_payload)
        status_payload = public_status.json() if public_status.ok else {}
        governance = status_payload.get("businessGovernance", {})
        expected_lines = {"public-trust", "weread-direct-export", "local-import", "normalize-export", "chatgpt-handoff", "release-supply-chain", "operations-recovery"}
        observed_lines = {line.get("id") for line in governance.get("lines", []) if isinstance(line, dict)}
        check(f"{label}：公开状态不含用户内容", public_status.ok and status_payload.get("dataBoundary", {}).get("statusContainsUserContent") is False and status_payload.get("dataBoundary", {}).get("businessGovernanceContainsUserContent") is False, status_payload)
        check(f"{label}：公开业务矩阵 schema 与依赖图有效", governance.get("schemaVersion") == "1.0.0" and governance.get("graphStatus") == "VALID", governance)
        check(f"{label}：公开业务矩阵七条业务线完整且无阻塞", observed_lines == expected_lines and all(line.get("state") != "BLOCKED" for line in governance.get("lines", [])), governance)
        version_payload = version.json() if version.ok else {}
        check(f"{label}：版本端点公开治理 schema", version.ok and version_payload.get("appVersion") == "v0.0.0.1.7" and version_payload.get("businessGovernanceSchemaVersion") == "1.0.0", version_payload)
        page.goto(BASE, wait_until="networkidle")

        # 上传入口：真实选择本地 Markdown，浏览器 Worker 本地解析。
        page.set_input_files("#local-files", [
            {"name": "第一本.md", "mimeType": "text/markdown", "buffer": "# 第一本\n\n这是第一份本地笔记。".encode("utf-8")},
            {"name": "第二本.txt", "mimeType": "text/plain", "buffer": "# 第二本\n\n这是第二份本地笔记。".encode("utf-8")},
        ])
        check(f"{label}：上传按钮在有效选择后可用", page.locator("#local-import-button").is_enabled())
        page.click("#local-import-button")
        page.wait_for_selector("#select-panel:not(.hidden)")
        page.wait_for_function("document.querySelectorAll('.book-row').length === 2")
        check(f"{label}：上传后显示两项本地笔记", page.locator(".book-row").count() == 2)
        check(f"{label}：上传来源明确标注本地读取", "本地" in page.locator("#source-summary").inner_text())
        page.screenshot(path=str(OUT / f"{label}-上传后选择.png"), full_page=True)

        # Fake Clock：即时验证，不等待 13 分钟。
        page.evaluate("window.__WEREAD_PORT_TEST_CLOCK__.advance(200)")
        page.evaluate("window.__WEREAD_PORT_TEST_CLOCK__.advance(13 * 60 * 1000)")
        check(f"{label}：会话过期预警可即时触发", page.locator("#session-banner:not(.hidden)").count() == 1)
        page.click("#extend-session")
        check(f"{label}：会话可继续且无模态等待", page.locator("#session-banner.hidden").count() == 1)

        # 生成结果；未点击时不得自动下载。
        page.click("#export-button")
        page.wait_for_selector("#download-chatgpt", timeout=20_000)
        check(f"{label}：生成结果前没有自动下载", automatic_downloads == [], automatic_downloads)
        check(f"{label}：提供完整迁移压缩包下载", page.locator("a.download[download$='.zip']").count() == 1)
        check(f"{label}：提供独立 ChatGPT Markdown 下载", page.locator("#download-chatgpt[download$='.md']").count() == 1)
        check(f"{label}：提供复制提问词并打开 ChatGPT", page.locator("#copy-open-chatgpt").count() == 1)
        href = page.locator("#open-chatgpt").get_attribute("href")
        parsed = urlparse(href)
        check(f"{label}：ChatGPT 跳转固定为官方入口且不携带数据", href == "https://chatgpt.com/" and not parsed.query and not parsed.fragment, href)
        page.screenshot(path=str(OUT / f"{label}-下载与ChatGPT交接.png"), full_page=True)

        # 两类下载均必须由用户主动点击。
        with page.expect_download() as zip_info:
            page.locator("a.download[download$='.zip']").click()
        check(f"{label}：主动点击后下载 ZIP", zip_info.value.suggested_filename.endswith(".zip"), zip_info.value.suggested_filename)
        with page.expect_download() as md_info:
            page.click("#download-chatgpt")
        check(f"{label}：主动点击后下载 ChatGPT Markdown", md_info.value.suggested_filename.endswith(".md"), md_info.value.suggested_filename)

        page.click("#copy-open-chatgpt")
        copied = page.evaluate("window.__copiedText || ''")
        opened = page.evaluate("window.__openedUrls || []")
        check(f"{label}：中文提问词已复制", "我刚刚上传了" in copied and "请先完整读取文件" in copied, copied[:160])
        check(f"{label}：按钮只请求打开固定 ChatGPT 入口", opened == ["https://chatgpt.com/"], opened)

        storage = page.evaluate("""async () => ({
          local: Object.keys(localStorage), session: Object.keys(sessionStorage), cookies: document.cookie,
          idb: indexedDB.databases ? (await indexedDB.databases()).map(item => item.name) : []
        })""")
        check(f"{label}：上传、笔记与密钥不进入浏览器长期存储", storage == {"local": [], "session": [], "cookies": "", "idb": []}, storage)
        check(f"{label}：产品运行未加载第三方素材或跟踪请求", external == [], external)
        context.close()

    # 320px Reflow 与 Reduced Motion。
    context = browser.new_context(viewport={"width": 320, "height": 800}, reduced_motion="reduce")
    page = context.new_page()
    context.add_init_script(FAKE_CLOCK)
    page.goto(BASE, wait_until="networkidle")
    dims = page.locator("body").evaluate("e => ({scrollWidth:e.scrollWidth,clientWidth:e.clientWidth})")
    check("320px：无横向页面滚动", dims["scrollWidth"] <= dims["clientWidth"], dims)
    check("减少动态效果：关闭平滑滚动", page.evaluate("getComputedStyle(document.documentElement).scrollBehavior") == "auto")
    context.close()
    browser.close()

summary = {
    "status": "PASS" if all(row["status"] == "PASS" for row in RESULTS) else "FAIL",
    "base_url": BASE,
    "checks": RESULTS,
    "pass": sum(row["status"] == "PASS" for row in RESULTS),
    "fail": sum(row["status"] == "FAIL" for row in RESULTS),
}
(OUT / "PLAYWRIGHT_RESULTS.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
