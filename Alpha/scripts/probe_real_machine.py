#!/usr/bin/env python3
"""真机辖区探针(部署日运行;默认不在 CI 跑)。

用法(云主机,OpenD 已常驻、环境文件已就位):
    ALPHA_EXPECTED_ACC_ID=... python3 scripts/probe_real_machine.py

安全边界:只读——本脚本进程内永不解锁交易、永不下单。
本机没有 SDK/凭据时如实报错退出,不产生任何伪造证据。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.adapters.brokers.moomoo import MoomooReadOnlyAdapter, build_real_opend_client
from backend.app.adapters.brokers.probe import run_probe_and_persist
from backend.app.store.db import create_session_factory, init_engine


def main() -> int:
    acc_id = os.environ.get("ALPHA_EXPECTED_ACC_ID", "")
    if not acc_id:
        print("缺 ALPHA_EXPECTED_ACC_ID(只从环境读取,永不进 Git)", file=sys.stderr)
        return 2
    client = build_real_opend_client()  # SDK 缺失/桥接未联调会在此如实抛错
    adapter = MoomooReadOnlyAdapter(client, expected_acc_id=acc_id)
    adapter.connect()
    evidence = adapter.collect_probe_evidence()
    engine = init_engine()  # ALPHA_DATABASE_URL 或本地 SQLite
    result = run_probe_and_persist(
        evidence,
        create_session_factory(engine),
        account_principal=os.environ.get("ALPHA_ACCOUNT_PRINCIPAL", "owner"),
        location=os.environ.get("ALPHA_ACCOUNT_LOCATION", "AU"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "ALLOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
