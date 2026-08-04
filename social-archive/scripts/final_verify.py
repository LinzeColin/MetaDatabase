from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> dict[str, object]:
    completed = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-5000:],
        "stderr": completed.stderr[-5000:],
    }


def structural_commands() -> list[list[str]]:
    """Checks that are safe after SA-507's single frozen full-suite run.

    The Task Pack deliberately puts the only application-suite command before
    this script.  Re-running pytest here would make a green final verifier
    ambiguous: it could no longer prove which candidate the one permitted
    full-suite result belongs to.
    """

    python = sys.executable
    return [
        [python, "-B", "-m", "compileall", "-q", "src", "scripts"],
        [python, "scripts/check_brand.py"],
        [python, "scripts/secret_scan.py", "."],
        [python, "scripts/validate_compose.py", "compose.yaml"],
        [python, "scripts/validate_compose.py", "compose.readers.yaml"],
        # compose.workers.yaml 已随 v0.0.0.7 / T03 删除（那三个 HTTP worker 被实测证伪，
        # 上游 API 没有任何收藏枚举接口）。这一行留着会让**发布门本身**永远 FAIL——
        # 而且从 T03 起就是红的，只是没人跑它，所以一直没被发现。
        [python, "scripts/validate_systemd.py"],
        # v0.0.0.7 新增的三道门。不挂进来的话，它们只在有人手动敲 pytest 时才生效。
        [python, "scripts/preflight_extension.py"],
        [python, "scripts/scan_plaintext_credentials.py", "--all"],
        # 「建好了没接上」在本会话出现了**五次**（失败文案词典、静默零审计、
        # 扩展的 lastResult、凭据托管、多租户审计）。每一次都是模块写完、
        # 判据全绿，然后才发现没有人在调它。判据证明「函数写得对」，
        # 不证明「有人在调」。这道门把第六次挡在发布之前。
        [python, "scripts/find_unwired_code.py"],
        # 文档里最要命的一句，是**出事那天才会被人读到的那一句**。运维手册第 14 行
        # 让人跑 `scripts/restore.sh`——那一天再发现脚本不在，是最坏的时机。
        # 这道门把文档里出现的 scripts/xxx 逐个去磁盘上找一遍。
        [python, "scripts/check_docs_point_at_things_that_exist.py"],
        # 失败码 → 中文句子是**人手维护**的映射表，新加一个码没人提醒你补词典。
        # 补漏的后果不是少一句话，是界面说「我们没能记录下原因」而原因就在代码里。
        # 这道门第一次跑就找出 24 个说不出人话的码。
        [python, "scripts/check_every_failure_code_is_explainable.py"],
        # INV-HONEST-EVIDENCE 的机器落点。清点各不变量的守卫时发现
        # TRUTH-TRACEABLE / REAL-USABLE / HONEST-EVIDENCE **三条一个判据都没有**，
        # 只活在文档里。这道门管住其中可机器查的那条：
        # 每份证据要写「这不能证明什么」，自锁的 BLOCKED 不许被改写成 PASS。
        [python, "scripts/check_evidence_declares_its_limits.py"],
        # find_unwired_code 把带装饰器的函数当「框架注册」放过——对路由函数是对的，
        # 但因此看不见另一半：路由注册了、服务端能响应，而**没有任何客户端请求它**。
        # 这道门第一次跑就找出 /v1/storage/status 从来没被界面调过。
        [python, "scripts/find_endpoints_no_client_calls.py"],
        # 文档教用户点的按钮，界面上必须真有。手工扫了三次、三次都找出真问题
        # （连接中心改名、安装/连接两步指着不存在的按钮、教用户点 T03 已删的
        # 「读取当前列表」）。照旧文档操作的人会以为是自己错了，而**没有任何
        # 东西会报错**——这类缺陷比代码 bug 更难被发现。
        [python, "scripts/check_docs_match_the_ui.py"],
        # 「建好了没接上」的第三种形态：往 chrome.storage 写了状态，
        # 而没有任何界面读它。前两道门（未引用符号、无客户端接口）都看不见它。
        # 这道门第一次跑就抓到 saAccountSyncQueueLastResult 写三处、读零处
        # ——那正是我为「放弃时也要说得出原因」补的记录，写进了没人看的地方。
        [python, "scripts/find_write_only_storage_keys.py"],
        # 第四种形态：扩展内部的消息只有一头。有人听没人发（功能在代码上完整、
        # 在产品上够不着），或有人发没人听（消息落进虚空，发送处 catch 掉，
        # 连报错都没有）。这道门第一次跑就抓到 SA_REVOKE_PLATFORM_SESSION——
        # 而连接成功时产品**当着用户面许诺**「随时可以一键撤销」。
        [python, "scripts/find_messages_with_only_one_end.py"],
        # 第五种：代码读一个配置项，而 .env.example / compose / 部署脚本 / 文档
        # 一处都没有它——**没有任何文档化的路径能把它设上**。第一次跑就抓到
        # X / Reddit / Instagram 账号扫描要的六项全在这个状态：Owner 把该做的
        # 全做对了，这三个平台仍然一条都取不到，而没有任何东西告诉他还差什么。
        [python, "scripts/find_settings_with_no_way_to_set_them.py"],
        # 第六种，也是最直接的一种：**函数压根不存在**。node --check 只查语法
        # 不查标识符，判据也测不到（没人在 Node 里真跑那个 IIFE），
        # 只有用户点到那颗按钮的一刻才会炸。这道门是我自己刚犯完这个错才加的。
        [python, "scripts/find_calls_to_functions_that_do_not_exist.py"],
        # 第七种，也是最贵的一种：代码全都接上了，**它对用户说了做不到的事**。
        # 前六道门全绿、614 条判据全过的时候，界面正在让 Owner
        # 一遍遍重试一件结构上不可能成功的事。它们证明的是「函数写得对」
        # 「接口有人调」「文案能落到一句中文」——**没有一条在问
        # 「这颗按钮点下去会发生它承诺的事吗」**。这道门补的就是那一问。
        [python, "scripts/find_affordances_the_backend_says_cannot_work.py"],
        [python, "scripts/validate_deployment_contract.py"],
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Social Archive final structural verification.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="explicitly run pytest; do not use this during the SA-507 single-suite release run",
    )
    parser.add_argument(
        "--report",
        default=None,
        help=(
            "把报告写到别处，而不是 evidence/final-verification.json。"
            "部署脚本用它：部署的第 0 道门要求工作树干净，而它自己跑一次发布门就会"
            "改写那份报告（里面有生成时间，每次都不同）——**于是上一次部署把下一次挡在门外**。"
            "一个自己会把自己挡住的门，用不了几次就会有人绕过去，那时它连真的脏改动也挡不住。"
        ),
    )
    args = parser.parse_args(argv)
    commands = structural_commands()
    suite_mode = "structural"
    if args.full:
        commands.append([sys.executable, "-m", "pytest", "-q"])
        suite_mode = "explicit_full"

    results = [run(command) for command in commands]
    status = "PASS" if all(int(result["exit_code"]) == 0 for result in results) else "FAIL"

    # **「跳过」不是「通过」。**
    #
    # 有的门在环境不全时只做一半：validate_compose 在缺 .env 时
    # 「跳过 Docker Compose 渲染」，然后照样以 PASS 开头、退出 0。
    # 单看它自己的输出还算诚实（那句话就写在里面），但 14 道门聚合成一个
    # "PASS" 打印出来之后，这件事就彻底看不见了——而我每轮都是看那一个
    # PASS 来判断能不能提交的。
    #
    # 这里不改那些门的退出码（缺 .env 在开发机上是常态，让它红没有意义），
    # 只是把「哪几道其实只查了一半」明说出来，并记进产物。
    skipped = []
    for result in results:
        blob = f"{result.get('stdout', '')}{result.get('stderr', '')}"
        if any(marker in blob for marker in ("跳过", "未检查", "SKIP", "skipped")):
            skipped.append({
                "argv": result.get("argv", [])[-2:],
                "why": " ".join(blob.split())[:160],
            })

    report = {
        "status": status,
        "suite_mode": suite_mode,
        "application_suite_rerun": bool(args.full),
        "partial_checks": skipped,
        "results": results,
    }
    output = Path(args.report) if args.report else ROOT / "evidence/final-verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(status)
    if skipped:
        print(f"注意：{len(skipped)} 道门只查了一半（环境不全时的降级），它们**不是完整通过**：")
        for item in skipped:
            print(f"  · {' '.join(item['argv'])} —— {item['why'][:100]}")
        # 说清楚怎么让它们完整跑，否则「降级」就成了一句永远没人处理的告警。
        # 实测：本机装了 docker（Compose v5.3.1），缺的只是 install.sh 会创建的
        # .env 与 runtime/secrets/*.env。补上之后 validate_compose 就真的会去
        # 跑 `docker compose config`，而不是只做结构检查。
        print("  ↳ 让它们完整跑：在本工作树跑一次 `bash scripts/install.sh`"
              "（它会创建 .env 与 runtime/secrets/ 下的 env 文件）。")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
