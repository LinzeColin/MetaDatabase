"""事件航图专用的 SQLite 库（events.sqlite）：申报索引、Form 4 买入、内部人买入历史、8-K 事项、股数。

与 factstore.py 分开：这里的表只服务事件采集，避免和事实库的表结构互相牵制。
所有读取都带 as_of，只返回 filed <= as_of 的行（时点正确）。
"""

from __future__ import annotations

import gzip
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

SCHEMA = """
CREATE TABLE IF NOT EXISTS filings (
    cik        INTEGER NOT NULL,
    accession  TEXT    NOT NULL,
    form       TEXT    NOT NULL,
    filed      TEXT    NOT NULL,          -- YYYY-MM-DD，EDGAR 索引上的申报日
    company    TEXT    NOT NULL,
    PRIMARY KEY (cik, accession)
);
CREATE INDEX IF NOT EXISTS filings_form ON filings (form, filed);
CREATE INDEX IF NOT EXISTS filings_cik ON filings (cik, form, filed);

-- 来自 submissions：8-K 事项、主文档名、受理时刻
CREATE TABLE IF NOT EXISTS filing_meta (
    accession        TEXT PRIMARY KEY,
    cik              INTEGER NOT NULL,
    form             TEXT NOT NULL,
    filed            TEXT NOT NULL,
    accepted_at      TEXT,
    report_date      TEXT,
    items            TEXT,
    primary_document TEXT
);
CREATE INDEX IF NOT EXISTS filing_meta_cik ON filing_meta (cik, form, filed);

-- 每份 Form 4 原文只抓一次；状态记下来，重跑不重复抓
CREATE TABLE IF NOT EXISTS form4_fetch (
    accession  TEXT PRIMARY KEY,
    status     TEXT NOT NULL,            -- OK / NOT_FOUND / PARSE_ERROR / FETCH_ERROR
    fetched_at TEXT NOT NULL
);
-- 含 P 交易的 Form 4 原文（gzip）留档，便于复核；不含 P 的不存
CREATE TABLE IF NOT EXISTS form4_raw (
    accession TEXT PRIMARY KEY,
    body_gz   BLOB NOT NULL
);

-- 一份申报 × 一位内部人 一行：该内部人在这份申报里的公开市场买入合计
CREATE TABLE IF NOT EXISTS form4_buys (
    accession       TEXT    NOT NULL,
    owner_cik       INTEGER NOT NULL,
    issuer_cik      INTEGER NOT NULL,
    symbol          TEXT,
    owner_name      TEXT,
    role            TEXT,
    filed           TEXT    NOT NULL,
    accepted_at     TEXT,
    first_trade     TEXT    NOT NULL,
    last_trade      TEXT    NOT NULL,
    shares          REAL    NOT NULL,
    amount_usd      REAL    NOT NULL,
    plan_10b5_1     INTEGER NOT NULL,     -- 1：整份或全部 P 行属于 10b5-1 计划
    indirect        INTEGER NOT NULL,
    PRIMARY KEY (accession, owner_cik)
);
CREATE INDEX IF NOT EXISTS form4_buys_issuer ON form4_buys (issuer_cik, filed);

-- 全市场内部人 P 买入历史（DERA 内部人数据集 + 原文），只用于判断「例行买入者」
CREATE TABLE IF NOT EXISTS insider_p (
    accession  TEXT    NOT NULL,
    owner_cik  INTEGER NOT NULL,
    issuer_cik INTEGER NOT NULL,
    trade_date TEXT    NOT NULL,
    filed      TEXT    NOT NULL,
    shares     REAL,
    price      REAL,
    source     TEXT    NOT NULL,
    PRIMARY KEY (accession, owner_cik, trade_date, shares, price)
);
CREATE INDEX IF NOT EXISTS insider_p_owner ON insider_p (owner_cik, trade_date);
CREATE INDEX IF NOT EXISTS insider_p_issuer_day ON insider_p (issuer_cik, trade_date, price);
-- 每位内部人最早一次出现在 Form 3/4/5 的申报日（判断「历史不足 3 年」）
CREATE TABLE IF NOT EXISTS owner_first (
    owner_cik   INTEGER PRIMARY KEY,
    first_filed TEXT NOT NULL,
    source      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_loaded (
    name TEXT PRIMARY KEY,
    rows INTEGER NOT NULL,
    loaded_at TEXT NOT NULL
);

-- 424B5 招股说明书文本分类（ATM / 增发 / 其他），只抓主文档头部
CREATE TABLE IF NOT EXISTS prospectus_class (
    accession  TEXT PRIMARY KEY,
    label      TEXT NOT NULL,            -- ATM / EQUITY_OFFERING / OTHER_PROSPECTUS / UNVERIFIED
    checked_at TEXT NOT NULL
);

-- 股数（dei 封面流通股）：frames 取回，按封面日入账
CREATE TABLE IF NOT EXISTS shares_obs (
    cik       INTEGER NOT NULL,
    cover_end TEXT    NOT NULL,
    shares    REAL    NOT NULL,
    accession TEXT    NOT NULL,
    PRIMARY KEY (cik, cover_end, accession)
);
"""

DateLike = Union[str, date, datetime]


def iso(value: DateLike) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    date.fromisoformat(str(value))
    return str(value)


class EventStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=60)
        self.db.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")  # 采集进程写入时，分析进程可以同时读
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._offering_cache: dict = {}

    def close(self) -> None:
        self.db.close()

    # ---- 写入 -------------------------------------------------------------
    def add_filings(self, rows: Iterable) -> int:
        before = self.db.total_changes
        self.db.executemany(
            "INSERT OR IGNORE INTO filings (cik, accession, form, filed, company) VALUES (?,?,?,?,?)",
            [(r.cik, r.accession, r.form, r.filed, r.company) for r in rows])
        self.db.commit()
        return self.db.total_changes - before

    def add_submissions(self, cik: int, payload: dict, extra_pages: Sequence[dict] = ()) -> int:
        """submissions（含 filings.files 里的历史分页）里的申报清单，取 8-K 事项与受理时刻。"""
        blocks = [(payload.get("filings") or {}).get("recent") or {}] + [dict(page) for page in extra_pages]
        before = self.db.total_changes
        for block in blocks:
            accessions = block.get("accessionNumber") or []

            def col(key, i):
                values = block.get(key) or []
                return values[i] if i < len(values) else None

            for i, accession in enumerate(accessions):
                form, filed = col("form", i), col("filingDate", i)
                if not form or not filed:
                    continue
                self.db.execute(
                    "INSERT OR IGNORE INTO filing_meta (accession, cik, form, filed, accepted_at, report_date, items, primary_document) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (accession, int(cik), form, filed, col("acceptanceDateTime", i), col("reportDate", i) or None,
                     col("items", i) or None, col("primaryDocument", i) or None))
        self.db.commit()
        return self.db.total_changes - before

    def log_form4(self, accession: str, status: str, fetched_at: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO form4_fetch (accession, status, fetched_at) VALUES (?,?,?)",
                        (accession, status, fetched_at))

    def save_form4_raw(self, accession: str, payload: bytes) -> None:
        self.db.execute("INSERT OR REPLACE INTO form4_raw (accession, body_gz) VALUES (?,?)",
                        (accession, gzip.compress(payload, 6)))

    def add_buy(self, row: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO form4_buys (accession, owner_cik, issuer_cik, symbol, owner_name, role, filed, "
            "accepted_at, first_trade, last_trade, shares, amount_usd, plan_10b5_1, indirect) "
            "VALUES (:accession,:owner_cik,:issuer_cik,:symbol,:owner_name,:role,:filed,:accepted_at,:first_trade,"
            ":last_trade,:shares,:amount_usd,:plan_10b5_1,:indirect)", row)

    def add_insider_p(self, rows: Iterable[tuple], source: str) -> int:
        before = self.db.total_changes
        self.db.executemany(
            "INSERT OR IGNORE INTO insider_p (accession, owner_cik, issuer_cik, trade_date, filed, shares, price, source) "
            "VALUES (?,?,?,?,?,?,?,?)", [tuple(r) + (source,) for r in rows])
        return self.db.total_changes - before

    def touch_owner_first(self, rows: Iterable[tuple], source: str) -> None:
        self.db.executemany(
            "INSERT INTO owner_first (owner_cik, first_filed, source) VALUES (?,?,?) "
            "ON CONFLICT(owner_cik) DO UPDATE SET first_filed=excluded.first_filed, source=excluded.source "
            "WHERE excluded.first_filed < owner_first.first_filed", [tuple(r) + (source,) for r in rows])

    def mark_dataset(self, name: str, rows: int, loaded_at: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO dataset_loaded (name, rows, loaded_at) VALUES (?,?,?)",
                        (name, rows, loaded_at))

    def add_shares(self, rows: Iterable[tuple]) -> int:
        before = self.db.total_changes
        self.db.executemany("INSERT OR IGNORE INTO shares_obs (cik, cover_end, shares, accession) VALUES (?,?,?,?)",
                            list(rows))
        self.db.commit()
        return self.db.total_changes - before

    def commit(self) -> None:
        self.db.commit()

    # ---- 读取（都带 as_of）-----------------------------------------------
    def filings_as_of(self, forms: Sequence[str], as_of: DateLike, since: Optional[DateLike] = None,
                      ciks: Optional[Sequence[int]] = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM filings WHERE filed <= ? AND form IN (%s)" % ",".join("?" * len(forms))
        params: list = [iso(as_of)] + list(forms)
        if since is not None:
            sql += " AND filed >= ?"
            params.append(iso(since))
        if ciks is not None:
            sql += " AND cik IN (%s)" % ",".join("?" * len(ciks))
            params += [int(c) for c in ciks]
        return list(self.db.execute(sql + " ORDER BY filed, accession", params))

    def buys_as_of(self, issuer_cik: int, as_of: DateLike, since: Optional[DateLike] = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM form4_buys WHERE issuer_cik = ? AND filed <= ?"
        params: list = [int(issuer_cik), iso(as_of)]
        if since is not None:
            sql += " AND filed >= ?"
            params.append(iso(since))
        return list(self.db.execute(sql + " ORDER BY filed, accession, owner_cik", params))

    def all_buys_as_of(self, as_of: DateLike, since: Optional[DateLike] = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM form4_buys WHERE filed <= ?"
        params: list = [iso(as_of)]
        if since is not None:
            sql += " AND filed >= ?"
            params.append(iso(since))
        return list(self.db.execute(sql + " ORDER BY filed, accession, owner_cik", params))

    def owner_p_months(self, owner_cik: int, as_of: DateLike) -> set:
        """该内部人（任何发行人）在 as_of 前已申报的 P 买入所在的 (年, 月) 集合。"""
        rows = self.db.execute(
            "SELECT DISTINCT trade_date FROM insider_p WHERE owner_cik = ? AND filed <= ?",
            (int(owner_cik), iso(as_of)))
        months = set()
        for (trade_date,) in rows:
            months.add((int(trade_date[:4]), int(trade_date[5:7])))
        return months

    def offering_like_accessions(self, as_of: DateLike, min_buyers: int) -> set:
        """同一发行人、同一成交日、同一价格，有 >= min_buyers 份不同申报在买——多半是 IPO/定向增发/转换发行里的认购，
        不是公开市场上各自掏钱。联名申报是同一份 accession，只算一份。"""
        key = (iso(as_of), int(min_buyers), self.db.total_changes)
        cached = self._offering_cache.get(key)
        if cached is not None:
            return cached
        rows = self.db.execute(
            "SELECT DISTINCT p.accession FROM insider_p p JOIN ("
            " SELECT issuer_cik, trade_date, price FROM insider_p WHERE price > 0 AND filed <= ?"
            " GROUP BY issuer_cik, trade_date, price HAVING COUNT(DISTINCT accession) >= ?) k"
            " ON p.issuer_cik = k.issuer_cik AND p.trade_date = k.trade_date AND p.price = k.price",
            (iso(as_of), int(min_buyers)))
        result = {row[0] for row in rows}
        self._offering_cache = {key: result}    # 只留最近一次；库有写入（total_changes 变了）就自动失效
        return result

    def owner_first_filed(self, owner_cik: int) -> Optional[str]:
        row = self.db.execute("SELECT first_filed FROM owner_first WHERE owner_cik = ?", (int(owner_cik),)).fetchone()
        return row[0] if row else None

    def meta_as_of(self, cik: int, forms: Sequence[str], as_of: DateLike, since: Optional[DateLike] = None):
        sql = "SELECT * FROM filing_meta WHERE cik = ? AND filed <= ? AND form IN (%s)" % ",".join("?" * len(forms))
        params: list = [int(cik), iso(as_of)] + list(forms)
        if since is not None:
            sql += " AND filed >= ?"
            params.append(iso(since))
        return list(self.db.execute(sql + " ORDER BY filed, accession", params))

    def count(self, table: str) -> int:
        if table not in {"filings", "filing_meta", "form4_fetch", "form4_raw", "form4_buys", "insider_p",
                         "owner_first", "dataset_loaded", "shares_obs", "prospectus_class"}:
            raise ValueError(table)
        return self.db.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
