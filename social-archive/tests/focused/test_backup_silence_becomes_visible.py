r"""备份那条链停了，`/health` 必须说出来（2026-08-13）。

## 它修的是一次真事故

2026-08-11 23:53 起，`social-archive-replication.service` 每次触发都以
`200/CHDIR` 失败——有人把 `/opt/social-archive` 改成了 700，而它以
`socialarchive` 用户跑，连工作目录都进不去。

**连着失败 108 次、28 小时。** 而这段时间里：

    /v1/status 的 replicas   github/oci/r2 全是 verified
    recovery.last_backup     写死成 "unknown"
    界面                     一个字都没有

「加密存三份」停了一天多，**每一个绿灯都还是绿的**。

## 为什么 replicas 那一格救不了

它读的是库里记着的**回执**——记的是"过去成功过"。定时器死掉之后没有新回执，
旧回执原样躺着，于是它永远是绿的。**回执是历史，不是活性。**

活性信号是另一样东西：`replicate_objects.py` 每跑一次就重写
`status/object-replication.json`。跑不起来时那个文件停在旧时间——
**所以要看的是它的时间戳**。

## 这条判据钉两个方向

新鲜 → 不许说话（不打扰）；停了 → 必须说话，而且那句话要先按住他最担心的事：
**已经存下来的东西没有少**。
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def _write_heartbeat(root: Path, when: datetime, status: str = "PASS") -> None:
    path = root / "status/object-replication.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generated_at": when.isoformat().replace("+00:00", "Z"),
        "status": status,
    }, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def api_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """**先把环境指到 tmp 再导入**——`api.py` 一进来就 ensure_directories()，
    不指的话它会去动 `/var/lib/social-archive`（本机直接 PermissionError）。
    这是这个仓已有的写法，照抄。"""
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



def test_刚跑过就不要打扰他(api_module, tmp_path: Path) -> None:
    _write_heartbeat(tmp_path, datetime.now(UTC) - timedelta(minutes=10))
    got = api_module._replication_liveness()                      # noqa: SLF001
    assert got["stale"] is False
    assert got["message_zh"] == "", "刚跑过还说话，就成了狼来了"


def test_停了就必须说出来(api_module, tmp_path: Path) -> None:
    """**这就是那 28 小时里本该出现的那句话。**"""
    _write_heartbeat(tmp_path, datetime.now(UTC) - timedelta(hours=28))
    got = api_module._replication_liveness()                      # noqa: SLF001
    assert got["stale"] is True
    assert got["message_zh"], "备份停了 28 小时而 /health 一声不吭——正是这次事故"
    # 先按住他最担心的那件事：东西没少。
    assert "一条都没少" in got["message_zh"]
    assert "28 小时" in got["message_zh"]


def test_跑了但没跑完也要说(api_module, tmp_path: Path) -> None:
    _write_heartbeat(tmp_path, datetime.now(UTC) - timedelta(minutes=5),
                     status="DEGRADED")
    got = api_module._replication_liveness()                      # noqa: SLF001
    assert got["message_zh"], "这一轮没跑完，也该说"


def test_文件还不存在时不许假装正常(api_module, tmp_path: Path) -> None:
    """**「读不到」不等于「没问题」**——这个仓最常踩的那种空默认值。"""
    got = api_module._replication_liveness()                      # noqa: SLF001
    assert got["status"] == "unknown"
    assert got["stale"] is None, "读不到就该是「不知道」，不该是 False"
