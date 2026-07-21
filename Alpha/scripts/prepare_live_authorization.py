#!/usr/bin/env python3
"""预签授权文件生成器(080 前置;owner 签字短语经会话明示后由运维落盘)。

规则:
- 一切常量(3000/0.6/5/US)写死为契约值——工具不接受放宽参数;
- policy/promotion 双哈希取自当前仓库文件,签后任何改动都会使授权失效(须重签);
- owner_signature 必须是 owner 亲自给出的短语,空/占位一律拒绝;
- 全绿自动激活(auto_activate_on_all_green=true)= 契约口径的"预签"。
用法:
    python3 scripts/prepare_live_authorization.py \
        --sign "<owner 在会话中亲口给出的授权短语>" --days 14 \
        --out runtime/LIVE_AUTHORIZATION.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.execution.gates import sha256_of_file, validate_authorization


def build(sign: str, days: int, signed_at: str) -> dict:
    return {
        "authorization_id": f"auth_{signed_at[:10].replace('-', '')}_micro_live",
        "owner": "Linze",
        "mode": "MICRO_LIVE",
        "capital": {
            "currency": "AUD",
            "max_managed_gross_exposure": 3000,
            "fat_finger_max_single_order_ratio": 0.6,
            "max_orders_per_hour": 5,
            "max_open_positions": None,
        },
        "markets": ["US_STOCK", "US_ETF"],
        "promotion_conditions": {
            "auto_activate_on_all_green": True,
            "strategy_promotion_config_hash": sha256_of_file("configs/strategy_promotion.yaml"),
        },
        "valid_from": signed_at,
        "valid_until": (datetime.fromisoformat(signed_at) + timedelta(days=days))
        .isoformat().replace("+00:00", "Z"),
        "policy_hash": sha256_of_file("configs/trading_governor_policy.yaml"),
        "owner_signature": sign,
        "signed_at": signed_at,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sign", required=True, help="owner 亲自给出的授权短语(不得代拟)")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default="runtime/LIVE_AUTHORIZATION.json")
    a = ap.parse_args()
    if not a.sign.strip() or "<" in a.sign:
        print("拒绝:签字短语为空或含占位符", file=sys.stderr)
        return 2

    signed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    auth = build(a.sign.strip(), a.days, signed_at)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(auth, ensure_ascii=False, indent=2))
    os.chmod(out, 0o600)

    ok, reasons = validate_authorization(
        out, policy_path="configs/trading_governor_policy.yaml",
        promotion_config_path="configs/strategy_promotion.yaml",
        now=datetime.now(timezone.utc))
    print(json.dumps({"written": str(out), "self_check_ok": ok, "reasons": reasons},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
