"""SEC 客户端：User-Agent、全局限速、ETag 缓存、有上限的重试。网络一律替身化。"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from signal_lattice.evidence import (
    DEFAULT_USER_AGENT,
    MAX_ATTEMPTS,
    MAX_REQUESTS_PER_SECOND,
    RateLimiter,
    SecClient,
    SecFetchError,
    SecNotFound,
    form4_raw_xml_name,
)


class FakeResponse:
    def __init__(self, body: bytes, headers=None):
        self._body, self.headers, self.status = body, headers or {}, 200

    def read(self):
        return self._body


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, None)


class ScriptedOpener:
    def __init__(self, script):
        self.script, self.requests = list(script), []

    def __call__(self, request, timeout):
        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def client_with(script, cache_dir=None, clock=None):
    clock = clock or FakeClock()
    opener = ScriptedOpener(script)
    naps = []
    client = SecClient(cache_dir, limiter=RateLimiter(clock=clock, sleep=clock.sleep), opener=opener,
                       sleep=lambda s: (naps.append(s), clock.sleep(s)))
    return client, opener, naps


class SecClientTests(unittest.TestCase):
    def test_default_user_agent_and_env_override(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SIGNAL_LATTICE_SEC_UA", None)
            self.assertEqual(SecClient().user_agent, "SignalLattice research ops@linzezhang.com")
            self.assertEqual(SecClient().user_agent, DEFAULT_USER_AGENT)
        with patch.dict(os.environ, {"SIGNAL_LATTICE_SEC_UA": "Tester test@example.com"}):
            self.assertEqual(SecClient().user_agent, "Tester test@example.com")

    def test_every_request_carries_the_user_agent(self):
        client, opener, _ = client_with([FakeResponse(b"{}"), FakeResponse(b"{}")])
        client.user_agent = "Tester test@example.com"
        client.get_json("https://data.sec.gov/a")
        client.get_json("https://data.sec.gov/b")
        self.assertEqual([r.get_header("User-agent") for r in opener.requests], ["Tester test@example.com"] * 2)

    def test_limit_is_at_most_five_requests_per_second(self):
        self.assertEqual(MAX_REQUESTS_PER_SECOND, 5)
        client, _, _ = client_with([FakeResponse(b"{}") for _ in range(40)])
        stamps = []
        clock = client.limiter._clock
        for i in range(40):
            client.get_json("https://data.sec.gov/%d" % i)
            stamps.append(clock())
        for i, start in enumerate(stamps):
            in_window = [t for t in stamps if start <= t <= start + 1.0]
            self.assertLessEqual(len(in_window), 5)

    def test_limiter_is_shared_across_clients(self):
        clock = FakeClock()
        limiter = RateLimiter(clock=clock, sleep=clock.sleep)
        a = SecClient(limiter=limiter, opener=ScriptedOpener([FakeResponse(b"{}")] * 5))
        b = SecClient(limiter=limiter, opener=ScriptedOpener([FakeResponse(b"{}")] * 5))
        for _ in range(5):
            a.get_json("https://data.sec.gov/a")
            b.get_json("https://data.sec.gov/b")
        self.assertGreaterEqual(clock.now, 9 * limiter.min_interval - 1e-9)  # 10 次请求共用一条时间线

    def test_retries_are_capped_at_three_attempts_with_backoff(self):
        self.assertEqual(MAX_ATTEMPTS, 3)
        client, opener, naps = client_with([http_error(503), http_error(503), http_error(503), FakeResponse(b"{}")])
        with self.assertRaises(SecFetchError):
            client.get_bytes("https://data.sec.gov/x")
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(len(naps), 2)
        self.assertGreater(naps[1], naps[0])

    def test_transient_failure_then_success(self):
        client, opener, _ = client_with([urllib.error.URLError("boom"), FakeResponse(b'{"ok":1}')])
        self.assertEqual(client.get_json("https://data.sec.gov/x"), {"ok": 1})
        self.assertEqual(len(opener.requests), 2)

    def test_404_is_not_retried(self):
        client, opener, _ = client_with([http_error(404)])
        with self.assertRaises(SecNotFound):
            client.get_bytes("https://data.sec.gov/x")
        self.assertEqual(len(opener.requests), 1)

    def test_etag_cache_sends_conditional_request_and_serves_304_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, opener, _ = client_with(
                [FakeResponse(b'{"v":1}', {"ETag": '"abc"', "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"}), http_error(304)],
                cache_dir=Path(tmp))
            self.assertEqual(client.get_json("https://data.sec.gov/x"), {"v": 1})
            self.assertEqual(client.get_json("https://data.sec.gov/x"), {"v": 1})
            second = opener.requests[1]
            self.assertEqual(second.get_header("If-none-match"), '"abc"')
            self.assertEqual(second.get_header("If-modified-since"), "Wed, 01 Jan 2025 00:00:00 GMT")
            self.assertEqual(client.cache_hits_304, 1)

    def test_gzip_body_is_decoded(self):
        client, _, _ = client_with([FakeResponse(gzip.compress(b'{"z":1}'), {"Content-Encoding": "gzip"})])
        self.assertEqual(client.get_json("https://data.sec.gov/x"), {"z": 1})

    def test_named_endpoints_build_the_documented_urls(self):
        client, opener, _ = client_with([
            FakeResponse(json.dumps({"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "A", "A", "NYSE"]]}).encode()),
            FakeResponse(b"{}"), FakeResponse(b"{}"), FakeResponse(b"{}"), FakeResponse(b"<x/>"),
        ])
        self.assertEqual(client.company_tickers_exchange(), [{"cik": 1, "name": "A", "ticker": "A", "exchange": "NYSE"}])
        client.submissions(874866)
        client.companyfacts(874866)
        client.frames("dei", "EntityCommonStockSharesOutstanding", "shares", "CY2026Q2I")
        client.form4_xml(874866, "0001-24-000001", "xslF345X06/wk-form4.xml")
        self.assertEqual([r.full_url for r in opener.requests], [
            "https://www.sec.gov/files/company_tickers_exchange.json",
            "https://data.sec.gov/submissions/CIK0000874866.json",
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000874866.json",
            "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY2026Q2I.json",
            "https://www.sec.gov/Archives/edgar/data/874866/000124000001/wk-form4.xml",
        ])

    def test_form4_prefix_strip(self):
        self.assertEqual(form4_raw_xml_name("xslF345X06/wk-form4_1.xml"), "wk-form4_1.xml")
        self.assertEqual(form4_raw_xml_name("xslF345X05/a.xml"), "a.xml")
        self.assertEqual(form4_raw_xml_name("plain.xml"), "plain.xml")


if __name__ == "__main__":
    unittest.main()
