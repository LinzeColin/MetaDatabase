#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MODEL_SECRET_KEYS = {
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "AZURE_OPENAI_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY",
}
REDACT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s]+)"),
)
PASS_STATES = {"PASS", "SATISFIED", "NO_CHANGE"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def self_hashed(payload: dict[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body.pop("receipt_sha256", None)
    body["receipt_sha256"] = digest(body)
    return body


def verify_receipt(path: Path) -> tuple[bool, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        claimed = payload.pop("receipt_sha256")
        return claimed == digest(payload), payload.get("state")
    except Exception:
        return False, None


def redact(text: str, secret_values: list[str]) -> str:
    out = text
    for value in sorted({v for v in secret_values if v}, key=len, reverse=True):
        out = out.replace(value, "<REDACTED>")
    for pattern in REDACT_PATTERNS:
        out = pattern.sub(lambda m: m.group(1) + m.group(2) + "<REDACTED>" if len(m.groups()) == 3 else m.group(1) + "<REDACTED>", out)
    return out


def expand(value: str, root: Path, artifacts: Path) -> str:
    value = value.replace("{ROOT}", str(root)).replace("{ARTIFACT_DIR}", str(artifacts))

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        val = os.environ.get(key)
        if val is None:
            raise KeyError(key)
        return val

    return re.sub(r"\$\{([A-Z0-9_]+)\}", repl, value)


def write_receipt(path: Path, payload: dict[str, Any]) -> None:
    body = self_hashed(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def run_command(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int, secret_values: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
    duration = round(time.monotonic() - started, 6)
    safe_stdout = redact(stdout or "", secret_values)
    safe_stderr = redact(stderr or "", secret_values)
    return {
        "command": cmd,
        "command_sha256": digest(cmd),
        "returncode": 124 if timed_out else proc.returncode,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "stdout_sha256": hashlib.sha256((stdout or "").encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256((stderr or "").encode()).hexdigest(),
        "stdout_tail": safe_stdout[-2000:],
        "stderr_tail": safe_stderr[-2000:],
    }


def load_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = json.loads((root / "machine/facts/task_execution_contract.json").read_text(encoding="utf-8"))
    dag = json.loads((root / "machine/facts/task_dag.json").read_text(encoding="utf-8"))
    state = json.loads((root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))
    return contract, dag, state


def validate_row(row: dict[str, Any], dagrow: dict[str, Any], root: Path) -> list[str]:
    findings: list[str] = []
    required = (
        "task_id", "title", "mode", "environment_bound", "environment_bound_reason",
        "authorization_required", "authorization_env", "required_env", "commands",
        "timeout_seconds", "allow_degraded", "expected", "failure_branch",
        "stop_condition", "rollback", "evidence_path",
    )
    for key in required:
        if key not in row:
            findings.append("MISSING_CONTRACT_FIELD:" + key)
    if row.get("task_id") != dagrow.get("id"):
        findings.append("TASK_ID_MISMATCH")
    if row.get("environment_bound") != dagrow.get("environment_bound"):
        findings.append("ENVIRONMENT_BOUND_MISMATCH")
    if row.get("mode") not in {"DETERMINISTIC", "ENVIRONMENT_BOUND", "AUTHORIZED_SIDE_EFFECT"}:
        findings.append("INVALID_MODE")
    if row.get("authorization_required") and row.get("mode") != "AUTHORIZED_SIDE_EFFECT":
        findings.append("AUTHORIZATION_MODE_MISMATCH")
    if row.get("authorization_required") and not row.get("authorization_env"):
        findings.append("AUTHORIZATION_ENV_MISSING")
    if not isinstance(row.get("required_env"), list) or any(not isinstance(x, str) or not x for x in row.get("required_env", [])):
        findings.append("INVALID_REQUIRED_ENV")
    if not isinstance(row.get("commands"), list) or not row.get("commands"):
        findings.append("NO_COMMANDS")
    for cmd in row.get("commands", []):
        if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) and x for x in cmd):
            findings.append("INVALID_COMMAND")
            continue
        if cmd[0] in {"python3", "bash"} and len(cmd) > 1 and cmd[1].startswith("scripts/") and not (root / cmd[1]).is_file():
            findings.append("MISSING_SCRIPT:" + cmd[1])
    timeout = row.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout < 1 or timeout > 3600:
        findings.append("INVALID_TIMEOUT")
    expected_evidence = "{ARTIFACT_DIR}/tasks/" + row.get("task_id", "UNKNOWN") + ".json"
    if row.get("evidence_path") != expected_evidence:
        findings.append("EVIDENCE_PATH_MISMATCH")
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task")
    parser.add_argument("--validate-all", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan", action="store_true")
    group.add_argument("--validate", action="store_true")
    group.add_argument("--execute", action="store_true")
    parser.add_argument("--ignore-dependencies", action="store_true")
    args = parser.parse_args()
    if not args.validate_all and (not args.task or not (args.plan or args.validate or args.execute)):
        parser.error("--task and one of --plan/--validate/--execute are required unless --validate-all is used")
    if args.validate_all and (args.task or args.plan or args.validate or args.execute):
        parser.error("--validate-all cannot be combined with task execution flags")

    root = Path(__file__).resolve().parents[1]
    artifacts = Path(os.environ.get("SIGNAL_LATTICE_ARTIFACT_DIR", "/tmp/signal-lattice-artifacts")).resolve()
    contract, dag, canonical_state = load_inputs(root)
    rows = {x["task_id"]: x for x in contract["tasks"]}
    dagrows = {x["id"]: x for x in dag["tasks"]}
    if args.validate_all:
        findings: dict[str, list[str]] = {}
        if set(rows) != set(dagrows):
            findings["TASK_SET"] = ["CONTRACT_DAG_TASK_SET_MISMATCH"]
        for task_id in sorted(set(rows) & set(dagrows)):
            row_findings = validate_row(rows[task_id], dagrows[task_id], root)
            if row_findings:
                findings[task_id] = row_findings
        payload = {
            "schema_version": "1.0.0",
            "state": "PASS" if not findings else "FAIL",
            "task_count": len(rows),
            "findings": findings,
            "candidate_version": canonical_state.get("taskpack_version"),
            "developer_research_required": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if not findings else 2
    if args.task not in rows or args.task not in dagrows:
        print(json.dumps({"state": "FAIL", "reason": "UNKNOWN_TASK", "task_id": args.task}, sort_keys=True))
        return 2

    row = rows[args.task]
    dagrow = dagrows[args.task]
    findings = validate_row(row, dagrow, root)
    plan = {
        "schema_version": "1.0.0",
        "state": "PASS" if not findings else "FAIL",
        "task_id": args.task,
        "title": row.get("title"),
        "mode": row.get("mode"),
        "environment_bound": row.get("environment_bound"),
        "environment_bound_reason": row.get("environment_bound_reason"),
        "authorization_required": row.get("authorization_required"),
        "authorization_env": row.get("authorization_env"),
        "required_env": row.get("required_env", []),
        "depends_on": dagrow.get("depends_on", []),
        "commands": row.get("commands", []),
        "expected": row.get("expected"),
        "failure_branch": row.get("failure_branch"),
        "stop_condition": row.get("stop_condition"),
        "rollback": row.get("rollback"),
        "evidence_path": row.get("evidence_path"),
        "findings": findings,
        "candidate_version": canonical_state.get("taskpack_version"),
        "input_sha256": digest({"contract": row, "dag": dagrow, "state": canonical_state}),
        "developer_research_required": False,
    }
    if args.plan or args.validate:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0 if not findings else 2
    if findings:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 2

    receipt_path = Path(expand(row["evidence_path"], root, artifacts))
    missing = [key for key in row["required_env"] if not os.environ.get(key)]
    if missing:
        payload = {
            **plan,
            "state": "BLOCKED",
            "reason": "ENVIRONMENT_INPUT_MISSING",
            "missing": missing,
        }
        write_receipt(receipt_path, payload)
        print(json.dumps({"state": "BLOCKED", "task_id": args.task, "receipt": str(receipt_path), "missing": missing}, ensure_ascii=False, sort_keys=True))
        return 2

    if row["authorization_required"]:
        auth_env = row["authorization_env"]
        if os.environ.get(str(auth_env)) != "1":
            payload = {
                **plan,
                "state": "BLOCKED",
                "reason": "EXPLICIT_SIDE_EFFECT_AUTHORIZATION_REQUIRED",
                "authorization_env": auth_env,
            }
            write_receipt(receipt_path, payload)
            print(json.dumps({"state": "BLOCKED", "task_id": args.task, "receipt": str(receipt_path), "reason": payload["reason"]}, sort_keys=True))
            return 2

    if not args.ignore_dependencies:
        blocked: list[dict[str, str]] = []
        for dep in dagrow.get("depends_on", []):
            dep_path = artifacts / "tasks" / f"{dep}.json"
            valid, dep_state = verify_receipt(dep_path) if dep_path.is_file() else (False, None)
            if not valid or dep_state not in PASS_STATES:
                blocked.append({"task_id": dep, "reason": "RECEIPT_INVALID" if dep_path.is_file() and not valid else "RECEIPT_NOT_PASS"})
        if blocked:
            payload = {
                **plan,
                "state": "BLOCKED",
                "reason": "DEPENDENCY_RECEIPT_NOT_PASS",
                "dependencies": blocked,
            }
            write_receipt(receipt_path, payload)
            print(json.dumps({"state": "BLOCKED", "task_id": args.task, "receipt": str(receipt_path), "dependencies": blocked}, sort_keys=True))
            return 2

    env = {k: v for k, v in os.environ.items() if k not in MODEL_SECRET_KEYS and k != "PYTHONHOME"}
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONHASHSEED"] = "0"
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    secret_values = [os.environ.get(k, "") for k in MODEL_SECRET_KEYS]
    runs: list[dict[str, Any]] = []
    state = "PASS"
    reason: str | None = None
    for raw in row["commands"]:
        try:
            cmd = [expand(x, root, artifacts) for x in raw]
        except KeyError as exc:
            state = "BLOCKED"
            reason = "ENV_EXPANSION_MISSING:" + str(exc)
            runs.append({"command": raw, "returncode": 2, "reason": reason})
            break
        result = run_command(cmd, root, env, row["timeout_seconds"], secret_values)
        runs.append(result)
        if result["returncode"] != 0:
            state = "BLOCKED" if result["returncode"] in {2, 124} else "FAIL"
            reason = "COMMAND_TIMEOUT" if result["timed_out"] else "COMMAND_FAILED"
            break

    payload = {
        **plan,
        "state": state,
        "reason": reason,
        "runs": runs,
        "completed_command_count": len(runs),
        "command_count": len(row["commands"]),
        "side_effect_authorized": (not row["authorization_required"]) or os.environ.get(str(row["authorization_env"])) == "1",
    }
    write_receipt(receipt_path, payload)
    print(json.dumps({"state": state, "task_id": args.task, "receipt": str(receipt_path)}, ensure_ascii=False, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
