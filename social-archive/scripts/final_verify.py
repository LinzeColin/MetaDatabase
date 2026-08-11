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
        # 同一类：文档安静地说一个不成立的事实。2026-08-05 数了一遍全仓的版本号，
        # README 第 1 行说 v0.0.0.6、AGENTS.md 第 9 行说 v0.0.0.6——**而 AGENTS.md
        # 是接手的 agent 读的那一份**，每一个后来的人都会被它告知一个错的版本；
        # CHANGELOG 最新一节停在 v0.0.0.4，v5/v6/v7 三版一条都没有。
        # 改版本时代码里那几处会因为跑不起来被发现，文档里这几处不会。
        [python, "scripts/check_the_stated_version_is_the_real_one.py"],
        # 上一道管的是「各处写的版本号一不一致」。**这一道管的是「版本号配不配得上那份插件」**：
        # 2026-08-11 查账发现 VERSION 停在 0.0.0.41 期间真部署了 11 次。
        # 这次侥幸没出事（那段时间 apps/browser-extension/ 零提交），而出事的样子这个仓记过：
        # 一天发 6 个不同的扩展包全标 v0.0.0.22。真因就在 extension-install.html 里——
        # `compareVersions(installed, requiredVersion) < 0`，**只比版本号字符串**：
        # 字节变了而字符串没变，那一页就对他说「✓ 已是最新」并把他送回去。
        [python, "scripts/check_one_version_means_one_package.py"],
        # 同一个平台散在十几张表里，而「我以为查全了又冒出一张」在 youtube 一个
        # 平台上就发生了四次——最狠的一次是 options.js 的 platformOrder 没有它，
        # **设置页不出卡片，交接里让 Owner 点的那个按钮根本不存在**。
        # 这道门不靠人记得有几张表：一行里出现三个以上平台名就当它是平台表，
        # 逐张问「可托管的平台都在里面吗」，有意的子集必须登记并写下理由。
        [python, "scripts/check_every_platform_table_is_complete.py"],
        # 加目的地和加平台是同一个形状，而它一直没有对应的门。
        # 2026-08-06 实测：加一个 brandnewdest，1020 条判据全过、23 道门全绿，
        # 而用户会在「自动导出」那张面板上看到一个没有名字的 id。
        [python, "scripts/check_every_destination_table_is_complete.py"],
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
        # 反方向：**界面在调一条服务端没有的接口**。
        # 2026-08-06 抓到的：「批量修改分类」打 POST /v1/library/classify，
        # 而那条路由不存在，实测 405——那颗按钮从来没成功过一次，
        # 而 1000 多条判据、23 道门没有一个看得见。
        [python, "scripts/find_client_calls_to_routes_that_do_not_exist.py"],
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
        # 上面那道只管 src/ 的 SOCIAL_ARCHIVE_* 环境变量，够不着扩展的
        # chrome.storage 配置。2026-08-05 实测：showFloatingButton 默认 true
        # 而全仓没人写它——那颗浮动按钮出现在每个已授权页面上，用户关不掉。
        [python, "scripts/find_extension_settings_with_no_way_to_set_them.py"],
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
        # 第八种：**同一件事在四个地方各说各的**（v0.0.0.7 / G2）。
        # 「这个平台能不能同步」写在服务端两张表、扩展的取数缝隙、
        # 以及扩展的扫描范围表里；任意两处漂开，用户拿到的都是同一样东西——
        # 一颗结构上不可能成功的按钮。上面那道 find_affordances 问的是
        # 「界面画的按钮服务端认不认」，这一道问的是
        # 「服务端认了的，扩展里真的有实现吗」——**两个方向**。
        [python, "scripts/check_sync_promises_match_reality.py"],
        # 「按形状读」那条路上的平台，有没有演练真走过（2026-08-11）。
        # 抖音 / 快手在生产上走它，而演练一次都没走过——两张表在两个文件里，
        # 此前没有任何东西把它们对过。上一道问「说的和写的一不一致」，
        # 这一道问「真的有人走过吗」。
        [python, "scripts/check_shape_read_platforms_have_drills.py"],
        # **建好了，但没有任何东西调得到它**（v0.0.0.22 / G2）。
        # 这一类已经栽过五次，最近一次是 Instagram 的连接按钮被 Cookie 托管吃掉：
        # 今天能跑通的那条路从界面上够不着。写测试防不住——要防的恰恰是
        # 「我没想到要为它写测试」，所以反过来枚举每个函数和每种消息问「谁调它」。
        [python, "scripts/check_no_mechanism_is_unreachable.py"],
        # **演练没有调用方，就等于没有演练**（v0.0.0.22 / G3）。
        # 2026-08-06 查了一遍：15 个演练，调用方 0——全靠人记得去跑。
        # 代价当场看到：十一个真 Chrome 演练全都加载源码目录、且加载前把
        # 可选权限提成必给权限，于是"他真正下载的那个包在权限未授予时会怎样"
        # 从没被走过；第一次真跑就抓到一句指错方向的失败文案。
        [python, "scripts/check_every_drill_has_a_caller.py"],
        # **git 钩子会把 GIT_DIR 塞进环境，子进程于是去问那个仓**（2026-08-07）。
        # 一天之内踩了三次，症状都是「单独跑绿、pre-commit 里红」；仓里更早
        # 已经为同一件事栽过一次，教训写在测试里——**写下来没有用，得有人拦**。
        # 最坏的一种不是红，是静悄悄读了另一个仓：数出得来，只是错的。
        # 当场抓到两处存量的，其中一处是明文凭据扫描器——它靠 git ls-files
        # 决定扫哪些文件，环境脏了它会去扫别的仓然后报「0 处命中」。
        [python, "scripts/check_git_calls_cannot_be_hijacked_by_hooks.py"],
        # 第九种：**说明书开始骗人**（v0.0.0.7 / G4）。
        # 这个仓已经有过一模一样的教训：CONNECT_IS_CLICKABLE_TODAY 里写过一句
        # 详细的操作路径，然后发现没有任何界面读那个字段——写完就是隐形的。
        # 一份没人核对的使用说明是同一类东西：写的时候对，改一次代码就开始骗人，
        # 而**读它的人是 Owner，他没有别的办法发现自己被骗了**。
        [python, "scripts/check_the_guide_matches_the_product.py"],
        # 使用说明改了却忘了重生成产品里那一页 → 他看到的是上一版。
        [python, "scripts/build_guide_page.py", "--check"],
        # 第十种：**界面上写死的「哪些平台能干什么」**（v0.0.0.15）。
        # 2026-08-06 一天之内同一个缺陷在三处被逐个撞见，每次都是打开那个
        # 真实界面看一眼才发现的——判据全绿、演练全绿、发布门全绿。
        # 三处写法一样：一句写死的散文，说的却是会变的事实。
        # 上面那道 check_the_guide 管的是**说明书**，这一道管的是**界面本身**。
        [python, "scripts/find_hardcoded_platform_claims.py"],
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
