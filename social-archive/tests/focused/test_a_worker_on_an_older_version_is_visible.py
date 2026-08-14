r"""worker 活着、但跑的是旧版——这件事必须看得见（2026-08-14）。

## 它修的是什么

`HANDOFF.md` 让接手方靠四样判活：`version` / `worker.alive` /
`backup.stale` / `replication.stale`。**有一种情况这四样全正常而系统是坏的**：

部署被打断时，可能 `core-api` 换成了新镜像而 `core-worker` **还跑着旧的**。
那时 `version` 是 api 报的（新的）、`worker.alive` 是 `true`
（旧 worker 照样发心跳）、两条备份链也没事——**而后台跑的是旧代码**。

实测过（v0.0.0.96 那天）：`/health.worker` 只有
`ever_seen`/`alive`/`last_seen_at`/`seconds_since`/`note`，
心跳表 `worker_heartbeat` 只有 `worker_id`/`owner`/`last_seen_at`——**两边都不带版本**。

这是 2026-08-06 那次事故的更坏变体：那次 SIGTERM 打断在 `docker compose up` 中间，
`core-worker` 卡在 `Created`、后台任务全积压，**而 /health 是好的**。
停着的那种后来被 `worker.alive` 查出来了；**活着但是旧的**，在此之前查不出来。

## 三层都要测，缺一层就等于没修

1. **心跳里存下了版本**（表结构 + 写入）
2. **`/health` 比对并给出句子**（判断在服务端，界面不自己造句）
3. **界面读那句话**——这一层最容易漏：`paintServiceBadge` 原来只看
   `worker.alive === false`，版本不符时 `alive` 是 true，一路穿过去，
   **句子存在而没人显示**。今天这一类（建好了没接上）已经是第四次。
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir(parents=True, exist_ok=True)
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


def test_版本对得上时不说话(tmp_path, monkeypatch) -> None:
    """反方向先立住。少了它，把实现写成「永远说版本不符」也能让下面那条过。"""
    client, api = _client(tmp_path, monkeypatch)
    from social_archive import __version__
    api.store.record_worker_heartbeat("test:1", __version__)
    worker = client.get("/health").json()["worker"]
    assert worker["alive"] is True, worker
    assert worker["version"] == __version__, worker
    assert worker["version_matches"] is True, worker
    assert not worker["message_zh"], f"版本一致却在说话：{worker}"


def test_worker_跑旧版时必须说出来(tmp_path, monkeypatch) -> None:
    client, api = _client(tmp_path, monkeypatch)
    api.store.record_worker_heartbeat("test:1", "0.0.0.1")
    worker = client.get("/health").json()["worker"]
    assert worker["alive"] is True, "这一条测的是**活着但是旧的**，先得让它活着"
    assert worker["version"] == "0.0.0.1", worker
    assert worker["version_matches"] is False, worker
    assert worker["message_zh"], (
        "worker 跑的是另一版，而 /health 一个字都没说——"
        f"界面靠 message_zh 触发徽章，不下发就等于看不见：{worker}")


def test_旧worker根本不写版本时也要说出来(tmp_path, monkeypatch) -> None:
    """**不写版本和写了个旧版本，都是"对不上"。**

    加这一列之前的 worker 不会写它，读出来是 None。
    把 None 当成"没意见"放行的话，**升级前的那个 worker 永远不会被发现**——
    而那恰恰是最可能出现的一种。
    """
    client, api = _client(tmp_path, monkeypatch)
    api.store.record_worker_heartbeat("test:1")   # 不带版本，模拟旧 worker
    worker = client.get("/health").json()["worker"]
    assert worker["alive"] is True, worker
    assert worker["version"] is None, worker
    assert worker["version_matches"] is False, worker
    assert worker["message_zh"], f"旧 worker 不报版本，也必须说出来：{worker}"


def test_worker那一格的键集不随分支变(tmp_path, monkeypatch) -> None:
    """今天为「字段依状态而存在」修过两条链，这一格不许重蹈。

    键集随分支变的话，任何拿一份夹具量 schema 的判据都会同时产生假阴和假阳。
    """
    keysets = []
    for index, setup in enumerate((
        lambda api: None,                                        # 从没发过心跳
        lambda api: api.store.record_worker_heartbeat("t:1"),     # 旧 worker，无版本
        lambda api: api.store.record_worker_heartbeat("t:1", "0.0.0.1"),  # 旧版本
    )):
        client, api = _client(tmp_path / f"s{index}", monkeypatch)
        setup(api)
        keysets.append(frozenset(client.get("/health").json()["worker"]))
    assert len(set(keysets)) == 1, (
        "worker 那一格的键集随状态变：" +
        "；".join(str(sorted(k)) for k in keysets))


def test_界面真的读了那句话() -> None:
    """**第三层：句子存在 ≠ 有人显示。**

    `paintServiceBadge` 原来只看 `worker.alive === false`；版本不符时
    `alive` 是 true，一路穿过去，句子谁也看不见。
    这里剥掉注释再查——**说明里提到 `worker.message_zh` 不等于代码读了它**
    （今天因为这个误判过好几次）。
    """
    source = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith("//")
    )
    assert re.search(r"worker(\.|\[\")message_zh", code), (
        "app.js 里没有任何地方读 `worker.message_zh`——"
        "服务端把句子算好了而界面不显示，等于没修。")


def test_老库加列那条路真的走得通(tmp_path, monkeypatch) -> None:
    """**上面五条一条都没走过 `ALTER TABLE`，而生产上正是老库。**

    它们都是新建库——直接从 `runtime_schema.sql` 拿到 `version` 那一列，
    迁移分支一次都没执行。这个仓栽过「没测过的兜底分支只在别人机器上发作」，
    而这次「别人的机器」是**他的生产库**。

    所以这里造一个**加列之前**的真库（只有三列、还带一行旧数据），
    让 `api` 起来跑一次迁移，再逐项核：列加上了、**旧行没丢**、
    旧行的 version 是 `None`（不是默认值——"旧 worker 没写过"本身就是信息）。
    """
    import sqlite3

    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    db = root / "db.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE worker_heartbeat "
                "(worker_id TEXT PRIMARY KEY, owner TEXT NOT NULL, last_seen_at TEXT NOT NULL)")
    con.execute("INSERT INTO worker_heartbeat VALUES('default','old:1','2026-08-14T00:00:00Z')")
    con.commit()
    con.close()
    before = [row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(worker_heartbeat)")]
    assert "version" not in before, f"夹具没造对，它本来就该缺这一列：{before}"

    client, api = _client(tmp_path, monkeypatch)   # 起 api = 跑迁移

    after = [row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(worker_heartbeat)")]
    assert "version" in after, f"迁移没加上这一列：{after}"

    row = sqlite3.connect(db).execute(
        "SELECT owner,version FROM worker_heartbeat WHERE worker_id='default'").fetchone()
    assert row is not None, "**旧行被迁移弄丢了**——加列不该动数据"
    assert row[0] == "old:1", f"旧行的内容变了：{row}"
    assert row[1] is None, f"旧行不该被塞默认值——None 才是「旧 worker 没写过」：{row}"

    # 迁移完之后，让那个**旧 worker 继续发心跳**（不带版本）——这才是真实形状：
    # 升级被打断时旧 worker 还活着、还在跑。
    #
    # （第一版这里直接读 /health 就断言 version_matches is False，**错的是我**：
    #   夹具里那行心跳是 15160 秒前的，worker 已经不 alive，
    #   而产品**故意**不在死掉的 worker 上再叠一句版本抱怨——那会盖掉更要紧的那句。）
    api.store.record_worker_heartbeat("old:1")
    worker = client.get("/health").json()["worker"]
    assert worker["alive"] is True, worker
    assert worker["version"] is None, worker
    assert worker["version_matches"] is False, worker
    assert worker["message_zh"], f"迁移完之后旧 worker 仍然不被点名：{worker}"
