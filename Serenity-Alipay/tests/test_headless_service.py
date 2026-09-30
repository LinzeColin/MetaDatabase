import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from app.db import connect
from app.headless.publish import ReleasePublisher
from app.headless.service import latest_due_slot, service_tick
from tests.headless_fakes import CST, FakeClient, FakeGitHub
from tests.helpers import temp_settings

SEED = Path.cwd() / "data" / "manual"
NOW = datetime(2026, 9, 30, 14, 40, tzinfo=CST)


def _settings(tmp_path):
    return replace(
        temp_settings(tmp_path),
        headless=True,
        moomoo_enabled=False,
        persist_price_history=False,
        candidate_universe_auto_expand_enabled=False,
        candidate_universe_rule_autofill_enabled=False,
    )


def test_latest_due_slot_windows():
    assert latest_due_slot(datetime(2026, 9, 30, 14, 30, tzinfo=CST)) == "R7"
    assert latest_due_slot(datetime(2026, 9, 30, 14, 29, 30, tzinfo=CST)) == "R7"  # 定时器早到几秒
    assert latest_due_slot(datetime(2026, 9, 30, 16, 20, tzinfo=CST)) == "R8"
    assert latest_due_slot(datetime(2026, 9, 30, 7, 0, tzinfo=CST)) is None
    assert latest_due_slot(datetime(2026, 9, 30, 22, 0, tzinfo=CST)) is None  # 超过 3 小时补跑窗口


def test_non_business_day_does_nothing(tmp_path):
    result = service_tick(_settings(tmp_path), now=datetime(2026, 10, 3, 14, 30, tzinfo=CST), publish=False, client=FakeClient(), seed_dir=SEED)
    assert result["action"] == "non_business_day"


def test_tick_runs_publishes_and_is_idempotent(tmp_path):
    settings = _settings(tmp_path)
    gh = FakeGitHub()
    publisher = ReleasePublisher("t", opener=gh, index_path=settings.data_dir / "idx.json", sleep=lambda s: None)
    result = service_tick(settings, now=NOW, client=FakeClient(), publisher=publisher, seed_dir=SEED)
    assert result["action"] == "ran" and result["slot"] == "R7" and result["published"] is True
    assert result["data_health"] == "ok"
    (release_id,) = gh.assets
    names = set(gh.assets[release_id])
    assert {n for n in names if n.endswith("_report.md")} and {n for n in names if n.endswith("_report.html")}
    report = next(v for k, v in gh.assets[release_id].items() if k.endswith("_report.md")).decode()
    assert "持仓快照：**暂无**" in report and "增配/买入候选" not in report and "偏离 |" not in report
    with connect(settings.db_path) as conn:
        assert conn.execute("select count(*) from run_log where schedule_slot='R7'").fetchone()[0] == 1
        # headless 不落全量净值历史
        assert conn.execute("select count(*) from market_kline_snapshot").fetchone()[0] <= 40
    again = service_tick(settings, now=NOW, client=FakeClient(), publisher=publisher, seed_dir=SEED)
    assert again["action"] == "skipped_duplicate"
    assert len(gh.assets) == 1


def test_publish_failure_keeps_run_and_republishes_without_recompute(tmp_path):
    settings = _settings(tmp_path)
    gh = FakeGitHub(private=False)  # 目标仓不是私有：发布必须失败
    bad = ReleasePublisher("t", opener=gh, index_path=settings.data_dir / "idx.json", sleep=lambda s: None)
    try:
        service_tick(settings, now=NOW, client=FakeClient(), publisher=bad, seed_dir=SEED)
        raise AssertionError("应当抛错")
    except Exception as exc:
        assert "不是私有仓" in str(exc)
    good_gh = FakeGitHub()
    good = ReleasePublisher("t", opener=good_gh, index_path=settings.data_dir / "idx.json", sleep=lambda s: None)
    fake = FakeClient()
    result = service_tick(settings, now=NOW, client=fake, publisher=good, seed_dir=SEED)
    assert result["published"] is True
    assert fake.request_count == 0  # 直接重发已算好的报告，没有重新联网取数
    with connect(settings.db_path) as conn:
        assert conn.execute("select count(*) from run_log where schedule_slot='R7'").fetchone()[0] == 1


def test_degraded_data_is_reported_not_hidden(tmp_path):
    settings = _settings(tmp_path)
    result = service_tick(settings, now=NOW, publish=False, client=FakeClient(fail=("yunhq.sse",)), seed_dir=SEED)
    assert result["data_health"] == "degraded"
    saved = json.loads(next((settings.output_root() / "service").rglob("result.json")).read_text(encoding="utf-8"))
    assert saved["result"]["status"] == "degraded"
    md = next((settings.output_root() / "service").rglob("report.md")).read_text(encoding="utf-8")
    assert "数据状态：降级" in md and "上证综指" in md
