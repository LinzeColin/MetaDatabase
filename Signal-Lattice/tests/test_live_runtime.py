import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from signal_lattice.live_runtime import LiveStore, apply_profitability_disclosure


def report_at(observed_at: datetime, price: float) -> dict:
    return {
        "state": "DATA_READY",
        "generated_at": observed_at.isoformat(),
        "market_fingerprint": {
            "quotes": {"usSPY": price},
            "bars": {"usSPY": observed_at.date().isoformat()},
        },
        "decision": {"state": "LONG", "action": "研究观察", "primary_symbol": "usSPY", "conviction": 0.609},
        "backtest": {"full_report_payload": "x" * 100_000},
        "branches": [{"full_branch_payload": "x" * 100_000}],
    }


class LiveHistoryTests(unittest.TestCase):
    def test_history_prunes_to_compact_day_budget_without_full_report_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LiveStore(root)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            with patch("signal_lattice.live_runtime.HISTORY_RETENTION_DAYS", 1), patch(
                "signal_lattice.live_runtime.HISTORY_MAX_RECORDS_PER_DAY", 2
            ), patch("signal_lattice.live_runtime.HISTORY_MAX_BYTES_PER_DAY", 2_048):
                store.save(report_at(now - timedelta(days=2), 98.0))
                store.save(report_at(now, 100.0))
                store.save(report_at(now + timedelta(seconds=1), 101.0))
                latest = report_at(now + timedelta(seconds=2), 102.0)
                store.save(latest)

                files = sorted((root / "history").glob("market_changes-*.jsonl"))
                lines = files[0].read_text(encoding="utf-8").splitlines()
                storage = latest["history_storage"]

            self.assertEqual(len(files), 1)
            self.assertEqual(len(lines), 2)
            self.assertLessEqual(storage["record_count"], 2)
            self.assertLessEqual(storage["bytes_used"], 2_048)
            self.assertEqual(storage["max_total_bytes"], 2_048)
            record = json.loads(lines[-1])
            self.assertEqual(set(record), {"generated_at", "state", "decision", "market_delta"})
            self.assertIn("quotes", record["market_delta"])
            self.assertNotIn("backtest", record)
            self.assertNotIn("branches", record)

    def test_directional_decision_is_preserved_and_marked_when_profitability_is_insufficient(self):
        branch_report = {
            "decision": {"state": "LONG", "primary_symbol": "usEEM", "conviction": 0.609}
        }
        backtest = {
            "sample_sufficiency": "OOS_HISTORY_INSUFFICIENT: 4/6",
            "sample_sufficiency_message": "样本外历史不足，仅供研究参考，不构成收益证据。",
        }

        apply_profitability_disclosure(branch_report, backtest)

        self.assertEqual(branch_report["decision"]["state"], "LONG")
        self.assertEqual(branch_report["decision"]["primary_symbol"], "usEEM")
        self.assertEqual(branch_report["decision"]["conviction"], 0.609)
        self.assertEqual(branch_report["decision"]["sample_sufficiency"], "OOS_HISTORY_INSUFFICIENT: 4/6")
        self.assertIn("仅供研究参考", branch_report["decision"]["sample_sufficiency_message"])


if __name__ == "__main__":
    unittest.main()
