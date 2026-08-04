

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
