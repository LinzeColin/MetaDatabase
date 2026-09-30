"""滚动回测：每个截止日只用「截止日之前」的数据拟合，再预测其后一段时间内已经踢完的比赛。

对照基线 = 训练数据里同赛事的主胜/平/客胜历史频率（什么模型都不用时的最佳常数预测）。
指标：对数损失（越低越好）、Brier 分数（越低越好）、命中率；另附校准表（预测概率 vs 实际发生率）。
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from . import config
from .dataset import Dataset, team_groups
from .model import fit, outcome_index

_BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]


def walk_forward(ds: Dataset, report_comps: set[str], end: str, days: int = config.BACKTEST_DAYS,
                 step: int = config.BACKTEST_STEP_DAYS) -> dict:
    end_d = date.fromisoformat(end)
    cutoffs = []
    c = end_d - timedelta(days=days)
    while c < end_d:
        cutoffs.append(c)
        c += timedelta(days=step)

    rows = []  # (p_model[3], p_base[3], outcome)
    for c in cutoffs:
        c_s, n_s = c.isoformat(), min(c + timedelta(days=step), end_d).isoformat()
        test = [m for m in ds.matches if m["hg"] is not None and m["comp"] in report_comps and c_s <= m["date"] < n_s]
        if not test:
            continue
        groups, _ = team_groups(ds.matches, before=c_s)
        try:
            fitted = fit(ds.played, {**{k: "OTHER" for k in ds.team_group}, **groups}, c_s)
        except ValueError:
            continue
        freq: dict[str, list[float]] = {}
        for m in ds.played:
            if m.date < c_s and m.comp in report_comps:
                freq.setdefault(m.comp, [0, 0, 0])[outcome_index(m.hg, m.ag)] += 1
        for m in test:
            pr = fitted.predict(m["hk"], m["ak"], m["comp"])
            f = freq.get(m["comp"], [1, 1, 1])
            tot = sum(f)
            rows.append(([pr["p_home"], pr["p_draw"], pr["p_away"]], [x / tot for x in f],
                         outcome_index(m["hg"], m["ag"])))
    return summarize(rows, days)


def _ll(p: list[float], o: int) -> float:
    return -math.log(max(p[o], 1e-9))


def _brier(p: list[float], o: int) -> float:
    return sum((p[i] - (1.0 if i == o else 0.0)) ** 2 for i in range(3))


def summarize(rows: list[tuple], days: int) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "window_days": days}
    ll_m = sum(_ll(p, o) for p, _, o in rows) / n
    ll_b = sum(_ll(b, o) for _, b, o in rows) / n
    br_m = sum(_brier(p, o) for p, _, o in rows) / n
    br_b = sum(_brier(b, o) for _, b, o in rows) / n
    acc = sum(1 for p, _, o in rows if max(range(3), key=lambda i: p[i]) == o) / n
    diffs = [_ll(b, o) - _ll(p, o) for p, b, o in rows]   # >0 表示模型更好
    mean_d = sum(diffs) / n
    sd = math.sqrt(sum((d - mean_d) ** 2 for d in diffs) / max(n - 1, 1))
    calib = []
    for lo, hi in _BINS:
        pts = [(p[i], 1.0 if i == o else 0.0) for p, _, o in rows for i in range(3) if lo <= p[i] < hi]
        if pts:
            calib.append({"bin": f"{int(lo * 100)}-{min(int(hi * 100), 100)}%", "n": len(pts),
                          "predicted": sum(x for x, _ in pts) / len(pts), "actual": sum(y for _, y in pts) / len(pts)})
    return {"n": n, "window_days": days, "logloss_model": ll_m, "logloss_base": ll_b, "brier_model": br_m,
            "brier_base": br_b, "accuracy": acc, "logloss_gain": mean_d, "logloss_gain_se": sd / math.sqrt(n),
            "calibration": calib}
