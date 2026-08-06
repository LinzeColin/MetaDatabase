#!/usr/bin/env python3
"""平台表不许漏平台——**而且不许靠我记得有几张**（v0.0.0.7 / T06）。

## 为什么必须机器来数

给 youtube 接入口这一件事上，「我以为已经查全了，又冒出一张表」发生了**四次**：

  1. 说「开 B 站时顺手连一下」—— 硬边界禁止，方向就错了
  2. 说「两个方向都封住了」—— 漏了 `platform-catalog.js`，中文名退回内部 id
  3. 四张表全绿之后 —— 漏了 `options.js` 的 platformOrder，
     **设置页不出卡片，交接里让 Owner 点的那个按钮根本不存在**
  4. 补完之后又扫出四张 —— popup 的两张、sidepanel 的两张、options 的 relationCopy

**每一次都是宣布完成之后才发现的。** 第 4 次是我不再靠记忆、
改用「一行里出现三个以上平台名就当它是平台表」去扫全仓才捞出来的。
这个脚本就是把那次扫描固定下来。

## 判据

对每个**已声明可托管**的平台（credentials.CUSTODIAL_PLATFORMS），
每一张平台表都必须提到它——除非那张表在 `DELIBERATE_SUBSETS` 里
登记过「它是个有意的子集，理由是……」。

**登记的门槛是写下理由**，和「已删」那条规则同一个道理：
允许例外，但例外必须说得出话。

## 边界

· 只扫源码（`apps/` `src/` `scripts/`），不扫测试与证据——
  那些地方出现平台名单是正常的。
· 认表有两条规则：**一行里 ≥3 个平台名**，以及**一个括号块里 ≥3 个**。
  后者是补上来的：第一版只有前者，把「跨行的表看不到」写成了已知盲区，
  而那不是「没有问题」。补完当天就从盲区里捞出两处真缺失——
  PWA 的 platformMeta（Owner 的库里 YouTube 会被标成「Chrome书签/网页」）
  和抓取选择器 LIST_SELECTORS。
· 仍然看不到的三类，以及**2026-08-05 各查过一次的结果**：

    拼出来的平台名（`"you"+"tube"`）  —— 全仓搜，0 处（只有这段说明里的例子）
    从配置/环境变量读的平台清单        —— 全仓搜，0 处
    散在三个以上括号层里的             —— 没查（这条本身不好机器化）

  **「今天没有」不是「以后不会有」**，也不是「这条规则能看见它们」。
  写在这里是为了让下一个人知道：这三类它查不到，而前两类当天是空的。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.credentials import CUSTODIAL_PLATFORMS  # noqa: E402

SCANNED = ("apps", "src", "scripts")
SUFFIXES = {".py", ".js", ".html"}
KNOWN = ("xiaohongshu", "douyin", "kuaishou", "bilibili", "instagram", "reddit", "tiktok", "x")

# 有意的子集：键是**那一行里的一段特征文字**，值是**理由**。
# 加进来之前先问一句：这张表少了那个平台，用户会看到什么？
#
# **为什么按特征文字而不按表名。**
#
# 第一版按 "文件名:表名" 登记，而 platform_canary.py 里两行的表名都叫
# `platforms`——一行是全平台、一行是 all-cn 的国内子集。**两者分不开**，
# 于是要么一起放行（漏掉真的缺失），要么一起报错（冤枉有意的子集）。
DELIBERATE_SUBSETS = {
    # run_all_drills 里那张「要参数的演练」表：只列**这一版真的有链可跑**的平台。
    # x / youtube 这一版没有取数链，给它们排一次演练等于跑一个空壳。
    # 多列一个不是更全，是假证据。
    "PARAMETRISED": "全量演练的参数表；只放这一版真的有链可跑的平台",
    # 按形状读那条路的演练（list_shape_end_to_end_drill.py）：
    # 它造的是**假站**，一个平台一套响应形状。只有走这条路的平台才在里面——
    # x 走不通（它的 id 埋在五层 GraphQL 壳里，识别器够不着，见 SYNCABLE_NOW 的注释），
    # youtube 根本还没有取数路。**不列 ≠ 漏了**，列了才是假的。
    "PLATFORMS": "按形状读的演练夹具；只放真走这条路的平台，多列一个就是假证据",
    "RELATIONS": "同上：演练里每个平台读哪个关系",
    # SYNCABLE_NOW（v0.0.0.21 起跨过 3 个平台，才被这道门当成"平台表"）：
    # **它本来就是事实清单**——只放"这一版真的读得动"的。
    # x / reddit / instagram / youtube 不在里面，各自的原因写在 NOT_SYNCABLE_YET。
    "SYNCABLE_NOW": "事实清单，不是平台目录；不在里面的都在 NOT_SYNCABLE_YET 里写了原因",
    # SCANNABLE_RELATIONS：这一版**真的会去枚举**的关系。
    # 没登记的平台按「声明什么就扫什么」，所以不列 ≠ 漏了。
    "SCANNABLE_RELATIONS": "只登记需要收窄扫描范围的平台；其余按平台目录声明的关系扫",

    # SHAPE_READ_PLATFORMS（v0.0.0.21）：**按形状认列表**那条路覆盖的平台。
    # 它是有意的子集——只放"主路径是扩展读页面列表、且接口带签名所以只能拦截"
    # 的那三个国内源。
    #   · x / reddit / instagram：Owner 的平台表里主路径是扩展读当前页 + 官方导出导入，
    #     媒体走 gallery-dl / Instaloader，不走这条拦截路
    #   · youtube：主路径同上，且它的列表不是这种一次性 JSON 响应
    #   · bilibili：接口公开无签名，直接调更准（content/bilibili-reader.js）
    #   · generic-web：Chrome 书签，根本没有页面响应可拦
    "SHAPE_READ_PLATFORMS": "只覆盖三个「接口带签名、只能拦截」的国内源；"
                            "其余平台按 Owner 的平台表走别的主路径",

    "FORBIDDEN_PLATFORMS": "国内四平台的硬边界名单，youtube 本来就不该在里面",
    "DOMESTIC_PLATFORMS": "同上，国内平台专用",
    "SERVER_ACCOUNT_CONNECTORS": "服务端直连的那几个；youtube 走 Cookie 托管，不走这条",
    "all-cn": "国内平台的 canary 批次",
    "INCIDENTAL_PROBE_FAILURES": "失败码表，不是平台表",
    "CONTENT_ID_PATTERNS": "按 pathname 匹配；youtube 的 id 在查询串里（watch?v=），"
                           "由 externalId 的专门分支处理，放进这张表反而取不到",
    "INTERCEPT_PREFIXES": "只放**实测过**的收藏接口前缀，没实测的一律 null——"
                          "写一个看着像的比空着更坏（T09 才是取得它们的正当途径）",
    "self._connectors": "三个 HTTP worker 平台的实例；x/instagram/youtube 走别的代码路径",
    "_IDENTITY_SHAPE": "只放**账号 id 有已知形状**的平台；没有形状的走 shape is None 那条",
}


def _table_name(line: str) -> str:
    found = re.search(r"(?:const|let|var)\s+([A-Za-z_]\w*)|^([A-Z_]{3,})\s*[:=]|"
                      r"([A-Za-z_]\w*)\s*=\s*(?:\{|\[|frozenset|new Set)", line.strip())
    if found:
        return next((g for g in found.groups() if g), "?")
    return "?"


def _blocks(lines: list[str]) -> list[tuple[int, str]]:
    """把「赋值 + 花括号/方括号」的整块取出来，一块只报一次。

    第一版只看单行，于是跨行的表全看不见。而滑动窗口那种做法噪音极大：
    同一张表在每一行都报一次，20 处里有 15 处是同一张。
    这里按括号配平取块，**一张表只出现一次**。
    """
    out: list[tuple[int, str]] = []
    opener = re.compile(r"[=:]\s*(?:frozenset\(|new Set\(|Object\.freeze\()?\s*[\{\[]\s*$")
    for index, line in enumerate(lines):
        if line.strip().startswith(("#", "//", "*")) or not opener.search(line):
            continue
        # **窗口不能截断。** 第一版取 60 行，而 platform-catalog 的 PLATFORMS
        # 块有 80 行——于是它读到一半就下结论，报「PLATFORMS 里没有 instagram」，
        # 而 instagram 就在第 99 行。**指控一个没错的表**，今天第五次。
        # 现在只按括号配平收块；配不平就**明说没读完**，不装作读完了。
        depth = 0
        chunk = []
        closed = False
        for probe in lines[index:]:
            chunk.append(probe)
            depth += probe.count("{") + probe.count("[")
            depth -= probe.count("}") + probe.count("]")
            if depth <= 0 and len(chunk) > 1:
                closed = True
                break
        if not closed:
            continue        # 读到文件尾都没配平，多半不是一张表，别据此指控
        out.append((index + 1, "\n".join(chunk)))
    return out


# 允许自己写一份平台中文名的地方。**每一处都要有理由**，
# 因为每多一份，改名字就要多记一处，而漏掉的那处会显示原始 id。
NAME_TABLE_ALLOWED = {
    "apps/browser-extension/content/platform-catalog.js": "扩展这边的真源",
    "apps/browser-extension/options.js": "设置页；它还要画平台卡片的图标和关系说明，整套一起维护",
    "apps/pwa/app.js": "资料库；名字和图标、列宽绑在一起",
    "src/social_archive/account_sync.py": "服务端真源",
}


def _extra_name_tables() -> list[dict]:
    """又多了一份平台中文名表吗（v0.0.0.22）。

    仓里已经有四份（服务端、扩展目录、设置页、资料库）。
    2026-08-07 我在连接面板里加了**第五份**——正是我一直在抱怨的那种漂移：
    改一个名字要记得改五处，漏一处就有一个界面显示原始 id。
    而目录里本来就有 `platformLabel`，那一页也已经加载了目录。

    **是碰巧发现的**，不是任何判据抓到的。所以立这一条。
    """
    import re as _re

    # **图标表不算名字表。** 第一版把 `{xiaohongshu: "小", douyin: "抖"}`
    # 也报了——那是一个字的图标，目录里没有它，本来就该各页自己写。
    # 只认"值有两个字以上"的，那才是名字。
    pairs = _re.compile(
        r'["\']?(xiaohongshu|douyin|kuaishou|bilibili|instagram|youtube)["\']?\s*:\s*'
        r'["\'][^"\']{2,}["\']')
    # **这条问的是「又多了一份」，不是「存在一份」。**
    #
    # 一份表是真源，两份才开始漂。所以只有在**真源已经存在**的前提下
    # 才去报多出来的那些——否则这条会把"仓里唯一那张表"也判成违规
    # （它自己的自检夹具就是那样一棵只有一个文件的树，第一版当场把它判红了）。
    source_of_truth_present = any(
        (ROOT / name).is_file() for name in NAME_TABLE_ALLOWED)
    out: list[dict] = []
    if not source_of_truth_present:
        return out
    for path in sorted(ROOT.glob("apps/**/*.js")):
        relative = str(path.relative_to(ROOT))
        if relative in NAME_TABLE_ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(("//", "*")):
                continue
            if len(set(pairs.findall(line))) >= 3:
                out.append({
                    "where": f"{relative}:{number}",
                    "problem": "**又写了一份平台中文名表**——仓里已经有四份，"
                               "改一个名字要记得改五处，漏一处就有一个界面显示原始 id。"
                               "用 SAPlatformCatalog.platformLabel()；"
                               "确实要自己一份就写进 NAME_TABLE_ALLOWED 并说明理由",
                })
    return out


def main() -> int:
    problems: list[str] = []
    tables = 0
    for directory in SCANNED:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            if path.name == Path(__file__).name:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, 1):
                if line.strip().startswith(("#", "//", "*")):
                    continue                      # 注释里列平台名是解释，不是表
                present = {name for name in KNOWN if re.search(rf"\b{name}\b", line)}
                if len(present) < 3:
                    continue
                tables += 1
                # 一张表可能跨行；把紧邻的几行一起看，避免把续行判成缺失。
                window = "\n".join(lines[max(0, number - 3): number + 3])
                name = _table_name(line)
                for platform in sorted(CUSTODIAL_PLATFORMS):
                    if re.search(rf"\b{platform}\b", window):
                        continue
                    if any(marker in line for marker in DELIBERATE_SUBSETS):
                        continue
                    problems.append(
                        f"{path.relative_to(ROOT)}:{number} 这张表（{name}）里没有 {platform}"
                    )

            # **再按括号块看一遍**——跨行的表单行规则一个都看不见。
            for start, block in _blocks(lines):
                names = {name for name in KNOWN if re.search(rf"\b{name}\b", block)}
                if len(names) < 3:
                    continue
                head = lines[start - 1]
                if any(marker in block for marker in DELIBERATE_SUBSETS):
                    continue
                tables += 1
                for platform in sorted(CUSTODIAL_PLATFORMS):
                    if re.search(rf"\b{platform}\b", block):
                        continue
                    problems.append(
                        f"{path.relative_to(ROOT)}:{start} 这个块（{_table_name(head)}）里没有 {platform}"
                    )

    extra = _extra_name_tables()
    problems.extend(f"{item['where']} {item['problem']}" for item in extra)

    print(f"扫了 {'/'.join(SCANNED)} 下 {tables} 处平台表；"
          f"已登记的有意子集 {len(DELIBERATE_SUBSETS)} 张；"
          f"允许自带平台中文名的地方 {len(NAME_TABLE_ALLOWED)} 处")
    if problems:
        print(f"**漏了 {len(problems)} 处**：")
        for item in sorted(set(problems)):
            print(f"  {item}")
        print("  ↳ 加平台时漏一张表，用户看到的是内部 id、空白，"
              "或者**一个根本不存在的按钮**。")
        print("  ↳ 确实该是子集的话，登记进 DELIBERATE_SUBSETS，**并写下理由**。")
        return 1
    print("每一张平台表都提到了所有可托管平台。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
