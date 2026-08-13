r"""复制链**从来没跑过**时，界面必须说话（2026-08-14）。

## 它修的是什么

2026-08-13 我把「备份这条链停了」接进了 `/health.backup`，界面也读了。
2026-08-14 拿空数据根起真 app 一量，发现**同一个病还压着另一条链**：

    backup       从没跑过 → message_zh="还没有做出过任何一次备份。"   徽标会说话
    replication  从没跑过 → **连 message_zh 这个键都不下发**          徽标全哑

哑的原因是一个三合一的 `except (OSError, ValueError)`：
文件不在（**知道**——`replicate_objects.py` 跑一次就会写它）、
读不动（**不知道**）、不是合法 JSON（**知道，坏了**）收成了一支，
只能统一答 `status="unknown"`，而 unknown 按设计不说话。
于是「确实一次都没跑过」搭着「不知道」的便车溜了过去。

这正是 2026-08-04 事故的形状：三个 timer 全 disabled、90 天 No entries，
而界面照样显示「已归档」。**全新安装、或者那个状态文件被删掉，都会落进这一支。**

`failure_copy.py` 第 443 行那句注释写着「上一轮我只把 replication 接了出来，
就以为这条线补完了」——这次是反过来又犯一次。所以这道测试盯的不是某一句文案，
是**两条链在同一个状态下必须一样会说话**。
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from social_archive import failure_copy  # noqa: E402


def _health(tmp_path, monkeypatch, build) -> dict:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir(parents=True, exist_ok=True)
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    build(root)
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
    return TestClient(api.app).get("/health").json()


def _nothing(root: Path) -> None:
    """全新安装：两条链都一次没跑过。"""


def _healthy(root: Path) -> None:
    for chain in ("private-database", "runtime-db"):
        snapshot = root / "backups" / chain / "20260814T030000Z"
        snapshot.mkdir(parents=True)
        (snapshot / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "status").mkdir(parents=True, exist_ok=True)
    (root / "status/object-replication.json").write_text(
        json.dumps({"generated_at": "2026-08-14T03:05:00Z", "status": "PASS"}),
        encoding="utf-8")


def _corrupt(root: Path) -> None:
    _healthy(root)
    (root / "status/object-replication.json").write_text("{ not json", encoding="utf-8")


def test_a_replication_that_never_ran_says_so(tmp_path, monkeypatch) -> None:
    """从没跑过 → 必须说话，而且说的是冻结词典里那一句。"""
    health = _health(tmp_path, monkeypatch, _nothing)
    chain = health["replication"]

    assert chain["message_zh"] == failure_copy.NO_REPLICATION_YET_SENTENCE, (
        "复制链一次都没跑过，而 /health 一个字都没说——"
        f"实际下发：{chain}")
    # `stale=None` 是"不知道"的意思，按设计不说话。这里**知道**：
    # 文件不在就是没跑过，所以不许落进不知道那一支。
    assert chain["stale"] is True, f"「从来没跑过」不是「不知道」，实际：{chain['stale']}"
    assert chain["status"] == "never-ran", chain["status"]


def test_both_chains_speak_in_the_same_state(tmp_path, monkeypatch) -> None:
    """**这才是真正要守的东西**：同一个状态下，两条链要么都说话、要么都不说。

    只盯 replication 那一句的话，下一次轮到别的链出这个病时照样看不见。
    """
    silent_when_never_ran = [
        name for name, chain in _health(tmp_path, monkeypatch, _nothing).items()
        if name in ("backup", "replication") and not chain.get("message_zh")
    ]
    assert not silent_when_never_ran, (
        f"这几条链「从来没跑过」时一个字都不说：{silent_when_never_ran}。"
        "界面靠 message_zh 触发徽标，不下发这一格 = 用户看不见。")


def test_a_broken_status_file_is_not_read_as_healthy(tmp_path, monkeypatch) -> None:
    """状态文件坏了也是**知道**（知道说不清），不许装作没看见。"""
    chain = _health(tmp_path, monkeypatch, _corrupt)["replication"]
    assert chain["message_zh"] == failure_copy.REPLICATION_STATUS_UNREADABLE_SENTENCE, chain
    assert chain["stale"] is True, chain


def test_a_healthy_chain_stays_quiet(tmp_path, monkeypatch) -> None:
    """反方向：都跑成了就别说话。少了这条，上面几条可以靠"永远说话"作弊过关。"""
    health = _health(tmp_path, monkeypatch, _healthy)
    for name in ("backup", "replication"):
        assert not health[name]["message_zh"], (
            f"{name} 一切正常却在说话——狼来了几次之后没人会再看徽标：{health[name]}")
        assert health[name]["stale"] is False, health[name]


def test_the_field_set_does_not_depend_on_which_branch_ran(tmp_path, monkeypatch) -> None:
    """键集必须在所有状态下一样。

    修之前是不一样的：`backup` 的降级支多一个 `why`，
    `replication` 的降级支**少** `hours_since` 和 `message_zh`。
    后果不只是难看——任何"拿一份夹具量出 schema 再去核对文档"的判据，
    都会同时产生假阴（漏掉只在降级支出现的名字）和假阳（把只在正常支
    出现的名字报成不存在）。2026-08-14 我写的那道文档判据就是这么坏的。
    """
    states = {
        "从没跑过": _nothing,
        "正常": _healthy,
        "状态文件坏了": _corrupt,
    }
    seen: dict[str, dict[str, frozenset]] = {}
    for index, (label, build) in enumerate(states.items()):
        # 每种状态一个干净的根：**共用一个根的话，上一种状态留下的文件
        # 会渗进下一种**（这个仓的变异台就因为不复原包根，第 7 条起归因全掺余毒）。
        health = _health(tmp_path / f"state{index}", monkeypatch, build)
        for name in ("backup", "replication"):
            seen.setdefault(name, {})[label] = frozenset(health[name])

    for name, per_state in seen.items():
        distinct = set(per_state.values())
        assert len(distinct) == 1, (
            f"{name} 的键集随状态变：" +
            "；".join(f"{label}={sorted(keys)}" for label, keys in per_state.items()))


@pytest.mark.skipif(os.geteuid() == 0, reason="root 读得动 chmod 000，这条测不了")
def test_unreadable_is_not_the_same_as_never_ran(tmp_path, monkeypatch) -> None:
    """**读不动**才是真的不知道——那一支必须闭嘴，不许拿它吓人。

    这条是上面几条的负对照：如果实现图省事把三支又并回一支
    （统统当成"没跑过"并说话），上面全绿而这条会红。
    """
    def unreadable(root: Path) -> None:
        _healthy(root)
        (root / "status/object-replication.json").chmod(0o000)

    chain = _health(tmp_path, monkeypatch, unreadable)["replication"]
    assert chain["stale"] is None, f"读不动 ≠ 没跑过，不该给出判断：{chain}"
    assert not chain["message_zh"], f"不知道的事不该说出来吓人：{chain}"
