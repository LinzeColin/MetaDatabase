import csv
from datetime import date, datetime
from pathlib import Path

from app.adapters.manual_sources import load_candidates, load_price_history
from app.headless.refresh import apply_nav_freshness, refresh_public_data
from tests.headless_fakes import CST, FakeClient
from tests.helpers import temp_settings
from dataclasses import replace

NOW = datetime(2026, 9, 30, 14, 30, tzinfo=CST)
SEED = Path.cwd() / "data" / "manual"


def _settings(tmp_path):
    return replace(
        temp_settings(tmp_path),
        headless=True,
        candidate_universe_auto_expand_enabled=False,
        candidate_universe_rule_autofill_enabled=False,
    )


def test_refresh_writes_fresh_state_and_reports_ok(tmp_path):
    settings = _settings(tmp_path)
    health = refresh_public_data(settings, client=FakeClient(), now=NOW, seed_dir=SEED)
    assert health.status == "ok"
    assert health.latest_nav_date == "2026-09-29"
    prices = load_price_history(settings.manual_dir / "price_history.csv")
    assert prices["008887"][-1].date == date(2026, 9, 29)
    bench = load_price_history(settings.manual_dir / "benchmark_price_history.csv")
    assert set(bench) == {"000001.SH", "SPX"}
    with (settings.manual_dir / "benchmark_price_history.csv").open(encoding="utf-8") as handle:
        sources = {row["source_name"] for row in csv.DictReader(handle)}
    assert not any("Yahoo" in name for name in sources)


def test_refresh_marks_degraded_when_benchmark_source_fails(tmp_path):
    settings = _settings(tmp_path)
    health = refresh_public_data(settings, client=FakeClient(fail=("fredgraph",)), now=NOW, seed_dir=SEED)
    assert health.status == "degraded"
    spx = [s for s in health.sources if s.key == "SPX"][0]
    assert spx.ok is False and "失败" in spx.detail
    assert spx.used_cache is False  # 种子里的 Yahoo 旧数据不是允许的来源，不得冒充


def test_refresh_second_run_same_morning_skips_nav_refetch(tmp_path):
    settings = _settings(tmp_path)
    refresh_public_data(settings, client=FakeClient(), now=NOW, seed_dir=SEED)
    second = FakeClient()
    refresh_public_data(settings, client=second, now=NOW, seed_dir=SEED)
    assert not any("pingzhongdata" in u for u in second.urls)
    assert not any("startDate" in u for u in second.urls)


def test_apply_nav_freshness_counts_trading_days_behind(tmp_path):
    settings = _settings(tmp_path)
    refresh_public_data(settings, client=FakeClient(), now=NOW, seed_dir=SEED)
    candidates = load_candidates(settings.manual_dir / "candidates.csv")
    prices = load_price_history(settings.manual_dir / "price_history.csv")
    trading = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]
    fresh = apply_nav_freshness(candidates, prices, trading, date(2026, 9, 30))
    assert {c.asset_code: c.missing_nav_days for c in fresh}["008887"] == 1
    long_gap = apply_nav_freshness(candidates, prices, trading + [date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12)], date(2026, 10, 12))
    assert {c.asset_code: c.missing_nav_days for c in long_gap}["008887"] == 4
