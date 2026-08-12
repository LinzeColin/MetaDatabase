from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Social Archive Chrome 扩展 Popup 浏览器验收")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 Playwright"}, ensure_ascii=False))
        return 3

    root = Path(__file__).resolve().parents[1]
    ext = root / "apps" / "browser-extension"
    output = Path(args.output).resolve()
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)

    html = (ext / "popup.html").read_text(encoding="utf-8")
    css = (ext / "popup.css").read_text(encoding="utf-8")
    shared = (ext / "shared.js").read_text(encoding="utf-8")
    popup = (ext / "popup.js").read_text(encoding="utf-8")
    mock = r'''
      window.__captureMessages = [];
      window.__store = {};
      window.chrome = {
        runtime: {
          getURL: path => `https://extension.test/${path}`,
          sendMessage: async message => {
            window.__captureMessages.push(message);
            if (message.type === "SA_CAPTURE_ACTIVE") return {ok:true,savedCount:1,failedCount:0,destinationWarningCount:0};
            return {ok:true};
          },
          openOptionsPage: () => { window.__optionsOpened = true; }
        },
        storage: { local: {
          get: async defaults => ({...defaults,...window.__store}),
          set: async values => { Object.assign(window.__store, values); }
        }},
        tabs: {
          query: async () => [{id:1,url:"https://www.xiaohongshu.com/explore/example",title:"一篇值得保存的小红书笔记"}],
          create: async value => { window.__createdTab = value; }
        },
        permissions: {
          contains: async () => true,
          request: async () => true,
          remove: async () => true
        }
      };
      window.fetch = async (url, options={}) => {
        const value = String(url);
        if (value.includes("runtime-config.json")) return new Response(JSON.stringify({endpoint:"https://social-archive-api.linzezhang.com",library_url:"https://social-archive.linzezhang.com",managed:true}),{status:200,headers:{"Content-Type":"application/json"}});
        if (value.includes("/v1/extension/bootstrap")) return new Response(JSON.stringify({
          destinations:[
            {destination_id:"social_archive",state:"connected"},
            {destination_id:"markdown",state:"connected"},
            {destination_id:"notion",state:"connected",last_message_zh:"Notion 已连接"},
            {destination_id:"obsidian",state:"needs_user_action",next_action_zh:"需要连接 Obsidian"},
            {destination_id:"github",state:"connected",last_message_zh:"GitHub Private 已连接"}
          ],
          jobs:[{id:"job1",status:"failed"}],
          summary:{failed_exports:0}
        }),{status:200,headers:{"Content-Type":"application/json"}});
        return new Response(JSON.stringify({detail:"not found"}),{status:404,headers:{"Content-Type":"application/json"}});
      };
    '''
    html = html.replace('<link rel="stylesheet" href="popup.css">', f"<style>{css}</style>")
    html = html.replace('<script src="shared.js"></script>', f"<script>{mock}</script><script>{shared}</script>")
    html = html.replace('<script src="popup.js"></script>', f"<script>{popup}</script>")

    console_errors: list[str] = []
    dialogs: list[str] = []
    assertions: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 430, "height": 760}, device_scale_factor=1)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
        page.set_content(html, wait_until="networkidle")
        page.wait_for_function("document.querySelector('#pageTitle').textContent.includes('小红书笔记')")

        assert page.locator("#platformBadge").inner_text() == "小红书"
        assert page.locator("#authorization").get_by_text("已授权").is_visible()
        assertions.append("当前平台识别和真实授权状态可见")
        assert page.get_by_role("button", name="保存到我的档案馆 默认归档 L0＋L1＋L3").is_visible()
        assert page.get_by_role("button", name="读取当前列表 只读取当前可见内容，不自动滚动").is_visible()
        assertions.append("单一主操作和部分扫描防误删提示可见")
        assert "已授权来源" in page.locator("#connectionSummary").inner_text()
        assert page.locator("#destinationChips .destination-chip").count() == 5
        assertions.append("来源、目的地、待处理状态集中展示")
        page.screenshot(path=str(screenshots / "extension-popup-ready.png"), full_page=True)

        page.locator("#savePage").click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('已保存 1 条')")
        capture = page.evaluate("window.__captureMessages.find(x=>x.type==='SA_CAPTURE_ACTIVE')")
        assert capture["mode"] == "page"
        assert capture["destinationIds"] == ["social_archive", "markdown"]
        assertions.append("点击一次保存真实发出当前页归档请求并显示成功反馈")
        page.screenshot(path=str(screenshots / "extension-popup-saved.png"), full_page=True)

        page.locator("#scanList").click()
        page.wait_for_function("window.__captureMessages.filter(x=>x.type==='SA_CAPTURE_ACTIVE').length===2")
        scan = page.evaluate("window.__captureMessages.filter(x=>x.type==='SA_CAPTURE_ACTIVE')[1]")
        assert scan["mode"] == "list"
        assertions.append("当前可见列表读取真实发出 partial-scan 请求")
        browser.close()

    if dialogs:
        raise AssertionError(f"出现浏览器原生对话框：{dialogs}")
    if console_errors:
        raise AssertionError(f"控制台错误：{console_errors}")
    result = {
        "schema_version": "1.0",
        "status": "PASS",
        "subject": "Social Archive v0.0.0.6 Chrome extension popup",
        "mode": "real_chromium_with_deterministic_chrome_api_fixture",
        "assertions": assertions,
        "native_dialogs": dialogs,
        "console_errors": console_errors,
        "screenshots": [str(path.relative_to(output)) for path in sorted(screenshots.glob("extension-*.png"))],
        "boundary": "Popup HTML/CSS/JavaScript ran in real Chromium with deterministic Chrome API and server fixtures; unpacked extension installation and live platform accounts remain last-mile NOT_RUN.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "EXTENSION_UI_ACCEPTANCE.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
