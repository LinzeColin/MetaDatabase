#!/usr/bin/env python3
"""B 站收藏夹取数路，真的读得到吗（v0.0.0.7 / G1）。

## 为什么有这个

Owner 2026-08-06 的原话：

    「我希望最后我来验收能给到我的是一个操作简单、满足要求、
      多平台聚合到一起的一个软件。不要永远把任何的半成品推到我面前来。」

在此之前 `SYNCABLE_NOW` 里只有 `generic-web`（Chrome 书签）——九个平台里
八个的 `sync_supported` 都是 false。「多平台聚合」那句话没有兑现。

原计划（T08/T10）是在浏览器里拦平台自己的响应，但那条路要 Owner 先去收藏夹页
按一次诊断按钮把接口地址抓出来。**那正是他说的「不要让我和你重复地反攻」。**
所以改成主动调 B 站自己的公开 REST 接口——地址是实测出来的，不需要他按任何东西。

## 这个演练量什么

三段，分得很清楚，因为**它们的可信度不一样**：

**A. 打真实接口**（`--live`，默认开）
   拿一个公开收藏夹跑完整条取数路：列收藏夹 → 翻页 → 归一化成入库条目。
   验的是「我们对 B 站接口的理解对不对」，这一段没法自己骗自己。

**B. 打真实接口的失败路**（`--live`）
   未登录时 nav 回什么、看不见的收藏夹回什么。
   **第二条是这条路上最危险的形状**：`{"code":0,"message":"OK","data":null}`
   ——成功码、成功文案、空数据。照着 `data?.list || []` 写就会得到
   「同步成功，0 条」，也就是 INV-NO-SILENT-ZERO 禁的那种零。

**C. 固定装置**（永远跑）
   翻页卡住、条数对不上、超出页数上限、深链条目——这几种没法在真接口上点着放，
   用固定装置驱动。**这一段的可信度低于 A/B**：装置是我写的，
   它和实现共用我的假设。所以它只验分支走对了，不作为「这条路能用」的依据。

## 它不证明什么

**没有证明「Owner 自己的收藏夹读得出来」。** 那要他本人的登录态，
而这台机器上没有、也不该有。真实的登录态验证发生在他自己的浏览器里：
装上插件 → 连接 B 站 → 点同步。这个演练能保证的是：到那一刻为止，
接口理解、翻页、解析、失败分类都是对的，且每一种读不到都会明确报出来。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "apps/browser-extension/content/bilibili-reader.js"
# 一个公开收藏夹，不需要登录就读得到。选它是因为条数少、翻得完。
PUBLIC_FOLDER = "4026748432"
PUBLIC_MID = "8047632"


def _node(script: str) -> dict:
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, timeout=180)
    if done.returncode != 0:
        return {"_error": (done.stderr or done.stdout)[-800:]}
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"_error": f"读不懂 node 的输出：{done.stdout[-400:]}"}


LIVE = """
const R = require("./apps/browser-extension/content/bilibili-reader.js");
(async () => {
  const out = {};

  // A. 完整读一个公开收藏夹
  const read = await R.readFolder("%(folder)s", { pageSize: 4 });
  out.live_folder = {
    ok: read.ok, partial: Boolean(read.partial), failureCode: read.failureCode || null,
    declared: read.expected, read: (read.items || []).length,
    skipped: (read.skipped || []).length, pages: read.pagesRead,
    folder_title: read.folderTitle || "",
    // 每一条都必须是能在浏览器里打开的网址。B 站的 media.link 是
    // bilibili://video/… 这种 App 深链，直接用会让入库的每一条都点不开。
    all_urls_openable: (read.items || []).every(i => /^https:\\/\\/www\\.bilibili\\.com\\/video\\/BV/.test(i.url)),
    sample_url: (read.items || [])[0] ? (read.items || [])[0].url : "",
  };

  // A2. 收藏夹清单
  const folders = await R.listFolders("%(mid)s");
  out.live_folder_list = {
    ok: folders.ok, count: (folders.folders || []).length,
    failureCode: folders.failureCode || null,
  };

  // B. 失败路：未登录
  const who = await R.currentUser();
  out.live_not_logged_in = {
    ok: who.ok, failureCode: who.failureCode || null,
    // 这台机器没有 B 站登录态，所以这里**必须**是未登录
    behaved_as_expected: who.ok === false && who.failureCode === "BILIBILI_NOT_LOGGED_IN",
  };

  // B2. 失败路：成功码 + 空数据（看不见的收藏夹）
  const invisible = await R.listFolders("1");
  out.live_invisible_folder = {
    ok: invisible.ok, failureCode: invisible.failureCode || null,
    behaved_as_expected: invisible.ok === false
      && invisible.failureCode === "BILIBILI_FOLDER_NOT_VISIBLE",
  };

  console.log(JSON.stringify(out));
})().catch(e => { console.log(JSON.stringify({ _error: String(e && e.message || e) })); });
"""


FIXTURE = """
const R = require("./apps/browser-extension/content/bilibili-reader.js");

function reply(body) {
  return { ok: true, json: async () => body };
}
function medias(n, start = 0) {
  return Array.from({ length: n }, (_, i) => ({
    id: 1000 + start + i, bvid: "BV" + String(start + i).padStart(8, "0"),
    title: "条目" + (start + i), intro: "简介", cover: "https://i0.hdslb.com/x.jpg",
    upper: { name: "作者" }, pubtime: 1700000000, fav_time: 1700000001,
  }));
}

(async () => {
  const out = {};

  // ① 翻页卡住：接口说还有更多，却给了空页。**不许死循环，也不许假装读完了。**
  {
    let call = 0;
    const fetchImpl = async () => {
      call += 1;
      return reply({ code: 0, data: { info: { title: "t", media_count: 99 },
        medias: call === 1 ? medias(2) : [], has_more: true } });
    };
    const r = await R.readFolder("1", { fetchImpl, pageSize: 2 });
    out.pagination_stuck = { failureCode: r.failureCode, partial: r.partial,
                             kept: r.items.length, calls: call };
  }

  // ② 条数对不上：声明 10 条，只给 2 条就说没有更多了。
  {
    const fetchImpl = async () => reply({ code: 0, data: {
      info: { title: "t", media_count: 10 }, medias: medias(2), has_more: false } });
    const r = await R.readFolder("1", { fetchImpl, pageSize: 20 });
    out.count_mismatch = { failureCode: r.failureCode, partial: r.partial,
                           declared: r.expected, read: r.items.length };
  }

  // ③ 深链：只有 bilibili:// 而没有 bvid 的条目，必须被跳过并记下，不能默默丢。
  {
    const fetchImpl = async () => reply({ code: 0, data: {
      info: { title: "t", media_count: 2 },
      medias: [
        { id: 1, link: "bilibili://video/1", title: "只有深链" },
        { id: 2, bvid: "BV11111111", title: "正常", upper: { name: "a" } },
      ], has_more: false } });
    const r = await R.readFolder("1", { fetchImpl, pageSize: 20 });
    out.deeplink_only = { kept: r.items.length, skipped: r.skipped.length,
                          failureCode: r.failureCode,
                          kept_url: r.items[0] ? r.items[0].url : "" };
  }

  // ④ 超出页数上限：一直说 has_more，必须停下来并报 partial。
  {
    let call = 0;
    const fetchImpl = async () => {
      call += 1;
      return reply({ code: 0, data: { info: { title: "t", media_count: 999999 },
        medias: medias(1, call), has_more: true } });
    };
    const r = await R.readFolder("1", { fetchImpl, pageSize: 1 });
    out.too_many_pages = { failureCode: r.failureCode, partial: r.partial,
                           calls: call, cap: R.MAX_PAGES };
  }

  // ⑤ **整条路上最要紧的一条**：没有收藏夹时，绝不能报成「成功，0 条」。
  {
    const fetchImpl = async (url) => {
      if (String(url).includes("/nav")) {
        return reply({ code: 0, data: { isLogin: true, mid: 42, uname: "u" } });
      }
      return reply({ code: 0, data: { count: 0, list: [] } });
    };
    const r = await R.readAllFavorites({ fetchImpl });
    out.no_folders_is_not_success = {
      ok: r.ok, failureCode: r.failureCode,
      // 这一行就是 INV-NO-SILENT-ZERO 的判据本身
      refused_to_report_silent_zero: r.ok === false,
    };
  }

  // ⑥ 正常读完：两个收藏夹，条数都对得上 → complete
  {
    const fetchImpl = async (url) => {
      const text = String(url);
      if (text.includes("/nav")) return reply({ code: 0, data: { isLogin: true, mid: 42, uname: "u" } });
      if (text.includes("list-all")) return reply({ code: 0, data: { count: 2, list: [
        { id: 11, title: "夹一", media_count: 2 }, { id: 22, title: "夹二", media_count: 1 }] } });
      const id = text.match(/media_id=(\\d+)/)[1];
      return reply({ code: 0, data: { info: { title: "夹" + id, media_count: id === "11" ? 2 : 1 },
        medias: medias(id === "11" ? 2 : 1), has_more: false } });
    };
    const r = await R.readAllFavorites({ fetchImpl });
    out.happy_path = { ok: r.ok, completeness: r.completeness, items: r.items.length,
                       collections: r.cursor.collections_found,
                       every_item_has_collection_key: r.items.every(i => Boolean(i.collection_key)) };
  }

  console.log(JSON.stringify(out));
})().catch(e => { console.log(JSON.stringify({ _error: String(e && e.message || e) })); });
"""


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description="验 B 站收藏夹取数路真的读得到")
    parser.add_argument("--no-live", action="store_true",
                        help="不打真实接口（离线时用）。**这样跑出来的结论弱一档**，报告里会写明。")
    parser.add_argument("--out", default="evidence/G1/BILIBILI_ACQUISITION.json")
    args = parser.parse_args()

    if not READER.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "READER_MISSING"}, ensure_ascii=False))
        return 2

    problems: list[str] = []
    live: dict = {}
    if not args.no_live:
        live = _node(LIVE % {"folder": PUBLIC_FOLDER, "mid": PUBLIC_MID})
        if live.get("_error"):
            problems.append(f"打真实接口那一段没跑成：{live['_error'][:200]}")
        else:
            folder = live.get("live_folder", {})
            if not folder.get("ok"):
                problems.append(f"读公开收藏夹失败：{folder.get('failureCode')}")
            if folder.get("partial"):
                problems.append(f"读公开收藏夹没读完：{folder.get('failureCode')}")
            if folder.get("declared") != folder.get("read"):
                problems.append(
                    f"声明 {folder.get('declared')} 条、只读到 {folder.get('read')} 条")
            if not folder.get("all_urls_openable"):
                problems.append("**有条目的网址不是能打开的 https 网址**——"
                                "media.link 是 bilibili:// 深链，必须由 bvid 拼")
            if not live.get("live_not_logged_in", {}).get("behaved_as_expected"):
                problems.append("未登录时没有报 BILIBILI_NOT_LOGGED_IN")
            if not live.get("live_invisible_folder", {}).get("behaved_as_expected"):
                problems.append("**「成功码 + 空数据」没有被判成失败**——"
                                "这正是 INV-NO-SILENT-ZERO 要防的那种零")

    fixture = _node(FIXTURE)
    if fixture.get("_error"):
        problems.append(f"固定装置那一段没跑成：{fixture['_error'][:200]}")
    else:
        checks = [
            ("pagination_stuck", lambda d: d.get("failureCode") == "BILIBILI_PAGINATION_STUCK"
                                 and d.get("calls", 0) < 10, "翻页卡住没有被拦下"),
            ("count_mismatch", lambda d: d.get("failureCode") == "BILIBILI_COUNT_MISMATCH",
             "条数对不上没有被判成没读完"),
            ("deeplink_only", lambda d: d.get("skipped") == 1 and d.get("kept") == 1
                              and d.get("kept_url", "").startswith("https://"),
             "只有深链的条目没有被跳过并记下"),
            ("too_many_pages", lambda d: d.get("failureCode") == "BILIBILI_TOO_MANY_PAGES"
                               and d.get("calls") == d.get("cap"), "超出页数上限没有停下来"),
            ("no_folders_is_not_success",
             lambda d: d.get("refused_to_report_silent_zero"),
             "**没有收藏夹时报成了「成功，0 条」**——这是 INV-NO-SILENT-ZERO 的红线"),
            ("happy_path", lambda d: d.get("ok") and d.get("completeness") == "complete"
                           and d.get("items") == 3 and d.get("collections") == 2
                           and d.get("every_item_has_collection_key"),
             "正常路径没有读成 complete / 条目数或收藏夹归属不对"),
        ]
        for key, ok, message in checks:
            if not ok(fixture.get(key) or {}):
                problems.append(f"{message}（{key} = {fixture.get(key)}）")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "task": "G1",
        "what_this_is": "B 站收藏夹取数路的实测记录。SYNCABLE_NOW 收 bilibili 的依据就是这份。",
        "live_probe_ran": not args.no_live,
        # **这份证据是哪天的。**（2026-08-07）
        # `SYNCABLE_NOW` 收 bilibili 的依据就是这份文件，而文件本身不会过期——
        # B 站改了接口它还是 PASS。写上时间，至少让「这是哪天的事实」看得见。
        "probed_at": _utcnow(),
        "live": live,
        "fixture": fixture,
        "problems": problems,
        "zero_cost": {
            "api_key_required": False,
            "paid_tier_required": False,
            "note": "B 站收藏夹接口是公开 REST，无签名、无 API key。不触及 L0「0 新增必付费用」。",
        },
        "cookie_handling": {
            "reads_cookie_values": False,
            "stores_cookie_values": False,
            "transmits_cookie_values": False,
            "note": "请求由**页面自己**发出（content script + credentials:'include'），"
                    "带凭据的是浏览器。符合 INV-DOMESTIC-COOKIE-STAYS："
                    "cookie-export.js 的 FORBIDDEN_PLATFORMS 里就有 bilibili。",
        },
        "owner_actions_required": [],
        "what_this_does_not_prove": (
            "**没有证明 Owner 自己的收藏夹读得出来。** 那需要他本人的 B 站登录态，"
            "这台机器上没有也不该有。这份证据能保证的是：接口理解、翻页终点、解析、"
            "以及六种读不到的分类都是对的，且每一种都会明确报出来、不会静默成零。"
            "真实登录态下的那一次，发生在他自己的浏览器里。"
        ),
    }
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "fixture"},
                     ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
