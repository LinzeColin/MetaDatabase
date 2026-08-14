from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_lattice_v19.engine import V19Engine
from signal_lattice_v19.storage import RuntimeStorage

from common import fixture_settings

ROOT = Path(__file__).resolve().parents[1]
TOP = ["运行时间", "提示词版本", "运行状态", "市场覆盖", "数据截止", "状态连续性", "裁决完整性", "技能适用覆盖率", "第一板块", "第二板块"]
FIRST = ["唯一操作", "唯一平台", "唯一标的", "代码", "唯一方向", "可观察回撤", "风险调整回撤", "剩余回撤预算", "预期研究窗口", "相对宽基", "相对现金", "现在怎么做", "核心依据", "最大反证", "失效条件", "下一正式复核"]
SECOND = ["矩阵", "适用技能", "实际参与", "适用覆盖率", "原生参与", "原生覆盖率", "中央定量审查", "权重说明"]


class ReportContractTests(unittest.TestCase):
    def test_exact_v16_visible_structure_and_v19_version(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            report = V19Engine(settings).run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))["report"]
            self.assertEqual(list(report), TOP)
            self.assertEqual(list(report["第一板块"]), FIRST)
            self.assertEqual(list(report["第二板块"]), SECOND)
            self.assertEqual(report["提示词版本"], "v0.0.0.19")
            text = json.dumps(report, ensure_ascii=False)
            self.assertNotIn("v0.0.0." + "20", text)
            self.assertNotIn("V" + "20", text)

    def test_public_payload_contains_one_asset_and_one_code(self):
        with fixture_settings(ROOT) as (settings, state_dir):
            RuntimeStorage(state_dir).bootstrap(settings.canonical_state)
            report = V19Engine(settings).run_once(datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc))["report"]
            first = report["第一板块"]
            self.assertEqual(first["唯一标的"], "State Street SPDR 标普500 ETF")
            self.assertEqual(first["代码"], "SPY")
            self.assertNotIn("SEMI", json.dumps(first, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
