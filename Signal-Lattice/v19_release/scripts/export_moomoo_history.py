#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _provider():
    try:
        import moomoo as provider  # type: ignore
    except ImportError:
        import futu as provider  # type: ignore
    return provider


def export_history(
    codes: list[str],
    *,
    host: str,
    port: int,
    start: str,
    end: str,
) -> dict[str, Any]:
    provider = _provider()
    context = provider.OpenQuoteContext(host=host, port=port)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        for code in codes:
            page_req_key = None
            while True:
                ret, data, page_req_key = context.request_history_kline(
                    code,
                    start=start,
                    end=end,
                    ktype=provider.KLType.K_DAY,
                    autype=provider.AuType.QFQ,
                    max_count=1000,
                    page_req_key=page_req_key,
                )
                if ret != provider.RET_OK:
                    failures.append({"code": code, "error": str(data)})
                    break
                for record in data.to_dict("records"):
                    rows.append({
                        "date": str(record.get("time_key", ""))[:10],
                        "symbol": str(record.get("code", code)),
                        "open": float(record.get("open", 0.0)),
                        "high": float(record.get("high", 0.0)),
                        "low": float(record.get("low", 0.0)),
                        "close": float(record.get("close", 0.0)),
                        "volume": float(record.get("volume", 0.0)),
                    })
                if not page_req_key:
                    break
    finally:
        context.close()
    rows.sort(key=lambda row: (row["date"], row["symbol"]))
    return {
        "source": "MooMoo OpenD read-only history kline",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "start": start,
        "end": end,
        "codes": codes,
        "prices": rows,
        "failures": failures,
        "automatic_trading": False,
        "trade_context_opened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = export_history(
        args.codes,
        host=args.host,
        port=args.port,
        start=args.start,
        end=args.end,
    )
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "PASS" if payload["prices"] and not payload["failures"] else "PARTIAL",
        "rows": len(payload["prices"]),
        "failures": payload["failures"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))
    return 0 if payload["prices"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
