from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> dict[str, object]:
    completed = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-5000:],
        "stderr": completed.stderr[-5000:],
    }


def structural_commands() -> list[list[str]]:
    """Checks that are safe after SA-507's single frozen full-suite run.

    The Task Pack deliberately puts the only application-suite command before
    this script.  Re-running pytest here would make a green final verifier
    ambiguous: it could no longer prove which candidate the one permitted
    full-suite result belongs to.
    """

    python = sys.executable
    return [
        [python, "-B", "-m", "compileall", "-q", "src", "scripts"],
        [python, "scripts/check_brand.py"],
        [python, "scripts/secret_scan.py", "."],
        [python, "scripts/validate_compose.py", "compose.yaml"],
        [python, "scripts/validate_compose.py", "compose.readers.yaml"],
        [python, "scripts/validate_compose.py", "compose.workers.yaml"],
        [python, "scripts/validate_systemd.py"],
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Social Archive final structural verification.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="explicitly run pytest; do not use this during the SA-507 single-suite release run",
    )
    args = parser.parse_args(argv)
    commands = structural_commands()
    suite_mode = "structural"
    if args.full:
        commands.append([sys.executable, "-m", "pytest", "-q"])
        suite_mode = "explicit_full"

    results = [run(command) for command in commands]
    status = "PASS" if all(int(result["exit_code"]) == 0 for result in results) else "FAIL"
    report = {
        "status": status,
        "suite_mode": suite_mode,
        "application_suite_rerun": bool(args.full),
        "results": results,
    }
    output = ROOT / "evidence/final-verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(status)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
