"""盘要满了，服务得先说一声（2026-08-07）。

**盘满是这个服务已知的死法。** 2026-08-05 那次：`/v1/accounts` 报
`sqlite3.OperationalError: unable to open database file`——SQLite 建不出
`-wal`/`-shm` 时就是这句话。部署脚本因此立了「不足 5G 不许构建」那道门，
但那只拦住**我**，拦不住盘自己满。

2026-08-07 实测：同机另一个项目的容器可写层 2.5 小时涨了 0.58G
（2.48→3.06GB），而我们自己的服务从头到尾一声不吭——`/health` 里
没有任何一个字段和磁盘有关。

这里守两件事，都是这类检查最常见的空转法：
  · **量的必须是数据库那块盘**，不是根分区（根分区宽裕而数据盘满了，
    它照样报健康）；
  · **量不出来要说量不出来**，不许拿 0 或者 null 冒充「没问题」。
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app), api


def test_health_reports_how_much_room_is_left(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    disk = client.get("/health").json()["disk"]
    assert disk["measured"] is True, disk
    assert disk["free_bytes"] > 0 and disk["free_gb"] > 0
    assert 0 <= disk["used_percent"] <= 100


def test_it_measures_the_database_disk_not_the_root_disk(tmp_path, monkeypatch) -> None:
    """**量错地方是这类检查最常见的空转。**

    根分区宽裕、数据盘满了，一道量根分区的检查会一路报健康到服务写不下为止。
    """
    client, api = _client(tmp_path, monkeypatch)
    disk = client.get("/health").json()["disk"]
    measured_at = disk["measured_at"]
    database = str(api.settings.runtime_db.resolve())
    assert database.startswith(measured_at) or measured_at.startswith(str(tmp_path)), (
        f"量的是 {measured_at}，而数据库在 {database}——**量错盘了**")
    assert measured_at != "/", "量的是根分区，不是数据库那块盘"


def test_an_unmeasurable_disk_is_not_reported_as_fine(tmp_path, monkeypatch) -> None:
    """**量不出来要说量不出来。**

    这个仓栽在「空默认值被读成没问题」上不止一次，最坏一次静默吞掉的是
    对照基准本身。所以量不到的时候要给 `measured: False` 和一句原因，
    而不是 0 或者 null——那两个在监控里长得跟「很宽裕」一模一样。
    """
    client, api = _client(tmp_path, monkeypatch)

    def boom(_path):
        raise OSError("盘不见了")

    monkeypatch.setattr(api.shutil if hasattr(api, "shutil") else __import__("shutil"),
                        "disk_usage", boom)
    disk = client.get("/health").json()["disk"]
    assert disk["measured"] is False, disk
    assert disk.get("why_zh"), "没说为什么量不出来"
    assert "free_bytes" not in disk, "量不出来却还给了一个数——那会被读成「很宽裕」"


def test_a_full_disk_does_not_mark_the_service_unhealthy(tmp_path, monkeypatch) -> None:
    """**只报事实，不在这里判死活。**

    判多少算低是监控的事。一个会因为磁盘把自己标成不健康的服务，
    会在还能用的时候被负载均衡摘掉——那是把一个警告变成一次停机。
    """
    client, api = _client(tmp_path, monkeypatch)
    import shutil as real_shutil

    monkeypatch.setattr(
        real_shutil, "disk_usage",
        lambda _p: real_shutil._ntuple_diskusage(100 * 1024 ** 3, 100 * 1024 ** 3, 0))
    body = client.get("/health").json()
    assert body["status"] == "ok", "盘满了就把自己标成不健康——那是把警告变成停机"
    assert body["disk"]["free_gb"] == 0.0
    assert body["disk"]["used_percent"] == 100.0
