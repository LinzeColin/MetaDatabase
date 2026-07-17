"""ALPHA-LIVE-070:3 日报告生成器与四判定(离线,固定输入)。"""

from pathlib import Path

from backend.app.reporting.three_day_report import (
    RunInputs,
    evaluate_promotion,
    generate,
    load_promotion_gates,
)


def healthy_run(**over):
    kw = dict(
        trading_days=["2026-07-20", "2026-07-21", "2026-07-22"],
        uptime_pct=99.9, notify_p95_seconds=1.2, notify_success_pct=100.0,
        strategy_evals=15, signals=4, risk_passed=3, submitted=3, accepted=3, filled=3,
        net_pnl_aud=30.0, gross_pnl_aud=33.0, fees_aud=3.0, max_drawdown_pct=1.5,
        trades=3, wins=2, avg_win_aud=20.0, avg_loss_aud=-8.0,
        raw_events=[{"seq": 1, "type": "FILL"}],
    )
    kw.update(over)
    return RunInputs(**kw)


def test_gates_load_from_config():
    g = load_promotion_gates()
    assert g["paper_days_required"] == 3
    assert g["monthly_gate_pct"] == 0.6          # owner 选乙保底线
    assert g["pace_tolerance"] == 0.60


def test_insufficient_days_never_promotes():
    inp = healthy_run(trading_days=["2026-07-20"])   # 只 1 日
    promo = evaluate_promotion(inp, capital_aud=3000.0)
    assert promo["PROMO-2"]["passed"] is False
    assert promo["PROMO-3"]["passed"] is False
    assert promo["auto_promote"] is False            # 样本不足绝不晋级


def test_engineering_violation_fails_promo4():
    inp = healthy_run(illegal_transitions=1)
    promo = evaluate_promotion(inp, capital_aud=3000.0)
    assert promo["PROMO-4"]["passed"] is False
    assert promo["auto_promote"] is False


def test_low_uptime_fails_promo4():
    inp = healthy_run(uptime_pct=98.0)
    promo = evaluate_promotion(inp, capital_aud=3000.0)
    assert promo["PROMO-4"]["passed"] is False


def test_pace_below_tolerance_fails_promo3():
    # 3 日净 1 AUD / 3000 本金 → 折算月化 ≈ 0.23%,低于 0.6×0.6=0.36% 容忍线
    inp = healthy_run(net_pnl_aud=1.0)
    promo = evaluate_promotion(inp, capital_aud=3000.0)
    assert promo["PROMO-3"]["passed"] is False


def test_all_green_promotes():
    # 3 日净 40 AUD / 3000 → 日 0.444% → 月化 ≈ 9.3%,远超 0.36% 容忍线
    inp = healthy_run(net_pnl_aud=40.0)
    promo = evaluate_promotion(inp, capital_aud=3000.0)
    assert promo["PROMO-2"]["passed"] and promo["PROMO-3"]["passed"] and promo["PROMO-4"]["passed"]
    assert promo["auto_promote"] is True


def test_generate_four_artifacts_with_hashes(tmp_path):
    inp = healthy_run(net_pnl_aud=40.0)
    report = generate(inp, capital_aud=3000.0, out_dir=tmp_path, generated_at="2026-07-22T21:00:00Z")
    for name in ("report.md", "report.json", "evidence_hashes.txt", "events.jsonl"):
        assert (tmp_path / name).exists(), name
    # 证据哈希可复验
    import hashlib
    actual = hashlib.sha256((tmp_path / "events.jsonl").read_bytes()).hexdigest()
    assert actual == report["_hashes"]["events_jsonl"]
    md = (tmp_path / "report.md").read_text()
    assert "人话版" in md and "核账版" in md and "样本置信度低" in md


def test_determinism(tmp_path):
    inp = healthy_run(net_pnl_aud=40.0)
    a = generate(inp, capital_aud=3000.0, out_dir=tmp_path / "a", generated_at="2026-07-22T21:00:00Z")
    b = generate(inp, capital_aud=3000.0, out_dir=tmp_path / "b", generated_at="2026-07-22T21:00:00Z")
    assert a["_hashes"] == b["_hashes"]
