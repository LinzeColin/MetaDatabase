"""once 每分钟跑一次：stdout 只在结论变化时记一行，不再打印整份报告。

原先每轮把整份报告（约 7,500 行、0.7 MB）打到 stdout，journal 与 syslog 各存一份，
整机日志被冲到只剩 2 天。整份报告本来就落盘在 latest.json，stdout 不需要再给一份。
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from signal_lattice import cli
from signal_lattice.live_runtime import LiveStore


def report(state: str, action_code: str, symbol: str, conviction: float) -> dict:
    return {
        "state": state,
        "generated_at": f"2026-09-30T09:0{int(conviction * 10) % 10}:00+00:00",
        "decision": {"action_code": action_code, "primary_symbol": symbol, "conviction": conviction},
        "blocking_findings": [] if state == "DATA_READY" else ["QUOTE_STALE:usSPY"],
        "backtest": {"payload": "x" * 50_000},
    }


class OnceOutputTests(unittest.TestCase):
    def run_once_with(self, state_dir: Path, produced: dict) -> tuple[int, str]:
        def fake_run_once(engine_self):
            LiveStore(state_dir).save(produced)
            return produced

        buffer = io.StringIO()
        with patch.dict(os.environ, {"SIGNAL_LATTICE_STATE_DIR": str(state_dir)}), patch.object(
            cli.LiveEngine, "__init__", lambda engine_self, settings: None
        ), patch.object(cli.LiveEngine, "run_once", fake_run_once), redirect_stdout(buffer):
            code = cli.main(["once"])
        return code, buffer.getvalue()

    def test_logs_one_line_only_when_outcome_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)

            code, first = self.run_once_with(state_dir, report("DATA_READY", "BULLISH", "usQQQ", 0.61))
            self.assertEqual(code, 0)
            self.assertEqual(len(first.splitlines()), 1)
            line = json.loads(first)
            self.assertEqual(line["event"], "OUTCOME_CHANGED")
            self.assertEqual(line["action_code"], "BULLISH")
            self.assertNotIn("backtest", line)
            self.assertLess(len(first), 1_000)

            # 同一结论、只有置信度变化：不打印。
            code, same = self.run_once_with(state_dir, report("DATA_READY", "BULLISH", "usQQQ", 0.63))
            self.assertEqual(code, 0)
            self.assertEqual(same, "")

            # 结论变化：记一行，并带上阻断原因；退出码照旧非零。
            code, changed = self.run_once_with(state_dir, report("SYSTEM_BLOCKED", "NO_ACTION", "usQQQ", 0.0))
            self.assertEqual(code, 2)
            line = json.loads(changed)
            self.assertEqual(line["state"], "SYSTEM_BLOCKED")
            self.assertEqual(line["blocking_findings"], ["QUOTE_STALE:usSPY"])

            # 整份报告仍然落盘，print-latest 读到的是完整报告。
            self.assertIn("backtest", LiveStore(state_dir).latest())


if __name__ == "__main__":
    unittest.main()
