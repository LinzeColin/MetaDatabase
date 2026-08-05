"""真实浏览器 UI 验收 —— **这份脚本已经对不上现在的界面，跑不通。**

## 为什么保留而不是删掉

它驱动的每一个选择器在当前 PWA 里都不存在了（2026-08-04 实测）：

    #sourceCards        0 命中
    #destinationCards   0 命中
    #detailDialog       0 命中
    连接中心（链接名）   v0.0.0.6 改名为「账号同步中心」
    XHS-Downloader Sidecar  T03 已删除这条取数通道

而且**全仓没有任何地方调用它**。

留着比删掉危险的地方在于：文件名叫 browser_acceptance.py，
看见它的人（包括以后的我）会以为 PWA 有自动化验收。
**那是假的保证，比没有更糟。**

所以它现在**开跑就拒绝**，把过时的地方逐条说清楚，而不是跑到一半
在某个 locator 上报个看不懂的超时。267 行的选择器与断言留着，
将来重做界面验收时是现成的参照。

要重新启用：把下面 STALE_SELECTORS 逐条对到新界面上，然后删掉这个闸。
"""

from __future__ import annotations


STALE_SELECTORS = {
    "#sourceCards": "九类来源卡片；当前界面没有这个容器",
    "#destinationCards": "五类目的地卡片；同上",
    "#detailDialog": "详情弹窗；当前是 drawer 结构",
    "连接中心": "v0.0.0.6（40d833bf）改名为「账号同步中心」",
    "XHS-Downloader Sidecar": "T03 已删除该取数通道，界面上不该再出现",
}


def _refuse_because_it_is_stale() -> int:
    import json as _json
    print(_json.dumps({
        "status": "BLOCKED_STALE",
        "message": "本脚本对不上当前界面，拒绝运行（跑下去只会在某个 locator 上莫名超时）",
        "stale": STALE_SELECTORS,
        "how_to_reenable": "逐条对到新界面后，删除 main() 开头的这道闸",
    }, ensure_ascii=False, indent=2))
    return 3



import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def main() -> int:
    # 这道闸在最前面：不许它跑到一半才发现界面全变了。
    return _refuse_because_it_is_stale()

    parser = argparse.ArgumentParser(description="Social Archive 离线真实浏览器 UI 验收")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"status": "BLOCKED_ENVIRONMENT", "message": "缺少 Playwright"}, ensure_ascii=False))
        return 3

    root = Path(__file__).resolve().parents[1]
    pwa = root / "apps" / "pwa"
    output = Path(args.output).resolve()
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)

    html = (pwa / "index.html").read_text(encoding="utf-8")
    css = (pwa / "styles.css").read_text(encoding="utf-8")
    js = (pwa / "app.js").read_text(encoding="utf-8")
    # about:blank cannot push a relative history URL; UI routing itself remains fully exercised.
    js = js.replace('history.pushState({route},"",`/${route}`);', 'void 0;')
    js = js.replace("localStorage", "window.__saStorage")
    js = "window.__saStorage={data:{},getItem(k){return this.data[k]??null},setItem(k,v){this.data[k]=String(v)},removeItem(k){delete this.data[k]}};" + js
    html = html.replace('<link rel="stylesheet" href="/assets/styles.css">', f"<style>{css}</style>")
    html = html.replace('<script src="/assets/app.js" defer></script>', f"<script>{js}</script>")
    html = html.replace("<head>", '<head><base href="https://social-archive.test/">', 1)

    items = [
        {
            "id": "item-xhs",
            "platform": "xiaohongshu",
            "title": "一篇值得长期保留的小红书笔记",
            "author_name": "示例作者",
            "canonical_url": "https://www.xiaohongshu.com/explore/example",
            "relation_type": "saved",
            "last_observed_at": "2026-08-02T09:00:00Z",
            "verified_replica_count": 3,
        },
        {
            "id": "item-x",
            "platform": "x",
            "title": "跨平台收藏归档方法",
            "author_name": "researcher",
            "canonical_url": "https://x.com/example/status/1",
            "relation_type": "bookmark",
            "last_observed_at": "2026-08-02T08:00:00Z",
            "verified_replica_count": 2,
        },
    ]
    connectors = [
        {"connector_id": key, "display_name": name, "state": "healthy" if key in {"generic-web", "xiaohongshu"} else "degraded", "next_action_zh": "已完成真实读取" if key in {"generic-web", "xiaohongshu"} else "当前页保存可用；批量读取等待授权"}
        for key, name in [
            ("generic-web", "普通网页"), ("x", "X"), ("reddit", "Reddit"),
            ("instagram", "Instagram"), ("tiktok", "TikTok"), ("xiaohongshu", "小红书"),
            ("douyin", "抖音"), ("kuaishou", "快手"), ("bilibili", "B站"),
            ("youtube", "YouTube"),
        ]
    ]
    destinations = [
        {"destination_id": "social_archive", "display_name": "我的档案馆", "state": "connected", "next_action_zh": "主档案正常"},
        {"destination_id": "markdown", "display_name": "Markdown", "state": "connected", "next_action_zh": "自动导出正常"},
        {"destination_id": "notion", "display_name": "Notion", "state": "connected", "next_action_zh": "真实写入探针通过"},
        {"destination_id": "obsidian", "display_name": "Obsidian", "state": "needs_user_action", "next_action_zh": "安装本地桥后点击检查"},
        {"destination_id": "github", "display_name": "GitHub 私有库", "state": "connected", "next_action_zh": "私有仓写入探针通过"},
    ]
    jobs = [
        {"id": "job-done", "job_type": "export_destination", "status": "done", "connector_id": "markdown", "attempt_count": 1},
        {"id": "job-failed", "job_type": "download_l3", "status": "failed", "connector_id": "xiaohongshu", "attempt_count": 2, "last_error_message": "网络暂时不可用；点击重试"},
    ]
    receipts = [
        {"id": "receipt-1", "destination_id": "notion", "status": "done", "message_zh": "已写入 Notion"},
        {"id": "receipt-2", "destination_id": "github", "status": "done", "message_zh": "已写入 GitHub Private"},
    ]
    captures: list[dict[str, object]] = []
    retry_count = 0
    probe_count = 0
    console_errors: list[str] = []
    dialogs: list[str] = []
    assertions: list[str] = []

    def response_json(route, payload: object, status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json; charset=utf-8", body=json.dumps(payload, ensure_ascii=False))

    def handler(route) -> None:
        nonlocal retry_count, probe_count
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            return response_json(route, {"status": "ok", "version": _project_version()})
        if path == "/v1/extension/bootstrap":
            return response_json(route, {"connectors": connectors, "destinations": destinations, "jobs": jobs})
        if path == "/v1/library":
            q = (query.get("q") or [""])[0].lower()
            platform = (query.get("platform") or [""])[0]
            relation = (query.get("relation") or [""])[0]
            visible = list(items)
            if q:
                visible = [item for item in visible if q in (str(item["title"]) + " " + str(item["author_name"])).lower()]
            if platform:
                visible = [item for item in visible if item["platform"] == platform]
            if relation:
                visible = [item for item in visible if item["relation_type"] == relation]
            return response_json(route, {"items": visible})
        if path.startswith("/v1/library/"):
            item_id = path.rsplit("/", 1)[-1]
            item = next((candidate for candidate in items if candidate["id"] == item_id), None)
            if not item:
                return response_json(route, {"detail": "不存在"}, 404)
            detail = dict(item)
            detail.update({
                "metadata_json": json.dumps({"text": "这是已经进入 L1 的正文内容。"}, ensure_ascii=False),
                "relations": [{"relation_type": item["relation_type"]}],
                "artifacts": [{"level": "L1"}, {"level": "L3"}],
                "availability": "observed",
            })
            return response_json(route, detail)
        if path == "/v1/captures" and request.method == "POST":
            payload = request.post_data_json
            captures.append(payload)
            new_item = {
                "id": f"capture-{len(captures)}",
                "platform": payload.get("platform", "generic-web"),
                "title": payload.get("title") or "新保存内容",
                "author_name": "",
                "canonical_url": payload.get("url"),
                "relation_type": payload.get("relation_type", "saved"),
                "last_observed_at": "2026-08-02T10:00:00Z",
                "verified_replica_count": 0,
            }
            items.insert(0, new_item)
            return response_json(route, {"status": "accepted", "content_id": new_item["id"], "message_zh": "已保存"}, 202)
        if path == "/v1/jobs":
            return response_json(route, {"items": jobs})
        if path == "/v1/destinations/receipts":
            return response_json(route, {"items": receipts})
        if path.startswith("/v1/jobs/") and path.endswith("/retry") and request.method == "POST":
            retry_count += 1
            for job in jobs:
                if job["id"] in path:
                    job["status"] = "queued"
                    job.pop("last_error_message", None)
            return response_json(route, {"status": "queued", "message_zh": "已重新加入队列"})
        if path.startswith("/v1/destinations/") and path.endswith("/probe") and request.method == "POST":
            probe_count += 1
            destination_id = path.split("/")[3]
            for destination in destinations:
                if destination["destination_id"] == destination_id:
                    destination["state"] = "connected"
                    destination["next_action_zh"] = "真实写入探针通过"
            return response_json(route, {"status": "connected", "message_zh": "连接有效"})
        if path == "/assets/sw.js":
            return route.fulfill(status=200, content_type="application/javascript", body="self.addEventListener('fetch',()=>{});")
        return response_json(route, {"detail": f"未处理路径 {path}"}, 404)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.route("https://social-archive.test/**", handler)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(1800)

        assert page.get_by_role("heading", name="把散落在各个平台的收藏，变成你自己的资料。").is_visible()
        assertions.append("首页北极星与单一主动作可见")
        assert page.get_by_role("button", name="安装浏览器插件").is_visible()
        assertions.append("插件安装入口可见")
        page.screenshot(path=str(screenshots / "pwa-home-desktop.png"), full_page=True)

        page.locator("#saveUrl").fill("https://www.wikipedia.org/wiki/Archiving")
        page.locator("#saveLinkForm button[type=submit]").click()
        page.wait_for_function("document.querySelector('#saveFeedback').textContent.includes('已保存')")
        assert captures and captures[0]["requested_levels"] == ["L0", "L1", "L3"]
        assertions.append("免插件链接保存提交 L0/L1/L3 并收到成功反馈")

        page.get_by_role("link", name="资料库").click()
        page.wait_for_function("document.querySelectorAll('.library-card').length >= 3")
        assert page.locator(".library-card").count() >= 3
        page.locator("#librarySearch").fill("跨平台")
        page.wait_for_timeout(350)
        assert page.locator(".library-card").count() == 1
        page.locator(".library-card").first.click()
        page.wait_for_timeout(500)
        assert page.locator("#detailDialog").get_attribute("open") is not None
        assert "这是已经进入 L1 的正文内容。" in page.locator("#detailDialog").inner_text()
        page.evaluate("document.querySelector('#detailDialog').close()")
        assertions.append("资料库搜索、筛选、详情与 L1 正文可用")
        page.screenshot(path=str(screenshots / "pwa-library-desktop.png"), full_page=True)

        page.get_by_role("link", name="连接中心").click()
        page.wait_for_timeout(250)
        assert page.locator("#sourceCards .connection-card").count() == 9
        assert page.locator("#destinationCards .connection-card").count() == 5
        assert page.get_by_text("XHS-Downloader Sidecar").is_visible()
        assertions.append("九类来源、五类目的地与内部开源引擎同屏可见")
        page.screenshot(path=str(screenshots / "pwa-connections-desktop.png"), full_page=True)

        page.get_by_role("link", name="任务中心").click()
        page.wait_for_timeout(250)
        assert page.locator("[data-retry-job]").count() == 1
        page.locator("[data-retry-job]").click()
        page.wait_for_timeout(150)
        assert retry_count == 1
        assertions.append("失败任务提供唯一重试动作并真实调用重试接口")
        page.screenshot(path=str(screenshots / "pwa-tasks-desktop.png"), full_page=True)

        page.get_by_role("link", name="设置").click()
        page.wait_for_timeout(150)
        before = page.locator("#settingL2").is_checked()
        page.locator("#settingL2").set_checked(not before)
        assert page.evaluate("Boolean(window.__saStorage.getItem('sa-ui-settings'))")
        assertions.append("用户设置即时保存且 L2 默认不阻塞")

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.route("https://social-archive.test/**", handler)
        mobile.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        mobile.on("pageerror", lambda error: console_errors.append(str(error)))
        mobile.set_content(html, wait_until="networkidle")
        mobile.wait_for_timeout(1800)
        assert mobile.locator(".main-nav").is_visible()
        assert mobile.get_by_role("button", name="先保存一个链接").is_visible()
        mobile.screenshot(path=str(screenshots / "pwa-home-mobile.png"), full_page=True)
        assertions.append("390×844 移动端主操作与底部导航可用")

        browser.close()

    if dialogs:
        raise AssertionError(f"出现浏览器原生 dialog：{dialogs}")
    meaningful_errors = [error for error in console_errors if "service worker" not in error.lower()]
    if meaningful_errors:
        raise AssertionError(f"浏览器控制台错误：{meaningful_errors}")

    result = {
        "schema_version": "1.0",
        "status": "PASS",
        "subject": "Social Archive v0.0.0.6 PWA",
        "mode": "real_chromium_offline_intercepted_api",
        "assertions": assertions,
        "capture_requests": len(captures),
        "retry_requests": retry_count,
        "probe_requests": probe_count,
        "native_dialogs": dialogs,
        "console_errors": meaningful_errors,
        "screenshots": [str(path.relative_to(output)) for path in sorted(screenshots.glob("*.png"))],
        "boundary": "UI/browser behavior is real Chromium; provider/cloud/account calls are deterministic intercepted fixtures and do not claim production PASS.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "BROWSER_UI_ACCEPTANCE.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
