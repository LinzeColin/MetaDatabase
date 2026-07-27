#!/usr/bin/env python3
"""同源 UI 质量验收：响应式、触控、键盘、静态法律/状态页和高对比边界。"""
from __future__ import annotations
import json, os, re
from pathlib import Path
from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("WEREAD_PORT_EVIDENCE", "/tmp/weread-port-ui-quality"))
OUT.mkdir(parents=True, exist_ok=True)
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")
CSS = (APP / "src/ui/styles.css").read_text(encoding="utf-8")
RESULTS=[]

def check(name, condition, detail=None):
    RESULTS.append({"name":name,"status":"PASS" if condition else "FAIL","detail":detail})
    print(f"[{'PASS' if condition else 'FAIL'}] {name}", flush=True)
    if not condition: raise AssertionError(f"{name}: {detail}")

def inline_static(route):
    html=(APP/route/"index.html").read_text(encoding="utf-8")
    html=re.sub(r'<link rel="stylesheet" href="/src/ui/styles.css"\s*/?>', f"<style>{CSS}</style>", html)
    html=re.sub(r'<script type="module" src="/src/ui/app.js"></script>', '', html)
    return html

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, executable_path=CHROMIUM, args=["--no-sandbox","--disable-dev-shm-usage"])
    for width,height,label in [(1440,1000,"1440"),(1024,900,"1024"),(768,900,"768"),(375,812,"375"),(320,800,"320")]:
        ctx=browser.new_context(viewport={"width":width,"height":height}, color_scheme="light", reduced_motion="reduce")
        page=ctx.new_page(); page.set_content(inline_static("status"), wait_until="domcontentloaded")
        dims=page.locator("body").evaluate("e=>({sw:e.scrollWidth,cw:e.clientWidth,fs:parseFloat(getComputedStyle(e).fontSize)})")
        check(f"{label}px 状态页无页面横向溢出", dims["sw"] <= dims["cw"], dims)
        check(f"{label}px 正文字号不低于 16px", dims["fs"] >= 16, dims)
        check(f"{label}px 七业务线完整", page.locator("[data-business-line]").count()==7, page.locator("[data-business-line]").count())
        if width <= 768:
            matrix=page.locator(".business-table-wrap").evaluate("e=>({sw:e.scrollWidth,cw:e.clientWidth})")
            display=page.locator(".business-governance table").evaluate("e=>getComputedStyle(e).display")
            detail={"wrapper":matrix,"tableDisplay":display}
            check(f"{label}px 业务矩阵真实卡片化且无横滚", matrix["sw"] <= matrix["cw"] and display == "block", detail)
        ctx.close()

    for route, required in [("privacy",["隐私政策","我们处理哪些数据","保存、清除与备份边界"]),("terms",["使用条款","禁止用途","安全停止"]),("status",["系统状态","端到端白箱治理矩阵"])]:
        ctx=browser.new_context(viewport={"width":390,"height":844}, java_script_enabled=False)
        page=ctx.new_page(); page.set_content(inline_static(route), wait_until="domcontentloaded")
        text=page.locator("body").inner_text()
        check(f"{route} 禁用 JavaScript 仍可读", all(x in text for x in required), text[:300])
        ctx.close()

    # Use the real product HTML/CSS for keyboard and touch sizing; no network or Worker execution needed.
    # Render a minimal control surface with the real CSS.
    index=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><a class="skip-link" href="#main">跳到正文</a><main id="main"><button class="button primary">主动作</button><a class="button secondary" href="#x">辅助动作</a></main></body></html>'
    ctx=browser.new_context(viewport={"width":375,"height":812}, reduced_motion="reduce")
    page=ctx.new_page(); page.set_content(index, wait_until="domcontentloaded")
    sizes=page.locator(".button").evaluate_all("els=>els.map(e=>({w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height}))")
    check("移动端可交互控件高度至少 44px", all(x["h"]>=44 for x in sizes), sizes)
    page.keyboard.press("Tab")
    focused=page.evaluate("document.activeElement.className")
    check("首个 Tab 命中跳转链接", "skip-link" in focused, focused)
    check("减少动态效果关闭平滑滚动", page.evaluate("getComputedStyle(document.documentElement).scrollBehavior") == "auto")
    ctx.close(); browser.close()

summary={"status":"PASS" if all(x["status"]=="PASS" for x in RESULTS) else "FAIL","pass":sum(x["status"]=="PASS" for x in RESULTS),"fail":sum(x["status"]=="FAIL" for x in RESULTS),"checks":RESULTS}
(OUT/"UI_QUALITY_RESULTS.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False,indent=2))
