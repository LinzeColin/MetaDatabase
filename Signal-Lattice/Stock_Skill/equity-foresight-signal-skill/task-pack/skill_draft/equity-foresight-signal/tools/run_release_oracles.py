from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("tests_engine", "tests_cli_status", "tests_contracts", "specialized_tests", "statistical", "isolation", "static")
WORKSPACE_IGNORES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    "PREPACKAGING_RELEASE_ORACLES.json",
    "PREPACKAGING_REVIEW_CLOSURE.json",
}
_ACTIVE_PROCESSES: dict[int, subprocess.Popen[bytes]] = {}


def _emit(message: str, *, file: object = sys.stderr) -> None:
    try:
        print(message, file=file, flush=True)
    except BrokenPipeError:
        # The caller may close its display pipe while the output receipt is still
        # being written to --output. Do not turn that UI condition into an Oracle
        # failure or skip process-group cleanup.
        return


def _register_process(process: subprocess.Popen[bytes]) -> None:
    _ACTIVE_PROCESSES[process.pid] = process


def _unregister_process(process: subprocess.Popen[bytes]) -> None:
    _ACTIVE_PROCESSES.pop(process.pid, None)


def _process_group_exists(pgid: int) -> bool:
    if os.name != "posix":
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Existence is enough for cleanup accounting even if a restrictive
        # environment prevents signalling it directly.
        return True


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate the parent and every process left in its dedicated group.

    A command can exit successfully after spawning a child.  Checking only the
    parent's return code would leave that descendant running and violate the
    zero-resident-process contract.  Every command is started in a fresh
    session, so its PID is also the process-group ID and can be cleaned even
    after the group leader exits.
    """
    try:
        if os.name == "posix":
            pgid = process.pid
            if _process_group_exists(pgid):
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                if process.poll() is None:
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
                time.sleep(0.05)
                if _process_group_exists(pgid):
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if process.poll() is None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        elif process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    finally:
        _unregister_process(process)


def _terminate_all_active() -> int:
    processes = list(_ACTIVE_PROCESSES.values())
    for process in processes:
        _terminate_process(process)
    return len(processes)


def _signal_exit(signum: int, _frame: object) -> None:
    cleaned = _terminate_all_active()
    _emit(f"[efs-release] INTERRUPTED signal={signum} cleaned_process_groups={cleaned}")
    raise SystemExit(128 + signum)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _python_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] == sys.executable and (len(argv) < 2 or argv[1] != "-B"):
        return [argv[0], "-B", *argv[1:]]
    return argv


def _read_subject_hash(root: Path) -> str:
    argv = _python_argv(
        [
            sys.executable,
            "tools/verify_formal_runtime.py",
            "--print-subject-sha256",
        ]
    )
    process = subprocess.Popen(
        argv,
        cwd=root,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    _register_process(process)
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired as exc:
        _terminate_process(process)
        raise RuntimeError("subject hash command timed out after 30 seconds") from exc
    finally:
        _unregister_process(process)

    value = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError(f"unable to compute subject hash: {error[-1000:]}")
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("subject hash command returned invalid SHA-256")
    return value


def _copy_workspace(source: Path, destination: Path, *, expected_subject_sha256: str) -> None:
    for path in source.rglob("*"):
        if ".git" in path.relative_to(source).parts:
            continue
        if path.is_symlink():
            raise RuntimeError(f"source workspace contains symlink: {path.relative_to(source)}")

    def ignore(_directory: str, names: list[str]) -> set[str]:
        result = {name for name in names if name in WORKSPACE_IGNORES}
        result.update(
            name
            for name in names
            if name.endswith((".pyc", ".pyo", ".tmp", ".swp"))
        )
        return result

    shutil.copytree(source, destination, ignore=ignore)
    actual = _read_subject_hash(destination)
    if actual != expected_subject_sha256:
        raise RuntimeError(
            f"component workspace subject mismatch: expected {expected_subject_sha256}, got {actual}"
        )


def _file_summary(path: Path, *, tail_bytes: int = 1500) -> tuple[str, str]:
    if not path.is_file():
        return hashlib.sha256(b"").hexdigest(), ""
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), raw[-tail_bytes:].decode("utf-8", errors="replace")


def _row(
    *,
    name: str,
    argv: list[str],
    returncode: int | None,
    stdout_path: Path,
    stderr_path: Path,
    elapsed_seconds: float,
    timed_out: bool = False,
    reason: str | None = None,
) -> dict[str, object]:
    stdout_sha256, stdout_tail = _file_summary(stdout_path)
    stderr_sha256, stderr_tail = _file_summary(stderr_path)
    status = "PASS" if returncode == 0 and not timed_out else "FAIL"
    return {
        "name": name,
        "argv": argv,
        "returncode": returncode,
        "status": status,
        "timed_out": timed_out,
        "reason": reason,
        "elapsed_seconds": format(elapsed_seconds, ".3f"),
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def run_once(name: str, argv: list[str], *, timeout: int, work_dir: Path) -> dict[str, object]:
    argv = _python_argv(argv)
    stdout_path = work_dir / f"{name}.stdout"
    stderr_path = work_dir / f"{name}.stderr"
    started = time.monotonic()
    _emit(f"[efs-release] START {name}")
    process: subprocess.Popen[bytes] | None = None
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                argv,
                cwd=ROOT,
                env=_env(),
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=(os.name == "posix"),
            )
            _register_process(process)
            returncode = process.wait(timeout=timeout)
            _terminate_process(process)
        result = _row(
            name=name,
            argv=argv,
            returncode=returncode,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired:
        if process is not None:
            _terminate_process(process)
        result = _row(
            name=name,
            argv=argv,
            returncode=None,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            elapsed_seconds=time.monotonic() - started,
            timed_out=True,
            reason=f"TIMEOUT_{timeout}_SECONDS",
        )
    finally:
        if process is not None:
            _unregister_process(process)
    _emit(f"[efs-release] {result['status']} {name} elapsed={result['elapsed_seconds']}s")
    return result


@dataclass
class RunningComponent:
    name: str
    argv: list[str]
    process: subprocess.Popen[bytes]
    stdout_path: Path
    stderr_path: Path
    stdout_handle: object
    stderr_handle: object
    started: float


def _terminate(component: RunningComponent) -> None:
    _terminate_process(component.process)


def _close(component: RunningComponent) -> None:
    component.stdout_handle.close()  # type: ignore[union-attr]
    component.stderr_handle.close()  # type: ignore[union-attr]


def run_components_parallel(
    *,
    component_dir: Path,
    determinism_iterations: int,
    fuzz_cases: int,
    component_timeout: int,
    global_timeout: int,
    expected_subject_sha256: str,
) -> list[dict[str, object]]:
    running: dict[str, RunningComponent] = {}
    rows: list[dict[str, object]] = []
    global_started = time.monotonic()
    last_heartbeat = global_started
    workspace_root = component_dir / "workspaces"
    workspace_root.mkdir()
    component_workspaces: dict[str, Path] = {}
    for component in COMPONENTS:
        workspace = workspace_root / component
        _copy_workspace(ROOT, workspace, expected_subject_sha256=expected_subject_sha256)
        component_workspaces[component] = workspace

    for component in COMPONENTS:
        workspace = component_workspaces[component]
        stdout_path = component_dir / f"{component}.stdout"
        stderr_path = component_dir / f"{component}.stderr"
        stdout_handle = stdout_path.open("wb")
        stderr_handle = stderr_path.open("wb")
        argv = _python_argv(
            [
                sys.executable,
                "tools/verify_formal_runtime.py",
                "--component",
                component,
                "--determinism-iterations",
                str(determinism_iterations),
                "--fuzz-cases",
                str(fuzz_cases),
                "--expected-subject-sha256",
                expected_subject_sha256,
                "--output",
                str(component_dir / f"{component}.json"),
            ]
        )
        _emit(f"[efs-release] START component:{component}")
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=_env(),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=(os.name == "posix"),
        )
        _register_process(process)
        running[component] = RunningComponent(
            name=component,
            argv=argv,
            process=process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
            started=time.monotonic(),
        )

    try:
        while running:
            now = time.monotonic()
            global_elapsed = now - global_started
            if global_elapsed > global_timeout:
                for component in list(running.values()):
                    _terminate(component)
                    _close(component)
                    rows.append(
                        _row(
                            name=f"component:{component.name}",
                            argv=component.argv,
                            returncode=component.process.returncode,
                            stdout_path=component.stdout_path,
                            stderr_path=component.stderr_path,
                            elapsed_seconds=now - component.started,
                            timed_out=True,
                            reason=f"GLOBAL_TIMEOUT_{global_timeout}_SECONDS",
                        )
                    )
                    del running[component.name]
                break

            if now - last_heartbeat >= 5.0:
                active = ",".join(sorted(running))
                _emit(f"[efs-release] PROGRESS elapsed={global_elapsed:.1f}s active={active}")
                last_heartbeat = now

            for name, component in list(running.items()):
                returncode = component.process.poll()
                elapsed = now - component.started
                if returncode is not None:
                    _terminate(component)
                    _close(component)
                    row = _row(
                        name=f"component:{name}",
                        argv=component.argv,
                        returncode=returncode,
                        stdout_path=component.stdout_path,
                        stderr_path=component.stderr_path,
                        elapsed_seconds=elapsed,
                    )
                    rows.append(row)
                    del running[name]
                    _emit(f"[efs-release] {row['status']} component:{name} elapsed={row['elapsed_seconds']}s")
                elif elapsed > component_timeout:
                    _terminate(component)
                    _close(component)
                    row = _row(
                        name=f"component:{name}",
                        argv=component.argv,
                        returncode=component.process.returncode,
                        stdout_path=component.stdout_path,
                        stderr_path=component.stderr_path,
                        elapsed_seconds=elapsed,
                        timed_out=True,
                        reason=f"COMPONENT_TIMEOUT_{component_timeout}_SECONDS",
                    )
                    rows.append(row)
                    del running[name]
                    _emit(f"[efs-release] FAIL component:{name} timeout={component_timeout}s")
            if running:
                time.sleep(0.2)
    except BaseException:
        for component in list(running.values()):
            _terminate(component)
            _close(component)
        raise

    order = {f"component:{name}": index for index, name in enumerate(COMPONENTS)}
    rows.sort(key=lambda item: order.get(str(item["name"]), len(order)))
    return rows


def aggregate_components_in_process(
    component_dir: Path,
    *,
    expected_subject_sha256: str,
    work_dir: Path,
) -> tuple[dict[str, object], dict[str, object] | None]:
    stdout_path = work_dir / "aggregate.stdout"
    stderr_path = work_dir / "aggregate.stderr"
    started = time.monotonic()
    _emit("[efs-release] START aggregate")
    try:
        spec = importlib.util.spec_from_file_location(
            "efs_release_aggregate_verifier", ROOT / "tools" / "verify_formal_runtime.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load formal runtime aggregate verifier")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        aggregate = module._aggregate(
            component_dir,
            expected_subject_sha256=expected_subject_sha256,
        )
        stdout_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        stderr_path.write_text("", encoding="utf-8")
        row = _row(
            name="aggregate",
            argv=["IN_PROCESS_PURE_AGGREGATE"],
            returncode=0 if aggregate.get("status") == "PASS" else 1,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            elapsed_seconds=time.monotonic() - started,
        )
        _emit(f"[efs-release] {row['status']} aggregate elapsed={row['elapsed_seconds']}s")
        return row, aggregate
    except Exception as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        row = _row(
            name="aggregate",
            argv=["IN_PROCESS_PURE_AGGREGATE"],
            returncode=1,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            elapsed_seconds=time.monotonic() - started,
            reason="AGGREGATE_EXCEPTION",
        )
        _emit(f"[efs-release] FAIL aggregate elapsed={row['elapsed_seconds']}s")
        return row, None


def _finalize_report(report: dict[str, object], output: Path | None) -> None:
    body = dict(report)
    body.pop("report_sha256", None)
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        display: dict[str, object] = {
            "schema": "efs.release_oracles.operator_summary.v1",
            "status": report.get("status"),
            "report_sha256": report.get("report_sha256"),
            "formal_runtime_subject_sha256": report.get("formal_runtime_subject_sha256"),
            "failed_rows": report.get("failed_rows"),
            "output": str(output),
        }
        display_text = json.dumps(display, ensure_ascii=False, sort_keys=True) + "\n"
    else:
        display_text = text
    try:
        print(display_text, end="")
    except BrokenPipeError:
        pass


def main() -> int:
    old_handlers: dict[int, object] = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[int(sig)] = signal.signal(sig, _signal_exit)

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--determinism-iterations", type=int, default=10_000)
    parser.add_argument("--fuzz-cases", type=int, default=10_000)
    parser.add_argument("--precheck-timeout", type=int, default=60)
    parser.add_argument("--component-timeout", type=int, default=270)
    parser.add_argument("--global-timeout", type=int, default=285)
    args = parser.parse_args()
    if args.determinism_iterations < 10_000:
        parser.error("determinism iterations must be at least 10000")
    if args.fuzz_cases < 10_000 or args.fuzz_cases > 100_000:
        parser.error("fuzz cases must be between 10000 and 100000")
    if args.component_timeout <= 0 or args.global_timeout <= 0 or args.precheck_timeout <= 0:
        parser.error("timeouts must be positive")
    if args.component_timeout > args.global_timeout:
        parser.error("component timeout cannot exceed global timeout")

    report: dict[str, object] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="efs-release-oracles-") as tmp:
            work_dir = Path(tmp)
            expected_subject_sha256 = _read_subject_hash(ROOT)
            rows = [
                run_once(
                    "self_check",
                    [sys.executable, "-m", "equity_foresight_signal", "self-check"],
                    timeout=args.precheck_timeout,
                    work_dir=work_dir,
                ),
                run_once(
                    "golden_evaluate",
                    [sys.executable, "-m", "equity_foresight_signal", "evaluate", "fixtures/request.json", "fixtures/bundle.json"],
                    timeout=args.precheck_timeout,
                    work_dir=work_dir,
                ),
            ]
            component_dir = work_dir / "components"
            component_dir.mkdir()
            rows.extend(
                run_components_parallel(
                    component_dir=component_dir,
                    determinism_iterations=args.determinism_iterations,
                    fuzz_cases=args.fuzz_cases,
                    component_timeout=args.component_timeout,
                    global_timeout=args.global_timeout,
                    expected_subject_sha256=expected_subject_sha256,
                )
            )

            integrity_stdout = work_dir / "source_integrity.stdout"
            integrity_stderr = work_dir / "source_integrity.stderr"
            current_subject_sha256 = _read_subject_hash(ROOT)
            integrity_stdout.write_text(
                json.dumps(
                    {
                        "expected_subject_sha256": expected_subject_sha256,
                        "actual_subject_sha256": current_subject_sha256,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            integrity_stderr.write_text("", encoding="utf-8")
            rows.append(
                _row(
                    name="source_integrity",
                    argv=["INTERNAL_SUBJECT_HASH_COMPARISON"],
                    returncode=0 if current_subject_sha256 == expected_subject_sha256 else 1,
                    stdout_path=integrity_stdout,
                    stderr_path=integrity_stderr,
                    elapsed_seconds=0.0,
                    reason=(
                        None
                        if current_subject_sha256 == expected_subject_sha256
                        else "CANONICAL_SOURCE_CHANGED_DURING_RELEASE_ORACLES"
                    ),
                )
            )

            component_failures = [row for row in rows if row["status"] != "PASS"]
            aggregate: dict[str, object] | None = None
            if not component_failures and all((component_dir / f"{name}.json").is_file() for name in COMPONENTS):
                aggregate_row, aggregate = aggregate_components_in_process(
                    component_dir,
                    expected_subject_sha256=expected_subject_sha256,
                    work_dir=work_dir,
                )
                rows.append(aggregate_row)

            failures = [index for index, row in enumerate(rows, 1) if row["status"] != "PASS"]
            if not isinstance(aggregate, dict) or aggregate.get("status") != "PASS":
                failures.append(len(rows) + 1)
            report = {
                "schema": "efs.release_oracles.v4",
                "status": "PASS" if not failures else "FAIL",
                "failed_rows": sorted(set(failures)),
                "rows": rows,
                "formal_runtime_report_sha256": aggregate.get("report_sha256") if isinstance(aggregate, dict) else None,
                "formal_runtime_subject_sha256": aggregate.get("subject_sha256") if isinstance(aggregate, dict) else None,
                "expected_subject_sha256": expected_subject_sha256,
                "determinism_iterations": args.determinism_iterations,
                "fuzz_cases": args.fuzz_cases,
                "component_timeout_seconds": args.component_timeout,
                "global_timeout_seconds": args.global_timeout,
                "capability_ceiling": "SHADOW_ONLY",
                "outcome_status": "NOT_PROVEN",
                "claim_boundary": "SHADOW_ONLY_ENGINEERING_NOT_OUTCOME_PROOF_NOT_EXTERNAL_INDEPENDENT_REVIEW",
            }
            _finalize_report(report, args.output)
            return 0 if not failures else 1
    except Exception as exc:
        report = {
            "schema": "efs.release_oracles.v4",
            "status": "FAIL",
            "failed_rows": [0],
            "rows": [],
            "formal_runtime_report_sha256": None,
            "formal_runtime_subject_sha256": None,
            "expected_subject_sha256": None,
            "determinism_iterations": args.determinism_iterations,
            "fuzz_cases": args.fuzz_cases,
            "component_timeout_seconds": args.component_timeout,
            "global_timeout_seconds": args.global_timeout,
            "capability_ceiling": "SHADOW_ONLY",
            "outcome_status": "NOT_PROVEN",
            "claim_boundary": "SHADOW_ONLY_ENGINEERING_NOT_OUTCOME_PROOF_NOT_EXTERNAL_INDEPENDENT_REVIEW",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        _finalize_report(report, args.output)
        return 1
    finally:
        _terminate_all_active()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
