"""改风控配置的**唯一正确姿势**(二次部署门 #22)。

2026-07-28 事故:把单笔比例 60%→90% 只改了配置文件,忘了重签授权 →
policy_hash 失配 → build_live_cycle 抛错 → 交易静默空转 10 小时,而页面显示"正常运行中"。
失败关闭本身是对的,**缺的是配套动作**。本脚本把那套动作变成一条不可漏步的命令。

流程(任一步失败即回滚配置,绝不留下"配置改了但授权没跟上"的死锁态):
  1. 备份当前配置
  2. 改配置(单笔比例 / 总敞口 / 每小时笔数)
  3. **用 owner 原话重签授权**(必须由 owner 提供,脚本绝不代拟)
  4. 校验授权对新配置有效
  5. 重启交易进程(可选 --restart,需在部署机上)
  6. 复验心跳模式确实回到 MICRO_LIVE 且未空转

用法:
    python scripts/change_risk_policy.py --ratio 0.9 --sign "<owner 原话>" --restart
    python scripts/change_risk_policy.py --check     # 只体检:配置与授权是否一致
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

POLICY = Path("configs/trading_governor_policy.yaml")
AUTH = Path("runtime/LIVE_AUTHORIZATION.json")


def consistency_report() -> tuple[bool, list[str]]:
    """体检:权威配置 ↔ 授权记录 ↔ 风控引擎缺省,三者是否一致。"""
    import backend.app.truth as truth
    from backend.app.execution.gates import validate_authorization
    truth._policy.cache_clear()

    problems: list[str] = []
    ratio = truth.fat_finger_ratio()
    cap = truth.capital_aud()

    ok_auth, reasons = validate_authorization(
        AUTH, policy_path=str(POLICY),
        promotion_config_path="configs/strategy_promotion.yaml",
        now=datetime.now(timezone.utc)) if AUTH.exists() else (False, ["授权文件不存在"])
    if not ok_auth:
        problems.append(f"授权对当前配置无效:{list(reasons)[:2]}")

    # 风控引擎缺省必须等于权威值(此前两者各写一遍,漏改即出事)
    from decimal import Decimal

    from backend.app.risk.engine import RiskContext
    got = RiskContext(side="BUY", symbol="X", market="US_ETF", quantity=1,
                      price_usd=Decimal("1"), fx_usd_aud=Decimal("1.5"),
                      now=datetime.now(timezone.utc),
                      current_gross_exposure_aud=Decimal("0"),
                      pending_buy_reserved_aud=Decimal("0"), quote_age_seconds=1.0,
                      jurisdiction_verdict="ALLOW", recent_order_times=[]).fat_finger_ratio
    if float(got) != ratio:
        problems.append(f"风控引擎缺省 {got} ≠ 权威配置 {ratio}")

    print(f"  单笔比例(权威)= {ratio}   总敞口 = {cap} 澳元")
    print(f"  单笔上限       = {truth.single_order_cap_usd():.2f} 美元")
    print(f"  授权有效       = {ok_auth}")
    return (not problems), problems


def _set_ratio(new_ratio: float) -> None:
    import re
    text = POLICY.read_text()
    new = re.sub(r"(fat_finger_max_single_order_ratio:\s*)[0-9.]+",
                 rf"\g<1>{new_ratio}", text, count=1)
    if new == text:
        raise RuntimeError("未在配置中找到 fat_finger_max_single_order_ratio")
    POLICY.write_text(new)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=float, help="新的单笔比例(0-1)")
    ap.add_argument("--sign", help="owner 原话签字(重签授权必需;脚本绝不代拟)")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--restart", action="store_true", help="改完重启交易进程并复验")
    ap.add_argument("--check", action="store_true", help="只体检不改动")
    a = ap.parse_args()

    if a.check or a.ratio is None:
        ok, problems = consistency_report()
        for p in problems:
            print(f"  ❌ {p}")
        print("  ✅ 配置/授权/引擎三者一致" if ok else "  ⚠️ 存在不一致,交易可能已被门禁卡住")
        return 0 if ok else 1

    if not a.sign or not a.sign.strip() or "<" in a.sign:
        print("拒绝:改风控必须同时重签授权,而签字短语只能由 owner 给出(--sign)。",
              file=sys.stderr)
        return 2
    if not (0 < a.ratio <= 1):
        print("拒绝:单笔比例必须在 (0,1] 之间", file=sys.stderr)
        return 2

    backup = POLICY.with_suffix(f".yaml.bak.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    shutil.copy2(POLICY, backup)
    print(f"1) 已备份配置 → {backup.name}")
    try:
        _set_ratio(a.ratio)
        print(f"2) 单笔比例已改为 {a.ratio}")

        rc = subprocess.run([sys.executable, "scripts/prepare_live_authorization.py",
                             "--sign", a.sign, "--days", str(a.days)],
                            capture_output=True, text=True, timeout=120)
        if rc.returncode != 0:
            raise RuntimeError(f"重签授权失败:{rc.stdout[-300:]}{rc.stderr[-300:]}")
        print("3) 授权已用 owner 原话重签")

        ok, problems = consistency_report()
        if not ok:
            raise RuntimeError(f"一致性校验未过:{problems}")
        print("4) 配置/授权/引擎一致性校验通过")
    except Exception as exc:
        shutil.copy2(backup, POLICY)
        print(f"❌ 失败已回滚配置:{exc}", file=sys.stderr)
        return 1

    if a.restart:
        subprocess.run(["sudo", "systemctl", "restart", "alpha-trading-worker"], timeout=120)
        print("5) 交易进程已重启,等待心跳…")
        time.sleep(35)
        try:
            from backend.app.store.db import create_session_factory, init_engine
            from backend.app.workers.heartbeat import HeartbeatStore
            detail = str(HeartbeatStore(create_session_factory(init_engine()))
                         .snapshot().get("trading-worker", {}).get("detail", ""))
            good = "MICRO_LIVE" in detail and "BLOCKED_ON_OPEND" not in detail
            print(f"6) 心跳复验:{'✅ 已回到微实盘且未空转' if good else '❌ ' + detail[:120]}")
            if not good:
                return 1
        except Exception as exc:
            print(f"6) 心跳复验失败:{exc}", file=sys.stderr)
            return 1
    else:
        print("⚠️ 未加 --restart:配置与授权已一致,但**交易进程仍在用旧配置**,记得重启并复验。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
