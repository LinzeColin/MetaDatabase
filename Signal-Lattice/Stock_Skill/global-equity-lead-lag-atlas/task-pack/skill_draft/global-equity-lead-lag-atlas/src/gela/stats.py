from __future__ import annotations

import math
import random
from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("不能计算空序列均值")
    return sum(values) / len(values)


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    mx, my = mean(x), mean(y)
    dx = [value - mx for value in x]
    dy = [value - my for value in y]
    denom = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom <= 0:
        return None
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(dx, dy)) / denom))


def ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_rank = (cursor + 1 + end) / 2.0
        for index in range(cursor, end):
            result[indexed[index][0]] = average_rank
        cursor = end
    return result


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    return pearson(ranks(x), ranks(y))


def fisher_two_sided_p(r: float | None, n_effective: int) -> float | None:
    if r is None or n_effective <= 3:
        return None
    clipped = max(-0.999999999, min(0.999999999, r))
    z = abs(math.atanh(clipped) * math.sqrt(n_effective - 3))
    return math.erfc(z / math.sqrt(2.0))


def benjamini_hochberg(p_values: Sequence[float | None]) -> list[float | None]:
    valid = [(index, value) for index, value in enumerate(p_values) if value is not None]
    result: list[float | None] = [None] * len(p_values)
    if not valid:
        return result
    ordered = sorted(valid, key=lambda item: item[1])
    m = len(ordered)
    running = 1.0
    adjusted: dict[int, float] = {}
    for rank_from_end, (index, value) in enumerate(reversed(ordered), start=1):
        rank = m - rank_from_end + 1
        candidate = min(1.0, value * m / rank)
        running = min(running, candidate)
        adjusted[index] = running
    for index, value in adjusted.items():
        result[index] = value
    return result


def conservative_effective_n(n_raw: int, horizon: int) -> int:
    if n_raw <= 0:
        return 0
    return max(1, n_raw // max(1, horizon))


def circular_block_bootstrap_ci(
    x: Sequence[float],
    y: Sequence[float],
    repetitions: int,
    block_size: int,
    seed: int,
) -> tuple[float | None, float | None]:
    if len(x) != len(y) or len(x) < 8 or repetitions <= 0:
        return None, None
    n = len(x)
    block = max(1, min(block_size, n))
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(repetitions):
        indices: list[int] = []
        while len(indices) < n:
            start = rng.randrange(n)
            indices.extend((start + offset) % n for offset in range(block))
        indices = indices[:n]
        value = pearson([x[i] for i in indices], [y[i] for i in indices])
        if value is not None:
            samples.append(value)
    if len(samples) < max(20, repetitions // 4):
        return None, None
    samples.sort()
    low_index = max(0, math.floor(0.025 * (len(samples) - 1)))
    high_index = min(len(samples) - 1, math.ceil(0.975 * (len(samples) - 1)))
    return samples[low_index], samples[high_index]


def rolling_sign_stability(
    x: Sequence[float], y: Sequence[float], windows: int, reference: float
) -> float | None:
    if len(x) != len(y) or len(x) < max(12, windows * 5) or reference == 0:
        return None
    windows = max(2, windows)
    width = len(x) // windows
    signs: list[bool] = []
    for index in range(windows):
        start = index * width
        end = len(x) if index == windows - 1 else (index + 1) * width
        value = pearson(x[start:end], y[start:end])
        if value is not None and value != 0:
            signs.append((value > 0) == (reference > 0))
    if not signs:
        return None
    return sum(1 for value in signs if value) / len(signs)


def linear_fit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float] | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    mx, my = mean(x), mean(y)
    denominator = sum((value - mx) ** 2 for value in x)
    if denominator <= 0:
        return None
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / denominator
    return my - slope * mx, slope


def out_of_sample_mse_improvement(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 30:
        return None
    split = max(15, int(len(x) * 0.7))
    if len(x) - split < 8:
        return None
    fit = linear_fit(x[:split], y[:split])
    if fit is None:
        return None
    intercept, slope = fit
    baseline = mean(y[:split])
    actual = y[split:]
    baseline_mse = mean([(value - baseline) ** 2 for value in actual])
    model_mse = mean([(value - (intercept + slope * feature)) ** 2 for feature, value in zip(x[split:], actual)])
    if baseline_mse <= 0:
        return None
    return (baseline_mse - model_mse) / baseline_mse
