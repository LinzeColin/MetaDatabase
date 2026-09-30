"""测试用的合成数据：已知强弱的小联赛 + 欧冠，全部离线。"""

from __future__ import annotations

import random
from datetime import date, timedelta

import numpy as np

STRENGTH = {"Alpha": 0.6, "Bravo": 0.3, "Charlie": 0.0, "Delta": -0.3, "Echo": -0.6, "Foxtrot": -0.2}


def synth_league(comp: str, season: str, start: date, seed: int, teams: dict[str, float] | None = None,
                 played_until: date | None = None, tz_time: str = "15:00") -> list[dict]:
    rng = np.random.default_rng(seed)
    teams = teams or STRENGTH
    names = list(teams)
    out, d = [], start
    for rnd in range(2):
        for i, h in enumerate(names):
            for j, a in enumerate(names):
                if i == j:
                    continue
                d = start + timedelta(days=(len(out) // 3) * 3)
                lam_h = np.exp(0.25 + 0.2 + teams[h] - teams[a] * 0.8)
                lam_a = np.exp(0.25 + teams[a] - teams[h] * 0.8)
                played = played_until is None or d <= played_until
                out.append({"comp": comp, "season": season, "date": d.isoformat(),
                            "kickoff_utc": f"{d.isoformat()}T{tz_time}Z", "home": h, "away": a,
                            "hg": int(rng.poisson(lam_h)) if played else None,
                            "ag": int(rng.poisson(lam_a)) if played else None,
                            "round": f"Matchday {len(out) // 3 + 1}", "source": "test"})
        break
    return out


def ok_info(n: int, latest: str = "2026-09-20") -> dict:
    return {"ok": True, "url": "test", "n": n, "latest_result": latest, "fetched_at": "2026-09-30T00:00:00Z"}


def synth_raw(now_date: date) -> dict:
    """五个报告联赛（各 6 队，去掉重名影响）+ 欧冠历史，结构与 sources.fetch_all 的返回一致。"""
    by_source: dict[str, list[dict]] = {}
    sources: dict[str, dict] = {}
    seed = 1
    for comp in ("en.1", "es.1", "de.1", "it.1", "fr.1"):
        teams = {f"{comp}-{n}": v for n, v in STRENGTH.items()}
        past = synth_league(comp, "2025-26", date(2025, 8, 20), seed, teams)
        seed += 1
        cur = synth_league(comp, "2026-27", now_date - timedelta(days=60), seed, teams,
                           played_until=now_date - timedelta(days=1))
        seed += 1
        for season, rows in (("2025-26", past), ("2026-27", cur)):
            name = f"openfootball:{comp}:{season}"
            by_source[name] = rows
            sources[name] = ok_info(len(rows))
    # 欧冠历史：把各联赛的队连起来
    rng = random.Random(3)
    cl = []
    comps = ["en.1", "es.1", "de.1", "it.1", "fr.1"]
    for k in range(120):
        ca, cb = rng.sample(comps, 2)
        ta, tb = rng.choice(list(STRENGTH)), rng.choice(list(STRENGTH))
        d = date(2025, 9, 15) + timedelta(days=k * 2)
        la = np.exp(0.3 + 0.2 + STRENGTH[ta] - STRENGTH[tb] * 0.8)
        lb = np.exp(0.3 + STRENGTH[tb] - STRENGTH[ta] * 0.8)
        cl.append({"comp": "uefa.cl", "season": "2025-26", "date": d.isoformat(), "kickoff_utc": None,
                   "home": f"{ca}-{ta}", "away": f"{cb}-{tb}", "hg": int(np.random.default_rng(k).poisson(la)),
                   "ag": int(np.random.default_rng(k + 999).poisson(lb)), "round": "League, Matchday 1", "source": "test"})
    cl = [m for m in cl if m["home"] != m["away"]]
    by_source["openfootball:uefa.cl:2025-26"] = cl
    sources["openfootball:uefa.cl:2025-26"] = ok_info(len(cl), "2026-05-30")
    matches = [m for rows in by_source.values() for m in rows]
    return {"matches": matches, "by_source": by_source, "sources": sources, "fetched_at": "2026-09-30T00:00:00Z"}
