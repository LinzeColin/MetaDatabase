#!/usr/bin/env python3
"""Embedded browser acceptance for v0.0.0.1.9 account-first UI.

This executes the real account UI source and real CSS with a deterministic API
fixture. It never contacts OAuth providers, WeChat Reading, or production.
"""
from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, sync_playwright

APP = Path(__file__).resolve().parents[2]
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")
CSS = (APP / "src/ui/styles.css").read_text(encoding="utf-8")


def bundle() -> str:
    api = (APP / "src/ui/account-api.js").read_text(encoding="utf-8")
    api = re.sub(r"\bexport\s+", "", api)
    platform = (APP / "src/ui/account-platform.js").read_text(encoding="utf-8")
    platform = re.sub(r'^import\s+\{\s*AccountApi\s*\}\s+from\s+"\./account-api\.js";\s*', "", platform, count=1, flags=re.M)
    platform = re.sub(r'^import\s+\{\s*gsap\s*\}\s+from\s+"gsap";\s*', "", platform, count=1, flags=re.M)
    platform = re.sub(r'^import\s+\{\s*readObsidianSelection\s*\}\s+from\s+"\./obsidian-import\.js";\s*', "", platform, count=1, flags=re.M)
    platform = re.sub(r'^import\s+\{\s*CHATGPT_HANDOFF_URL\s*\}\s+from\s+"\.\./core/constants\.js";\s*', "", platform, count=1, flags=re.M)
    platform = re.sub(r'^import\s+\{\s*buildAccountNotesArchive,\s*renderAccountNotesChatGPTContext\s*\}\s+from\s+"\.\./core/account-note-handoff\.js";\s*', "", platform, count=1, flags=re.M)
    platform = re.sub(r"\bexport\s+", "", platform)
    obsidian_double = "async function readObsidianSelection(){ return {items:[],sourceLabel:'浏览器夹具',totalFiles:0,totalBytes:0}; }"
    handoff_double = "const gsap={matchMedia(){return{add(_conditions,callback){return callback({conditions:{reduceMotion:true}});},revert(){}}},set(){},to(){},fromTo(){},killTweensOf(){}}; const CHATGPT_HANDOFF_URL='https://chatgpt.com/'; function renderAccountNotesChatGPTContext(notes){ return '# 浏览器夹具笔记\\n'; } function buildAccountNotesArchive(notes){ return {bytes:new Uint8Array([1]),filename:'fixture.zip'}; }"
    return api + "\n" + obsidian_double + "\n" + handoff_double + "\n" + platform + "\nvoid renderAccountPlatform(document.querySelector('#app'));"



BUNDLE = bundle()
HTML = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>阅迁账户平台浏览器验收</title><style>{CSS}</style></head><body><div id="app"></div></body></html>'''
ACCOUNT = {
    "id": "acct_browser_fixture_001", "displayName": "新手读者", "email": "reader@example.com", "createdAt": 1785196800000,
    "credentials": [
        {"kind": "key", "provider": "weread", "label": "微信读书密钥", "updatedAt": 1785196800000},
        {"kind": "password", "provider": "email", "label": "reader@example.com", "updatedAt": 1785196800000},
    ],
    "connections": [
        {"provider": "notion", "metadata": {"workspaceName": "我的 Notion"}},
        {"provider": "github", "metadata": {"emailHint": "已授权仓库"}},
        {"provider": "google", "metadata": {"emailHint": "r***@example.com"}},
    ],
    "consent": {"behaviorAnalytics": True, "recommendationPersonalization": True},
}
SESSIONS = [
    {"id": "sess-current", "current": True, "createdAt": 1785196800, "lastSeenAt": 1785196800, "expiresAt": 1787788800, "ipHint": "abc12345"},
    {"id": "sess-other", "current": False, "createdAt": 1785110400, "lastSeenAt": 1785110400, "expiresAt": 1787702400, "ipHint": "def67890"},
]
NOTES = [
    {"id": "note-1", "title": "系统思维摘录", "source": "weread", "bookTitle": "系统思维", "author": "彼得·圣吉", "chapterTitle": "第三章", "noteKind": "highlight", "category": "管理", "eventAt": 1785196800, "updatedAt": 1785196800000, "version": 3},
    {"id": "note-2", "title": "第二大脑方法", "source": "notion", "bookTitle": "第二大脑", "author": "蒂亚戈·福特", "chapterTitle": "方法", "noteKind": "review", "category": "知识管理", "eventAt": 1785110400, "updatedAt": 1785110400000, "version": 1},
]
NOTE_CONTENT = {
    "note-1": "以反馈环路理解复杂系统，而不是只追逐短期结果。",
    "note-2": "知识整理的关键，是减少未来寻找信息的摩擦。",
}
DASHBOARD = {
    "consent": ACCOUNT["consent"],
    "summary": {"noteCount": 2, "sourceCount": 4, "estimatedWords": 18340, "noteActivityDays90": 17, "activeDays90": 17},
    "officialReading": {
        "freshness": "CURRENT", "collectedAt": 1785196800,
        "statistics": {
            "weekly": {"mode": "weekly", "totalReadingTimeSeconds": 3600, "totalReadingDays": 2, "totalFinishedBooks": None},
            "monthly": {"mode": "monthly", "totalReadingTimeSeconds": 14400, "totalReadingDays": 9, "totalFinishedBooks": 2},
            "overall": {"mode": "overall", "totalReadingTimeSeconds": 72000, "totalReadingDays": 42, "totalFinishedBooks": 12},
        },
        "preferredCategories": [{"label": "历史", "readingTimeSeconds": 36000, "readingCount": 8}, {"label": "科学", "readingTimeSeconds": 18000, "readingCount": 4}],
        "preferredHours": [{"hour": 21}, {"hour": 22}],
    },
    "officialReadingPeriods": {
        "source": "weread-official-readdata-detail", "metric": "totalReadingTimeSeconds",
        "items": [{"mode": "weekly", "label": "本周", "value": 3600}, {"mode": "monthly", "label": "本月", "value": 14400}, {"mode": "annually", "label": "本年", "value": 54000}, {"mode": "overall", "label": "累计", "value": 72000}],
    },
    "readingCategoryDistribution": {
        "source": "weread-official-readdata-detail", "metric": "readingTimeSeconds",
        "items": [{"label": "历史", "value": 36000}, {"label": "科学", "value": 18000}],
    },
    "readingProgress": {
        "source": "weread-official-book-progress",
        "items": [
            {"label": "系统思维", "author": "彼得·圣吉", "progress": 41, "updatedAt": 1785196800},
            {"label": "第二大脑", "author": "蒂亚戈·福特", "progress": 7, "updatedAt": 1785110400},
        ],
    },
    "categoryDistribution": [{"label": "管理", "value": 5}, {"label": "知识管理", "value": 2}],
    "noteWeeklyTrend": [{"week": f"2026-05-{i + 1:02d}", "value": value} for i, value in enumerate([0, 0, 4, 103, 0, 0, 0, 0, 0, 0, 0, 0])],
    "sourceDistribution": [
        {"label": "weread", "value": 8}, {"label": "notion", "value": 5},
        {"label": "obsidian", "value": 3}, {"label": "github", "value": 2}, {"label": "google", "value": 1},
    ],
    "noteActivityHeatmap": [
        {"date": f"2026-07-{(i % 28) + 1:02d}", "value": i % 6, "level": min(4, i % 5)} for i in range(90)
    ],
    "dataFreshness": {"analyticsRecomputedAt": 1785196800, "weread": {"lastSyncedAt": 1785196800, "officialReadingCollectedAt": 1785196800, "latestNoteEventAt": 1785110400, "noteActivitySource": "real-note-event-time"}},
    "recommendations": [
        {"source": "account-pattern", "title": "继续整理系统思维主题", "author": "账户主题建议", "reason": "最近 30 天该主题笔记增长最快。"},
        {"id": "weread:fixture-book-123", "source": "weread-official", "title": "回顾高频划线章节", "author": "微信读书官方", "reason": "该书划线密度较高且两周未回顾。", "deepLink": "https://weread.qq.com/web/reader/fixture-book-123"},
    ],
}


def fixture_script(authenticated: bool, service_ready: bool = True) -> str:
    fixture = {"account": ACCOUNT, "notes": NOTES, "dashboard": DASHBOARD, "sessions": SESSIONS, "authenticated": authenticated, "serviceReady": service_ready}
    return f'''(() => {{
      const f = {json.dumps(fixture, ensure_ascii=False)};
      f.account.weread = {{lastSyncAt:Math.floor(Date.now()/1000)}};
      f.dashboard.dataFreshness.weread.lastSyncedAt = f.account.weread.lastSyncAt;
      f.synces = 0;
      f.downstreamReads = {{profile:0,notes:0,analytics:0}};
      f.copied = [];
      Object.defineProperty(navigator, 'clipboard', {{configurable:true, value:{{writeText:async value => f.copied.push(String(value))}}}});
      window.__browserFixture = f;
      window.fetch = async (input, init={{}}) => {{
        const url = String(input);
        const path = url.includes('/api/platform/v1') ? url.split('/api/platform/v1')[1] : url;
        const ok = value => new Response(JSON.stringify(value), {{status:200, headers:{{'content-type':'application/json'}}}});
        if (path === '/readyz') return f.serviceReady ? ok({{status:'READY', checks:{{accountPlatformService:{{status:'READY',detail:'账户服务可用'}}}}}}) : new Response(JSON.stringify({{status:'NOT_READY',checks:{{accountPlatformService:{{status:'BLOCKED',detail:'账户服务未完成部署身份与存储就绪检查'}}}}}}), {{status:503,headers:{{'content-type':'application/json'}}}});
        if (path.startsWith('/session')) return f.authenticated ? ok({{account:f.account, csrf:'csrf-browser-fixture'}}) : new Response(JSON.stringify({{error:{{code:'UNAUTHENTICATED',message:'请先登录'}}}}), {{status:401,headers:{{'content-type':'application/json'}}}});
        if (path.startsWith('/notes?')) {{ if (f.synces) f.downstreamReads.notes += 1; return ok({{notes:f.notes}}); }}
        if (path.startsWith('/notes/') && path !== '/notes/export') {{ const id=decodeURIComponent(path.split('/').pop()); const note=f.notes.find(item => item.id===id); return note ? ok({{note:{{...note,content:{json.dumps(NOTE_CONTENT, ensure_ascii=False)}[id]}}}}) : new Response(JSON.stringify({{error:{{code:'NOT_FOUND',message:'笔记不存在'}}}}),{{status:404,headers:{{'content-type':'application/json'}}}}); }}
        if (path === '/notes/export') {{ return ok({{notes:f.notes.map(note => ({{...note,content:{json.dumps(NOTE_CONTENT, ensure_ascii=False)}[note.id]}}))}}); }}
        if (path === '/analytics/dashboard') {{ if (f.synces) f.downstreamReads.analytics += 1; return ok({{dashboard:f.dashboard}}); }}
        if (path === '/profile') {{ if (f.synces) f.downstreamReads.profile += 1; return ok({{account:f.account}}); }}
        if (path === '/weread/sync') {{
          f.synces += 1;
          f.account.weread.lastSyncAt = Math.floor(Date.now()/1000);
          f.dashboard.officialReading.statistics.overall.totalReadingTimeSeconds = 108000;
          f.dashboard.officialReadingPeriods.items.find(item => item.mode === 'overall').value = 108000;
          f.dashboard.dataFreshness.weread.lastSyncedAt = f.account.weread.lastSyncAt;
          f.notes = [...f.notes, {{id:'note-sync-3',title:'同步后的真实笔记',source:'weread',category:'历史',updatedAt:1785283200000,version:1}}];
          return ok({{summary:{{syncMode:'incremental',notebookBooks:1,skippedUnchangedBooks:0,updatedDocuments:1,unchangedDocuments:0,coverage:{{verified:true}}}},failures:[]}});
        }}
        if (path === '/consent') return ok({{consent:f.account.consent}});
        if (path === '/account/sessions') return ok({{sessions:f.sessions}});
        if (path.startsWith('/status/business-lines')) return ok({{businessLines:[]}});
        if (path.startsWith('/imports/')) return ok({{items:[{{id:'fixture-1',label:'阅读笔记',detail:'只读内容'}}]}});
        return ok({{}});
      }};
      window.confirm = () => false;
      window.open = () => null;
    }})();'''


def load(page: Page, authenticated: bool, service_ready: bool = True) -> None:
    page.set_default_timeout(8000)
    page.set_content(HTML, wait_until="domcontentloaded")
    page.evaluate(fixture_script(authenticated, service_ready))
    page.add_script_tag(type="module", content=BUNDLE)
    page.wait_for_selector("#platform-main")


def no_overflow(page: Page, label: str) -> None:
    values = page.evaluate("() => ({viewport:document.documentElement.clientWidth,html:document.documentElement.scrollWidth,body:document.body.scrollWidth})")
    assert values["html"] <= values["viewport"] + 1, f"{label}: html overflow {values}"
    assert values["body"] <= values["viewport"] + 1, f"{label}: body overflow {values}"


def touch_targets(page: Page, label: str) -> None:
    undersized = page.evaluate("""() => [...document.querySelectorAll('button')]
      .filter(el => { const r=el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>0 && r.height>0 && s.visibility!=='hidden' && !el.disabled && r.height<43.5; })
      .map(el => ({text:(el.textContent||'').trim().slice(0,50),height:el.getBoundingClientRect().height,cls:el.className}))""")
    assert not undersized, f"{label}: controls below 44px {undersized[:8]}"


def assert_clean(page_errors: list[str], console_errors: list[str], label: str) -> None:
    assert not page_errors, f"{label}: page errors {page_errors}"
    assert not console_errors, f"{label}: console errors {console_errors}"


def auth_contract(browser: Browser, width: int) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": width, "height": 1000}, locale="zh-CN")
    page = context.new_page(); page_errors: list[str] = []; console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    load(page, False)
    page.get_by_role("heading", name="一个账户，统一保存、同步和理解你的全部阅读笔记。").wait_for()
    for name in ["验证密钥并创建账户", "用 Google 创建", "用 GitHub 创建", "用 Notion 创建"]:
        assert page.get_by_role("button", name=name).is_visible(), name
    page.get_by_text("使用邮箱和密码", exact=True).click()
    assert page.locator("#account-email").is_visible()
    font_size = float(page.locator("#account-email").evaluate("e=>parseFloat(getComputedStyle(e).fontSize)"))
    assert font_size >= 16, font_size
    page.get_by_role("tab", name="登录").click()
    assert page.get_by_role("button", name="邮箱密码登录").is_visible()
    assert page.get_by_role("button", name="用密钥登录").is_visible()
    page.keyboard.press("Tab")
    focus = page.evaluate("() => ({tag:document.activeElement.tagName, outline:getComputedStyle(document.activeElement).outlineStyle})")
    assert focus["outline"] != "none", f"keyboard focus not visible: {focus}"
    no_overflow(page, f"auth-{width}"); touch_targets(page, f"auth-{width}")
    assert_clean(page_errors, console_errors, f"auth-{width}")
    context.close()
    return {"surface": "auth", "width": width, "status": "PASS"}


def account_contract(browser: Browser, width: int) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": width, "height": 1050}, locale="zh-CN", reduced_motion="reduce")
    page = context.new_page(); page_errors: list[str] = []; console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    load(page, True)
    page.get_by_role("heading", name="早上好，新手读者").wait_for()
    assert page.get_by_text("不需要理解 API、仓库或 Vault。按顺序点按钮即可。").is_visible()
    assert page.get_by_text("你的笔记、连接与画像已经绑定到同一账户", exact=False).is_visible()
    assert page.get_by_role("heading", name="你的阅读偏好，已经整合到首页").is_visible()
    assert page.get_by_role("button", name="下载微信读书数据（JSON）").is_visible()

    page.get_by_role("button", name="导入与连接").click()
    page.get_by_role("heading", name="选择你现在使用的应用").wait_for()
    for name in ["微信读书", "Notion", "Obsidian", "GitHub", "Google Drive"]:
        assert page.get_by_role("heading", name=name).is_visible(), name
    assert page.get_by_text("你在哪里写笔记，就点哪个图标。", exact=False).is_visible()
    page.locator("button[data-source='obsidian']").click()
    assert page.get_by_role("heading", name="选择 Obsidian 笔记").is_visible()
    assert page.get_by_role("button", name="选择 Vault 文件夹").is_visible()
    assert page.get_by_role("button", name="我只有 ZIP 或 Markdown").is_visible()

    page.get_by_role("button", name="阅读画像").click()
    page.get_by_role("heading", name="你的真实阅读数据、笔记活动与潜在下一步").wait_for()
    assert page.get_by_role("heading", name="微信读书官方阅读快照").is_visible()
    assert page.locator(".reading-snapshot-item").count() == 4
    assert page.get_by_role("heading", name="类别分布").is_visible()
    assert page.get_by_role("heading", name="来源分布").count() == 0
    assert page.locator("[data-category-row]").count() == 2
    assert page.locator("[data-note-trend-fill]").count() == 2
    assert page.get_by_text("2 个活跃周", exact=True).is_visible()
    assert page.get_by_text("累计", exact=True).is_visible()
    assert page.get_by_role("heading", name="阅读进展").is_visible()
    assert page.locator("[data-reading-progress]").count() == 2
    assert page.get_by_text("41%", exact=True).is_visible()
    assert page.get_by_role("img", name="近九十天笔记活动").is_visible()
    assert page.get_by_role("heading", name="潜在推荐").is_visible()
    assert page.get_by_text("继续整理系统思维主题").is_visible()
    weread_link = page.get_by_role("link", name="在微信读书打开")
    assert weread_link.is_visible()
    assert weread_link.get_attribute("href") == "https://weread.qq.com/web/reader/fixture-book-123"
    assert page.get_by_role("button", name="复制书名").count() == 2
    assert page.get_by_role("button", name="复制作者").count() == 2
    page.get_by_role("button", name="复制书名").first.click()
    page.wait_for_function("() => window.__browserFixture.copied.includes('继续整理系统思维主题')")
    assert page.get_by_text("不会把笔记正文发送给模型", exact=False).is_visible()

    page.get_by_role("button", name="首页").click()
    page.get_by_role("heading", name="早上好，新手读者").wait_for()
    page.get_by_role("button", name="立即同步").click()
    page.wait_for_function("() => window.__browserFixture.synces === 1")
    page.wait_for_function("() => { const r=window.__browserFixture.downstreamReads; return r.profile && r.notes && r.analytics; }")
    downstream = page.evaluate("() => window.__browserFixture.downstreamReads")
    assert downstream["profile"] >= 1 and downstream["notes"] >= 1 and downstream["analytics"] >= 1, downstream
    page.get_by_role("heading", name="所有来源，统一保存在你的账户").wait_for()
    assert page.get_by_text("同步后的真实笔记", exact=True).is_visible()
    page.get_by_role("button", name="阅读画像").click()
    page.get_by_role("heading", name="你的真实阅读数据、笔记活动与潜在下一步").wait_for()
    assert page.get_by_text("30小时0分钟", exact=True).count() >= 1

    page.get_by_role("button", name="我的笔记").click()
    page.get_by_role("heading", name="所有来源，统一保存在你的账户").wait_for()
    for name in ["模糊搜索", "书籍", "作者", "开始时间", "结束时间", "打包下载当前结果", "带当前结果问 ChatGPT"]:
        assert page.get_by_text(name, exact=True).is_visible(), name
    assert page.get_by_text("点击笔记才会按需解密并显示完整正文。", exact=False).is_visible()
    assert page.locator(".notes-workbench .note-row").count() == 3
    page.locator("#note-search").fill("系统")
    assert page.locator(".notes-workbench .note-row").count() == 1
    page.locator("#note-book").fill("系统思维")
    assert page.locator(".notes-workbench .note-row").count() == 1
    page.get_by_role("button", name="查看正文").click()
    page.get_by_role("heading", name="系统思维摘录").wait_for()
    assert "以反馈环路理解复杂系统，而不是只追逐短期结果。" in page.locator(".note-detail-body p").inner_text()
    assert page.get_by_role("button", name="编辑笔记").is_visible()
    page.locator(".note-detail-modal .modal-close-action").click()
    page.get_by_role("button", name="清除条件").click()
    assert page.locator(".notes-workbench .note-row").count() == 3
    page.get_by_role("button", name="问 ChatGPT").first.click()
    page.get_by_text("已下载阅读资料；请打开 ChatGPT 后手动添加该文件。", exact=True).wait_for()
    page.get_by_role("button", name="打包下载当前结果").click()
    page.get_by_text("当前显示的笔记已打包下载。", exact=True).wait_for()
    page.get_by_role("button", name="带当前结果问 ChatGPT").click()
    page.get_by_text("已下载阅读资料；请打开 ChatGPT 后手动添加该文件。", exact=True).wait_for()

    page.get_by_role("button", name="账户与安全").click()
    page.get_by_role("heading", name="管理你的身份、设备、连接和数据选择").wait_for()
    assert page.get_by_text("账户 ID 不随密钥或登录方式变化", exact=False).is_visible()
    assert page.get_by_text("不会因为 Google、GitHub、Notion 或邮箱相同而静默合并账户", exact=False).is_visible()
    assert page.get_by_role("heading", name="已登录设备").is_visible()
    for name in ["修改邮箱和密码", "退出其他设备", "轮换微信读书密钥", "导出我的全部数据", "永久删除账户"]:
        assert page.get_by_role("button", name=name).is_visible(), name

    no_overflow(page, f"account-{width}"); touch_targets(page, f"account-{width}")
    assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches") is True
    assert_clean(page_errors, console_errors, f"account-{width}")
    context.close()
    return {"surface": "account", "width": width, "status": "PASS", "imports": "PASS", "analytics": "PASS", "security": "PASS"}



def service_blocker_contract(browser: Browser) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 390, "height": 900}, locale="zh-CN")
    page = context.new_page(); page_errors: list[str] = []; console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    load(page, False, service_ready=False)
    page.get_by_role("heading", name="账户服务尚未完成安全连接。").wait_for()
    assert page.get_by_role("link", name="先用匿名迁移工具").is_visible()
    assert page.get_by_role("link", name="查看系统状态").is_visible()
    assert page.get_by_role("button", name="验证密钥并创建账户").count() == 0
    page.get_by_role("button", name="重新检查").click()
    page.get_by_role("heading", name="账户服务尚未完成安全连接。").wait_for()
    no_overflow(page, "service-blocker-390"); touch_targets(page, "service-blocker-390")
    assert_clean(page_errors, console_errors, "service-blocker-390")
    context.close()
    return {"surface": "service-blocker", "width": 390, "status": "PASS", "falseLoginEntryPrevented": True}

def main() -> int:
    report: dict[str, Any] = {"suite": "v0.0.0.1.9-account-whitebox", "mode": "embedded-real-ui-source-deterministic-api-double", "status": "FAIL", "checks": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=CHROMIUM, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                report["checks"].append(service_blocker_contract(browser))
                for width in (320, 390, 1440):
                    report["checks"].append(auth_contract(browser, width))
                    report["checks"].append(account_contract(browser, width))
            finally:
                browser.close()
        report["status"] = "PASS"; report["passed"] = len(report["checks"])
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"; report["traceback"] = traceback.format_exc()
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 1


if __name__ == "__main__":
    raise SystemExit(main())
