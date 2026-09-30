"""不可变证据快照：一轮研究里所有分支共同、只读的输入。

文件名 evidence-<日期>-<内容hash前12位>.json，内容 hash（canonical JSON 的 sha256）写在文件里，读取端重算，
对不上就拒绝（SnapshotError），分支收据里记同一个 snapshot_hash。

快照本体只放小东西（候选池、Lazy Prices 记录、市场环境日线、参数版本与 hash、采集统计）；
大东西（事实库 1.5GB、事件库、日线目录、结构性抽取）按「路径 + sha256 + 字节数」钉住，分支读之前先校验：
- 事实库 / 事件库：SQLite immutable 只读打开，构建快照时先把 WAL 检查点到主文件；
- 日线目录：一份 manifest（文件名+各文件 sha256）的 sha256；
- 结构性抽取：一个 gz JSON，内容寻址（文件名含 hash），随快照新建、不覆盖。
数据库是追加更新的，所以历史快照的钉住 hash 在之后的采集后会对不上——快照的保证是「本轮所有分支读到的是同一份、
且没在中途被改过的数据」，不是「永久可重放」；要永久重放需要另存数据库副本（体量 1.7GB，本版不做）。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .evidence.eventstore import EventStore
from .evidence.factstore import FactStore
from .evidence.history_prices import BarStore
from .evidence.structure_text import FilingExtraction
from .marketdata.models import Bar

SCHEMA = "signal-lattice-evidence/1"
BENCHMARK_SYMBOL = "IWM"


class SnapshotError(RuntimeError):
    pass


def canonical_hash(body: Mapping) -> str:
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def bars_manifest(bar_store: BarStore, symbols: Iterable[str]) -> Dict[str, Any]:
    lines = []
    for symbol in sorted(set(symbols)):
        path = bar_store.path(symbol)
        if path.is_file():
            lines.append("%s\t%s" % (symbol, sha256_file(path)))
    text = "\n".join(lines)
    return {"path": str(bar_store.directory), "files": len(lines), "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "symbols": sorted({line.split("\t")[0] for line in lines})}


def checkpoint_sqlite(path: Path) -> None:
    """把 WAL 合并回主文件并截断，保证「主文件 hash = 全部内容」。"""
    connection = sqlite3.connect(str(path), timeout=60)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    wal = Path(str(path) + "-wal")
    if wal.is_file() and wal.stat().st_size > 0:
        raise SnapshotError("WAL 未清空，不能给 %s 建快照" % path)


def pin_file(path: Path) -> Dict[str, Any]:
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def write_structure_file(structure_by_cik: Mapping[int, Sequence[FilingExtraction]], directory: Path) -> Dict[str, Any]:
    """内容寻址：同样的内容得到同样的文件名，已存在就不重写。"""
    payload = {str(cik): [f.to_dict() for f in filings] for cik, filings in sorted(structure_by_cik.items())}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ("structure-%s.json.gz" % digest[:12])
    if not target.is_file():
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(raw, 6, mtime=0))
        temporary.replace(target)
    return {"path": str(target), "content_sha256": digest, "sha256": sha256_file(target), "bytes": target.stat().st_size,
            "companies": len(payload)}


def bars_to_rows(bars: Sequence[Bar]) -> List[list]:
    return [[b.day.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in bars]


def build_body(*, as_of: str, universe: Mapping, facts_db: Path, events_db: Path, bar_store: BarStore,
               structure: Mapping[str, Any], text_similarity: Mapping, market_environment: Mapping[str, Sequence[Bar]],
               params: Mapping, collection: Mapping, verify_hashes: bool = True,
               evidence_cards: Optional[Mapping] = None) -> dict:
    """evidence_cards：产业瓶颈证据卡载荷（evidence/cards.load_payload）。随快照一起钉住并进 hash：
    同一份快照无论何时重跑，分支看到的证据卡都一样；不传则快照里没有这一项（旧快照同样读不到卡片）。"""
    checkpoint_sqlite(Path(events_db))
    symbols = [e["symbol"] for e in universe["entries"]] + [BENCHMARK_SYMBOL]
    body = {
        "schema": SCHEMA,
        "as_of_date": as_of,
        "universe": {"source_sha256": universe["content_sha256"], "count": len(universe["entries"]),
                     "rules": universe.get("rules"), "entries": universe["entries"]},
        "data_files": {"facts_db": pin_file(Path(facts_db)), "events_db": pin_file(Path(events_db)),
                       "bars": bars_manifest(bar_store, symbols), "structure": dict(structure)},
        "text_similarity": dict(text_similarity),
        "market_environment": {"symbols": {s: {"sha256": hashlib.sha256(json.dumps(bars_to_rows(b)).encode()).hexdigest(),
                                               "bars": bars_to_rows(b)} for s, b in sorted(market_environment.items())}},
        "params": dict(params),
        "collection": dict(collection),
    }
    if evidence_cards is not None:
        body["evidence_cards"] = dict(evidence_cards)
    return body


def write_snapshot(body: Mapping, out_dir: Path, generated_at: Optional[datetime] = None,
                   run_info: Optional[Mapping] = None) -> Path:
    """run_info（采集统计、参数 findings 等运行事件）随文件保存但不进 hash：内容相同的快照 hash 必须相同。"""
    digest = canonical_hash(body)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("evidence-%s-%s.json" % (body["as_of_date"], digest[:12]))
    document = {**body, "content_sha256": digest, "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
                "run_info": dict(run_info or {})}
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        existing = json.loads(path.read_text("utf-8"))
        if existing.get("content_sha256") != digest:
            raise SnapshotError("同名快照内容不一致：%s" % path)
    return path


@dataclass
class EvidenceSnapshot:
    path: Path
    document: dict

    @property
    def sha256(self) -> str:
        return self.document["content_sha256"]

    @property
    def as_of(self) -> str:
        return self.document["as_of_date"]

    @property
    def entries(self) -> List[dict]:
        return self.document["universe"]["entries"]

    def data(self, key: str) -> dict:
        return self.document["data_files"][key]

    # ---- 校验 -----------------------------------------------------------------
    def verify_body(self) -> None:
        body = {k: v for k, v in self.document.items() if k not in ("content_sha256", "generated_at", "run_info")}
        if canonical_hash(body) != self.document["content_sha256"]:
            raise SnapshotError("快照内容 hash 对不上：文件被改过")
        if self.document.get("schema") != SCHEMA:
            raise SnapshotError("快照 schema 不认识：%r" % self.document.get("schema"))

    def verify_data(self, keys: Iterable[str]) -> None:
        for key in keys:
            info = self.data(key)
            if key == "bars":
                store = BarStore(Path(info["path"]))
                if bars_manifest(store, info["symbols"])["manifest_sha256"] != info["manifest_sha256"]:
                    raise SnapshotError("日线目录 hash 对不上")
                continue
            path = Path(info["path"])
            if not path.is_file() or path.stat().st_size != info["bytes"] or sha256_file(path) != info["sha256"]:
                raise SnapshotError("%s 的内容与快照钉住的 hash 不一致（快照之后被改过，或文件缺失）" % key)

    # ---- 只读访问 ---------------------------------------------------------------
    def facts(self) -> FactStore:
        return FactStore.read_only(self.data("facts_db")["path"])

    def events(self) -> EventStore:
        return EventStore.read_only(self.data("events_db")["path"])

    def bar_store(self) -> BarStore:
        return BarStore(Path(self.data("bars")["path"]))

    def structure(self) -> Dict[int, List[FilingExtraction]]:
        info = self.data("structure")
        raw = json.loads(gzip.decompress(Path(info["path"]).read_bytes()).decode("utf-8"))
        return {int(cik): [FilingExtraction.from_dict(f) for f in filings] for cik, filings in raw.items()}

    def evidence_cards(self) -> Optional[Mapping[str, Any]]:
        """产业瓶颈证据卡载荷；快照里没有这一项（旧快照）返回 None，等同没有任何卡片。"""
        return self.document.get("evidence_cards")

    def text_similarity_by_symbol(self) -> Dict[str, dict]:
        return {r["symbol"]: r for r in self.document["text_similarity"].get("records", [])}

    def market_environment_bars(self) -> Dict[str, List[Bar]]:
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        zones = {"usSPY": "America/New_York", "sh000300": "Asia/Shanghai", "hk02800": "Asia/Hong_Kong"}
        out: Dict[str, List[Bar]] = {}
        for symbol, block in self.document["market_environment"]["symbols"].items():
            out[symbol] = [Bar(symbol, date.fromisoformat(r[0]), r[1], r[2], r[3], r[4], r[5], zones.get(symbol, "UTC"),
                               "evidence_snapshot", epoch) for r in block["bars"]]
        return out

    def params_file(self, skill_id: str) -> Optional[Path]:
        """本轮该 Skill 的参数文件；读之前核对钉住的 sha256（防被中途改过）。没有外置参数返回 None。"""
        info = self.document["params"]["skills"].get(skill_id)
        if not info or not info.get("active_path"):
            return None
        path = Path(info["active_path"])
        if not path.is_file() or sha256_file(path) != info["params_sha256"]:
            raise SnapshotError("参数文件与快照钉住的 hash 不一致：%s" % skill_id)
        return path

    def params_info(self, skill_id: str) -> Mapping[str, Any]:
        return self.document["params"]["skills"][skill_id]


def load_snapshot(path: Path, verify_keys: Optional[Iterable[str]] = ()) -> EvidenceSnapshot:
    try:
        document = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise SnapshotError("快照读不了：%s" % exc) from exc
    snapshot = EvidenceSnapshot(Path(path), document)
    snapshot.verify_body()
    snapshot.verify_data(verify_keys or ())
    return snapshot
