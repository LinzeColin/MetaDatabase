"""发布门对作者提的要求，得写在人看得到的地方（v0.0.0.7 / T18）。

## 为什么有这份判据

2026-08-05：我因为「直角引号只给界面词」这条约定被拦了三次，
去查才发现**它哪儿都没写**——只有那道门自己的 docstring 说了它为什么存在，
而那没告诉写文档的人该怎么写。

顺手数了一遍：发布门 22 道，其中 6 道是**对写东西的人提要求**的，
`AGENTS.md` 和 `docs/` 里**一条都没有**。也就是说每个人都得先被拦一次
才知道规矩，而被拦住的那一刻往往是最赶时间的时候。

**规矩藏在门里，和没有规矩差不多。**
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
FINAL_VERIFY = (ROOT / "scripts/final_verify.py").read_text(encoding="utf-8")

# 这几道门红的时候，作者需要知道一条**他本可以事先遵守**的规矩。
# 其余 find_* 那些查的是「建好了没接上」，红了就是真有东西没接上，
# 不需要作者记住什么，所以不在这张表里。
AUTHOR_FACING = (
    "check_docs_match_the_ui.py",
    "check_docs_point_at_things_that_exist.py",
    "check_evidence_declares_its_limits.py",
    "check_every_failure_code_is_explainable.py",
    "check_every_platform_table_is_complete.py",
    "check_the_stated_version_is_the_real_one.py",
)


def test_every_author_facing_gate_is_explained_in_agents_md() -> None:
    """**规矩藏在门里，和没有规矩差不多。**"""
    missing = [gate for gate in AUTHOR_FACING if gate not in AGENTS]
    assert not missing, (
        f"这几道门会拦住作者，而 AGENTS.md 里没写它们要求什么：{missing}"
    )


def test_those_gates_still_exist_and_still_run() -> None:
    """反过来：AGENTS.md 里写着的门，必须真的还在发布门里跑。

    否则那张表会慢慢变成一份**关于已经不存在的规矩**的说明书。
    """
    code = "\n".join(line for line in FINAL_VERIFY.splitlines()
                     if not line.strip().startswith("#"))
    for gate in AUTHOR_FACING:
        assert (ROOT / "scripts" / gate).is_file(), f"{gate} 不在了，而 AGENTS.md 还写着它"
        assert gate in code, f"{gate} 已经不在发布门里跑了，而 AGENTS.md 还写着它"


def test_the_rule_itself_is_stated_not_just_the_gate_name() -> None:
    """只列门的名字没有用——**作者要的是「我该怎么写」**。"""
    for phrase in ("这不能证明什么", "直角引号", "pyproject.toml"):
        assert phrase in AGENTS, f"AGENTS.md 里没说清这条规矩：{phrase}"
