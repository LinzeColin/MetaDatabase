#!/usr/bin/env python3
"""Build a deterministic exact-commit cloud acceptance Corresponding Source artifact."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO


EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
COMMON_REQUIRED_SOURCE_PATHS = (
    "LICENSE",
    "app/LICENSE",
    "app/package-lock.json",
    "app/scripts/cloud-supervisor.js",
    "docs/evidence/CB-000/LICENSE_COMPLIANCE.md",
    "machine/facts/post-baseline-change-ledger.json",
    "vendor/timeline-for-agent/LICENSE",
    "vendor/whereabouts-mcp/LICENSE",
)
TASKS = {
    "CB-130": {
        "phase": "P1.4",
        "contract": "docs/governance/RUN_CONTRACT_P1_4_CB_130.md",
        "stage_prefix": ".cb130-artifacts-",
    },
    "CB-140": {
        "phase": "P1.5",
        "contract": "docs/governance/RUN_CONTRACT_P1_5_CB_140.md",
        "stage_prefix": ".cb140-artifacts-",
    },
    "CB-200": {
        "phase": "P2.1",
        "contract": "docs/governance/RUN_CONTRACT_P2_1_CB_200.md",
        "stage_prefix": ".cb200-artifacts-",
    },
    "CB-210": {
        "phase": "P2.2",
        "contract": "docs/governance/RUN_CONTRACT_P2_2_CB_210.md",
        "stage_prefix": ".cb210-artifacts-",
    },
    "CB-220": {
        "phase": "P2.3",
        "contract": "docs/governance/RUN_CONTRACT_P2_3_CB_220.md",
        "stage_prefix": ".cb220-artifacts-",
    },
}


class BuildViolation(RuntimeError):
    """The requested build violates the frozen cloud artifact contract."""


def expect(condition: bool, code: str) -> None:
    if not condition:
        raise BuildViolation(code)


def command(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise BuildViolation(
            f"command:{args[0]}:{result.returncode}:{result.stderr.strip()[:160]}"
        )
    return result.stdout.rstrip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha256(repo: Path, commit: str, relative: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:CyberBoss/{relative}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise BuildViolation(
            f"git_blob:{relative}:{result.returncode}:"
            f"{result.stderr.decode('utf-8', 'replace').strip()[:120]}"
        )
    return hashlib.sha256(result.stdout).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o644)


def gzip_stream(source: BinaryIO, destination: Path) -> None:
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            shutil.copyfileobj(source, zipped, length=1024 * 1024)


def create_source_archive(repo: Path, commit: str, output: Path) -> None:
    process = subprocess.Popen(
        [
            "git",
            "-C",
            str(repo),
            "archive",
            "--format=tar",
            "--prefix=cyberboss-source/",
            f"{commit}:CyberBoss",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    gzip_stream(process.stdout, output)
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
    if process.wait() != 0:
        raise BuildViolation(f"source_archive:{stderr.strip()[:160]}")
    output.chmod(0o644)


def assert_remote_branch_absent(repo: Path) -> None:
    result = subprocess.run(
        [
            "git",
            "ls-remote",
            "--exit-code",
            "--heads",
            "origin",
            f"refs/heads/{EXPECTED_BRANCH}",
        ],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    expect(result.returncode == 2 and not result.stdout.strip(), "remote_publication")


def build_durable_inbox_matrix(
    repo: Path,
    commit: str,
    stage: Path,
) -> Path:
    with tempfile.TemporaryDirectory(prefix=".cb210-runtime-", dir=stage.parent) as raw:
        runtime = Path(raw)
        key_file = runtime / "synthetic.key"
        runtime_state = runtime / "state"
        output = runtime / "output"
        runtime_state.mkdir(mode=0o700)
        output.mkdir(mode=0o700)
        key_file.write_bytes(os.urandom(32))
        key_file.chmod(0o400)
        result = subprocess.run(
            [
                "node",
                str(
                    repo
                    / "CyberBoss/app/scripts/durable-inbox-acceptance.js"
                ),
                "--runtime-root",
                str(runtime_state),
                "--key-file",
                str(key_file),
                "--output-directory",
                str(output),
                "--release-commit",
                commit,
                "--target-id-sha256",
                "7865f743d174",
            ],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
        )
        expect(
            result.returncode == 0
            and "CB210_ACCEPTANCE=PASS" in result.stdout,
            "durable_inbox_acceptance",
        )
        generated = output / "durable-inbox-matrix.json"
        report = json.loads(generated.read_text(encoding="utf-8"))
        expect(
            report.get("task_id") == "CB-210"
            and report.get("phase") == "P2.2"
            and report.get("release_commit") == commit
            and report.get("result") == "passed"
            and report.get("replay", {}).get("replay_count") == 1000
            and report.get("replay", {}).get("execution_count") == 1
            and report.get("database", {}).get(
                "canonical_reconcile_set_diff"
            )
            == 0,
            "durable_inbox_matrix",
        )
        destination = stage / "durable-inbox-matrix.json"
        shutil.copyfile(generated, destination)
        destination.chmod(0o644)
        return destination


def build_job_scheduler_matrix(
    repo: Path,
    commit: str,
    stage: Path,
) -> Path:
    with tempfile.TemporaryDirectory(prefix=".cb220-runtime-", dir=stage.parent) as raw:
        output = Path(raw) / "job-scheduler-acceptance.json"
        result = subprocess.run(
            [
                "node",
                str(repo / "CyberBoss/app/scripts/job-scheduler-acceptance.js"),
                "--output",
                str(output),
            ],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
        )
        expect(
            result.returncode == 0
            and "CB220_JOB_SCHEDULER_ACCEPTANCE=PASS" in result.stdout,
            "job_scheduler_acceptance",
        )
        report = json.loads(output.read_text(encoding="utf-8"))
        expect(
            report.get("task_id") == "CB-220"
            and report.get("phase") == "P2.3"
            and report.get("result") == "passed"
            and report.get("scheduler", {}).get(
                "max_active_runtime_leases"
            )
            == 1
            and report.get("scheduler", {}).get("fifo_dispatch_order")
            is True
            and report.get("workspace", {}).get(
                "symlink_escape_dispatched"
            )
            is False
            and report.get("recovery", {}).get(
                "ambiguous_mutation_replayed"
            )
            is False,
            "job_scheduler_matrix",
        )
        destination = stage / "job-scheduler-acceptance.json"
        shutil.copyfile(output, destination)
        destination.chmod(0o644)
        return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-id", choices=sorted(TASKS), default="CB-130")
    args = parser.parse_args()

    try:
        task = TASKS[args.task_id]
        repo = args.repo.resolve(strict=True)
        output = args.output
        expect(output.is_absolute(), "output_absolute")
        expect(not output.exists(), "output_exists")
        expect(re.fullmatch(r"[0-9a-f]{40}", args.commit) is not None, "commit_format")
        expect(command(["git", "rev-parse", "HEAD"], repo) == args.commit, "head")
        expect(
            command(["git", "branch", "--show-current"], repo) == EXPECTED_BRANCH,
            "branch",
        )
        expect(
            command(["git", "remote", "get-url", "origin"], repo)
            == EXPECTED_ORIGIN,
            "origin",
        )
        expect(command(["git", "remote"], repo).splitlines() == ["origin"], "remotes")
        expect(command(["git", "status", "--porcelain=v1"], repo) == "", "dirty")
        assert_remote_branch_absent(repo)
        inventory = set(
            command(
                ["git", "ls-tree", "-r", "--name-only", f"{args.commit}:CyberBoss"],
                repo,
            ).splitlines()
        )
        for required in (*COMMON_REQUIRED_SOURCE_PATHS, task["contract"]):
            expect(required in inventory, f"source_missing:{required}")
        if args.task_id == "CB-140":
            for required in (
                "app/src/core/walking-skeleton-trace.js",
                "app/test/cloud-walking-skeleton.test.js",
                "app/test/cloud-walking-skeleton-live.test.js",
                "docs/product_design/v0.0.0.4/implementation-kit/scripts/"
                "run-walking-skeleton-acceptance.mjs",
            ):
                expect(required in inventory, f"source_missing:{required}")
        if args.task_id == "CB-200":
            for required in (
                "app/migrations/001_runtime_spool.sql",
                "app/migrations/002_cb200_retention_and_transitions.sql",
                "app/scripts/runtime-spool-acceptance.js",
                "app/src/services/db/database-adapter.js",
                "app/src/services/jobs/job-state-machine.js",
                "app/test/job-state-machine.test.js",
                "app/test/runtime-spool.test.js",
            ):
                expect(required in inventory, f"source_missing:{required}")
        if args.task_id == "CB-210":
            for required in (
                "app/scripts/durable-inbox-acceptance.js",
                "app/src/adapters/channel/weixin/index.js",
                "app/src/adapters/channel/weixin/sync-buffer-store.js",
                "app/src/services/db/database-adapter.js",
                "app/src/services/inbox/durable-inbox.js",
                "app/test/durable-inbox-crash-cut.test.js",
                "app/test/weixin-cursor-commit.test.js",
            ):
                expect(required in inventory, f"source_missing:{required}")
        if args.task_id == "CB-220":
            for required in (
                "app/migrations/001_runtime_spool.sql",
                "app/migrations/002_cb200_retention_and_transitions.sql",
                "app/migrations/003_cb220_scheduler_control.sql",
                "app/scripts/job-scheduler-acceptance.js",
                "app/src/adapters/runtime/claudecode/events.js",
                "app/src/adapters/runtime/codex/events.js",
                "app/src/services/db/database-adapter.js",
                "app/src/services/jobs/job-scheduler.js",
                "app/src/services/jobs/resource-readiness-gate.js",
                "app/test/job-scheduler.test.js",
                "app/test/resource-readiness-gate.test.js",
                "app/test/workspace-scope.test.js",
                "docs/product_design/v0.0.0.4/implementation-kit/scripts/"
                "resource-pressure-fixture.py",
            ):
                expect(required in inventory, f"source_missing:{required}")

        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=task["stage_prefix"], dir=output.parent)
        )
        try:
            archive_name = f"cyberboss-source-{args.commit}.tar.gz"
            archive_path = stage / archive_name
            create_source_archive(repo, args.commit, archive_path)
            manifest = {
                "schema_version": 1,
                "task_id": args.task_id,
                "phase": task["phase"],
                "release_commit": args.commit,
                "branch": EXPECTED_BRANCH,
                "repository": "LinzeColin/MetaDatabase",
                "repository_tree": command(
                    ["git", "rev-parse", f"{args.commit}^{{tree}}"], repo
                ),
                "cyberboss_tree": command(
                    ["git", "rev-parse", f"{args.commit}:CyberBoss"], repo
                ),
                "source": {
                    "archive": archive_name,
                    "sha256": sha256(archive_path),
                    "corresponding_source_complete": True,
                    "original_licenses_preserved": True,
                    "license_expression": STRICT_LICENSE,
                    "conflict_record":
                    "docs/evidence/CB-000/LICENSE_COMPLIANCE.md",
                    "modification_record":
                    "machine/facts/post-baseline-change-ledger.json",
                    "upstream_clarification_received": False,
                },
                "process_family": {
                    "systemd_unit": "cyberboss-cloud.service",
                    "kill_mode": "control-group",
                    "detached_children": False,
                    "runtime_endpoint": "ws://127.0.0.1:8765",
                    "status_endpoint": "http://127.0.0.1:8780",
                    "simulator_when_auth_pending": True,
                    "configuration_only_provider_switch": True,
                },
                "deployment": {
                    "candidate_only": True,
                    "switch_current": False,
                    "enable_service": False,
                    "activate_real_credentials": False,
                    "clone_private_database": False,
                    "remote_publication": "none",
                },
            }
            if args.task_id == "CB-140":
                manifest["walking_skeleton"] = {
                    "simulator_e2e_expected": 10,
                    "latency_samples_expected": 20,
                    "max_input_bytes": 32768,
                    "trace_raw_content_allowed": False,
                    "mac_dependency_allowed": False,
                    "real_adapters": "activation_pending",
                    "pg_1_executed": False,
                    "stage_2_spool_claimed": False,
                }
            if args.task_id == "CB-200":
                manifest["runtime_spool"] = {
                    "schema_version": 2,
                    "migration_mode": "additive_backward_compatible",
                    "migration_sha256": {
                        "001_runtime_spool.sql": git_blob_sha256(
                            repo,
                            args.commit,
                            "app/migrations/001_runtime_spool.sql",
                        ),
                        "002_cb200_retention_and_transitions.sql":
                            git_blob_sha256(
                                repo,
                                args.commit,
                                "app/migrations/"
                                "002_cb200_retention_and_transitions.sql",
                            ),
                    },
                    "journal_mode": "WAL",
                    "synchronous": "FULL",
                    "foreign_keys": True,
                    "busy_timeout_ms": 5000,
                    "active_payload_encryption": "AES-256-GCM",
                    "active_payload_ttl_hours": 24,
                    "real_canonical_sync": False,
                    "channel_poll_integrated": False,
                    "scheduler_integrated": False,
                    "outbox_worker_integrated": False,
                    "pg_2_executed": False,
                }
            if args.task_id == "CB-210":
                manifest["runtime_spool"] = {
                    "schema_version": 2,
                    "migration_mode": "additive_backward_compatible",
                    "migration_sha256": {
                        "001_runtime_spool.sql": git_blob_sha256(
                            repo,
                            args.commit,
                            "app/migrations/001_runtime_spool.sql",
                        ),
                        "002_cb200_retention_and_transitions.sql":
                            git_blob_sha256(
                                repo,
                                args.commit,
                                "app/migrations/"
                                "002_cb200_retention_and_transitions.sql",
                            ),
                    },
                    "journal_mode": "WAL",
                    "synchronous": "FULL",
                    "foreign_keys": True,
                    "busy_timeout_ms": 5000,
                    "active_payload_encryption": "AES-256-GCM",
                    "active_payload_ttl_hours": 24,
                    "real_canonical_sync": False,
                    "channel_poll_integrated": True,
                    "scheduler_integrated": False,
                    "outbox_worker_integrated": False,
                    "pg_2_executed": False,
                }
                manifest["durable_inbox"] = {
                    "candidate_cursor_api": True,
                    "cursor_commit_after_durable": True,
                    "numeric_continuity_guard": True,
                    "stable_source_id_required": True,
                    "replay_count": 1000,
                    "crash_cut_points": [
                        "after_fetch_before_durable",
                        "after_durable_before_cursor",
                        "after_cursor",
                    ],
                    "active_payload_encryption": "AES-256-GCM",
                    "channel_poll_integrated": True,
                    "scheduler_integrated": False,
                    "outbox_worker_integrated": False,
                    "real_wechat": False,
                    "real_runtime": False,
                    "pg_2_executed": False,
                }
            if args.task_id == "CB-220":
                manifest["runtime_spool"] = {
                    "schema_version": 3,
                    "migration_mode": "additive_backward_compatible",
                    "migration_sha256": {
                        "001_runtime_spool.sql": git_blob_sha256(
                            repo,
                            args.commit,
                            "app/migrations/001_runtime_spool.sql",
                        ),
                        "002_cb200_retention_and_transitions.sql":
                            git_blob_sha256(
                                repo,
                                args.commit,
                                "app/migrations/"
                                "002_cb200_retention_and_transitions.sql",
                            ),
                        "003_cb220_scheduler_control.sql":
                            git_blob_sha256(
                                repo,
                                args.commit,
                                "app/migrations/"
                                "003_cb220_scheduler_control.sql",
                            ),
                    },
                    "journal_mode": "WAL",
                    "synchronous": "FULL",
                    "foreign_keys": True,
                    "busy_timeout_ms": 5000,
                    "active_payload_encryption": "AES-256-GCM",
                    "active_payload_ttl_hours": 24,
                    "real_canonical_sync": False,
                    "channel_poll_integrated": True,
                    "scheduler_integrated": True,
                    "outbox_worker_integrated": False,
                    "pg_2_executed": False,
                }
                manifest["durable_inbox"] = {
                    "candidate_cursor_api": True,
                    "cursor_commit_after_durable": True,
                    "numeric_continuity_guard": True,
                    "stable_source_id_required": True,
                    "active_payload_encryption": "AES-256-GCM",
                    "channel_poll_integrated": True,
                    "scheduler_integrated": True,
                    "outbox_worker_integrated": False,
                    "real_wechat": False,
                    "real_runtime": False,
                    "pg_2_executed": False,
                }
                manifest["job_scheduler"] = {
                    "single_runtime_lease": True,
                    "max_runtime_concurrency": 1,
                    "fifo_order": "created_at,id",
                    "transactional_claim": True,
                    "heartbeat_and_expiry": True,
                    "command_runtime_planes_separated": True,
                    "workspace_alias_gate": True,
                    "resource_readiness_gate": True,
                    "truthful_stop_terminal": True,
                    "unsafe_mutation_auto_replay": False,
                    "outbox_worker_integrated": False,
                    "real_wechat": False,
                    "real_runtime": False,
                    "pg_2_executed": False,
                }
            manifest_path = stage / "artifact-manifest.json"
            write_json(manifest_path, manifest)
            matrix_path = (
                build_durable_inbox_matrix(repo, args.commit, stage)
                if args.task_id == "CB-210"
                else (
                    build_job_scheduler_matrix(repo, args.commit, stage)
                    if args.task_id == "CB-220"
                    else None
                )
            )
            checksum_lines = [
                f"{sha256(manifest_path)}  {manifest_path.name}",
                f"{sha256(archive_path)}  {archive_path.name}",
            ]
            if matrix_path is not None:
                checksum_lines.append(
                    f"{sha256(matrix_path)}  {matrix_path.name}"
                )
            checksums = stage / "SHA256SUMS"
            checksums.write_text("\n".join(sorted(checksum_lines)) + "\n", encoding="utf-8")
            checksums.chmod(0o644)
            stage.rename(output)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    except (BuildViolation, OSError, ValueError) as error:
        print(f"{args.task_id.replace('-', '')}_ARTIFACT_BUILD=FAIL reason={error}")
        return 2

    print(
        f"{args.task_id.replace('-', '')}_ARTIFACT_BUILD=PASS "
        f"release_id={args.commit} "
        f"artifacts={4 if args.task_id in {'CB-210', 'CB-220'} else 3} "
        "corresponding_source_complete=true "
        "license_expression=AGPL-3.0-only_AND_GPL-3.0-only "
        "upstream_clarification_received=false publication=none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
