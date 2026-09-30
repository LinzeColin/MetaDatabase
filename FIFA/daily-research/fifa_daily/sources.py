"""数据源：只取免 key、条款明确允许自动访问的公开数据。

- openfootball（CC0 公有领域）：各联赛赛程赛果（football.json）与欧冠历史（Football.TXT）。
- Wikipedia（CC BY-SA 4.0，官方 API，带说明性 User-Agent）：当季欧冠联赛阶段的赛程赛果。

本模块只做「下载 + 解析」，不做任何联网以外的副作用；解析函数都是纯函数，测试用固定样本。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import config


@dataclass
class Match:
    comp: str               # en.1 / uefa.cl ...
    season: str             # 2026-27
    date: str               # 场地当地日期 YYYY-MM-DD（无开球时间时用它排序）
    kickoff_utc: str | None  # YYYY-MM-DDTHH:MMZ；未知则 None
    home: str
    away: str
    hg: int | None
    ag: int | None
    round: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class FetchError(RuntimeError):
    pass


class NotFound(FetchError):
    """上游没有这个文件（例如某联赛当季文件尚未发布）——这不算故障。"""


def fetch_text(url: str, *, retries: int = 3, timeout: int = 40, headers: dict | None = None) -> str:
    """带重试的 GET。失败抛 FetchError（调用方决定降级还是中止）。"""
    last: Exception | None = None
    hdrs = {"User-Agent": config.USER_AGENT, "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 404:
                raise NotFound(f"404 {url}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"{url}: {last}")


# ---------------------------------------------------------------- 时间
def to_utc(day: str, hhmm: str | None, tz: str) -> str | None:
    """场地当地时间 -> UTC 字符串；没有开球时间返回 None。"""
    if not hhmm:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})", hhmm.strip())
    if not m:
        return None
    y, mo, d = (int(x) for x in day.split("-"))
    local = datetime(y, mo, d, int(m.group(1)), int(m.group(2)), tzinfo=ZoneInfo(tz))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# ---------------------------------------------------------------- openfootball football.json
def parse_football_json(obj: dict, comp: str, season: str, tz: str) -> list[Match]:
    out: list[Match] = []
    for m in obj.get("matches", []):
        # 不同赛季的文件里 score 有三种写法：{"ft":[h,a],"ht":[..]}、[h,a]（90 分钟比分）、缺失/None
        score = m.get("score")
        ft = score.get("ft") if isinstance(score, dict) else score
        hg, ag = (int(ft[0]), int(ft[1])) if isinstance(ft, list) and len(ft) == 2 else (None, None)
        out.append(
            Match(
                comp=comp, season=season, date=m["date"],
                kickoff_utc=to_utc(m["date"], m.get("time"), tz),
                home=m["team1"], away=m["team2"], hg=hg, ag=ag,
                round=str(m.get("round", "")), source="openfootball",
            )
        )
    return out


# ---------------------------------------------------------------- openfootball Football.TXT（欧冠历史）
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
_DATE_LINE = re.compile(r"^\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
_MATCH_LINE = re.compile(r"^\s*(?:\d{1,2}:\d{2}\s+)?(?P<h>.+?)\s+v\s+(?P<a>.+?)\s{2,}(?P<tail>\d+-\d+.*?)\s*$")
_TAIL = re.compile(
    r"^(?:(?P<pen>\d+-\d+)\s+pen\.\s+)?(?P<main>\d+-\d+)(?P<aet>\s+a\.e\.t\.)?"
    r"(?:\s+\((?P<p1>\d+-\d+)(?:,\s*(?P<p2>\d+-\d+))?\))?$"
)
_STAGE = re.compile(r"^▪\s*(.+?)\s*$")


def _pair(s: str) -> tuple[int, int]:
    a, b = s.split("-")
    return int(a), int(b)


def parse_football_txt(text: str, comp: str, season: str) -> list[Match]:
    """解析 Football.TXT。90 分钟比分：有加时时取括号里的第一个比分，否则取主比分。"""
    start_year = int(season[:4])
    cur_date: str | None = None
    stage = ""
    out: list[Match] = []
    for line in text.splitlines():
        sm = _STAGE.match(line)
        if sm:
            stage = sm.group(1)
            continue
        dm = _DATE_LINE.match(line)
        if dm:
            mon, day, year = _MONTHS[dm.group(1)], int(dm.group(2)), dm.group(3)
            y = int(year) if year else (start_year if mon >= 7 else start_year + 1)
            cur_date = f"{y:04d}-{mon:02d}-{day:02d}"
            continue
        mm = _MATCH_LINE.match(line)
        if not mm or not cur_date:
            continue
        tm = _TAIL.match(mm.group("tail").strip())
        if not tm:
            continue
        if tm.group("aet"):
            if not tm.group("p1"):
                continue
            hg, ag = _pair(tm.group("p1"))
        else:
            hg, ag = _pair(tm.group("main"))
        out.append(Match(comp=comp, season=season, date=cur_date, kickoff_utc=None,
                         home=mm.group("h"), away=mm.group("a"), hg=hg, ag=ag,
                         round=stage, source="openfootball"))
    return out


# ---------------------------------------------------------------- Wikipedia（欧冠当季）
_BOX = re.compile(r"\{\{#invoke:Football box\|main\n(.*?)\n\}\}", re.S)
_FIELD = lambda name: re.compile(r"^\|" + name + r"[ \t]*=[ \t]*(.*)$", re.M)  # noqa: E731
_F_DATE, _F_TIME, _F_T1, _F_T2, _F_SCORE = (_FIELD(n) for n in ("date", "time", "team1", "team2", "score"))
_START_DATE = re.compile(r"\{\{Start date\|(\d{4})\|(\d{1,2})\|(\d{1,2})")
_HEADING = re.compile(r"^={2,4}\s*(.+?)\s*={2,4}\s*$", re.M)


def _wiki_team(raw: str) -> str:
    s = re.sub(r"\{\{fbaicon\|[^}]*\}\}", "", raw)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>.*?(?:</[^>]+>|$)", "", s)
    return re.sub(r"\s+", " ", s.replace("&nbsp;", " ")).strip()


def parse_wiki_boxes(wikitext: str, comp: str, season: str, tz: str) -> list[Match]:
    """解析 Wikipedia 的 Football box 模板。时间为 UEFA 公布的 CET/CEST（页面开头声明）。"""
    out: list[Match] = []
    # 记录每个 box 之前最近的小节标题作为轮次
    headings = [(m.start(), m.group(1)) for m in _HEADING.finditer(wikitext)]
    for bm in _BOX.finditer(wikitext):
        body = bm.group(1)
        dm = _F_DATE.search(body)
        sd = _START_DATE.search(dm.group(1)) if dm else None
        t1, t2 = _F_T1.search(body), _F_T2.search(body)
        if not (sd and t1 and t2):
            continue
        day = f"{int(sd.group(1)):04d}-{int(sd.group(2)):02d}-{int(sd.group(3)):02d}"
        tmm = _F_TIME.search(body)
        hhmm = None
        if tmm:
            m = re.match(r"\s*(\d{1,2}:\d{2})", tmm.group(1))
            hhmm = m.group(1) if m else None
        sc = _F_SCORE.search(body)
        hg = ag = None
        if sc:
            m = re.match(r"^\s*(\d+)\s*[–-]\s*(\d+)\s*$", re.sub(r"<!--.*?-->", "", sc.group(1)))
            if m:
                hg, ag = int(m.group(1)), int(m.group(2))
        rnd = ""
        for pos, title in headings:
            if pos < bm.start():
                rnd = title
        out.append(Match(comp=comp, season=season, date=day, kickoff_utc=to_utc(day, hhmm, tz),
                         home=_wiki_team(t1.group(1)), away=_wiki_team(t2.group(1)),
                         hg=hg, ag=ag, round=rnd, source="wikipedia"))
    return out


def fetch_wikipedia(title: str) -> tuple[str, str]:
    """返回 (wikitext, 页面最新修订时间 ISO)。页面不存在抛 FetchError。"""
    qs = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "rvprop": "content|timestamp", "rvslots": "main",
        "titles": title, "format": "json", "formatversion": "2",
    })
    data = json.loads(fetch_text(f"{config.WIKI_API}?{qs}"))
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        raise NotFound(f"wikipedia page missing: {title}")
    rev = pages[0]["revisions"][0]
    return rev["slots"]["main"]["content"], rev["timestamp"]


# ---------------------------------------------------------------- 汇总抓取
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_football_json(comp: str, season: str) -> tuple[str, list[Match], dict]:
    name = f"openfootball:{comp}:{season}"
    url = f"{config.FOOTBALL_JSON_BASE}/{season}/{comp}.json"
    try:
        got = parse_football_json(json.loads(fetch_text(url)), comp, season, config.COMP_TZ[comp])
    except NotFound:
        return name, [], {"ok": True, "absent": True, "url": url, "n": 0, "fetched_at": _now_iso()}
    except (FetchError, json.JSONDecodeError, KeyError) as exc:
        return name, [], {"ok": False, "url": url, "error": str(exc)[:160], "fetched_at": _now_iso()}
    played = [m.date for m in got if m.hg is not None]
    return name, got, {"ok": True, "url": url, "n": len(got),
                       "latest_result": max(played) if played else None, "fetched_at": _now_iso()}


def _one_cl_txt(season: str) -> tuple[str, list[Match], dict]:
    name = f"openfootball:uefa.cl:{season}"
    url = f"{config.CL_TXT_BASE}/{season}/cl.txt"
    try:
        got = parse_football_txt(fetch_text(url), "uefa.cl", season)
        if not got:
            raise FetchError("解析出 0 场（文件结构可能变了）")
    except FetchError as exc:
        return name, [], {"ok": False, "url": url, "error": str(exc)[:160], "fetched_at": _now_iso()}
    return name, got, {"ok": True, "url": url, "n": len(got),
                       "latest_result": max(m.date for m in got), "fetched_at": _now_iso()}


def _wiki_cl() -> tuple[str, list[Match], dict]:
    name = f"wikipedia:uefa.cl:{config.CURRENT_SEASON}"
    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(config.WIKI_CL_PAGE)
    try:
        text, rev_ts = fetch_wikipedia(config.WIKI_CL_PAGE)
        got = parse_wiki_boxes(text, "uefa.cl", config.CURRENT_SEASON, config.COMP_TZ["uefa.cl"])
        if not got:
            raise FetchError("解析出 0 场（页面结构可能变了）")
    except FetchError as exc:
        return name, [], {"ok": False, "url": url, "error": str(exc)[:160], "fetched_at": _now_iso()}
    played = [m.date for m in got if m.hg is not None]
    return name, got, {"ok": True, "url": url, "n": len(got),
                       "latest_result": max(played) if played else None,
                       "upstream_updated": rev_ts, "fetched_at": _now_iso()}


def fetch_all(workers: int = 8) -> dict:
    """抓全部来源。返回 {"matches": [...], "sources": {name: {...}}, "fetched_at": ...}。

    单个来源失败只记录在 sources 里（ok=False + error），由调用方决定是否还能出报告；
    绝不静默吞掉。上游没有的文件（404）记 absent，不算故障。
    """
    from concurrent.futures import ThreadPoolExecutor

    jobs = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for season in config.FOOTBALL_JSON_SEASONS:
            for comp in [*config.REPORT_COMPS, *config.TRAIN_ONLY_COMPS]:
                if comp == "uefa.cl":
                    continue
                jobs.append(pool.submit(_one_football_json, comp, season))
        for season in config.CL_TXT_SEASONS:
            jobs.append(pool.submit(_one_cl_txt, season))
        jobs.append(pool.submit(_wiki_cl))
        results = [j.result() for j in jobs]

    matches: list[dict] = []
    sources: dict[str, dict] = {}
    by_source: dict[str, list[dict]] = {}
    for name, got, info in results:
        rows = [m.to_dict() for m in got]
        matches.extend(rows)
        by_source[name] = rows
        sources[name] = info
    return {"matches": matches, "by_source": by_source, "sources": sources, "fetched_at": _now_iso()}
