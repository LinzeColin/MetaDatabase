"""API 的阻断响应无需监听 TCP 即可验证；监听和 curl 交由目标机验收。"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from signal_lattice.live_api import HEADERS, blocked_report, handler, latest_for_api, public_report_view, v2_get_route_responses
from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import LiveEngine, LiveStore
from signal_lattice.marketdata.base import MarketDataError
from signal_lattice.marketdata.models import Bar
from signal_lattice.marketdata.tencent import TencentQuoteProvider


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

    def test_public_report_keeps_quote_freshness_disclosure(self):
        report = {
            "state": "DATA_READY",
            "quote_freshness": {
                "hk00700": {
                    "declared_feed_delay_minutes": 25,
                    "observed_lag_minutes": 22.0,
                    "last_advance_at": "2026-09-14T01:54:06+00:00",
                    "stalled_minutes": 4.5,
                    "status": "FRESH",
                },
            },
        }

        public = public_report_view(report)

        self.assertEqual(public["quote_freshness"]["hk00700"]["declared_feed_delay_minutes"], 25)
        self.assertEqual(public["quote_freshness"]["hk00700"]["observed_lag_minutes"], 22.0)
        self.assertEqual(public["quote_freshness"]["hk00700"]["last_advance_at"], "2026-09-14T01:54:06+00:00")
        self.assertEqual(public["quote_freshness"]["hk00700"]["stalled_minutes"], 4.5)

    def test_openapi_paths_exactly_match_v2_handler_route_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<!doctype html><title>V2</title>", encoding="utf-8")
            settings = self._settings(root)
            live_routes = set(v2_get_route_responses(
                settings,
                {},
                {"reason": None, "max_age_seconds": 270},
            ))
            contract = json.loads((Path(__file__).resolve().parents[1] / "openapi.yaml").read_text(encoding="utf-8"))
            declared_routes = set(contract["paths"])

        self.assertEqual(declared_routes, live_routes)
        self.assertTrue(all(set(item) == {"get"} for item in contract["paths"].values()))
        self.assertEqual(contract["info"]["version"], "0.0.0.2.3")
        self.assertEqual(
            {
                (entry["path"], tuple(entry["methods"]))
                for entry in contract["x-removed-legacy-interfaces"]
            } & {
                ("/api/v1/inputs/market-snapshot", ("POST",)),
                ("/api/v1/inputs/skill-signal", ("POST",)),
            },
            {
                ("/api/v1/inputs/market-snapshot", ("POST",)),
                ("/api/v1/inputs/skill-signal", ("POST",)),
            },
        )
        self.assertNotIn("/api/v1/inputs/market-snapshot", declared_routes)
        self.assertNotIn("/api/v1/inputs/skill-signal", declared_routes)

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

    def test_future_report_heartbeat_or_both_make_ready_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self._settings(root)
            now = datetime.now(timezone.utc)
            future = now + timedelta(seconds=61)

            for report_time, heartbeat_time, expected_reason in (
                (future, now, "REPORT_CLOCK_AHEAD"),
                (now, future, "HEARTBEAT_CLOCK_AHEAD"),
                (future, future, "REPORT_CLOCK_AHEAD,HEARTBEAT_CLOCK_AHEAD"),
            ):
                with self.subTest(report_time=report_time, heartbeat_time=heartbeat_time):
                    state_dir = root / expected_reason.replace(",", "_")
                    store = LiveStore(state_dir)
                    store.save({
                        "state": "DATA_READY",
                        "generated_at": report_time.isoformat(),
                        "market_fingerprint": {"quotes": {}, "bars": {}},
                        "decision": {"state": "LONG", "action": "研究观察"},
                    })
                    store.write_heartbeat(heartbeat_time)

                    effective, liveness = latest_for_api(settings, store, now=now)
                    self.assertFalse(liveness["fresh"])
                    self.assertEqual(liveness["reason"], expected_reason)
                    self.assertEqual(effective["state"], "SYSTEM_BLOCKED")
                    self.assertEqual(effective["blocked_reason"], "COLLECTION_LOOP_UNREACHABLE")

    def test_public_routes_remove_insufficient_profitability_values_and_keep_private_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self._settings(root)
            store = LiveStore(settings.state_dir)
            now = datetime.now(timezone.utc)
            report = {
                "state": "DATA_READY",
                "generated_at": now.isoformat(),
                "profitability_status": "OOS_HISTORY_INSUFFICIENT: 4/6",
                "branches": [{"branch_id": "s1_momentum", "direction": "看涨"}],
                "contribution_weights": {
                    "weight_mode": "COLD_START_EQUAL",
                    "weight_sample_count": 4,
                    "minimum_contribution_samples": 8,
                    "branches": [{
                        "branch_id": "s1_momentum",
                        "weight": 1.0,
                        "usable_sample_count": 4,
                        "cumulative_risk_adjusted_excess": 5.4753,
                        "weight_trajectory": [{"update_value": -78.5628}],
                    }],
                },
                "backtest": {
                    "status": "OOS_READY",
                    "sample_sufficiency": "OOS_HISTORY_INSUFFICIENT: 4/6",
                    "sample_sufficiency_message": "样本外历史不足，仅供研究参考，不构成收益证据。",
                    "profitability_status": "OOS_HISTORY_INSUFFICIENT: 4/6",
                    "method": {"minimum_oos_windows_for_profitability": 6},
                    "branches": {
                        "s1_momentum": {
                            "branch_id": "s1_momentum",
                            "status": "OOS_READY",
                            "sample_sufficiency": "OOS_HISTORY_INSUFFICIENT: 4/6",
                            "profitability_evidence": "INSUFFICIENT",
                            "active_config": {"selection": {"top_n": 2}},
                            "config_as_of": "2026-09-12",
                            "config_source_window": {"window_label": "WF-04"},
                            "config_status": "ACTIVE_TRAIN_WINDOW_AS_OF",
                            "windows": [{
                                "test_metrics": {"excess_return_pct": 5.4753},
                                "contribution": {"excess_return": -78.5628},
                            }],
                            "stitched": {"excess_return_pct": 5.4753, "information_ratio": -78.5628},
                            "contributions": [{"excess_return": -78.5628}],
                        },
                    },
                    "contribution_summary": {
                        "sample_count": 4,
                        "samples": [{"branch_return": 5.4753, "excess_return": -78.5628}],
                    },
                },
            }
            store.save(report)
            store.write_heartbeat(now)
            request_handler = handler(settings, store)

            for path in (
                "/api/v1/report/latest",
                "/api/v1/whitebox/backtest/latest",
                "/api/v1/whitebox/summary",
                "/api/v1/whitebox/skills",
                "/api/v1/heartbeat",
                "/api/v1/metadata",
                "/api/v1/system/status",
            ):
                with self.subTest(path=path):
                    status, payload = self._get_without_tcp(request_handler, path)
                    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                    self.assertEqual(status, 200)
                    self.assertNotIn("5.4753", serialized)
                    self.assertNotIn("-78.5628", serialized)
                    self.assertNotIn('"stitched"', serialized)
                    self.assertNotIn('"test_metrics"', serialized)
                    self.assertNotIn('"contributions"', serialized)
                    self.assertNotIn('"weight_trajectory"', serialized)

            public_status, public_backtest = self._get_without_tcp(request_handler, "/api/v1/whitebox/backtest/latest")
            self.assertEqual(public_status, 200)
            self.assertEqual(public_backtest["sample_sufficiency"], "OOS_HISTORY_INSUFFICIENT: 4/6")
            self.assertEqual(public_backtest["profitability_disclosure"]["minimum_oos_windows_for_profitability"], 6)
            self.assertIn("仅供研究参考", public_backtest["profitability_disclosure"]["message"])
            public_s1 = public_backtest["branches"][0]
            self.assertEqual(public_s1["active_config"], {"selection": {"top_n": 2}})
            self.assertEqual(public_s1["config_as_of"], "2026-09-12")
            self.assertEqual(public_s1["config_source_window"]["window_label"], "WF-04")
            self.assertIn("5.4753", json.dumps(store.latest(), ensure_ascii=False, sort_keys=True))
            self.assertIn("-78.5628", json.dumps(store.latest(), ensure_ascii=False, sort_keys=True))

    def test_non_gbk_tencent_fallback_replaces_ready_report_with_blocked_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self._settings(root)
            engine = LiveEngine(settings)
            now = datetime.now(timezone.utc)
            engine.store.save({
                "state": "DATA_READY",
                "generated_at": (now - timedelta(seconds=1)).isoformat(),
                "decision": {"state": "LONG", "action": "研究观察"},
            })
            engine.store.write_heartbeat(now)

            class UnavailableSina:
                def fetch(self, instruments):
                    raise MarketDataError("SINA_UPSTREAM_UNAVAILABLE")

            class NonGbkClient:
                def get(self, url, headers=None):
                    return b"\xff\xfe"

            class FreshBars:
                def fetch(self, instrument):
                    return [Bar(
                        instrument.symbol, now.date(), 1, 1, 1, 1, 1,
                        instrument.timezone, "fixture", now,
                    )]

            engine.gateway.sina = UnavailableSina()
            engine.gateway.tencent_quote = TencentQuoteProvider(NonGbkClient(), "https://fixture/")
            engine.gateway.sina_bars = FreshBars()
            engine.gateway.tencent_bars = FreshBars()
            engine.gateway.fund_bars = FreshBars()

            report = engine.run_once()
            persisted = engine.store.latest()
            request_handler = handler(settings, engine.store)
            ready_status, ready = self._get_without_tcp(request_handler, "/health/ready")

            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            self.assertEqual(persisted["state"], "SYSTEM_BLOCKED")
            self.assertIsNone(persisted["decision"]["action"])
            self.assertIn("TENCENT_QUOTE:TENCENT_QUOTE_DECODE_FAILED", report["freshness_findings"])
            self.assertEqual(ready_status, 503)
            self.assertEqual(ready["state"], "SYSTEM_BLOCKED")


if __name__ == "__main__":
    unittest.main()
