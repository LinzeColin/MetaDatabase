#!/usr/bin/env python3
"""ALPHA-LIVE-050 真实数据回测运行入口。

用法: .venv/bin/python scripts/run_backtest.py [--no-cache]
输出: reports/backtest/<end>/report.json + report_hash.txt,并打印判定摘要。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.backtest.runner import run_full


def main() -> int:
    use_cache = "--no-cache" not in sys.argv
    report = run_full(
        start=date(2014, 1, 1),
        end=date(2026, 7, 16),
        capital_aud=3000.0,
        use_cache=use_cache,
    )
    print(json.dumps({
        "s1_oos": report["s1"]["oos_metrics"],
        "s2_oos": report["s2"]["oos_metrics"],
        "s2_skipped_infeasible": report["s2"]["oos_skipped_infeasible"],
        "combined_oos": report["combined"]["oos_metrics"],
        "promo1": report["combined"]["promo1"],
        "report_sha256": report["report_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
