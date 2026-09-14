"""一个对结论零贡献的标的掉线，不能让整个产品不出结论。

线上事故：港股 hk00700 的免费报价源取不到 source_time，数据门 fail-closed，
整站变成「数据链路不完整，不出结论」。而 hk00700 根本不在任何已实现分支的
资产池里（OUT_OF_STRATEGY_UNIVERSE，权重恒为 0），它对当轮结论的贡献是零。

正确行为：该标的降级并在页面上写明，结论照常发布；一旦出问题的是结论真正
读取的标的，仍然整站阻断。这个边界必须两个方向都钉死。
"""
import ast
import unittest
from pathlib import Path

from signal_lattice.branches import DECISION_INPUT_SYMBOLS
from signal_lattice.live_config import LiveSettings
from signal_lattice.live_runtime import LiveEngine

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")


def _bind(settings: LiveSettings) -> LiveEngine:
    """只装配分区逻辑需要的 settings，不碰状态目录和网络。"""
    instance = LiveEngine.__new__(LiveEngine)
    instance.settings = settings
    return instance


class UnrelatedSymbolDegradesInsteadOfBlanking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = LiveSettings.from_env(ROOT)
        cls.engine = _bind(settings)
        cls.symbols = {item.symbol for item in settings.universe}

    def test_the_decision_input_set_is_not_empty_and_is_a_real_subset(self):
        self.assertTrue(DECISION_INPUT_SYMBOLS)
        self.assertTrue(DECISION_INPUT_SYMBOLS <= self.symbols)
        self.assertTrue(self.symbols - DECISION_INPUT_SYMBOLS, "没有非结论标的，这条防护就形同虚设")

    def test_a_symbol_no_branch_reads_is_coverage_only(self):
        spare = sorted(self.symbols - DECISION_INPUT_SYMBOLS)[0]
        blocking, coverage = self.engine._partition_findings(
            ["QUOTE_SOURCE_TIME_MISSING:%s:tencent" % spare]
        )
        self.assertEqual(blocking, [])
        self.assertEqual(len(coverage), 1)

    def test_a_symbol_a_branch_actually_reads_still_blocks(self):
        for symbol in sorted(DECISION_INPUT_SYMBOLS):
            with self.subTest(symbol=symbol):
                blocking, coverage = self.engine._partition_findings(
                    ["QUOTE_SOURCE_TIME_MISSING:%s:sina" % symbol]
                )
                self.assertEqual(coverage, [])
                self.assertEqual(len(blocking), 1)

    def test_a_finding_with_no_symbol_still_blocks(self):
        for finding in ("COLLECTION_LOOP_UNREACHABLE", "SYSTEM_BLOCKED", "COLLECTION_BACKING_OFF"):
            with self.subTest(finding=finding):
                blocking, coverage = self.engine._partition_findings([finding])
                self.assertEqual(coverage, [])
                self.assertEqual(blocking, [finding])

    def test_a_finding_about_an_unknown_symbol_still_blocks(self):
        blocking, coverage = self.engine._partition_findings(["QUOTE_MISSING:usNOTREAL"])
        self.assertEqual(coverage, [])
        self.assertEqual(len(blocking), 1)

    def test_every_emitted_finding_puts_the_symbol_in_the_second_field(self):
        """分区靠「第二段是标的」。任何一处把标的编进代码里，归属就会失败。

        线上就是这样漏的：BARS_usSPY:... 的标的在代码里，分区读到的第二段是
        异常类型，于是一个覆盖面问题被误判成全站阻断。这里用 AST 逐个检查
        每一处 append 的实参位置，不靠格式串猜。
        """
        source = (ROOT / "src" / "signal_lattice" / "live_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        checked = 0
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                continue
            if call.func.attr != "append" or not call.args:
                continue
            value = call.args[0]
            if not (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mod)):
                continue
            if not (isinstance(value.left, ast.Constant) and isinstance(value.left.value, str)):
                continue
            template = value.left.value
            right = value.right
            arguments = list(right.elts) if isinstance(right, ast.Tuple) else [right]
            texts = [ast.unparse(argument) for argument in arguments]
            symbol_positions = [
                index for index, text in enumerate(texts) if text in ("item.symbol", "symbol")
            ]
            if not symbol_positions:
                continue
            checked += 1
            with self.subTest(template=template):
                self.assertEqual(
                    symbol_positions[0], 0, f"{template}：标的必须是第一个实参"
                )
                self.assertRegex(
                    template, r"^[A-Za-z_0-9]+:%s", f"{template}：标的必须在第二段"
                )
        self.assertGreaterEqual(checked, 10, "没有扫到足够的发现格式，这条防护可能失效了")

    def test_the_page_shows_degraded_symbols_with_the_decision(self):
        self.assertIn("degradedSummary", APP_JS)
        self.assertIn("renderDegraded", APP_JS)
        self.assertIn("这些标的不参与任何分支计算，结论不受影响。", APP_JS)
        hero = APP_JS[APP_JS.index("function renderDecisionHero"):]
        hero = hero[: hero.index("function renderCycle")]
        self.assertIn("degradedSummary(report)", hero)

    def test_a_degraded_symbol_price_is_not_presented_as_a_current_price(self):
        source = (ROOT / "src" / "signal_lattice" / "live_runtime.py").read_text(encoding="utf-8")
        self.assertIn("symbol not in degraded_symbols", source)


if __name__ == "__main__":
    unittest.main()
