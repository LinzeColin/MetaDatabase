r"""验收台账引的证据，必须是这一版的、而且还产得出来（2026-08-14）。

## 它修的是什么

`evidence/G5/DEPLOYED_AND_READ_BACK.json` —— 四条验收判据里**第 4 条
「上线并回读」的全部证据** —— 停在 `expected_version: 0.0.0.22`、
`time: 2026-08-07T04:34:44`。线上那时跑的是 0.0.0.101，隔了 79 个版本。它标着 PASS。

根因不是有人忘了跑，是**没有任何东西会跑它**：

    $ grep -n verify_production_deployment scripts/deploy_to_production.sh
    45:# 然后**一定要跑一次完整回读**（scripts/verify_production_deployment.py 与 …

唯一一次出现在一条注释里。「注释声称的守卫不是守卫」＋「判据没有调用方就不算做完」。
同一次排查还查出另外三份同病（G2 两份、G4 一份）——G1/G3 那几份没冻住，
是因为 `run_all_drills` 顺带刷新了它们，**那是运气不是设计**。

## 这里为什么要焊反例

写这道判据时第一版就坏了，而且**是绿着坏的**：可达性我按「剥掉注释后出现过
这个名字」算，结果 156 个脚本里 134 个算成可达——`verify_production_deployment.py`
也「可达」，因为另一个脚本在一句错误消息里提了它的名字。
**「被提到」不是「被调用」。** 改成只认调用位置之后降到 51 个，当场报出 4 处真缺陷。

所以下面每一条都配一个必须红的反例，其中一条专门盯这个：
消息文本里的同名字符串不许算可达。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_the_ledger_evidence_is_for_this_version.py"
CITATIONS = ROOT / "evidence/LEDGER_CITATIONS.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("ledger_checker", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run() -> tuple[int, dict]:
    done = subprocess.run([sys.executable, str(CHECKER), "--json"],
                          capture_output=True, text=True, check=False, cwd=ROOT)
    try:
        return done.returncode, json.loads(done.stdout)
    except json.JSONDecodeError:
        return done.returncode, {"_stdout": done.stdout, "_stderr": done.stderr}


def test_现在是绿的_而且真核到了东西() -> None:
    code, payload = _run()
    assert code == 0, f"台账引的证据现在就对不上：{json.dumps(payload, ensure_ascii=False)[:900]}"
    # **空扫要当失败**：核了 0 条也会 rc=0 地"通过"，那是这个仓栽过很多次的形状。
    assert payload["citations_checked"] >= 9, payload
    assert payload["problems"] == [], payload


def test_被提到不算被调用(tmp_path: Path) -> None:
    """**这是第一版判据坏掉的那个形状，专门钉住。**

    只在一句消息文本里出现的脚本名，不许算成"部署会跑它"。
    """
    module = _load_module()

    mentions_only = tmp_path / "mentions_only.py"
    mentions_only.write_text(
        'def main():\n'
        '    print("忘了跑 verify_production_deployment.py 就会留下旧证据")\n'
        '    raise SystemExit("请先跑 some_other_drill.py")\n',
        encoding="utf-8")
    found = module._invoked_by(mentions_only)
    assert "verify_production_deployment.py" not in found, (
        f"消息文本里的脚本名被算成调用了：{found}——"
        "这正是第一版把 134/156 个脚本算成可达的原因")
    assert "some_other_drill.py" not in found, found

    really_runs = tmp_path / "really_runs.py"
    really_runs.write_text(
        'import subprocess\n'
        'DRILLS = ["a_drill.py", ["b_drill.py", "--platform", "x"]]\n'
        'def main():\n'
        '    subprocess.run(["python3", "c_drill.py"])\n',
        encoding="utf-8")
    found = module._invoked_by(really_runs)
    for name in ("a_drill.py", "b_drill.py", "c_drill.py"):
        assert name in found, f"真在跑的 {name} 没被认出来：{found}"


def test_钉在旧版本的实测必须红(tmp_path: Path) -> None:
    """反例：把 G5 那份的 expected_version 改成旧的，判据必须红。

    这就是 2026-08-14 真实发生过的状态。
    """
    target = ROOT / "evidence/G5/DEPLOYED_AND_READ_BACK.json"
    original = target.read_text(encoding="utf-8")
    data = json.loads(original)
    assert data.get("expected_version"), "这份证据本来就该钉着版本号，夹具前提没了"
    data["expected_version"] = "0.0.0.22"
    try:
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # **先确认反例真的落盘了**（这个仓有过"反例根本没生效，3 passed 是假绿"）
        assert json.loads(target.read_text(encoding="utf-8"))["expected_version"] == "0.0.0.22"
        code, payload = _run()
        assert code == 1, f"证据钉在 0.0.0.22 而判据没红：{json.dumps(payload, ensure_ascii=False)[:600]}"
        assert any("0.0.0.22" in one for one in payload["problems"]), payload
    finally:
        target.write_text(original, encoding="utf-8")
    # **复原要复原干净**——这个仓栽过"试验台只复原了一半"
    assert target.read_text(encoding="utf-8") == original
    assert _run()[0] == 0, "复原之后判据没回到绿——夹具把仓改脏了"


def test_证据不在了必须红(tmp_path: Path) -> None:
    """反例：把一条引用指到一个不存在的文件。"""
    original = CITATIONS.read_text(encoding="utf-8")
    book = json.loads(original)
    book["criteria"]["G5"]["evidence"] = ["evidence/G5/THIS_DOES_NOT_EXIST.json"]
    try:
        CITATIONS.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = _run()
        assert code == 1, f"引了一个不存在的证据而判据没红：{payload}"
        assert any("不在或是空的" in one for one in payload["problems"]), payload
    finally:
        CITATIONS.write_text(original, encoding="utf-8")
    assert CITATIONS.read_text(encoding="utf-8") == original
    assert _run()[0] == 0


def test_产出者够不到就必须红() -> None:
    """反例：把某条引用的产出者改成一个部署不会跑的脚本。

    这是原缺陷的形状——脚本存在、写着那个输出名，**只是没人调它**。
    """
    original = CITATIONS.read_text(encoding="utf-8")
    book = json.loads(original)

    # **反例的脚本要现算，不能写死。**（第一版就栽在这儿）
    # 我随手挑了 `check_the_ledger_evidence_is_for_this_version.py` 当"没人调的脚本"，
    # 而那一刻它刚被我接进部署第 8.95 步——**真的可达**，于是判据不红，
    # 我差点把这读成"判据坏了"。挑一个此刻真的够不到的。
    module = _load_module()
    reachable = module._reachable_from_deploy()
    candidates = sorted(p.name for p in (ROOT / "scripts").glob("*.py")
                        if p.name not in reachable)
    assert candidates, "scripts 下每个脚本都被部署调到了？那这条反例造不出来，改判据"
    orphan = f"scripts/{candidates[0]}"
    book["producers"]["evidence/G5/DEPLOYED_AND_READ_BACK.json"] = orphan
    try:
        CITATIONS.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = _run()
        assert code == 1, f"产出者对不上而判据没红：{payload}"
        assert any("够不到" in one or "对不上" in one for one in payload["problems"]), payload
    finally:
        CITATIONS.write_text(original, encoding="utf-8")
    assert _run()[0] == 0


def test_台账副本本身要在仓里() -> None:
    """**原件在 `~/.claude/` 里，那是仓外。**

    这个仓栽过「写在 `~/.claude/` 里的教训进不了交付包」——
    随本机消失，接手的人看不见。所以引用关系必须有一份在仓里。
    """
    assert CITATIONS.exists(), f"{CITATIONS} 不在——台账引什么就没人知道了"
    book = json.loads(CITATIONS.read_text(encoding="utf-8"))
    assert set(book["criteria"]) == {"G1", "G2", "G3", "G4", "G5"}, book["criteria"].keys()
    cited = [one for block in book["criteria"].values() for one in block["evidence"]]
    assert len(cited) == 9, f"引用条数变了（{len(cited)}）——台账改了就把这份副本一起改"
    # 每条引用都要登记产出者，否则"谁来刷新它"没人知道
    missing = [one for one in cited if one not in book["producers"]]
    assert not missing, f"这几条没登记产出者：{missing}"
