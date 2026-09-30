"""一只候选掉线，不能让整个产品不出结论；结论真正依赖的输入出问题，仍然整站阻断。

线上事故（旧版）：港股 hk00700 的免费报价源取不到 source_time，数据门 fail-closed，整站变成
「数据链路不完整，不出结论」，而它对当轮结论的贡献是零。

重建后的边界，两个方向都钉死：
  · 某只候选的报价缺失/过期/停滞 -> 只有这只候选没过「实时报价」门，其它候选照常，结论照常发布；
  · 所有候选和 IWM 的报价都没通过 -> 行情源全断，SYSTEM_BLOCKED；
  · 研究层缺失/过期/分支收据不全 -> SYSTEM_BLOCKED（这些才是结论真正读取的输入）。
"""
import ast
import unittest
from pathlib import Path

from signal_lattice import hub
from hub_fixtures import NOW, build_view, fresh_market, run_decision, standard_pool

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")


class OneCandidateDegradesInsteadOfBlanking(unittest.TestCase):
    def test_a_candidate_without_a_quote_only_fails_its_own_quote_gate(self):
        view = build_view(standard_pool())
        market = fresh_market([e["symbol"] for e in view.shortlist])
        market["BETA"] = {"price": None, "quote_status": "QUOTE_MISSING", "source_time": None}
        outcome = run_decision(view, market=market)
        self.assertEqual(outcome["decision"]["state"], "RECOMMENDATION")
        by_symbol = {c["symbol"]: c for c in outcome["candidates"]}
        self.assertFalse(by_symbol["BETA"]["gates"]["quote"]["ok"])
        self.assertTrue(by_symbol["ALPHA"]["gates"]["quote"]["ok"])

    def test_every_quote_failing_is_a_blocked_system(self):
        view = build_view(standard_pool())
        self.assertEqual(run_decision(view, quotes_available=False)["decision"]["state"], "SYSTEM_BLOCKED")

    def test_research_inputs_are_what_the_conclusion_really_reads(self):
        view = build_view(standard_pool(), problems=["BRANCH_RECEIPT_MISSING:equity-event-atlas"])
        self.assertEqual(run_decision(view)["decision"]["state"], "SYSTEM_BLOCKED")

    def test_every_emitted_finding_puts_the_symbol_in_the_second_field(self):
        """发现格式「代码:标的:...」——页面和退避逻辑靠第二段是标的来归属。任何一处把标的编进代码里，归属就会失败。

        用 AST 逐个检查每一处 append 的实参位置，不靠格式串猜。
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
            symbol_positions = [index for index, text in enumerate(texts) if text in ("item.symbol", "symbol")]
            if not symbol_positions:
                continue
            checked += 1
            with self.subTest(template=template):
                self.assertEqual(symbol_positions[0], 0, f"{template}：标的必须是第一个实参")
                self.assertRegex(template, r"^[A-Za-z_0-9]+:%s", f"{template}：标的必须在第二段")
        self.assertGreaterEqual(checked, 10, "没有扫到足够的发现格式，这条防护可能失效了")

    def test_the_page_shows_degraded_candidates_with_the_decision(self):
        self.assertIn("degradedSummary", APP_JS)
        self.assertIn("renderDegraded", APP_JS)
        self.assertIn("它们本轮不参与发布判断，其它候选与结论不受影响。", APP_JS)
        hero = APP_JS[APP_JS.index("function renderDecisionHero"):]
        hero = hero[: hero.index("function renderCycle")]
        self.assertIn("degradedSummary(report)", hero)

    def test_a_degraded_symbol_price_is_not_presented_as_a_current_price(self):
        source = (ROOT / "src" / "signal_lattice" / "live_runtime.py").read_text(encoding="utf-8")
        self.assertIn("symbol not in degraded", source)


if __name__ == "__main__":
    unittest.main()
