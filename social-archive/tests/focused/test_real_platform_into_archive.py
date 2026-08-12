r"""一个真平台的收藏，真的进到档案馆里（2026-08-12）。

## 这道门为什么在

Owner 那句话的第一条是「**至少一个真实平台的收藏能自动读进档案馆**」。
仓里两个演练各证一半，而**没有一个把两半接起来**：

    bilibili_acquisition_drill   打 B 站真接口，全文 0 次 POST——读到的东西哪儿也没去
    from_zero_drill              整条链走通，而它连的是仓里自己写的假站

两个都绿，合起来仍然答不了那句话。下面这几条盯的是**新那个演练没被悄悄削弱**。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "scripts/real_platform_into_archive_drill.py"


def test_it_reads_the_extension_s_own_reader_not_a_copy() -> None:
    """取数必须用插件里那一份，否则测的是我另抄的一份（`fixtures-cleaner-than-the-real-thing`）。"""
    source = DRILL.read_text(encoding="utf-8")
    assert 'require("./apps/browser-extension/content/bilibili-reader.js")' in source
    assert "readFolder" in source


def test_it_ingests_through_the_real_endpoint() -> None:
    """入库必须走 background.js 送条目的同一条路。"""
    source = DRILL.read_text(encoding="utf-8")
    assert "/v1/captures/batch" in source, "换了别的入口，就不再证明产品那条路通"
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "/v1/captures/batch" in background, "插件不再走这条路了——这个演练的前提变了"


def test_it_never_touches_his_own_library() -> None:
    """**他的库一个字节都不能动。** 档案馆必须起在一次性容器的 tmpfs 上。"""
    source = DRILL.read_text(encoding="utf-8")
    assert "--tmpfs" in source, "档案馆不起在 tmpfs 上，就有碰到他那份库的可能"
    assert "docker rm -f" in source, "跑完不收容器，下一次会撞名字"
    assert "SOCIAL_ARCHIVE_DATA_ROOT=/var/lib/social-archive" in source, (
        "数据根没被指到容器内——这条边界是这个演练敢跑在生产机上的全部理由")
    # **光靠隔离的写法不够，要量。**（2026-08-12）
    # 这条边界原来只写在散文里：演练**声称**碰不到他的库，而从没数过。
    # `self-report-is-not-evidence`——能出示的就要出示。现在跑前跑后各数一次。
    assert "his_library_count" in source, "不再数他的库了——那句「没动」又变回自述"
    assert "他的库被动了" in source, "数了却不判红，等于没数"


def test_it_compares_titles_not_just_counts() -> None:
    """只比条数的话，进去 5 条空壳也算过。"""
    source = DRILL.read_text(encoding="utf-8")
    assert "missing_titles" in source, "没有比标题——「进去了几条」证明不了「进去的是那几条」"


def test_it_states_the_one_platform_boundary() -> None:
    """只证明 bilibili 一个平台；别让它读起来像「多平台都验过了」。"""
    source = DRILL.read_text(encoding="utf-8")
    assert "只证明 bilibili 这一个平台" in source


def test_the_deploy_actually_runs_it() -> None:
    """**没有调用方的判据不算判据。**

    Owner 那句话的第一条就靠这一步兑现——它不在部署里，就等于又回到
    「两个演练各证一半」的状态。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert DRILL.name in deploy, f"部署没调 {DRILL.name}——真平台那条链又没人验了"
    step = deploy[deploy.index(DRILL.name):]
    nxt = step.find('\nstep "')
    step = step[:nxt] if nxt > 0 else step
    assert "fail " in step, "它红了不中止部署，等于没验"
    assert "| tail" not in step and "| head" not in step, "别把成败接进管道"
