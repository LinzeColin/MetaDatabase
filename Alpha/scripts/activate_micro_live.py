#!/usr/bin/env python3
"""微实盘自动切换器(全链唯一有权改交易模式的组件;由 systemd 路径单元以 root 触发)。

触发:runtime/ACTIVATE_REQUEST.json 出现(只有每日复判在"四灯全绿+授权有效+
资金达标"三者同时成立时才会写它)。本脚本再独立复核一遍全部前提(纵深防御),
然后原子改写环境文件三键、重启交易进程、确认存活;任何一步不符 → 回滚+告警。
请求文件无论结果如何都会被归档移走,防止路径单元循环触发。

红线:不改任何契约常量;门禁矩阵(resolve_mode/validate_authorization)在
worker 启动时仍会独立把关——本脚本失败关闭,worker 也失败关闭,双保险。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUEST_MAX_AGE_SECONDS = 24 * 3600
LIVE_KEYS = ("ALPHA_MODE", "ALPHA_EXPECTED_ACC_ID", "LIVE_TRADING_ENABLED")


def set_env_keys(text: str, updates: dict[str, str]) -> str:
    """环境文件行级替换:已有键改值,缺键追加;注释与其余行原样保留。"""
    lines = text.splitlines()
    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if ("=" in stripped and not stripped.startswith("#")) else None
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    return "\n".join(out) + "\n"


def check_preconditions(*, request: dict, now: datetime, auth_ok: bool,
                        auth_reasons: list, live_flag: str, real_acc_id: str,
                        report_auto_promote: bool) -> tuple[bool, str]:
    """独立复核(与复判脚本互为纵深):任何一条不符都拒绝切换。"""
    try:
        requested_at = datetime.fromisoformat(request["requested_at"].replace("Z", "+00:00"))
    except Exception:
        return False, "请求文件缺 requested_at"
    if (now - requested_at).total_seconds() > REQUEST_MAX_AGE_SECONDS:
        return False, "切换请求已超过 24 小时,过期作废"
    if live_flag == "1":
        return False, "实盘总开关已经是 1,无需切换"
    if not real_acc_id:
        return False, "环境缺真实账户号配置(私密键),拒绝切换"
    if not report_auto_promote:
        return False, "复核报告非全绿(auto_promote 不为真)"
    if not auth_ok:
        return False, f"预签授权复核未过: {auth_reasons[:3]}"
    return True, "全部前提复核通过"


def main() -> int:
    check_only = "--check-only" in sys.argv
    repo = Path(__file__).resolve().parent.parent
    os.chdir(repo)
    now = datetime.now(timezone.utc)
    env_path = Path(os.environ.get("ALPHA_ENV_FILE", "/opt/alpha/env"))
    request_path = repo / "runtime/ACTIVATE_REQUEST.json"
    auth_path = Path(os.environ.get("ALPHA_AUTHORIZATION_PATH", "runtime/LIVE_AUTHORIZATION.json"))
    archive_dir = repo / "runtime"
    stamp = now.strftime("%Y%m%dT%H%M%SZ")

    def archive(result: dict) -> None:
        if request_path.exists() and not check_only:
            data = json.loads(request_path.read_text())
            data["_activation_result"] = result
            dest = archive_dir / f"ACTIVATE_ARCHIVED_{stamp}.json"
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            request_path.unlink()

    def email(event_type: str, text: str) -> None:
        if check_only:
            print(f"[check-only] 邮件({event_type}): {text[:80]}...")
            return
        try:
            from backend.app.notify.outbox import Outbox
            from backend.app.store.db import create_session_factory, init_engine
            ob = Outbox(create_session_factory(init_engine(os.environ["ALPHA_DATABASE_URL"])))
            ob.enqueue(event_type=event_type, payload={"text": text})
        except Exception as e:  # 邮件失败不阻断主流程,但要留痕
            print(f"邮件入队失败: {e}", file=sys.stderr)

    if not request_path.exists():
        print("无切换请求文件,退出(设计内:路径单元只应在文件出现时拉起本脚本)")
        return 0

    request = json.loads(request_path.read_text())
    report_dir = Path(request.get("report_dir", ""))
    report_auto = False
    try:
        report = json.loads((report_dir / "report.json").read_text())
        report_auto = bool(report.get("promotion", {}).get("auto_promote"))
    except Exception:
        report_auto = False

    from backend.app.execution.gates import validate_authorization
    auth_ok, auth_reasons = (False, ["授权文件不存在"])
    if auth_path.exists():
        auth_ok, auth_reasons = validate_authorization(
            auth_path, policy_path="configs/trading_governor_policy.yaml",
            promotion_config_path="configs/strategy_promotion.yaml", now=now)

    env_text = env_path.read_text()
    live_flag = "1" if any(line.strip() == "LIVE_TRADING_ENABLED=1" for line in env_text.splitlines()) else "0"
    real_acc = os.environ.get("ALPHA_REAL_ACC_ID", "").strip()

    ok, why = check_preconditions(
        request=request, now=now, auth_ok=auth_ok, auth_reasons=list(auth_reasons),
        live_flag=live_flag, real_acc_id=real_acc, report_auto_promote=report_auto)
    print(json.dumps({"check_only": check_only, "preconditions_ok": ok, "why": why},
                     ensure_ascii=False))
    if check_only:
        return 0
    if not ok:
        archive({"activated": False, "why": why, "at": now.isoformat()})
        email("ACTIVATION_BLOCKED",
              f"复判请求了实盘切换,但切换器复核未过:{why}。系统保持模拟盘,失败关闭。")
        return 1

    # ---- 执行切换(备份 → 原子改写 → 重启 → 存活确认;失败回滚) ----
    backup = env_path.with_name(f"env.bak.{stamp}")
    shutil.copy2(env_path, backup)
    os.chmod(backup, 0o600)
    new_text = set_env_keys(env_text, {
        "ALPHA_MODE": "MICRO_LIVE",
        "ALPHA_EXPECTED_ACC_ID": real_acc,
        "LIVE_TRADING_ENABLED": "1",
    })
    tmp = env_path.with_name("env.tmp")
    tmp.write_text(new_text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, env_path)

    subprocess.run(["systemctl", "restart", "alpha-trading-worker"], check=False, timeout=120)
    healthy = False
    for _ in range(10):
        time.sleep(3)
        r = subprocess.run(["systemctl", "is-active", "alpha-trading-worker"],
                           capture_output=True, text=True, timeout=30)
        healthy = r.stdout.strip() == "active"
        if not healthy:
            break
    if not healthy:
        os.replace(backup, env_path)
        subprocess.run(["systemctl", "restart", "alpha-trading-worker"], check=False, timeout=120)
        archive({"activated": False, "why": "切换后交易进程未能保持存活,已回滚到模拟盘", "at": now.isoformat()})
        email("ACTIVATION_BLOCKED",
              "已尝试切换微实盘,但交易进程启动自检未过(门禁矩阵失败关闭),"
              "环境已自动回滚到模拟盘并恢复运行。我会带着日志复盘后再试。")
        return 1

    archive({"activated": True, "at": now.isoformat()})
    email("LIVE_ACTIVATED",
          "四灯全绿+预签授权有效+资金达标,系统已自动切换到微实盘(MICRO_LIVE)。\n"
          "约束不变:总敞口上限 3000 澳元、单笔不超 60%、每小时不超 5 笔、仅美股。\n"
          "第一笔真实订单将出现在下一个评估窗口(每周二美股开盘后一小时内,或补评估窗口),"
          "下单前后你都会收到邮件;moomoo 应用里从此可以直接看到每笔真实订单和持仓。\n"
          "随时可停:回复邮件说停,或用你手里的控制令牌一键停机。")
    print("已切换微实盘并确认交易进程存活")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
