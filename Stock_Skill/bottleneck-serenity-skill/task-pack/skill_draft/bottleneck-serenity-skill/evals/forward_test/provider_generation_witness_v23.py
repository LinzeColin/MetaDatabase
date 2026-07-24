#!/usr/bin/env python3
"""Run a reviewer-observed fresh provider generation inside a deny-default boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CONTROL_DIR = Path(__file__).resolve().parent
DEFAULT_SKILL_ROOT = CONTROL_DIR.parents[1]
TASK_NAME = "provider_generation_v23_task.txt"
SCHEMA_NAME = "provider_generation_v23.schema.json"
PROTOCOL_NAME = "provider_generation_v23_protocol.json"
EXPECTED_DRAFT_FIELDS = {
    "memo_markdown",
    "evidence_json",
    "opportunity_json",
    "portfolio_json",
    "decision_label",
    "research_trace",
}
EXPECTED_TRACE_FIELDS = {
    "files_read",
    "web_searches",
    "pages_opened",
    "files_written",
    "limitations",
}
PRODUCTION_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/backtest_and_evals.md",
    "references/failure_modes.md",
    "references/integration_contract.md",
    "references/methodology.md",
    "references/output_contract.md",
    "references/portfolio_risk.md",
    "references/research_workflow.md",
    "references/scoring_model.md",
    "references/serenity_audit.md",
    "references/source_catalog.md",
    "references/source_policy.md",
    "schemas/evidence.schema.json",
    "schemas/opportunity.schema.json",
    "schemas/portfolio.schema.json",
    "scripts/analyze_portfolio_clusters.py",
    "scripts/new_research_case.py",
    "scripts/prepare_forward_output_v18.py",
    "scripts/prepare_forward_output_v19.py",
    "scripts/presentation_contract.py",
    "scripts/score_opportunity.py",
    "scripts/validate_evidence.py",
    "templates/candidate_card.md",
    "templates/evidence_ledger.csv",
    "templates/investment_memo.md",
    "templates/monitor_plan.csv",
    "templates/research_config.json",
    "templates/theme_map.md",
    "templates/thesis_ledger.csv",
)
DECISION_LABELS = {
    "RESEARCH_PRIORITY",
    "CANDIDATE",
    "WATCH_PRICED",
    "WATCH_EVIDENCE",
    "BOTTLENECK_NOT_EQUITY",
    "AVOID",
    "BROKEN",
}
FORBIDDEN_TASK_MARKERS = (
    "provider_attestation_v2",
    "remediation_v1",
    "prior result",
    "expected score",
    "expected decision",
    "judge_a",
    "judge_b",
)


class WitnessError(ValueError):
    """Raised when the live witness contract cannot be admitted."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WitnessError(f"{label} is not readable canonical JSON") from exc
    if not isinstance(value, dict):
        raise WitnessError(f"{label} must be one JSON object")
    return value


def production_tree(skill_root: Path) -> tuple[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    digest_input = bytearray()
    for relative in PRODUCTION_PATHS:
        path = skill_root / relative
        if path.is_symlink() or not path.is_file():
            raise WitnessError(f"production projection path is unavailable: {relative}")
        raw = path.read_bytes()
        mode = "0755" if path.stat().st_mode & stat.S_IXUSR else "0644"
        digest = sha256_bytes(raw)
        rows.append(
            {
                "path": relative,
                "mode": mode,
                "byte_count": len(raw),
                "sha256": digest,
            }
        )
        digest_input.extend(
            f"{mode} {relative} {len(raw)} {digest}\n".encode("utf-8")
        )
    return sha256_bytes(bytes(digest_input)), rows


def validate_schema_shape(schema: dict[str, Any]) -> None:
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or set(schema.get("required", [])) != EXPECTED_DRAFT_FIELDS
        or set(schema.get("properties", {})) != EXPECTED_DRAFT_FIELDS
    ):
        raise WitnessError("v23 output schema top-level contract drift")
    trace = schema["properties"].get("research_trace", {})
    if (
        trace.get("type") != "object"
        or trace.get("additionalProperties") is not False
        or set(trace.get("required", [])) != EXPECTED_TRACE_FIELDS
        or set(trace.get("properties", {})) != EXPECTED_TRACE_FIELDS
    ):
        raise WitnessError("v23 output schema trace contract drift")


def validate_controls(skill_root: Path) -> dict[str, Any]:
    protocol = load_json(CONTROL_DIR / PROTOCOL_NAME, "v23 protocol")
    schema = load_json(CONTROL_DIR / SCHEMA_NAME, "v23 schema")
    validate_schema_shape(schema)
    task_bytes = (CONTROL_DIR / TASK_NAME).read_bytes()
    task_text = task_bytes.decode("utf-8")
    if not task_bytes.endswith(b"\n") or any(
        marker in task_text.casefold() for marker in FORBIDDEN_TASK_MARKERS
    ):
        raise WitnessError("v23 task leaks prior output, diagnosis, or expectation")
    tree_sha256, rows = production_tree(skill_root)
    expected_bindings = {
        TASK_NAME: sha256_bytes(task_bytes),
        SCHEMA_NAME: sha256_bytes((CONTROL_DIR / SCHEMA_NAME).read_bytes()),
        Path(__file__).name: sha256_bytes(Path(__file__).read_bytes()),
    }
    context = protocol.get("context_contract", {})
    if (
        protocol.get("protocol_id")
        != "BSS-S3-P3-T016-provider-generation-v23"
        or protocol.get("status") != "READY_FOR_T017_REREVIEW"
        or protocol.get("review_task") != "BSS-S3-P3-T017"
        or protocol.get("artifact_bindings") != expected_bindings
        or context.get("production_file_count") != len(PRODUCTION_PATHS)
        or context.get("production_tree_sha256") != tree_sha256
        or any(
            context.get(key) is not False
            for key in (
                "prior_answers_present",
                "prior_diagnoses_present",
                "judge_commentary_present",
                "examples_present",
                "tests_present",
                "task_pack_present",
            )
        )
        or protocol.get("admission", {}).get(
            "live_reviewer_observation_required"
        )
        is not True
    ):
        raise WitnessError("v23 protocol binding drift")
    return {
        "status": "PASS",
        "protocol_id": protocol["protocol_id"],
        "production_file_count": len(rows),
        "production_tree_sha256": tree_sha256,
        "task_sha256": expected_bindings[TASK_NAME],
        "schema_sha256": expected_bindings[SCHEMA_NAME],
        "witness_sha256": expected_bindings[Path(__file__).name],
        "live_reviewer_observation_required": True,
    }


def copy_projection(skill_root: Path, projection: Path) -> None:
    for relative in PRODUCTION_PATHS:
        source = skill_root / relative
        target = projection / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def sandbox_profile(
    denied_roots: tuple[Path, ...],
) -> str:
    clauses = "\n".join(
        f'(deny file-read* (subpath "{path.resolve()}"))\n'
        f'(deny file-write* (subpath "{path.resolve()}"))'
        for path in denied_roots
    )
    return (
        "(version 1)\n"
        "(allow default)\n"
        f"{clauses}\n"
    )


def excluded_roots(skill_root: Path) -> tuple[Path, ...]:
    repository_root = next(
        (
            parent
            for parent in (skill_root, *skill_root.parents)
            if (parent / ".git").exists()
        ),
        None,
    )
    if repository_root is None:
        raise WitnessError("cannot resolve repository root for denied boundary")
    github_project = (
        repository_root.parent.parent
        if repository_root.parent.name == "_scratch"
        else repository_root.parent
    )
    candidates = (
        github_project,
        Path.home() / "Downloads" / "TaskPack",
        Path.home() / ".codex" / "sessions",
        Path.home() / ".codex" / "archived_sessions",
        Path.home() / ".codex" / "worktrees",
        Path.home() / ".codex" / "history.jsonl",
        Path.home() / ".agents" / "skills",
        Path.home() / ".codex" / "skills",
    )
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


def run_probe(
    sandbox_exec: str,
    profile_path: Path,
    target: Path,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sandbox_exec,
            "-f",
            str(profile_path),
            "/usr/bin/head",
            "-c",
            "1",
            str(target),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def validate_returned_draft(value: dict[str, Any]) -> None:
    if set(value) != EXPECTED_DRAFT_FIELDS:
        raise WitnessError("provider return fields do not match v23 schema")
    if value.get("decision_label") not in DECISION_LABELS:
        raise WitnessError("provider return decision label is outside contract")
    for field in EXPECTED_DRAFT_FIELDS - {"research_trace"}:
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise WitnessError(f"provider return {field} must be nonempty text")
    trace = value.get("research_trace")
    if not isinstance(trace, dict) or set(trace) != EXPECTED_TRACE_FIELDS:
        raise WitnessError("provider return research_trace shape drift")
    for field in EXPECTED_TRACE_FIELDS:
        items = trace.get(field)
        if not isinstance(items, list) or not items or not all(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise WitnessError(f"provider return research_trace.{field} is invalid")


def run_live(
    skill_root: Path,
    codex_binary: Path,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    controls = validate_controls(skill_root)
    if platform.system() != "Darwin":
        raise WitnessError("v23 live boundary requires macOS sandbox-exec")
    sandbox_exec = shutil.which("sandbox-exec")
    if sandbox_exec is None:
        raise WitnessError("sandbox-exec is unavailable")
    excluded_subject = (
        skill_root / "evals/forward_test/remediation_v19_raw.json"
    )
    if not excluded_subject.is_file():
        raise WitnessError("denied-source probe target is unavailable")

    with tempfile.TemporaryDirectory(prefix="bss-v23-live-witness-") as raw:
        temporary_root = Path(raw)
        projection = temporary_root / "projection"
        control = temporary_root / "control"
        output = temporary_root / "output"
        projection.mkdir()
        control.mkdir()
        output.mkdir()
        copy_projection(skill_root, projection)
        copied_schema = control / SCHEMA_NAME
        copied_schema.write_bytes((CONTROL_DIR / SCHEMA_NAME).read_bytes())
        profile_path = control / "provider.sb"
        profile_path.write_text(
            sandbox_profile(excluded_roots(skill_root)),
            encoding="utf-8",
        )
        allowed_probe = run_probe(
            sandbox_exec,
            profile_path,
            projection / "SKILL.md",
        )
        denied_probe = run_probe(
            sandbox_exec,
            profile_path,
            excluded_subject,
        )
        if allowed_probe.returncode != 0 or denied_probe.returncode == 0:
            raise WitnessError("external filesystem boundary probe failed")

        last_message = output / "exact_provider_return.json"
        command = [
            sandbox_exec,
            "-f",
            str(profile_path),
            str(codex_binary),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            model,
            "--output-schema",
            str(copied_schema),
            "--output-last-message",
            str(last_message),
            "--cd",
            str(projection),
            "-",
        ]
        task_bytes = (CONTROL_DIR / TASK_NAME).read_bytes()
        try:
            provider = subprocess.run(
                command,
                cwd=temporary_root,
                input=task_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                env={
                    "HOME": str(Path.home()),
                    "LANG": "C",
                    "LC_ALL": "C",
                    "LOGNAME": os.environ.get("LOGNAME", ""),
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "TMPDIR": str(temporary_root),
                    "USER": os.environ.get("USER", ""),
                },
            )
        except subprocess.TimeoutExpired as exc:
            raise WitnessError("provider generation exceeded live timeout") from exc
        if provider.returncode != 0 or not last_message.is_file():
            raise WitnessError(
                "provider generation failed; "
                f"exit={provider.returncode}; "
                f"stdout_sha256={sha256_bytes(provider.stdout)}; "
                f"stderr_sha256={sha256_bytes(provider.stderr)}"
            )

        exact_return = last_message.read_bytes()
        try:
            returned = json.loads(exact_return.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WitnessError("exact provider return is not JSON") from exc
        if not isinstance(returned, dict):
            raise WitnessError("exact provider return is not one object")
        validate_returned_draft(returned)

        draft_path = output / "draft_v23.json"
        draft_path.write_bytes(exact_return)
        prepared_path = output / "prepared_v23.json"
        protocol_sha256 = sha256_bytes(
            (CONTROL_DIR / PROTOCOL_NAME).read_bytes()
        )
        prepare = subprocess.run(
            [
                sys.executable,
                "-B",
                "scripts/prepare_forward_output_v19.py",
                str(draft_path),
                str(prepared_path),
                "--preexecution-seal-sha",
                protocol_sha256,
            ],
            cwd=projection,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if prepare.returncode != 0 or not prepared_path.is_file():
            raise WitnessError(
                "host replay rejected exact provider return; "
                f"exit={prepare.returncode}; "
                f"stdout_sha256={sha256_bytes(prepare.stdout)}; "
                f"stderr_sha256={sha256_bytes(prepare.stderr)}"
            )
        prepared = load_json(prepared_path, "prepared provider return")
        if any(
            prepared.get(field) != returned.get(field)
            for field in EXPECTED_DRAFT_FIELDS - {"research_trace"}
        ):
            raise WitnessError("host preparation changed a primary returned field")

        return {
            **controls,
            "status": "LIVE_WITNESS_PASS",
            "provider_process_exit_code": provider.returncode,
            "allowed_projection_probe_exit_code": allowed_probe.returncode,
            "denied_source_probe_exit_code": denied_probe.returncode,
            "exact_provider_return_sha256": sha256_bytes(exact_return),
            "exact_provider_return_byte_count": len(exact_return),
            "provider_stdout_sha256": sha256_bytes(provider.stdout),
            "provider_stderr_sha256": sha256_bytes(provider.stderr),
            "host_prepare_exit_code": prepare.returncode,
            "host_prepare_stdout_sha256": sha256_bytes(prepare.stdout),
            "prepared_output_sha256": sha256_bytes(prepared_path.read_bytes()),
            "decision_label": returned["decision_label"],
            "web_search_count": len(returned["research_trace"]["web_searches"]),
            "page_count": len(returned["research_trace"]["pages_opened"]),
            "prior_answer_or_diagnosis_available_in_projection": False,
            "reviewer_observed_live_process": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--codex-bin", type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    skill_root = args.skill_root.resolve()
    try:
        if args.live:
            codex_binary = args.codex_bin
            if codex_binary is None:
                resolved = shutil.which("codex")
                if resolved is None:
                    raise WitnessError("codex executable is unavailable")
                codex_binary = Path(resolved)
            result = run_live(
                skill_root,
                codex_binary.resolve(),
                args.model,
                args.timeout_seconds,
            )
        else:
            result = validate_controls(skill_root)
    except (OSError, UnicodeError, WitnessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
