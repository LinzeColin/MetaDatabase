from __future__ import annotations

import copy
import json
import sqlite3
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


def sample_report(counterevidence: str = "反证A", basis: str = "测试", code: str = "SPY") -> dict:
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
            "代码": code,
            "唯一方向": "看涨",
            "可观察回撤": "0.0%",
            "风险调整回撤": "0.0%",
            "剩余回撤预算": "20.0%",
            "预期研究窗口": "60交易日主窗；20交易日战术复核",
            "相对宽基": "宽基为赢家",
            "相对现金": "稳健占优",
            "现在怎么做": "仅影子持有",
            "核心依据": basis,
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

    def test_missing_source_quote_time_is_not_relabelled_as_observed_at(self):
        with TemporaryDirectory() as tmp:
            ledger = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            candidate = Candidate(
                provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                currency="AUD", bucket_id="us_broad", bucket_name="美国宽基",
                risk_tier=1, price=100.0, quote_time=None,
            )
            observed_at = datetime(2026, 8, 15, tzinfo=timezone.utc)
            ledger.record_cycle(
                observed_at=observed_at,
                app_version="0.0.0.1.43",
                prompt_version="v0.0.0.19",
                report=sample_report(),
                internal={"qualification": {}},
                skills=[sample_skill(0, "支持")],
                candidates=[candidate],
                winner_provider_code="AU.SPY",
                provider_state="fixture",
            )
            with ledger._session() as db:
                row = db.execute(
                    "SELECT observed_at, quote_time FROM price_observation WHERE provider_code='AU.SPY'"
                ).fetchone()
            self.assertEqual(row["observed_at"], observed_at.isoformat())
            self.assertIsNone(row["quote_time"])

    def test_maturity_updates_skill_value_and_shadow_weights(self):
        with TemporaryDirectory() as tmp:
            ledger = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            conclusions = ["支持", "支持", "反对", "反对", "中性", "无结论"]
            skills = [sample_skill(i, conclusions[i]) for i in range(6)]
            opened = datetime(2026, 1, 1, tzinfo=timezone.utc)
            observations = [(opened, 100.0, 100.0)]
            current_day = opened.date()
            trading_days = 0
            while trading_days < 20:
                current_day += timedelta(days=1)
                if current_day.weekday() >= 5:
                    continue
                trading_days += 1
                observations.append((
                    datetime(current_day.year, current_day.month, current_day.day, tzinfo=timezone.utc),
                    100.0 + trading_days * 0.5,
                    100.0 + trading_days * 0.25,
                ))
            record = None
            for observed_at, candidate_price, benchmark_price in observations:
                candidate = Candidate(
                    provider_code="AU.CAND", public_code="CAND", name="Candidate", market="AU",
                    currency="AUD", bucket_id="theme", bucket_name="主题", risk_tier=2,
                    price=candidate_price, quote_time=observed_at.isoformat(), cost_bps=10.0,
                )
                benchmark = Candidate(
                    provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                    currency="AUD", bucket_id="us_broad", bucket_name="美国宽基", risk_tier=1,
                    price=benchmark_price, quote_time=observed_at.isoformat(), cost_bps=5.0,
                )
                record = ledger.record_cycle(
                    observed_at=observed_at, app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                    report=sample_report(code="CAND"), internal={"qualification": {}}, skills=skills,
                    candidates=[candidate, benchmark], winner_provider_code="AU.CAND", provider_state="fixture",
                    cash_rate_annual_pct=0.0,
                )
            assert record is not None
            matured = ledger.mature_decision(
                decision_id=record["decision_id"], horizon_days=20,
                matured_at=observations[-1][0],
            )
            self.assertEqual(matured["central_outcome"], "正确")
            self.assertEqual(matured["trading_day_count"], 20)
            rows = {row["skill_id"]: row for row in ledger.skills()}
            self.assertEqual(rows["skill-0"]["correct_count"], 1)
            self.assertEqual(rows["skill-2"]["opposite_count"], 1)
            self.assertEqual(rows["skill-4"]["invalid_count"], 1)
            self.assertAlmostEqual(sum(row["shadow_weight_pct"] for row in rows.values()), 100.0, places=6)
            self.assertEqual(ledger.summary()["weight_mode"], "SHADOW_ONLY")

    def test_shadow_weight_penalizes_low_coverage_even_when_its_single_call_is_correct(self):
        with TemporaryDirectory() as tmp:
            ledger = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            thin = sample_skill(90, "支持")
            broad = sample_skill(91, "支持")
            with ledger._session() as db:
                ledger._ensure_skill_performance(db, [thin, broad], "2026-08-01T00:00:00+00:00")
                for index in range(10):
                    db.execute(
                        """
                        INSERT INTO skill_outcome(
                            decision_id, horizon_days, skill_id, verdict, matured_at,
                            economic_margin_pct, applicable
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            f"thin-{index}",
                            60 if index == 0 else 20,
                            thin.skill_id,
                            "正确" if index == 0 else "无效",
                            f"2026-08-{20 - index:02d}T00:00:00+00:00",
                            4.0 if index == 0 else 0.0,
                            1,
                        ),
                    )
                    correct = index < 6
                    db.execute(
                        """
                        INSERT INTO skill_outcome(
                            decision_id, horizon_days, skill_id, verdict, matured_at,
                            economic_margin_pct, applicable
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            f"broad-{index}",
                            60 if index % 2 == 0 else 20,
                            broad.skill_id,
                            "正确" if correct else "相反",
                            f"2026-07-{20 - index:02d}T00:00:00+00:00",
                            4.0 if correct else -4.0,
                            1,
                        ),
                    )
                ledger._recalculate_skill_performance(db, "2026-08-21T00:00:00+00:00")

            rows = {row["skill_id"]: row for row in ledger.skills()}
            self.assertLess(rows[thin.skill_id]["coverage_pct"], rows[broad.skill_id]["coverage_pct"])
            self.assertLess(rows[thin.skill_id]["effective_sample_size"], rows[broad.skill_id]["effective_sample_size"])
            self.assertLess(rows[thin.skill_id]["shadow_weight_pct"], rows[broad.skill_id]["shadow_weight_pct"])
            self.assertEqual(ledger.summary()["weight_mode"], "SHADOW_ONLY")

    def test_maturity_rejects_early_or_external_outcome_overrides(self):
        with TemporaryDirectory() as tmp:
            ledger = WhiteboxLedger(Path(tmp) / "whitebox.sqlite3")
            opened = datetime(2026, 8, 15, tzinfo=timezone.utc)
            candidate = Candidate(
                provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                currency="AUD", bucket_id="us_broad", bucket_name="美国宽基", risk_tier=1,
                price=100.0, quote_time=opened.isoformat(), cost_bps=10.0,
            )
            record = ledger.record_cycle(
                observed_at=opened, app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report(), internal={"qualification": {}},
                skills=[sample_skill(i, "支持") for i in range(6)], candidates=[candidate],
                winner_provider_code="AU.SPY", provider_state="fixture",
            )
            with self.assertRaisesRegex(ValueError, "OUTCOME_NOT_DUE"):
                ledger.mature_decision(
                    decision_id=record["decision_id"], horizon_days=60,
                    matured_at=opened + timedelta(seconds=1),
                )
            with self.assertRaisesRegex(ValueError, "EXTERNAL_OUTCOME_OVERRIDES_FORBIDDEN"):
                ledger.mature_decision(
                    decision_id=record["decision_id"], horizon_days=20,
                    matured_at=opened,
                    realized_price=999.0,
                )

    def test_original_episode_snapshot_is_immutable_and_latest_observation_is_separate(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "whitebox.sqlite3"
            ledger = WhiteboxLedger(path)
            opened = datetime(2026, 8, 15, tzinfo=timezone.utc)
            skills = [sample_skill(i, "中性") for i in range(6)]

            def candidate(price: float, observed_at: datetime) -> Candidate:
                return Candidate(
                    provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                    currency="AUD", bucket_id="us_broad", bucket_name="美国宽基", risk_tier=1,
                    price=price, quote_time=observed_at.isoformat(), cost_bps=10.0,
                )

            first = ledger.record_cycle(
                observed_at=opened, app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report(basis="ORIGINAL"), internal={"qualification": {"lower": 1.0}},
                skills=skills, candidates=[candidate(100.0, opened)], winner_provider_code="AU.SPY",
                provider_state="fixture",
            )
            second = ledger.record_cycle(
                observed_at=opened + timedelta(seconds=15), app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report(basis="LATEST"), internal={"qualification": {"lower": 1.0}},
                skills=skills, candidates=[candidate(125.0, opened + timedelta(seconds=15))],
                winner_provider_code="AU.SPY", provider_state="fixture",
            )
            self.assertEqual(first["decision_id"], second["decision_id"])
            db = sqlite3.connect(path)
            row = db.execute(
                """
                SELECT report_json, internal_json, latest_observation_json,
                       original_input_json, original_input_signature, snapshot_integrity_state
                  FROM decision_episode WHERE decision_id=?
                """,
                (first["decision_id"],),
            ).fetchone()
            db.close()
            assert row is not None
            self.assertEqual(json.loads(row[0])["第一板块"]["核心依据"], "ORIGINAL")
            self.assertEqual(json.loads(row[1])["qualification"]["lower"], 1.0)
            self.assertEqual(json.loads(row[2])["report"]["第一板块"]["核心依据"], "LATEST")
            original_inputs = json.loads(row[3])
            self.assertEqual(original_inputs["winner"]["baseline_price"], 100.0)
            self.assertEqual(original_inputs["central_quantitative_inputs"]["qualification"]["lower"], 1.0)
            self.assertEqual(row[3], row[4])
            self.assertEqual(row[5], "IMMUTABLE_ORIGINAL")

    def test_legacy_episode_is_marked_unverified_and_not_reused(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "whitebox.sqlite3"
            db = sqlite3.connect(path)
            db.executescript(
                """
                CREATE TABLE decision_episode (
                    sequence INTEGER PRIMARY KEY,
                    decision_id TEXT NOT NULL UNIQUE,
                    opened_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    observation_count INTEGER NOT NULL,
                    material_signature TEXT NOT NULL,
                    winner_code TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    internal_json TEXT NOT NULL
                );
                """
            )
            db.execute(
                """
                INSERT INTO decision_episode VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    1, "D00000001", "2026-08-15T00:00:00+00:00", "2026-08-15T00:00:00+00:00",
                    1, "legacy", "SPY", "持有", "看涨", "正常", "{}", "{}",
                ),
            )
            db.commit()
            db.close()

            ledger = WhiteboxLedger(path)
            db = sqlite3.connect(path)
            migrated = db.execute(
                "SELECT snapshot_integrity_state FROM decision_episode WHERE decision_id='D00000001'"
            ).fetchone()
            db.close()
            self.assertEqual(migrated[0], "LEGACY_UNVERIFIED")
            opened = datetime(2026, 8, 15, 0, 0, 15, tzinfo=timezone.utc)
            candidate = Candidate(
                provider_code="AU.SPY", public_code="SPY", name="SPY", market="AU",
                currency="AUD", bucket_id="us_broad", bucket_name="美国宽基", risk_tier=1,
                price=100.0, quote_time=opened.isoformat(), cost_bps=10.0,
            )
            record = ledger.record_cycle(
                observed_at=opened, app_version="0.0.0.1.43", prompt_version="v0.0.0.19",
                report=sample_report(), internal={"qualification": {}},
                skills=[sample_skill(i, "中性") for i in range(6)], candidates=[candidate],
                winner_provider_code="AU.SPY", provider_state="fixture",
            )
            self.assertEqual(record["decision_id"], "D00000002")


if __name__ == "__main__":
    unittest.main()
