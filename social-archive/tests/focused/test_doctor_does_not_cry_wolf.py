"""诊断不能对着正确的状态喊 FAIL（v0.0.0.7）。

2026-08-04 在生产上跑 doctor.sh，秘密文件权限那一节打出 **16 个 FAIL**
——而那 16 个文件全都是**对的**：挂进容器的密钥必须是 0640，容器
（core 跑 uid 10001、cli-tools 跑 uid 10002 / gid 10001）只能靠组权限读。
这条不变量写在 prepare_systemd_host.sh:205，由 install.sh 落实。

**一个总是喊狼来了的诊断，用不了几次就会被人整段跳过。**

同一节还要永远提醒一件事：三份副本一把钥匙。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = ROOT / "scripts/doctor.sh"


def _code() -> str:
    return "\n".join(
        line for line in DOCTOR.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_mounted_secrets_are_allowed_to_be_group_readable() -> None:
    code = _code()
    assert "640|440)" in code, "挂进容器的密钥仍然会被判 FAIL——而那是它们必须的权限"
    assert "MOUNTED" in code, "没有区分「挂进容器的」和「仅宿主使用的」"


def test_the_mounted_list_comes_from_compose() -> None:
    """抄第二份必然漂开——instagram_session 就是那么被漏掉的。"""
    code = _code()
    block = code.split("MOUNTED=", 1)[1].split("PYMOUNTED\n)", 1)[0]
    assert "compose.yaml" in block, "挂载名单不是从 compose.yaml 读的"
    for name in ("instagram_session", "cli_worker_token", "notion_token"):
        assert f'"{name}"' not in block, f"{name} 被硬编码进了名单"


def test_host_only_secrets_still_must_not_be_group_readable() -> None:
    """放宽的只是挂进容器的那一类。仅宿主使用的仍然不该给组。"""
    code = _code()
    assert "600|400|0)" in code, "仅宿主使用的密钥的判据没了"


def test_it_always_warns_that_there_is_only_one_key() -> None:
    """三份副本，一把钥匙。产品无法验证你有没有在别处存过它——
    那正是它安全的原因——所以这一条不做通过/失败，只做永远提醒。"""
    text = DOCTOR.read_text(encoding="utf-8")
    assert "备份私钥" in text, "诊断里没有这一条"
    assert "一份也解不开" in text, "没有把后果说出来"
    assert "别把它放进任何一个对象仓" in text, "没有说清哪里**不能**存"
    # 不能做成 PASS/FAIL：产品验证不了。
    #
    # **窗口按结构切，不按字节数切。** 原来是「备份私钥」之后的 900 个字符，
    # 2026-08-05 给 doctor 加了三段新检查（保命 unit / 异地副本 / 主机 venv），
    # 它们合法地带着 PASS/FAIL，一落进那个 900 字窗口，这条判据就红了——
    # **而它要守的那件事一点没变**。固定字节窗口钉的是位置，不是事实；
    # 本会话已经在 JS 判据上栽过同一种。
    after = text.split("备份私钥", 1)[1]
    # 切到下一段小标题为止。标记里那个反斜杠是 shell 源码里的 `printf '\n…`，
    # 用 chr(92) 拼出来，免得在 Python 与 shell 两层转义里数错斜杠——
    # 第一版就数错了，切出来的窗口 3666 字符，整整包住了后面三段新检查。
    warning = after.split("printf '" + chr(92) + "n保命的 unit", 1)[0]
    assert "别把它放进任何一个对象仓" in warning, "切出来的窗口没盖住那条提醒本身"
    # **只看会被执行的行。** 判据要守的是「脚本不会给这一条打通过/失败」，
    # 而不是「附近的注释里不许出现 PASS 这个词」——注释里出现是完全正常的
    # （旁边那段就在讲「doctor 全绿 25 条 PASS 却看不见三件事」）。
    code = "\n".join(l for l in warning.splitlines() if not l.lstrip().startswith("#"))
    assert "PASS" not in code and "FAIL" not in code, (
        "把一件产品验证不了的事做成了通过/失败——那会变成又一个假的绿灯"
    )
