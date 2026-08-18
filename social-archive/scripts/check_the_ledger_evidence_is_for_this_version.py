#!/usr/bin/env python3
r"""验收台账引的那几份证据，是不是这一版的、而且还产得出来（2026-08-14）。

## 它修的是什么

2026-08-14 查出：`evidence/G5/DEPLOYED_AND_READ_BACK.json` —— 四条验收判据里
**第 4 条「上线并回读」的全部证据** —— 停在 `expected_version: 0.0.0.22`，
时间 `2026-08-07T04:34:44`。七天前、79 个版本前的一次实测，标着 PASS。

根因不是有人忘了跑，是**没有任何东西会跑它**：

    $ grep -n verify_production_deployment scripts/deploy_to_production.sh
    45:# 然后**一定要跑一次完整回读**（scripts/verify_production_deployment.py 与
    46:# scripts/check_production_matches_the_repo.py）——被打断的部署最容易留下

**唯一一次出现，在一条注释里。** 注释写着「一定要跑」，而没有一行代码跑它。
这个仓已经为这个形状付过账：「注释声称的守卫不是守卫」「判据没有调用方就不算做完」。

## 口径

真源是 `evidence/LEDGER_CITATIONS.json`（台账原件在 `~/.claude/` 里，仓外，
随本机消失；那份是它在仓里的副本）。对每一条引用核四件事：

1. **文件在、非空、解得开、status 是 PASS、problems 为空**
2. **带 `expected_version` 的必须等于当前 VERSION**
   —— 这一档是「对生产的实测」，会随版本变。
   确定性判据（对静态表、对文档）输出逐字节不变，**不能拿提交日期判它们新旧**：
   2026-08-14 实测三份旧日期的重跑之后一个字节没变，旧日期只意味着「此后没变过」。
3. **产出者存在，而且源码里真的写着那个输出名**
4. **产出者从部署脚本可达** —— 直接调，或经 `run_all_drills.py` 这类调度器间接调。
   查可达性时**先剥掉注释**：不剥的话，正是上面那条注释会让这道判据自己空过。

## 边界

只读。不跑任何产出者、不改任何证据。它只回答「台账引的东西，现在还成不成立」。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CITATIONS = ROOT / "evidence/LEDGER_CITATIONS.json"
DEPLOY = ROOT / "scripts/deploy_to_production.sh"

GOOD_STATUS = {"PASS", "OK", "ok", "pass"}


def _strip_comments(path: Path) -> str:
    """剥掉注释再看。

    **不剥就会空过**：`deploy_to_production.sh` 第 45 行的注释里写着
    `scripts/verify_production_deployment.py`，一个只搜字符串的判据会认为
    「它被调了」——而那正是这道判据要抓的那个缺陷本身。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        # Python 的说明也在字符串里（docstring），用 ast 一并剥掉
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc:
                        text = text.replace(doc, "")
        except SyntaxError:
            pass
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _invoked_by(path: Path) -> set[str]:
    """`path` **真的会去跑**哪些脚本——不是「提到过哪些」。

    第一版写的是「剥掉注释后出现过这个名字」，实测把 156 个脚本里的 134 个
    算成可达，于是 `verify_production_deployment.py` 也「可达」了——
    因为 `check_production_matches_the_repo.py` 在一句错误消息里提了它的名字。
    **「被提到」不是「被调用」**，那样量出来的可达性一片绿，什么也没守住。

    现在按调用位置认：
      · .sh —— 名字前面得有个解释器（`python3` / `.venv/bin/python` / `bash` / `sh`）
      · .py —— 名字得是**模块级清单里的字符串**（`DRILLS = [...]`，
                `run_all_drills.py` 就是这么列演练的），或者
                `subprocess.run/Popen/check_call/check_output` 的实参。
                消息文本里的同名字符串不算。
    """
    if not path.exists():
        return set()
    found: set[str] = set()

    if path.suffix == ".sh":
        code = _strip_comments(path)
        for name in re.findall(
                r'(?:python3?|\.venv/bin/python\S*|bash|sh)\s+(?:\S*/)?([A-Za-z0-9_]+\.(?:py|sh))',
                code):
            found.add(name)
        return found

    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return found

    def strings_under(node: ast.AST) -> list[str]:
        return [child.value for child in ast.walk(node)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)]

    for node in ast.walk(tree):
        # DRILLS = ["a_drill.py", ["b_drill.py", "--platform", "x"], …]
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
            for text_value in strings_under(node.value):
                if text_value.endswith((".py", ".sh")):
                    found.add(Path(text_value).name)
        # subprocess.run([...])
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in {"run", "Popen", "check_call", "check_output"}:
                for text_value in strings_under(node):
                    if text_value.endswith((".py", ".sh")):
                        found.add(Path(text_value).name)
    return found


def _reachable_from_deploy() -> set[str]:
    """从部署脚本出发，闭包展开「它真的会跑到的脚本」。

    部署不直接列每个演练——它调 `run_all_drills.py`，那里面才是清单。
    所以要传递地展开，否则每个演练都会被误判成「没人调」。
    """
    seen: set[str] = set()
    frontier = [DEPLOY]
    while frontier:
        current = frontier.pop()
        for name in _invoked_by(current):
            if name in seen:
                continue
            seen.add(name)
            candidate = ROOT / "scripts" / name
            if candidate.exists():
                frontier.append(candidate)
    return seen


def pinned_is_current(data: dict, version: str) -> bool:
    """这份证据钉的就是当前这一版（也就是说它是**刚跑的**，不是陈的）。"""
    pinned = data.get("expected_version")
    return pinned is None or str(pinned) == str(version)

def _previous_version(current: str) -> str | None:
    """CHANGELOG 里紧挨着 `current` 的那一版。

    **不做数值推算**（把 102 减成 101）——版本号不一定连续，跳号时推算会
    悄悄多容忍一版。这里只认「CHANGELOG 里排在它下面那一条」，
    找不到 current 就返回 None（于是一律走严格分支）。
    """
    heads = re.findall(r"^## v([0-9][0-9.]*)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    if current not in heads:
        return None
    index = heads.index(current)
    return heads[index + 1] if index + 1 < len(heads) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    book = json.loads(CITATIONS.read_text(encoding="utf-8"))
    producers = book.get("producers") or {}
    reachable = _reachable_from_deploy()

    problems: list[str] = []
    warnings: list[str] = []
    checked = 0
    per_file: dict[str, dict] = {}

    for gate, block in (book.get("criteria") or {}).items():
        for rel in block.get("evidence") or []:
            checked += 1
            path = ROOT / rel
            note: dict[str, object] = {"criterion": gate}
            per_file[rel] = note

            if not path.exists() or path.stat().st_size == 0:
                problems.append(f"{gate} 引的 {rel} 不在或是空的")
                note["ok"] = False
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                problems.append(f"{gate} 引的 {rel} 解不开：{error}")
                note["ok"] = False
                continue

            status = data.get("status")
            note["status"] = status

            # **「生产还没升到这一版」不是证据坏了，是这次部署还没跑。**（2026-08-18）
            #
            # 对生产的实测只能由部署本身刷新，而部署第 0 步要这道门先绿 ——
            # 2026-08-18 实测：0.0.0.106 卡死在这里，唯一能让它变绿的动作
            # 就是那次被它挡住的部署。
            #
            # 判据不看措辞，看**数据**：这份证据自己记着它量到的生产版本。
            # 那个版本恰好是 CHANGELOG 里紧邻的上一版时，这份 FAIL 的全部内容
            # 就是「生产是上一版」——本次部署跑完它自然会变。**再红一次没有信息量。**
            # 生产停在更早的版本（真的没部署成）照样红，因为那不是紧邻的上一版。
            live = ((data.get("measured_from_production") or {}).get("health") or {}).get("version")
            pending_deploy = (
                pinned_is_current(data, version)
                and live is not None
                and str(live) == str(_previous_version(version) or "")
            )
            note["pending_deploy"] = bool(pending_deploy)

            if status not in GOOD_STATUS and not pending_deploy:
                problems.append(f"{gate} 引的 {rel} status={status!r}，不是通过")
            elif status not in GOOD_STATUS:
                warnings.append(
                    f"{gate} 引的 {rel} status={status!r}，而它量到的生产版本是 {live}"
                    f"（CHANGELOG 里紧邻的上一版）——**本次部署跑完才会变**。"
                    f"部署结束后它仍然是 {status!r}，就是真的没部署成。")

            if data.get("problems") and not pending_deploy:
                problems.append(f"{gate} 引的 {rel} 自己带着 {len(data['problems'])} 条 problems")

            pinned = data.get("expected_version")
            note["expected_version"] = pinned
            if pinned is not None and pinned != version:
                # **升版当下这一刻，差一版是结构性的，不是陈旧。**（2026-08-17）
                #
                # 这类证据是**对生产的实测**，只能由部署跑完才刷新。而部署第 0 步
                # 又要这道门先绿 —— 于是「改 VERSION → 部署」被自己锁死：
                # 2026-08-17 实测，0.0.0.101→102 那次部署在第 0 步就停住，
                # 而唯一能让它变绿的动作就是那次部署本身。
                #
                # 所以只容忍**恰好上一版**（CHANGELOG 里紧邻的那一条），
                # 并且明说它在途中。原来那个「停在 79 个版本前还标 PASS」的病
                # 照样会红 —— 那不是紧邻的上一版。
                if pinned == _previous_version(version):
                    note["pending_this_deploy"] = True
                    warnings.append(
                        f"{gate} 引的 {rel} 钉在上一版 {pinned}（当前 {version}）——"
                        "这份是对生产的实测，**本次部署跑完才会刷新**。"
                        f"部署结束后它仍然停在 {pinned} 的话，就是真的没刷新。")
                else:
                    problems.append(
                        f"{gate} 引的 {rel} 钉在 {pinned}，而当前是 {version}——"
                        "它是对生产的实测，钉在旧版就等于在给另一版背书")

            producer = producers.get(rel)
            note["producer"] = producer
            if not producer:
                problems.append(f"{rel} 没登记产出者——不知道它该由谁刷新")
                continue
            script = ROOT / producer
            if not script.exists():
                problems.append(f"{rel} 登记的产出者 {producer} 不存在")
                continue
            stem = re.sub(r"_(reddit|instagram|douyin|xiaohongshu|kuaishou|x|youtube)$", "",
                          Path(rel).name[: -len(".json")])
            # **剥掉注释和文档字符串再找。** 不剥的话，一个只是在说明里提到
            # 这个输出名的脚本也算"产出者"——这道判据自己的 docstring 就提了
            # `DEPLOYED_AND_READ_BACK`，于是拿它当反例时判据不红（实测）。
            # 「我写来解释修复的那句注释把判据废掉」，这个仓当天已经第六次。
            if stem not in _strip_comments(script):
                problems.append(f"{producer} 源码里没有 {stem}——登记的产出者对不上")
            name = Path(producer).name
            note["reachable_from_deploy"] = name in reachable
            if name not in reachable:
                problems.append(
                    f"{producer} 从部署脚本**够不到**（剥掉注释之后）——"
                    f"没有任何东西会刷新 {rel}，它只会冻在最后一次手跑那版")

    # **空扫要当失败。** 引用一条都没读到，说明台账副本坏了或路径变了，
    # 不是「没问题」。
    if checked == 0:
        problems.append("一条引用都没核到——LEDGER_CITATIONS.json 坏了或空了")

    verdict = {
        "version": version,
        "citations_checked": checked,
        "scripts_reachable_from_deploy": len(reachable),
        "per_file": per_file,
        "problems": problems,
        "warnings": warnings,
        "status": "FAIL" if problems else "PASS",
    }
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    elif problems:
        print(f"✗ 台账引的证据有 {len(problems)} 处对不上（当前 {version}）：")
        for one in problems:
            print(f"    {one}")
    else:
        print(f"✓ 台账引的 {checked} 份证据都对得上（当前 {version}），"
              f"且每一份的产出者都从部署脚本够得到")
        # **警告要印出来，不能只塞进 JSON。** 印不出来的警告等于没有。
        for one in warnings:
            print(f"    ⚠️  {one}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
