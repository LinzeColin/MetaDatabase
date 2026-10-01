#!/usr/bin/env python3
"""开发期工具：逐个打开证据卡里的每一个链接，核对状态码与原文摘录，写 verification.json（核验印章）。

运行期不会调用它（运行期零联网）；新增/改卡、续期时由人运行。印章按「链接 + 规范化后的摘录」取 key，
改了链接或摘录，旧印章自动对不上，必须重新核验，否则该来源在运行期视为「不可验证」。

    PYTHONPATH=src python3 scripts/verify_evidence_cards.py [--dir src/signal_lattice/evidence_cards] [--only ID ...]

需要联网；PDF 来源需要 `pip install pypdf`（没有就如实记 excerpt_found=false 并写明原因，不假装找到）。
SEC 站点请求间隔 >= 0.3 秒，User-Agent 用 SIGNAL_LATTICE_SEC_UA（缺失时用仓库约定的研究用途声明）。
退出码：0 = 所有链接 200 且摘录找到；1 = 有失败（印章照写，失败项运行期不会被采信）。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.evidence import cards as C  # noqa: E402

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
DEFAULT_SEC_UA = "SignalLattice research noreply@anthropic.com"
MAX_BYTES = 60 * 1024 * 1024


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def squash(text: str) -> str:
    """比对用：只留字母数字（排版、断行、连字符、引号差异都不影响）。"""
    return re.sub(r"[^0-9a-z一-鿿]", "", C.normalize_excerpt(unicodedata.normalize("NFKC", text)))


def fetch(url: str, sec_ua: str) -> Tuple[int, bytes, str, str]:
    host = url.split("/")[2]
    ua = sec_ua if host.endswith("sec.gov") else BROWSER_UA
    request = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,application/pdf,*/*;q=0.8",
                                                   "Accept-Language": "en-US,en;q=0.9"})
    last: Optional[Exception] = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read(MAX_BYTES + 1)
                return response.status, body[:MAX_BYTES], response.headers.get("Content-Type", ""), response.geturl()
        except urllib.error.HTTPError as exc:
            return exc.code, b"", exc.headers.get("Content-Type", "") if exc.headers else "", url
        except Exception as exc:                                     # 网络抖动：重试一次
            last = exc
            time.sleep(2)
    return 0, b"", "network error: %s" % last, url


def page_text(body: bytes, content_type: str, url: str) -> Tuple[Optional[str], str]:
    if "pdf" in content_type.lower() or url.lower().split("?")[0].endswith(".pdf") or body[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
        except ImportError:
            return None, "PDF 文本提取需要 pypdf，本机没有"
        try:
            reader = PdfReader(io.BytesIO(body))
            return "\n".join((page.extract_text() or "") for page in reader.pages), "pdf"
        except Exception as exc:
            return None, "PDF 解析失败：%s" % exc
    parser = _Text()
    parser.feed(body.decode("utf-8", errors="replace"))
    return " ".join(parser.parts), "html"


def sources_of(raw: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(位置, 链接, 摘录)；反证记录里的链接只核对能不能打开（摘录为空串）。"""
    out: List[Tuple[str, str, str]] = []
    for name, body in (raw.get("factors") or {}).items():
        for i, src in enumerate(body.get("sources") or []):
            out.append(("factors.%s.sources[%d]" % (name, i), src["url"], src["excerpt"]))
    for i, company in enumerate(raw.get("companies") or []):
        out.append(("companies[%d].source" % i, company["source"]["url"], company["source"]["excerpt"]))
    for i, item in enumerate(raw.get("contradictions") or []):
        if item.get("url"):
            out.append(("contradictions[%d]" % i, item["url"], ""))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=C.CARDS_DIR)
    parser.add_argument("--only", nargs="*", default=None, help="只核验这些卡片 id（其余卡片保留原印章）")
    args = parser.parse_args()
    sec_ua = os.environ.get("SIGNAL_LATTICE_SEC_UA") or DEFAULT_SEC_UA
    stamp_path = args.dir / C.VERIFICATION_FILE
    old: Dict[str, Any] = {}
    if stamp_path.is_file():
        old = json.loads(stamp_path.read_text("utf-8")).get("entries", {})

    entries: Dict[str, Any] = {}
    cache: Dict[str, Tuple[int, bytes, str, str]] = {}
    failures = 0
    today = date.today().isoformat()
    cards = {p.stem: C.parse_simple_yaml(p.read_text("utf-8")) for p in sorted(args.dir.glob("*.yaml"))}
    for card_id, raw in cards.items():
        if args.only is not None and card_id not in args.only:
            for place, url, excerpt in sources_of(raw):          # 没被点名的卡：沿用旧印章（如果有）
                key = C.stamp_key(url, excerpt)
                if key in old:
                    entries[key] = old[key]
            continue
        for place, url, excerpt in sources_of(raw):
            key = C.stamp_key(url, excerpt)
            if url not in cache:
                time.sleep(0.35 if "sec.gov" in url else 0.6)
                cache[url] = fetch(url, sec_ua)
            status, body, content_type, final_url = cache[url]
            found: Optional[bool] = None
            note = ""
            if status == 200 and excerpt:
                text, kind = page_text(body, content_type, url)
                if text is None:
                    found, note = False, kind
                else:
                    found = squash(excerpt) in squash(text)
                    note = "" if found else "页面（%s，%d 字）里没有找到这段摘录" % (kind, len(text))
            elif status == 200:
                found = True                                         # 反证链接：只要求能打开
            else:
                found, note = False, "HTTP %s %s" % (status, content_type[:60])
            entries[key] = {"url": url, "status": status, "checked": today, "excerpt_found": bool(found),
                            "content_sha256": hashlib.sha256(body).hexdigest() if body else None, "bytes": len(body),
                            "content_type": content_type.split(";")[0][:60], "card": card_id, "place": place,
                            "note": note}
            ok = status == 200 and found
            failures += not ok
            print("%-4s %s %s %s%s" % ("OK" if ok else "FAIL", status, card_id, place, "" if ok else "  <- " + note))
            print("       " + url)
    document = {"schema": C.VERIFICATION_SCHEMA, "generated": today, "entries": dict(sorted(entries.items()))}
    stamp_path.write_text(json.dumps(document, ensure_ascii=False, indent=1, sort_keys=False) + "\n", "utf-8")
    print("写入 %s：%d 条印章，%d 条失败" % (stamp_path, len(entries), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
