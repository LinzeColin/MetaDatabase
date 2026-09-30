"""把抓到的数据 + 模型 + 账本组装成一份日报（纯数据，不含 HTML）。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, ledger as ledger_mod
from .dataset import Dataset, prepare
from .model import Fitted, OTHER_GROUP, fit, outcome_index

SYD = ZoneInfo(config.REPORT_TZ)
WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def comp_zh(code: str) -> str:
    if code in config.REPORT_COMPS:
        return config.REPORT_COMPS[code]["zh"]
    return config.TRAIN_ONLY_COMPS.get(code, code)


def _kick_dt(m: dict) -> tuple[datetime, bool]:
    if m.get("kickoff_utc"):
        return datetime.strptime(m["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc), True
    y, mo, d = (int(x) for x in m["date"].split("-"))
    return datetime(y, mo, d, 12, 0, tzinfo=timezone.utc), False


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _team_view(ds: Dataset, fitted: Fitted, k: str) -> dict:
    return {"key": k, "name": ds.name(k), "zh": ds.zh(k), "n_eff": round(fitted.n_eff.get(k, 0.0), 1),
            "known": k in fitted.n_eff}


def risk_flags(ds: Dataset, fitted: Fitted, m: dict, pred: dict, fx_date: str) -> dict:
    flags: list[dict] = []
    score = 0
    for side, k in (("主队", m["hk"]), ("客队", m["ak"])):
        nm = ds.zh(k) or ds.name(k)
        ne = fitted.n_eff.get(k)
        if ne is None:
            flags.append({"code": "no_history", "text": f"{side}{nm}：模型里没有它的任何比赛记录，按同组平均处理"})
            score += 2
        elif ne < 12:
            flags.append({"code": "small_sample", "text": f"{side}{nm}：历史样本少（加权约 {ne:.0f} 场），评级偏保守"})
            score += 1
        last = fitted.last_played.get(k)
        if last:
            rest = (datetime.fromisoformat(fx_date) - datetime.fromisoformat(last)).days
            if 0 <= rest < 4:
                flags.append({"code": "short_rest", "text": f"{side}{nm}：距上一场已收录赛果仅 {rest} 天，注意体能与轮换"})
                score += 1
        if m["comp"] != "uefa.cl":
            leagues = ds.team_leagues.get(k, {})
            prev = [s for s in leagues if s < config.CURRENT_SEASON]
            if prev and leagues.get(max(prev)) not in (None, m["comp"]):
                flags.append({"code": "moved_league", "text": f"{side}{nm}：上赛季在{comp_zh(leagues[max(prev)])}，"
                                                             f"评级部分来自下级/其他联赛，跨级别有偏差"})
                score += 1
    if m["comp"] == "uefa.cl":
        gh, ga = fitted.team_group.get(m["hk"], OTHER_GROUP), fitted.team_group.get(m["ak"], OTHER_GROUP)
        if gh != ga or gh == OTHER_GROUP:
            flags.append({"code": "cross_league", "text": "跨联赛对阵：强弱只能靠欧冠交手间接估计，比国内联赛更不稳"})
            score += 1
    iv = pred["interval"]
    width = max(iv[k][1] - iv[k][0] for k in ("home", "draw", "away"))
    if width > 0.30:
        flags.append({"code": "wide_interval", "text": f"模型不确定度高：某一结果的 10%-90% 区间宽达 {width * 100:.0f} 个百分点"})
        score += 1
    top = max(pred["p_home"], pred["p_draw"], pred["p_away"])
    if top >= 0.70:
        flags.append({"code": "heavy_favourite", "text": f"一边倒：热门胜率约 {_pct(top)}，剩下 {_pct(1 - top)} 属于冷门/平局空间"})
    flags.append({"code": "unmodelled", "text": "伤病、首发、天气、动机等模型看不到的信息不在其中"})
    grade = "低" if score <= 1 else ("中" if score == 2 else "高")
    return {"grade": grade, "score": score, "flags": flags}


def strength_tables(ds: Dataset, fitted: Fitted) -> dict[str, list[dict]]:
    """每个赛事一张「实力值」表：对平均球队、中立场、每场预期净胜球。"""
    ix = fitted._ix
    th = fitted.theta
    keys = fitted.teams
    att = {}
    dfn = {}
    for k in keys:
        g = fitted._group_idx(k)
        i = ix["team"][k]
        att[k] = th[ix["A"] + g] + th[ix["a"] + i]
        dfn[k] = th[ix["D"] + g] + th[ix["d"] + i]
    # 参照系：本页覆盖赛事当季所有球队的平均水平（不含低级别联赛，否则强队的数字会被拉高）
    ref_keys = sorted({k for m in ds.matches if m["comp"] in config.REPORT_COMPS and m["season"] == config.CURRENT_SEASON
                       for k in (m["hk"], m["ak"]) if k in att}) or keys
    ref_att = sum(att[k] for k in ref_keys) / len(ref_keys)
    ref_def = sum(dfn[k] for k in ref_keys) / len(ref_keys)
    dom = [c for c in config.REPORT_COMPS if c != "uefa.cl" and c in fitted.comps]
    mu0 = float(sum(th[fitted.comps.index(c)] for c in dom) / max(len(dom), 1))
    out: dict[str, list[dict]] = {}
    for comp in config.REPORT_COMPS:
        teams = sorted({k for m in ds.matches if m["comp"] == comp and m["season"] == config.CURRENT_SEASON
                        for k in (m["hk"], m["ak"])})
        rows = []
        for k in teams:
            if k not in att:
                continue
            gf = math.exp(mu0 + att[k] - ref_def)
            ga = math.exp(mu0 + ref_att - dfn[k])
            rows.append({"key": k, "name": ds.name(k), "zh": ds.zh(k), "rating": round(gf - ga, 2),
                         "goals_for": round(gf, 2), "goals_against": round(ga, 2),
                         "n_eff": round(fitted.n_eff.get(k, 0.0), 1)})
        rows.sort(key=lambda r: -r["rating"])
        out[comp] = rows
    return out


def source_summary(sources: dict) -> list[dict]:
    """把 60 多个来源文件汇成 3 行给人看；出错的文件单列。"""
    fam: dict[str, dict] = {}
    labels = {"openfootball-league": "openfootball 联赛赛程赛果（CC0）",
              "openfootball-cl": "openfootball 欧冠历史赛果（CC0）",
              "wikipedia-cl": "Wikipedia 欧冠当季赛程赛果（CC BY-SA 4.0）"}
    for name, info in sources.items():
        typ, comp, _season = name.split(":")
        key = "wikipedia-cl" if typ == "wikipedia" else ("openfootball-cl" if comp == "uefa.cl" else "openfootball-league")
        f = fam.setdefault(key, {"id": key, "label": labels[key], "files": 0, "ok": 0, "absent": 0, "failed": [],
                                 "stale_cache": [], "latest_result": None, "fetched_at": None, "upstream_updated": None})
        f["files"] += 1
        if info.get("absent"):
            f["absent"] += 1
        elif info.get("ok"):
            f["ok"] += 1
        else:
            f["failed"].append({"name": name, "error": info.get("error", "")})
        if info.get("stale_cache_from"):
            f["stale_cache"].append({"name": name, "from": info["stale_cache_from"]})
        lr = info.get("latest_result")
        if lr and (f["latest_result"] is None or lr > f["latest_result"]):
            f["latest_result"] = lr
        fa = info.get("fetched_at")
        if fa and (f["fetched_at"] is None or fa > f["fetched_at"]):
            f["fetched_at"] = fa
        if info.get("upstream_updated"):
            f["upstream_updated"] = info["upstream_updated"]
    return [fam[k] for k in ("openfootball-league", "openfootball-cl", "wikipedia-cl") if k in fam]


SOURCE_REVIEW = [
    {"name": "openfootball（GitHub）", "verdict": "采用", "why": "CC0 公有领域，明确允许任意使用；联赛赛程赛果与欧冠历史。每周自动更新，赛果通常滞后不超过一周。"},
    {"name": "Wikipedia 官方 API", "verdict": "采用", "why": "CC BY-SA 4.0，官方 API 允许带说明性 User-Agent 的程序读取；用于当季欧冠（openfootball 尚未收录）。页面要署名。"},
    {"name": "football-data.co.uk（含多家博彩公司赔率）", "verdict": "不用", "why": "站点声明仅限个人使用，禁止用于商业或「自动化 bot/爬虫/AI 的数据产品」，robots.txt 也屏蔽 AI 爬虫。它是唯一免费的赔率来源，所以盘口对比因此为空。"},
    {"name": "The Odds API", "verdict": "不用", "why": "需要注册取得 API key；仓库 Secrets 与服务器上都没有可复用的 key，不注册、不付费。"},
    {"name": "TAB 官网公开盘口", "verdict": "不用", "why": "被判定为 ai_controlled_access_rejected（拒绝 AI 受控访问），按硬边界失败关闭，不绕过。"},
    {"name": "FixtureDownload", "verdict": "不用", "why": "条款禁止把内容转存到其他网站或再发布，本页是公开网页，会违反。"},
    {"name": "TheSportsDB 免费档", "verdict": "不用", "why": "免费 key 只面向开发测试，实测欧冠「下一场」只返回 1 条、赛季接口最多返回 5 条，数据不完整。"},
    {"name": "ClubElo API", "verdict": "不用", "why": "2026-09-30 实测 Fixtures 接口返回「已停用」，按日期取评级的接口返回 502。"},
]


def build(raw: dict, now: datetime, ledger: dict, backtest: dict | None) -> tuple[dict, dict]:
    ds = prepare(raw["matches"])
    today = now.astimezone(SYD).date()
    as_of = (now.date() + timedelta(days=1)).isoformat()
    fitted = fit(ds.played, ds.team_group, as_of)
    report_comps = set(config.REPORT_COMPS)

    freq: dict[str, list[float]] = {}
    for tm in ds.played:
        if tm.comp in report_comps:
            freq.setdefault(tm.comp, [0, 0, 0])[outcome_index(tm.hg, tm.ag)] += 1

    def base(comp: str) -> list[float]:
        f = freq.get(comp) or [1, 1, 1]
        t = sum(f)
        return [x / t for x in f]

    horizon = now + timedelta(days=config.HORIZON_DAYS)
    fixtures: list[dict] = []
    pending: list[dict] = []
    for m in ds.matches:
        if m["hg"] is not None or m["comp"] not in report_comps:
            continue
        kdt, known = _kick_dt(m)
        if kdt < now - timedelta(hours=3):
            if kdt >= now - timedelta(days=config.RECENT_DAYS):
                pending.append({"comp": m["comp"], "comp_zh": comp_zh(m["comp"]), "date": m["date"],
                                "home": ds.zh(m["hk"]) or ds.name(m["hk"]), "away": ds.zh(m["ak"]) or ds.name(m["ak"])})
            continue
        if kdt > horizon:
            continue
        pred = fitted.predict(m["hk"], m["ak"], m["comp"], draws=config.UNCERTAINTY_DRAWS)
        ksyd = kdt.astimezone(SYD)
        fx = {
            "id": ledger_mod.match_id(m["comp"], m["date"], m["hk"], m["ak"]),
            "comp": m["comp"], "comp_zh": comp_zh(m["comp"]), "round": m.get("round", ""),
            "kickoff_utc": m.get("kickoff_utc"), "time_known": known,
            "kickoff_syd": ksyd.strftime("%Y-%m-%dT%H:%M"), "syd_date": ksyd.date().isoformat(),
            "syd_weekday": WEEKDAY_ZH[ksyd.weekday()], "local_date": m["date"],
            "days_ahead": (ksyd.date() - today).days,
            "home": _team_view(ds, fitted, m["hk"]), "away": _team_view(ds, fitted, m["ak"]),
            "p": {"home": pred["p_home"], "draw": pred["p_draw"], "away": pred["p_away"]},
            "interval": pred["interval"], "lam": [pred["lam_home"], pred["lam_away"]],
            "exp_goals": [pred["exp_goals_home"], pred["exp_goals_away"]],
            "p_over25": pred["p_over25"], "p_btts": pred["p_btts"], "top_scores": pred["top_scores"],
            "risk": risk_flags(ds, fitted, m, pred, m["date"]),
            "market": {"available": False, "note": "暂无合法盘口源，本场不做盘口对比、不算期望值与凯利"},
        }
        fixtures.append(fx)
        ledger_mod.upsert_prediction(
            ledger, mid=fx["id"], now=now, comp=m["comp"], day=m["date"], kickoff_utc=m.get("kickoff_utc"),
            home=m["hk"], away=m["ak"], home_name=ds.zh(m["hk"]) or ds.name(m["hk"]),
            away_name=ds.zh(m["ak"]) or ds.name(m["ak"]),
            p=[pred["p_home"], pred["p_draw"], pred["p_away"]], p_base=base(m["comp"]),
            lam=[pred["lam_home"], pred["lam_away"]], model=config.MODEL_VERSION)
    fixtures.sort(key=lambda f: (f["kickoff_syd"], f["comp"]))

    results = {ledger_mod.match_id(m["comp"], m["date"], m["hk"], m["ak"]): (m["hg"], m["ag"])
               for m in ds.matches if m["hg"] is not None and m["comp"] in report_comps}
    newly = ledger_mod.settle(ledger, results, now)
    ledger_mod.prune(ledger, now)

    recent: list[dict] = []
    since = (today - timedelta(days=config.RECENT_DAYS)).isoformat()
    for m in ds.matches:
        if m["hg"] is None or m["comp"] not in report_comps or m["date"] < since:
            continue
        mid = ledger_mod.match_id(m["comp"], m["date"], m["hk"], m["ak"])
        e = ledger.get("entries", {}).get(mid)
        recent.append({"comp_zh": comp_zh(m["comp"]), "date": m["date"],
                       "home": ds.zh(m["hk"]) or ds.name(m["hk"]), "away": ds.zh(m["ak"]) or ds.name(m["ak"]),
                       "score": [m["hg"], m["ag"]], "outcome": outcome_index(m["hg"], m["ag"]),
                       "predicted": e["p"] if e else None, "hit": e["score"]["hit"] if e and e.get("score") else None})
    recent.sort(key=lambda r: r["date"], reverse=True)

    latest_by_comp: dict[str, str] = {}
    for m in ds.matches:
        if m["hg"] is not None and m["season"] == config.CURRENT_SEASON and m["comp"] in report_comps:
            if m["date"] > latest_by_comp.get(m["comp"], ""):
                latest_by_comp[m["comp"]] = m["date"]

    today_iso = today.isoformat()
    todays = [f for f in fixtures if f["syd_date"] == today_iso]
    report = {
        "schema": 1,
        "report_date": today_iso,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_version": config.MODEL_VERSION,
        "model": {"n_matches": fitted.n_matches, "half_life_days": config.HALF_LIFE_DAYS, "rho": round(fitted.rho, 4),
                  "home_advantage": round(math.exp(float(fitted.theta[len(fitted.comps)])), 3),
                  "fit_as_of": as_of},
        "fixtures": fixtures,
        "matches_today": len(todays),
        "pending_results": pending,
        "recent_results": recent,
        "strength": strength_tables(ds, fitted),
        "latest_result_by_comp": {comp_zh(c): d for c, d in sorted(latest_by_comp.items())},
        "newest_result": max(latest_by_comp.values()) if latest_by_comp else None,
        "sources": source_summary(raw["sources"]),
        "source_review": SOURCE_REVIEW,
        "backtest": backtest,
        "live_track": ledger_mod.summary(ledger),
        "ledger_newly_scored": newly,
        "coverage": {
            "covered": [{"code": c, "zh": v["zh"], "en": v["en"], "why": v["why"]} for c, v in config.REPORT_COMPS.items()],
            "training_only": [{"code": c, "zh": z} for c, z in config.TRAIN_ONLY_COMPS.items()],
            "not_covered": [{"zh": "澳超（A-League）",
                             "why": "2026-27 赛季 10-16 才开赛；openfootball 的澳超数据只到 2024-25；"
                                    "FixtureDownload 条款禁止转存再发布、TheSportsDB 免费档只给零星几场，"
                                    "都不满足「条款允许自动访问 + 数据完整」，不拿不合规来源凑数。开季后再评估。"}],
        },
    }
    return report, ledger
