import datetime as dt
from pathlib import Path

import pytest

import run


def journey(steps, name="旅程一"):
    return {"journeys": [{"name": name, "steps": steps}]}


def reasons(rep, vp="desktop"):
    return [f["message"] for j in rep["projects"][0]["journeys"] for f in j["viewports"][vp]["failures"]]


# ---------- 通过路径 ----------

def test_happy_path_passes_with_screenshot_and_reports(go):
    rc, rep, out = go(journey([
        {"goto": "ok"},
        {"expect_text": ["欢迎 正常页面", "行一"]},
        {"expect_any_text": ["西甲", "英超"]},
        {"expect_no_text": ["500 错误"]},
        {"expect_visible": "table"},
        {"click_text": "第二页"},
        {"expect_url_contains": "/ok2"},
        {"screenshot": "第二页"},
    ]))
    assert rc == 0, reasons(rep)
    v = rep["projects"][0]["journeys"][0]["viewports"]["desktop"]
    assert v["passed"] and v["screenshots"] == ["测试项目-旅程一-desktop-第二页.png"]
    assert (out / v["screenshots"][0]).stat().st_size > 1000
    md = (out / "报告.md").read_text(encoding="utf-8")
    assert "测试项目 —— 通过" in md and "测试项目-旅程一-desktop-第二页.png" in md
    # axe：桩每页返回 1 个 critical，走了两页共 2 个；只报告，不判不合格
    assert v["checks"]["axe"]["critical"] == 2 and v["passed"]
    # 只支持 GET 的链接（HEAD 返回 405）不算死链
    assert not any(f["kind"] == "broken_link" for f in v["failures"])


def test_click_with_dom_change_passes(go):
    rc, rep, _ = go(journey([{"goto": "ok"}, {"click": "#chg"}, {"expect_text": ["已变化"]}]))
    assert rc == 0, reasons(rep)


# ---------- 判失败 ----------

def test_forbidden_text_hit_fails(go):
    rc, rep, out = go(journey([{"goto": "undef"}, {"screenshot": "价格页"}]))
    assert rc == 1
    assert any("undefined" in r and "不该出现" in r for r in reasons(rep))
    assert "不通过" in (out / "报告.md").read_text(encoding="utf-8")


def test_forbid_text_extra(go):
    rc, rep, _ = go({**journey([{"goto": "ok"}]), "forbid_text_extra": ["英超"]})
    assert rc == 1 and any("英超" in r for r in reasons(rep))


def test_dead_link_fails(go):
    rc, rep, _ = go(journey([{"goto": "deadlink"}]))
    assert rc == 1
    assert any("链接打不开" in r and "missing-page" in r and "404" in r for r in reasons(rep))


def test_mobile_horizontal_scroll_fails_but_desktop_not_checked(go):
    rc, rep, _ = go({**journey([{"goto": "wide"}]), "viewports": ["desktop", "mobile"]})
    assert rc == 1
    assert reasons(rep, "desktop") == []
    assert any("横向滚动" in r for r in reasons(rep, "mobile"))


def test_click_without_any_change_fails(go):
    rc, rep, out = go(journey([{"goto": "ok"}, {"click": "#noop"}, {"screenshot": "不该走到"}]))
    assert rc == 1
    assert any("点击后页面没有任何变化" in r for r in reasons(rep))
    shots = rep["projects"][0]["journeys"][0]["viewports"]["desktop"]["screenshots"]
    assert shots and shots[0].endswith("失败-第2步.png")  # 失败留证据，后续步骤不再执行


def test_expect_text_missing_fails_with_reason(go):
    rc, rep, out = go(journey([{"goto": "ok"}, {"expect_text": ["这句话不存在-e2e-negative"]}]))
    assert rc == 1
    assert any("页面上没找到：「这句话不存在-e2e-negative」" in r for r in reasons(rep))
    assert "这句话不存在-e2e-negative" in (out / "报告.md").read_text(encoding="utf-8")


def test_goto_404_fails(go):
    rc, rep, _ = go(journey([{"goto": "no-such-page"}]))
    assert rc == 1 and any("HTTP 404" in r for r in reasons(rep))


def test_js_error_and_same_origin_5xx_fail(go):
    rc, rep, _ = go(journey([{"goto": "jserr"}]))
    assert rc == 1 and any("boom-e2e" in r for r in reasons(rep))
    rc, rep, _ = go(journey([{"goto": "fetch500"}]))
    assert rc == 1 and any("HTTP 500" in r and "/api/boom" in r for r in reasons(rep))


# ---------- freshness ----------

def test_freshness_ok_and_stale(go):
    ok = {"pattern": r"报告日期[：:]\s*(\d{4}-\d{2}-\d{2})", "max_age_hours": 48, "url": "fresh"}
    rc, rep, out = go({**journey([{"goto": "fresh"}]), "freshness": ok})
    fr = rep["projects"][0]["freshness"]
    assert rc == 0 and fr["passed"] and fr["assumed_utc"] is True
    assert "按 UTC 处理" in (out / "报告.md").read_text(encoding="utf-8")

    rc, rep, out = go({**journey([{"goto": "ok"}]), "freshness": {**ok, "url": "stale"}})
    assert rc == 1
    assert "数据不新鲜" in rep["projects"][0]["freshness"]["message"]
    assert "数据新鲜度" in (out / "报告.md").read_text(encoding="utf-8")


def test_freshness_pattern_not_found_fails(go):
    rc, rep, _ = go({**journey([{"goto": "ok"}]),
                     "freshness": {"pattern": r"没有这个字段(\d+)", "max_age_hours": 1, "url": "ok"}})
    assert rc == 1 and "没有找到" in rep["projects"][0]["freshness"]["message"]


@pytest.mark.parametrize("raw,assumed", [
    ("2026-09-30", True), ("2026-09-30 07:30", True), ("2026/9/30", True), ("2026年9月30日", True),
    ("2026-09-30T07:30:00Z", False), ("2026-09-30T07:30:00+10:00", False), ("1790000000", False),
])
def test_parse_time(raw, assumed):
    t, a = run.parse_time(raw)
    assert t.tzinfo is not None and a is assumed


def test_parse_time_offset_converted_to_utc():
    t, _ = run.parse_time("2026-09-30T07:30:00+10:00")
    assert t == dt.datetime(2026, 9, 29, 21, 30, tzinfo=dt.timezone.utc)


# ---------- expect_json ----------

def test_expect_json_pass_and_fail(go):
    rc, rep, _ = go(journey([{"expect_json": {"url": "api/items.json", "path": "data.items", "min_items": 3}}]))
    assert rc == 0, reasons(rep)
    rc, rep, _ = go(journey([{"expect_json": {"url": "api/items.json", "path": "data.items", "min_items": 4}}]))
    assert rc == 1 and any("只有 3 项，至少应有 4 项" in r for r in reasons(rep))
    rc, rep, _ = go(journey([{"expect_json": {"url": "api/empty.json", "path": "data.items", "min_items": 1}}]))
    assert rc == 1
    rc, rep, _ = go(journey([{"expect_json": {"url": "api/items.json", "path": "data.nope"}}]))
    assert rc == 1 and any("取不到值" in r for r in reasons(rep))


# ---------- 执行器自身错误 = 退出码 2 ----------

def test_bad_journey_file_exits_2(go):
    rc, rep, _ = go(journey([{"teleport": "x"}]))
    assert rc == 2 and rep is None


def test_missing_file_exits_2(tmp_path):
    assert run.main([str(tmp_path / "nope.yaml"), "--out", str(tmp_path / "o")]) == 2


def test_viewports_three_kinds(go):
    rc, rep, _ = go({**journey([{"goto": "ok"}, {"screenshot": "首屏"}]), "viewports": ["desktop", "mobile", "dark"]})
    assert rc == 0, reasons(rep)
    vps = rep["projects"][0]["journeys"][0]["viewports"]
    assert set(vps) == {"desktop", "mobile", "dark"}
    assert [vps[v]["screenshots"][0] for v in ("desktop", "mobile", "dark")] == [
        f"测试项目-旅程一-{v}-首屏.png" for v in ("desktop", "mobile", "dark")]
