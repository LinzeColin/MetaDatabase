"""股势前瞻分支：标准库逻辑回归、标签口径（下一交易日入场、扣 0.3% 往返成本）、时点正确、滚动前推清洗、
基线对全模型、样本外 Brier 不优于基准概率就整分支 ABSTAIN（写明原因），PASS 必带 SEC 链接。"""

from __future__ import annotations

import copy
import json
import math
import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from signal_lattice.branches import foresight as F

START = date(2023, 6, 1)


def weekdays(n: int, start: date = START):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def walk(days, mu, sigma, rng, start_price=20.0):
    price, closes = start_price, []
    for _ in days:
        price *= math.exp(mu + sigma * rng.gauss(0, 1))
        closes.append(price)
    return (list(days), closes)


def entry(i, cap=1e9):
    return {"symbol": "S%02d" % i, "cik": 1000 + i, "name": "Synthetic %d" % i, "market_cap_usd": cap,
            "shares_outstanding": 1e7, "median_dollar_volume_20d_usd": 5e6}


def small_params(**overrides):
    p = copy.deepcopy(F.DEFAULT_PARAMS)
    p["panel"].update({"start": "2024-06-01", "max_symbols": 500, "min_bars": 200})
    p["walk_forward"].update({"min_train_dates": 4, "bootstrap_samples": 200})
    p["decision"].update({"min_oos_rows": 100, "min_oos_dates": 4, "min_train_rows": 100})
    p["features"]["extra"] = ["bn_score"]
    for section, values in overrides.items():
        p[section].update(values)
    return p


def universe(n, sigma_of, mu_of, days, seed=1):
    rng = random.Random(seed)
    entries = [entry(i) for i in range(n)]
    bars = {e["symbol"]: walk(days, mu_of(i), sigma_of(i), rng) for i, e in enumerate(entries)}
    bench = walk(days, 0.0, 0.0, rng, 100.0)       # 基准恒定：超额收益 = 个股收益
    return entries, bars, bench


LINK = lambda e: [{"url": "https://www.sec.gov/Archives/edgar/data/%d/x/y.htm" % e["cik"], "accession": "0000000001-26-000001",
                   "form": "10-Q", "filed": "2026-08-01", "supports": "latest_periodic_report"}]
QUIET = lambda msg: None


class LogisticTests(unittest.TestCase):
    def test_recovers_direction_and_calibrated_levels(self):
        rng = random.Random(3)
        xs, ys = [], []
        for _ in range(2000):
            x = rng.gauss(0, 1)
            xs.append([x])
            ys.append(1 if rng.random() < F.sigmoid(1.5 * x - 0.3) else 0)
        w = F.fit_logistic(xs, ys, l2=0.1)
        self.assertAlmostEqual(w[1], 1.5, delta=0.25)
        self.assertAlmostEqual(w[0], -0.3, delta=0.15)

    def test_l2_shrinks_weights_and_intercept_is_not_penalized(self):
        rng = random.Random(4)
        xs = [[rng.gauss(0, 1)] for _ in range(300)]
        ys = [1 if x[0] + rng.gauss(0, 1) > 0.5 else 0 for x in xs]
        loose, tight = F.fit_logistic(xs, ys, l2=0.01), F.fit_logistic(xs, ys, l2=500.0)
        self.assertLess(abs(tight[1]), abs(loose[1]))

    def test_platt_falls_back_to_identity_when_data_is_thin_or_single_class(self):
        self.assertEqual(F.fit_platt([0.1] * 10, [1, 0] * 5), (1.0, 0.0))
        self.assertEqual(F.fit_platt([0.1] * 100, [1] * 100), (1.0, 0.0))

    def test_platt_corrects_a_level_shift(self):
        rng = random.Random(5)
        scores = [rng.gauss(0, 1) for _ in range(3000)]
        ys = [1 if rng.random() < F.sigmoid(0.6 * s - 1.0) else 0 for s in scores]
        a, b = F.fit_platt(scores, ys)
        self.assertAlmostEqual(a, 0.6, delta=0.12)
        self.assertAlmostEqual(b, -1.0, delta=0.12)

    def test_brier_and_auc(self):
        self.assertAlmostEqual(F.brier([0.5, 0.5], [1, 0]), 0.25)
        self.assertEqual(F.auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]), 0.75)
        self.assertIsNone(F.auc([0.1, 0.2], [1, 1]))


class TimeCorrectnessTests(unittest.TestCase):
    def test_price_features_use_only_data_up_to_the_signal_day(self):
        days = weekdays(400)
        rng = random.Random(6)
        _, closes = walk(days, 0.0, 0.02, rng)
        index = 300
        before = F.price_features(days, closes, index, 200)
        mutated = closes[:index + 1] + [c * 7.0 for c in closes[index + 1:]]
        self.assertEqual(before, F.price_features(days, mutated, index, 200))
        self.assertLessEqual(before["dist_52w_high"], 0.0)
        self.assertIsNone(F.price_features(days, closes, 150, 200))        # 历史不够就没有特征

    def test_label_enters_next_trading_day_and_charges_round_trip_cost(self):
        days = weekdays(60)
        flat = [100.0] * 60
        bench = (days, flat)

        def stock_with_return(r):
            closes = [100.0] * 60
            for i in range(11, 60):                        # 信号日 = days[9]；入场 = days[10]；出场 = days[30]
                closes[i] = 100.0 * (1 + r) if i >= 30 else 100.0
            return (days, closes)

        y_low, ex_low, end = F.make_label(stock_with_return(0.002), bench, days[9], 20, 1, 0.003)
        y_high, ex_high, _ = F.make_label(stock_with_return(0.004), bench, days[9], 20, 1, 0.003)
        self.assertEqual((y_low, y_high), (0, 1))            # 超额 0.2% 扣 0.3% 成本 < 0；0.4% > 0.3%
        self.assertAlmostEqual(ex_high, 0.004)
        self.assertEqual(end, days[30])
        # 信号当日收盘不能当入场价：让信号日当天暴涨，标签不受影响
        spike = [100.0] * 60
        spike[9] = 500.0
        self.assertEqual(F.make_label((days, spike), bench, days[9], 20, 1, 0.003)[0], 0)

    def test_event_features_respect_the_publication_date(self):
        from types import SimpleNamespace as NS
        opp = lambda day, acc, amount: NS(kind="INSIDER_BUY_OPPORTUNISTIC", published_date=day, accession=acc, details={"amount_usd": amount})
        events = [opp("2026-05-01", "a", 100_000.0), opp("2026-06-20", "b", 300_000.0),
                  NS(kind="DILUTION_ATM", published_date="2026-06-25", accession="c", details={}),
                  NS(kind="SHARE_COUNT_GROWTH", published_date="2026-06-10", accession="d", details={})]
        early = F.event_features(events, "2026-06-01", 100e6)
        late = F.event_features(events, "2026-06-30", 100e6)
        self.assertEqual((early["ev_opportunistic_buy"], early["ev_dilution_90d"], early["ev_share_growth"]), (1.0, 0.0, 0.0))
        self.assertEqual((late["ev_dilution_90d"], late["ev_share_growth"]), (1.0, 1.0))
        self.assertAlmostEqual(late["ev_opportunistic_bps"], min(400_000 / 100e6 * 1e4, 40.0) / 40.0)


class WalkForwardTests(unittest.TestCase):
    def rows(self, dates, per_date=40, seed=7, label_lag=1):
        rng = random.Random(seed)
        out = []
        future = ["2030-%02d-28" % m for m in range(1, 10)]          # 超出样本的日期，标签揭晓日可以落在这里
        extended = list(dates) + future
        for k, d in enumerate(dates):
            end = extended[k + label_lag] if label_lag else d
            for s in range(per_date):
                x = rng.gauss(0, 1)
                out.append(F.Row(d, "S%d" % s, 1 if rng.random() < F.sigmoid(1.2 * x) else 0, 0.0, end,
                                 {"dist_52w_high": x, "vol_60d": rng.random(), "bn_score": rng.random()}))
        return out

    def test_training_only_uses_rows_whose_labels_were_known_before_the_prediction_day(self):
        dates = ["2025-%02d-28" % m for m in range(1, 13)]
        rows = self.rows(dates, label_lag=3)              # 每个标签要 3 个月才揭晓
        params = small_params()
        summary = F.evaluate_walk_forward(rows, dates, ["dist_52w_high"], ["dist_52w_high", "bn_score"], params)
        for fold in summary["folds"]:
            k = dates.index(fold["date"])
            self.assertEqual(fold["train_dates"], max(0, k - 2))          # 只有 k-3 之前（含）的月份标签已揭晓
            self.assertEqual(fold["train_rows"], fold["train_dates"] * 40)

    def test_pure_noise_is_not_better_than_the_base_rate_and_branch_abstains(self):
        rng = random.Random(8)
        dates = ["2024-%02d-28" % m for m in range(1, 13)] + ["2025-%02d-28" % m for m in range(1, 13)]
        rows = [F.Row(d, "S%d" % s, 1 if rng.random() < 0.5 else 0, 0.0, d,
                      {"dist_52w_high": rng.gauss(0, 1), "vol_60d": rng.random(), "bn_score": rng.random()})
                for d in dates for s in range(60)]
        # 标签揭晓日取同一天（极端情形）也不允许用当天行训练：date < d 是硬条件
        summary = F.evaluate_walk_forward(rows, dates, ["dist_52w_high", "vol_60d"], ["dist_52w_high", "vol_60d", "bn_score"], small_params())
        status, reasons = F.branch_decision(summary, small_params())
        self.assertEqual(status, "ABSTAIN")
        self.assertTrue(reasons[0].startswith("OOS_BRIER_NOT_BETTER_THAN_BASE_RATE"), reasons)
        self.assertFalse(summary["selected_beats_constant"])

    def test_informative_baseline_feature_beats_the_base_rate(self):
        dates = ["2024-%02d-28" % m for m in range(1, 13)] + ["2025-%02d-28" % m for m in range(1, 13)]
        rows = self.rows(dates, per_date=60, seed=9, label_lag=0)
        summary = F.evaluate_walk_forward(rows, dates, ["dist_52w_high", "vol_60d"], ["dist_52w_high", "vol_60d", "bn_score"], small_params())
        self.assertTrue(summary["selected_beats_constant"])
        self.assertLess(summary["brier"]["baseline_model"], summary["brier"]["const"])
        self.assertEqual(F.branch_decision(summary, small_params())[0], "PASS")
        self.assertFalse(summary["full_beats_baseline_model"])        # 多加的 bn_score 是噪声：全模型对不过基线 -> 用基线
        self.assertEqual(summary["selected_model"], "baseline_model")

    def test_insufficient_oos_window_abstains_instead_of_publishing(self):
        dates = ["2025-%02d-28" % m for m in range(1, 9)]
        rows = self.rows(dates, per_date=30, seed=10, label_lag=0)
        summary = F.evaluate_walk_forward(rows, dates, ["dist_52w_high"], ["dist_52w_high", "bn_score"], small_params())
        params = small_params(decision={"min_oos_dates": 6})
        status, reasons = F.branch_decision(summary, params)
        self.assertEqual(status, "ABSTAIN")
        self.assertTrue(reasons[0].startswith("SAMPLE_INSUFFICIENT"))

    def test_feature_with_low_training_coverage_is_dropped_and_reported(self):
        dates = ["2025-%02d-28" % m for m in range(1, 11)]
        rows = self.rows(dates, per_date=40, seed=11, label_lag=0)
        for r in rows:
            r.features["lazy_prices_pct"] = 0.5 if r.symbol == "S0" else None       # 只有 2.5% 的行有值
        params = small_params()
        model = F.fit_model(rows, ["dist_52w_high", "lazy_prices_pct"], params)
        self.assertIn("lazy_prices_pct", model.spec.dropped)
        self.assertIn("覆盖率", model.spec.dropped["lazy_prices_pct"])
        self.assertEqual(model.spec.names, ["dist_52w_high"])


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.days = weekdays(720)

    def test_volatility_carries_signal_so_branch_passes_and_each_pass_has_a_link(self):
        # 高波动股带正漂移、低波动股带负漂移：单靠 vol_60d 就能预测超额收益方向
        entries, bars, bench = universe(40, lambda i: 0.04 if i % 2 == 0 else 0.008, lambda i: 0.004 if i % 2 == 0 else -0.003, self.days)
        result = F.run_with(entries, bars, bench, self.days[-1], small_params(), None, LINK, QUIET)
        self.assertEqual(result["branch_status"], "PASS", result["branch_reasons"])
        summary = result["meta"]["summary"]
        self.assertLess(summary["brier"][summary["selected_model"]], summary["brier"]["const"])
        verdicts = {v["symbol"]: v for v in result["verdicts"]}
        self.assertEqual(len(verdicts), 40)
        passes = [v for v in verdicts.values() if v["verdict"] == "PASS"]
        self.assertTrue(passes)
        for v in passes:
            self.assertTrue(v["links"])
            self.assertTrue(v["links"][0]["url"].startswith("https://www.sec.gov/"))
            ev = v["evidence"]
            self.assertGreaterEqual(ev["probability_lift"], 0.05)
            self.assertGreaterEqual(ev["efs_score"], 55.0)
            self.assertAlmostEqual(ev["efs_score"] / 100 - ev["baseline_prob"], ev["probability_lift"], delta=0.0006)
            self.assertGreater(ev["sample_rows"], 100)
            self.assertIsNotNone(ev["brier_model_oos"])
        self.assertTrue(all(verdicts["S%02d" % i]["verdict"] != "PASS" for i in range(1, 40, 2)))     # 低波动负漂移的一个也不 PASS

    def test_no_signal_world_abstains_with_a_reason_and_every_stock_abstains(self):
        entries, bars, bench = universe(40, lambda i: 0.02, lambda i: 0.0, self.days, seed=2)
        result = F.run_with(entries, bars, bench, self.days[-1], small_params(), None, LINK, QUIET)
        self.assertEqual(result["branch_status"], "ABSTAIN")
        self.assertTrue(result["branch_reasons"][0].startswith("OOS_BRIER_NOT_BETTER_THAN_BASE_RATE"), result["branch_reasons"])
        self.assertTrue(all(v["verdict"] == "ABSTAIN" and v["reasons"][0] == "BRANCH_ABSTAIN" for v in result["verdicts"]))
        self.assertEqual(result["meta"]["abstain_reasons"], result["branch_reasons"])

    def test_pass_without_a_link_is_downgraded(self):
        entries, bars, bench = universe(40, lambda i: 0.04 if i % 2 == 0 else 0.008, lambda i: 0.004 if i % 2 == 0 else -0.003, self.days)
        result = F.run_with(entries, bars, bench, self.days[-1], small_params(), None, lambda e: [], QUIET)
        self.assertEqual(result["branch_status"], "PASS")
        self.assertFalse([v for v in result["verdicts"] if v["verdict"] == "PASS"])
        self.assertTrue(any("PASS_REQUIRES_PRIMARY_SEC_LINK" in v["reasons"] for v in result["verdicts"]))

    def test_rows_for_a_day_do_not_change_when_future_prices_change(self):
        entries, bars, bench = universe(12, lambda i: 0.02, lambda i: 0.0, self.days, seed=5)
        params = small_params()
        dates = F.prediction_dates_for(bench[0], params)
        target = dates[6]
        rows = {r.symbol: r.features for r in F.build_rows(entries, bars, bench, [target], params, None, QUIET)}
        cut = self.days.index(target)
        future = {s: (d, c[:cut + 1] + [x * 3.0 for x in c[cut + 1:]]) for s, (d, c) in bars.items()}
        rows2 = {r.symbol: r.features for r in F.build_rows(entries, future, bench, [target], params, None, QUIET)}
        self.assertEqual(rows, rows2)

    def test_prediction_dates_stop_before_labels_run_off_the_calendar(self):
        params = small_params()
        dates = F.prediction_dates_for(self.days, params)
        last = self.days.index(dates[-1])
        self.assertLess(last + 1 + params["label"]["horizon_trading_days"], len(self.days))
        self.assertTrue(all(d >= params["panel"]["start"] for d in dates))


class ParamsTests(unittest.TestCase):
    def test_file_equals_builtin_defaults_and_validates(self):
        loaded, findings = F.load_params()
        self.assertEqual((loaded, findings), (F.DEFAULT_PARAMS, []))
        self.assertEqual(F.DEFAULT_PARAMS_PATH.parts[-3:], ("equity-foresight-signal-skill", "runtime", "params.json"))

    def test_rejects_same_day_entry_unknown_feature_and_bad_cost(self):
        for mutate, text in ((lambda p: p["label"].update(entry_lag_trading_days=0), "入场"),
                             (lambda p: p["features"]["extra"].append("tomorrow_return"), "未知特征"),
                             (lambda p: p["label"].update(round_trip_cost=0.5), "round_trip_cost"),
                             (lambda p: p["features"]["extra"].append("dist_52w_high"), "重叠")):
            p = copy.deepcopy(F.DEFAULT_PARAMS)
            mutate(p)
            with self.assertRaises(F.ParamsError) as ctx:
                F.validate_params(p)
            self.assertIn(text, str(ctx.exception))

    def test_bad_params_file_falls_back_with_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "params.json"
            bad = copy.deepcopy(F.DEFAULT_PARAMS)
            bad["label"]["entry_lag_trading_days"] = 0
            path.write_text(json.dumps(bad), "utf-8")
            params, findings = F.load_params(path)
            self.assertEqual(params, F.DEFAULT_PARAMS)
            self.assertEqual(findings[0]["code"], "PARAMS_INVALID")


if __name__ == "__main__":
    unittest.main()
