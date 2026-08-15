from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Candidate, SkillResult


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pct(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().removesuffix("%")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _business_day_after(day: date, count: int) -> date:
    current = day
    left = count
    while left > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            left -= 1
    return current


def _material_signature(report: dict[str, Any], internal: dict[str, Any]) -> str:
    first = report.get("第一板块", {}) if isinstance(report, dict) else {}
    second = report.get("第二板块", {}) if isinstance(report, dict) else {}
    rows = second.get("矩阵", []) if isinstance(second, dict) else []
    payload = {
        "winner": {
            "operation": first.get("唯一操作"),
            "platform": first.get("唯一平台"),
            "name": first.get("唯一标的"),
            "code": first.get("代码"),
            "direction": first.get("唯一方向"),
            "relative_broad": first.get("相对宽基"),
            "relative_cash": first.get("相对现金"),
            "counterevidence": first.get("最大反证"),
            "invalidates": first.get("失效条件"),
        },
        "skills": [
            {
                "skill": row.get("技能"),
                "applicable": row.get("适用状态"),
                "mode": row.get("运行方式"),
                "reason": row.get("弃权主原因"),
                "family": row.get("方法家族"),
                "conclusion": row.get("结论"),
                "contribution": row.get("独立性"),
            }
            for row in rows
            if isinstance(row, dict)
        ],
        "qualification": internal.get("qualification", {}),
        "selected_challenger_code": internal.get("selected_challenger_code"),
        "provider_state": internal.get("market_context", {}).get("provider_state")
        if isinstance(internal.get("market_context"), dict)
        else None,
    }
    return _json(payload)


class WhiteboxLedger:
    """Persistent read-only research ledger.

    Fifteen-second observations are stored as observations. A new decision episode is
    created only when the material winner/skill/qualification state changes.
    Shadow weights never alter the frozen V19 public decision in this phase.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _setup(self) -> None:
        with self._session() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS observation_tick (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT NOT NULL,
                    report_time TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    decision_changed INTEGER NOT NULL,
                    app_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    provider_state TEXT NOT NULL,
                    quote_observed_at TEXT,
                    winner_code TEXT NOT NULL,
                    winner_price REAL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS observation_tick_time
                    ON observation_tick(observed_at);

                CREATE TABLE IF NOT EXISTS decision_episode (
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

                CREATE TABLE IF NOT EXISTS skill_episode (
                    decision_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    applicable INTEGER NOT NULL,
                    run_mode TEXT NOT NULL,
                    conclusion TEXT NOT NULL,
                    overall_weight_pct REAL NOT NULL,
                    contribution TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(decision_id, skill_id),
                    FOREIGN KEY(decision_id) REFERENCES decision_episode(decision_id)
                );

                CREATE TABLE IF NOT EXISTS maturity_outcome (
                    decision_id TEXT NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    baseline_price REAL,
                    realized_price REAL,
                    net_return_pct REAL,
                    cash_return_pct REAL,
                    benchmark_return_pct REAL,
                    max_drawdown_pct REAL,
                    central_outcome TEXT,
                    matured_at TEXT,
                    PRIMARY KEY(decision_id, horizon_days),
                    FOREIGN KEY(decision_id) REFERENCES decision_episode(decision_id)
                );

                CREATE TABLE IF NOT EXISTS skill_outcome (
                    decision_id TEXT NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    skill_id TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    matured_at TEXT NOT NULL,
                    PRIMARY KEY(decision_id, horizon_days, skill_id)
                );

                CREATE TABLE IF NOT EXISTS skill_performance (
                    skill_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    matured_count INTEGER NOT NULL,
                    correct_count INTEGER NOT NULL,
                    opposite_count INTEGER NOT NULL,
                    invalid_count INTEGER NOT NULL,
                    value_score_pct REAL NOT NULL,
                    shadow_weight_pct REAL NOT NULL,
                    trend TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backtest_run (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    observations INTEGER NOT NULL,
                    strategy_net_return_pct REAL,
                    benchmark_net_return_pct REAL,
                    cash_return_pct REAL,
                    max_drawdown_pct REAL,
                    gate_status TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _quote_time(candidates: Iterable[Candidate]) -> str | None:
        times = [str(item.quote_time) for item in candidates if item.quote_time]
        return max(times) if times else None

    @staticmethod
    def _winner_price(candidates: Iterable[Candidate], provider_code: str) -> float | None:
        for candidate in candidates:
            if candidate.provider_code == provider_code:
                return float(candidate.price) if candidate.price is not None else None
        return None

    def record_cycle(
        self,
        *,
        observed_at: datetime,
        app_version: str,
        prompt_version: str,
        report: dict[str, Any],
        internal: dict[str, Any],
        skills: list[SkillResult],
        candidates: list[Candidate],
        winner_provider_code: str,
        provider_state: str,
    ) -> dict[str, Any]:
        observed_at = observed_at.astimezone(timezone.utc)
        first = report.get("第一板块", {})
        signature = _material_signature(report, internal)
        opened = observed_at.isoformat()
        quote_time = self._quote_time(candidates)
        winner_price = self._winner_price(candidates, winner_provider_code)

        with self._session() as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute(
                "SELECT * FROM decision_episode ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            changed = last is None or str(last["material_signature"]) != signature
            if changed:
                next_sequence = int(
                    db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM decision_episode").fetchone()[0]
                )
                decision_id = f"D{next_sequence:08d}"
                db.execute(
                    """
                    INSERT INTO decision_episode(
                        sequence, decision_id, opened_at, last_seen_at, observation_count,
                        material_signature, winner_code, operation, direction, status,
                        report_json, internal_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        next_sequence,
                        decision_id,
                        opened,
                        opened,
                        1,
                        signature,
                        str(first.get("代码", "无")),
                        str(first.get("唯一操作", "持有")),
                        str(first.get("唯一方向", "看涨")),
                        str(report.get("运行状态", "不确定")),
                        _json(report),
                        _json(internal),
                    ),
                )
                for skill in skills:
                    db.execute(
                        """
                        INSERT INTO skill_episode(
                            decision_id, skill_id, display_name, applicable, run_mode,
                            conclusion, overall_weight_pct, contribution, payload_json
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            decision_id,
                            skill.skill_id,
                            skill.display_name,
                            1 if skill.applicable else 0,
                            skill.run_mode,
                            skill.conclusion,
                            float(skill.overall_weight_pct),
                            skill.contribution,
                            _json(skill.to_dict()),
                        ),
                    )
                day = observed_at.date()
                for horizon in (20, 60):
                    db.execute(
                        """
                        INSERT INTO maturity_outcome(
                            decision_id, horizon_days, due_date, status
                        ) VALUES(?,?,?,?)
                        """,
                        (decision_id, horizon, _business_day_after(day, horizon).isoformat(), "PENDING"),
                    )
            else:
                decision_id = str(last["decision_id"])
                db.execute(
                    """
                    UPDATE decision_episode
                       SET last_seen_at=?, observation_count=observation_count+1,
                           report_json=?, internal_json=?
                     WHERE decision_id=?
                    """,
                    (opened, _json(report), _json(internal), decision_id),
                )

            db.execute(
                """
                INSERT INTO observation_tick(
                    observed_at, report_time, decision_id, decision_changed,
                    app_version, prompt_version, provider_state, quote_observed_at,
                    winner_code, winner_price, payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    opened,
                    str(report.get("运行时间", "")),
                    decision_id,
                    1 if changed else 0,
                    app_version,
                    prompt_version,
                    provider_state,
                    quote_time,
                    str(first.get("代码", "无")),
                    winner_price,
                    _json({
                        "data_cutoff": report.get("数据截止"),
                        "decision_id": decision_id,
                        "decision_changed": changed,
                    }),
                ),
            )
            self._ensure_skill_performance(db, skills, opened)

        summary = self.summary()
        return {
            "decision_id": decision_id,
            "decision_changed": changed,
            "observation_count": summary["observation_count"],
            "decision_count": summary["decision_count"],
            "quote_observed_at": quote_time,
            "shadow_weights": summary["shadow_weights"],
        }

    def _ensure_skill_performance(
        self, db: sqlite3.Connection, skills: list[SkillResult], observed_at: str
    ) -> None:
        equal = 100.0 / max(1, len(skills))
        for skill in skills:
            db.execute(
                """
                INSERT OR IGNORE INTO skill_performance(
                    skill_id, display_name, matured_count, correct_count,
                    opposite_count, invalid_count, value_score_pct,
                    shadow_weight_pct, trend, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    skill.skill_id,
                    skill.display_name,
                    0,
                    0,
                    0,
                    0,
                    50.0,
                    equal,
                    "样本不足",
                    observed_at,
                ),
            )

    def summary(self) -> dict[str, Any]:
        with self._session() as db:
            observations = int(db.execute("SELECT COUNT(*) FROM observation_tick").fetchone()[0])
            decisions = int(db.execute("SELECT COUNT(*) FROM decision_episode").fetchone()[0])
            latest = db.execute(
                "SELECT * FROM decision_episode ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            last_tick = db.execute(
                "SELECT * FROM observation_tick ORDER BY id DESC LIMIT 1"
            ).fetchone()
            skill_rows = db.execute(
                "SELECT * FROM skill_performance ORDER BY skill_id"
            ).fetchall()
        return {
            "observation_count": observations,
            "decision_count": decisions,
            "unchanged_observations": max(0, observations - decisions),
            "latest_decision_id": str(latest["decision_id"]) if latest else None,
            "latest_decision_opened_at": str(latest["opened_at"]) if latest else None,
            "latest_decision_last_seen_at": str(latest["last_seen_at"]) if latest else None,
            "latest_observed_at": str(last_tick["observed_at"]) if last_tick else None,
            "quote_observed_at": str(last_tick["quote_observed_at"]) if last_tick and last_tick["quote_observed_at"] else None,
            "shadow_weights": {
                str(row["skill_id"]): round(float(row["shadow_weight_pct"]), 4)
                for row in skill_rows
            },
            "profitability_status": "NOT_ISSUED",
            "weight_mode": "SHADOW_ONLY",
        }

    def skills(self) -> list[dict[str, Any]]:
        with self._session() as db:
            rows = db.execute(
                "SELECT * FROM skill_performance ORDER BY shadow_weight_pct DESC, skill_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 200)
        with self._session() as db:
            rows = db.execute(
                """
                SELECT decision_id, opened_at, last_seen_at, observation_count,
                       winner_code, operation, direction, status
                  FROM decision_episode
                 ORDER BY sequence DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def outcomes(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 500)
        with self._session() as db:
            rows = db.execute(
                """
                SELECT * FROM maturity_outcome
                 ORDER BY due_date DESC, horizon_days DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mature_decision(
        self,
        *,
        decision_id: str,
        horizon_days: int,
        realized_price: float,
        baseline_price: float,
        cash_return_pct: float,
        benchmark_return_pct: float,
        max_drawdown_pct: float,
        round_trip_cost_pct: float,
        matured_at: datetime | None = None,
    ) -> dict[str, Any]:
        if horizon_days not in {20, 60}:
            raise ValueError("HORIZON_MUST_BE_20_OR_60")
        matured = (matured_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        gross = (float(realized_price) / float(baseline_price) - 1.0) * 100.0
        net = gross - float(round_trip_cost_pct)
        central_correct = (
            net >= float(cash_return_pct)
            and net >= float(benchmark_return_pct)
            and float(max_drawdown_pct) < 20.0
        )
        central_outcome = "正确" if central_correct else "错误"

        with self._session() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM maturity_outcome WHERE decision_id=? AND horizon_days=?",
                (decision_id, horizon_days),
            ).fetchone()
            if row is None:
                raise ValueError("OUTCOME_NOT_FOUND")
            if str(row["status"]) == "MATURED":
                return {
                    "decision_id": decision_id,
                    "horizon_days": horizon_days,
                    "status": "ALREADY_MATURED",
                }
            db.execute(
                """
                UPDATE maturity_outcome
                   SET status='MATURED', baseline_price=?, realized_price=?,
                       net_return_pct=?, cash_return_pct=?, benchmark_return_pct=?,
                       max_drawdown_pct=?, central_outcome=?, matured_at=?
                 WHERE decision_id=? AND horizon_days=?
                """,
                (
                    float(baseline_price),
                    float(realized_price),
                    net,
                    float(cash_return_pct),
                    float(benchmark_return_pct),
                    float(max_drawdown_pct),
                    central_outcome,
                    matured,
                    decision_id,
                    horizon_days,
                ),
            )
            skill_rows = db.execute(
                "SELECT skill_id, conclusion FROM skill_episode WHERE decision_id=?",
                (decision_id,),
            ).fetchall()
            for skill in skill_rows:
                conclusion = str(skill["conclusion"])
                if conclusion not in {"支持", "反对"}:
                    verdict = "无效"
                elif (conclusion == "支持") == central_correct:
                    verdict = "正确"
                else:
                    verdict = "相反"
                db.execute(
                    """
                    INSERT INTO skill_outcome(decision_id, horizon_days, skill_id, verdict, matured_at)
                    VALUES(?,?,?,?,?)
                    """,
                    (decision_id, horizon_days, str(skill["skill_id"]), verdict, matured),
                )
            self._recalculate_skill_performance(db, matured)

        return {
            "decision_id": decision_id,
            "horizon_days": horizon_days,
            "status": "MATURED",
            "net_return_pct": round(net, 6),
            "central_outcome": central_outcome,
            "shadow_weights": self.summary()["shadow_weights"],
        }

    def _recalculate_skill_performance(self, db: sqlite3.Connection, updated_at: str) -> None:
        skills = db.execute("SELECT skill_id, display_name FROM skill_performance").fetchall()
        raw_scores: dict[str, float] = {}
        stats: dict[str, tuple[int, int, int]] = {}
        trends: dict[str, str] = {}
        for skill in skills:
            skill_id = str(skill["skill_id"])
            outcomes = db.execute(
                """
                SELECT verdict FROM skill_outcome
                 WHERE skill_id=? ORDER BY matured_at DESC, rowid DESC LIMIT 60
                """,
                (skill_id,),
            ).fetchall()
            correct = opposite = invalid = 0
            weighted_correct = weighted_valid = 0.0
            recent_score = older_score = None
            recent_values: list[float] = []
            older_values: list[float] = []
            for index, outcome in enumerate(outcomes):
                verdict = str(outcome["verdict"])
                if verdict == "正确":
                    correct += 1
                    value = 1.0
                elif verdict == "相反":
                    opposite += 1
                    value = 0.0
                else:
                    invalid += 1
                    continue
                decay = math.pow(0.94, index)
                weighted_correct += value * decay
                weighted_valid += decay
                (recent_values if index < 10 else older_values).append(value)
            valid_score = weighted_correct / weighted_valid if weighted_valid else 0.5
            shrunk = (weighted_correct + 2.0) / (weighted_valid + 4.0)
            raw_scores[skill_id] = max(0.20, min(0.80, shrunk))
            stats[skill_id] = (correct, opposite, invalid)
            if recent_values:
                recent_score = sum(recent_values) / len(recent_values)
            if older_values:
                older_score = sum(older_values) / len(older_values)
            if recent_score is None or older_score is None:
                trend = "样本不足"
            elif recent_score > older_score + 0.08:
                trend = "上升"
            elif recent_score < older_score - 0.08:
                trend = "下降"
            else:
                trend = "稳定"
            trends[skill_id] = trend

        total = sum(raw_scores.values()) or 1.0
        weights = {skill_id: score / total * 100.0 for skill_id, score in raw_scores.items()}
        # Keep every method alive and prevent a short regime from permanently zeroing one method.
        bounded = {skill_id: max(8.0, min(25.0, value)) for skill_id, value in weights.items()}
        bounded_total = sum(bounded.values()) or 1.0
        weights = {skill_id: value / bounded_total * 100.0 for skill_id, value in bounded.items()}

        for skill in skills:
            skill_id = str(skill["skill_id"])
            correct, opposite, invalid = stats.get(skill_id, (0, 0, 0))
            valid = correct + opposite
            value_score = (correct / valid * 100.0) if valid else 50.0
            db.execute(
                """
                UPDATE skill_performance
                   SET matured_count=?, correct_count=?, opposite_count=?, invalid_count=?,
                       value_score_pct=?, shadow_weight_pct=?, trend=?, updated_at=?
                 WHERE skill_id=?
                """,
                (
                    correct + opposite + invalid,
                    correct,
                    opposite,
                    invalid,
                    value_score,
                    weights.get(skill_id, 0.0),
                    trends.get(skill_id, "样本不足"),
                    updated_at,
                    skill_id,
                ),
            )

    def record_backtest(self, result: dict[str, Any], source_label: str) -> None:
        with self._session() as db:
            db.execute(
                """
                INSERT INTO backtest_run(
                    run_at, source_label, status, observations,
                    strategy_net_return_pct, benchmark_net_return_pct,
                    cash_return_pct, max_drawdown_pct, gate_status, result_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    source_label,
                    str(result.get("status", "NOT_RUN")),
                    int(result.get("observations", 0)),
                    result.get("strategy_net_return_pct"),
                    result.get("benchmark_net_return_pct"),
                    result.get("cash_return_pct"),
                    result.get("max_drawdown_pct"),
                    str(result.get("gate_status", "NOT_RUN")),
                    _json(result),
                ),
            )

    def latest_backtest(self) -> dict[str, Any] | None:
        with self._session() as db:
            row = db.execute("SELECT result_json FROM backtest_run ORDER BY id DESC LIMIT 1").fetchone()
        return json.loads(str(row["result_json"])) if row else None
