from __future__ import annotations

import argparse
import ast
import concurrent.futures
import multiprocessing
import copy
import hashlib
import importlib.util
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SUBJECT_SPEC = importlib.util.spec_from_file_location(
    "efs_formal_subject", Path(__file__).with_name("formal_subject.py")
)
if _SUBJECT_SPEC is None or _SUBJECT_SPEC.loader is None:
    raise RuntimeError("unable to load formal Subject contract")
_FORMAL_SUBJECT = importlib.util.module_from_spec(_SUBJECT_SPEC)
_SUBJECT_SPEC.loader.exec_module(_FORMAL_SUBJECT)

from equity_foresight_signal import (  # noqa: E402
    EFSError,
    audit_runtime_source,
    evaluate,
    evaluate_prepared,
    prepare_bundle,
    train_direction_pipeline,
    validate_bundle,
    validate_pit_dataset,
    validate_training_config,
)
from equity_foresight_signal.canonical import sha256_hex  # noqa: E402

SCHEMA = "efs.formal_runtime_verification.v2"
SECRET_PATTERNS = {
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GITHUB_TOKEN": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "OPENAI_KEY": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _load(name: str) -> dict:
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def _run(argv: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)


def _run_test_modules(modules: list[str], *, label: str) -> dict:
    if not modules:
        return {"status": "FAIL", "test_count": 0, "returncode": None, "reason": f"NO_{label.upper()}_TESTS"}
    result = _run([sys.executable, "-B", "-m", "unittest", *modules, "-q"], 600)
    text = result.stdout + result.stderr
    match = re.search(r"Ran (\d+) tests", text)
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "test_count": int(match.group(1)) if match else None,
        "module_count": len(modules),
        "label": label,
        "returncode": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        "stderr_tail": result.stderr[-1500:],
    }


COMPONENTS = (
    "tests_engine",
    "tests_cli_status",
    "tests_contracts",
    "specialized_tests",
    "statistical",
    "isolation",
    "static",
)

SPECIALIZED_TEST_MODULES = {
    "test_formal_runtime_verifier.py",
    "test_kernel_isolation.py",
    "test_network_namespace_isolation.py",
    "test_macos_zero_footprint.py",
}

SOURCE_TEST_COMPONENT_MODULES = {
    "tests_engine": ("tests.test_engine",),
    "tests_cli_status": ("tests.test_cli_operations", "tests.test_status_integration"),
    "tests_contracts": (
        "tests.test_capacity",
        "tests.test_dataset",
        "tests.test_governance",
        "tests.test_host",
        "tests.test_legacy_evidence",
        "tests.test_oracle_runner",
        "tests.test_portability",
        "tests.test_runtime_operations",
        "tests.test_seal_snapshot",
        "tests.test_training",
    ),
}

# The installed Skill deliberately excludes outer task-pack governance and the
# LinzeHomeHub landing adapter. Those are validated by the outer ZIP verifier.
# It still carries a complete Runtime test profile and can verify itself without
# reaching back into the builder worktree.
PACKAGED_TEST_COMPONENT_MODULES = {
    "tests_engine": ("tests.test_engine",),
    "tests_cli_status": ("tests.test_cli_operations",),
    "tests_contracts": (
        "tests.test_capacity",
        "tests.test_dataset",
        "tests.test_host",
        "tests.test_legacy_evidence",
        "tests.test_portability",
        "tests.test_runtime_operations",
        "tests.test_training",
    ),
}


def _source_worktree_mode() -> bool:
    return (
        ROOT
        / "taskpack_blueprint"
        / "skill_draft"
        / "equity-foresight-signal"
        / "SKILL.md"
    ).is_file()


def _active_test_component_modules() -> dict[str, tuple[str, ...]]:
    return SOURCE_TEST_COMPONENT_MODULES if _source_worktree_mode() else PACKAGED_TEST_COMPONENT_MODULES


def _test_component(name: str) -> dict:
    active = _active_test_component_modules()
    modules = list(active[name])
    report = _run_test_modules(modules, label=name)
    report["runtime_profile"] = "SOURCE_WORKTREE" if _source_worktree_mode() else "PACKAGED_SKILL"
    report["excluded_modules"] = [
        "tests.test_formal_packaging",
        *sorted(f"tests.{Path(item).stem}" for item in SPECIALIZED_TEST_MODULES),
        *sorted(module for component, values in active.items() if component != name for module in values),
    ]
    return report


def _specialized_test_suite() -> dict:
    modules = [
        f"tests.{Path(name).stem}"
        for name in sorted(SPECIALIZED_TEST_MODULES)
        if (ROOT / "tests" / name).is_file()
    ]
    return _run_test_modules(modules, label="specialized_release_and_isolation")


def _determinism(iterations: int) -> dict:
    prepared = prepare_bundle(_load("bundle.json"))
    request = _load("request.json")
    hashes: set[str] = set()
    start = time.perf_counter()
    with mock.patch.object(socket, "socket", side_effect=AssertionError("socket forbidden")), mock.patch.object(
        subprocess, "Popen", side_effect=AssertionError("child process forbidden")
    ):
        for _ in range(iterations):
            hashes.add(evaluate_prepared(request, prepared)["result_sha256"])
    elapsed = time.perf_counter() - start
    return {
        "status": "PASS" if len(hashes) == 1 else "FAIL",
        "iterations": iterations,
        "unique_result_hashes": sorted(hashes),
        "throughput_per_second_observed": format(iterations / elapsed, ".3f"),
        "claim_boundary": "CURRENT_ENVIRONMENT_OBSERVATION_NOT_PRODUCTION_SLO",
    }


def _training(repeats: int) -> dict:
    dataset, config = _load("pit_dataset.json"), _load("training_config.json")
    hashes = []
    with mock.patch.object(socket, "socket", side_effect=AssertionError("socket forbidden")), mock.patch.object(
        subprocess, "Popen", side_effect=AssertionError("child process forbidden")
    ):
        for _ in range(repeats):
            hashes.append(train_direction_pipeline(dataset, config)["run_sha256"])
    return {"status": "PASS" if len(set(hashes)) == 1 else "FAIL", "repeats": repeats, "unique_run_hashes": sorted(set(hashes)), "automatic_promotion_permitted": False}


def _paths(value: object, prefix: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    result = [prefix]
    if isinstance(value, dict):
        for key, child in value.items():
            result.extend(_paths(child, prefix + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(_paths(child, prefix + (index,)))
    return result


def _fuzz(cases: int, seed: int) -> dict:
    if cases < 10_000 or cases > 100_000:
        raise ValueError("fuzz cases must be between 10000 and 100000")
    rng = random.Random(seed)
    sources = {
        "request": _load("request.json"),
        "bundle": _load("bundle.json"),
        "dataset": _load("pit_dataset.json"),
        "config": _load("training_config.json"),
    }
    replacements: tuple[object, ...] = (None, True, False, 0, -1, 10**30, 1.5, "", "x" * 20_000, [], {}, [None], {"invalid": None}, float("nan"), float("inf"))

    def mutate(source: dict) -> object:
        value: object = copy.deepcopy(source)
        action = rng.randrange(5)
        if action == 0 and isinstance(value, dict) and value:
            value.pop(rng.choice(list(value)))
            return value
        if action == 1 and isinstance(value, dict):
            value[f"unexpected_{rng.randrange(1000)}"] = copy.deepcopy(rng.choice(replacements))
            return value
        path = rng.choice(_paths(value))
        replacement = copy.deepcopy(rng.choice(replacements))
        if not path:
            return replacement
        target = value
        for key in path[:-1]:
            target = target[key]  # type: ignore[index]
        target[path[-1]] = replacement  # type: ignore[index]
        return value

    unexpected: list[dict[str, str]] = []
    bad_envelopes = 0
    allocations = {"request": 3000, "bundle": 3000, "dataset": 2000, "config": 2000}
    scale = cases / 10_000
    counts = {key: int(value * scale) for key, value in allocations.items()}
    counts["config"] += cases - sum(counts.values())
    for _ in range(counts["request"]):
        try:
            result = evaluate(mutate(sources["request"]), sources["bundle"])  # type: ignore[arg-type]
            if not isinstance(result, dict) or "result_sha256" not in result:
                bad_envelopes += 1
        except Exception as exc:
            unexpected.append({"surface": "request", "type": type(exc).__name__})
    for _ in range(counts["bundle"]):
        mutated = mutate(sources["bundle"])
        try:
            result = evaluate(sources["request"], mutated)  # type: ignore[arg-type]
            if not isinstance(result, dict) or "result_sha256" not in result:
                bad_envelopes += 1
        except Exception as exc:
            unexpected.append({"surface": "bundle_evaluate", "type": type(exc).__name__})
        try:
            validate_bundle(mutated)  # type: ignore[arg-type]
        except EFSError:
            pass
        except Exception as exc:
            unexpected.append({"surface": "bundle_validate", "type": type(exc).__name__})
    for name, validator in (("dataset", validate_pit_dataset), ("config", validate_training_config)):
        for _ in range(counts[name]):
            try:
                validator(mutate(sources[name]))  # type: ignore[arg-type]
            except EFSError:
                pass
            except Exception as exc:
                unexpected.append({"surface": name, "type": type(exc).__name__})
    return {"status": "PASS" if not unexpected and bad_envelopes == 0 else "FAIL", "seed": seed, "case_count": cases, "bad_envelopes": bad_envelopes, "unexpected_exception_count": len(unexpected), "unexpected_examples": unexpected[:20]}


def _isolation(script: str) -> dict:
    result = _run([sys.executable, "-B", f"tools/{script}"], 180)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"status": "FAIL", "stderr_tail": result.stderr[-1000:]}
    payload["returncode"] = result.returncode
    if result.returncode != 0:
        payload["status"] = "FAIL"
    return payload


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    seen: set[str] = set()
    for key, value in pairs:
        normalized = unicodedata.normalize("NFC", key)
        if key != normalized:
            raise ValueError(f"noncanonical JSON key: {key!r}")
        if normalized in seen:
            raise ValueError(f"duplicate JSON key: {key!r}")
        seen.add(normalized)
        result[key] = value
    return result


def _python_structure_findings(text: str, rel: str) -> list[dict[str, object]]:
    tree = ast.parse(text, filename=rel)
    findings: list[dict[str, object]] = []
    scopes: list[ast.Module | ast.ClassDef] = [tree]
    scopes.extend(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    for scope in scopes:
        scope_name = getattr(scope, "name", "<module>")
        seen_names: dict[str, int] = {}
        for node in scope.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            previous = seen_names.get(node.name)
            if previous is not None:
                findings.append({
                    "path": rel, "kind": "DUPLICATE_DEFINITION", "scope": scope_name,
                    "name": node.name, "first_line": previous, "duplicate_line": node.lineno,
                })
            else:
                seen_names[node.name] = node.lineno
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen_keys: dict[tuple[str, object], int] = {}
        for key_node in node.keys:
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, (str, int, float, bytes, bool, type(None))):
                continue
            value = key_node.value
            identity: tuple[str, object]
            if isinstance(value, str):
                identity = ("str", unicodedata.normalize("NFC", value))
            else:
                identity = (type(value).__name__, value)
            previous = seen_keys.get(identity)
            if previous is not None:
                findings.append({
                    "path": rel, "kind": "DUPLICATE_LITERAL_DICT_KEY", "key": repr(value),
                    "first_line": previous, "duplicate_line": key_node.lineno,
                })
            else:
                seen_keys[identity] = key_node.lineno
    return findings


def _syntax_check() -> dict:
    findings: list[dict[str, object]] = []
    python_count = 0
    json_count = 0
    for relative in ("equity_foresight_signal", "tools", "tests"):
        base = ROOT / relative
        for path in sorted(base.rglob("*.py")):
            if any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
                continue
            python_count += 1
            rel = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
                compile(text, rel, "exec", dont_inherit=True)
                findings.extend(_python_structure_findings(text, rel))
            except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
                findings.append({"path": rel, "kind": "PYTHON_PARSE_ERROR", "error_type": type(exc).__name__, "message": str(exc)})
    for path in sorted(ROOT.rglob("*.json")):
        if any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        json_count += 1
        rel = path.relative_to(ROOT).as_posix()
        try:
            json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            findings.append({"path": rel, "kind": "JSON_PARSE_ERROR", "error_type": type(exc).__name__, "message": str(exc)})
    return {
        "status": "PASS" if not findings else "FAIL",
        "checked_python_files": python_count,
        "checked_json_files": json_count,
        "findings": findings,
    }


def _secret_scan() -> dict:
    findings = []
    count = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.is_symlink() or any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".yaml", ".yml", ".sh", ".txt"}:
            continue
        count += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"path": path.relative_to(ROOT).as_posix(), "pattern": name})
    return {"status": "PASS" if not findings else "FAIL", "scanned_files": count, "findings": findings}


def _subject_sha256() -> str:
    # Bind exactly the final installed Skill tree. Source worktrees map files into
    # their installed destinations; assembled Skill roots hash their own tree.
    source_marker = ROOT / "taskpack_blueprint" / "skill_draft" / "equity-foresight-signal" / "SKILL.md"
    if source_marker.is_file():
        return _FORMAL_SUBJECT.source_subject_sha256(ROOT)
    return _FORMAL_SUBJECT.packaged_subject_sha256(ROOT)


def _statistical_checks(determinism_iterations: int, fuzz_cases: int, fuzz_seed: int) -> dict:
    if sys.platform.startswith("linux"):
        context = multiprocessing.get_context("fork")
        with concurrent.futures.ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
            det_future = executor.submit(_determinism, determinism_iterations)
            fuzz_future = executor.submit(_fuzz, fuzz_cases, fuzz_seed)
            runtime_determinism = det_future.result(timeout=300)
            contract_fuzz = fuzz_future.result(timeout=300)
    else:
        runtime_determinism = _determinism(determinism_iterations)
        contract_fuzz = _fuzz(fuzz_cases, fuzz_seed)
    return {
        "runtime_determinism": runtime_determinism,
        "training_determinism": _training(7),
        "contract_fuzz": contract_fuzz,
    }


def _component_report(
    component: str,
    checks: dict[str, dict],
    *,
    expected_subject_sha256: str | None = None,
) -> dict:
    current_subject = _subject_sha256()
    if expected_subject_sha256 is not None and current_subject != expected_subject_sha256:
        checks = dict(checks)
        checks["subject_integrity"] = {
            "status": "FAIL",
            "expected_subject_sha256": expected_subject_sha256,
            "actual_subject_sha256": current_subject,
        }
    failures = [key for key, value in checks.items() if value.get("status") != "PASS"]
    report = {
        "schema": "efs.formal_runtime_component.v1",
        "component": component,
        "subject": "equity-foresight-signal-v0.0.0.1-shadow-only",
        "subject_sha256": expected_subject_sha256 or current_subject,
        "status": "PASS" if not failures else "FAIL",
        "failed_checks": failures,
        "checks": checks,
        "capability_ceiling": "SHADOW_ONLY",
        "outcome_status": "NOT_PROVEN",
        "claim_boundary": "ENGINEERING_COMPONENT_NOT_EXTERNAL_INDEPENDENT_REVIEW",
    }
    report["report_sha256"] = sha256_hex(report)
    return report


def _write_report(report: dict, output: Path | None) -> None:
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")


def _load_component(path: Path, expected_component: str, expected_subject: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "efs.formal_runtime_component.v1" or data.get("component") != expected_component:
        raise ValueError(f"invalid component receipt: {expected_component}")
    claimed = data.get("report_sha256")
    payload = dict(data)
    payload.pop("report_sha256", None)
    if claimed != sha256_hex(payload):
        raise ValueError(f"component receipt hash mismatch: {expected_component}")
    if data.get("subject_sha256") != expected_subject:
        raise ValueError(f"component subject mismatch: {expected_component}")
    return data


def _aggregate(component_dir: Path, *, expected_subject_sha256: str | None = None) -> dict:
    current_subject = _subject_sha256()
    if expected_subject_sha256 is not None and current_subject != expected_subject_sha256:
        raise ValueError("aggregate subject changed after component execution")
    expected_subject = expected_subject_sha256 or current_subject
    components = {
        name: _load_component(component_dir / f"{name}.json", name, expected_subject)
        for name in COMPONENTS
    }
    checks: dict[str, dict] = {}
    for component in components.values():
        checks.update(component["checks"])
    failures = [key for key, value in checks.items() if value.get("status") != "PASS"]
    report = {
        "schema": SCHEMA,
        "subject": "equity-foresight-signal-v0.0.0.1-shadow-only",
        "subject_sha256": expected_subject,
        "status": "PASS" if not failures and all(item["status"] == "PASS" for item in components.values()) else "FAIL",
        "capability_ceiling": "SHADOW_ONLY",
        "outcome_status": "NOT_PROVEN",
        "failed_checks": failures,
        "component_receipts": {name: item["report_sha256"] for name, item in components.items()},
        "checks": checks,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
        "macos_launchd_units": 0,
        "local_persistent_bytes_after_invocation": 0,
        "resident_background_processes_after_invocation": 0,
        "claim_boundary": "ENGINEERING_FORMAL_CANDIDATE_NOT_OUTCOME_PROOF_NOT_EXTERNAL_INDEPENDENT_REVIEW",
    }
    report["report_sha256"] = sha256_hex(report)
    return report


def _run_component(name: str, args: argparse.Namespace) -> dict:
    if name in _active_test_component_modules():
        checks = {name: _test_component(name)}
        if name == "tests_contracts":
            checks["compile"] = _syntax_check()
        return _component_report(
            name,
            checks,
            expected_subject_sha256=args.expected_subject_sha256,
        )
    if name == "specialized_tests":
        return _component_report(
            "specialized_tests",
            {"specialized_tests": _specialized_test_suite()},
            expected_subject_sha256=args.expected_subject_sha256,
        )
    if name == "statistical":
        return _component_report(
            "statistical",
            _statistical_checks(args.determinism_iterations, args.fuzz_cases, args.fuzz_seed),
            expected_subject_sha256=args.expected_subject_sha256,
        )
    if name == "isolation":
        return _component_report(
            "isolation",
            {
                "kernel_seccomp_isolation": _isolation("run_kernel_isolation.py"),
                "network_namespace_isolation": _isolation("run_network_namespace_isolation.py"),
                "macos_zero_persistent_footprint": _isolation("verify_macos_zero_footprint.py"),
            },
            expected_subject_sha256=args.expected_subject_sha256,
        )
    if name == "static":
        return _component_report(
            "static",
            {
                "runtime_static_audit": audit_runtime_source(ROOT / "equity_foresight_signal"),
                "secret_scan": _secret_scan(),
            },
            expected_subject_sha256=args.expected_subject_sha256,
        )
    raise ValueError(f"unsupported component: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--component", choices=("all", *COMPONENTS, "aggregate"), default="all")
    parser.add_argument("--component-dir", type=Path)
    parser.add_argument("--expected-subject-sha256")
    parser.add_argument("--print-subject-sha256", action="store_true")
    parser.add_argument("--determinism-iterations", type=int, default=10_000)
    parser.add_argument("--fuzz-cases", type=int, default=10_000)
    parser.add_argument("--fuzz-seed", type=int, default=20_260_727)
    args = parser.parse_args()
    if args.print_subject_sha256:
        print(_subject_sha256())
        return 0
    if args.expected_subject_sha256 is not None:
        value = args.expected_subject_sha256
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            parser.error("--expected-subject-sha256 must be lowercase SHA-256 hex")
    if args.component == "aggregate":
        if args.component_dir is None:
            parser.error("--component-dir is required for aggregate")
        report = _aggregate(
            args.component_dir,
            expected_subject_sha256=args.expected_subject_sha256,
        )
    elif args.component == "all":
        reports = {
            name: _run_component(name, args)
            for name in COMPONENTS
        }
        checks: dict[str, dict] = {}
        for item in reports.values():
            checks.update(item["checks"])
        failures = [key for key, value in checks.items() if value.get("status") != "PASS"]
        report = {
            "schema": SCHEMA,
            "subject": "equity-foresight-signal-v0.0.0.1-shadow-only",
            "subject_sha256": args.expected_subject_sha256 or _subject_sha256(),
            "status": "PASS" if not failures else "FAIL",
            "capability_ceiling": "SHADOW_ONLY",
            "outcome_status": "NOT_PROVEN",
            "failed_checks": failures,
            "component_receipts": {name: item["report_sha256"] for name, item in reports.items()},
            "checks": checks,
            "agent_invocations_total": 0,
            "llm_requests_total": 0,
            "llm_input_tokens_total": 0,
            "llm_output_tokens_total": 0,
            "network_requests_total": 0,
            "macos_launchd_units": 0,
            "local_persistent_bytes_after_invocation": 0,
            "resident_background_processes_after_invocation": 0,
            "claim_boundary": "ENGINEERING_FORMAL_CANDIDATE_NOT_OUTCOME_PROOF_NOT_EXTERNAL_INDEPENDENT_REVIEW",
        }
        report["report_sha256"] = sha256_hex(report)
    else:
        report = _run_component(args.component, args)
    _write_report(report, args.output)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
