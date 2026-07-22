#!/usr/bin/env python3
"""Deterministic, fail-closed CI primitives for Foundation005.

The module never reads ambient credential variables. Source scans are confined to
the x2n project and reports contain only repository-relative paths or aggregates.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parent
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/x2n-ci.yml"
CI_POLICY = PROJECT_ROOT / "machine/policy/ci_gate_manifest.json"
LICENSE_POLICY = PROJECT_ROOT / "machine/policy/dependency_license_policy.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/release_artifact_allowlist.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
CHANGE_FIXTURE = PROJECT_ROOT / "packages/test-fixtures/ci/v1/change_scope_cases.json"
MODEL_FIXTURE = PROJECT_ROOT / "packages/test-fixtures/ci/v1/model_eval_dataset.json"
FAILURE_FIXTURE = PROJECT_ROOT / "packages/test-fixtures/ci/v1/seeded_failure_fragments.json"
SBOM = PROJECT_ROOT / "machine/sbom/stage_1_foundation_005.cdx.json"

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "node_modules",
}
TEXT_SIZE_LIMIT = 4 * 1024 * 1024
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
ACTION_SHA_PATTERN = re.compile(r"^[^\s@]+@[0-9a-f]{40}$")


class BaselineError(RuntimeError):
    pass


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    line: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "line": self.line,
            "path": self.path,
            "severity": self.severity,
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BaselineError(message)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_relative(value: str) -> str:
    _require("\x00" not in value and "\n" not in value and "\r" not in value, "unsafe path character")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    _require(not path.is_absolute() and ".." not in path.parts, "absolute or traversing path rejected")
    return path.as_posix()


def classify_paths(paths: Sequence[str], *, force_full: bool = False) -> dict[str, Any]:
    normalized = [_safe_relative(path) for path in paths if path]
    x2n_paths = [
        path
        for path in normalized
        if path == ".github/workflows/x2n-ci.yml"
        or path == "xhs-douyin-2notion"
        or path.startswith("xhs-douyin-2notion/")
    ]
    full_paths: list[str] = []
    for path in x2n_paths:
        if path == ".github/workflows/x2n-ci.yml":
            full_paths.append(path)
            continue
        relative = path.removeprefix("xhs-douyin-2notion/")
        documentation_only = relative.endswith(".md") and (
            relative.startswith("docs/") or "/docs/" in relative or relative in {"README.md", "HANDOFF.md"}
        )
        redacted_evidence_only = relative.startswith("evidence/") and relative.endswith(".json")
        if not documentation_only and not redacted_evidence_only:
            full_paths.append(path)
    result = {
        "full_required": bool(force_full or full_paths),
        "path_count": len(normalized),
        "reason": "forced_release_event"
        if force_full
        else ("critical_x2n_change" if full_paths else "path_scoped_fast_only"),
        "x2n_changed": bool(force_full or x2n_paths),
        "x2n_path_count": len(x2n_paths),
    }
    return result


def _git_changed_paths(base: str, head: str) -> list[str]:
    _require(SHA_PATTERN.fullmatch(base) is not None, "invalid base SHA")
    _require(SHA_PATTERN.fullmatch(head) is not None, "invalid head SHA")
    git = shutil.which("git")
    _require(git is not None, "git unavailable")
    result = subprocess.run(
        [git, "-c", "core.quotePath=false", "diff", "--name-only", "-z", base, head],
        cwd=REPOSITORY_ROOT,
        env={
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
        },
        check=False,
        capture_output=True,
    )
    _require(result.returncode == 0, "git changed-scope diff failed")
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def _iter_project_files(root: Path = PROJECT_ROOT) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts):
            continue
        yield path


def _line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def _sensitive_patterns() -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    github_shape = r"(?:ghp|gho|ghu|ghs|ghr|github" + r"_pat)_[A-Za-z0-9_]{20,}"
    private_key = r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    local_path = r"(?:/" + r"Users/|/" + r"home/)[^/\s]+/"
    cdn_names = "|".join(
        (
            "xhs" + "cdn",
            "douyin" + "vod",
            "byte" + "img",
            "pstatp",
            "bili" + "video",
            "hdslb",
            "ks" + "cdn",
            "yx" + "imgs",
            "sina" + "img",
            "tb" + "cdn",
            r"(?:img|gw|video|vod|pic|media)\.ali" + "cdn",
        )
    )
    return (
        ("secret.github_token_shape", "HIGH", re.compile(github_shape)),
        ("secret.private_key", "CRITICAL", re.compile(private_key)),
        ("secret.aws_access_key", "HIGH", re.compile(r"AKIA[0-9A-Z]{16}")),
        ("secret.bearer_value", "HIGH", re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{20,}")),
        ("private.local_absolute_path", "HIGH", re.compile(local_path)),
        ("private.windows_user_path", "HIGH", re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\")),
        ("cdn.platform_media_url", "HIGH", re.compile(rf"https?://[^\s'\"]*(?:{cdn_names})", re.IGNORECASE)),
        ("cdn.signed_parameter", "HIGH", re.compile(r"(?i)(?:xsec_token|signature|auth_key)=")),
    )


def scan_text(text: str, public_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for code, severity, pattern in _sensitive_patterns():
        for match in pattern.finditer(text):
            findings.append(Finding(code, severity, public_path, _line_number(text, match.start())))
    return findings


def scan_source(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    findings: list[Finding] = []
    scanned = 0
    binary_files = 0
    denied_suffixes = set(_load_json(ARTIFACT_POLICY)["denied_suffixes"])
    for path in _iter_project_files(root):
        relative = path.relative_to(root).as_posix()
        scanned += 1
        if path.suffix.lower() in denied_suffixes:
            findings.append(Finding("private.denied_file_type", "HIGH", relative, 0))
            continue
        data = path.read_bytes()
        if len(data) > TEXT_SIZE_LIMIT:
            findings.append(Finding("private.oversized_repository_file", "HIGH", relative, 0))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            binary_files += 1
            findings.append(Finding("private.unapproved_binary", "HIGH", relative, 0))
            continue
        findings.extend(scan_text(text, relative))
    return {
        "binary_files": binary_files,
        "finding_count": len(findings),
        "findings": [item.public_dict() for item in findings],
        "scanned_files": scanned,
        "status": "PASS" if not findings else "FAIL_CLOSED",
    }


def validate_unittest_skips(output: str) -> dict[str, Any]:
    policy = _load_json(CI_POLICY)["nonblocking_optional_skips"]
    expected = Counter({row["reason"]: row["count_per_repetition"] for row in policy["reasons"]})
    observed = Counter(re.findall(r"skipped '([^']+)'", output))
    summary = re.search(r"OK \(skipped=(\d+)\)", output)
    expected_count = int(policy["per_repetition"])
    _require(observed == expected, "unit test skip reason/count drifted")
    _require(summary is not None and int(summary.group(1)) == expected_count, "unit test skip summary drifted")
    _require(sum(observed.values()) == expected_count, "optional skip policy count drifted")
    return {
        "explicit_nonblocking_skips": expected_count,
        "reason_classes": len(observed),
        "status": "PASS",
    }


def fixture_guard() -> dict[str, Any]:
    manifest = _load_json(FIXTURE_MANIFEST)
    rows = manifest.get("fixtures")
    _require(isinstance(rows, list) and rows, "fixture manifest is empty")
    ids = [item.get("id") for item in rows]
    paths = [item.get("path") for item in rows]
    _require(len(ids) == len(set(ids)) and len(paths) == len(set(paths)), "fixture registration is not unique")
    findings: list[Finding] = []
    cases = 0
    for row in rows:
        relative = _safe_relative(str(row.get("path", "")))
        path = PROJECT_ROOT / relative
        _require(path.is_file() and path.resolve().is_relative_to(PROJECT_ROOT.resolve()), "registered fixture missing")
        payload = _load_json(path)
        for field in (
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
            "contains_real_accounts",
            "real_accounts",
        ):
            if field in payload:
                _require(payload[field] is False, f"fixture private boundary asserted true: {relative}")
        findings.extend(scan_text(path.read_text(encoding="utf-8"), relative))
        declared = row.get("case_count")
        _require(isinstance(declared, int) and declared > 0, "fixture case_count invalid")
        cases += declared
        if relative.startswith("packages/test-fixtures/ci/"):
            _require(len(payload.get("cases", [])) == declared, "Foundation005 fixture case count drifted")
            _require(payload.get("synthetic") is True, "Foundation005 fixture is not synthetic")
    _require(not findings, "fixture leak scan found sensitive material")
    return {
        "declared_cases": cases,
        "finding_count": 0,
        "registered_fixtures": len(rows),
        "status": "PASS",
    }


def _python_sast(path: Path, public_path: str) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=public_path)
    except SyntaxError as error:
        return [Finding("sast.python.syntax_error", "HIGH", public_path, error.lineno or 0)]
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            findings.append(Finding("sast.python.dynamic_execution", "HIGH", public_path, node.lineno))
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            dotted = f"{node.func.value.id}.{node.func.attr}"
            if dotted in {"os.system", "pickle.loads", "marshal.loads"}:
                findings.append(
                    Finding("sast.python.unsafe_execution_or_deserialization", "HIGH", public_path, node.lineno)
                )
            if dotted in {"subprocess.call", "subprocess.Popen", "subprocess.run"}:
                for keyword in node.keywords:
                    if (
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    ):
                        findings.append(Finding("sast.python.shell_true", "HIGH", public_path, node.lineno))
        for keyword in node.keywords:
            if keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                findings.append(Finding("sast.python.tls_verify_disabled", "HIGH", public_path, node.lineno))
    return findings


def _javascript_sast(path: Path, public_path: str) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    patterns = (
        ("sast.javascript.dynamic_execution", re.compile(r"\b(?:eval\s*\(|new\s+Function\s*\()")),
        ("sast.javascript.shell_execution", re.compile(r"\b(?:exec|execSync)\s*\(")),
        ("sast.javascript.html_injection", re.compile(r"\.(?:innerHTML|outerHTML)\s*=")),
        ("sast.javascript.remote_import", re.compile(r"\bimport\s*(?:\(|[^;]*?from\s*)['\"]https?://")),
    )
    findings: list[Finding] = []
    for code, pattern in patterns:
        for match in pattern.finditer(text):
            findings.append(Finding(code, "HIGH", public_path, _line_number(text, match.start())))
    return findings


def _workflow_sast(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    public_path = ".github/workflows/x2n-ci.yml"
    findings: list[Finding] = []
    for match in re.finditer(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", text):
        value = match.group(1)
        if not value.startswith("./") and ACTION_SHA_PATTERN.fullmatch(value) is None:
            findings.append(
                Finding("sast.workflow.unpinned_action", "HIGH", public_path, _line_number(text, match.start()))
            )
    prohibited = {
        "sast.workflow.pull_request_target": "pull_request_target:",
        "sast.workflow.secret_context": "secrets.",
        "sast.workflow.continue_on_error": "continue-on-error: true",
        "sast.workflow.persist_credentials": "persist-credentials: true",
    }
    for code, token in prohibited.items():
        start = text.find(token)
        if start >= 0:
            findings.append(Finding(code, "HIGH", public_path, _line_number(text, start)))
    if not re.search(r"(?m)^permissions:\s*\n\s+contents:\s+read\s*$", text):
        findings.append(Finding("sast.workflow.permissions_not_minimal", "HIGH", public_path, 1))
    if re.search(r"(?i)(?:curl|wget)[^\n|]*\|\s*(?:sh|bash)", text):
        findings.append(Finding("sast.workflow.pipe_to_shell", "CRITICAL", public_path, 1))
    return findings


def run_sast(*, source_root: Path = PROJECT_ROOT, workflow: Path = WORKFLOW) -> tuple[dict[str, Any], dict[str, Any]]:
    findings: list[Finding] = []
    roots = (
        source_root / "apps/companion/src",
        source_root / "apps/extension/src",
        source_root / "scripts/ci",
        source_root / "packages/contracts/src",
    )
    scanned = 0
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix == ".py":
                findings.extend(_python_sast(path, path.relative_to(source_root).as_posix()))
                scanned += 1
            elif path.suffix in {".js", ".mjs", ".ts"}:
                findings.extend(_javascript_sast(path, path.relative_to(source_root).as_posix()))
                scanned += 1
    _require(workflow.is_file(), "x2n workflow missing")
    findings.extend(_workflow_sast(workflow))
    scanned += 1
    report = {
        "critical_high_findings": sum(item.severity in {"CRITICAL", "HIGH"} for item in findings),
        "finding_count": len(findings),
        "findings": [item.public_dict() for item in findings],
        "scanned_files": scanned,
        "status": "PASS" if not findings else "FAIL_CLOSED",
    }
    rules = sorted({item.code for item in findings})
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "results": [
                    {
                        "level": "error",
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": item.path},
                                    "region": {"startLine": max(item.line, 1)},
                                }
                            }
                        ],
                        "ruleId": item.code,
                    }
                    for item in findings
                ],
                "tool": {
                    "driver": {
                        "name": "x2n-foundation005-sast",
                        "rules": [{"id": rule, "shortDescription": {"text": rule}} for rule in rules],
                        "version": "1.0",
                    }
                },
            }
        ],
        "version": "2.1.0",
    }
    return report, sarif


def validate_csp() -> dict[str, Any]:
    manifest = _load_json(PROJECT_ROOT / "apps/extension/manifest.json")
    _require(manifest.get("manifest_version") == 3, "extension is not MV3")
    csp = manifest.get("content_security_policy")
    if csp is not None:
        extension_pages = csp.get("extension_pages") if isinstance(csp, dict) else csp
        _require(extension_pages == "script-src 'self'; object-src 'none';", "extension CSP widened")
    _require(not manifest.get("host_permissions"), "host permissions entered Foundation005 baseline")
    scripts = list((PROJECT_ROOT / "apps/extension").glob("*.html")) + list(
        (PROJECT_ROOT / "apps/extension/src").glob("*.js")
    )
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        _require(
            re.search(r"(?:src|href)=['\"]https?://", text, re.IGNORECASE) is None, "remote extension resource found"
        )
        _require(re.search(r"\b(?:eval\s*\(|new\s+Function\s*\()", text) is None, "dynamic extension code found")
    return {
        "host_permissions": 0,
        "remote_resources": 0,
        "scripts_scanned": len(scripts),
        "status": "PASS",
    }


def validate_license(sbom_path: Path = SBOM) -> dict[str, Any]:
    policy = _load_json(LICENSE_POLICY)
    sbom = _load_json(sbom_path)
    components = sbom.get("components", [])
    _require(isinstance(components, list) and len(components) == 33, "Foundation005 SBOM is incomplete")
    allowed = set(policy["allowed_spdx_ids"])
    refs: set[str] = set()
    unknown = 0
    for component in components:
        ref = component.get("bom-ref")
        _require(isinstance(ref, str) and ref not in refs, "SBOM component identity missing or duplicated")
        refs.add(ref)
        licenses = component.get("licenses", [])
        license_ids = [row.get("license", {}).get("id") for row in licenses]
        if len(license_ids) != 1 or license_ids[0] not in allowed:
            unknown += 1
    _require(unknown == 0, "unknown or prohibited dependency license")
    dependency_rows = sbom.get("dependencies", [])
    dependency_refs = {row.get("ref") for row in dependency_rows}
    _require(refs <= dependency_refs, "SBOM dependency rows incomplete")
    _require(all(set(row.get("dependsOn", [])) <= refs for row in dependency_rows), "SBOM edge unresolved")

    expected_python = policy["runtime_python"] | policy["ci_python"]
    actual_python = {
        item["name"]: {"version": item["version"], "license": item["licenses"][0]["license"]["id"]}
        for item in components
        if item["purl"].startswith("pkg:pypi/")
    }
    _require(actual_python == expected_python, "Python dependency license registry drifted")
    return {
        "components": len(components),
        "dependency_edges_resolved": True,
        "status": "PASS",
        "unknown_licenses": 0,
    }


def validate_model_dataset(path: Path = MODEL_FIXTURE) -> dict[str, Any]:
    dataset = _load_json(path)
    _require(
        dataset.get("schema_version") == "1.0" and dataset.get("dataset_version") == "1.0.0",
        "model dataset version drifted",
    )
    _require(
        dataset.get("synthetic") is True and dataset.get("model_invocation_allowed") is False,
        "model dataset boundary weakened",
    )
    for field in (
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_real_accounts",
    ):
        _require(dataset.get(field) is False, f"model dataset contains prohibited class: {field}")
    _require(dataset.get("owner_top_level_taxonomy_required") is True, "Owner taxonomy gate missing")
    cases = dataset.get("cases", [])
    _require(len(cases) == 8 and len({row.get("id") for row in cases}) == 8, "model dataset case set drifted")
    capabilities = {row.get("capability") for row in cases}
    _require(
        capabilities == {"dataset_contract", "asr", "ocr", "fusion", "classification", "red_team"},
        "model capability set incomplete",
    )
    red_team_cases = sum(row.get("capability") == "red_team" for row in cases)
    _require(red_team_cases == 3, "model Red Team contract cases incomplete")
    policy = _load_json(CI_POLICY)
    flags = policy["model_features"]
    _require(
        all(flags[name] is False for name in ("asr", "ocr", "fusion", "classification", "automatic_classification")),
        "model feature enabled before acceptance",
    )
    _require(flags["automatic_classification_gate"] == "ACC.x2n.ai.006", "automatic classification gate drifted")
    return {
        "automatic_classification": "DISABLED_PENDING_ACC.x2n.ai.006",
        "capabilities": {
            "asr": "NOT_RUN_FEATURE_DISABLED",
            "classification": "NOT_RUN_FEATURE_DISABLED",
            "dataset_contract": "PASS",
            "fusion": "NOT_RUN_FEATURE_DISABLED",
            "ocr": "NOT_RUN_FEATURE_DISABLED",
            "red_team": "CONTRACT_PASS_MODEL_NOT_RUN",
        },
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "fallback": "DISABLE_RELATED_CAPABILITY_AND_REQUIRE_REVIEW",
        "model_calls": 0,
        "red_team_contract_cases": red_team_cases,
        "status": "PASS_BASELINE_SKELETON",
    }


def validate_coverage(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    policy = _load_json(CI_POLICY)["coverage"]
    _require(payload.get("meta", {}).get("branch_coverage") is True, "branch coverage mode not enabled")
    overall = float(payload.get("totals", {}).get("percent_covered", 0.0))
    _require(overall >= float(policy["overall_combined_percent_min"]), "overall risk coverage threshold missed")
    critical: dict[str, Any] = {}
    for filename, threshold in policy["critical_module_combined_percent_min"].items():
        summary = payload.get("files", {}).get(filename, {}).get("summary", {})
        combined = float(summary.get("percent_covered", 0.0))
        branches = int(summary.get("num_branches", 0))
        covered_branches = int(summary.get("covered_branches", 0))
        _require(branches > 0 and combined >= float(threshold), f"critical coverage threshold missed: {filename}")
        critical[filename] = {
            "combined_percent": round(combined, 2),
            "covered_branches": covered_branches,
            "total_branches": branches,
        }
    return {
        "branch_mode": True,
        "critical_modules": critical,
        "overall_combined_percent": round(overall, 2),
        "status": "PASS",
    }


def _allowed_artifact_path(relative: str, policy: dict[str, Any]) -> bool:
    return relative in set(policy["allowed_exact"]) or any(
        relative.startswith(prefix) for prefix in policy["allowed_prefixes"]
    )


def _artifact_source_files(policy: dict[str, Any]) -> list[Path]:
    selected: list[Path] = []
    for path in _iter_project_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if _allowed_artifact_path(relative, policy):
            _require(
                not any(relative.startswith(prefix) for prefix in policy["denied_prefixes"]),
                "denied artifact prefix selected",
            )
            _require(path.suffix.lower() not in set(policy["denied_suffixes"]), "denied artifact suffix selected")
            selected.append(path)
    selected_rel = {path.relative_to(PROJECT_ROOT).as_posix() for path in selected}
    _require(set(policy["required_files"]) <= selected_rel, "required release candidate file missing")
    return selected


def _zip_info(name: str, *, executable: bool) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
    return info


def validate_artifact(path: Path) -> dict[str, Any]:
    policy = _load_json(ARTIFACT_POLICY)
    findings: list[Finding] = []
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        _require(len(members) == len({row.filename for row in members}), "duplicate archive member")
        for member in members:
            pure = PurePosixPath(member.filename)
            _require(not pure.is_absolute() and ".." not in pure.parts, "unsafe archive member path")
            _require(pure.parts and pure.parts[0] == "xhs-douyin-2notion", "artifact namespace drifted")
            relative = PurePosixPath(*pure.parts[1:]).as_posix()
            _require(_allowed_artifact_path(relative, policy), "artifact member not allowlisted")
            _require(
                not any(relative.startswith(prefix) for prefix in policy["denied_prefixes"]), "denied artifact member"
            )
            _require(
                PurePosixPath(relative).suffix.lower() not in set(policy["denied_suffixes"]),
                "runtime/media artifact member",
            )
            data = archive.read(member)
            _require(len(data) <= TEXT_SIZE_LIMIT, "artifact member exceeds scan limit")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise BaselineError("unapproved binary artifact member") from error
            findings.extend(scan_text(text, relative))
    _require(not findings, "artifact contains secret/private/CDN material")
    return {
        "allowlist_findings": 0,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "member_count": len(members),
        "runtime_data_files": 0,
        "status": "PASS",
    }


def build_artifact(path: Path) -> dict[str, Any]:
    policy = _load_json(ARTIFACT_POLICY)
    files = _artifact_source_files(policy)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in files:
            relative = source.relative_to(PROJECT_ROOT).as_posix()
            data = source.read_bytes()
            executable = data.startswith(b"#!")
            archive.writestr(_zip_info(f"xhs-douyin-2notion/{relative}", executable=executable), data)
    return validate_artifact(path)


def _osv_queries(sbom_path: Path = SBOM) -> list[dict[str, Any]]:
    sbom = _load_json(sbom_path)
    queries: list[dict[str, Any]] = []
    for component in sbom.get("components", []):
        purl = str(component.get("purl", ""))
        if purl.startswith("pkg:pypi/"):
            ecosystem = "PyPI"
        elif purl.startswith("pkg:npm/"):
            ecosystem = "npm"
        else:
            raise BaselineError("unsupported SBOM ecosystem for OSV")
        queries.append(
            {
                "package": {"ecosystem": ecosystem, "name": urllib.parse.unquote(component["name"])},
                "version": component["version"],
            }
        )
    _require(len(queries) == 33, "OSV query set incomplete")
    return queries


def _validate_osv_response(response: dict[str, Any], query_count: int) -> dict[str, Any]:
    results = response.get("results")
    _require(isinstance(results, list) and len(results) == query_count, "OSV response incomplete")
    vulnerabilities = sum(len(row.get("vulns", [])) for row in results)
    _require(vulnerabilities == 0, "OSV reported an unresolved vulnerability")
    return {
        "critical_high_unresolved": 0,
        "dependencies_queried": query_count,
        "status": "PASS",
        "vulnerabilities_reported": 0,
    }


def _anonymous_url_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run_osv(*, response_override: dict[str, Any] | None = None) -> dict[str, Any]:
    queries = _osv_queries()
    if response_override is None:
        body = json.dumps({"queries": queries}, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            "https://api.osv.dev/v1/querybatch",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "x2n-foundation005-ci/1.0"},
            method="POST",
        )
        try:
            with _anonymous_url_opener().open(request, timeout=30) as handle:
                response = json.load(handle)
        except Exception as error:
            raise BaselineError("OSV live query unavailable; fail closed") from error
    else:
        response = response_override
    _require(isinstance(response, dict), "OSV response must be an object")
    return _validate_osv_response(response, len(queries))


def run_self_test() -> dict[str, Any]:
    change_fixture = _load_json(CHANGE_FIXTURE)
    routing_passed = 0
    for case in change_fixture.get("cases", []):
        result = classify_paths(case["paths"])
        _require(result["x2n_changed"] is case["x2n_changed"], "changed-scope x2n routing self-test failed")
        _require(result["full_required"] is case["full_required"], "changed-scope full routing self-test failed")
        routing_passed += 1
    fragments = {row["id"]: "".join(row["fragments"]) for row in _load_json(FAILURE_FIXTURE)["cases"]}
    seeded_categories: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="x2n-f005-self-test-") as value:
        root = Path(value)
        sensitive = "\n".join((fragments["secret-shape"], fragments["local-path"], fragments["cdn-url"]))
        sensitive_findings = scan_text(sensitive, "synthetic-seed.txt")
        seeded_categories.update(item.code for item in sensitive_findings)
        _require(
            {"secret.github_token_shape", "private.local_absolute_path", "cdn.platform_media_url"} <= seeded_categories,
            "sensitive scanner seeded failure was not detected",
        )

        sast_file = root / "unsafe.py"
        sast_file.write_text(fragments["sast-eval"] + "\n", encoding="utf-8")
        findings = _python_sast(sast_file, "synthetic-unsafe.py")
        _require(
            any(item.code == "sast.python.dynamic_execution" for item in findings), "Python SAST seed was not detected"
        )
        seeded_categories.update(item.code for item in findings)

        workflow = root / "workflow.yml"
        workflow.write_text(
            "permissions:\n  contents: read\njobs:\n  test:\n    timeout-minutes: 1\n    steps:\n      - uses: "
            + fragments["unpinned-action"]
            + "\n",
            encoding="utf-8",
        )
        findings = _workflow_sast(workflow)
        _require(
            any(item.code == "sast.workflow.unpinned_action" for item in findings), "workflow pin seed was not detected"
        )
        seeded_categories.update(item.code for item in findings)

        invalid_archive = root / "invalid.zip"
        with zipfile.ZipFile(invalid_archive, "w") as archive:
            archive.writestr("xhs-douyin-2notion/runtime/canonical.sqlite", b"synthetic")
        try:
            validate_artifact(invalid_archive)
        except BaselineError:
            seeded_categories.add("artifact.runtime_data")
        else:
            raise BaselineError("artifact allowlist seed was not detected")

        mutated = _load_json(MODEL_FIXTURE)
        mutated["contains_private_content"] = True
        mutated_path = root / "model.json"
        _write_json(mutated_path, mutated)
        try:
            validate_model_dataset(mutated_path)
        except BaselineError:
            seeded_categories.add("model.private_fixture")
        else:
            raise BaselineError("model dataset seed was not detected")

    query_count = len(_osv_queries())
    seeded_osv = {"results": [{"vulns": [{"id": "synthetic-only"}]}] + [{} for _ in range(query_count - 1)]}
    try:
        _validate_osv_response(seeded_osv, query_count)
    except BaselineError:
        seeded_categories.add("osv.vulnerability")
    else:
        raise BaselineError("OSV vulnerability seed was not detected")

    _require(routing_passed == 8 and len(seeded_categories) >= 8, "CI self-test coverage incomplete")
    return {
        "change_scope_cases": routing_passed,
        "seeded_failure_categories": len(seeded_categories),
        "silent_skips": 0,
        "status": "PASS",
    }


def _emit_or_write(payload: dict[str, Any], output: Path | None) -> None:
    if output is not None:
        _write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="x2n Foundation005 CI baseline primitives")
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--base")
    classify.add_argument("--head")
    classify.add_argument("--paths-file", type=Path)
    classify.add_argument("--force-full", action="store_true")
    classify.add_argument("--github-output", type=Path)

    for name in ("scan-source", "fixture-guard", "license", "model", "self-test", "csp"):
        command = subparsers.add_parser(name)
        command.add_argument("--output", type=Path)

    sast = subparsers.add_parser("sast")
    sast.add_argument("--output", type=Path)
    sast.add_argument("--sarif", type=Path)

    coverage = subparsers.add_parser("coverage")
    coverage.add_argument("--input", type=Path, required=True)
    coverage.add_argument("--output", type=Path)

    artifact = subparsers.add_parser("build-artifact")
    artifact.add_argument("--artifact", type=Path, required=True)
    artifact.add_argument("--output", type=Path)

    osv = subparsers.add_parser("osv")
    osv.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "classify":
            if args.paths_file:
                paths = [line for line in args.paths_file.read_text(encoding="utf-8").splitlines() if line]
            else:
                _require(args.base and args.head, "classify requires --base/--head or --paths-file")
                if args.base == "0" * 40:
                    paths = []
                    args.force_full = True
                else:
                    paths = _git_changed_paths(args.base, args.head)
            payload = classify_paths(paths, force_full=args.force_full)
            if args.github_output:
                args.github_output.write_text(
                    "x2n_changed=" + str(payload["x2n_changed"]).lower() + "\n"
                    "full_required=" + str(payload["full_required"]).lower() + "\n"
                    "reason=" + payload["reason"] + "\n",
                    encoding="utf-8",
                )
            _emit_or_write(payload, None)
        elif args.command == "scan-source":
            payload = scan_source()
            _require(payload["status"] == "PASS", "source privacy scan failed")
            _emit_or_write(payload, args.output)
        elif args.command == "fixture-guard":
            _emit_or_write(fixture_guard(), args.output)
        elif args.command == "license":
            _emit_or_write(validate_license(), args.output)
        elif args.command == "model":
            _emit_or_write(validate_model_dataset(), args.output)
        elif args.command == "self-test":
            _emit_or_write(run_self_test(), args.output)
        elif args.command == "csp":
            _emit_or_write(validate_csp(), args.output)
        elif args.command == "sast":
            payload, sarif = run_sast()
            if args.sarif:
                _write_json(args.sarif, sarif)
            _require(payload["status"] == "PASS", "SAST detected a blocking finding")
            _emit_or_write(payload, args.output)
        elif args.command == "coverage":
            _emit_or_write(validate_coverage(args.input), args.output)
        elif args.command == "build-artifact":
            _emit_or_write(build_artifact(args.artifact), args.output)
        elif args.command == "osv":
            _emit_or_write(run_osv(), args.output)
        else:
            raise BaselineError("unknown command")
        return 0
    except (BaselineError, OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(
            json.dumps({"reason": str(error), "status": "FAIL_CLOSED"}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
