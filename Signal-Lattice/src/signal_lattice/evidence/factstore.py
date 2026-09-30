"""时点正确的事实库（SQLite）。

- 按 filed（申报日）入账；同一概念同一期的重述是新增一行，绝不覆盖原值。
- facts_as_of(cik, concept, as_of) 只返回 filed <= as_of 的行，同一期取 filed 最新的一条。
- 实体表只增不删：退市、改名的公司留在库里，避免幸存者偏差。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional, Union

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    cik          INTEGER NOT NULL,
    concept      TEXT    NOT NULL,          -- taxonomy:tag，例如 us-gaap:Revenues
    unit         TEXT    NOT NULL,
    value        REAL    NOT NULL,
    period_start TEXT,                      -- 时点型事实（资产负债表/封面）为 NULL
    period_end   TEXT    NOT NULL,
    form         TEXT    NOT NULL,
    accession    TEXT    NOT NULL,
    filed        TEXT    NOT NULL,          -- YYYY-MM-DD，点时查询的唯一时钟
    source_url   TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS facts_identity
    ON facts (cik, concept, unit, COALESCE(period_start, ''), period_end, accession);
CREATE INDEX IF NOT EXISTS facts_lookup ON facts (cik, concept, filed);

CREATE TABLE IF NOT EXISTS entities (
    cik                INTEGER PRIMARY KEY,
    first_seen         TEXT NOT NULL,
    last_seen_listed   TEXT,                -- 最近一次出现在 SEC 上市名单的日期；退市后不再更新，行不删除
    sic                TEXT
);
CREATE TABLE IF NOT EXISTS entity_names (
    cik      INTEGER NOT NULL,
    name     TEXT    NOT NULL,
    ticker   TEXT    NOT NULL DEFAULT '',
    exchange TEXT    NOT NULL DEFAULT '',
    source   TEXT    NOT NULL,
    seen_at  TEXT    NOT NULL,
    PRIMARY KEY (cik, name, ticker, exchange)
);
CREATE TABLE IF NOT EXISTS filings (
    cik              INTEGER NOT NULL,
    accession        TEXT    NOT NULL,
    form             TEXT    NOT NULL,
    filed            TEXT    NOT NULL,
    report_date      TEXT,
    items            TEXT,
    primary_document TEXT,
    source_url       TEXT    NOT NULL,
    PRIMARY KEY (cik, accession)
);
CREATE INDEX IF NOT EXISTS filings_lookup ON filings (cik, form, filed);
CREATE TABLE IF NOT EXISTS ingest_log (
    cik         INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    ingested_at TEXT    NOT NULL,
    rows_added  INTEGER NOT NULL
);
"""

DateLike = Union[str, date, datetime]


def _iso(value: DateLike) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    date.fromisoformat(text)  # 非法日期在这里抛错，不让脏字符串进查询
    return text


def filing_index_url(cik: int, accession: str) -> str:
    return "https://www.sec.gov/Archives/edgar/data/%d/%s/%s-index.htm" % (
        int(cik), accession.replace("-", ""), accession,
    )


@dataclass(frozen=True)
class Fact:
    cik: int
    concept: str
    unit: str
    value: float
    period_start: Optional[str]
    period_end: str
    form: str
    accession: str
    filed: str
    source_url: str


_FACT_COLUMNS = "cik, concept, unit, value, period_start, period_end, form, accession, filed, source_url"


class FactStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    @classmethod
    def read_only(cls, path: Union[str, Path]) -> "FactStore":
        """只读打开（immutable：不建库、不写、不取锁）。给隔离子进程读快照用；写入方法在只读连接上会直接报错。"""
        store = cls.__new__(cls)
        store.path = str(path)
        store.db = sqlite3.connect("file:%s?mode=ro&immutable=1" % store.path, uri=True)
        store.db.row_factory = sqlite3.Row
        return store

    def close(self) -> None:
        self.db.close()

    # ---- 写入（只增不改不删）----------------------------------------------
    def ingest_companyfacts(self, cik: int, payload: dict, ingested_at: DateLike) -> int:
        """把 companyfacts 整份入账。已存在的 (概念, 期, accession) 忽略，其余新增。"""
        rows = []
        for taxonomy, concepts in (payload.get("facts") or {}).items():
            for tag, body in concepts.items():
                concept = "%s:%s" % (taxonomy, tag)
                for unit, entries in (body.get("units") or {}).items():
                    for entry in entries:
                        try:
                            rows.append((
                                int(cik), concept, unit, float(entry["val"]), entry.get("start"),
                                entry["end"], entry["form"], entry["accn"], _iso(entry["filed"]),
                                filing_index_url(cik, entry["accn"]),
                            ))
                        except (KeyError, TypeError, ValueError):
                            continue  # 缺关键字段的行不入账
        before = self.db.total_changes
        self.db.executemany(
            "INSERT OR IGNORE INTO facts (%s) VALUES (?,?,?,?,?,?,?,?,?,?)" % _FACT_COLUMNS, rows
        )
        added = self.db.total_changes - before
        self._log(cik, "companyfacts", ingested_at, added)
        self.db.commit()
        return added

    def upsert_listed(self, rows: Iterable[dict], seen_on: DateLike) -> int:
        """company_tickers_exchange 的行（cik/name/ticker/exchange）。只增不删。"""
        seen = _iso(seen_on)
        count = 0
        for row in rows:
            cik = int(row["cik"])
            self.db.execute(
                "INSERT INTO entities (cik, first_seen, last_seen_listed) VALUES (?,?,?) "
                "ON CONFLICT(cik) DO UPDATE SET last_seen_listed=excluded.last_seen_listed",
                (cik, seen, seen),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO entity_names (cik, name, ticker, exchange, source, seen_at) "
                "VALUES (?,?,?,?,?,?)",
                (cik, row["name"], row.get("ticker") or "", row.get("exchange") or "", "tickers_exchange", seen),
            )
            count += 1
        self.db.commit()
        return count

    def ingest_submissions(self, cik: int, payload: dict, seen_on: DateLike) -> int:
        """submissions：公司名（含曾用名）、SIC、近期申报清单。返回新增申报条数。"""
        seen = _iso(seen_on)
        cik = int(cik)
        self.db.execute(
            "INSERT INTO entities (cik, first_seen, sic) VALUES (?,?,?) "
            "ON CONFLICT(cik) DO UPDATE SET sic=COALESCE(excluded.sic, entities.sic)",
            (cik, seen, payload.get("sic") or None),
        )
        name = payload.get("name")
        tickers = payload.get("tickers") or [""]
        exchanges = payload.get("exchanges") or [""]
        if name:
            for index, ticker in enumerate(tickers):
                exchange = exchanges[index] if index < len(exchanges) else ""
                self.db.execute(
                    "INSERT OR IGNORE INTO entity_names (cik, name, ticker, exchange, source, seen_at) "
                    "VALUES (?,?,?,?,?,?)", (cik, name, ticker, exchange, "submissions", seen),
                )
        for former in payload.get("formerNames") or []:
            if former.get("name"):
                self.db.execute(
                    "INSERT OR IGNORE INTO entity_names (cik, name, ticker, exchange, source, seen_at) "
                    "VALUES (?,?,?,?,?,?)", (cik, former["name"], "", "", "submissions_former", seen),
                )
        recent = (payload.get("filings") or {}).get("recent") or {}
        accessions = recent.get("accessionNumber") or []

        def column(key: str, index: int):
            values = recent.get(key) or []
            return values[index] if index < len(values) else None

        before = self.db.total_changes
        for index, accession in enumerate(accessions):
            filed, form = column("filingDate", index), column("form", index)
            if not filed or not form:
                continue
            self.db.execute(
                "INSERT OR IGNORE INTO filings (cik, accession, form, filed, report_date, items, primary_document, source_url) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (cik, accession, form, _iso(filed), column("reportDate", index) or None,
                 column("items", index) or None, column("primaryDocument", index) or None,
                 filing_index_url(cik, accession)),
            )
        added = self.db.total_changes - before
        self._log(cik, "submissions", seen, added)
        self.db.commit()
        return added

    def _log(self, cik: int, source: str, at: DateLike, rows: int) -> None:
        self.db.execute(
            "INSERT INTO ingest_log (cik, source, ingested_at, rows_added) VALUES (?,?,?,?)",
            (int(cik), source, _iso(at), rows),
        )

    # ---- 读取 ------------------------------------------------------------
    def facts_as_of(self, cik: int, concept: str, as_of: DateLike, unit: Optional[str] = None) -> list[Fact]:
        """as_of 当天收盘时能看到的事实：filed <= as_of，同一期取 filed 最新的一条。"""
        sql = (
            "SELECT %s FROM ("
            " SELECT %s, ROW_NUMBER() OVER ("
            "   PARTITION BY unit, COALESCE(period_start, ''), period_end"
            "   ORDER BY filed DESC, accession DESC) AS rn"
            " FROM facts WHERE cik = ? AND concept = ? AND filed <= ?"
        ) % (_FACT_COLUMNS, _FACT_COLUMNS)
        params: list = [int(cik), concept, _iso(as_of)]
        if unit is not None:
            sql += " AND unit = ?"
            params.append(unit)
        sql += ") WHERE rn = 1 ORDER BY period_end, COALESCE(period_start, ''), unit"
        return [Fact(**dict(row)) for row in self.db.execute(sql, params)]

    def all_versions(self, cik: int, concept: str) -> list[Fact]:
        """同一概念同一期的全部版本（原值与历次重述并存），按期与申报日排序。"""
        rows = self.db.execute(
            "SELECT %s FROM facts WHERE cik = ? AND concept = ? "
            "ORDER BY period_end, COALESCE(period_start, ''), unit, filed, accession" % _FACT_COLUMNS,
            (int(cik), concept),
        )
        return [Fact(**dict(row)) for row in rows]

    def filings_as_of(self, cik: int, as_of: DateLike, forms: Optional[Iterable[str]] = None) -> list[dict]:
        sql = "SELECT * FROM filings WHERE cik = ? AND filed <= ?"
        params: list = [int(cik), _iso(as_of)]
        if forms:
            forms = list(forms)
            sql += " AND form IN (%s)" % ",".join("?" * len(forms))
            params += forms
        sql += " ORDER BY filed, accession"
        return [dict(row) for row in self.db.execute(sql, params)]

    def entity_names(self, cik: int) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT name, ticker, exchange, source, seen_at FROM entity_names WHERE cik = ? ORDER BY seen_at, name",
            (int(cik),),
        )]

    def count(self, table: str, cik: Optional[int] = None) -> int:
        if table not in {"facts", "entities", "entity_names", "filings", "ingest_log"}:
            raise ValueError(table)
        if cik is None:
            return self.db.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
        return self.db.execute("SELECT COUNT(*) FROM %s WHERE cik = ?" % table, (int(cik),)).fetchone()[0]
