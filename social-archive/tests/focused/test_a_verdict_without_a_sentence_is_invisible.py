r"""判断出问题了，就必须有一句给人看的话（2026-08-14）。

## 它守的是这次缺陷的**一般形式**

v0.0.0.79 修的那个洞，具体形状是「复制链从来没跑过 → `message_zh` 这个键
根本不下发 → 徽章全哑」。但那只是一个实例。**一般形式是：**

    服务端已经判定「这件事不对」（`stale=true` / `status` 不是好值），
    而它没有给出任何一句人看得懂的话 —— 于是这个判定**只存在于 JSON 里**。

界面的触发条件是 `message_zh` 非空（`app.js` 里那句
`[health.backup, health.replication].find((chain) => chain && chain.message_zh)`）。
所以「有判断、没句子」= **屏幕上什么都不会发生**，
和「一切正常」在用户那里长得一模一样。

这个仓已经为这一类形状付过三次代价：
2026-08-04（三个 timer 全 disabled 而界面显示「已归档」）、
2026-08-13（备份链死了两天，界面一个字没有）、
2026-08-14（复制链的「从来没跑过」哑着）。
**每一次都是修完那一个实例就算了**，没有任何东西守着这条一般形式。

## 口径

- 只管 `/health` 里**活性那两条链**（`backup` / `replication`）。
  别的对象（`disk` / `worker` / `archive_defaults`）有各自的判据和触发方式。
- 判「不对」的口径写死成两条：`stale is True`，或 `status` 落在坏值集合里。
  **不用「不等于某个好值」**——那样新增一个中性状态就会误红。
- 反方向也钉：一切正常时不许说话。少了它，实现可以靠「永远说话」作弊过关。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

LIVENESS_CHAINS = ("backup", "replication")
BAD_STATUSES = {"never-ran", "unreadable", "FAIL", "INCOMPLETE"}


def _health(tmp_path: Path, monkeypatch, build) -> dict:
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
    """全新安装。"""


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


def _replication_failed(root: Path) -> None:
    _healthy(root)
    (root / "status/object-replication.json").write_text(
        json.dumps({"generated_at": "2026-08-14T03:05:00Z", "status": "FAIL"}),
        encoding="utf-8")


# **口径由夹具的意图给，不问服务端。**
#
# 第一版我写的是「服务端判定不对（`stale is True` 或 `status` 是坏值）就必须说话」，
# 拿修复前的 api.py 一跑：**3 条全绿**——这道判据在它专门纪念的那次缺陷上
# 一个红都没有。因为那次缺陷的形状恰恰是**坏状态被吞进 `unknown`、
# 压根没被判成不对**（`stale=None`），于是前提不成立，结论当然不违反。
#
# **判据不能拿被测方的结论当自己的前提。** 状态是我造的，好不好我知道；
# 服务端有没有认出来，正是要测的东西。
#
# 每一项：(造状态的函数, {链名: 这条链在这个状态下好不好})
STATES = {
    "从没跑过":       (_nothing,            {"backup": "坏", "replication": "坏"}),
    "正常":           (_healthy,            {"backup": "好", "replication": "好"}),
    "状态文件坏了":   (_corrupt,            {"backup": "好", "replication": "坏"}),
    "复制跑了但失败": (_replication_failed, {"backup": "好", "replication": "坏"}),
}


def test_坏状态必须有一句给人看的话(tmp_path: Path, monkeypatch) -> None:
    """状态是坏的（**我造的时候就知道**）→ `message_zh` 必须非空。"""
    silent = []
    for index, (label, (build, verdicts)) in enumerate(STATES.items()):
        health = _health(tmp_path / f"s{index}", monkeypatch, build)
        for name, expected in verdicts.items():
            if expected != "坏":
                continue
            block = health.get(name) or {}
            if not block.get("message_zh"):
                silent.append(f"{label} / {name} → {block}")

    assert not silent, (
        "这些状态是坏的，而 /health 一个字都没说：\n  "
        + "\n  ".join(silent)
        + "\n\n界面靠 message_zh 非空触发徽章，所以这件事只存在于 JSON 里——"
        "\n屏幕上什么都不会发生，和一切正常长得一模一样。"
        "\n这个仓为这一类形状付过三次代价（2026-08-04 / 08-13 / 08-14）。")


def test_服务端自己判成坏的也必须说话(tmp_path: Path, monkeypatch) -> None:
    """补一刀：**它自己都承认不对了**，那更没有理由不说。

    这条比上面那条弱（前提建在被测方的结论上），但它管得更宽：
    将来加了我这份夹具没造出来的坏状态，只要服务端认了，这里就会红。
    两条一起才是完整的——上面那条防「不承认」，这条防「承认了不说」。
    """
    silent = []
    for index, (label, (build, _)) in enumerate(STATES.items()):
        health = _health(tmp_path / f"v{index}", monkeypatch, build)
        for name in LIVENESS_CHAINS:
            block = health.get(name) or {}
            if (block.get("stale") is True or block.get("status") in BAD_STATUSES) \
                    and not block.get("message_zh"):
                silent.append(f"{label} / {name} → {block}")
    assert not silent, "服务端自己判成坏的，却一个字不说：\n  " + "\n  ".join(silent)


def test_一切正常时不许说话(tmp_path: Path, monkeypatch) -> None:
    """反方向。少了它，实现可以靠「永远说话」把上面两条骗过去，
    而狼来了几次之后没人会再看徽章。"""
    for index, (label, (build, verdicts)) in enumerate(STATES.items()):
        health = _health(tmp_path / f"q{index}", monkeypatch, build)
        noisy = [name for name, expected in verdicts.items()
                 if expected == "好" and (health.get(name) or {}).get("message_zh")]
        assert not noisy, f"{label}：这几条链好好的却在说话：{noisy}"


def test_这道判据自己盯着的链没有凭空变少(tmp_path: Path, monkeypatch) -> None:
    """**扫描集不许悄悄缩水。**

    这个仓最常见的失效方式不是判据判错，是它扫的东西变少了而它照样绿。
    所以把「/health 里哪些格子是活性链」这件事本身也断言一遍：
    新增一条链而没加进 LIVENESS_CHAINS 时，这里会红。
    """
    health = _health(tmp_path / "scan", monkeypatch, _healthy)
    # 活性链的识别特征：既有 `stale` 又有 `message_zh` 两格
    looks_like_a_chain = {
        name for name, value in health.items()
        if isinstance(value, dict) and "stale" in value and "message_zh" in value
    }
    assert looks_like_a_chain == set(LIVENESS_CHAINS), (
        f"/health 里长得像活性链的是 {sorted(looks_like_a_chain)}，"
        f"而这道判据只盯着 {sorted(LIVENESS_CHAINS)}——"
        "新增的那条不会被「判定不对就必须有话说」管到。")
