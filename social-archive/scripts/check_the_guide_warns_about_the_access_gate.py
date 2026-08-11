#!/usr/bin/env python3
r"""说明书让他打开的那个地址，会不会先弹一个它没提过的验证页（2026-08-12）。

## 撞见它的经过

说明书第 1 步的原话是「打开 <https://social-archive.linzezhang.com/extension-install>，
照着页面上的四步做」。而没有会话的浏览器打开它，拿到的是：

    302 → https://tiny-scene-b867.cloudflareaccess.com/cdn-cgi/access/login/…

**那一屏说明书一个字都没提**（`Access` / `验证` / `邮箱` / `Cloudflare` 全是 0 处）。
他在自己常用的浏览器里多半有会话、看不见这一屏；换一台机器、换个浏览器，
第一步就卡在一个说明书没写过的页面上——而那份说明的开头写着
「这份说明里写的每一句…都逐条核对过」。

## 这道门补的是**反方向**

`check_the_guide_matches_the_product.py` 查的是「说明里写的东西真的存在」。
它查不到这一类：**真实存在、而说明里没有**。两个方向漏一个，
说明书就可以靠「少说」来永远绿。

## 判据（两个方向都判，所以它不会变成摆设）

· 那个地址**确实**挡在 Access 后面 → 说明书必须提到这一屏，否则红。
· 那个地址**已经不挡了**（哪天他去掉了 Access）→ 说明书里那句提醒必须删掉，
  否则也红——**一句过期的提醒和一句缺失的提醒一样会把人带错**。

只读：不带任何凭据打一次那个地址，看它往哪儿跳。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/使用说明.md"
# 说明书里那句提醒的锚点。改文案时连这里一起改，别让判据指着一个不存在的句子。
WARNING_MARK = "Cloudflare"


def first_url(text: str) -> str | None:
    """说明书让他打开的第一个地址。"""
    found = re.search(r"<(https://[^>]+)>", text)
    return found.group(1) if found else None


def _short(location: str) -> str:
    """只留主机和路径。

    Access 的跳转带着一大段 `meta=` JWT，原样进证据文件既是噪声，
    也会撞上这个仓的密钥扫描——**报告里要的是「跳去哪一家」，不是那串东西**。
    """
    return location.split("?", 1)[0]


def where_does_it_send_you(url: str) -> dict:
    """不带任何凭据打一次，看它 302 去哪儿。"""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # noqa: D401, ANN002
            return None

    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (guide-check)"})
    try:
        with opener.open(request, timeout=25) as response:
            return {"status": response.status,
                    "location": _short(response.headers.get("Location") or "")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "location": _short(exc.headers.get("Location") or "")}
    except Exception as exc:  # noqa: BLE001
        return {"status": None, "error": f"{exc.__class__.__name__}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="说明书有没有提那一屏验证")
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--root", default=None, help="仓的位置（默认按脚本所在处推）")
    args = parser.parse_args()

    guide = (Path(args.root).resolve() / "docs/使用说明.md") if args.root else GUIDE
    text = guide.read_text(encoding="utf-8")
    url = first_url(text)
    problems: list[str] = []
    if not url:
        problems.append("说明书里读不出第一个地址——**这不是通过，是没数到**")
        measured = {}
    else:
        measured = where_does_it_send_you(url)
        gated = "cloudflareaccess.com" in (measured.get("location") or "")
        mentioned = WARNING_MARK in text
        if measured.get("status") is None:
            problems.append(
                f"打不到那个地址（{measured.get('error')}）——**这不是通过**："
                "这台机器上不去就说上不去，别当成「没有那一屏」")
        elif gated and not mentioned:
            problems.append(
                f"说明书第一步让他打开 {url}，而没有会话时它先跳到 Cloudflare Access 的验证页——"
                "**说明书一个字都没提这一屏**。他在自己浏览器里有会话看不见，"
                "换台机器就卡在第一步。")
        elif not gated and mentioned:
            problems.append(
                "那个地址已经不挡了，而说明书里还留着 Cloudflare 那句提醒——"
                "**过期的提醒和缺失的提醒一样会把人带错**，删掉它。")

    report = {
        "status": "FAIL" if problems else "PASS",
        "guide_first_url": url,
        "measured": measured,
        "guide_mentions_the_gate": WARNING_MARK in text,
        "problems": problems,
        "why_zh": "这道门补的是**反方向**：另一道门查「说明里写的真的存在」，"
                  "查不到「真实存在、而说明里没有」。少说也是说错。",
    }
    print(report["status"] if args.brief and not problems
          else json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
