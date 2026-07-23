#!/usr/bin/env python3
"""Execute the closed RMD-05 local gate matrix in a clean detached candidate checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

BASELINE_COMMIT = "2b8625a83e69093b9dce989f4eb964556e1b5fa2"
GOVERNANCE_COMMIT = (
    "ebc6c2e4884edc959118cfc56d0e18a86c49460f"  # pragma: allowlist secret  # noqa: E501
)
PROJECT_RELATIVE = Path("LinzeDatabase/MooMooAU")
LOCK_SHA256 = "bed62218c229318cb95575b7880bc5ed78558d6014e299582f62d32ba0a05eb7"  # pragma: allowlist secret  # noqa: E501
SENSITIVE_OUTPUT = (
    re.compile(r"AGE-SECRET-KEY-1[0-9a-z]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"1//[A-Za-z0-9_-]{20,}"),
)
LOCAL_PATH_MARKERS = (
    "/Users/",
    "/home/",
    "/private/tmp/",
    "/var/folders/",
    "C:\\Users\\",
)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    command_id: str
    argv: tuple[str, ...]
    tools: tuple[str, ...]
    result_summary: str


class CaptureError(RuntimeError):
    """The candidate or one local assurance command failed closed."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run_text(argv: list[str], cwd: Path) -> tuple[int, str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def _git(root: Path, *args: str) -> str:
    returncode, output = _run_text(["git", "-C", str(root), *args], root)
    if returncode != 0:
        raise CaptureError(f"git {' '.join(args)} failed")
    return output


def _version(argv: list[str], cwd: Path) -> str:
    returncode, output = _run_text(argv, cwd)
    if returncode != 0 or not output:
        raise CaptureError(f"tool version command failed: {' '.join(argv)}")
    return output.splitlines()[0][:200]


def _normalize(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for original, replacement in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if original:
            normalized = normalized.replace(original, replacement)
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _logical_argv(
    argv: tuple[str, ...],
    replacements: tuple[tuple[str, str], ...],
) -> list[str]:
    return [_normalize(value, replacements).removesuffix("\n") for value in argv]


def _sanitized_tool_versions(
    versions: dict[str, str],
    names: tuple[str, ...],
    replacements: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    sanitized = {
        name: _normalize(versions[name], replacements).removesuffix("\n") for name in names
    }
    if any(marker in "\n".join(sanitized.values()) for marker in LOCAL_PATH_MARKERS):
        raise CaptureError("local path remains in tool versions after sanitization")
    if any(pattern.search("\n".join(sanitized.values())) for pattern in SENSITIVE_OUTPUT):
        raise CaptureError("sensitive output pattern observed in tool versions")
    return sanitized


def _command_specs(
    python: Path,
    governance: Path,
    temp: Path,
    image: str,
) -> tuple[CommandSpec, ...]:
    python_text = str(python)
    ruff_scope = (
        "src",
        "tests/stage6_support.py",
        "tests/stage7_support.py",
        "tests/tasks/test_t0601.py",
        "tests/tasks/test_t0602.py",
        "tests/tasks/test_t0603.py",
        "tests/tasks/test_t0604.py",
        "tests/tasks/test_t0605.py",
        "tests/tasks/test_t0606.py",
        "tests/tasks/test_t0607.py",
        "tests/tasks/test_t0608.py",
        "tests/tasks/test_t0702.py",
        "tests/tasks/test_t0703.py",
        "tests/tasks/test_t0704.py",
        "tests/tasks/test_t0705.py",
        "tests/remediation",
        "machine/stages/S6/tools",
        "machine/tools/validate_assurance_reviews.py",
        "machine/tools/build_delivery_status.py",
        "machine/tools/build_governance_facts.py",
        "machine/tools/build_package_manifest.py",
        "machine/tools/capture_candidate_gates.py",
        "machine/tools/validate_delivery_status.py",
        "machine/tools/validate_evidence.py",
        "machine/tools/validate_package.py",
        "machine/tools/validate_stage6_sbom_reproducibility.py",
        "machine/tools/validate_stage6_secret_scan.py",
    )
    mypy_scope = (
        "src",
        "tests/stage7_support.py",
        "tests/tasks/test_t0606.py",
        "tests/tasks/test_t0607.py",
        "tests/remediation/test_rmd05.py",
        "machine/stages/S6/tools",
        "machine/tools/validate_assurance_reviews.py",
        "machine/tools/build_delivery_status.py",
        "machine/tools/build_governance_facts.py",
        "machine/tools/build_package_manifest.py",
        "machine/tools/capture_candidate_gates.py",
        "machine/tools/validate_delivery_status.py",
        "machine/tools/validate_evidence.py",
        "machine/tools/validate_package.py",
        "machine/tools/validate_stage6_sbom_reproducibility.py",
        "machine/tools/validate_stage6_secret_scan.py",
    )
    return (
        CommandSpec(
            "ruff-format",
            (python_text, "-m", "ruff", "format", "--check", *ruff_scope),
            ("python", "ruff"),
            "All RMD-05 scoped Python files are format-stable.",
        ),
        CommandSpec(
            "ruff-lint",
            (python_text, "-m", "ruff", "check", "--no-cache", *ruff_scope),
            ("python", "ruff"),
            "All RMD-05 scoped Python files pass lint.",
        ),
        CommandSpec(
            "mypy-strict",
            (
                python_text,
                "-m",
                "mypy",
                "--no-incremental",
                "--cache-dir",
                str(temp / "mypy-cache"),
                *mypy_scope,
            ),
            ("python", "mypy"),
            "Strict typing passes for runtime and RMD-05 assurance code.",
        ),
        CommandSpec(
            "stage6-task-tests",
            (
                python_text,
                "-m",
                "pytest",
                "-q",
                "tests/tasks/test_t0601.py",
                "tests/tasks/test_t0602.py",
                "tests/tasks/test_t0603.py",
                "tests/tasks/test_t0604.py",
                "tests/tasks/test_t0605.py",
                "tests/tasks/test_t0606.py",
                "tests/tasks/test_t0607.py",
                "tests/tasks/test_t0608.py",
            ),
            ("python", "pytest"),
            "All Stage 6 task tests pass on the candidate.",
        ),
        CommandSpec(
            "stage7-runtime-regression-tests",
            (
                python_text,
                "-m",
                "pytest",
                "-q",
                "tests/tasks/test_t0702.py",
                "tests/tasks/test_t0703.py",
                "tests/tasks/test_t0704.py",
                "tests/tasks/test_t0705.py",
            ),
            ("python", "pytest"),
            "Affected Stage 7 runtime composition tests pass on the candidate.",
        ),
        CommandSpec(
            "remediation-tests",
            (python_text, "-m", "pytest", "-q", "tests/remediation/test_rmd05.py"),
            ("python", "pytest"),
            "RMD-05 provenance and post-review transition regressions pass.",
        ),
        CommandSpec(
            "assurance-history",
            (python_text, "machine/tools/validate_assurance_reviews.py", "--history-only"),
            ("python", "git"),
            (
                "The exact seventeen-attempt superseded review history is integral "
                "and honestly blocked."
            ),
        ),
        CommandSpec(
            "stage6-validation",
            (
                python_text,
                "machine/stages/S6/tools/validate_stage6.py",
                "--governance-root",
                str(governance),
                "--cumulative-final",
                "--review-input",
            ),
            ("python", "git"),
            "Stage 6 validates in the fail-closed pre-final state.",
        ),
        CommandSpec(
            "delivery-status-validation",
            (python_text, "machine/tools/validate_delivery_status.py"),
            ("python", "git"),
            "The deterministic delivery status remains the exact PRE_CLOSURE state.",
        ),
        CommandSpec(
            "governance-facts-check",
            (python_text, "machine/tools/build_governance_facts.py", "--check"),
            ("python",),
            "Derived governance facts match the honest PRE_CLOSURE delivery status.",
        ),
        CommandSpec(
            "dependency-audit",
            (
                python_text,
                "-m",
                "pip_audit",
                "-r",
                "requirements/stage6.lock",
                "--require-hashes",
                "--progress-spinner=off",
            ),
            ("python", "pip-audit"),
            "The hash-locked Stage 6 dependency audit reports no known vulnerability.",
        ),
        CommandSpec(
            "sbom-reproducibility",
            (python_text, "machine/tools/validate_stage6_sbom_reproducibility.py"),
            ("python", "cyclonedx-py"),
            "The regenerated sanitized SBOM is byte-identical.",
        ),
        CommandSpec(
            "secret-scan",
            (python_text, "machine/tools/validate_stage6_secret_scan.py"),
            ("python", "detect-secrets"),
            "The scoped Stage 6 secret scan reports zero findings.",
        ),
        CommandSpec(
            "publication-scan",
            (python_text, "machine/tools/validate_publication.py", "--root", "."),
            ("python",),
            "The publishable project tree has zero forbidden-value findings.",
        ),
        CommandSpec(
            "governance-validation",
            (
                python_text,
                "machine/tools/validate_governance.py",
                "--governance-root",
                str(governance),
            ),
            ("python", "git"),
            "Pinned Governance renders and validates without changing the candidate tree.",
        ),
        CommandSpec(
            "container-build",
            (
                "docker",
                "build",
                "--no-cache",
                "--tag",
                image,
                "--file",
                "container/Dockerfile.stage6-ci",
                ".",
            ),
            ("docker",),
            "The digest-pinned Stage 6 validation container builds locally.",
        ),
        CommandSpec(
            "container-smoke",
            (
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp",
                image,
                "--help",
            ),
            ("docker",),
            "The validation container passes network-none read-only smoke.",
        ),
        CommandSpec(
            "container-cleanup",
            ("docker", "image", "rm", "--force", image),
            ("docker",),
            "The ephemeral local validation image is removed.",
        ),
        CommandSpec(
            "package-build",
            (
                python_text,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(temp / "dist"),
            ),
            ("python", "build"),
            "The Python package builds into an ephemeral directory without publication.",
        ),
    )


def capture(
    repository: Path,
    governance: Path,
    python: Path,
    candidate: str,
    output: Path,
) -> dict[str, Any]:
    repository = repository.resolve()
    governance = governance.resolve()
    # Preserve a virtual-environment launcher path: resolving its symlink would bypass the
    # hash-locked environment and invoke the dependency-free base interpreter.
    python = python.absolute()
    output = output.resolve()
    project = repository / PROJECT_RELATIVE
    if (
        not project.is_dir()
        or not python.is_file()
        or _git(repository, "rev-parse", "HEAD") != candidate
        or _git(repository, "status", "--porcelain")
    ):
        raise CaptureError("candidate checkout is absent, dirty or at another commit")
    candidate_tree = _git(repository, "rev-parse", f"{candidate}^{{tree}}")
    if _git(repository, "merge-base", "--is-ancestor", BASELINE_COMMIT, candidate):
        raise CaptureError("candidate baseline ancestry command emitted unexpected output")
    if _git(governance, "rev-parse", "HEAD") != GOVERNANCE_COMMIT:
        raise CaptureError("Governance checkout differs from the frozen pin")
    if _sha256(project / "requirements/stage6.lock") != LOCK_SHA256:
        raise CaptureError("Stage 6 dependency lock differs")
    python_version = _version([str(python), "--version"], project).removeprefix("Python ")
    if not re.fullmatch(r"3\.12\.[0-9]+", python_version):
        raise CaptureError("locked candidate interpreter is not Python 3.12")

    versions = {
        "python": python_version,
        "ruff": _version([str(python), "-m", "ruff", "--version"], project),
        "mypy": _version([str(python), "-m", "mypy", "--version"], project),
        "pytest": _version([str(python), "-m", "pytest", "--version"], project),
        "pip-audit": _version([str(python), "-m", "pip_audit", "--version"], project),
        "cyclonedx-py": _version([str(python.parent / "cyclonedx-py"), "--version"], project),
        "detect-secrets": _version([str(python.parent / "detect-secrets"), "--version"], project),
        "docker": _version(["docker", "--version"], project),
        "build": _version([str(python), "-m", "build", "--version"], project),
        "git": _version(["git", "--version"], project),
    }

    receipt: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="moomooau-rmd05-candidate-") as temporary:
        temp = Path(temporary)
        image = f"moomooau-stage6-rmd05-{candidate[:12]}"
        replacements = (
            (str(project), "${PROJECT_ROOT}"),
            (str(repository), "${REPOSITORY_ROOT}"),
            (str(governance), "${GOVERNANCE_ROOT}"),
            (str(python), "${LOCKED_PYTHON}"),
            (str(python.parent.parent), "${LOCKED_ENV}"),
            (str(temp), "${TMPDIR}"),
            (str(Path.home()), "${USER_HOME}"),
        )
        sanitized_versions = _sanitized_tool_versions(
            versions,
            tuple(versions),
            replacements,
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HYPOTHESIS_STORAGE_DIRECTORY": str(temp / "hypothesis"),
                "MOOMOOAU_GOVERNANCE_ROOT": str(governance),
                "PATH": f"{python.parent}{os.pathsep}{environment.get('PATH', '')}",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
            }
        )
        records: list[dict[str, Any]] = []
        image_built = False
        try:
            for spec in _command_specs(python, governance, temp, image):
                completed = subprocess.run(
                    list(spec.argv),
                    cwd=project,
                    env=environment,
                    check=False,
                    capture_output=True,
                )
                if spec.command_id == "container-build" and completed.returncode == 0:
                    image_built = True
                if spec.command_id == "container-cleanup" and completed.returncode == 0:
                    image_built = False
                raw_stdout = completed.stdout
                raw_stderr = completed.stderr
                stdout = _normalize(raw_stdout.decode("utf-8", errors="replace"), replacements)
                stderr = _normalize(raw_stderr.decode("utf-8", errors="replace"), replacements)
                if any(pattern.search(stdout + stderr) for pattern in SENSITIVE_OUTPUT):
                    raise CaptureError(f"sensitive output pattern observed in {spec.command_id}")
                record = {
                    "id": spec.command_id,
                    "working_directory": PROJECT_RELATIVE.as_posix(),
                    "argv": _logical_argv(spec.argv, replacements),
                    "tool_versions": _sanitized_tool_versions(
                        sanitized_versions,
                        spec.tools,
                        (),
                    ),
                    "exit_code": completed.returncode,
                    "raw_stdout_bytes": len(raw_stdout),
                    "raw_stderr_bytes": len(raw_stderr),
                    "raw_stdout_sha256": _sha256_bytes(raw_stdout),
                    "raw_stderr_sha256": _sha256_bytes(raw_stderr),
                    "sanitized_stdout": stdout,
                    "sanitized_stderr": stderr,
                    "sanitized_stdout_sha256": _sha256_bytes(stdout.encode()),
                    "sanitized_stderr_sha256": _sha256_bytes(stderr.encode()),
                    "result_summary": spec.result_summary,
                }
                records.append(record)
                if completed.returncode != 0:
                    raise CaptureError(f"candidate gate failed: {spec.command_id}")
        finally:
            if image_built:
                subprocess.run(
                    ["docker", "image", "rm", "--force", image],
                    cwd=project,
                    check=False,
                    capture_output=True,
                )
        if _git(repository, "status", "--porcelain", "--untracked-files=no"):
            raise CaptureError("candidate gate commands changed a tracked file")
        receipt = {
            "schema_version": "moomooau.candidate-execution-receipt.v1",
            "receipt_id": "S6-RMD05-CANDIDATE-GATES",
            "subject": {
                "repository": "MetaDatabase",
                "project_path": PROJECT_RELATIVE.as_posix(),
                "baseline_commit": BASELINE_COMMIT,
                "candidate_commit": candidate,
                "candidate_tree": candidate_tree,
                "clean_detached_checkout": True,
            },
            "scope": "LOCAL_SYNTHETIC_ONLY",
            "environment": {
                "platform": platform.platform(),
                "python": python_version,
                "dependency_lock_path": "requirements/stage6.lock",
                "dependency_lock_sha256": LOCK_SHA256,
                "governance_commit": GOVERNANCE_COMMIT,
                "python_executable_sha256": _sha256(python),
            },
            "commands": records,
            "raw_logs_retained": False,
            "sensitive_data_observed": False,
            "production_or_protected_executed": False,
            "remote_service_writes": 0,
            "ephemeral_local_outputs_removed": True,
        }
    if output.is_relative_to(repository):
        raise CaptureError("receipt output must be outside the immutable candidate checkout")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--governance-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.candidate) is None:
        raise SystemExit("--candidate must be a full Git commit ID")
    try:
        receipt = capture(
            args.repository_root,
            args.governance_root,
            args.python,
            args.candidate,
            args.output,
        )
    except CaptureError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "candidate_commit": receipt["subject"]["candidate_commit"],
                "candidate_tree": receipt["subject"]["candidate_tree"],
                "commands_passed": len(receipt["commands"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
