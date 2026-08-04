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
        # compose.workers.yaml 已随 v0.0.0.7 / T03 删除（那三个 HTTP worker 被实测证伪，
        # 上游 API 没有任何收藏枚举接口）。这一行留着会让**发布门本身**永远 FAIL——
        # 而且从 T03 起就是红的，只是没人跑它，所以一直没被发现。
        [python, "scripts/validate_systemd.py"],
        # v0.0.0.7 新增的三道门。不挂进来的话，它们只在有人手动敲 pytest 时才生效。
        [python, "scripts/preflight_extension.py"],
        [python, "scripts/scan_plaintext_credentials.py", "--all"],
        # 「建好了没接上」在本会话出现了**五次**（失败文案词典、静默零审计、
        # 扩展的 lastResult、凭据托管、多租户审计）。每一次都是模块写完、
        # 判据全绿，然后才发现没有人在调它。判据证明「函数写得对」，
        # 不证明「有人在调」。这道门把第六次挡在发布之前。
        [python, "scripts/find_unwired_code.py"],
        # 失败码 → 中文句子是**人手维护**的映射表，新加一个码没人提醒你补词典。
        # 补漏的后果不是少一句话，是界面说「我们没能记录下原因」而原因就在代码里。
        # 这道门第一次跑就找出 24 个说不出人话的码。
        [python, "scripts/check_every_failure_code_is_explainable.py"],
        [python, "scripts/validate_deployment_contract.py"],
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
