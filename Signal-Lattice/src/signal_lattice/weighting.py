"""Stage 3 贡献度动态权重。

只读取 Stage 4 落盘的严格样本外贡献度样本，并在现有分支资格门之后分配权重。
这里不改变 PROMO-1、数据新鲜度或任何分支的实现状态。
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


# 八个完整的六个月样本外窗口约覆盖四年实际在场期。它比 S1 当前的四个窗口
# 更能降低单一市场阶段主导权重的风险，同时不为了启用动态权重而降低门槛。
MIN_CONTRIBUTION_SAMPLES = 8

# risk_adjusted_excess 可明显大于 1；η=0.10 时 r=2.5 的单期倍率为 e^0.25≈1.28，
# 能反映贡献差异，也不会让一个窗口直接决定全部后续权重。
HEDGE_LEARNING_RATE = 0.10

# risk_adjusted_excess 是以 active volatility 标准化后的单期量。把它限定在 ±20
# 个标准化单位后，单期 Hedge 对数更新位于 ±2，倍率位于 e^-2 至 e^2；极端贡献
# 仍能显著影响权重，同时极小波动率产生的有限异常值不会主导整个权重轨迹。
MAX_STANDARDIZED_CONTRIBUTION = 20.0

# 保留每个动态分支至少 5% 的恢复空间；单个分支最多 60%，使其余分支至少保留
# 40% 的比较空间。只有一个可参与分支时不存在可比较对象，冷启动权重为 100%。
WEIGHT_FLOOR = 0.05
WEIGHT_CAP = 0.60


def load_contribution_samples(path: Path | None) -> tuple[list[dict[str, Any]], str]:
    """读取 Stage 4 的贡献度落盘，缺失或不可读取时明确返回空样本状态。"""
    if path is None:
        return [], "CONTRIBUTION_SAMPLES_PATH_NOT_PROVIDED"
    if not path.is_file():
        return [], "CONTRIBUTION_SAMPLES_NOT_FOUND"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], "CONTRIBUTION_SAMPLES_UNREADABLE"
    raw_samples = payload.get("samples", []) if isinstance(payload, Mapping) else payload
    if not isinstance(raw_samples, list):
        return [], "CONTRIBUTION_SAMPLES_INVALID"
    return [sample for sample in raw_samples if isinstance(sample, dict)], "CONTRIBUTION_SAMPLES_LOADED"


def build_weighting_from_state(
    state_dir: Path | None,
    *,
    branch_ids: Iterable[str],
    eligible_branch_ids: Iterable[str],
    branch_participation: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """从 ``state_dir/backtest/contribution_samples.json`` 构建可审计权重。"""
    sample_path = state_dir / "backtest" / "contribution_samples.json" if state_dir else None
    samples, source_status = load_contribution_samples(sample_path)
    result = calculate_contribution_weights(
        samples,
        branch_ids=branch_ids,
        eligible_branch_ids=eligible_branch_ids,
        branch_participation=branch_participation,
    )
    result["source"] = {
        "path": str(sample_path) if sample_path else None,
        "status": source_status,
        "loaded_sample_count": len(samples),
    }
    return result


def calculate_contribution_weights(
    samples: Sequence[Mapping[str, Any]],
    *,
    branch_ids: Iterable[str],
    eligible_branch_ids: Iterable[str],
    branch_participation: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """用 Hedge 在已获资格的分支间计算权重，并保留每一步可复算轨迹。

    同一 ``period_start/period_end/window_label`` 的分支样本同步更新；某分支在
    某期没有样本时该期乘数为 1。样本不足的已资格分支固定在其冷启动等权份额，
    充足分支在剩余份额内进行 Hedge 更新。
    """
    all_branch_ids = sorted({str(branch_id) for branch_id in branch_ids})
    eligible = sorted({str(branch_id) for branch_id in eligible_branch_ids if str(branch_id) in all_branch_ids})
    participation = dict(branch_participation or {})
    samples_by_branch: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        branch_id = sample.get("branch_id")
        if isinstance(branch_id, str) and branch_id in all_branch_ids:
            samples_by_branch[branch_id].append(sample)

    details = {
        branch_id: _branch_detail(
            branch_id,
            samples_by_branch.get(branch_id, []),
            eligible=branch_id in eligible,
            participation_status=participation.get(branch_id),
        )
        for branch_id in all_branch_ids
    }
    eligible_details = [details[branch_id] for branch_id in eligible]
    sufficient = [item for item in eligible_details if item["usable_sample_count"] >= MIN_CONTRIBUTION_SAMPLES]
    insufficient = [item for item in eligible_details if item["usable_sample_count"] < MIN_CONTRIBUTION_SAMPLES]
    weight_sample_count = sum(item["usable_sample_count"] for item in eligible_details)

    if not eligible:
        return _result("COLD_START_EQUAL", weight_sample_count, details, eligible)

    if not sufficient:
        equal_weight = 1.0 / len(eligible)
        for item in eligible_details:
            item["weight"] = equal_weight
            item["weight_status"] = _insufficient_status(item["usable_sample_count"])
            item["weight_trajectory_summary"] = {"start_weight": equal_weight, "end_weight": equal_weight}
        return _result("COLD_START_EQUAL", weight_sample_count, details, eligible)

    cold_start_share = 1.0 / len(eligible)
    for item in insufficient:
        item["weight"] = cold_start_share
        item["weight_status"] = _insufficient_status(item["usable_sample_count"])
        item["weight_trajectory_summary"] = {"start_weight": cold_start_share, "end_weight": cold_start_share}

    dynamic_ids = [item["branch_id"] for item in sufficient]
    dynamic_mass = 1.0 - cold_start_share * len(insufficient)
    dynamic_weights, calculation_issue = _hedge_weights(dynamic_ids, details, dynamic_mass)
    if calculation_issue:
        equal_weight = 1.0 / len(eligible)
        for item in eligible_details:
            item["weight"] = equal_weight
            item["weight_status"] = f"COLD_START_EQUAL_WEIGHTING_DEGRADED:{calculation_issue}"
            item["weighting_degradation"] = calculation_issue
            item["weight_trajectory"] = []
            item["weight_trajectory_summary"] = {"start_weight": equal_weight, "end_weight": equal_weight}
        return _result("COLD_START_EQUAL", weight_sample_count, details, eligible)

    for branch_id, weight in dynamic_weights.items():
        item = details[branch_id]
        item["weight"] = weight
        item["weight_status"] = "CONTRIBUTION_WEIGHTED"
        _mark_negative_floor(item)

    return _result("CONTRIBUTION_WEIGHTED", weight_sample_count, details, eligible)


def _branch_detail(
    branch_id: str,
    samples: Sequence[Mapping[str, Any]],
    *,
    eligible: bool,
    participation_status: str | None,
) -> dict[str, Any]:
    usable = []
    risk_adjusted_values: list[float] = []
    source_counts = {"risk_adjusted_excess": 0, "excess_return_fallback": 0}
    for sample in samples:
        metric = _sample_metric(sample)
        if metric is None:
            continue
        value, source = metric
        usable.append((sample, value, source))
        source_counts[source] += 1
        if source == "risk_adjusted_excess":
            risk_adjusted_values.append(value)

    detail: dict[str, Any] = {
        "branch_id": branch_id,
        "weight": 0.0,
        "sample_count": len(samples),
        "usable_sample_count": len(usable),
        "minimum_contribution_samples": MIN_CONTRIBUTION_SAMPLES,
        "cumulative_risk_adjusted_excess": sum(risk_adjusted_values),
        "cumulative_update_contribution": sum(value for _, value, _ in usable),
        "negative_update_count": sum(1 for _, value, _ in usable if value < 0.0),
        "metric_source_counts": source_counts,
        "metric_source": _metric_source_label(source_counts),
        "contribution_input_truncation": {
            "limit_standardized_units": MAX_STANDARDIZED_CONTRIBUTION,
            "truncated_period_count": 0,
            "status": "NONE",
        },
        "weight_trajectory": [],
        "weight_trajectory_summary": {"start_weight": 0.0, "end_weight": 0.0},
        "participation_status": participation_status or ("COLD_START_ELIGIBLE" if eligible else "UNSPECIFIED"),
        "eligible_for_weighting": eligible,
        "negative_contribution_status": "NONE",
    }
    if not eligible:
        detail["weight_status"] = f"EXCLUDED_BY_BRANCH_GATE:{detail['participation_status']}"
    elif len(usable) < MIN_CONTRIBUTION_SAMPLES:
        detail["weight_status"] = _insufficient_status(len(usable))
    else:
        detail["weight_status"] = "CONTRIBUTION_WEIGHTED_PENDING"
    detail["_usable_samples"] = usable
    return detail


def _sample_metric(sample: Mapping[str, Any]) -> tuple[float, str] | None:
    risk_adjusted = _finite_number(sample.get("risk_adjusted_excess"))
    if risk_adjusted is not None:
        return risk_adjusted, "risk_adjusted_excess"
    excess = _finite_number(sample.get("excess_return"))
    if excess is not None:
        return excess, "excess_return_fallback"
    return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metric_source_label(counts: Mapping[str, int]) -> str:
    risk_count = counts["risk_adjusted_excess"]
    fallback_count = counts["excess_return_fallback"]
    if risk_count and fallback_count:
        return "MIXED_RISK_ADJUSTED_EXCESS_AND_EXCESS_RETURN_FALLBACK"
    if risk_count:
        return "RISK_ADJUSTED_EXCESS"
    if fallback_count:
        return "EXCESS_RETURN_FALLBACK"
    return "NO_USABLE_CONTRIBUTION"


def _hedge_weights(
    dynamic_ids: Sequence[str],
    details: Mapping[str, dict[str, Any]],
    total_mass: float,
) -> tuple[dict[str, float], str | None]:
    """同步执行对数 Hedge 更新，并把每期的起止权重保存在分支自身轨迹中。"""
    weights = _bounded_normalize({branch_id: 1.0 for branch_id in dynamic_ids}, total_mass)
    if weights is None:
        return {}, "WEIGHT_BOUNDS_INFEASIBLE_FOR_DYNAMIC_COHORT"
    for branch_id in dynamic_ids:
        details[branch_id]["weight_trajectory_summary"] = {
            "start_weight": weights[branch_id],
            "end_weight": weights[branch_id],
        }

    periods: dict[tuple[str, str, str], dict[str, list[tuple[float, str]]]] = defaultdict(lambda: defaultdict(list))
    for branch_id in dynamic_ids:
        for sample, value, source in details[branch_id]["_usable_samples"]:
            key = (
                str(sample.get("period_start", "")),
                str(sample.get("period_end", "")),
                str(sample.get("window_label", "")),
            )
            periods[key][branch_id].append((value, source))

    for period_start, period_end, window_label in sorted(periods):
        updates = periods[(period_start, period_end, window_label)]
        starting = dict(weights)
        if any(weight <= 0.0 or not math.isfinite(weight) for weight in starting.values()):
            return {}, "WEIGHT_START_STATE_UNCOMPUTABLE"
        candidate_logs: dict[str, float] = {}
        period_metrics: dict[str, tuple[float | None, float | None, str, bool]] = {}
        for branch_id in dynamic_ids:
            values = updates.get(branch_id, [])
            if values:
                raw_update_value = _finite_mean([value for value, _ in values])
                if raw_update_value is None:
                    return {}, "WEIGHT_PERIOD_INPUT_UNCOMPUTABLE"
                update_value, truncated = _truncate_standardized_contribution(raw_update_value)
                sources = {source for _, source in values}
                source = next(iter(sources)) if len(sources) == 1 else "MIXED_PERIOD_METRICS"
                candidate_logs[branch_id] = math.log(starting[branch_id]) + HEDGE_LEARNING_RATE * update_value
                period_metrics[branch_id] = (raw_update_value, update_value, source, truncated)
            else:
                candidate_logs[branch_id] = math.log(starting[branch_id])
                period_metrics[branch_id] = (None, None, "NO_SAMPLE_NO_UPDATE", False)
        weights = _log_sum_exp_normalize(candidate_logs, total_mass)
        if weights is None:
            return {}, "WEIGHT_LOG_NORMALIZATION_UNCOMPUTABLE"
        for branch_id in dynamic_ids:
            raw_update_value, update_value, source, truncated = period_metrics[branch_id]
            multiplier = math.exp(HEDGE_LEARNING_RATE * update_value) if update_value is not None else 1.0
            unconstrained_weight = starting[branch_id] * multiplier
            truncation = details[branch_id]["contribution_input_truncation"]
            if truncated:
                truncation["truncated_period_count"] += 1
                truncation["status"] = "STANDARDIZED_CONTRIBUTION_TRUNCATED"
            details[branch_id]["weight_trajectory"].append(
                {
                    "period_start": period_start,
                    "period_end": period_end,
                    "window_label": window_label,
                    "start_weight": starting[branch_id],
                    "raw_update_value": raw_update_value,
                    "update_value": update_value,
                    "metric_source": source,
                    "input_truncated": truncated,
                    "unconstrained_log_weight": candidate_logs[branch_id],
                    "unconstrained_weight": unconstrained_weight,
                    "end_weight": weights[branch_id],
                }
            )
            details[branch_id]["weight_trajectory_summary"]["end_weight"] = weights[branch_id]
    return weights, None


def _finite_mean(values: Sequence[float]) -> float | None:
    """缩放后求均值，有限的极端输入仍能保持有限均值。"""
    if not values or any(not math.isfinite(value) for value in values):
        return None
    scale = max(abs(value) for value in values)
    if scale == 0.0:
        return 0.0
    return math.fsum(value / scale for value in values) / len(values) * scale


def _truncate_standardized_contribution(value: float) -> tuple[float, bool]:
    if value > MAX_STANDARDIZED_CONTRIBUTION:
        return MAX_STANDARDIZED_CONTRIBUTION, True
    if value < -MAX_STANDARDIZED_CONTRIBUTION:
        return -MAX_STANDARDIZED_CONTRIBUTION, True
    return value, False


def _log_sum_exp_normalize(log_weights: Mapping[str, float], total_mass: float) -> dict[str, float] | None:
    """用 log-sum-exp 转成相对权重，再投影到既有的 floor/cap 边界。"""
    if not log_weights or any(not math.isfinite(value) for value in log_weights.values()):
        return None
    maximum = max(log_weights.values())
    relative = {branch_id: math.exp(value - maximum) for branch_id, value in log_weights.items()}
    return _bounded_normalize(relative, total_mass)


def _bounded_normalize(raw_weights: Mapping[str, float], total_mass: float) -> dict[str, float] | None:
    """把正权重投影到总和为 ``total_mass`` 且每项受 floor/cap 约束的单纯形。"""
    branch_ids = sorted(raw_weights)
    if not branch_ids or not math.isfinite(total_mass) or total_mass <= 0.0:
        return None
    if any(weight <= 0.0 or not math.isfinite(weight) for weight in raw_weights.values()):
        return None
    if len(branch_ids) == 1:
        return {branch_ids[0]: total_mass}
    if total_mass < len(branch_ids) * WEIGHT_FLOOR or total_mass > len(branch_ids) * WEIGHT_CAP:
        return None

    remaining = set(branch_ids)
    allocated: dict[str, float] = {}
    remaining_mass = total_mass
    while remaining:
        denominator = sum(raw_weights[branch_id] for branch_id in remaining)
        if denominator <= 0.0 or not math.isfinite(denominator):
            return None
        proposed = {
            branch_id: (raw_weights[branch_id] / denominator * remaining_mass)
            for branch_id in remaining
        }
        high = sorted(branch_id for branch_id, value in proposed.items() if value > WEIGHT_CAP)
        low = sorted(branch_id for branch_id, value in proposed.items() if value < WEIGHT_FLOOR)
        if not high and not low:
            allocated.update(proposed)
            break
        # 先固定超 cap 的项。它释放的份额会首先回流给较低项；同轮同时把
        # 低项固定会丢失这部分份额，破坏总权重为 1 的不变量。
        for branch_id in high:
            allocated[branch_id] = WEIGHT_CAP
            remaining.remove(branch_id)
            remaining_mass -= WEIGHT_CAP
        if not high:
            for branch_id in low:
                allocated[branch_id] = WEIGHT_FLOOR
                remaining.remove(branch_id)
                remaining_mass -= WEIGHT_FLOOR
    if len(allocated) != len(branch_ids) or any(not math.isfinite(weight) for weight in allocated.values()):
        return None
    return allocated


def _insufficient_status(sample_count: int) -> str:
    return f"INSUFFICIENT_CONTRIBUTION_SAMPLES: {sample_count}/{MIN_CONTRIBUTION_SAMPLES}"


def _mark_negative_floor(item: dict[str, Any]) -> None:
    at_floor = math.isclose(item["weight"], WEIGHT_FLOOR, abs_tol=1e-12)
    if item["cumulative_update_contribution"] >= 0.0 or not at_floor:
        return
    if item["negative_update_count"] >= 2:
        item["negative_contribution_status"] = "PERSISTENT_NEGATIVE_CONTRIBUTION_AT_FLOOR"
        item["negative_contribution_message"] = "持续负贡献，已压至下限。"
    else:
        item["negative_contribution_status"] = "NEGATIVE_CONTRIBUTION_AT_FLOOR"
        item["negative_contribution_message"] = "负贡献，已压至下限。"


def _result(
    weight_mode: str,
    weight_sample_count: int,
    details: Mapping[str, dict[str, Any]],
    eligible_branch_ids: Sequence[str],
) -> dict[str, Any]:
    branches = []
    for branch_id in sorted(details):
        item = dict(details[branch_id])
        item.pop("_usable_samples", None)
        branches.append(item)
    return {
        "weight_mode": weight_mode,
        "weight_sample_count": weight_sample_count,
        "minimum_contribution_samples": MIN_CONTRIBUTION_SAMPLES,
        "learning_rate": HEDGE_LEARNING_RATE,
        "max_standardized_contribution": MAX_STANDARDIZED_CONTRIBUTION,
        "weight_floor": WEIGHT_FLOOR,
        "weight_cap": WEIGHT_CAP,
        "eligible_branch_ids": list(eligible_branch_ids),
        "branches": branches,
        "weights": {item["branch_id"]: item["weight"] for item in branches},
    }
