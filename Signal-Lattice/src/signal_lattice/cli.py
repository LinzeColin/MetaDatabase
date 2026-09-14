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
        "commands": ["once", "loop", "serve", "print-latest", "verify-runtime"],
    }
    return {
        "state": "PASS" if checks["state_dir_exists"] and checks["web_index_exists"] else "FAIL",
        "checks": checks,
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    settings = LiveSettings.from_env(project_root())
    if args.command == "once":
        report = LiveEngine(settings).run_once()
        print(strict_json_dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
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
