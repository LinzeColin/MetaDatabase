#!/usr/bin/env python3
"""交付流水线第 8 关：公网端到端执行器。

读 `旅程/*.yaml`（格式见 Governance 仓 `交付流水线/旅程格式.md`，本执行器只实现、不改格式），
用 Playwright Chromium 无头，在 桌面 / 手机 / 暗色 三种视口各走一遍每条旅程，
输出 `<out>/<时间戳>/{report.json, 报告.md, 各截图.png}`。

退出码：0 全部通过；1 有不通过；2 执行器自身出错（参数、旅程文件格式、浏览器起不来、程序 bug）。
只含公网地址，不含任何密钥。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import traceback
import urllib.request
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import yaml

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
DEFAULT_JOURNEY_DIR = HERE / "旅程"

VIEWPORTS = ("desktop", "mobile", "dark")
VP_LABEL = {"desktop": "桌面", "mobile": "手机", "dark": "暗色"}

# axe-core 版本固定；自动下载时校验 sha256（镜像里由 Dockerfile 用同一校验值打包，并用 E2E_AXE_JS 指向）
AXE_VERSION = "4.11.4"
AXE_SHA256 = "fb83a4378d978ecb7d2dae48a3a3778a84c971ac692f3afd45d714fba89c0f0d"
AXE_URL = f"https://cdnjs.cloudflare.com/ajax/libs/axe-core/{AXE_VERSION}/axe.min.js"

MAX_LINKS_PER_PAGE = 30

# 默认禁用词：(展示名, 正则)。undefined/NaN/null/TODO 按独立词匹配，其余按子串。
FORBID = [
    ("undefined", re.compile(r"\bundefined\b")),
    ("NaN", re.compile(r"\bNaN\b")),
    ("null", re.compile(r"\bnull\b")),
    ("Traceback", re.compile(r"Traceback")),
    ("Exception", re.compile(r"Exception")),
    ("TODO", re.compile(r"\bTODO\b")),
    ("lorem", re.compile(r"lorem", re.I)),
    ("[object Object]", re.compile(re.escape("[object Object]"))),
    ("Internal Server Error", re.compile(r"Internal Server Error", re.I)),
]

STEP_KEYS = (
    "goto", "expect_text", "expect_any_text", "expect_no_text", "expect_visible",
    "click_text", "click", "expect_url_contains", "expect_json", "screenshot",
)


class SpecError(Exception):
    """旅程文件格式问题 —— 执行器无法继续，退出码 2。"""


class StepFail(Exception):
    """步骤条件不满足 —— 该旅程在该视口判不通过。"""


# ---------------------------------------------------------------- 旅程文件读取与校验

def _need(cond: bool, where: str, msg: str) -> None:
    if not cond:
        raise SpecError(f"{where}：{msg}")


def _str_list(v, where: str, key: str) -> list[str]:
    _need(isinstance(v, list) and v and all(isinstance(x, str) and x for x in v), where,
          f"`{key}` 必须是非空的文字列表")
    return v


def validate_step(step, where: str) -> tuple[str, object]:
    _need(isinstance(step, dict) and len(step) == 1, where, "每一步必须是只有一个键的映射")
    key, val = next(iter(step.items()))
    _need(key in STEP_KEYS, where, f"未知步骤 `{key}`，可用：{', '.join(STEP_KEYS)}")
    if key == "goto":
        _need(val is None or isinstance(val, str), where, "`goto` 必须是路径或完整 URL（可为空串）")
        val = val or ""
    elif key in ("expect_text", "expect_any_text", "expect_no_text"):
        _str_list(val, where, key)
    elif key in ("expect_visible", "click", "click_text", "expect_url_contains", "screenshot"):
        _need(isinstance(val, (str, int)) and str(val) != "", where, f"`{key}` 必须是非空文字")
        val = str(val)
    elif key == "expect_json":
        _need(isinstance(val, dict) and isinstance(val.get("url"), str) and val["url"], where,
              "`expect_json` 需要 {url, path, min_items}")
        mi = val.get("min_items", 1)
        _need(isinstance(mi, int) and not isinstance(mi, bool) and mi >= 0, where, "`min_items` 必须是非负整数")
        _need(isinstance(val.get("path", ""), str), where, "`path` 必须是点路径文字")
    return key, val


def load_spec(path: Path) -> dict:
    where = path.name
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise SpecError(f"{where}：读不了或不是合法 YAML（{e}）") from e
    _need(isinstance(raw, dict), where, "顶层必须是映射")
    _need(isinstance(raw.get("project"), str) and raw["project"].strip(), where, "缺 `project`")
    base = raw.get("base_url")
    _need(isinstance(base, str) and urlparse(base).scheme in ("http", "https") and urlparse(base).netloc,
          where, "`base_url` 必须是 http(s) 完整地址")
    vps = raw.get("viewports") or list(VIEWPORTS)
    _need(isinstance(vps, list) and all(v in VIEWPORTS for v in vps), where,
          f"`viewports` 只能取 {list(VIEWPORTS)}")
    extra = raw.get("forbid_text_extra") or []
    _need(isinstance(extra, list) and all(isinstance(x, str) and x for x in extra), where,
          "`forbid_text_extra` 必须是文字列表")
    fresh = raw.get("freshness")
    if fresh is not None:
        _need(isinstance(fresh, dict), where, "`freshness` 必须是映射")
        _need(isinstance(fresh.get("pattern"), str), where, "`freshness.pattern` 必填")
        try:
            rx = re.compile(fresh["pattern"])
        except re.error as e:
            raise SpecError(f"{where}：`freshness.pattern` 不是合法正则（{e}）") from e
        _need(rx.groups >= 1, where, "`freshness.pattern` 至少要有一个捕获组")
        mh = fresh.get("max_age_hours")
        _need(isinstance(mh, (int, float)) and not isinstance(mh, bool) and mh > 0, where,
              "`freshness.max_age_hours` 必须是正数")
    js = raw.get("journeys")
    _need(isinstance(js, list) and js, where, "`journeys` 必须是非空列表")
    journeys = []
    for ji, j in enumerate(js, 1):
        jw = f"{where} 第 {ji} 条旅程"
        _need(isinstance(j, dict) and isinstance(j.get("name"), str) and j["name"].strip(), jw, "缺 `name`")
        _need(isinstance(j.get("steps"), list) and j["steps"], jw, "`steps` 必须是非空列表")
        steps = [validate_step(s, f"{jw}「{j['name']}」第 {si} 步") for si, s in enumerate(j["steps"], 1)]
        journeys.append({"name": j["name"].strip(), "steps": steps})
    return {
        "file": path.name, "project": raw["project"].strip(), "owner_words": raw.get("owner_words", ""),
        "base_url": base, "viewports": vps, "forbid_text_extra": extra, "freshness": fresh, "journeys": journeys,
    }


# ---------------------------------------------------------------- 小工具

def safe(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("_") or "_"


def origin(url: str) -> tuple[str, str, int]:
    u = urlparse(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    return (u.scheme, (u.hostname or "").lower(), port)


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def clip(s: str, n: int = 160) -> str:
    s = norm_ws(str(s))
    return s if len(s) <= n else s[: n - 1] + "…"


def quote_list(xs) -> str:
    return "、".join(f"「{x}」" for x in xs)


def describe(key: str, val) -> str:
    """把步骤翻成人话。"""
    if key == "goto":
        return f"打开「{val or '首页'}」"
    if key == "expect_text":
        return f"页面上应同时出现 {quote_list(val)}"
    if key == "expect_any_text":
        return f"页面上应出现 {quote_list(val)} 中的任意一个"
    if key == "expect_no_text":
        return f"页面上不应出现 {quote_list(val)}"
    if key == "expect_visible":
        return f"元素 {val} 应可见且有内容"
    if key == "click_text":
        return f"点击文字「{val}」"
    if key == "click":
        return f"点击元素 {val}"
    if key == "expect_url_contains":
        return f"网址应包含「{val}」"
    if key == "expect_json":
        return f"接口 {val['url']} 的 {val.get('path') or '根'} 应至少有 {val.get('min_items', 1)} 项"
    if key == "screenshot":
        return f"截图「{val}」"
    return key


def parse_time(s: str) -> tuple[dt.datetime, bool]:
    """解析日期/日期时间，返回 (UTC 时间, 是否因时区不明按 UTC 处理)。"""
    s = s.strip()
    if re.fullmatch(r"\d{13}", s):
        return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc), False
    if re.fullmatch(r"\d{10}", s):
        return dt.datetime.fromtimestamp(int(s), dt.timezone.utc), False
    m = re.fullmatch(
        r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?"
        r"(?:[T\s]+(\d{1,2})[:时](\d{2})(?::(\d{2}))?(?:\.\d+)?)?\s*(Z|UTC|GMT|[+-]\d{2}:?\d{2})?",
        s,
    )
    if not m:
        raise ValueError(f"无法识别的日期时间格式：{s!r}")
    y, mo, d, hh, mm, ss, tz = m.groups()
    naive = dt.datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
    if tz is None:
        return naive.replace(tzinfo=dt.timezone.utc), True
    if tz in ("Z", "UTC", "GMT"):
        return naive.replace(tzinfo=dt.timezone.utc), False
    sign = 1 if tz[0] == "+" else -1
    digits = tz[1:].replace(":", "")
    off = dt.timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return naive.replace(tzinfo=dt.timezone(sign * off)).astimezone(dt.timezone.utc), False


def dotted_get(data, path: str):
    cur = data
    if not path:
        return cur
    for seg in path.split("."):
        if isinstance(cur, list) and seg.lstrip("-").isdigit():
            i = int(seg)
            if not -len(cur) <= i < len(cur):
                raise StepFail(f"路径 {path} 中下标 {seg} 超出范围（数组只有 {len(cur)} 项）")
            cur = cur[i]
        elif isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            raise StepFail(f"路径 {path} 在「{seg}」处取不到值")
    return cur


def load_axe() -> tuple[str | None, str]:
    """返回 (axe 源码或 None, 说明)。"""
    p = os.environ.get("E2E_AXE_JS")
    if p:
        try:
            return Path(p).read_text(encoding="utf-8"), f"axe-core（{p}）"
        except OSError as e:
            return None, f"E2E_AXE_JS 读不了：{e}"
    cache_root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    cache = cache_root / "linze-e2e" / f"axe-{AXE_VERSION}.min.js"
    try:
        if cache.exists() and hashlib.sha256(cache.read_bytes()).hexdigest() == AXE_SHA256:
            return cache.read_text(encoding="utf-8"), f"axe-core {AXE_VERSION}"
        with urllib.request.urlopen(AXE_URL, timeout=30) as r:
            body = r.read()
        if hashlib.sha256(body).hexdigest() != AXE_SHA256:
            return None, "axe-core 下载后校验值不符，已跳过"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(body)
        return body.decode("utf-8"), f"axe-core {AXE_VERSION}"
    except Exception as e:  # 网络等原因：axe 只报告，不因此让整次运行失败
        return None, f"axe-core 不可用，已跳过（{type(e).__name__}）"


# ---------------------------------------------------------------- 浏览器侧

DOM_SIG_JS = """() => { const s = document.documentElement.outerHTML; let h = 5381;
  for (let i = 0; i < s.length; i++) { h = ((h << 5) + h + s.charCodeAt(i)) | 0; } return s.length + ':' + h; }"""

VISIBLE_JS = """(sel) => {
  const media = 'img,svg,canvas,video,picture,iframe,object,embed';
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0 || cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
    const hasText = (el.innerText || el.textContent || '').trim().length > 0;
    const hasMedia = el.matches(media) || !!el.querySelector(media);
    if (hasText || hasMedia) return true;
  }
  return false;
}"""


class JourneyRun:
    """一条旅程在一个视口里的一次执行：一个独立的浏览器上下文。"""

    def __init__(self, pw, browser, spec, journey, vp, out_dir: Path, shared: dict):
        self.pw, self.browser, self.spec, self.journey, self.vp = pw, browser, spec, journey, vp
        self.out_dir, self.shared = out_dir, shared
        self.origin = origin(spec["base_url"])
        self.failures: list[dict] = []
        self.steps: list[dict] = []
        self.shots: list[str] = []
        self.pageerrors: list[str] = []
        self.pageerrors_reported = 0
        self.http_errors: set[tuple[int, str]] = set()
        self.forbid_hits: set[tuple[str, str, str]] = set()
        self.link_checked_urls: set[str] = set()
        self.axe: dict = {}
        self.req_count = 0
        self.popup: object | None = None
        self.hscroll_max = 0
        self.page = None

    # -- 装配
    def ctx_args(self) -> dict:
        if self.vp == "mobile":
            args = dict(self.pw.devices["iPhone 13"])
            args.pop("default_browser_type", None)
            return {**args, "locale": "zh-CN"}
        args = {"viewport": {"width": 1440, "height": 900}, "locale": "zh-CN"}
        if self.vp == "dark":
            args["color_scheme"] = "dark"
        return args

    def attach(self, page) -> None:
        page.on("pageerror", lambda e: self.pageerrors.append(clip(str(e), 300)))
        page.on("request", lambda r: setattr(self, "req_count", self.req_count + 1))

        def on_response(resp):
            if resp.status >= 400 and origin(resp.url) == self.origin:
                self.http_errors.add((resp.status, resp.url))
        page.on("response", on_response)

    def fail(self, kind: str, message: str, step: int | None = None) -> None:
        self.failures.append({"kind": kind, "step": step, "message": message})

    # -- 页面辅助
    def settle(self) -> None:
        page = self.page
        try:
            page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(300)

    def visible_text(self) -> str:
        try:
            return norm_ws(self.page.inner_text("body", timeout=5000))
        except Exception:
            return ""

    def poll(self, fn, timeout: float = 8.0):
        end = time.monotonic() + timeout
        while True:
            r = fn()
            if r or time.monotonic() >= end:
                return r
            self.page.wait_for_timeout(250)

    # -- 每个页面状态后的默认检查
    def checkpoint(self) -> None:
        self.settle()
        page = self.page
        url = page.url
        text = self.visible_text()
        words = [(w, rx) for w, rx in FORBID] + [(w, re.compile(re.escape(w))) for w in self.spec["forbid_text_extra"]]
        for name, rx in words:
            m = rx.search(text)
            if m:
                a, b = max(0, m.start() - 20), min(len(text), m.end() + 20)
                self.forbid_hits.add((name, urldefrag(url)[0], text[a:b]))
        if self.vp == "mobile":
            try:
                sw, cw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                if sw > cw + 2:
                    self.hscroll_max = max(self.hscroll_max, sw - cw)
                    self.fail("hscroll", f"手机视口下页面可以横向滚动（页面宽 {sw}px，屏幕宽 {cw}px），地址 {url}")
            except Exception:
                pass
        key = urldefrag(url)[0]
        if key not in self.link_checked_urls:
            self.link_checked_urls.add(key)
            self.check_links(key)
            self.run_axe(key)

    def check_links(self, page_url: str) -> None:
        try:
            hrefs = self.page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except Exception:
            return
        seen, todo = set(), []
        for h in hrefs:
            if not isinstance(h, str) or urlparse(h).scheme not in ("http", "https"):
                continue
            h = urldefrag(h)[0]
            if h in seen or h == page_url or origin(h) != self.origin:
                continue
            seen.add(h)
            todo.append(h)
        cache = self.shared.setdefault("links", {})
        for link in todo[:MAX_LINKS_PER_PAGE]:
            if link not in cache:
                cache[link] = self.probe(link)
            status = cache[link]
            if status is None or status >= 400:
                self.fail("broken_link", f"页面 {page_url} 上的链接打不开：{link}（{'连不上' if status is None else 'HTTP ' + str(status)}）")

    def probe(self, link: str):
        req = self.ctx.request
        try:
            st = req.head(link, timeout=15000).status
            if st < 400:
                return st
        except Exception:
            pass
        try:
            return req.get(link, timeout=15000).status
        except Exception:
            return None

    def run_axe(self, url: str) -> None:
        src = self.shared["axe_src"]
        if src is None:
            self.axe.setdefault("skipped", self.shared["axe_note"])
            return
        try:
            self.page.evaluate(src)
            res = self.page.evaluate(
                "() => axe.run().then(r => r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length})))")
        except Exception as e:
            self.axe.setdefault("error", clip(str(e), 120))
            return
        crit = [v for v in res if v["impact"] == "critical"]
        self.axe.setdefault("critical", 0)
        self.axe["critical"] += sum(v["nodes"] for v in crit)
        self.axe.setdefault("rules", [])
        self.axe["rules"] += [v["id"] for v in crit if v["id"] not in self.axe["rules"]]
        self.axe["version"] = AXE_VERSION

    # -- 步骤
    def new_shot_path(self, name: str) -> Path:
        base = f"{safe(self.spec['project'])}-{safe(self.journey['name'])}-{self.vp}-{safe(name)}"
        p, n = self.out_dir / f"{base}.png", 2
        while p.name in self.shots or p.exists():
            p = self.out_dir / f"{base}-{n}.png"
            n += 1
        return p

    def shot(self, name: str) -> None:
        p = self.new_shot_path(name)
        self.page.screenshot(path=str(p))
        self.shots.append(p.name)

    def step(self, key: str, val, idx: int) -> None:
        page = self.page
        base = self.spec["base_url"]
        if key == "goto":
            url = urljoin(base, val)
            errs_before = len(self.pageerrors)
            resp = page.goto(url, wait_until="load", timeout=30000)
            if resp is not None and not (200 <= resp.status < 400):
                raise StepFail(f"{url} 返回 HTTP {resp.status}")
            self.checkpoint()
            if len(self.pageerrors) > errs_before:
                self.pageerrors_reported = len(self.pageerrors)
                raise StepFail(f"页面出现 JS 报错：{self.pageerrors[errs_before]}")
        elif key == "expect_text":
            need = [norm_ws(x) for x in val]
            text = ""

            def check():
                nonlocal text
                text = self.visible_text()
                return all(x in text for x in need)
            if not self.poll(check):
                raise StepFail(f"页面上没找到：{quote_list([x for x in need if x not in text])}")
        elif key == "expect_any_text":
            need = [norm_ws(x) for x in val]
            if not self.poll(lambda: any(x in self.visible_text() for x in need)):
                raise StepFail(f"页面上一个都没找到：{quote_list(need)}")
        elif key == "expect_no_text":
            self.settle()
            text = self.visible_text()
            found = [x for x in (norm_ws(v) for v in val) if x in text]
            if found:
                raise StepFail(f"页面上出现了不该出现的文字：{quote_list(found)}")
        elif key == "expect_visible":
            try:
                ok = self.poll(lambda: page.evaluate(VISIBLE_JS, val))
            except Exception as e:
                raise StepFail(f"选择器 {val} 无法使用（{clip(str(e), 100)}）")
            if not ok:
                raise StepFail(f"没有找到可见且有内容的元素 {val}")
        elif key in ("click_text", "click"):
            self.do_click(key, val)
        elif key == "expect_url_contains":
            if not self.poll(lambda: val in page.url, timeout=5.0):
                raise StepFail(f"当前网址是 {page.url}，不包含「{val}」")
        elif key == "expect_json":
            url = urljoin(base, val["url"])
            try:
                r = self.ctx.request.get(url, timeout=20000)
            except Exception as e:
                raise StepFail(f"接口 {url} 连不上（{clip(str(e), 100)}）")
            if not 200 <= r.status < 400:
                raise StepFail(f"接口 {url} 返回 HTTP {r.status}")
            try:
                data = r.json()
            except Exception:
                raise StepFail(f"接口 {url} 返回的不是 JSON")
            target = dotted_get(data, val.get("path", ""))
            if not isinstance(target, list):
                raise StepFail(f"接口 {url} 的 {val.get('path') or '根'} 不是数组")
            need = val.get("min_items", 1)
            if len(target) < need:
                raise StepFail(f"接口 {url} 的 {val.get('path') or '根'} 只有 {len(target)} 项，至少应有 {need} 项")
        elif key == "screenshot":
            self.settle()
            self.shot(val)

    def do_click(self, key: str, val: str) -> None:
        page = self.page
        if key == "click_text":
            def find():
                for exact in (True, False):
                    loc = page.get_by_text(val, exact=exact).filter(visible=True)
                    if loc.count() > 0:
                        return loc.first
                return None
            loc = self.poll(find)
            if not loc:
                raise StepFail(f"页面上没有可点击的文字「{val}」")
        else:
            loc = page.locator(val).filter(visible=True)
            if not self.poll(lambda: loc.count() > 0):
                raise StepFail(f"页面上没有可见的元素 {val}")
            loc = loc.first
        before = (page.url, page.evaluate(DOM_SIG_JS), self.req_count)
        self.popup = None
        loc.click(timeout=8000)

        def changed():
            if self.popup is not None:
                return True
            p = self.page
            return p.url != before[0] or self.req_count > before[2] or p.evaluate(DOM_SIG_JS) != before[1]
        ok = self.poll(changed, timeout=3.0)
        if self.popup is not None:  # 点击开了新标签页：跟过去继续走
            self.page = self.popup
            self.popup = None
        if not ok:
            raise StepFail("点击后页面没有任何变化（网址、页面内容、网络请求都没动）")
        self.checkpoint()

    # -- 主流程
    def run(self) -> dict:
        self.ctx = self.browser.new_context(**self.ctx_args())
        self.ctx.set_default_timeout(20000)

        def on_page(p):
            if self.page is not None and p is not self.page:
                self.popup = p
                self.attach(p)
        self.ctx.on("page", on_page)
        self.page = self.ctx.new_page()
        self.attach(self.page)
        try:
            for i, (key, val) in enumerate(self.journey["steps"], 1):
                rec = {"index": i, "step": describe(key, val), "ok": True, "message": ""}
                self.steps.append(rec)
                try:
                    self.step(key, val, i)
                except StepFail as e:
                    rec.update(ok=False, message=str(e))
                except Exception as e:
                    # Playwright 的超时/导航错误等是页面问题；其余异常是执行器 bug，向外抛（退出码 2）
                    if type(e).__module__.startswith("playwright"):
                        rec.update(ok=False, message=clip(str(e).splitlines()[0] if str(e) else type(e).__name__, 200))
                    else:
                        raise
                if not rec["ok"]:
                    self.fail("step", f"第 {i} 步（{rec['step']}）没通过：{rec['message']}", i)
                    try:
                        p = self.new_shot_path(f"失败-第{i}步")
                        self.page.screenshot(path=str(p))
                        self.shots.append(p.name)
                    except Exception:
                        pass
                    break
            # 整条旅程结束后的汇总检查
            for name, url, ctxt in sorted(self.forbid_hits):
                self.fail("forbidden_text", f"页面 {url} 的可见文字里出现了不该出现的「{name}」（…{ctxt}…）")
            for err in self.pageerrors[self.pageerrors_reported:]:
                self.fail("pageerror", f"控制台有未捕获的 JS 错误：{err}")
            for status, url in sorted(self.http_errors):
                self.fail("http_error", f"同源请求返回 HTTP {status}：{url}")
        finally:
            self.ctx.close()
        return {
            "passed": not self.failures,
            "failures": self.failures,
            "steps": self.steps,
            "screenshots": self.shots,
            "checks": {
                "forbidden_text_hits": len(self.forbid_hits),
                "pageerrors": len(self.pageerrors),
                "http_errors": len(self.http_errors),
                "mobile_horizontal_overflow_px": self.hscroll_max if self.vp == "mobile" else None,
                "links_checked_pages": len(self.link_checked_urls),
                "axe": self.axe,
            },
        }


# ---------------------------------------------------------------- 新鲜度

def check_freshness(browser, spec, shared) -> dict | None:
    f = spec["freshness"]
    if not f:
        return None
    url = urljoin(spec["base_url"], f.get("url") or "")
    max_age = float(f["max_age_hours"])
    res = {"url": url, "pattern": f["pattern"], "max_age_hours": max_age, "passed": False}
    rx = re.compile(f["pattern"])
    ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
    try:
        text = None
        try:
            r = ctx.request.get(url, timeout=20000)
            if not 200 <= r.status < 400:
                res["message"] = f"{url} 返回 HTTP {r.status}，无法核对数据日期"
                return res
            body = r.text()
            if rx.search(body):
                text = body
        except Exception as e:
            res["message"] = f"{url} 连不上（{clip(str(e), 100)}）"
            return res
        m = rx.search(text) if text else None
        if not m:  # 数据可能是页面脚本渲染出来的：再用真实浏览器渲染后取可见文字
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="load", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                m = rx.search(page.inner_text("body", timeout=5000))
            except Exception as e:
                res["message"] = f"{url} 渲染失败（{clip(str(e), 100)}）"
                return res
        if not m:
            res["message"] = f"在 {url} 里没有找到匹配 {f['pattern']} 的数据日期"
            return res
        raw = m.group(1)
        res["found"] = raw
        try:
            when, assumed = parse_time(raw)
        except ValueError as e:
            res["message"] = str(e)
            return res
        res["assumed_utc"] = assumed
        age_h = (dt.datetime.now(dt.timezone.utc) - when).total_seconds() / 3600
        res["age_hours"] = round(age_h, 1)
        note = "（无时区信息，按 UTC 处理）" if assumed else ""
        if age_h > max_age:
            res["message"] = f"数据日期 {raw}{note} 距今 {age_h:.1f} 小时，超过允许的 {max_age:g} 小时，数据不新鲜"
        elif age_h < -26:  # 日期无时区时最多有 ±14h 误差，再多就是页面写错了
            res["message"] = f"数据日期 {raw}{note} 比现在晚了 {-age_h:.1f} 小时，日期不合理"
        else:
            res["passed"] = True
            res["message"] = f"数据日期 {raw}{note} 距今 {max(age_h, 0):.1f} 小时，在 {max_age:g} 小时内"
        return res
    finally:
        ctx.close()


# ---------------------------------------------------------------- 报告

def render_md(report: dict) -> str:
    L = ["# 公网端到端验收报告", ""]
    tot = report["totals"]
    L.append(f"- 运行时间（UTC）：{report['started_at']}　执行器 {report['runner_version']}")
    L.append(f"- 总体：{tot['projects']} 个项目，{tot['passed']} 个通过，{tot['failed']} 个不通过")
    L.append("- 判定口径：每条旅程在 桌面 / 手机 / 暗色 各走一遍，任何一个视口任何一项检查不过，该项目即不通过；"
             "无障碍（axe）的 critical 数只报告，不单独判不合格。")
    if any((p.get("freshness") or {}).get("assumed_utc") for p in report["projects"]):
        L.append("- 注：数据日期没有写时区的，一律按 UTC 处理（日期只到天的按当天 0 点 UTC）。")
    L.append(f"- 无障碍扫描：{report['axe_note']}")
    L.append("")
    for p in report["projects"]:
        L.append(f"## {p['project']} —— {'通过' if p['passed'] else '不通过'}")
        L.append("")
        L.append(f"- 地址：{p['base_url']}")
        if p.get("owner_words"):
            L.append(f"- 需求原话：{p['owner_words']}")
        reasons, shots = [], []
        for j in p["journeys"]:
            cells = []
            for vp in p["viewports"]:
                v = j["viewports"][vp]
                cells.append(f"{VP_LABEL[vp]} {'通过' if v['passed'] else '不通过'}")
                shots += v["screenshots"]
                for f in v["failures"]:
                    reasons.append(f"旅程「{j['name']}」在{VP_LABEL[vp]}：{f['message']}")
            L.append(f"- 旅程「{j['name']}」：{'，'.join(cells)}")
        fr = p.get("freshness")
        if fr:
            L.append(f"- 数据新鲜度：{'通过' if fr['passed'] else '不通过'} —— {fr['message']}")
            if not fr["passed"]:
                reasons.append(f"数据新鲜度：{fr['message']}")
        crit = [(j["name"], vp, j["viewports"][vp]["checks"]["axe"]) for j in p["journeys"] for vp in p["viewports"]]
        crit_n = sum(a.get("critical", 0) for _, _, a in crit)
        rules = sorted({r for _, _, a in crit for r in a.get("rules", [])})
        if any("critical" in a for _, _, a in crit):
            L.append(f"- 无障碍（只报告）：critical 级别违规共 {crit_n} 处" + (f"（{'、'.join(rules)}）" if rules else ""))
        if reasons:
            L.append("")
            L.append("不通过的原因：")
            seen = set()
            for r in reasons:
                if r not in seen:
                    seen.add(r)
                    L.append(f"- {r}")
        if shots:
            L.append("")
            L.append("截图：" + "、".join(shots))
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- 入口

def resolve_journeys(names: list[str], jdir: Path) -> list[Path]:
    if not names:
        files = sorted(jdir.glob("*.yaml"))
        if not files:
            raise SpecError(f"{jdir} 下没有 *.yaml 旅程文件")
        return files
    out = []
    for n in names:
        cands = [Path(n), jdir / n, jdir / f"{n}.yaml"]
        hit = next((c for c in cands if c.is_file()), None)
        if hit is None:
            raise SpecError(f"找不到旅程文件：{n}（找过 {', '.join(str(c) for c in cands)}）")
        out.append(hit)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="交付流水线第 8 关：公网端到端执行器")
    ap.add_argument("journeys", nargs="*", help="旅程文件（路径或旅程目录下的文件名）；缺省 = 旅程目录下全部 *.yaml")
    ap.add_argument("--journeys-dir", default=str(DEFAULT_JOURNEY_DIR))
    ap.add_argument("--out", default="out", help="输出根目录，每次运行建 <out>/<时间戳>/")
    args = ap.parse_args(argv)
    try:
        return _run(args)
    except SpecError as e:
        print(f"[执行器错误] 旅程文件有问题：{e}", file=sys.stderr)
        return 2
    except Exception:
        print("[执行器错误] 执行器自身出错：", file=sys.stderr)
        traceback.print_exc()
        return 2


def _run(args) -> int:
    from playwright.sync_api import sync_playwright

    files = resolve_journeys(args.journeys, Path(args.journeys_dir))
    specs = [load_spec(f) for f in files]  # 先全部校验，格式有错就在开浏览器前退出

    started = dt.datetime.now(dt.timezone.utc)
    out_root = Path(args.out)
    out_dir = out_root / started.strftime("%Y%m%d-%H%M%S")
    n = 2
    while out_dir.exists():
        out_dir = out_root / f"{started.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    out_dir.mkdir(parents=True)

    axe_src, axe_note = load_axe()
    shared = {"axe_src": axe_src, "axe_note": axe_note}
    report = {
        "runner_version": VERSION, "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "out_dir": str(out_dir), "axe_note": axe_note, "projects": [],
    }
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
            try:
                for spec in specs:
                    proj = {
                        "project": spec["project"], "file": spec["file"], "base_url": spec["base_url"],
                        "owner_words": spec["owner_words"], "viewports": spec["viewports"], "journeys": [],
                    }
                    for j in spec["journeys"]:
                        jr = {"name": j["name"], "viewports": {}}
                        for vp in spec["viewports"]:
                            jr["viewports"][vp] = JourneyRun(pw, browser, spec, j, vp, out_dir, shared).run()
                        proj["journeys"].append(jr)
                    proj["freshness"] = check_freshness(browser, spec, shared)
                    proj["passed"] = all(v["passed"] for jr in proj["journeys"] for v in jr["viewports"].values()) \
                        and (proj["freshness"] is None or proj["freshness"]["passed"])
                    report["projects"].append(proj)
            finally:
                browser.close()
    except BaseException:
        (out_dir / "executor-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finished = dt.datetime.now(dt.timezone.utc)
    report["finished_at"] = finished.strftime("%Y-%m-%d %H:%M:%S")
    npass = sum(1 for p in report["projects"] if p["passed"])
    report["totals"] = {"projects": len(report["projects"]), "passed": npass, "failed": len(report["projects"]) - npass}
    report["exit_code"] = 0 if npass == len(report["projects"]) else 1
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "报告.md").write_text(render_md(report), encoding="utf-8")
    print(f"报告目录: {out_dir}")
    print(f"结果: {npass}/{len(report['projects'])} 个项目通过，退出码 {report['exit_code']}")
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
