#!/usr/bin/env python3
"""Build a deterministic exact-commit CB-130 Corresponding Source artifact."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO


EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
REQUIRED_SOURCE_PATHS = (
    "LICENSE",
    "app/LICENSE",
    "app/package-lock.json",
    "app/scripts/cloud-supervisor.js",
    "docs/evidence/CB-000/LICENSE_COMPLIANCE.md",
    "docs/governance/RUN_CONTRACT_P1_4_CB_130.md",
    "machine/facts/post-baseline-change-ledger.json",
    "vendor/timeline-for-agent/LICENSE",
    "vendor/whereabouts-mcp/LICENSE",
)


class BuildViolation(RuntimeError):
    """The requested build is not the frozen CB-130 artifact build."""


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
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
        for required in REQUIRED_SOURCE_PATHS:
            expect(required in inventory, f"source_missing:{required}")

        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=".cb130-artifacts-", dir=output.parent)
        )
        try:
            archive_name = f"cyberboss-source-{args.commit}.tar.gz"
            archive_path = stage / archive_name
            create_source_archive(repo, args.commit, archive_path)
            manifest = {
                "schema_version": 1,
                "task_id": "CB-130",
                "phase": "P1.4",
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
            manifest_path = stage / "artifact-manifest.json"
            write_json(manifest_path, manifest)
            checksum_lines = [
                f"{sha256(manifest_path)}  {manifest_path.name}",
                f"{sha256(archive_path)}  {archive_path.name}",
            ]
            checksums = stage / "SHA256SUMS"
            checksums.write_text("\n".join(sorted(checksum_lines)) + "\n", encoding="utf-8")
            checksums.chmod(0o644)
            stage.rename(output)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    except (BuildViolation, OSError, ValueError) as error:
        print(f"CB130_ARTIFACT_BUILD=FAIL reason={error}")
        return 2

    print(
        "CB130_ARTIFACT_BUILD=PASS "
        f"release_id={args.commit} artifacts=3 "
        "corresponding_source_complete=true "
        "license_expression=AGPL-3.0-only_AND_GPL-3.0-only "
        "upstream_clarification_received=false publication=none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
