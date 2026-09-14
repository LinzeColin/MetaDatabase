"""生产入口必须永远到不了 v19 的 fixture / moomoo 行情路径。

用户最初的问题是「页面 200 但行情冻在 2026-08-09 的 fixture」。v19 那套
config.Settings + market_provider（默认 market_provider="fixture"）仍留在包里
供历史测试使用，但 5 个生产子命令必须只能走 marketdata/ 下的真实免密钥接口。
这条测试锁死这个边界：一旦有人把 v19 栈重新接回 CLI，这里立刻红。
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "signal_lattice"
FORBIDDEN_MODULES = {"config", "cycle_engine", "market_provider", "api", "worker", "orchestrator"}
PRODUCTION_ENTRY = "cli"


def _local_imports(module_name: str) -> set[str]:
    tree = ast.parse((SRC / f"{module_name}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("signal_lattice."):
                    found.add(alias.name.split(".")[1])
    return found


def _reachable_from(entry: str) -> set[str]:
    seen: set[str] = set()
    queue = [entry]
    while queue:
        current = queue.pop()
        if current in seen or not (SRC / f"{current}.py").is_file():
            continue
        seen.add(current)
        queue.extend(_local_imports(current))
    return seen


class ProductionEntrypointTests(unittest.TestCase):
    def test_cli_cannot_reach_v19_fixture_stack(self):
        reachable = _reachable_from(PRODUCTION_ENTRY)
        leaked = sorted(reachable & FORBIDDEN_MODULES)
        self.assertEqual(leaked, [], "生产 CLI 可达 v19 行情栈：%s" % leaked)

    def test_cli_subcommands_are_the_five_known_ones(self):
        tree = ast.parse((SRC / "cli.py").read_text(encoding="utf-8"))
        names = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        }
        self.assertEqual(names, {"once", "loop", "serve", "print-latest", "verify-runtime"})

    def test_v19_fixture_default_stays_out_of_the_live_universe(self):
        live = (SRC / "live_config.py").read_text(encoding="utf-8")
        for token in ("fixture", "moomoo", "market_provider"):
            self.assertNotIn(token, live, token)


if __name__ == "__main__":
    unittest.main()
