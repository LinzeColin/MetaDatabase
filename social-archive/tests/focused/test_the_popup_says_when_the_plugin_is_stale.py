"""弹窗也要告诉他插件旧了——它已经拿到那个数，只是扔掉了（2026-08-10）。

## 同一种病，第三个界面

`popup.js` 每次刷新都会调 `/health`：

    workerState = await SA.api("/health", …).then(payload => payload.worker || null)

应答里带着 `version`，**它只留了 `worker`，把版本整个丢掉了**。
于是点插件图标那一屏——他最可能先点的那个入口——
**完全不提「你装的是旧版」**，他会直接去点「立即同步全部账号」或
「连接与管理账号」，撞上旧包里那几条今天刚修掉的死路。

这个仓在安装页那段注释里写过同一句病历：

    应答里是带版本号的，而这一页原来只看「有没有回应」，把版本整个丢掉了。

换了个界面又犯一次。资料库那一页 2026-08-10 已经会拦了（`outdated` →
拦住连接并打开更新说明），弹窗这一侧还没有。

## 说清这一改帮不到今天

修好的弹窗在**新插件**里，而他此刻装的是旧的那份。所以这条只对**以后**的
更新有用；这一次仍然靠资料库那一页拦他。**不许把它说成「今天就生效」。**
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POPUP = ROOT / "apps/browser-extension/popup.js"

pytestmark = pytest.mark.skipif(not POPUP.is_file(), reason="popup.js 不存在")


def _code() -> str:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from js_source import code_only

    return code_only(POPUP)


def test_the_popup_keeps_the_version_from_health() -> None:
    """**别再把它丢掉。** `/health` 已经在调，版本就在那个应答里。"""
    code = _code()
    index = code.find('SA.api("/health"')
    assert index >= 0, "弹窗不再调 /health 了——那它连后台在不在都不知道"
    # **要的是「那次应答里的版本被留下来了」，不是「代码里出现过这个词」。**
    # 第一版只断言 `"serverVersion" in code`——把取值那一行删掉，
    # 变量声明还在，判据照样绿。反例试出来的，不是想出来的。
    after = code[index:index + 400]
    assert "serverVersion" in after and "version" in after, (
        f"弹窗调了 /health 却没把版本留下来：{after[:220]}——"
        "这正是安装页那段注释写过的病：「应答里是带版本号的，"
        "而这一页只看有没有回应，把版本整个丢掉了」")


def test_it_compares_against_its_own_manifest() -> None:
    code = _code()
    assert "getManifest().version" in code, (
        "没有拿自己的版本去比——只有服务端那个数，比不出「我是不是旧的」")


def test_it_says_so_where_he_will_see_it() -> None:
    """**看得见才算说了。** 只算出来不显示，等于没有（这个仓栽过：`outdated`
    算出来了，没有任何地方读它）。"""
    code = _code()
    # **锚在渲染那个函数上，不是第一处 `serverVersion`。**
    # 第一版锚错了：`serverVersion` 第一次出现是变量声明，往后 1500 字
    # 全是别的声明，于是判据报「算出来了却没说给他听」——
    # 红在自己的窗口位置上。今天第三次踩这个坑了。
    index = code.find("function renderUpdateNotice(")
    assert index >= 0, "找不到渲染那句话的函数——它是不是被改名了？"
    after = code[index:index + 1200]
    assert "旧版" in after, f"算出来了却没说给他听：{after[:200]}"
    # **要的是「有人调它」，而 `renderUpdateNotice()` 这个串在定义那一行也有。**
    # 第一版就是这么写的，把「函数写了没人调」那个反例放过去了——
    # 而那正是这条断言要抓的东西。改成找一条真正的调用语句。
    import re as _re

    assert _re.search(r"^\s*renderUpdateNotice\(\);", code, _re.M), (
        "函数写了却没人调——这个仓栽过：`outdated` 算出来了，没有任何地方读它")
    assert "extension-install" in code, (
        "没有把更新说明的去处给他——「做不到不是罪，做不到却说不清才是」")
