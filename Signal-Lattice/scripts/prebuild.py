#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def normalize_for_package(value: Any, root: Path, temp: Path) -> Any:
    if isinstance(value, dict):
        return {key: normalize_for_package(item, root, temp) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_for_package(item, root, temp) for item in value]
    if isinstance(value, str):
        return value.replace(str(root), "{ROOT}").replace(str(temp), "{TEMP}").replace(os.sys.executable, "python3")
    return value


def run_check(
    name: str, command: list[str], root: Path, timeout: int,
    accepted_codes: set[int] | None = None, extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    accepted = accepted_codes or {0}
    started = time.monotonic()
    print(json.dumps({"event": "check_started", "name": name, "command": shlex.join(command)}, ensure_ascii=False), flush=True)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"}}
    env.update({"PYTHONPATH": str(root / "src"), "PYTHONHASHSEED": "0", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
    if extra_env:
        env.update(extra_env)
    try:
        completed = subprocess.run(command, cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        code = completed.returncode
        state = "PASS" if code in accepted else "FAIL"
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        code = 124
        state = "FAIL"
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nTIMEOUT"
    duration = round(time.monotonic() - started, 3)
    result = {
        "name": name,
        "state": state,
        "command": command,
        "returncode": code,
        "accepted_returncodes": sorted(accepted),
        "duration_seconds": duration,
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
        "stdout_tail": stdout[-1200:],
        "stderr_tail": stderr[-1200:],
    }
    print(json.dumps({"event": "check_finished", "name": name, "state": state, "returncode": code, "duration_seconds": duration}, ensure_ascii=False), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("/tmp/signal-lattice-prebuild-receipt.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output

    # Clean only known transient artifacts before validation.
    subprocess.run([os.sys.executable, "scripts/clean_transients.py", "--root", str(root)], cwd=root, check=True)
    with tempfile.TemporaryDirectory(prefix="signal-lattice-prebuild-") as tmp:
        temp = Path(tmp)
        wheel_dir = temp / "wheel"
        install_root = temp / "install"
        state_dir = temp / "state"
        artifacts = temp / "artifacts"
        checks: list[tuple[str, list[str], int, set[int] | None]] = [
            ("unit_tests", ["bash", "scripts/run_tests.sh"], 240, None),
            ("canonical_state", [os.sys.executable, "scripts/verify_canonical_state.py", "--state", str(root / "CANONICAL_STATE.json")], 30, None),
            ("version_lock", [os.sys.executable, "scripts/verify_version_lock.py", "--root", str(root)], 30, None),
            ("dual_plane", [os.sys.executable, "machine/tools/check_dual_plane_ci.py", "--root", str(root), "--projects", "."], 30, None),
            ("upstream_precheck", [os.sys.executable, "scripts/build_upstream_precheck.py", "--root", str(root), "--output", str(root / "evidence/upstream/upstream_precheck.json")], 30, {0, 2}),
            ("quant_seal", [os.sys.executable, "scripts/build_quant_seal.py", str(root / "evidence/quant/quant_seal.json")], 60, None),
            ("task_contract", [os.sys.executable, "scripts/run_task.py", "--validate-all"], 60, None),
            ("builder_readiness_static", [os.sys.executable, "scripts/builder_readiness_static.py", "--root", str(root), "--output", str(root / "evidence/builder_readiness/static_readiness.json")], 30, None),
            ("browser", [os.sys.executable, "scripts/browser_smoke.py", "--root", str(root), "--output", str(root / "evidence/browser/browser_smoke.json")], 90, None),
            ("systemd", [os.sys.executable, "scripts/verify_systemd.py", "--root", str(root), "--output", str(root / "evidence/systemd/systemd_verify.json")], 60, None),
            ("zero_runtime", [os.sys.executable, "scripts/verify_zero_runtime.py", "--root", str(root)], 30, None),
            ("walking_skeleton", [os.sys.executable, "scripts/walking_skeleton.py", "--receipt", str(root / "evidence/walking_skeleton.json")], 60, None),
            ("recovery", [os.sys.executable, "scripts/verify_recovery.py", "--output", str(root / "evidence/recovery/recovery.json")], 60, None),
            ("wheel", [os.sys.executable, "scripts/build_wheel.py", "--root", str(root), "--output-dir", str(wheel_dir), "--receipt", str(root / "evidence/release/wheel_receipt.json")], 240, None),
        ]
        results = [run_check(name, command, root, timeout, accepted) for name, command, timeout, accepted in checks]

        wheel_files = sorted(wheel_dir.glob("signal_lattice-*.whl"))
        if len(wheel_files) == 1:
            # install_release is hermetic itself; force an ephemeral install root so prebuild has no host side effect.
            results.append(run_check(
                "hermetic_install",
                ["bash", "scripts/install_release.sh", str(wheel_files[0])],
                root, 180, None,
                {"SIGNAL_LATTICE_INSTALL_ROOT": str(install_root)},
            ))
        else:
            results.append({"name": "hermetic_install", "state": "FAIL", "returncode": 2, "duration_seconds": 0.0, "stdout_tail": "", "stderr_tail": "WHEEL_NOT_AVAILABLE", "command": [], "accepted_returncodes": [0], "stdout_sha256": hashlib.sha256(b"").hexdigest(), "stderr_sha256": hashlib.sha256(b"WHEEL_NOT_AVAILABLE").hexdigest()})

    # Persist immutable pre-manifest check evidence inside the candidate. The final package/manifest
    # receipt is deliberately written outside the candidate to avoid self-referential manifest drift.
    pre_manifest = {
        "schema_version": "1.0.0",
        "state": "PASS" if all(row["state"] == "PASS" for row in results) else "FAIL",
        "checks": normalize_for_package(results, root, temp),
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
    }
    pre_manifest["receipt_sha256"] = hashlib.sha256(canonical(pre_manifest)).hexdigest()
    internal_receipt = root / "evidence/prebuild/pre_manifest_checks.json"
    internal_receipt.parent.mkdir(parents=True, exist_ok=True)
    internal_receipt.write_text(json.dumps(pre_manifest, ensure_ascii=False, indent=2, sort_keys=True))

    # Re-clean bytecode and other known transients created by checks, then build final manifest.
    subprocess.run([os.sys.executable, "scripts/clean_transients.py", "--root", str(root)], cwd=root, check=True)
    results.append(run_check("manifest", [os.sys.executable, "scripts/build_manifest.py", "--root", str(root), "--output", str(root / "MANIFEST.json")], root, 60, None))
    results.append(run_check("package_guard", [os.sys.executable, "scripts/verify_package.py", "--root", str(root), "--manifest", str(root / "MANIFEST.json")], root, 120, None))

    failures = [row["name"] for row in results if row["state"] != "PASS"]
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": "PASS" if not failures else "FAIL",
        "candidate_version": json.loads((root / "machine/facts/project.json").read_text())["product_version"],
        "check_count": len(results),
        "failure_count": len(failures),
        "failures": failures,
        "checks": results,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "automatic_trading": False,
        "formal_upstream_seal_required": not (root / "evidence/upstream/upstream_seal.json").is_file(),
        "formal_independent_review_required": True,
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps({"state": receipt["state"], "check_count": len(results), "receipt_sha256": receipt["receipt_sha256"]}, ensure_ascii=False))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
