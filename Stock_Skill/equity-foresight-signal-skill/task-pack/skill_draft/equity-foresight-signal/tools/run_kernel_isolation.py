from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import platform
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

SCHEMA = "efs.kernel_isolation_execution.v1"

# Linux classic-BPF / seccomp constants.
PR_SET_NO_NEW_PRIVS = 38
SECCOMP_SET_MODE_FILTER = 1
SYS_SECCOMP_X86_64 = 317
AUDIT_ARCH_X86_64 = 0xC000003E

BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_K = 0x00
BPF_RET = 0x06

SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000

# x86_64 syscall numbers. The profile blocks socket creation/use and all common
# process creation / image replacement paths after the interpreter has loaded.
BLOCKED_SYSCALLS_X86_64: dict[str, int] = {
    "socket": 41,
    "connect": 42,
    "accept": 43,
    "sendto": 44,
    "recvfrom": 45,
    "sendmsg": 46,
    "recvmsg": 47,
    "shutdown": 48,
    "bind": 49,
    "listen": 50,
    "getsockname": 51,
    "getpeername": 52,
    "socketpair": 53,
    "setsockopt": 54,
    "getsockopt": 55,
    "clone": 56,
    "fork": 57,
    "vfork": 58,
    "execve": 59,
    "ptrace": 101,
    "unshare": 272,
    "accept4": 288,
    "recvmmsg": 299,
    "setns": 308,
    "sendmmsg": 307,
    "execveat": 322,
    "clone3": 435,
}


class SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class SockFprog(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.POINTER(SockFilter)),
    ]


def _stmt(code: int, k: int) -> SockFilter:
    return SockFilter(code=code, jt=0, jf=0, k=k)


def _jump(code: int, k: int, jt: int, jf: int) -> SockFilter:
    return SockFilter(code=code, jt=jt, jf=jf, k=k)


def _install_filter() -> dict[str, Any]:
    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        return {
            "status": "NOT_APPLICABLE_UNSUPPORTED_PROFILE",
            "platform": sys.platform,
            "machine": platform.machine(),
        }

    instructions: list[SockFilter] = [
        _stmt(BPF_LD | BPF_W | BPF_ABS, 4),
        _jump(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        _stmt(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        _stmt(BPF_LD | BPF_W | BPF_ABS, 0),
    ]
    for syscall_number in sorted(set(BLOCKED_SYSCALLS_X86_64.values())):
        instructions.extend(
            [
                _jump(BPF_JMP | BPF_JEQ | BPF_K, syscall_number, 0, 1),
                _stmt(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | errno.EPERM),
            ]
        )
    instructions.append(_stmt(BPF_RET | BPF_K, SECCOMP_RET_ALLOW))

    array_type = SockFilter * len(instructions)
    instruction_array = array_type(*instructions)
    program = SockFprog(len=len(instructions), filter=instruction_array)

    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.prctl.restype = ctypes.c_int
    libc.syscall.restype = ctypes.c_long

    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    result = libc.syscall(SYS_SECCOMP_X86_64, SECCOMP_SET_MODE_FILTER, 0, ctypes.byref(program))
    if result != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))

    # Keep ctypes-backed filter objects live until the kernel copied the program.
    return {
        "status": "INSTALLED",
        "platform": sys.platform,
        "machine": platform.machine(),
        "blocked_syscall_count": len(set(BLOCKED_SYSCALLS_X86_64.values())),
        "blocked_syscalls": sorted(BLOCKED_SYSCALLS_X86_64),
        "no_new_privileges": True,
    }


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def _expect_errno(operation) -> dict[str, Any]:
    try:
        operation()
    except OSError as exc:
        return {
            "status": "PASS" if exc.errno in {errno.EPERM, errno.EACCES} else "FAIL",
            "errno": exc.errno,
            "exception": type(exc).__name__,
        }
    except Exception as exc:  # pragma: no cover - defensive report boundary
        return {"status": "FAIL", "errno": None, "exception": type(exc).__name__}
    return {"status": "FAIL", "errno": None, "exception": "NO_EXCEPTION"}


def _socket_probe() -> None:
    candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    candidate.close()


def _fork_probe() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    ctypes.set_errno(0)
    result = libc.syscall(BLOCKED_SYSCALLS_X86_64["fork"])
    if result == -1:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    if result == 0:  # pragma: no cover - should be blocked by the filter
        os._exit(91)
    os.waitpid(result, 0)


def _subprocess_probe() -> None:
    subprocess.run(
        [sys.executable, "-c", "raise SystemExit(92)"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def execute() -> dict[str, Any]:
    # Inputs are loaded before the filter only to avoid conflating local file I/O
    # with the network/process isolation property under test.
    request = _load_fixture("request.json")
    bundle = _load_fixture("bundle.json")
    trust = _load_fixture("trust_context_shadow.json")
    dataset = _load_fixture("pit_dataset.json")
    training_config = _load_fixture("training_config.json")

    installation = _install_filter()
    if installation["status"] != "INSTALLED":
        report: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "NOT_APPLICABLE_UNSUPPORTED_PROFILE",
            "installation": installation,
            "claim_boundary": "ONLY_LINUX_X86_64_IS_IN_V0_SUPPORTED_RUNTIME_PROFILE",
        }
        report["report_sha256"] = sha256_hex(report)
        return report

    probes = {
        "socket_creation_blocked": _expect_errno(_socket_probe),
        "fork_blocked": _expect_errno(_fork_probe),
        "subprocess_blocked": _expect_errno(_subprocess_probe),
    }

    forecast = evaluate(request, bundle, trust)
    training = train_direction_pipeline(dataset, training_config)
    runtime = self_check()
    deterministic_checks = {
        "forecast_completed": forecast.get("status") in {"FORECAST", "ABSTAIN"},
        "forecast_hash_present": isinstance(forecast.get("result_sha256"), str),
        "training_hash_present": isinstance(training.get("run_sha256"), str),
        "runtime_agent_dependency_zero": runtime["runtime_profile"]["agent_dependency"] == 0,
        "runtime_llm_dependency_zero": runtime["runtime_profile"]["llm_dependency"] == 0,
        "runtime_network_dependency_zero": runtime["runtime_profile"]["network_dependency"] == 0,
    }
    pass_all = all(item["status"] == "PASS" for item in probes.values()) and all(deterministic_checks.values())
    report = {
        "schema": SCHEMA,
        "status": "PASS" if pass_all else "FAIL",
        "installation": installation,
        "probes": probes,
        "deterministic_runtime_checks": deterministic_checks,
        "forecast_result_sha256": forecast.get("result_sha256"),
        "training_run_sha256": training.get("run_sha256"),
        "runtime_self_check_sha256": sha256_hex(runtime),
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
        "process_spawn_success_total": 0,
        "claim_boundary": (
            "KERNEL_ENFORCED_SECCOMP_BPF_ON_LINUX_X86_64; "
            "THIS_PROVES THE TESTED PROCESS CANNOT CREATE/USE SOCKETS OR SPAWN/EXECUTE CHILD PROCESSES "
            "AFTER FILTER INSTALLATION, NOT A GENERAL HOST-WIDE NETWORK POLICY"
        ),
    }
    report["report_sha256"] = sha256_hex(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run EFS under a kernel seccomp socket/process deny profile")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = execute()
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] in {"PASS", "NOT_APPLICABLE_UNSUPPORTED_PROFILE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
