"""服务端认识的平台，界面上也得认识（v0.0.0.7 / T06）。

2026-08-05 实测：youtube 在**服务端凭据表**（还有 CHECK 约束顶着）、
**Cookie 导出白名单**、**manifest 权限声明**三处都是受支持的托管平台，
唯独 PLATFORM_RULES——驱动界面、权限请求、平台识别的那张表——里没有它。

**权限要了、存得下、导得出，而他点不到。** 三层支持，一层缺席，
而缺席的恰好是唯一他碰得到的那层。由 Owner 裁定接上之后，
这条判据把这类缺口钉住，免得下一个平台再这样躺半年。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# **只出现在状态列表里、界面上没有入口的平台。**
#
# tiktok：它只活在 registry 的 DISPLAY / DEFAULT_RELATION 里，
# PLATFORM_RELATIONS、PLATFORM_LABELS、权限模式一概没有。也就是说
# 状态页会列出一行「TikTok 本版本还不能自动读取这个平台的内容」，
# 而产品其余部分根本不知道有这个平台。
#
# 那一行**不是谎**（它说的正是做不到），但它是个幽灵：列着、连不了、也没写
# 何时会有。留着它需要一个理由，所以写在这里——**没写下来的决定，
# 和疏忽长得一模一样**（youtube 就是这么躺了很久的）。
STATUS_ONLY_PLATFORMS = {
    "tiktok": "只在状态列表里露一行「本版本还不能自动读取」；产品其余部分没有它，"
              "也没有连接入口。要么哪天补齐成真平台，要么从 DISPLAY 里去掉——"
              "在那之前，它的存在是有意的、并且被记在案。",
}


def _ui_platform_ids() -> set[str]:
    script = '''
const fs=require("fs"), vm=require("vm");
const s={chrome:{runtime:{getURL:()=>""}},console,URL,URLSearchParams};
s.globalThis=s; s.self=s; s.window=s;
vm.runInContext(fs.readFileSync("apps/browser-extension/shared.js","utf8"), vm.createContext(s));
console.log(JSON.stringify(s.SA.PLATFORM_RULES.map(r=>r.id)));
'''
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, check=True)
    return set(json.loads(done.stdout))


def _server_tables() -> dict[str, set[str]]:
    sys.path.insert(0, str(ROOT / "src"))
    from social_archive.account_sync import (
        NOT_SYNCABLE_YET, PLATFORM_LABELS, PLATFORM_RELATIONS,
        SERVER_ACCOUNT_CONNECTORS, SYNCABLE_NOW,
    )
    from social_archive.credentials import CUSTODIAL_PLATFORMS
    from social_archive.registry import DISPLAY

    return {
        "PLATFORM_RELATIONS": set(PLATFORM_RELATIONS),
        "PLATFORM_LABELS": set(PLATFORM_LABELS),
        "SERVER_ACCOUNT_CONNECTORS": set(SERVER_ACCOUNT_CONNECTORS),
        "CUSTODIAL_PLATFORMS": set(CUSTODIAL_PLATFORMS),
        "SYNCABLE_NOW": set(SYNCABLE_NOW),
        "NOT_SYNCABLE_YET": set(NOT_SYNCABLE_YET),
        "registry.DISPLAY": set(DISPLAY),
    }


def test_every_server_side_platform_is_reachable_in_the_ui() -> None:
    ui = _ui_platform_ids()
    orphans = []
    for table, ids in _server_tables().items():
        for platform in sorted(ids - ui - set(STATUS_ONLY_PLATFORMS)):
            orphans.append(f"{platform}（在 {table} 里有，界面上没有）")
    assert not orphans, (
        "这些平台服务端支持、而他点不到——**youtube 就是这么躺了很久的**："
        + "；".join(orphans)
        + "。要么把它接进 PLATFORM_RULES，要么写进 STATUS_ONLY_PLATFORMS 并说明理由。"
    )


def test_the_custody_platforms_are_all_clickable() -> None:
    """托管平台尤其不能缺入口：**存得下却连不上，等于那张表白写。**"""
    ui = _ui_platform_ids()
    custodial = _server_tables()["CUSTODIAL_PLATFORMS"]
    missing = sorted(custodial - ui)
    assert not missing, f"这些平台能托管凭据、却没有连接入口：{missing}"


def test_the_registered_exceptions_are_really_absent_from_the_ui() -> None:
    """登记的例外必须**确实**是例外——它要是哪天被接进界面了，
    这条会红，提醒把它从名单里删掉，而不是让名单越攒越长没人管。"""
    ui = _ui_platform_ids()
    stale = sorted(set(STATUS_ONLY_PLATFORMS) & ui)
    assert not stale, f"这些已经在界面上了，该从 STATUS_ONLY_PLATFORMS 里删掉：{stale}"


def test_every_clickable_platform_is_known_to_the_server() -> None:
    """**反过来也要成立。**

    界面上有、而服务端不认识的平台，会让他点一个后端放不下的东西：
    连接时找不到关系类型、状态页没有它、能力声明里也没有它的位置——
    而「每个平台要么能同步、要么有一句说不能的理由」那道判据只管
    服务端那张表，界面上多出来的它一个字都看不见。

    两个方向都钉住，这类缺口才是封死的。
    """
    ui = _ui_platform_ids()
    tables = _server_tables()
    unknown = sorted(
        platform for platform in ui
        if platform not in tables["PLATFORM_RELATIONS"]
        or platform not in tables["PLATFORM_LABELS"]
    )
    assert not unknown, (
        f"这些平台界面上点得到、服务端却不认识：{unknown}。"
        "连接时会找不到关系类型，能力声明里也没有它的位置。"
    )


def test_every_clickable_platform_has_an_honest_capability_line() -> None:
    """点得到的每一个，要么在「现在能同步」里，要么有一句说不能的理由。

    这条和 test_syncable_now_is_a_fact_list 里那条是同一件事，
    但**从界面那一侧数**——那一侧多出一个平台时，服务端那条数不到它。
    """
    ui = _ui_platform_ids()
    tables = _server_tables()
    declared = tables["SYNCABLE_NOW"] | set(tables["NOT_SYNCABLE_YET"])
    silent = sorted(ui - declared)
    assert not silent, (
        f"这些平台界面上点得到，却既不在「能同步」也没有一句说不能的理由：{silent}"
    )


def _catalog_platform_ids() -> set[str]:
    """content/platform-catalog.js 里那份平台目录。

    **第三张表。** 我第一版只对了「服务端 ↔ shared.js」两张，于是接上 youtube
    之后它在目录里仍然缺席——platformLabel("youtube") 返回的是内部 id
    「youtube」本身，任何用中文名的地方都会把它甩给用户看。
    一个只覆盖两张表的判据，挡不住第三张表上的同一个洞。
    """
    done = subprocess.run(
        ["node", "-e",
         'const c=require("./apps/browser-extension/content/platform-catalog.js");'
         'console.log(JSON.stringify(Object.keys(c.PLATFORMS)));'],
        cwd=ROOT, capture_output=True, text=True, check=True)
    return set(json.loads(done.stdout))


def test_every_clickable_platform_has_a_chinese_name_in_the_catalog() -> None:
    """点得到的每一个平台，目录里都要有中文名。

    没有的话 platformLabel 会原样返回内部 id——而界面上多处直接显示它，
    用户看到的就是「youtube」「xiaohongshu」这种词。
    Owner 的原话：「我没有技术基础」。
    """
    ui = _ui_platform_ids() - {"generic-web"}   # 通用网页不是平台，目录里本就没有
    missing = sorted(ui - _catalog_platform_ids())
    assert not missing, (
        f"这些平台点得到、目录里却没有中文名：{missing}——"
        "platformLabel 会把内部 id 直接甩给用户"
    )
