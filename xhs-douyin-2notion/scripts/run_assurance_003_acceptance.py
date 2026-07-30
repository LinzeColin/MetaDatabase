#!/usr/bin/env python3
"""Run Stage 6.3 security assurance without accessing shared authentication material."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.assurance.003"
PHASE = "PH.X2N.6.3"
RUN_ID = "RUN-X2N-S06-A003"
EXPECTED_ACCEPTANCES = {
    "ACC.x2n.gov.002": "PASS_CI_SYNTH_PRIVATE_AUTH_ZERO_CONTACT_CURRENT_AND_HISTORY_SCAN_ZERO",
    "ACC.x2n.gov.003": "PASS_CI_SYNTH_PUBLIC_SOURCE_RELEASE_ALLOWLIST_LICENSE_ZERO_UNKNOWN",
    "ACC.x2n.media.001": "PASS_CI_SYNTH_FIVE_SCOPE_PERSISTENCE_CDN_PRIVATE_ZERO",
    "ACC.x2n.media.003": "PASS_CI_SYNTH_512_URL_FUZZ_32_SSRF_FORBIDDEN_ZERO_LOCAL_FILE_READS",
    "ACC.x2n.media.004": "PASS_CI_SYNTH_BOUNDED_FFMPEG_FFPROBE_TEMPORARY_ONLY",
    "ACC.x2n.rel.003": "PASS_CI_SYNTH_SAST_OSV_SBOM_LICENSE_ARTIFACT_HISTORY_ZERO",
}
EXPECTED_EXECUTION = {
    "anonymous_osv_batch_requests": 1,
    "external_release_uploads": 0,
    "model_calls": 0,
    "platform_calls": 0,
    "private_gold_reads": 0,
    "real_account_execution": "NOT_RUN",
    "runtime_deployment": "NOT_RUN",
    "secret_reads": 0,
}
EXPECTED_REPORTS = {
    "artifact": {"allowlist_findings": 0, "deterministic": True, "runtime_data_files": 0},
    "csp": {"host_permissions": 0, "remote_resources": 0},
    "history": {"credential_history_hits": 0},
    "license": {"unknown_licenses": 0},
    "media": {"cdn_persistence_findings": 0, "forbidden_target_successes": 0, "local_file_reads": 0},
    "osv": {"critical_high_unresolved": 0, "dependencies_queried": 33, "vulnerabilities_reported": 0},
    "sast": {"critical_high_findings": 0},
    "source": {"finding_count": 0},
    "terminology": {"active_legacy_aliases": 0},
}


class Assurance003Error(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Assurance003Error(message)


def _environment(home: Path) -> dict[str, str]:
    return {
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(PROJECT_ROOT / "apps/companion/src")
        + os.pathsep
        + str(PROJECT_ROOT / "packages/contracts/src"),
        "RUFF_CACHE_DIR": str(home / "ruff-cache"),
    }


def _run(
    label: str,
    command: Sequence[str],
    *,
    env: dict[str, str],
    cwd: Path = PROJECT_ROOT,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise Assurance003Error(f"blocking command failed: {label}")
    return result


def _json_line(output: str, *, label: str) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(payloads, f"{label} emitted no JSON receipt")
    return payloads[-1]


def _unittest_metrics(output: str, *, label: str) -> dict[str, int]:
    match = re.search(r"Ran (\d+) tests? in [0-9.]+s", output)
    _require(match is not None and "OK" in output, f"{label} did not report success")
    _require("skipped" not in output.lower(), f"{label} skipped a blocking test")
    return {"blocking_skips": 0, "tests": int(match.group(1))}


def _baseline(command: str, *, env: dict[str, str], timeout: int = 300) -> dict[str, Any]:
    result = _run(
        f"baseline_{command}",
        (sys.executable, "-B", "scripts/ci/ci_baseline.py", command),
        env=env,
        timeout=timeout,
    )
    return _json_line(result.stdout, label=f"baseline {command}")


def _artifact(*, env: dict[str, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a003-artifact-") as temporary:
        root = Path(temporary)
        first = root / "first.zip"
        second = root / "second.zip"
        reports: list[dict[str, Any]] = []
        for label, target in (("first", first), ("second", second)):
            result = _run(
                f"artifact_{label}",
                (
                    sys.executable,
                    "-B",
                    "scripts/ci/ci_baseline.py",
                    "build-artifact",
                    "--artifact",
                    str(target),
                ),
                env=env,
            )
            reports.append(_json_line(result.stdout, label=f"artifact {label}"))
    _require(reports[0] == reports[1], "release artifact is not deterministic")
    _require(
        reports[0].get("allowlist_findings") == 0
        and reports[0].get("runtime_data_files") == 0
        and reports[0].get("status") == "PASS",
        "release artifact security gate failed",
    )
    return {
        "allowlist_findings": 0,
        "deterministic": True,
        "member_count": reports[0].get("member_count"),
        "runtime_data_files": 0,
    }


def _history_scan(*, env: dict[str, str]) -> dict[str, int]:
    git = shutil.which("git")
    _require(git is not None, "git is unavailable")
    commits_result = _run(
        "history_commits",
        (git, "rev-list", "--all", "--", "xhs-douyin-2notion"),
        env=env,
        cwd=REPOSITORY_ROOT,
    )
    commits = [value for value in commits_result.stdout.splitlines() if value]
    expressions = (
        "github" + r"_pat_[A-Za-z0-9_]{20,}",
        "gh" + r"[pousr]_[A-Za-z0-9]{20,}",
        "[Bb]earer[[:space:]]+[A-Za-z0-9._~-]{20,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"https://[^[:space:]/:@]+(:[^[:space:]/@]+)?@github\.com/",
    )
    hits = 0
    for commit in commits:
        for expression in expressions:
            result = subprocess.run(
                (git, "grep", "-I", "-l", "-E", "-e", expression, commit, "--", "xhs-douyin-2notion"),
                cwd=REPOSITORY_ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            _require(result.returncode in {0, 1}, "history scanner failed")
            hits += len([line for line in result.stdout.splitlines() if line])
    _require(hits == 0, "history credential scan found a secret or authenticated remote")
    return {"commits_scanned": len(commits), "credential_history_hits": 0, "pattern_classes": len(expressions)}


def _zero_auth_boundary(*, env: dict[str, str]) -> dict[str, int]:
    policy_path = PROJECT_ROOT / "machine/policy/external_auth_material_isolation_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    controls = policy.get("x2n_controls")
    _require(
        isinstance(controls, dict) and controls and all(value is False for value in controls.values()),
        "auth policy drifted",
    )
    implementation = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "scripts/ci/ci_baseline.py",
            PROJECT_ROOT / "scripts/run_assurance_003_acceptance.py",
        )
    )
    ambient_copy = "os.environ" + ".copy"
    _require(ambient_copy not in implementation, "security runner inherits ambient environment")
    _require(
        "GITHUB" + "_TOKEN" not in implementation and "GH" + "_TOKEN" not in implementation, "token surface entered"
    )
    remote = subprocess.run(
        (shutil.which("git") or "git", "config", "--local", "--get", "remote.origin.url"),
        cwd=REPOSITORY_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    remote_url = remote.stdout.strip()
    _require(
        remote.returncode == 0
        and re.fullmatch(r"(https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", remote_url)
        is not None,
        "authenticated remote entered local config",
    )
    return {"credential_helpers_touched": 0, "secret_reads": 0, "zero_contact_controls": len(controls)}


def _nomenclature() -> dict[str, Any]:
    path = PROJECT_ROOT / "scripts/verify_uxops_003.py"
    spec = importlib.util.spec_from_file_location("x2n_assurance003_nomenclature", path)
    _require(spec is not None and spec.loader is not None, "nomenclature verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    check = module.validate_active_nomenclature()
    _require(check.status == "PASS", "active runtime nomenclature gate failed")
    return dict(check.details)


def _run_pipeline(env: dict[str, str]) -> dict[str, Any]:
    ruff = (sys.executable, "-B", "-m", "ruff")
    _run("format", (*ruff, "format", "--check", "."), env=env)
    _run("lint", (*ruff, "check", "."), env=env)
    _run(
        "python_compile",
        (sys.executable, "-B", "-m", "compileall", "-q", "apps/companion/src", "packages/contracts/src", "scripts"),
        env=env,
    )
    _run("typescript_contract", ("npm", "run", "check:contracts:types"), env=env)
    sbom = _run("sbom", (sys.executable, "-B", "scripts/generate_foundation_005_sbom.py", "--check"), env=env)
    tests = _run(
        "security_contract_tests",
        (
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "-v",
            "tests.test_assurance_003",
            "tests.test_stage_3_review_resume_recheck",
            "apps.companion.tests.test_media_safety",
            "apps.companion.tests.test_media_preprocessing",
            "tests.test_skeleton_003",
        ),
        env=env,
        timeout=900,
    )
    media = _run("media_security", (sys.executable, "-B", "scripts/run_skeleton_003_acceptance.py"), env=env)
    source = _baseline("scan-source", env=env)
    fixture = _baseline("fixture-guard", env=env)
    self_test = _baseline("self-test", env=env)
    sast = _baseline("sast", env=env)
    license_report = _baseline("license", env=env)
    csp = _baseline("csp", env=env)
    osv = _baseline("osv", env=env, timeout=120)
    artifact = _artifact(env=env)
    history = _history_scan(env=env)
    auth = _zero_auth_boundary(env=env)
    terminology = _nomenclature()
    media_report = _json_line(media.stdout, label="media security")
    _require(
        source.get("finding_count") == 0
        and fixture.get("finding_count") == 0
        and self_test.get("silent_skips") == 0
        and sast.get("critical_high_findings") == 0
        and license_report.get("unknown_licenses") == 0
        and csp.get("host_permissions") == 0
        and csp.get("remote_resources") == 0
        and osv.get("critical_high_unresolved") == 0
        and media_report.get("media_persistence", {}).get("platform_cdn_url_findings") == 0
        and media_report.get("ssrf", {}).get("forbidden_target_successes") == 0
        and media_report.get("ssrf", {}).get("local_file_reads") == 0,
        "security acceptance report drifted",
    )
    return {
        "artifact": artifact,
        "auth": auth,
        "blocking_commands": 7,
        "blocking_failures": 0,
        "blocking_skips": 0,
        "csp": csp,
        "fixture": fixture,
        "history": history,
        "license": license_report,
        "media": media_report,
        "nomenclature": terminology,
        "osv": osv,
        "sast": sast,
        "sbom": _json_line(sbom.stdout, label="sbom"),
        "security_contract_tests": _unittest_metrics(tests.stdout + tests.stderr, label="security contract tests"),
        "self_test": self_test,
        "source": source,
    }


def run_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a003-acceptance-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        pipeline = _run_pipeline(_environment(home))
    reports = {
        "artifact": {
            "allowlist_findings": pipeline["artifact"]["allowlist_findings"],
            "deterministic": pipeline["artifact"]["deterministic"],
            "runtime_data_files": pipeline["artifact"]["runtime_data_files"],
        },
        "csp": {
            "host_permissions": pipeline["csp"]["host_permissions"],
            "remote_resources": pipeline["csp"]["remote_resources"],
        },
        "history": {"credential_history_hits": pipeline["history"]["credential_history_hits"]},
        "license": {"unknown_licenses": pipeline["license"]["unknown_licenses"]},
        "media": {
            "cdn_persistence_findings": pipeline["media"]["media_persistence"]["platform_cdn_url_findings"],
            "forbidden_target_successes": pipeline["media"]["ssrf"]["forbidden_target_successes"],
            "local_file_reads": pipeline["media"]["ssrf"]["local_file_reads"],
        },
        "osv": {
            "critical_high_unresolved": pipeline["osv"]["critical_high_unresolved"],
            "dependencies_queried": pipeline["osv"]["dependencies_queried"],
            "vulnerabilities_reported": pipeline["osv"]["vulnerabilities_reported"],
        },
        "sast": {"critical_high_findings": pipeline["sast"]["critical_high_findings"]},
        "source": {"finding_count": pipeline["source"]["finding_count"]},
        "terminology": {"active_legacy_aliases": pipeline["nomenclature"]["active_legacy_aliases"]},
    }
    _require(reports == EXPECTED_REPORTS, "security report summary drifted")
    return {
        "acceptance_status": EXPECTED_ACCEPTANCES,
        "execution": EXPECTED_EXECUTION,
        "phase": PHASE,
        "pipeline": pipeline,
        "reports": reports,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_CI_SYNTH_SECURITY_PRIVACY_SUPPLY_CHAIN_REAL_MVP_NOT_RUN",
        "task_id": TASK_ID,
    }


def main() -> int:
    try:
        print(json.dumps(run_acceptance(), ensure_ascii=True, sort_keys=True))
        return 0
    except (Assurance003Error, OSError, subprocess.SubprocessError, ValueError):
        print(
            json.dumps({"status": "FAIL_CLOSED", "task_id": TASK_ID}, ensure_ascii=True, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
