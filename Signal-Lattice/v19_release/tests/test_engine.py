from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from signal_lattice_v19.decision import _qualifies, decide
from signal_lattice_v19.engine import V19Engine
from signal_lattice_v19.models import Candidate, Metrics, SkillResult
from signal_lattice_v19.storage import RuntimeStorage
from signal_lattice_v19.skills import run_six_skills

from common import fixture_settings

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def test_price_only_theme_cannot_replace_current_winner(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            result = V19Engine(settings).run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
            first = result["report"]["第一板块"]
            self.assertEqual(first["代码"], "SPY")
            self.assertEqual(first["唯一操作"], "持有")
            bullish = result["internal"]["qualification"]["bullish"]
            self.assertFalse(bullish["passed"])
            self.assertIn("缺少候选级非价格方法支持", bullish["reasons"])

    def test_six_methods_freeze_before_single_decision(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            result = V19Engine(settings).run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
            rows = result["report"]["第二板块"]["矩阵"]
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(row["适用状态"] == "适用" for row in rows))
            self.assertTrue(all(row["运行方式"] == "方法契约" for row in rows))
            self.assertTrue(all("本轮贡献" in row["独立性"] for row in rows))
            self.assertEqual(result["report"]["技能适用覆盖率"], "100.0%")

    def test_skill_output_labels_the_frozen_local_substitute_and_its_binding(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            result = V19Engine(settings).run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
            internal_skills = result["internal"]["skills"]
            self.assertEqual(len(internal_skills), 6)
            self.assertTrue(all(row["source_state"] == "冻结本地替代" for row in internal_skills))
            self.assertTrue(all(row["method_version"].startswith("v19-frozen-local-contract-1:") for row in internal_skills))
            self.assertTrue(all("Canonical SKILL.md 未执行" in row["method_evidence"] for row in internal_skills))
            visible = [row["独立性"] for row in result["report"]["第二板块"]["矩阵"]]
            self.assertTrue(all("冻结本地替代" in value for value in visible))
            self.assertFalse(any("Canonical方法已读取" in value for value in visible))

    def test_two_consecutive_slots_keep_fifteen_second_contract(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            engine = V19Engine(settings)
            first = engine.run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
            second = engine.run_once(datetime(2026, 8, 14, 0, 0, 16, tzinfo=timezone.utc))
            self.assertEqual(first["refresh_seconds"], 15)
            self.assertNotEqual(first["report"]["运行时间"], second["report"]["运行时间"])
            self.assertTrue(second["report"]["第一板块"]["下一正式复核"].startswith("2026-08-14 11:00:00"))

    def test_only_the_scheduled_review_runs_six_skills_and_central_adjudication(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            engine = V19Engine(settings)
            with patch("signal_lattice_v19.engine.run_six_skills", wraps=run_six_skills) as skills, patch(
                "signal_lattice_v19.engine.decide", wraps=decide
            ) as adjudicate:
                engine.run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
                second = engine.run_once(datetime(2026, 8, 14, 0, 0, 16, tzinfo=timezone.utc))

            self.assertEqual(skills.call_count, 1)
            self.assertEqual(adjudicate.call_count, 1)
            self.assertEqual(second["internal"]["review_gate"]["mode"], "OBSERVATION_ONLY")
            self.assertIn("本轮仅作市场观察", second["report"]["第一板块"]["核心依据"])

    def test_material_price_move_promotes_an_early_formal_review(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            engine = V19Engine(settings)
            engine.run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
            original_snapshot = engine.provider.snapshot

            def moved_snapshot(candidates, now, include_history):
                rows = original_snapshot(candidates, now, include_history)
                for row in rows:
                    if row.provider_code == "AU.SPY":
                        row.price = float(row.price or 0.0) * 1.03
                return rows

            with patch.object(engine.provider, "snapshot", side_effect=moved_snapshot), patch(
                "signal_lattice_v19.engine.run_six_skills", wraps=run_six_skills
            ) as skills:
                result = engine.run_once(datetime(2026, 8, 14, 0, 0, 16, tzinfo=timezone.utc))

            self.assertEqual(skills.call_count, 1)
            self.assertEqual(result["internal"]["review_gate"]["mode"], "FORMAL_REVIEW")
            self.assertIn("PRICE_MOVE:AU.SPY", result["internal"]["review_gate"]["reasons"])

    def test_corrupt_strategy_state_blocks_the_cycle_without_silent_reset(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            storage = RuntimeStorage(state_dir)
            storage.bootstrap(settings.canonical_state)
            storage.state_file.write_text("{bad-state", encoding="utf-8")

            result = V19Engine(settings).run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))

            self.assertEqual(result["report"]["运行状态"], "阻断")
            self.assertEqual(result["report"]["状态连续性"], "冲突待恢复")
            self.assertEqual(result["report"]["裁决完整性"], "阻断")
            self.assertTrue(storage.state_conflict_file.is_file())
            self.assertFalse(storage.state_file.exists())

    def test_report_keeps_source_time_and_observed_time_distinct(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            now = datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc)
            result = V19Engine(settings).run_once(now)

            context = result["internal"]["market_context"]
            self.assertEqual(context["provider_state"], "fixture")
            self.assertIn("2026-08-13T16:00:00+00:00", result["report"]["数据截止"])
            self.assertEqual(context["observed_at"], now.isoformat())
            self.assertEqual(context["fx_cutoff"], "仅AUD候选；无需外汇转换")

    def test_failure_still_publishes_full_visible_report(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            storage = RuntimeStorage(state_dir)
            storage.bootstrap(settings.canonical_state)
            engine = V19Engine(settings)
            now = datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc)
            result = engine.publish_failure(now, RuntimeError("fixture"))
            report = result["report"]
            self.assertEqual(report["运行状态"], "阻断")
            self.assertEqual(len(report["第二板块"]["矩阵"]), 6)
            self.assertEqual(report["第二板块"]["实际参与"], "0/6")

    def test_candidate_cost_and_non_price_evidence_are_hard_eligibility_inputs(self):
        with fixture_settings(ROOT) as (settings, _):
            metric = Metrics(
                "AU.TEST",
                {"20": 2.0, "60": 10.0, "120": 12.0},
                {"20": 1.0, "60": 1.0, "120": 1.0},
                {"20": 1.0, "60": 2.0, "120": 3.0},
                {"20": 2.0, "60": 10.0, "120": 12.0},
                {"20": 1.0, "60": 8.0, "120": 10.0},
                140,
            )

            def candidate(cost_bps: float) -> Candidate:
                return Candidate(
                    provider_code="AU.TEST", public_code="TEST", name="Test", market="AU",
                    currency="AUD", bucket_id="global_broad", bucket_name="全球宽基",
                    risk_tier=1, platform_verified=True, price=100.0,
                    quote_time="2026-08-15T00:00:00+00:00", liquidity_score=1.0,
                    cost_bps=cost_bps,
                )

            non_price_support = SkillResult(
                skill_id="commercial", display_name="Commercial", applicable=True,
                run_mode="方法契约", abstention_reason="无", family="商业捕获",
                raw_weight=1.0, family_weight_pct=100.0, overall_weight_pct=100.0,
                conclusion="支持", independence="独立", contribution="本轮贡献",
                source_state="冻结本地替代", candidate_conclusions={"AU.TEST": "支持"},
            )
            low = candidate(5.0)
            low_result = _qualifies(
                low, metric, settings, [non_price_support], [low], {"AU.TEST": metric}, "AUD"
            )
            self.assertTrue(low_result[0])
            self.assertGreater(low_result[2]["conservative_round_trip_cost_pct"], 0.0)

            high = candidate(5000.0)
            high_result = _qualifies(
                high, metric, settings, [non_price_support], [high], {"AU.TEST": metric}, "AUD"
            )
            self.assertFalse(high_result[0])
            self.assertIn("候选成本FX滑点后60日保守下界未越切换门", high_result[1])

            no_non_price_result = _qualifies(
                low, metric, settings, [], [low], {"AU.TEST": metric}, "AUD"
            )
            self.assertFalse(no_non_price_result[0])
            self.assertIn("缺少候选级非价格方法支持", no_non_price_result[1])

            usd_without_fx = candidate(5.0)
            usd_without_fx.currency = "USD"
            fx_missing_result = _qualifies(
                usd_without_fx, metric, settings, [non_price_support], [usd_without_fx], {"AU.TEST": metric}, "AUD"
            )
            self.assertFalse(fx_missing_result[0])
            self.assertIn("缺少可定位外汇转换链", fx_missing_result[1])


if __name__ == "__main__":
    unittest.main()
