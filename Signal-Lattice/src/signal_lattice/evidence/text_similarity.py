"""年报/季报措辞变化（Lazy Prices，Cohen-Malloy-Nguyen）：相邻同类申报的正文余弦相似度。

同类 = 10-K 对上一份 10-K；10-Q 对上年同季的 10-Q。相似度越低，说明公司这次改动越大。
本模块只产出特征与证据（相似度、分位、是否「大改动者」、变化最大的段落、两份原文链接），
不自己出 verdict——给商业机会（风险扣分）与股势前瞻（特征）当输入。

实现：标准库。HTML 去标签 → 小写、去数字与标点的词袋（TF）→ 余弦。
风险因素（Item 1A）与法律诉讼（Item 3 / 10-Q 的 Part II Item 1）单独比一次，并找出「上期没有对应段落」的新段落。
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import math
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .. import cache_cap
from .eventstore import EventStore, iso
from .prospectus import document_url
from .sec_client import SecClient, SecFetchError

BIG_CHANGER_QUANTILE = 0.20
NEW_PARAGRAPH_MAX_COSINE = 0.5      # 与上期任何段落的余弦都低于它，就算「新段落」
MIN_PARAGRAPH_CHARS = 80
SAMPLE_EXCERPT_CHARS = 260

_HIDDEN = re.compile(r"<(ix:header|script|style|head)\b.*?</\1>", re.I | re.S)
_BLOCK_END = re.compile(r"</(?:p|div|tr|li|h[1-6]|table|section)\s*>|<br\s*/?>", re.I)
_CELL_END = re.compile(r"</t[dh]\s*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[a-z]{2,}")
_NUMBERISH = re.compile(r"[\d$%]+[\d,.\-]*")

# 段落定位：标题可能被拆成两行（"Item 1A." / "Risk Factors"），所以标题词之间允许换行
_SECTIONS = {
    "risk_factors": (
        re.compile(r"(?im)^\s*item\s*1a\W{0,6}\s*risk\s*factors"),
        re.compile(r"(?im)^\s*item\s*(?:1b|2)\b"),
        "风险因素（Item 1A）",
    ),
    "legal_proceedings": (
        re.compile(r"(?im)^\s*item\s*(?:3|1)\W{0,6}\s*legal\s*proceedings"),
        re.compile(r"(?im)^\s*item\s*(?:4|1a|2)\b"),
        "法律诉讼（Legal Proceedings）",
    ),
}


_MIN_SECTION_CHARS = {"risk_factors": 200, "legal_proceedings": 60}  # 短于此的多半只是目录里的一行


def html_to_text(payload: bytes) -> str:
    """去隐藏块/脚本/标签，保留段落换行。"""
    text = payload.decode("utf-8", errors="replace")
    text = _HIDDEN.sub(" ", text)
    text = _CELL_END.sub(" ", text)
    text = _BLOCK_END.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def tokens(text: str) -> List[str]:
    return _WORD.findall(_NUMBERISH.sub(" ", text.lower()))


def tf_vector(text: str) -> Counter:
    return Counter(tokens(text))


def _norm(vector: Counter) -> float:
    return math.sqrt(sum(v * v for v in vector.values()))


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(count * large.get(word, 0) for word, count in small.items())
    denominator = _norm(a) * _norm(b)
    return dot / denominator if denominator else 0.0


def extract_section(text: str, name: str) -> str:
    """同一个标题在目录里出现一次、正文里出现一次：取「起点到终点最长」的那一段。"""
    start_pattern, end_pattern, _label = _SECTIONS[name]
    best = ""
    for start in start_pattern.finditer(text):
        end = end_pattern.search(text, start.end())
        chunk = text[start.start(): end.start() if end else len(text)]
        if len(chunk) > len(best):
            best = chunk
    return best if len(best) >= _MIN_SECTION_CHARS[name] else ""


def paragraphs(text: str) -> List[str]:
    return [line for line in text.split("\n") if len(line) >= MIN_PARAGRAPH_CHARS]


def changed_paragraphs(new_text: str, old_text: str) -> Tuple[float, Optional[str], int]:
    """(新段落词数占比, 变化最大的新段落摘录, 新段落数)。新段落 = 与上期所有段落的余弦都低于阈值。"""
    new_paras = paragraphs(new_text)
    old_vectors = [tf_vector(p) for p in paragraphs(old_text)]
    if not new_paras:
        return 0.0, None, 0
    total_words = changed_words = changed = 0
    top: Tuple[float, Optional[str]] = (2.0, None)
    for paragraph in new_paras:
        vector = tf_vector(paragraph)
        words = sum(vector.values())
        total_words += words
        best = max((cosine(vector, old) for old in old_vectors), default=0.0)
        if best < NEW_PARAGRAPH_MAX_COSINE:
            changed += 1
            changed_words += words
            if words >= 20 and best < top[0]:
                top = (best, paragraph)
    excerpt = top[1][:SAMPLE_EXCERPT_CHARS] if top[1] else None
    return (changed_words / total_words if total_words else 0.0), excerpt, changed


def compare_documents(new_text: str, old_text: str) -> dict:
    """整篇相似度 + 风险因素/法律诉讼两段的相似度与新段落。"""
    result: dict = {"similarity": cosine(tf_vector(new_text), tf_vector(old_text)),
                    "new_words": len(tokens(new_text)), "old_words": len(tokens(old_text)), "sections": {}}
    largest: Tuple[float, Optional[str], Optional[str]] = (-1.0, None, None)
    for name, (_s, _e, label) in _SECTIONS.items():
        new_section, old_section = extract_section(new_text, name), extract_section(old_text, name)
        if not new_section or not old_section:
            result["sections"][name] = {"label": label, "found": False}
            continue
        share, excerpt, count = changed_paragraphs(new_section, old_section)
        result["sections"][name] = {
            "label": label, "found": True, "similarity": cosine(tf_vector(new_section), tf_vector(old_section)),
            "new_paragraph_share": share, "new_paragraphs": count, "sample_new_paragraph": excerpt}
        if share > largest[0] and share > 0:
            largest = (share, label, excerpt)
    result["largest_change_section"] = largest[1]
    result["largest_change_share"] = largest[0] if largest[1] else None
    result["largest_change_excerpt"] = largest[2]
    return result


# ---- 选文件 ---------------------------------------------------------------------
def pick_pair(rows: Sequence[Mapping], as_of) -> Optional[Tuple[Mapping, Mapping]]:
    """rows：filing_meta 里该公司的 10-K/10-Q（已按 filed 升序）。返回 (最新一份, 上期同类)。"""
    visible = [r for r in rows if r["filed"] <= iso(as_of) and r["primary_document"]]
    if not visible:
        return None
    latest = visible[-1]
    same_form = [r for r in visible[:-1] if r["form"] == latest["form"]]
    if latest["form"] == "10-K":
        return (latest, same_form[-1]) if same_form else None
    if not latest["report_date"]:
        return None
    target = date.fromisoformat(latest["report_date"]) - timedelta(days=365)
    candidates = [r for r in same_form if r["report_date"] and abs((date.fromisoformat(r["report_date"]) - target).days) <= 25]
    if not candidates:
        return None
    return latest, min(candidates, key=lambda r: abs((date.fromisoformat(r["report_date"]) - target).days))


def stratified_sample(entries: Sequence[Mapping], size: int, seed: int = 20260930) -> List[Mapping]:
    """按市值分层抽样：每层按其在池内的占比取，层内随机（固定种子，可复现）。"""
    edges = [3e8, 5e8, 1e9, 2e9, 5e9, float("inf")]
    strata: Dict[int, List[Mapping]] = {}
    for entry in entries:
        for index in range(len(edges) - 1):
            if edges[index] <= entry["market_cap_usd"] < edges[index + 1]:
                strata.setdefault(index, []).append(entry)
                break
    if size >= len(entries):
        return list(entries)
    rng = random.Random(seed)
    chosen: List[Mapping] = []
    total = len(entries)
    for index in sorted(strata):
        bucket = sorted(strata[index], key=lambda e: e["symbol"])
        take = max(1, round(size * len(bucket) / total))
        chosen += rng.sample(bucket, min(take, len(bucket)))
    return sorted(chosen, key=lambda e: e["symbol"])


class TextCache:
    """抽出来的正文（不是原始 HTML）压缩落盘，一份申报一个文件。"""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, accession: str) -> Path:
        return self.directory / (accession + ".txt.gz")

    def get(self, accession: str) -> Optional[str]:
        try:
            text = gzip.decompress(self.path(accession).read_bytes()).decode("utf-8")
        except (OSError, EOFError):
            return None
        cache_cap.touch(self.path(accession))
        return text

    def put(self, accession: str, text: str) -> None:
        temporary = self.path(accession).with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(text.encode("utf-8"), 6))
        temporary.replace(self.path(accession))


def fetch_text(client: SecClient, cache: TextCache, cik: int, row: Mapping) -> Optional[str]:
    cached = cache.get(row["accession"])
    if cached is not None:
        return cached
    try:
        payload = client.get_bytes(document_url(cik, row["accession"], row["primary_document"]), cache=False)
    except SecFetchError:
        return None
    text = html_to_text(payload)
    if len(text) < 2000:
        return None
    cache.put(row["accession"], text)
    return text


def compute_for_company(client: SecClient, cache: TextCache, entry: Mapping, rows: Sequence[Mapping], as_of) -> Optional[dict]:
    """rows：该公司 filing_meta 里的 10-K/10-Q（调用方在主线程读好，工作线程不碰数据库）。"""
    pair = pick_pair(rows, as_of)
    if pair is None:
        return None
    latest, previous = pair
    new_text, old_text = fetch_text(client, cache, int(entry["cik"]), latest), fetch_text(client, cache, int(entry["cik"]), previous)
    if new_text is None or old_text is None:
        return None
    result = compare_documents(new_text, old_text)
    cik = int(entry["cik"])
    result.update({
        "symbol": entry["symbol"], "cik": cik, "name": entry["name"], "market_cap_usd": entry["market_cap_usd"],
        "form": latest["form"], "filed": latest["filed"], "prior_filed": previous["filed"],
        "accession": latest["accession"], "prior_accession": previous["accession"],
        "url": document_url(cik, latest["accession"], latest["primary_document"]),
        "prior_url": document_url(cik, previous["accession"], previous["primary_document"]),
    })
    return result


def add_percentiles(records: List[dict], quantile: float = BIG_CHANGER_QUANTILE) -> dict:
    """同一表格类型内排名：分位 = 相似度不高于它的比例（越低越是大改动者）；最低 quantile 为「大改动者」。"""
    by_form: Dict[str, List[dict]] = {}
    for record in records:
        by_form.setdefault(record["form"], []).append(record)
    thresholds = {}
    for form, group in by_form.items():
        ordered = sorted(r["similarity"] for r in group)
        for record in group:
            rank = sum(1 for v in ordered if v <= record["similarity"])
            record["percentile"] = rank / len(ordered)
        cutoff_index = max(0, math.ceil(len(ordered) * quantile) - 1)
        thresholds[form] = ordered[cutoff_index]
        for record in group:
            record["big_changer"] = len(ordered) >= 5 and record["similarity"] <= thresholds[form]
    return thresholds


def save_records(store: EventStore, records: Iterable[dict], as_of) -> None:
    store.db.execute("CREATE TABLE IF NOT EXISTS text_sim (cik INTEGER NOT NULL, accession TEXT NOT NULL, as_of TEXT NOT NULL, "
                     "payload TEXT NOT NULL, PRIMARY KEY (cik, accession))")
    for record in records:
        store.db.execute("INSERT OR REPLACE INTO text_sim (cik, accession, as_of, payload) VALUES (?,?,?,?)",
                         (record["cik"], record["accession"], iso(as_of), json.dumps(record, ensure_ascii=False)))
    store.commit()


def run_batch(client: SecClient, store: EventStore, cache: TextCache, entries: Sequence[Mapping], as_of,
              workers: int = 3, log: Callable[[str], None] = print) -> dict:
    records: List[dict] = []
    skipped = 0
    rows_by_cik = {int(e["cik"]): [dict(r) for r in store.meta_as_of(int(e["cik"]), ["10-K", "10-Q"], as_of)] for e in entries}

    def work(entry):
        try:
            return compute_for_company(client, cache, entry, rows_by_cik[int(entry["cik"])], as_of)
        except Exception as exc:  # 单家失败不拖垮整批；计入 skipped 并写日志
            log("text-sim failed %s: %s" % (entry["symbol"], type(exc).__name__))
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, record in enumerate(pool.map(work, entries), 1):
            if record is None:
                skipped += 1
            else:
                records.append(record)
            if index % 25 == 0:
                log("text-sim %d/%d ok=%d skipped=%d requests=%d" % (index, len(entries), len(records), skipped, client.requests_sent))
    thresholds = add_percentiles(records)
    save_records(store, records, as_of)
    return {"records": records, "skipped": skipped, "thresholds": thresholds}


# ---- 研究层每轮增量生成（生产路径）-----------------------------------------------------
TEXT_SIM_MAX_REQUESTS_PER_RUN = 1500    # 单轮最多下载多少份申报正文（= SEC 请求数）；超出的下一轮接着补，限速仍是全局 <= 4 次/秒
TEXT_SIM_MAX_TRIES = 3                  # 同一份申报取不到/正文过短，累计尝试这么多次后不再占用请求额度
PERIODIC_FORMS = ("10-K", "10-Q")


def ensure_tables(store: EventStore) -> None:
    store.db.execute("CREATE TABLE IF NOT EXISTS text_sim (cik INTEGER NOT NULL, accession TEXT NOT NULL, as_of TEXT NOT NULL, "
                     "payload TEXT NOT NULL, PRIMARY KEY (cik, accession))")
    store.db.execute("CREATE TABLE IF NOT EXISTS text_sim_attempt (cik INTEGER NOT NULL, accession TEXT NOT NULL, "
                     "tries INTEGER NOT NULL, last_as_of TEXT NOT NULL, PRIMARY KEY (cik, accession))")


def load_stored(store: EventStore) -> Tuple[Dict[Tuple[int, str], dict], Dict[Tuple[int, str], int]]:
    """已算好的记录 {(cik, accession): 记录}（没有分位）与失败次数。"""
    ensure_tables(store)
    records = {(int(r["cik"]), r["accession"]): json.loads(r["payload"]) for r in store.db.execute("SELECT cik, accession, payload FROM text_sim")}
    tries = {(int(r["cik"]), r["accession"]): int(r["tries"]) for r in store.db.execute("SELECT cik, accession, tries FROM text_sim_attempt")}
    return records, tries


def plan_pairs(facts, entries: Sequence[Mapping], as_of) -> Dict[int, Tuple[Mapping, Mapping]]:
    """每家公司「截至 as_of 已公开」的最新 10-K/10-Q 及其上期同类。只读 filed <= as_of 的申报（时点正确）。"""
    plan: Dict[int, Tuple[Mapping, Mapping]] = {}
    for entry in entries:
        rows = [r for r in facts.filings_as_of(int(entry["cik"]), as_of, PERIODIC_FORMS)
                if r.get("primary_document") and "/" not in r["primary_document"]]
        pair = pick_pair(rows, as_of)
        if pair is not None:
            plan[int(entry["cik"])] = pair
    return plan


def _record_for(entry: Mapping, latest: Mapping, previous: Mapping, comparison: dict) -> dict:
    cik = int(entry["cik"])
    record = dict(comparison)
    record.update({
        "symbol": entry["symbol"], "cik": cik, "name": entry["name"], "market_cap_usd": entry["market_cap_usd"],
        "form": latest["form"], "filed": latest["filed"], "prior_filed": previous["filed"],
        "accession": latest["accession"], "prior_accession": previous["accession"],
        "url": document_url(cik, latest["accession"], latest["primary_document"]),
        "prior_url": document_url(cik, previous["accession"], previous["primary_document"]),
    })
    return record


def collect_records(client: Optional[SecClient], store: EventStore, facts, cache: TextCache, entries: Sequence[Mapping], as_of,
                    max_requests: int = TEXT_SIM_MAX_REQUESTS_PER_RUN, workers: int = 3,
                    log: Callable[[str], None] = print) -> dict:
    """候选池每家公司的最新 10-K/10-Q 对上期同类的措辞相似度。

    - 已算过的（同一份最新申报）直接复用，不再下载；新申报出现才重算；
    - 单轮最多下载 max_requests 份正文（正文缓存命中的不占额度），没有记录的公司优先，剩下的下一轮接着补；
    - 取不到/正文过短的申报累计尝试 TEXT_SIM_MAX_TRIES 次后不再占额度；
    - client 为 None（离线）时只用已有记录和已缓存的正文，不发请求。
    返回 {"records": [...含分位...], "thresholds": {...}, "coverage": {...}}；记录按 symbol 排序，内容只取决于库里的数据。"""
    as_of_iso = iso(as_of)
    stored, tries = load_stored(store)
    plan = plan_pairs(facts, entries, as_of)
    by_cik = {int(e["cik"]): e for e in entries}
    have_any = {cik for (cik, _acc) in stored}
    reused: List[dict] = []
    todo: List[Tuple[Mapping, Mapping, Mapping, int]] = []        # (entry, latest, previous, 需下载份数)
    gave_up = 0
    for cik, (latest, previous) in sorted(plan.items(), key=lambda kv: by_cik[kv[0]]["symbol"]):
        existing = stored.get((cik, latest["accession"]))
        if existing is not None:
            reused.append(_record_for(by_cik[cik], latest, previous, existing))
            continue
        if tries.get((cik, latest["accession"]), 0) >= TEXT_SIM_MAX_TRIES:
            gave_up += 1
            continue
        cost = sum(1 for row in (latest, previous) if not cache.path(row["accession"]).is_file())
        todo.append((by_cik[cik], latest, previous, cost))
    todo.sort(key=lambda item: (int(item[0]["cik"]) in have_any, item[0]["symbol"]))   # 从没有记录的公司先做
    budget = 0 if client is None else max(0, int(max_requests))
    runnable: List[Tuple[Mapping, Mapping, Mapping, int]] = []
    spent = skipped_by_cap = 0
    for item in todo:
        if item[3] == 0 or spent + item[3] <= budget:
            spent += item[3]
            runnable.append(item)
        else:
            skipped_by_cap += 1
    requests_before = client.requests_sent if client is not None else 0

    def work(item):
        entry, latest, previous, _cost = item
        try:
            cik = int(entry["cik"])
            new_text, old_text = fetch_text(client, cache, cik, latest), fetch_text(client, cache, cik, previous)
            if new_text is None or old_text is None:
                return item, None
            return item, compare_documents(new_text, old_text)
        except Exception as exc:  # 单家失败不拖垮整批；记一次尝试并写日志
            log("text-sim failed %s: %s" % (entry["symbol"], type(exc).__name__))
            return item, None

    fresh: List[dict] = []
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (item, comparison) in enumerate(pool.map(work, runnable), 1):
            entry, latest, previous, _cost = item
            if comparison is None:
                failed += 1
                store.db.execute("INSERT INTO text_sim_attempt (cik, accession, tries, last_as_of) VALUES (?,?,1,?) "
                                 "ON CONFLICT(cik, accession) DO UPDATE SET tries = tries + 1, last_as_of = excluded.last_as_of",
                                 (int(entry["cik"]), latest["accession"], as_of_iso))
            else:
                record = _record_for(entry, latest, previous, comparison)
                fresh.append(record)
                store.db.execute("INSERT OR REPLACE INTO text_sim (cik, accession, as_of, payload) VALUES (?,?,?,?)",
                                 (record["cik"], record["accession"], as_of_iso, json.dumps(record, ensure_ascii=False)))
            if index % 100 == 0:
                log("text-sim %d/%d fresh=%d failed=%d requests=%d" % (
                    index, len(runnable), len(fresh), failed, (client.requests_sent - requests_before) if client is not None else 0))
    store.commit()
    records = sorted(reused + fresh, key=lambda r: r["symbol"])
    assert all(r["filed"] <= as_of_iso for r in records), "text similarity record newer than as_of"
    thresholds = add_percentiles(records)
    requests = (client.requests_sent - requests_before) if client is not None else 0
    coverage = {"pool": len(entries), "sampled": len(entries), "computed": len(records), "skipped": len(entries) - len(records),
                "reused": len(reused), "computed_this_run": len(fresh), "failed_this_run": failed, "gave_up": gave_up,
                "no_comparable_pair": len(entries) - len(plan), "deferred_by_request_cap": skipped_by_cap,
                "requests_this_run": requests, "max_requests_per_run": budget}
    log("text-sim: %s" % coverage)
    return {"records": records, "thresholds": thresholds, "coverage": coverage}


def main(argv: Optional[Sequence[str]] = None) -> int:
    from .event_collect import load_pool, make_client

    parser = argparse.ArgumentParser(prog="signal_lattice.evidence.text_similarity")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--sample", type=int, default=300, help="首次按市值分层抽样的家数")
    parser.add_argument("--max-cap", type=float, default=5e9)
    parser.add_argument("--db", default="events.sqlite")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    entries, _ = load_pool(args.universe, max_cap_usd=args.max_cap)
    sample = stratified_sample(entries, args.sample)
    client = make_client(args.run_dir / "ev-cache")
    store = EventStore(args.run_dir / args.db)
    result = run_batch(client, store, TextCache(args.run_dir / "text-cache"), sample, args.as_of)
    out = args.out or (args.run_dir / ("text-similarity-%s.json" % args.as_of))
    coverage = {"pool": len(entries), "sampled": len(sample), "computed": len(result["records"]), "skipped": result["skipped"]}
    out.write_text(json.dumps({"as_of": args.as_of, "coverage": coverage, "thresholds": result["thresholds"],
                               "records": result["records"]}, ensure_ascii=False, indent=1), "utf-8")
    print("wrote", out, coverage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
