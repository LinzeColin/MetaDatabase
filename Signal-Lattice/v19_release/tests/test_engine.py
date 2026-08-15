from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_lattice_v19.engine import V19Engine
from signal_lattice_v19.storage import RuntimeStorage

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

    def test_two_consecutive_slots_keep_fifteen_second_contract(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            engine = V19Engine(settings)
            first = engine.run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))
            second = engine.run_once(datetime(2026, 8, 14, 0, 0, 16, tzinfo=timezone.utc))
            self.assertEqual(first["refresh_seconds"], 15)
            self.assertNotEqual(first["report"]["运行时间"], second["report"]["运行时间"])
            self.assertTrue(second["report"]["第一板块"]["下一正式复核"].startswith("2026-08-14 11:00:00"))

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


if __name__ == "__main__":
    unittest.main()
