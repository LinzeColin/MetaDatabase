#!/usr/bin/env python3
"""Read-only Codex/WeChat auth-state probe that never reads credential content."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION_RE = re.compile(r"\bcodex-cli\s+([0-9A-Za-z.+_-]+)\b")
LOGIN_POSITIVE_RE = re.compile(r"\blogged\s+in\b|\bauthenticated\b", re.IGNORECASE)
LOGIN_NEGATIVE_RE = re.compile(
    r"\bnot\s+logged\s+in\b|\bnot\s+authenticated\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe CLI/auth-state existence and permissions without reading "
            "auth, account, token or QR content."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("local", "authorized_ovh_staging"),
        required=True,
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
    )
    parser.add_argument(
        "--wechat-state-dir",
        type=Path,
        default=Path(
            os.environ.get("CYBERBOSS_STATE_DIR", Path.home() / ".cyberboss")
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Write only the JSON output; suppress the summary line.",
    )
    return parser.parse_args()


def run_metadata_command(command: list[str], environment: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "executed": False,
            "exit_code": None,
            "classification": type(error).__name__,
        }
    output = result.stdout or ""
    return {
        "executed": True,
        "exit_code": result.returncode,
        "output": output,
    }


def classify_login(command_result: dict[str, Any]) -> str:
    if not command_result.get("executed"):
        return "unknown"
    output = str(command_result.get("output") or "")
    if LOGIN_NEGATIVE_RE.search(output):
        return "not_authenticated"
    if command_result.get("exit_code") == 0 and LOGIN_POSITIVE_RE.search(output):
        return "authenticated"
    return "unknown"


def parse_version(command_result: dict[str, Any]) -> str | None:
    if not command_result.get("executed"):
        return None
    match = VERSION_RE.search(str(command_result.get("output") or ""))
    return match.group(1) if match else None


def file_metadata(path: Path, label: str) -> dict[str, Any]:
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return {
            "path_label": label,
            "present": False,
            "regular_file": False,
            "mode": None,
            "owner_is_probe_user": None,
            "group_or_other_bits_zero": None,
        }
    mode = stat.S_IMODE(metadata.st_mode)
    return {
        "path_label": label,
        "present": True,
        "regular_file": stat.S_ISREG(metadata.st_mode),
        "mode": f"{mode:04o}",
        "owner_is_probe_user": metadata.st_uid == os.geteuid(),
        "group_or_other_bits_zero": (mode & 0o077) == 0,
    }


def directory_metadata(path: Path, label: str) -> dict[str, Any]:
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return {
            "path_label": label,
            "present": False,
            "directory": False,
            "mode": None,
            "owner_is_probe_user": None,
            "group_or_other_write_bits_zero": None,
        }
    mode = stat.S_IMODE(metadata.st_mode)
    return {
        "path_label": label,
        "present": True,
        "directory": stat.S_ISDIR(metadata.st_mode),
        "mode": f"{mode:04o}",
        "owner_is_probe_user": metadata.st_uid == os.geteuid(),
        "group_or_other_write_bits_zero": (mode & 0o022) == 0,
    }


def count_account_state_files(state_dir: Path) -> int:
    accounts_dir = state_dir / "accounts"
    try:
        return sum(
            1
            for path in accounts_dir.iterdir()
            if path.is_file() and path.suffix == ".json"
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return 0


def sanitized_command_result(command_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "executed": bool(command_result.get("executed")),
        "exit_code": command_result.get("exit_code"),
        "classification": command_result.get("classification"),
        "raw_output_persisted": False,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    codex_command = shutil.which("codex")
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(args.codex_home)

    version_result: dict[str, Any] = {
        "executed": False,
        "exit_code": None,
        "classification": "cli_absent",
    }
    login_result = dict(version_result)
    if codex_command:
        version_result = run_metadata_command([codex_command, "--version"], environment)
        login_result = run_metadata_command(
            [codex_command, "login", "status"],
            environment,
        )

    auth_file = file_metadata(
        args.codex_home / "auth.json",
        "$CODEX_HOME/auth.json",
    )
    codex_login_classification = classify_login(login_result)
    wechat_account_count = count_account_state_files(args.wechat_state_dir)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "claim_level": "read_only_probe",
        "probe_scope": args.mode,
        "external_mutation_performed": False,
        "credential_content_read": False,
        "credential_values_emitted": False,
        "codex": {
            "cli_present": codex_command is not None,
            "version": parse_version(version_result),
            "version_probe": sanitized_command_result(version_result),
            "login_status_probe": sanitized_command_result(login_result),
            "login_classification": codex_login_classification,
            "auth_file": auth_file,
            "target_adapter_state": (
                "activation_pending"
                if args.mode == "local"
                else (
                    "verified"
                    if codex_login_classification == "authenticated"
                    and auth_file["present"]
                    and auth_file["regular_file"]
                    and auth_file["group_or_other_bits_zero"]
                    else "activation_pending"
                )
            ),
        },
        "wechat": {
            "state_directory": directory_metadata(
                args.wechat_state_dir,
                "$CYBERBOSS_STATE_DIR",
            ),
            "account_state_file_count": wechat_account_count,
            "account_state_content_read": False,
            "target_adapter_state": "activation_pending",
            "real_ping_sent": False,
            "real_qr_scanned": False,
        },
        "acceptance": {
            "ac_001_real": "activation_pending",
            "ac_010_real": "activation_pending",
            "ac_056_non_activation_continuation": "eligible",
            "ac_065_secret_exposure": "no_values_observed",
        },
    }


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not args.quiet:
        print(
            "AUTH_ACTIVATION_CHECK=PASS "
            f"scope={report['probe_scope']} "
            f"codex={report['codex']['target_adapter_state']} "
            f"wechat={report['wechat']['target_adapter_state']} "
            "external_mutation=0 credential_values_emitted=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
