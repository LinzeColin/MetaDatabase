#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://signal-lattice.linzezhang.com")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    browser = next((shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable") if shutil.which(name)), None)
    if not browser:
        print(json.dumps({"state": "BLOCKED", "reason": "CHROMIUM_NOT_FOUND", "required_for_release": False}, sort_keys=True))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--window-size=1440,1200",
        "--virtual-time-budget=8000",
        f"--screenshot={args.output}",
        args.url,
    ]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, env=env)
    passed = completed.returncode == 0 and args.output.is_file() and args.output.stat().st_size > 10_000
    payload = {
        "state": "PASS" if passed else "BLOCKED",
        "url": args.url,
        "output": args.output.as_posix(),
        "size": args.output.stat().st_size if args.output.exists() else 0,
        "returncode": completed.returncode,
        "stderr_tail": completed.stderr.decode(errors="replace")[-1000:],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
