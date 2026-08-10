"""界面从「单条内容详情」里读的每个键，服务端都得真的发（2026-08-10）。

## 它拦的是什么

`GET /v1/library/{id}` 直接返回 `store.get_content(...)`。那个方法往结果里
写了几个列表键（`export_receipts` / `destination_bindings` / `object_replicas` …），
而界面读的是 `row.detail?.<键>`。

2026-08-10 抓到一处对不上：界面读 **`destination_receipts`**，
服务端发的是 **`export_receipts`**。`destination_receipts` 不是打错字——
它是**另一条路由**（`/v1/status` 的全局 30 条）的键，同名不同物。

后果是静默的：`row.detail?.destination_receipts || []` 恒取到 `[]`，
不报错、不告警，于是**抽屉里那段回执列表一行都没画过、「重试」那颗按钮
一次都没出现过**，永远显示「尚无已完成回执」——而他库里 github 193 条、
markdown 193 条都是 done。

生产实测（拿他一条真内容问 `get_content`）：

    顶层键 = [… 'destination_bindings', 'export_receipts', 'object_replicas', …]
    destination_receipts 在不在 = False

这个仓有 `find_endpoints_no_client_calls.py` 扫「接口建好了没人调」，
**没有反方向的那把尺子**——「界面读的键，没人发」。这条判据补的就是它。

## 为什么只盯这一条路由

`/v1/accounts`、`/v1/sync-runs`、`/v1/destinations` 三条 2026-08-10 逐个问过
生产（只打印键名），界面读的键服务端一个不缺。真正会漂的是详情这条：
它的键不是从数据库列直接来的，是**在方法里手写拼进去的**，
拼的人和读的人隔着一个仓。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"
DB = ROOT / "src/social_archive/db.py"

pytestmark = pytest.mark.skipif(not APP.is_file(), reason="app.js 不存在")


def _keys_the_server_puts_in_the_detail() -> set[str]:
    """`get_content` 往结果里手写拼进去的那些键——从代码里取，不手抄。"""
    source = DB.read_text(encoding="utf-8")
    start = source.find("def get_content(")
    assert start > 0, "找不到 get_content——这条判据在空扫"
    end = source.find("\n    def ", start + 10)
    body = source[start:end if end > 0 else len(source)]
    keys = set(re.findall(r'result\[\s*"([a-z_]+)"\s*\]\s*=', body))
    # 结果本身还带着 content 表的列（`dict(row)`），列名从建表语句里取。
    schema = (ROOT / "src/social_archive/sql/runtime_schema.sql")
    if schema.is_file():
        text = schema.read_text(encoding="utf-8")
        table = re.search(r"CREATE TABLE IF NOT EXISTS content\b(.*?);", text, re.S)
        if table:
            keys |= set(re.findall(r"^\s*([a-z_]+)\s+[A-Z]", table.group(1), re.M))
    return keys


def test_the_extractor_is_not_scanning_empty() -> None:
    keys = _keys_the_server_puts_in_the_detail()
    assert len(keys) >= 4, f"只解析出 {keys}——正则够不到 get_content 了，下面每条都会白过"
    assert "export_receipts" in keys, f"解析到的键里没有 export_receipts：{sorted(keys)}"


def test_every_detail_key_the_ui_reads_is_really_sent() -> None:
    code = APP.read_text(encoding="utf-8")
    read = set(re.findall(r"detail\?\.([a-z_]+)", code)) | set(
        re.findall(r"detail\.([a-z_]+)", code))
    assert read, "界面一处 detail.<键> 都没读——这条判据在空扫"
    sent = _keys_the_server_puts_in_the_detail()
    # **允许"读了一个不存在的键"只有一种情形：它和一个真键写在同一个 `||` 兜底链上。**
    # 2026-08-10 那次修复保留了旧键做兼容，但把真键排在了前面。
    missing = sorted(key for key in read if key not in sent)
    for key in list(missing):
        chain = re.search(rf"detail\?\.[a-z_]+\s*\|\|\s*[^;]*detail\?\.{key}", code)
        if chain:
            missing.remove(key)
    assert not missing, (
        f"界面读了服务端不发的键：{missing}——`?.` 取不到时是 undefined，"
        "`|| []` 之后变成空数组，**不报错、不告警**，那一段就永远是空的。"
        f"服务端在详情里发的是：{sorted(sent)}")
