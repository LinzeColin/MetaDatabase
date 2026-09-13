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
    sub.add_parser("loop")
    sub.add_parser("serve")
    sub.add_parser("print-latest")
    return root


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    settings = LiveSettings.from_env(project_root())
    if args.command == "once":
        report = LiveEngine(settings).run_once()
        print(strict_json_dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["state"] == "DATA_READY" else 2
    if args.command == "loop":
        engine = LiveEngine(settings)
        while True:
            engine.run_once()
            time.sleep(settings.loop_seconds)
    if args.command == "serve":
        serve(settings)
        return 0
    if args.command == "print-latest":
        report = LiveStore(settings.state_dir).latest()
        print(strict_json_dumps(report or {"state": "SYSTEM_BLOCKED", "message": "数据链路不完整，不出结论"}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
