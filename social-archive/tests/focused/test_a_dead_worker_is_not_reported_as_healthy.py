"""后台没在跑的时候，/health 不许说一切正常（v0.0.0.18）。

2026-08-06 一次被打断的部署留下的状态：

    core-api      0.0.0.17  Up (healthy)
    core-worker   0.0.0.17  **Created —— 没启动**

而 `/health` 由 api 提供，它照样回 `"status": "ok"`。
**从外面完全看不出后台没在跑**，用户点了同步只会看到任务静静排队，
而每一处显示都说服务是好的。

这正是这个产品一直在防的那个形状——健康检查不读出问题的那半边
（部署脚本的文件头写着同一件事：「只给前者，容器 /health 照样 200
而业务路由一律 401，界面永远『同步中』」）。

修法是一行心跳：worker 每轮循环写一次时间戳，/health 拿它和现在比。
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    """照 test_capture_api.py 的老办法起一个真 app —— 这里必须走真接口，
    因为要验的正是 `/health` 这个端点说什么。"""
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
    return TestClient(api.app), api.store


def test_health_says_the_worker_has_never_been_seen(tmp_path, monkeypatch) -> None:
    """还没有 worker 写过心跳时，**不许说它活着**，也要分清是哪一种。

    「从来没露过面」和「露过面但很久没动」下一步不一样：
    前者多半是刚部署完还没起来，后者是它挂了。合成一个布尔值会把
    「刚部署完」也报成故障，那种门很快会被人忽略。
    """
    client, _ = _client(tmp_path, monkeypatch)
    payload = client.get("/health").json()
    worker = payload["worker"]
    assert worker["ever_seen"] is False
    assert worker["alive"] is False
    assert "没收到过" in worker["note"]


def test_a_fresh_heartbeat_reads_as_alive(tmp_path, monkeypatch) -> None:
    client, store = _client(tmp_path, monkeypatch)
    store.record_worker_heartbeat("test-host:1")
    worker = client.get("/health").json()["worker"]
    assert worker["ever_seen"] is True
    assert worker["alive"] is True, f"刚写的心跳却被判成挂了：{worker}"
    assert worker["seconds_since"] is not None and worker["seconds_since"] < 30


def test_a_stale_heartbeat_reads_as_dead_and_says_why(tmp_path, monkeypatch) -> None:
    """**这条是整件事的重点。**

    心跳停了，接口本身照样是好的——那句话必须被说出来，
    否则运维看到 status=ok 就走了。
    """
    client, store = _client(tmp_path, monkeypatch)
    old = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    with store.connection() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """INSERT INTO worker_heartbeat(worker_id,owner,last_seen_at)
               VALUES('default','stale',?)
               ON CONFLICT(worker_id) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
            (old,))
        con.execute("COMMIT")
    worker = client.get("/health").json()["worker"]
    assert worker["alive"] is False, "心跳停了半小时，却还说它活着"
    assert worker["seconds_since"] > 1000
    assert "接口本身照样是好的" in worker["note"], (
        "只说了 worker 挂了，没说「而接口是好的」——"
        "而正是那半句让人看懂为什么 status 还是 ok"
    )


def test_the_worker_writes_a_heartbeat_even_when_idle() -> None:
    """**空转的那一轮也要写。**

    只在有任务时写的话，「闲着但活着」和「死了」在数据上分不开——
    而恰恰是没任务的时候最需要知道它还在。
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "src/social_archive/worker.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    loop = code.split("while True:", 1)[1]
    beat = loop.index("record_worker_heartbeat")
    claim = loop.index("claim_job")
    assert beat < claim, (
        "心跳写在取任务之后——没任务的那一轮就不会写，"
        "于是「闲着但活着」会被报成「挂了」"
    )
