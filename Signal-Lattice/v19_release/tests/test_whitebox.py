from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from signal_lattice_v19.engine import V19Engine
from signal_lattice_v19.models import Candidate, SkillResult
from signal_lattice_v19.storage import RuntimeStorage
from signal_lattice_v19.whitebox import WhiteboxLedger

from common import fixture_settings

ROOT = Path(__file__).resolve().parents[1]


def sample_skill(index: int, conclusion: str) -> SkillResult:
    return SkillResult(
        skill_id=f"skill-{index}",
        display_name=f"Skill {index}",
        applicable=True,
        run_mode="方法契约",
        abstention_reason="无",
        family=f"family-{index}",
        raw_weight=1.0,
        family_weight_pct=100.0,
        overall_weight_pct=100.0 / 6.0,
        conclusion=conclusion,
        independence="独立",
        contribution="本轮形成可见贡献",
        source_state="冻结方法契约",
    )


def sample_report(counterevidence: str = "反证A") -> dict:
    return {
        "运行时间": "2026-08-15 12:00:00",
        "提示词版本": "v0.0.0.19",
        "运行状态": "正常",
        "市场覆盖": "公共广泛",
        "数据截止": "测试截止",
        "状态连续性": "完整状态",
        "裁决完整性": "方法完整",
        "技能适用覆盖率": "100.0%",
        "第一板块": {
            "唯一操作": "持有",
            "唯一平台": "MooMooAU",
            "唯一标的": "State Street SPDR 标普500 ETF",
            "代码": "SPY",
            "唯一方向": "看涨",
            "可观察回撤": "0.0%",
            "风险调整回撤": "0.0%",
            "剩余回撤预算": "20.0%",
            "预期研究窗口": "60交易日主窗；20交易日战术复核",
            "相对宽基": "宽基为赢家",
            "相对现金": "稳健占优",
            "现在怎么做": "仅影子持有",
            "核心依据": "测试",
            "最大反证": counterevidence,
            "失效条件": "回撤达到20%",
            "下一正式复核": "2026-08-15 13:00:00",
        },
        "第二板块": {"矩阵": []},
    }


class WhiteboxTests(unittest.TestCase):
    def test_identical_fifteen_second_ticks_create_one_decision_episode(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            storage = RuntimeStorage(state_dir)
            storage.bootstrap(settings.canonical_state)
            engine = V19Engine(settings)
            first = engine.run_once(datetime(2026, 8, 15, 0, 0, 1, tzinfo=timezone.utc))
            second = engine.run_once(datetime(2026, 8, 15, 0, 0, 16, tzinfo=timezone.utc))
            self.assertTrue(first["internal"]["whitebox"]["decision_changed"])
            self.assertFalse(second["internal"]["whitebox"]["decision_changed"])
            summary = WhiteboxLedger(storage.whitebox_db_file).summary()
            self.assertEqual(summary["observation_count"], 2)
            self.assertEqual(summary["decision_count"], 1)
            self.assertEqual(summary["unchanged_observations"], 1)
            self.assertEqual(len(list((state_dir / "skills").glob("*.json"))), 1)
            history_lines = (state_dir / "history" / "2026-08-15.jsonl").read_text().splitlines()
            self.assertEqual(len(history_lines), 1)

    def test_material_change_creates_new_episode_and_persists(self):
        with TemporaryDirectory() as tmp:
            ledger = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            candidate = Candidate(
                provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                currency="AUD", bucket_id="us_broad", bucket_name="美国宽基",
                risk_tier=1, price=100.0, quote_time="2026-08-15T00:00:00+00:00",
            )
            skills = [sample_skill(i, "支持" if i < 3 else "中性") for i in range(6)]
            first = ledger.record_cycle(
                observed_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report("反证A"), internal={"qualification": {}},
                skills=skills, candidates=[candidate], winner_provider_code="AU.SPY",
                provider_state="fixture",
            )
            second = ledger.record_cycle(
                observed_at=datetime(2026, 8, 15, 0, 0, 15, tzinfo=timezone.utc),
                app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report("反证B"), internal={"qualification": {}},
                skills=skills, candidates=[candidate], winner_provider_code="AU.SPY",
                provider_state="fixture",
            )
            self.assertNotEqual(first["decision_id"], second["decision_id"])
            reopened = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            self.assertEqual(reopened.summary()["decision_count"], 2)

    def test_maturity_updates_skill_value_and_shadow_weights(self):
        with TemporaryDirectory() as tmp:
            ledger = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            candidate = Candidate(
                provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                currency="AUD", bucket_id="us_broad", bucket_name="美国宽基",
                risk_tier=1, price=100.0, quote_time="2026-08-15T00:00:00+00:00",
            )
            conclusions = ["支持", "支持", "反对", "反对", "中性", "无结论"]
            skills = [sample_skill(i, conclusions[i]) for i in range(6)]
            record = ledger.record_cycle(
                observed_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
                app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report(), internal={"qualification": {}},
                skills=skills, candidates=[candidate], winner_provider_code="AU.SPY",
                provider_state="fixture",
            )
            matured = ledger.mature_decision(
                decision_id=record["decision_id"], horizon_days=20,
                baseline_price=100.0, realized_price=110.0,
                cash_return_pct=0.3, benchmark_return_pct=0.0,
                max_drawdown_pct=4.0, round_trip_cost_pct=0.16,
            )
            self.assertEqual(matured["central_outcome"], "正确")
            rows = {row["skill_id"]: row for row in ledger.skills()}
            self.assertEqual(rows["skill-0"]["correct_count"], 1)
            self.assertEqual(rows["skill-2"]["opposite_count"], 1)
            self.assertEqual(rows["skill-4"]["invalid_count"], 1)
            self.assertAlmostEqual(sum(row["shadow_weight_pct"] for row in rows.values()), 100.0, places=6)
            self.assertEqual(ledger.summary()["weight_mode"], "SHADOW_ONLY")


if __name__ == "__main__":
    unittest.main()
