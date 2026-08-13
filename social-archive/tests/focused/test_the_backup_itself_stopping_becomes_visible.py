r"""**备份本身**停了，`/health` 必须说出来（2026-08-13）。

## 上一轮我只补了半条线

`test_backup_silence_becomes_visible.py` 补的是 **replication**——把制品再
复制到别处那条链。但它上游还有一条：`backup.timer` 每天跑 `backup.py`，
**做出**那份加密快照。**两条链是分开的定时器，会单独死。**

2026-08-12、08-13 连着两天，`social-archive-backup.service` 以 `200/CHDIR`
失败（和 08-11 那次 replication 事故同一个根因：`/opt/social-archive` 被改回
700，两个服务共用这个 `WorkingDirectory`）。生产快照目录上一目了然：

    20260810T110900Z
    20260811T032747Z   ← 最后一次自动备份
    （8/12、8/13 两天的定时备份整个缺失）
    20260813T085049Z   ← 人手触发才补上的

而这两天里 replication 一直跑得好好的，`/health` 的 replication 那一格
**全程是绿的**，界面一个字都没有。

**修 08-11 那次事故时我只确认了 replication 恢复，没回头查 backup。**
同一个根因、同一个目录、隔壁那个服务，我没看。

## 这条判据钉的四件事

1. 刚备份过 → 不许说话；
2. 缺了一整天以上 → 必须说话，而且先按住"旧的没少"；
3. **只有目录没有 `manifest.json`**（跑一半崩了）→ 不算做完；
4. **读不到** 和 **确实一个都没有** 是两回事，不许并成一个默认值。
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def _make_snapshot(root: Path, when: datetime, *, finished: bool = True) -> str:
    """造一份快照。目录名就是它的时刻——生产上就是这么落的。"""
    name = when.strftime("%Y%m%dT%H%M%SZ")
    path = root / "backups/private-database" / name
    (path / "encrypted").mkdir(parents=True, exist_ok=True)
    if finished:
        (path / "manifest.json").write_text("{}", encoding="utf-8")
    return name


@pytest.fixture
def api_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """**先把环境指到 tmp 再导入**——`api.py` 一进来就 ensure_directories()。
    照抄这个仓已有的写法。"""
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


def test_刚备份过就不要打扰他(api_module, tmp_path: Path) -> None:
    name = _make_snapshot(tmp_path, datetime.now(UTC) - timedelta(hours=2))
    got = api_module._backup_liveness()                           # noqa: SLF001
    assert got["stale"] is False
    assert got["last_backup_at"] == name
    assert got["message_zh"] == "", "刚跑过还说话，就成了狼来了"


def test_缺了两天必须说出来(api_module, tmp_path: Path) -> None:
    """**这就是 8/12~8/13 那两天里本该出现的那句话。**"""
    _make_snapshot(tmp_path, datetime.now(UTC) - timedelta(days=2, hours=6))
    got = api_module._backup_liveness()                           # noqa: SLF001
    assert got["stale"] is True
    assert got["message_zh"], "两天没有新备份而 /health 一声不吭——正是这次"
    # 先按住他最担心的那件事：旧的没少；再说清真正缺的是什么。
    assert "一条都没少" in got["message_zh"]
    assert "没有进过备份" in got["message_zh"]


def test_跑一半崩掉不算做完(api_module, tmp_path: Path) -> None:
    """**光有目录不算备份。** 新鲜但没写完的那个不能把旧的顶掉，
    否则崩一次就永远显示"刚刚备份过"。"""
    old = _make_snapshot(tmp_path, datetime.now(UTC) - timedelta(days=3))
    _make_snapshot(tmp_path, datetime.now(UTC) - timedelta(minutes=5), finished=False)
    got = api_module._backup_liveness()                           # noqa: SLF001
    assert got["last_backup_at"] == old, "没有 manifest.json 的那个被当成做完了"
    assert got["stale"] is True, "最近一次做完的是 3 天前，这必须是红的"


def test_一次都没备份过要直说(api_module, tmp_path: Path) -> None:
    (tmp_path / "backups/private-database").mkdir(parents=True)
    got = api_module._backup_liveness()                           # noqa: SLF001
    assert got["stale"] is True
    assert "还没有做出过任何一次备份" in got["message_zh"]


def test_读不到不等于没有备份(api_module, tmp_path: Path, monkeypatch) -> None:
    """**这个仓最常踩的那种空默认值。** 读不动时的正确答案是"不知道"，
    既不是"没问题"，也不是拿"一个都没有"去吓他。"""
    def _boom(self):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(Path, "iterdir", _boom)
    got = api_module._backup_liveness()                           # noqa: SLF001
    assert got["stale"] is None, "读不到就该是「不知道」，不该是 False 也不该是 True"
    assert got["message_zh"] == "", "读不到就不许拿吓人的话去填"
    assert "读不到" in got["why"]


def test_两条链分开报(api_module, tmp_path: Path) -> None:
    """**8/12~13 就是只死了 backup 一条。** 合成一格的话，
    replication 还活着就会把它盖过去——那正是当时看不见的原因。"""
    got = api_module.health()
    assert "backup" in got and "replication" in got, "两条会单独死的链要分开报"
