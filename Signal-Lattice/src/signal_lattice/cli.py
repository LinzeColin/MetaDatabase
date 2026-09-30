"""Signal Lattice V2 production command line.

生产命令只会拉取可追溯的免费数据源。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List, Optional

from .live_api import serve
from .live_config import APP_VERSION, LiveSettings
from .live_runtime import LiveEngine, LiveStore
from .serialization import strict_json_dumps


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="signal-lattice")
    root.add_argument("--version", action="version", version=APP_VERSION)
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("once")
    loop = sub.add_parser("loop")
    loop.add_argument("--max-runs", type=int, default=1)
    sub.add_parser("serve")
    sub.add_parser("print-latest")
    sub.add_parser("verify-runtime")
    research = sub.add_parser("research", help="研究层：候选池 -> 增量采集 -> 证据快照 -> 五个分支（隔离子进程）-> shortlist")
    from .research_cycle import add_arguments as add_research_arguments
    add_research_arguments(research)
    backtest = sub.add_parser("backtest", help="中枢回测：按月末重放线上规则（时点正确、扣成本、安慰剂），落盘 hub-backtest.json")
    backtest.add_argument("--research-dir", type=Path, required=True, help="研究层产物目录（含 <as_of>/latest.json），取其证据快照")
    backtest.add_argument("--out-dir", type=Path, required=True, help="回测产物目录；实时层读 SIGNAL_LATTICE_BACKTEST_DIR 下的 hub-backtest.json")
    backtest.add_argument("--cache-dir", type=Path, required=True, help="每个月末的重建结果缓存（重跑不重算）")
    backtest.add_argument("--start", default="2024-12-31")
    backtest.add_argument("--end", default="2026-08-31")
    backtest.add_argument("--workers", type=int, default=6)
    return root


def verify_runtime(settings: LiveSettings) -> dict:
    """只验证已安装 runtime 的静态依赖；不读取行情也不写入 state_dir。"""
    web_index = settings.web_dir / "index.html"
    checks = {
        "application_version": APP_VERSION,
        "state_dir": str(settings.state_dir),
        "state_dir_exists": settings.state_dir.is_dir(),
        "web_dir": str(settings.web_dir),
        "web_index_exists": web_index.is_file(),
        "commands": ["once", "loop", "serve", "print-latest", "verify-runtime", "research", "backtest"],
    }
    return {
        "state": "PASS" if checks["state_dir_exists"] and checks["web_index_exists"] else "FAIL",
        "checks": checks,
    }


def run_outcome(report: dict) -> dict:
    """一轮采集的结论摘要：只含决定「要不要记一行」的字段。"""
    decision = report.get("decision") or {}
    return {
        "state": report.get("state"),
        "action_code": decision.get("action_code"),
        "primary_symbol": decision.get("primary_symbol"),
        "blocking_findings": report.get("blocking_findings") or [],
    }


def backtest_main(args: argparse.Namespace) -> int:
    import json
    from .backtest import hub_backtest
    from .research_view import latest_day_dir
    day = latest_day_dir(args.research_dir)
    if day is None:
        print("找不到研究产物：%s" % args.research_dir)
        return 2
    latest = json.loads((day / "latest.json").read_text("utf-8"))
    cycle = json.loads((day / latest["cycle"]).read_text("utf-8"))
    report = hub_backtest.run(hub_backtest.BacktestConfig(
        snapshot_path=Path(cycle["snapshot"]), out_dir=args.out_dir, cache_dir=args.cache_dir,
        start=args.start, end=args.end, workers=args.workers))
    print(hub_backtest.render_summary(report))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "research":
        from .research_cycle import cli_main as research_main
        return research_main(args, project_root())
    if args.command == "backtest":
        return backtest_main(args)
    settings = LiveSettings.from_env(project_root())
    if args.command == "once":
        # 定时器每分钟跑一次 once。整份报告已落盘（print-latest / API 可读），
        # stdout 只在结论变化时记一行：原先每轮打印整份报告约 0.7 MB，
        # journal 与 syslog 各存一份，把整机日志冲到只剩 2 天。
        previous = LiveStore(settings.state_dir).latest()
        report = LiveEngine(settings).run_once()
        outcome = run_outcome(report)
        if not previous or run_outcome(previous) != outcome:
            print(strict_json_dumps(
                {"event": "OUTCOME_CHANGED", "generated_at": report.get("generated_at"), **outcome},
                ensure_ascii=False, sort_keys=True,
            ))
        return 0 if report["state"] == "DATA_READY" else 2
    if args.command == "loop":
        engine = LiveEngine(settings)
        if args.max_runs < 1:
            raise SystemExit("LOOP_MAX_RUNS_MUST_BE_POSITIVE")
        final_report: dict = {}
        for iteration in range(args.max_runs):
            final_report = engine.run_once()
            if final_report["state"] != "DATA_READY":
                break
            if iteration + 1 < args.max_runs:
                time.sleep(settings.loop_seconds)
        print(strict_json_dumps(final_report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if final_report["state"] == "DATA_READY" else 2
    if args.command == "serve":
        serve(settings)
        return 0
    if args.command == "print-latest":
        report = LiveStore(settings.state_dir).latest()
        print(strict_json_dumps(report or {"state": "SYSTEM_BLOCKED", "message": "数据链路不完整，不出结论"}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report else 2
    if args.command == "verify-runtime":
        report = verify_runtime(settings)
        print(strict_json_dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["state"] == "PASS" else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
