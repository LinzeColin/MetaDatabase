from datetime import date

import pytest

from app.headless import sources as src
from tests.headless_fakes import FakeClient, pingzhong_text


def test_parse_pingzhong_reads_cst_dates_and_nav():
    name, points = src.parse_pingzhong(pingzhong_text(3).decode())
    assert name == "测试基金"
    assert points[-1].date == date(2026, 9, 29)
    assert all(a.date < b.date for a, b in zip(points, points[1:]))


def test_parse_pingzhong_rejects_garbage():
    with pytest.raises(src.SourceError):
        src.parse_pingzhong("var x = 1;")


def test_status_mapping():
    assert src._map_status("暂停申购", "subscription") == "closed"
    assert src._map_status("限大额", "subscription") == "limited"
    assert src._map_status("开放申购", "subscription") == "open"
    assert src._map_status("开放赎回", "redemption") == "open"
    assert src._map_status("", "redemption") is None


def test_sse_and_fred_parsers():
    client = FakeClient()
    sse = src.fetch_sse_index(client, count=900)
    assert sse[-1].date == date(2026, 9, 30)
    spx = src.fetch_fred_sp500(client, start=date(2025, 1, 1))
    assert spx[-1].date == date(2026, 9, 29)


def test_http_client_retries_then_raises_without_leaking_headers():
    calls = []

    def opener(request, timeout=None):
        calls.append(request.full_url)
        raise TimeoutError("boom")

    client = src.HttpClient(retries=3, opener=opener, sleep=lambda s: None, min_interval=0)
    with pytest.raises(src.SourceError) as info:
        client.get("https://example.invalid/x", {"Authorization": "secret-token"})
    assert len(calls) == 3
    assert "secret-token" not in str(info.value)
