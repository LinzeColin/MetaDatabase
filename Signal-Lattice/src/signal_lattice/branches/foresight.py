"""分支 4：股势前瞻（equity-foresight-signal）。

问题：一只候选股未来 20 个交易日相对 IWM 的超额收益扣掉 0.3% 往返成本后是否 > 0？
给出经样本外校准的概率 efs_score（= 校准后概率 × 100），并且必须和基准概率对比（probability_lift）。

诚实优先（Skill 的合同）：
- 先立简单基线（52 周高点折价 + 60 日波动率的逻辑回归，调研：单靠波动率就接近全模型），全模型（再加瓶颈/商业机会/事件航图分数、
  Lazy Prices 相似度分位、稀释标记）在样本外 Brier 上对不过基线就用基线；
- 选出的模型样本外 Brier 不优于「常数基准概率」（训练窗口内的历史上涨比例）→ 整个分支 ABSTAIN 并写明原因；
  这不是失败，是诚实：没有可校准的预测力就不给概率；
- 全部特征按时点构造：特征只用 ≤ 当日已可见的日线、SEC 申报（按申报日入账）、事件（按公开日）；标签用下一交易日入场、
  20 个交易日后的收盘；训练只用「标签在预测日之前已经揭晓」的样本（滚动前推，每月重训，含 20 日标签清洗）。

已知局限（收据里原样带上）：
- 历史市值 = 当前 SEC 股数 × 当日收盘（股数不随时间变；稀释另有稀释标记特征）；
- 特征里的瓶颈/商业机会分数不含 10-K 正文抽取（正文只有最新一份，回填历史会前视）；
- Lazy Prices 相似度只有最新一期的记录，历史日期没有时点相似度：该特征训练覆盖率低于下限，会被自动剔除并写明；
- 候选池是当前快照，退市股不在（幸存者偏差），样本外窗口不长（月度取样，同月内个股互相不独立）。
"""

from __future__ import annotations

import bisect
import json
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import event_study
from .param_floors import enforce_not_looser, floors_from_defaults
from .scoring_support import ParamsError, check_shape

SKILL_ID = "equity-foresight-signal"
DEFAULT_PARAMS_PATH = Path(__file__).resolve().parents[3] / "Stock_Skill" / "equity-foresight-signal-skill" / "runtime" / "params.json"
PARAMS_SCHEMA = "equity-foresight-signal/params-v1"

DEFAULT_PARAMS: Dict[str, Any] = {
    "schema": PARAMS_SCHEMA,
    "skill_id": SKILL_ID,
    "params_version": "0.0.0.1",
    "label": {"horizon_trading_days": 20, "benchmark": "IWM", "round_trip_cost": 0.003, "entry_lag_trading_days": 1},
    "panel": {"start": "2025-01-01", "max_symbols": 250, "seed": 20260930, "min_bars": 200},
    "features": {
        "baseline": ["dist_52w_high", "vol_60d"],
        "extra": ["bn_score", "bn_gate_margin", "bn_constraint", "bn_capture", "bn_mispricing", "cm_score", "cm_confidence",
                  "cm_maturity", "ev_opportunistic_buy", "ev_opportunistic_bps", "ev_dilution_90d", "ev_share_growth",
                  "share_change_yoy", "lazy_prices_pct"],
        "min_train_coverage": 0.30,
        "na_indicator_above": 0.02,
        "winsor_z": 4.0,
    },
    "model": {"l2": 5.0, "max_iter": 40, "tol": 1e-7},
    "walk_forward": {"min_train_dates": 6, "calibration_tail_fraction": 0.30, "min_calibration_dates": 2, "bootstrap_samples": 2000,
                     "bootstrap_seed": 20260930},
    # 事先写死的判定线，不按结果调：样本外行数/月数不够不公布；PASS 要求概率增量至少 5 个百分点且校准后概率不低于 55%
    "decision": {"min_oos_rows": 500, "min_oos_dates": 6, "pass_min_probability_lift": 0.05, "pass_min_efs": 55.0,
                 "min_train_rows": 300},
}


# 远端参数只许收紧：判定线与成本假设不得比仓库默认更宽松（阈值越高越严；成本越高越保守）。
FLOOR_RULES = {"decision.min_oos_rows": "min", "decision.min_oos_dates": "min", "decision.pass_min_probability_lift": "min",
               "decision.pass_min_efs": "min", "decision.min_train_rows": "min", "label.round_trip_cost": "min",
               "label.entry_lag_trading_days": "min", "walk_forward.min_train_dates": "min", "walk_forward.min_calibration_dates": "min"}


def validate_params(params: Any) -> Any:
    check_shape(DEFAULT_PARAMS, params, "params")
    if params["schema"] != PARAMS_SCHEMA or params["skill_id"] != SKILL_ID:
        raise ParamsError("schema/skill_id 不匹配")
    label = params["label"]
    if not 1 <= label["horizon_trading_days"] <= 120 or label["entry_lag_trading_days"] < 1:
        raise ParamsError("label.horizon_trading_days 需在 1..120 且入场滞后 >= 1（不能用信号当日收盘入场）")
    if not 0 <= label["round_trip_cost"] < 0.05:
        raise ParamsError("label.round_trip_cost 需在 [0, 0.05)")
    feats = params["features"]
    if not feats["baseline"] or not all(isinstance(x, str) for x in feats["baseline"] + feats["extra"]):
        raise ParamsError("features.baseline 不能为空，特征名必须是字符串")
    if set(feats["baseline"]) & set(feats["extra"]):
        raise ParamsError("features.baseline 与 extra 重叠")
    if set(feats["baseline"] + feats["extra"]) - set(FEATURE_NAMES):
        raise ParamsError("未知特征：%s" % sorted(set(feats["baseline"] + feats["extra"]) - set(FEATURE_NAMES)))
    for key in ("min_train_coverage", "na_indicator_above"):
        if not 0 <= feats[key] <= 1:
            raise ParamsError("features.%s 需在 [0,1]" % key)
    if params["model"]["l2"] < 0 or params["model"]["max_iter"] < 1:
        raise ParamsError("model 参数不合法")
    wf = params["walk_forward"]
    if wf["min_train_dates"] < 2 or not 0 < wf["calibration_tail_fraction"] < 0.9:
        raise ParamsError("walk_forward 参数不合法")
    d = params["decision"]
    if d["min_oos_dates"] < 2 or d["min_oos_rows"] < 1 or not 0 <= d["pass_min_probability_lift"] < 1 or not 0 <= d["pass_min_efs"] <= 100:
        raise ParamsError("decision 参数不合法")
    enforce_not_looser(params, floors_from_defaults(DEFAULT_PARAMS, FLOOR_RULES), ParamsError, SKILL_ID)
    return params


def load_params(path: Optional[Path] = DEFAULT_PARAMS_PATH) -> Tuple[dict, List[dict]]:
    from .scoring_support import load_params as _load
    return _load(DEFAULT_PARAMS, validate_params, path)


def write_default_params(path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(DEFAULT_PARAMS, ensure_ascii=False, indent=2) + "\n", "utf-8")


FEATURE_NAMES = ("dist_52w_high", "vol_60d", "bn_score", "bn_gate_margin", "bn_constraint", "bn_capture", "bn_mispricing",
                 "cm_score", "cm_confidence", "cm_maturity", "ev_opportunistic_buy", "ev_opportunistic_bps", "ev_dilution_90d",
                 "ev_share_growth", "share_change_yoy", "lazy_prices_pct")


# ---- 数学：逻辑回归（标准库）-------------------------------------------------------------
def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1.0 - eps)
    return math.log(p / (1.0 - p))


def solve_linear(a: List[List[float]], b: List[float]) -> List[float]:
    """高斯消元（部分主元）解 A x = b；A 是小的对称正定矩阵。"""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ArithmeticError("singular")
        m[col], m[pivot] = m[pivot], m[col]
        inv = 1.0 / m[col][col]
        for r in range(col + 1, n):
            factor = m[r][col] * inv
            if factor:
                row_r, row_c = m[r], m[col]
                for c in range(col, n + 1):
                    row_r[c] -= factor * row_c[c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / m[r][r]
    return x


def _loss(w: Sequence[float], xs: Sequence[Sequence[float]], ys: Sequence[int], l2: float) -> float:
    total = 0.0
    for x, y in zip(xs, ys):
        z = w[0] + sum(wi * xi for wi, xi in zip(w[1:], x))
        total += math.log1p(math.exp(-abs(z))) + max(z, 0.0) - y * z
    return total + 0.5 * l2 * sum(wi * wi for wi in w[1:])


def fit_logistic(xs: Sequence[Sequence[float]], ys: Sequence[int], l2: float = 1.0, max_iter: int = 40, tol: float = 1e-7) -> List[float]:
    """带 L2（截距不罚）的逻辑回归，牛顿法 + 回溯步长。返回 [截距, w1, ...]。xs 已标准化。"""
    n, d = len(xs), (len(xs[0]) if xs else 0)
    w = [0.0] * (d + 1)
    if n == 0:
        return w
    base = sum(ys) / n
    w[0] = logit(base)
    current = _loss(w, xs, ys, l2)
    for _ in range(max_iter):
        grad = [0.0] * (d + 1)
        hess = [[0.0] * (d + 1) for _ in range(d + 1)]
        for x, y in zip(xs, ys):
            z = w[0] + sum(wi * xi for wi, xi in zip(w[1:], x))
            p = sigmoid(z)
            r = p - y
            v = max(p * (1.0 - p), 1e-6)
            grad[0] += r
            hess[0][0] += v
            for i in range(d):
                xi = x[i]
                grad[i + 1] += r * xi
                vx = v * xi
                hess[0][i + 1] += vx
                row = hess[i + 1]
                for j in range(i + 1):
                    row[j + 1] += vx * x[j]
        for i in range(1, d + 1):
            hess[i][0] = hess[0][i]
            grad[i] += l2 * w[i]
            hess[i][i] += l2
            for j in range(i):
                hess[j + 1][i] = hess[i][j + 1]
        hess[0][0] += 1e-9
        try:
            step = solve_linear(hess, grad)
        except ArithmeticError:
            break
        scale = 1.0
        while scale > 1e-4:
            trial = [wi - scale * si for wi, si in zip(w, step)]
            loss = _loss(trial, xs, ys, l2)
            if loss <= current + 1e-12:
                break
            scale *= 0.5
        else:
            break
        improvement = current - loss
        w, current = trial, loss
        if improvement < tol * max(1.0, abs(current)):
            break
    return w


def fit_platt(scores: Sequence[float], ys: Sequence[int], iterations: int = 30) -> Tuple[float, float]:
    """一维逻辑回归 p = sigmoid(a * score + b)（Platt 校准）；样本太少或单一类别退回恒等 (1, 0)。"""
    if len(scores) < 30 or len(set(ys)) < 2:
        return 1.0, 0.0
    a, b = 1.0, 0.0
    for _ in range(iterations):
        ga = gb = haa = hab = hbb = 0.0
        for s, y in zip(scores, ys):
            p = sigmoid(a * s + b)
            r = p - y
            v = max(p * (1 - p), 1e-6)
            ga += r * s
            gb += r
            haa += v * s * s
            hab += v * s
            hbb += v
        haa += 1e-6
        hbb += 1e-6
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-8:
            break
    if not (math.isfinite(a) and math.isfinite(b)):
        return 1.0, 0.0
    return a, b


def brier(ps: Sequence[float], ys: Sequence[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def auc(ps: Sequence[float], ys: Sequence[int]) -> Optional[float]:
    positives = sum(ys)
    negatives = len(ys) - positives
    if positives == 0 or negatives == 0:
        return None
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    ranks = [0.0] * len(ps)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and ps[order[j + 1]] == ps[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return (sum(ranks[i] for i in range(len(ys)) if ys[i] == 1) - positives * (positives + 1) / 2.0) / (positives * negatives)


# ---- 特征矩阵 ------------------------------------------------------------------------
@dataclass
class FeatureSpec:
    """训练时冻结的特征处理：用了哪些特征、缺失怎么补、怎么标准化。"""
    names: List[str]
    medians: Dict[str, float]
    na_flags: List[str]
    means: List[float]
    stds: List[float]
    winsor: float
    dropped: Dict[str, str] = field(default_factory=dict)

    @property
    def columns(self) -> List[str]:
        return list(self.names) + ["%s__na" % n for n in self.na_flags]

    def transform(self, features: Mapping[str, Optional[float]]) -> List[float]:
        row: List[float] = []
        for name in self.names:
            value = features.get(name)
            row.append(self.medians[name] if value is None or not math.isfinite(value) else float(value))
        for name in self.na_flags:
            value = features.get(name)
            row.append(1.0 if value is None or not math.isfinite(value) else 0.0)
        out = []
        for value, mean, std in zip(row, self.means, self.stds):
            z = (value - mean) / std if std > 0 else 0.0
            out.append(max(-self.winsor, min(self.winsor, z)))
        return out


def fit_feature_spec(rows: Sequence[Mapping[str, Optional[float]]], names: Sequence[str], min_coverage: float,
                     na_indicator_above: float, winsor: float) -> FeatureSpec:
    kept: List[str] = []
    dropped: Dict[str, str] = {}
    medians: Dict[str, float] = {}
    na_flags: List[str] = []
    n = len(rows)
    for name in names:
        values = [r.get(name) for r in rows]
        present = [v for v in values if v is not None and math.isfinite(v)]
        coverage = len(present) / n if n else 0.0
        if coverage < min_coverage:
            dropped[name] = "训练覆盖率 %.0f%% 低于下限 %.0f%%" % (coverage * 100, min_coverage * 100)
            continue
        if len(set(present)) < 2:
            dropped[name] = "训练样本里没有变化"
            continue
        kept.append(name)
        medians[name] = statistics.median(present)
        if 1.0 - coverage > na_indicator_above:
            na_flags.append(name)
    spec = FeatureSpec(kept, medians, na_flags, [], [], winsor, dropped)
    matrix = [[(medians[nm] if (r.get(nm) is None or not math.isfinite(r.get(nm))) else float(r[nm])) for nm in kept]
              + [1.0 if (r.get(nm) is None or not math.isfinite(r.get(nm))) else 0.0 for nm in na_flags] for r in rows]
    means, stds = [], []
    for j in range(len(kept) + len(na_flags)):
        column = [row[j] for row in matrix]
        mean = sum(column) / len(column) if column else 0.0
        var = sum((v - mean) ** 2 for v in column) / len(column) if column else 0.0
        means.append(mean)
        stds.append(math.sqrt(var))
    spec.means, spec.stds = means, stds
    return spec


@dataclass
class FittedModel:
    spec: FeatureSpec
    weights: List[float]
    platt: Tuple[float, float]
    calibrated: bool

    def raw_probability(self, features: Mapping[str, Optional[float]]) -> float:
        x = self.spec.transform(features)
        return sigmoid(self.weights[0] + sum(w * v for w, v in zip(self.weights[1:], x)))

    def probability(self, features: Mapping[str, Optional[float]]) -> float:
        p = self.raw_probability(features)
        a, b = self.platt
        return sigmoid(a * logit(p) + b)

    def coefficients(self) -> Dict[str, float]:
        return {name: round(w, 5) for name, w in zip(self.spec.columns, self.weights[1:])}


def fit_model(rows: Sequence["Row"], names: Sequence[str], params: Mapping) -> Optional[FittedModel]:
    """在训练行上拟合：最近 calibration_tail 比例的日期只用来做 Platt 校准（清洗掉标签与校准期重叠的行），
    拟合部分与校准部分不重叠；返回的模型就是「拟合部分的模型 + 校准」，前后一致。"""
    if not rows or len({r.y for r in rows}) < 2:
        return None
    feats, mcfg, wf = params["features"], params["model"], params["walk_forward"]
    dates = sorted({r.date for r in rows})
    tail_n = max(int(wf["min_calibration_dates"]), int(round(len(dates) * wf["calibration_tail_fraction"])))
    fit_rows, cal_rows = list(rows), []
    if len(dates) - tail_n >= max(2, int(wf["min_train_dates"]) - int(wf["min_calibration_dates"])):
        cal_start = dates[len(dates) - tail_n]
        cal_rows = [r for r in rows if r.date >= cal_start]
        fit_rows = [r for r in rows if r.date < cal_start and r.label_end < cal_start]     # 清洗：标签不与校准期重叠
    if not fit_rows or len({r.y for r in fit_rows}) < 2:
        fit_rows, cal_rows = list(rows), []
    spec = fit_feature_spec([r.features for r in fit_rows], names, feats["min_train_coverage"], feats["na_indicator_above"], feats["winsor_z"])
    if not spec.names:
        return None
    xs = [spec.transform(r.features) for r in fit_rows]
    weights = fit_logistic(xs, [r.y for r in fit_rows], mcfg["l2"], mcfg["max_iter"], mcfg["tol"])
    model = FittedModel(spec, weights, (1.0, 0.0), False)
    if cal_rows and len({r.y for r in cal_rows}) == 2:
        scores = [logit(model.raw_probability(r.features)) for r in cal_rows]
        model.platt = fit_platt(scores, [r.y for r in cal_rows])
        model.calibrated = model.platt != (1.0, 0.0)
    return model


# ---- 面板 ----------------------------------------------------------------------------
@dataclass
class Row:
    date: str
    symbol: str
    y: int
    excess: float
    label_end: str                       # 标签揭晓日（20 个交易日后的收盘日）
    features: Dict[str, Optional[float]]


def month_end_dates(days: Sequence[str], start: str, last_index: int) -> List[str]:
    """交易日历里每个月最后一个交易日，>= start，且下标 <= last_index。"""
    out: List[str] = []
    for i, day in enumerate(days[:last_index + 1]):
        if day < start:
            continue
        if i + 1 >= len(days) or days[i + 1][:7] != day[:7]:
            out.append(day)
    return out


def price_features(days: Sequence[str], closes: Sequence[float], index: int, min_bars: int) -> Optional[Dict[str, float]]:
    """dist_52w_high = 收盘/近 252 日最高 - 1（<=0）；vol_60d = 近 60 日对数收益标准差 × sqrt(252)。只用下标 <= index 的数据。"""
    if index + 1 < min_bars or index < 61:
        return None
    window = closes[max(0, index - 251): index + 1]
    peak = max(window)
    if peak <= 0 or closes[index] <= 0:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(index - 59, index + 1) if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 40:
        return None
    return {"dist_52w_high": closes[index] / peak - 1.0, "vol_60d": statistics.pstdev(rets) * math.sqrt(252.0)}


def make_label(stock: event_study.Bars, bench: event_study.Bars, day: str, horizon: int, lag: int, cost: float) -> Optional[Tuple[int, float, str]]:
    """(y, 超额收益, 标签揭晓日)。入场 = 信号日之后第 lag 个交易日收盘，出场 = 入场后 horizon 个交易日。"""
    start = event_study.entry_index(stock[0], day, lag)
    if start is None:
        return None
    excess = event_study.excess_return(stock, bench, start, horizon)
    if excess is None:
        return None
    return (1 if excess - cost > 0 else 0), excess, stock[0][start + horizon]


def evaluate_walk_forward(rows: Sequence[Row], prediction_dates: Sequence[str], baseline_names: Sequence[str],
                          full_names: Sequence[str], params: Mapping) -> dict:
    """每个预测日只用「标签在该日之前已揭晓」的行训练（每月重训），预测该日的行；返回样本外预测与汇总。"""
    wf, dec = params["walk_forward"], params["decision"]
    by_date: Dict[str, List[Row]] = {}
    for r in rows:
        by_date.setdefault(r.date, []).append(r)
    oos: List[dict] = []
    folds: List[dict] = []
    for d in prediction_dates:
        train = [r for r in rows if r.label_end <= d and r.date < d]
        train_dates = {r.date for r in train}
        test = by_date.get(d, [])
        if len(train_dates) < wf["min_train_dates"] or not test or len({r.y for r in train}) < 2:
            continue
        const = sum(r.y for r in train) / len(train)
        base_model = fit_model(train, baseline_names, params)
        full_model = fit_model(train, full_names, params)
        if base_model is None or full_model is None:
            continue
        for r in test:
            oos.append({"date": d, "symbol": r.symbol, "y": r.y, "p_const": const, "p_base": base_model.probability(r.features),
                        "p_full": full_model.probability(r.features), "p_base_raw": base_model.raw_probability(r.features),
                        "p_full_raw": full_model.raw_probability(r.features)})
        folds.append({"date": d, "train_rows": len(train), "train_dates": len(train_dates), "test_rows": len(test),
                      "base_rate": const, "full_dropped": full_model.spec.dropped, "full_calibrated": full_model.calibrated,
                      "base_calibrated": base_model.calibrated})
    return summarize_oos(oos, folds, wf, dec)


def summarize_oos(oos: Sequence[dict], folds: Sequence[dict], wf: Mapping, dec: Mapping) -> dict:
    result: dict = {"oos_rows": len(oos), "oos_dates": len({o["date"] for o in oos}), "folds": list(folds)}
    if not oos:
        result["status"] = "NO_OOS"
        return result
    ys = [o["y"] for o in oos]
    metrics = {name: brier([o[key] for o in oos], ys) for name, key in
               (("const", "p_const"), ("baseline_model", "p_base"), ("full_model", "p_full"),
                ("baseline_model_uncalibrated", "p_base_raw"), ("full_model_uncalibrated", "p_full_raw"))}
    result["brier"] = metrics
    result["auc"] = {"baseline_model": auc([o["p_base"] for o in oos], ys), "full_model": auc([o["p_full"] for o in oos], ys)}
    result["oos_positive_rate"] = sum(ys) / len(ys)
    full_beats_baseline = metrics["full_model"] < metrics["baseline_model"]
    selected = "full_model" if full_beats_baseline else "baseline_model"
    result["full_beats_baseline_model"] = full_beats_baseline
    result["selected_model"] = selected
    result["selected_beats_constant"] = metrics[selected] < metrics["const"]
    # 日期块自助：选出模型相对常数基准的 Brier 差（每个预测日的均值为一块），只作参考，不改判定
    key = "p_full" if selected == "full_model" else "p_base"
    per_date: Dict[str, List[float]] = {}
    for o in oos:
        per_date.setdefault(o["date"], []).append((o[key] - o["y"]) ** 2 - (o["p_const"] - o["y"]) ** 2)
    diffs = [statistics.fmean(v) for v in per_date.values()]
    rng = random.Random(int(wf["bootstrap_seed"]))
    boots = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(int(wf["bootstrap_samples"])))
    result["selected_minus_constant_brier"] = {
        "mean": statistics.fmean(diffs), "ci95": [boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]],
        "negative_means_model_better": True, "blocks": len(diffs)}
    result["reliability"] = reliability_table([o[key] for o in oos], ys)
    return result


def reliability_table(ps: Sequence[float], ys: Sequence[int], bins: int = 5) -> List[dict]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out = []
    for b in range(bins):
        chunk = order[b * len(order) // bins:(b + 1) * len(order) // bins]
        if chunk:
            out.append({"bin": b + 1, "n": len(chunk), "mean_predicted": statistics.fmean(ps[i] for i in chunk),
                        "realized_rate": statistics.fmean(ys[i] for i in chunk)})
    return out


def branch_decision(summary: Mapping, params: Mapping) -> Tuple[str, List[str]]:
    """PASS = 能给校准后的概率；ABSTAIN = 整个分支不出概率（写明原因）。"""
    dec = params["decision"]
    reasons: List[str] = []
    if summary.get("oos_rows", 0) < dec["min_oos_rows"] or summary.get("oos_dates", 0) < dec["min_oos_dates"]:
        reasons.append("SAMPLE_INSUFFICIENT:oos_rows=%d(<%d) or oos_dates=%d(<%d)" % (
            summary.get("oos_rows", 0), dec["min_oos_rows"], summary.get("oos_dates", 0), dec["min_oos_dates"]))
    elif not summary.get("selected_beats_constant"):
        b = summary["brier"]
        reasons.append("OOS_BRIER_NOT_BETTER_THAN_BASE_RATE:%s=%.5f>=const=%.5f" % (
            summary["selected_model"], b[summary["selected_model"]], b["const"]))
    return ("ABSTAIN" if reasons else "PASS"), reasons


# ---- 面板构造与整条分支 ------------------------------------------------------------------
BarSeries = Tuple[List[str], List[float]]
ExtraFeatureProvider = Callable[[str, Sequence[Mapping]], Dict[str, Dict[str, Optional[float]]]]


def stratified_sample(entries: Sequence[Mapping], size: int, seed: int) -> List[Mapping]:
    """按市值分层、固定种子抽样（与 Lazy Prices 抽样同一口径）：分层内随机，结果可复现。"""
    from ..evidence.text_similarity import stratified_sample as _sample
    return list(_sample(entries, size, seed))


def prediction_dates_for(bench_days: Sequence[str], params: Mapping) -> List[str]:
    label = params["label"]
    last_index = len(bench_days) - 1 - int(label["horizon_trading_days"]) - int(label["entry_lag_trading_days"])
    if last_index <= 0:
        return []
    return month_end_dates(bench_days, params["panel"]["start"], last_index)


def build_rows(entries: Sequence[Mapping], bars: Mapping[str, BarSeries], bench: BarSeries, dates: Sequence[str],
               params: Mapping, extra_provider: Optional[ExtraFeatureProvider], log: Callable[[str], None] = print) -> List[Row]:
    label_cfg, panel = params["label"], params["panel"]
    horizon, lag, cost = int(label_cfg["horizon_trading_days"]), int(label_cfg["entry_lag_trading_days"]), float(label_cfg["round_trip_cost"])
    rows: List[Row] = []
    for n, day in enumerate(dates, 1):
        eligible: List[Tuple[Mapping, Dict[str, float], Tuple[int, float, str]]] = []
        for entry in entries:
            series = bars.get(entry["symbol"])
            if not series:
                continue
            days, closes = series
            index = bisect.bisect_right(days, day) - 1
            if index < 0 or days[index] != day:
                continue
            features = price_features(days, closes, index, int(panel["min_bars"]))
            label = make_label(series, bench, day, horizon, lag, cost)
            if features is None or label is None:
                continue
            eligible.append((entry, features, label))
        extras = extra_provider(day, [e for e, _f, _l in eligible]) if extra_provider is not None else {}
        for entry, features, (y, excess, label_end) in eligible:
            merged: Dict[str, Optional[float]] = dict(features)
            merged.update(extras.get(entry["symbol"], {}))
            rows.append(Row(day, entry["symbol"], y, excess, label_end, merged))
        log("foresight panel %d/%d %s rows=%d" % (n, len(dates), day, len(rows)))
    return rows


def production_features(entries: Sequence[Mapping], bars: Mapping[str, BarSeries], as_of: str, params: Mapping,
                        extra_provider: Optional[ExtraFeatureProvider], need_extra: bool) -> Dict[str, Dict[str, Optional[float]]]:
    out: Dict[str, Dict[str, Optional[float]]] = {}
    usable: List[Mapping] = []
    for entry in entries:
        series = bars.get(entry["symbol"])
        if not series:
            continue
        days, closes = series
        index = bisect.bisect_right(days, as_of) - 1
        if index < 0:
            continue
        features = price_features(days, closes, index, int(params["panel"]["min_bars"]))
        if features is not None:
            out[entry["symbol"]] = dict(features)
            usable.append(entry)
    if need_extra and extra_provider is not None:
        extras = extra_provider(as_of, usable)
        for symbol in out:
            out[symbol].update(extras.get(symbol, {}))
    return out


def verdict_records(entries: Sequence[Mapping], features: Mapping[str, Mapping], model: Optional[FittedModel], base_rate: float,
                    branch_status: str, branch_reasons: Sequence[str], summary: Mapping, selected: Optional[str], train_rows: int,
                    train_dates: int, params: Mapping, links: Callable[[Mapping], List[dict]]) -> List[dict]:
    dec = params["decision"]
    selected_brier = summary.get("brier", {}).get(selected) if selected else None
    const_brier = summary.get("brier", {}).get("const")
    out: List[dict] = []
    for entry in entries:
        symbol = entry["symbol"]
        base = {"symbol": symbol, "cik": int(entry["cik"]), "name": entry["name"], "market_cap_usd": entry["market_cap_usd"]}
        feats = features.get(symbol)
        if branch_status != "PASS" or model is None:
            out.append({**base, "verdict": "ABSTAIN", "label": "BRANCH_ABSTAIN", "score": 0.0, "rank_key": 0.0,
                        "reasons": ["BRANCH_ABSTAIN"] + list(branch_reasons), "evidence": {}, "links": []})
            continue
        if feats is None:
            out.append({**base, "verdict": "ABSTAIN", "label": "INSUFFICIENT_PRICE_HISTORY", "score": 0.0, "rank_key": 0.0,
                        "reasons": ["NO_PRICE_FEATURES:bars<%d" % params["panel"]["min_bars"]], "evidence": {}, "links": []})
            continue
        p = model.probability(feats)
        lift = p - base_rate
        efs = round(p * 100.0, 2)
        attached = links(entry)
        reasons: List[str] = []
        verdict, label = "ABSTAIN", "NO_EDGE"
        if lift >= dec["pass_min_probability_lift"] and efs >= dec["pass_min_efs"]:
            if train_rows < dec["min_train_rows"]:
                reasons.append("TRAIN_ROWS_BELOW_MIN:%d<%d" % (train_rows, dec["min_train_rows"]))
            elif not attached:
                reasons.append("PASS_REQUIRES_PRIMARY_SEC_LINK")
            else:
                verdict, label = "PASS", "FORECAST_OUTPERFORM"
                reasons.append("CALIBRATED_LIFT:%+.3f>=%s;EFS:%.1f>=%s" % (lift, dec["pass_min_probability_lift"], efs, dec["pass_min_efs"]))
        else:
            reasons.append("LIFT_OR_EFS_BELOW_PASS_LINE:lift=%+.3f,efs=%.1f" % (lift, efs))
        out.append({**base, "verdict": verdict, "label": label, "score": efs, "rank_key": (1000.0 if verdict == "PASS" else 0.0) + 100.0 * lift,
                    "reasons": reasons,
                    "evidence": {"efs_score": efs, "baseline_prob": round(base_rate, 4), "probability_lift": round(lift, 4),
                                 "sample_rows": train_rows, "sample_dates": train_dates, "model": selected,
                                 "brier_model_oos": selected_brier, "brier_baseline_oos": const_brier,
                                 "features": {k: (None if v is None else round(float(v), 4)) for k, v in feats.items()}},
                    "links": attached})
    return out


def run_with(entries: Sequence[Mapping], bars: Mapping[str, BarSeries], bench: BarSeries, as_of: str, params: Mapping,
             extra_provider: Optional[ExtraFeatureProvider], links: Callable[[Mapping], List[dict]],
             log: Callable[[str], None] = print) -> dict:
    feats = params["features"]
    baseline, full = list(feats["baseline"]), list(feats["baseline"]) + list(feats["extra"])
    sample = stratified_sample(entries, int(params["panel"]["max_symbols"]), int(params["panel"]["seed"]))
    dates = prediction_dates_for(bench[0], params)
    rows = build_rows(sample, bars, bench, dates, params, extra_provider, log)
    summary = evaluate_walk_forward(rows, dates, baseline, full, params)
    status, reasons = branch_decision(summary, params)
    selected = summary.get("selected_model")
    meta = {"panel": {"symbols_sampled": len(sample), "dates": len(dates), "rows": len(rows),
                      "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None},
            "summary": summary, "limitations": list(LIMITATIONS)}
    model = None
    base_rate = 0.0
    features_now: Dict[str, Dict[str, Optional[float]]] = {}
    train = [r for r in rows if r.label_end <= as_of]
    if status == "PASS":
        names = full if selected == "full_model" else baseline
        model = fit_model(train, names, params)
        base_rate = sum(r.y for r in train) / len(train) if train else 0.0
        if model is None:
            status, reasons = "ABSTAIN", ["FINAL_MODEL_NOT_FITTABLE"]
        else:
            features_now = production_features(entries, bars, as_of, params, extra_provider, selected == "full_model")
            meta["final_model"] = {"which": selected, "coefficients": model.coefficients(), "dropped_features": model.spec.dropped,
                                   "platt": list(model.platt), "calibrated": model.calibrated, "train_rows": len(train),
                                   "train_dates": len({r.date for r in train}), "base_rate": base_rate}
    if status != "PASS":
        meta["abstain_reasons"] = reasons
    verdicts = verdict_records(entries, features_now, model, base_rate, status, reasons, summary, selected, len(train),
                               len({r.date for r in train}), params, links)
    return {"branch_status": status, "branch_reasons": reasons, "verdicts": verdicts, "meta": meta}


LIMITATIONS = (
    "历史市值 = 当前 SEC 股数 × 当日收盘（股数不随时间变）",
    "瓶颈/商业机会特征不含 10-K 正文抽取（正文只有最新一份，回填历史会前视）",
    "Lazy Prices 相似度只有最新一期，历史日期没有时点相似度：覆盖率低于下限会被剔除并写明",
    "候选池是当前快照，退市股不在（幸存者偏差）；月度取样，同月内个股不独立",
)


# ---- 接真实数据：快照 -> 特征提供者 ---------------------------------------------------------
def load_series(bar_store: Any, symbols: Sequence[str]) -> Tuple[Dict[str, BarSeries], Dict[str, List[Optional[float]]]]:
    series: Dict[str, BarSeries] = {}
    volumes: Dict[str, List[Optional[float]]] = {}
    for symbol in symbols:
        rows = bar_store.load(symbol)
        if rows:
            series[symbol] = ([r[0] for r in rows], [float(r[1]) for r in rows])
            volumes[symbol] = [r[2] if len(r) > 2 else None for r in rows]
    return series, volumes


def market_input_at(entry: Mapping, series: BarSeries, volumes: Sequence[Optional[float]], index: int):
    """as_of = series 第 index 天的时点行情输入：价格取当日收盘，市值 = 当前 SEC 股数 × 当日收盘（股数不变的近似），
    成交额中位数取截至当日的 20 个交易日；历史只含 <= 当日。"""
    from .fundamentals import MarketInput
    days, closes = series
    window = [(closes[i] * volumes[i]) for i in range(max(0, index - 19), index + 1) if volumes[i]]
    median = statistics.median(window) if window else float(entry["median_dollar_volume_20d_usd"])
    shares = float(entry["shares_outstanding"])
    price = closes[index]
    base = MarketInput.from_entry(entry, list(zip(days[:index + 1], closes[:index + 1])))
    from dataclasses import replace
    return replace(base, price=price, market_cap=shares * price, median_dollar_volume=median)


def event_features(events: Sequence[Any], day: str, market_cap: float, lookback_days: int = 90) -> Dict[str, Optional[float]]:
    """按公开日（published_date <= day）取事件：近 90 天机会型买入人数/金额占市值、近 90 天增发/ATM/S-1、近 200 天股数同比增长。"""
    from .event_atlas import OFFERING_KINDS
    floor = (date.fromisoformat(day) - timedelta(days=lookback_days)).isoformat()
    growth_floor = (date.fromisoformat(day) - timedelta(days=200)).isoformat()
    opp = [e for e in events if e.kind == "INSIDER_BUY_OPPORTUNISTIC" and floor <= e.published_date <= day]
    per_accession: Dict[str, float] = {}
    for e in opp:
        per_accession[e.accession] = max(per_accession.get(e.accession, 0.0), float(e.details.get("amount_usd", 0.0)))
    bps = (sum(per_accession.values()) / market_cap * 1e4) if market_cap and per_accession else 0.0
    return {
        "ev_opportunistic_buy": 1.0 if opp else 0.0,
        "ev_opportunistic_bps": min(bps, 40.0) / 40.0,
        "ev_dilution_90d": 1.0 if any(e.kind in OFFERING_KINDS and floor <= e.published_date <= day for e in events) else 0.0,
        "ev_share_growth": 1.0 if any(e.kind == "SHARE_COUNT_GROWTH" and growth_floor <= e.published_date <= day for e in events) else 0.0,
    }


MATURITY_NUMBER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4, "E5": 5}


def make_snapshot_provider(snapshot: Any, bars: Mapping[str, BarSeries], volumes: Mapping[str, Sequence[Optional[float]]],
                           log: Callable[[str], None] = print) -> Tuple[ExtraFeatureProvider, Callable[[Mapping], List[dict]], Callable[[], None]]:
    from ..evidence.prospectus import document_url
    from . import bottleneck as B, commercial as C, event_atlas as EA
    from .fundamentals import PeerContext, compute_fundamentals
    from .textmarkers import latest_periodic_with_document

    bn_path, cm_path, ev_path = (snapshot.params_file(s) for s in ("bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas"))
    bn_params, bn_findings = B.load_bottleneck_params(bn_path) if bn_path else B.load_bottleneck_params(None)
    cm_params, cm_findings = C.load_commercial_params(cm_path) if cm_path else C.load_commercial_params(None)
    ev_params = EA.load_params(ev_path) if ev_path else EA.load_params()
    facts, ev_store = snapshot.facts(), snapshot.events()
    event_start = snapshot.document.get("collection", {}).get("event_start", "2024-10-01")
    events = EA.build_events(ev_store, snapshot.entries, snapshot.as_of, ev_params, since=event_start)
    by_cik: Dict[int, List[Any]] = {}
    for e in events:
        by_cik.setdefault(e.cik, []).append(e)
    lazy = snapshot.text_similarity_by_symbol()
    log("foresight: %d events loaded for feature construction" % len(events))

    def provider(day: str, subset: Sequence[Mapping]) -> Dict[str, Dict[str, Optional[float]]]:
        funds = {}
        for entry in subset:
            series = bars[entry["symbol"]]
            index = bisect.bisect_right(series[0], day) - 1
            funds[entry["symbol"]] = compute_fundamentals(facts, market_input_at(entry, series, volumes[entry["symbol"]], index), day)
        peers = PeerContext.build(funds.values(), C.DEFAULT_PARAMS["peers"]["min_group"])
        out: Dict[str, Dict[str, Optional[float]]] = {}
        for symbol, f in funds.items():
            b = B.score_bottleneck(facts, f.market, day, bn_params, bn_findings, peers, None, f).detail
            c = C.score_commercial(facts, f.market, day, cm_params, cm_findings, peers, f).detail
            dims = b["dimensions"]

            def dim(name: str) -> Optional[float]:
                score = dims[name]["score"]
                return None if score is None else score / 100.0

            feats: Dict[str, Optional[float]] = {
                "bn_score": None if b["indicative_score"] is None else b["indicative_score"] / 100.0,
                "bn_gate_margin": b["gate_margin"], "bn_constraint": dim("constraint"), "bn_capture": dim("capture"),
                "bn_mispricing": dim("mispricing"),
                "cm_score": None if c["decision_score"] is None else c["decision_score"] / 100.0,
                "cm_confidence": None if c["evidence_confidence"] is None else c["evidence_confidence"] / 100.0,
                "cm_maturity": MATURITY_NUMBER.get(c["maturity_code"], 0) / 5.0,
                "share_change_yoy": (max(-0.3, min(0.6, f.share_change_yoy.value)) if f.share_change_yoy.ok else None),
                "lazy_prices_pct": (lazy[symbol]["percentile"] if symbol in lazy and lazy[symbol]["filed"] <= day else None),
            }
            feats.update(event_features(by_cik.get(f.cik, []), day, f.market.market_cap))
            out[symbol] = feats
        return out

    def links(entry: Mapping) -> List[dict]:
        row = latest_periodic_with_document(facts, int(entry["cik"]), snapshot.as_of)
        if row is None:
            return []
        return [{"url": document_url(int(entry["cik"]), row["accession"], row["primary_document"]), "accession": row["accession"],
                 "form": row["form"], "filed": row["filed"], "supports": "latest_periodic_report",
                 "role": "CONTEXT_ONLY（该模型的特征来自行情与申报索引，此链接只证明公司身份与申报时点）"}]

    def close() -> None:
        facts.close()
        ev_store.close()

    return provider, links, close


def run(snapshot: Any, params: Mapping, log: Callable[[str], None] = print) -> dict:
    bar_store = snapshot.bar_store()
    symbols = [e["symbol"] for e in snapshot.entries]
    bars, volumes = load_series(bar_store, symbols + [params["label"]["benchmark"]])
    bench = bars.get(params["label"]["benchmark"])
    if bench is None:
        return {"branch_status": "ABSTAIN", "branch_reasons": ["BENCHMARK_BARS_MISSING:%s" % params["label"]["benchmark"]],
                "verdicts": [], "meta": {}}
    provider, links, close = make_snapshot_provider(snapshot, bars, volumes, log)
    try:
        return run_with(snapshot.entries, bars, bench, snapshot.as_of, params, provider, links, log)
    finally:
        close()
