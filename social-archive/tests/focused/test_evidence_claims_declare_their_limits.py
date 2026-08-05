

def test_the_handoff_evidence_counts_match_reality() -> None:
    """交接表里写「见 TXX/ 下 N 份证据」，那个 N 必须是真的。

    2026-08-05：我刚把 T14 写成 8 份，实际是 11 份。**一个每次读都在
    撒谎的数字**，正是这一整天在清的那类东西（pre-commit 里那句
    「道数从产物里读，不写死」是同一条教训）。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    handoff = (root / "evidence/HANDOFF_v0007.md").read_text(encoding="utf-8")
    wrong = []
    for task, claimed in re.findall(r"见 `(T\d+)/` 下 (\d+) 份证据", handoff):
        actual = len(list((root / "evidence" / task).iterdir()))
        if int(claimed) != actual:
            wrong.append(f"{task}: 写着 {claimed} 份，实际 {actual} 份")
    assert not wrong, f"交接表里的证据份数对不上：{wrong}"


def test_the_handoff_open_item_count_matches_the_ledger() -> None:
    """交接开头写「证据里还挂着 N 条未完成项」，那个 N 也必须是真的。

    2026-08-05：它写着 17，`list_open_items.py` 数出来是 19——两条新的
    （磁盘那格多了一条、又加了「没有 CI 在生产那个 Python 上跑判据」）。

    **上面那条判据只管「TXX/ 下 N 份证据」，管不到这个数**，
    于是同一份文件里一个数字被钉住、另一个继续飘。
    这条把它一起钉上：数从台账现算，不从文档里抄。
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    handoff = (root / "evidence/HANDOFF_v0007.md").read_text(encoding="utf-8")
    claimed = re.search(r"证据里还挂着 (\d+) 条未完成项", handoff)
    assert claimed, "交接里那句「证据里还挂着 N 条未完成项」不见了——判据要跟着改"

    # **让台账自己去数，不在这里重抄一遍判定逻辑。**
    # 抄一份的话两边必然漂开，而漂开的时候这条判据会站在错的那边。
    # （它的计数写在 main() 里、没有可导入的函数，所以直接跑它读那一行。
    #   第一版我按 `module.collect(...)` 去调——**那个函数根本不存在，是我编的**。）
    import subprocess
    import sys as _sys
    out = subprocess.run([_sys.executable, str(root / "scripts/list_open_items.py")],
                         capture_output=True, text=True, cwd=root).stdout
    counted = re.search(r"未完成项：(\d+) 条", out)
    assert counted, f"台账没报出条数，判据没法比：{out[:200]}"
    assert int(claimed.group(1)) == int(counted.group(1)), (
        f"交接写着 {claimed.group(1)} 条未完成项，台账数出来是 {counted.group(1)} 条"
    )
