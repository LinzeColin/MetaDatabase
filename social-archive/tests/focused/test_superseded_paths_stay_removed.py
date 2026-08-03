"""防复活守卫（v0.0.0.7 / T03）。

这个文件取代了原先那 6 个**断言那三个 worker 存在**的测试。
它们不是被静默删掉的——是被反过来了：原来断言「xhs/ks/douk worker 已定义且
健康检查就位」，现在断言「它们不许再出现」。

为什么要反过来而不是直接删：`CONFLICT_ORDER.md` 把这条路列为 SUPERSEDED，
理由是**实测证伪**——那三个上游项目的 HTTP API 只有单篇详情，
`XHS-Downloader` 是 `/xhs/detail`，`DouK` 只有 detail/account/mix/live/comment/search，
**都没有任何收藏枚举接口**。按那个 compose 把它们起成 worker，
拿到的还是单篇详情，同步结果**依然是 0**。

删掉一个错误实现只解决今天；留一条守卫才防得住明天有人看着旧文档
"把它加回来"。这就是那条守卫。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_domestic_http_worker_compose_is_gone() -> None:
    """compose.workers.yaml 整个文件都是那三个 worker，不留。"""
    assert not (ROOT / "compose.workers.yaml").exists(), (
        "compose.workers.yaml 又出现了。那三个 worker 的 HTTP API 没有收藏枚举接口，"
        "接上去结果依然是 0——见 CONFLICT_ORDER.md 的 SUPERSEDED 表。"
    )


def test_worker_start_stop_scripts_are_gone() -> None:
    for name in ("start_workers.sh", "stop_workers.sh"):
        assert not (ROOT / "scripts" / name).exists(), f"scripts/{name} 又出现了"


def test_no_main_py_api_worker_definitions_anywhere() -> None:
    """不只看那一个文件——换个文件名把同样的东西加回来也要被抓住。

    判据打在**内容**上（`python main.py api` 这个启动形态），不是文件名上。
    """
    offenders = []
    for path in ROOT.rglob("*.y*ml"):
        if any(part in {".venv", "node_modules", ".git", "evidence"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # compose 里 command 是 YAML 列表，逐行写；所以按"main.py 紧跟 api"判
        if "main.py" in text and "- api" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"这些文件里又出现了 `python main.py api` 形态的 worker 定义：{offenders}。"
        "实测证伪：该 API 只暴露单篇详情，没有收藏枚举。"
    )


def test_guard_actually_reads_something() -> None:
    """判据自己的自检：上面那条 rglob 必须真的扫到过文件。

    扫到 0 份和"没问题"长得一模一样——这条把两者分开。
    （本机吃过这个亏不止一次：非递归 glob 读到 0 份，门却报绿。）
    """
    scanned = [
        p for p in ROOT.rglob("*.y*ml")
        if not any(part in {".venv", "node_modules", ".git", "evidence"} for part in p.parts)
    ]
    assert len(scanned) >= 3, f"守卫只扫到 {len(scanned)} 份 YAML，它大概没在查"


# ── 一次性配对码（v0.0.0.7 / T03）──────────────────────────────────
#
# CONFLICT_ORDER 废止它的理由：真实使用中连续失败三次，
# 十分钟有效期与手抄验证码本身就是技术门槛，与 INV-ZERO-BARRIER 直接冲突。
# 替代品是扩展长期可撤销令牌（POST /v1/auth/extension-token）。


def test_pairing_endpoints_are_gone() -> None:
    """判据打在**端点响应**上，不是打在源码 grep 上——
    源码里留个同名函数但没挂路由，grep 会报红而实际是好的；
    反过来换个名字挂回同样的路由，grep 会报绿而实际复活了。"""
    import importlib
    import os
    import tempfile

    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SOCIAL_ARCHIVE_DATA_ROOT"] = os.path.join(tmp, "data")
        import social_archive.api as api_module

        importlib.reload(api_module)
        client = TestClient(api_module.app)
        for path in ("/v1/pairing/status", "/v1/pair"):
            assert client.get(path).status_code == 404, f"{path} 又活了"
        assert client.post("/v1/pairing/exchange", json={"code": "X"}).status_code == 404


def test_pairing_helpers_are_gone_from_api_module() -> None:
    """上一条查端点，这条查实现——两者都要，单查一边都能被绕过。"""
    import social_archive.api as api_module

    for name in (
        "PairingRequest", "PairingRateLimiter", "require_pairing_edge",
        "_read_pairing_record", "_exchange_pairing_code", "_normalize_pairing_code",
        "PAIRING_PATHS", "PAIRING_STATE_FILENAME",
    ):
        assert not hasattr(api_module, name), f"api.{name} 还在——配对码链路没删干净"


def test_auth_switch_survived_the_deletion() -> None:
    """`settings.pairing_required` 名字里带 pairing，但它是**总鉴权开关**：
    require_token 第一行据此早退，什么都不校验。删配对码时把它一起删掉
    会静默关掉全站鉴权。这条守着它别被顺手删了。"""
    from social_archive.config import Settings

    assert hasattr(Settings, "__dataclass_fields__")
    assert "pairing_required" in Settings.__dataclass_fields__, (
        "pairing_required 被删了——它不是配对码开关，是总鉴权开关，"
        "删掉等于 require_token 永远早退，全站不再鉴权"
    )
