r"""出事的时候东西拿不拿得回来，有人每次部署都真去试吗（2026-08-11）。

## 这道门为什么在

`docs/DRILLS.md` 里三个恢复演练写着「定期」，而**「定期」没有闹钟**：
部署脚本里那三个脚本名出现 0 次。别的演练答的是**功能对不对**，
这三个答的是**东西还在不在、拿不拿得回来**——最贵的一格，没有任何自动触发。

生产上第一次真跑，当场量出这个演练自己的两个毛病，两个都是**假绿**：

    远端那份不见了      → 抛 botocore 回溯，stdout 上没有结构化结果
    一个空的合法 SQLite → 照样 PASS（`_counts` 把缺的表悄悄省掉键）

第二条不是假想：同一天生产上就躺着一个 0 字节的同名运行库。

下面测的是**判据本身**（`judge`）和**它有没有调用方**。
真跑那一路（下载 → 解密 → 打开）在生产机上，证据落
`evidence/G3/RESTORE_FROM_BACKUP.json`。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "scripts/restore_runtime_db_drill.py"
CHECK = ROOT / "scripts/check_the_backup_can_actually_be_restored.py"


def _judge():
    """直接从演练里取那个判据函数——测的是它跑的那一份，不是手抄。"""
    source = DRILL.read_text(encoding="utf-8")
    start = source.index("COMPARED_TABLES = ")
    end = source.index("def main(")
    namespace: dict = {}
    exec(compile(source[start:end], str(DRILL), "exec"), namespace)  # noqa: S102
    return namespace["judge"]


LIVE = {"content": 193, "user_relation": 194, "artifact": 552,
        "object_replica": 1656, "destination_receipt": 391}


def test_a_healthy_snapshot_passes() -> None:
    """正对照：快照比线上少几行是正常的，不该报。"""
    restored = dict(LIVE, content=191)
    assert _judge()(restored, LIVE) == []


def test_an_empty_but_valid_database_is_caught() -> None:
    """**这一条是这次修的主角。**

    解密出来是个合法 SQLite、打得开、一条内容都没有——原来报 PASS。
    生产上真躺着一个 0 字节的同名运行库，备份对着它拍一张就是这个形状。
    """
    problems = _judge()(dict(LIVE, content=0), LIVE)
    assert problems, "空库被判成了「取回来了」"
    assert "一条内容都没有" in problems[0]


def test_a_missing_table_is_caught() -> None:
    """缺表原来是**悄悄少一个键**，下游只把字典打印出来。"""
    restored = dict(LIVE, artifact=None)
    problems = _judge()(restored, LIVE)
    assert any("artifact" in p for p in problems), "缺了一张表，判据没说话"


def test_a_snapshot_that_lost_half_its_rows_is_caught() -> None:
    """快照天然会比线上少几行；少一半以上不是「这十几分钟写的」。"""
    assert _judge()(dict(LIVE, artifact=200), LIVE), "少了 64% 的行，判据没说话"
    assert _judge()(dict(LIVE, artifact=551), LIVE) == [], "少一行就报，那是噪声不是信号"


def test_live_counts_unavailable_does_not_turn_into_a_pass() -> None:
    """线上库读不到的时候，**空字典不许被读成「都对得上」**。

    `empty-default-swallows-unknown`：这个仓吃过太多次这个亏。
    比不了就比不了，但「一条内容都没有」这条仍然必须成立。
    """
    assert _judge()(dict(LIVE, content=0), {}), "线上读不到时，空库居然过了"


def test_the_deploy_actually_runs_it() -> None:
    """**没有调用方的判据不算判据。**（这个仓第七批同形状的缺陷）"""
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    name = CHECK.name
    assert name in deploy, f"部署脚本没有调 {name}——恢复这件事又回到「靠人记得」"
    step = deploy[deploy.index(name):]
    nxt = step.find('\nstep "')
    step = step[:nxt] if nxt > 0 else step
    assert "fail " in step, "它红了不中止部署，等于没验"
    assert "| tail" not in step and "| head" not in step, "别把成败接进管道"


def test_the_checker_never_handles_key_material() -> None:
    """凭据由 systemd 发；这个脚本只经手**路径**，不读、不传、不打印内容。"""
    source = CHECK.read_text(encoding="utf-8")
    assert "LoadCredential=" in source, "凭据不走 systemd，就是自己经手密钥了"
    for leak in ("read_text()", "open(SECRETS", "cat /opt/social-archive/runtime/secrets"):
        assert leak not in source, f"它在读密钥文件本身：{leak}"


def test_the_third_copy_is_reported_as_unreachable_not_as_green() -> None:
    """GitHub 那份至今取不回（令牌看不见那个仓，只有 Owner 能授权）。

    **跳过不许伪装成绿**——这个仓的规矩。
    """
    source = CHECK.read_text(encoding="utf-8")
    assert "不算通过" in source or "不是「通过」" in source, (
        "第三份取不回来，而文案没说清它不算通过")


def _caller_gate():
    spec = importlib.util.spec_from_file_location(
        "drill_caller_gate", ROOT / "scripts/check_every_drill_has_a_caller.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_a_we_do_not_run_this_table_does_not_count_as_a_caller() -> None:
    """**这道门自己的假绿**（2026-08-11 实测）。

    `check_every_drill_has_a_caller.py` 跟一层调用链、然后做子串命中。
    而 `run_all_drills.py` 里有一张 `NEEDS_REAL_INPUT`，登记的是**它明确跳过**的演练——
    于是三个恢复演练靠着「我不跑它」这句话，满足了「有人调它」。

    发现它不是靠读代码：把部署里那一步删掉，门居然照样绿。
    """
    declared = _caller_gate()._declared_not_run(
        'NEEDS_REAL_INPUT = {\n    "some_drill.py": "本机没有远端凭据，这里跑不了",\n}\n')
    assert "some_drill.py" in declared


def test_the_real_run_all_drills_still_declares_what_it_skips() -> None:
    """对着**真文件**测，不对着我编的夹具测（`fixtures-cleaner-than-the-real-thing`）。"""
    source = (ROOT / "scripts/run_all_drills.py").read_text(encoding="utf-8")
    declared = _caller_gate()._declared_not_run(source)
    assert "disaster_recovery_drill.py" in declared, (
        "那张「我不跑它」的表变了形状——门会重新把散文命中当成调用方")


def test_prose_that_merely_mentions_a_drill_is_not_a_caller() -> None:
    """注释里提到名字也不该算——那正是这次的病根。"""
    declared = _caller_gate()._declared_not_run(
        '# 这里说到 mentioned_drill.py，只是散文\nDRILLS = ["real_drill.py"]\n')
    assert declared == [], "把散文/真调用表也当成了「不跑」声明，射程反了"


def test_the_registry_no_longer_calls_it_a_manual_drill() -> None:
    """清单里那一行要跟着现实走，否则下一个人照着它以为还得手动跑。"""
    registry = (ROOT / "docs/DRILLS.md").read_text(encoding="utf-8")
    row = next(line for line in registry.splitlines()
               if "`restore_runtime_db_drill.py`" in line and line.startswith("|"))
    assert "每次发布" in row, "清单还写着「定期」，而它已经接进部署了"
    assert "8.69" in row, "没写清它挂在哪一步，出问题时找不到人"
