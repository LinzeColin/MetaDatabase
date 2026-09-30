"""python -m signal_lattice.evidence collect --db X.sqlite --cache-dir DIR --cik 874866 [--cik ...] [--ticker CRVL]"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .collector import collect_company
from .factstore import FactStore
from .sec_client import SecClient


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="signal_lattice.evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="采集若干公司的 submissions + companyfacts 入库")
    collect.add_argument("--db", required=True, type=Path)
    collect.add_argument("--cache-dir", required=True, type=Path)
    collect.add_argument("--cik", type=int, action="append", default=[])
    collect.add_argument("--ticker", action="append", default=[])
    args = parser.parse_args(argv)

    client = SecClient(args.cache_dir)
    store = FactStore(args.db)
    ciks = list(args.cik)
    if args.ticker:
        by_ticker = {row["ticker"].upper(): int(row["cik"]) for row in client.company_tickers_exchange()}
        store.upsert_listed(client.company_tickers_exchange(), date.today())
        ciks += [by_ticker[t.upper()] for t in args.ticker]
    for cik in ciks:
        print(json.dumps(collect_company(client, store, cik), ensure_ascii=False))
    print("SEC requests sent: %d (304 cache hits: %d)" % (client.requests_sent, client.cache_hits_304))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
