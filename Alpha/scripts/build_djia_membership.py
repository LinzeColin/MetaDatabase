#!/usr/bin/env python3
"""道指 30 历史成分表构建(第六批无偏名单)。

来源:维基百科 Historical components of the Dow Jones Industrial Average
(公开可审计;检索时间戳写入产物)。产物:configs/strategies/research/djia_membership.yaml
——每期变更日的当期 30 家成分(时点正确,杜绝幸存者偏差)。

数据可得性排除(如实声明,窗口内按 29 家运行):
- 老杜邦(2013-09~2017-09 在指)与 DowDuPont(2017-09~2019-04 在指):
  合并/拆分链条中的退市主体,免费日线源无其历史,显式排除。
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

PAGE = "Historical_components_of_the_Dow_Jones_Industrial_Average"
API = (f"https://en.wikipedia.org/w/api.php?action=parse&page={PAGE}"
       "&prop=wikitext&format=json&formatversion=2")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}

NAME_TO_TICKER = {
    "3M": "MMM", "AT&T": "T", "Alphabet": "GOOGL", "Amazon.com": "AMZN",
    "American Express": "AXP", "Amgen": "AMGN", "Apple": "AAPL",
    "Boeing": "BA", "Caterpillar": "CAT", "Chevron": "CVX", "Cisco": "CSCO",
    "Coca-Cola": "KO", "Dow Inc": "DOW", "Exxon": "XOM",
    "General Electric": "GE", "Goldman": "GS", "Home Depot": "HD",
    "Honeywell": "HON", "International Business Machines": "IBM",
    "Intel": "INTC", "JPMorgan": "JPM", "Johnson & Johnson": "JNJ",
    "McDonald": "MCD", "Merck": "MRK", "Microsoft": "MSFT", "Nike": "NKE",
    "Nvidia": "NVDA", "Pfizer": "PFE", "Procter & Gamble": "PG",
    "Raytheon": "RTX", "Salesforce": "CRM", "Sherwin-Williams": "SHW",
    "Travelers": "TRV", "Walt Disney": "DIS",
    "United Technologies": "RTX",  # 2020-04 更名重组,雅虎 RTX 序列连续覆盖 UTX 期
    "UnitedHealth": "UNH", "Verizon": "VZ", "Visa": "V",
    "Wal-Mart": "WMT", "Walmart": "WMT", "Walgreens": "WBA",
}
EXCLUDED = {
    "DowDuPont": "退市合并主体,免费源无历史日线",
    "du Pont": "老杜邦并入 DowDuPont 链条,免费源无独立历史",
}


def to_ticker(name: str) -> str | None:
    for key, reason in EXCLUDED.items():
        if key.lower() in name.lower():
            return None
    for key, tk in NAME_TO_TICKER.items():
        if key.lower() in name.lower():
            return tk
    raise ValueError(f"未知公司名(请补映射): {name}")


def main() -> int:
    req = urllib.request.Request(API, headers={"User-Agent": "AlphaResearch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = json.loads(resp.read().decode())["parse"]["wikitext"]

    sections = re.split(r"==\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*==", text)
    snapshots: dict[str, list[str]] = {}
    for i in range(1, len(sections), 2):
        header, body = sections[i], sections[i + 1]
        m = re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", header)
        if not m or int(m.group(3)) < 2013:
            continue
        # 只取「当期成分」主表:在“Dropped from Average”子表处截断
        cut = re.search(r"Dropped from Average", body)
        if cut:
            body = body[: cut.start()]
        cells = re.findall(r"^\|\s*([^|{\-!].*?)\s*$", body, re.M)
        tickers: list[str] = []
        for c in cells:
            c = re.sub(r"<!--.*?-->", "", c, flags=re.S)
            c = re.sub(r"\[\[([^|\]]*\|)?([^\]]+)\]\]", r"\2", c)
            c = re.sub(r"\{\{small\|.*?\}\}", "", c)
            c = re.sub(r"<br\s*/?>.*", "", c)
            c = c.split("|")[-1]  # 残留管道取右侧显示名
            c = c.replace("†", "").replace("↑", "").replace("↓", "").replace("'", "").strip()
            if not c or c.startswith(("class=", "{|", "|}", "colspan")) or len(c) <= 2:
                continue
            if not re.search(r"[A-Za-z]", c):
                continue  # 纯符号残渣
            tk = to_ticker(c)
            if tk and tk not in tickers:
                tickers.append(tk)
        if len(tickers) >= 28:
            day = f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
            snapshots[day] = sorted(tickers)

    out = {
        "source": f"https://en.wikipedia.org/wiki/{PAGE}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "note": "每期为变更日起生效的当期成分(时点正确);排除项见 exclusions",
        "exclusions": EXCLUDED,
        "snapshots": [{"effective_from": d, "tickers": tks}
                       for d, tks in sorted(snapshots.items())],
    }
    dest = Path("configs/strategies/research/djia_membership.yaml")
    dest.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))
    for s in out["snapshots"]:
        print(s["effective_from"], len(s["tickers"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
