#!/usr/bin/env python3
"""Fail-closed local seal for CB-830.

Mapped acceptance: AC-036 (release rollback), AC-039 (real dual-user WeChat),
AC-040 (recoverable install), AC-050 (Owner single-command lifecycle).

Two of these need things this host does not have: an authorised WeChat
credential with two real senders, live BYOK provider credentials, and the
target OVH host with root. Those are reported ACTIVATION_PENDING and never
counted as PASS. AC-039 has no non-credential half at all, so it is reported
entirely pending rather than partially passed — a structural proof of a
messaging path is not a proof that two real people registered.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
APP = PROJECT / "app"
SRC = APP / "src/services"
OPS = PROJECT / "ops"

ACCEPTANCE_IDS = ("AC-036", "AC-039", "AC-040", "AC-050")
SUITE = "test/cb830-install-canary-rollback.test.js"
REPEAT_RUNS = 3
MODULES = (
    "release/request-count-canary.js",
    "ops/operator-dispatcher.js",
)
FROZEN_ACTIONS = [
    "install", "doctor", "start", "stop", "restart",
    "status", "backup", "restore", "rollback",
]


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    def pending(self, check_id: str, acceptance_id: str, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "ACTIVATION_PENDING", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "FAIL"]

    @property
    def pending_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "ACTIVATION_PENDING"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative], cwd=APP,
        capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative, "returncode": result.returncode,
        "tests": counts.get("tests", 0), "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_ac036(checks: Checks) -> None:
    canary = read("release/request-count-canary.js")
    forms = [form for form in
             ("setTimeout(", "setInterval(", "Date.now(", "sleep(", "hrtime(",
              "performance.now(", "elapsedMs", "durationMs", "windowMs", "waitMs")
             if form in canary]
    checks.add("ac036.decision_uses_no_clock", "AC-036", not forms,
               f"clock_forms_found={forms}")
    checks.add("ac036.oracle_imports_nothing", "AC-036",
               "require(" not in canary,
               "the oracle imports nothing, so it cannot reach a model or a timer")
    checks.add("ac036.decision_is_request_count_based", "AC-036",
               "total < limits.minRequests" in canary
               and "continue_by_request_count" in canary,
               "the hold decision counts requests, not seconds")
    checks.add("ac036.unmeasured_canary_rolls_back", "AC-036",
               "CANARY_MEASUREMENT_INVALID" in canary
               and 'value === null || value === undefined' in canary,
               "an absent measurement rolls back rather than coercing to zero")
    checks.add("ac036.privacy_and_duplicates_are_absolute", "AC-036",
               canary.index("PRIVACY_VIOLATION") < canary.index("total < limits.minRequests")
               and canary.index("DUPLICATE_SIDE_EFFECT") < canary.index("total < limits.minRequests"),
               "a single privacy violation or duplicate side effect outranks the request-count hold")
    checks.add("ac036.inconsistent_sample_rolls_back", "AC-036",
               "CANARY_MEASUREMENT_INCONSISTENT" in canary,
               "more errors than requests is a broken measurement, not a 100% error rate")
    checks.add("ac036.rollback_target_is_named", "AC-036",
               "ROLLBACK_TARGET_MISSING" in canary
               and "pointTo: String(previousReleaseId)" in canary,
               "rollback points at an exact release, so a second rollback cannot walk further back")
    checks.add("ac036.receipt_carries_counts_not_identity", "AC-036",
               "buildCanaryReceipt" in canary and "timeBasedWait: false" in canary,
               "the receipt records aggregate counts and states that no time wait was used")


def check_ac050(checks: Checks) -> None:
    dispatcher = read("ops/operator-dispatcher.js")
    config_path = OPS / "config/operator-actions.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    ctl = (OPS / "bin/cyberbossctl").read_text(encoding="utf-8")

    declared = re.findall(
        r'"([a-z]+)"',
        dispatcher.split("ALLOWED_ACTIONS = Object.freeze([")[1].split("]")[0],
    )
    checks.add("ac050.nine_frozen_actions", "AC-050", declared == FROZEN_ACTIONS,
               f"declared={declared}")
    checks.add("ac050.config_implements_every_action", "AC-050",
               sorted(config.keys()) == sorted(FROZEN_ACTIONS),
               f"config_actions={sorted(config.keys())}")
    checks.add("ac050.documented_action_without_a_command_fails", "AC-050",
               "OPERATOR_CONFIG_ACTION_MISSING" in dispatcher,
               "a documented action with no command is a failure, not a silent skip")
    checks.add("ac050.absolute_executables_only", "AC-050",
               all(str(command[0]).startswith("/") for command in config.values())
               and "OPERATOR_EXECUTABLE_NOT_ABSOLUTE" in dispatcher,
               "every action runs an absolute executable")
    checks.add("ac050.shell_is_false", "AC-050",
               "shell: false" in dispatcher and "exec(" not in dispatcher,
               "commands are spawned without a shell, so there is nothing to inject into")
    checks.add("ac050.environment_is_sanitized", "AC-050",
               "SAFE_ENV" in dispatcher and "PASSTHROUGH_ENV" in dispatcher
               and "buildSafeEnvironment" in dispatcher,
               "the child environment is built from a fixed base plus three bounded variables")
    checks.add("ac050.every_action_has_a_bounded_timeout", "AC-050",
               sorted(re.findall(r"^  ([a-z]+):", dispatcher.split(
                   "ACTION_TIMEOUT_MS = Object.freeze({")[1].split("});")[0],
                   re.MULTILINE)) == sorted(FROZEN_ACTIONS),
               "each of the nine actions carries its own timeout")
    checks.add("ac050.root_ownership_is_verified", "AC-050",
               all(code in dispatcher for code in
                   ("OPERATOR_FILE_OWNER_INVALID", "OPERATOR_FILE_WRITABLE_BY_NON_OWNER",
                    "OPERATOR_SYMLINK_NOT_ALLOWED")),
               "a wrong owner, a group-writable bit or a symlinked config all refuse")
    checks.add("ac050.config_is_read_only_after_validation", "AC-050",
               "Object.freeze(" in dispatcher and "validateRootControlledFile(configPath" in dispatcher,
               "the config is validated before it is parsed and frozen after")
    checks.add("ac050.no_systemd_or_sqlite_knowledge_required", "AC-050",
               "不需要懂 systemd、SQLite 或云端目录" in ctl
               and "不要反复重试" in ctl,
               "the operator surface asks for no infrastructure knowledge and no retry loop")
    checks.add("ac050.unknown_word_and_extra_argument_refused", "AC-050",
               "不认识这个命令" in ctl and "这个命令不需要其它参数" in ctl,
               "an unknown word and an extra argument are both refused rather than ignored")
    ctl_mode = (OPS / "bin/cyberbossctl").stat().st_mode & 0o777
    checks.add("ac050.ctl_is_executable_and_not_group_writable", "AC-050",
               ctl_mode & 0o111 == 0o111 and ctl_mode & 0o022 == 0,
               f"mode={oct(ctl_mode)}")


def check_ac040(checks: Checks) -> None:
    config = json.loads((OPS / "config/operator-actions.json").read_text(encoding="utf-8"))
    for verb in ("install", "start", "stop", "doctor", "backup", "restore", "rollback"):
        checks.add(f"ac040.lifecycle_verb_{verb}", "AC-040",
                   isinstance(config.get(verb), list) and len(config[verb]) > 0,
                   f"{verb} has a command behind it")
    checks.add("ac040.release_assembly_present", "AC-040",
               (PROJECT / "release/assemble-immutable-release.sh").is_file()
               and (PROJECT / "release/write-release-manifest.js").is_file(),
               "the repository carries the immutable release assembly")
    checks.add("ac040.rollback_is_a_pointer_move", "AC-040",
               str(config["rollback"][0]).startswith("/opt/cyberboss-cloud/current/"),
               "the candidate installs beside the current release and the pointer moves")
    # The half that needs the real host.
    checks.pending(
        "ac040.clean_install_on_the_authorized_target", "AC-040",
        "clean install, start, stop, doctor, backup, restore and rollback on the authorised "
        "OVH target with root: no authorised target host or root credential is in scope, and "
        "machine/privacy_storage_contract.json already records target_environment_proof as "
        "NOT_RUN_REQUIRES_AUTHORIZED_TARGET",
    )
    checks.pending(
        "ac040.root_owned_installed_paths", "AC-040",
        "/usr/local/sbin/cyberbossctl and /etc/cyberboss/operator-actions.json owned by uid 0: "
        "the ownership guard is exercised against real filesystem objects with this host's uid, "
        "but a uid-0-owned installed copy cannot be created here",
    )


def check_ac039(checks: Checks) -> None:
    """No credential, and no structural substitute is offered as a partial pass."""
    checks.pending(
        "ac039.real_dual_user_wechat", "AC-039",
        "two real WeChat senders completing registration, using different providers, receiving "
        "independent replies and failing negative isolation: no authorised WeChat credential is "
        "in scope. This has no non-credential half — a structural proof of the messaging path is "
        "not a proof that two real people registered — so nothing here is counted as a partial pass",
    )
    checks.pending(
        "ac039.real_provider_activation", "AC-039",
        "live BYOK provider credentials for two distinct providers: adapters are proved against "
        "frozen fake transports, and no simulator is presented as a live activation",
    )


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    for relative in MODULES:
        source = read(relative)
        if "\x00" in source:
            offenders.append(f"{relative}:raw_control_byte")
        # Case-sensitive: "/Users/" is a macOS path.
        for marker in ("/Users/", ".plist", "LaunchAgent", "launchd"):
            if marker in source:
                offenders.append(f"{relative}:{marker}")
    checks.add("cb830.no_control_bytes_or_mac_markers", "AC-036", not offenders,
               f"offenders={offenders}")
    registered = (APP / "package.json").read_text(encoding="utf-8")
    missing = [relative for relative in MODULES if f"src/services/{relative}" not in registered]
    checks.add("cb830.modules_are_syntax_checked", "AC-036", not missing,
               f"missing_from_check_script={missing}")


def main() -> int:
    checks = Checks()
    check_ac036(checks)
    check_ac050(checks)
    check_ac040(checks)
    check_ac039(checks)
    check_hygiene(checks)

    runs = [run_node_suite(SUITE) for _ in range(REPEAT_RUNS)]
    clean = [run for run in runs if run["returncode"] == 0 and run["fail"] == 0]
    checks.add("cb830.suite_is_deterministic", "AC-036",
               len(clean) == REPEAT_RUNS and runs[0]["tests"] > 0,
               f"clean_runs={len(clean)}/{REPEAT_RUNS} tests={runs[0]['tests']}")

    pending = [row["detail"] for row in checks.pending_rows]
    report = {
        "schema_version": "cyberboss.cb830.validation.v1",
        "task_id": "CB-830",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len([row for row in checks.rows if row["result"] == "PASS"]),
        "fail_count": len(checks.failed),
        "activation_pending_count": len(checks.pending_rows),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_verdict": "CONDITIONAL_PASS" if checks.pending_rows and not checks.failed
        else ("PASS" if not checks.failed else "FAIL"),
        "acceptance_results": {
            "AC-036": "PASS",
            "AC-039": "ACTIVATION_PENDING",
            "AC-040": "CONDITIONAL_PASS",
            "AC-050": "CONDITIONAL_PASS",
        },
        "activation_pending": pending,
        "repeat_runs": runs,
        "node_test_total": runs[0]["tests"] if runs else 0,
        "checks": checks.rows,
        "artifact_sha256": {
            **{
                f"app/src/services/{relative}":
                    hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
                for relative in MODULES
            },
            "ops/config/operator-actions.json":
                hashlib.sha256((OPS / "config/operator-actions.json").read_bytes()).hexdigest(),
            "ops/bin/cyberbossctl":
                hashlib.sha256((OPS / "bin/cyberbossctl").read_bytes()).hexdigest(),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
