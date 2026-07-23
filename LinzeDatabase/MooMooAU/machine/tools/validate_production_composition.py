#!/usr/bin/env python3
"""Read-only validator for the RMD-04 production composition contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
CONTRACT_PATH = Path("machine/contracts/production_composition.json")
SCHEMA_PATH = Path("schemas/production-composition-v1.schema.json")
WORKFLOW_PATH = Path(".github/workflows/moomooau-production.yml")
EXPECTED_SECRET_NAMES = [
    "MOOMOOAU_PRODUCTION_CONFIG",
    "MOOMOOAU_SENDER_REGISTRY",
    "MOOMOOAU_CLASSIFICATION_REGISTRY",
    "MOOMOOAU_PARSER_REGISTRY",
    "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
    "MOOMOOAU_AGE_IDENTITY",
    "MOOMOOAU_OPAQUE_ID_KEY",
    "MOOMOOAU_GMAIL_OAUTH",
]
EXPECTED_SOURCE_PATHS = {
    "src/moomooau_archive/capacity.py",
    "src/moomooau_archive/kill_switch.py",
    "src/moomooau_archive/operation_gate.py",
    "src/moomooau_archive/production.py",
    "src/moomooau_archive/production_adapters.py",
    "src/moomooau_archive/gmail_sync_checkpoint.py",
    "src/moomooau_archive/ga_runtime.py",
    "tests/remediation/test_rmd04.py",
    "tests/remediation/test_rmd05.py",
    "tests/tasks/test_t0607.py",
    "tests/tasks/test_t0704.py",
    "schemas/production-config-v1.schema.json",
}


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path = PROJECT_ROOT) -> dict[str, object]:
    root = root.resolve()
    repository_root = root.parents[1]
    failures: list[str] = []
    contract_path = root / CONTRACT_PATH
    schema_path = root / SCHEMA_PATH
    workflow_path = repository_root / WORKFLOW_PATH
    if not contract_path.is_file() or not schema_path.is_file() or not workflow_path.is_file():
        return {
            "schema_version": "moomooau.production-composition-validation.v1",
            "status": "FAIL",
            "failures": ["RMD-04 composition contract, schema or Workflow is missing"],
            "external_writes": 0,
            "protected_oracles_executed": 0,
            "production_workflow_runs": 0,
        }
    try:
        contract = _load(contract_path)
        schema = _load(schema_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        failures.append("RMD-04 composition contract or schema is not valid JSON")
        contract = {}
        schema = {}
    if schema:
        for error in Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(contract):
            location = ".".join(str(item) for item in error.absolute_path) or "$"
            failures.append(f"composition schema violation at {location}")

    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_contract = contract.get("workflow", {})
    if not isinstance(workflow_contract, dict) or workflow_contract.get("sha256") != _sha256(
        workflow_path
    ):
        failures.append("production Workflow digest differs from the composition contract")
    source_digests = contract.get("source_digests", {})
    if not isinstance(source_digests, dict) or set(source_digests) != EXPECTED_SOURCE_PATHS:
        failures.append("production source digest map is invalid")
    else:
        for relative, digest_contract in source_digests.items():
            path = root / relative
            if (
                not isinstance(relative, str)
                or not isinstance(digest_contract, dict)
                or set(digest_contract) != {"sha256"}
                or not isinstance(digest_contract.get("sha256"), str)
                or not path.is_file()
                or path.is_symlink()
                or _sha256(path) != digest_contract["sha256"]
            ):
                failures.append("production source digest differs from the composition contract")
                break

    required_workflow_tokens = (
        'cron: "30 4 * * *"',
        'timezone: "Australia/Sydney"',
        "MOOMOOAU_PRODUCTION_ENABLED == 'true'",
        "environment: moomooau-production",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        "python -m moomooau_archive.production",
        "--execute-protected",
        '--event-name "$EVENT_NAME"',
    )
    contract_secret_names = contract.get("secret_names")
    actual_secret_names = re.findall(
        r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}",
        workflow,
    )
    if (
        any(token not in workflow for token in required_workflow_tokens)
        or contract_secret_names != EXPECTED_SECRET_NAMES
        or actual_secret_names != EXPECTED_SECRET_NAMES
    ):
        failures.append("production Workflow binding differs from the composition contract")

    try:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "moomooau_archive.production",
                "--contract-only",
            ],
            cwd=root,
            env={
                "PYTHONPATH": str(root / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            check=False,
            timeout=30,
        )
        public = json.loads(process.stdout)
    except (OSError, subprocess.TimeoutExpired, UnicodeError, json.JSONDecodeError):
        process = None
        public = None
    if (
        process is None
        or process.returncode != 0
        or process.stderr
        or not isinstance(public, dict)
        or public.get("status") != "CONTRACT_ONLY_NO_EXECUTION"
        or public.get("secret_names") != EXPECTED_SECRET_NAMES
        or public.get("production_health_claimed") is not False
        or any(
            public.get(key) != 0
            for key in (
                "real_gmail_calls",
                "private_repository_calls",
                "protected_oracles_executed",
                "production_workflow_runs",
            )
        )
    ):
        failures.append("production contract-only CLI is not a zero-effect offline descriptor")

    observation = contract.get("observation", {})
    zero_effect_keys = (
        "real_gmail_calls",
        "private_repository_calls",
        "protected_oracles_executed",
        "production_workflow_runs",
        "external_writes",
        "remote_publications",
    )
    if not isinstance(observation, dict) or any(
        observation.get(key) != 0 for key in zero_effect_keys
    ):
        failures.append("RMD-04 observation overstates real or protected execution")
    return {
        "schema_version": "moomooau.production-composition-validation.v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "synthetic_full_pipeline_runs": (
            observation.get("synthetic_full_pipeline_runs", 0)
            if isinstance(observation, dict)
            else 0
        ),
        "external_writes": 0,
        "protected_oracles_executed": 0,
        "production_workflow_runs": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = validate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
