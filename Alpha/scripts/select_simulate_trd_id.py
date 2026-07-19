#!/usr/bin/env python3
"""部署日工具:向券商实查账户列表,把 SIMULATE 账户写入 env 的 ALPHA_EXPECTED_ACC_ID。

070 三日模拟盘必须绑 SIMULATE 账户(080 实盘另行由 owner 切换)。
不猜测:找不到或有歧义时如实报错退出,绝不默认。只改 env 该一行,其余不动。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.adapters.brokers.moomoo import build_real_opend_client


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="/opt/alpha/env")
    ap.add_argument("--trd-env", default="SIMULATE", choices=["SIMULATE", "REAL"])
    a = ap.parse_args()

    client = build_real_opend_client()
    try:
        rows = client.get_acc_list()
    finally:
        client.close()

    print("账户列表(券商实查):")
    for r in rows:
        print(f"  acc_id={r['acc_id']} trd_env={r['trd_env']} acc_type={r['acc_type']} status={r['status']}")

    matches = [r for r in rows if str(r["trd_env"]).upper() == a.trd_env]
    if not matches:
        print(f"FAIL: 无 {a.trd_env} 账户", file=sys.stderr)
        return 2
    if len(matches) > 1:
        cash = [r for r in matches if "CASH" in str(r["acc_type"]).upper()]
        if len(cash) == 1:
            matches = cash
        else:
            print(f"FAIL: {a.trd_env} 账户有 {len(matches)} 个且无法唯一定位,请 owner 指定", file=sys.stderr)
            return 3
    chosen = matches[0]["acc_id"]

    path = a.env_file
    lines = open(path, encoding="utf-8").read().splitlines()
    out, hit = [], False
    for ln in lines:
        if ln.startswith("ALPHA_EXPECTED_ACC_ID="):
            out.append(f"ALPHA_EXPECTED_ACC_ID={chosen}")
            hit = True
        else:
            out.append(ln)
    if not hit:
        out.append(f"ALPHA_EXPECTED_ACC_ID={chosen}")
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"已写入 ALPHA_EXPECTED_ACC_ID={chosen}({a.trd_env})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
