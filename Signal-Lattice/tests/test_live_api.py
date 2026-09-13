"""API 的阻断响应无需监听 TCP 即可验证；监听和 curl 交由目标机验收。"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from signal_lattice.live_api import HEADERS, blocked_report, handler, latest_for_api
from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import LiveStore


class LiveApiTests(unittest.TestCase):
    def _settings(self, root: Path) -> LiveSettings:
        return LiveSettings(
            state_dir=root / "state", web_dir=root, host="127.0.0.1", port=0, loop_seconds=60,
            quote_max_age_seconds=180, bar_max_age_days=7, public_url="http://example.test",
            sina_quote_url="http://unused/", sina_us_kline_url="http://unused/us/{symbol}",
            sina_cn_kline_url="http://unused/cn/{symbol}", tencent_quote_url="http://unused/",
            tencent_kline_url="http://unused/{kind}/{symbol}",
            eastmoney_fund_url="http://unused/{code}", universe=default_universe(),
        )

    def _get_without_tcp(self, request_handler, path: str) -> tuple[int, dict]:
        instance = object.__new__(request_handler)
        statuses: list[int] = []
        instance.path = path
        instance.wfile = BytesIO()
        instance.send_response = lambda status: statuses.append(status)
        instance.send_header = lambda key, value: None
        instance.end_headers = lambda: None
        instance.do_GET()
        return statuses[0], json.loads(instance.wfile.getvalue())

    def test_blocked_response_refuses_investment_action(self):
        report = blocked_report()
        self.assertEqual(report["state"], "SYSTEM_BLOCKED")
        self.assertEqual(report["decision"]["state"], "SYSTEM_BLOCKED")
        self.assertIsNone(report["decision"]["action"])
        self.assertEqual(report["message"], "数据链路不完整，不出结论")
        self.assertEqual(HEADERS["Cache-Control"], "no-store")

    def test_stale_report_and_heartbeat_make_ready_and_latest_report_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self._settings(root)
            store = LiveStore(settings.state_dir)
            now = datetime.now(timezone.utc)
            stale = now - timedelta(seconds=271)
            store.save(
                {
                    "state": "DATA_READY",
                    "generated_at": stale.isoformat(),
                    "market_fingerprint": {"quotes": {"usSPY": 100.0}, "bars": {"usSPY": stale.date().isoformat()}},
                    "decision": {"state": "LONG", "action": "研究观察", "primary_symbol": "usSPY", "conviction": 0.609},
                }
            )
            store.write_heartbeat(stale)

            effective, liveness = latest_for_api(settings, store, now=now)
            self.assertFalse(liveness["fresh"])
            self.assertEqual(effective["state"], "SYSTEM_BLOCKED")
            self.assertEqual(effective["blocked_reason"], "COLLECTION_LOOP_UNREACHABLE")
            self.assertEqual(effective["message"], "采集循环失联，结论已过期")
            self.assertNotEqual(effective["message"], blocked_report()["message"])

            request_handler = handler(settings, store)
            ready_status, ready = self._get_without_tcp(request_handler, "/health/ready")
            report_status, report = self._get_without_tcp(request_handler, "/api/v1/report/latest")
            self.assertEqual(ready_status, 503)
            self.assertEqual(ready["state"], "SYSTEM_BLOCKED")
            self.assertEqual(report_status, 503)
            self.assertEqual(report["blocked_reason"], "COLLECTION_LOOP_UNREACHABLE")


if __name__ == "__main__":
    unittest.main()
