#!/usr/bin/env python3
"""拿他生产库里的真数据，逐个面去对产品说的话（2026-08-07）。

## 为什么要有它

2026-08-07 这一天在他的生产数据上查出十处缺陷，**没有一处被那 1190 条测试
和 31 道发布门抓到**。原因不是判据写得差，是它们全在问「机制对不对」，
而这十处问的是**「产品对他这份数据说的话对不对」**：

    · 三个账号断开了，而弹窗说「还没有连接平台账号」「连接第一个账号」
    · 库里 193 条，而资料库说「首次同步尚未开始」
    · 33 条视频被平台挡了，而那一列全标着「完整」
    · 一次主动中断被说成「这是产品的问题」
    · 状态页把靠浏览器同步的平台说成「这个来源暂时不可用」，还附内部码

这些只有把**他的数**喂进产品的判断里才看得见。手工查一遍要一整天，
所以做成一条命令——**证据要留在仓里，不是留在我的终端里**。

## 边界

· **只读。** 打的都是 GET；数据库那部分走 `mode=ro` 的 SELECT。
  不写、不改、不触发任何有副作用的路由（比如 backfill）。
· 不取任何内容正文、不取 Cookie、不碰凭据表。报告里只有数和状态码。
· 数**全部现算**。手写的数必然往好里漂——这个仓在这上面栽过。
· **它不替代演练**：演练验「机制在真 Chrome 里走不走得通」，
  这个验「产品对他这份数据说的话对不对」。两件事，都要。

    python3 scripts/audit_production_against_the_product.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "G5" / "PRODUCTION_AUDIT.json"
API = "https://social-archive-api.linzezhang.com"
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (audit)"}


def _token(host: str) -> str:
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         "sudo cat /opt/social-archive/runtime/secrets/social_archive_api_token"],
        capture_output=True, text=True, check=False)
    return done.stdout.strip()


def _get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        API + path, headers={**BROWSER_UA, "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def audit(library: dict, accounts: dict, status: dict,
          runs_codes: set[str] | None = None) -> tuple[list[str], dict]:
    """**判断逻辑与取数分开。**

    分开是为了能用「修之前那些真实形状」喂它，证明它真的会红——
    一条永远说 PASS 的审计等于没有。判据在
    tests/focused/test_production_audit_catches_what_it_missed.py。
    """
    from social_archive.failure_copy import describe_sync_outcome

    items = library["items"]
    runs_codes = runs_codes or set()
    problems: list[str] = []
    # ── 1. 界面上的字里不许出现内部码 ────────────────────────────────
    # 十处里有两处是这个：状态页印 `HEALTH_PROBE_FAILED`、
    # 账号卡片印 `disconnected`。**规则是给人看的字里不许有 A_B_C 这种**。
    leaked: list[str] = []
    for connector in status.get("connectors", []):
        for key in ("last_message_zh", "next_action_zh"):
            for hit in re.findall(r"[A-Z][A-Z_]{4,}", str(connector.get(key) or "")):
                leaked.append(f"{connector.get('connector_id')}.{key}: {hit}")
    for platform in accounts.get("supported_platforms", []):
        for hit in re.findall(r"[A-Z][A-Z_]{4,}", str(platform.get("not_syncable_reason") or "")):
            leaked.append(f"{platform.get('platform')}.not_syncable_reason: {hit}")
    if leaked:
        problems.append(f"**给人看的字里有内部码**：{leaked[:4]}")

    # ── 2. 靠浏览器同步的平台，不许被服务端探针说成「不可用」 ──────────
    # 服务端按 INV-DOMESTIC-COOKIE-STAYS 永远不该有他的 Cookie，
    # 探不通是**预期**。而同一时刻连接面板正给它们画着能用的按钮。
    connectable = {p["platform"] for p in accounts.get("supported_platforms", [])
                   if p.get("sync_supported") is not False}
    for connector in status.get("connectors", []):
        name = connector.get("connector_id")
        if name in connectable and connector.get("state") == "blocked_environment":
            problems.append(
                f"**{name} 能同步，状态却是 blocked_environment**——"
                "那一档是「本版本根本做不了」的意思，他会以为不支持")
        if name in connectable and "暂时不可用" in str(connector.get("last_message_zh") or ""):
            problems.append(f"**{name} 能同步，状态页却说「这个来源暂时不可用」**")

    # ── 3. 归档状态不许盖住「视频没存下」 ────────────────────────────
    by_archive: dict[str, int] = {}
    for item in items:
        by_archive[str(item.get("archive_status"))] = by_archive.get(
            str(item.get("archive_status")), 0) + 1

    # ── 4. 每条内容都要能认出是哪一条 ───────────────────────────────
    # **空标题本身不是缺陷**——资料库会用链接的尾巴认人
    # （app.js 的 `item.title || _urlLabel(item.canonical_url)`）。
    # 只有**连链接都没有**的才是真的认不出来。
    # 第一版按「标题为空」报，当场误报 6 条——那 6 条界面上显示的是
    # `douyin.com/video/7584…`，他分得清。**判据指错了对象。**
    untitled = [item for item in items if not str(item.get("title") or "").strip()]
    faceless = [item["id"] for item in untitled
                if not str(item.get("canonical_url") or "").strip()]
    if faceless:
        problems.append(
            f"**{len(faceless)} 条内容在表格里认不出是哪一条**"
            "（标题为空，而且没有链接可以兜底）")

    # ── 5. 生产里出现过的每个失败码，都要能说成人话 ─────────────────
    #
    # failure_copy.py 里记着 2026-08-04 的教训：**生产库里有代码里已经不存在
    # 的码**（v0.0.0.6 留下的三个），光读代码列不全。所以反过来：
    # 把生产**真出现过**的码逐个渲染一遍，看它说得出话、且不泄漏内部码。
    # 这样将来冒出一个谁都没想到的新码，这里会当场发现。
    for code in sorted(runs_codes):
        try:
            rendered = describe_sync_outcome(
                imported=0, failure_code=code, platform_label="某平台", status="partial")
        except Exception as error:                        # noqa: BLE001
            problems.append(f"**失败码 {code} 渲染时抛异常**：{str(error)[:80]}")
            continue
        text = str(rendered.get("message_zh") or "")
        if not text.strip():
            problems.append(f"**失败码 {code} 说不出话**——他只会看到一片空白")
        # **「有话说」还不够**：不认识的码会落进 unexplained_zero 那句
        # 「我们没能记录下原因。这是产品的问题」——它有话说、也不泄漏码，
        # 但那句话的意思正是「**我们没有为这个码写过文案**」。
        # 按结局判才准，按有没有字判会漏掉每一个新码。
        if rendered.get("outcome") == "unexplained_zero":
            problems.append(
                f"**失败码 {code} 没有人为它写过文案**——他看到的会是"
                "「我们没能记录下原因，这是产品的问题」，而原因就写在这个码里")
        for hit in re.findall(r"[A-Z][A-Z_]{4,}", text):
            problems.append(f"**失败码 {code} 的句子里有内部码**：{hit}")

    # ── 6. 账号状态与「界面会说什么」对不对得上 ──────────────────────
    account_items = accounts.get("items", [])
    connected = [a for a in account_items
                 if a.get("connection_state") in ("connected", "degraded")]
    if account_items and not connected:
        # 这不是缺陷，是他现在的处境——报出来，好让人一眼看到该做什么。
        pass


    measured = {
        "items_total": library.get("total"),
        "archive_status": by_archive,
        "items_without_title": len(untitled),
        "items_with_nothing_to_identify_them": len(faceless),
        "fields_present": {
            field: sum(1 for item in items if str(item.get(field) or "").strip())
            for field in ("title", "author_name", "published_at", "summary",
                          "canonical_url")},
        "accounts": [{k: a.get(k) for k in
                      ("platform", "connection_state", "auto_sync_enabled",
                       "content_count")} for a in accounts.get("items", [])],
        "connectors": [{k: c.get(k) for k in ("connector_id", "state")}
                       for c in status.get("connectors", [])],
    }
    return problems, measured


def main() -> int:
    parser = argparse.ArgumentParser(description="拿生产真数据对产品说的话（只读）")
    parser.add_argument("--host", default="linze-ovh")
    # **给人看的那几行由脚本自己打。**
    # 今天已经在第 8.7 步踩过一次：把格式化写成部署脚本里嵌的一段 Python，
    # `\"` 落进单引号里当场 SyntaxError，而外层 `||` 把它兜成一句
    # 「读不到」——看起来像读不到，其实是我把模板写崩了。**第二次了。**
    parser.add_argument("--brief", action="store_true", help="只打给人看的几行")
    args = parser.parse_args()

    token = _token(args.host)
    if not token:
        print(json.dumps({"status": "FAIL", "error_code": "TOKEN_UNREADABLE",
                          "message_zh": "取不到生产令牌——**这不是通过**"},
                         ensure_ascii=False, indent=2))
        return 2

    library = _get("/v1/library?limit=500", token)
    accounts = _get("/v1/accounts", token)
    status = _get("/v1/status", token)
    # 生产里**真出现过**的失败码——不是我从代码里列的那些。
    history = ROOT / "evidence/G1/PRODUCTION_AGGREGATION_REALLY_HAPPENED.json"
    runs_codes: set[str] = set()
    if history.is_file():
        runs_codes = {run["last_error_code"] for run
                      in json.loads(history.read_text(encoding="utf-8"))["all_runs"]
                      if run.get("last_error_code")}
    problems, measured = audit(library, accounts, status, runs_codes)

    report = {
        "status": "PASS" if not problems else "FAIL",
        "measured_from_production": measured,
        "failure_codes_seen_in_production": sorted(runs_codes),
        "problems": problems,
        "what_this_does_not_prove": (
            "它验的是**产品对他这份数据说的话对不对**，不验机制在真 Chrome 里"
            "走不走得通——那是演练的事。两件事都要。"),
        "boundary_zh": "只读；不取正文、不取 Cookie、不碰凭据表；数全部现算。",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    if args.brief:
        print(f"  {report['status']} · 条目 {measured['items_total']}"
              f" · 归档 {measured['archive_status']}")
        for item in problems:
            print(f"    · {item}")
        return 0          # **播报不当门**：他那份数据长什么样不是部署的属性
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
