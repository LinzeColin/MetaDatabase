"""预测账本：开球前最后一次预测被冻结，赛果出来后打分。

这是「报告可信度」的活证据：不是回测，而是每天真实发出去的预测事后对不对。
账本只增不改已冻结条目；缺天时下一次运行自然补上（赛果到了就打分）。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .model import outcome_index

KEEP_DAYS = 400


def match_id(comp: str, day: str, hk: str, ak: str) -> str:
    return f"{comp}|{day}|{hk}|{ak}"


def _kick(entry: dict) -> datetime | None:
    k = entry.get("kickoff_utc")
    return datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) if k else None


def upsert_prediction(ledger: dict, *, mid: str, now: datetime, comp: str, day: str, kickoff_utc: str | None,
                      home: str, away: str, home_name: str, away_name: str, p: list[float], p_base: list[float],
                      lam: list[float], model: str) -> None:
    """开球前每次运行都刷新预测；开球后不再改（冻结）。"""
    entries = ledger.setdefault("entries", {})
    cur = entries.get(mid)
    if cur and cur.get("frozen"):
        return
    kick = _kick({"kickoff_utc": kickoff_utc})
    if kick is not None and kick <= now:
        # 开球后才第一次看到这场：没有「赛前预测」，不补记，避免事后诸葛
        if cur:
            cur["frozen"] = True
        return
    entries[mid] = {
        "comp": comp, "date": day, "kickoff_utc": kickoff_utc, "home": home, "away": away,
        "home_name": home_name, "away_name": away_name, "p": [round(x, 5) for x in p],
        "p_base": [round(x, 5) for x in p_base], "lam": [round(x, 4) for x in lam], "model": model,
        "first_predicted_at": (cur or {}).get("first_predicted_at") or now.strftime("%Y-%m-%dT%H:%MZ"),
        "predicted_at": now.strftime("%Y-%m-%dT%H:%MZ"), "frozen": False, "result": None, "score": None,
    }


def settle(ledger: dict, results: dict[str, tuple[int, int]], now: datetime) -> int:
    """给已开球的条目冻结，并对有赛果的条目打分。返回本次新打分的条数。"""
    n = 0
    for mid, e in ledger.get("entries", {}).items():
        kick = _kick(e)
        if not e.get("frozen") and kick is not None and kick <= now:
            e["frozen"] = True
        if e.get("score") is None and mid in results:
            hg, ag = results[mid]
            o = outcome_index(hg, ag)
            p, pb = e["p"], e["p_base"]
            e["result"] = [hg, ag]
            e["frozen"] = True
            e["score"] = {
                "outcome": o,
                "logloss": -math.log(max(p[o], 1e-9)),
                "logloss_base": -math.log(max(pb[o], 1e-9)),
                "brier": sum((p[i] - (1.0 if i == o else 0.0)) ** 2 for i in range(3)),
                "brier_base": sum((pb[i] - (1.0 if i == o else 0.0)) ** 2 for i in range(3)),
                "hit": max(range(3), key=lambda i: p[i]) == o,
            }
            n += 1
    return n


def prune(ledger: dict, now: datetime) -> None:
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    ledger["entries"] = {k: v for k, v in ledger.get("entries", {}).items() if v["date"] >= cutoff}


def summary(ledger: dict) -> dict:
    sc = [e["score"] for e in ledger.get("entries", {}).values() if e.get("score")]
    pending = sum(1 for e in ledger.get("entries", {}).values() if not e.get("score"))
    if not sc:
        return {"n": 0, "pending": pending}
    n = len(sc)
    return {"n": n, "pending": pending,
            "logloss": sum(s["logloss"] for s in sc) / n, "logloss_base": sum(s["logloss_base"] for s in sc) / n,
            "brier": sum(s["brier"] for s in sc) / n, "brier_base": sum(s["brier_base"] for s in sc) / n,
            "accuracy": sum(1 for s in sc if s["hit"]) / n}
