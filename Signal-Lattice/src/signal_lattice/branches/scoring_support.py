"""瓶颈 / 商业机会两个分支共用的打分零件。

约定（Owner 2026-09-30）：
- 拿不到证据的因子记 NO_EVIDENCE（rating=None），既不是中值也不是 0 分冒充；
- 维度分只对「有证据的因子」按权重归一，同时报告覆盖率（有证据的权重占比）；
  覆盖率低于 params 里的下限、或缺了该维度的必备因子，这一维记为「不可核实」，
  对应的门一律不能算通过（关键证据缺失即硬标记）；
- 每个有数的因子都带 EvidenceRef（SEC 申报 accession + 原文链接），没有链接的因子不算「有原文」。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

NO_EVIDENCE = "NO_EVIDENCE"

# 证据类别：xbrl=SEC 结构化财务数据；text=SEC 申报原文关键词；market=行情（新浪/腾讯）；estimate=推算
KIND_XBRL = "xbrl"
KIND_TEXT = "text"
KIND_MARKET = "market"
KIND_ESTIMATE = "estimate"
PRIMARY_KINDS = (KIND_XBRL, KIND_TEXT)  # 一手：来自 SEC 申报


@dataclass(frozen=True)
class EvidenceRef:
    kind: str
    label: str                    # 例：us-gaap:RevenueRemainingPerformanceObligation @2026-06-30
    value: Optional[float] = None
    accession: Optional[str] = None
    form: Optional[str] = None
    filed: Optional[str] = None
    period_end: Optional[str] = None
    url: Optional[str] = None     # SEC 原文页面（只在 kind 为 xbrl/text 时必有）

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if value is not None}

    @property
    def is_primary_link(self) -> bool:
        return self.kind in PRIMARY_KINDS and bool(self.url) and str(self.url).startswith("https://www.sec.gov/")


@dataclass(frozen=True)
class FactorResult:
    name: str
    rating: Optional[float]                 # None = NO_EVIDENCE
    basis: str                              # 人话：这个评分怎么来的 / 为什么没有
    refs: Tuple[EvidenceRef, ...] = ()
    status: str = "OBSERVED"                # OBSERVED | ESTIMATED | PROXY | NO_EVIDENCE
    metric: Optional[float] = None          # 驱动评分的原始数值（便于复核）

    @property
    def observed(self) -> bool:
        return self.rating is not None

    def to_dict(self) -> dict:
        return {
            "rating": self.rating if self.observed else NO_EVIDENCE,
            "status": self.status if self.observed else "NO_EVIDENCE",
            "basis": self.basis,
            "metric": self.metric,
            "refs": [ref.to_dict() for ref in self.refs],
        }


def no_evidence(name: str, why: str) -> FactorResult:
    return FactorResult(name, None, why, (), "NO_EVIDENCE")


# ---- 阶梯评分 ----------------------------------------------------------------
def table_rating(value: Optional[float], table: Mapping[str, Any]) -> Optional[float]:
    """table = {"direction": "higher"|"lower", "cuts": [[阈值, 评分], ...], "floor": 评分}。

    higher：value >= 阈值 取最高一档；lower：value <= 阈值 取最严一档；都不满足给 floor。
    """
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    cuts = [(float(threshold), float(rating)) for threshold, rating in table["cuts"]]
    if table["direction"] == "higher":
        for threshold, rating in sorted(cuts, key=lambda item: -item[0]):
            if value >= threshold:
                return rating
    else:
        for threshold, rating in sorted(cuts, key=lambda item: item[0]):
            if value <= threshold:
                return rating
    return float(table["floor"])


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---- 维度聚合 ---------------------------------------------------------------
@dataclass(frozen=True)
class DimensionResult:
    name: str
    score: Optional[float]           # 0-100；None = 不可核实
    coverage: float                  # 有证据因子的权重占比 0-1
    verifiable: bool
    observed: Tuple[str, ...]
    no_evidence: Tuple[str, ...]
    missing_required: Tuple[str, ...]
    reason: Optional[str]            # 不可核实的机器可读原因

    def to_dict(self) -> dict:
        return {
            "score": None if self.score is None else round(self.score, 2),
            "coverage": round(self.coverage, 3),
            "verifiable": self.verifiable,
            "observed_factors": list(self.observed),
            "no_evidence_factors": list(self.no_evidence),
            "missing_required_factors": list(self.missing_required),
            "reason": self.reason,
        }


def aggregate_dimension(
    name: str,
    factors: Mapping[str, FactorResult],
    weights: Mapping[str, float],
    scale: float,
    min_coverage: float,
    required: Sequence[str],
) -> DimensionResult:
    """有证据因子按权重归一到 0-100；覆盖率不足或缺必备因子则不可核实。

    scale 是单个因子评分的满分（瓶颈 5，商业机会 10）。
    """
    total_weight = float(sum(weights.values()))
    observed = [key for key in weights if factors[key].observed]
    missing = [key for key in weights if not factors[key].observed]
    observed_weight = sum(weights[key] for key in observed)
    coverage = observed_weight / total_weight if total_weight else 0.0
    missing_required = tuple(key for key in required if not factors[key].observed)
    score: Optional[float] = None
    if observed_weight > 0:
        points = sum(float(factors[key].rating) / scale * weights[key] for key in observed)
        score = points / observed_weight * 100.0
    reason = None
    if score is None:
        reason = "NO_FACTOR_OBSERVED"
    elif missing_required:
        reason = "REQUIRED_FACTOR_NO_EVIDENCE:" + ",".join(missing_required)
    elif coverage + 1e-9 < min_coverage:
        reason = "COVERAGE_BELOW_FLOOR:%.2f<%.2f" % (coverage, min_coverage)
    return DimensionResult(
        name=name,
        score=score,
        coverage=coverage,
        verifiable=reason is None,
        observed=tuple(observed),
        no_evidence=tuple(missing),
        missing_required=missing_required,
        reason=reason,
    )


def geometric_mean(values: Iterable[float], floor: float = 0.01) -> float:
    vals = [max(float(v), floor) for v in values]
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


# ---- 参数：外置 JSON + 内置默认 ----------------------------------------------
class ParamsError(ValueError):
    pass


def _require_keys(mapping: Any, keys: Iterable[str], where: str) -> None:
    if not isinstance(mapping, dict):
        raise ParamsError("%s 必须是对象" % where)
    missing = sorted(set(keys) - set(mapping))
    extra = sorted(set(mapping) - set(keys))
    if missing or extra:
        raise ParamsError("%s 键不齐：缺 %s，多 %s" % (where, missing, extra))


def _check_weights(weights: Any, where: str, expected_sum: float, expected_keys: Optional[Iterable[str]] = None) -> None:
    if expected_keys is not None:
        _require_keys(weights, expected_keys, where)
    if not isinstance(weights, dict) or not weights:
        raise ParamsError("%s 必须是非空对象" % where)
    for key, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ParamsError("%s.%s 必须是正数" % (where, key))
    if abs(sum(weights.values()) - expected_sum) > 1e-6:
        raise ParamsError("%s 权重和必须是 %s，实际 %s" % (where, expected_sum, sum(weights.values())))


def check_shape(default: Any, loaded: Any, where: str) -> None:
    """键齐全：与内置默认同构（同样的键、同样的值类型）；数值只要是数字，具体大小由专门的检查负责。"""
    if isinstance(default, dict):
        _require_keys(loaded, default.keys(), where)
        for key in default:
            check_shape(default[key], loaded[key], "%s.%s" % (where, key))
    elif isinstance(default, list):
        if not isinstance(loaded, list):
            raise ParamsError("%s 必须是数组" % where)
    elif isinstance(default, bool):
        if not isinstance(loaded, bool):
            raise ParamsError("%s 必须是布尔" % where)
    elif isinstance(default, (int, float)):
        if isinstance(loaded, bool) or not isinstance(loaded, (int, float)):
            raise ParamsError("%s 必须是数字" % where)
    elif isinstance(default, str):
        if not isinstance(loaded, str):
            raise ParamsError("%s 必须是字符串" % where)


def check_table(table: Any, where: str) -> None:
    _require_keys(table, ("direction", "cuts", "floor"), where)
    if table["direction"] not in ("higher", "lower"):
        raise ParamsError("%s.direction 只能是 higher/lower" % where)
    cuts = table["cuts"]
    if not isinstance(cuts, list) or not cuts:
        raise ParamsError("%s.cuts 必须是非空数组" % where)
    thresholds = []
    for index, cut in enumerate(cuts):
        if not (isinstance(cut, list) and len(cut) == 2 and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in cut)):
            raise ParamsError("%s.cuts[%d] 必须是 [阈值, 评分]" % (where, index))
        thresholds.append(cut[0])
    if len(set(thresholds)) != len(thresholds):
        raise ParamsError("%s.cuts 阈值重复" % where)
    if isinstance(table["floor"], bool) or not isinstance(table["floor"], (int, float)):
        raise ParamsError("%s.floor 必须是数字" % where)
    ordered = sorted(cuts, key=lambda c: c[0], reverse=(table["direction"] == "higher"))
    ratings = [c[1] for c in ordered]
    # 越接近「好」的一端评分越高：higher 时阈值大者评分高，lower 时阈值小者评分高。
    if any(a < b for a, b in zip(ratings, ratings[1:])):
        raise ParamsError("%s 评分对阈值不单调" % where)
    if ratings and table["floor"] > ratings[-1]:
        raise ParamsError("%s.floor 不得高于最差一档" % where)


def check_unit_interval(value: Any, where: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise ParamsError("%s 必须在 [0,1]" % where)


def load_params(
    default: Mapping[str, Any],
    validator: Callable[[Any], None],
    path: Optional[Path],
) -> Tuple[dict, List[dict]]:
    """读 params.json 并校验；文件缺失/损坏/校验失败一律回退内置默认，并把原因写进 findings。"""
    findings: List[dict] = []
    if path is None:
        return json.loads(json.dumps(default)), findings
    try:
        loaded = json.loads(Path(path).read_text("utf-8"))
        validator(loaded)
        return loaded, findings
    except FileNotFoundError:
        code = "PARAMS_FILE_MISSING"
        detail = str(path)
    except (OSError, ValueError) as exc:  # JSONDecodeError 与 ParamsError 都是 ValueError
        code = "PARAMS_INVALID"
        detail = "%s: %s" % (path, exc)
    findings.append({"code": code, "detail": detail, "action": "USING_BUILTIN_DEFAULTS"})
    return json.loads(json.dumps(default)), findings


def dedupe_refs(refs: Iterable[EvidenceRef]) -> Tuple[EvidenceRef, ...]:
    seen = set()
    out = []
    for ref in refs:
        key = (ref.kind, ref.label, ref.accession, ref.period_end)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return tuple(out)


@dataclass
class Receipt:
    """分支对单只股票的收据：机器可读，供中枢与页面使用。"""
    symbol: str
    cik: int
    name: str
    as_of: str
    verdict: str                              # PASS | ABSTAIN | FAILED
    label: str                                # Skill 自带的决策标签
    reasons: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"symbol": self.symbol, "cik": self.cik, "name": self.name, "as_of": self.as_of,
                "verdict": self.verdict, "label": self.label, "reasons": self.reasons, **self.detail}
