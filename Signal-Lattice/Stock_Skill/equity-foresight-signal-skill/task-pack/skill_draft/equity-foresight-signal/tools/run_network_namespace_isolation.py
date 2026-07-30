from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_foresight_signal import evaluate, self_check, train_direction_pipeline
from equity_foresight_signal.canonical import sha256_hex

SCHEMA = "efs.network_namespace_isolation_execution.v1"
WORKER_SCHEMA = "efs.network_namespace_isolation_worker.v1"
EXPECTED_NETWORK_ERRNOS = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EACCES, errno.EPERM, errno.ETIMEDOUT}


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def _net_namespace_id() -> str | None:
    try:
        return os.readlink("/proc/self/ns/net")
    except OSError:
        return None


def _network_probe() -> dict[str, Any]:
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=0.25):
            pass
    except OSError as exc:
        return {
            "status": "PASS" if exc.errno in EXPECTED_NETWORK_ERRNOS else "FAIL",
            "errno": exc.errno,
            "exception": type(exc).__name__,
        }
    return {"status": "FAIL", "errno": None, "exception": "UNEXPECTED_CONNECTION_SUCCESS"}


def _worker() -> dict[str, Any]:
    request = _load_fixture("request.json")
    bundle = _load_fixture("bundle.json")
    trust = _load_fixture("trust_context_shadow.json")
    dataset = _load_fixture("pit_dataset.json")
    config = _load_fixture("training_config.json")
    network_probe = _network_probe()
    forecast = evaluate(request, bundle, trust)
    training = train_direction_pipeline(dataset, config)
    runtime = self_check()
    checks = {
        "network_connection_blocked": network_probe["status"] == "PASS",
        "forecast_completed": forecast.get("status") in {"FORECAST", "ABSTAIN"},
        "forecast_hash_present": isinstance(forecast.get("result_sha256"), str),
        "training_hash_present": isinstance(training.get("run_sha256"), str),
        "runtime_agent_dependency_zero": runtime["runtime_profile"]["agent_dependency"] == 0,
        "runtime_llm_dependency_zero": runtime["runtime_profile"]["llm_dependency"] == 0,
        "runtime_network_dependency_zero": runtime["runtime_profile"]["network_dependency"] == 0,
    }
    report = {
        "schema": WORKER_SCHEMA,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "child_network_namespace": _net_namespace_id(),
        "network_probe": network_probe,
        "checks": checks,
        "forecast_result_sha256": forecast.get("result_sha256"),
        "training_run_sha256": training.get("run_sha256"),
        "runtime_self_check_sha256": sha256_hex(runtime),
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_success_total": 0,
    }
    report["worker_sha256"] = sha256_hex(report)
    return report


def execute() -> dict[str, Any]:
    if sys.platform != "linux":
        report = {
            "schema": SCHEMA,
            "status": "NOT_APPLICABLE_UNSUPPORTED_PROFILE",
            "claim_boundary": "V0_NETWORK_NAMESPACE_ORACLE_IS_LINUX_ONLY",
        }
        report["report_sha256"] = sha256_hex(report)
        return report
    unshare = shutil.which("unshare")
    if not unshare:
        report = {"schema": SCHEMA, "status": "NOT_RUN_ENVIRONMENT", "reason": "UNSHARE_NOT_FOUND"}
        report["report_sha256"] = sha256_hex(report)
        return report
    parent_namespace = _net_namespace_id()
    command = [
        unshare,
        "--user",
        "--map-root-user",
        "--net",
        "--",
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
    ]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    try:
        worker = json.loads(completed.stdout)
    except json.JSONDecodeError:
        worker = None
    child_namespace = worker.get("child_network_namespace") if worker else None
    namespace_distinct = bool(parent_namespace and child_namespace and child_namespace != parent_namespace)
    passed = bool(completed.returncode == 0 and worker and worker.get("status") == "PASS" and namespace_distinct)
    report = {
        "schema": SCHEMA,
        "status": "PASS" if passed else "FAIL",
        "parent_network_namespace": parent_namespace,
        "child_network_namespace": child_namespace,
        "namespace_is_distinct": namespace_distinct,
        "worker": worker,
        "command_returncode": completed.returncode,
        "stderr_tail": completed.stderr[-1000:],
        "claim_boundary": (
            "LINUX_USER_AND_NETWORK_NAMESPACE_WITH_NO_EXTERNAL_ROUTE; "
            "THIS PROVES THE TESTED CHILD RUNTIME AND TRAINING PATH COMPLETE IN A DISTINCT NETWORK NAMESPACE "
            "WHERE AN EXPLICIT OUTBOUND CONNECTION FAILS, NOT A GENERAL HOST-WIDE FIREWALL CLAIM"
        ),
    }
    report["report_sha256"] = sha256_hex(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run EFS in a distinct Linux user/network namespace")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = _worker() if args.worker else execute()
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    if args.worker:
        return 0 if report["status"] == "PASS" else 1
    return 0 if report["status"] in {"PASS", "NOT_APPLICABLE_UNSUPPORTED_PROFILE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
