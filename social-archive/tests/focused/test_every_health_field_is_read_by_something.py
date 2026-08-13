r"""`/health` 里每一格都得有人读（2026-08-13）。

## 它修的是什么

2026-08-13 我给 `/health` 加了 `backup` 一格——备份那条链停了就说话。
判据全绿、生产回读也对。**而界面从来没读过它。**

资料库那一页只读 `health.replication`，于是那句新话谁也看不见，
而 `HANDOFF.md` 写着「打开资料库那一页就够了，坏了它会自己说话」——
**对刚死掉两天的那条链，这句话是假的。**

「建好了没接上」这个仓已经犯过至少 6 次，而现有的两个探测器**都看不见这一种**：

    find_endpoints_no_client_calls.py   只看 /v1 路由有没有人调（/health 根本不是 /v1）
    find_unwired_code.py                只看公开符号有没有人引用（_backup_liveness 被 health() 引用着）

两个都绿，因为没人读的**是路由里的一个字段**，不是路由、也不是符号。

## 口径（写出来，免得被当成覆盖了全部）

- 只查**顶层**字段。嵌套的（`replication.message_zh` 之类）不查。
- 「有人读」= 客户端源码里出现 `health.<字段>` 或 `health["<字段>"]`。
  **解构写法（`const {backup} = health`）这条判据看不见**——真那么写的话它会误报，
  而修法是把它加进下面那张表并写明理由，也就是逼一次自觉的决定，不是坏事。
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIRS = ("apps", "scripts")

# **故意不读的**，每条都要有理由。这张表只许缩短，不许在没想清楚时变长。
KNOWN_UNREAD = {
    "project": "常量招牌，给人 curl 时认出打的是哪个服务；界面不显示",
    "time": "服务端时刻，给人对时用；界面不显示",
    "paid_api_allowed": "付费开关的现状，给运维 curl 看；界面上没有对应入口",
    "archive_defaults": "L0～L3 的默认档位，给运维 curl 看；界面不显示",
}


@pytest.fixture
def api_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pwa = tmp_path / "pwa"; pwa.mkdir()
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": tmp_path,
        "SOCIAL_ARCHIVE_RUNTIME_DB": tmp_path / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": tmp_path / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": tmp_path / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": tmp_path / "import",
        "SOCIAL_ARCHIVE_EXPORT_ROOT": tmp_path / "exports",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    return importlib.reload(api)


def _strip_comments(text: str, suffix: str) -> str:
    """**注释里的字样不算「有人读」。**

    第一版没剥注释，于是它绿得毫无意义：我在 `app.js` 里解释这次改动时
    写了一句「v0.0.0.71 加了 `/health.backup` 这一格」——**判据匹配到了那句注释**。
    把代码退回只读 replication 的旧写法，判据照样全绿。

    **是跑反例发现的，不是读代码看出来的**（这个仓的判据切错，从来没有一次
    是读出来的）。
    """
    if suffix == ".py":
        return re.sub(r"#.*", "", text)
    if suffix == ".html":
        return re.sub(r"<!--.*?-->", "", text, flags=re.S)
    # .js：块注释整段去掉；行注释只在不是 `https://` 那种时去掉。
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?<!:)//.*", "", text)


def _client_sources() -> str:
    chunks = []
    for folder in CLIENT_DIRS:
        for path in (ROOT / folder).rglob("*"):
            if path.suffix in (".js", ".html", ".py") and path.is_file():
                chunks.append(_strip_comments(
                    path.read_text(encoding="utf-8", errors="replace"), path.suffix))
    return "\n".join(chunks)


def _is_read(field: str, sources: str) -> bool:
    return bool(re.search(
        rf"health\.{re.escape(field)}\b|health\[[\"']{re.escape(field)}[\"']\]", sources))


def test_每一格要么有人读要么写明为什么不读(api_module) -> None:
    """**这条判据在 backup 接上界面之前是红的**——那正是它要抓的那次。"""
    payload = api_module.health()
    sources = _client_sources()
    orphans = [k for k in payload
               if k not in KNOWN_UNREAD and not _is_read(k, sources)]
    assert not orphans, (
        f"/health 算出了这些格，而客户端一处都没读：{orphans}。\n"
        "服务端算得出、用户看不到，就是「建好了没接上」——这个仓犯过至少 6 次。\n"
        "要么在界面里读它，要么加进 KNOWN_UNREAD 并写明为什么不用读。")


def test_白名单里不许躺着已经被读的字段(api_module) -> None:
    """**白名单只许缩短。** 某一格后来接上了界面，就该从表里拿掉——
    留着它等于给下一个人挖坑：他会以为这格本来就不用读。"""
    sources = _client_sources()
    stale = [k for k in KNOWN_UNREAD if _is_read(k, sources)]
    assert not stale, f"这些已经有人读了，从 KNOWN_UNREAD 里删掉：{stale}"


def test_白名单里不许有已经不存在的字段(api_module) -> None:
    payload = api_module.health()
    ghosts = [k for k in KNOWN_UNREAD if k not in payload]
    assert not ghosts, f"/health 已经不回这些格了，从 KNOWN_UNREAD 里删掉：{ghosts}"


def test_备份那一格必须有人读(api_module) -> None:
    """单独钉住它：**这就是 2026-08-13 漏掉的那一格。**

    备份停了两天没人看得见，是因为界面只读 replication。
    两条链会单独死，所以两格都得有人读。"""
    sources = _client_sources()
    for field in ("backup", "replication"):
        assert _is_read(field, sources), (
            f"界面不读 health.{field}——那条链停了他就看不见")
